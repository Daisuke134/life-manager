#!/usr/bin/env python3
"""Resolve the final fixed legacy Coconala result-only occurrence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import coconala_legacy_pre_effect_migration as legacy  # noqa: E402
from runtime.host.resource_admission import resolve_pre_effect_occurrence  # noqa: E402


OWNER_ID = legacy.OWNER_ID
LEGACY_RELEASE_SHA = legacy.LEGACY_RELEASE_SHA
TARGET_OCCURRENCE_ID = "hf-gig-apply-direct:18dad118c3aa4a38-19467"
CLAIM_RUN_ID = "18dad29a777a6138-68078"
CLAIM_PASS_ID = "gig-apply-direct-1790975363879245000-68108"
STARTED_EVENT_ID = "92d03dc45d50bc65f33fb697"
REPORT_EVENT_ID = "295f89a8579aee8157cbf680"
ALLOWED_ROOT_FILES = frozenset({
    "b2-context.json", "b2-coverage-cursor.json", "b2-gate.stderr",
    "b2-gate.stdout", "b2-refresh-cursor.json", "parent.invocation-refresh.json",
    "passprep.json", "passprep.stderr", "passprep.stdout", "refresh.stderr",
    "refresh.stdout", "result.json",
})
ALLOWED_EVIDENCE_FILES = frozenset({
    "application-decision-telegram.json",
    "parent-B2-applied-history-before-snapshot.json",
    "parent-B2-applied-history-before-snapshot.png",
})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted((candidate for candidate in path.rglob("*") if candidate.is_file()),
                       key=lambda candidate: str(candidate.relative_to(path))):
        digest.update(str(item.relative_to(path)).encode())
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _events(events_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("legacy_final_events_unreadable") from error
    started = [row for row in rows if isinstance(row, dict)
               and row.get("event_id") == STARTED_EVENT_ID
               and row.get("run_id") == CLAIM_RUN_ID
               and row.get("occurrence_id") == f"{OWNER_ID}:{CLAIM_RUN_ID}"
               and row.get("phase") == "execute" and row.get("status") == "running"
               and row.get("effect_status") == "started"]
    reports = [row for row in rows if isinstance(row, dict)
               and row.get("event_id") == REPORT_EVENT_ID
               and row.get("run_id") == CLAIM_RUN_ID
               and row.get("occurrence_id") == TARGET_OCCURRENCE_ID
               and row.get("phase") == "report" and row.get("status") == "fail"
               and row.get("exit_code") == 1 and row.get("error_class") == "entrypoint_exit_1"
               and row.get("effect_status") == "unknown"]
    if len(started) != 1 or len(reports) != 1:
        raise ValueError("legacy_final_events_not_unique")
    started_event, report_event = started[0], reports[0]
    if (started_event.get("release_sha") != LEGACY_RELEASE_SHA
            or report_event.get("release_sha") != LEGACY_RELEASE_SHA
            or f"lm-occurrence://{TARGET_OCCURRENCE_ID.replace(':', '/', 1)}/claim"
            not in report_event.get("evidence_refs", [])):
        raise ValueError("legacy_final_events_invalid")
    legacy._timestamp(started_event.get("timestamp"))
    legacy._timestamp(report_event.get("timestamp"))
    return started_event, report_event


def _pass_proof(pass_root: Path, pass_dir: Path, intent_root: Path) -> dict[str, str]:
    raw_root, raw_dir = Path(pass_root).absolute(), Path(pass_dir).absolute()
    if raw_root.is_symlink() or raw_dir.is_symlink():
        raise ValueError("legacy_final_pass_symlink_present")
    root, directory = raw_root.resolve(strict=True), raw_dir.resolve(strict=True)
    if raw_root != root or raw_dir != directory or directory.parent != root or directory.name != CLAIM_PASS_ID:
        raise ValueError("legacy_final_pass_identity_invalid")
    matched, run_match = legacy.PASS_ID.fullmatch(directory.name), legacy.TIMED_RUN_ID.fullmatch(CLAIM_RUN_ID)
    if matched is None or run_match is None:
        raise ValueError("legacy_final_pass_identity_invalid")
    pass_ns, child_pid = int(matched.group(1)), int(matched.group(2))
    run_ns, parent_pid = int(run_match.group(1), 16), int(run_match.group(2))
    if not (0 <= pass_ns - run_ns <= 10_000_000_000) or not (
            parent_pid < child_pid <= parent_pid + 512):
        raise ValueError("legacy_final_pass_binding_invalid")
    candidates = [path.resolve(strict=True) for path in root.glob("gig-apply-direct-*")
                  if (match := legacy.PASS_ID.fullmatch(path.name)) is not None
                  and abs(int(match.group(1)) - run_ns) <= 10_000_000_000]
    if sorted(candidates) != [directory] or any(path.is_symlink() for path in directory.rglob("*")):
        raise ValueError("legacy_final_pass_ambiguous")
    files = {path.name for path in directory.iterdir() if path.is_file()}
    dirs = {path.name for path in directory.iterdir() if path.is_dir()}
    evidence = directory / "refresh-evidence"
    evidence_files = {path.name for path in evidence.iterdir() if path.is_file()}
    evidence_dirs = {path.name for path in evidence.iterdir() if path.is_dir()}
    if (files != ALLOWED_ROOT_FILES or dirs != {"refresh-evidence"}
            or evidence_files != ALLOWED_EVIDENCE_FILES or evidence_dirs != {"discovery"}
            or any("submitted" in path.name or "submit-attempt" in path.name
                   for path in directory.rglob("*"))):
        raise ValueError("legacy_final_pass_shape_invalid")
    result_path = directory / "result.json"
    result = legacy._read_json(result_path, "legacy_final_result")
    if (result.get("status") != "failed" or result.get("pass_id") != CLAIM_PASS_ID
            or result.get("error") != "parent_failed_rc_1"
            or any(result.get(field) != 0 for field in (
                "observed", "judged", "actionable", "effect", "readback", "pending"))):
        raise ValueError("legacy_final_result_invalid")
    history_path = evidence / "parent-B2-applied-history-before-snapshot.json"
    history = legacy._read_json(history_path, "legacy_final_history")
    if history.get("pass_id") != CLAIM_PASS_ID or history.get("observed") is not True:
        raise ValueError("legacy_final_history_invalid")
    legacy._assert_no_bound_intent(intent_root, CLAIM_PASS_ID)
    return {"pass_id": CLAIM_PASS_ID, "result_sha256": _sha256(result_path),
            "history_sha256": _sha256(history_path),
            "evidence_tree_sha256": _tree_sha256(evidence)}


def build_proof(*, admission_db: Path, events_path: Path, occurrence_id: str,
                claim_run_id: str, pass_root: Path, pass_dir: Path,
                intent_root: Path) -> dict[str, Any]:
    if occurrence_id != TARGET_OCCURRENCE_ID or claim_run_id != CLAIM_RUN_ID:
        raise ValueError("legacy_final_target_not_allowed")
    occurrence = legacy._occurrence(admission_db, occurrence_id)
    started, report = _events(events_path)
    boundary = _pass_proof(pass_root, pass_dir, intent_root)
    digest = hashlib.sha256(json.dumps({
        "occurrence_id": occurrence_id, "claim_run_id": claim_run_id,
        "started_event_id": STARTED_EVENT_ID, "report_event_id": REPORT_EVENT_ID,
        **boundary,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"owner_id": OWNER_ID, "occurrence_id": occurrence_id,
            "occurrence_state": occurrence["state"], "claim_run_id": claim_run_id,
            "started_event_id": started["event_id"], "report_event_id": report["event_id"],
            **boundary, "verified": True, "proof_type": "pre_effect",
            "effect": 0, "readback": 0,
            "evidence_ref": f"coconala-pass://{CLAIM_PASS_ID}/final-pre-effect/{digest}"}


def reconcile(*, resolve: bool = False, **kwargs) -> dict[str, Any]:
    proof = build_proof(**kwargs)
    resolved = False
    if resolve:
        resolved = resolve_pre_effect_occurrence(
            OWNER_ID, TARGET_OCCURRENCE_ID,
            pre_effect_readback=lambda: build_proof(**kwargs),
            expected_state=str(proof["occurrence_state"]),
        )
    return {**proof, "resolution_state": "RESOLVED" if resolved else "PROOF_READY"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admission-db", type=Path, default=Path("~/.local/state/life-manager/host-admission/resources/admission-v2.sqlite3"))
    parser.add_argument("--events", type=Path, default=Path("~/.local/state/life-manager/coconala/apply/events.jsonl"))
    parser.add_argument("--occurrence-id", required=True)
    parser.add_argument("--claim-run-id", required=True)
    parser.add_argument("--pass-root", type=Path, default=Path("~/gig/apply-direct"))
    parser.add_argument("--pass-dir", type=Path, required=True)
    parser.add_argument("--intent-root", type=Path, default=Path("~/gig/application-intents"))
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args()
    try:
        result = reconcile(
            admission_db=args.admission_db.expanduser().resolve(),
            events_path=args.events.expanduser().resolve(), occurrence_id=args.occurrence_id,
            claim_run_id=args.claim_run_id, pass_root=args.pass_root.expanduser().resolve(),
            pass_dir=args.pass_dir.expanduser().resolve(),
            intent_root=args.intent_root.expanduser().resolve(), resolve=args.resolve)
    except (OSError, RuntimeError, sqlite3.Error, ValueError) as error:
        print(json.dumps({"status": "inconclusive", "owner_id": OWNER_ID,
                          "occurrence_id": args.occurrence_id,
                          "reason": str(error) if isinstance(error, ValueError) else "legacy_read_failed"},
                         sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
