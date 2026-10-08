#!/usr/bin/env python3
"""TDD for capafy-loop-daily's effect_unknown fence reconciler.

capafy-loop-daily (Capafy skill factory, owner-scoped admission) gets an
effect_unknown fence every time a run exits non-zero after touching Capafy.
The official readback here is packager.py publish-list (+ publish-remote-status
for the receipt's platform_status) -- the same read-only calls
inventory_status.py already trusts. A durable pre-dispatch snapshot recorded
at run start lets the adapter diff precisely; absent a snapshot it falls back
to an updated_at-window check against queued_at.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "capafy_factory_fence_reconcile.py"
_spec = importlib.util.spec_from_file_location("capafy_factory_fence_reconcile", MODULE_PATH)
assert _spec and _spec.loader
reconciler = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = reconciler
_spec.loader.exec_module(reconciler)

OWNER = reconciler.OWNER_ID
OCCURRENCE = f"{OWNER}:18d9271e675ea990-45935"
QUEUED_AT = dt.datetime(2026, 9, 27, 10, 0, 0, tzinfo=dt.timezone.utc)


def _fenced_row_fn(state="claimed", queued_at=QUEUED_AT):
    return lambda owner, occurrence: (state, queued_at)


def _publish_list(agents):
    return {"ok": True, "agents": agents, "sha256": "deadbeef" * 8}


def test_effected_new_agent_since_snapshot_closes_with_receipt(tmp_path):
    snapshot = {
        "schema_version": 1, "owner_id": OWNER, "occurrence_id": OCCURRENCE, "ok": True,
        "agent_count": 1, "latest_versions": {"111": "v1"},
    }
    current_agents = [
        {"agent_id": "111", "updated_at": "2026-09-20T00:00:00Z", "latest_agent_version_id": "v1"},
        {"agent_id": "9563867391", "updated_at": "2026-09-27T10:20:00Z",
         "latest_agent_version_id": "2104175282811195392"},
    ]
    closed_calls = []

    def fake_resolve(owner_id, occurrence_id, *, official_readback, expected_state):
        proof = official_readback()
        closed_calls.append((owner_id, occurrence_id, proof, expected_state))
        return True

    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(),
        load_snapshot_fn=lambda occurrence: snapshot,
        read_publish_list_fn=lambda: _publish_list(current_agents),
        read_remote_status_fn=lambda agent_id: {"ok": True, "platform_status": 1,
                                                 "agent_version_id": "2104175282811195392"},
        resolve_unknown_fn=fake_resolve,
        now=QUEUED_AT + dt.timedelta(minutes=25),
        resolve=True,
    )

    assert result["verified"] is True
    assert result["effected"] is True
    assert result["provider_receipt_id"] == (
        "capafy:agent/9563867391/version/2104175282811195392:platform_status=1"
    )
    assert result["closed"] is True
    assert len(closed_calls) == 1
    assert closed_calls[0][3] == "claimed"


def test_effected_version_bump_without_snapshot_falls_back_to_window(tmp_path):
    current_agents = [
        {"agent_id": "9563867391", "updated_at": "2026-09-27T10:20:00Z",
         "latest_agent_version_id": "2104175282811195392"},
    ]

    def fake_resolve(owner_id, occurrence_id, *, official_readback, expected_state):
        return True

    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(),
        load_snapshot_fn=lambda occurrence: None,
        read_publish_list_fn=lambda: _publish_list(current_agents),
        read_remote_status_fn=lambda agent_id: {"ok": True, "platform_status": 1,
                                                 "agent_version_id": "2104175282811195392"},
        resolve_unknown_fn=fake_resolve,
        now=QUEUED_AT + dt.timedelta(minutes=25),
        resolve=True,
    )

    assert result["verified"] is True
    assert result["effected"] is True
    assert result["provider_receipt_id"] == (
        "capafy:agent/9563867391/version/2104175282811195392:platform_status=1"
    )
    assert result["closed"] is True


def test_no_effect_stable_publish_list_writes_evidence_and_closes(tmp_path):
    snapshot = {
        "schema_version": 1, "owner_id": OWNER, "occurrence_id": OCCURRENCE, "ok": True,
        "agent_count": 1, "latest_versions": {"111": "v1"},
    }
    current_agents = [
        {"agent_id": "111", "updated_at": "2026-09-20T00:00:00Z", "latest_agent_version_id": "v1"},
    ]
    closed_calls = []

    def fake_resolve_pre_effect(owner_id, occurrence_id, *, pre_effect_readback, expected_state):
        proof = pre_effect_readback()
        closed_calls.append((owner_id, occurrence_id, proof, expected_state))
        return True

    evidence_dir = tmp_path / "evidence"
    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(),
        load_snapshot_fn=lambda occurrence: snapshot,
        read_publish_list_fn=lambda: _publish_list(current_agents),
        read_remote_status_fn=lambda agent_id: {"ok": False, "reason": "unused"},
        resolve_pre_effect_fn=fake_resolve_pre_effect,
        evidence_dir=evidence_dir,
        now=QUEUED_AT + dt.timedelta(hours=2),
        resolve=True,
    )

    assert result["verified"] is True
    assert result["effected"] is False
    assert result["closed"] is True
    assert len(closed_calls) == 1
    proof = closed_calls[0][2]
    assert proof["proof_type"] == "pre_effect"
    evidence_path = Path(proof["evidence_ref"])
    assert evidence_path.is_file()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["owner_id"] == OWNER
    assert evidence["occurrence_id"] == OCCURRENCE
    assert evidence["verdict"] == "no_effect"
    assert evidence["agent_count"] == 1


def test_inconclusive_too_recent_stays_fenced(tmp_path):
    current_agents = [
        {"agent_id": "111", "updated_at": "2026-09-20T00:00:00Z", "latest_agent_version_id": "v1"},
    ]
    resolve_called = []

    def fake_resolve_pre_effect(*args, **kwargs):
        resolve_called.append((args, kwargs))
        return True

    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(),
        load_snapshot_fn=lambda occurrence: None,
        read_publish_list_fn=lambda: _publish_list(current_agents),
        read_remote_status_fn=lambda agent_id: {"ok": False, "reason": "unused"},
        resolve_pre_effect_fn=fake_resolve_pre_effect,
        evidence_dir=tmp_path / "evidence",
        now=QUEUED_AT + dt.timedelta(minutes=5),
        run_finished_fn=lambda occurrence, queued: False,  # the run is still alive
        resolve=True,
    )

    assert result["verified"] is False
    assert result["reason"].startswith("too_recent")
    assert "closed" not in result
    assert resolve_called == []
    assert not (tmp_path / "evidence").exists()


def test_inconclusive_publish_list_read_failure_stays_fenced(tmp_path):
    resolve_called = []

    def fake_resolve(*args, **kwargs):
        resolve_called.append((args, kwargs))
        return True

    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(),
        load_snapshot_fn=lambda occurrence: None,
        read_publish_list_fn=lambda: {"ok": False, "reason": "publish_list_exit_1"},
        read_remote_status_fn=lambda agent_id: {"ok": False, "reason": "unused"},
        resolve_unknown_fn=fake_resolve,
        resolve_pre_effect_fn=fake_resolve,
        evidence_dir=tmp_path / "evidence",
        now=QUEUED_AT + dt.timedelta(hours=3),
        resolve=True,
    )

    assert result["verified"] is False
    assert result["reason"] == "publish_list_exit_1"
    assert result["error_class"] == "provider_read_failed"
    assert "closed" not in result
    assert resolve_called == []


def test_effected_but_remote_status_unreadable_stays_fenced(tmp_path):
    snapshot = {
        "schema_version": 1, "owner_id": OWNER, "occurrence_id": OCCURRENCE, "ok": True,
        "agent_count": 0, "latest_versions": {},
    }
    current_agents = [
        {"agent_id": "9563867391", "updated_at": "2026-09-27T10:20:00Z",
         "latest_agent_version_id": "2104175282811195392"},
    ]
    resolve_called = []

    def fake_resolve(*args, **kwargs):
        resolve_called.append((args, kwargs))
        return True

    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(),
        load_snapshot_fn=lambda occurrence: snapshot,
        read_publish_list_fn=lambda: _publish_list(current_agents),
        read_remote_status_fn=lambda agent_id: {"ok": False, "reason": "remote_status_exit_1"},
        resolve_unknown_fn=fake_resolve,
        now=QUEUED_AT + dt.timedelta(minutes=10),
        resolve=True,
    )

    assert result["verified"] is False
    assert result["reason"] == "remote_status_exit_1"
    assert result["error_class"] == "remote_status_read_failed"
    assert "closed" not in result
    assert resolve_called == []


def test_record_snapshot_writes_durable_file(tmp_path):
    snapshot_dir = tmp_path / "snapshots"
    agents = [
        {"agent_id": "111", "updated_at": "2026-09-20T00:00:00Z", "latest_agent_version_id": "v1"},
        {"agent_id": "222", "updated_at": "2026-09-21T00:00:00Z", "latest_agent_version_id": "v9"},
    ]

    written = reconciler.record_snapshot(
        OCCURRENCE,
        read_publish_list_fn=lambda: _publish_list(agents),
        snapshot_dir=snapshot_dir,
    )

    assert written["ok"] is True
    loaded = reconciler.load_snapshot(OCCURRENCE, snapshot_dir=snapshot_dir)
    assert loaded["ok"] is True
    assert loaded["agent_count"] == 2
    assert loaded["latest_versions"] == {"111": "v1", "222": "v9"}


def test_record_snapshot_read_failure_is_recorded_not_fatal(tmp_path):
    snapshot_dir = tmp_path / "snapshots"
    written = reconciler.record_snapshot(
        OCCURRENCE,
        read_publish_list_fn=lambda: {"ok": False, "reason": "publish_list_exit_1"},
        snapshot_dir=snapshot_dir,
    )
    assert written["ok"] is False
    loaded = reconciler.load_snapshot(OCCURRENCE, snapshot_dir=snapshot_dir)
    assert loaded["ok"] is False


def _no_effect_call(tmp_path, *, age, run_finished_fn, resolved):
    return reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(),
        load_snapshot_fn=lambda occurrence: None,
        read_publish_list_fn=lambda: _publish_list([
            {"agent_id": "111", "updated_at": "2026-09-20T00:00:00Z", "latest_agent_version_id": "v1"}]),
        read_remote_status_fn=lambda agent_id: {"ok": False, "reason": "unused"},
        resolve_pre_effect_fn=lambda *a, **k: resolved.append(1) or True,
        evidence_dir=tmp_path / "evidence",
        now=QUEUED_AT + age,
        run_finished_fn=run_finished_fn,
        resolve=True,
    )


def test_finished_run_with_no_effect_closes_without_waiting_an_hour(tmp_path):
    """Dais 2026-10-08: a failed run (e.g. PREPARE_FAILED, no agent spend) left the factory
    fenced for an hour, twice in one day. Once the run process is gone the 3720s wait is moot."""
    resolved = []
    result = _no_effect_call(tmp_path, age=dt.timedelta(minutes=3),
                             run_finished_fn=lambda occurrence, queued: True, resolved=resolved)
    assert result["verified"] is True and result["effected"] is False and result["closed"] is True
    assert resolved == [1]


def test_running_run_still_waits_the_full_window(tmp_path):
    resolved = []
    result = _no_effect_call(tmp_path, age=dt.timedelta(minutes=30),
                             run_finished_fn=lambda occurrence, queued: False, resolved=resolved)
    assert result["verified"] is False and result["reason"].startswith("too_recent")
    assert resolved == []


def test_finished_run_still_needs_a_minute_for_clock_skew(tmp_path):
    resolved = []
    result = _no_effect_call(tmp_path, age=dt.timedelta(seconds=20),
                             run_finished_fn=lambda occurrence, queued: True, resolved=resolved)
    assert result["verified"] is False and resolved == []


def test_run_finished_detects_dead_and_reused_pids():
    queued = dt.datetime(2026, 10, 8, 5, 31, 42, tzinfo=dt.timezone.utc)
    occ = "capafy-loop-daily:18dc77082a0f5390-59016"
    assert reconciler.run_finished(occ, queued, process_start_fn=lambda pid: None) is True
    later = (queued + dt.timedelta(hours=2)).astimezone().strftime("%a %b %e %H:%M:%S %Y")
    assert reconciler.run_finished(occ, queued, process_start_fn=lambda pid: later) is True  # pid reused
    same = queued.astimezone().strftime("%a %b %e %H:%M:%S %Y")
    assert reconciler.run_finished(occ, queued, process_start_fn=lambda pid: same) is False  # still the run
    assert reconciler.run_finished("capafy-loop-daily:no-pid-here", queued,
                                   process_start_fn=lambda pid: None) is False  # unparseable: stay safe
