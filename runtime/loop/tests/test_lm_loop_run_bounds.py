import json
import os
import signal
import plistlib
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import call, patch

from runtime.host import resource_admission as admission
from runtime.loop.lm_loop_run import (
    PRE_EFFECT_HINT_ENTRYPOINTS,
    _admission_class, _dispatch_reserved, _host_admission_deferred, _queue_priority,
    _persist_effect_identity, _resource_class,
    _run_admitted, _run_entrypoint, _runtime_limit, _terminal_outcome,
)


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


def test_crowdworks_paid_owner_declares_a_bounded_runtime():
    registry = json.loads(
        (Path(__file__).resolve().parents[3] / "config/loop-registry.json").read_text()
    )

    assert registry["loops"]["crowdworks-revenue-paid"]["runtime_timeout_seconds"] == 180


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
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(
            ["/bin/true"], entry, "life-manager-connector-native", {},
            tmp_path / "receipt", occurrence_id="connector:new",
        ) == 75
    enqueue.assert_called_once_with(
        "browser", "life-manager-connector-native", admission_class="revenue",
        occurrence_id="connector:new",
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
    for loop_id in ("life-manager-release-reconciler", "life-manager-disk-cleanup",
                    "capafy-loop-healthcheck"):
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


def test_mercor_application_and_reply_pre_effect_hints_are_allowlisted():
    assert "skills/earn/mercor/scripts/application-owner" in PRE_EFFECT_HINT_ENTRYPOINTS
    assert "skills/earn/mercor/scripts/reply-owner" in PRE_EFFECT_HINT_ENTRYPOINTS


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
    sidecar.write_text('{"job_id":"job-1"}\n', encoding="utf-8")
    state_root = tmp_path / "state"

    ref = _persist_effect_identity(
        sidecar, state_root, "life-manager-honne-ja", "run-1",
    )

    assert ref == "lm-effect://life-manager-honne-ja/run-1/identity.jsonl"
    persisted = state_root / "effect-identities" / "run-1.jsonl"
    assert persisted.read_text(encoding="utf-8") == '{"job_id":"job-1"}\n'
    assert persisted.stat().st_mode & 0o777 == 0o600


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

    with (patch("runtime.loop.lm_loop_run.cancel_durable_resource",
                side_effect=OSError("admission unavailable")) as cancel,
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


def test_dispatch_drift_syncs_and_starts_one_idle_owner(tmp_path):
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
    expected = [str(current.resolve() / "bin/lm-loop-run"),
                "example", str(current.resolve())]
    loaded_idle = subprocess.CompletedProcess(
        [], 0, "arguments = {\n" + "\n".join(expected) + "\n}\nstate = not running",
    )
    kicked = subprocess.CompletedProcess([], 0, "")
    loaded_running = subprocess.CompletedProcess(
        [], 0, "arguments = {\n" + "\n".join(expected) + "\n}\nstate = running",
    )
    with (patch("runtime.loop.lm_loop_run.apply_live", create=True,
                return_value=[{"ok": True, "loaded_arguments": expected}]) as apply,
          patch("runtime.loop.lm_loop_run.defer_durable_resource") as defer,
          patch("runtime.loop.lm_loop_run.subprocess.run",
                side_effect=[loaded_idle, kicked, loaded_running]) as run):
        assert _dispatch_reserved(["example"], current=current, agents_dir=agents) == ["example"]
    apply.assert_called_once()
    assert apply.call_args.kwargs["target"] == "example"
    assert apply.call_args.kwargs["skip_busy"] is True
    defer.assert_not_called()
    assert [item.args[0][1] for item in run.call_args_list] == [
        "print", "kickstart", "print",
    ]
    with (patch("runtime.loop.lm_loop_run.apply_live",
                return_value=[{"ok": True, "loaded_arguments": expected}]),
          patch("runtime.loop.lm_loop_run.subprocess.run",
                return_value=loaded_running) as run):
        assert _dispatch_reserved(["example"], current=current, agents_dir=agents) == []
    assert [item.args[0][1] for item in run.call_args_list] == ["print"]


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
