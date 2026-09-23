import json
import sqlite3
from unittest.mock import patch

from runtime.loop.lm_loop_run import _run_admitted


def _entry() -> dict:
    return {
        "cadence": {"start_interval_seconds": 300},
        "provider_route": "deterministic",
        "resource_class": "agent",
        "admission_class": "revenue",
        "effect_class": "provider_write",
    }


def test_unavailable_enqueue_names_phase_and_bounded_error_class(tmp_path):
    receipt = tmp_path / "host-admission.json"
    with (
        patch(
            "runtime.loop.lm_loop_run.enqueue_durable_resource",
            side_effect=sqlite3.OperationalError("sensitive provider path"),
        ),
        patch("runtime.loop.lm_loop_run._run_entrypoint") as run,
    ):
        assert _run_admitted(
            ["/bin/true"],
            _entry(),
            "example-apply",
            {},
            receipt,
            occurrence_id="example-apply:wake-1",
        ) == 75

    assert json.loads(receipt.read_text()) == {
        "status": "deferred",
        "effect": 0,
        "reason": "resource_admission_unavailable",
        "phase": "enqueue",
        "error_class": "sqlite_operational_error",
    }
    assert "sensitive provider path" not in receipt.read_text()
    run.assert_not_called()


def test_unavailable_claim_names_phase_and_bounded_error_class(tmp_path):
    receipt = tmp_path / "host-admission.json"
    with (
        patch(
            "runtime.loop.lm_loop_run.enqueue_durable_resource",
            return_value=(tmp_path / "ticket", "ready"),
        ),
        patch(
            "runtime.loop.lm_loop_run.claim_durable_resource",
            side_effect=OSError("sensitive host path"),
        ),
        patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=50),
        patch("runtime.loop.lm_loop_run._run_entrypoint") as run,
    ):
        assert _run_admitted(
            ["/bin/true"],
            _entry(),
            "example-apply",
            {},
            receipt,
            occurrence_id="example-apply:wake-2",
        ) == 75

    assert json.loads(receipt.read_text()) == {
        "status": "deferred",
        "effect": 0,
        "reason": "resource_admission_unavailable",
        "phase": "claim",
        "error_class": "os_error",
    }
    assert "sensitive host path" not in receipt.read_text()
    run.assert_not_called()
