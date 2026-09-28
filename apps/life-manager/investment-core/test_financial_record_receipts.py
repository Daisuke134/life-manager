import unittest

from financial_record_receipts import financial_records_to_treasury_receipts


def record(record_id, *, subject="subject-a", kind="business_revenue", currency="USD",
           amount_minor=100, status="verified", occurred_at="2026-09-12T00:00:00Z",
           provider="fixture"):
    return {
        "record_id": record_id,
        "subject_id": subject,
        "kind": kind,
        "currency": currency,
        "amount_minor": amount_minor,
        "occurred_at": occurred_at,
        "source": {"provider": provider, "external_ref": f"external:{record_id}"},
        "verification": {"status": status},
    }


class FinancialRecordReceiptTests(unittest.TestCase):
    def test_maps_subject_scoped_usd_revenue_and_fee_and_filters_period(self):
        rows = [
            record("revenue-1", amount_minor=1234, provider="stripe"),
            record("fee-1", kind="fee", amount_minor=50, provider="stripe"),
            record("old-1", amount_minor=999, occurred_at="2026-08-31T23:59:59Z"),
        ]

        result = financial_records_to_treasury_receipts(rows, "subject-a", "2026-09")

        self.assertEqual(result["evidence_status"], "measured")
        self.assertEqual(
            [(row["category"], row["amount_usd"], row["source_record_id"])
             for row in result["receipts"]],
            [
                ("operating_cost", "0.50", "fee-1"),
                ("customer_revenue", "12.34", "revenue-1"),
            ],
        )
        self.assertTrue(all(row["status"] == "verified" for row in result["receipts"]))
        self.assertEqual(result["source_record_ids"], ["fee-1", "revenue-1"])

    def test_non_usd_assets_are_excluded_without_fx(self):
        result = financial_records_to_treasury_receipts(
            [
                record("usdc-1", currency="USDC", amount_minor=3000),
                record("jpy-1", currency="JPY", amount_minor=500),
            ],
            "subject-a",
            "2026-09",
        )

        self.assertEqual(result["evidence_status"], "partial")
        self.assertEqual(result["receipts"], [])
        self.assertEqual(
            {(row["record_id"], row["currency"]) for row in result["excluded_currencies"]},
            {("usdc-1", "USDC"), ("jpy-1", "JPY")},
        )

    def test_unverified_and_unclassified_rows_are_visible_not_booked(self):
        result = financial_records_to_treasury_receipts(
            [
                record("unknown-1", status="unverified"),
                record("stale-1", kind="fee", status="stale"),
                record("cost-1", kind="business_cost", amount_minor=200),
                record("payout-1", kind="payout", amount_minor=300),
                record("tax-1", kind="tax", amount_minor=400),
            ],
            "subject-a",
            "2026-09",
        )

        self.assertEqual(result["evidence_status"], "partial")
        self.assertEqual(result["receipts"], [])
        self.assertIn({"record_id": "unknown-1", "reason": "verification_unverified"}, result["missing_sources"])
        self.assertIn({"record_id": "stale-1", "reason": "verification_stale"}, result["missing_sources"])
        self.assertEqual(
            {row["record_id"] for row in result["unclassified_records"]},
            {"cost-1", "payout-1", "tax-1"},
        )

    def test_non_business_balances_are_ignored_not_counted_as_missing_business_evidence(self):
        result = financial_records_to_treasury_receipts(
            [
                record("asset-1", kind="asset_balance", status="unverified", amount_minor=100000),
                record("liability-1", kind="liability_balance", amount_minor=20000),
            ],
            "subject-a",
            "2026-09",
        )

        self.assertEqual(result["evidence_status"], "partial")
        self.assertEqual(result["reason"], "no_usd_treasury_receipts")
        self.assertEqual(result["missing_sources"], [])
        self.assertEqual(result["unclassified_records"], [])
        self.assertEqual(result["ignored_non_business_records"], ["asset-1", "liability-1"])

    def test_subject_mismatch_blocks_and_never_leaks_other_subject(self):
        result = financial_records_to_treasury_receipts(
            [record("other-1", subject="subject-b", amount_minor=999999)],
            "subject-a",
            "2026-09",
        )

        self.assertEqual(result["evidence_status"], "blocked")
        self.assertEqual(result["reason"], "subject_mismatch")
        self.assertEqual(result["receipts"], [])

    def test_duplicate_or_malformed_rows_block(self):
        duplicate = financial_records_to_treasury_receipts(
            [record("same-1"), record("same-1", kind="fee")], "subject-a", "2026-09"
        )
        self.assertEqual(duplicate["evidence_status"], "blocked")
        self.assertEqual(duplicate["reason"], "duplicate_record_id")

        malformed = financial_records_to_treasury_receipts(
            [record("negative-1", amount_minor=-1)], "subject-a", "2026-09"
        )
        self.assertEqual(malformed["evidence_status"], "blocked")
        self.assertEqual(malformed["reason"], "amount_minor_invalid")

    def test_output_is_deterministic_when_input_order_changes(self):
        rows = [record("b", amount_minor=2), record("a", amount_minor=1)]
        first = financial_records_to_treasury_receipts(rows, "subject-a", "2026-09")
        second = financial_records_to_treasury_receipts(list(reversed(rows)), "subject-a", "2026-09")
        self.assertEqual(first, second)
        self.assertEqual([row["receipt_id"] for row in first["receipts"]], [
            "financial-record:a", "financial-record:b",
        ])


if __name__ == "__main__":
    unittest.main()
