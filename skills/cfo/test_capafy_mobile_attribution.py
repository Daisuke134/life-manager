"""Literal provider-boundary tests for the Capafy/Mobile B0 adapter."""

from __future__ import annotations

import json
import hashlib
import unittest
from pathlib import Path

from skills.cfo import economic_attribution as contract

try:
    from skills.cfo.adapters import capafy_mobile as adapter
except ModuleNotFoundError:
    adapter = None


FIXTURES = Path(__file__).parent / "fixtures" / "economic_attribution"
SNAPSHOT = "2026-10-01T00:00:00Z"
TRAILING_START = "2026-09-24T00:00:00Z"


class CapafyMobileAttributionTest(unittest.TestCase):
    def require_adapter(self):
        self.assertIsNotNone(adapter, "skills.cfo.adapters.capafy_mobile is not implemented")
        return adapter

    def assert_contract_records(self, records):
        self.assertTrue(records)
        self.assertEqual(records, [contract.validate_record(row) for row in records])

    def adapt_capafy(self, name, *, snapshot_at=SNAPSHOT):
        module = self.require_adapter()
        return module.adapt_capafy(
            FIXTURES / name,
            snapshot_at=snapshot_at,
            trailing_start=TRAILING_START,
        )

    def adapt_mobile(self, name, *, snapshot_at=SNAPSHOT):
        module = self.require_adapter()
        return module.adapt_mobile(
            FIXTURES / name,
            snapshot_at=snapshot_at,
            trailing_start=TRAILING_START,
        )

    def test_capafy_settled_order_separates_immutable_payment_and_fee(self):
        records = self.adapt_capafy("capafy-settled.json")
        self.assert_contract_records(records)
        receipts = [row for row in records if row["record_type"] == "receipt"]
        self.assertEqual(
            [(row["receipt_id"], row["components"]) for row in receipts],
            [
                ("capafy:fee:buy-capafy-001", [
                    {"category": "provider_fee", "amount": "18"},
                ]),
                ("capafy:payment:buy-capafy-001", [
                    {"category": "settled_external_revenue", "amount": "100"},
                ]),
            ],
        )
        self.assertNotIn("82", json.dumps(receipts))  # developerActualAmount is net, not a second revenue.
        complete = [row for row in records if row["record_type"] == "coverage"
                    and row["coverage_state"] == "complete"]
        self.assertEqual({row["projection"] for row in complete}, {"historical", "trailing"})
        self.assertTrue(all(row["covered_categories"] == [
            "provider_fee", "refund", "settled_external_revenue",
        ] for row in complete))

    def test_capafy_later_refund_adds_immutable_refund_without_mutating_payment(self):
        before = self.adapt_capafy("capafy-settled.json")
        after = self.adapt_capafy("capafy-refunded.json")
        before_receipts = [row for row in before if row["record_type"] == "receipt"]
        after_receipts = [row for row in after if row["record_type"] == "receipt"]
        self.assertEqual(after_receipts[:2], before_receipts)
        self.assertEqual(after_receipts[2]["receipt_id"], "capafy:refund:refund-capafy-001")
        self.assertEqual(after_receipts[2]["components"], [
            {"category": "refund", "amount": "10"},
        ])
        result = contract.project(
            [*before_receipts, *after], snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertEqual(result["duplicate_receipts"], [
            {"provider": "capafy", "receipt_id": "capafy:fee:buy-capafy-001"},
            {"provider": "capafy", "receipt_id": "capafy:payment:buy-capafy-001"},
        ])
        self.assertEqual(
            result["trailing"]["loops"]["capafy"]["currencies"]["USD"]
            ["settled_external_revenue"],
            "100",
        )
        self.assertEqual(
            result["trailing"]["loops"]["capafy"]["currencies"]["USD"]["refund"],
            "10",
        )

    def test_capafy_refund_without_identity_and_self_pay_are_coverage_gaps(self):
        no_refund_id = self.adapt_capafy("capafy-refund-without-id.json")
        self.assertFalse(any(
            row["record_type"] == "receipt" and row["components"][0]["category"] == "refund"
            for row in no_refund_id
        ))
        self.assertIn("missing_coverage", {
            row["reason"] for row in no_refund_id if row["record_type"] == "coverage"
        })
        self_pay = self.adapt_capafy("capafy-self-pay.json")
        self.assertFalse(any(row["record_type"] == "receipt" for row in self_pay))
        self.assertEqual({
            row["reason"] for row in self_pay if row["record_type"] == "coverage"
        }, {"unverified_receipt"})

    def test_capafy_pending_unverified_and_unsupported_currency_fail_closed(self):
        pending = self.adapt_capafy("capafy-pending.json")
        pending_receipts = [row for row in pending if row["record_type"] == "receipt"]
        self.assertEqual(len(pending_receipts), 1)
        self.assertEqual(pending_receipts[0]["verification_state"], "pending")
        self.assertEqual(pending_receipts[0]["components"], [
            {"category": "pending_revenue", "amount": "29.99"},
        ])
        self.assertIn("unverified_receipt", {
            row["reason"] for row in pending if row["record_type"] == "coverage"
        })

        unsupported = self.adapt_capafy("capafy-unsupported-currency.json")
        self.assertFalse(any(row["record_type"] == "receipt" for row in unsupported))
        self.assertEqual({
            row["reason"] for row in unsupported if row["record_type"] == "coverage"
        }, {"unsupported_currency"})

    def test_capafy_only_known_pending_status_emits_pending_revenue(self):
        records = self.adapt_capafy("capafy-statuses.json")
        receipts = [row for row in records if row["record_type"] == "receipt"]
        self.assertEqual([row["receipt_id"] for row in receipts], [
            "capafy:order:cre-pending-001",
        ])
        self.assertEqual(receipts[0]["components"], [
            {"category": "pending_revenue", "amount": "20"},
        ])
        rendered = json.dumps(records)
        self.assertNotIn("buy-declined-001", rendered)
        self.assertNotIn("buy-canceled-001", rendered)
        self.assertIn("unverified_receipt", {
            row["reason"] for row in records if row["record_type"] == "coverage"
        })

    def test_capafy_rejects_invalid_money_time_and_identity_boundaries(self):
        for fixture in (
            "capafy-inconsistent-money.json",
            "capafy-float-epoch.json",
            "capafy-overflow-epoch.json",
            "capafy-empty-order-id.json",
            "capafy-invalid-subscription-id.json",
        ):
            with self.subTest(fixture=fixture):
                records = self.adapt_capafy(fixture)
                self.assertFalse(any(row["record_type"] == "receipt" for row in records))
                self.assertEqual({
                    row["reason"] for row in records if row["record_type"] == "coverage"
                }, {"missing_coverage"})

    def test_capafy_requires_bound_content_hash_and_complete_pagination(self):
        module = self.require_adapter()
        original = json.loads((FIXTURES / "capafy-settled.json").read_text())
        keys = (
            "schema_version", "kind", "observed_at", "window_start", "window_end",
            "history_complete", "currency", "pagination", "orders",
        )

        def bind_content(payload):
            canonical = json.dumps(
                {key: payload[key] for key in keys},
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
            payload["content_sha256"] = hashlib.sha256(canonical).hexdigest()
            payload["evidence_ref"] = (
                f"capafy://orders/readback/sha256/{payload['content_sha256']}"
            )

        tampered = json.loads(json.dumps(original))
        order = tampered["orders"][0]
        order.update({
            "amount": 101,
            "actualAmount": 101,
            "developerActualAmount": 83,
        })
        tampered_records = module.adapt_capafy(
            tampered, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in tampered_records))

        partial = json.loads(json.dumps(original))
        partial["pagination"]["complete"] = False
        bind_content(partial)
        partial_records = module.adapt_capafy(
            partial, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in partial_records))
        self.assertEqual({
            row["reason"] for row in partial_records if row["record_type"] == "coverage"
        }, {"missing_coverage"})

        for mutate in (
            lambda payload: payload["pagination"].update(records_fetched=True),
            lambda payload: payload["orders"][0].update(orderId=[]),
        ):
            with self.subTest(mutate=mutate):
                invalid = json.loads(json.dumps(original))
                mutate(invalid)
                bind_content(invalid)
                records = module.adapt_capafy(
                    invalid, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
                )
                self.assertFalse(any(row["record_type"] == "receipt" for row in records))
                self.assertEqual({
                    row["reason"] for row in records if row["record_type"] == "coverage"
                }, {"missing_coverage"})

    def test_capafy_missing_partial_and_stale_sources_are_gaps_not_zero(self):
        module = self.require_adapter()
        missing = module.adapt_capafy(
            FIXTURES / "does-not-exist.json",
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
        )
        self.assertEqual({row["reason"] for row in missing}, {"source_unconnected"})
        partial = self.adapt_capafy("capafy-partial.json")
        self.assertEqual({row["reason"] for row in partial}, {"missing_coverage"})
        stale = self.adapt_capafy("capafy-settled.json", snapshot_at="2026-10-02T00:00:00Z")
        self.assertIn("stale_readback", {
            row["reason"] for row in stale if row["record_type"] == "coverage"
        })
        self.assertFalse(any(
            row["record_type"] == "coverage" and row["coverage_state"] == "complete"
            for row in stale
        ))

    def test_mobile_only_financial_report_settles_and_mrr_stays_snapshot_only(self):
        records = self.adapt_mobile("mobile-verified.json")
        self.assert_contract_records(records)
        receipts = [row for row in records if row["record_type"] == "receipt"]
        self.assertEqual({row["provider"] for row in receipts}, {"app-store-connect-financial"})
        self.assertEqual(sum(
            int(row["components"][0]["amount"]) for row in receipts
            if row["components"][0]["category"] == "settled_external_revenue"
        ), 1700)
        self.assertEqual(sum(
            int(row["components"][0]["amount"]) for row in receipts
            if row["components"][0]["category"] == "refund"
        ), 200)
        self.assertTrue(all("financial" in row["receipt_id"] for row in receipts))
        self.assertEqual(
            [(row["receipt_id"].rsplit(":", 1)[-1], row["revenue_class"])
             for row in receipts],
            [("17", "other_recurring"), ("18", "one_time"), ("19", None)],
        )
        self.assertNotIn("9999", json.dumps(receipts))
        self.assertNotIn("8888", json.dumps(receipts))
        self.assertFalse(any(
            row["record_type"] == "coverage"
            and row["source_id"] == "app-store-connect-sales"
            for row in records
        ))
        financial_complete = [
            row for row in records if row["record_type"] == "coverage"
            and row["source_id"] == "app-store-connect-financial"
            and row["projection"] == "trailing" and row["coverage_state"] == "complete"
        ]
        self.assertEqual(financial_complete[0]["covered_categories"], [
            "refund", "settled_external_revenue",
        ])
        snapshots = [row for row in records if row["record_type"] == "subscription_snapshot"]
        self.assertEqual([(row["subscription_id"], row["status"], row["normalized_monthly_amount"])
                          for row in snapshots], [
            ("revenuecat:anicca-ios:mrr", "active", "3000"),
            ("revenuecat:breath-reset:mrr", "inactive", "0"),
            ("revenuecat:desk-stretch-timer:mrr", "inactive", "0"),
            ("revenuecat:honne-ai:mrr", "inactive", "0"),
            ("revenuecat:micro-mood:mrr", "inactive", "0"),
            ("revenuecat:sleep-ritual:mrr", "inactive", "0"),
        ])
        projected = contract.project(
            records, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertEqual(projected["mrr"]["loops"]["mobile-apps"]["currencies"], {"JPY": "3000"})
        self.assertEqual(projected["trailing"]["loops"]["mobile-apps"]["status"], "unknown")
        self.assertIn("model_cost", projected["trailing"]["loops"]["mobile-apps"]
                      ["currencies"]["JPY"]["unknown_categories"])

    def test_mobile_provider_identity_and_replay_are_stable(self):
        once = self.adapt_mobile("mobile-verified.json")
        replay = self.adapt_mobile("mobile-verified.json")
        self.assertEqual(once, replay)
        result = contract.project(
            [*once, *replay], snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertEqual(result["duplicate_receipts"], [
            {"provider": "app-store-connect-financial",
             "receipt_id": "app-store-connect-financial:JP-2026-09-final:17"},
            {"provider": "app-store-connect-financial",
             "receipt_id": "app-store-connect-financial:JP-2026-09-final:18"},
            {"provider": "app-store-connect-financial",
             "receipt_id": "app-store-connect-financial:JP-2026-09-final:19"},
        ])

    def test_mobile_financial_report_does_not_depend_on_sales_and_trends(self):
        module = self.require_adapter()
        rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
        for row in rows:
            del row["sources"]["app_store_sales"]
        records = module.adapt_mobile(
            rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertEqual(sum(row["record_type"] == "receipt" for row in records), 3)
        self.assertEqual({
            row["provider"] for row in records if row["record_type"] == "receipt"
        }, {"app-store-connect-financial"})

    def test_mobile_empty_financial_report_requires_envelope_product_identity(self):
        module = self.require_adapter()
        rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
        for row in rows:
            row["sources"]["app_store_financial"]["data"]["rows"] = []
        complete = module.adapt_mobile(
            rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in complete))
        self.assertTrue(any(
            row["record_type"] == "coverage"
            and row["source_id"] == "app-store-connect-financial"
            and row["projection"] == "trailing"
            and row["coverage_state"] == "complete"
            for row in complete
        ))

        del rows[0]["sources"]["app_store_financial"]["data"]["apple_identifier"]
        missing_identity = module.adapt_mobile(
            rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertFalse(any(
            row["record_type"] == "coverage"
            and row["source_id"] == "app-store-connect-financial"
            and row["projection"] == "trailing"
            and row["coverage_state"] == "complete"
            for row in missing_identity
        ))

    def test_mobile_malformed_nested_provider_shapes_fail_closed(self):
        module = self.require_adapter()
        mutations = (
            lambda rows: rows[0].update({"sources": []}),
            lambda rows: rows[0]["sources"].update({"app_store_financial": []}),
            lambda rows: rows[0]["sources"]["app_store_financial"]["data"].update(
                {"rows": [7]}
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
                mutate(rows)
                records = module.adapt_mobile(
                    rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
                )
                self.assertIn("missing_coverage", {
                    row["reason"] for row in records if row["record_type"] == "coverage"
                })

    def test_mobile_rejects_wrong_mrr_definition_and_incomplete_period(self):
        module = self.require_adapter()
        rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
        rows[0]["sources"]["revenuecat"]["data"]["revenue_definition"]["metric"] = "revenue"
        rows[1]["sources"]["revenuecat"]["data"]["charts"]["mrr"]["latest_complete"]["MRR"]["incomplete"] = True
        records = module.adapt_mobile(
            rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        snapshot_ids = {
            row["subscription_id"] for row in records
            if row["record_type"] == "subscription_snapshot"
        }
        self.assertNotIn("revenuecat:anicca-ios:mrr", snapshot_ids)
        self.assertNotIn("revenuecat:honne-ai:mrr", snapshot_ids)
        self.assertIn("missing_coverage", {
            row["reason"] for row in records
            if row["record_type"] == "coverage" and row["source_id"] == "revenuecat-mrr"
        })

    def test_mobile_requires_mrr_evidence_sha256(self):
        module = self.require_adapter()
        rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
        del rows[0]["sources"]["revenuecat"]["evidence_sha256"]
        rows[1]["sources"]["revenuecat"]["evidence_sha256"] = "not-a-valid-sha256"
        records = module.adapt_mobile(
            rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        snapshot_ids = {
            row["subscription_id"] for row in records
            if row["record_type"] == "subscription_snapshot"
        }
        self.assertNotIn("revenuecat:anicca-ios:mrr", snapshot_ids)
        self.assertNotIn("revenuecat:honne-ai:mrr", snapshot_ids)
        self.assertIn("missing_coverage", {
            row["reason"] for row in records
            if row["record_type"] == "coverage" and row["source_id"] == "revenuecat-mrr"
        })

    def test_mobile_rejects_cross_product_financial_rows(self):
        module = self.require_adapter()
        rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
        rows[0]["sources"], rows[1]["sources"] = rows[1]["sources"], rows[0]["sources"]
        records = module.adapt_mobile(
            rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in records))
        self.assertIn("missing_coverage", {
            row["reason"] for row in records if row["record_type"] == "coverage"
            and row["source_id"] == "app-store-connect-financial"
        })

    def test_mobile_rejects_subset_or_extra_product_scope(self):
        module = self.require_adapter()
        rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
        subset = module.adapt_mobile(
            rows,
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
            products=("anicca-ios", "honne-ai"),
        )
        self.assertFalse(any(
            row["record_type"] in {"receipt", "subscription_snapshot"} for row in subset
        ))
        extra_rows = [*rows, {**rows[0], "product_id": "unexpected-product"}]
        extra = module.adapt_mobile(
            extra_rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertFalse(any(
            row["record_type"] in {"receipt", "subscription_snapshot"} for row in extra
        ))

    def test_mobile_current_producer_shape_is_explicit_fail_closed_input(self):
        records = self.adapt_mobile("mobile-current-producer.json")
        self.assert_contract_records(records)
        self.assertFalse(any(
            row["record_type"] in {"receipt", "subscription_snapshot"} for row in records
        ))
        self.assertEqual({
            row["source_id"] for row in records if row["record_type"] == "coverage"
        }, {"app-store-connect-financial", "revenuecat-mrr"})

    def test_mobile_partial_stale_unsupported_and_missing_sources_fail_closed(self):
        partial = self.adapt_mobile("mobile-partial.jsonl")
        self.assertIn("missing_coverage", {row["reason"] for row in partial
                                           if row["record_type"] == "coverage"})
        stale = self.adapt_mobile("mobile-verified.json", snapshot_at="2026-10-02T00:00:00Z")
        self.assertIn("stale_readback", {row["reason"] for row in stale
                                         if row["record_type"] == "coverage"})
        module = self.require_adapter()
        unsupported_rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
        unsupported_rows[0]["sources"]["app_store_financial"]["data"]["rows"][0][
            "partner_share_currency"
        ] = "UNKNOWN"
        unsupported_rows[0]["sources"]["revenuecat"]["data"]["currency"] = "UNKNOWN"
        unsupported = module.adapt_mobile(
            unsupported_rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertIn("unsupported_currency", {row["reason"] for row in unsupported
                                                if row["record_type"] == "coverage"})
        self.assertFalse(any(row["record_type"] in {"receipt", "subscription_snapshot"}
                             for row in unsupported))

        module = self.require_adapter()
        missing = module.adapt_mobile(
            FIXTURES / "does-not-exist.jsonl",
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
        )
        self.assertEqual({row["reason"] for row in missing}, {"source_unconnected"})


if __name__ == "__main__":
    unittest.main()
