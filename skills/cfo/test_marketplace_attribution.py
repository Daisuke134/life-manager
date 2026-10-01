"""Literal marketplace readback tests for the B0 economic attribution adapter."""

from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from skills.cfo import economic_attribution as contract

try:
    from skills.cfo.adapters import marketplace as adapter
except (ImportError, ModuleNotFoundError):
    adapter = None


FIXTURES = Path(__file__).parent / "fixtures" / "economic_attribution"
SNAPSHOT = "2026-10-01T00:00:00Z"
TRAILING_START = "2026-09-24T00:00:00Z"


class MarketplaceAttributionTest(unittest.TestCase):
    def require_adapter(self):
        self.assertIsNotNone(
            adapter,
            "skills.cfo.adapters.marketplace is not implemented",
        )
        return adapter

    def fixture(self, name: str) -> dict:
        return json.loads((FIXTURES / name).read_text())

    def bind(self, payload: dict) -> dict:
        unsigned = {
            key: value
            for key, value in payload.items()
            if key not in {"content_sha256", "evidence_ref"}
        }
        digest = hashlib.sha256(json.dumps(
            unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode()).hexdigest()
        payload["content_sha256"] = digest
        payload["evidence_ref"] = (
            f"marketplace://{payload['platform']}/financial-readback/sha256/{digest}"
        )
        return payload

    def reobserve(self, payload: dict, observed_at: str) -> dict:
        payload["observed_at"] = observed_at
        for window in payload["coverage"].values():
            window["window_end"] = observed_at
        for row in payload["receipt_map"]["records"]:
            row["observed_at"] = observed_at
        return self.bind(payload)

    def adapt(self, name: str):
        module = self.require_adapter()
        return module.adapt(
            self.fixture(name),
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
        )

    def test_settled_gross_refund_and_each_fee_are_recorded_once(self):
        rows = self.adapt("marketplace-settled.json")
        receipts = {
            row["receipt_id"]: row
            for row in rows
            if row["record_type"] == "receipt"
        }
        self.assertEqual(
            receipts["marketplace:lancers:payment:payment-1"]["components"],
            [
                {"category": "provider_fee", "amount": "4500"},
                {"category": "settled_external_revenue", "amount": "45000"},
            ],
        )
        self.assertEqual(
            receipts["marketplace:lancers:payment:payment-2"]["components"],
            [{"category": "settled_external_revenue", "amount": "10000"}],
        )
        self.assertEqual(
            receipts["marketplace:lancers:fee:fee-2"]["components"],
            [{"category": "payment_fee", "amount": "200"}],
        )
        self.assertEqual(
            receipts["marketplace:lancers:refund:refund-1"]["components"],
            [{"category": "refund", "amount": "5000"}],
        )
        for row in rows:
            self.assertEqual(row, contract.validate_record(row))

    def test_payout_pending_self_payment_and_owner_deposit_never_become_revenue(self):
        rows = self.adapt("marketplace-settled.json")
        receipts = {
            row["receipt_id"]: row
            for row in rows
            if row["record_type"] == "receipt"
        }
        self.assertEqual(
            receipts["marketplace:lancers:payout:payout-1"]["components"],
            [{"category": "payout", "amount": "40500"}],
        )
        self.assertEqual(
            receipts["marketplace:lancers:pending:payment-pending"]["components"],
            [{"category": "pending_revenue", "amount": "7000"}],
        )
        self.assertEqual(
            receipts["marketplace:lancers:pending:payment-pending"]["verification_state"],
            "pending",
        )
        self.assertEqual(
            receipts["marketplace:lancers:movement:self-pay-1"]["components"],
            [{"category": "self_payment", "amount": "1000"}],
        )
        self.assertEqual(
            receipts["marketplace:lancers:movement:owner-deposit-1"]["components"],
            [{"category": "owner_deposit", "amount": "3000"}],
        )
        self.assertEqual(
            receipts["marketplace:lancers:movement:internal-transfer-1"]["components"],
            [{"category": "internal_transfer", "amount": "2000"}],
        )
        revenue_ids = {
            row["receipt_id"]
            for row in receipts.values()
            if any(component["category"] == contract.REVENUE
                   for component in row["components"])
        }
        self.assertEqual(revenue_ids, {
            "marketplace:lancers:payment:payment-1",
            "marketplace:lancers:payment:payment-2",
        })
        projected = contract.project(
            rows,
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
        )
        self.assertEqual(projected["duplicate_receipts"], [])
        excluded = projected["historical"]["loops"]["gig-lancers"]["excluded"]
        self.assertEqual(
            {row["category"] for row in excluded},
            {"internal_transfer", "owner_deposit", "pending_revenue", "payout", "self_payment"},
        )

    def test_promptbase_aggregate_without_immutable_receipt_map_is_a_gap_not_zero(self):
        rows = self.require_adapter().adapt(
            self.fixture("marketplace-promptbase-aggregate.json"),
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
            platform="promptbase",
            product_loop_id="writer",
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in rows))
        gaps = [row for row in rows if row["record_type"] == "coverage"]
        self.assertEqual(
            {(row["projection"], row["coverage_state"], row["reason"])
             for row in gaps},
            {
                ("historical", "gap", "missing_coverage"),
                ("trailing", "gap", "missing_coverage"),
                ("as_of", "gap", "missing_category"),
            },
        )
        projected = contract.project(
            rows,
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
        )
        self.assertEqual(
            projected["historical"]["loops"]["writer"]["status"],
            "unknown",
        )

    def test_same_provider_identity_replays_deterministically_and_b0_reports_duplicate(self):
        first = self.adapt("marketplace-settled.json")
        second = self.require_adapter().adapt(
            self.fixture("marketplace-settled.json"),
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
        )
        self.assertEqual(first, second)
        payment = next(
            row for row in first
            if row.get("receipt_id") == "marketplace:lancers:payment:payment-1"
        )
        replay = contract.project(
            [*first, copy.deepcopy(payment)],
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
        )
        self.assertEqual(replay["duplicate_receipts"], [{
            "provider": "marketplace-lancers",
            "receipt_id": "marketplace:lancers:payment:payment-1",
        }])

    def test_conflicting_same_payment_identity_is_a_coverage_gap(self):
        payload = self.fixture("marketplace-settled.json")
        conflicting = copy.deepcopy(payload["receipt_map"]["records"][0])
        conflicting["gross_amount_minor"] += 1
        conflicting["net_amount_minor"] += 1
        payload["receipt_map"]["records"].append(conflicting)
        payload["pagination"]["records_fetched"] += 1
        self.bind(payload)
        rows = self.require_adapter().adapt(
            payload,
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in rows))
        self.assertEqual(
            {(row["projection"], row["reason"])
             for row in rows if row["record_type"] == "coverage"},
            {
                ("historical", "unverified_receipt"),
                ("trailing", "unverified_receipt"),
                ("as_of", "missing_category"),
            },
        )

    def test_incomplete_pagination_is_not_partial_revenue(self):
        payload = self.fixture("marketplace-settled.json")
        payload["pagination"]["complete"] = False
        payload["pagination"]["next_cursor"] = "page-2"
        self.bind(payload)
        rows = self.require_adapter().adapt(
            payload,
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in rows))
        self.assertEqual(
            {row["reason"] for row in rows
             if row["record_type"] == "coverage" and row["projection"] != "as_of"},
            {"missing_coverage"},
        )

    def test_unknown_receipt_shape_is_fail_closed(self):
        payload = self.fixture("marketplace-settled.json")
        payload["receipt_map"]["records"][0]["unexpected"] = "new-provider-field"
        self.bind(payload)
        rows = self.require_adapter().adapt(
            payload,
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in rows))
        self.assertEqual(
            {row["reason"] for row in rows
             if row["record_type"] == "coverage" and row["projection"] != "as_of"},
            {"unverified_receipt"},
        )

    def test_incomplete_trailing_coverage_keeps_receipts_but_marks_trailing_unknown(self):
        payload = self.fixture("marketplace-settled.json")
        payload["coverage"]["trailing"]["complete"] = False
        self.bind(payload)
        rows = self.require_adapter().adapt(
            payload,
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
        )
        self.assertTrue(any(row["record_type"] == "receipt" for row in rows))
        coverage = {
            row["projection"]: row
            for row in rows
            if row["record_type"] == "coverage"
        }
        self.assertEqual((coverage["historical"]["coverage_state"], coverage["historical"]["reason"]),
                         ("complete", None))
        self.assertEqual((coverage["trailing"]["coverage_state"], coverage["trailing"]["reason"]),
                         ("gap", "missing_coverage"))

    def test_stale_readback_emits_no_receipts(self):
        payload = self.fixture("marketplace-settled.json")
        payload["observed_at"] = "2026-09-30T23:59:59Z"
        self.bind(payload)
        rows = self.require_adapter().adapt(
            payload,
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in rows))
        self.assertEqual(
            {row["reason"] for row in rows
             if row["record_type"] == "coverage" and row["projection"] != "as_of"},
            {"stale_readback"},
        )

    def test_embedded_and_itemized_provider_fee_cannot_be_counted_twice(self):
        payload = self.fixture("marketplace-settled.json")
        payload["receipt_map"]["records"].append({
            "schema_version": 1,
            "record_type": "fee_receipt",
            "platform": "lancers",
            "payment_external_id": "payment-1",
            "receipt_id": "fee-duplicate-provider",
            "fee_type": "provider_fee",
            "amount_minor": 4500,
            "currency": "JPY",
            "occurred_at": "2026-09-26T03:00:00Z",
            "settled_at": "2026-09-26T03:00:00Z",
            "observed_at": SNAPSHOT,
        })
        payload["pagination"]["records_fetched"] += 1
        self.bind(payload)
        rows = self.require_adapter().adapt(
            payload,
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in rows))
        self.assertEqual(
            {row["reason"] for row in rows
             if row["record_type"] == "coverage" and row["projection"] != "as_of"},
            {"unverified_receipt"},
        )

    def test_envelope_aggregate_is_exact_and_reconciles_receipt_map(self):
        cases = []

        malformed = self.fixture("marketplace-settled.json")
        del malformed["aggregate"]["net_amount_minor"]
        cases.append(("missing aggregate field", malformed))

        unknown = self.fixture("marketplace-settled.json")
        unknown["aggregate"]["unexpected"] = 1
        cases.append(("unknown aggregate field", unknown))

        count_conflict = self.fixture("marketplace-settled.json")
        count_conflict["aggregate"]["sales_count"] = 3
        cases.append(("settled payment count conflict", count_conflict))

        net_conflict = self.fixture("marketplace-settled.json")
        net_conflict["aggregate"]["net_amount_minor"] = 45301
        cases.append(("net amount conflict", net_conflict))

        missing_currency = self.fixture("marketplace-settled.json")
        missing_currency["aggregate"].pop("currency", None)
        cases.append(("missing aggregate currency", missing_currency))

        for name, payload in cases:
            with self.subTest(name=name):
                self.bind(payload)
                rows = self.require_adapter().adapt(
                    payload,
                    snapshot_at=SNAPSHOT,
                    trailing_start=TRAILING_START,
                )
                self.assertFalse(any(row["record_type"] == "receipt" for row in rows))
                self.assertEqual(
                    {row["reason"] for row in rows
                     if row["record_type"] == "coverage" and row["projection"] != "as_of"},
                    {"unverified_receipt"},
                )

    def test_mixed_receipt_currencies_are_a_gap_for_single_currency_aggregate(self):
        payload = self.fixture("marketplace-settled.json")
        payload["aggregate"]["currency"] = "JPY"
        usd_payment = copy.deepcopy(payload["receipt_map"]["records"][1])
        usd_payment.update({
            "work_external_id": "work-usd",
            "payment_external_id": "payment-usd",
            "receipt_id": "payment-usd",
            "gross_amount_minor": 1000,
            "net_amount_minor": 1000,
            "currency": "USD",
            "occurred_at": "2026-09-28T03:00:00Z",
        })
        payload["receipt_map"]["records"].append(usd_payment)
        payload["pagination"]["records_fetched"] += 1
        payload["aggregate"]["sales_count"] = 3
        payload["aggregate"]["net_amount_minor"] = 46300
        self.bind(payload)
        rows = self.require_adapter().adapt(
            payload,
            snapshot_at=SNAPSHOT,
            trailing_start=TRAILING_START,
        )
        self.assertFalse(any(row["record_type"] == "receipt" for row in rows))
        self.assertEqual(
            {row["reason"] for row in rows
             if row["record_type"] == "coverage" and row["projection"] != "as_of"},
            {"unverified_receipt"},
        )

    def test_payment_pending_and_movement_future_times_are_gaps(self):
        cases = []

        future_payment = self.fixture("marketplace-settled.json")
        payment = next(row for row in future_payment["receipt_map"]["records"]
                       if row.get("record_type") == "payment_receipt"
                       and row.get("payment_external_id") == "payment-2")
        payment["occurred_at"] = "2026-10-01T00:00:01Z"
        future_payment["receipt_map"]["records"] = [
            row for row in future_payment["receipt_map"]["records"]
            if not (
                row.get("record_type") == "fee_receipt"
                and row.get("payment_external_id") == "payment-2"
            )
        ]
        future_payment["pagination"]["records_fetched"] -= 1
        future_payment["aggregate"]["net_amount_minor"] = 45500
        cases.append(("payment after readback", future_payment))

        future_pending = self.fixture("marketplace-settled.json")
        pending = next(row for row in future_pending["receipt_map"]["records"]
                       if row.get("record_type") == "pending_payment_receipt")
        pending["occurred_at"] = "2026-10-01T00:00:01Z"
        cases.append(("pending payment after readback", future_pending))

        future_movement = self.fixture("marketplace-settled.json")
        movement = next(row for row in future_movement["receipt_map"]["records"]
                        if row.get("record_type") == "movement_receipt")
        movement["occurred_at"] = "2026-10-01T00:00:01Z"
        movement["settled_at"] = "2026-10-01T00:00:01Z"
        cases.append(("movement after readback", future_movement))

        for name, payload in cases:
            with self.subTest(name=name):
                self.bind(payload)
                rows = self.require_adapter().adapt(
                    payload,
                    snapshot_at=SNAPSHOT,
                    trailing_start=TRAILING_START,
                )
                self.assertFalse(any(row["record_type"] == "receipt" for row in rows))
                self.assertEqual(
                    {row["reason"] for row in rows
                     if row["record_type"] == "coverage" and row["projection"] != "as_of"},
                    {"unverified_receipt"},
                )

    def test_fee_and_refund_times_stay_between_payment_and_readback(self):
        cases = []

        before_payment = self.fixture("marketplace-settled.json")
        fee = next(row for row in before_payment["receipt_map"]["records"]
                   if row.get("record_type") == "fee_receipt")
        fee["occurred_at"] = "2026-09-26T02:59:59Z"
        fee["settled_at"] = "2026-09-26T02:59:59Z"
        cases.append(("fee before linked payment", before_payment))

        after_readback = self.fixture("marketplace-settled.json")
        fee = next(row for row in after_readback["receipt_map"]["records"]
                   if row.get("record_type") == "fee_receipt")
        fee["settled_at"] = "2026-10-01T00:00:01Z"
        cases.append(("fee after readback", after_readback))

        refund_after_readback = self.fixture("marketplace-settled.json")
        refund = next(row for row in refund_after_readback["receipt_map"]["records"]
                      if row.get("record_type") == "refund_receipt")
        refund["occurred_at"] = "2026-10-02T00:00:00Z"
        cases.append(("refund after readback", refund_after_readback))

        for name, payload in cases:
            with self.subTest(name=name):
                self.bind(payload)
                rows = self.require_adapter().adapt(
                    payload,
                    snapshot_at=SNAPSHOT,
                    trailing_start=TRAILING_START,
                )
                self.assertFalse(any(row["record_type"] == "receipt" for row in rows))
                self.assertEqual(
                    {row["reason"] for row in rows
                     if row["record_type"] == "coverage" and row["projection"] != "as_of"},
                    {"unverified_receipt"},
                )

    def test_distinct_source_links_cannot_share_a_provider_scoped_receipt_id(self):
        payment_collision = self.fixture("marketplace-settled.json")
        extra_payment = copy.deepcopy(payment_collision["receipt_map"]["records"][0])
        extra_payment.update({
            "work_external_id": "work-collision",
            "payment_external_id": "payment-collision",
            "gross_amount_minor": 1000,
            "net_amount_minor": 1000,
            "occurred_at": "2026-09-28T03:00:00Z",
        })
        payment_collision["receipt_map"]["records"].append(extra_payment)
        payment_collision["pagination"]["records_fetched"] += 1
        payment_collision["aggregate"]["sales_count"] = 3
        payment_collision["aggregate"]["net_amount_minor"] = 46300

        pending_collision = self.fixture("marketplace-settled.json")
        extra_pending = copy.deepcopy(next(
            row for row in pending_collision["receipt_map"]["records"]
            if row.get("record_type") == "pending_payment_receipt"
        ))
        extra_pending["payment_external_id"] = "payment-pending-collision"
        pending_collision["receipt_map"]["records"].append(extra_pending)
        pending_collision["pagination"]["records_fetched"] += 1

        for name, payload in (
            ("payment receipt identity collision", payment_collision),
            ("pending source identity collision", pending_collision),
        ):
            with self.subTest(name=name):
                self.bind(payload)
                rows = self.require_adapter().adapt(
                    payload,
                    snapshot_at=SNAPSHOT,
                    trailing_start=TRAILING_START,
                )
                self.assertFalse(any(row["record_type"] == "receipt" for row in rows))
                self.assertEqual(
                    {row["reason"] for row in rows
                     if row["record_type"] == "coverage" and row["projection"] != "as_of"},
                    {"unverified_receipt"},
                )

    def test_payout_timestamp_is_linked_payment_time_across_reobservations(self):
        first = self.adapt("marketplace-settled.json")
        first_payout = next(
            row for row in first
            if row.get("receipt_id") == "marketplace:lancers:payout:payout-1"
        )
        self.assertEqual(first_payout["occurred_at"], "2026-09-26T03:00:00.000000Z")
        self.assertEqual(first_payout["settled_at"], "2026-09-26T03:00:00.000000Z")

        reread = self.reobserve(
            self.fixture("marketplace-settled.json"),
            "2026-10-02T00:00:00Z",
        )
        second = self.require_adapter().adapt(
            reread,
            snapshot_at="2026-10-02T00:00:00Z",
            trailing_start=TRAILING_START,
        )
        second_payout = next(
            row for row in second
            if row.get("receipt_id") == "marketplace:lancers:payout:payout-1"
        )
        self.assertEqual(second_payout["receipt_id"], first_payout["receipt_id"])
        self.assertEqual(second_payout["occurred_at"], first_payout["occurred_at"])
        self.assertEqual(second_payout["settled_at"], first_payout["settled_at"])


if __name__ == "__main__":
    unittest.main()
