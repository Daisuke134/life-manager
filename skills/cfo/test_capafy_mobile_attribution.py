"""Literal provider-boundary tests for the Capafy/Mobile B0 adapter."""

from __future__ import annotations

import json
import hashlib
import importlib.util
import unittest
from pathlib import Path
from unittest import mock

from skills.cfo import economic_attribution as contract

try:
    from skills.cfo.adapters import capafy_mobile as adapter
except ModuleNotFoundError:
    adapter = None


FIXTURES = Path(__file__).parent / "fixtures" / "economic_attribution"
SNAPSHOT = "2026-10-01T00:00:00Z"
TRAILING_START = "2026-09-24T00:00:00Z"
OVERSIZED_MONEY = ("1e999999", "999999999999999999999999999")
SILENT_ROUND_MONEY = "99999999999999999999999999.123456789012345678"


def canonical_sha256(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()


def bind_capafy_content(payload):
    keys = [
        "schema_version", "kind", "observed_at", "window_start", "window_end",
        "history_complete", "currency", "pagination",
    ]
    if "account_inventory" in payload:
        keys.append("account_inventory")
    keys.append("orders")
    payload["content_sha256"] = canonical_sha256({key: payload[key] for key in keys})
    payload["evidence_ref"] = (
        f"capafy://orders/readback/sha256/{payload['content_sha256']}"
    )


def bind_capafy_account_inventory(payload, owner_buyer_ids):
    order = payload["orders"][0]
    inventory = {
        "schema_version": 1,
        "kind": "capafy_account_inventory_readback",
        "observed_at": payload["observed_at"],
        "developer_id": order["developerId"],
        "owner_buyer_ids": owner_buyer_ids,
        "complete": True,
    }
    inventory["content_sha256"] = canonical_sha256(inventory)
    inventory["evidence_ref"] = (
        f"capafy://accounts/readback/sha256/{inventory['content_sha256']}"
    )
    payload["account_inventory"] = inventory
    bind_capafy_content(payload)


def bind_revenuecat_hash(row):
    source = row["sources"]["revenuecat"]
    source["evidence_sha256"] = canonical_sha256({
        "status": source.get("status"),
        "reason": source.get("reason"),
        "data": source.get("data"),
    })


def load_business_outcomes_producer():
    path = (
        Path(__file__).parent.parent / "earn" / "marketing-engine" / "measure"
        / "business_outcomes.py"
    )
    spec = importlib.util.spec_from_file_location("cfo_business_outcomes", path)
    if not spec or not spec.loader:
        raise AssertionError("business_outcomes producer is not importable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bind_financial_report_hash(rows):
    financial = [row["sources"]["app_store_financial"]["data"] for row in rows]
    report = {
        "report_id": financial[0]["report_id"],
        "report_status": financial[0]["report_status"],
        "period_start": financial[0]["period_start"],
        "period_end": financial[0]["period_end"],
        "rows": sorted(
            [item for data in financial for item in data["rows"]],
            key=lambda item: item["source_row_index"],
        ),
    }
    report_sha = canonical_sha256(report)
    for data in financial:
        data["report_sha256"] = report_sha


def capafy_order_row_sha(order, currency):
    return canonical_sha256({
        "order_id": order["orderId"],
        "subscription_id": order.get("subscriptionId"),
        "buyer_id": order["buyerId"],
        "developer_id": order["developerId"],
        "currency": currency.upper(),
        "amount": order["amount"],
        "platform_fee_amount": order["platformFeeAmount"],
        "payment_at": order["paymentAt"],
        "completed_at": order["completedAt"],
    })


def capafy_refund_row_sha(order, currency):
    return canonical_sha256({
        "order_id": order["orderId"],
        "refund_id": order["refundId"],
        "buyer_id": order["buyerId"],
        "developer_id": order["developerId"],
        "currency": currency.upper(),
        "refund_amount": order["refundAmount"],
        "refunded_at": order["refundedAt"],
    })


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
        self.assertNotIn(
            "82",
            [component["amount"] for row in receipts for component in row["components"]],
        )  # developerActualAmount is net, not a second revenue.
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
        refunded_payload = json.loads((FIXTURES / "capafy-refunded.json").read_text())
        refund_row = refunded_payload["orders"][0]
        self.assertEqual(after_receipts[2]["evidence_refs"], [
            "capafy://refunds/refund-capafy-001/row-sha256/"
            + capafy_refund_row_sha(refund_row, refunded_payload["currency"]),
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

    def test_capafy_rejects_bool_and_float_schema_versions_at_each_boundary(self):
        module = self.require_adapter()
        for boundary in ("envelope", "account_inventory"):
            for schema_version in (True, 1.0):
                with self.subTest(boundary=boundary, schema_version=schema_version):
                    payload = json.loads(
                        (FIXTURES / "capafy-settled.json").read_text()
                    )
                    if boundary == "envelope":
                        payload["schema_version"] = schema_version
                    else:
                        inventory = payload["account_inventory"]
                        inventory["schema_version"] = schema_version
                        inventory["content_sha256"] = canonical_sha256({
                            key: inventory[key] for key in (
                                "schema_version", "kind", "observed_at",
                                "developer_id", "owner_buyer_ids", "complete",
                            )
                        })
                        inventory["evidence_ref"] = (
                            "capafy://accounts/readback/sha256/"
                            + inventory["content_sha256"]
                        )
                    bind_capafy_content(payload)
                    records = module.adapt_capafy(
                        payload, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
                    )
                    self.assertFalse(any(
                        row["record_type"] == "receipt" for row in records
                    ))
                    self.assertEqual({
                        row["coverage_state"] for row in records
                        if row["record_type"] == "coverage"
                    }, {"gap"})

    def test_capafy_requires_bound_content_hash_and_complete_pagination(self):
        module = self.require_adapter()
        original = json.loads((FIXTURES / "capafy-settled.json").read_text())

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
        bind_capafy_content(partial)
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
                bind_capafy_content(invalid)
                records = module.adapt_capafy(
                    invalid, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
                )
                self.assertFalse(any(row["record_type"] == "receipt" for row in records))
                self.assertEqual({
                    row["reason"] for row in records if row["record_type"] == "coverage"
                }, {"missing_coverage"})

    def test_capafy_receipt_evidence_binds_canonical_immutable_row_hash(self):
        module = self.require_adapter()
        original = json.loads((FIXTURES / "capafy-settled.json").read_text())
        changed = json.loads(json.dumps(original))
        changed["orders"][0].update({
            "amount": 101,
            "actualAmount": 101,
            "developerActualAmount": 83,
        })
        bind_capafy_content(changed)

        before = module.adapt_capafy(
            original, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        after = module.adapt_capafy(
            changed, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        before_receipts = [row for row in before if row["record_type"] == "receipt"]
        after_receipts = [row for row in after if row["record_type"] == "receipt"]
        self.assertEqual(
            [row["receipt_id"] for row in before_receipts],
            [row["receipt_id"] for row in after_receipts],
        )
        before_row_sha = capafy_order_row_sha(original["orders"][0], original["currency"])
        after_row_sha = capafy_order_row_sha(changed["orders"][0], changed["currency"])
        self.assertTrue(all(
            row["evidence_refs"] == [
                f"capafy://orders/buy-capafy-001/row-sha256/{before_row_sha}"
            ]
            for row in before_receipts
        ))
        self.assertTrue(all(
            row["evidence_refs"] == [
                f"capafy://orders/buy-capafy-001/row-sha256/{after_row_sha}"
            ]
            for row in after_receipts
        ))
        self.assertNotEqual(
            [row["evidence_refs"] for row in before_receipts],
            [row["evidence_refs"] for row in after_receipts],
        )
        with self.assertRaisesRegex(contract.ContractError, "receipt_conflict"):
            contract.project(
                [*before_receipts, *after_receipts],
                snapshot_at=SNAPSHOT,
                trailing_start=TRAILING_START,
            )
        self.assertTrue(all(
            original["content_sha256"] in row["evidence_refs"][0]
            for row in before if row["record_type"] == "coverage"
        ))

    def test_capafy_appending_another_order_preserves_existing_receipts_exactly(self):
        module = self.require_adapter()
        original = json.loads((FIXTURES / "capafy-settled.json").read_text())
        appended = json.loads(json.dumps(original))
        second = json.loads(json.dumps(original["orders"][0]))
        second.update({
            "orderId": "buy-capafy-002",
            "buyerId": "buyer-external-002",
            "amount": 50,
            "actualAmount": 50,
            "developerActualAmount": 42,
            "platformFeeAmount": 8,
            "paymentAt": 1790773210000,
            "completedAt": 1790773220000,
            "updatedAt": 1790773220000,
        })
        appended["orders"].append(second)
        appended["pagination"]["records_fetched"] = 2
        bind_capafy_content(appended)
        before = module.adapt_capafy(
            original, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        after = module.adapt_capafy(
            appended, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        before_receipts = [row for row in before if row["record_type"] == "receipt"]
        existing_after = [
            row for row in after if row["record_type"] == "receipt"
            and row["receipt_id"].endswith("buy-capafy-001")
        ]
        self.assertEqual(existing_after, before_receipts)

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

    def test_capafy_requires_bound_account_inventory_and_excludes_secondary_owner(self):
        module = self.require_adapter()
        source = json.loads((FIXTURES / "capafy-settled.json").read_text())
        missing = json.loads(json.dumps(source))
        del missing["account_inventory"]
        missing_records = module.adapt_capafy(
            missing, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in missing_records))

        external = json.loads(json.dumps(source))
        bind_capafy_account_inventory(
            external, ["developer-owner-001", "buyer-owner-secondary-001"],
        )
        external_records = module.adapt_capafy(
            external, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertEqual(sum(
            row["record_type"] == "receipt" for row in external_records
        ), 2)

        forged_inventory = json.loads(json.dumps(external))
        forged_inventory["account_inventory"]["content_sha256"] = "f" * 64
        forged_inventory["account_inventory"]["evidence_ref"] = (
            "capafy://accounts/readback/sha256/" + "f" * 64
        )
        bind_capafy_content(forged_inventory)
        forged_records = module.adapt_capafy(
            forged_inventory, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in forged_records))

        secondary_owner = json.loads(json.dumps(external))
        secondary_owner["orders"][0]["buyerId"] = "buyer-owner-secondary-001"
        bind_capafy_content(secondary_owner)
        owner_records = module.adapt_capafy(
            secondary_owner, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in owner_records))
        self.assertEqual({
            row["reason"] for row in owner_records if row["record_type"] == "coverage"
        }, {"unverified_receipt"})

    def test_capafy_rejects_unknown_envelope_and_pagination_fields(self):
        module = self.require_adapter()
        original = json.loads((FIXTURES / "capafy-settled.json").read_text())
        unknown = json.loads(json.dumps(original))
        unknown["unexpected"] = "not-official"
        unknown_records = module.adapt_capafy(
            unknown, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in unknown_records))

        has_more = json.loads(json.dumps(original))
        has_more["pagination"]["has_more"] = True
        bind_capafy_content(has_more)
        has_more_records = module.adapt_capafy(
            has_more, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in has_more_records))

    def test_capafy_oversized_money_fails_closed_after_valid_rehash(self):
        module = self.require_adapter()
        for amount in OVERSIZED_MONEY:
            with self.subTest(amount=amount):
                payload = json.loads((FIXTURES / "capafy-settled.json").read_text())
                payload["orders"][0].update({
                    "amount": amount,
                    "actualAmount": amount,
                    "developerActualAmount": amount,
                    "platformFeeAmount": 0,
                })
                bind_capafy_content(payload)
                records = module.adapt_capafy(
                    payload, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
                )
                self.assertFalse(any(
                    row["record_type"] == "receipt" for row in records
                ))
                self.assertEqual({
                    row["coverage_state"] for row in records
                    if row["record_type"] == "coverage"
                }, {"gap"})

    def test_capafy_rejects_money_that_decimal_context_would_round(self):
        module = self.require_adapter()
        payload = json.loads((FIXTURES / "capafy-settled.json").read_text())
        payload["orders"][0].update({
            "amount": SILENT_ROUND_MONEY,
            "actualAmount": SILENT_ROUND_MONEY,
            "developerActualAmount": SILENT_ROUND_MONEY,
            "platformFeeAmount": 0,
        })
        bind_capafy_content(payload)
        records = module.adapt_capafy(
            payload, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in records))
        self.assertEqual({
            row["coverage_state"] for row in records
            if row["record_type"] == "coverage"
        }, {"gap"})

    def test_capafy_preserves_valid_26_digit_integer(self):
        module = self.require_adapter()
        amount = "99999999999999999999999999"
        payload = json.loads((FIXTURES / "capafy-settled.json").read_text())
        payload["orders"][0].update({
            "amount": amount,
            "actualAmount": amount,
            "developerActualAmount": amount,
            "platformFeeAmount": 0,
        })
        bind_capafy_content(payload)
        records = module.adapt_capafy(
            payload, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertEqual([
            row["components"] for row in records if row["record_type"] == "receipt"
        ], [[{"category": "settled_external_revenue", "amount": amount}]])

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

    def test_mobile_retimestamp_does_not_extend_provider_projection_coverage(self):
        module = self.require_adapter()
        rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
        for row in rows:
            row["observed_at"] = "2026-10-02T00:00:00Z"
        records = module.adapt_mobile(
            rows,
            snapshot_at="2026-10-02T00:00:00Z",
            trailing_start=TRAILING_START,
        )
        self.assertEqual(sum(
            row["record_type"] == "receipt" for row in records
        ), 3)
        self.assertFalse(any(
            row["record_type"] == "subscription_snapshot" for row in records
        ))
        self.assertTrue(any(
            row["record_type"] == "coverage"
            and row["source_id"] == "app-store-connect-financial"
            and row["projection"] == "trailing"
            and row["coverage_state"] == "gap"
            for row in records
        ))
        self.assertTrue(any(
            row["record_type"] == "coverage"
            and row["source_id"] == "revenuecat-mrr"
            and row["projection"] == "as_of"
            and row["coverage_state"] == "gap"
            for row in records
        ))

    def test_mobile_empty_financial_report_requires_envelope_product_identity(self):
        module = self.require_adapter()
        rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
        for row in rows:
            row["sources"]["app_store_financial"]["data"]["rows"] = []
        bind_financial_report_hash(rows)
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

    def test_mobile_rejects_bool_and_float_row_schema_versions(self):
        module = self.require_adapter()
        for schema_version in (True, 1.0):
            with self.subTest(schema_version=schema_version):
                rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
                rows[0]["schema_version"] = schema_version
                records = module.adapt_mobile(
                    rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
                )
                self.assertFalse(any(
                    row["record_type"] in {"receipt", "subscription_snapshot"}
                    for row in records
                ))
                self.assertEqual({
                    row["coverage_state"] for row in records
                    if row["record_type"] == "coverage"
                }, {"gap"})

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

    def test_mobile_rejects_mrr_changed_without_matching_content_hash(self):
        module = self.require_adapter()
        rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
        rows[0]["sources"]["revenuecat"]["data"]["charts"]["mrr"][
            "latest_complete"
        ]["MRR"]["value"] = 987654321
        records = module.adapt_mobile(
            rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertNotIn("revenuecat:anicca-ios:mrr", {
            row["subscription_id"] for row in records
            if row["record_type"] == "subscription_snapshot"
        })
        self.assertTrue(any(
            row["record_type"] == "coverage"
            and row["source_id"] == "revenuecat-mrr"
            and row["coverage_state"] == "gap"
            for row in records
        ))

    def test_mobile_rejects_financial_amount_changed_without_matching_report_hash(self):
        module = self.require_adapter()
        rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
        rows[0]["sources"]["app_store_financial"]["data"]["rows"][0][
            "extended_partner_share"
        ] = 7654321
        records = module.adapt_mobile(
            rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in records))
        self.assertTrue(any(
            row["record_type"] == "coverage"
            and row["source_id"] == "app-store-connect-financial"
            and row["projection"] == "trailing"
            and row["coverage_state"] == "gap"
            for row in records
        ))

    def test_mobile_financial_oversized_money_fails_closed_after_valid_rehash(self):
        module = self.require_adapter()
        for amount in OVERSIZED_MONEY:
            with self.subTest(amount=amount):
                rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
                rows[0]["sources"]["app_store_financial"]["data"]["rows"][0][
                    "extended_partner_share"
                ] = amount
                bind_financial_report_hash(rows)
                records = module.adapt_mobile(
                    rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
                )
                self.assertFalse(any(
                    row["record_type"] == "receipt" for row in records
                ))
                self.assertTrue(any(
                    row["record_type"] == "coverage"
                    and row["source_id"] == "app-store-connect-financial"
                    and row["projection"] == "trailing"
                    and row["coverage_state"] == "gap"
                    for row in records
                ))

    def test_mobile_financial_rejects_money_that_decimal_context_would_round(self):
        module = self.require_adapter()
        rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
        rows[0]["sources"]["app_store_financial"]["data"]["rows"][0][
            "extended_partner_share"
        ] = SILENT_ROUND_MONEY
        bind_financial_report_hash(rows)
        records = module.adapt_mobile(
            rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in records))
        self.assertTrue(any(
            row["record_type"] == "coverage"
            and row["source_id"] == "app-store-connect-financial"
            and row["projection"] == "trailing"
            and row["coverage_state"] == "gap"
            for row in records
        ))

    def test_mobile_financial_preserves_signed_return_and_trailing_zero(self):
        module = self.require_adapter()
        rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
        rows[0]["sources"]["app_store_financial"]["data"]["rows"][1][
            "extended_partner_share"
        ] = "-200.5000"
        bind_financial_report_hash(rows)
        records = module.adapt_mobile(
            rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        refunds = [
            row for row in records if row["record_type"] == "receipt"
            and row["components"][0]["category"] == "refund"
        ]
        self.assertEqual(refunds[0]["components"], [
            {"category": "refund", "amount": "200.5"},
        ])

    def test_mobile_rejects_duplicate_financial_row_identity_with_valid_hash(self):
        module = self.require_adapter()
        rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
        rows[1]["sources"]["app_store_financial"]["data"]["rows"][0][
            "source_row_index"
        ] = 17
        bind_financial_report_hash(rows)
        records = module.adapt_mobile(
            rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in records))
        self.assertTrue(any(
            row["record_type"] == "coverage"
            and row["source_id"] == "app-store-connect-financial"
            and row["projection"] == "trailing"
            and row["coverage_state"] == "gap"
            for row in records
        ))

    def test_mobile_requires_consistent_financial_report_identity_hash_and_period(self):
        module = self.require_adapter()
        mutations = (
            lambda data: data.update(report_id="JP-2026-09-other"),
            lambda data: data.update(report_sha256="f" * 64),
            lambda data: data.update(period_start="2026-08-01"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
                mutate(rows[1]["sources"]["app_store_financial"]["data"])
                records = module.adapt_mobile(
                    rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
                )
                self.assertFalse(any(row["record_type"] == "receipt" for row in records))
                self.assertTrue(any(
                    row["record_type"] == "coverage"
                    and row["source_id"] == "app-store-connect-financial"
                    and row["projection"] == "trailing"
                    and row["coverage_state"] == "gap"
                    for row in records
                ))

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

    def test_mobile_dedupes_exact_snapshot_and_rejects_material_identity_conflict(self):
        module = self.require_adapter()
        baseline = json.loads((FIXTURES / "mobile-verified.json").read_text())
        expected = module.adapt_mobile(
            baseline, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        exact_duplicate = [*baseline, json.loads(json.dumps(baseline[0]))]
        self.assertEqual(module.adapt_mobile(
            exact_duplicate, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        ), expected)

        conflicting = json.loads(json.dumps(baseline[0]))
        conflicting["sources"]["revenuecat"]["data"]["charts"]["mrr"][
            "latest_complete"
        ]["MRR"]["value"] = 7777
        bind_revenuecat_hash(conflicting)
        for rows in ([*baseline, conflicting], [conflicting, *baseline]):
            with self.subTest(first_mrr=rows[0]["sources"]["revenuecat"]["data"]):
                records = module.adapt_mobile(
                    rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
                )
                self.assertFalse(any(
                    row["record_type"] in {"receipt", "subscription_snapshot"}
                    for row in records
                ))
                self.assertEqual({
                    row["coverage_state"] for row in records
                    if row["record_type"] == "coverage"
                }, {"gap"})

    def test_mobile_numeric_type_difference_is_material_snapshot_conflict(self):
        module = self.require_adapter()
        for source in ("financial", "revenuecat"):
            baseline = json.loads((FIXTURES / "mobile-verified.json").read_text())
            conflicting = json.loads(json.dumps(baseline[0]))
            if source == "financial":
                conflicting["sources"]["app_store_financial"]["data"]["rows"][0][
                    "extended_partner_share"
                ] = 1200.0
            else:
                conflicting["sources"]["revenuecat"]["data"]["charts"]["mrr"][
                    "latest_complete"
                ]["MRR"]["value"] = 3000.0
            for order, rows in (
                ("conflict_last", [*baseline, conflicting]),
                ("conflict_first", [conflicting, *baseline]),
            ):
                with self.subTest(source=source, order=order):
                    records = module.adapt_mobile(
                        rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
                    )
                    self.assertFalse(any(
                        row["record_type"] in {"receipt", "subscription_snapshot"}
                        for row in records
                    ))
                    self.assertEqual({
                        row["coverage_state"] for row in records
                        if row["record_type"] == "coverage"
                    }, {"gap"})

    def test_mobile_rejects_non_dict_and_out_of_catalog_rows_at_any_date(self):
        module = self.require_adapter()
        baseline = json.loads((FIXTURES / "mobile-verified.json").read_text())
        unexpected = json.loads(json.dumps(baseline[0]))
        unexpected.update({
            "product_id": "unexpected-product",
            "business_date": "2026-09-29",
            "observed_at": "2026-09-30T00:00:00Z",
        })
        for extra in (42, unexpected):
            with self.subTest(extra=extra):
                records = module.adapt_mobile(
                    [*baseline, extra], snapshot_at=SNAPSHOT,
                    trailing_start=TRAILING_START,
                )
                self.assertFalse(any(
                    row["record_type"] in {"receipt", "subscription_snapshot"}
                    for row in records
                ))
                self.assertEqual({
                    row["coverage_state"] for row in records
                    if row["record_type"] == "coverage"
                }, {"gap"})

    def test_mobile_mrr_oversized_money_fails_closed_after_valid_rehash(self):
        module = self.require_adapter()
        for amount in OVERSIZED_MONEY:
            with self.subTest(amount=amount):
                rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
                rows[0]["sources"]["revenuecat"]["data"]["charts"]["mrr"][
                    "latest_complete"
                ]["MRR"]["value"] = amount
                bind_revenuecat_hash(rows[0])
                records = module.adapt_mobile(
                    rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
                )
                self.assertFalse(any(
                    row["record_type"] == "subscription_snapshot" for row in records
                ))
                self.assertTrue(any(
                    row["record_type"] == "coverage"
                    and row["source_id"] == "revenuecat-mrr"
                    and row["coverage_state"] == "gap"
                    for row in records
                ))

    def test_mobile_mrr_rejects_money_that_decimal_context_would_round(self):
        module = self.require_adapter()
        rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
        rows[0]["sources"]["revenuecat"]["data"]["charts"]["mrr"][
            "latest_complete"
        ]["MRR"]["value"] = SILENT_ROUND_MONEY
        bind_revenuecat_hash(rows[0])
        records = module.adapt_mobile(
            rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertFalse(any(
            row["record_type"] == "subscription_snapshot" for row in records
        ))
        self.assertTrue(any(
            row["record_type"] == "coverage"
            and row["source_id"] == "revenuecat-mrr"
            and row["coverage_state"] == "gap"
            for row in records
        ))

    def test_mobile_mrr_preserves_trailing_zero_without_rounding(self):
        module = self.require_adapter()
        rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
        rows[0]["sources"]["revenuecat"]["data"]["charts"]["mrr"][
            "latest_complete"
        ]["MRR"]["value"] = "3000.5000"
        bind_revenuecat_hash(rows[0])
        records = module.adapt_mobile(
            rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        snapshots = {
            row["subscription_id"]: row["normalized_monthly_amount"]
            for row in records if row["record_type"] == "subscription_snapshot"
        }
        self.assertEqual(snapshots["revenuecat:anicca-ios:mrr"], "3000.5")

    def test_incomplete_revenuecat_shape_remains_fail_closed(self):
        records = self.adapt_mobile("mobile-current-producer.json")
        self.assert_contract_records(records)
        self.assertFalse(any(
            row["record_type"] in {"receipt", "subscription_snapshot"} for row in records
        ))
        self.assertEqual({
            row["source_id"] for row in records if row["record_type"] == "coverage"
        }, {"app-store-connect-financial", "revenuecat-mrr"})

    def test_business_outcomes_revenuecat_envelope_reaches_mobile_mrr_consumer(self):
        module = self.require_adapter()
        producer = load_business_outcomes_producer()
        rows = json.loads((FIXTURES / "mobile-verified.json").read_text())
        for row in rows:
            app_id = module.MOBILE_PRODUCT_BINDINGS[row["product_id"]][
                "revenuecat_app_id"
            ]
            body = {
                "yaxis_currency": "USD",
                "measures": [{"display_name": "MRR"}],
                "periods": [{"date": "2026-09-30"}],
                "values": [{
                    "cohort": 0,
                    "value": row["sources"]["revenuecat"]["data"]["charts"]
                    ["mrr"]["latest_complete"]["MRR"]["value"],
                    "incomplete": False,
                }],
            }
            options = {
                "filters": [{"id": "app_id", "options": [{"id": app_id}]}],
            }
            with (
                mock.patch.object(producer, "RC_CHARTS", ("mrr",)),
                mock.patch.object(producer, "http_json", side_effect=[options, body]),
                mock.patch.object(producer, "revenuecat_products", return_value={}),
                mock.patch.object(producer, "collect_asc", return_value={}),
                mock.patch.object(producer, "collect_asc_sales", return_value=({}, {})),
                mock.patch.object(producer, "collect_mixpanel", return_value={}),
            ):
                snapshot = producer.collect_snapshot(
                    {
                        "REVENUECAT_PROJECT_ID": "fixture-project",
                        "REVENUECAT_V2_SECRET_KEY": "fixture-token",
                    },
                    row["product_id"],
                    row["business_date"],
                )
            row["sources"]["revenuecat"] = snapshot["sources"]["revenuecat"]

        records = module.adapt_mobile(
            rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assert_contract_records(records)
        snapshots = {
            row["subscription_id"]: row["normalized_monthly_amount"]
            for row in records if row["record_type"] == "subscription_snapshot"
        }
        self.assertEqual(len(snapshots), len(module.MOBILE_PRODUCTS))
        self.assertEqual(snapshots["revenuecat:anicca-ios:mrr"], "3000")

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
