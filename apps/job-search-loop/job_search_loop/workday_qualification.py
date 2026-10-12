from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .agent_runner import AgentRunner, wrap_untrusted
from .ats import detect_provider
from .ledger import Ledger, WORKDAY_FIT_POLICY_VERSION
from .state import canonical_url


_REQUIRED = {
    "decision",
    "mandatory_evidence",
    "unsupported_gaps",
    "interview_thesis",
    "location_feasibility",
    "compensation_thesis",
    "compensation_uncertain",
    "resume_variant",
}
POLICY_VERSION = WORKDAY_FIT_POLICY_VERSION
EMAIL_RE = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
LONG_DIGIT_RE = re.compile(r"\d{7,}")
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:token|api[_-]key|secret|password)\s*[:=]\s*\S+"
)
SK_TOKEN_RE = re.compile(r"(?i)\bsk-\S+")


def _safe_provider_text(
    value: Any, maximum: int, *, redact_sensitive: bool = True
) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text:
        return None
    if redact_sensitive and (
        EMAIL_RE.search(text)
        or LONG_DIGIT_RE.search(text)
        or SENSITIVE_ASSIGNMENT_RE.search(text)
        or SK_TOKEN_RE.search(text)
    ):
        return "[redacted]"
    return text[:maximum]


def _http_failure_receipt(row: dict[str, Any], error: Exception) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if isinstance(error, HTTPError):
        try:
            parsed = json.loads(error.read(32_768))
            if isinstance(parsed, dict):
                payload = parsed
        except (OSError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
            pass
        finally:
            error.close()
    provider_error_code = _safe_provider_text(payload.get("errorCode"), 80)
    provider_message = _safe_provider_text(payload.get("message"), 240)
    if provider_message is None and isinstance(error, ValueError):
        provider_message = _safe_provider_text(str(error), 240)
    return {
        "status": "qualification_retryable_failure",
        "application_id": str(row["application_id"]),
        "company": _safe_provider_text(row.get("company"), 240) or "",
        "title": _safe_provider_text(row.get("title"), 240) or "",
        "canonical_url": (
            _safe_provider_text(
                row.get("canonical_url"), 2048, redact_sensitive=False
            )
            or ""
        ),
        "error": type(error).__name__,
        "http_status": error.code if isinstance(error, HTTPError) else None,
        "provider_error_code": provider_error_code,
        "provider_message": provider_message,
    }


def fetch_official_posting(
    url: str, sources: tuple[dict[str, str], ...]
) -> dict[str, Any]:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    source = next(
        (item for item in sources if item["host"].casefold() == host), None
    )
    if source is None:
        raise ValueError("unknown Workday tenant")
    marker = "/job/"
    if marker not in parsed.path:
        raise ValueError("Workday URL has no job path")
    job_path = marker + parsed.path.split(marker, 1)[1]
    endpoint = (
        f"https://{source['host']}/wday/cxs/{source['tenant']}/"
        f"{source['site']}{job_path}"
    )
    request = Request(
        endpoint,
        headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0 job-search-loop/1.0"},
    )
    with urlopen(request, timeout=20) as response:
        if urlsplit(response.geturl()).hostname.casefold() != host:
            raise ValueError("Workday detail redirected off tenant")
        payload = json.load(response)
    info = payload.get("jobPostingInfo") if isinstance(payload, dict) else None
    description = info.get("jobDescription") if isinstance(info, dict) else None
    if not isinstance(description, str) or not description.strip():
        raise ValueError("official Workday description is missing")
    return payload


def fetch_official_description(url: str, sources: tuple[dict[str, str], ...]) -> str:
    return fetch_official_posting(url, sources)['jobPostingInfo']['jobDescription'][:80_000]


def _validate(result: dict[str, Any]) -> None:
    if set(result) != _REQUIRED:
        raise ValueError("Workday fit result fields do not match the contract")
    if result["decision"] not in {"qualified", "rejected", "hold"}:
        raise ValueError("invalid Workday fit decision")
    if not isinstance(result["mandatory_evidence"], list) or not all(
        isinstance(value, str) for value in result["mandatory_evidence"]
    ):
        raise ValueError("mandatory_evidence must be a string array")
    if not isinstance(result["unsupported_gaps"], list) or not all(
        isinstance(value, str) for value in result["unsupported_gaps"]
    ):
        raise ValueError("unsupported_gaps must be a string array")
    for key in (
        "interview_thesis",
        "location_feasibility",
        "compensation_thesis",
        "resume_variant",
    ):
        if not isinstance(result[key], str) or not result[key].strip():
            raise ValueError(f"{key} must be a nonempty string")
    if not isinstance(result["compensation_uncertain"], bool):
        raise ValueError("compensation_uncertain must be boolean")


def qualify_one(
    *,
    ledger_path: Path,
    candidate_memory_path: Path,
    fetch_description: Callable[[str], str],
    run_model: Callable[[str], dict[str, Any]],
    allowed_hosts: set[str] | None = None,
    excluded_application_ids: frozenset[str] = frozenset(),
    preferred_urls: tuple[str, ...] = (),
) -> dict[str, Any]:
    ledger = Ledger(ledger_path)
    try:
        preferred_rank: dict[str, int] = {}
        for index, url in enumerate(preferred_urls):
            preferred_rank.setdefault(canonical_url(str(url)).casefold(), index)
        candidates = []
        fit_rows = [
            *ledger.pending_materials_ready_applications(),
            *ledger.superseded_workday_fit_rejections(POLICY_VERSION),
        ]
        for row in fit_rows:
            if str(row["application_id"]) in excluded_application_ids:
                continue
            if detect_provider(str(row["canonical_url"])) != "workday":
                continue
            host = (urlsplit(str(row["canonical_url"])).hostname or "").casefold()
            if allowed_hosts is not None and host not in allowed_hosts:
                continue
            fit = ledger.connection.execute(
                """
                SELECT decision, policy_version
                FROM workday_fit_decisions
                WHERE application_id = ?
                """,
                (row["application_id"],),
            ).fetchone()
            if fit is None or (
                str(fit["decision"]) in {"hold", "rejected", "qualified"}
                and str(fit["policy_version"] or "") != POLICY_VERSION
            ):
                candidates.append(row)
        if not candidates:
            return {"status": "no_pending_workday_fit"}
        candidates.sort(
            key=lambda row: preferred_rank.get(
                canonical_url(str(row["canonical_url"])).casefold(),
                len(preferred_urls),
            )
        )
        row = candidates[0]
        try:
            description = fetch_description(str(row["canonical_url"])).strip()
            if not description:
                raise ValueError("official Workday description is empty")
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            return _http_failure_receipt(row, error)
        candidate_memory = candidate_memory_path.read_text(encoding="utf-8")
        prompt = (
            "Evaluate exactly one Workday job under the no-voluntary-skip policy. "
            "Use only evidence in the candidate memory and official job description. "
            "Do not infer missing skills, years, management scope, credentials, salary, "
            "or work authorization. Judge mandatory requirements and the candidate's "
            "supported application scope. Remote, onsite, and hybrid roles in every country "
            "are in scope; no country, location, or work arrangement is a location-only "
            "rejection reason. This global location preference supersedes any narrower stored "
            "location preference. Sponsorship status alone is not a reason to reject any role, "
            "including when sponsorship is stated as unavailable or left unstated; the "
            "employer decides whether to make an exception. Never claim authorization "
            "or sponsorship without candidate-memory evidence; answer every work-authorization and sponsorship question truthfully. "
            "Keep remote roles "
            "worldwide in scope without inferring country-specific work authorization. "
            "Use the user's target of USD 100,000 annual gross base "
            "or the clearly equivalent amount in another currency. If compensation is "
            "unpublished, state uncertainty and never invent a range, but do not reject or "
            "hold for unpublished compensation alone. Applying is free: pessimism about interview "
            "odds is not permission to skip. Qualify every role when location is eligible, "
            "every form answer can be truthful, and grounded "
            "evidence is adjacent to any core part of the work. Missing preferred years, exact "
            "stack, perfect title match, management tenure, or published compensation must remain "
            "an honest gap and can never cause reject or hold. Canonical example: a Tokyo customer "
            "implementation role that asks for five years is qualified when the candidate has "
            "grounded production AI implementation evidence, even with fewer stated years. Reject "
            "only for an objective hard blocker or user-excluded executive scope: an explicit required credential "
            "the candidate lacks, "
            "a required false attestation, a closed posting, stated compensation below the configured "
            "target, no grounded connection to the core work at all, or actual responsibilities "
            "that require unsupported executive experience. CEO or C-suite roles are outside "
            "the user's target. Do not reject a role based on title alone: senior, lead, director, "
            "manager, and people-management roles remain eligible when the full responsibilities "
            "and mandatory requirements fit the candidate's evidence. For every role, read the "
            "complete responsibilities rather than guessing scope from one word. Hold only "
            "for one unknown that prevents a truthful application, never for ordinary uncertainty. Write "
            "interview_thesis, location_feasibility, and "
            "compensation_thesis in concise natural Japanese for the user's realtime "
            "Telegram report. Return only the schema.\n\n"
            + wrap_untrusted(
                "job",
                json.dumps(
                    {
                        "company": row["company"],
                        "title": row["title"],
                        "canonical_url": row["canonical_url"],
                        "official_description": description,
                    },
                    ensure_ascii=False,
                ),
            )
            + "\n\n"
            + wrap_untrusted("candidate_memory", candidate_memory)
        )
        result = run_model(prompt)
        if not isinstance(result, dict):
            raise ValueError("Workday fit result must be an object")
        _validate(result)
        evidence_sha256 = hashlib.sha256(
            json.dumps(result, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        ledger.record_workday_fit_decision(
            str(row["application_id"]),
            str(result["decision"]),
            evidence_sha256,
            policy_version=POLICY_VERSION,
        )
        return {
            "status": "decided",
            "application_id": row["application_id"],
            "company": row["company"],
            "title": row["title"],
            "decision": result["decision"],
            "reason": result["interview_thesis"],
            "compensation": result["compensation_thesis"],
            "evidence_sha256": evidence_sha256,
        }
    finally:
        ledger.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--candidate-memory", required=True, type=Path)
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--runner", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    runner = AgentRunner(evidence_root=args.evidence_root, runner_path=args.runner)
    source_payload = json.loads(args.sources.read_text(encoding="utf-8"))
    sources = tuple(dict(row) for row in source_payload.get("sources", []))
    allowed_hosts = {str(row["host"]).casefold() for row in sources}
    result = qualify_one(
        ledger_path=args.ledger,
        candidate_memory_path=args.candidate_memory,
        fetch_description=lambda url: fetch_official_description(url, sources),
        run_model=lambda prompt: runner.run(
            task="improve",
            prompt=prompt,
            schema_path=args.schema,
            workdir=args.workdir,
            run_id=f"workday-fit-{uuid.uuid4().hex}",
        ),
        allowed_hosts=allowed_hosts,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(args.output, 0o600)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
