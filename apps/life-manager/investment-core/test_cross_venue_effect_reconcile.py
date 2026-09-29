import json
import sqlite3
from pathlib import Path

import pytest

from cross_venue_effect_reconcile import build_proof
from telegram_outbox import claim_next, enqueue, mark_delivered


OWNER = "investment-cross-venue-report"


def _fixture(tmp_path: Path, *, status: str = "delivered") -> tuple[Path, Path, str]:
    state = tmp_path / "cross-venue"
    state.mkdir()
    database = tmp_path / "admission.sqlite3"
    occurrence = f"{OWNER}:run-1"
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
            (occurrence, OWNER, "claimed", 1),
        )

    event_key = "cross-venue-daily:2026-09-29"
    message = "[Investment Loop][Cross Venue P&L] 2026-09-29"
    enqueue(
        database=state / "telegram-outbox.sqlite3",
        event_key=event_key,
        message=message,
        created_at="2026-09-29T00:00:00Z",
        repeat_after_seconds=None,
    )
    claimed = claim_next(state / "telegram-outbox.sqlite3")
    assert claimed is not None
    if status == "delivered":
        mark_delivered(
            state / "telegram-outbox.sqlite3",
            event_key,
            "telegram-1",
            "2026-09-29T00:00:01Z",
            claimed_at=claimed.claimed_at,
        )

    (state / "cross-venue-2026-09-29.json").write_text(
        json.dumps({
            "day": "2026-09-29",
            "event_key": event_key,
            "occurrence_id": occurrence,
            "status": status,
            "provider_message_id": "telegram-1" if status == "delivered" else None,
        }),
        encoding="utf-8",
    )
    return state, database, occurrence


def test_build_proof_requires_exact_occurrence_and_delivered_provider_receipt(tmp_path):
    state, database, occurrence = _fixture(tmp_path)

    proof = build_proof(
        state_dir=state,
        admission_db=database,
        occurrence_id=occurrence,
    )

    assert proof["verified"] is True
    assert proof["provider"] == "telegram"
    assert proof["provider_receipt_id"] == "telegram:telegram-1"
    assert proof["occurrence_id"] == occurrence


def test_build_proof_keeps_uncertain_delivery_fenced(tmp_path):
    state, database, occurrence = _fixture(tmp_path, status="delivery_uncertain")

    with pytest.raises(ValueError, match="provider_receipt_not_delivered"):
        build_proof(
            state_dir=state,
            admission_db=database,
            occurrence_id=occurrence,
        )
