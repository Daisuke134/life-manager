#!/usr/bin/env python3
"""TDD for promptbase-loop-daily's effect_unknown fence reconciler.

promptbase-loop-daily gets an effect_unknown fence whenever a run exits
non-zero after daily.sh writes a snapshot naming the slug/title it was about
to submit (the run touched -- or was about to touch -- PromptBase). The only
official readback is the seller dashboard text readback.py already parses;
this reconciler never opens the /sell wizard and never submits anything.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys
import tempfile
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "promptbase_fence_reconcile.py"
_spec = importlib.util.spec_from_file_location("promptbase_fence_reconcile", MODULE_PATH)
assert _spec and _spec.loader
reconciler = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = reconciler
_spec.loader.exec_module(reconciler)

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import ledger as ledger_mod  # noqa: E402

OWNER = reconciler.OWNER_ID
OCCURRENCE = f"{OWNER}:18d9271e675ea990-45935"
QUEUED_AT = dt.datetime(2026, 9, 28, 4, 0, 0, tzinfo=dt.timezone.utc)


def _fenced_row_fn(state="claimed", queued_at=QUEUED_AT):
    return lambda owner, occurrence: (state, queued_at)


def _ledger_path():
    tmp = tempfile.TemporaryDirectory()
    return Path(tmp.name) / "ledger.jsonl", tmp


def test_no_candidate_selected_resolves_no_effect_immediately():
    ledger_path, tmp = _ledger_path()
    try:
        closed_calls = []

        def fake_resolve(owner_id, occurrence_id, *, pre_effect_readback, expected_state):
            closed_calls.append((owner_id, occurrence_id, pre_effect_readback(), expected_state))
            return True

        result = reconciler.reconcile(
            OCCURRENCE,
            fenced_row_fn=_fenced_row_fn(),
            load_snapshot_fn=lambda occurrence: {"slug": None, "title": None},
            read_dashboard_fn=lambda: (_ for _ in ()).throw(AssertionError("must not read dashboard")),
            resolve_pre_effect_fn=fake_resolve,
            ledger_path=ledger_path,
            now=QUEUED_AT + dt.timedelta(minutes=1),
            resolve=True,
        )
        assert result["verified"] is True
        assert result["effected"] is False
        assert result["closed"] is True
        assert len(closed_calls) == 1
    finally:
        tmp.cleanup()


def test_already_in_ledger_since_queued_resolves_effected_without_dashboard_read():
    ledger_path, tmp = _ledger_path()
    try:
        ledger_mod.append(
            {"slug": "reels-hook-lab", "promptbase_id": "999", "url": "https://promptbase.com/x",
             "status": "submitted_pending_review", "submitted_at": "2026-09-28T04:05:00Z"},
            ledger_path,
        )

        def fake_resolve(owner_id, occurrence_id, *, official_readback, expected_state):
            return True

        result = reconciler.reconcile(
            OCCURRENCE,
            fenced_row_fn=_fenced_row_fn(),
            load_snapshot_fn=lambda occurrence: {"slug": "reels-hook-lab", "title": "Reels Hook Lab"},
            read_dashboard_fn=lambda: (_ for _ in ()).throw(AssertionError("must not read dashboard")),
            resolve_unknown_fn=fake_resolve,
            ledger_path=ledger_path,
            now=QUEUED_AT + dt.timedelta(minutes=10),
            resolve=True,
        )
        assert result["verified"] is True
        assert result["effected"] is True
        assert "ledger_row:reels-hook-lab" in result["provider_receipt_id"]
        assert result["closed"] is True
    finally:
        tmp.cleanup()


def test_dashboard_shows_pending_appends_missing_ledger_row_and_closes():
    ledger_path, tmp = _ledger_path()
    try:
        dashboard_text = "Pending\nReels Hook Lab\n"

        def fake_resolve(owner_id, occurrence_id, *, official_readback, expected_state):
            return True

        result = reconciler.reconcile(
            OCCURRENCE,
            fenced_row_fn=_fenced_row_fn(),
            load_snapshot_fn=lambda occurrence: {"slug": "reels-hook-lab", "title": "Reels Hook Lab"},
            read_dashboard_fn=lambda: {"ok": True, "text": dashboard_text},
            resolve_unknown_fn=fake_resolve,
            ledger_path=ledger_path,
            now=QUEUED_AT + dt.timedelta(minutes=10),
            resolve=True,
        )
        assert result["verified"] is True
        assert result["effected"] is True
        assert result["closed"] is True
        row = ledger_mod.latest_by_slug(ledger_path)["reels-hook-lab"]
        assert row["status"] == "submitted_pending_review"
    finally:
        tmp.cleanup()


def test_dashboard_absent_too_recent_stays_fenced():
    ledger_path, tmp = _ledger_path()
    try:
        result = reconciler.reconcile(
            OCCURRENCE,
            fenced_row_fn=_fenced_row_fn(),
            load_snapshot_fn=lambda occurrence: {"slug": "reels-hook-lab", "title": "Reels Hook Lab"},
            read_dashboard_fn=lambda: {"ok": True, "text": "nothing relevant here"},
            ledger_path=ledger_path,
            now=QUEUED_AT + dt.timedelta(minutes=1),
            resolve=False,
        )
        assert result["verified"] is False
        assert "too_recent" in result["reason"]
    finally:
        tmp.cleanup()


def test_dashboard_absent_after_window_resolves_no_effect():
    ledger_path, tmp = _ledger_path()
    try:
        closed_calls = []

        def fake_resolve(owner_id, occurrence_id, *, pre_effect_readback, expected_state):
            closed_calls.append(pre_effect_readback())
            return True

        result = reconciler.reconcile(
            OCCURRENCE,
            fenced_row_fn=_fenced_row_fn(),
            load_snapshot_fn=lambda occurrence: {"slug": "reels-hook-lab", "title": "Reels Hook Lab"},
            read_dashboard_fn=lambda: {"ok": True, "text": "nothing relevant here"},
            resolve_pre_effect_fn=fake_resolve,
            ledger_path=ledger_path,
            now=QUEUED_AT + dt.timedelta(seconds=reconciler.NO_EFFECT_MIN_AGE_SECONDS + 1),
            resolve=True,
        )
        assert result["verified"] is True
        assert result["effected"] is False
        assert result["closed"] is True
        assert len(closed_calls) == 1
    finally:
        tmp.cleanup()


def test_dashboard_read_failure_stays_fenced_inconclusive():
    ledger_path, tmp = _ledger_path()
    try:
        result = reconciler.reconcile(
            OCCURRENCE,
            fenced_row_fn=_fenced_row_fn(),
            load_snapshot_fn=lambda occurrence: {"slug": "reels-hook-lab", "title": "Reels Hook Lab"},
            read_dashboard_fn=lambda: {"ok": False, "reason": "browser_lease_rc_9"},
            ledger_path=ledger_path,
            now=QUEUED_AT + dt.timedelta(minutes=20),
            resolve=True,
        )
        assert result["verified"] is False
        assert result["error_class"] == "provider_read_failed"
        assert "closed" not in result
    finally:
        tmp.cleanup()


def test_record_and_load_snapshot_round_trip(tmp_path):
    snapshot_dir = tmp_path / "snapshots"
    written = reconciler.record_snapshot(
        OCCURRENCE, slug="reels-hook-lab", title="Reels Hook Lab", snapshot_dir=snapshot_dir,
        now=QUEUED_AT,
    )
    assert "write_error" not in written
    loaded = reconciler.load_snapshot(OCCURRENCE, snapshot_dir=snapshot_dir)
    assert loaded["slug"] == "reels-hook-lab"
    assert loaded["title"] == "Reels Hook Lab"
