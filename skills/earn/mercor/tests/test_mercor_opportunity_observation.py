from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
MODULE_PATH = SCRIPTS / "opportunity_observation.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


observation = _load(MODULE_PATH, "mercor_opportunity_observation_test")
APP_ROOT = Path(__file__).resolve().parents[4] / "apps" / "job-search-loop"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
from job_search_loop import mercor_pass  # noqa: E402


def _snapshot(*, decision: str = "submit_required", application_state: str = "ready"):
    return {
        "ok": True,
        "platform": "mercor",
        "observed_at": "2026-09-30T10:00:00Z",
        "inspected_listings": [{
            "listing_id": "list_123",
            "url": "https://work.mercor.com/explore?listingId=list_123",
            "title": "AI automation engineer",
            "application_state": application_state,
            "submit_visible": application_state == "ready",
            "decision": decision,
            "ranking_band": "high",
            "ranking_evidence": ["AI automation overlap"],
            "provider_fit_status": "allowed",
            "requirement_evidence": [],
            "strategy_version": "mercor-fit-evidence-v1",
        }],
        "submitted_listing_ids": [],
    }


def test_submit_required_is_eligible_for_mercor_effect(tmp_path):
    result = observation.observe_mercor_opportunities(
        _snapshot(),
        store_root=tmp_path / "observations",
        evidence_ref="snapshot://mercor/pass-1/public-discovery.json",
    )

    assert result["inspected"] == 1
    assert result["eligible"] == 1
    assert result["next_actions"] == [{
        "provider": "mercor",
        "opportunity_id": "listing:list_123",
        "decision": "eligible",
        "next_action": "mercor_application_effect",
    }]


def test_card_only_observation_is_held_until_detail_decision(tmp_path):
    result = observation.observe_mercor_opportunities(
        _snapshot(decision="card_only_unverified", application_state="card_only"),
        store_root=tmp_path / "observations",
        evidence_ref="snapshot://mercor/pass-1/public-discovery.json",
    )

    assert result["eligible"] == 0
    assert result["held"] == 1
    assert result["next_actions"][0]["next_action"] == "retain_mercor_effect_fence"


def test_provider_blocked_listing_is_held_without_effect(tmp_path):
    result = observation.observe_mercor_opportunities(
        _snapshot(decision="no_reasonable_shot", application_state="detail_observed")
        | {"inspected_listings": [{**_snapshot()["inspected_listings"][0], "provider_fit_status": "blocked"}]},
        store_root=tmp_path / "observations",
        evidence_ref="snapshot://mercor/pass-1/public-discovery.json",
    )

    assert result["held"] == 1
    assert result["next_actions"][0]["next_action"] == "do_not_apply"


def test_invalid_snapshot_fails_closed(tmp_path):
    with pytest.raises(observation.MercorObservationError, match="snapshot_invalid"):
        observation.observe_mercor_opportunities(
            None,
            store_root=tmp_path / "observations",
            evidence_ref="snapshot://mercor/pass-1/public-discovery.json",
        )


def test_pass_result_is_bound_to_shared_observation_snapshot(tmp_path):
    snapshot = mercor_pass.build_mercor_observation_snapshot(
        _snapshot(), observed_at="2026-09-30T10:00:00Z"
    )

    assert snapshot["platform"] == "mercor"
    assert snapshot["inspected_listings"][0]["listing_id"] == "list_123"
    assert snapshot["submitted_listing_ids"] == []


def test_live_mercor_observation_writes_summary(tmp_path):
    summary = mercor_pass.record_mercor_live_observation(
        _snapshot(),
        evidence_dir=tmp_path / "evidence",
        pass_id="pass-1",
        store_root=tmp_path / "observations",
    )

    assert summary["status"] == "success"
    assert summary["eligible"] == 1
    assert (tmp_path / "evidence" / "opportunity-observation-summary.json").is_file()
