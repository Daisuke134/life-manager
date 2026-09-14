import json
import os
import signal
import plistlib
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from runtime.host import resource_admission as admission
from runtime.loop.lm_loop_run import (
    _dispatch_reserved, _host_admission_deferred, _resource_class, _run_admitted, _run_entrypoint,
    _runtime_limit, _terminal_outcome,
)


@pytest.fixture(autouse=True)
def durable_protocol_v2(monkeypatch):
    monkeypatch.setattr(
        "runtime.loop.lm_loop_run.durable_protocol_version", lambda: 2,
    )


def test_scheduled_wakes_have_a_finite_one_hour_safety_limit():
    assert _runtime_limit({"cadence": {"start_interval_seconds": 300}}) == 3600
    assert _runtime_limit({"cadence": {"calendar_interval": {"Minute": 5}}}) == 3600
    assert _runtime_limit({"cadence": {"run_at_load": True}}) == 3600


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
        "agent", "example", retain_ticket=False, required_protocol=1,
    )
    enqueue.assert_not_called()
    transfer.assert_called_once_with(claim, 4242)
    release.assert_called_once_with(claim)


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
    enqueue.assert_called_once_with("agent", "example")
    acquire.assert_called_once_with("agent", "example")
    reserve.assert_called_once_with(); dispatch.assert_called_once_with([])
    run.assert_not_called()
    assert json.loads(receipt.read_text()) == {
        "effect": 0,
        "reason": "resource_capacity_busy",
        "status": "deferred",
    }


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

    with (patch("runtime.loop.lm_loop_run.cancel_durable_resource") as cancel,
          patch("runtime.loop.lm_loop_run.subprocess.run", return_value=observed) as run):
        assert _dispatch_reserved(
            ["example"], current=current, agents_dir=agents,
        ) == []

    cancel.assert_called_once_with("example")
    assert run.call_count == 1


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

    with (patch("runtime.loop.lm_loop_run.cancel_durable_resource") as cancel,
          patch("runtime.loop.lm_loop_run.subprocess.run", return_value=observed) as run):
        assert _dispatch_reserved(
            ["example"], current=current, agents_dir=agents,
        ) == []

    cancel.assert_not_called()
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

    with (patch("runtime.loop.lm_loop_run.cancel_durable_resource") as cancel,
          patch("runtime.loop.lm_loop_run.subprocess.run", return_value=observed) as run):
        assert _dispatch_reserved(
            ["example"], current=current, agents_dir=agents,
        ) == []

    cancel.assert_called_once_with("example")
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

    with (patch("runtime.loop.lm_loop_run.cancel_durable_resource") as cancel,
          patch("runtime.loop.lm_loop_run.subprocess.run") as run):
        assert _dispatch_reserved(
            ["example"], current=current, agents_dir=agents,
        ) == []

    cancel.assert_called_once_with("example")
    run.assert_not_called()


def test_dispatch_reserved_cancels_owner_with_missing_plist(tmp_path):
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

    with (patch("runtime.loop.lm_loop_run.cancel_durable_resource") as cancel,
          patch("runtime.loop.lm_loop_run.subprocess.run") as run):
        assert _dispatch_reserved(
            ["example"], current=current, agents_dir=agents,
        ) == []

    cancel.assert_called_once_with("example")
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
