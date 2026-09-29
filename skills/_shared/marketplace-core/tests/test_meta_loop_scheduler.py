from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


enrollment = _load(SCRIPTS / "platform_enrollment.py", "meta_loop_enrollment_test")
candidate_store_module = _load(
    SCRIPTS / "platform_candidate_store.py", "meta_loop_candidate_store_test"
)
run_store_module = _load(SCRIPTS / "meta_loop_run_store.py", "meta_loop_run_store_test")


def _candidate() -> dict[str, object]:
    return {
        "version": 1,
        "provider": "example-market",
        "policy": {
            "status": "unknown",
            "source_url": "https://example.test/policy",
            "observed_at": "2026-09-30T00:00:00Z",
        },
        "adapter": {
            "contract": "marketplace-core-v1",
            "actions": [
                "discover", "inspect", "propose", "message", "accept_offer",
                "deliver", "read_payments", "read_payouts",
            ],
            "source_sha256": "a" * 64,
        },
        "funded_work": {
            "status": "unknown",
            "receipt_ref": "provider-receipt://example-market/unverified",
            "observed_at": "2026-09-30T00:00:00Z",
        },
        "canary": {
            "status": "unknown",
            "official_receipt_ref": None,
            "replay_zero": False,
            "observed_at": "2026-09-30T00:00:00Z",
        },
        "unit_economics": {
            "status": "unknown",
            "net_amount_minor": 0,
            "currency": "USD",
            "evidence_refs": ["candidate://example-market/unverified"],
        },
    }


def _item() -> dict[str, object]:
    return {
        "candidate": _candidate(),
        "candidate_id": "platform:example-market",
        "observed_at": "2026-09-30T00:01:00Z",
        "source_url": "https://example.test/platform",
        "snapshot_sha256": "b" * 64,
        "evidence_refs": ["source://example-market/manifest-1"],
    }


def test_meta_loop_wake_persists_structured_summary(tmp_path):
    candidates = candidate_store_module.CandidateStateStore(tmp_path / "candidates")
    runs = run_store_module.MetaLoopRunStore(tmp_path / "runs")

    result = enrollment.run_meta_loop_wake(
        {"manifest": lambda: [_item()]},
        candidates,
        runs,
        run_id="wake-1",
        observed_at="2026-09-30T00:02:00Z",
    )

    assert result["run_id"] == "wake-1"
    assert result["status"] == "ok"
    assert result["inspected"] == 1
    assert result["run_persistence"]["status"] == "appended"
    [row] = runs.read_all()
    assert row["run_id"] == "wake-1"
    assert row["held"] == 1
    assert row["next_actions"][0]["next_action"] == "collect_missing_gates"


def test_meta_loop_wake_records_empty_summary_durably(tmp_path):
    candidates = candidate_store_module.CandidateStateStore(tmp_path / "candidates")
    runs = run_store_module.MetaLoopRunStore(tmp_path / "runs")

    result = enrollment.run_meta_loop_wake(
        {"manifest": lambda: []},
        candidates,
        runs,
        run_id="wake-empty",
        observed_at="2026-09-30T00:02:00Z",
    )

    assert result["status"] == "empty"
    assert result["run_persistence"]["status"] == "appended"
    assert runs.latest("wake-empty")["inspected"] == 0


def test_meta_loop_wake_rejects_invalid_run_id_before_discovery(tmp_path):
    candidates = candidate_store_module.CandidateStateStore(tmp_path / "candidates")
    runs = run_store_module.MetaLoopRunStore(tmp_path / "runs")
    called = False

    def discover():
        nonlocal called
        called = True
        return []

    with pytest.raises(enrollment.EnrollmentError, match="run_id_invalid"):
        enrollment.run_meta_loop_wake(
            {"manifest": discover},
            candidates,
            runs,
            run_id="../escape",
            observed_at="2026-09-30T00:02:00Z",
        )
    assert called is False


def test_meta_loop_wake_persists_safe_source_error_code(tmp_path):
    candidates = candidate_store_module.CandidateStateStore(tmp_path / "candidates")
    runs = run_store_module.MetaLoopRunStore(tmp_path / "runs")

    def failing_source():
        raise RuntimeError("account_state_invalid")

    result = enrollment.run_meta_loop_wake(
        {"lancers": failing_source},
        candidates,
        runs,
        run_id="wake-error-code",
        observed_at="2026-09-30T00:03:00Z",
    )

    assert result["status"] == "partial"
    assert result["source_errors"][0]["error_code"] == "account_state_invalid"
    assert runs.latest("wake-error-code")["source_errors"][0]["error_code"] == "account_state_invalid"
