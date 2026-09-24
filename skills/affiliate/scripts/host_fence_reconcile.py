#!/usr/bin/env python3
"""Resolve one Affiliate host fence only from an exact FIFO pre-effect window."""

from __future__ import annotations

import argparse
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
    resolve_pre_effect_occurrence,
    state_root as admission_root,
)
from runtime.loop.runtime_event import validate_runtime_event  # noqa: E402


OWNER_ID = "affiliate-loop"
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")


class EvidenceError(RuntimeError):
    pass


def _private_jsonl(path: Path, *, runtime_events: bool = False,
                   allowed_modes: frozenset[int] = frozenset({0o600}),
                   max_rows: int = 50_000) -> list[dict]:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) not in allowed_modes):
            raise EvidenceError("journal_not_private")
        rows: list[dict] = []
        with os.fdopen(descriptor, encoding="utf-8") as stream:
            descriptor = -1
            for line in stream:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise EvidenceError("journal_row_invalid")
                if runtime_events:
                    value = validate_runtime_event(value)
                rows.append(value)
                if len(rows) > max_rows:
                    raise EvidenceError("journal_too_large")
        return rows
    except EvidenceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise EvidenceError("journal_invalid") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _epoch(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError as error:
            raise EvidenceError("timestamp_invalid") from error
    raise EvidenceError("timestamp_invalid")


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


def _occurrence_chain(database: Path, occurrence_id: str | None) -> tuple[dict, dict]:
    with sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        unknown = [dict(row) for row in connection.execute(
            """SELECT occurrence_id,owner_id,queued_at,state,sequence,effect_unknown
                 FROM occurrences
                WHERE owner_id=? AND effect_unknown=1
                ORDER BY queued_at,occurrence_id""",
            (OWNER_ID,),
        )]
        if len(unknown) != 1:
            raise EvidenceError("unknown_occurrence_count")
        target = unknown[0]
        if (occurrence_id is not None and target["occurrence_id"] != occurrence_id):
            raise EvidenceError("unknown_occurrence_mismatch")
        if (not SAFE_ID.fullmatch(target["occurrence_id"])
                or target["state"] not in {"claimed", "released"}):
            raise EvidenceError("unknown_occurrence_invalid")
        older_open = connection.execute(
            """SELECT 1 FROM occurrences
                 WHERE owner_id=? AND effect_unknown=0
                   AND state IN ('queued','claimed')
                   AND (queued_at < ? OR (queued_at=? AND occurrence_id < ?))
                 LIMIT 1""",
            (OWNER_ID, target["queued_at"], target["queued_at"], target["occurrence_id"]),
        ).fetchone()
        if older_open:
            raise EvidenceError("older_occurrence_open")
        predecessor_row = connection.execute(
            """SELECT occurrence_id,owner_id,queued_at,state,sequence,effect_unknown
                 FROM occurrences
                WHERE owner_id=?
                  AND (queued_at < ? OR (queued_at=? AND occurrence_id < ?))
                ORDER BY queued_at DESC,occurrence_id DESC LIMIT 1""",
            (OWNER_ID, target["queued_at"], target["queued_at"], target["occurrence_id"]),
        ).fetchone()
    if predecessor_row is None:
        raise EvidenceError("predecessor_missing")
    predecessor = dict(predecessor_row)
    if predecessor["state"] != "released" or predecessor["effect_unknown"] != 0:
        raise EvidenceError("predecessor_not_released")
    return target, predecessor


def _claim_ref(occurrence_id: str) -> str:
    prefix = f"{OWNER_ID}:"
    if not occurrence_id.startswith(prefix):
        raise EvidenceError("occurrence_owner_mismatch")
    return f"lm-occurrence://{OWNER_ID}/{occurrence_id[len(prefix):]}/claim"


def _effect_window(runtime_rows: list[dict], target: dict,
                   predecessor: dict) -> tuple[dict, dict, float, float]:
    claim_ref = _claim_ref(predecessor["occurrence_id"])
    predecessor_reports = [
        row for row in runtime_rows
        if row.get("phase") == "report" and claim_ref in row.get("evidence_refs", [])
    ]
    if len(predecessor_reports) != 1:
        raise EvidenceError("predecessor_report_not_unique")
    released = predecessor_reports[0]
    if (released.get("status") != "pass" or released.get("blocker") is not None):
        raise EvidenceError("predecessor_report_not_pass")
    started = _epoch(released.get("timestamp"))
    if not float(target["queued_at"]) < started:
        raise EvidenceError("target_not_queued_before_window")
    later = sorted(
        (row for row in runtime_rows
         if row.get("phase") in {"execute", "report"}
         and _epoch(row.get("timestamp")) > started),
        key=lambda row: _epoch(row.get("timestamp")),
    )
    if len(later) < 2:
        raise EvidenceError("adjacent_fence_missing")
    execute, blocked = later[:2]
    if (execute.get("phase") != "execute" or execute.get("status") != "running"
            or blocked.get("phase") != "report"
            or blocked.get("run_id") != execute.get("run_id")
            or blocked.get("status") != "blocked"
            or blocked.get("blocker") != "host_admission_deferred:resource_effect_unknown"
            or blocked.get("effect_status") != "unknown"
            or _claim_ref(target["occurrence_id"]) in blocked.get("evidence_refs", [])):
        raise EvidenceError("adjacent_fence_invalid")
    stopped = _epoch(blocked.get("timestamp"))
    if not started < _epoch(execute.get("timestamp")) <= stopped:
        raise EvidenceError("adjacent_fence_time_invalid")
    return released, blocked, started, stopped


def _job_events_in_window(rows: list[dict], started: float, stopped: float) -> int:
    count = 0
    for row in rows:
        observed = _epoch(row.get("updated_at"))
        if started <= observed <= stopped:
            count += 1
    return count


def _interval_rows(rows: list[dict], started: float, stopped: float) -> int:
    count = 0
    for row in rows:
        row_started = _epoch(row.get("started_at"))
        row_stopped = _epoch(row.get("finished_at"))
        if row_started > row_stopped:
            raise EvidenceError("journal_interval_invalid")
        if row_started <= stopped and row_stopped >= started:
            count += 1
    return count


def _build_evidence(database: Path, loop_state: Path, affiliate_state: Path,
                    occurrence_id: str | None) -> tuple[dict, dict]:
    target, predecessor = _occurrence_chain(database, occurrence_id)
    runtime_rows = _private_jsonl(loop_state / "events.jsonl", runtime_events=True)
    released, blocked, started, stopped = _effect_window(
        runtime_rows, target, predecessor,
    )
    job_count = _job_events_in_window(
        _private_jsonl(affiliate_state / "job-events.jsonl"), started, stopped,
    )
    if job_count:
        raise EvidenceError("effect_journal_nonempty")
    child_count = _interval_rows(
        _private_jsonl(
            affiliate_state / "run-receipts.jsonl",
            allowed_modes=frozenset({0o600, 0o644}),
        ),
        started,
        stopped,
    )
    tool_count = _interval_rows(
        _private_jsonl(affiliate_state / "tool-attempt-receipts.jsonl"), started, stopped,
    )
    if child_count or tool_count:
        raise EvidenceError("child_evidence_nonempty")
    evidence = {
        "predecessor_occurrence_id": predecessor["occurrence_id"],
        "predecessor_report_event_id": released["event_id"],
        "blocked_run_id": blocked["run_id"],
        "blocked_report_event_id": blocked["event_id"],
        "window_started_at": released["timestamp"],
        "window_stopped_at": blocked["timestamp"],
        "job_events_in_window": job_count,
        "child_receipts_in_window": child_count,
        "tool_attempts_in_window": tool_count,
    }
    return target, evidence


def reconcile_host_fence(
    database: Path,
    loop_state: Path,
    affiliate_state: Path,
    *,
    occurrence_id: str | None = None,
    resolve: bool = False,
    resolver: Callable[..., bool] = resolve_pre_effect_occurrence,
) -> dict:
    """Return exact proof, or resolve only the occurrence proven pre-effect."""
    try:
        target, evidence = _build_evidence(
            database, loop_state, affiliate_state, occurrence_id,
        )
    except (EvidenceError, OSError, sqlite3.Error) as error:
        return {"state": "HELD", "reason": str(error)}
    proof_identity = {
        "owner_id": OWNER_ID,
        "occurrence_id": target["occurrence_id"],
        "evidence": evidence,
    }
    evidence_key = hashlib.sha256(json.dumps(
        proof_identity, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    evidence_ref = f"affiliate-pre-effect://{evidence_key}"
    if not resolve:
        return {
            "state": "PROOF_READY",
            "occurrence_id": target["occurrence_id"],
            "evidence_ref": evidence_ref,
            "evidence": evidence,
        }
    receipt = {
        "schema_version": 1,
        "receipt_type": "AFFILIATE_HOST_FENCE_RECONCILIATION",
        "owner_id": OWNER_ID,
        "occurrence_id": target["occurrence_id"],
        "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": evidence_ref,
        "evidence": evidence,
        "expected_state": target["state"],
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "resolution_state": "PROOF_READY",
    }
    receipt_path = affiliate_state / "reconciliation" / (
        target["occurrence_id"].replace(":", "-", 1) + ".json"
    )
    _atomic_json(receipt_path, receipt)
    proof = {
        "owner_id": OWNER_ID,
        "occurrence_id": target["occurrence_id"],
        "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": evidence_ref,
    }
    resolved = resolver(
        OWNER_ID,
        target["occurrence_id"],
        pre_effect_readback=lambda: proof,
        expected_state=target["state"],
    )
    receipt["resolution_state"] = "RESOLVED" if resolved else "HELD"
    _atomic_json(receipt_path, receipt)
    return {
        "state": "RECONCILED" if resolved else "HELD",
        "reason": None if resolved else "exact_resolution_rejected",
        "occurrence_id": target["occurrence_id"],
        "evidence_ref": evidence_ref,
        "receipt_path": str(receipt_path),
        "evidence": evidence,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path,
        default=admission_root() / "admission-v2.sqlite3",
    )
    parser.add_argument(
        "--loop-state", type=Path,
        default=Path("~/.local/state/life-manager/affiliate-loop"),
    )
    parser.add_argument(
        "--affiliate-state", type=Path,
        default=Path("~/.local/state/life-manager/affiliate"),
    )
    parser.add_argument("--occurrence")
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    database = args.database.expanduser().resolve()
    canonical_database = (admission_root() / "admission-v2.sqlite3").resolve()
    if args.resolve and database != canonical_database:
        result = {
            "state": "HELD",
            "reason": "resolution_database_not_canonical",
        }
    else:
        result = reconcile_host_fence(
            database,
            args.loop_state.expanduser().resolve(),
            args.affiliate_state.expanduser().resolve(),
            occurrence_id=args.occurrence,
            resolve=args.resolve,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["state"] in {"PROOF_READY", "RECONCILED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
