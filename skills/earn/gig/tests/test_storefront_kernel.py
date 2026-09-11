"""Pin the Coconala Storefront judgement kernel.

Run: python3 -m pytest skills/earn/gig/tests/test_storefront_kernel.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "storefront_kernel.py"
SPEC = importlib.util.spec_from_file_location("marketplace_storefront_kernel", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
kernel = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = kernel
SPEC.loader.exec_module(kernel)


# --- 1. allocate_portfolio: RETIRE a duplicate pair, KEEP a verified purchase --------------

def test_allocate_portfolio_retires_a_duplicate_and_keeps_a_verified_purchase(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "funnel-events.jsonl").write_text(json.dumps({
        "service_id": "3333333", "event_kind": "payment", "net_receipt_jpy": 1000,
    }) + "\n", encoding="utf-8")
    scorecard_path = tmp_path / "scorecard.json"
    scorecard_path.write_text(json.dumps({
        "portfolio_policy": {
            "version": 1, "slot_limit": 20, "minimum_views_for_retirement": 100,
            "short_term_zero_sales_can_retire": False,
            "retirement_mode": "recoverable_unpublish_before_delete",
            "replacement_candidates": [],
        },
        "services": [], "priority_backlog": [],
    }), encoding="utf-8")
    contracts = [
        {"service_id": "1111111", "service_version_sha256": "a" * 64},
        {"service_id": "2222222", "service_version_sha256": "b" * 64},
        {"service_id": "3333333", "service_version_sha256": "c" * 64},
    ]
    result = kernel.allocate_portfolio(
        state, contracts, {"cutoff_cursor": "official"}, scorecard_path, now=1,
        duplicate_listings=[{"service_ids": ["1111111", "2222222"]}],
    )
    by_id = {row["service_id"]: row for row in _read_allocations(state)}
    assert by_id["2222222"]["action"] == "RETIRE"
    assert by_id["2222222"]["reason"] == "duplicate_of_service_1111111"
    assert by_id["3333333"]["action"] == "KEEP"
    assert by_id["3333333"]["reason"] == "verified_purchase_or_payment"
    assert result["counts"]["RETIRE"] == 1


def _read_allocations(state_dir: Path) -> list[dict]:
    path = state_dir / "portfolio-allocations.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --- 2 & 3. mutation contract sealing and validation ---------------------------------------

def _unsigned_contract(**overrides) -> dict:
    contract = {
        "version": 1, "platform": "lancers", "service_id": "42",
        "precondition_listing_version_sha256": "a" * 64,
        "changed_field": "title", "before_value": "旧タイトル", "proposed_value": "新タイトル",
        "allowed_delta": ["data[Service][title]"], "rollback_value": "旧タイトル",
        "official_readback": {"field": "title"}, "success_metric": "inquiries",
        "observation_window_days": 14, "capability_family": "seo_writing",
        "evidence": ["evidence-1"],
    }
    contract.update(overrides)
    return contract


def test_seal_mutation_contract_digest_is_stable_and_changes_with_input():
    families = {"42": "seo_writing"}
    sealed_once = kernel.seal_mutation_contract(_unsigned_contract(), families, platform="lancers")
    sealed_again = kernel.seal_mutation_contract(_unsigned_contract(), families, platform="lancers")
    assert sealed_once["contract_sha256"] == sealed_again["contract_sha256"]
    assert len(sealed_once["contract_sha256"]) == 64

    changed = kernel.seal_mutation_contract(
        _unsigned_contract(evidence=["evidence-2"]), families, platform="lancers",
    )
    assert changed["contract_sha256"] != sealed_once["contract_sha256"]


def test_validate_mutation_contract_rejects_an_unknown_capability_family():
    contract = kernel.seal_mutation_contract(
        _unsigned_contract(), {"42": "seo_writing"}, platform="lancers",
    )
    try:
        kernel.validate_mutation_contract(contract, {"42": "a_different_family"}, platform="lancers")
    except RuntimeError as error:
        assert str(error) == "storefront_mutation_contract_invalid"
    else:
        raise AssertionError("expected storefront_mutation_contract_invalid")


# --- 4. official demand extraction and scoring ----------------------------------------------

SEARCH_BODY = """お届け日数
7,834 件中 1 - 60 件表示
おすすめ順
AI業務効率化システムを開発します
uta_lab_
5.0
(1)
10,000円
Excel/Python/GASで業務自動化します
株式会社SCコンサルティング
5.0
(11)
3,000円
"""


def test_extract_search_demand_derives_median_from_comparables():
    demand = kernel.extract_search_demand(SEARCH_BODY)
    assert demand["visible_result_count"] == 7834
    assert demand["comparables"] == [
        {"rating": 5.0, "review_count": 1, "display_price_jpy": 10000},
        {"rating": 5.0, "review_count": 11, "display_price_jpy": 3000},
    ]
    scored = kernel.score_demand_cluster(demand)
    assert scored["status"] == "known"
    assert scored["median_price_jpy"] == 10000


def test_score_demand_cluster_refuses_to_credit_demand_with_no_comparables():
    scored = kernel.score_demand_cluster({"visible_result_count": 9000, "comparables": []})
    assert scored["status"] == "unknown" and scored["score"] is None


# --- 5. in-flight draft recovery -------------------------------------------------------------

def test_families_with_unpublished_drafts_answers_several_families_from_one_read(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    ledger = state / "new-listing-drafts.jsonl"
    rows = [
        {"capability_family": "fam_a", "draft_service_id": "1001",
         "status": "draft_created", "public_effect": 0},
        {"capability_family": "fam_b", "draft_service_id": "1002",
         "status": "published", "public_effect": 1},
        {"capability_family": "fam_c", "draft_service_id": "1003",
         "status": "prepared", "public_effect": 0},
    ]
    ledger.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    stranded = kernel.families_with_unpublished_drafts(
        state, set(), observed_deleted_draft_ids=lambda _evidence_root: {"1003"},
    )
    assert stranded == {"fam_a": ("1001", 0)}  # fam_b published, fam_c deleted -- neither counts

    match = kernel.family_has_unpublished_draft(
        state, "fam_a", set(), observed_deleted_draft_ids=lambda _evidence_root: {"1003"},
    )
    assert match == "1001"


# --- 6. proposal-rejection guard --------------------------------------------------------------

def test_recent_rejections_cap_at_three_and_three_strike_compares_guard_identity(tmp_path):
    for suffix in ("スプレッドシート", "Dropbox", "ギガファイル", "firestorage"):
        kernel.append_proposal_rejection(
            tmp_path, gap_key="create:seo_writing",
            rejection=f"storefront_copy_names_prohibited_tool:{suffix}",
            proposed_value={"body": suffix}, pass_id="pass-" + suffix,
        )
    recent = kernel.recent_proposal_rejections(tmp_path, "create:seo_writing")
    assert len(recent) == 3
    assert recent[-1]["rejection"].endswith("firestorage")  # newest last

    # Same guard, three different offending terms in the message -- comparing the guard
    # identity (the prefix before ":") must still find one guard, not three.
    guard = kernel.three_strike_same_guard(recent)
    assert guard == "storefront_copy_names_prohibited_tool"

    mixed = recent[:-1] + [{"rejection": "storefront_replace_identity_invalid:x"}]
    assert kernel.three_strike_same_guard(mixed) is None


# --- 7. dependency direction: local kernel does not reach back into the DOM adapter -----------

def test_kernel_has_no_reach_back_into_storefront_adapter():
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "import storefront_direct" not in source
    assert "from storefront_direct" not in source
