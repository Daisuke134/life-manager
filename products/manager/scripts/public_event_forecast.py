#!/usr/bin/env python3
"""Bounded local lock and provenance checks for one scheduled FOMC endpoint."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import stat
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


CASE_ID = "fomc-2026-10-27-28"
TARGET_ID = "fomc-2026-10-27-28.upper-below-4pct.v1"
PROTOCOL_ID = "manager-public-event-forecast.fomc-upper-below-4pct.v1"
CUTOFF = "2026-10-26T23:59:59Z"
DEADLINE = "2026-11-06T23:59:59Z"
CANONICALIZATION = "manager.json-c14n.v1"
REPO = "Daisuke134/life-manager"
GITHUB_API = "https://api.github.com"
MAX_GITHUB_BYTES = 1_000_000

# Pin metadata copied from the private retrieval receipt; bytes are verified before HTML parsing.
PINNED_SOURCES = {
    "fomc-calendar": {
        "file": "fomc-calendar.html", "role": "official-calendar",
        "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        "bytes": 164813, "sha256": "219ad6b5822d73cb5e8efa7fab354e02c42b4846d1427283780a8f470afb5085",
    },
    "fomc-20260617": {
        "file": "fomc-20260617.html", "role": "historical-statement",
        "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617a.htm",
        "bytes": 80145, "sha256": "d153d08450c5dc41d9a4ce50c582b529d09bf2324279e96bb6731edd60da6469",
    },
    "fomc-20260729": {
        "file": "fomc-20260729.html", "role": "historical-statement",
        "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260729a.htm",
        "bytes": 80275, "sha256": "a71e50cbc7ea943ba5409b35dc433d95cc36acadd84c4b074f84870d92f5c7bd",
    },
    "fomc-20260916": {
        "file": "fomc-20260916.html", "role": "historical-statement",
        "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm",
        "bytes": 81698, "sha256": "29f79c969231c1e90dfd7befc26ce8d349b5c6dba6502e4a4d8ddf665283ed84",
    },
}
PINNED_SOURCE_HASHES = {name: row["sha256"] for name, row in PINNED_SOURCES.items()}
PINNED_HISTORY_HASHES = {name: PINNED_SOURCE_HASHES[name] for name in (
    "fomc-20260617", "fomc-20260729", "fomc-20260916")}
HISTORY_EXPECTED = {
    "fomc-20260617": ("June 17, 2026", "2026-06-17T18:00:00Z"),
    "fomc-20260729": ("July 29, 2026", "2026-07-29T18:00:00Z"),
    "fomc-20260916": ("September 16, 2026", "2026-09-16T18:00:00Z"),
}
PINNED_CONTEXT_SOURCES = [
    {"name": "fomc-calendar", "role": "official-calendar", "url": PINNED_SOURCES["fomc-calendar"]["url"], "final_url": PINNED_SOURCES["fomc-calendar"]["url"], "bytes": 164813, "sha256": PINNED_SOURCE_HASHES["fomc-calendar"], "observed_at": "2026-10-23T00:45:33.974305Z", "last_modified": "2026-10-07T18:00:37Z"},
    {"name": "fomc-20260617", "role": "historical-statement", "url": PINNED_SOURCES["fomc-20260617"]["url"], "final_url": PINNED_SOURCES["fomc-20260617"]["url"], "bytes": 80145, "sha256": PINNED_SOURCE_HASHES["fomc-20260617"], "observed_at": "2026-10-23T00:46:22.570470Z", "published_at": "2026-06-17T18:00:00Z"},
    {"name": "fomc-20260729", "role": "historical-statement", "url": PINNED_SOURCES["fomc-20260729"]["url"], "final_url": PINNED_SOURCES["fomc-20260729"]["url"], "bytes": 80275, "sha256": PINNED_SOURCE_HASHES["fomc-20260729"], "observed_at": "2026-10-23T00:46:22.341844Z", "published_at": "2026-07-29T18:00:00Z"},
    {"name": "fomc-20260916", "role": "historical-statement", "url": PINNED_SOURCES["fomc-20260916"]["url"], "final_url": PINNED_SOURCES["fomc-20260916"]["url"], "bytes": 81698, "sha256": PINNED_SOURCE_HASHES["fomc-20260916"], "observed_at": "2026-10-23T00:46:22.112964Z", "published_at": "2026-09-16T18:00:00Z"},
]


class ForecastError(Exception):
    """Stable public error; details never include source/private paths."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _fail(code: str) -> None:
    raise ForecastError(code)


def fixed_contract() -> dict[str, Any]:
    return {
        "case_id": CASE_ID,
        "target_id": TARGET_ID,
        "protocol_id": PROTOCOL_ID,
        "event_kind": "public-institution-statement",
        "event_schedule": {"date_start": "2026-10-27", "date_end": "2026-10-28", "timezone": "America/New_York", "precision": "date"},
        "cutoff": CUTOFF,
        "resolution_deadline": DEADLINE,
        "question": "Will the official statement for the scheduled 2026-10-27–28 FOMC meeting state a federal funds target range with an upper bound below 4.00 percent?",
        "outcome_rule": {"source_role": "same-meeting-official-policy-statement", "operator": "<", "threshold": "4.00", "unit": "percent", "missing_policy": "unavailable-is-not-zero", "reschedule_policy": "retain-original-case-status"},
        "scoring": {"primary": "binary-brier", "lower_is_better": True, "scheduled_targets": 1, "calibration_claim": False},
    }


def _reject_constant(value: str) -> None:
    _fail("NONFINITE_JSON_NUMBER")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def strict_json_loads(raw: bytes | str) -> Any:
    try:
        return json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    except ForecastError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        _fail("INVALID_JSON")


def _assert_finite_tree(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        _fail("NONFINITE_JSON_NUMBER")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                _fail("INVALID_JSON_KEY")
            _assert_finite_tree(child)
    elif isinstance(value, list):
        for child in value:
            _assert_finite_tree(child)
    elif value is None or isinstance(value, (str, int, bool, float)):
        return
    else:
        _fail("INVALID_JSON_VALUE")


def canonical_bytes(value: Any) -> bytes:
    _assert_finite_tree(value)
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        _fail("INVALID_CANONICAL_JSON")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def context_digest(source_hashes: dict[str, str]) -> str:
    return canonical_digest({"canonicalization": CANONICALIZATION, "source_hashes": source_hashes, "sources": PINNED_CONTEXT_SOURCES})

def protocol_digest() -> str:
    return canonical_digest(fixed_contract())

def baseline_digest(baselines: dict[str, Any]) -> str:
    without_digest = {key: value for key, value in baselines.items() if key != "baseline_digest"}
    return canonical_digest(without_digest)


def _parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail("TIME_NOT_UTC")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail("INVALID_TIME")
    if result.tzinfo is None or result.utcoffset() != timezone.utc.utcoffset(result):
        _fail("TIME_NOT_UTC")
    return result


def validate_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        _fail("INVALID_PAYLOAD")
    required = {"schema", "case_id", "target_id", "protocol_id", "protocol_sha256", "event_kind", "event_schedule", "cutoff", "resolution_deadline", "question", "outcome_rule", "context_manifest", "predictor", "prediction", "baselines", "scoring", "integrity"}
    if set(payload) != required:
        _fail("PAYLOAD_FIELDS_MISMATCH")
    contract = fixed_contract()
    for field in ("schema", "case_id", "target_id", "protocol_id", "event_kind", "event_schedule", "cutoff", "resolution_deadline", "question", "outcome_rule", "scoring"):
        expected = "manager.public-event-forecast.v1" if field == "schema" else contract[field]
        if payload.get(field) != expected:
            _fail("FIXED_CONTRACT_MISMATCH")
    if _parse_time(payload["cutoff"]) != _parse_time(CUTOFF) or _parse_time(payload["resolution_deadline"]) != _parse_time(DEADLINE):
        _fail("FIXED_CONTRACT_MISMATCH")
    if payload.get("protocol_sha256") != protocol_digest():
        _fail("PROTOCOL_HASH_MISMATCH")
    integrity = payload.get("integrity")
    if integrity != {"canonicalization": CANONICALIZATION}:
        _fail("CANONICALIZATION_MISMATCH")
    context = payload.get("context_manifest")
    if not isinstance(context, dict) or set(context) != {"source_hashes", "context_digest", "sources"} or context.get("source_hashes") != PINNED_SOURCE_HASHES or context.get("sources") != PINNED_CONTEXT_SOURCES:
        _fail("CONTEXT_HASH_MISMATCH")
    if context.get("context_digest") != context_digest(PINNED_SOURCE_HASHES):
        _fail("CONTEXT_HASH_MISMATCH")
    cutoff = _parse_time(CUTOFF)
    for source in context["sources"]:
        observed = _parse_time(source["observed_at"])
        if observed > cutoff or ("published_at" in source and _parse_time(source["published_at"]) > observed):
            _fail("CONTEXT_AFTER_CUTOFF")
    predictor = payload.get("predictor")
    if not isinstance(predictor, dict) or set(predictor) != {"kind", "id", "procedure_sha256"} or predictor.get("kind") not in {"manual", "reference"}:
        _fail("INVALID_PREDICTOR")
    if not isinstance(predictor.get("id"), str) or not predictor["id"] or not re.fullmatch(r"[0-9a-f]{64}", str(predictor.get("procedure_sha256", ""))):
        _fail("INVALID_PREDICTOR")
    prediction = payload.get("prediction")
    if not isinstance(prediction, dict) or set(prediction) != {"p", "unit", "target_id"} or prediction.get("target_id") != TARGET_ID or prediction.get("unit") != "probability-0-to-1":
        _fail("PREDICTION_UNIT_OR_TARGET_MISMATCH")
    p = prediction.get("p")
    if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or p < 0 or p > 1:
        _fail("INVALID_PROBABILITY")
    baselines = payload.get("baselines")
    if not isinstance(baselines, dict) or set(baselines) != {"persistence", "historical_frequency", "history_source_hashes", "baseline_digest"} or baselines.get("history_source_hashes") != PINNED_HISTORY_HASHES:
        _fail("BASELINE_HASH_MISMATCH")
    persistence = baselines.get("persistence")
    historical = baselines.get("historical_frequency")
    if not isinstance(persistence, dict) or persistence.get("p") != 0.0 or persistence.get("rule") != "latest upper unchanged at 4.00 percent":
        _fail("INVALID_BASELINE")
    if not isinstance(historical, dict) or set(historical) != {"p", "rule"} or historical.get("p") != 0.25 or historical.get("rule") != "(cuts+1)/(transitions+2); 1 cut / 3 values":
        _fail("INVALID_BASELINE")
    if baselines.get("baseline_digest") != baseline_digest(baselines):
        _fail("BASELINE_HASH_MISMATCH")


def _safe_new_store(path: Path) -> None:
    if not isinstance(path, Path):
        path = Path(path)
    if path.name in {"", ".", ".."} or ".." in path.parts:
        _fail("UNSAFE_STORE_PATH")
    absolute = path.absolute()
    for part in (absolute, *absolute.parents):
        if part.exists() and part.is_symlink():
            _fail("UNSAFE_STORE_PATH")
    if absolute.exists():
        _fail("STORE_ALREADY_EXISTS")
    parent = absolute.parent
    if not parent.is_dir():
        _fail("STORE_PARENT_MISSING")
    try:
        os.mkdir(absolute, 0o700)
    except OSError:
        _fail("STORE_CREATE_FAILED")
    os.chmod(absolute, 0o700)


def freeze_forecast(payload: dict[str, Any], store: Path | str) -> str:
    validate_payload(payload)
    raw = canonical_bytes(payload)
    digest = hashlib.sha256(raw).hexdigest()
    path = Path(store)
    _safe_new_store(path)
    target = path / f"{digest}.json"
    fd = -1
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb", closefd=True) as stream:
            fd = -1
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        dir_fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        if fd >= 0:
            os.close(fd)
        _fail("STORE_WRITE_FAILED")
    return digest


def read_forecast(store: Path | str, digest: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
        _fail("INVALID_DIGEST")
    path = Path(store)
    target = path / f"{digest}.json"
    try:
        if target.is_symlink() or not stat.S_ISREG(target.lstat().st_mode):
            _fail("UNSAFE_RECORD_PATH")
        raw = target.read_bytes()
    except ForecastError:
        raise
    except OSError:
        _fail("RECORD_READ_FAILED")
    if hashlib.sha256(raw).hexdigest() != digest:
        _fail("RECORD_DIGEST_MISMATCH")
    record = strict_json_loads(raw)
    if canonical_bytes(record) != raw:
        _fail("NONCANONICAL_RECORD")
    validate_payload(record)
    return record


class _AllText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


class _VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []
        self.current: list[str] = []
        self.current_class = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "p":
            self.current = []
            self.current_class = attrs_dict.get("class", "") or ""

    def handle_data(self, data: str) -> None:
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self.current is not None:
            text = " ".join(" ".join(self.current).split())
            if text:
                self.blocks.append((self.current_class, text))
            self.current = []
            self.current_class = ""
        if tag in {"ul", "div", "section", "article"} and self.current:
            text = " ".join(" ".join(self.current).split())
            if text:
                self.blocks.append((self.current_class, text))
            self.current = []
            self.current_class = ""


def _verify_pinned_bytes(source_dir: Path) -> dict[str, bytes]:
    data = {}
    try:
        for name, row in PINNED_SOURCES.items():
            path = source_dir / row["file"]
            if path.is_symlink() or not path.is_file():
                _fail("SOURCE_FILE_INVALID")
            data[name] = path.read_bytes()
    except ForecastError:
        raise
    except OSError:
        _fail("SOURCE_READ_ERROR")
    for name, row in PINNED_SOURCES.items():
        raw = data[name]
        if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
            _fail("SOURCE_HASH_MISMATCH")
    return data


def _text_blocks(raw: bytes) -> list[tuple[str, str]]:
    parser = _VisibleHTML()
    try:
        parser.feed(raw.decode("utf-8"))
        parser.close()
    except (UnicodeDecodeError, ValueError):
        _fail("SOURCE_PARSE_FAILED")
    return parser.blocks


_RATE_TOKEN = r"[0-9]+(?:-[0-9]+/[0-9]+|\s+[0-9]+/[0-9]+)?|[0-9]+\.[0-9]+"
_RANGE_RE = re.compile(r"target range for the federal funds rate[^.]*?\b(?:at|to)\s+(" + _RATE_TOKEN + r")\s+to\s+(" + _RATE_TOKEN + r")\s+percent", re.I)

def _decimal_rate(value: str) -> str:
    from fractions import Fraction
    pieces = value.split()
    try:
        if len(pieces) == 1 and "-" in pieces[0] and "/" in pieces[0]:
            whole, fraction = pieces[0].split("-", 1)
            number = Fraction(whole) + Fraction(fraction)
        elif len(pieces) == 1:
            number = Fraction(pieces[0])
        elif len(pieces) == 2:
            number = Fraction(pieces[0]) + Fraction(pieces[1])
        else:
            _fail("OUTCOME_PARSE_AMBIGUOUS")
    except (ValueError, ZeroDivisionError):
        _fail("OUTCOME_PARSE_AMBIGUOUS")
    return f"{float(number):.2f}"


def _all_text(raw: bytes) -> str:
    parser = _AllText()
    try:
        parser.feed(raw.decode("utf-8"))
        parser.close()
    except (UnicodeDecodeError, ValueError):
        _fail("SOURCE_PARSE_FAILED")
    return " ".join(" ".join(parser.parts).split())


def _statement_publication(raw: bytes, expected_date: str) -> str:
    text = _all_text(raw)
    if expected_date not in text:
        _fail("HISTORY_DATE_MISMATCH")
    if not re.search(re.escape(expected_date) + r" Federal Reserve issues FOMC statement For release at 2:00 p\.m\. EDT", text):
        _fail("HISTORY_PUBLICATION_TIME_MISMATCH")
    return "confirmed"


def _statement_upper(raw: bytes) -> str:
    blocks = _text_blocks(raw)
    candidates = []
    for _cls, text in blocks:
        if "target range for the federal funds rate" not in text.lower():
            continue
        matches = list(_RANGE_RE.finditer(text))
        if matches:
            candidates.extend(matches)
    if len(candidates) != 1:
        _fail("OUTCOME_PARSE_AMBIGUOUS")
    return _decimal_rate(candidates[0].group(2))


def preflight_official_context(source_dir: Path | str) -> dict[str, Any]:
    files = _verify_pinned_bytes(Path(source_dir))  # all four hashes are checked before any parse
    calendar_parser = _AllText()
    calendar_parser.feed(files["fomc-calendar"].decode("utf-8"))
    calendar = " ".join(" ".join(calendar_parser.parts).split()).lower()
    year_section = re.search(r"2026\s+fomc meetings(.*?)2025\s+fomc meetings", calendar, re.S)
    if year_section is None or not re.search(r"october\s+27\s*[-–]\s*28", year_section.group(1)):
        _fail("CALENDAR_CASE_MISMATCH")
    uppers = []
    for name in PINNED_HISTORY_HASHES:
        expected_date, _published_at = HISTORY_EXPECTED[name]
        _statement_publication(files[name], expected_date)
        uppers.append(_statement_upper(files[name]))
    if uppers != ["3.75", "3.75", "4.00"]:
        _fail("HISTORY_BASELINE_MISMATCH")
    return {
        "status": "CONTEXT_VALIDATED_NO_FORECAST", "case_id": CASE_ID,
        "meeting": "2026-10-27/2026-10-28", "official_calendar_sha256": PINNED_SOURCE_HASHES["fomc-calendar"],
        "historical_dates_and_release_times": {name: {"date": HISTORY_EXPECTED[name][0], "published_at": HISTORY_EXPECTED[name][1]} for name in PINNED_HISTORY_HASHES},
        "historical_upper_percent": uppers,
        "baseline_probabilities": {"persistence": 0.0, "historical_frequency": 0.25},
        "source_hashes": PINNED_SOURCE_HASHES,
        "context_digest": context_digest(PINNED_SOURCE_HASHES),
        "forecast_frozen": False, "attestation_status": "LOCAL_RECORD_ONLY",
    }


def attestation_assessment(receipt: Any) -> dict[str, str]:
    # Locally supplied receipts never establish provider provenance.
    return {"status": "LOCAL_RECORD_ONLY", "reason": "NO_LIVE_OFFICIAL_GITHUB_READBACK"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _fail("GITHUB_REDIRECT_REJECTED")


def _github_get(path: str) -> tuple[dict[str, Any], datetime]:
    if not path.startswith("/repos/" + REPO + "/") or ".." in path or path.startswith("//"):
        _fail("GITHUB_PATH_REJECTED")
    request = urllib.request.Request(GITHUB_API + path, headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "manager-public-event-forecast-readonly"})
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=8) as response:
            if response.geturl().split("/", 3)[:3] != ["https:", "", "api.github.com"]:
                _fail("GITHUB_HOST_REJECTED")
            raw = response.read(MAX_GITHUB_BYTES + 1)
            observed = datetime.now(timezone.utc)
    except ForecastError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError):
        _fail("GITHUB_READ_UNAVAILABLE")
    if len(raw) > MAX_GITHUB_BYTES:
        _fail("GITHUB_RESPONSE_TOO_LARGE")
    parsed = strict_json_loads(raw)
    if not isinstance(parsed, dict):
        _fail("GITHUB_RESPONSE_INVALID")
    return parsed, observed


def verify_github_pr_lock(record: dict[str, Any], repo: str, pr_number: int) -> dict[str, Any]:
    validate_payload(record)
    if repo != REPO or isinstance(pr_number, bool) or not isinstance(pr_number, int) or pr_number < 1:
        _fail("GITHUB_TARGET_REJECTED")
    digest = canonical_digest(record)
    pr, pr_observed = _github_get(f"/repos/{REPO}/pulls/{pr_number}")
    merged_at = pr.get("merged_at")
    merge_sha = pr.get("merge_commit_sha")
    if pr.get("number") != pr_number or pr.get("base", {}).get("repo", {}).get("full_name") != REPO or pr.get("base", {}).get("ref") != "main":
        return {"status": "ATTESTATION_UNAVAILABLE", "reason": "WRONG_PR_BASE"}
    if pr.get("merged") is not True or not isinstance(merged_at, str) or not isinstance(merge_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", merge_sha):
        return {"status": "ATTESTATION_UNAVAILABLE", "reason": "PR_NOT_MERGED"}
    if _parse_time(merged_at.replace("+00:00", "Z")) > _parse_time(CUTOFF):
        return {"status": "ATTESTATION_UNAVAILABLE", "reason": "MERGED_AFTER_CUTOFF"}
    commit, commit_observed = _github_get(f"/repos/{REPO}/commits/{merge_sha}")
    tree_sha = commit.get("commit", {}).get("tree", {}).get("sha")
    if not isinstance(tree_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", tree_sha):
        return {"status": "ATTESTATION_UNAVAILABLE", "reason": "MERGE_TREE_UNAVAILABLE"}
    record_path = f"docs/research/manager/predictions/fomc-2026-10-27-28/{digest}.json"
    encoded, content_observed = _github_get(f"/repos/{REPO}/contents/{record_path}?ref={merge_sha}")
    blob_sha = encoded.get("sha")
    if encoded.get("encoding") != "base64" or not isinstance(encoded.get("content"), str) or not re.fullmatch(r"[0-9a-f]{40}", str(blob_sha)):
        return {"status": "ATTESTATION_UNAVAILABLE", "reason": "MERGE_BLOB_UNAVAILABLE"}
    try:
        blob = base64.b64decode("".join(encoded["content"].split()), validate=True)
    except (ValueError, base64.binascii.Error):
        _fail("GITHUB_BLOB_INVALID")
    git_blob_sha = hashlib.sha1(f"blob {len(blob)}\0".encode("ascii") + blob).hexdigest()
    if git_blob_sha != blob_sha or hashlib.sha256(blob).hexdigest() != digest or blob != canonical_bytes(record):
        return {"status": "ATTESTATION_UNAVAILABLE", "reason": "MERGE_BLOB_MISMATCH"}
    returned = strict_json_loads(blob)
    if canonical_bytes(returned) != blob or canonical_digest(returned) != digest:
        return {"status": "ATTESTATION_UNAVAILABLE", "reason": "MERGE_PAYLOAD_MISMATCH"}
    return {
        "status": "VERIFIED_PROSPECTIVE", "provider": "github-public-readonly",
        "repo": REPO, "pull_request": pr_number, "merged_at": merged_at,
        "merge_commit_sha": merge_sha, "tree_sha": tree_sha, "path": record_path,
        "git_blob_sha": blob_sha, "payload_sha256": digest,
        "context_digest": record["context_manifest"]["context_digest"],
        "baseline_hashes": record["baselines"]["history_source_hashes"],
        "readback_observed_at": max(pr_observed, commit_observed, content_observed).isoformat().replace("+00:00", "Z"),
    }


def resolved_binary_outcome(status: str, outcome: Any) -> int | None:
    if status != "RESOLVED":
        return None
    if isinstance(outcome, bool) or outcome not in (0, 1):
        _fail("INVALID_BINARY_OUTCOME")
    return outcome


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect pinned FOMC context and local forecast-lock status")
    sub = parser.add_subparsers(dest="mode", required=True)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("--source-dir", required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--payload-file", required=True)
    freeze.add_argument("--store", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--store", required=True)
    inspect.add_argument("--digest", required=True)
    attest = sub.add_parser("attest-github")
    attest.add_argument("--store", required=True)
    attest.add_argument("--digest", required=True)
    attest.add_argument("--pr", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == "preflight":
            result = preflight_official_context(Path(args.source_dir))
        elif args.mode == "freeze":
            try:
                payload_raw = Path(args.payload_file).read_bytes()
            except OSError:
                _fail("PAYLOAD_READ_FAILED")
            payload = strict_json_loads(payload_raw)
            digest = freeze_forecast(payload, Path(args.store))
            result = {"status": "LOCAL_RECORD_ONLY", "digest": digest}
        else:
            record = read_forecast(Path(args.store), args.digest)
            if args.mode == "attest-github":
                result = verify_github_pr_lock(record, REPO, args.pr)
            else:
                result = {"status": "LOCAL_RECORD_ONLY", "digest": args.digest, "case_id": record["case_id"]}
        sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
        return 0
    except ForecastError as exc:
        sys.stderr.write(f"forecast-check failed: {exc.code}\n")
        return 2
    except OSError:
        sys.stderr.write("forecast-check failed: IO_ERROR\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
