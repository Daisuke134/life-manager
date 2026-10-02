#!/usr/bin/env python3
"""One-time proof for the legacy Coconala discovery-only heartbeat run."""

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


ALLOWED_FILES = frozenset({
    "b2-context.json", "b2-coverage-cursor.json", "b2-gate.stderr",
    "b2-gate.stdout", "b2-refresh-cursor.json", "passprep.json",
    "passprep.stderr", "passprep.stdout",
})
ALLOWED_EVIDENCE = frozenset({
    "application-observations.json", "application-snapshot.json",
    "parent-B2-applied-history-before-snapshot.json",
    "parent-B2-applied-history-before-snapshot.png",
})
ALLOWED_EVIDENCE_DIRECTORIES = frozenset({"discovery", "application-intent-planner"})
FORBIDDEN_EFFECT_ARTIFACTS = frozenset({
    "application-decisions.json", "parent-commit.json", "result.json",
    "submit-attempt-budget.json",
})
TARGET_OCCURRENCE_ID = "hf-gig-apply-direct:18dacf917a646990-66636"
CLAIM_RUN_ID = "18dad118c3aa4a38-19467"
CLAIM_PASS_ID = "gig-apply-direct-1790973707170340000-19494"
STARTED_EVENT_ID = "24679eaa8feb3b49d8aec1e4"
REPORT_EVENT_ID = "a4123e51ba1535ce72824ff2"


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


def _claim_events(events_path: Path, occurrence_id: str, claim_run_id: str):
    if occurrence_id == f"{legacy.OWNER_ID}:{claim_run_id}":
        raise ValueError("legacy_discovery_claim_identity_invalid")
    try:
        rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("legacy_events_unreadable") from error
    started = [row for row in rows if isinstance(row, dict)
               and row.get("run_id") == claim_run_id
               and row.get("occurrence_id") == f"{legacy.OWNER_ID}:{claim_run_id}"
               and row.get("phase") == "execute" and row.get("status") == "running"
               and row.get("effect_status") == "started"]
    reports = [row for row in rows if isinstance(row, dict)
               and row.get("run_id") == claim_run_id
               and row.get("occurrence_id") == occurrence_id
               and row.get("phase") == "report" and row.get("status") == "blocked"
               and row.get("exit_code") == 75
               and row.get("blocker") == "host_admission_deferred:resource_heartbeat_unavailable"
               and row.get("effect_status") == "unknown"]
    if len(started) != 1 or len(reports) != 1:
        raise ValueError("legacy_discovery_events_not_unique")
    started_event, report_event = started[0], reports[0]
    if (started_event.get("release_sha") != legacy.LEGACY_RELEASE_SHA
            or report_event.get("release_sha") != legacy.LEGACY_RELEASE_SHA
            or started_event.get("event_id") != STARTED_EVENT_ID
            or report_event.get("event_id") != REPORT_EVENT_ID
            or f"lm-occurrence://{occurrence_id.replace(':', '/', 1)}/claim"
            not in report_event.get("evidence_refs", [])):
        raise ValueError("legacy_discovery_events_invalid")
    legacy._timestamp(started_event.get("timestamp"))
    legacy._timestamp(report_event.get("timestamp"))
    return started_event, report_event


def _discovery_boundary(pass_root: Path, pass_dir: Path, claim_run_id: str) -> dict[str, Any]:
    raw_root, raw_dir = Path(pass_root).absolute(), Path(pass_dir).absolute()
    if raw_root.is_symlink() or raw_dir.is_symlink():
        raise ValueError("legacy_discovery_pass_symlink_present")
    root, directory = raw_root.resolve(strict=True), raw_dir.resolve(strict=True)
    if raw_root != root or raw_dir != directory or directory.parent != root:
        raise ValueError("legacy_discovery_pass_root_mismatch")
    matched = legacy.PASS_ID.fullmatch(directory.name)
    run_match = legacy.TIMED_RUN_ID.fullmatch(claim_run_id)
    if directory.name != CLAIM_PASS_ID or matched is None or run_match is None:
        raise ValueError("legacy_discovery_pass_identity_invalid")
    pass_ns, child_pid = int(matched.group(1)), int(matched.group(2))
    run_ns, parent_pid = int(run_match.group(1), 16), int(run_match.group(2))
    if not (0 <= pass_ns - run_ns <= 10_000_000_000):
        raise ValueError("legacy_discovery_pass_time_mismatch")
    if not (parent_pid < child_pid <= parent_pid + 512):
        raise ValueError("legacy_discovery_pass_pid_mismatch")
    candidates = []
    for path in root.glob("gig-apply-direct-*"):
        candidate = legacy.PASS_ID.fullmatch(path.name)
        if candidate is not None and abs(int(candidate.group(1)) - run_ns) <= 10_000_000_000:
            candidates.append(path.resolve(strict=True))
    if sorted(candidates) != [directory]:
        raise ValueError("legacy_discovery_pass_window_not_unique")
    if any(path.is_symlink() for path in directory.rglob("*")):
        raise ValueError("legacy_discovery_pass_symlink_present")
    files = {path.name for path in directory.iterdir() if path.is_file()}
    directories = {path.name for path in directory.iterdir() if path.is_dir()}
    evidence = directory / "refresh-evidence"
    evidence_files = {path.name for path in evidence.iterdir() if path.is_file()}
    evidence_directories = {path.name for path in evidence.iterdir() if path.is_dir()}
    if (files != ALLOWED_FILES or directories != {"refresh-evidence"}
            or evidence_files != ALLOWED_EVIDENCE
            or evidence_directories != ALLOWED_EVIDENCE_DIRECTORIES
            or any(path.name in FORBIDDEN_EFFECT_ARTIFACTS
                   or "submitted" in path.name or "submit-attempt" in path.name
                   for path in directory.rglob("*"))):
        raise ValueError("legacy_discovery_pass_shape_invalid")
    observations = legacy._read_json(evidence / "application-observations.json", "legacy_observations")
    snapshot = legacy._read_json(evidence / "application-snapshot.json", "legacy_snapshot")
    history = legacy._read_json(
        evidence / "parent-B2-applied-history-before-snapshot.json", "legacy_history"
    )
    if (observations.get("version") != 1
            or not all(isinstance(observations.get(key), list) for key in (
                "raw_request_ids", "already_applied_ids", "quarantined_ids",
                "filtered_results", "lifecycle_results"))
            or snapshot.get("pass_id") != directory.name
            or not str((snapshot.get("lease_fence") or {}).get("task", "")).startswith(
                f"gig-apply-direct-{directory.name}")
            or history.get("pass_id") != directory.name
            or history.get("observed") is not True):
        raise ValueError("legacy_discovery_evidence_invalid")
    return {
        "pass_id": directory.name,
        "observations_sha256": _sha256(evidence / "application-observations.json"),
        "snapshot_sha256": _sha256(evidence / "application-snapshot.json"),
        "history_sha256": _sha256(evidence / "parent-B2-applied-history-before-snapshot.json"),
        "evidence_tree_sha256": _tree_sha256(evidence),
    }


def build_proof(*, admission_db: Path, events_path: Path, occurrence_id: str,
                claim_run_id: str, pass_root: Path, pass_dir: Path,
                intent_root: Path) -> dict[str, Any]:
    if occurrence_id != TARGET_OCCURRENCE_ID or claim_run_id != CLAIM_RUN_ID:
        raise ValueError("legacy_discovery_target_not_allowed")
    occurrence = legacy._occurrence(admission_db, occurrence_id)
    started, report = _claim_events(events_path, occurrence_id, claim_run_id)
    boundary = _discovery_boundary(pass_root, pass_dir, claim_run_id)
    legacy._assert_no_bound_intent(intent_root, boundary["pass_id"])
    digest = hashlib.sha256(json.dumps({
        "occurrence_id": occurrence_id,
        "claim_run_id": claim_run_id,
        "started_event_id": started.get("event_id"),
        "report_event_id": report.get("event_id"),
        **boundary,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "owner_id": legacy.OWNER_ID, "occurrence_id": occurrence_id,
        "occurrence_state": occurrence["state"], "claim_run_id": claim_run_id,
        "started_event_id": started.get("event_id"),
        "report_event_id": report.get("event_id"), **boundary,
        "verified": True, "proof_type": "pre_effect", "effect": 0, "readback": 0,
        "evidence_ref": f"coconala-pass://{boundary['pass_id']}/discovery-pre-effect/{digest}",
    }


def reconcile(**kwargs) -> dict[str, Any]:
    resolve = bool(kwargs.pop("resolve", False))
    if (kwargs.get("occurrence_id") != TARGET_OCCURRENCE_ID
            or kwargs.get("claim_run_id") != CLAIM_RUN_ID):
        raise ValueError("legacy_discovery_target_not_allowed")
    proof = build_proof(**kwargs)
    resolved = False
    if resolve:
        resolved = resolve_pre_effect_occurrence(
            legacy.OWNER_ID, proof["occurrence_id"],
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
            events_path=args.events.expanduser().resolve(),
            occurrence_id=args.occurrence_id,
            claim_run_id=args.claim_run_id,
            pass_root=args.pass_root.expanduser().resolve(),
            pass_dir=args.pass_dir.expanduser().resolve(),
            intent_root=args.intent_root.expanduser().resolve(),
            resolve=args.resolve,
        )
    except (OSError, RuntimeError, sqlite3.Error, ValueError) as error:
        print(json.dumps({"status": "inconclusive", "owner_id": legacy.OWNER_ID,
                          "occurrence_id": args.occurrence_id,
                          "reason": str(error) if isinstance(error, ValueError) else "legacy_read_failed"},
                         sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
