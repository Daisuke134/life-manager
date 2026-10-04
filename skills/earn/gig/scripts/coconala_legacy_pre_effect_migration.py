#!/usr/bin/env python3
"""One-time pre-effect proof for the retired Coconala application pass.

This migration is deliberately separate from the normal provider reconciler.  It
can close only an old heartbeat-fenced occurrence whose matching pass directory
never crossed the browser/application boundary.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.host.resource_admission import resolve_pre_effect_occurrence  # noqa: E402


OWNER_ID = "hf-gig-apply-direct"
LEGACY_RELEASE_SHA = "287d913c1c76ceeaee04255f9ac63fb8c086d5f8"
OCCURRENCE = re.compile(r"^hf-gig-apply-direct:[A-Za-z0-9._:-]+$")
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TIMED_RUN_ID = re.compile(r"^([0-9a-f]+)-([0-9]+)$")
PASS_ID = re.compile(r"^gig-apply-direct-([0-9]{19})-([0-9]+)$")
ALLOWED_PRE_EFFECT_FILES = frozenset(
    {
        "b2-context.json",
        "b2-coverage-cursor.json",
        "b2-gate.stderr",
        "b2-gate.stdout",
        "b2-refresh-cursor.json",
        "passprep.json",
        "passprep.stderr",
        "passprep.stdout",
    }
)
ALLOWED_PRE_EFFECT_DIRECTORIES = frozenset({"refresh-evidence"})


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label}_unreadable") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label}_invalid")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _timestamp(value: object) -> float:
    if not isinstance(value, str):
        raise ValueError("legacy_cause_timestamp_invalid")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("legacy_cause_timestamp_invalid") from error
    if parsed.tzinfo is None:
        raise ValueError("legacy_cause_timestamp_invalid")
    return parsed.timestamp()


def _occurrence(admission_db: Path, occurrence_id: str) -> dict[str, object]:
    if not OCCURRENCE.fullmatch(occurrence_id):
        raise ValueError("legacy_occurrence_invalid")
    try:
        with sqlite3.connect(f"file:{admission_db}?mode=ro", uri=True, timeout=5) as connection:
            row = connection.execute(
                "SELECT owner_id,state,effect_unknown FROM occurrences WHERE occurrence_id=?",
                (occurrence_id,),
            ).fetchone()
    except sqlite3.Error as error:
        raise ValueError("legacy_admission_unreadable") from error
    if row is None or row[0] != OWNER_ID or row[1] != "claimed" or int(row[2]) != 1:
        raise ValueError("legacy_occurrence_not_fenced")
    return {"owner_id": row[0], "state": row[1], "effect_unknown": int(row[2])}


def _cause_event(events_path: Path, occurrence_id: str, cause_run_id: str) -> dict[str, Any]:
    if not RUN_ID.fullmatch(cause_run_id):
        raise ValueError("legacy_cause_run_invalid")
    matches = []
    try:
        lines = events_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError("legacy_events_unreadable") from error
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(row, dict)
            and row.get("run_id") == cause_run_id
            and row.get("occurrence_id") == occurrence_id
        ):
            matches.append(row)
    if len(matches) != 1:
        raise ValueError("legacy_cause_event_not_unique")
    event = matches[0]
    if event.get("release_sha") != LEGACY_RELEASE_SHA:
        raise ValueError("legacy_release_not_allowed")
    if (
        event.get("phase") != "report"
        or event.get("status") != "blocked"
        or event.get("exit_code") != 75
        or event.get("effect_class") != "application"
        or event.get("effect_status") != "unknown"
        or event.get("blocker")
        != "host_admission_deferred:resource_heartbeat_unavailable"
    ):
        raise ValueError("legacy_cause_event_invalid")
    _timestamp(event.get("timestamp"))
    return event


def _cause_layer_events(
    events_path: Path, occurrence_id: str, cause_run_id: str
) -> tuple[dict[str, Any], dict[str, Any], str]:
    if occurrence_id != f"{OWNER_ID}:{cause_run_id}":
        raise ValueError("legacy_cause_occurrence_mismatch")
    try:
        rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("legacy_events_unreadable") from error
    started = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("run_id") == cause_run_id
        and row.get("occurrence_id") == occurrence_id
        and row.get("phase") == "execute"
        and row.get("status") == "running"
        and row.get("effect_status") == "started"
    ]
    reports = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("run_id") == cause_run_id
        and row.get("phase") == "report"
        and row.get("status") == "blocked"
        and row.get("blocker") == "host_admission_deferred:resource_heartbeat_unavailable"
    ]
    if len(started) != 1 or len(reports) != 1:
        raise ValueError("legacy_cause_layer_events_not_unique")
    started_event, report_event = started[0], reports[0]
    predecessor = report_event.get("occurrence_id")
    if (
        started_event.get("release_sha") != LEGACY_RELEASE_SHA
        or report_event.get("release_sha") != LEGACY_RELEASE_SHA
        or started_event.get("effect_class") != "application"
        or report_event.get("effect_class") != "application"
        or report_event.get("effect_status") != "unknown"
        or report_event.get("exit_code") != 75
        or not isinstance(predecessor, str)
        or predecessor == occurrence_id
        or not OCCURRENCE.fullmatch(predecessor)
        or f"lm-occurrence://{predecessor.replace(':', '/', 1)}/claim"
        not in report_event.get("evidence_refs", [])
    ):
        raise ValueError("legacy_cause_layer_events_invalid")
    _timestamp(started_event.get("timestamp"))
    _timestamp(report_event.get("timestamp"))
    return started_event, report_event, predecessor


def _assert_released_predecessor(admission_db: Path, occurrence_id: str) -> None:
    try:
        with sqlite3.connect(f"file:{admission_db}?mode=ro", uri=True, timeout=5) as connection:
            row = connection.execute(
                "SELECT owner_id,state,effect_unknown FROM occurrences WHERE occurrence_id=?",
                (occurrence_id,),
            ).fetchone()
    except sqlite3.Error as error:
        raise ValueError("legacy_admission_unreadable") from error
    if row is None or row[0] != OWNER_ID or row[1] != "released" or int(row[2]) != 0:
        raise ValueError("legacy_predecessor_not_released")


def _claim_run_no_application(
    events_path: Path,
    occurrence_id: str,
    claim_run_id: str,
    pass_root: Path,
    claim_pass_dir: Path,
    intent_root: Path,
) -> dict[str, Any]:
    if not RUN_ID.fullmatch(claim_run_id):
        raise ValueError("legacy_claim_run_invalid")
    claim_occurrence = f"{OWNER_ID}:{claim_run_id}"
    try:
        rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("legacy_events_unreadable") from error
    started = [
        row for row in rows
        if isinstance(row, dict)
        and row.get("run_id") == claim_run_id
        and row.get("occurrence_id") == claim_occurrence
        and row.get("phase") == "execute"
        and row.get("status") == "running"
        and row.get("effect_status") == "started"
    ]
    reports = [
        row for row in rows
        if isinstance(row, dict)
        and row.get("run_id") == claim_run_id
        and row.get("occurrence_id") == occurrence_id
        and row.get("phase") == "report"
        and row.get("status") == "fail"
        and row.get("error_class") == "entrypoint_exit_1"
        and row.get("exit_code") == 1
        and row.get("effect_status") == "unknown"
    ]
    if len(started) != 1 or len(reports) != 1:
        raise ValueError("legacy_claim_events_not_unique")
    started_event, report_event = started[0], reports[0]
    if (
        started_event.get("release_sha") != LEGACY_RELEASE_SHA
        or report_event.get("release_sha") != LEGACY_RELEASE_SHA
        or f"lm-occurrence://{occurrence_id.replace(':', '/', 1)}/claim"
        not in report_event.get("evidence_refs", [])
    ):
        raise ValueError("legacy_claim_events_invalid")
    _timestamp(started_event.get("timestamp"))
    _timestamp(report_event.get("timestamp"))

    raw_root = Path(pass_root).absolute()
    raw_dir = Path(claim_pass_dir).absolute()
    if raw_root.is_symlink() or raw_dir.is_symlink():
        raise ValueError("legacy_claim_pass_symlink_present")
    resolved_root = raw_root.resolve(strict=True)
    resolved_dir = raw_dir.resolve(strict=True)
    if raw_root != resolved_root or raw_dir != resolved_dir or resolved_dir.parent != resolved_root:
        raise ValueError("legacy_claim_pass_root_mismatch")
    matched = PASS_ID.fullmatch(resolved_dir.name)
    run_match = TIMED_RUN_ID.fullmatch(claim_run_id)
    if matched is None or run_match is None:
        raise ValueError("legacy_claim_pass_identity_invalid")
    pass_ns = int(matched.group(1))
    child_pid = int(matched.group(2))
    run_ns = int(run_match.group(1), 16)
    parent_pid = int(run_match.group(2))
    if not (0 <= pass_ns - run_ns <= 10_000_000_000):
        raise ValueError("legacy_claim_pass_time_mismatch")
    if not (parent_pid < child_pid <= parent_pid + 512):
        raise ValueError("legacy_claim_pass_pid_mismatch")
    if any(path.is_symlink() for path in resolved_dir.rglob("*")):
        raise ValueError("legacy_claim_pass_symlink_present")

    result_path = resolved_dir / "result.json"
    decisions_path = resolved_dir / "combined-evidence" / "application-decisions.json"
    commit_path = resolved_dir / "combined-evidence" / "parent-commit.json"
    result = _read_json(result_path, "legacy_claim_result")
    decisions = _read_json(decisions_path, "legacy_claim_decisions")
    commit = _read_json(commit_path, "legacy_claim_commit")
    zero_fields = ("observed", "judged", "actionable", "effect", "readback", "pending")
    if (
        result.get("status") != "failed"
        or result.get("pass_id") != resolved_dir.name
        or result.get("error") != "parent_failed_rc_2"
        or any(result.get(field) != 0 for field in zero_fields)
        or decisions.get("decisions") != []
        or commit.get("planner_missing_request_ids") != []
        or commit.get("results") != []
    ):
        raise ValueError("legacy_claim_no_effect_invalid")
    _assert_no_bound_intent(intent_root, resolved_dir.name)
    return {
        "claim_run_id": claim_run_id,
        "claim_pass_id": resolved_dir.name,
        "claim_started_event_id": started_event.get("event_id"),
        "claim_report_event_id": report_event.get("event_id"),
        "claim_result_sha256": _sha256(result_path),
        "claim_decisions_sha256": _sha256(decisions_path),
        "claim_commit_sha256": _sha256(commit_path),
    }


def _pass_boundary(
    pass_root: Path, pass_dir: Path, cause_event: dict[str, Any], cause_run_id: str
) -> dict[str, object]:
    raw_root = Path(pass_root).absolute()
    raw_dir = Path(pass_dir).absolute()
    if raw_root.is_symlink() or raw_dir.is_symlink():
        raise ValueError("legacy_pass_symlink_present")
    pass_root = raw_root.resolve(strict=True)
    pass_dir = raw_dir.resolve(strict=True)
    if raw_root != pass_root or raw_dir != pass_dir:
        raise ValueError("legacy_pass_symlink_present")
    if pass_dir.parent != pass_root:
        raise ValueError("legacy_pass_root_mismatch")
    matched = PASS_ID.fullmatch(pass_dir.name)
    run_match = TIMED_RUN_ID.fullmatch(cause_run_id)
    if not pass_dir.is_dir() or matched is None or run_match is None:
        raise ValueError("legacy_pass_identity_invalid")
    pass_ns = int(matched.group(1))
    child_pid = int(matched.group(2))
    run_ns = int(run_match.group(1), 16)
    parent_pid = int(run_match.group(2))
    if not (0 <= pass_ns - run_ns <= 10_000_000_000):
        raise ValueError("legacy_pass_time_mismatch")
    if not (parent_pid < child_pid <= parent_pid + 512):
        raise ValueError("legacy_pass_pid_mismatch")
    candidates = []
    for path in pass_root.glob("gig-apply-direct-*"):
        candidate = PASS_ID.fullmatch(path.name)
        if candidate is not None and abs(int(candidate.group(1)) - run_ns) <= 10_000_000_000:
            candidates.append(path.resolve(strict=True))
    if sorted(candidates) != [pass_dir]:
        raise ValueError("legacy_pass_window_not_unique")
    entries = list(pass_dir.iterdir())
    if any(path.is_symlink() for path in entries):
        raise ValueError("legacy_pass_symlink_present")
    files = {path.name for path in entries if path.is_file()}
    directories = {path.name for path in entries if path.is_dir()}
    if files != ALLOWED_PRE_EFFECT_FILES or directories != ALLOWED_PRE_EFFECT_DIRECTORIES:
        raise ValueError("legacy_pass_shape_invalid")
    evidence_dir = pass_dir / "refresh-evidence"
    if any(evidence_dir.iterdir()):
        raise ValueError("legacy_effect_boundary_present")
    passprep = pass_dir / "passprep.json"
    context = pass_dir / "b2-context.json"
    passprep_value = _read_json(passprep, "legacy_passprep")
    context_value = _read_json(context, "legacy_b2_context")
    if not isinstance(passprep_value.get("pass_count"), int):
        raise ValueError("legacy_passprep_invalid")
    if context_value.get("version") != 7:
        raise ValueError("legacy_b2_context_invalid")
    return {
        "pass_id": pass_dir.name,
        "pass_ns": pass_ns,
        "run_ns": run_ns,
        "parent_pid": parent_pid,
        "child_pid": child_pid,
        "passprep_sha256": _sha256(passprep),
        "context_sha256": _sha256(context),
    }


def _assert_no_bound_intent(intent_root: Path, pass_id: str) -> None:
    raw_root = Path(intent_root).absolute()
    if raw_root.is_symlink() or raw_root.resolve(strict=True) != raw_root or not raw_root.is_dir():
        raise ValueError("legacy_intent_store_invalid")
    for path in sorted(raw_root.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            raise ValueError("legacy_intent_store_invalid")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("legacy_intent_store_invalid") from error
        if not isinstance(value, dict):
            raise ValueError("legacy_intent_store_invalid")
        lease = value.get("lease_fence")
        if isinstance(lease, dict):
            task = lease.get("task")
            if task == pass_id or (
                isinstance(task, str) and task.startswith(f"gig-apply-direct-{pass_id}")
            ):
                raise ValueError("legacy_intent_bound_to_pass")


def build_proof(
    *,
    admission_db: Path,
    events_path: Path,
    occurrence_id: str,
    cause_run_id: str,
    pass_root: Path,
    pass_dir: Path,
    intent_root: Path,
) -> dict[str, Any]:
    occurrence = _occurrence(admission_db, occurrence_id)
    cause = _cause_event(events_path, occurrence_id, cause_run_id)
    boundary = _pass_boundary(pass_root, pass_dir, cause, cause_run_id)
    _assert_no_bound_intent(intent_root, str(boundary["pass_id"]))
    evidence_digest = hashlib.sha256(
        json.dumps(
            {
                "occurrence_id": occurrence_id,
                "cause_event_id": cause.get("event_id"),
                "pass_id": boundary["pass_id"],
                "passprep_sha256": boundary["passprep_sha256"],
                "context_sha256": boundary["context_sha256"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
        "occurrence_state": occurrence["state"],
        "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": f"coconala-pass://{boundary['pass_id']}/pre-effect/{evidence_digest}",
        "cause_run_id": cause_run_id,
        "cause_event_id": cause.get("event_id"),
        "pass_id": boundary["pass_id"],
        "passprep_sha256": boundary["passprep_sha256"],
        "context_sha256": boundary["context_sha256"],
        "effect": 0,
        "readback": 0,
    }


def build_cause_proof(
    *,
    admission_db: Path,
    events_path: Path,
    occurrence_id: str,
    cause_run_id: str,
    pass_root: Path,
    pass_dir: Path,
    intent_root: Path,
    claim_run_id: str,
    claim_pass_dir: Path,
) -> dict[str, Any]:
    occurrence = _occurrence(admission_db, occurrence_id)
    started, report, predecessor = _cause_layer_events(
        events_path, occurrence_id, cause_run_id
    )
    _assert_released_predecessor(admission_db, predecessor)
    boundary = _pass_boundary(pass_root, pass_dir, report, cause_run_id)
    _assert_no_bound_intent(intent_root, str(boundary["pass_id"]))
    claim = _claim_run_no_application(
        events_path,
        occurrence_id,
        claim_run_id,
        pass_root,
        claim_pass_dir,
        intent_root,
    )
    evidence_digest = hashlib.sha256(
        json.dumps(
            {
                "occurrence_id": occurrence_id,
                "predecessor_occurrence_id": predecessor,
                "started_event_id": started.get("event_id"),
                "report_event_id": report.get("event_id"),
                "pass_id": boundary["pass_id"],
                "passprep_sha256": boundary["passprep_sha256"],
                "context_sha256": boundary["context_sha256"],
                **claim,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
        "occurrence_state": occurrence["state"],
        "predecessor_occurrence_id": predecessor,
        "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": f"coconala-pass://{boundary['pass_id']}/cause-pre-effect/{evidence_digest}",
        "cause_run_id": cause_run_id,
        "started_event_id": started.get("event_id"),
        "report_event_id": report.get("event_id"),
        "pass_id": boundary["pass_id"],
        "passprep_sha256": boundary["passprep_sha256"],
        "context_sha256": boundary["context_sha256"],
        **claim,
        "effect": 0,
        "readback": 0,
    }


def reconcile(
    *,
    admission_db: Path,
    events_path: Path,
    occurrence_id: str,
    cause_run_id: str,
    pass_root: Path,
    pass_dir: Path,
    intent_root: Path,
    resolve: bool = False,
) -> dict[str, Any]:
    proof = build_proof(
        admission_db=admission_db,
        events_path=events_path,
        occurrence_id=occurrence_id,
        cause_run_id=cause_run_id,
        pass_root=pass_root,
        pass_dir=pass_dir,
        intent_root=intent_root,
    )
    resolved = False
    if resolve:
        resolved = resolve_pre_effect_occurrence(
            OWNER_ID,
            occurrence_id,
            pre_effect_readback=lambda: build_proof(
                admission_db=admission_db,
                events_path=events_path,
                occurrence_id=occurrence_id,
                cause_run_id=cause_run_id,
                pass_root=pass_root,
                pass_dir=pass_dir,
                intent_root=intent_root,
            ),
            expected_state=str(proof["occurrence_state"]),
        )
    return {**proof, "resolution_state": "RESOLVED" if resolved else "PROOF_READY"}


def reconcile_cause(
    *,
    admission_db: Path,
    events_path: Path,
    occurrence_id: str,
    cause_run_id: str,
    pass_root: Path,
    pass_dir: Path,
    intent_root: Path,
    claim_run_id: str,
    claim_pass_dir: Path,
    resolve: bool = False,
) -> dict[str, Any]:
    proof_args = {
        "admission_db": admission_db,
        "events_path": events_path,
        "occurrence_id": occurrence_id,
        "cause_run_id": cause_run_id,
        "pass_root": pass_root,
        "pass_dir": pass_dir,
        "intent_root": intent_root,
        "claim_run_id": claim_run_id,
        "claim_pass_dir": claim_pass_dir,
    }
    proof = build_cause_proof(**proof_args)
    resolved = False
    if resolve:
        resolved = resolve_pre_effect_occurrence(
            OWNER_ID,
            occurrence_id,
            pre_effect_readback=lambda: build_cause_proof(**proof_args),
            expected_state=str(proof["occurrence_state"]),
        )
    return {**proof, "resolution_state": "RESOLVED" if resolved else "PROOF_READY"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admission-db", type=Path, default=Path("~/.local/state/life-manager/host-admission/resources/admission-v2.sqlite3"))
    parser.add_argument("--events", type=Path, default=Path("~/.local/state/life-manager/coconala/apply/events.jsonl"))
    parser.add_argument("--occurrence-id", required=True)
    parser.add_argument("--cause-run-id", required=True)
    parser.add_argument("--pass-root", type=Path, default=Path("~/gig/apply-direct"))
    parser.add_argument("--pass-dir", type=Path, required=True)
    parser.add_argument("--intent-root", type=Path, default=Path("~/gig/application-intents"))
    parser.add_argument("--resolve", action="store_true")
    parser.add_argument("--cause-layer", action="store_true")
    parser.add_argument("--claim-run-id")
    parser.add_argument("--claim-pass-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        common_args = dict(
            admission_db=args.admission_db.expanduser().resolve(),
            events_path=args.events.expanduser().resolve(),
            occurrence_id=str(args.occurrence_id),
            cause_run_id=str(args.cause_run_id),
            pass_root=args.pass_root.expanduser().resolve(),
            pass_dir=args.pass_dir.expanduser().resolve(),
            intent_root=args.intent_root.expanduser().resolve(),
        )
        if args.cause_layer:
            if not args.claim_run_id or args.claim_pass_dir is None:
                raise ValueError("legacy_claim_proof_required")
            result = reconcile_cause(
                **common_args,
                claim_run_id=str(args.claim_run_id),
                claim_pass_dir=args.claim_pass_dir.expanduser().resolve(),
                resolve=args.resolve,
            )
        else:
            result = reconcile(**common_args, resolve=args.resolve)
    except (OSError, RuntimeError, sqlite3.Error, ValueError) as error:
        print(
            json.dumps(
                {
                    "status": "inconclusive",
                    "owner_id": OWNER_ID,
                    "occurrence_id": str(args.occurrence_id),
                    "reason": str(error) if isinstance(error, ValueError) else "legacy_read_failed",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
