from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from datetime import datetime, timezone


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load(
    SCRIPTS / "lancers_platform_manifest_runtime.py",
    "lancers_platform_manifest_runtime_test",
)
application_loop = _load(
    SCRIPTS / "application_loop.py",
    "lancers_application_loop_manifest_runtime_test",
)


def test_lancers_natural_wake_filters_contract_state_and_persists_partial_cycle(tmp_path):
    contracts_path = tmp_path / "contracts.json"
    contracts_path.write_text(json.dumps({
        "logged_in": True,
        "source_complete": True,
        "observed_at": "2026-09-30T13:00:00Z",
        "board_count": 3,
        "required_reply_count": 1,
        "unread_count": 2,
        # These fields are deliberately opportunity/contract data and must not
        # cross the platform-manifest boundary.
        "boards": [{"board_id": "secret-opportunity-data"}],
        "contract_candidates": [{"project_id": "123"}],
    }), encoding="utf-8")

    result = runtime.run_lancers_platform_manifest_wake(
        contracts_path=contracts_path,
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        run_id="lancers-natural-1",
        observed_at="2026-09-30T13:01:00Z",
    )

    assert result["status"] == "partial"
    assert result["sources"] == 4
    assert result["inspected"] == 1
    assert result["held"] == 1
    assert {row["source"] for row in result["source_errors"]} == {
        "coconala", "crowdworks", "mercor",
    }


def test_lancers_natural_wake_missing_contract_state_is_typed_partial_without_creation(tmp_path):
    result = runtime.run_lancers_platform_manifest_wake(
        contracts_path=tmp_path / "missing-contracts.json",
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        run_id="lancers-natural-missing-1",
        observed_at="2026-09-30T13:02:00Z",
    )

    assert result["status"] == "partial"
    assert result["inspected"] == 0
    assert {row["source"] for row in result["source_errors"]} == {
        "coconala", "lancers", "crowdworks", "mercor",
    }
    assert not (tmp_path / "missing-contracts.json").exists()


def test_lancers_application_wake_bridge_writes_summary(tmp_path):
    contracts_path = tmp_path / "contracts.json"
    contracts_path.write_text(json.dumps({
        "logged_in": True,
        "source_complete": True,
        "board_count": 0,
        "required_reply_count": 0,
        "unread_count": 0,
    }), encoding="utf-8")

    payload = application_loop.record_live_lancers_platform_manifest_wake(
        evidence_dir=tmp_path / "evidence",
        pass_id="lancers-pass-1",
        contracts_path=contracts_path,
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        observed_at="2026-09-30T13:03:00Z",
    )

    assert payload["status"] == "partial"
    assert payload["pass_id"] == "lancers-pass-1"
    assert (tmp_path / "evidence" / "platform-manifest-wake.json").is_file()


def test_lancers_natural_run_invokes_platform_bridge_before_default_discovery(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        application_loop,
        "record_live_lancers_platform_manifest_wake",
        lambda **kwargs: calls.append(kwargs) or {"status": "partial"},
    )
    monkeypatch.setattr(application_loop, "_capacity_reason", lambda *_args: None)
    monkeypatch.setattr(
        application_loop,
        "_run_default_discovery",
        lambda *_args: {"ok": True, "opportunities": [], "observed_count": 0, "already_decided_count": 0},
    )

    result = application_loop.run_loop(
        state_path=tmp_path / "application.json",
        evidence_root=tmp_path / "evidence",
        clock=lambda: datetime(2026, 9, 30, 13, 4, tzinfo=timezone.utc),
    )

    assert result["reason"] == "no_eligible_project"
    assert len(calls) == 1
    assert calls[0]["contracts_path"] == tmp_path / "contracts.json"
