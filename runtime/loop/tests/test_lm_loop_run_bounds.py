import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

from runtime.loop.lm_loop_run import (
    _host_admission_deferred, _resource_class, _run_admitted, _run_entrypoint,
    _runtime_limit, _terminal_outcome,
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
    assert _terminal_outcome(75, host_deferred=True) == (
        False, True, "host_admission_deferred")
    assert _terminal_outcome(124, host_deferred=True) == (
        False, True, "host_admission_deferred")
    assert _terminal_outcome(75) == (False, False, "entrypoint_exit_75")
    assert _terminal_outcome(1) == (False, False, "entrypoint_exit_1")


def test_memory_deferral_requires_a_fresh_matching_receipt(tmp_path):
    receipt = tmp_path / "memory.json"
    started = time.time_ns()
    receipt.write_text(json.dumps({"status": "deferred", "effect": 0}))
    assert _host_admission_deferred(receipt, started)
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


def test_admission_wait_does_not_consume_entrypoint_runtime_budget(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner", "runtime_timeout_seconds": 123}
    claim = tmp_path / "claim"
    claim.write_text("owned")
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.acquire_resource", return_value=claim),
          patch("runtime.loop.lm_loop_run.release_resource") as release,
          patch("runtime.loop.lm_loop_run._run_entrypoint", return_value=0) as run):
        assert _run_admitted(["/bin/true"], entry, "example", {}, tmp_path / "receipt") == 0
    assert run.call_args.kwargs["timeout_seconds"] == 123
    release.assert_called_once_with(claim)


def test_interrupted_admission_becomes_deferred_receipt(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}
    receipt = tmp_path / "receipt"
    with (patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
          patch("runtime.loop.lm_loop_run.acquire_resource", side_effect=InterruptedError),
          patch("runtime.loop.lm_loop_run._run_entrypoint") as run):
        assert _run_admitted(["/bin/true"], entry, "example", {}, receipt) == 75
    run.assert_not_called()
    assert json.loads(receipt.read_text())["reason"] == "resource_admission_interrupted"


def test_invalid_memory_threshold_fails_closed(tmp_path):
    entry = {"cadence": {"start_interval_seconds": 60},
             "provider_route": "shared-agent-runner"}
    for value in ("0", "-1", "101"):
        with (patch.dict(os.environ, {"LIFE_MANAGER_MIN_MEMORY_FREE_PERCENT": value}),
              patch("runtime.loop.lm_loop_run.acquire_resource") as acquire,
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
          patch("runtime.loop.lm_loop_run.acquire_resource", return_value=claim),
          patch("runtime.loop.lm_loop_run.release_resource"),
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
          patch("runtime.loop.lm_loop_run.acquire_resource") as acquire,
          patch("runtime.loop.lm_loop_run.subprocess.Popen") as launch):
        assert _run_admitted(["/bin/true"], entry, "example", {}, receipt) == 75
    acquire.assert_not_called(); launch.assert_not_called()
    assert json.loads(receipt.read_text())["reason"] == "resource_admission_interrupted"


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
