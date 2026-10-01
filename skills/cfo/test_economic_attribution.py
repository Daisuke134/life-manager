"""Focused contract tests for receipt-level CFO economic attribution."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

sys.path.insert(0, str(Path(__file__).parent))
import economic_attribution as m  # noqa: E402
from skills.cfo.adapters import agent_economy_investment as adapter


SNAPSHOT = "2026-10-01T00:00:00Z"
TRAILING_START = "2026-09-24T00:00:00Z"


def receipt(receipt_id="stripe:txn_1", *, loop_id="self-build", provider="stripe",
            occurred_at="2026-09-30T12:00:00Z", settled_at="2026-09-30T12:05:00Z",
            verification_state="verified", currency="USD", revenue_class="one_time",
            components=None):
    return {
        "schema_version": m.SCHEMA_VERSION,
        "record_type": "receipt",
        "receipt_id": receipt_id,
        "product_loop_id": loop_id,
        "provider": provider,
        "currency": currency,
        "occurred_at": occurred_at,
        "settled_at": settled_at,
        "verification_state": verification_state,
        "revenue_class": revenue_class,
        "evidence_refs": [f"{provider}://receipts/{receipt_id}"],
        "components": components or [
            {"category": "settled_external_revenue", "amount": "10.10"},
        ],
    }


def liquid_balance(snapshot_id="stripe:balance-1", *, account_id="operating",
                   provider="stripe", currency="USD", amount="300",
                   verification_state="verified",
                   observed_at=SNAPSHOT):
    return {
        "schema_version": m.SCHEMA_VERSION,
        "record_type": "liquid_balance",
        "snapshot_id": snapshot_id,
        "account_id": account_id,
        "provider": provider,
        "currency": currency,
        "amount": amount,
        "observed_at": observed_at,
        "verification_state": verification_state,
        "evidence_refs": [f"{provider}://balances/{snapshot_id}"],
    }


def subscription_snapshot(snapshot_id="stripe:sub_1:20260930", *, subscription_id="stripe:sub_1",
                          loop_id="self-build", provider="stripe", currency="USD",
                          amount="30", status="active", verification_state="verified",
                          observed_at=SNAPSHOT):
    return {
        "schema_version": m.SCHEMA_VERSION,
        "record_type": "subscription_snapshot",
        "snapshot_id": snapshot_id,
        "subscription_id": subscription_id,
        "product_loop_id": loop_id,
        "provider": provider,
        "currency": currency,
        "normalized_monthly_amount": amount,
        "normalization_basis": "provider_monthly",
        "status": status,
        "observed_at": observed_at,
        "verification_state": verification_state,
        "evidence_refs": [f"{provider}://subscriptions/{subscription_id}"],
    }


def coverage(loop_id, projection, *, state="complete", reason=None,
             covered_categories=None, observed_at=SNAPSHOT):
    default_categories = (["mrr", "liquid_balance"] if projection == "as_of"
                          else list(m.COUNTED_CATEGORIES))
    row = {
        "schema_version": m.SCHEMA_VERSION,
        "record_type": "coverage",
        "product_loop_id": loop_id,
        "source_id": f"{loop_id}-financial-record",
        "projection": projection,
        "window_start": TRAILING_START if projection == "trailing" else None,
        "window_end": SNAPSHOT,
        "coverage_state": state,
        "reason": reason,
        "covered_categories": (default_categories if covered_categories is None
                               else covered_categories),
        "observed_at": observed_at,
        "evidence_refs": [f"lm-cfo://coverage/{loop_id}/{projection}"],
    }
    return row


def complete_coverage():
    return [coverage(loop_id, projection)
            for loop_id in m.PRODUCT_LOOP_IDS
            for projection in ("historical", "trailing", "as_of")]


class EconomicAttributionContractTest(unittest.TestCase):
    def project(self, receipts, coverage_rows=None):
        rows = [*receipts, *(complete_coverage() if coverage_rows is None else coverage_rows)]
        return m.project(rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START)

    def test_valid_settled_external_revenue_uses_same_rule_for_loop_and_company(self):
        result = self.project([receipt()])
        expected = {
            "status": "verified",
            "unknown_categories": [],
            "settled_external_revenue": "10.1",
            "refund": "0",
            "provider_fee": "0",
            "model_cost": "0",
            "tool_cost": "0",
            "browser_cost": "0",
            "infra_cost": "0",
            "payment_fee": "0",
            "other_measured_cost": "0",
            "total_cost": "0",
            "net": "10.1",
        }
        self.assertEqual(result["historical"]["loops"]["self-build"]["currencies"]["USD"], expected)
        self.assertEqual(result["historical"]["company"]["currencies"]["USD"], expected)
        self.assertEqual(result["historical"]["company"]["status"], "verified")

    def test_b5_to_b0_preserves_two_26_digit_decimal_operands_exactly(self):
        fixture_path = Path(__file__).parent / "fixtures" / "economic_attribution" / "investment-realized.json"
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        amount = "99999999999999999999999999.99"
        for outcome in payload["outcomes"]:
            outcome["fee_usd"] = "0"
            outcome["slippage_usd"] = "0"
        for outcome in payload["outcomes"][1:]:
            outcome["realized_pnl_usd"] = amount
            outcome["pnl_basis"] = "net_after_fee_slippage"

        b5_rows = adapter.adapt_investment(
            payload, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        result = m.project(
            [*b5_rows, *complete_coverage()],
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
        )
        usd = result["historical"]["company"]["currencies"]["USD"]
        expected = "199999999999999999999999999.98"
        self.assertEqual(usd["settled_external_revenue"], expected)
        self.assertEqual(usd["total_cost"], "0")
        self.assertEqual(usd["net"], expected)

    def test_every_non_revenue_class_is_preserved_and_excluded(self):
        categories = (
            "pending_revenue", "payout", "owner_deposit", "self_payment",
            "internal_transfer", "token_appreciation", "unrealized_investment_pnl",
            "fundraising",
        )
        rows = []
        for index, category in enumerate(categories):
            state = "pending" if category == "pending_revenue" else "verified"
            settled_at = None if category == "pending_revenue" else "2026-09-30T12:05:00Z"
            rows.append(receipt(
                f"provider:excluded-{index}", provider="provider", settled_at=settled_at,
                verification_state=state,
                revenue_class="monthly_recurring" if category == "pending_revenue" else None,
                components=[{"category": category, "amount": "12.34"}],
            ))
        result = self.project(rows)["historical"]["company"]
        self.assertEqual(result["currencies"], {})
        self.assertEqual({row["category"] for row in result["excluded"]}, set(categories))
        self.assertEqual({row["provider"] for row in result["excluded"]}, {"provider"})
        self.assertEqual(result["status"], "zero")

    def test_refund_and_measured_costs_are_subtracted_once_per_receipt(self):
        components = [
            {"category": "settled_external_revenue", "amount": "100"},
            {"category": "refund", "amount": "10"},
            {"category": "provider_fee", "amount": "2"},
            {"category": "model_cost", "amount": "1"},
            {"category": "tool_cost", "amount": "1"},
            {"category": "browser_cost", "amount": "1"},
            {"category": "infra_cost", "amount": "3"},
            {"category": "payment_fee", "amount": "1"},
            {"category": "other_measured_cost", "amount": "3"},
        ]
        usd = self.project([receipt(components=components)])["historical"]["company"]["currencies"]["USD"]
        self.assertEqual(usd["refund"], "10")
        self.assertEqual(usd["tool_cost"], "1")
        self.assertEqual(usd["browser_cost"], "1")
        self.assertEqual(usd["total_cost"], "12")
        self.assertEqual(usd["net"], "78")

    def test_duplicate_receipt_is_zero_addition(self):
        row = receipt()
        result = self.project([row, dict(row)])
        self.assertEqual(result["duplicate_receipts"], [
            {"provider": "stripe", "receipt_id": "stripe:txn_1"},
        ])
        self.assertEqual(
            result["historical"]["company"]["currencies"]["USD"]["settled_external_revenue"],
            "10.1",
        )

    def test_same_receipt_reexecution_is_idempotent(self):
        row = receipt()
        once = self.project([row])
        replayed = self.project([row, dict(row), dict(row)])
        self.assertEqual(once["historical"], replayed["historical"])
        self.assertEqual(once["trailing"], replayed["trailing"])

    def test_conflicting_duplicate_receipt_is_rejected(self):
        first = receipt()
        changed = receipt(components=[{"category": "settled_external_revenue", "amount": "99"}])
        with self.assertRaisesRegex(m.ContractError, "receipt_conflict"):
            self.project([first, changed])

    def test_invalid_or_missing_receipt_fields_fail_closed(self):
        cases = []
        missing = receipt()
        del missing["receipt_id"]
        cases.append(missing)
        cases.append(receipt(loop_id="not-a-product-loop"))
        cases.append(receipt(occurred_at="2026-09-30T12:00:00"))
        cases.append(receipt(components=[{"category": "settled_external_revenue", "amount": 10.1}]))
        no_evidence = receipt()
        no_evidence["evidence_refs"] = []
        cases.append(no_evidence)
        cases.append(receipt(settled_at=None))
        for invalid in cases:
            with self.subTest(invalid=invalid):
                with self.assertRaises(m.ContractError):
                    m.validate_record(invalid)

    def test_currency_totals_remain_separate_without_conversion(self):
        result = self.project([
            receipt("stripe:usd", currency="USD"),
            receipt("stripe:jpy", currency="JPY", components=[
                {"category": "settled_external_revenue", "amount": "1000"},
            ]),
        ])["historical"]["company"]["currencies"]
        self.assertEqual(set(result), {"JPY", "USD"})
        self.assertNotIn("converted", json.dumps(result))

    def test_mrr_uses_only_latest_verified_active_subscription_snapshot(self):
        rows = [
            receipt("stripe:monthly", revenue_class="monthly_recurring", components=[
                {"category": "settled_external_revenue", "amount": "30"},
            ]),
            receipt(
                "stripe:monthly-prior", revenue_class="monthly_recurring",
                occurred_at="2026-08-31T12:00:00Z", settled_at="2026-08-31T12:05:00Z",
                components=[{"category": "settled_external_revenue", "amount": "30"}],
            ),
            receipt("stripe:quarterly", revenue_class="other_recurring", components=[
                {"category": "settled_external_revenue", "amount": "40"},
            ]),
            receipt("stripe:one-time", revenue_class="one_time", components=[
                {"category": "settled_external_revenue", "amount": "100"},
            ]),
            receipt(
                "stripe:pending", revenue_class="monthly_recurring", settled_at=None,
                verification_state="pending", components=[
                    {"category": "pending_revenue", "amount": "50"},
                ],
            ),
            subscription_snapshot(
                "stripe:sub_1:old", amount="20", observed_at="2026-09-01T00:00:00Z",
            ),
            subscription_snapshot("stripe:sub_1:latest", amount="30"),
            subscription_snapshot(
                "stripe:sub_2:inactive", subscription_id="stripe:sub_2", amount="40",
                status="inactive",
            ),
        ]
        result = self.project(rows)
        usd = result["historical"]["company"]["currencies"]["USD"]
        self.assertEqual(usd["settled_external_revenue"], "200")
        self.assertEqual(result["mrr"]["as_of"], "2026-10-01T00:00:00.000000Z")
        self.assertEqual(result["mrr"]["loops"]["self-build"], {
            "status": "verified", "currencies": {"USD": "30"},
            "reasons": [], "coverage_gaps": [],
        })
        self.assertEqual(result["mrr"]["company"], {
            "status": "verified", "currencies": {"USD": "30"},
            "reasons": [], "coverage_gaps": [],
        })

    def test_mrr_is_unknown_without_verified_as_of_subscription_snapshot(self):
        missing_mrr_coverage = [row for row in complete_coverage()
                                if row["projection"] != "as_of"]
        no_snapshot = self.project([
            receipt(revenue_class="monthly_recurring"),
        ], missing_mrr_coverage)["mrr"]["company"]
        self.assertEqual(no_snapshot["status"], "unknown")
        self.assertIn("mrr_coverage_unknown", no_snapshot["reasons"])

        one_snapshot_without_coverage = self.project([
            subscription_snapshot(),
        ], missing_mrr_coverage)["mrr"]["company"]
        self.assertEqual(one_snapshot_without_coverage["status"], "unknown")
        self.assertIn("mrr_coverage_unknown", one_snapshot_without_coverage["reasons"])

        unverified = self.project([
            subscription_snapshot(verification_state="unverified"),
        ])["mrr"]["company"]
        self.assertEqual(unverified["status"], "unknown")
        self.assertIn("subscription_snapshot_unverified", unverified["reasons"])

        verified_zero = self.project([])["mrr"]["company"]
        self.assertEqual(verified_zero["status"], "verified")
        self.assertEqual(verified_zero["currencies"], {})

        one_loop_gap = complete_coverage()
        one_loop_gap = [row for row in one_loop_gap
                        if not (row["product_loop_id"] == "capafy"
                                and row["projection"] == "as_of")]
        one_loop_gap.append(coverage(
            "capafy", "as_of", state="gap", reason="stale_readback",
            covered_categories=[],
        ))
        partial = self.project([
            subscription_snapshot(),
            subscription_snapshot(
                "stripe:capafy-sub", subscription_id="stripe:capafy-sub",
                loop_id="capafy", amount="40",
            ),
        ], one_loop_gap)["mrr"]
        self.assertEqual(partial["loops"]["capafy"]["status"], "unknown")
        self.assertEqual(partial["loops"]["capafy"]["currencies"], {})
        self.assertEqual(partial["loops"]["self-build"]["currencies"], {"USD": "30"})
        self.assertEqual(partial["company"]["status"], "unknown")
        self.assertEqual(partial["company"]["currencies"], {})

    def test_runway_uses_verified_liquid_balance_and_net_cash_burn(self):
        actual_cost = receipt(
            "do:invoice-1", provider="digitalocean", revenue_class=None,
            components=[{"category": "infra_cost", "amount": "70"}],
        )
        result = self.project([actual_cost, liquid_balance()])
        self.assertEqual(result["runway"]["status"], "verified")
        self.assertEqual(result["runway"]["currencies"]["USD"], {
            "status": "verified",
            "liquid_balance": "300",
            "net_cash_burn": "70",
            "window_days": "7",
            "runway_days": "30",
        })

    def test_runway_is_positive_cashflow_when_net_cash_burn_is_not_positive(self):
        rows = [
            receipt(
                "do:invoice-1", provider="digitalocean", revenue_class=None,
                components=[{"category": "infra_cost", "amount": "70"}],
            ),
            receipt(
                "stripe:monthly", revenue_class="monthly_recurring",
                components=[{"category": "settled_external_revenue", "amount": "100"}],
            ),
            liquid_balance(),
        ]
        runway = self.project(rows)["runway"]
        self.assertEqual(runway["status"], "positive_cashflow")
        self.assertEqual(runway["currencies"]["USD"], {
            "status": "positive_cashflow",
            "liquid_balance": "300",
            "net_cash_burn": "-30",
            "window_days": "7",
            "runway_days": None,
        })

    def test_runway_is_unknown_without_complete_same_currency_inputs(self):
        actual_cost = receipt(
            "do:invoice-1", provider="digitalocean", revenue_class=None,
            components=[{"category": "infra_cost", "amount": "70"}],
        )

        missing_balance = self.project([actual_cost])["runway"]
        self.assertEqual(missing_balance["status"], "unknown")
        self.assertIn("liquid_balance_missing", missing_balance["reasons"])

        unverified_balance = self.project([
            actual_cost, liquid_balance(verification_state="unverified"),
        ])["runway"]
        self.assertEqual(unverified_balance["status"], "unknown")
        self.assertIn("liquid_balance_unverified", unverified_balance["reasons"])

        gap_rows = complete_coverage()
        gap_rows = [row for row in gap_rows
                    if not (row["product_loop_id"] == "capafy" and row["projection"] == "trailing")]
        gap_rows.append(coverage("capafy", "trailing", state="gap", reason="source_unconnected"))
        unknown_burn = self.project([actual_cost, liquid_balance()], gap_rows)["runway"]
        self.assertEqual(unknown_burn["status"], "unknown")
        self.assertIn("trailing_burn_unknown", unknown_burn["reasons"])

        mismatched = self.project([
            actual_cost,
            liquid_balance(currency="JPY", amount="45000"),
        ])["runway"]
        self.assertEqual(mismatched["status"], "unknown")
        self.assertIn("currency_mismatch", mismatched["reasons"])

        no_balance_coverage = [row for row in complete_coverage()
                               if not (row["projection"] == "as_of"
                                       and "liquid_balance" in row["covered_categories"])]
        uncovered_balance = self.project([actual_cost, liquid_balance()], no_balance_coverage)["runway"]
        self.assertEqual(uncovered_balance["status"], "unknown")
        self.assertIn("liquid_balance_coverage_unknown", uncovered_balance["reasons"])

    def test_historical_and_trailing_use_fixed_half_open_boundaries(self):
        rows = [
            receipt("stripe:old", occurred_at="2026-09-23T23:00:00Z", settled_at="2026-09-23T23:30:00Z"),
            receipt("stripe:start", occurred_at="2026-09-23T23:59:00Z", settled_at=TRAILING_START),
            receipt("stripe:end", occurred_at="2026-09-30T23:59:00Z", settled_at=SNAPSHOT),
        ]
        result = self.project(rows)
        self.assertEqual(result["historical"]["company"]["currencies"]["USD"]["settled_external_revenue"], "20.2")
        self.assertEqual(result["trailing"]["company"]["currencies"]["USD"]["settled_external_revenue"], "10.1")

    def test_fractional_settlement_after_an_integral_occurrence_keeps_chronological_order(self):
        row = receipt(
            "stripe:fractional", occurred_at="2026-09-24T00:00:00Z",
            settled_at="2026-09-24T00:00:00.500000Z",
        )
        result = self.project([row])
        self.assertEqual(
            result["trailing"]["company"]["currencies"]["USD"]["settled_external_revenue"],
            "10.1",
        )

    def test_unconnected_source_is_unknown_coverage_not_zero(self):
        coverage_rows = complete_coverage()
        coverage_rows = [row for row in coverage_rows
                         if not (row["product_loop_id"] == "capafy" and row["projection"] == "trailing")]
        coverage_rows.append(coverage(
            "capafy", "trailing", state="gap", reason="source_unconnected",
        ))
        result = self.project([], coverage_rows)["trailing"]
        self.assertEqual(result["loops"]["capafy"]["status"], "unknown")
        self.assertEqual(result["loops"]["capafy"]["currencies"], {})
        self.assertEqual(result["loops"]["capafy"]["coverage_gaps"][0]["reason"], "source_unconnected")
        self.assertEqual(result["company"]["status"], "unknown")

    def test_coverage_requires_union_of_revenue_refund_and_every_cost_category(self):
        rows = complete_coverage()
        rows = [row for row in rows
                if not (row["product_loop_id"] == "self-build" and row["projection"] == "trailing")]
        rows.append(coverage(
            "self-build", "trailing",
            covered_categories=[category for category in m.COUNTED_CATEGORIES
                                if category != "model_cost"],
        ))
        trailing = self.project([], rows)["trailing"]
        self.assertEqual(trailing["loops"]["self-build"]["status"], "unknown")
        self.assertIn(
            {"product_loop_id": "self-build", "source_id": "self-build-financial-record",
             "reason": "missing_category", "category": "model_cost"},
            trailing["loops"]["self-build"]["coverage_gaps"],
        )

        usd = self.project([receipt()], rows)["trailing"]["company"]["currencies"]["USD"]
        self.assertEqual(usd["status"], "unknown")
        self.assertEqual(usd["unknown_categories"], ["model_cost"])
        self.assertIsNone(usd["model_cost"])
        self.assertIsNone(usd["total_cost"])
        self.assertIsNone(usd["net"])

    def test_balance_and_coverage_exact_replay_are_idempotent_and_conflicts_fail(self):
        balance = liquid_balance()
        coverage_row = coverage("self-build", "trailing")
        once = self.project([balance])
        replayed = self.project([balance, dict(balance)])
        self.assertEqual(once["runway"], replayed["runway"])

        changed_balance = dict(balance)
        changed_balance["amount"] = "301"
        with self.assertRaisesRegex(m.ContractError, "balance_conflict"):
            self.project([balance, changed_balance])

        account_snapshots = [
            liquid_balance("operating-old", account_id="operating", amount="100",
                           observed_at="2026-09-29T00:00:00Z"),
            liquid_balance("operating-latest", account_id="operating", amount="120"),
            liquid_balance("reserve-latest", account_id="reserve", amount="180"),
        ]
        cost = receipt("cost", provider="infra", revenue_class=None,
                       components=[{"category": "infra_cost", "amount": "70"}])
        account_runway = self.project([cost, *account_snapshots])["runway"]
        self.assertEqual(account_runway["currencies"]["USD"]["liquid_balance"], "300")

        coverage_rows = complete_coverage()
        replayed_coverage = self.project([], [*coverage_rows, dict(coverage_row)])
        self.assertEqual(replayed_coverage["trailing"]["company"]["status"], "zero")
        changed_coverage = dict(coverage_row)
        changed_coverage["covered_categories"] = ["settled_external_revenue"]
        with self.assertRaisesRegex(m.ContractError, "coverage_conflict"):
            self.project([], [coverage_row, changed_coverage])

        old_gap = coverage(
            "self-build", "trailing", state="gap", reason="read_failed",
            covered_categories=[], observed_at="2026-09-30T23:59:59Z",
        )
        later_complete = coverage(
            "self-build", "trailing", observed_at=SNAPSHOT,
        )
        latest_coverage = self.project([], [
            *[row for row in complete_coverage()
              if not (row["product_loop_id"] == "self-build"
                      and row["projection"] == "trailing")],
            old_gap, later_complete,
        ])
        self.assertEqual(latest_coverage["trailing"]["loops"]["self-build"]["status"], "zero")

        snapshot = subscription_snapshot()
        self.assertEqual(
            self.project([snapshot])["mrr"],
            self.project([snapshot, dict(snapshot)])["mrr"],
        )
        changed_snapshot = dict(snapshot)
        changed_snapshot["normalized_monthly_amount"] = "31"
        with self.assertRaisesRegex(m.ContractError, "subscription_snapshot_conflict"):
            self.project([snapshot, changed_snapshot])
        reused_snapshot_id = dict(snapshot)
        reused_snapshot_id["observed_at"] = "2026-09-30T23:30:00Z"
        with self.assertRaisesRegex(m.ContractError, "subscription_snapshot_conflict"):
            self.project([snapshot, reused_snapshot_id])

    def test_point_in_time_records_must_be_fresh_at_projection_end(self):
        stale_subscription = subscription_snapshot(observed_at="2020-01-01T00:00:00Z")
        mrr = self.project([stale_subscription])["mrr"]
        self.assertEqual(mrr["loops"]["self-build"]["status"], "unknown")
        self.assertIn("subscription_snapshot_stale",
                      mrr["loops"]["self-build"]["reasons"])
        self.assertEqual(mrr["loops"]["self-build"]["currencies"], {})
        self.assertEqual(mrr["company"]["currencies"], {})

        cost = receipt("cost", provider="infra", revenue_class=None,
                       components=[{"category": "infra_cost", "amount": "70"}])
        stale_balance = liquid_balance(observed_at="2020-01-01T00:00:00Z")
        runway = self.project([cost, stale_balance])["runway"]
        self.assertEqual(runway["status"], "unknown")
        self.assertIn("liquid_balance_stale", runway["reasons"])

        future_coverage = [dict(row, observed_at="2099-01-01T00:00:00Z")
                           for row in complete_coverage()]
        result = self.project([subscription_snapshot(), liquid_balance()], future_coverage)
        self.assertEqual(result["historical"]["company"]["status"], "unknown")
        self.assertEqual(result["mrr"]["company"]["status"], "unknown")
        self.assertTrue(all(
            gap["reason"] in {"stale_readback", "missing_category"}
            for gap in result["historical"]["company"]["coverage_gaps"]
        ))

    def test_provider_scoped_identities_do_not_dedupe_other_providers(self):
        same_receipt_id = [
            receipt("same", provider="stripe"),
            receipt("same", provider="paypal"),
        ]
        revenue = self.project(same_receipt_id)["historical"]["company"]["currencies"]["USD"]
        self.assertEqual(revenue["settled_external_revenue"], "20.2")

        balances = [
            liquid_balance("same", provider="stripe", amount="100"),
            liquid_balance("same", provider="paypal", amount="200"),
        ]
        runway = self.project([
            receipt("cost", provider="infra", revenue_class=None,
                    components=[{"category": "infra_cost", "amount": "70"}]),
            *balances,
        ])["runway"]
        self.assertEqual(runway["currencies"]["USD"]["liquid_balance"], "300")

        subscriptions = [
            subscription_snapshot("stripe:same", subscription_id="same", provider="stripe", amount="30"),
            subscription_snapshot("paypal:same", subscription_id="same", provider="paypal", amount="40"),
        ]
        self.assertEqual(self.project(subscriptions)["mrr"]["company"]["currencies"]["USD"], "70")

    def test_schema_file_and_validator_contract_have_parity(self):
        schema_path = Path(__file__).parent / "schemas" / "economic-attribution-v1.schema.json"
        self.assertEqual(schema_path.read_bytes(), m.render_schema())
        schema = json.loads(schema_path.read_text())
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for valid in (receipt(), liquid_balance(), subscription_snapshot(),
                      coverage("self-build", "historical")):
            validated = m.validate_record(valid)
            self.assertEqual(list(validator.iter_errors(validated)), [])
        categories = set(schema["$defs"]["component"]["properties"]["category"]["enum"])
        self.assertEqual(categories, set(m.ALL_CATEGORIES))
        self.assertEqual(
            set(schema["$defs"]["receipt"]["properties"]["product_loop_id"]["enum"]),
            set(m.PRODUCT_LOOP_IDS),
        )

    def test_schema_and_validator_reject_the_same_semantic_contract_breaks(self):
        schema = m.economic_attribution_schema()
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        zero = receipt(components=[{"category": "settled_external_revenue", "amount": "0"}])
        estimated = receipt(currency="USD_API_EQUIV")
        unsettled = receipt(settled_at=None)
        mixed = receipt(components=[
            {"category": "owner_deposit", "amount": "10"},
            {"category": "settled_external_revenue", "amount": "10"},
        ])
        duplicate_category = receipt(components=[
            {"category": "model_cost", "amount": "1"},
            {"category": "model_cost", "amount": "2"},
        ], revenue_class=None)
        bad_coverage = coverage("capafy", "trailing", state="complete", reason="read_failed")
        non_rfc3339 = receipt(occurred_at="2026-09-30 12:00:00Z")
        ungrounded_mrr = subscription_snapshot()
        ungrounded_mrr["normalization_basis"] = "annual_divided"
        for invalid in (zero, estimated, unsettled, mixed, duplicate_category,
                        bad_coverage, non_rfc3339, ungrounded_mrr):
            with self.subTest(invalid=invalid):
                with self.assertRaises(m.ContractError):
                    m.validate_record(invalid)
                self.assertTrue(list(validator.iter_errors(invalid)))

    def test_cross_field_rules_are_annotated_and_enforced_by_python(self):
        schema = m.economic_attribution_schema()
        validation = schema["x-lm-validation-contract"]
        self.assertEqual(validation["json_schema_scope"], "structural_only")
        self.assertEqual(
            validation["canonical_validator"],
            "skills.cfo.economic_attribution.validate_record",
        )
        rules = set(schema["x-lm-semantic-rules"])
        self.assertIn("receipt.settled_at >= receipt.occurred_at", rules)
        self.assertIn("coverage.window_start < coverage.window_end", rules)

        backwards_receipt = receipt(
            occurred_at="2026-09-30T12:05:00Z",
            settled_at="2026-09-30T12:00:00Z",
        )
        invalid_window = coverage("self-build", "trailing")
        invalid_window["window_start"] = invalid_window["window_end"]
        structural_validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for invalid in (backwards_receipt, invalid_window):
            self.assertEqual(list(structural_validator.iter_errors(invalid)), [])
            with self.assertRaises(m.ContractError):
                m.validate_record(invalid)


if __name__ == "__main__":
    unittest.main()
