#!/usr/bin/env python3
"""Reconcile one Affiliate host fence from retained pre-effect evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.host.resource_admission import (  # noqa: E402
    cancel_coalesced_occurrences,
    process_start,
    resolve_pre_effect_occurrence,
    state_root as admission_root,
)
from runtime.loop.runtime_event import validate_runtime_event  # noqa: E402


OWNER_ID = "affiliate-loop"
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
OCCURRENCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
LEGACY_MARKER = {"status": "pre_effect_failure", "effect": 0}
LEGACY_MIGRATION_OCCURRENCE_ID = "affiliate-loop:18d7bd776d9c8a78-1576"
LEGACY_MIGRATION_RUN_ID = "18d7ef3c86d34350-17314"
EXACT_MARKER_FIELDS = {
    "schema_version", "kind", "status", "effect", "owner_id",
    "occurrence_id", "runtime_run_id",
}


def _atomic_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _private_file(path: Path, *, limit: int = 16 * 1024) -> bytes | None:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or info.st_mode & 0o777 != 0o600
                or info.st_size > limit):
            return None
        data = os.read(descriptor, limit + 1)
        return data if len(data) <= limit else None
    except OSError:
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _private_json(path: Path) -> dict | None:
    data = _private_file(path)
    if data is None:
        return None
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _sha256(path: Path) -> str:
    data = _private_file(path)
    return hashlib.sha256(data).hexdigest() if data is not None else ""


def _epoch(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def unknown_effect_occurrences(owner_id: str) -> list[dict]:
    """Read fenced rows without mutating the shared admission database."""
    database = admission_root() / "admission-v2.sqlite3"
    with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True, timeout=1) as connection:
        rows = connection.execute(
            """SELECT occurrence_id,owner_id,queued_at,sequence,state,effect_unknown,
                      (SELECT COUNT(*) FROM occurrences older
                        WHERE older.owner_id=current.owner_id
                          AND older.state IN ('queued','claimed')
                          AND older.effect_unknown=0
                          AND (older.queued_at < current.queued_at OR
                               (older.queued_at=current.queued_at AND
                                older.occurrence_id < current.occurrence_id)))
                 FROM occurrences current
                WHERE owner_id=? AND effect_unknown=1
                ORDER BY queued_at,occurrence_id""",
            (owner_id,),
        ).fetchall()
    return [{
        "occurrence_id": row[0], "owner_id": row[1], "queued_at": row[2],
        "sequence": row[3], "state": row[4], "effect_unknown": row[5],
        "older_open_count": row[6],
    } for row in rows]


def _runtime_rows(loop_state: Path) -> list[dict] | None:
    path = loop_state / "events.jsonl"
    rows: list[dict] = []
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or info.st_mode & 0o777 != 0o600):
            return None
        with os.fdopen(descriptor, encoding="utf-8") as stream:
            descriptor = -1
            for line in stream:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    return None
                if not isinstance(value, dict):
                    return None
                try:
                    rows.append(validate_runtime_event(value))
                except ValueError:
                    return None
                if len(rows) > 20_000:
                    return None
    except (OSError, UnicodeError):
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return rows


def _job_events_in_window(affiliate_state: Path, started: float, stopped: float) -> int:
    path = affiliate_state / "job-events.jsonl"
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
    except OSError:
        return -1
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_nlink != 1 or info.st_mode & 0o777 != 0o600):
        os.close(descriptor)
        return -1
    count = 0
    try:
        with os.fdopen(descriptor, encoding="utf-8") as stream:
            descriptor = -1
            for line in stream:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    return -1
                if not isinstance(row, dict):
                    return -1
                values = []
                for key in (
                    "created_at", "updated_at", "created_at_epoch", "updated_at_epoch",
                    "ts", "at", "effect_started_at", "verified_at",
                ):
                    if key not in row:
                        continue
                    value = _epoch(row[key])
                    if value is None:
                        return -1
                    values.append(value)
                if not values:
                    return -1
                if any(started <= value <= stopped for value in values):
                    count += 1
    except (OSError, UnicodeError):
        return -1
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return count


def _dead_scratch_owner(scratch: Path) -> bool:
    owner = _private_json(scratch / ".owner.json")
    if not owner or not isinstance(owner.get("pid"), int):
        return False
    observed = process_start(owner["pid"])
    return observed is None or observed != owner.get("process_start")


def _candidate(scratch: Path, occurrence_id: str, runtime_rows: list[dict],
               affiliate_state: Path) -> tuple[dict | None, str | None]:
    if (not scratch.is_dir() or scratch.is_symlink()
            or _private_file(scratch / ".terminal-unrecorded") is None
            or not _dead_scratch_owner(scratch)):
        return None, None
    run_id = scratch.name
    if not RUN_ID.fullmatch(run_id):
        return None, None
    admission = _private_json(scratch / "host-admission.json")
    marker_path = scratch / "entrypoint-result.json"
    marker = _private_json(marker_path)
    if admission != {
        "effect": 0, "reason": "resource_slot_acquired",
        "resource_class": "deterministic", "status": "pass",
    } or marker is None or (scratch / "effect-identity.jsonl").exists():
        return None, None
    execute = [row for row in runtime_rows if row.get("run_id") == run_id
               and row.get("phase") == "execute" and row.get("status") == "running"]
    reports = [row for row in runtime_rows if row.get("run_id") == run_id
               and row.get("phase") == "report"]
    if len(execute) != 1 or reports:
        return None, None
    started = _epoch(execute[0].get("timestamp"))
    if started is None:
        return None, None

    exact = (set(marker) == EXACT_MARKER_FIELDS
             and marker.get("schema_version") == 1
             and marker.get("kind") == "life_manager_pre_effect_result"
             and marker.get("status") == "pre_effect_failure"
             and marker.get("effect") == 0
             and marker.get("owner_id") == OWNER_ID
             and marker.get("occurrence_id") == occurrence_id
             and marker.get("runtime_run_id") == run_id)
    if exact:
        return {
            "run_id": run_id, "marker_contract": "exact",
            "execute_event_id": execute[0].get("event_id"),
            "marker_sha256": _sha256(marker_path),
            "host_admission_sha256": _sha256(scratch / "host-admission.json"),
            "new_job_events": 0,
        }, None
    if marker != LEGACY_MARKER:
        return None, None

    if (occurrence_id != LEGACY_MIGRATION_OCCURRENCE_ID
            or run_id != LEGACY_MIGRATION_RUN_ID):
        return None, "legacy_migration_identity_mismatch"

    execute_index = next(
        index for index, row in enumerate(runtime_rows) if row is execute[0]
    )
    next_events = [
        row for row in runtime_rows[execute_index + 1:]
        if row.get("phase") in {"execute", "report"}
    ]
    if len(next_events) < 2:
        return None, "legacy_adjacent_fence_missing"
    next_execute, blocked_report = next_events[:2]
    next_run_id = next_execute.get("run_id")
    next_started = _epoch(next_execute.get("timestamp"))
    stopped = _epoch(blocked_report.get("timestamp"))
    if (next_execute.get("phase") != "execute"
            or next_execute.get("status") != "running"
            or not isinstance(next_run_id, str) or not RUN_ID.fullmatch(next_run_id)
            or next_run_id == run_id
            or blocked_report.get("phase") != "report"
            or blocked_report.get("run_id") != next_run_id
            or blocked_report.get("blocker")
            != "host_admission_deferred:resource_effect_unknown"
            or next_started is None or stopped is None
            or not started < next_started <= stopped):
        return None, "legacy_adjacent_fence_missing"
    marker_mtime = marker_path.stat().st_mtime
    if not started <= marker_mtime <= stopped:
        return None, "legacy_marker_time_mismatch"
    job_count = _job_events_in_window(affiliate_state, started, stopped)
    if job_count != 0:
        return None, "legacy_effect_window_nonempty"
    return {
        "run_id": run_id, "marker_contract": "legacy_unique",
        "execute_event_id": execute[0].get("event_id"),
        "blocked_event_id": blocked_report.get("event_id"),
        "marker_sha256": _sha256(marker_path),
        "host_admission_sha256": _sha256(scratch / "host-admission.json"),
        "new_job_events": job_count,
    }, None


def reconcile_before_effect(
    affiliate_state: Path,
    loop_state: Path,
    *,
    unknown_reader: Callable[[str], list[dict]] = unknown_effect_occurrences,
    resolver: Callable[..., bool] = resolve_pre_effect_occurrence,
    coalescer: Callable[[str, str], int | None] = cancel_coalesced_occurrences,
    current_occurrence_id: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Resolve one exact no-effect fence, or hold before every business effect."""
    try:
        unknown = unknown_reader(OWNER_ID)
    except (OSError, RuntimeError, sqlite3.Error):
        return {"state": "HELD", "reason": "unknown_occurrence_read_failed"}
    if not unknown:
        cancelled = 0
        if current_occurrence_id is not None and not dry_run:
            try:
                result = coalescer(OWNER_ID, current_occurrence_id)
            except (OSError, RuntimeError, sqlite3.Error):
                result = None
            if result is None:
                return {"state": "HELD", "reason": "queued_wake_coalesce_rejected"}
            cancelled = result
        return {
            "state": "CLEAR", "reason": "no_unknown_occurrence",
            "cancelled_occurrences": cancelled,
        }
    if len(unknown) != 1:
        return {
            "state": "HELD", "reason": "unknown_occurrence_count", "count": len(unknown),
        }
    row = unknown[0]
    occurrence_id = row.get("occurrence_id")
    if (row.get("owner_id") != OWNER_ID
            or not isinstance(occurrence_id, str)
            or not occurrence_id.startswith(f"{OWNER_ID}:")
            or not OCCURRENCE_ID.fullmatch(occurrence_id)
            or row.get("state") not in {"claimed", "released"}
            or row.get("effect_unknown") != 1
            or row.get("older_open_count") != 0):
        return {"state": "HELD", "reason": "unknown_occurrence_not_exact"}

    runtime_rows = _runtime_rows(loop_state)
    if runtime_rows is None:
        return {"state": "HELD", "reason": "runtime_event_journal_invalid"}
    scratch_root = loop_state / "loop-tmp" / OWNER_ID
    candidates: list[dict] = []
    legacy_failure = None
    try:
        scratch_dirs = list(scratch_root.iterdir())
    except OSError:
        scratch_dirs = []
    for scratch in scratch_dirs:
        evidence, failure = _candidate(
            scratch, occurrence_id, runtime_rows, affiliate_state,
        )
        if evidence is not None:
            candidates.append(evidence)
        if failure is not None:
            legacy_failure = failure
    exact = [item for item in candidates if item["marker_contract"] == "exact"]
    selected = exact[0] if len(exact) == 1 else None
    if selected is None:
        legacy = [item for item in candidates if item["marker_contract"] == "legacy_unique"]
        selected = legacy[0] if not exact and len(legacy) == 1 else None
    if selected is None:
        return {
            "state": "HELD",
            "reason": legacy_failure or "pre_effect_evidence_not_unique",
        }

    evidence_key = hashlib.sha256(json.dumps({
        "owner_id": OWNER_ID, "occurrence_id": occurrence_id, "evidence": selected,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    evidence_ref = f"affiliate-pre-effect://{evidence_key}"
    if dry_run:
        return {
            "state": "PROOF_READY", "occurrence_id": occurrence_id,
            "evidence_ref": evidence_ref, "evidence": selected,
        }
    receipt = {
        "schema_version": 1,
        "receipt_type": "AFFILIATE_PRE_EFFECT_RECONCILIATION",
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
        "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": evidence_ref,
        "evidence": selected,
        "expected_state": row["state"],
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "resolution_state": "PROOF_READY",
    }
    receipt_path = affiliate_state / "reconciliation" / (
        occurrence_id.replace(":", "-", 1) + ".json"
    )
    _atomic_json(receipt_path, receipt)
    proof = {
        "owner_id": OWNER_ID, "occurrence_id": occurrence_id,
        "verified": True, "proof_type": "pre_effect", "evidence_ref": evidence_ref,
    }
    resolved = resolver(
        OWNER_ID, occurrence_id,
        pre_effect_readback=lambda: proof,
        expected_state=row["state"],
    )
    receipt["resolution_state"] = "RESOLVED" if resolved else "HELD"
    _atomic_json(receipt_path, receipt)
    if not resolved:
        return {
            "state": "HELD", "reason": "exact_resolution_rejected",
            "occurrence_id": occurrence_id, "receipt_path": str(receipt_path),
        }
    cancelled = 0
    if current_occurrence_id is not None:
        try:
            result = coalescer(OWNER_ID, current_occurrence_id)
        except (OSError, RuntimeError, sqlite3.Error):
            result = None
        if result is None:
            return {
                "state": "HELD", "reason": "queued_wake_coalesce_rejected",
                "occurrence_id": occurrence_id, "receipt_path": str(receipt_path),
            }
        cancelled = result
    return {
        "state": "RECONCILED", "occurrence_id": occurrence_id,
        "receipt_path": str(receipt_path), "evidence_ref": evidence_ref,
        "cancelled_occurrences": cancelled,
    }
