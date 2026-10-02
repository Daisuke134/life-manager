import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/life-manager/investment-core"))

from telegram_outbox import claim_next, enqueue, mark_delivered  # noqa: E402

import effect_reconcile as effect_reconcile_module  # noqa: E402
from effect_reconcile import build_proof, reconcile  # noqa: E402


OWNER = "life-manager-cfo-hourly"
DATE = "2026-09-26"
RUN_ID = "18d8de9f2e7b25a8-17283"
OCCURRENCE = f"{OWNER}:{RUN_ID}"
RELEASE_SHA = "a" * 40


def _event(*, phase: str, status: str, timestamp: str, exit_code=None, effect_status: str):
    return {
        "version": 1,
        "event_id": hashlib.sha256(f"{phase}:{timestamp}".encode()).hexdigest()[:24],
        "timestamp": timestamp,
        "loop_id": OWNER,
        "domain": "financial",
        "run_id": RUN_ID,
        "phase": phase,
        "status": status,
        "release_sha": RELEASE_SHA,
        "provider": "deterministic",
        "profile_alias": None,
        "effect_class": "message",
        "effect_status": effect_status,
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
    snapshot=True,
    event_pair=True,
    outbox_status="delivered",
    event_key: str | None = None,
):
    state_dir = tmp_path / "cfo"
    state_dir.mkdir(mode=0o700)
    admission_db = tmp_path / "admission.sqlite3"
    with sqlite3.connect(admission_db) as connection:
        connection.execute(
            """CREATE TABLE occurrences(
                occurrence_id TEXT PRIMARY KEY,
                owner_id TEXT,
                state TEXT,
                effect_unknown INTEGER
            )"""
        )
        connection.execute(
            "INSERT INTO occurrences VALUES(?,?,?,?)",
            (OCCURRENCE, OWNER, "claimed", 1),
        )

    event_key = event_key or f"cfo:subject:telegram:{DATE}"
    message = "CFO fixture message"
    message_sha256 = hashlib.sha256(message.encode()).hexdigest()
    outbox = state_dir / "telegram-outbox.sqlite3"
    enqueue(
        database=outbox,
        event_key=event_key,
        message=message,
        created_at="2026-09-26T12:27:08Z",
        repeat_after_seconds=None,
    )
    claimed = claim_next(outbox)
    assert claimed is not None
    if outbox_status == "delivered":
        mark_delivered(
            outbox,
            event_key,
            "94946",
            "2026-09-26T12:27:09Z",
            claimed_at=claimed.claimed_at,
        )
    elif outbox_status == "delivery_uncertain":
        from telegram_outbox import mark_delivery_uncertain

        mark_delivery_uncertain(outbox, event_key, "fixture_uncertain", claimed_at=claimed.claimed_at)

    if snapshot:
        (state_dir / "last-delivered-snapshot.json").write_text(
            json.dumps({
                "schemaVersion": 1,
                "status": "delivered",
                "reportingDate": DATE,
                "digest": "d" * 64,
                "eventKey": event_key,
                "message_sha256": message_sha256,
                "delivery": {"delivery": "delivered", "provider_message_id": "94946"},
                "occurrence_id": OCCURRENCE,
            }),
            encoding="utf-8",
        )
        (state_dir / "last-delivered-snapshot.json").chmod(0o600)

    if event_pair:
        (state_dir / "events.jsonl").write_text(
            "".join(
                json.dumps(row, separators=(",", ":")) + "\n"
                for row in (
                    _event(
                        phase="execute",
                        status="running",
                        effect_status="started",
                        timestamp="2026-09-26T12:27:07.145Z",
                    ),
                    _event(
                        phase="report",
                        status="pass",
                        effect_status="unknown",
                        exit_code=0,
                        timestamp="2026-09-26T12:27:38.256Z",
                    ),
                )
            ),
            encoding="utf-8",
        )
        (state_dir / "events.jsonl").chmod(0o600)

    return state_dir, admission_db, OCCURRENCE


def test_build_proof_requires_exact_runtime_pair_and_delivered_outbox_receipt(tmp_path):
    state_dir, admission_db, occurrence = _fixture(tmp_path)

    proof = build_proof(
        state_dir=state_dir,
        admission_db=admission_db,
        occurrence_id=occurrence,
    )

    assert proof["verified"] is True
    assert proof["owner_id"] == OWNER
    assert proof["occurrence_id"] == occurrence
    assert proof["reporting_date"] == DATE
    assert proof["event_key_sha256"] == hashlib.sha256(
        b"cfo:subject:telegram:2026-09-26"
    ).hexdigest()
    assert proof["message_sha256"] == hashlib.sha256(b"CFO fixture message").hexdigest()
    assert proof["provider_receipt_id"] == "telegram:94946"


def test_read_only_default_does_not_call_resolver(tmp_path, monkeypatch):
    state_dir, admission_db, occurrence = _fixture(tmp_path)
    called = []
    monkeypatch.setattr("effect_reconcile.resolve_unknown_occurrence", lambda *args, **kwargs: called.append(args))

    result = reconcile(
        state_dir=state_dir,
        admission_db=admission_db,
        occurrence_id=occurrence,
    )

    assert result["resolution_state"] == "PROOF_READY"
    assert called == []


def test_resolve_uses_only_verified_proof(tmp_path, monkeypatch):
    state_dir, admission_db, occurrence = _fixture(tmp_path)
    calls = []

    def resolve(owner_id, occurrence_id, **kwargs):
        calls.append((owner_id, occurrence_id, kwargs["official_readback"]()))
        return True

    monkeypatch.setattr("effect_reconcile.resolve_unknown_occurrence", resolve)
    result = reconcile(
        state_dir=state_dir,
        admission_db=admission_db,
        occurrence_id=occurrence,
        resolve=True,
    )

    assert result["resolution_state"] == "RESOLVED"
    assert calls[0][0:2] == (OWNER, occurrence)
    assert calls[0][2]["verified"] is True


@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        ("owner", "occurrence_owner_mismatch"),
        ("events", "runtime_event_pair_missing"),
        ("period", "runtime_event_period_mismatch"),
        ("uncertain", "provider_receipt_not_delivered"),
        ("snapshot", "snapshot_missing"),
    ],
)
def test_build_proof_fails_closed_on_boundary_mismatch(tmp_path, kind, reason):
    state_dir, admission_db, occurrence = _fixture(
        tmp_path,
        snapshot=kind != "snapshot",
        event_pair=kind != "events",
        outbox_status="delivery_uncertain" if kind == "uncertain" else "delivered",
    )
    if kind == "owner":
        occurrence = "other-owner:run-1"
    elif kind == "period":
        snapshot = json.loads((state_dir / "last-delivered-snapshot.json").read_text())
        snapshot["reportingDate"] = "2026-09-25"
        (state_dir / "last-delivered-snapshot.json").write_text(json.dumps(snapshot))
        (state_dir / "last-delivered-snapshot.json").chmod(0o600)

    with pytest.raises(ValueError, match=reason):
        build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)


def test_build_proof_rejects_duplicate_event_key_candidates(tmp_path, monkeypatch):
    state_dir, admission_db, occurrence = _fixture(tmp_path)
    snapshot = json.loads((state_dir / "last-delivered-snapshot.json").read_text())
    (state_dir / "last-delivered-snapshot.json").write_text(json.dumps(snapshot))
    (state_dir / "last-delivered-snapshot.json").chmod(0o600)
    rows = effect_reconcile_module.list_items(state_dir / "telegram-outbox.sqlite3")
    monkeypatch.setattr(effect_reconcile_module, "list_items", lambda _database: [rows[0], rows[0]])

    with pytest.raises(ValueError, match="telegram_outbox_event_not_unique"):
        build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)


def test_build_proof_accepts_legacy_snapshot_bound_by_provider_id(tmp_path):
    state_dir, admission_db, occurrence = _fixture(tmp_path)
    snapshot = json.loads((state_dir / "last-delivered-snapshot.json").read_text())
    snapshot.pop("eventKey")
    snapshot.pop("message_sha256")
    (state_dir / "last-delivered-snapshot.json").write_text(json.dumps(snapshot))
    (state_dir / "last-delivered-snapshot.json").chmod(0o600)

    proof = build_proof(
        state_dir=state_dir,
        admission_db=admission_db,
        occurrence_id=occurrence,
    )

    assert proof["verified"] is True
    assert proof["provider_message_id"] == "94946"
    assert "subject" not in json.dumps(proof)


def test_build_proof_accepts_current_cfo_result_event_key(tmp_path):
    state_dir, admission_db, occurrence = _fixture(
        tmp_path,
        event_key=f"cfo-result:subject:telegram:{DATE}:12",
    )

    proof = build_proof(
        state_dir=state_dir,
        admission_db=admission_db,
        occurrence_id=occurrence,
    )

    assert proof["verified"] is True
    assert proof["provider_receipt_id"] == "telegram:94946"


def test_build_proof_rejects_admission_owner_mismatch(tmp_path):
    state_dir, admission_db, occurrence = _fixture(tmp_path)
    with sqlite3.connect(admission_db) as connection:
        connection.execute("UPDATE occurrences SET owner_id=?", ("other-owner",))

    with pytest.raises(ValueError, match="occurrence_owner_mismatch"):
        build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)


def test_build_proof_rejects_nonterminal_runtime_pair(tmp_path):
    state_dir, admission_db, occurrence = _fixture(tmp_path)
    rows = [json.loads(line) for line in (state_dir / "events.jsonl").read_text().splitlines()]
    rows[-1]["exit_code"] = 1
    (state_dir / "events.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    (state_dir / "events.jsonl").chmod(0o600)

    with pytest.raises(ValueError, match="runtime_event_pair_missing"):
        build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)


def test_build_proof_rejects_uncertain_snapshot_delivery(tmp_path):
    state_dir, admission_db, occurrence = _fixture(tmp_path)
    snapshot = json.loads((state_dir / "last-delivered-snapshot.json").read_text())
    snapshot["status"] = "delivery_uncertain"
    snapshot["delivery"]["delivery"] = "delivery_uncertain"
    (state_dir / "last-delivered-snapshot.json").write_text(json.dumps(snapshot))
    (state_dir / "last-delivered-snapshot.json").chmod(0o600)

    with pytest.raises(ValueError, match="snapshot_not_delivered"):
        build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence)
