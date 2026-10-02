import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "coconala_discovery_pre_effect_migration.py"
SPEC = importlib.util.spec_from_file_location("coconala_discovery_migration_test", SCRIPT)
migration = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(migration)

OWNER = "hf-gig-apply-direct"
OCCURRENCE = f"{OWNER}:18dacf917a646990-66636"
CLAIM_RUN = "18dad118c3aa4a38-19467"
PASS_ID = "gig-apply-direct-1790973707170340000-19494"
RELEASE = "287d913c1c76ceeaee04255f9ac63fb8c086d5f8"


def _fixture(tmp_path: Path):
    database = tmp_path / "admission.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE occurrences(occurrence_id TEXT PRIMARY KEY, owner_id TEXT, state TEXT, effect_unknown INTEGER)"
        )
        connection.execute(
            "INSERT INTO occurrences VALUES(?,?,?,?)", (OCCURRENCE, OWNER, "claimed", 1)
        )
    started = {
        "event_id": "started",
        "run_id": CLAIM_RUN,
        "occurrence_id": f"{OWNER}:{CLAIM_RUN}",
        "release_sha": RELEASE,
        "phase": "execute",
        "status": "running",
        "effect_class": "application",
        "effect_status": "started",
        "timestamp": "2026-10-02T20:41:46+00:00",
    }
    report = {
        "event_id": "report",
        "run_id": CLAIM_RUN,
        "occurrence_id": OCCURRENCE,
        "release_sha": RELEASE,
        "phase": "report",
        "status": "blocked",
        "exit_code": 75,
        "effect_class": "application",
        "effect_status": "unknown",
        "blocker": "host_admission_deferred:resource_heartbeat_unavailable",
        "timestamp": "2026-10-02T20:45:20+00:00",
        "evidence_refs": [
            f"lm-occurrence://{OCCURRENCE.replace(':', '/', 1)}/claim"
        ],
    }
    events = tmp_path / "events.jsonl"
    events.write_text(json.dumps(started) + "\n" + json.dumps(report) + "\n")
    pass_root = tmp_path / "passes"
    pass_dir = pass_root / PASS_ID
    evidence = pass_dir / "refresh-evidence"
    evidence.mkdir(parents=True)
    (evidence / "discovery").mkdir()
    (evidence / "application-intent-planner").mkdir()
    for name in (
        "b2-context.json", "b2-coverage-cursor.json", "b2-gate.stderr",
        "b2-gate.stdout", "b2-refresh-cursor.json", "passprep.json",
        "passprep.stderr", "passprep.stdout",
    ):
        (pass_dir / name).write_text("{}")
    for name in (
        "application-observations.json", "application-snapshot.json",
        "parent-B2-applied-history-before-snapshot.json",
    ):
        value = {}
        if name == "application-observations.json":
            value = {"version": 1, "raw_request_ids": ["5304445"], "already_applied_ids": [],
                     "quarantined_ids": [], "filtered_results": [], "lifecycle_results": []}
        elif name == "application-snapshot.json":
            value = {"pass_id": PASS_ID, "lease_fence": {"task": f"gig-apply-direct-{PASS_ID}"}}
        else:
            value = {"pass_id": PASS_ID, "observed": True}
        (evidence / name).write_text(json.dumps(value))
    (evidence / "parent-B2-applied-history-before-snapshot.png").write_bytes(b"png")
    intents = tmp_path / "intents"
    intents.mkdir()
    return database, events, pass_root, pass_dir, intents


def test_discovery_only_claim_is_pre_effect(tmp_path):
    database, events, pass_root, pass_dir, intents = _fixture(tmp_path)

    proof = migration.build_proof(
        admission_db=database,
        events_path=events,
        occurrence_id=OCCURRENCE,
        claim_run_id=CLAIM_RUN,
        pass_root=pass_root,
        pass_dir=pass_dir,
        intent_root=intents,
    )

    assert proof["verified"] is True
    assert proof["effect"] == 0
    assert proof["readback"] == 0
    assert proof["pass_id"] == PASS_ID


def test_discovery_only_claim_rejects_bound_application_intent(tmp_path):
    database, events, pass_root, pass_dir, intents = _fixture(tmp_path)
    (intents / "request.json").write_text(json.dumps({
        "lease_fence": {"task": f"gig-apply-direct-{PASS_ID}-commit-request"}
    }))

    with pytest.raises(ValueError, match="legacy_intent_bound_to_pass"):
        migration.build_proof(
            admission_db=database,
            events_path=events,
            occurrence_id=OCCURRENCE,
            claim_run_id=CLAIM_RUN,
            pass_root=pass_root,
            pass_dir=pass_dir,
            intent_root=intents,
        )


def test_discovery_only_claim_rejects_submit_artifact(tmp_path):
    database, events, pass_root, pass_dir, intents = _fixture(tmp_path)
    (pass_dir / "submit-attempt-budget.json").write_text("{}")

    with pytest.raises(ValueError, match="legacy_discovery_pass_shape_invalid"):
        migration.build_proof(
            admission_db=database,
            events_path=events,
            occurrence_id=OCCURRENCE,
            claim_run_id=CLAIM_RUN,
            pass_root=pass_root,
            pass_dir=pass_dir,
            intent_root=intents,
        )
