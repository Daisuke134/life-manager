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
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
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


def _snapshot(slug="reels-hook-lab", title="Reels Hook Lab", *, occurrence=OCCURRENCE,
              captured_at="2026-09-28T04:00:00+00:00", **overrides):
    return {
        "schema_version": 1,
        "owner_id": OWNER,
        "occurrence_id": occurrence,
        "slug": slug,
        "title": title,
        "captured_at": captured_at,
        **overrides,
    }


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
            load_snapshot_fn=lambda occurrence: _snapshot(None, None),
            read_dashboard_fn=lambda: (_ for _ in ()).throw(AssertionError("must not read dashboard")),
            resolve_unknown_fn=lambda *args, **kwargs: True,
            resolve_pre_effect_fn=fake_resolve,
            ledger_path=ledger_path,
            evidence_dir=ledger_path.parent / "evidence",
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
            load_snapshot_fn=lambda occurrence: _snapshot(),
            read_dashboard_fn=lambda: (_ for _ in ()).throw(AssertionError("must not read dashboard")),
            resolve_unknown_fn=fake_resolve,
            resolve_pre_effect_fn=lambda *args, **kwargs: True,
            ledger_path=ledger_path,
            evidence_dir=ledger_path.parent / "evidence",
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
            load_snapshot_fn=lambda occurrence: _snapshot(),
            read_dashboard_fn=lambda: {"ok": True, "text": dashboard_text},
            resolve_unknown_fn=fake_resolve,
            resolve_pre_effect_fn=lambda *args, **kwargs: True,
            ledger_path=ledger_path,
            evidence_dir=ledger_path.parent / "evidence",
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
            load_snapshot_fn=lambda occurrence: _snapshot(),
            read_dashboard_fn=lambda: {"ok": True, "text": "nothing relevant here"},
            resolve_unknown_fn=lambda *args, **kwargs: True,
            resolve_pre_effect_fn=lambda *args, **kwargs: True,
            ledger_path=ledger_path,
            evidence_dir=ledger_path.parent / "evidence",
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
            load_snapshot_fn=lambda occurrence: _snapshot(),
            read_dashboard_fn=lambda: {"ok": True, "text": "nothing relevant here"},
            resolve_unknown_fn=lambda *args, **kwargs: True,
            resolve_pre_effect_fn=fake_resolve,
            ledger_path=ledger_path,
            evidence_dir=ledger_path.parent / "evidence",
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
            load_snapshot_fn=lambda occurrence: _snapshot(),
            read_dashboard_fn=lambda: {"ok": False, "reason": "browser_lease_rc_9"},
            resolve_unknown_fn=lambda *args, **kwargs: True,
            resolve_pre_effect_fn=lambda *args, **kwargs: True,
            ledger_path=ledger_path,
            evidence_dir=ledger_path.parent / "evidence",
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


def test_missing_or_untrusted_snapshot_stays_held_without_resolver(tmp_path):
    invalid_snapshots = [
        None,
        [],
        {},
        _snapshot(schema_version=True),
        _snapshot(owner_id="another-owner"),
        _snapshot(occurrence="promptbase-loop-daily:another-run"),
        _snapshot(captured_at="2026-09-28T03:59:58+00:00"),
        _snapshot(captured_at="2026-09-28T04:21:00+00:00"),
        _snapshot(title=None),
        _snapshot(None, "Reels Hook Lab"),
        _snapshot(captured_at="not-a-time"),
        _snapshot(extra_field="unbound"),
    ]
    resolver_calls = []
    for snapshot in invalid_snapshots:
        result = reconciler.reconcile(
            OCCURRENCE,
            fenced_row_fn=_fenced_row_fn(queued_at=QUEUED_AT + dt.timedelta(microseconds=500_000)),
            load_snapshot_fn=lambda occurrence, value=snapshot: value,
            read_dashboard_fn=lambda: (_ for _ in ()).throw(AssertionError("must hold before dashboard")),
            resolve_unknown_fn=lambda *args, **kwargs: True,
            resolve_pre_effect_fn=lambda *args, **kwargs: resolver_calls.append((args, kwargs)) or True,
            ledger_path=tmp_path / "ledger.jsonl",
            evidence_dir=tmp_path / "evidence",
            now=QUEUED_AT + dt.timedelta(minutes=20),
            resolve=True,
        )
        assert result["verified"] is False
        assert result["error_class"] == "snapshot_untrusted"
        assert "closed" not in result
    assert resolver_calls == []


def test_second_precision_snapshot_can_bind_to_microsecond_queue_time(tmp_path):
    resolver_calls = []
    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(queued_at=QUEUED_AT + dt.timedelta(microseconds=500_000)),
        load_snapshot_fn=lambda occurrence: _snapshot(None, None),
        read_dashboard_fn=lambda: (_ for _ in ()).throw(AssertionError("no-candidate snapshot proves no dispatch")),
        resolve_unknown_fn=lambda *args, **kwargs: True,
        resolve_pre_effect_fn=lambda *args, **kwargs: resolver_calls.append((args, kwargs)) or True,
        ledger_path=tmp_path / "ledger.jsonl",
        evidence_dir=tmp_path / "evidence",
        now=QUEUED_AT + dt.timedelta(minutes=1),
        resolve=True,
    )
    assert result["verified"] is True
    assert result["effected"] is False
    assert result["closed"] is True
    assert len(resolver_calls) == 1


def test_snapshot_replay_is_idempotent_but_candidate_change_and_corruption_are_rejected(tmp_path):
    snapshot_dir = tmp_path / "snapshots"
    path = reconciler.snapshot_path(OCCURRENCE, snapshot_dir=snapshot_dir)
    first = reconciler.record_snapshot(
        OCCURRENCE, slug="reels-hook-lab", title="Reels Hook Lab", snapshot_dir=snapshot_dir,
        now=QUEUED_AT,
    )
    original_bytes = path.read_bytes()
    replay = reconciler.record_snapshot(
        OCCURRENCE, slug="reels-hook-lab", title="Reels Hook Lab", snapshot_dir=snapshot_dir,
        now=QUEUED_AT + dt.timedelta(seconds=3),
    )
    changed = reconciler.record_snapshot(
        OCCURRENCE, slug="shorts-hook-lab", title="Shorts Hook Lab", snapshot_dir=snapshot_dir,
        now=QUEUED_AT,
    )
    assert "write_error" not in first
    assert replay == first
    assert path.read_bytes() == original_bytes
    assert "write_error" in changed
    assert path.read_bytes() == original_bytes

    path.write_text("{broken", encoding="utf-8")
    corrupted_bytes = path.read_bytes()
    rejected = reconciler.record_snapshot(
        OCCURRENCE, slug="reels-hook-lab", title="Reels Hook Lab", snapshot_dir=snapshot_dir,
        now=QUEUED_AT,
    )
    assert "write_error" in rejected
    assert path.read_bytes() == corrupted_bytes


def test_snapshot_cannot_change_from_selected_to_empty(tmp_path):
    snapshot_dir = tmp_path / "snapshots"
    path = reconciler.snapshot_path(OCCURRENCE, snapshot_dir=snapshot_dir)
    reconciler.record_snapshot(
        OCCURRENCE, slug="reels-hook-lab", title="Reels Hook Lab", snapshot_dir=snapshot_dir,
        now=QUEUED_AT,
    )
    selected_bytes = path.read_bytes()
    result = reconciler.record_snapshot(
        OCCURRENCE, slug=None, title=None, snapshot_dir=snapshot_dir,
        now=QUEUED_AT,
    )
    assert "write_error" in result
    assert path.read_bytes() == selected_bytes


def test_conflicting_concurrent_snapshots_publish_only_one_value(tmp_path):
    snapshot_dir = tmp_path / "snapshots"
    barrier = Barrier(2)

    def write(slug, title):
        barrier.wait()
        try:
            return reconciler.record_snapshot(
                OCCURRENCE, slug=slug, title=title, snapshot_dir=snapshot_dir, now=QUEUED_AT,
            ), None
        except Exception as exc:
            return None, exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda pair: write(*pair), [
            ("reels-hook-lab", "Reels Hook Lab"),
            ("shorts-hook-lab", "Shorts Hook Lab"),
        ]))
    stored = reconciler.load_snapshot(OCCURRENCE, snapshot_dir=snapshot_dir)
    assert all(error is None for _, error in results)
    assert sum("write_error" not in result for result, _ in results) == 1
    assert (stored["slug"], stored["title"]) in {
        ("reels-hook-lab", "Reels Hook Lab"),
        ("shorts-hook-lab", "Shorts Hook Lab"),
    }


def test_candidate_a_pending_cannot_become_no_effect_after_candidate_b_write_attempt(tmp_path):
    snapshot_dir = tmp_path / "snapshots"
    path = reconciler.snapshot_path(OCCURRENCE, snapshot_dir=snapshot_dir)
    reconciler.record_snapshot(
        OCCURRENCE, slug="reels-hook-lab", title="Reels Hook Lab", snapshot_dir=snapshot_dir,
        now=QUEUED_AT,
    )
    conflict = reconciler.record_snapshot(
        OCCURRENCE, slug="shorts-hook-lab", title="Shorts Hook Lab", snapshot_dir=snapshot_dir,
        now=QUEUED_AT + dt.timedelta(seconds=1),
    )
    assert "write_error" in conflict
    no_effect_calls = []
    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(),
        load_snapshot_fn=lambda occurrence: reconciler.load_snapshot(occurrence, snapshot_dir=snapshot_dir),
        read_dashboard_fn=lambda: {"ok": True, "text": "Pending\nReels Hook Lab\n"},
        resolve_unknown_fn=lambda *args, **kwargs: True,
        resolve_pre_effect_fn=lambda *args, **kwargs: no_effect_calls.append((args, kwargs)) or True,
        ledger_path=tmp_path / "ledger.jsonl",
        evidence_dir=tmp_path / "evidence",
        now=QUEUED_AT + dt.timedelta(minutes=20),
        resolve=True,
    )
    assert result["verified"] is True
    assert result["effected"] is True
    assert result["provider_receipt_id"].endswith("status=pending_review")
    assert result["closed"] is True
    assert no_effect_calls == []
