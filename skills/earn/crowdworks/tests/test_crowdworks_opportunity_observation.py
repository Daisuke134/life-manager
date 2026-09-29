from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
MODULE_PATH = SCRIPTS / "opportunity_observation.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


observation = _load(MODULE_PATH, "crowdworks_opportunity_observation_test")


def _snapshot() -> dict[str, object]:
    return {
        "ok": True,
        "platform": "crowdworks",
        "observed_at": "2026-09-30T10:00:00Z",
        "opportunities": [{
            "external_id": "123",
            "title": "業務自動化の案件",
            "description": "公開案件本文です。",
            "category": "システム開発",
            "url": "https://crowdworks.jp/public/jobs/123",
            "observed_at": "2026-09-30T10:00:00Z",
            "budget_type": "fixed",
            "currency": "JPY",
        }],
        "already_applied_ids": [],
    }


def test_submit_required_is_persisted_as_crowdworks_effect_eligible(tmp_path):
    result = observation.observe_crowdworks_opportunities(
        _snapshot(),
        {"decisions": [{"request_id": "123", "business_class": "submit_required"}]},
        store_root=tmp_path / "observations",
        evidence_ref="snapshot://crowdworks/pass-1/public-discovery.json",
    )

    assert result["inspected"] == 1
    assert result["eligible"] == 1
    assert result["next_actions"] == [{
        "provider": "crowdworks",
        "opportunity_id": "job:123",
        "decision": "eligible",
        "next_action": "crowdworks_application_effect",
    }]


def test_missing_planner_decision_is_held_without_apply_authorization(tmp_path):
    result = observation.observe_crowdworks_opportunities(
        _snapshot(),
        {"decisions": []},
        store_root=tmp_path / "observations",
        evidence_ref="snapshot://crowdworks/pass-1/public-discovery.json",
    )

    assert result["eligible"] == 0
    assert result["held"] == 1
    assert result["next_actions"][0]["next_action"] == "await_planner_decision"


def test_hard_prohibited_is_held_with_do_not_apply(tmp_path):
    result = observation.observe_crowdworks_opportunities(
        _snapshot(),
        {"decisions": [{"request_id": "123", "business_class": "hard_prohibited"}]},
        store_root=tmp_path / "observations",
        evidence_ref="snapshot://crowdworks/pass-1/public-discovery.json",
    )

    assert result["held"] == 1
    assert result["next_actions"][0]["next_action"] == "do_not_apply"


def test_invalid_decision_shape_fails_closed(tmp_path):
    with pytest.raises(observation.CrowdWorksObservationError, match="decisions_invalid"):
        observation.observe_crowdworks_opportunities(
            _snapshot(),
            {"decisions": "not-an-array"},
            store_root=tmp_path / "observations",
            evidence_ref="snapshot://crowdworks/pass-1/public-discovery.json",
        )


def test_source_collection_failure_is_typed():
    with pytest.raises(observation.CrowdWorksObservationError, match="observation_failed"):
        observation.observe_crowdworks_opportunities(
            {"ok": True, "platform": "crowdworks", "opportunities": "bad", "already_applied_ids": []},
            {"decisions": []},
            store_root=Path("/tmp/crowdworks-observation-test"),
            evidence_ref="snapshot://crowdworks/pass-1/public-discovery.json",
        )
