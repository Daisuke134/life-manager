"""A measurement window must buy evidence; otherwise it must not lock the listing.

Run: python3 -m pytest skills/earn/gig/tests/test_storefront_fence.py
"""
import json
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import storefront_direct as sd  # noqa: E402

SERVICE_ID = "90000005"
NOW = int(datetime.now(timezone.utc).timestamp())


def analytics(tmp_path, views, status="known", *, observed_at=None, official=True,
              complete=True, source_url=None, window_override=None, tamper_key=False):
    observed_at = NOW if observed_at is None else observed_at
    observed_date = datetime.fromtimestamp(observed_at, timezone.utc).date()
    start = (observed_date - timedelta(days=30)).strftime("%Y/%m/%d") if complete else None
    end = observed_date.strftime("%Y/%m/%d") if complete else None
    window = window_override or {"start": start, "end": end, "complete": complete}
    metrics = {
        "impressions": {"status": "unavailable", "value": None,
                        "reason": "seller_success_subscription_required"},
        "views": {"status": status, "value": views if status == "known" else None},
        "purchases": {"status": "known", "value": 0},
        "gross_jpy": {"status": "unavailable", "value": None,
                      "reason": "service_analytics_does_not_expose_sales_amount"},
        "favorites": {"status": "known", "value": 0},
    }
    content_sha256 = hashlib.sha256(b"official synthetic analytics report").hexdigest()
    identity = {
        "service_id": SERVICE_ID, "window_start": window.get("start"),
        "window_end": window.get("end"), "metrics": metrics,
        "content_sha256": content_sha256,
    }
    snapshot_key = "storefront:analytics:v1:" + hashlib.sha256(json.dumps(
        identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    if tamper_key:
        snapshot_key += "-mismatch"
    path = tmp_path / "analytics.jsonl"
    path.write_text(json.dumps({
        "version": 1, "snapshot_key": snapshot_key,
        "service_id": SERVICE_ID, "observed_at_epoch": observed_at,
        "official": official,
        "source_url": source_url or f"https://coconala.com/mypage/analytics/{SERVICE_ID}",
        "window": window, "metrics": metrics, "content_sha256": content_sha256,
    }) + "\n", encoding="utf-8")
    return path


def snapshot(path):
    return json.loads(path.read_text(encoding="utf-8").splitlines()[-1])


def _prepare_candidate(root, fresh_snapshots):
    policy = root / "scorecard.json"
    policy.write_text(json.dumps({
        "portfolio_policy": {"version": 1, "minimum_views_for_measurement": 100},
        "priority_backlog": [{
            "priority": 1, "service_id": SERVICE_ID, "field": "body", "before": 1,
            "success_metric": "inquiries", "reason": "bounded service outcome test",
        }],
    }), encoding="utf-8")
    contracts = [{"service_id": SERVICE_ID, "service_version_sha256": "a" * 64}]
    mutation = [{
        "service_id": SERVICE_ID, "changed_field": "body",
        "precondition_listing_version_sha256": "a" * 64,
        "contract_sha256": "b" * 64, "observation_window_days": 14,
        "proposed_value": "fixed scoped result",
    }]
    return sd._prepare_next_hypothesis(
        policy, root / "effects.jsonl", root / "outcomes.jsonl", contracts, NOW,
        mutation_contracts=mutation, fresh_snapshots=fresh_snapshots,
    )


def families_fixture(tmp_path, service_id=SERVICE_ID):
    """Write the smallest valid capability-family map needed by the loader."""
    path = tmp_path / "families.json"
    path.write_text(json.dumps({
        "version": 1,
        "service_families": {str(service_id): "synthetic_automation"},
        "families": {"synthetic_automation": {
            "inclusions": ["合成サービスの自動化"],
            "deliverables": ["合成成果物"],
            "required_inputs": ["合成入力"],
            "principles": ["合成原則"],
            "answer_patterns": [{
                "intent": "scope", "triggers": ["範囲"], "response": "範囲を確認します。"
            }],
        }},
    }), encoding="utf-8")
    return path


def test_a_window_that_cannot_reach_the_minimum_is_not_worth_waiting_for(tmp_path):
    # 93 views per 30 days projects to 43 in a 14-day window: far under the 100 minimum.
    result = sd._measurement_feasible([snapshot(analytics(tmp_path, 93))], SERVICE_ID, 14, 100, NOW)
    assert result["status"] == "known"
    assert result["projected_window_views"] == 43
    assert result["feasible"] is False
    assert result["basis"] == "rolling_30d_view_rate_projected_onto_window"


def test_discretionary_mutations_wait_until_their_experiment_has_enough_exposure(tmp_path):
    def prepare(root, views, status="known", **snapshot):
        root.mkdir()
        path = analytics(root, views, status, **snapshot)
        current = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
        return _prepare_candidate(root, [current])

    low = prepare(tmp_path / "low", 50)
    assert low["executable"] is False
    assert low["guard_reason"] == "metric_unmeasurable_insufficient_exposure"
    assert low["measurement_feasibility"]["projected_window_views"] == 23

    sufficient = prepare(tmp_path / "sufficient", 300)
    assert sufficient["executable"] is True
    assert sufficient["measurement_feasibility"]["projected_window_views"] == 140

    unknown = prepare(tmp_path / "unknown", 0, status="unavailable")
    assert unknown["executable"] is False
    assert unknown["guard_reason"] == "measurement_exposure_unknown"


@pytest.mark.parametrize("snapshot", [
    {"official": False},
    {"complete": False},
    {"window_override": {"start": "not-a-date", "end": "2026/99/99", "complete": True}},
    {"source_url": "https://coconala.com/mypage/analytics/90000006"},
    {"observed_at": NOW - 3601},
    {"observed_at": NOW + 1},
    {"tamper_key": True},
])
def test_discretionary_preflight_rejects_untrusted_or_stale_analytics(tmp_path, snapshot):
    result = _prepare_with_snapshot(tmp_path / "case", 300, snapshot)
    assert result["executable"] is False
    assert result["guard_reason"] == "measurement_exposure_unknown"
    assert result["measurement_feasibility"]["status"] == "unknown"


def _prepare_with_snapshot(root, views, snapshot):
    root.mkdir()
    path = analytics(root, views, **snapshot)
    current = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    return _prepare_candidate(root, [current])


def test_current_readback_keeps_unchanged_deduped_history_fresh(tmp_path):
    path = analytics(tmp_path, 300, observed_at=NOW - 3601)
    history = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    current_readback = {**history, "observed_at_epoch": NOW}

    result = _prepare_candidate(tmp_path, [current_readback])

    assert result["executable"] is True
    assert result["measurement_feasibility"]["status"] == "known"


def test_preflight_does_not_fallback_to_persisted_data_without_this_runs_readback(tmp_path):
    analytics(tmp_path, 300, observed_at=NOW)

    result = _prepare_candidate(tmp_path, [])

    assert result["executable"] is False
    assert result["guard_reason"] == "measurement_exposure_unknown"


def test_stale_offer_correction_is_not_an_exposure_gated_experiment(tmp_path):
    analytics(tmp_path, 15)
    policy = tmp_path / "scorecard.json"
    policy.write_text(json.dumps({"priority_backlog": []}), encoding="utf-8")
    contracts = [{"service_id": SERVICE_ID, "service_version_sha256": "a" * 64}]

    refresh = sd._prepare_next_hypothesis(
        policy, tmp_path / "effects.jsonl", tmp_path / "outcomes.jsonl", contracts,
        1_800_000_000,
        offer_refresh=[{
            "service_id": SERVICE_ID, "family": "sns_operations",
            "offer_field": "body", "offer_digest": "stale-offer",
        }],
    )

    assert refresh["offer_digest"] == "stale-offer"
    assert refresh["guard_reason"] == "proposal_contract_required"
    assert "measurement_feasibility" not in refresh


def test_a_listing_with_real_traffic_keeps_its_window(tmp_path):
    result = sd._measurement_feasible([snapshot(analytics(tmp_path, 900))], SERVICE_ID, 14, 100, NOW)
    assert result["projected_window_views"] == 420 and result["feasible"] is True


def test_missing_or_unknown_official_views_stay_unknown(tmp_path):
    assert sd._measurement_feasible(None, SERVICE_ID, 14, 100, NOW)["status"] == "unknown"
    unknown = sd._measurement_feasible(
        [snapshot(analytics(tmp_path, 0, status="unavailable"))], SERVICE_ID, 14, 100, NOW,
    )
    assert unknown["status"] == "unknown" and unknown["reason"] == "no_official_views_for_service"


def test_the_policy_states_the_threshold_it_enforces(tmp_path):
    policy_path = tmp_path / "scorecard.json"
    policy_path.write_text(json.dumps({"portfolio_policy": {
        "version": 1,
        "minimum_views_for_measurement": 100,
        "short_term_zero_sales_can_retire": False,
    }}), encoding="utf-8")
    policy = sd._portfolio_policy(policy_path)
    assert policy["minimum_views_for_measurement"] == 100
    # Freeing a listing must never be allowed to look like a retirement decision.
    assert policy["short_term_zero_sales_can_retire"] is False



def test_a_stale_hand_authored_contract_is_skipped_not_fatal(tmp_path):
    """One listing moving on must not stop the wake for every other listing."""
    import pytest

    root = tmp_path / "contracts"
    root.mkdir()
    service_id = "90000002"
    (root / f"{service_id}.json").write_text(json.dumps({
        "version": 1, "platform": "coconala", "service_id": service_id,
        "public_url": f"https://coconala.com/services/{service_id}",
        "service_version_sha256": "a" * 64,
        "offer": {"base_price_jpy": 6000, "required_inputs": ["x"]},
        "inquiry_playbook": {"answer_patterns": [
            {"intent": "i", "triggers": ["t"], "response": "r"}]},
    }), encoding="utf-8")
    observed = [{"service_id": service_id,
                 "public_url": f"https://coconala.com/services/{service_id}",
                 "service_version_sha256": "b" * 64, "price_jpy": 6000,
                 "title": "合成サービスを支援します", "state": "公開中",
                 "category": "合成カテゴリ", "public_text": "合成内容"}]

    families = families_fixture(tmp_path, service_id)
    loaded = sd._load_listing_contracts(root, observed, families_path=families)
    # The stale hand-authored file is recorded rather than raised...
    assert sd._stale_listing_contracts
    assert sd._stale_listing_contracts[0]["service_id"] == service_id
    assert sd._stale_listing_contracts[0]["reason"] == "listing_contract_binding_stale"
    # ...and the listing still gets a contract, derived from its capability family, bound to
    # the version actually observed rather than the one the stale file remembered.
    derived = [row for row in loaded if row["service_id"] == service_id]
    assert derived and derived[0]["service_version_sha256"] == "b" * 64


def test_a_published_generated_service_gets_a_reply_contract_without_private_family_config(tmp_path):
    root = tmp_path / "contracts"
    root.mkdir()
    families = families_fixture(tmp_path, "90000001")
    created = tmp_path / "new-listing-drafts.jsonl"
    created.write_text(json.dumps({
        "status": "prepared", "public_effect": 0, "draft_service_id": "4371816",
        "capability_family": "ai-automation-builder",
    }) + "\n", encoding="utf-8")
    observed = [{
        "service_id": "4371816", "public_url": "https://coconala.com/services/4371816",
        "service_version_sha256": "c" * 64, "price_jpy": 30000,
        "title": "AIで定型業務1件を自動化します", "state": "公開中",
        "category": "生成AI", "public_text": "サービス内容\n購入にあたってのお願い",
    }]

    loaded = sd._load_listing_contracts(
        root, observed, families_path=families, created_path=created,
    )

    contract = loaded[0]
    assert contract["service_id"] == "4371816"
    assert contract["generated_from_family"] == "ai-automation-builder"
    assert contract["offer"]["base_price_jpy"] == 30000
    assert contract["inquiry_playbook"]["required_clarifications"]


def test_prepared_and_published_are_distinct_events_for_the_same_contract(tmp_path):
    path = tmp_path / "drafts.jsonl"
    digest = "a" * 64
    prepared = {"contract_sha256": digest, "status": "prepared",
                "draft_event_key": f"{digest}:prepared"}
    published = {"contract_sha256": digest, "status": "published",
                 "draft_event_key": f"{digest}:published"}
    assert sd._append_key_once(path, "draft_event_key", prepared) is True
    assert sd._append_key_once(path, "draft_event_key", published) is True
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
