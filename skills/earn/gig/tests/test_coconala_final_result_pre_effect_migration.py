import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "coconala_final_result_pre_effect_migration.py"
SPEC = importlib.util.spec_from_file_location("coconala_final_result_test", SCRIPT)
migration = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(migration)


def _fixture(tmp_path: Path):
    database = tmp_path / "admission.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE occurrences(occurrence_id TEXT PRIMARY KEY, owner_id TEXT, state TEXT, effect_unknown INTEGER)"
        )
        connection.execute("INSERT INTO occurrences VALUES(?,?,?,?)", (
            migration.TARGET_OCCURRENCE_ID, migration.OWNER_ID, "claimed", 1,
        ))
    events = tmp_path / "events.jsonl"
    events.write_text("\n".join(map(json.dumps, [
        {
            "event_id": migration.STARTED_EVENT_ID,
            "run_id": migration.CLAIM_RUN_ID,
            "occurrence_id": f"{migration.OWNER_ID}:{migration.CLAIM_RUN_ID}",
            "release_sha": migration.LEGACY_RELEASE_SHA,
            "phase": "execute", "status": "running", "effect_class": "application",
            "effect_status": "started", "timestamp": "2026-10-02T21:09:22+00:00",
        },
        {
            "event_id": migration.REPORT_EVENT_ID,
            "run_id": migration.CLAIM_RUN_ID,
            "occurrence_id": migration.TARGET_OCCURRENCE_ID,
            "release_sha": migration.LEGACY_RELEASE_SHA,
            "phase": "report", "status": "fail", "exit_code": 1,
            "effect_class": "application", "effect_status": "unknown",
            "error_class": "entrypoint_exit_1", "timestamp": "2026-10-02T21:11:00+00:00",
            "evidence_refs": [
                f"lm-occurrence://{migration.TARGET_OCCURRENCE_ID.replace(':', '/', 1)}/claim"
            ],
        },
    ])) + "\n")
    pass_root = tmp_path / "passes"
    pass_dir = pass_root / migration.CLAIM_PASS_ID
    evidence = pass_dir / "refresh-evidence"
    evidence.mkdir(parents=True)
    (evidence / "discovery").mkdir()
    root_files = {
        "b2-context.json": {}, "b2-coverage-cursor.json": {}, "b2-gate.stderr": "",
        "b2-gate.stdout": "", "b2-refresh-cursor.json": {}, "passprep.json": {},
        "passprep.stderr": "", "passprep.stdout": "", "parent.invocation-refresh.json": {},
        "refresh.stderr": "", "refresh.stdout": "",
        "result.json": {
            "status": "failed", "pass_id": migration.CLAIM_PASS_ID,
            "observed": 0, "judged": 0, "actionable": 0, "effect": 0,
            "readback": 0, "pending": 0, "error": "parent_failed_rc_1",
        },
    }
    for name, value in root_files.items():
        (pass_dir / name).write_text(json.dumps(value) if isinstance(value, dict) else value)
    for name, value in {
        "application-decision-telegram.json": {},
        "parent-B2-applied-history-before-snapshot.json": {
            "pass_id": migration.CLAIM_PASS_ID, "observed": True,
        },
    }.items():
        (evidence / name).write_text(json.dumps(value))
    (evidence / "parent-B2-applied-history-before-snapshot.png").write_bytes(b"png")
    intents = tmp_path / "intents"
    intents.mkdir()
    return database, events, pass_root, pass_dir, intents


def test_exact_final_result_proves_no_application(tmp_path):
    database, events, pass_root, pass_dir, intents = _fixture(tmp_path)
    proof = migration.build_proof(
        admission_db=database, events_path=events,
        occurrence_id=migration.TARGET_OCCURRENCE_ID,
        claim_run_id=migration.CLAIM_RUN_ID,
        pass_root=pass_root, pass_dir=pass_dir, intent_root=intents,
    )
    assert proof["effect"] == 0
    assert proof["readback"] == 0
    assert proof["verified"] is True


def test_final_result_rejects_any_other_target(tmp_path):
    database, events, pass_root, pass_dir, intents = _fixture(tmp_path)
    with pytest.raises(ValueError, match="legacy_final_target_not_allowed"):
        migration.build_proof(
            admission_db=database, events_path=events,
            occurrence_id=f"{migration.OWNER_ID}:other",
            claim_run_id=migration.CLAIM_RUN_ID,
            pass_root=pass_root, pass_dir=pass_dir, intent_root=intents,
        )


def test_final_result_rejects_bound_application_intent(tmp_path):
    database, events, pass_root, pass_dir, intents = _fixture(tmp_path)
    (intents / "request.json").write_text(json.dumps({
        "lease_fence": {"task": f"gig-apply-direct-{migration.CLAIM_PASS_ID}-commit-request"}
    }))
    with pytest.raises(ValueError, match="legacy_intent_bound_to_pass"):
        migration.build_proof(
            admission_db=database, events_path=events,
            occurrence_id=migration.TARGET_OCCURRENCE_ID,
            claim_run_id=migration.CLAIM_RUN_ID,
            pass_root=pass_root, pass_dir=pass_dir, intent_root=intents,
        )
