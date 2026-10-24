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

import pytest

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


@pytest.mark.parametrize("current_ids", [[], ["111"], ["111", "111"], ["111", ""]])
def test_no_effect_requires_complete_unique_snapshot_agent_set(tmp_path, current_ids):
    snapshot = {
        "ok": True, "agent_count": 2, "latest_versions": {"111": "v1", "222": "v1"},
    }
    agents = [
        {"agent_id": agent_id, "updated_at": "2026-09-20T00:00:00Z",
         "latest_agent_version_id": "v1"} for agent_id in current_ids
    ]
    closed_calls = []
    evidence_dir = tmp_path / "evidence"
    result = reconciler.reconcile(
        OCCURRENCE, fenced_row_fn=_fenced_row_fn(),
        load_snapshot_fn=lambda occurrence: snapshot,
        read_publish_list_fn=lambda: _publish_list(agents),
        resolve_pre_effect_fn=lambda *args, **kwargs: closed_calls.append((args, kwargs)) or True,
        evidence_dir=evidence_dir, now=QUEUED_AT + dt.timedelta(hours=2),
        run_finished_fn=lambda occurrence, queued: True, resolve=True,
    )
    assert result["verified"] is False
    assert result["reason"] == "snapshot_agent_set_mismatch"
    assert "closed" not in result
    assert closed_calls == []
    assert not evidence_dir.exists()


def test_same_version_updated_after_queue_stays_inconclusive(tmp_path):
    snapshot = {
        "schema_version": 1, "owner_id": OWNER, "occurrence_id": OCCURRENCE, "ok": True,
        "agent_count": 1, "latest_versions": {"111": "v1"},
    }
    current_agents = [{
        "agent_id": "111",
        "updated_at": int((QUEUED_AT + dt.timedelta(minutes=10)).timestamp() * 1000),
        "latest_agent_version_id": "v1",
    }]
    closed_calls = []
    evidence_dir = tmp_path / "evidence"

    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(),
        load_snapshot_fn=lambda occurrence: snapshot,
        read_publish_list_fn=lambda: _publish_list(current_agents),
        read_remote_status_fn=lambda agent_id: {"ok": False, "reason": "unused"},
        resolve_pre_effect_fn=lambda *args, **kwargs: closed_calls.append((args, kwargs)) or True,
        evidence_dir=evidence_dir,
        now=QUEUED_AT + dt.timedelta(hours=2),
        run_finished_fn=lambda occurrence, queued: True,
        resolve=True,
    )

    assert result["verified"] is False
    assert result["reason"] == "same_version_updated_after_queued_at"
    assert "closed" not in result
    assert closed_calls == []
    assert not evidence_dir.exists()


def _write_bound_cp3_run(tmp_path, *, parent_occurrence=OCCURRENCE,
                         agent_id="111", version_id="v1", cp3_attempts=1,
                         event_release_sha=None, publisher_start="2026-09-27 19:00:05",
                         log_summary_overrides=None, verifications_before_cp3=(),
                         verifications_after_cp3=None):
    child_start = QUEUED_AT + dt.timedelta(seconds=10)
    child_finish = QUEUED_AT + dt.timedelta(seconds=20)
    parent_run_id = OCCURRENCE.split(":", 1)[1]
    child_run_id = "f30ba176ebb74acb09a01535"
    release_sha = "a" * 40
    summary = {
        "version": 1,
        "owner_id": OWNER,
        "loop": "capafy",
        "run_id": child_run_id,
        "occurrence_id": f"{OWNER}:{child_run_id}",
        "parent_lifecycle_run_id": parent_run_id,
        "parent_lifecycle_occurrence_id": parent_occurrence,
        "release_sha": release_sha,
        "started_at": child_start.isoformat(),
        "finished_at": child_finish.isoformat(),
        "task_label": "capafy-drainer",
        "task_class": "application-lane-agent",
        "status": "success",
    }
    evidence_root = tmp_path / "agent-runner-evidence" / "capafy-drainer"
    run_dir = evidence_root / f"{int(child_start.timestamp())}-47974"
    run_dir.mkdir(parents=True)
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    summary_path.chmod(0o600)

    log_summary = {**summary, **(log_summary_overrides or {})}
    lines = [
        f"=== {publisher_start} daily_loop start ===",
        f"AGENT_ID={agent_id}",
        f"AGENT_VERSION_ID={version_id}",
        json.dumps(log_summary),
        *verifications_before_cp3,
        *[f"CP3 submit attempt {attempt}" for attempt in range(1, cp3_attempts + 1)],
    ]
    if verifications_after_cp3 is None:
        verifications_after_cp3 = (
            "platform_status=1",
            "platform_status=1 skills=1 cfg=1 package_uploaded=1 audit=1 title=Test Agent",
        )
    lines.extend(verifications_after_cp3)
    lines.extend([
        f"ledger appended {agent_id}",
        f"PUBLISHED + VERIFIED: agent_id={agent_id} (test) — status=1 under review.",
        f"=== {publisher_start} daily_loop done rc=0 (SUBMITTED — {agent_id} finished CP2/CP3 after prepare) ===",
    ])
    publisher_log = tmp_path / "daily_loop.log"
    publisher_log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    event_log = tmp_path / "events.jsonl"
    event_sha = event_release_sha or release_sha
    events = [
        {
            "owner_id": OWNER, "job_id": OWNER, "run_id": parent_run_id,
            "occurrence_id": OCCURRENCE, "release_sha": event_sha,
            "phase": "execute", "status": "running", "effect_class": "publish",
            "effect_status": "started", "timestamp": (QUEUED_AT + dt.timedelta(seconds=1)).isoformat(),
        },
        {
            "owner_id": OWNER, "job_id": OWNER, "run_id": parent_run_id,
            "occurrence_id": OCCURRENCE, "release_sha": event_sha,
            "phase": "report", "status": "pass", "effect_class": "publish",
            "effect_status": "unknown", "exit_code": 0,
            "timestamp": (QUEUED_AT + dt.timedelta(seconds=30)).isoformat(),
        },
    ]
    event_log.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    event_log.chmod(0o600)
    return evidence_root, publisher_log, event_log


def _write_bound_partial_retry_run(tmp_path, *, agent_id="7393298474",
                                   version_id="2110426515594047488",
                                   child_parent_occurrence=OCCURRENCE):
    parent_run_id = OCCURRENCE.split(":", 1)[1]
    child_run_id = "partial-child-run-001"
    release_sha = "b" * 40
    parent_start = QUEUED_AT + dt.timedelta(seconds=1)
    child_start = QUEUED_AT + dt.timedelta(seconds=10)
    child_finish = QUEUED_AT + dt.timedelta(seconds=20)
    parent_finish = QUEUED_AT + dt.timedelta(seconds=30)
    result_path = (
        tmp_path / "agent-runner-evidence" / "capafy-drainer"
        / f"{int(child_start.timestamp())}-47975" / "attempt-01.result.json"
    )
    result_path.parent.mkdir(parents=True)
    result = {
        "status": "ok",
        "evidence": [
            f"STOPPED: agent {agent_id} remains platform_status=0; cannot claim publication.",
            "Lint PASS; CP1 saved with price tab green and PRICES_MATCH 3.",
            "Remote status confirms is_confirmed_skills=true, is_confirmed_config_keys=true, package_uploaded=true, agent_type=run_online",
            "CP3 did not produce official under-review readback; no ledger/commit was made.",
        ],
    }
    result_path.write_text(json.dumps(result), encoding="utf-8")
    # agent_runner writes attempt results 0644 in production (all observed runs).
    result_path.chmod(0o644)
    summary = {
        "version": 1,
        "owner_id": OWNER,
        "loop": "capafy",
        "run_id": child_run_id,
        "occurrence_id": f"{OWNER}:{child_run_id}",
        "parent_lifecycle_run_id": parent_run_id,
        "parent_lifecycle_occurrence_id": child_parent_occurrence,
        "release_sha": release_sha,
        "started_at": child_start.isoformat(),
        "finished_at": child_finish.isoformat(),
        "task_label": "capafy-drainer",
        "task_class": "application-lane-agent",
        "status": "success",
        "result_path": str(result_path),
        "evidence_dir": str(result_path.parent),
    }
    summary_path = result_path.parent / "summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    summary_path.chmod(0o600)

    stamp = (QUEUED_AT + dt.timedelta(seconds=5)).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    inventory = {
        "verdict": "PUBLISHABLE",
        "action": "retry_existing",
        "action_key": f"retry:{agent_id}",
        "item": {"agent_id": agent_id, "title": "TikTok Comment Reply Script Pack"},
    }
    publisher_log = tmp_path / "daily_loop.log"
    publisher_log.write_text("\n".join((
        f"=== {stamp} daily_loop start ===",
        f"{stamp} inventory verdict=PUBLISHABLE :: {json.dumps(inventory, sort_keys=True)}",
        json.dumps(summary, sort_keys=True),
        f"=== {stamp} daily_loop done rc=1 (BLOCKED — post-verdict=PUBLISHABLE, marker NOT touched → self-fix will escalate) ===",
        "",
    )), encoding="utf-8")
    publisher_log.chmod(0o600)

    events = [
        {
            "owner_id": OWNER, "job_id": OWNER, "run_id": parent_run_id,
            "occurrence_id": OCCURRENCE, "release_sha": release_sha,
            "phase": "execute", "status": "running", "effect_class": "publish",
            "effect_status": "started", "timestamp": parent_start.isoformat(),
        },
        {
            "owner_id": OWNER, "job_id": OWNER, "run_id": parent_run_id,
            "occurrence_id": OCCURRENCE, "release_sha": release_sha,
            "phase": "report", "status": "fail", "effect_class": "publish",
            "effect_status": "unknown", "error_class": "entrypoint_exit_1",
            "exit_code": 1, "timestamp": parent_finish.isoformat(),
        },
    ]
    event_log = tmp_path / "events.jsonl"
    event_log.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    event_log.chmod(0o600)
    return result_path.parent.parent, publisher_log, event_log


def test_occurrence_bound_cp3_and_official_status_close_same_version(tmp_path, monkeypatch):
    snapshot = {
        "schema_version": 1, "owner_id": OWNER, "occurrence_id": OCCURRENCE, "ok": True,
        "agent_count": 1, "latest_versions": {"111": "v1"},
    }
    current_agents = [{
        "agent_id": "111",
        "updated_at": int((QUEUED_AT + dt.timedelta(minutes=10)).timestamp() * 1000),
        "latest_agent_version_id": "v1",
    }]
    evidence_root, publisher_log, event_log = _write_bound_cp3_run(tmp_path)
    monkeypatch.setattr(reconciler, "CAPAFY_DRAINER_EVIDENCE_ROOT", evidence_root, raising=False)
    monkeypatch.setattr(reconciler, "CAPAFY_DAILY_LOOP_LOG", publisher_log, raising=False)
    monkeypatch.setattr(reconciler, "RUNTIME_EVENT_LOG", event_log, raising=False)
    closed_calls = []

    def fake_resolve(owner_id, occurrence_id, *, official_readback, expected_state):
        proof = official_readback()
        closed_calls.append((owner_id, occurrence_id, proof, expected_state))
        return True

    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(state="released"),
        load_snapshot_fn=lambda occurrence: snapshot,
        read_publish_list_fn=lambda: _publish_list(current_agents),
        read_remote_status_fn=lambda agent_id: {
            "ok": True, "platform_status": 1, "agent_version_id": "v1",
        },
        resolve_unknown_fn=fake_resolve,
        evidence_dir=tmp_path / "evidence",
        now=QUEUED_AT + dt.timedelta(hours=2),
        run_finished_fn=lambda occurrence, queued: True,
        resolve=True,
    )

    assert result["verified"] is True
    assert result["effected"] is True
    assert result["provider_receipt_id"] == "capafy:agent/111/version/v1:platform_status=1"
    assert result["proof_kind"] == "occurrence_bound_capafy_cp3_and_remote_status"
    assert result["closed"] is True
    assert len(closed_calls) == 1
    proof = closed_calls[0][2]
    assert proof["child_run_id"] == "f30ba176ebb74acb09a01535"
    assert proof["parent_release_sha"] == "a" * 40
    assert proof["platform_status"] == 1
    assert closed_calls[0][3] == "released"
    evidence_path = Path(proof["evidence_ref"])
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["occurrence_id"] == OCCURRENCE
    assert evidence["agent_version_id"] == "v1"
    assert "publisher_log" not in evidence


def test_occurrence_bound_cp3_rejects_wrong_parent_occurrence(tmp_path, monkeypatch):
    snapshot = {
        "schema_version": 1, "owner_id": OWNER, "occurrence_id": OCCURRENCE, "ok": True,
        "agent_count": 1, "latest_versions": {"111": "v1"},
    }
    current_agents = [{
        "agent_id": "111",
        "updated_at": int((QUEUED_AT + dt.timedelta(minutes=10)).timestamp() * 1000),
        "latest_agent_version_id": "v1",
    }]
    evidence_root, publisher_log, event_log = _write_bound_cp3_run(
        tmp_path, parent_occurrence=f"{OWNER}:different-run",
    )
    monkeypatch.setattr(reconciler, "CAPAFY_DRAINER_EVIDENCE_ROOT", evidence_root, raising=False)
    monkeypatch.setattr(reconciler, "CAPAFY_DAILY_LOOP_LOG", publisher_log, raising=False)
    monkeypatch.setattr(reconciler, "RUNTIME_EVENT_LOG", event_log, raising=False)
    remote_calls = []
    closed_calls = []

    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(state="released"),
        load_snapshot_fn=lambda occurrence: snapshot,
        read_publish_list_fn=lambda: _publish_list(current_agents),
        read_remote_status_fn=lambda agent_id: remote_calls.append(agent_id) or {
            "ok": True, "platform_status": 1, "agent_version_id": "v1",
        },
        resolve_unknown_fn=lambda *args, **kwargs: closed_calls.append((args, kwargs)) or True,
        evidence_dir=tmp_path / "evidence",
        now=QUEUED_AT + dt.timedelta(hours=2),
        run_finished_fn=lambda occurrence, queued: True,
        resolve=True,
    )

    assert result["verified"] is False
    assert result["reason"] == "same_version_updated_after_queued_at"
    assert remote_calls == []
    assert closed_calls == []
    assert not (tmp_path / "evidence").exists()


def test_occurrence_bound_cp3_rejects_parent_release_mismatch(tmp_path, monkeypatch):
    snapshot = {
        "schema_version": 1, "owner_id": OWNER, "occurrence_id": OCCURRENCE, "ok": True,
        "agent_count": 1, "latest_versions": {"111": "v1"},
    }
    current_agents = [{
        "agent_id": "111",
        "updated_at": int((QUEUED_AT + dt.timedelta(minutes=10)).timestamp() * 1000),
        "latest_agent_version_id": "v1",
    }]
    evidence_root, publisher_log, event_log = _write_bound_cp3_run(
        tmp_path, event_release_sha="b" * 40,
    )
    monkeypatch.setattr(reconciler, "CAPAFY_DRAINER_EVIDENCE_ROOT", evidence_root, raising=False)
    monkeypatch.setattr(reconciler, "CAPAFY_DAILY_LOOP_LOG", publisher_log, raising=False)
    monkeypatch.setattr(reconciler, "RUNTIME_EVENT_LOG", event_log, raising=False)
    closed_calls = []

    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(state="released"),
        load_snapshot_fn=lambda occurrence: snapshot,
        read_publish_list_fn=lambda: _publish_list(current_agents),
        read_remote_status_fn=lambda agent_id: {
            "ok": True, "platform_status": 1, "agent_version_id": "v1",
        },
        resolve_unknown_fn=lambda *args, **kwargs: closed_calls.append((args, kwargs)) or True,
        evidence_dir=tmp_path / "evidence",
        now=QUEUED_AT + dt.timedelta(hours=2),
        run_finished_fn=lambda occurrence, queued: True,
        resolve=True,
    )

    assert result["verified"] is False
    assert result["reason"] == "same_version_updated_after_queued_at"
    assert closed_calls == []
    assert not (tmp_path / "evidence").exists()


def test_occurrence_bound_cp3_rejects_multiple_submit_attempts(tmp_path, monkeypatch):
    snapshot = {
        "schema_version": 1, "owner_id": OWNER, "occurrence_id": OCCURRENCE, "ok": True,
        "agent_count": 1, "latest_versions": {"111": "v1"},
    }
    current_agents = [{
        "agent_id": "111",
        "updated_at": int((QUEUED_AT + dt.timedelta(minutes=10)).timestamp() * 1000),
        "latest_agent_version_id": "v1",
    }]
    evidence_root, publisher_log, event_log = _write_bound_cp3_run(tmp_path, cp3_attempts=2)
    monkeypatch.setattr(reconciler, "CAPAFY_DRAINER_EVIDENCE_ROOT", evidence_root, raising=False)
    monkeypatch.setattr(reconciler, "CAPAFY_DAILY_LOOP_LOG", publisher_log, raising=False)
    monkeypatch.setattr(reconciler, "RUNTIME_EVENT_LOG", event_log, raising=False)
    remote_calls = []
    closed_calls = []

    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(state="released"),
        load_snapshot_fn=lambda occurrence: snapshot,
        read_publish_list_fn=lambda: _publish_list(current_agents),
        read_remote_status_fn=lambda agent_id: remote_calls.append(agent_id) or {
            "ok": True, "platform_status": 1, "agent_version_id": "v1",
        },
        resolve_unknown_fn=lambda *args, **kwargs: closed_calls.append((args, kwargs)) or True,
        evidence_dir=tmp_path / "evidence",
        now=QUEUED_AT + dt.timedelta(hours=2),
        run_finished_fn=lambda occurrence, queued: True,
        resolve=True,
    )

    assert result["verified"] is False
    assert result["reason"] == "same_version_updated_after_queued_at"
    assert remote_calls == []
    assert closed_calls == []
    assert not (tmp_path / "evidence").exists()


def test_occurrence_bound_cp3_rejects_log_summary_time_mismatch(tmp_path):
    evidence_root, publisher_log, event_log = _write_bound_cp3_run(
        tmp_path,
        log_summary_overrides={
            "finished_at": (QUEUED_AT + dt.timedelta(minutes=5)).isoformat(),
        },
    )

    assert reconciler.read_occurrence_bound_cp3_receipt(
        OCCURRENCE,
        QUEUED_AT,
        QUEUED_AT + dt.timedelta(seconds=reconciler.MAX_RUN_SECONDS),
        evidence_root=evidence_root,
        publisher_log=publisher_log,
        event_log=event_log,
    ) is None


def test_occurrence_bound_cp3_rejects_log_summary_parent_run_mismatch(tmp_path):
    evidence_root, publisher_log, event_log = _write_bound_cp3_run(
        tmp_path, log_summary_overrides={"parent_lifecycle_run_id": "another-parent"},
    )

    assert reconciler.read_occurrence_bound_cp3_receipt(
        OCCURRENCE,
        QUEUED_AT,
        QUEUED_AT + dt.timedelta(seconds=reconciler.MAX_RUN_SECONDS),
        evidence_root=evidence_root,
        publisher_log=publisher_log,
        event_log=event_log,
    ) is None


def test_occurrence_bound_cp3_rejects_publisher_started_before_parent_window(tmp_path):
    evidence_root, publisher_log, event_log = _write_bound_cp3_run(
        tmp_path, publisher_start="2026-09-27 18:59:59",
    )

    assert reconciler.read_occurrence_bound_cp3_receipt(
        OCCURRENCE,
        QUEUED_AT,
        QUEUED_AT + dt.timedelta(seconds=reconciler.MAX_RUN_SECONDS),
        evidence_root=evidence_root,
        publisher_log=publisher_log,
        event_log=event_log,
    ) is None


def test_occurrence_bound_cp3_rejects_conflicting_final_verification_order(tmp_path):
    evidence_root, publisher_log, event_log = _write_bound_cp3_run(
        tmp_path,
        verifications_before_cp3=(
            "platform_status=1 skills=1 cfg=1 package_uploaded=1 audit=1 title=Test Agent",
        ),
        verifications_after_cp3=(
            "platform_status=0 skills=1 cfg=1 package_uploaded=1 audit=1 title=Test Agent",
        ),
    )

    assert reconciler.read_occurrence_bound_cp3_receipt(
        OCCURRENCE,
        QUEUED_AT,
        QUEUED_AT + dt.timedelta(seconds=reconciler.MAX_RUN_SECONDS),
        evidence_root=evidence_root,
        publisher_log=publisher_log,
        event_log=event_log,
    ) is None


def test_occurrence_bound_cp3_rejects_current_remote_version_mismatch(tmp_path, monkeypatch):
    snapshot = {
        "schema_version": 1, "owner_id": OWNER, "occurrence_id": OCCURRENCE, "ok": True,
        "agent_count": 1, "latest_versions": {"111": "v1"},
    }
    current_agents = [{
        "agent_id": "111",
        "updated_at": int((QUEUED_AT + dt.timedelta(minutes=10)).timestamp() * 1000),
        "latest_agent_version_id": "v1",
    }]
    evidence_root, publisher_log, event_log = _write_bound_cp3_run(tmp_path)
    monkeypatch.setattr(reconciler, "CAPAFY_DRAINER_EVIDENCE_ROOT", evidence_root, raising=False)
    monkeypatch.setattr(reconciler, "CAPAFY_DAILY_LOOP_LOG", publisher_log, raising=False)
    monkeypatch.setattr(reconciler, "RUNTIME_EVENT_LOG", event_log, raising=False)
    closed_calls = []

    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(state="released"),
        load_snapshot_fn=lambda occurrence: snapshot,
        read_publish_list_fn=lambda: _publish_list(current_agents),
        read_remote_status_fn=lambda agent_id: {
            "ok": True, "platform_status": 1, "agent_version_id": "v2",
        },
        resolve_unknown_fn=lambda *args, **kwargs: closed_calls.append((args, kwargs)) or True,
        evidence_dir=tmp_path / "evidence",
        now=QUEUED_AT + dt.timedelta(hours=2),
        run_finished_fn=lambda occurrence, queued: True,
        resolve=True,
    )

    assert result["verified"] is False
    assert result["reason"] == "occurrence_bound_remote_status_mismatch"
    assert closed_calls == []
    assert not (tmp_path / "evidence").exists()


def test_occurrence_bound_cp3_rejects_current_draft_status(tmp_path, monkeypatch):
    snapshot = {
        "schema_version": 1, "owner_id": OWNER, "occurrence_id": OCCURRENCE, "ok": True,
        "agent_count": 1, "latest_versions": {"111": "v1"},
    }
    current_agents = [{
        "agent_id": "111",
        "updated_at": int((QUEUED_AT + dt.timedelta(minutes=10)).timestamp() * 1000),
        "latest_agent_version_id": "v1",
    }]
    evidence_root, publisher_log, event_log = _write_bound_cp3_run(tmp_path)
    monkeypatch.setattr(reconciler, "CAPAFY_DRAINER_EVIDENCE_ROOT", evidence_root, raising=False)
    monkeypatch.setattr(reconciler, "CAPAFY_DAILY_LOOP_LOG", publisher_log, raising=False)
    monkeypatch.setattr(reconciler, "RUNTIME_EVENT_LOG", event_log, raising=False)
    closed_calls = []

    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(state="released"),
        load_snapshot_fn=lambda occurrence: snapshot,
        read_publish_list_fn=lambda: _publish_list(current_agents),
        read_remote_status_fn=lambda agent_id: {
            "ok": True, "platform_status": 0, "agent_version_id": "v1",
        },
        resolve_unknown_fn=lambda *args, **kwargs: closed_calls.append((args, kwargs)) or True,
        evidence_dir=tmp_path / "evidence",
        now=QUEUED_AT + dt.timedelta(hours=2),
        run_finished_fn=lambda occurrence, queued: True,
        resolve=True,
    )

    assert result["verified"] is False
    assert result["reason"] == "occurrence_bound_remote_status_mismatch"
    assert closed_calls == []
    assert not (tmp_path / "evidence").exists()


def test_same_version_without_verifiable_updated_at_stays_inconclusive(tmp_path):
    snapshot = {
        "schema_version": 1, "owner_id": OWNER, "occurrence_id": OCCURRENCE, "ok": True,
        "agent_count": 1, "latest_versions": {"111": "v1"},
    }
    for updated_at in (None, "not-an-iso-timestamp"):
        current_agents = [{
            "agent_id": "111", "updated_at": updated_at,
            "latest_agent_version_id": "v1",
        }]
        closed_calls = []
        evidence_dir = tmp_path / str(updated_at)
        result = reconciler.reconcile(
            OCCURRENCE,
            fenced_row_fn=_fenced_row_fn(),
            load_snapshot_fn=lambda occurrence: snapshot,
            read_publish_list_fn=lambda: _publish_list(current_agents),
            read_remote_status_fn=lambda agent_id: {"ok": False, "reason": "unused"},
            resolve_pre_effect_fn=lambda *args, **kwargs: closed_calls.append((args, kwargs)) or True,
            evidence_dir=evidence_dir,
            now=QUEUED_AT + dt.timedelta(hours=2),
            run_finished_fn=lambda occurrence, queued: True,
            resolve=True,
        )

        assert result["verified"] is False
        assert result["reason"] == "same_version_updated_at_missing_or_malformed"
        assert "closed" not in result
        assert closed_calls == []
        assert not evidence_dir.exists()


def test_out_of_range_numeric_updated_at_stays_inconclusive(tmp_path):
    snapshot = {
        "schema_version": 1, "owner_id": OWNER, "occurrence_id": OCCURRENCE, "ok": True,
        "agent_count": 1, "latest_versions": {"111": "v1"},
    }
    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(),
        load_snapshot_fn=lambda occurrence: snapshot,
        read_publish_list_fn=lambda: _publish_list([{
            "agent_id": "111", "updated_at": 10 ** 400, "latest_agent_version_id": "v1",
        }]),
        read_remote_status_fn=lambda agent_id: {"ok": False, "reason": "unused"},
        resolve_pre_effect_fn=lambda *args, **kwargs: True,
        evidence_dir=tmp_path / "evidence",
        now=QUEUED_AT + dt.timedelta(hours=2),
        run_finished_fn=lambda occurrence, queued: True,
        resolve=True,
    )

    assert result["verified"] is False
    assert result["reason"] == "same_version_updated_at_missing_or_malformed"
    assert "closed" not in result
    assert not (tmp_path / "evidence").exists()


def test_numeric_epoch_milliseconds_without_snapshot_prove_window_hit():
    updated_at = int((QUEUED_AT + dt.timedelta(minutes=5)).timestamp() * 1000)
    current_agents = [{
        "agent_id": "9563867391", "updated_at": updated_at,
        "latest_agent_version_id": "2104175282811195392",
    }]
    closed_calls = []

    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(),
        load_snapshot_fn=lambda occurrence: None,
        read_publish_list_fn=lambda: _publish_list(current_agents),
        read_remote_status_fn=lambda agent_id: {"ok": True, "platform_status": 1,
                                                 "agent_version_id": "2104175282811195392"},
        resolve_unknown_fn=lambda owner, occurrence, **kwargs: closed_calls.append(
            (owner, occurrence, kwargs)) or True,
        now=QUEUED_AT + dt.timedelta(minutes=10),
        resolve=True,
    )

    assert result["verified"] is True
    assert result["effected"] is True
    assert result["closed"] is True
    assert len(closed_calls) == 1


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


def test_same_version_update_without_bound_retry_evidence_stays_held(tmp_path):
    agent_id = "7393298474"
    version_id = "2110426515594047488"
    snapshot = {
        "schema_version": 1, "owner_id": OWNER, "occurrence_id": OCCURRENCE, "ok": True,
        "agent_count": 1, "latest_versions": {agent_id: version_id},
        "captured_at": (QUEUED_AT + dt.timedelta(seconds=2)).isoformat(),
    }
    updated_at = (QUEUED_AT + dt.timedelta(minutes=5)).isoformat()
    current_agents = [{
        "agent_id": agent_id, "updated_at": updated_at,
        "latest_agent_version_id": version_id,
    }]
    remote = {
        "ok": True, "agent_version_id": version_id, "platform_status": 0,
        "audit_status": 0, "is_confirmed_skills": True,
        "is_confirmed_config_keys": True, "package_uploaded": True,
        "agent_type": "run_online",
    }
    closed_calls = []

    def resolve_unknown(owner_id, occurrence_id, *, official_readback, expected_state):
        proof = official_readback()
        closed_calls.append((owner_id, occurrence_id, proof, expected_state))
        return True

    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(state="claimed"),
        load_snapshot_fn=lambda occurrence: snapshot,
        read_publish_list_fn=lambda: _publish_list(current_agents),
        read_remote_status_fn=lambda got_id: remote if got_id == agent_id else {"ok": False},
        resolve_unknown_fn=resolve_unknown,
        now=QUEUED_AT + dt.timedelta(minutes=10),
        run_finished_fn=lambda occurrence, queued: True,
        resolve=True,
    )

    assert result["verified"] is False
    assert result["reason"] == "same_version_updated_after_queued_at"
    assert closed_calls == []


@pytest.mark.parametrize("later_other_update", [False, True])
def test_occurrence_bound_partial_retry_upload_closes_as_effected(tmp_path, monkeypatch,
                                                                  later_other_update):
    agent_id = "7393298474"
    version_id = "2110426515594047488"
    snapshot = {
        "schema_version": 1, "owner_id": OWNER, "occurrence_id": OCCURRENCE, "ok": True,
        "agent_count": 1, "latest_versions": {agent_id: version_id},
        "captured_at": (QUEUED_AT + dt.timedelta(seconds=2)).isoformat(),
    }
    current_agents = [{
        "agent_id": agent_id,
        "updated_at": int((QUEUED_AT + dt.timedelta(seconds=15)).timestamp() * 1000),
        "latest_agent_version_id": version_id,
    }]
    if later_other_update:
        # Another Agent changed hours after this run ended (e.g. its review status);
        # it cannot undo the proven in-window effect on agent_id.
        snapshot["agent_count"] = 2
        snapshot["latest_versions"]["8354665033"] = "2110259929315954688"
        current_agents.append({
            "agent_id": "8354665033",
            "updated_at": int((QUEUED_AT + dt.timedelta(hours=8)).timestamp() * 1000),
            "latest_agent_version_id": "2110259929315954688",
        })
    remote = {
        "ok": True, "agent_version_id": version_id, "platform_status": 0,
        "audit_status": 0, "is_confirmed_skills": True,
        "is_confirmed_config_keys": True, "package_uploaded": True,
        "agent_type": "run_online",
    }
    evidence_root, publisher_log, event_log = _write_bound_partial_retry_run(tmp_path)
    monkeypatch.setattr(reconciler, "CAPAFY_DRAINER_EVIDENCE_ROOT", evidence_root)
    monkeypatch.setattr(reconciler, "CAPAFY_DAILY_LOOP_LOG", publisher_log)
    monkeypatch.setattr(reconciler, "RUNTIME_EVENT_LOG", event_log)
    closed_calls = []

    def resolve_unknown(owner_id, occurrence_id, *, official_readback, expected_state):
        proof = official_readback()
        closed_calls.append((owner_id, occurrence_id, proof, expected_state))
        return True

    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(state="claimed"),
        load_snapshot_fn=lambda occurrence: snapshot,
        read_publish_list_fn=lambda: _publish_list(current_agents),
        read_remote_status_fn=lambda got_id: remote if got_id == agent_id else {"ok": False},
        resolve_unknown_fn=resolve_unknown,
        evidence_dir=tmp_path / "reconciliation-evidence",
        now=QUEUED_AT + dt.timedelta(minutes=10),
        run_finished_fn=lambda occurrence, queued: True,
        resolve=True,
    )

    assert result["verified"] is True
    assert result["effected"] is True
    assert result["proof_kind"] == "occurrence_bound_capafy_partial_package_upload"
    assert result["provider_receipt_id"] == (
        f"capafy:agent/{agent_id}/version/{version_id}:platform_status=0:package_uploaded=1"
    )
    assert result["closed"] is True
    assert len(closed_calls) == 1
    assert closed_calls[0][3] == "claimed"
    assert closed_calls[0][2]["platform_status"] == 0


@pytest.mark.parametrize("later_other_update", [False, True])
@pytest.mark.parametrize("action", ["retry_existing", "resume_draft"])
@pytest.mark.parametrize("admission_wait_seconds", [0, 59])
@pytest.mark.parametrize("snapshot_agent_missing", [False, True])
def test_deterministic_retry_finish_receipt_closes_same_version_after_status_one(
    tmp_path, monkeypatch, snapshot_agent_missing, admission_wait_seconds, action,
    later_other_update,
):
    # A kickstarted occurrence can wait in the admission FIFO before it starts
    # (2026-10-15: queued 10:12:39Z, started 10:13:38Z).
    agent_id = "7393298474"
    version_id = "2110426515594047488"
    release_sha = "c" * 40
    parent_run_id = OCCURRENCE.split(":", 1)[1]
    checked_at = QUEUED_AT + dt.timedelta(seconds=25)
    snapshot_versions = {agent_id: version_id}
    if snapshot_agent_missing:
        snapshot_versions["5555555555"] = "other-version"
    snapshot = {
        "schema_version": 1, "owner_id": OWNER, "occurrence_id": OCCURRENCE, "ok": True,
        "captured_at": (QUEUED_AT + dt.timedelta(seconds=2)).isoformat(),
        "agent_count": len(snapshot_versions), "latest_versions": snapshot_versions,
    }
    current_agents = [{
        "agent_id": agent_id,
        "updated_at": int(checked_at.timestamp() * 1000),
        "latest_agent_version_id": version_id,
    }]
    if later_other_update:
        # Another Agent's review status changed hours after this run (2026-10-15 NHL).
        snapshot_versions["8354665033"] = "2110259929315954688"
        snapshot["agent_count"] = len(snapshot_versions)
        current_agents.append({
            "agent_id": "8354665033",
            "updated_at": int((QUEUED_AT + dt.timedelta(hours=8)).timestamp() * 1000),
            "latest_agent_version_id": "2110259929315954688",
        })
    resume = action == "resume_draft"
    action_key = f"{'resume' if resume else 'retry'}:{agent_id}"
    receipt = {
        "event": "capafy_resume_draft_finish" if resume else "capafy_retry_existing_finish",
        "owner_id": OWNER, "run_id": parent_run_id,
        "occurrence_id": OCCURRENCE, "release_sha": release_sha,
        "action_key": action_key, "agent_id": agent_id,
        "agent_version_id": version_id, "cp3_attempt": 1,
        "platform_status": 1, "is_confirmed_skills": True,
        "is_confirmed_config_keys": True, "package_uploaded": True,
        "provider_receipt_id": f"capafy:agent/{agent_id}/version/{version_id}:platform_status=1",
        "verified_at": checked_at.isoformat(),
    }
    stamp = (QUEUED_AT + dt.timedelta(seconds=5)).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    inventory = {
        "verdict": "PUBLISHABLE", "action": action,
        "action_key": action_key,
        "item": {"agent_id": agent_id, "title": "TikTok Comment Reply Script Pack"},
    }
    publisher_log = tmp_path / "daily_loop.log"
    publisher_log.write_text("\n".join((
        f"=== {stamp} daily_loop start ===",
        f"{stamp} inventory verdict=PUBLISHABLE :: {json.dumps(inventory, sort_keys=True)}",
        f"CAPAFY_RETRY_FINISH_RECEIPT={json.dumps(receipt, sort_keys=True)}",
        f"AGENT_ID={agent_id}",
        f"AGENT_VERSION_ID={version_id}",
        "CP3 submit attempt 1",
        "platform_status=1 skills=1 cfg=1 package_uploaded=1 audit=1 title=Test Agent",
        f"ledger appended {agent_id}",
        f"PUBLISHED + VERIFIED: agent_id={agent_id} (test) — status=1 under review.",
        (f"=== {stamp} daily_loop done rc=0 (RESUMED — {agent_id} finished CP2/CP3 deterministically; no LLM spend) ==="
         if resume else
         f"=== {stamp} daily_loop done rc=0 (SUBMITTED — {agent_id} finished CP2/CP3 after prepare) ==="),
        "",
    )), encoding="utf-8")
    publisher_log.chmod(0o600)
    events = [
        {
            "owner_id": OWNER, "job_id": OWNER, "run_id": parent_run_id,
            "occurrence_id": OCCURRENCE, "release_sha": release_sha,
            "phase": "execute", "status": "running", "effect_class": "publish",
            "effect_status": "started", "timestamp": (QUEUED_AT + dt.timedelta(seconds=1)).isoformat(),
        },
        {
            "owner_id": OWNER, "job_id": OWNER, "run_id": parent_run_id,
            "occurrence_id": OCCURRENCE, "release_sha": release_sha,
            "phase": "report", "status": "pass", "effect_class": "publish",
            "effect_status": "unknown", "exit_code": 0, "timestamp": checked_at.isoformat(),
        },
    ]
    event_log = tmp_path / "events.jsonl"
    event_log.write_text("".join(json.dumps(row) + "\n" for row in events), encoding="utf-8")
    event_log.chmod(0o600)
    monkeypatch.setattr(reconciler, "CAPAFY_DAILY_LOOP_LOG", publisher_log)
    monkeypatch.setattr(reconciler, "RUNTIME_EVENT_LOG", event_log)
    monkeypatch.setattr(reconciler, "CAPAFY_DRAINER_EVIDENCE_ROOT", tmp_path / "no-child-runs")
    remote = {
        "ok": True, "agent_version_id": version_id, "platform_status": 1,
        "audit_status": 0, "is_confirmed_skills": True,
        "is_confirmed_config_keys": True, "package_uploaded": True,
        "agent_type": "run_online",
    }
    closed_calls = []

    def resolve_unknown(owner_id, occurrence_id, *, official_readback, expected_state):
        proof = official_readback()
        closed_calls.append((owner_id, occurrence_id, proof, expected_state))
        return True

    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(
            state="claimed",
            queued_at=QUEUED_AT - dt.timedelta(seconds=admission_wait_seconds)),
        load_snapshot_fn=lambda occurrence: snapshot,
        read_publish_list_fn=lambda: _publish_list(current_agents),
        read_remote_status_fn=lambda got_id: remote if got_id == agent_id else {"ok": False},
        resolve_unknown_fn=resolve_unknown,
        evidence_dir=tmp_path / "reconciliation-evidence",
        now=QUEUED_AT + dt.timedelta(minutes=10),
        run_finished_fn=lambda occurrence, queued: True,
        resolve=True,
    )

    if snapshot_agent_missing:
        assert result["verified"] is False
        assert result["reason"] == "same_version_updated_after_queued_at"
        assert closed_calls == []
        assert not (tmp_path / "reconciliation-evidence").exists()
        return

    assert result["verified"] is True
    assert result["effected"] is True
    assert result["proof_kind"] == "occurrence_bound_capafy_deterministic_retry_finish"
    assert result["provider_receipt_id"] == (
        f"capafy:agent/{agent_id}/version/{version_id}:platform_status=1"
    )
    assert result["closed"] is True
    assert len(closed_calls) == 1
    assert closed_calls[0][3] == "claimed"


@pytest.mark.parametrize(
    "mismatch",
    ["child_occurrence", "remote_version", "snapshot_occurrence", "snapshot_agent_missing"],
)
def test_partial_receipt_rejects_mismatched_child_snapshot_or_remote_version(tmp_path, monkeypatch, mismatch):
    agent_id = "7393298474"
    version_id = "2110426515594047488"
    snapshot_versions = {agent_id: version_id}
    if mismatch == "snapshot_agent_missing":
        snapshot_versions["5555555555"] = "other-version"
    snapshot = {
        "schema_version": 1, "owner_id": OWNER,
        "occurrence_id": f"{OWNER}:different-run" if mismatch == "snapshot_occurrence" else OCCURRENCE,
        "ok": True,
        "agent_count": len(snapshot_versions), "latest_versions": snapshot_versions,
        "captured_at": (QUEUED_AT + dt.timedelta(seconds=2)).isoformat(),
    }
    current_agents = [{
        "agent_id": agent_id,
        "updated_at": int((QUEUED_AT + dt.timedelta(seconds=15)).timestamp() * 1000),
        "latest_agent_version_id": version_id,
    }]
    child_parent_occurrence = f"{OWNER}:different-run" if mismatch == "child_occurrence" else OCCURRENCE
    evidence_root, publisher_log, event_log = _write_bound_partial_retry_run(
        tmp_path, child_parent_occurrence=child_parent_occurrence,
    )
    monkeypatch.setattr(reconciler, "CAPAFY_DRAINER_EVIDENCE_ROOT", evidence_root)
    monkeypatch.setattr(reconciler, "CAPAFY_DAILY_LOOP_LOG", publisher_log)
    monkeypatch.setattr(reconciler, "RUNTIME_EVENT_LOG", event_log)
    remote_version = "different-version" if mismatch == "remote_version" else version_id
    remote = {
        "ok": True, "agent_version_id": remote_version, "platform_status": 0,
        "audit_status": 0, "is_confirmed_skills": True,
        "is_confirmed_config_keys": True, "package_uploaded": True,
        "agent_type": "run_online",
    }
    closed_calls = []
    remote_calls = []

    result = reconciler.reconcile(
        OCCURRENCE,
        fenced_row_fn=_fenced_row_fn(state="claimed"),
        load_snapshot_fn=lambda occurrence: snapshot,
        read_publish_list_fn=lambda: _publish_list(current_agents),
        read_remote_status_fn=lambda got_id: remote_calls.append(got_id) or
            (remote if got_id == agent_id else {"ok": False}),
        resolve_unknown_fn=lambda *args, **kwargs: closed_calls.append(args) or True,
        now=QUEUED_AT + dt.timedelta(minutes=10),
        run_finished_fn=lambda occurrence, queued: True,
        resolve=True,
    )

    assert result["verified"] is False
    assert "closed" not in result
    assert closed_calls == []
    assert remote_calls == ([agent_id] if mismatch == "remote_version" else [])


def test_remote_status_preserves_confirmation_and_upload_fields(tmp_path):
    publisher = tmp_path / "publisher"
    publisher.mkdir()
    (publisher / "packager.py").write_text(
        "import json\n"
        "print(json.dumps({'latest_version': {"
        "'agent_version_id': 'v1', 'platform_status': 0, 'audit_status': 0, "
        "'is_confirmed_skills': True, 'is_confirmed_config_keys': True, "
        "'package_uploaded': True, 'agent_type': 'run_online'}}))\n",
        encoding="utf-8",
    )

    result = reconciler.read_remote_status("7393298474", publisher_dir=publisher)

    assert result == {
        "ok": True, "platform_status": 0, "agent_version_id": "v1",
        "audit_status": 0, "is_confirmed_skills": True,
        "is_confirmed_config_keys": True, "package_uploaded": True,
        "agent_type": "run_online",
    }


# --- in-place update by the loop's own agent pass (resume of an existing draft) ---------------

RUN_START = QUEUED_AT + dt.timedelta(minutes=6)
RUN_END = RUN_START + dt.timedelta(minutes=9)


def _ms(moment):
    return int(moment.timestamp() * 1000)


def _agent_pass_case(updates, *, remote=None, window=(RUN_START, RUN_END)):
    snapshot = {
        "schema_version": 1, "owner_id": OWNER, "occurrence_id": OCCURRENCE, "ok": True,
        "captured_at": RUN_START.isoformat(), "agent_count": 3,
        "latest_versions": {"111": "v1", "222": "v2", "333": "v3"},
    }
    agents = [
        {"agent_id": "111", "latest_agent_version_id": "v1",
         "updated_at": _ms(QUEUED_AT - dt.timedelta(days=2))},
        {"agent_id": "222", "latest_agent_version_id": "v2",
         "updated_at": _ms(QUEUED_AT - dt.timedelta(days=3))},
        {"agent_id": "333", "latest_agent_version_id": "v3",
         "updated_at": _ms(QUEUED_AT - dt.timedelta(days=4))},
    ]
    for agent_id, moment in updates.items():
        next(row for row in agents if row["agent_id"] == agent_id)["updated_at"] = _ms(moment)
    closed = []
    result_kwargs = dict(
        fenced_row_fn=_fenced_row_fn(),
        load_snapshot_fn=lambda occurrence: snapshot,
        read_publish_list_fn=lambda: _publish_list(agents),
        read_remote_status_fn=lambda agent_id: remote if remote is not None else {
            "ok": True, "agent_version_id": {"111": "v1", "222": "v2", "333": "v3"}[agent_id],
            "platform_status": 0, "agent_type": "run_online"},
        resolve_unknown_fn=lambda owner, occurrence, **kwargs: closed.append((owner, occurrence)) or True,
        run_window_fn=lambda occurrence, snap: window,
        now=QUEUED_AT + dt.timedelta(hours=2),
        run_finished_fn=lambda occurrence, queued: True,
        resolve=True,
    )
    return result_kwargs, closed


def test_agent_pass_in_place_update_inside_run_window_closes_with_receipt(tmp_path):
    kwargs, closed = _agent_pass_case({"222": RUN_START + dt.timedelta(minutes=8, seconds=30)})

    result = reconciler.reconcile(OCCURRENCE, evidence_dir=tmp_path / "evidence", **kwargs)

    assert result["verified"] is True and result["effected"] is True
    assert result["proof_kind"] == "occurrence_bound_capafy_agent_pass_in_place_update"
    assert result["provider_receipt_id"].startswith("capafy:agent/222/version/v2:platform_status=0")
    assert result["closed"] is True and closed == [(OWNER, OCCURRENCE)]


def test_agent_pass_update_after_run_end_stays_inconclusive(tmp_path):
    kwargs, closed = _agent_pass_case({"222": RUN_END + dt.timedelta(minutes=7)})

    result = reconciler.reconcile(OCCURRENCE, evidence_dir=tmp_path / "evidence", **kwargs)

    assert result["verified"] is False
    assert result["reason"] == "same_version_updated_after_queued_at"
    assert closed == []


def test_agent_pass_two_updated_agents_stays_inconclusive(tmp_path):
    inside = RUN_START + dt.timedelta(minutes=3)
    kwargs, closed = _agent_pass_case({"222": inside, "333": inside + dt.timedelta(minutes=1)})

    result = reconciler.reconcile(OCCURRENCE, evidence_dir=tmp_path / "evidence", **kwargs)

    assert result["verified"] is False
    assert closed == []


def test_agent_pass_without_run_window_stays_inconclusive(tmp_path):
    kwargs, closed = _agent_pass_case({"222": RUN_START + dt.timedelta(minutes=3)}, window=None)

    result = reconciler.reconcile(OCCURRENCE, evidence_dir=tmp_path / "evidence", **kwargs)

    assert result["verified"] is False
    assert result["reason"] == "same_version_updated_after_queued_at"
    assert closed == []


def test_agent_pass_remote_version_mismatch_stays_fenced(tmp_path):
    kwargs, closed = _agent_pass_case(
        {"222": RUN_START + dt.timedelta(minutes=3)},
        remote={"ok": True, "agent_version_id": "other", "platform_status": 0, "agent_type": "run_online"},
    )

    result = reconciler.reconcile(OCCURRENCE, evidence_dir=tmp_path / "evidence", **kwargs)

    assert result["verified"] is False
    assert result["reason"] == "agent_pass_remote_status_mismatch"
    assert closed == []


def _terminal_ledger(tmp_path, rows):
    path = tmp_path / "terminals.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path


def test_run_window_comes_from_the_wrappers_own_terminal_ledger(tmp_path):
    execution = RUN_START.strftime("%Y%m%dT%H%M%SZ") + "-53565"
    ledger = _terminal_ledger(tmp_path, [
        {"execution_id": execution, "phase": "started",
         "observed_at": (RUN_START + dt.timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        {"execution_id": execution, "phase": "terminal",
         "observed_at": RUN_END.strftime("%Y-%m-%dT%H:%M:%SZ"), "rc": 1},
    ])
    snapshot = {"ok": True, "captured_at": (RUN_START + dt.timedelta(seconds=1)).isoformat()}

    window = reconciler.read_occurrence_bound_run_window(OCCURRENCE, snapshot, ledger_path=ledger)

    assert window == (RUN_START + dt.timedelta(seconds=1), RUN_END)


def test_run_window_is_none_without_a_terminal_record(tmp_path):
    execution = RUN_START.strftime("%Y%m%dT%H%M%SZ") + "-53565"
    ledger = _terminal_ledger(tmp_path, [
        {"execution_id": execution, "phase": "started",
         "observed_at": RUN_START.strftime("%Y-%m-%dT%H:%M:%SZ")},
    ])
    snapshot = {"ok": True, "captured_at": RUN_START.isoformat()}

    assert reconciler.read_occurrence_bound_run_window(OCCURRENCE, snapshot, ledger_path=ledger) is None


def test_run_window_is_none_when_two_executions_start_together(tmp_path):
    rows = []
    for pid in ("111", "222"):
        execution = RUN_START.strftime("%Y%m%dT%H%M%SZ") + "-" + pid
        rows += [{"execution_id": execution, "phase": "started",
                  "observed_at": RUN_START.strftime("%Y-%m-%dT%H:%M:%SZ")},
                 {"execution_id": execution, "phase": "terminal",
                  "observed_at": RUN_END.strftime("%Y-%m-%dT%H:%M:%SZ"), "rc": 0}]
    ledger = _terminal_ledger(tmp_path, rows)
    snapshot = {"ok": True, "captured_at": RUN_START.isoformat()}

    assert reconciler.read_occurrence_bound_run_window(OCCURRENCE, snapshot, ledger_path=ledger) is None
