"""A listing the platform would withdraw is repaired before anything is optimised."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import storefront_direct  # noqa: E402

SERVICE = "91000003"
VIOLATION = {"service_id": SERVICE, "prohibited_terms": ["Googleドキュメント"],
             "content_sha256": "a" * 64}


def _scorecard(tmp_path: Path) -> Path:
    path = tmp_path / "scorecard.json"
    path.write_text(json.dumps({
        "portfolio_policy": {"version": 1, "minimum_views_for_measurement": 100},
        "priority_backlog": [
            {"service_id": "91000005", "field": "body", "success_metric": "inquiries", "reason": "gap"},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    return path


def _effects(tmp_path: Path, now: int) -> Path:
    path = tmp_path / "effects.jsonl"
    path.write_text(json.dumps({
        "status": "accepted", "effect": 1, "service_id": SERVICE, "changed_field": "body",
        "experiment_key": "k", "accepted_at_epoch": now - 3600,
    }) + "\n", encoding="utf-8")
    return path


def _contracts():
    return [{"service_id": SERVICE, "service_version_sha256": "b" * 64},
            {"service_id": "91000005", "service_version_sha256": "c" * 64}]


def test_a_violating_listing_is_selected_even_inside_its_cooldown(tmp_path):
    now = 1_787_000_000
    picked = storefront_direct._prepare_next_hypothesis(
        _scorecard(tmp_path), _effects(tmp_path, now), tmp_path / "outcomes.jsonl",
        _contracts(), now, [], [VIOLATION])
    assert picked["service_id"] == SERVICE
    assert picked["field"] == "body"
    assert picked["compliance_repair"] is True
    assert "Googleドキュメント" in picked["reason"]


def test_without_a_violation_the_cooldown_still_holds(tmp_path):
    now = 1_787_000_000
    picked = storefront_direct._prepare_next_hypothesis(
        _scorecard(tmp_path), _effects(tmp_path, now), tmp_path / "outcomes.jsonl",
        _contracts(), now, [], [])
    assert picked is None or picked["service_id"] != SERVICE


def test_a_repair_is_not_held_behind_the_executor_cooldown(tmp_path, monkeypatch):
    now = 1_787_000_000
    contract = {
        "service_id": SERVICE, "changed_field": "body", "contract_sha256": "d" * 64,
        "before_value": "旧本文 Googleドキュメント", "proposed_value": "新本文 Word形式",
        "success_metric": "inquiries", "observation_window_days": 14,
    }
    monkeypatch.setattr(storefront_direct, "_load_capability_families", lambda path: ({}, {}))
    monkeypatch.setattr(storefront_direct, "_validate_mutation_contract", lambda c, m: None)
    hypothesis = {"service_id": SERVICE, "field": "body", "mutation_contract_sha256": "d" * 64,
                  "executable": True, "reason": "compliance", "compliance_repair": True}
    decided = storefront_direct._text_judgement(hypothesis, contract, _effects(tmp_path, now), now)
    assert decided["decision"] == "change"

    held = storefront_direct._text_judgement(
        {**hypothesis, "compliance_repair": False}, contract, _effects(tmp_path, now), now)
    assert held["no_op_reason"] == "service_cooldown_7d"
