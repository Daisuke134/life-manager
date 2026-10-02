import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "coconala_legacy_pre_effect_migration.py"
SPEC = importlib.util.spec_from_file_location("coconala_legacy_pre_effect_migration_test", SCRIPT)
migration = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(migration)

OWNER = "hf-gig-apply-direct"
OCCURRENCE = f"{OWNER}:18d88651ee0bf088-46308"
CAUSE_RUN = "18d886647deb66b8-47365"
RELEASE = "287d913c1c76ceeaee04255f9ac63fb8c086d5f8"
PASS_ID = "gig-apply-direct-1790328621458333000-47404"


def _fixture(tmp_path: Path):
    admission_db = tmp_path / "admission.sqlite3"
    with sqlite3.connect(admission_db) as connection:
        connection.execute(
            "CREATE TABLE occurrences(occurrence_id TEXT PRIMARY KEY, owner_id TEXT, state TEXT, effect_unknown INTEGER)"
        )
        connection.execute(
            "INSERT INTO occurrences VALUES(?,?,?,?)", (OCCURRENCE, OWNER, "claimed", 1)
        )
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps(
            {
                "version": 1,
                "event_id": "a" * 24,
                "timestamp": "2026-09-25T09:30:56.586237+00:00",
                "loop_id": OWNER,
                "run_id": CAUSE_RUN,
                "phase": "report",
                "status": "blocked",
                "release_sha": RELEASE,
                "effect_class": "application",
                "effect_status": "unknown",
                "blocker": "host_admission_deferred:resource_heartbeat_unavailable",
                "occurrence_id": OCCURRENCE,
                "exit_code": 75,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pass_dir = tmp_path / PASS_ID
    pass_dir.mkdir()
    (pass_dir / "passprep.json").write_text(
        json.dumps({"pass_count": 6385, "do_improve": False}), encoding="utf-8"
    )
    (pass_dir / "b2-context.json").write_text(
        json.dumps({"version": 7, "target_applications": 19}), encoding="utf-8"
    )
    for name in (
        "b2-coverage-cursor.json",
        "b2-refresh-cursor.json",
    ):
        (pass_dir / name).write_text("{}\n", encoding="utf-8")
    for name in ("b2-gate.stderr", "b2-gate.stdout", "passprep.stderr", "passprep.stdout"):
        (pass_dir / name).write_text("", encoding="utf-8")
    (pass_dir / "refresh-evidence").mkdir()
    intent_root = tmp_path / "application-intents"
    intent_root.mkdir()
    return admission_db, events, pass_dir, intent_root


def test_legacy_pre_effect_migration_is_read_only_by_default(tmp_path, monkeypatch):
    admission_db, events, pass_dir, intent_root = _fixture(tmp_path)
    calls = []
    monkeypatch.setattr(
        migration,
        "resolve_pre_effect_occurrence",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = migration.reconcile(
        admission_db=admission_db,
        events_path=events,
        occurrence_id=OCCURRENCE,
        cause_run_id=CAUSE_RUN,
        pass_root=pass_dir.parent,
        pass_dir=pass_dir,
        intent_root=intent_root,
    )

    assert result["resolution_state"] == "PROOF_READY"
    assert result["proof_type"] == "pre_effect"
    assert result["pass_id"] == PASS_ID
    assert calls == []


def test_legacy_pre_effect_migration_resolves_exact_occurrence(tmp_path, monkeypatch):
    admission_db, events, pass_dir, intent_root = _fixture(tmp_path)
    calls = []

    def resolver(owner_id, occurrence_id, **kwargs):
        calls.append((owner_id, occurrence_id, kwargs["pre_effect_readback"]()))
        return True

    monkeypatch.setattr(migration, "resolve_pre_effect_occurrence", resolver)
    result = migration.reconcile(
        admission_db=admission_db,
        events_path=events,
        occurrence_id=OCCURRENCE,
        cause_run_id=CAUSE_RUN,
        pass_root=pass_dir.parent,
        pass_dir=pass_dir,
        intent_root=intent_root,
        resolve=True,
    )

    assert result["resolution_state"] == "RESOLVED"
    assert calls[0][0:2] == (OWNER, OCCURRENCE)
    assert calls[0][2]["verified"] is True
    assert calls[0][2]["proof_type"] == "pre_effect"


@pytest.mark.parametrize("forbidden", ["result.json", "parent.invocation-refresh.json"])
def test_legacy_pre_effect_migration_rejects_unknown_top_level_file(tmp_path, forbidden):
    admission_db, events, pass_dir, intent_root = _fixture(tmp_path)
    path = pass_dir / forbidden
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="legacy_pass_shape_invalid"):
        migration.build_proof(
            admission_db=admission_db,
            events_path=events,
            occurrence_id=OCCURRENCE,
            cause_run_id=CAUSE_RUN,
            pass_root=pass_dir.parent,
            pass_dir=pass_dir,
            intent_root=intent_root,
        )


def test_legacy_pre_effect_migration_rejects_intent_bound_to_pass(tmp_path):
    admission_db, events, pass_dir, intent_root = _fixture(tmp_path)
    (intent_root / "123.json").write_text(
        json.dumps(
            {
                "request_id": "123",
                "state": "prepared",
                "effect_phase": "irreversible_attempt_started",
                "lease_fence": {"task": PASS_ID},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="legacy_intent_bound_to_pass"):
        migration.build_proof(
            admission_db=admission_db,
            events_path=events,
            occurrence_id=OCCURRENCE,
            cause_run_id=CAUSE_RUN,
            pass_root=pass_dir.parent,
            pass_dir=pass_dir,
            intent_root=intent_root,
        )


def test_legacy_pre_effect_migration_rejects_runtime_intent_task_for_pass(tmp_path):
    admission_db, events, pass_dir, intent_root = _fixture(tmp_path)
    (intent_root / "123.json").write_text(
        json.dumps(
            {
                "request_id": "123",
                "state": "prepared",
                "effect_phase": "irreversible_attempt_started",
                "lease_fence": {"task": f"gig-apply-direct-{PASS_ID}-commit-123"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="legacy_intent_bound_to_pass"):
        migration.build_proof(
            admission_db=admission_db,
            events_path=events,
            occurrence_id=OCCURRENCE,
            cause_run_id=CAUSE_RUN,
            pass_root=pass_dir.parent,
            pass_dir=pass_dir,
            intent_root=intent_root,
        )


def test_legacy_pre_effect_migration_rejects_unbound_cause_event(tmp_path):
    admission_db, events, pass_dir, intent_root = _fixture(tmp_path)
    rows = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
    rows[0]["release_sha"] = "b" * 40
    events.write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="legacy_release_not_allowed"):
        migration.build_proof(
            admission_db=admission_db,
            events_path=events,
            occurrence_id=OCCURRENCE,
            cause_run_id=CAUSE_RUN,
            pass_root=pass_dir.parent,
            pass_dir=pass_dir,
            intent_root=intent_root,
        )


def test_legacy_pre_effect_migration_rejects_competing_pass_in_window(tmp_path):
    admission_db, events, pass_dir, intent_root = _fixture(tmp_path)
    competing = pass_dir.parent / "gig-apply-direct-1790328622458333000-47405"
    competing.mkdir()

    with pytest.raises(ValueError, match="legacy_pass_window_not_unique"):
        migration.build_proof(
            admission_db=admission_db,
            events_path=events,
            occurrence_id=OCCURRENCE,
            cause_run_id=CAUSE_RUN,
            pass_root=pass_dir.parent,
            pass_dir=pass_dir,
            intent_root=intent_root,
        )


def test_legacy_pre_effect_migration_rejects_malformed_intent(tmp_path):
    admission_db, events, pass_dir, intent_root = _fixture(tmp_path)
    (intent_root / "broken.json").write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="legacy_intent_store_invalid"):
        migration.build_proof(
            admission_db=admission_db,
            events_path=events,
            occurrence_id=OCCURRENCE,
            cause_run_id=CAUSE_RUN,
            pass_root=pass_dir.parent,
            pass_dir=pass_dir,
            intent_root=intent_root,
        )


def test_legacy_pre_effect_migration_rejects_symlinked_pass(tmp_path):
    admission_db, events, pass_dir, intent_root = _fixture(tmp_path)
    linked = tmp_path / "linked-pass"
    linked.symlink_to(pass_dir, target_is_directory=True)

    with pytest.raises(ValueError, match="legacy_pass_symlink_present"):
        migration.build_proof(
            admission_db=admission_db,
            events_path=events,
            occurrence_id=OCCURRENCE,
            cause_run_id=CAUSE_RUN,
            pass_root=pass_dir.parent,
            pass_dir=linked,
            intent_root=intent_root,
        )


def test_resolve_rebuilds_proof_inside_admission_lock(tmp_path, monkeypatch):
    admission_db, events, pass_dir, intent_root = _fixture(tmp_path)
    original = migration.build_proof
    proofs = []

    def counted(**kwargs):
        proof = original(**kwargs)
        proofs.append(proof)
        return proof

    def resolver(_owner_id, _occurrence_id, **kwargs):
        assert kwargs["pre_effect_readback"]()["verified"] is True
        return True

    monkeypatch.setattr(migration, "build_proof", counted)
    monkeypatch.setattr(migration, "resolve_pre_effect_occurrence", resolver)
    result = migration.reconcile(
        admission_db=admission_db,
        events_path=events,
        occurrence_id=OCCURRENCE,
        cause_run_id=CAUSE_RUN,
        pass_root=pass_dir.parent,
        pass_dir=pass_dir,
        intent_root=intent_root,
        resolve=True,
    )

    assert result["resolution_state"] == "RESOLVED"
    assert len(proofs) == 2
