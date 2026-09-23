import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from websocket import WebSocketException, WebSocketTimeoutException


SCRIPT = Path(__file__).parents[1] / "scripts" / "revenue_cli.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("affiliate_revenue", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RevenueCliTest(unittest.TestCase):
    def test_month_bucket_rows_for_one_link_are_aggregated(self):
        link = "https://try.elevenlabs.io/campaign-one"
        candidate = {
            "placement_id": "campaign-one",
            "link_fingerprints": sorted(MODULE.link_fingerprints(link)),
        }
        rows = [
            {
                "link_path": link,
                "click_created_at_month": "2026-08-01",
                "click_count": 3,
                "unique_click_count": 2,
            },
            {
                "link_path": link,
                "click_created_at_month": "2026-09-01",
                "click_count": 4,
                "unique_click_count": 3,
            },
        ]

        result = MODULE.aggregate_link_rows(
            rows, candidate, secondary_grouping="click_created_at_month",
        )

        self.assertEqual(result["click_count"], 7)
        self.assertEqual(result["unique_click_count"], 5)
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["aggregation_state"], "MONTH_BUCKETS_AGGREGATED")
        self.assertEqual(
            result["unique_click_count_state"], "OBSERVED_MONTH_BUCKET_SUM",
        )

    def test_multiple_distinct_links_remain_ambiguous(self):
        first = "https://try.elevenlabs.io/campaign-one"
        second = "https://try.elevenlabs.io/campaign-two"
        candidate = {
            "placement_id": "ambiguous",
            "link_fingerprints": sorted(
                MODULE.link_fingerprints(first) | MODULE.link_fingerprints(second)
            ),
        }
        rows = [
            {
                "link_path": first, "click_created_at_month": "2026-09-01",
                "click_count": 1, "unique_click_count": 1,
            },
            {
                "link_path": second, "click_created_at_month": "2026-08-01",
                "click_count": 1, "unique_click_count": 1,
            },
        ]

        with self.assertRaisesRegex(MODULE.RevenueError, "attribution is ambiguous"):
            MODULE.aggregate_link_rows(
                rows, candidate, secondary_grouping="click_created_at_month",
            )

    def test_rolling_window_change_keeps_delta_unknown(self):
        result = MODULE.link_count_delta(
            current=2,
            previous=5,
            current_window={"start_date": "new-start", "end_date": "new-end"},
            previous_window={"start_date": "old-start", "end_date": "old-end"},
        )

        self.assertEqual(result, {
            "baseline": None,
            "delta": None,
            "state": "WINDOW_CHANGED",
        })

    def test_same_window_count_regression_still_fails_closed(self):
        window = {"start_date": "same-start", "end_date": "same-end"}
        with self.assertRaisesRegex(MODULE.RevenueError, "count regressed"):
            MODULE.link_count_delta(
                current=2, previous=5,
                current_window=window, previous_window=window,
            )

    def test_failure_type_is_redacted_and_actionable(self):
        self.assertEqual(
            MODULE.failure_type(MODULE.RevenueError("PartnerStack authentication is required")),
            "AUTH_REQUIRED",
        )
        self.assertEqual(
            MODULE.failure_type(MODULE.RevenueError("PartnerStack metrics did not become ready")),
            "METRICS_NOT_READY",
        )
        self.assertEqual(
            MODULE.failure_type(MODULE.RevenueError("expected one provider tab, found 2")),
            "TAB_INVARIANT",
        )
        self.assertEqual(
            MODULE.failure_type(MODULE.RevenueError("provider report schema is incomplete")),
            "PROVIDER_SCHEMA_ERROR",
        )
        self.assertEqual(MODULE.failure_type(OSError("private path")), "RUNTIME_IO")
        self.assertEqual(
            MODULE.failure_type(WebSocketTimeoutException("private timeout detail")),
            "BROWSER_TRANSPORT",
        )
        self.assertEqual(
            MODULE.failure_type(WebSocketException("private transport detail")),
            "BROWSER_TRANSPORT",
        )

    def test_legacy_slug_merges_into_canonical_dedicated_placement(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            for name in ("program-links", "content", "owned-publications"):
                (state / name).mkdir(parents=True)
            (state / "program-links" / "elevenlabs-en-1.json").write_text(json.dumps({
                "placement": "elevenlabs-en-1", "state": "VERIFIED",
                "provider_link_key": "link-1", "link_fingerprints": ["f" * 64],
            }))
            (state / "content" / "elevenlabs-plans-for-solo-creators.json").write_text(
                json.dumps({
                    "slug": "elevenlabs-plans-for-solo-creators",
                    "readback_links": ["https://try.elevenlabs.io/example"],
                })
            )
            (state / "owned-publications" / "elevenlabs-plans-for-solo-creators.json").write_text(
                json.dumps({"state": "LIVE", "public_url": "https://example.test/plans"})
            )

            candidates = MODULE.placement_candidates(state)

            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["placement_id"], "elevenlabs-en-1")
            self.assertEqual(candidates[0]["provider_link_key"], "link-1")
            self.assertEqual(candidates[0]["public_url"], "https://example.test/plans")

    def test_placement_economics_separates_api_estimate_from_actual_cash(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "campaign-publications").mkdir(parents=True)
            (state / "program-links").mkdir(parents=True)
            (state / "telemetry").mkdir(parents=True)
            (state / "distribution-metrics").mkdir(parents=True)
            (state / "campaign-publications" / "alpha-en.json").write_text(json.dumps({
                "plan_id": "alpha-en", "placement_id": "alpha-en-1",
                "slug": "alpha", "state": "X_LIVE",
                "owned_url": "https://example.com/alpha",
            }))
            (state / "program-links" / "alpha-en-1.json").write_text(json.dumps({
                "placement": "alpha-en-1", "state": "VERIFIED",
                "provider_link_key": "link-1", "link_fingerprints": ["f" * 64],
            }))
            (state / "telemetry" / "agent-usage.jsonl").write_text(json.dumps({
                "task_label": "alpha-en-sourcehash", "measurement": "provider_reported",
                "tokens": {"total": 1200}, "provider_cost_usd": 0.12,
                "cost_basis": "api_equivalent_estimate",
            }) + "\n")
            (state / "distribution-metrics" / "devto.json").write_text(json.dumps({
                "articles": [{"placement_id": "alpha-en-1", "page_views_count": 0}],
            }))
            (state / "provider-reports" / "partnerstack-links").mkdir(parents=True)
            (state / "provider-reports" / "partnerstack-links" / "latest.json").write_text(
                json.dumps({"observed_at": "provider-time", "placements": [{
                    "placement_id": "alpha-en-1", "current_click_count": 3,
                    "delta_click_count": 1, "current_unique_click_count": 2,
                    "delta_unique_click_count": 1,
                    "unique_click_count_state": "OBSERVED",
                }]})
            )

            row = MODULE.build_placement_ledger(state)["placements"][0]

            self.assertEqual(row["cost"]["model_usage"]["total_tokens"], 1200)
            self.assertEqual(row["cost"]["model_usage"]["api_equivalent_estimate_usd"], 0.12)
            self.assertIsNone(row["cost"]["model_actual_billed_usd"])
            self.assertEqual(row["unit_economics"]["actual_net_profit_state"], "UNKNOWN_COST")
            self.assertEqual(row["unit_economics"]["exposure_denominator_state"], "INSUFFICIENT_DENOMINATOR")
            self.assertIsNone(row["exposure"]["x_impressions"])
            self.assertEqual(row["exposure"]["x_impressions_state"], "UNKNOWN")
            self.assertIsNone(row["exposure"]["owned_page_visits"])
            self.assertEqual(row["exposure"]["owned_page_visits_state"], "UNKNOWN")
            self.assertEqual(row["provider_clicks"]["count"], 3)
            self.assertEqual(row["provider_clicks"]["unique_count"], 2)
            self.assertEqual(row["provider_clicks"]["unique_state"], "OBSERVED")

    def test_classifies_tax_and_provider_setup_without_bank_data(self):
        readiness = MODULE.payout_readiness(
            "納税登録が必要\n出金するための税金情報を記入する\n"
            "口座振替、PayPal、Stripeからお選びください"
        )
        self.assertEqual(readiness, {
            "payout_readiness": "PAYOUT_BLOCKED_BY_TAX_SETUP",
            "tax_information_state": "REQUIRED",
            "payment_provider_state": "SELECTION_REQUIRED",
        })

    def test_japanese_overview_values_preserve_unknown_money_states(self):
        cards = {
            "クリック数": "1", "登録数": "0", "有料会員登録": "0",
            "コンバージョン率": "0%", "収益": "$0.00",
            "支払い待ちのコミッション": "$0.00",
            "支払い済みコミッション": "$0.00",
            "クリックあたりの収益": "$0.00",
        }
        metrics = MODULE.parse_cards(cards)
        self.assertEqual(metrics["clicks"], 1)
        self.assertEqual(metrics["pending_minor"], 0)
        self.assertIsNone(metrics["approved_minor"])
        self.assertIsNone(metrics["reversed_minor"])

    def test_later_observation_preserves_baseline_and_reports_delta(self):
        baseline = MODULE.parse_cards({
            "Clicks": "1", "Signups": "0", "Paid signups": "0",
            "Conversion rate": "0%", "Revenue": "$0.00",
            "Commissions pending payment": "$0.00",
            "Commissions paid": "$0.00", "Earnings per click": "$0.00",
        })
        first = MODULE.build_receipt(baseline, {}, "first")
        current = dict(baseline, clicks=3, signups=1)
        later = MODULE.build_receipt(current, first, "later")
        self.assertEqual(later["baseline_metrics"], baseline)
        self.assertEqual(later["baseline_observed_at"], "first")
        self.assertEqual(later["delta_from_baseline"]["clicks"], 2)
        self.assertEqual(later["delta_from_baseline"]["signups"], 1)

    def test_extracts_value_when_comparison_labels_surround_click_total(self):
        text = """クリック数
Last 30 days
Previous 30 days
クリック数
Total
0
クリック数
1
100%
登録数
0
有料会員登録
0
コンバージョン率
0%
収益
$0.00
支払い待ちのコミッション
$0.00
支払い済みコミッション
$0.00
クリックあたりの収益
$0.00"""
        cards = MODULE.extract_cards(text)
        self.assertEqual(MODULE.parse_cards(cards)["clicks"], 1)

    def test_report_schema_requires_commission_key_and_attribution_fields(self):
        text = "\n".join(aliases[0] for aliases in MODULE.COMMISSION_FIELDS.values())
        fields = MODULE.present_fields(text, MODULE.COMMISSION_FIELDS)
        self.assertIn("reward_key", fields)
        self.assertIn("sub_id_1", fields)
        self.assertNotIn("transaction_id", fields)

    def test_bundle_contract_normalizes_scheduled_without_customer_pii(self):
        row = {
            "reward_key": "reward-1", "reward_status": "scheduled",
            "commission_amount": "22.50", "created_at_date": "2026-08-16",
            "customer_email": "private@example.com", "sub_id_1": "placement-1",
        }
        normalized = MODULE.normalize_commission_row(row)
        self.assertEqual(normalized["provider_transaction_id"], "reward-1")
        self.assertEqual(normalized["status"], "approved")
        self.assertEqual(normalized["net_commission_minor"], 2250)
        self.assertNotIn("customer_email", normalized)
        self.assertNotIn("link", normalized["attribution"])

        placement = {
            "placement_id": "placement-1", "public_url": "https://example.com/article",
            "link_fingerprints": sorted(MODULE.link_fingerprints("https://try.elevenlabs.io/example")),
        }
        raw = dict(row, link_path="/example")
        normalized["placement"] = MODULE.resolve_attribution(raw, [placement])
        self.assertEqual(normalized["placement"]["state"], "MATCHED")
        self.assertEqual(normalized["placement"]["match_basis"], ["SUB_ID", "LINK_FINGERPRINT"])
        transition = MODULE.build_transition(normalized, "source-hash", "observed")
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            self.assertTrue(MODULE.append_unique(ledger, transition, ("transition_id",)))
            self.assertFalse(MODULE.append_unique(ledger, transition, ("transition_id",)))
            self.assertEqual(len(ledger.read_text().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
