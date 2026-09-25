from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "telegram_effect_reconcile.py"
SPEC = importlib.util.spec_from_file_location("affiliate_telegram_effect_reconcile", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)


def _load_module():
    assert SPEC.loader is not None
    SPEC.loader.exec_module(MODULE)
    return MODULE


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    path.chmod(0o600)


def _fixture(tmp_path: Path) -> tuple[Path, Path, str, str, str]:
    state = tmp_path / "affiliate"
    database = tmp_path / "admission.sqlite3"
    occurrence = "affiliate-loop:run-1"
    telegram_event = "telegram-event-1"
    body = "Affiliate report\nresult: SELF_HEALED"
    with sqlite3.connect(database) as connection:
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
            (occurrence, "affiliate-loop", "claimed", 1),
        )
    _jsonl(state / "telegram-outbox.jsonl", [{
        "event_uuid": telegram_event,
        "kind": "SELF_HEALED",
        "body": body,
        "created_at": 1_000,
    }])
    _jsonl(state / "telegram-sent.jsonl", [{
        "event_uuid": telegram_event,
        "message_id": "old-provider-id",
        "sent_at": 1_010,
    }])
    return state, database, occurrence, telegram_event, body


def _readback(body: str, *, message_id: str = "new-provider-id",
              timestamp: str = "1970-01-01T00:18:00+00:00") -> dict:
    return {
        "verified": True,
        "provider": "telegram",
        "chat_id": "local-life-manager",
        "chat_name": "Local Life Manager",
        "message_id": message_id,
        "sender_id": "bot-1",
        "date": timestamp,
        "text_sha256": hashlib.sha256(body.encode()).hexdigest(),
    }


def test_build_proof_binds_exact_body_and_records_provider_id_mismatch(tmp_path):
    module = _load_module()
    state, database, occurrence, telegram_event, body = _fixture(tmp_path)

    proof = module.build_proof(
        state_root=state,
        database=database,
        occurrence_id=occurrence,
        telegram_event_uuid=telegram_event,
        readback=_readback(body),
    )

    assert proof["verified"] is True
    assert proof["provider_receipt_id"] == "telegram:local-life-manager:new-provider-id"
    assert proof["local_provider_message_id"] == "old-provider-id"
    assert proof["official_provider_message_id"] == "new-provider-id"
    assert proof["provider_message_id_mismatch"] is True
    assert proof["body_sha256"] == hashlib.sha256(body.encode()).hexdigest()


def test_build_proof_rejects_body_hash_mismatch(tmp_path):
    module = _load_module()
    state, database, occurrence, telegram_event, body = _fixture(tmp_path)
    readback = _readback(body)
    readback["text_sha256"] = hashlib.sha256(b"different").hexdigest()

    with pytest.raises(ValueError, match="body_hash_mismatch"):
        module.build_proof(
            state_root=state,
            database=database,
            occurrence_id=occurrence,
            telegram_event_uuid=telegram_event,
            readback=readback,
        )


def test_build_proof_rejects_readback_outside_send_window(tmp_path):
    module = _load_module()
    state, database, occurrence, telegram_event, body = _fixture(tmp_path)

    with pytest.raises(ValueError, match="readback_time_outside_window"):
        module.build_proof(
            state_root=state,
            database=database,
            occurrence_id=occurrence,
            telegram_event_uuid=telegram_event,
            readback=_readback(body, timestamp="1970-01-01T02:00:00+00:00"),
        )
