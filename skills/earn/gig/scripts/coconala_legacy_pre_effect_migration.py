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
PASS_ID = re.compile(r"^gig-apply-direct-([0-9]{19})-([0-9]+)$")
FORBIDDEN_EFFECT_PATHS = (
    "result.json",
    "parent.invocation-refresh.json",
    "submit-attempt-budget.json",
    "refresh-legacy-b2.json",
    "refresh-evidence/application-decisions.json",
    "refresh-evidence/application-snapshot.json",
    "refresh-evidence/application-decision-telegram.json",
)


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


def _pass_boundary(pass_dir: Path, cause_event: dict[str, Any]) -> dict[str, object]:
    pass_dir = pass_dir.resolve()
    matched = PASS_ID.fullmatch(pass_dir.name)
    if not pass_dir.is_dir() or matched is None:
        raise ValueError("legacy_pass_identity_invalid")
    pass_epoch = int(matched.group(1)) / 1_000_000_000
    cause_epoch = _timestamp(cause_event.get("timestamp"))
    if pass_epoch > cause_epoch or cause_epoch - pass_epoch > 120:
        raise ValueError("legacy_pass_time_mismatch")
    passprep = pass_dir / "passprep.json"
    context = pass_dir / "b2-context.json"
    passprep_value = _read_json(passprep, "legacy_passprep")
    context_value = _read_json(context, "legacy_b2_context")
    if not isinstance(passprep_value.get("pass_count"), int):
        raise ValueError("legacy_passprep_invalid")
    if context_value.get("version") != 7:
        raise ValueError("legacy_b2_context_invalid")
    for relative in FORBIDDEN_EFFECT_PATHS:
        if (pass_dir / relative).exists():
            raise ValueError("legacy_effect_boundary_present")
    return {
        "pass_id": pass_dir.name,
        "pass_epoch": pass_epoch,
        "passprep_sha256": _sha256(passprep),
        "context_sha256": _sha256(context),
    }


def _assert_no_bound_intent(intent_root: Path, pass_id: str) -> None:
    for path in sorted(intent_root.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        lease = value.get("lease_fence") if isinstance(value, dict) else None
        if isinstance(lease, dict) and lease.get("task") == pass_id:
            raise ValueError("legacy_intent_bound_to_pass")


def build_proof(
    *,
    admission_db: Path,
    events_path: Path,
    occurrence_id: str,
    cause_run_id: str,
    pass_dir: Path,
    intent_root: Path,
) -> dict[str, Any]:
    occurrence = _occurrence(admission_db, occurrence_id)
    cause = _cause_event(events_path, occurrence_id, cause_run_id)
    boundary = _pass_boundary(pass_dir, cause)
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


def reconcile(
    *,
    admission_db: Path,
    events_path: Path,
    occurrence_id: str,
    cause_run_id: str,
    pass_dir: Path,
    intent_root: Path,
    resolve: bool = False,
) -> dict[str, Any]:
    proof = build_proof(
        admission_db=admission_db,
        events_path=events_path,
        occurrence_id=occurrence_id,
        cause_run_id=cause_run_id,
        pass_dir=pass_dir,
        intent_root=intent_root,
    )
    resolved = False
    if resolve:
        resolved = resolve_pre_effect_occurrence(
            OWNER_ID,
            occurrence_id,
            pre_effect_readback=lambda: proof,
            expected_state=str(proof["occurrence_state"]),
        )
    return {**proof, "resolution_state": "RESOLVED" if resolved else "PROOF_READY"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admission-db", type=Path, default=Path("~/.local/state/life-manager/host-admission/resources/admission-v2.sqlite3"))
    parser.add_argument("--events", type=Path, default=Path("~/.local/state/life-manager/coconala/apply/events.jsonl"))
    parser.add_argument("--occurrence-id", required=True)
    parser.add_argument("--cause-run-id", required=True)
    parser.add_argument("--pass-dir", type=Path, required=True)
    parser.add_argument("--intent-root", type=Path, default=Path("~/gig/application-intents"))
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = reconcile(
            admission_db=args.admission_db.expanduser().resolve(),
            events_path=args.events.expanduser().resolve(),
            occurrence_id=str(args.occurrence_id),
            cause_run_id=str(args.cause_run_id),
            pass_dir=args.pass_dir.expanduser().resolve(),
            intent_root=args.intent_root.expanduser().resolve(),
            resolve=args.resolve,
        )
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
