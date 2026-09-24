"""Tests for the occurrence-bound, read-only CFO Telegram reconciler."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("cfo-telegram-reconcile.py")
SPEC = importlib.util.spec_from_file_location("cfo_telegram_reconcile", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


OWNER = "life-manager-cfo-hourly"
OCCURRENCE = f"{OWNER}:fixture-1"
CHAT_ID = "-100123456789"
MESSAGE_ID = "88317"
BODY_SHA = "a" * 64


def _snapshot(**overrides):
    value = {
        "schemaVersion": 1,
        "status": "delivered",
        "occurrence_id": OCCURRENCE,
        "message_sha256": BODY_SHA,
        "delivery": {"delivery": "delivered", "provider_message_id": MESSAGE_ID},
    }
    value.update(overrides)
    return value


def _proof(**overrides):
    value = {
        "provider": "telegram",
        "state": "delivered",
        "chat_id": CHAT_ID,
        "message_id": MESSAGE_ID,
        "body_sha256": BODY_SHA,
    }
    value.update(overrides)
    return value


def test_exact_occurrence_message_and_body_hash_are_required():
    ready = MODULE.build_proof(_snapshot(), _proof(), owner_id=OWNER,
                               occurrence_id=OCCURRENCE, expected_chat_id=CHAT_ID)
    assert ready["status"] == "ready"
    assert ready["verified"] is True
    assert ready["provider_receipt_id"] == MESSAGE_ID
    assert ready["official_readback_ref"] == f"telegram://{CHAT_ID}/messages/{MESSAGE_ID}"

    assert MODULE.build_proof(_snapshot(occurrence_id=None), _proof(), owner_id=OWNER,
                              occurrence_id=OCCURRENCE, expected_chat_id=CHAT_ID)["reason"] == "snapshot_identity_mismatch"
    assert MODULE.build_proof(_snapshot(), _proof(body_sha256="b" * 64), owner_id=OWNER,
                              occurrence_id=OCCURRENCE, expected_chat_id=CHAT_ID)["reason"] == "telegram_body_mismatch"


def test_provider_chat_and_message_identity_must_match():
    result = MODULE.build_proof(_snapshot(), _proof(chat_id="-100999"), owner_id=OWNER,
                                occurrence_id=OCCURRENCE, expected_chat_id=CHAT_ID)
    assert result["status"] == "inconclusive"
    assert result["reason"] == "telegram_identity_mismatch"


def test_legacy_snapshot_without_occurrence_or_hash_fails_closed():
    result = MODULE.build_proof(
        {"schemaVersion": 1, "status": "delivered", "delivery": {"provider_message_id": MESSAGE_ID}},
        _proof(), owner_id=OWNER, occurrence_id=OCCURRENCE, expected_chat_id=CHAT_ID,
    )
    assert result["status"] == "inconclusive"
    assert result["reason"] == "snapshot_identity_mismatch"
