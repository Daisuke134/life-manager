"""Stripe official readback payloads to B0 economic attribution records."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from skills.cfo import economic_attribution as contract
from skills.cfo.adapters import stripe


FIXTURES = Path(__file__).parent / "fixtures/economic_attribution"
OBSERVED_AT = "2026-10-01T00:00:00Z"
TRAILING_START = "2026-09-01T00:00:00Z"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def payloads() -> dict:
    return {
        "readback": {
            "provider": "stripe",
            "provenance": "stripe_api",
            "read_at": OBSERVED_AT,
            "queries": {
                "trailing": {
                    "start": TRAILING_START,
                    "end": OBSERVED_AT,
                    "has_more": False,
                },
            },
        },
        **{
            name: fixture(f"stripe-{name.replace('_', '-')}.json")
            for name in ("balance_transactions", "charges", "refunds", "subscriptions")
        },
    }


def adapt(value: dict | None = None, *, observed_at: str = OBSERVED_AT) -> list[dict]:
    return stripe.adapt(
        payloads() if value is None else value,
        product_loop_id="self-build",
        observed_at=observed_at,
        trailing_start=TRAILING_START,
    )


class StripeAttributionTest(unittest.TestCase):
    def test_cross_currency_settlement_uses_balance_transaction_currency(self):
        value = payloads()
        charge = next(row for row in value["charges"]["data"]
                      if row["id"] == "ch_external_usd")
        charge_transaction = next(row for row in value["balance_transactions"]["data"]
                                  if row["id"] == "txn_charge_usd")
        refund_transaction = next(row for row in value["balance_transactions"]["data"]
                                 if row["id"] == "txn_refund_usd")
        charge_transaction.update(currency="jpy", amount=723, fee=26, net=697)
        refund_transaction.update(currency="jpy", amount=-737, fee=0, net=-737)

        rows = adapt(value)
        receipts = {
            row["receipt_id"]: row for row in rows if row["record_type"] == "receipt"
        }
        self.assertEqual(receipts["stripe:balance_transaction:txn_charge_usd"]["currency"], "JPY")
        self.assertEqual(
            receipts["stripe:balance_transaction:txn_charge_usd"]["components"],
            [
                {"category": "payment_fee", "amount": "26"},
                {"category": "settled_external_revenue", "amount": "723"},
            ],
        )
        self.assertEqual(receipts["stripe:balance_transaction:txn_refund_usd"]["currency"], "JPY")
        self.assertEqual(
            receipts["stripe:balance_transaction:txn_refund_usd"]["components"],
            [{"category": "refund", "amount": "737"}],
        )
        trailing = next(row for row in rows
                        if row["record_type"] == "coverage" and row["projection"] == "trailing")
        self.assertEqual((trailing["coverage_state"], trailing["reason"]), ("complete", None))

    def test_explicit_account_default_classifies_only_unannotated_live_charge(self):
        value = payloads()
        charge = next(row for row in value["charges"]["data"]
                      if row["id"] == "ch_external_usd")
        charge["metadata"] = {}

        rows = stripe.adapt(
            value,
            product_loop_id="self-build",
            observed_at=OBSERVED_AT,
            trailing_start=TRAILING_START,
            default_economic_category=contract.REVENUE,
        )
        receipts = {
            row["receipt_id"]: row for row in rows if row["record_type"] == "receipt"
        }
        self.assertIn("stripe:balance_transaction:txn_charge_usd", receipts)
        self.assertEqual(
            next(row for row in rows
                 if row["record_type"] == "coverage" and row["projection"] == "trailing")["coverage_state"],
            "complete",
        )
        self.assertEqual(
            next(row for row in rows
                 if row["record_type"] == "coverage" and row["projection"] == "as_of")["coverage_state"],
            "complete",
        )

    def test_explicit_unknown_charge_classification_overrides_account_default_fail_closed(self):
        value = payloads()
        charge = next(row for row in value["charges"]["data"]
                      if row["id"] == "ch_external_usd")
        charge["metadata"] = {"lm_economic_category": "unknown_classification"}

        rows = stripe.adapt(
            value,
            product_loop_id="self-build",
            observed_at=OBSERVED_AT,
            trailing_start=TRAILING_START,
            default_economic_category=contract.REVENUE,
        )
        trailing = next(row for row in rows
                        if row["record_type"] == "coverage" and row["projection"] == "trailing")
        self.assertEqual((trailing["coverage_state"], trailing["reason"]), ("gap", "unverified_receipt"))

    def test_historical_unhandled_balance_transaction_does_not_poison_trailing_window(self):
        value = payloads()
        value["balance_transactions"]["data"].append({
            "id": "txn_old_adjustment",
            "object": "balance_transaction",
            "amount": 1,
            "available_on": 1785542400,
            "created": 1785542400,
            "currency": "usd",
            "fee": 0,
            "net": 1,
            "source": None,
            "status": "available",
            "type": "adjustment",
        })

        rows = adapt(value)
        trailing = next(row for row in rows
                        if row["record_type"] == "coverage" and row["projection"] == "trailing")
        self.assertEqual((trailing["coverage_state"], trailing["reason"]), ("complete", None))

    def test_unhandled_transaction_settled_in_window_keeps_trailing_gap(self):
        value = payloads()
        value["balance_transactions"]["data"].append({
            "id": "txn_old_created_window_settled",
            "object": "balance_transaction",
            "amount": 1,
            "available_on": 1789430400,
            "created": 1788134400,
            "currency": "usd",
            "fee": 0,
            "net": 1,
            "source": None,
            "status": "available",
            "type": "adjustment",
        })

        rows = adapt(value)
        trailing = next(row for row in rows
                        if row["record_type"] == "coverage" and row["projection"] == "trailing")
        self.assertEqual((trailing["coverage_state"], trailing["reason"]),
                         ("gap", "unverified_receipt"))

    def test_failure_with_unknown_settlement_time_keeps_trailing_gap(self):
        value = payloads()
        value["balance_transactions"]["data"].append({
            "id": "txn_unknown_time",
            "object": "balance_transaction",
            "amount": 1,
            "currency": "usd",
            "fee": 0,
            "net": 1,
            "source": None,
            "status": "available",
            "type": "adjustment",
        })

        rows = adapt(value)
        trailing = next(row for row in rows
                        if row["record_type"] == "coverage" and row["projection"] == "trailing")
        self.assertEqual((trailing["coverage_state"], trailing["reason"]),
                         ("gap", "unverified_receipt"))

    def test_old_charge_failure_is_relevant_when_linked_refund_settles_in_window(self):
        value = payloads()
        transactions = {row["id"]: row for row in value["balance_transactions"]["data"]}
        charges = {row["id"]: row for row in value["charges"]["data"]}
        refunds = {row["id"]: row for row in value["refunds"]["data"]}
        charges["ch_external_usd"]["created"] = 1788134400
        transactions["txn_charge_usd"]["created"] = 1788134400
        transactions["txn_charge_usd"]["available_on"] = 1788134400
        refunds["re_external_usd"]["created"] = 1788134400
        transactions["txn_refund_usd"]["created"] = 1788134400
        transactions["txn_refund_usd"]["available_on"] = 1789430400

        refs = stripe._trailing_refs(
            ["stripe://charges/ch_external_usd"], transactions, charges, refunds,
            TRAILING_START, OBSERVED_AT,
        )
        self.assertEqual(refs, ["stripe://charges/ch_external_usd"])

    def test_available_external_gross_refund_and_fees_are_each_recorded_once(self):
        rows = adapt()
        receipts = {row["receipt_id"]: row for row in rows if row["record_type"] == "receipt"}

        self.assertEqual(receipts["stripe:balance_transaction:txn_charge_usd"]["components"], [
            {"category": "payment_fee", "amount": "0.88"},
            {"category": "settled_external_revenue", "amount": "19.99"},
        ])
        self.assertEqual(receipts["stripe:balance_transaction:txn_refund_usd"]["components"], [
            {"category": "refund", "amount": "5"},
        ])
        self.assertEqual(receipts["stripe:balance_transaction:txn_stripe_fee"]["components"], [
            {"category": "provider_fee", "amount": "1.25"},
        ])
        self.assertEqual(receipts["stripe:balance_transaction:txn_charge_jpy"]["components"], [
            {"category": "payment_fee", "amount": "108"},
            {"category": "settled_external_revenue", "amount": "3000"},
        ])
        for row in rows:
            contract.validate_record(row)

    def test_pending_and_internal_movements_are_excluded_not_revenue(self):
        receipts = {
            row["receipt_id"]: row for row in adapt() if row["record_type"] == "receipt"
        }
        expected = {
            "txn_pending_usd": ("pending_revenue", "25", "pending", None),
            "txn_self_payment": ("self_payment", "9", "verified", "2026-09-30T23:00:00.000000Z"),
            "txn_payout": ("payout", "100", "verified", "2026-09-30T23:00:00.000000Z"),
            "txn_topup": ("owner_deposit", "500", "verified", "2026-09-30T23:00:00.000000Z"),
            "txn_transfer": ("internal_transfer", "7", "verified", "2026-09-30T23:00:00.000000Z"),
        }
        for transaction_id, (category, amount, state, settled_at) in expected.items():
            suffix = ":pending" if transaction_id == "txn_pending_usd" else ""
            row = receipts[f"stripe:balance_transaction:{transaction_id}{suffix}"]
            self.assertEqual(row["components"], [{"category": category, "amount": amount}])
            self.assertEqual(row["verification_state"], state)
            self.assertEqual(row["settled_at"], settled_at)
        revenue_receipts = [row for row in receipts.values()
                            if any(component["category"] == contract.REVENUE
                                   for component in row["components"])]
        self.assertEqual({row["receipt_id"] for row in revenue_receipts}, {
            "stripe:balance_transaction:txn_charge_usd",
            "stripe:balance_transaction:txn_charge_jpy",
        })

    def test_excluded_movements_record_fee_once_in_a_separate_receipt(self):
        expected = {
            "txn_self_payment": ("self_payment", "9"),
            "txn_payout": ("payout", "100"),
            "txn_topup": ("owner_deposit", "500"),
            "txn_transfer": ("internal_transfer", "7"),
        }
        for transaction_id, (category, amount) in expected.items():
            with self.subTest(transaction_id=transaction_id):
                value = payloads()
                transaction = next(row for row in value["balance_transactions"]["data"]
                                   if row["id"] == transaction_id)
                transaction.update(fee=50, net=transaction["amount"] - 50)
                rows = adapt(value)
                receipts = {
                    row["receipt_id"]: row for row in rows if row["record_type"] == "receipt"
                }
                receipt_id = f"stripe:balance_transaction:{transaction_id}"
                fee_receipt_id = f"{receipt_id}:fee"
                self.assertEqual(
                    receipts[receipt_id]["components"],
                    [{"category": category, "amount": amount}],
                )
                self.assertIn(fee_receipt_id, receipts)
                self.assertEqual(
                    receipts[fee_receipt_id]["components"],
                    [{"category": "payment_fee", "amount": "0.5"}],
                )
                matching_fees = [
                    row for row in receipts.values()
                    if row["components"] == [{"category": "payment_fee", "amount": "0.5"}]
                    and f"stripe://balance_transactions/{transaction_id}" in row["evidence_refs"]
                ]
                self.assertEqual([row["receipt_id"] for row in matching_fees], [fee_receipt_id])
                trailing = next(row for row in rows
                                if row.get("record_type") == "coverage"
                                and row.get("projection") == "trailing")
                self.assertEqual(
                    (trailing["coverage_state"], trailing["reason"]),
                    ("complete", None),
                )

    def test_pending_charge_with_fee_is_a_coverage_gap(self):
        value = payloads()
        transaction = next(row for row in value["balance_transactions"]["data"]
                           if row["id"] == "txn_pending_usd")
        transaction.update(fee=50, net=2450)

        rows = adapt(value)
        self.assertFalse(any(
            row.get("receipt_id", "").startswith(
                "stripe:balance_transaction:txn_pending_usd"
            ) for row in rows
        ))
        trailing = next(row for row in rows
                        if row.get("record_type") == "coverage"
                        and row.get("projection") == "trailing")
        self.assertEqual(
            (trailing["coverage_state"], trailing["reason"]),
            ("gap", "unverified_receipt"),
        )

    def test_complete_charge_collection_requires_matching_balance_transaction(self):
        value = payloads()
        value["charges"]["data"].append({
            "id": "ch_silent", "object": "charge", "amount": 1200,
            "amount_captured": 1200, "amount_refunded": 0,
            "balance_transaction": "txn_absent", "captured": True,
            "created": 1790808000, "currency": "usd", "customer": "cus_silent",
            "disputed": False, "livemode": True,
            "metadata": {"lm_economic_category": "settled_external_revenue"},
            "paid": True, "refunded": False, "status": "succeeded",
        })

        rows = adapt(value)
        self.assertFalse(any(row.get("receipt_id") ==
                             "stripe:balance_transaction:txn_absent" for row in rows))
        trailing = next(row for row in rows
                        if row.get("record_type") == "coverage"
                        and row.get("projection") == "trailing")
        self.assertEqual(
            (trailing["coverage_state"], trailing["reason"]),
            ("gap", "unverified_receipt"),
        )
        self.assertIn("stripe://charges/ch_silent", trailing["evidence_refs"])

    def test_unpaid_external_captured_charge_cannot_hide_missing_balance_transaction(self):
        value = payloads()
        charge = value["charges"]["data"][0]
        charge.update(paid=False, amount_refunded=0, balance_transaction="txn_absent")
        value["balance_transactions"]["data"] = [
            transaction for transaction in value["balance_transactions"]["data"]
            if transaction["id"] not in {"txn_charge_usd", "txn_refund_usd"}
        ]
        value["refunds"]["data"] = []

        rows = adapt(value)
        trailing = next(row for row in rows
                        if row.get("record_type") == "coverage"
                        and row.get("projection") == "trailing")
        self.assertEqual(
            (trailing["coverage_state"], trailing["reason"]),
            ("gap", "unverified_receipt"),
        )
        self.assertIn("stripe://charges/ch_external_usd", trailing["evidence_refs"])

    def test_active_verified_provider_monthly_subscription_is_the_only_mrr(self):
        rows = adapt()
        snapshots = [row for row in rows if row["record_type"] == "subscription_snapshot"]
        self.assertEqual(snapshots, [
            {
                "schema_version": contract.SCHEMA_VERSION,
                "record_type": "subscription_snapshot",
                "snapshot_id": "stripe:subscription:sub_canceled:2026-10-01T00:00:00Z",
                "subscription_id": "stripe:subscription:sub_canceled",
                "product_loop_id": "self-build",
                "provider": "stripe",
                "currency": "USD",
                "normalized_monthly_amount": "0",
                "normalization_basis": "provider_monthly",
                "status": "inactive",
                "observed_at": "2026-10-01T00:00:00.000000Z",
                "verification_state": "verified",
                "evidence_refs": ["stripe://subscriptions/sub_canceled"],
            },
            {
                "schema_version": contract.SCHEMA_VERSION,
                "record_type": "subscription_snapshot",
                "snapshot_id": "stripe:subscription:sub_monthly:2026-10-01T00:00:00Z",
                "subscription_id": "stripe:subscription:sub_monthly",
                "product_loop_id": "self-build",
                "provider": "stripe",
                "currency": "USD",
                "normalized_monthly_amount": "29.98",
                "normalization_basis": "provider_monthly",
                "status": "active",
                "observed_at": "2026-10-01T00:00:00.000000Z",
                "verification_state": "verified",
                "evidence_refs": ["stripe://subscriptions/sub_monthly"],
            },
        ])

    def test_unknown_dispute_missing_linkage_and_nonmonthly_subscription_are_coverage_gaps(self):
        rows = adapt(fixture("stripe-unknown.json"))
        self.assertFalse(any(row["record_type"] in {"receipt", "subscription_snapshot"}
                             for row in rows))
        gaps = [row for row in rows if row["record_type"] == "coverage"]
        self.assertEqual({(row["projection"], row["coverage_state"], row["reason"])
                          for row in gaps}, {
            ("historical", "gap", "unverified_receipt"),
            ("trailing", "gap", "unverified_receipt"),
            ("as_of", "gap", "unverified_receipt"),
        })
        refs = {ref for row in gaps for ref in row["evidence_refs"]}
        self.assertTrue({
            "stripe://balance_transactions/txn_missing_charge",
            "stripe://balance_transactions/txn_disputed_charge",
            "stripe://balance_transactions/txn_adjustment",
            "stripe://subscriptions/sub_yearly",
        }.issubset(refs))
        for row in gaps:
            contract.validate_record(row)

    def test_missing_or_unknown_server_side_economic_class_never_becomes_revenue(self):
        for classification in (None, "unknown_classification"):
            with self.subTest(classification=classification):
                value = payloads()
                metadata = value["charges"]["data"][0]["metadata"]
                if classification is None:
                    metadata.clear()
                else:
                    metadata["lm_economic_category"] = classification
                rows = adapt(value)
                self.assertFalse(any(
                    row.get("receipt_id") == "stripe:balance_transaction:txn_charge_usd"
                    for row in rows
                ))
                self.assertFalse(any(
                    row.get("receipt_id") == "stripe:balance_transaction:txn_refund_usd"
                    for row in rows
                ))
                financial = [row for row in rows if row["record_type"] == "coverage"
                             and row["projection"] != "as_of"]
                self.assertEqual({row["coverage_state"] for row in financial}, {"gap"})
                self.assertEqual({row["reason"] for row in financial}, {"unverified_receipt"})

    def test_unclassified_successful_charge_cannot_hide_missing_balance_transaction(self):
        for classification in (None, "unknown_classification"):
            with self.subTest(classification=classification):
                value = payloads()
                charge = next(row for row in value["charges"]["data"]
                              if row["id"] == "ch_external_jpy")
                if classification is None:
                    charge["metadata"].clear()
                else:
                    charge["metadata"]["lm_economic_category"] = classification
                value["balance_transactions"]["data"] = [
                    row for row in value["balance_transactions"]["data"]
                    if row["id"] != "txn_charge_jpy"
                ]

                rows = adapt(value)
                self.assertFalse(any(
                    row.get("receipt_id") == "stripe:balance_transaction:txn_charge_jpy"
                    for row in rows
                ))
                trailing = next(row for row in rows
                                if row.get("record_type") == "coverage"
                                and row.get("projection") == "trailing")
                self.assertEqual(
                    (trailing["coverage_state"], trailing["reason"]),
                    ("gap", "unverified_receipt"),
                )
                self.assertIn(
                    "stripe://charges/ch_external_jpy", trailing["evidence_refs"]
                )

    def test_invalid_charge_boolean_flags_cannot_hide_missing_balance_transaction(self):
        flag_cases = {
            "captured_missing": lambda charge: charge.pop("captured"),
            "captured_string": lambda charge: charge.update(captured="true"),
            "livemode_missing": lambda charge: charge.pop("livemode"),
            "livemode_string": lambda charge: charge.update(livemode="true"),
        }
        classifications = ("unknown_classification", "owner_deposit", "self_payment")
        for classification in classifications:
            for case, mutate in flag_cases.items():
                with self.subTest(classification=classification, case=case):
                    value = payloads()
                    charge = next(row for row in value["charges"]["data"]
                                  if row["id"] == "ch_external_jpy")
                    charge["metadata"]["lm_economic_category"] = classification
                    mutate(charge)
                    value["balance_transactions"]["data"] = [
                        row for row in value["balance_transactions"]["data"]
                        if row["id"] != "txn_charge_jpy"
                    ]

                    rows = adapt(value)
                    self.assertFalse(any(
                        row.get("receipt_id") == "stripe:balance_transaction:txn_charge_jpy"
                        for row in rows
                    ))
                    trailing = next(row for row in rows
                                    if row.get("record_type") == "coverage"
                                    and row.get("projection") == "trailing")
                    self.assertEqual(
                        (trailing["coverage_state"], trailing["reason"]),
                        ("gap", "unverified_receipt"),
                    )
                    self.assertIn(
                        "stripe://charges/ch_external_jpy", trailing["evidence_refs"]
                    )

    def test_explicit_false_charge_flags_remain_known_negative_states(self):
        for field in ("captured", "livemode"):
            with self.subTest(field=field):
                value = payloads()
                charge = next(row for row in value["charges"]["data"]
                              if row["id"] == "ch_external_jpy")
                charge[field] = False
                value["balance_transactions"]["data"] = [
                    row for row in value["balance_transactions"]["data"]
                    if row["id"] != "txn_charge_jpy"
                ]

                rows = adapt(value)
                trailing = next(row for row in rows
                                if row.get("record_type") == "coverage"
                                and row.get("projection") == "trailing")
                self.assertEqual(
                    (trailing["coverage_state"], trailing["reason"]),
                    ("complete", None),
                )
                self.assertNotIn(
                    "stripe://charges/ch_external_jpy", trailing["evidence_refs"]
                )

    def test_subscription_requires_trusted_external_economic_class(self):
        for classification in (None, "self_payment", "unknown_classification"):
            with self.subTest(classification=classification):
                value = payloads()
                metadata = value["subscriptions"]["data"][0]["metadata"]
                if classification is None:
                    metadata.clear()
                else:
                    metadata["lm_economic_category"] = classification
                rows = adapt(value)
                self.assertFalse(any(
                    row.get("subscription_id") == "stripe:subscription:sub_monthly"
                    for row in rows
                ))
                as_of = next(row for row in rows
                             if row["record_type"] == "coverage"
                             and row["projection"] == "as_of")
                self.assertEqual(as_of["coverage_state"], "gap")
                self.assertEqual(as_of["reason"], "unverified_receipt")

    def test_subscription_mrr_requires_live_licensed_per_unit_price_shape(self):
        def mutate_item_object(item, price):
            item["object"] = "invoiceitem"

        cases = {
            "item_object": mutate_item_object,
            "price_object": lambda item, price: price.update(object="product"),
            "price_livemode": lambda item, price: price.update(livemode=False),
            "usage_type": lambda item, price: price["recurring"].update(
                usage_type="metered"
            ),
            "billing_scheme": lambda item, price: price.update(billing_scheme="tiered"),
        }
        for case, mutate in cases.items():
            with self.subTest(case=case):
                value = payloads()
                item = value["subscriptions"]["data"][0]["items"]["data"][0]
                mutate(item, item["price"])
                rows = adapt(value)
                self.assertFalse(any(
                    row.get("subscription_id") == "stripe:subscription:sub_monthly"
                    for row in rows
                ))
                as_of = next(row for row in rows
                             if row["record_type"] == "coverage"
                             and row["projection"] == "as_of")
                self.assertEqual(
                    (as_of["coverage_state"], as_of["reason"]),
                    ("gap", "unverified_receipt"),
                )

    def test_charge_balance_transaction_requires_object_and_net_consistency(self):
        cases = {
            "object": lambda transaction: transaction.update(object="charge"),
            "net": lambda transaction: transaction.update(net=0),
        }
        for case, mutate in cases.items():
            with self.subTest(case=case):
                value = payloads()
                mutate(value["balance_transactions"]["data"][0])
                rows = adapt(value)
                self.assertFalse(any(
                    row.get("receipt_id") == "stripe:balance_transaction:txn_charge_usd"
                    for row in rows
                ))
                trailing = next(row for row in rows
                                if row["record_type"] == "coverage"
                                and row["projection"] == "trailing")
                self.assertEqual(
                    (trailing["coverage_state"], trailing["reason"]),
                    ("gap", "unverified_receipt"),
                )

    def test_refund_requires_fully_verified_original_charge_linkage(self):
        mutations = {
            "object": lambda charge, transactions: charge.update(object="payment_intent"),
            "currency": lambda charge, transactions: charge.update(currency="eur"),
            "status": lambda charge, transactions: charge.update(status="failed"),
            "paid": lambda charge, transactions: charge.update(paid=False),
            "captured": lambda charge, transactions: charge.update(captured=False),
            "disputed": lambda charge, transactions: charge.update(disputed=True),
            "balance_link": lambda charge, transactions: charge.update(balance_transaction="txn_other"),
            "captured_amount": lambda charge, transactions: charge.update(amount_captured=1998),
            "refunded_amount": lambda charge, transactions: charge.update(amount_refunded=499),
            "balance_amount": lambda charge, transactions: transactions[0].update(amount=1998),
        }
        for field, mutate in mutations.items():
            with self.subTest(field=field):
                value = payloads()
                mutate(value["charges"]["data"][0], value["balance_transactions"]["data"])
                rows = adapt(value)
                self.assertFalse(any(
                    row.get("receipt_id") == "stripe:balance_transaction:txn_refund_usd"
                    for row in rows
                ))
                financial = [row for row in rows if row["record_type"] == "coverage"
                             and row["projection"] != "as_of"]
                self.assertEqual({row["coverage_state"] for row in financial}, {"gap"})
                self.assertEqual({row["reason"] for row in financial}, {"unverified_receipt"})

    def test_charge_minor_amounts_require_positive_exact_integers(self):
        cases = {
            "amount_string": lambda charge, transaction: charge.update(amount="3000"),
            "amount_float": lambda charge, transaction: charge.update(amount=3000.0),
            "amount_bool": lambda charge, transaction: charge.update(amount=True),
            "amount_zero": lambda charge, transaction: charge.update(amount=0),
            "amount_negative": lambda charge, transaction: charge.update(amount=-1),
            "captured_float_equal": lambda charge, transaction: (
                transaction.update(amount=1, fee=0, net=1),
                charge.update(amount=1, amount_captured=1.0),
            ),
            "captured_bool_equal": lambda charge, transaction: (
                transaction.update(amount=1, fee=0, net=1),
                charge.update(amount=1, amount_captured=True),
            ),
            "negative_fee": lambda charge, transaction: transaction.update(
                fee=-1, net=3001
            ),
        }
        for case, mutate in cases.items():
            with self.subTest(case=case):
                value = payloads()
                charge = next(row for row in value["charges"]["data"]
                              if row["id"] == "ch_external_jpy")
                transaction = next(row for row in value["balance_transactions"]["data"]
                                   if row["id"] == "txn_charge_jpy")
                mutate(charge, transaction)
                rows = adapt(value)
                self.assertFalse(any(
                    row.get("receipt_id") == "stripe:balance_transaction:txn_charge_jpy"
                    for row in rows
                ))
                trailing = next(row for row in rows
                                if row.get("record_type") == "coverage"
                                and row.get("projection") == "trailing")
                self.assertEqual(
                    (trailing["coverage_state"], trailing["reason"]),
                    ("gap", "unverified_receipt"),
                )

    def test_refund_rejects_malformed_original_charge_balance_amounts(self):
        cases = {
            "fee_type": lambda transaction: transaction.update(fee="88"),
            "net_type": lambda transaction: transaction.update(net="1911"),
            "net_mismatch": lambda transaction: transaction.update(net=1900),
            "negative_fee": lambda transaction: transaction.update(fee=-88, net=2087),
        }
        for case, mutate in cases.items():
            with self.subTest(case=case):
                value = payloads()
                mutate(value["balance_transactions"]["data"][0])
                rows = adapt(value)
                self.assertFalse(any(
                    row.get("receipt_id") == "stripe:balance_transaction:txn_refund_usd"
                    for row in rows
                ))

    def test_refund_evidence_includes_original_charge_balance_transaction(self):
        refund = next(row for row in adapt()
                      if row.get("receipt_id") == "stripe:balance_transaction:txn_refund_usd")
        self.assertIn(
            "stripe://balance_transactions/txn_charge_usd",
            refund["evidence_refs"],
        )

    def test_refund_balance_transaction_requires_object_and_net_consistency(self):
        cases = {
            "object": lambda transaction: transaction.update(object="topup"),
            "net": lambda transaction: transaction.update(net=-999),
        }
        for case, mutate in cases.items():
            with self.subTest(case=case):
                value = payloads()
                mutate(value["balance_transactions"]["data"][1])
                rows = adapt(value)
                self.assertFalse(any(
                    row.get("receipt_id") == "stripe:balance_transaction:txn_refund_usd"
                    for row in rows
                ))
                trailing = next(row for row in rows
                                if row["record_type"] == "coverage"
                                and row["projection"] == "trailing")
                self.assertEqual(
                    (trailing["coverage_state"], trailing["reason"]),
                    ("gap", "unverified_receipt"),
                )

    def test_complete_refund_collections_must_reconcile_to_charge_total(self):
        def remove_refund_transaction(value):
            value["balance_transactions"]["data"] = [
                transaction for transaction in value["balance_transactions"]["data"]
                if transaction["id"] != "txn_refund_usd"
            ]

        def remove_refund_and_transaction(value):
            value["refunds"]["data"] = []
            remove_refund_transaction(value)

        cases = {
            "missing_refund_and_transaction": remove_refund_and_transaction,
            "missing_refund_transaction": remove_refund_transaction,
            "charge_total_mismatch": lambda value: value["charges"]["data"][0].update(
                amount_refunded=600
            ),
        }
        for case, mutate in cases.items():
            with self.subTest(case=case):
                value = payloads()
                mutate(value)
                rows = adapt(value)
                trailing = next(row for row in rows
                                if row["record_type"] == "coverage"
                                and row["projection"] == "trailing")
                self.assertEqual(
                    (trailing["coverage_state"], trailing["reason"]),
                    ("gap", "unverified_receipt"),
                )

    def test_movements_require_available_balance_transaction_sign_and_net(self):
        mutations = {
            "object": (6, lambda row: row.update(object="topup")),
            "pending_topup": (6, lambda row: row.update(status="pending")),
            "negative_topup": (6, lambda row: row.update(amount=-50000, net=-50000)),
            "positive_payout": (5, lambda row: row.update(amount=10000, net=10000)),
            "positive_transfer": (7, lambda row: row.update(amount=700, net=700)),
            "positive_stripe_fee": (8, lambda row: row.update(amount=125, net=125)),
            "net_mismatch": (6, lambda row: row.update(net=49999)),
        }
        for case, (index, mutate) in mutations.items():
            with self.subTest(case=case):
                value = payloads()
                transaction = value["balance_transactions"]["data"][index]
                transaction_id = transaction["id"]
                mutate(transaction)
                rows = adapt(value)
                self.assertFalse(any(
                    row.get("receipt_id") == f"stripe:balance_transaction:{transaction_id}"
                    for row in rows
                ))
                financial = [row for row in rows if row["record_type"] == "coverage"
                             and row["projection"] != "as_of"]
                self.assertEqual({row["coverage_state"] for row in financial}, {"gap"})
                self.assertEqual({row["reason"] for row in financial}, {"unverified_receipt"})

    def test_readback_envelope_prevents_stale_or_unproven_retimestamping(self):
        cases = {
            "missing": (lambda value: value.pop("readback"), "read_failed"),
            "provenance": (
                lambda value: value["readback"].update(provenance="caller_supplied"),
                "read_failed",
            ),
            "stale_read_at": (
                lambda value: value["readback"].update(read_at="2026-09-30T00:00:00Z"),
                "stale_readback",
            ),
            "window_start": (
                lambda value: value["readback"]["queries"]["trailing"].update(
                    start="2026-09-02T00:00:00Z"
                ),
                "stale_readback",
            ),
            "window_end": (
                lambda value: value["readback"]["queries"]["trailing"].update(
                    end="2026-09-30T00:00:00Z"
                ),
                "stale_readback",
            ),
        }
        for case, (mutate, reason) in cases.items():
            with self.subTest(case=case):
                value = payloads()
                mutate(value)
                rows = adapt(value)
                self.assertFalse(any(
                    row["record_type"] in {"receipt", "subscription_snapshot"}
                    for row in rows
                ))
                coverage = [row for row in rows if row["record_type"] == "coverage"]
                self.assertEqual(len(coverage), 3)
                self.assertEqual({row["coverage_state"] for row in coverage}, {"gap"})
                self.assertEqual({row["reason"] for row in coverage}, {reason})

    def test_readback_datetime_boundaries_fail_closed(self):
        cases = {
            "minimum_with_positive_offset": lambda value: value["readback"].update(
                read_at="0001-01-01T00:00:00+14:00"
            ),
            "maximum_with_negative_offset": lambda value: value["readback"].update(
                read_at="9999-12-31T23:59:59-14:00"
            ),
        }
        for case, mutate in cases.items():
            with self.subTest(case=case):
                value = payloads()
                mutate(value)
                try:
                    rows = adapt(value)
                except (OverflowError, OSError, ValueError) as error:
                    self.fail(f"datetime error escaped adapter: {type(error).__name__}")
                self.assertFalse(any(
                    row["record_type"] in {"receipt", "subscription_snapshot"}
                    for row in rows
                ))
                coverage = [row for row in rows if row["record_type"] == "coverage"]
                self.assertEqual(len(coverage), 3)
                self.assertEqual({row["coverage_state"] for row in coverage}, {"gap"})
                self.assertEqual({row["reason"] for row in coverage}, {"read_failed"})

    def test_historical_coverage_requires_its_own_complete_query_proof(self):
        unproven = adapt()
        unproven_coverage = {
            row["projection"]: row for row in unproven if row["record_type"] == "coverage"
        }
        self.assertEqual(
            (unproven_coverage["historical"]["coverage_state"],
             unproven_coverage["historical"]["reason"]),
            ("gap", "read_failed"),
        )
        self.assertEqual(
            (unproven_coverage["trailing"]["coverage_state"],
             unproven_coverage["trailing"]["reason"]),
            ("complete", None),
        )

        history_start_only = payloads()
        history_start_only["readback"]["queries"]["historical"] = {
            "history_start": "2025-01-01T00:00:00Z",
            "end": OBSERVED_AT,
            "has_more": False,
        }
        history_start_only_coverage = {
            row["projection"]: row for row in adapt(history_start_only)
            if row["record_type"] == "coverage"
        }
        self.assertEqual(
            (history_start_only_coverage["historical"]["coverage_state"],
             history_start_only_coverage["historical"]["reason"]),
            ("gap", "read_failed"),
        )
        self.assertEqual(
            (history_start_only_coverage["trailing"]["coverage_state"],
             history_start_only_coverage["trailing"]["reason"]),
            ("complete", None),
        )

        inception_proven = payloads()
        inception_proven["readback"]["queries"]["historical"] = {
            "account_inception": True,
            "end": OBSERVED_AT,
            "has_more": False,
        }
        inception_coverage = {
            row["projection"]: row for row in adapt(inception_proven)
            if row["record_type"] == "coverage"
        }
        self.assertEqual(
            (inception_coverage["historical"]["coverage_state"],
             inception_coverage["historical"]["reason"]),
            ("gap", "read_failed"),
        )
        self.assertEqual(
            (inception_coverage["trailing"]["coverage_state"],
             inception_coverage["trailing"]["reason"]),
            ("complete", None),
        )

        fully_proven = payloads()
        fully_proven["readback"]["queries"]["historical"] = {
            "account_inception": True,
            "history_start": "2025-01-01T00:00:00Z",
            "end": OBSERVED_AT,
            "has_more": False,
        }
        fully_proven_coverage = {
            row["projection"]: row for row in adapt(fully_proven)
            if row["record_type"] == "coverage"
        }
        for projection in ("historical", "trailing"):
            self.assertEqual(
                (fully_proven_coverage[projection]["coverage_state"],
                 fully_proven_coverage[projection]["reason"]),
                ("complete", None),
            )

        partial = copy.deepcopy(fully_proven)
        partial["readback"]["queries"]["historical"]["has_more"] = True
        partial_coverage = {
            row["projection"]: row for row in adapt(partial)
            if row["record_type"] == "coverage"
        }
        self.assertEqual(
            (partial_coverage["historical"]["coverage_state"],
             partial_coverage["historical"]["reason"]),
            ("gap", "read_failed"),
        )
        self.assertEqual(
            (partial_coverage["trailing"]["coverage_state"],
             partial_coverage["trailing"]["reason"]),
            ("complete", None),
        )

    def test_exact_replay_is_stable_and_conflicting_provider_ids_fail_closed(self):
        first = adapt()
        self.assertEqual(first, adapt(copy.deepcopy(payloads())))
        projected_once = contract.project(
            first, snapshot_at=OBSERVED_AT, trailing_start=TRAILING_START,
        )
        projected_replay = contract.project(
            [*first, *copy.deepcopy(first)],
            snapshot_at=OBSERVED_AT, trailing_start=TRAILING_START,
        )
        self.assertEqual(projected_once["historical"], projected_replay["historical"])
        self.assertEqual(projected_once["mrr"], projected_replay["mrr"])

        conflicting = payloads()
        changed = copy.deepcopy(conflicting["balance_transactions"]["data"][0])
        changed["amount"] = 9999
        conflicting["balance_transactions"]["data"].append(changed)
        with self.assertRaisesRegex(stripe.StripeAttributionError,
                                    "payload_conflict:balance_transactions:txn_charge_usd"):
            adapt(conflicting)

    def test_incomplete_official_list_fails_coverage_closed(self):
        incomplete = payloads()
        incomplete["balance_transactions"]["has_more"] = True
        rows = adapt(incomplete)
        financial = [row for row in rows if row["record_type"] == "coverage"
                     and row["projection"] != "as_of"]
        self.assertEqual({row["coverage_state"] for row in financial}, {"gap"})
        self.assertEqual({row["reason"] for row in financial}, {"read_failed"})
        self.assertFalse(any(row["record_type"] == "receipt" for row in rows))

    def test_provider_lists_require_expected_object_and_endpoint_url(self):
        expected_urls = {
            "balance_transactions": "/v1/balance_transactions",
            "charges": "/v1/charges",
            "refunds": "/v1/refunds",
            "subscriptions": "/v1/subscriptions",
        }
        swapped_urls = {
            "balance_transactions": "/v1/charges",
            "charges": "/v1/refunds",
            "refunds": "/v1/subscriptions",
            "subscriptions": "/v1/balance_transactions",
        }
        mutations = {
            "wrong_object": lambda value, name: value[name].update(object="collection"),
            "missing_url": lambda value, name: value[name].pop("url"),
            "wrong_url_type": lambda value, name: value[name].update(url={}),
            "wrong_url": lambda value, name: value[name].update(url="/v1/customers"),
            "swapped_url": lambda value, name: value[name].update(url=swapped_urls[name]),
        }
        for name, expected_url in expected_urls.items():
            self.assertEqual(payloads()[name]["url"], expected_url)
            for case, mutate in mutations.items():
                with self.subTest(name=name, case=case):
                    value = payloads()
                    mutate(value, name)
                    rows = adapt(value)
                    projection = "as_of" if name == "subscriptions" else "trailing"
                    coverage = next(row for row in rows
                                    if row.get("record_type") == "coverage"
                                    and row.get("projection") == projection)
                    self.assertEqual(
                        (coverage["coverage_state"], coverage["reason"]),
                        ("gap", "read_failed"),
                    )

    def test_subscription_item_list_requires_expected_object_and_endpoint_url(self):
        mutations = {
            "wrong_object": lambda items: items.update(object="collection"),
            "missing_url": lambda items: items.pop("url"),
            "wrong_url_type": lambda items: items.update(url={}),
            "wrong_url": lambda items: items.update(url="/v1/refunds"),
            "wrong_subscription": lambda items: items.update(
                url="/v1/subscription_items?subscription=sub_other"
            ),
        }
        for case, mutate in mutations.items():
            with self.subTest(case=case):
                value = payloads()
                mutate(value["subscriptions"]["data"][0]["items"])
                rows = adapt(value)
                self.assertFalse(any(
                    row.get("subscription_id") == "stripe:subscription:sub_monthly"
                    for row in rows
                ))
                as_of = next(row for row in rows
                             if row.get("record_type") == "coverage"
                             and row.get("projection") == "as_of")
                self.assertEqual(
                    (as_of["coverage_state"], as_of["reason"]),
                    ("gap", "unverified_receipt"),
                )

    def test_subscription_accounting_numbers_require_positive_exact_integers(self):
        cases = {
            "interval_count_bool": lambda item, price, recurring: recurring.update(
                interval_count=True
            ),
            "interval_count_float": lambda item, price, recurring: recurring.update(
                interval_count=1.0
            ),
            "quantity_bool": lambda item, price, recurring: item.update(quantity=True),
            "quantity_float": lambda item, price, recurring: item.update(quantity=2.0),
            "quantity_zero": lambda item, price, recurring: item.update(quantity=0),
            "quantity_negative": lambda item, price, recurring: item.update(quantity=-1),
            "unit_amount_bool": lambda item, price, recurring: price.update(unit_amount=True),
            "unit_amount_float": lambda item, price, recurring: price.update(unit_amount=1499.0),
            "unit_amount_string": lambda item, price, recurring: price.update(unit_amount="1499"),
            "unit_amount_zero": lambda item, price, recurring: price.update(unit_amount=0),
            "unit_amount_negative": lambda item, price, recurring: price.update(unit_amount=-1),
        }
        for case, mutate in cases.items():
            with self.subTest(case=case):
                value = payloads()
                item = value["subscriptions"]["data"][0]["items"]["data"][0]
                price = item["price"]
                mutate(item, price, price["recurring"])
                rows = adapt(value)
                self.assertFalse(any(
                    row.get("subscription_id") == "stripe:subscription:sub_monthly"
                    for row in rows
                ))
                as_of = next(row for row in rows
                             if row.get("record_type") == "coverage"
                             and row.get("projection") == "as_of")
                self.assertEqual(
                    (as_of["coverage_state"], as_of["reason"]),
                    ("gap", "unverified_receipt"),
                )

    def test_malformed_amount_becomes_coverage_gap_instead_of_escaping(self):
        for transaction_index in (0, 1, 5):
            with self.subTest(transaction_index=transaction_index):
                malformed = payloads()
                transaction_id = malformed["balance_transactions"]["data"][transaction_index]["id"]
                del malformed["balance_transactions"]["data"][transaction_index]["amount"]
                rows = adapt(malformed)
                self.assertFalse(any(row.get("receipt_id") ==
                                     f"stripe:balance_transaction:{transaction_id}" for row in rows))
                self.assertEqual(
                    {row["reason"] for row in rows
                     if row["record_type"] == "coverage" and row["projection"] != "as_of"},
                    {"unverified_receipt"},
                )
        wrong_type = payloads()
        wrong_type["balance_transactions"]["data"][0]["amount"] = "1999"
        rows = adapt(wrong_type)
        self.assertFalse(any(row.get("receipt_id") ==
                             "stripe:balance_transaction:txn_charge_usd" for row in rows))
        wrong_fee_type = payloads()
        wrong_fee_type["balance_transactions"]["data"][0]["fee"] = "88"
        rows = adapt(wrong_fee_type)
        self.assertFalse(any(row.get("receipt_id") ==
                             "stripe:balance_transaction:txn_charge_usd" for row in rows))

    def test_out_of_range_provider_timestamps_fail_coverage_closed(self):
        cases = {
            "created": lambda charge, transaction: charge.update(created=10**20),
            "available_on": lambda charge, transaction: transaction.update(available_on=10**20),
        }
        for field, mutate in cases.items():
            with self.subTest(field=field):
                value = payloads()
                charge = next(row for row in value["charges"]["data"]
                              if row["id"] == "ch_external_jpy")
                transaction = next(row for row in value["balance_transactions"]["data"]
                                   if row["id"] == "txn_charge_jpy")
                mutate(charge, transaction)
                try:
                    rows = adapt(value)
                except (OverflowError, OSError, ValueError) as error:
                    self.fail(f"datetime error escaped adapter: {type(error).__name__}")
                self.assertFalse(any(
                    row.get("receipt_id") == "stripe:balance_transaction:txn_charge_jpy"
                    for row in rows
                ))
                trailing = next(row for row in rows
                                if row.get("record_type") == "coverage"
                                and row.get("projection") == "trailing")
                self.assertEqual(
                    (trailing["coverage_state"], trailing["reason"]),
                    ("gap", "unverified_receipt"),
                )

    def test_reversed_settlement_timestamps_fail_coverage_closed(self):
        cases = {
            "movement": ("txn_payout", "balance_transaction"),
            "charge": ("txn_charge_jpy", "charge"),
            "refund": ("txn_refund_usd", "refund"),
        }
        for pathway, (transaction_id, occurred_source) in cases.items():
            with self.subTest(pathway=pathway):
                value = payloads()
                transaction = next(row for row in value["balance_transactions"]["data"]
                                   if row["id"] == transaction_id)
                if occurred_source == "balance_transaction":
                    occurred_at = transaction["created"]
                elif occurred_source == "charge":
                    charge = next(row for row in value["charges"]["data"]
                                  if row["balance_transaction"] == transaction_id)
                    occurred_at = charge["created"]
                else:
                    refund = next(row for row in value["refunds"]["data"]
                                  if row["balance_transaction"] == transaction_id)
                    occurred_at = refund["created"]
                transaction["available_on"] = occurred_at - 1

                try:
                    rows = adapt(value)
                except contract.ContractError as error:
                    self.fail(f"contract error escaped adapter: {error.code}")
                self.assertFalse(any(
                    row.get("receipt_id", "").startswith(
                        f"stripe:balance_transaction:{transaction_id}"
                    ) for row in rows
                ))
                trailing = next(row for row in rows
                                if row.get("record_type") == "coverage"
                                and row.get("projection") == "trailing")
                self.assertEqual(
                    (trailing["coverage_state"], trailing["reason"]),
                    ("gap", "unverified_receipt"),
                )
                self.assertIn(
                    f"stripe://balance_transactions/{transaction_id}",
                    trailing["evidence_refs"],
                )

    def test_minor_amounts_are_bounded_before_exact_integer_conversion(self):
        for raw_amount in (10**40 + 1, 10**1000000):
            with self.subTest(digits="40" if raw_amount < 10**100 else "1000001"):
                value = payloads()
                charge = next(row for row in value["charges"]["data"]
                              if row["id"] == "ch_external_jpy")
                transaction = next(row for row in value["balance_transactions"]["data"]
                                   if row["id"] == "txn_charge_jpy")
                charge.update(amount=raw_amount, amount_captured=raw_amount)
                transaction.update(amount=raw_amount, net=raw_amount - transaction["fee"])
                try:
                    rows = adapt(value)
                except (OverflowError, ValueError) as error:
                    self.fail(f"amount error escaped adapter: {type(error).__name__}")
                self.assertFalse(any(
                    row.get("receipt_id") == "stripe:balance_transaction:txn_charge_jpy"
                    for row in rows
                ))
                trailing = next(row for row in rows
                                if row.get("record_type") == "coverage"
                                and row.get("projection") == "trailing")
                self.assertEqual(
                    (trailing["coverage_state"], trailing["reason"]),
                    ("gap", "unverified_receipt"),
                )

        exact = payloads()
        maximum = 10**28 - 1
        charge = next(row for row in exact["charges"]["data"]
                      if row["id"] == "ch_external_jpy")
        transaction = next(row for row in exact["balance_transactions"]["data"]
                           if row["id"] == "txn_charge_jpy")
        charge.update(amount=maximum, amount_captured=maximum, currency="usd")
        transaction.update(
            amount=maximum, net=maximum - transaction["fee"], currency="usd",
        )
        receipt = next(row for row in adapt(exact)
                       if row.get("receipt_id") ==
                       "stripe:balance_transaction:txn_charge_jpy")
        self.assertIn(
            {
                "category": "settled_external_revenue",
                "amount": "99999999999999999999999999.99",
            },
            receipt["components"],
        )

    def test_subscription_item_ids_dedupe_exact_replays_and_reject_conflicts(self):
        exact_duplicate = payloads()
        items = exact_duplicate["subscriptions"]["data"][0]["items"]["data"]
        items.append(copy.deepcopy(items[0]))
        snapshot = next(row for row in adapt(exact_duplicate)
                        if row.get("subscription_id") ==
                        "stripe:subscription:sub_monthly")
        self.assertEqual(snapshot["normalized_monthly_amount"], "29.98")

        cases = {
            "conflicting_duplicate": lambda rows: rows.append({
                **copy.deepcopy(rows[0]), "quantity": 3,
            }),
            "missing_id": lambda rows: rows[0].pop("id"),
        }
        for case, mutate in cases.items():
            with self.subTest(case=case):
                value = payloads()
                rows = value["subscriptions"]["data"][0]["items"]["data"]
                mutate(rows)
                adapted = adapt(value)
                self.assertFalse(any(
                    row.get("subscription_id") == "stripe:subscription:sub_monthly"
                    for row in adapted
                ))
                as_of = next(row for row in adapted
                             if row.get("record_type") == "coverage"
                             and row.get("projection") == "as_of")
                self.assertEqual(
                    (as_of["coverage_state"], as_of["reason"]),
                    ("gap", "unverified_receipt"),
                )

    def test_classified_internal_charges_require_matching_balance_transaction(self):
        for category in ("self_payment", "owner_deposit"):
            with self.subTest(category=category):
                value = payloads()
                charge = next(row for row in value["charges"]["data"]
                              if row["id"] == "ch_self_payment")
                charge["metadata"]["lm_economic_category"] = category
                value["balance_transactions"]["data"] = [
                    row for row in value["balance_transactions"]["data"]
                    if row["id"] != "txn_self_payment"
                ]
                rows = adapt(value)
                trailing = next(row for row in rows
                                if row.get("record_type") == "coverage"
                                and row.get("projection") == "trailing")
                self.assertEqual(
                    (trailing["coverage_state"], trailing["reason"]),
                    ("gap", "unverified_receipt"),
                )
                self.assertIn(
                    "stripe://charges/ch_self_payment", trailing["evidence_refs"]
                )

    def test_unknown_charge_and_refund_statuses_fail_coverage_closed(self):
        cases = {
            "charge": lambda value: value["charges"]["data"].append({
                "id": "ch_future", "object": "charge", "amount": 100,
                "amount_captured": 0, "amount_refunded": 0,
                "balance_transaction": None, "captured": False,
                "created": 1790808000, "currency": "usd", "customer": "cus_future",
                "disputed": False, "livemode": True, "metadata": {}, "paid": False,
                "refunded": False, "status": "future_status",
            }),
            "refund": lambda value: value["refunds"]["data"].append({
                "id": "re_future", "object": "refund", "amount": 100,
                "balance_transaction": None, "charge": "ch_external_jpy",
                "created": 1790808000, "currency": "jpy", "metadata": {},
                "payment_intent": "pi_future", "reason": None,
                "status": "future_status",
            }),
        }
        for object_type, mutate in cases.items():
            with self.subTest(object_type=object_type):
                value = payloads()
                mutate(value)
                rows = adapt(value)
                trailing = next(row for row in rows
                                if row.get("record_type") == "coverage"
                                and row.get("projection") == "trailing")
                self.assertEqual(
                    (trailing["coverage_state"], trailing["reason"]),
                    ("gap", "unverified_receipt"),
                )
                self.assertIn(
                    f"stripe://{object_type}s/{'ch' if object_type == 'charge' else 're'}_future",
                    trailing["evidence_refs"],
                )

    def test_coverage_keeps_collection_manifests_when_object_refs_are_truncated(self):
        value = payloads()
        for index in range(40):
            value["balance_transactions"]["data"].append({
                "id": f"txn_unknown_{index:02d}", "object": "balance_transaction",
                "amount": 1, "available_on": 1790809200, "created": 1790807400,
                "currency": "usd", "description": "Unknown transaction",
                "exchange_rate": None, "fee": 0, "fee_details": [], "net": 1,
                "reporting_category": "other", "source": f"src_unknown_{index:02d}",
                "status": "available", "type": "future_type",
            })
        trailing = next(row for row in adapt(value)
                        if row.get("record_type") == "coverage"
                        and row.get("projection") == "trailing")
        self.assertEqual(
            (trailing["coverage_state"], trailing["reason"]),
            ("gap", "unverified_receipt"),
        )
        for manifest in (
            "stripe://balance_transactions", "stripe://charges", "stripe://refunds",
        ):
            self.assertIn(manifest, trailing["evidence_refs"])
        self.assertIn("stripe://evidence/truncated", trailing["evidence_refs"])
        self.assertLessEqual(len(trailing["evidence_refs"]), 32)
        self.assertTrue(any(
            ref.startswith("stripe://balance_transactions/txn_unknown_")
            for ref in trailing["evidence_refs"]
        ))

    def test_snapshot_identity_uses_canonical_instant_and_testmode_is_unverified(self):
        canonical = adapt()
        equivalent = adapt(observed_at="2026-10-01T09:00:00+09:00")
        canonical_snapshots = [row for row in canonical
                               if row["record_type"] == "subscription_snapshot"]
        equivalent_snapshots = [row for row in equivalent
                                if row["record_type"] == "subscription_snapshot"]
        self.assertEqual(canonical_snapshots, equivalent_snapshots)

        testmode = payloads()
        testmode["subscriptions"]["data"][0]["livemode"] = False
        snapshot = next(row for row in adapt(testmode)
                        if row.get("subscription_id") == "stripe:subscription:sub_monthly")
        self.assertEqual(snapshot["verification_state"], "unverified")

    def test_stripe_api_special_currency_exponent_is_exact(self):
        value = payloads()
        value["balance_transactions"]["data"].append({
            "id": "txn_charge_ugx", "object": "balance_transaction", "amount": 500,
            "available_on": 1790809200, "created": 1790807400, "currency": "ugx",
            "description": "UGX payment", "exchange_rate": None, "fee": 100,
            "fee_details": [], "net": 400, "reporting_category": "charge",
            "source": "ch_external_ugx", "status": "available", "type": "charge",
        })
        value["charges"]["data"].append({
            "id": "ch_external_ugx", "object": "charge", "amount": 500,
            "amount_captured": 500, "amount_refunded": 0,
            "balance_transaction": "txn_charge_ugx", "captured": True,
            "created": 1790807400, "currency": "ugx", "customer": "cus_ugx",
            "disputed": False, "livemode": True,
            "metadata": {"lm_economic_category": "settled_external_revenue"}, "paid": True,
            "refunded": False, "status": "succeeded",
        })
        receipt = next(row for row in adapt(value)
                       if row.get("receipt_id") == "stripe:balance_transaction:txn_charge_ugx")
        self.assertEqual(receipt["components"], [
            {"category": "payment_fee", "amount": "1"},
            {"category": "settled_external_revenue", "amount": "5"},
        ])


if __name__ == "__main__":
    unittest.main()
