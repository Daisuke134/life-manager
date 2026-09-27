#!/usr/bin/env python3
"""TDD for capafy-ig-marketing-daily's effect_unknown fence reconciler.

Covers the exact CrowdWorks-incident failure mode: never close a fence on an
inconclusive or too-recent readback, only on a complete provider listing.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "capafy_ig_fence_reconcile.py"
_spec = importlib.util.spec_from_file_location("capafy_ig_fence_reconcile", MODULE_PATH)
assert _spec and _spec.loader
reconciler = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = reconciler
_spec.loader.exec_module(reconciler)

OWNER = reconciler.OWNER_ID
OCCURRENCE = f"{OWNER}:18d9196be46174b0-5558"
QUEUED_AT = dt.datetime(2026, 9, 27, 6, 23, 36, tzinfo=dt.timezone.utc)


def _fenced_row_fn(state="claimed", queued_at=QUEUED_AT):
    return lambda owner, occurrence: (state, queued_at)


def test_effected_appends_ledger_and_closes(tmp_path):
    reel_taken_at = QUEUED_AT + dt.timedelta(minutes=20)
    media_readback = {"ok": True, "media": [{"code": "Da7EXAMPLE", "taken_at": reel_taken_at}]}
    ledger_path = tmp_path / "ig-ledger.jsonl"
    closed_calls = []

    def fake_resolve(owner_id, occurrence_id, *, official_readback, expected_state):
        proof = official_readback()
        closed_calls.append((owner_id, occurrence_id, proof, expected_state))
        return True

    result = reconciler.reconcile(
        OCCURRENCE,
        handle="capafy.skills8m4q2z",
        settings_path=tmp_path / "unused-settings.json",
        ledger_path=ledger_path,
        fenced_row_fn=_fenced_row_fn(),
        read_media_fn=lambda handle, settings_path: media_readback,
        resolve_fn=fake_resolve,
        now=QUEUED_AT + dt.timedelta(minutes=25),
        resolve=True,
    )

    assert result["verified"] is True
    assert result["effected"] is True
    assert result["provider_receipt_id"] == "https://www.instagram.com/reel/Da7EXAMPLE/"
    assert result["closed"] is True
    assert result["ledger_appended"] is True
    assert len(closed_calls) == 1
    rows = [json.loads(line) for line in ledger_path.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["reel_url"] == "https://www.instagram.com/reel/Da7EXAMPLE/"
    assert rows[0]["handle"] == "capafy.skills8m4q2z"

    # Re-running must not duplicate the ledger row (idempotent).
    result2 = reconciler.reconcile(
        OCCURRENCE,
        handle="capafy.skills8m4q2z",
        settings_path=tmp_path / "unused-settings.json",
        ledger_path=ledger_path,
        fenced_row_fn=_fenced_row_fn(),
        read_media_fn=lambda handle, settings_path: media_readback,
        resolve_fn=fake_resolve,
        now=QUEUED_AT + dt.timedelta(minutes=30),
        resolve=True,
    )
    assert result2["ledger_appended"] is False
    rows_after = ledger_path.read_text().splitlines()
    assert len(rows_after) == 1


def test_no_effect_complete_listing_closes(tmp_path):
    # Full account history, nothing in the occurrence window, well past the
    # no-effect age gate (2h): safe to close as no-effect.
    media_readback = {"ok": True, "media": [
        {"code": "OldReel1", "taken_at": QUEUED_AT - dt.timedelta(days=1)},
    ]}
    closed_calls = []

    def fake_resolve(owner_id, occurrence_id, *, official_readback, expected_state):
        proof = official_readback()
        closed_calls.append(proof)
        return True

    result = reconciler.reconcile(
        OCCURRENCE,
        handle="capafy.skills8m4q2z",
        settings_path=tmp_path / "unused-settings.json",
        ledger_path=tmp_path / "ig-ledger.jsonl",
        fenced_row_fn=_fenced_row_fn(),
        read_media_fn=lambda handle, settings_path: media_readback,
        resolve_fn=fake_resolve,
        now=QUEUED_AT + dt.timedelta(hours=3),
        resolve=True,
    )

    assert result["verified"] is True
    assert result["effected"] is False
    assert result["closed"] is True
    assert "ledger_appended" not in result
    assert len(closed_calls) == 1
    assert not (tmp_path / "ig-ledger.jsonl").exists()


def test_incomplete_listing_stays_fenced(tmp_path):
    media_readback = {"ok": False, "reason": "readback_failed:LoginRequired"}
    resolve_called = []

    def fake_resolve(*args, **kwargs):
        resolve_called.append((args, kwargs))
        return True

    result = reconciler.reconcile(
        OCCURRENCE,
        handle="capafy.skills8m4q2z",
        settings_path=tmp_path / "unused-settings.json",
        ledger_path=tmp_path / "ig-ledger.jsonl",
        fenced_row_fn=_fenced_row_fn(),
        read_media_fn=lambda handle, settings_path: media_readback,
        resolve_fn=fake_resolve,
        now=QUEUED_AT + dt.timedelta(hours=3),
        resolve=True,
    )

    assert result["verified"] is False
    assert result["reason"] == "readback_failed:LoginRequired"
    assert "closed" not in result
    assert resolve_called == []


def test_too_recent_stays_fenced(tmp_path):
    # Complete listing, nothing in window, but not enough time has passed
    # since queued_at yet -- must not guess "no effect" early.
    media_readback = {"ok": True, "media": []}
    resolve_called = []

    def fake_resolve(*args, **kwargs):
        resolve_called.append((args, kwargs))
        return True

    result = reconciler.reconcile(
        OCCURRENCE,
        handle="capafy.skills8m4q2z",
        settings_path=tmp_path / "unused-settings.json",
        ledger_path=tmp_path / "ig-ledger.jsonl",
        fenced_row_fn=_fenced_row_fn(),
        read_media_fn=lambda handle, settings_path: media_readback,
        resolve_fn=fake_resolve,
        now=QUEUED_AT + dt.timedelta(minutes=30),
        resolve=True,
    )

    assert result["verified"] is False
    assert result["reason"].startswith("too_recent:")
    assert "closed" not in result
    assert resolve_called == []


def test_read_media_rejects_identity_mismatch(tmp_path):
    settings_path = tmp_path / "instagrapi-capafy.skills8m4q2z.json"
    settings_path.write_text("{}", encoding="utf-8")

    class FakeAccount:
        username = "someone-else"
        pk = "123"

    class FakeClient:
        delay_range = None

        def load_settings(self, path):
            return None

        def account_info(self):
            return FakeAccount()

        def user_medias(self, user_id, amount=0):
            raise AssertionError("must not be called after an identity mismatch")

    result = reconciler.read_media(
        "capafy.skills8m4q2z", settings_path, client_factory=FakeClient,
    )
    assert result == {"ok": False, "reason": "authenticated_identity_mismatch"}


def test_read_media_no_saved_session(tmp_path):
    result = reconciler.read_media(
        "capafy.skills8m4q2z", tmp_path / "missing.json",
    )
    assert result == {"ok": False, "reason": "no_saved_session"}


def test_active_ig_handle_unresolvable_stays_fenced(tmp_path):
    accounts_path = tmp_path / "accounts.json"
    accounts_path.write_text("[]", encoding="utf-8")
    result = reconciler.reconcile(
        OCCURRENCE,
        accounts_path=accounts_path,
        ledger_path=tmp_path / "ig-ledger.jsonl",
        fenced_row_fn=_fenced_row_fn(),
        now=QUEUED_AT + dt.timedelta(hours=3),
        resolve=True,
    )
    assert result["verified"] is False
    assert result["reason"] == "active_ig_handle_unresolvable"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
