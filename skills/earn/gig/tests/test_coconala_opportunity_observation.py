from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SNAPSHOT_PATH = SCRIPTS / "application_snapshot.py"
MODULE_PATH = SCRIPTS / "coconala_opportunity_observation.py"
PARENT_PATH = SCRIPTS / "application_parent.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


snapshot_contract = _load(SNAPSHOT_PATH, "coconala_snapshot_for_observation_test")
observation = _load(MODULE_PATH, "coconala_observation_test")
parent = _load(PARENT_PATH, "application_parent_observation_test")


def _snapshot():
    collector = {
        "pass_id": "pass-observe-1",
        "lease_fence": {"task": "gig", "token": "a" * 32, "generation": 1},
        "observed_at": "2026-09-30T10:00:00Z",
        "objective": {
            "target_applications": 1,
            "max_applications": 2,
            "required_search_source_ids": ["single:new"],
        },
        "search_sources": [{
            "source_id": "single:new",
            "url": "https://coconala.com/requests?sort=new&recruiting=true",
            "page_index": 1,
            "card_request_ids": ["123"],
            "has_next": False,
            "exhausted": True,
            "screenshot_sha256": "a" * 64,
            "dom_sha256": "b" * 64,
        }],
        "request_details": [{
            "request_id": "123",
            "canonical_url": "https://coconala.com/requests/123",
            "title": "案件123",
            "category": "記事作成",
            "visible_text": "募集内容\n本文",
            "accepting_applications": True,
            "budget_min_jpy": 1000,
            "budget_max_jpy": 5000,
            "applicants_count": 0,
            "contracted_count": 0,
            "applicants": [],
            "application_questions": [],
            "observed_at": "2026-09-30T10:00:00Z",
        }],
        "already_applied_ids": [],
    }
    return snapshot_contract.build_envelope(collector)


def test_live_snapshot_observation_persists_planner_eligibility(tmp_path):
    result = observation.observe_coconala_opportunities(
        _snapshot(),
        {"decisions": [{"request_id": "123", "business_class": "submit_required"}]},
        store_root=tmp_path / "observations",
        evidence_ref="snapshot://coconala/pass-observe-1",
    )

    assert result["inspected"] == 1
    assert result["eligible"] == 1
    assert result["persisted"] == 1
    assert result["next_actions"] == [{
        "provider": "coconala",
        "opportunity_id": "request:123",
        "decision": "eligible",
        "next_action": "application_parent_commit",
    }]


def test_missing_planner_decision_is_held_without_apply_authorization(tmp_path):
    result = observation.observe_coconala_opportunities(
        _snapshot(),
        {"decisions": []},
        store_root=tmp_path / "observations",
        evidence_ref="snapshot://coconala/pass-observe-1",
    )

    assert result["eligible"] == 0
    assert result["held"] == 1
    assert result["next_actions"][0]["next_action"] == "await_planner_decision"


def test_invalid_decision_shape_fails_closed(tmp_path):
    with pytest.raises(observation.CoconalaObservationError, match="decisions_invalid"):
        observation.observe_coconala_opportunities(
            _snapshot(),
            {"decisions": "not-an-array"},
            store_root=tmp_path / "observations",
            evidence_ref="snapshot://coconala/pass-observe-1",
        )


def test_application_parent_live_boundary_writes_observation_summary(tmp_path):
    evidence_dir = tmp_path / "evidence"
    summary = parent.record_live_coconala_observation(
        _snapshot(),
        {"decisions": [{"request_id": "123", "business_class": "submit_required"}]},
        evidence_dir=evidence_dir,
        pass_id="pass-observe-1",
        store_root=tmp_path / "observations",
    )

    assert summary["eligible"] == 1
    assert (evidence_dir / "opportunity-observation-summary.json").is_file()


def test_application_parent_source_failure_is_explicit_and_read_only(tmp_path):
    evidence_dir = tmp_path / "evidence"

    parent.record_coconala_observation_source_failure(
        evidence_dir, "pass-source-failure", RuntimeError("session unavailable"),
    )

    payload = json.loads(
        (evidence_dir / "opportunity-observation-summary.json").read_text(encoding="utf-8")
    )
    assert payload["status"] == "source_collect_failed"
    assert payload["next_action"] == "retry_authenticated_snapshot_read_only"


def test_application_parent_platform_manifest_wake_writes_durable_summary(tmp_path):
    onboarding_path = tmp_path / "coconala-onboarding.json"
    states = (
        "preflight", "authenticated", "email_verified", "sms_verified",
        "seller_information", "identity_approved", "bank_registered",
        "launchd_readback", "storefront_listing_readback",
    )
    onboarding_path.write_text(json.dumps({
        "version": 2,
        "platform": "coconala",
        "states": {
            state: {
                "status": "complete" if state == "authenticated" else "pending",
                "evidence_sha256": "c" * 64 if state == "authenticated" else None,
            }
            for state in states
        },
    }), encoding="utf-8")

    payload = parent.record_live_coconala_platform_manifest_wake(
        evidence_dir=tmp_path / "evidence",
        pass_id="pass-platform-manifest-1",
        onboarding_path=onboarding_path,
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        observed_at="2026-09-30T10:01:00Z",
    )

    assert payload["status"] == "partial"
    assert payload["pass_id"] == "pass-platform-manifest-1"
    assert (tmp_path / "evidence" / "platform-manifest-wake.json").is_file()
