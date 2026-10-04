import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

import legacy_message_migration as migration
from telegram_outbox import claim_next, enqueue, mark_delivered


OWNER = "life-manager-cfo-hourly"
DATE = "2026-09-26"
RELEASE = "86e447303b9c4f03edaa90244b80c9d4d214ac65"
RUN_ID = "legacy-run-1"
OCCURRENCE = f"{OWNER}:{RUN_ID}"
EVENT_KEY = f"cfo:legacy-subject:telegram:{DATE}"
MESSAGE = "legacy CFO message"


def _event(*, phase, status, timestamp, exit_code=None):
    return {
        "version": 1,
        "event_id": hashlib.sha256(f"{phase}:{timestamp}".encode()).hexdigest()[:24],
        "timestamp": timestamp,
        "loop_id": OWNER,
        "domain": "financial",
        "run_id": RUN_ID,
        "phase": phase,
        "status": status,
        "release_sha": RELEASE,
        "provider": "deterministic",
        "profile_alias": None,
        "effect_class": "message",
        "effect_status": "started" if phase == "execute" else "unknown",
        "blocker": None,
        "evidence_refs": [f"lm-loop://{OWNER}/{RUN_ID}/summary.json"],
        "product_loop_id": None,
        "job_id": OWNER,
        "owner_id": OWNER,
        "wake_id": RUN_ID,
        "occurrence_id": OCCURRENCE,
        "loaded_argv_sha256": None,
        "loaded_env_sha256": None,
        "exit_code": exit_code,
        "failure_layer": "clean",
        "error_class": None,
        "retryable": False,
        "next_action": "none",
        "provider_receipt_id": None,
        "official_readback_ref": None,
    }


def _fixture(
    tmp_path: Path,
    *,
    release=RELEASE,
    delivered_at="2026-09-26T12:26:00Z",
    outbox_delivered_at=None,
):
    outbox_delivered_at = outbox_delivered_at or delivered_at
    state_dir = tmp_path / "cfo"
    state_dir.mkdir(mode=0o700)
    admission_db = tmp_path / "admission.sqlite3"
    with sqlite3.connect(admission_db) as connection:
        connection.execute(
            "CREATE TABLE occurrences(occurrence_id TEXT PRIMARY KEY, owner_id TEXT, state TEXT, effect_unknown INTEGER)"
        )
        connection.execute("INSERT INTO occurrences VALUES(?,?,?,?)", (OCCURRENCE, OWNER, "claimed", 1))
    (state_dir / "last-delivered-snapshot.json").write_text(
        json.dumps({
            "schemaVersion": 1,
            "status": "delivered",
            "reportingDate": DATE,
            "delivery": {"delivery": "delivered", "provider_message_id": "94946"},
            "deliveredAt": delivered_at,
        }),
        encoding="utf-8",
    )
    (state_dir / "last-delivered-snapshot.json").chmod(0o600)
    outbox = state_dir / "telegram-outbox.sqlite3"
    enqueue(database=outbox, event_key=EVENT_KEY, message=MESSAGE, created_at=outbox_delivered_at, repeat_after_seconds=None)
    claimed = claim_next(outbox)
    assert claimed is not None
    mark_delivered(outbox, EVENT_KEY, "94946", outbox_delivered_at, claimed_at=claimed.claimed_at)
    (state_dir / "events.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in (
            {**_event(phase="execute", status="running", timestamp="2026-09-26T12:27:07Z"), "release_sha": release},
            {**_event(phase="report", status="pass", timestamp="2026-09-26T12:27:38Z", exit_code=0), "release_sha": release},
        )),
        encoding="utf-8",
    )
    (state_dir / "events.jsonl").chmod(0o600)
    return state_dir, admission_db, OCCURRENCE


def test_legacy_migration_is_read_only_by_default(tmp_path, monkeypatch):
    state_dir, admission_db, occurrence = _fixture(tmp_path)
    calls = []
    monkeypatch.setattr(migration, "resolve_pre_effect_occurrence", lambda *args, **kwargs: calls.append(args))

    result = migration.reconcile(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)

    assert result["resolution_state"] == "PROOF_READY"
    assert result["proof_type"] == "pre_effect"
    assert calls == []


def test_legacy_migration_resolves_only_exact_old_release_and_pre_effect_proof(tmp_path, monkeypatch):
    state_dir, admission_db, occurrence = _fixture(tmp_path)
    calls = []

    def resolver(owner_id, occurrence_id, **kwargs):
        calls.append((owner_id, occurrence_id, kwargs["pre_effect_readback"]()))
        return True

    monkeypatch.setattr(migration, "resolve_pre_effect_occurrence", resolver)
    result = migration.reconcile(
        state_dir=state_dir,
        admission_db=admission_db,
        occurrence_id=occurrence,
        resolve=True,
    )

    assert result["resolution_state"] == "RESOLVED"
    assert calls[0][2]["proof_type"] == "pre_effect"
    assert calls[0][2]["occurrence_id"] == occurrence


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"release": "a" * 40}, "legacy_release_not_allowed"),
        ({"delivered_at": "2026-09-26T12:28:00Z"}, "legacy_delivery_after_runtime_start"),
    ],
)
def test_legacy_migration_fails_closed_on_release_or_time_mismatch(tmp_path, kwargs, reason):
    state_dir, admission_db, occurrence = _fixture(tmp_path, **kwargs)

    with pytest.raises(ValueError, match=reason):
        migration.build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)


def test_legacy_migration_rejects_multiple_receipt_candidates(tmp_path, monkeypatch):
    state_dir, admission_db, occurrence = _fixture(tmp_path)
    rows = migration.list_items(state_dir / "telegram-outbox.sqlite3")
    monkeypatch.setattr(migration, "list_items", lambda _database: [rows[0], rows[0]])

    with pytest.raises(ValueError, match="legacy_outbox_not_unique"):
        migration.build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)


def test_legacy_migration_rejects_snapshot_outbox_delivery_timestamp_mismatch(tmp_path):
    state_dir, admission_db, occurrence = _fixture(
        tmp_path,
        delivered_at="2026-09-26T12:26:00Z",
        outbox_delivered_at="2026-09-26T12:26:01Z",
    )

    with pytest.raises(ValueError, match="legacy_delivery_timestamp_mismatch"):
        migration.build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)


def test_legacy_migration_rejects_late_outbox_even_when_snapshot_is_before_start(tmp_path):
    state_dir, admission_db, occurrence = _fixture(
        tmp_path,
        delivered_at="2026-09-26T12:26:00Z",
        outbox_delivered_at="2026-09-26T12:28:00Z",
    )

    with pytest.raises(ValueError, match="legacy_delivery_timestamp_mismatch"):
        migration.build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)
