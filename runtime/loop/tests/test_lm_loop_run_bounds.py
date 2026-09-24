import json
import hashlib
import os
import shutil
import signal
import plistlib
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import call, patch

from runtime.host import resource_admission as admission
from runtime.loop.lm_loop_run import (
    EFFECT_RESULT_HINT_ENTRYPOINTS,
    PRE_EFFECT_HINT_ENTRYPOINTS,
    _apply_verified_effect_result,
    _admission_class, _dispatch_reserved, _host_admission_deferred, _queue_priority,
    _enqueue_recovery_intent, _persist_effect_identity, _resource_class,
    _run_admitted, _run_entrypoint, _runtime_limit, _sqlite_database_busy,
    _should_enqueue_recovery_intent, _terminal_outcome, _verified_effect_result,
    build_loop_command,
    main as lm_loop_run_main,
)
from runtime.loop.runtime_event import build_runtime_event


_PROTOCOL_PATCHER = None


def setup_module():
    global _PROTOCOL_PATCHER
    _PROTOCOL_PATCHER = patch(
        "runtime.loop.lm_loop_run.durable_protocol_version", return_value=2,
    )
    _PROTOCOL_PATCHER.start()


def teardown_module():
    _PROTOCOL_PATCHER.stop()


def test_scheduled_wakes_have_a_finite_one_hour_safety_limit():
    assert _runtime_limit({"cadence": {"start_interval_seconds": 300}}) == 3600
    assert _runtime_limit({"cadence": {"calendar_interval": {"Minute": 5}}}) == 3600
    assert _runtime_limit({"cadence": {"run_at_load": True}}) == 3600


def test_javascript_entrypoint_uses_pinned_runtime_node(tmp_path):
    executable = tmp_path / "worker.mjs"
    executable.write_text("#!/usr/bin/env node\n")
    executable.chmod(0o755)
    node = tmp_path / "node"
    node.write_text("#!/bin/sh\nexit 0\n")
    node.chmod(0o755)
    registry = {"schema_version": 2, "loops": {"example": {
        "label": "ai.anicca.example", "domain": "system",
        "entrypoint": "worker.mjs", "cadence": {"start_interval_seconds": 60},
        "effect_class": "none", "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic", "adapter": "exec", "command": [],
    }}}

    with patch.dict(os.environ, {"LIFE_MANAGER_RUNTIME_NODE": str(node)}):
        assert build_loop_command(registry, "example", tmp_path) == [
            str(node), str(executable),
        ]


def test_crowdworks_paid_owner_declares_a_bounded_runtime():
    registry = json.loads(
        (Path(__file__).resolve().parents[3] / "config/loop-registry.json").read_text()
    )

    assert registry["loops"]["crowdworks-revenue-paid"]["runtime_timeout_seconds"] == 900


def test_scheduled_wake_can_declare_a_longer_finite_safety_limit():
    assert _runtime_limit({
        "cadence": {"start_interval_seconds": 600},
        "runtime_timeout_seconds": 10800,
    }) == 10800


def test_continuous_owner_has_no_scheduled_wake_deadline():
    assert _runtime_limit({"cadence": {"keep_alive": True}}) is None


def test_resource_class_is_explicit_or_provider_default():
    assert _resource_class({"provider_route": "shared-agent-runner"}) == "agent"
    assert _resource_class({"provider_route": "deterministic"}) == "deterministic"
    assert _resource_class({"provider_route": "deterministic", "resource_class": "agent"}) == "agent"


def test_revenue_admission_requires_an_explicit_registry_contract():
    assert _admission_class({"domain": "earn"}) == "borrow"
    assert _admission_class({
        "domain": "earn", "admission_class": "revenue",
    }) == "revenue"


def test_explicit_registry_priority_is_forwarded_to_durable_admission(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 60},
        "provider_route": "deterministic",
        "admission_class": "revenue",
        "priority": "critical_paid",
    }
    receipt = tmp_path / "receipt"
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "capacity_busy")) as enqueue,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(["/bin/true"], entry, "paid", {}, receipt) == 75

    assert _queue_priority(entry) == "critical_paid"
    enqueue.assert_called_once_with(
        "deterministic", "paid", admission_class="revenue",
        priority="critical_paid",
    )
    run.assert_not_called()


def test_mobile_publish_entrypoint_uses_occurrence_scoped_admission(tmp_path):
    entry = {
        "cadence": {"calendar_interval": [{"Hour": 8, "Minute": 0}]},
        "provider_route": "deterministic",
        "resource_class": "agent",
        "admission_class": "revenue",
        "priority": "revenue",
        "effect_class": "publish",
        "entrypoint": "apps/life-manager/scripts/mobile-app",
    }
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")) as enqueue,
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(None, "effect_unknown")) as claim,
          patch("runtime.loop.lm_loop_run.reserve_available_resource", return_value=[]),
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(
            ["/bin/true"], entry, "life-manager-honne-ja", {},
            tmp_path / "mobile-receipt", occurrence_id="life-manager-honne-ja:new",
        ) == 75

    enqueue.assert_called_once_with(
        "agent", "life-manager-honne-ja", admission_class="revenue",
        priority="revenue", occurrence_id="life-manager-honne-ja:new",
        effect_scope="occurrence",
    )
    claim.assert_called_once_with(
        "agent", "life-manager-honne-ja", admission_class="revenue",
        effect_scope="occurrence",
    )
    run.assert_not_called()


def test_explicit_marketplace_occurrence_scope_is_forwarded_to_admission(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 300},
        "provider_route": "deterministic",
        "resource_class": "agent",
        "admission_class": "revenue",
        "priority": "critical_paid",
        "effect_class": "money",
        "entrypoint": "skills/earn/crowdworks/scripts/paid-owner",
        "admission_effect_scope": "occurrence",
    }
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")) as enqueue,
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(None, "effect_unknown")) as claim,
          patch("runtime.loop.lm_loop_run.reserve_available_resource", return_value=[]),
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(
            ["/bin/true"], entry, "crowdworks-revenue-paid", {},
            tmp_path / "paid-receipt", occurrence_id="crowdworks-revenue-paid:new",
        ) == 75

    enqueue.assert_called_once_with(
        "agent", "crowdworks-revenue-paid", admission_class="revenue",
        priority="critical_paid", occurrence_id="crowdworks-revenue-paid:new",
        effect_scope="occurrence",
    )
    claim.assert_called_once_with(
        "agent", "crowdworks-revenue-paid", admission_class="revenue",
        effect_scope="occurrence",
    )
    run.assert_not_called()


def test_non_mobile_publish_entrypoint_keeps_owner_scoped_admission(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 60},
        "provider_route": "deterministic",
        "admission_class": "revenue",
        "effect_class": "publish",
        "entrypoint": "skills/earn/article/scripts/article-daily.sh",
    }
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(None, "effect_unknown")) as enqueue,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(
            ["/bin/true"], entry, "article-daily", {},
            tmp_path / "article-receipt", occurrence_id="article-daily:new",
        ) == 75

    enqueue.assert_called_once_with(
        "deterministic", "article-daily", admission_class="revenue",
        occurrence_id="article-daily:new",
    )
    run.assert_not_called()


def test_transient_admission_lock_contention_is_retried_before_deferring(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 60},
        "provider_route": "deterministic",
        "admission_class": "revenue",
        "priority": "critical_paid",
    }
    claim = tmp_path / "claim"
    claim.write_text("owned")
    enqueue_results = [
        (None, "control_busy"),
        (None, "control_busy"),
        (tmp_path / "ticket", "ready"),
    ]

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                side_effect=enqueue_results) as enqueue,
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]),
          patch("runtime.loop.lm_loop_run._run_entrypoint", return_value=0),
          patch("runtime.loop.lm_loop_run.time.sleep") as sleep):
        assert _run_admitted(
            ["/bin/true"], entry, "crowdworks-revenue-paid", {},
            tmp_path / "receipt",
        ) == 0

    assert enqueue.call_count == 3
    assert sleep.call_count == 2


def test_transient_sqlite_lock_before_claim_recovers_in_same_wake(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 300},
        "provider_route": "deterministic",
        "resource_class": "browser",
        "effect_class": "none",
    }
    claim = tmp_path / "claim"
    claim.write_text(json.dumps({
        "occurrence_id": "browser-probe:wake-recover",
    }))
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource", side_effect=[
              sqlite3.OperationalError("database is locked"),
              sqlite3.OperationalError("database is locked"),
              (tmp_path / "ticket", "ready"),
          ]) as enqueue,
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]),
          patch("runtime.loop.lm_loop_run._run_entrypoint", return_value=0) as run,
          patch("runtime.loop.lm_loop_run.time.sleep") as sleep):
        assert _run_admitted(
            ["/bin/true"], entry, "browser-probe", {}, tmp_path / "receipt",
            occurrence_id="browser-probe:wake-recover",
        ) == 0

    assert enqueue.call_count == 3
    assert sleep.call_count == 2
    run.assert_called_once()


def test_sqlite_busy_classification_prefers_primary_error_code():
    for primary in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        error = sqlite3.OperationalError("not a lock message")
        error.sqlite_errorcode = primary | (7 << 8)
        assert _sqlite_database_busy(error)

    non_busy = sqlite3.OperationalError("database is locked")
    non_busy.sqlite_errorcode = sqlite3.SQLITE_IOERR
    assert not _sqlite_database_busy(non_busy)


def test_persistent_sqlite_lock_before_claim_records_typed_deferred_admission(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 300},
        "provider_route": "deterministic",
        "resource_class": "browser",
        "effect_class": "none",
    }
    receipt = tmp_path / "host-admission.json"
    started_ns = time.time_ns()
    with (patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                side_effect=sqlite3.OperationalError("database is locked")) as enqueue,
          patch("runtime.loop.lm_loop_run.time.sleep") as sleep,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(["/bin/true"], entry, "browser-probe", {}, receipt,
                             occurrence_id="browser-probe:wake-1") == 75

    assert json.loads(receipt.read_text()) == {
        "status": "deferred", "effect": 0,
        "reason": "resource_database_busy",
    }
    assert _terminal_outcome(
        75, host_deferred=_host_admission_deferred(receipt, started_ns),
    ) == (False, True, "host_admission_deferred:resource_database_busy")
    assert enqueue.call_count == 8
    assert sleep.call_count == 7
    run.assert_not_called()


def test_persistent_sqlite_lock_during_claim_records_typed_deferred_admission(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 300},
        "provider_route": "deterministic",
        "resource_class": "browser",
        "effect_class": "none",
    }
    receipt = tmp_path / "host-admission.json"
    with (patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                side_effect=sqlite3.OperationalError("database is locked")) as claim,
          patch("runtime.loop.lm_loop_run.time.sleep") as sleep,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(["/bin/true"], entry, "browser-probe", {}, receipt,
                             occurrence_id="browser-probe:wake-2") == 75

    assert json.loads(receipt.read_text()) == {
        "status": "deferred", "effect": 0,
        "reason": "resource_database_busy",
    }
    assert claim.call_count == 8
    assert sleep.call_count == 7
    run.assert_not_called()


def test_non_busy_sqlite_failure_is_not_retried_or_misclassified(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 300},
        "provider_route": "deterministic",
        "resource_class": "browser",
        "effect_class": "none",
    }
    receipt = tmp_path / "host-admission.json"
    with (patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                side_effect=sqlite3.OperationalError("disk I/O error")) as enqueue,
          patch("runtime.loop.lm_loop_run.time.sleep") as sleep,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(
            ["/bin/true"], entry, "browser-probe", {}, receipt,
            occurrence_id="browser-probe:wake-io-error",
        ) == 75

    assert json.loads(receipt.read_text())["reason"] == "resource_admission_unavailable"
    enqueue.assert_called_once()
    sleep.assert_not_called()
    run.assert_not_called()


def test_nonlock_claim_io_failure_is_not_retried_or_started(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 300},
        "provider_route": "deterministic",
        "resource_class": "browser",
        "effect_class": "none",
    }
    receipt = tmp_path / "host-admission.json"
    with (patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                side_effect=OSError("claim cleanup I/O failed")) as claim,
          patch("runtime.loop.lm_loop_run.time.sleep") as sleep,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(
            ["/bin/true"], entry, "browser-probe", {}, receipt,
            occurrence_id="browser-probe:wake-cleanup-io",
        ) == 75

    assert json.loads(receipt.read_text())["reason"] == "resource_admission_unavailable"
    claim.assert_called_once()
    sleep.assert_not_called()
    run.assert_not_called()


def test_sqlite_lock_during_best_effort_reservation_keeps_terminal_path(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 300},
        "provider_route": "deterministic",
        "resource_class": "browser",
        "effect_class": "none",
    }
    receipt = tmp_path / "host-admission.json"
    with (patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(None, "capacity_busy")),
          patch("runtime.loop.lm_loop_run.reserve_available_resource",
                side_effect=sqlite3.OperationalError("database is locked")),
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(["/bin/true"], entry, "browser-probe", {}, receipt,
                             occurrence_id="browser-probe:wake-3") == 75

    assert json.loads(receipt.read_text()) == {
        "status": "deferred", "effect": 0,
        "reason": "resource_capacity_busy",
    }
    run.assert_not_called()


def test_wake_occurrence_identity_is_forwarded_to_durable_admission(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 60},
        "provider_route": "deterministic",
        "admission_class": "revenue",
        "priority": "revenue",
    }
    receipt = tmp_path / "receipt"
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "capacity_busy")) as enqueue,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(
            ["/bin/true"], entry, "connector", {}, receipt,
            occurrence_id="connector:1800000000-1",
        ) == 75

    enqueue.assert_called_once_with(
        "deterministic", "connector", admission_class="revenue",
        priority="revenue", occurrence_id="connector:1800000000-1",
    )
    run.assert_not_called()


def test_old_reservation_only_marker_does_not_advertise_queued_coalescing(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 1800},
        "provider_route": "deterministic", "resource_class": "browser",
        "admission_class": "revenue", "coalesce_reserved_wakes": True,
    }
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "capacity_busy")) as enqueue,
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(None, "capacity_busy")) as claim,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(
            ["/bin/true"], entry, "life-manager-connector-native", {},
            tmp_path / "receipt", occurrence_id="connector:new",
        ) == 75
    enqueue.assert_called_once_with(
        "browser", "life-manager-connector-native", admission_class="revenue",
        occurrence_id="connector:new",
    )
    claim.assert_called_once_with(
        "browser", "life-manager-connector-native", admission_class="revenue",
    )
    run.assert_not_called()


def test_connector_registry_opt_in_coalesces_queued_scan(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 1800},
        "provider_route": "deterministic",
        "resource_class": "browser",
        "admission_class": "revenue",
        "coalesce_reserved_wakes": True,
        "coalesce_queued_wakes": True,
    }
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "capacity_busy")) as enqueue,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(
            ["/bin/true"], entry, "life-manager-connector-native", {},
            tmp_path / "receipt", occurrence_id="connector:new",
        ) == 75
    enqueue.assert_called_once_with(
        "browser", "life-manager-connector-native", admission_class="revenue",
        occurrence_id="connector:new", coalesce_reserved=True,
    )
    run.assert_not_called()


def test_running_child_receives_periodic_claim_heartbeat(tmp_path, monkeypatch):
    entry = {
        "cadence": {"start_interval_seconds": 60},
        "provider_route": "deterministic",
        "admission_class": "revenue",
        "priority": "revenue",
    }
    receipt = tmp_path / "receipt"
    claim = tmp_path / "claim"
    claim.write_text(json.dumps({"occurrence_id": "heartbeat-owner:run-1"}))
    heartbeat_seen = threading.Event()
    calls = []

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        assert heartbeat_seen.wait(timeout=1)
        return 0

    def heartbeat(_claim):
        calls.append("heartbeat")
        heartbeat_seen.set()
        return True

    monkeypatch.setattr("runtime.loop.lm_loop_run.HEARTBEAT_INTERVAL_SECONDS", 0.01)
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.heartbeat_durable_resource",
                side_effect=heartbeat),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                side_effect=lambda *_args, **_kwargs: calls.append("release") or []),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(
            ["/bin/true"], entry, "heartbeat-owner", {}, receipt,
            occurrence_id="heartbeat-owner:run-1",
        ) == 0

    assert calls[0] == "heartbeat"
    assert calls[-1] == "release"


def test_release_waits_for_inflight_heartbeat_before_closing_claim(tmp_path, monkeypatch):
    entry = {
        "cadence": {"start_interval_seconds": 60},
        "provider_route": "deterministic",
        "admission_class": "revenue",
        "priority": "revenue",
    }
    receipt = tmp_path / "receipt"
    claim = tmp_path / "claim"
    claim.write_text(json.dumps({"occurrence_id": "heartbeat-owner:run-2"}))
    heartbeat_started = threading.Event()
    heartbeat_finished = threading.Event()

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        assert heartbeat_started.wait(timeout=1)
        return 0

    def heartbeat(_claim):
        heartbeat_started.set()
        time.sleep(1.2)
        heartbeat_finished.set()
        return False

    def release(*_args, **_kwargs):
        assert heartbeat_finished.is_set()
        return []

    monkeypatch.setattr("runtime.loop.lm_loop_run.HEARTBEAT_INTERVAL_SECONDS", 0.01)
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.heartbeat_durable_resource",
                side_effect=heartbeat),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                side_effect=release),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(
            ["/bin/true"], entry, "heartbeat-owner", {}, receipt,
            occurrence_id="heartbeat-owner:run-2",
        ) == 0


def test_memory_admission_exit_is_deferred_not_failed():
    assert _terminal_outcome(75, host_deferred="resource_capacity_busy") == (
        False, True, "host_admission_deferred:resource_capacity_busy")
    assert _terminal_outcome(124, host_deferred="memory_headroom_low") == (
        False, True, "host_admission_deferred:memory_headroom_low")
    assert _terminal_outcome(75) == (False, False, "entrypoint_exit_75")
    assert _terminal_outcome(1) == (False, False, "entrypoint_exit_1")


def test_memory_deferral_requires_a_fresh_matching_receipt(tmp_path):
    receipt = tmp_path / "memory.json"
    started = time.time_ns()
    receipt.write_text(json.dumps({
        "status": "deferred", "effect": 0, "reason": "capacity_busy",
    }))
    assert _host_admission_deferred(receipt, started) == "capacity_busy"
    receipt.write_text(json.dumps({
        "status": "deferred", "effect": 0, "reason": "x" * 128,
    }))
    assert _host_admission_deferred(receipt, started) == "unknown"
    receipt.write_text(json.dumps({"status": "pass", "effect": 0}))
    assert not _host_admission_deferred(receipt, started)


def test_entrypoint_timeout_terminates_its_process_group():
    started = time.monotonic()
    result = _run_entrypoint(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        timeout_seconds=0.05,
        termination_grace_seconds=0.05,
    )

    assert result == 124
    assert time.monotonic() - started < 2


def test_entrypoint_completes_handoff_before_effect_gate(tmp_path):
    handoff = tmp_path / "handoff"
    child = (
        "import pathlib,sys; "
        f"sys.exit(0 if pathlib.Path({str(handoff)!r}).is_file() else 1)"
    )

    result = _run_entrypoint(
        [sys.executable, "-c", child], timeout_seconds=5,
        on_started=lambda pid: handoff.write_text(str(pid)),
    )

    assert result == 0


def test_acquired_slot_keeps_the_full_entrypoint_runtime_budget(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner", "runtime_timeout_seconds": 123}
    claim = tmp_path / "claim"
    claim.write_text("owned")

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        return 0

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=["next"]) as release,
          patch("runtime.loop.lm_loop_run.transfer_durable_resource") as transfer,
          patch("runtime.loop.lm_loop_run._dispatch_reserved") as dispatch,
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child) as run):
        assert _run_admitted(["/bin/true"], entry, "example", {}, tmp_path / "receipt") == 0
    assert run.call_args.kwargs["timeout_seconds"] == 123
    transfer.assert_called_once_with(claim, 4242)
    release.assert_called_once_with(claim, requeue=False, reserve=True)
    dispatch.assert_called_once_with(["next"])


def test_control_plane_safety_loops_bypass_data_plane_admission(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "deterministic", "runtime_timeout_seconds": 900}
    for loop_id in ("life-manager-release-reconciler", "life-manager-recovery-supervisor",
                    "life-manager-disk-cleanup", "capafy-loop-healthcheck"):
        receipt = tmp_path / f"receipt-{loop_id}"
        with (patch("runtime.loop.lm_loop_run.memory_free_percent") as memory,
              patch("runtime.loop.lm_loop_run.durable_protocol_version",
                    return_value=1) as protocol,
              patch("runtime.loop.lm_loop_run.try_acquire_resource") as acquire,
              patch("runtime.loop.lm_loop_run._run_entrypoint", return_value=0) as run):
            assert _run_admitted(
                ["/bin/true"], entry, loop_id, {}, receipt,
            ) == 0

        memory.assert_not_called()
        if loop_id == "capafy-loop-healthcheck":
            protocol.assert_not_called()
        else:
            protocol.assert_called_once_with()
        acquire.assert_not_called()
        run.assert_called_once_with(["/bin/true"], env={}, timeout_seconds=900)
        assert json.loads(receipt.read_text()) == {
            "effect": 0,
            "reason": "control_plane_exempt",
            "status": "pass",
        }


def test_control_plane_no_effect_owner_clears_stale_fence(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 300},
             "provider_route": "deterministic", "effect_class": "none",
             "runtime_timeout_seconds": 900}
    with (patch("runtime.loop.lm_loop_run.clear_no_effect_unknown_resource",
                return_value=1) as clear,
          patch("runtime.loop.lm_loop_run._run_entrypoint", return_value=0)):
        assert _run_admitted(
            ["/bin/true"], entry, "capafy-loop-healthcheck", {},
            tmp_path / "receipt",
        ) == 0
    clear.assert_called_once_with("capafy-loop-healthcheck")


def test_successful_safety_wake_dispatches_waiting_owner_without_taking_a_slot(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 300},
             "provider_route": "deterministic"}
    with (patch("runtime.loop.lm_loop_run.durable_protocol_version", return_value=2),
          patch("runtime.loop.lm_loop_run.try_acquire_resource") as acquire,
          patch("runtime.loop.lm_loop_run.reserve_available_resource",
                return_value=["waiting-owner"]) as reserve,
          patch("runtime.loop.lm_loop_run._dispatch_reserved") as dispatch,
          patch("runtime.loop.lm_loop_run._run_entrypoint", return_value=0)):
        assert _run_admitted(["/bin/true"], entry, "life-manager-disk-cleanup",
                             {}, tmp_path / "receipt") == 0
    acquire.assert_not_called()
    reserve.assert_called_once_with()
    dispatch.assert_called_once_with(["waiting-owner"])


def test_v1_protocol_uses_legacy_nonretaining_admission(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}
    claim = tmp_path / "claim"
    claim.write_text("owned")

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        return 0

    with (patch("runtime.loop.lm_loop_run.durable_protocol_version", return_value=1),
          patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.try_acquire_resource",
                return_value=(claim, "acquired")) as acquire,
          patch("runtime.loop.lm_loop_run.release_resource") as release,
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource") as enqueue,
          patch("runtime.loop.lm_loop_run.transfer_durable_resource") as transfer,
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(
            ["/bin/true"], entry, "example", {}, tmp_path / "receipt",
        ) == 0

    acquire.assert_called_once_with(
        "agent", "example", admission_class="borrow",
        retain_ticket=False, required_protocol=1,
    )
    enqueue.assert_not_called()
    transfer.assert_called_once_with(claim, 4242)
    release.assert_called_once_with(claim)


def test_started_child_timeout_and_signal_mark_effect_unknown_before_release(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "deterministic", "resource_class": "browser",
             "admission_class": "revenue"}
    for exit_code in (124, 143):
        claim = tmp_path / f"claim-{exit_code}"
        claim.write_text("owned")

        def run_child(*_args, **kwargs):
            kwargs["on_started"](4242)
            return exit_code

        with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
              patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                    return_value=(tmp_path / "ticket", "ready")),
              patch("runtime.loop.lm_loop_run.claim_durable_resource",
                    return_value=(claim, "acquired")),
              patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
              patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                    return_value=[]) as release,
              patch("runtime.loop.lm_loop_run._dispatch_reserved"),
              patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
            assert _run_admitted(["/bin/true"], entry, "connector", {},
                                 tmp_path / f"receipt-{exit_code}") == exit_code
        release.assert_called_once_with(
            claim, requeue=False, reserve=True, effect_unknown=True)


def test_none_effect_child_failure_requeues_without_effect_unknown(tmp_path):
    """A control/report loop has no external effect to fence after a failed child."""
    claim = tmp_path / "claim-none-effect"
    claim.write_text("owned")

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        return 1

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]) as release,
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 60},
            "provider_route": "deterministic", "resource_class": "agent",
            "admission_class": "borrow", "effect_class": "none",
        }, "marketing-owner-events", {}, tmp_path / "receipt") == 1
    release.assert_called_once_with(claim, requeue=False, reserve=True)


def test_proven_pre_effect_failure_releases_owner_for_next_wake(tmp_path):
    claim = tmp_path / "claim"
    claim.write_text("owned")

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        hint = Path(kwargs["env"]["LIFE_MANAGER_RESULT_HINT_PATH"])
        hint.write_text('{"status":"pre_effect_failure","effect":0}\n')
        hint.chmod(0o600)
        return 1

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]) as release,
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 60},
            "provider_route": "deterministic", "resource_class": "agent",
            "admission_class": "revenue",
            "entrypoint": "skills/earn/crowdworks/scripts/paid-owner",
        }, "paid", {}, tmp_path / "receipt") == 1
    release.assert_called_once_with(claim, requeue=False, reserve=True)


def test_writer_article_resume_pre_effect_failure_releases_without_unknown_fence(tmp_path):
    claim = tmp_path / "claim-writer-resume"
    claim.write_text("owned")

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        hint = Path(kwargs["env"]["LIFE_MANAGER_RESULT_HINT_PATH"])
        hint.write_text('{"status":"pre_effect_failure","effect":0}\n')
        hint.chmod(0o600)
        return 1

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]) as release,
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 300},
            "provider_route": "shared-agent-runner", "resource_class": "agent",
            "admission_class": "borrow",
            "entrypoint": "skills/writer-agent/scripts/article-resume-pending.sh",
        }, "article-resume", {}, tmp_path / "receipt") == 1
    release.assert_called_once_with(claim, requeue=False, reserve=True)


def test_mercor_application_and_reply_pre_effect_hints_are_allowlisted():
    assert "skills/earn/mercor/scripts/application-owner" in PRE_EFFECT_HINT_ENTRYPOINTS
    assert "skills/earn/mercor/scripts/reply-owner" in PRE_EFFECT_HINT_ENTRYPOINTS


def test_lancers_application_pre_effect_hint_is_allowlisted():
    assert "skills/earn/lancers/scripts/application-owner" in PRE_EFFECT_HINT_ENTRYPOINTS


def test_lancers_storefront_pre_effect_hint_is_allowlisted():
    assert "skills/earn/lancers/scripts/storefront-owner" in PRE_EFFECT_HINT_ENTRYPOINTS


def test_affiliate_loop_pre_effect_hint_is_allowlisted():
    assert "skills/affiliate/affiliate" in PRE_EFFECT_HINT_ENTRYPOINTS


def test_generic_child_hint_cannot_clear_unknown_effect(tmp_path):
    claim = tmp_path / "claim"
    claim.write_text("owned")

    def run_child(*_args, **kwargs):
        kwargs["on_started"](4242)
        assert "LIFE_MANAGER_RESULT_HINT_PATH" not in kwargs["env"]
        hint = tmp_path / "entrypoint-result.json"
        hint.write_text('{"status":"pre_effect_failure","effect":0}\n')
        hint.chmod(0o600)
        return 1

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]) as release,
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 60},
            "provider_route": "deterministic", "resource_class": "browser",
            "admission_class": "revenue", "entrypoint": "skills/connector/run.sh",
        }, "connector", {}, tmp_path / "receipt") == 1
    release.assert_called_once_with(
        claim, requeue=False, reserve=True, effect_unknown=True)


def test_mobile_child_receives_effect_result_hint_path(tmp_path):
    claim = tmp_path / "claim"
    claim.write_text(json.dumps({
        "occurrence_id": "life-manager-honne-ja:run-1",
    }))
    observed = {}

    def run_child(*_args, **kwargs):
        observed.update(kwargs["env"])
        kwargs["on_started"](4242)
        return 0

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource", return_value=[]),
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 60},
            "provider_route": "postiz", "resource_class": "agent",
            "admission_class": "revenue", "effect_class": "publish",
            "entrypoint": "apps/life-manager/scripts/mobile-app",
        }, "life-manager-honne-ja", {}, tmp_path / "host-admission.json",
            occurrence_id="life-manager-honne-ja:run-1") == 0

    assert EFFECT_RESULT_HINT_ENTRYPOINTS == frozenset({
        "apps/life-manager/scripts/mobile-app",
    })
    assert observed["LIFE_MANAGER_RESULT_HINT_PATH"] == str(
        tmp_path / "entrypoint-result.json")


def _write_effect_result(path, **overrides):
    value = {
        "schema_version": 1,
        "kind": "life_manager_effect_result",
        "status": "verified_effect",
        "effect": 1,
        "owner_id": "life-manager-honne-ja",
        "occurrence_id": "life-manager-honne-ja:run-1",
        "provider": "postiz",
        "provider_receipt_id": "postiz-post-1",
        "effect_status": "reconciled",
    }
    value.update(overrides)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return value


def test_verified_mobile_effect_result_requires_exact_private_identity(tmp_path):
    hint = tmp_path / "entrypoint-result.json"
    _write_effect_result(hint)

    assert _verified_effect_result(
        hint, "life-manager-honne-ja", "life-manager-honne-ja:run-1",
    ) == ("reconciled", "postiz://posts/postiz-post-1")

    _write_effect_result(hint, occurrence_id="life-manager-honne-ja:other")
    assert _verified_effect_result(
        hint, "life-manager-honne-ja", "life-manager-honne-ja:run-1",
    ) is None
    _write_effect_result(hint)
    hint.chmod(0o644)
    assert _verified_effect_result(
        hint, "life-manager-honne-ja", "life-manager-honne-ja:run-1",
    ) is None


def test_verified_mobile_effect_result_rejects_symlink_and_unknown_fields(tmp_path):
    outside = tmp_path / "outside.json"
    _write_effect_result(outside)
    symlink = tmp_path / "entrypoint-result.json"
    symlink.symlink_to(outside)
    assert _verified_effect_result(
        symlink, "life-manager-honne-ja", "life-manager-honne-ja:run-1",
    ) is None

    malformed = tmp_path / "malformed.json"
    _write_effect_result(malformed, unexpected=True)
    assert _verified_effect_result(
        malformed, "life-manager-honne-ja", "life-manager-honne-ja:run-1",
    ) is None


def test_verified_mobile_effect_result_upgrades_only_success_event(tmp_path):
    event = build_runtime_event(
        loop_id="life-manager-honne-ja", domain="growth", run_id="run-1",
        release_sha="a" * 40, provider="postiz", profile_alias=None,
        effect_class="publish", succeeded=True, blocker=None,
        claimed_occurrence_id="life-manager-honne-ja:run-1",
    )
    upgraded = _apply_verified_effect_result(
        event, ("verified", "postiz://posts/postiz-post-1"),
    )
    assert upgraded["effect_status"] == "verified"
    assert upgraded["evidence_refs"][-1] == "postiz://posts/postiz-post-1"

    failed = {**event, "status": "fail", "blocker": "entrypoint_exit_1"}
    assert _apply_verified_effect_result(
        failed, ("verified", "postiz://posts/postiz-post-1"),
    )["effect_status"] == "unknown"


def test_main_projects_exact_mobile_result_into_terminal_event(tmp_path):
    release = tmp_path / "release"
    (release / "config").mkdir(parents=True)
    (release / "apps/life-manager/config").mkdir(parents=True)
    (release / "config/loop-registry.json").write_text(json.dumps({
        "loops": {"life-manager-honne-ja": {
            "label": "ai.anicca.life-manager-honne-ja",
            "domain": "growth",
            "entrypoint": "apps/life-manager/scripts/mobile-app",
            "provider_route": "postiz",
            "effect_class": "publish",
            "state_root": str(tmp_path / "unused-state"),
        }},
    }), encoding="utf-8")
    (release / "RELEASE.json").write_text(json.dumps({
        "sha": "a" * 40,
    }), encoding="utf-8")
    (release / "apps/life-manager/config/product-loop-catalog.json").write_text(json.dumps({
        "loops": [{"id": "mobile-apps", "job_ids": ["life-manager-honne-ja"]}],
    }), encoding="utf-8")
    events = []

    def run_admitted(_command, _entry, loop_id, _env, receipt, *,
                     occurrence_id, on_claimed):
        on_claimed(occurrence_id)
        receipt.write_text('{"status":"pass","effect":0}\n', encoding="utf-8")
        receipt.chmod(0o600)
        _write_effect_result(
            receipt.parent / "entrypoint-result.json",
            owner_id=loop_id,
            occurrence_id=occurrence_id,
            effect_status="verified",
        )
        return 0

    with (patch.dict(os.environ, {
              "LIFE_MANAGER_STATE_ROOT": str(tmp_path / "state"),
              "LIFE_MANAGER_RUN_ID": "run-1",
              "WAKE_ID": "wake-1",
          }, clear=False),
          patch("runtime.loop.lm_loop_run._apply_lock", return_value=nullcontext()),
          patch("runtime.loop.lm_loop_run.build_loop_command", return_value=["/bin/true"]),
          patch("runtime.loop.lm_loop_run._run_admitted", side_effect=run_admitted),
          patch("runtime.loop.lm_loop_run.append_runtime_event",
                side_effect=lambda _path, event: events.append(event)),
          patch("runtime.loop.lm_loop_run._enqueue_recovery_intent") as enqueue):
        assert lm_loop_run_main(["life-manager-honne-ja", str(release)]) == 0

    assert events[-1]["status"] == "pass"
    assert events[-1]["effect_status"] == "verified"
    assert events[-1]["evidence_refs"][-1] == "postiz://posts/postiz-post-1"
    assert events[-1]["product_loop_id"] == "mobile-apps"
    assert events[-1]["job_id"] == "life-manager-honne-ja"
    assert events[-1]["owner_id"] == "life-manager-honne-ja"
    assert events[-1]["wake_id"] == "wake-1"
    assert events[-1]["occurrence_id"] == "life-manager-honne-ja:run-1"
    assert events[-1]["exit_code"] == 0
    assert events[-1]["failure_layer"] == "clean"
    assert events[-1]["error_class"] is None
    assert events[-1]["retryable"] is False
    assert events[-1]["next_action"] == "none"
    assert events[-1]["provider_receipt_id"] == "postiz-post-1"
    assert events[-1]["official_readback_ref"] == "postiz://posts/postiz-post-1"
    assert len(events[-1]["loaded_argv_sha256"]) == 64
    assert len(events[-1]["loaded_env_sha256"]) == 64
    enqueue.assert_not_called()


def test_shared_runner_failure_emits_one_exact_recovery_intent(tmp_path):
    release = tmp_path / "release"
    (release / "config").mkdir(parents=True)
    (release / "config/loop-registry.json").write_text(json.dumps({
        "loops": {"example": {
            "label": "ai.anicca.example", "domain": "system",
            "entrypoint": "bin/example", "provider_route": "deterministic",
            "effect_class": "none", "state_root": str(tmp_path / "unused-state"),
        }},
    }), encoding="utf-8")
    (release / "RELEASE.json").write_text(json.dumps({"sha": "a" * 40}), encoding="utf-8")
    events = []

    def fail(_command, _entry, _loop_id, _env, receipt, **_kwargs):
        receipt.write_text('{"status":"pass","effect":0}\n', encoding="utf-8")
        receipt.chmod(0o600)
        return 1

    with (patch.dict(os.environ, {
              "LIFE_MANAGER_STATE_ROOT": str(tmp_path / "state"),
              "LIFE_MANAGER_RUN_ID": "run-1",
          }, clear=False),
          patch("runtime.loop.lm_loop_run._apply_lock", return_value=nullcontext()),
          patch("runtime.loop.lm_loop_run.build_loop_command", return_value=["/bin/false"]),
          patch("runtime.loop.lm_loop_run._run_admitted", side_effect=fail),
          patch("runtime.loop.lm_loop_run.append_runtime_event",
                side_effect=lambda _path, event: events.append(event)),
          patch("runtime.loop.lm_loop_run._enqueue_recovery_intent", return_value=True) as enqueue):
        assert lm_loop_run_main(["example", str(release)]) == 1

    enqueue.assert_called_once()
    queued_event = enqueue.call_args.args[1]
    assert queued_event["status"] == "fail"
    assert queued_event["owner_id"] == "example"
    assert queued_event["occurrence_id"] == "example:run-1"
    assert queued_event["release_sha"] == "a" * 40


def test_recovery_enqueue_is_replay_zero_and_fences_unknown_effect(tmp_path):
    queue = tmp_path / "recovery" / "intents.jsonl"
    event = build_runtime_event(
        loop_id="affiliate-loop", domain="growth", run_id="run-1",
        release_sha="a" * 40, provider="deterministic", profile_alias=None,
        effect_class="publish", succeeded=False, blocker="entrypoint_exit_1",
        exit_code=1,
    )
    with patch.dict(os.environ, {
        "LIFE_MANAGER_RECOVERY_INTENTS_PATH": str(queue),
        "LIFE_MANAGER_RUNTIME_NODE": shutil.which("node"),
        "PATH": "/usr/bin:/bin",
    }):
        assert _enqueue_recovery_intent(Path(__file__).resolve().parents[3], event, tmp_path)
        assert _enqueue_recovery_intent(Path(__file__).resolve().parents[3], event, tmp_path)
    rows = [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["record_type"] == "recovery_intent"
    assert rows[0]["occurrence_id"] == "affiliate-loop:run-1"
    assert rows[0]["action"] == "hold_effect_unknown"
    assert rows[0]["retryable"] is False
    assert rows[0]["mutates_external_effect"] is False


def test_recovery_enqueue_skips_success_admission_and_paid_owned_jobs():
    failed = build_runtime_event(
        loop_id="example", domain="system", run_id="run-1", release_sha="a" * 40,
        provider="deterministic", profile_alias=None, effect_class="none",
        succeeded=False, blocker="entrypoint_exit_1", exit_code=1,
    )
    admitted = build_runtime_event(
        loop_id="example", domain="system", run_id="run-2", release_sha="a" * 40,
        provider="deterministic", profile_alias=None, effect_class="none",
        succeeded=False, deferred=True, blocker="host_admission_deferred:resource_capacity_busy",
        exit_code=75,
    )
    succeeded = build_runtime_event(
        loop_id="example", domain="system", run_id="run-3", release_sha="a" * 40,
        provider="deterministic", profile_alias=None, effect_class="none",
        succeeded=True, blocker=None, exit_code=0,
    )
    assert _should_enqueue_recovery_intent({"priority": "support"}, failed)
    assert not _should_enqueue_recovery_intent({"priority": "support"}, admitted)
    assert not _should_enqueue_recovery_intent({"priority": "support"}, succeeded)
    assert not _should_enqueue_recovery_intent({
        "priority": "critical_paid", "entrypoint": "skills/earn/gig/scripts/paid-direct-owner",
    }, failed)
    assert not _should_enqueue_recovery_intent({
        "priority": "support", "entrypoint": "runtime/loop/recovery-supervisor-cli.mjs",
    }, failed)


def test_admitted_child_receives_exact_host_occurrence_identity(tmp_path):
    claim = tmp_path / "claim"
    claim.write_text(json.dumps({"occurrence_id": "connector:run-123"}))
    observed = {}

    def run_child(*_args, **kwargs):
        observed.update(kwargs["env"])
        kwargs["on_started"](4242)
        return 0

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")) as claim_admission,
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource", return_value=[]),
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 60},
            "provider_route": "deterministic", "resource_class": "browser",
            "admission_class": "revenue", "coalesce_queued_wakes": True,
        }, "connector", {}, tmp_path / "receipt",
            occurrence_id="connector:run-123") == 0
    claim_admission.assert_called_once_with(
        "browser", "connector", admission_class="revenue",
        coalesced_occurrence_id="connector:run-123")
    assert observed["LIFE_MANAGER_OCCURRENCE_ID"] == "connector:run-123"


def test_unknown_effect_identity_moves_from_scratch_to_private_state(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    sidecar = scratch / "effect-identity.jsonl"
    sidecar.write_text(json.dumps({
        "schema_version": 1,
        "kind": "life_manager_effect_identity",
        "runtime_run_id": "run-1",
        "occurrence_id": "life-manager-honne-ja:run-1",
        "loop_id": "life-manager-honne-ja",
        "job_id": "job-1",
        "effect_key": "marketing:video:honne-ai:tiktok:creative:" + "a" * 64 + ":" + "b" * 64,
        "product_id": "honne-ai",
        "format_id": "reelclaw",
        "form": "relationship-confession",
        "locale": "ja",
        "platform": "tiktok",
        "creative_id": "creative",
        "slot": "2026-07-30T12:30:00.000Z",
        "integration_ref": "integration://postiz/tiktok/honne-ai-ja",
        "account_id": "@honnevideo",
        "video_sha256": "a" * 64,
        "caption_sha256": "b" * 64,
    }) + "\n", encoding="utf-8")
    sidecar.chmod(0o600)
    state_root = tmp_path / "state"

    ref = _persist_effect_identity(
        sidecar, state_root, "life-manager-honne-ja", "run-1",
        "life-manager-honne-ja:run-1",
    )

    assert ref == "lm-effect://life-manager-honne-ja/run-1/identity.jsonl"
    persisted = state_root / "effect-identities" / "run-1.jsonl"
    assert json.loads(persisted.read_text(encoding="utf-8"))["job_id"] == "job-1"
    assert persisted.stat().st_mode & 0o777 == 0o600


def test_unknown_effect_identity_rejects_symlink_and_malformed_sidecars(tmp_path):
    state_root = tmp_path / "state"
    outside = tmp_path / "outside.jsonl"
    outside.write_text('{"job_id":"outside"}\n', encoding="utf-8")
    outside.chmod(0o600)
    symlink = tmp_path / "symlink.jsonl"
    symlink.symlink_to(outside)
    assert _persist_effect_identity(
        symlink, state_root, "life-manager-honne-ja", "run-1",
        "life-manager-honne-ja:run-1",
    ) is None
    assert not (state_root / "effect-identities" / "run-1.jsonl").exists()

    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text('{"job_id":"missing-schema"}\n', encoding="utf-8")
    malformed.chmod(0o600)
    assert _persist_effect_identity(
        malformed, state_root, "life-manager-honne-ja", "run-2",
        "life-manager-honne-ja:run-2",
    ) is None


def test_unknown_effect_identity_rejects_cross_field_mismatch_and_destination_symlink(tmp_path):
    def row(**overrides):
        value = {
            "schema_version": 1,
            "kind": "life_manager_effect_identity",
            "runtime_run_id": "run-3",
            "occurrence_id": "life-manager-honne-ja:run-3",
            "loop_id": "life-manager-honne-ja",
            "job_id": "marketing-video-publication:job-3",
            "effect_key": "marketing:video:honne-ai:tiktok:creative:" + "a" * 64 + ":" + "b" * 64,
            "product_id": "honne-ai",
            "format_id": "reelclaw",
            "form": "relationship-confession",
            "locale": "ja",
            "platform": "tiktok",
            "creative_id": "creative",
            "slot": "2026-07-30T12:30:00.000Z",
            "integration_ref": "integration://postiz/tiktok/honne-ai-ja",
            "account_id": "@honnevideo",
            "video_sha256": "a" * 64,
            "caption_sha256": "b" * 64,
        }
        value.update(overrides)
        return value

    state_root = tmp_path / "state"
    mismatch = tmp_path / "mismatch.jsonl"
    mismatch.write_text(json.dumps(row(video_sha256="c" * 64)) + "\n", encoding="utf-8")
    mismatch.chmod(0o600)
    assert _persist_effect_identity(
        mismatch, state_root, "life-manager-honne-ja", "run-3",
        "life-manager-honne-ja:run-3",
    ) is None

    mismatch.write_text(json.dumps(row(integration_ref="integration://postiz/instagram/honne-ai-ja")) + "\n", encoding="utf-8")
    mismatch.chmod(0o600)
    assert _persist_effect_identity(
        mismatch, state_root, "life-manager-honne-ja", "run-3",
        "life-manager-honne-ja:run-3",
    ) is None

    state_root.mkdir()
    destination = state_root / "effect-identities"
    outside = tmp_path / "outside-identities"
    outside.mkdir()
    destination.symlink_to(outside, target_is_directory=True)
    valid = tmp_path / "valid.jsonl"
    valid.write_text(json.dumps(row()) + "\n", encoding="utf-8")
    valid.chmod(0o600)
    assert _persist_effect_identity(
        valid, state_root, "life-manager-honne-ja", "run-3",
        "life-manager-honne-ja:run-3",
    ) is None
    assert not (outside / "run-3.jsonl").exists()

    media = [f"{chr(97 + i)}" * 64 for i in range(6)]
    media_order = hashlib.sha256(
        json.dumps(media, ensure_ascii=False, separators=(",", ":")).encode(),
    ).hexdigest()
    carousel = row(
        product_id="anicca-ios",
        platform="instagram",
        effect_key="marketing:carousel:anicca-ios:creative:" + "d" * 64 + ":" + media_order + ":" + "e" * 64,
        integration_ref="integration://postiz/instagram/anicca-carousel",
        account_id="@anicca.carousel",
        video_sha256=None,
        caption_sha256="e" * 64,
        pack_sha256="d" * 64,
        media_sha256=media,
        media_order_sha256=media_order,
    )
    carousel_path = tmp_path / "carousel.jsonl"
    carousel_path.write_text(json.dumps(carousel) + "\n", encoding="utf-8")
    carousel_path.chmod(0o600)
    assert _persist_effect_identity(
        carousel_path, tmp_path / "carousel-state", "life-manager-honne-ja", "run-3",
        "life-manager-honne-ja:run-3",
    ) == "lm-effect://life-manager-honne-ja/run-3/identity.jsonl"
    carousel["product_id"] = "anicca-ios"
    carousel["effect_key"] = "marketing:carousel:anicca-ios:creative:" + "d" * 64 + ":" + media_order + ":" + "e" * 64
    carousel["media_sha256"] = None
    carousel_path.write_text(json.dumps(carousel) + "\n", encoding="utf-8")
    carousel_path.chmod(0o600)
    assert _persist_effect_identity(
        carousel_path, tmp_path / "carousel-state", "life-manager-honne-ja", "run-3",
        "life-manager-honne-ja:run-3",
    ) is None


def test_noncoalesced_child_uses_claimed_older_occurrence(tmp_path):
    claim = tmp_path / "claim"
    claim.write_text(json.dumps({"occurrence_id": "example:older"}))
    observed = {}
    claimed = []

    def run_child(*_args, **kwargs):
        observed.update(kwargs["env"])
        kwargs["on_started"](4242)
        return 0

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.transfer_durable_resource"),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource", return_value=[]),
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint", side_effect=run_child)):
        assert _run_admitted(["/bin/true"], {
            "cadence": {"start_interval_seconds": 60},
            "provider_route": "deterministic", "resource_class": "agent",
            "admission_class": "revenue",
        }, "example", {}, tmp_path / "receipt", occurrence_id="example:new",
            on_claimed=claimed.append) == 0
    assert observed["LIFE_MANAGER_OCCURRENCE_ID"] == "example:older"
    assert claimed == ["example:older"]


def test_v1_protocol_coexists_with_live_legacy_owner_without_sqlite(tmp_path, monkeypatch):
    root = tmp_path / "admission"
    monkeypatch.setenv("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", str(root))
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_FINITE_RUNS", "1")
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_AGENT_RUNS", "1")
    legacy, reason = admission.try_acquire(
        "agent", "legacy", retain_ticket=False,
    )
    assert legacy is not None and reason == "acquired"
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}
    receipt = tmp_path / "receipt"
    try:
        with (patch("runtime.loop.lm_loop_run.durable_protocol_version", return_value=1),
              patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
              patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
            assert _run_admitted(
                ["/bin/true"], entry, "candidate", {}, receipt,
            ) == 75
        run.assert_not_called()
        assert json.loads(receipt.read_text())["reason"] == "resource_capacity_busy"
        assert not (root / "admission-v2.sqlite3").exists()
    finally:
        admission.release(legacy)


def test_busy_resource_admission_defers_without_waiting_or_starting_child(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}
    receipt = tmp_path / "receipt"
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "capacity_busy")) as enqueue,
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(None, "capacity_busy")) as acquire,
          patch("runtime.loop.lm_loop_run.reserve_available_resource",
                return_value=[]) as reserve,
          patch("runtime.loop.lm_loop_run._dispatch_reserved") as dispatch,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        started = time.monotonic()
        assert _run_admitted(["/bin/true"], entry, "example", {}, receipt) == 75
    assert time.monotonic() - started < 0.5
    enqueue.assert_called_once_with("agent", "example", admission_class="borrow")
    acquire.assert_called_once_with("agent", "example", admission_class="borrow")
    reserve.assert_called_once_with(); dispatch.assert_called_once_with([])
    run.assert_not_called()
    assert json.loads(receipt.read_text()) == {
        "effect": 0,
        "reason": "resource_capacity_busy",
        "status": "deferred",
    }


def test_all_coconala_lanes_enter_revenue_admission(tmp_path):
    registry = json.loads(
        (Path(__file__).parents[3] / "config/loop-registry.json").read_text()
    )["loops"]
    loop_ids = (
        "hf-gig-apply-direct",
        "hf-gig-reply-detector",
        "hf-gig-paid-direct",
        "hf-gig-storefront-direct",
    )
    assert all(registry[loop_id].get("admission_class") == "revenue"
               for loop_id in loop_ids)
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "capacity_busy")) as enqueue,
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(None, "capacity_busy")) as claim,
          patch("runtime.loop.lm_loop_run.reserve_available_resource", return_value=[]),
          patch("runtime.loop.lm_loop_run._dispatch_reserved"),
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        for loop_id in loop_ids:
            assert _run_admitted(
                ["/bin/true"], registry[loop_id], loop_id, {},
                tmp_path / f"{loop_id}.json",
            ) == 75

    expected_enqueue = []
    for loop_id in loop_ids:
        kwargs = {
            "admission_class": "revenue",
            "priority": registry[loop_id]["priority"],
        }
        if registry[loop_id].get("effect_class") == "none":
            kwargs["allow_no_effect_recovery"] = True
        if registry[loop_id].get("coalesce_queued_wakes") is True:
            kwargs["coalesce_reserved"] = True
        expected_enqueue.append(call("agent", loop_id, **kwargs))
    assert enqueue.call_args_list == expected_enqueue
    assert claim.call_args_list == [
        call("agent", loop_id, admission_class="revenue") for loop_id in loop_ids
    ]
    run.assert_not_called()


def test_lancers_effect_lanes_enter_revenue_admission():
    registry = json.loads(
        (Path(__file__).parents[3] / "config/loop-registry.json").read_text()
    )["loops"]
    loop_ids = (
        "lancers-revenue-application",
        "lancers-revenue-negotiate",
        "lancers-revenue-paid",
        "lancers-revenue-storefront",
    )
    assert all(registry[loop_id].get("admission_class") == "revenue"
               for loop_id in loop_ids)


def test_all_marketplace_revenue_lanes_use_agent_revenue_admission():
    registry = json.loads(
        (Path(__file__).parents[3] / "config/loop-registry.json").read_text()
    )["loops"]
    loop_ids = (
        "crowdworks-revenue-application",
        "crowdworks-revenue-reply",
        "crowdworks-revenue-paid",
        "lancers-revenue-application",
        "lancers-revenue-negotiate",
        "lancers-revenue-paid",
        "lancers-revenue-storefront",
        "mercor-revenue-application",
        "mercor-revenue-reply",
        "mercor-revenue-paid",
    )
    assert all(registry[loop_id].get("resource_class") == "agent"
               for loop_id in loop_ids)
    assert all(registry[loop_id].get("admission_class") == "revenue"
               for loop_id in loop_ids)


def test_unavailable_admission_becomes_deferred_receipt(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}
    receipt = tmp_path / "receipt"
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                side_effect=RuntimeError),
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(["/bin/true"], entry, "example", {}, receipt) == 75
    run.assert_not_called()
    assert json.loads(receipt.read_text())["reason"] == "resource_admission_unavailable"


def test_invalid_memory_threshold_fails_closed(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}
    for value in ("0", "-1", "101"):
        with (patch.dict(os.environ, {"LIFE_MANAGER_MIN_MEMORY_FREE_PERCENT": value}),
              patch("runtime.loop.lm_loop_run.enqueue_durable_resource") as acquire,
              patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
            assert _run_admitted(["/bin/true"], entry, "example", {}, tmp_path / value) == 64
        acquire.assert_not_called(); run.assert_not_called()


def test_entrypoint_blocks_signal_until_handler_owns_child(monkeypatch):
    class Process:
        pid = 43210
        def poll(self): return None
        def wait(self, timeout=None): return 0

    def launch(*_args, **_kwargs):
        os.kill(os.getpid(), signal.SIGTERM)
        return Process()

    monkeypatch.setattr("runtime.loop.lm_loop_run.subprocess.Popen", launch)
    with patch("runtime.loop.lm_loop_run.os.killpg") as killpg:
        assert _run_entrypoint(["/bin/true"], timeout_seconds=1) == 75
    killpg.assert_called_once_with(43210, signal.SIGTERM)


def test_cancelled_before_atomic_handoff_never_starts_child():
    with patch("runtime.loop.lm_loop_run.subprocess.Popen") as launch:
        assert _run_entrypoint(["/bin/true"], cancelled=lambda: True) == 75
    launch.assert_not_called()


def test_signal_during_claim_retry_stops_before_effect_child(tmp_path):
    entry = {
        "cadence": {"start_interval_seconds": 60},
        "provider_route": "deterministic",
        "effect_class": "publish",
    }

    def interrupt_claim(*_args, **_kwargs):
        os.kill(os.getpid(), signal.SIGTERM)
        return None, "control_busy"

    receipt = tmp_path / "receipt"
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                side_effect=interrupt_claim) as claim,
          patch("runtime.loop.lm_loop_run.time.sleep") as sleep,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(["/bin/true"], entry, "example", {}, receipt) == 75

    assert json.loads(receipt.read_text())["reason"] == "resource_admission_interrupted"
    claim.assert_called_once()
    sleep.assert_not_called()
    run.assert_not_called()


def test_signal_after_pass_receipt_cannot_start_effect_child(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}
    claim = tmp_path / "claim"
    original_write = __import__("runtime.loop.lm_loop_run", fromlist=["_atomic_json"])._atomic_json

    def write_then_stop(path, value):
        original_write(path, value)
        if value.get("reason") == "resource_slot_acquired":
            os.kill(os.getpid(), signal.SIGTERM)

    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]),
          patch("runtime.loop.lm_loop_run._atomic_json", side_effect=write_then_stop),
          patch("runtime.loop.lm_loop_run.subprocess.Popen") as launch):
        assert _run_admitted(["/bin/true"], entry, "example", {}, tmp_path / "receipt") == 75
    launch.assert_not_called()


def test_signal_during_memory_probe_defers_before_child(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}

    def interrupted_probe():
        os.kill(os.getpid(), signal.SIGTERM)
        return 50

    receipt = tmp_path / "receipt"
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", side_effect=interrupted_probe),
          patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")) as enqueue,
          patch("runtime.loop.lm_loop_run.claim_durable_resource") as acquire,
          patch("runtime.loop.lm_loop_run.subprocess.Popen") as launch):
        assert _run_admitted(["/bin/true"], entry, "example", {}, receipt) == 75
    enqueue.assert_called_once(); acquire.assert_not_called(); launch.assert_not_called()
    assert json.loads(receipt.read_text())["reason"] == "resource_admission_interrupted"


def test_memory_deferral_preserves_queue_and_releases_reservation(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}
    receipt = tmp_path / "receipt"
    with (patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "capacity_busy")),
          patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=None),
          patch("runtime.loop.lm_loop_run.defer_durable_resource") as defer,
          patch("runtime.loop.lm_loop_run.claim_durable_resource") as claim):
        assert _run_admitted(["/bin/true"], entry, "example", {}, receipt) == 75
    defer.assert_called_once_with("example")
    claim.assert_not_called()
    assert json.loads(receipt.read_text())["reason"] == "memory_headroom_unavailable"


def test_post_claim_memory_deferral_requeues_without_dispatch(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}
    claim = tmp_path / "claim"
    with (patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                return_value=(tmp_path / "ticket", "ready")),
          patch("runtime.loop.lm_loop_run.claim_durable_resource",
                return_value=(claim, "acquired")),
          patch("runtime.loop.lm_loop_run.memory_free_percent", side_effect=[50, 10]),
          patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                return_value=[]) as release,
          patch("runtime.loop.lm_loop_run._dispatch_reserved") as dispatch,
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(["/bin/true"], entry, "example", {}, tmp_path / "receipt") == 75
    release.assert_called_once_with(claim, requeue=True, reserve=False)
    dispatch.assert_not_called(); run.assert_not_called()


def test_dispatch_reserved_kicks_only_current_loaded_idle_label(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    (current / "bin").mkdir(); agents.mkdir()
    safe = current / "bin/launchctl-safe"; safe.write_text("safe")
    row = {
        "label": "ai.anicca.example", "domain": "earn", "entrypoint": "bin/example",
        "cadence": {"start_interval_seconds": 300}, "effect_class": "message",
        "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic",
    }
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {"example": row}}))
    plist = {"ProgramArguments": [str(current.resolve() / "bin/lm-loop-run"),
                                   "example", str(current.resolve())]}
    (agents / "ai.anicca.example.plist").write_bytes(plistlib.dumps(plist))
    outputs = [
        subprocess.CompletedProcess(
            [], 0, "arguments = {\n" + "\n".join(plist["ProgramArguments"])
            + "\n}\nstate = not running",
        ),
        subprocess.CompletedProcess([], 0, ""),
        subprocess.CompletedProcess([], 0, "state = running"),
    ]
    with patch("runtime.loop.lm_loop_run.subprocess.run", side_effect=outputs) as run:
        assert _dispatch_reserved(["example"], current=current, agents_dir=agents) == ["example"]
    commands = [call.args[0][1] for call in run.call_args_list]
    assert commands == ["print", "kickstart", "print"]
    assert "-k" not in run.call_args_list[1].args[0]


def test_dispatch_reserved_cancels_missing_registry_owner(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {},
    }))

    with (patch("runtime.loop.lm_loop_run.cancel_durable_resource") as cancel,
          patch("runtime.loop.lm_loop_run.subprocess.run") as run):
        assert _dispatch_reserved(
            ["retired"], current=current, agents_dir=agents,
        ) == []

    cancel.assert_called_once_with("retired")
    run.assert_not_called()


def test_dispatch_scans_past_sixteen_stale_releases_to_healthy_owner(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    loop_ids = [f"stale-{index}" for index in range(17)] + ["healthy"]
    rows = {}
    for loop_id in loop_ids:
        label = f"ai.anicca.{loop_id}"
        rows[loop_id] = {
            "label": label, "domain": "earn", "entrypoint": "bin/example",
            "cadence": {"start_interval_seconds": 300}, "effect_class": "none",
            "state_root": f"~/.local/state/life-manager/{loop_id}",
            "log_root": f"~/.local/state/life-manager/{loop_id}/logs",
            "cleanup": {"max_runs": 10, "max_age_days": 7},
            "provider_route": "deterministic",
        }
        args = ([str(current.resolve() / "bin/lm-loop-run"), loop_id, str(current.resolve())]
                if loop_id == "healthy" else ["/old/bin/lm-loop-run", loop_id, "/old"])
        (agents / f"{label}.plist").write_bytes(plistlib.dumps({"ProgramArguments": args}))
    (current / "config/loop-registry.json").write_text(json.dumps({"schema_version": 2, "loops": rows}))

    def launchctl_result(args, **_kwargs):
        if args[1] == "kickstart":
            return subprocess.CompletedProcess(args, 0, "")
        expected = [str(current.resolve() / "bin/lm-loop-run"), "healthy", str(current.resolve())]
        return subprocess.CompletedProcess(
            args, 0, "arguments = {\n" + "\n".join(expected) + "\n}\nstate = waiting")

    with (patch("runtime.loop.lm_loop_run.defer_durable_resource", return_value=True),
          patch("runtime.loop.lm_loop_run.reserve_available_resource", return_value=[]),
          patch("runtime.loop.lm_loop_run.subprocess.run", side_effect=launchctl_result)):
        assert _dispatch_reserved(loop_ids, current=current, agents_dir=agents) == ["healthy"]


def test_dispatch_reserved_tolerates_missing_owner_cancel_failure(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {},
    }))

    for error in (OSError("admission unavailable"),
                  sqlite3.OperationalError("database is locked")):
        with (patch("runtime.loop.lm_loop_run.cancel_durable_resource",
                    side_effect=error) as cancel,
              patch("runtime.loop.lm_loop_run.subprocess.run") as run):
            assert _dispatch_reserved(
                ["retired"], current=current, agents_dir=agents,
            ) == []

        cancel.assert_called_once_with("retired")
        run.assert_not_called()


def test_dispatch_reserved_rejects_stale_loaded_release_prefix(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    row = {
        "label": "ai.anicca.example", "domain": "earn", "entrypoint": "bin/example",
        "cadence": {"start_interval_seconds": 300}, "effect_class": "message",
        "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic",
    }
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {"example": row},
    }))
    expected = [str(current.resolve() / "bin/lm-loop-run"),
                "example", str(current.resolve())]
    (agents / "ai.anicca.example.plist").write_bytes(plistlib.dumps({
        "ProgramArguments": expected,
    }))
    stale = [*expected[:-1], f"{current.resolve()}-stale"]
    observed = subprocess.CompletedProcess(
        [], 0, "arguments = {\n" + "\n".join(stale) + "\n}\nstate = not running",
    )

    with (patch("runtime.loop.lm_loop_run.defer_durable_resource") as defer,
          patch("runtime.loop.lm_loop_run.subprocess.run", return_value=observed) as run):
        assert _dispatch_reserved(
            ["example"], current=current, agents_dir=agents,
        ) == []

    defer.assert_called_once_with("example", cooldown_seconds=60)
    assert run.call_count == 1


def test_dispatch_drift_defers_unverified_loaded_release(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    row = {
        "label": "ai.anicca.example", "domain": "earn", "entrypoint": "bin/example",
        "cadence": {"start_interval_seconds": 300}, "effect_class": "none",
        "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic",
    }
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {"example": row},
    }))
    (agents / "ai.anicca.example.plist").write_bytes(plistlib.dumps({
        "ProgramArguments": ["/old/bin/lm-loop-run", "example", "/old"],
    }))
    with (patch("runtime.loop.lm_loop_run.apply_live", create=True,
                side_effect=AssertionError("queued owner rebound")),
          patch("runtime.loop.lm_loop_run.defer_durable_resource", return_value=False) as defer,
          patch("runtime.loop.lm_loop_run.subprocess.run") as run):
        assert _dispatch_reserved(["example"], current=current, agents_dir=agents) == []
    defer.assert_called_once_with("example", cooldown_seconds=60)
    run.assert_not_called()


def test_dispatch_kicks_queued_owner_on_valid_loaded_main_release(tmp_path):
    releases = tmp_path / "releases"
    current = releases / "new"
    old = releases / "old"
    agents = tmp_path / "agents"
    for release in (current, old):
        (release / "config").mkdir(parents=True)
        (release / "bin").mkdir()
        (release / "bin/lm-loop-run").write_text("#!/bin/sh\n")
        (release / "config/runtime-capabilities.json").write_text(
            json.dumps({"resource_admission": 2}))
    agents.mkdir()
    row = {
        "label": "ai.anicca.example", "domain": "system", "entrypoint": "bin/lm-loop-run",
        "cadence": {"start_interval_seconds": 300}, "effect_class": "none",
        "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic", "resource_class": "browser",
    }
    for release in (current, old):
        (release / "config/loop-registry.json").write_text(json.dumps({
            "schema_version": 2, "loops": {"example": row},
        }))
        (release / "RELEASE.json").write_text(json.dumps({
            "sha": "a" * 40, "provenance": "ancestor-of-origin-main",
            "release_paths": "ALL",
        }))
    old_args = [str(old / "bin/lm-loop-run"), "example", str(old)]
    (agents / "ai.anicca.example.plist").write_bytes(plistlib.dumps({
        "ProgramArguments": old_args,
    }))
    idle = subprocess.CompletedProcess(
        [], 0, "arguments = {\n" + "\n".join(old_args) + "\n}\nstate = not running",
    )
    running = subprocess.CompletedProcess(
        [], 0, "arguments = {\n" + "\n".join(old_args) + "\n}\nstate = running",
    )
    with (patch("runtime.loop.lm_loop_run.apply_live", create=True,
                side_effect=AssertionError("queued owner rebound")),
          patch("runtime.loop.lm_loop_run.subprocess.run",
                side_effect=[idle, subprocess.CompletedProcess([], 0, ""), running]) as run):
        assert _dispatch_reserved(["example"], current=current, agents_dir=agents) == ["example"]
    assert [item.args[0][1] for item in run.call_args_list] == [
        "print", "kickstart", "print",
    ]


def test_dispatch_release_drift_preserves_real_sqlite_waiter(tmp_path, monkeypatch):
    admission_root = tmp_path / "admission"
    monkeypatch.setenv("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", str(admission_root))
    admission.activate_durable_v2()
    admission.enqueue_durable("deterministic", "example", admission_class="borrow")
    assert admission.reserve_available() == ["example"]

    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    row = {
        "label": "ai.anicca.example", "domain": "earn", "entrypoint": "bin/example",
        "cadence": {"start_interval_seconds": 300}, "effect_class": "message",
        "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic",
    }
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {"example": row},
    }))
    (agents / "ai.anicca.example.plist").write_bytes(plistlib.dumps({
        "ProgramArguments": ["/old-release/bin/lm-loop-run", "example", "/old-release"],
    }))

    assert _dispatch_reserved(["example"], current=current, agents_dir=agents) == []
    with sqlite3.connect(admission_root / "admission-v2.sqlite3") as connection:
        assert connection.execute(
            "SELECT owner_id FROM queue WHERE owner_id='example'"
        ).fetchone() == ("example",)
        assert connection.execute(
            "SELECT owner_id FROM reservations WHERE owner_id='example'"
        ).fetchone() is None


def test_dispatch_drift_immediately_hands_free_slot_to_healthy_follower(
        tmp_path, monkeypatch):
    admission_root = tmp_path / "admission"
    monkeypatch.setenv("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", str(admission_root))
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_FINITE_RUNS", "1")
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_DETERMINISTIC_RUNS", "1")
    admission.activate_durable_v2()
    admission.enqueue_durable("deterministic", "drifted", admission_class="borrow")
    admission.enqueue_durable("deterministic", "healthy", admission_class="borrow")
    assert admission.reserve_available() == ["drifted"]

    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    rows = {}
    for loop_id in ("drifted", "healthy"):
        rows[loop_id] = {
            "label": f"ai.anicca.{loop_id}", "domain": "earn",
            "entrypoint": "bin/example", "cadence": {"start_interval_seconds": 300},
            "effect_class": "none", "state_root": f"~/.local/state/life-manager/{loop_id}",
            "log_root": f"~/.local/state/life-manager/{loop_id}/logs",
            "cleanup": {"max_runs": 10, "max_age_days": 7},
            "provider_route": "deterministic",
        }
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": rows,
    }))
    healthy_args = [str(current.resolve() / "bin/lm-loop-run"),
                    "healthy", str(current.resolve())]
    (agents / "ai.anicca.drifted.plist").write_bytes(plistlib.dumps({
        "ProgramArguments": ["/old/bin/lm-loop-run", "drifted", "/old"],
    }))
    (agents / "ai.anicca.healthy.plist").write_bytes(plistlib.dumps({
        "ProgramArguments": healthy_args,
    }))

    def launchctl_result(args, **_kwargs):
        if args[1] == "kickstart":
            return subprocess.CompletedProcess(args, 0, "")
        detail = "arguments = {\n" + "\n".join(healthy_args) + "\n}\nstate = waiting"
        return subprocess.CompletedProcess(args, 0, detail)

    with patch("runtime.loop.lm_loop_run.subprocess.run", side_effect=launchctl_result):
        started = _dispatch_reserved(["drifted"], current=current, agents_dir=agents)
    assert started == ["healthy"]
    with sqlite3.connect(admission_root / "admission-v2.sqlite3") as connection:
        assert connection.execute(
            "SELECT owner_id FROM queue WHERE owner_id='drifted'"
        ).fetchone() == ("drifted",)


def test_dispatch_reserved_keeps_running_owner_reservation(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    row = {
        "label": "ai.anicca.example", "domain": "earn", "entrypoint": "bin/example",
        "cadence": {"start_interval_seconds": 300}, "effect_class": "message",
        "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic",
    }
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {"example": row},
    }))
    expected = [str(current.resolve() / "bin/lm-loop-run"),
                "example", str(current.resolve())]
    (agents / "ai.anicca.example.plist").write_bytes(plistlib.dumps({
        "ProgramArguments": expected,
    }))
    observed = subprocess.CompletedProcess(
        [], 0, "arguments = {\n" + "\n".join(expected) + "\n}\nstate = running",
    )

    with (patch("runtime.loop.lm_loop_run.defer_durable_resource") as defer,
          patch("runtime.loop.lm_loop_run.subprocess.run", return_value=observed) as run):
        assert _dispatch_reserved(
            ["example"], current=current, agents_dir=agents,
        ) == []

    defer.assert_not_called()
    assert run.call_count == 1


def test_dispatch_reserved_rejects_loaded_output_without_explicit_idle_state(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    row = {
        "label": "ai.anicca.example", "domain": "earn", "entrypoint": "bin/example",
        "cadence": {"start_interval_seconds": 300}, "effect_class": "message",
        "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic",
    }
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {"example": row},
    }))
    expected = [str(current.resolve() / "bin/lm-loop-run"),
                "example", str(current.resolve())]
    (agents / "ai.anicca.example.plist").write_bytes(plistlib.dumps({
        "ProgramArguments": expected,
    }))
    observed = subprocess.CompletedProcess(
        [], 0, "arguments = {\n" + "\n".join(expected) + "\n}\nruns = 1",
    )

    with (patch("runtime.loop.lm_loop_run.defer_durable_resource") as defer,
          patch("runtime.loop.lm_loop_run.subprocess.run", return_value=observed) as run):
        assert _dispatch_reserved(
            ["example"], current=current, agents_dir=agents,
        ) == []

    defer.assert_called_once_with("example", cooldown_seconds=60)
    assert run.call_count == 1


def test_dispatch_reserved_rejects_noncanonical_installed_argv(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    row = {
        "label": "ai.anicca.example", "domain": "earn", "entrypoint": "bin/example",
        "cadence": {"start_interval_seconds": 300}, "effect_class": "message",
        "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic",
    }
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {"example": row},
    }))
    prefixed = [sys.executable, "-m", "runtime.loop.lm_loop_run",
                "example", str(current.resolve())]
    (agents / "ai.anicca.example.plist").write_bytes(plistlib.dumps({
        "ProgramArguments": prefixed,
    }))

    with (patch("runtime.loop.lm_loop_run.defer_durable_resource") as defer,
          patch("runtime.loop.lm_loop_run.subprocess.run") as run):
        assert _dispatch_reserved(
            ["example"], current=current, agents_dir=agents,
        ) == []

    defer.assert_called_once_with("example", cooldown_seconds=60)
    run.assert_not_called()


def test_dispatch_reserved_defers_owner_with_missing_plist(tmp_path):
    current = tmp_path / "release"
    agents = tmp_path / "agents"
    (current / "config").mkdir(parents=True)
    agents.mkdir()
    row = {
        "label": "ai.anicca.example", "domain": "earn", "entrypoint": "bin/example",
        "cadence": {"start_interval_seconds": 300}, "effect_class": "message",
        "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic",
    }
    (current / "config/loop-registry.json").write_text(json.dumps({
        "schema_version": 2, "loops": {"example": row},
    }))

    with (patch("runtime.loop.lm_loop_run.defer_durable_resource") as defer,
          patch("runtime.loop.lm_loop_run.subprocess.run") as run):
        assert _dispatch_reserved(
            ["example"], current=current, agents_dir=agents,
        ) == []

    defer.assert_called_once_with("example", cooldown_seconds=60)
    run.assert_not_called()


def test_real_child_receives_sigterm_after_atomic_handoff(tmp_path):
    ready = tmp_path / "ready"
    child = (
        "import pathlib,signal,time,sys; "
        "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); "
        f"pathlib.Path({str(ready)!r}).write_text('ready'); time.sleep(60)"
    )
    runner = (
        "import sys; from runtime.loop.lm_loop_run import _run_entrypoint; "
        f"sys.exit(_run_entrypoint([sys.executable, '-c', {child!r}], timeout_seconds=60))"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", runner], cwd=str(Path(__file__).parents[3]),
        env={**os.environ, "PYTHONPATH": "."})
    deadline = time.monotonic() + 10
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(.01)
    assert ready.exists()
    os.kill(process.pid, signal.SIGTERM)
    assert process.wait(timeout=5) == 0


def test_wrapper_sigkill_keeps_effect_child_claim_live(tmp_path, monkeypatch):
    admission_root = tmp_path / "admission"
    ready = tmp_path / "ready"
    receipt = tmp_path / "receipt.json"
    monkeypatch.setenv("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", str(admission_root))
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_FINITE_RUNS", "1")
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_AGENT_RUNS", "1")
    child = (
        "import pathlib,signal,time,sys; "
        "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); "
        f"pathlib.Path({str(ready)!r}).write_text('ready'); time.sleep(60)"
    )
    entry = {
        "cadence": {"start_interval_seconds": 60},
        "provider_route": "shared-agent-runner",
    }
    runner = (
        "import os,pathlib,sys; "
        "from runtime.loop.lm_loop_run import _run_admitted; "
        f"entry={entry!r}; command=[sys.executable,'-c',{child!r}]; "
        f"sys.exit(_run_admitted(command,entry,'example',os.environ.copy(),"
        f"pathlib.Path({str(receipt)!r})))"
    )
    wrapper = subprocess.Popen(
        [sys.executable, "-c", runner], cwd=str(Path(__file__).parents[3]),
        env={**os.environ, "PYTHONPATH": "."},
    )
    child_pid = None
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            rows = list((admission_root / "owners").glob("*.json"))
            if rows and ready.exists():
                row = json.loads(rows[0].read_text())
                if row.get("phase") == "running":
                    child_pid = row["pid"]
                    break
            time.sleep(.01)
        assert child_pid is not None

        os.kill(wrapper.pid, signal.SIGKILL)
        assert wrapper.wait(timeout=5) == -signal.SIGKILL
        admission = __import__(
            "runtime.host.resource_admission", fromlist=["process_start"],
        )
        assert admission.process_start(child_pid)

        queued, reason = admission.enqueue_durable("agent", "example")
        assert queued is None and reason == "owner_busy"
        with sqlite3.connect(admission_root / "admission-v2.sqlite3") as connection:
            assert connection.execute("SELECT COUNT(*) FROM queue").fetchone()[0] == 0
        duplicate, reason = admission.claim_durable("agent", "example")
        assert duplicate is None and reason == "ticket_missing"
        os.killpg(child_pid, signal.SIGTERM)
        deadline = time.monotonic() + 5
        while admission.process_start(child_pid) and time.monotonic() < deadline:
            time.sleep(.01)
        assert not admission.process_start(child_pid)
        assert admission.reserve_available() == []
        with sqlite3.connect(admission_root / "admission-v2.sqlite3") as connection:
            assert connection.execute("SELECT COUNT(*) FROM queue").fetchone()[0] == 0
    finally:
        if wrapper.poll() is None:
            wrapper.kill()
            wrapper.wait(timeout=5)
        if child_pid is not None:
            try:
                os.killpg(child_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
