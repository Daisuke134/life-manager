from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import unicodedata
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from .inbox import mark_messages_seen, message_is_seen
from .ledger import FenceError, Ledger


_WRAPPED_CONTENT = re.compile(
    r'\A<<<EXTERNAL_UNTRUSTED_CONTENT id="[^"]+">>>\n'
    r"Source: google_api\n---\n"
    r"(.*)\n"
    r'<<<END_EXTERNAL_UNTRUSTED_CONTENT id="[^"]+">>>\Z',
    re.DOTALL,
)
_CONFIRMATION_TERMS = (
    "applicationreceived",
    "thankyouforapplying",
    "thanksforapplying",
    "thankyouforyouronlinesubmission",
    "thankyouforyourinterest",
    "applicationsubmitted",
    "wehavereceivedyourapplication",
    "wevereceivedyourapplication",
    "wevegotyourapplication",
    "hasbeenreceived",
    "応募が完了",
    "応募を受け付け",
    "応募を受付",
    "ご応募いただ",
    "ご応募ありがとう",
    "エントリーが完了",
    "応募受付",
)
_CONFIRMATION_SEARCH_QUERY = (
    'newer_than:30d ("application received" OR '
    '"received your application" OR "thank you for applying" OR '
    '"thanks for applying" OR "thank you for your online submission" OR '
    '"thank you for your interest" OR "has been received" OR '
    '"got your application" OR "応募が完了" OR "応募を受け付け" OR '
    '"ご応募いただ" OR "ご応募ありがとう" OR from:myworkday.com OR '
    'from:myworkdayjobs.com)'
)
# Inbox invokes receipt reconciliation before and after the candidate pass.
# Child-call timeouts total at most 220 seconds: 3 searches, 10 threads, 4 postings.
_CONFIRMATION_SEARCH_PAGE_SIZE = 5
_CONFIRMATION_SEARCH_TIMEOUT_SECONDS = 20
_CONFIRMATION_THREAD_TIMEOUT_SECONDS = 8
_WORKDAY_POSTING_READBACK_LIMIT = 4
_RETRYABLE_CONFIRMATION_READBACK_FAILURES = frozenset(
    {"gmail_thread_readback_failed", "official_posting_readback_unavailable"}
)


class _OfficialPostingReadbackBudgetExceeded(ValueError):
    pass


def _unwrap(value: Any) -> str:
    text = str(value or "").strip()
    match = _WRAPPED_CONTENT.fullmatch(text)
    return match.group(1).strip() if match else text


def _fold(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", value).casefold()
        if character.isalnum()
    )


def _sender_matches(sender: str, canonical_url: str) -> bool:
    sender_address = parseaddr(sender)[1].casefold()
    if "@" not in sender_address:
        return False
    sender_host = sender_address.rsplit("@", 1)[1].rstrip(".")
    job_host = (urlsplit(canonical_url).hostname or "").casefold().rstrip(".")
    if not sender_host or not job_host:
        return False
    if job_host == "jobs.ashbyhq.com":
        return sender_host == "ashbyhq.com" or sender_host.endswith(
            ".ashbyhq.com"
        )
    if "workday" in job_host:
        return sender_host in {"myworkday.com", "myworkdayjobs.com"} or any(
            sender_host.endswith(f".{domain}")
            for domain in ("myworkday.com", "myworkdayjobs.com")
        )
    return (
        sender_host == job_host
        or sender_host.endswith(f".{job_host}")
        or job_host.endswith(f".{sender_host}")
    )


def _message_from_payload(value: dict[str, Any]) -> dict[str, Any] | None:
    message_id = str(value.get("id") or "")
    thread_id = str(value.get("threadId") or "")
    headers = value.get("headers")
    if not isinstance(headers, dict):
        return None
    try:
        received_at = datetime.fromtimestamp(
            int(value.get("internalDate")) / 1000,
            tz=timezone.utc,
        ).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_-]+", message_id):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_-]+", thread_id):
        return None
    return {
        "message_id": message_id,
        "thread_id": thread_id,
        "sender": _unwrap(headers.get("from")),
        "recipient": _unwrap(
            headers.get("delivered-to")
            or headers.get("to")
            or headers.get("x-original-to")
        ),
        "subject": _unwrap(headers.get("subject")),
        "body": _unwrap(value.get("body")),
        "received_at": received_at,
    }


def _exact_receipt_role(message: dict[str, str], title: str) -> bool:
    normalize = lambda value: ' '.join(unicodedata.normalize('NFKC', value).casefold().split())
    body = normalize(message['body'])
    roles = []
    for pattern in (r'\bapplication for (.+?)(?:\.(?:\s|$)|$)',
                    r'\bapplying (?:to|for) (.+?) at ',
                    r'\sの\s+(.+?)\s+の職務にご応募いただき'):
        roles.extend(match.group(1).strip() for match in re.finditer(pattern, body))
    return set(roles) == {normalize(title)}


def _confirmation_matches(
    message: dict[str, str],
    candidate: dict[str, str],
    expected_recipient: str | None = None,
) -> bool:
    subject_and_body = _fold(f"{message['subject']}\n{message['body']}")
    company_context = _fold(
        f"{message['sender']}\n{message['subject']}\n{message['body']}"
    )
    return (
        (
            expected_recipient is None
            or parseaddr(message["recipient"])[1].casefold()
            == expected_recipient.casefold()
        )
        and any(term in subject_and_body for term in _CONFIRMATION_TERMS)
        and _fold(candidate["company"]) in company_context
        and _fold(candidate["title"]) in subject_and_body
        and _sender_matches(message["sender"], candidate["canonical_url"])
    )


def _confirmation_matches_without_title(
    message: dict[str, str],
    candidate: dict[str, str],
    expected_recipient: str | None = None,
) -> bool:
    hostname = urlsplit(candidate["canonical_url"]).hostname or ""
    if "workday" in hostname.casefold():
        return False
    subject_and_body = _fold(f"{message['subject']}\n{message['body']}")
    company_context = _fold(
        f"{message['sender']}\n{message['subject']}\n{message['body']}"
    )
    return (
        (
            expected_recipient is None
            or parseaddr(message["recipient"])[1].casefold()
            == expected_recipient.casefold()
        )
        and any(term in subject_and_body for term in _CONFIRMATION_TERMS)
        and _fold(candidate["company"]) in company_context
        and _sender_matches(message["sender"], candidate["canonical_url"])
    )


def _workday_hiring_receipt_matches(message, candidate, expected_recipient, loader):
    if loader is None or expected_recipient is None or 'workday' not in urlsplit(candidate['canonical_url']).hostname:
        return False
    if not _sender_matches(message['sender'], candidate['canonical_url']):
        return False
    if parseaddr(message['recipient'])[1].casefold() != expected_recipient.casefold():
        return False
    body = ' '.join(unicodedata.normalize('NFKC', message['body']).split())
    title = ' '.join(unicodedata.normalize('NFKC', candidate['title']).split())
    receipt = re.search(r'(?:^|,\s*)([^,]+?)\s*の\s*' + re.escape(title)
                        + r'\s*の職務にご応募いただき', body)
    if not receipt:
        return False
    brand = receipt.group(1).strip()
    if not brand or len(brand) > 200:
        return False
    posting = loader(candidate)
    info = posting.get('jobPostingInfo', {})
    if _fold(str(info.get('title') or '')) != _fold(candidate['title']):
        return False
    organization = posting.get('hiringOrganization') or {}
    logo = info.get('logoImage') or {}
    organization_name = organization.get('name', '') if isinstance(organization, dict) else ''
    logo_alt = str(logo.get('alt') or '') if isinstance(logo, dict) else ''
    names = {_fold(str(organization_name))}
    # This is the provider's structured employer branding field, not a mention
    # of a customer, vendor or product in a description.
    if logo_alt.casefold().endswith(' logo'):
        names.add(_fold(logo_alt[:-5]))
    if _fold(brand) not in names:
        return False
    candidate['official_posting_sha256'] = hashlib.sha256(json.dumps(posting, sort_keys=True).encode()).hexdigest()
    candidate['official_hiring_brand'] = brand
    return True


def _looks_like_confirmation_summary(thread: dict[str, Any]) -> bool:
    summary_text = _fold(
        f"{thread.get('subject', '')}\n{thread.get('snippet', '')}"
    )
    sender = parseaddr(str(thread.get('from') or ''))[1].casefold().rsplit('@', 1)[-1]
    official_workday = sender in {'myworkday.com', 'myworkdayjobs.com'} or sender.endswith(('.myworkday.com', '.myworkdayjobs.com'))
    return official_workday or any(term in summary_text for term in _CONFIRMATION_TERMS)


def _uncertain_candidates(ledger: Ledger) -> list[dict[str, str]]:
    rows = ledger.connection.execute(
        """
        SELECT
          applications.id AS application_id,
          applications.company,
          applications.title,
          applications.canonical_url,
          submit_intents.intent_id,
          submit_intents.created_at,
          applications.current_state
        FROM applications
        JOIN submit_intents
          ON submit_intents.application_id = applications.id
        WHERE (applications.current_state = 'submit_unknown' AND submit_intents.status = 'submit_unknown')
           OR (applications.current_state = 'not_submitted' AND submit_intents.status = 'not_submitted'
               AND submit_intents.outcome_evidence_class = 'rendered_validation_rejection')
        ORDER BY applications.created_at, applications.id
        """
    ).fetchall()
    return [
        {key: str(row[key]) for key in row.keys()}
        for row in rows
    ]


def _evidence_sha256(
    message: dict[str, str], candidate: dict[str, str]
) -> str:
    encoded = json.dumps(
        {
            "message": message,
            "application_id": candidate["application_id"],
            "intent_id": candidate["intent_id"],
            **({key: candidate[key] for key in ('official_posting_sha256', 'official_hiring_brand')}
               if 'official_posting_sha256' in candidate else {}),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def reconcile_confirmation_threads(
    *,
    ledger_path: Path,
    threads: list[dict[str, Any]],
    thread_loader: Callable[[str], dict[str, Any]],
    seen_state: Path,
    expected_recipient: str | None = None,
    official_posting_loader: Callable[[dict[str, str]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ledger = Ledger(ledger_path)
    reconciled: list[dict[str, str]] = []
    blocked: list[dict[str, str]] = []
    checked_threads = 0
    seen_messages_after_success: list[str] = []
    try:
        for thread in threads:
            thread_id = str(thread.get("id") or "")
            if (
                not re.fullmatch(r"[A-Za-z0-9_-]+", thread_id)
                or not _looks_like_confirmation_summary(thread)
            ):
                continue
            checked_threads += 1
            try:
                payload = thread_loader(thread_id)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                blocked.append(
                    {
                        "thread_id": thread_id,
                        "status": "gmail_thread_readback_failed",
                        "error_class": type(error).__name__,
                    }
                )
                continue
            messages = (
                payload.get("thread", {}).get("messages", [])
                if isinstance(payload, dict)
                else []
            )
            if not isinstance(messages, list):
                messages = []
            for raw_message in messages:
                if not isinstance(raw_message, dict):
                    continue
                message = _message_from_payload(raw_message)
                if message is None or message["thread_id"] != thread_id:
                    continue
                received_epoch = datetime.fromisoformat(
                    message["received_at"]
                ).timestamp()
                if message_is_seen(
                    seen_state,
                    message_id=message["message_id"],
                    thread_id=thread_id,
                    received_epoch=received_epoch,
                ):
                    continue
                uncertain = _uncertain_candidates(ledger)
                candidates = []
                readback_failed = False
                for candidate in uncertain:
                    if datetime.fromisoformat(message['received_at']) < datetime.fromisoformat(candidate['created_at']):
                        continue
                    matched = _confirmation_matches(message, candidate, expected_recipient)
                    if candidate['current_state'] == 'not_submitted':
                        matched = matched and _exact_receipt_role(message, candidate['title'])
                    if not matched:
                        try:
                            matched = _workday_hiring_receipt_matches(message, candidate, expected_recipient, official_posting_loader)
                        except (OSError, ValueError, KeyError, TypeError) as error:
                            readback_failed = True
                            status = (
                                "official_posting_readback_budget_exhausted"
                                if isinstance(error, _OfficialPostingReadbackBudgetExceeded)
                                else "official_posting_readback_unavailable"
                            )
                            blocked.append({'message_id': message['message_id'], 'thread_id': thread_id,
                                'application_id': candidate['application_id'], 'status': status,
                                'error_class': type(error).__name__})
                    if matched:
                        candidates.append(candidate)
                if readback_failed:
                    continue
                if not candidates:
                    candidates = [
                        candidate
                        for candidate in uncertain
                        if candidate['current_state'] == 'submit_unknown'
                        and _confirmation_matches_without_title(
                            message, candidate, expected_recipient
                        )
                    ]
                if len(candidates) != 1:
                    reason = (
                        "ambiguous_application_match"
                        if len(candidates) > 1
                        else "no_exact_uncertain_application"
                    )
                    blocked.append(
                        {
                            "message_id": message["message_id"],
                            "thread_id": thread_id,
                            "status": reason,
                        }
                    )
                    continue
                candidate = candidates[0]
                try:
                    status = ledger.reconcile_submission_confirmation(
                        intent_id=candidate["intent_id"],
                        message_id=message["message_id"],
                        thread_id=thread_id,
                        evidence_sha256=_evidence_sha256(message, candidate),
                        received_at=message["received_at"],
                    )
                except FenceError:
                    blocked.append(
                        {
                            "message_id": message["message_id"],
                            "thread_id": thread_id,
                            "status": "ledger_fence_blocked",
                        }
                    )
                    continue
                reconciled.append(
                    {
                        "application_id": candidate["application_id"],
                        "message_id": message["message_id"],
                        "thread_id": thread_id,
                        "status": status,
                    }
                )
                seen_messages_after_success.append(message["message_id"])
    finally:
        ledger.close()
    if seen_messages_after_success:
        mark_messages_seen(seen_state, seen_messages_after_success)
    return {
        "version": 1,
        "checked_threads": checked_threads,
        "reconciled": reconciled,
        "blocked": blocked,
    }


def _confirmation_search_cursor_path(seen_state: Path) -> Path:
    return Path(seen_state).with_name("submission-confirmation-page.json")


def _confirmation_search_query_sha256() -> str:
    return hashlib.sha256(_CONFIRMATION_SEARCH_QUERY.encode("utf-8")).hexdigest()


def _next_confirmation_page_token(
    *,
    fetched_page_token: str | None,
    next_page_token: str | None,
    newest_next_page_token: str | None,
    result: dict[str, Any] | None,
) -> str | None:
    blocked = result.get("blocked", []) if isinstance(result, dict) else []
    if fetched_page_token and any(
        isinstance(item, dict)
        and item.get("status") in _RETRYABLE_CONFIRMATION_READBACK_FAILURES
        for item in blocked
    ):
        return fetched_page_token
    return next_page_token or newest_next_page_token


def _read_search_page_token(path: Path, query_sha256: str) -> str | None:
    path = Path(path)
    if path.is_symlink():
        raise ValueError("unsafe_confirmation_search_cursor")
    try:
        if path.stat().st_mode & 0o077:
            raise ValueError("unsafe_confirmation_search_cursor")
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("version") != 1:
        return None
    if value.get("query_sha256") != query_sha256:
        return None
    token = value.get("next_page_token")
    if (
        not isinstance(token, str)
        or not token
        or len(token) > 4096
        or not token.isprintable()
    ):
        return None
    return token


def _write_search_page_token(
    path: Path, query_sha256: str, next_page_token: str | None
) -> None:
    path = Path(path)
    if path.is_symlink():
        raise ValueError("unsafe_confirmation_search_cursor")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    if next_page_token is not None and (
        not isinstance(next_page_token, str)
        or not next_page_token
        or len(next_page_token) > 4096
        or not next_page_token.isprintable()
    ):
        raise ValueError("invalid_confirmation_search_cursor")
    descriptor, temporary = tempfile.mkstemp(
        prefix=".submission-confirmation-page.", dir=path.parent
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "version": 1,
                    "query_sha256": query_sha256,
                    "next_page_token": next_page_token,
                },
                handle,
                sort_keys=True,
                separators=(",", ":"),
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _gmail_confirmation_threads(
    account: str, executable: str, *, page_token: str | None = None
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    base_args = [
        executable,
        "gmail",
        "search",
        "--account",
        account,
        "--json",
        "--max",
        str(_CONFIRMATION_SEARCH_PAGE_SIZE),
    ]

    def run_search(token: str | None) -> subprocess.CompletedProcess[str]:
        command = list(base_args)
        if token:
            command.append(f"--page={token}")
        command.append(_CONFIRMATION_SEARCH_QUERY)
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=_CONFIRMATION_SEARCH_TIMEOUT_SECONDS,
        )

    try:
        completed = run_search(page_token)
        fetched_page_token = page_token
    except subprocess.CalledProcessError:
        if not page_token:
            raise
        # Gmail page tokens can expire as the rolling 30-day result set changes.
        # Restart at the newest page; receipt writes remain message-ID idempotent.
        completed = run_search(None)
        fetched_page_token = None
    value = json.loads(completed.stdout)
    threads = value.get("threads", [])
    next_page_token = value.get("nextPageToken")
    if (
        not isinstance(next_page_token, str)
        or not next_page_token
        or len(next_page_token) > 4096
        or not next_page_token.isprintable()
    ):
        next_page_token = None
    return (
        [row for row in threads if isinstance(row, dict)],
        next_page_token,
        fetched_page_token,
    )


def _gmail_thread(
    account: str, thread_id: str, executable: str
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            executable,
            "gmail",
            "thread",
            "get",
            "--account",
            account,
            "--json",
            "--wrap-untrusted",
            "--full",
            "--sanitize-content",
            thread_id,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=_CONFIRMATION_THREAD_TIMEOUT_SECONDS,
    )
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise ValueError("gog Gmail thread result must be an object")
    return value


def _bounded_official_posting_loader(sources, fetcher, *, readback_limit: int):
    cache = {}
    attempts = 0

    def load(candidate):
        nonlocal attempts
        url = candidate["canonical_url"]
        if url not in cache:
            if attempts >= readback_limit:
                raise _OfficialPostingReadbackBudgetExceeded(
                    "workday_posting_readback_budget_exhausted"
                )
            attempts += 1
            cache[url] = fetcher(url, sources)
        return cache[url]

    return load


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("reconcile",))
    parser.add_argument("--account", required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--seen", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--gog",
        default=os.environ.get("JOB_SEARCH_GOG", "gog"),
    )
    args = parser.parse_args()

    from .workday_qualification import fetch_official_posting
    sources_path = args.ledger.parent / 'workday-sources.v1.json'
    sources = tuple(json.loads(sources_path.read_text()).get('sources', [])) if sources_path.exists() else ()
    official_posting = _bounded_official_posting_loader(
        sources,
        fetch_official_posting,
        readback_limit=_WORKDAY_POSTING_READBACK_LIMIT,
    )
    cursor_path = _confirmation_search_cursor_path(args.seen)
    query_sha256 = _confirmation_search_query_sha256()
    stored_page_token = _read_search_page_token(cursor_path, query_sha256)
    recent_threads, recent_next_page, _ = _gmail_confirmation_threads(
        args.account, args.gog
    )
    page_batches = [recent_threads]
    backlog_token = stored_page_token or recent_next_page
    next_page_token = recent_next_page
    backlog_threads: list[dict[str, Any]] = []
    backlog_next_page: str | None = None
    backlog_page_token_used: str | None = None
    if backlog_token:
        (
            backlog_threads,
            backlog_next_page,
            backlog_page_token_used,
        ) = _gmail_confirmation_threads(
            args.account, args.gog, page_token=backlog_token
        )
        page_batches.append(backlog_threads)

    recent_result = (
        reconcile_confirmation_threads(
            ledger_path=args.ledger,
            threads=recent_threads,
            thread_loader=lambda thread_id: _gmail_thread(
                args.account, thread_id, args.gog
            ),
            seen_state=args.seen,
            expected_recipient=args.account,
            official_posting_loader=official_posting,
        )
        if recent_threads
        else None
    )
    backlog_result = (
        reconcile_confirmation_threads(
            ledger_path=args.ledger,
            threads=backlog_threads,
            thread_loader=lambda thread_id: _gmail_thread(
                args.account, thread_id, args.gog
            ),
            seen_state=args.seen,
            expected_recipient=args.account,
            official_posting_loader=official_posting,
        )
        if backlog_threads
        else None
    )
    next_page_token = _next_confirmation_page_token(
        fetched_page_token=backlog_page_token_used,
        next_page_token=backlog_next_page,
        newest_next_page_token=recent_next_page,
        result=backlog_result,
    )
    page_results = [
        result for result in (recent_result, backlog_result) if result is not None
    ]
    result = {
        "version": 1,
        "checked_threads": sum(page["checked_threads"] for page in page_results),
        "reconciled": [
            row for page in page_results for row in page["reconciled"]
        ],
        "blocked": [row for page in page_results for row in page["blocked"]],
        "pagination": {
            "page_size": _CONFIRMATION_SEARCH_PAGE_SIZE,
            "pages_scanned": len(page_batches),
            "has_more": next_page_token is not None,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(args.output, 0o600)
    _write_search_page_token(cursor_path, query_sha256, next_page_token)


if __name__ == "__main__":
    main()
