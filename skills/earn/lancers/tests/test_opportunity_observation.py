from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
MODULE_PATH = SCRIPTS / "opportunity_observation.py"
LOOP_PATH = SCRIPTS / "application_loop.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


observation = _load(MODULE_PATH, "lancers_opportunity_observation_test")
loop = _load(LOOP_PATH, "lancers_application_loop_observation_test")


def _record(external_id: str = "123"):
    return {
        "schema_version": 1,
        "record_type": "opportunity",
        "platform": "lancers",
        "external_id": external_id,
        "title": "業務自動化案件",
        "description": "業務フローを自動化する案件です。",
        "url": f"https://www.lancers.jp/work/detail/{external_id}",
        "category": "システム開発",
        "budget_type": "fixed",
        "budget_min_minor": 10000,
        "budget_max_minor": 50000,
        "currency": "JPY",
        "buyer_external_id": "client-1",
        "observed_at": "2026-09-30T12:00:00Z",
    }


def _snapshot():
    return {
        "ok": True,
        "platform": "lancers",
        "source": "public_html",
        "opportunities": [_record()],
        "already_applied_ids": [],
    }


def test_lancers_observation_persists_planner_eligibility(tmp_path):
    result = observation.observe_lancers_opportunities(
        _snapshot(),
        {"decisions": [{"request_id": "123", "business_class": "submit_required"}]},
        store_root=tmp_path / "observations",
        evidence_ref="snapshot://lancers/pass-1",
    )

    assert result["eligible"] == 1
    assert result["persisted"] == 1
    assert result["next_actions"][0]["next_action"] == "lancers_application_effect"


def test_lancers_observation_holds_missing_planner_decision(tmp_path):
    result = observation.observe_lancers_opportunities(
        _snapshot(),
        {"decisions": []},
        store_root=tmp_path / "observations",
        evidence_ref="snapshot://lancers/pass-1",
    )

    assert result["eligible"] == 0
    assert result["held"] == 1
    assert result["next_actions"][0]["next_action"] == "await_planner_decision"


def test_lancers_observation_rejects_invalid_decisions(tmp_path):
    with pytest.raises(observation.LancersObservationError, match="decisions_invalid"):
        observation.observe_lancers_opportunities(
            _snapshot(),
            {"decisions": None},
            store_root=tmp_path / "observations",
            evidence_ref="snapshot://lancers/pass-1",
        )


def test_application_loop_live_boundary_writes_observation_summary(tmp_path):
    summary = loop.record_lancers_live_observation(
        _snapshot(),
        {"decisions": [{"request_id": "123", "business_class": "submit_required"}]},
        evidence_dir=tmp_path / "evidence",
        pass_id="pass-1",
        store_root=tmp_path / "observations",
    )

    assert summary["eligible"] == 1
    assert (tmp_path / "evidence" / "opportunity-observation-summary.json").is_file()


def test_application_loop_source_failure_is_not_reported_as_empty_market(tmp_path):
    evidence_dir = tmp_path / "evidence"
    loop.record_lancers_observation_source_failure(
        evidence_dir, "pass-1", "lancers_human_verification_required",
    )

    payload = json.loads(
        (evidence_dir / "opportunity-observation-summary.json").read_text(encoding="utf-8")
    )
    assert payload["status"] == "source_collect_failed"
    assert payload["next_action"] == "retry_lancers_public_snapshot_read_only"
