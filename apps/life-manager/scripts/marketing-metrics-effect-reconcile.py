#!/usr/bin/env python3
"""Close a metrics-owner fence only when its exact run had no Telegram job."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
from typing import Any, Callable
import zlib

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from runtime.host.resource_admission import resolve_pre_effect_occurrence  # noqa: E402
from runtime.loop.runtime_event import validate_runtime_event  # noqa: E402

OWNER_IDS = frozenset({"life-manager-tiktok-metrics", "life-manager-instagram-metrics"})
OCCURRENCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
RELEASE_SHA = re.compile(r"^[a-f0-9]{40}$")
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_LINE_BYTES = 1024 * 1024
MAX_RUN_SECONDS = 24 * 60 * 60
MAX_EVENT_ARCHIVES = 256
MAX_EVENT_BYTES = 512 * 1024 * 1024
MAX_EVENT_ROWS = 1_000_000


def _instant(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], str] | None:
    try:
        before = path.lstat()
        if (not stat.S_ISREG(before.st_mode) or path.is_symlink()
                or before.st_uid != os.getuid() or before.st_nlink != 1
                or before.st_mode & 0o077 or before.st_size > MAX_FILE_BYTES):
            return None
        digest = hashlib.sha256()
        rows: list[dict[str, Any]] = []
        with path.open("rb") as handle:
            for raw in handle:
                if len(raw) > MAX_LINE_BYTES:
                    return None
                digest.update(raw)
                if not raw.strip():
                    continue
                value = json.loads(raw.decode("utf-8"))
                if not isinstance(value, dict):
                    return None
                rows.append(value)
        after = path.lstat()
        if (before.st_ino != after.st_ino or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns):
            return None
        return rows, digest.hexdigest()
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _read_runtime_events(state_root: Path, owner_id: str,
                         occurrence_id: str) -> tuple[tuple[list[dict[str, Any]], str] | None, str | None]:
    current = state_root / "events.jsonl"
    archives = sorted(state_root.glob("events-*.jsonl.gz"), reverse=True)
    if len(archives) > MAX_EVENT_ARCHIVES:
        return None, "event_archive_history_exceeds_limit"
    paths = [current, *archives]
    matched: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    total_bytes = 0
    rows_seen = 0
    try:
        for path in paths:
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or path.is_symlink()
                    or info.st_uid != os.getuid() or info.st_nlink != 1
                    or stat.S_IMODE(info.st_mode) != 0o600):
                return None, "event_archive_invalid" if path != current else "event_ledger_missing_or_invalid"
            total_bytes += info.st_size
            if total_bytes > MAX_EVENT_BYTES:
                return None, "event_archive_history_exceeds_limit"
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                opened = os.fstat(descriptor)
                if (opened.st_ino != info.st_ino or opened.st_dev != info.st_dev
                        or opened.st_size != info.st_size or opened.st_mtime_ns != info.st_mtime_ns):
                    return None, "event_journal_changed_during_read"
                with os.fdopen(descriptor, "rb") as raw:
                    descriptor = -1
                    stream = gzip.GzipFile(fileobj=raw, mode="rb") if path.suffix == ".gz" else raw
                    try:
                        digest.update(path.name.encode("utf-8") + b"\0")
                        for line in stream:
                            if len(line) > MAX_LINE_BYTES:
                                return None, "event_journal_line_too_large"
                            if not line.strip():
                                continue
                            row = json.loads(line.decode("utf-8"))
                            if not isinstance(row, dict):
                                return None, "event_ledger_row_invalid"
                            validate_runtime_event(row)
                            digest.update(line)
                            rows_seen += 1
                            if rows_seen > MAX_EVENT_ROWS:
                                return None, "event_archive_history_exceeds_limit"
                            if (row.get("owner_id") == owner_id
                                    and row.get("loop_id") == owner_id
                                    and row.get("occurrence_id") == occurrence_id):
                                matched.append(row)
                    finally:
                        if stream is not raw:
                            stream.close()
                after = path.lstat()
                if (after.st_ino != info.st_ino or after.st_dev != info.st_dev
                        or after.st_size != info.st_size or after.st_mtime_ns != info.st_mtime_ns):
                    return None, "event_journal_changed_during_read"
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
        if [p.name for p in sorted(state_root.glob("events-*.jsonl.gz"), reverse=True)] != [
            p.name for p in archives
        ]:
            return None, "event_journal_changed_during_read"
    except (OSError, EOFError, UnicodeError, json.JSONDecodeError, ValueError, zlib.error):
        return None, "event_archive_invalid"
    return (matched, digest.hexdigest()), None


def _run_windows(events: list[dict[str, Any]], owner_id: str,
                 occurrence_id: str) -> tuple[list[dict[str, Any]], str | None]:
    runs: dict[str, list[dict[str, Any]]] = {}
    for row in events:
        if (row.get("owner_id") != owner_id or row.get("loop_id") != owner_id
                or row.get("occurrence_id") != occurrence_id):
            continue
        run_id = row.get("run_id")
        if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
            return [], "run_identity_invalid"
        runs.setdefault(run_id, []).append(row)
    if not runs:
        return [], "run_history_missing"

    windows = []
    for run_id, rows in runs.items():
        starts = [row for row in rows if row.get("phase") == "execute" and row.get("status") == "running"]
        terminals = [row for row in rows if row.get("phase") == "report"
                     and row.get("status") in {"pass", "fail", "blocked"}]
        if len(starts) != 1:
            return [], "run_start_missing_or_ambiguous"
        if len(terminals) != 1:
            return [], "run_terminal_missing" if not terminals else "run_terminal_ambiguous"
        start, terminal = starts[0], terminals[0]
        if start.get("effect_class") == "publish":
            # Legacy releases did not bind the historical data root or fsync
            # the pre-dispatch ledger marker, so an empty current ledger is not proof.
            return [], "legacy_effect_class_unbound"
        start_at, end_at = _instant(start.get("timestamp")), _instant(terminal.get("timestamp"))
        release_sha = start.get("release_sha")
        if (start_at is None or end_at is None or end_at < start_at
                or (end_at - start_at).total_seconds() > MAX_RUN_SECONDS
                or not RELEASE_SHA.fullmatch(str(release_sha or ""))
                or terminal.get("release_sha") != release_sha
                or start.get("effect_class") != "message"
                or terminal.get("effect_class") != start.get("effect_class")
                or terminal.get("effect_status") != "unknown"):
            return [], "run_terminal_not_provable"
        windows.append({"run_id": run_id, "release_sha": release_sha,
                        "started_at": start_at.isoformat(), "ended_at": end_at.isoformat(),
                        "start": start_at, "end": end_at})
    return windows, None


def _in_windows(value: datetime, windows: list[dict[str, Any]]) -> bool:
    return any(window["start"] <= value <= window["end"] for window in windows)


def _load_ledgers(state_root: Path, data_root: Path, owner_id: str,
                  occurrence_id: str):
    event_data, event_error = _read_runtime_events(state_root, owner_id, occurrence_id)
    if event_error:
        return None, event_error
    jobs_data = _read_jsonl(data_root / "marketing/jobs.jsonl")
    receipts_data = _read_jsonl(data_root / "marketing/receipts.jsonl")
    if not jobs_data or not receipts_data:
        return None, "marketing_ledger_missing_or_invalid"
    return (event_data, jobs_data, receipts_data), None


def _analyze_loaded(owner_id: str, occurrence_id: str, ledgers) -> dict[str, Any]:
    if (owner_id not in OWNER_IDS or not OCCURRENCE_ID.fullmatch(occurrence_id)
            or not occurrence_id.startswith(f"{owner_id}:")):
        return {"verified": False, "reason": "identity_not_allowlisted"}
    event_data, jobs_data, receipts_data = ledgers
    windows, reason = _run_windows(event_data[0], owner_id, occurrence_id)
    if reason:
        return {"verified": False, "reason": reason}
    release_shas = {window["release_sha"] for window in windows}
    if len(release_shas) != 1:
        return {"verified": False, "reason": "run_release_mismatch"}

    # Both metrics entrypoints route notifications through this durable job queue;
    # the queue write precedes executeMarketingLivenessJob's Telegram send.
    for row in jobs_data[0]:
        job = row.get("job")
        if not isinstance(job, dict):
            return {"verified": False, "reason": "job_ledger_row_invalid"}
        if (job.get("capability") != "marketing.liveness.telegram"
                and job.get("effect_class") != "message"):
            continue
        raw_timestamps = [job.get(key) for key in ("enqueued_at", "updated_at")]
        present_timestamps = [value for value in raw_timestamps if value is not None]
        if not present_timestamps:
            return {"verified": False, "reason": "telegram_job_timestamp_missing"}
        timestamps = [_instant(value) for value in present_timestamps]
        if any(value is None for value in timestamps):
            return {"verified": False, "reason": "telegram_job_timestamp_invalid"}
        if any(_in_windows(value, windows) for value in timestamps if value is not None):
            return {"verified": False, "reason": "telegram_job_in_run_window"}

    for row in receipts_data[0]:
        receipt = row.get("receipt")
        if not isinstance(receipt, dict):
            return {"verified": False, "reason": "receipt_ledger_row_invalid"}
        if (receipt.get("kind") != "telegram_marketing_liveness"
                and not (receipt.get("chat_id_hash") and receipt.get("message_id"))):
            continue
        sent_at = _instant(receipt.get("sent_at"))
        if sent_at is None:
            return {"verified": False, "reason": "telegram_receipt_timestamp_missing"}
        if _in_windows(sent_at, windows):
            return {"verified": False, "reason": "telegram_receipt_in_run_window"}

    evidence = {
        "owner_id": owner_id,
        "occurrence_id": occurrence_id,
        "release_sha": next(iter(release_shas)),
        "run_windows": [{k: v for k, v in window.items() if k not in {"start", "end"}}
                        for window in windows],
        "events_sha256": event_data[1],
        "jobs_sha256": jobs_data[1],
        "receipts_sha256": receipts_data[1],
        "telegram_job_events_in_window": 0,
        "telegram_receipts_in_window": 0,
    }
    proof_hash = hashlib.sha256(json.dumps(evidence, sort_keys=True,
                                          separators=(",", ":")).encode()).hexdigest()
    return {**evidence, "verified": True, "proof_type": "pre_effect",
            "evidence_ref": f"lm-no-effect://{owner_id}/{occurrence_id}/telegram-job-absent/{proof_hash}"}


def analyze_no_dispatch(owner_id: str, occurrence_id: str, *,
                        state_root: Path, data_root: Path) -> dict[str, Any]:
    if (owner_id not in OWNER_IDS or not OCCURRENCE_ID.fullmatch(occurrence_id)
            or not occurrence_id.startswith(f"{owner_id}:")):
        return {"verified": False, "reason": "identity_not_allowlisted"}
    ledgers, reason = _load_ledgers(state_root, data_root, owner_id, occurrence_id)
    return ({"verified": False, "reason": reason} if reason
            else _analyze_loaded(owner_id, occurrence_id, ledgers))


def _resolve_proof(owner_id: str, occurrence_id: str, proof: dict[str, Any],
                   resolver: Callable[..., bool]) -> dict[str, Any]:
    for expected_state in ("claimed", "released"):
        try:
            resolved = resolver(owner_id, occurrence_id,
                                pre_effect_readback=lambda: proof,
                                expected_state=expected_state)
        except (OSError, RuntimeError, ValueError, sqlite3.Error):
            return {"owner_id": owner_id, "occurrence_id": occurrence_id,
                    **proof, "verified": False, "resolved": False,
                    "reason": "admission_resolution_failed"}
        if resolved:
            return {"owner_id": owner_id, "occurrence_id": occurrence_id,
                    **proof, "resolved": True}
    return {"owner_id": owner_id, "occurrence_id": occurrence_id,
            **proof, "verified": False, "resolved": False,
            "reason": "admission_occurrence_not_active"}


def reconcile(owner_id: str, occurrence_id: str, *, state_root: Path, data_root: Path,
              resolve: bool = False, resolver: Callable[..., bool] | None = None) -> dict[str, Any]:
    proof = analyze_no_dispatch(owner_id, occurrence_id,
                                state_root=state_root, data_root=data_root)
    result = {"owner_id": owner_id, "occurrence_id": occurrence_id,
              **proof, "resolved": False}
    if not proof.get("verified") or not resolve:
        return result
    return _resolve_proof(owner_id, occurrence_id, proof,
                          resolver or resolve_pre_effect_occurrence)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-id", required=True)
    parser.add_argument("--occurrence-id", required=True)
    parser.add_argument("--state-root", type=Path,
                        default=Path.home() / ".local/state/life-manager")
    parser.add_argument("--data-root", type=Path,
                        default=Path(os.environ.get("LM_DATA_DIR", Path.home() / ".local/state/life-manager")))
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    state_root = args.state_root.expanduser().resolve()
    data_root = args.data_root.expanduser().resolve()
    inherited_data_root = os.environ.get("LM_DATA_DIR")
    if inherited_data_root and Path(inherited_data_root).expanduser().resolve() != data_root:
        print(json.dumps({
            "owner_id": args.owner_id,
            "occurrence_id": args.occurrence_id,
            "verified": False,
            "resolved": False,
            "reason": "data_root_environment_mismatch",
        }, ensure_ascii=False, sort_keys=True))
        return 0
    result = reconcile(args.owner_id, args.occurrence_id,
                       state_root=state_root, data_root=data_root,
                       resolve=args.resolve)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
