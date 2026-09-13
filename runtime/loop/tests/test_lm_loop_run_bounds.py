import json
import os
import sys
import time

from runtime.loop.lm_loop_run import (
    HOST_ADMISSION, _host_admitted_command, _memory_admission_deferred,
    _run_entrypoint, _runtime_limit, _terminal_outcome,
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


def test_only_finite_wakes_use_the_shared_host_admission():
    command = ["/bin/true"]
    assert _host_admitted_command(command, {"cadence": {"keep_alive": True}}) is command
    assert _host_admitted_command(command, {"cadence": {"start_interval_seconds": 60}}) == [
        sys.executable, str(HOST_ADMISSION), "/bin/true"]


def test_memory_admission_exit_is_deferred_not_failed():
    assert _terminal_outcome(75, memory_deferred=True) == (
        False, True, "memory_admission_deferred")
    assert _terminal_outcome(75) == (False, False, "entrypoint_exit_75")
    assert _terminal_outcome(1) == (False, False, "entrypoint_exit_1")


def test_memory_deferral_requires_a_fresh_matching_receipt(tmp_path):
    receipt = tmp_path / "memory.json"
    started = time.time_ns()
    receipt.write_text(json.dumps({"status": "deferred", "effect": 0}))
    assert _memory_admission_deferred(receipt, started)
    receipt.write_text(json.dumps({"status": "pass", "effect": 0}))
    assert not _memory_admission_deferred(receipt, started)


def test_entrypoint_timeout_terminates_its_process_group():
    started = time.monotonic()
    result = _run_entrypoint(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        timeout_seconds=0.05,
        termination_grace_seconds=0.05,
    )

    assert result == 124
    assert time.monotonic() - started < 2
