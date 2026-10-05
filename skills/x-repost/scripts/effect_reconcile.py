#!/usr/bin/env python3
"""Reconcile one x-repost effect_unknown fence from its exact run and Postiz readback."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Mapping


OWNER_ID = "x-repost"
READBACK_ONLY_RELEASES = {
    "c16f437b93028ea5d94014a1fa32c091795cbee0",
    "86fa863d4fe04ec0b5c44e8a2e513e55edaf2928",
    "88872a85cc652877f242ead444108a813084cfc9",
    "4eb6bbbaeb9a8368895e6391e34e8c895908b0ec",
    "447e5b62693ce67b6ea94aa1993fb2a5a3e5d24b",
    "d3d7be63f7de25ddad49d7d8901aaab6d4a0ce66",
}
POSTIZ_INTEGRATION_ID = "cmt4l2jld031tqp0y8qtyo983"
POSTIZ_POSTS_URL = "https://api.postiz.com/public/v1/posts"
FINALITY_SECONDS = 900
MAX_POSTIZ_ROWS = 500
FENCE_START_TOLERANCE_SECONDS = 1
MAX_EVENT_BYTES = 16 * 1024 * 1024
MAX_POSTIZ_BYTES = 16 * 1024 * 1024
STATE_ROOT = Path(os.environ.get(
    "X_REPOST_STATE_DIR",
    "~/.local/state/life-manager/social-x/x-repost/en",
)).expanduser()
EVIDENCE_ROOT = Path(os.environ.get(
    "X_REPOST_EVIDENCE_ROOT", "~/loops/x-repost-en/evidence",
)).expanduser()
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
POSTIZ_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
X_URL = re.compile(
    r"^https://(?:x|twitter)\.com/([A-Za-z0-9_]+)/status/([0-9]+)$"
)
HASH = re.compile(r"^[0-9a-f]{64}$")
RELEASE_SHA = re.compile(r"^[0-9a-f]{40}$")


def _parse_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(dt.timezone.utc)


def _occurrence_run(occurrence_id: str) -> str | None:
    prefix = f"{OWNER_ID}:"
    if not isinstance(occurrence_id, str) or not occurrence_id.startswith(prefix):
        return None
    run_id = occurrence_id[len(prefix):]
    return run_id if RUN_ID.fullmatch(run_id) else None


def read_runtime_events(path: Path | None = None) -> list[dict[str, Any]] | None:
    """Read the owner event stream; malformed or oversized logs are inconclusive."""
    event_path = path or STATE_ROOT / "events.jsonl"
    try:
        data = event_path.read_bytes()
    except OSError:
        return None
    if len(data) > MAX_EVENT_BYTES:
        return None
    rows: list[dict[str, Any]] = []
    try:
        for line in data.splitlines():
            value = json.loads(line.decode("utf-8"))
            if not isinstance(value, dict):
                return None
            rows.append(value)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return rows


def _event_pairs(occurrence_id: str,
                 events: list[dict[str, Any]]) -> list[tuple[dict, dict]] | None:
    """Pair every reported attempt for a queued occurrence with its actual executor run."""
    original_run_id = _occurrence_run(occurrence_id)
    if original_run_id is None or not isinstance(events, list):
        return None
    reports = [row for row in events if isinstance(row, dict)
               and row.get("loop_id") == OWNER_ID and row.get("phase") == "report"
               and row.get("effect_status") == "unknown"
               and (row.get("occurrence_id") == occurrence_id
                    or (row.get("run_id") == original_run_id
                        and row.get("occurrence_id") in {None, occurrence_id}))]
    if not reports:
        return None
    pairs: list[tuple[dict, dict]] = []
    seen_run_ids: set[str] = set()
    for report in reports:
        run_id = report.get("run_id")
        if not isinstance(run_id, str) or RUN_ID.fullmatch(run_id) is None \
                or run_id in seen_run_ids:
            return None
        related = [row for row in events if isinstance(row, dict)
                   and row.get("loop_id") == OWNER_ID and row.get("run_id") == run_id]
        if len(related) != 2:
            return None
        if any(row.get("owner_id") not in {None, OWNER_ID}
               or row.get("effect_class") != "publish"
               or row.get("provider") != "shared-agent-runner"
               or not isinstance(row.get("release_sha"), str)
               or RELEASE_SHA.fullmatch(row["release_sha"]) is None
               for row in related):
            return None
        starts = [row for row in related if row.get("phase") == "execute"]
        run_reports = [row for row in related if row.get("phase") == "report"]
        if len(starts) != 1 or len(run_reports) != 1 or run_reports[0] is not report:
            return None
        start = starts[0]
        report_occurrence = report.get("occurrence_id")
        expected_report_occurrence = (
            report_occurrence == occurrence_id
            or (run_id == original_run_id and report_occurrence is None)
        )
        expected_start_occurrence = start.get("occurrence_id") in {
            None, occurrence_id, f"{OWNER_ID}:{run_id}",
        }
        if not expected_report_occurrence or not expected_start_occurrence:
            return None
        start_at = _parse_time(start.get("timestamp"))
        report_at = _parse_time(report.get("timestamp"))
        status, exit_code = report.get("status"), report.get("exit_code")
        valid_terminal = (
            (status == "pass" and exit_code in {None, 0}
             and report.get("blocker") is None)
            or (status == "fail" and type(exit_code) is int and exit_code != 0
                and isinstance(report.get("blocker"), str) and bool(report["blocker"]))
        )
        if (start_at is None or report_at is None or start_at >= report_at
                or start.get("status") != "running"
                or start.get("effect_status") != "started"
                or report.get("effect_status") != "unknown"
                or not valid_terminal
                or start.get("release_sha") != report.get("release_sha")):
            return None
        pairs.append((start, report))
        seen_run_ids.add(run_id)
    pairs.sort(key=lambda pair: _parse_time(pair[0]["timestamp"]) or dt.datetime.min.replace(
        tzinfo=dt.timezone.utc))
    return pairs


def _event_pair(occurrence_id: str, events: list[dict[str, Any]]) -> tuple[dict, dict] | None:
    """Return the sole attempt; multi-attempt proof uses ``_event_pairs`` directly."""
    pairs = _event_pairs(occurrence_id, events)
    return pairs[-1] if pairs else None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def read_run_evidence(start_at: dt.datetime, report_at: dt.datetime,
                      evidence_root: Path | None = None) -> dict[str, Any]:
    """Find the unique pass directory whose filesystem mtime falls inside this exact run."""
    root = evidence_root or EVIDENCE_ROOT
    try:
        candidates = [path for path in root.iterdir()
                      if path.is_dir() and not path.is_symlink()
                      and start_at.timestamp() <= path.stat().st_mtime <= report_at.timestamp()]
    except OSError:
        return {"ok": False, "reason": "evidence_directory_unreadable"}
    if len(candidates) != 1:
        return {"ok": False, "reason": "evidence_missing_or_ambiguous"}
    directory = candidates[0]
    files = {
        "affiliate_job_reconcile": "affiliate-job-reconcile.json",
        "affiliate_success_recovery": "affiliate-success-recovery.json",
        "generic_recovery": "generic-recovery.json",
        "crash_recovery": "postiz-readback-crash-recovery.json",
        "affiliate_job_post": "affiliate-job-post.json",
        "post": "post.json",
    }
    result: dict[str, Any] = {
        "ok": True,
        "pass_id": directory.name,
        "mtime": dt.datetime.fromtimestamp(
            directory.stat().st_mtime, dt.timezone.utc,
        ).isoformat(),
        "path": str(directory),
    }
    try:
        for key, filename in files.items():
            path = directory / filename
            if path.exists():
                parsed = _read_json(path)
                if parsed is None:
                    return {"ok": False, "reason": "evidence_json_malformed"}
                result[key] = parsed
            else:
                result[key] = None
        error_path = directory / "affiliate-job-reconcile.err"
        result["errors"] = error_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {"ok": False, "reason": "evidence_file_unreadable"}
    return result


def _readback_only_evidence(evidence: Mapping[str, Any], start_at: dt.datetime,
                            report_at: dt.datetime) -> bool:
    if evidence.get("ok", True) is not True:
        return False
    mtime = _parse_time(evidence.get("mtime"))
    reconcile = evidence.get("affiliate_job_reconcile")
    provider_id = reconcile.get("provider_submission_id") if isinstance(reconcile, Mapping) else None
    return bool(
        isinstance(evidence.get("pass_id"), str)
        and mtime is not None and start_at <= mtime <= report_at
        and isinstance(reconcile, Mapping)
        and reconcile.get("posted") == "unverified"
        and reconcile.get("mode") == "reconcile"
        and isinstance(provider_id, str) and POSTIZ_ID.fullmatch(provider_id)
        and reconcile.get("reason") == "Postiz effect is not published with an exact X URL"
        and isinstance(evidence.get("affiliate_success_recovery"), Mapping)
        and evidence["affiliate_success_recovery"].get("pending") is False
        and isinstance(evidence.get("generic_recovery"), Mapping)
        and evidence["generic_recovery"].get("pending") is False
        and isinstance(evidence.get("crash_recovery"), Mapping)
        and evidence["crash_recovery"].get("recovered") is False
        and evidence.get("affiliate_job_post") is None
        and evidence.get("post") is None
        and evidence.get("errors") == ""
    )


def _positive_evidence(evidence: Mapping[str, Any], start_at: dt.datetime,
                       report_at: dt.datetime) -> tuple[str, str] | None:
    if evidence.get("ok", True) is not True:
        return None
    mtime = _parse_time(evidence.get("mtime"))
    if (not isinstance(evidence.get("pass_id"), str) or mtime is None
            or not start_at <= mtime <= report_at or evidence.get("errors") != ""):
        return None
    candidates = [evidence.get(name) for name in ("affiliate_job_post", "post")
                  if evidence.get(name) is not None]
    if len(candidates) != 1 or not isinstance(candidates[0], Mapping):
        return None
    row = candidates[0]
    post_id, post_url = row.get("provider_submission_id"), row.get("post_url")
    if (row.get("posted") is not True or row.get("provider") != "postiz"
            or row.get("mode") not in {"quote", "original"}):
        return None
    if not isinstance(post_id, str) or not POSTIZ_ID.fullmatch(post_id):
        return None
    match = X_URL.fullmatch(str(post_url or ""))
    if match is None:
        return None
    return post_id, f"https://x.com/{match.group(1)}/status/{match.group(2)}"


def _listing_posts(listing: Mapping[str, Any]) -> list[dict[str, Any]] | None:
    if not isinstance(listing, Mapping) or listing.get("ok") is not True:
        return None
    posts = listing.get("posts")
    response_count = listing.get("response_count", len(posts) if isinstance(posts, list) else None)
    if (not isinstance(posts, list) or type(response_count) is not int
            or response_count != len(posts) or response_count >= MAX_POSTIZ_ROWS
            or any(not isinstance(row, dict) for row in posts)):
        return None
    if not isinstance(listing.get("response_sha256"), str) or not HASH.fullmatch(
            listing["response_sha256"]):
        return None
    if listing.get("has_more") is True or listing.get("hasMore") is True:
        return None
    for row in posts:
        integration = row.get("integration")
        if (not isinstance(integration, Mapping)
                or not isinstance(integration.get("id"), str)
                or not integration["id"]):
            return None
    return posts


def _post_time(post: Mapping[str, Any]) -> dt.datetime | None:
    for field in ("publishedAt", "published_at", "publishDate", "publish_date", "date"):
        if field in post:
            return _parse_time(post.get(field))
    return None


def _window_token(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _postiz_query_url(start_at: dt.datetime, end_at: dt.datetime) -> str:
    start_at = start_at.astimezone(dt.timezone.utc).replace(microsecond=0)
    end_at = end_at.astimezone(dt.timezone.utc)
    if end_at.microsecond:
        end_at = end_at.replace(microsecond=0) + dt.timedelta(seconds=1)
    query = urllib.parse.urlencode({
        "startDate": start_at.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "endDate": end_at.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "limit": MAX_POSTIZ_ROWS,
    })
    return f"{POSTIZ_POSTS_URL}?{query}"


def build_proof(occurrence_id: str, runtime_events: list[dict[str, Any]],
                evidence: Mapping[str, Any], postiz_listing: Mapping[str, Any], *,
                now: dt.datetime | None = None) -> dict[str, Any]:
    checked_at = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    proof: dict[str, Any] = {
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
        "verified": False,
        "effected": None,
        "checked_at": checked_at.isoformat(),
    }
    pairs = _event_pairs(occurrence_id, runtime_events)
    if not pairs:
        proof["reason"] = "runtime_occurrence_missing_ambiguous_or_unsupported"
        return proof
    if isinstance(evidence, Mapping) and len(pairs) == 1:
        evidence_rows = [evidence]
    elif isinstance(evidence, list) and len(evidence) == len(pairs) \
            and all(isinstance(row, Mapping) for row in evidence):
        evidence_rows = evidence
    else:
        proof["reason"] = "run_evidence_missing_or_ambiguous"
        return proof
    attempts: list[dict[str, Any]] = []
    for (start, report), run_evidence in zip(pairs, evidence_rows):
        start_at = _parse_time(start["timestamp"])
        report_at = _parse_time(report["timestamp"])
        assert start_at is not None and report_at is not None
        attempt_end = report_at + dt.timedelta(seconds=FINALITY_SECONDS)
        evidence_mtime = _parse_time(run_evidence.get("mtime"))
        if (run_evidence.get("ok", True) is not True or evidence_mtime is None
                or not start_at <= evidence_mtime <= report_at):
            proof["reason"] = "run_evidence_missing_or_ambiguous"
            return proof
        attempts.append({
            "start": start, "report": report, "evidence": run_evidence,
            "start_at": start_at, "report_at": report_at, "end_at": attempt_end,
        })
    start_at = min(attempt["start_at"] for attempt in attempts)
    end_at = max(attempt["end_at"] for attempt in attempts)
    latest = attempts[-1]
    proof.update({
        "window_start": start_at.isoformat(),
        "window_end": end_at.isoformat(),
        "finality_at": end_at.isoformat(),
        "release_sha": latest["report"]["release_sha"],
        "attempt_windows": [{
            "run_id": attempt["report"]["run_id"],
            "start": attempt["start_at"].isoformat(),
            "end": attempt["end_at"].isoformat(),
            "release_sha": attempt["report"]["release_sha"],
        } for attempt in attempts],
    })
    if checked_at < end_at:
        proof["reason"] = "provider_window_not_final"
        return proof
    if not isinstance(postiz_listing, Mapping):
        proof["reason"] = "postiz_listing_incomplete_or_invalid"
        return proof
    posts = _listing_posts(postiz_listing)
    if posts is None:
        proof["reason"] = "postiz_listing_incomplete_or_invalid"
        return proof
    query_url = _postiz_query_url(start_at, end_at)
    proof["official_query"] = query_url
    proof["postiz_integration_id"] = POSTIZ_INTEGRATION_ID
    target_posts = []
    for post in posts:
        if post["integration"]["id"] != POSTIZ_INTEGRATION_ID:
            continue
        published_at = _post_time(post)
        if published_at is None:
            proof["reason"] = "postiz_target_post_outside_or_missing_exact_window"
            return proof
        matching = [attempt for attempt in attempts
                    if attempt["start_at"] <= published_at <= attempt["end_at"]]
        if matching:
            if len(matching) != 1:
                proof["reason"] = "postiz_target_post_matches_multiple_attempt_windows"
                return proof
            target_posts.append((post, matching[0]))
    if not target_posts:
        if any(attempt["report"]["release_sha"] not in READBACK_ONLY_RELEASES
               or not _readback_only_evidence(
                   attempt["evidence"], attempt["start_at"], attempt["report_at"],
               ) for attempt in attempts):
            proof["reason"] = "empty_listing_without_exact_readback_only_evidence"
            return proof
        response_hash = postiz_listing["response_sha256"]
        query_hash = hashlib.sha256(query_url.encode("utf-8")).hexdigest()
        proof.update(
            verified=True,
            effected=False,
            proof_kind="postiz_exact_window_complete_empty_readback_only",
            response_sha256=response_hash,
            query_sha256=query_hash,
            provider_receipt_id=(
                f"postiz-empty-window:{POSTIZ_INTEGRATION_ID}:"
                f"{_window_token(start_at)}-{_window_token(end_at)}:"
                f"query-sha256:{query_hash}:response-sha256:{response_hash}"
            ),
        )
        return proof
    if len(target_posts) != 1:
        proof["reason"] = "postiz_target_integration_has_multiple_window_rows"
        return proof
    post, attempt = target_posts[0]
    if post.get("state") != "PUBLISHED":
        proof["reason"] = "postiz_target_effect_not_final_published"
        return proof
    published_id, evidence_url = _positive_evidence(
        attempt["evidence"], attempt["start_at"], attempt["report_at"],
    ) or (None, None)
    release_url = post.get("releaseURL")
    match = X_URL.fullmatch(str(release_url or ""))
    canonical_release_url = (
        f"https://x.com/{match.group(1)}/status/{match.group(2)}" if match else None
    )
    if (published_id != post.get("id") or not isinstance(published_id, str)
            or canonical_release_url is None or evidence_url != canonical_release_url):
        proof["reason"] = "postiz_published_receipt_not_bound_to_exact_run_evidence"
        return proof
    proof.update(
        verified=True,
        effected=True,
        proof_kind="postiz_exact_window_unique_published_receipt",
        provider_receipt_id=f"postiz:{published_id}",
        post_url=f"https://x.com/{match.group(1)}/status/{match.group(2)}",
        response_sha256=postiz_listing["response_sha256"],
    )
    return proof


def _postiz_key(credentials_path: Path | None = None) -> str:
    if "POSTIZ_API_KEY" in os.environ:
        return os.environ["POSTIZ_API_KEY"].strip()
    path = credentials_path or Path.home() / ".local/share/anicca/credentials.json"
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory_flag is None:
        return ""
    directory_fd = None
    file_fd = None
    try:
        directory_fd = os.open(path.parent, os.O_RDONLY | directory_flag | nofollow)
        directory_stat = os.fstat(directory_fd)
        if (not stat.S_ISDIR(directory_stat.st_mode)
                or directory_stat.st_uid != os.getuid()
                or stat.S_IMODE(directory_stat.st_mode) != 0o700):
            return ""
        file_fd = os.open(path.name, os.O_RDONLY | nofollow, dir_fd=directory_fd)
        file_stat = os.fstat(file_fd)
        if (not stat.S_ISREG(file_stat.st_mode) or file_stat.st_uid != os.getuid()
                or stat.S_IMODE(file_stat.st_mode) != 0o600):
            return ""
        with os.fdopen(file_fd, "r", encoding="utf-8") as credentials_file:
            file_fd = None
            value = json.load(credentials_file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, NotImplementedError):
        return ""
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)
    rows = value.get("credentials") if isinstance(value, dict) else None
    if not isinstance(rows, list):
        return ""
    matches = [row for row in rows if isinstance(row, dict)
               and row.get("service") == "postiz"]
    if len(matches) != 1:
        return ""
    api_key = matches[0].get("api_key")
    return api_key.strip() if isinstance(api_key, str) else ""


def _postiz_has_more(payload: Mapping[str, Any], post_count: int) -> bool:
    """Treat malformed, contradictory, or explicitly paged metadata as incomplete."""
    if post_count >= MAX_POSTIZ_ROWS:
        return True
    sources: list[Mapping[str, Any]] = [payload]
    for key in ("pagination", "meta"):
        if key in payload:
            value = payload[key]
            if not isinstance(value, Mapping):
                return True
            sources.append(value)

    flags: list[bool] = []
    more_signals: list[bool] = []
    totals: list[int] = []
    for source in sources:
        for key in ("hasMore", "has_more", "hasNextPage"):
            if key in source:
                value = source[key]
                if type(value) is not bool:
                    return True
                flags.append(value)
        if "total" in source:
            total = source["total"]
            if type(total) is not int or total < post_count:
                return True
            totals.append(total)
            more_signals.append(total > post_count)
        for key in ("next", "nextCursor", "next_cursor"):
            if key in source:
                value = source[key]
                if value is not None and not isinstance(value, str):
                    return True
                more_signals.append(bool(value))
        for key in ("nextPage", "next_page"):
            if key in source:
                value = source[key]
                if value is None:
                    more_signals.append(False)
                elif type(value) is int and value > 0:
                    more_signals.append(True)
                else:
                    return True

        page_keys = [key for key in ("page", "currentPage") if key in source]
        page_count_keys = [key for key in ("totalPages", "total_pages") if key in source]
        if page_keys or page_count_keys:
            pages = [source[key] for key in page_keys]
            page_counts = [source[key] for key in page_count_keys]
            if (not pages or not page_counts
                    or any(type(value) is not int or value < 1 for value in pages + page_counts)
                    or len(set(pages)) != 1 or len(set(page_counts)) != 1
                    or pages[0] != 1 or pages[0] > page_counts[0]):
                return True
            more_signals.append(pages[0] < page_counts[0])

    if len(set(flags)) > 1 or len(set(totals)) > 1:
        return True
    has_more = any(more_signals)
    if flags and more_signals and flags[0] != has_more:
        return True
    return flags[0] if flags else has_more


def read_postiz_listing(start_at: dt.datetime, end_at: dt.datetime, *,
                        api_key: str | None = None) -> dict[str, Any]:
    key = api_key or _postiz_key()
    if not key:
        return {"ok": False, "reason": "postiz_key_missing"}
    request = urllib.request.Request(
        _postiz_query_url(start_at, end_at),
        headers={"Authorization": key, "User-Agent": "life-manager-x-repost-reconcile/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(MAX_POSTIZ_BYTES + 1)
        if len(raw) > MAX_POSTIZ_BYTES:
            return {"ok": False, "reason": "postiz_response_too_large"}
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError,
            UnicodeDecodeError, json.JSONDecodeError):
        return {"ok": False, "reason": "postiz_official_readback_failed"}
    metadata: Mapping[str, Any] = payload if isinstance(payload, dict) else {}
    if isinstance(payload, list):
        posts = payload
    elif isinstance(payload, dict) and isinstance(payload.get("posts"), list):
        posts = payload["posts"]
    else:
        return {"ok": False, "reason": "postiz_response_shape_invalid"}
    if any(not isinstance(row, dict) for row in posts):
        return {"ok": False, "reason": "postiz_response_shape_invalid"}
    return {
        "ok": True,
        "posts": posts,
        "response_count": len(posts),
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "has_more": _postiz_has_more(metadata, len(posts)),
    }


def fenced_row(owner_id: str, occurrence_id: str) -> tuple[str, float]:
    from runtime.host import resource_admission

    database = resource_admission.state_root() / "admission-v2.sqlite3"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        row = connection.execute(
            """SELECT state,queued_at FROM occurrences
                 WHERE owner_id=? AND occurrence_id=? AND effect_unknown=1""",
            (owner_id, occurrence_id),
        ).fetchone()
    if row is None or row[1] is None:
        raise ValueError("occurrence is not an effect_unknown row")
    return str(row[0]), float(row[1])


def reconcile(occurrence_id: str, *, resolve: bool = False,
              now: dt.datetime | None = None,
              events_fn: Callable[[str], list[dict[str, Any]] | None] | None = None,
              evidence_fn: Callable[[dt.datetime, dt.datetime], Mapping[str, Any]] | None = None,
              postiz_fn: Callable[[dt.datetime, dt.datetime], Mapping[str, Any]] | None = None,
              fenced_row_fn: Callable[[str, str], tuple[str, float]] = fenced_row,
              resolve_fn: Callable[..., bool] | None = None) -> dict[str, Any]:
    run_id = _occurrence_run(occurrence_id)
    if run_id is None:
        raise ValueError("invalid x-repost occurrence")
    events = (events_fn or (lambda _occurrence: read_runtime_events()))(occurrence_id)
    if events is None:
        proof = {"owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                 "verified": False, "reason": "runtime_events_unreadable"}
        return proof
    pairs = _event_pairs(occurrence_id, events)
    if not pairs:
        proof = build_proof(occurrence_id, events, {}, {"ok": False}, now=now)
        return proof
    attempt_times = [
        (_parse_time(start["timestamp"]), _parse_time(report["timestamp"]))
        for start, report in pairs
    ]
    assert all(start is not None and report is not None for start, report in attempt_times)
    start_at = min(start for start, _report in attempt_times if start is not None)
    end_at = max(report + dt.timedelta(seconds=FINALITY_SECONDS)
                 for _start, report in attempt_times if report is not None)
    checked_at = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    if checked_at < end_at:
        return build_proof(occurrence_id, events, {}, {"ok": False}, now=checked_at)
    state, queued_at = fenced_row_fn(OWNER_ID, occurrence_id)
    # A queued owner may start after its original queue time when shared capacity opens later.
    # The exact occurrence/run event pair anchors identity; a queue time after start stays fenced.
    if (state not in {"claimed", "released"}
            or float(queued_at) > start_at.timestamp() + FENCE_START_TOLERANCE_SECONDS):
        proof = build_proof(occurrence_id, events, {}, {"ok": False}, now=checked_at)
        proof["reason"] = "fenced_occurrence_does_not_match_runtime_start"
        return proof
    evidence_rows = [
        (evidence_fn or read_run_evidence)(
            _parse_time(start["timestamp"]), _parse_time(report["timestamp"]),
        )
        for start, report in pairs
    ]
    listing = (postiz_fn or read_postiz_listing)(start_at, end_at)
    proof = build_proof(occurrence_id, events, evidence_rows, listing, now=now)
    proof["admission_state"] = state
    proof["admission_queued_at"] = dt.datetime.fromtimestamp(
        float(queued_at), dt.timezone.utc,
    ).isoformat()
    if proof.get("verified") is not True or not resolve:
        return proof
    if resolve_fn is None:
        from runtime.host.resource_admission import resolve_unknown_occurrence
        resolve_fn = resolve_unknown_occurrence
    proof["closed"] = resolve_fn(
        OWNER_ID,
        occurrence_id,
        official_readback=lambda: proof,
        expected_state=state,
    )
    return proof


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = reconcile(args.occurrence, resolve=args.resolve)
    except (OSError, ValueError, sqlite3.Error) as exc:
        result = {"owner_id": OWNER_ID, "occurrence_id": args.occurrence,
                  "verified": False, "error": type(exc).__name__}
    print(json.dumps(result, sort_keys=True, default=str))
    if result.get("verified") is not True:
        print("X_REPOST_EFFECT_RECONCILE=HELD", file=sys.stderr)
        return 1
    if not args.resolve:
        print("X_REPOST_EFFECT_RECONCILE=PROOF_READY")
        return 0
    if result.get("closed") is not True:
        print("X_REPOST_EFFECT_RECONCILE=FAIL reason=admission_refused_close", file=sys.stderr)
        return 1
    print("X_REPOST_EFFECT_RECONCILE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
