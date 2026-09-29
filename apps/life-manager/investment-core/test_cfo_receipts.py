import unittest

from cfo_receipts import cfo_table_to_treasury_receipts


def cell(status="zero", amounts=None, receipts=None, sources=None, incomplete=0, reason=None):
    value = {
        "status": status,
        "amounts": amounts or {},
        "receipts": receipts or [],
        "sources": sources or ["fixture"],
        "incomplete": incomplete,
    }
    if reason is not None:
        value["reason"] = reason
    return value


def table(rows, sources=None, reporting_date="2026-09-28"):
    return {
        "reporting_date": reporting_date,
        "timezone": "Asia/Tokyo",
        "sources": sources or [{"name": "fixture", "ok": True, "error": None, "entries": 1, "notes": {}}],
        "rows": rows,
    }


class CfoReceiptAdapterTests(unittest.TestCase):
    def test_maps_non_investment_usd_cells_and_excludes_investment(self):
        result = cfo_table_to_treasury_receipts(table([
            {
                "loop_id": "self-build",
                "revenue": cell("verified", {"USD": "100"}, ["stripe:charge-1"]),
                "refund": cell("verified", {"USD": "5"}, ["stripe:refund-1"]),
                "cost": cell("verified", {"USD": "10"}, ["stripe:charge-1"]),
                "net": {"status": "verified", "amounts": {"USD": "85"}},
            },
            {
                "loop_id": "investment",
                "revenue": cell("verified", {"USD": "12"}, ["alpaca:fill-1"]),
                "refund": cell(),
                "cost": cell("verified", {"USD": "1"}, ["alpaca:fee-1"]),
                "net": {"status": "verified", "amounts": {"USD": "11"}},
            },
        ]))

        self.assertEqual(
            [(row["category"], row["amount_usd"], row["source_loop_id"], row["source_kind"])
             for row in result["receipts"]],
            [
                ("customer_revenue", "100", "self-build", "revenue"),
                ("customer_refund", "5", "self-build", "refund"),
                ("operating_cost", "10", "self-build", "cost"),
            ],
        )
        self.assertEqual(result["excluded_investment_rows"], ["investment:cost", "investment:revenue"])
        self.assertEqual(result["evidence_status"], "measured")
        self.assertEqual(result["source_receipt_ids"], ["stripe:charge-1", "stripe:refund-1"])

    def test_excludes_non_usd_and_api_price_estimates_without_fx_or_bill_claim(self):
        result = cfo_table_to_treasury_receipts(table([
            {
                "loop_id": "gig-lancers",
                "revenue": cell("verified", {"JPY": "45000"}, ["lancers:pay-1"]),
                "refund": cell(),
                "cost": cell("verified", {"USD_API_EQUIV": "7.5"}, ["agent-usage:cost-1"]),
                "net": {"status": "verified", "amounts": {"JPY": "45000", "USD_API_EQUIV": "-7.5"}},
            },
        ]))

        self.assertEqual(result["receipts"], [])
        self.assertEqual(
            {(row["source_kind"], row["currency"]) for row in result["excluded_currencies"]},
            {("revenue", "JPY"), ("cost", "USD_API_EQUIV")},
        )
        self.assertEqual(result["evidence_status"], "partial")
        self.assertNotIn("USD_API_EQUIV", {row.get("currency") for row in result["receipts"]})

    def test_unverified_and_incomplete_cells_are_missing_not_zero(self):
        result = cfo_table_to_treasury_receipts(table([
            {
                "loop_id": "self-build",
                "revenue": cell("unverified", reason="stripe:credential_missing"),
                "refund": cell(),
                "cost": cell(),
                "net": {"status": "unverified", "amounts": {}},
            },
            {
                "loop_id": "agent-economy",
                "revenue": cell(),
                "refund": cell(),
                "cost": cell("verified", {"USD": "2"}, ["stripe:cost-1"], incomplete=1),
                "net": {"status": "verified", "amounts": {"USD": "-2"}},
            },
        ]))

        self.assertEqual(result["receipts"], [])
        self.assertEqual(result["evidence_status"], "partial")
        self.assertIn(
            {"loop_id": "self-build", "kind": "revenue", "reason": "stripe:credential_missing"},
            result["missing_sources"],
        )
        self.assertIn(
            {"loop_id": "agent-economy", "kind": "cost", "reason": "incomplete_cost_evidence:1"},
            result["missing_sources"],
        )

    def test_receipt_ids_are_deterministic_and_duplicate_cell_sources_block(self):
        rows = [{
            "loop_id": "self-build",
            "revenue": cell("verified", {"USD": "1"}, ["stripe:b", "stripe:a"]),
            "refund": cell(),
            "cost": cell(),
            "net": {"status": "verified", "amounts": {"USD": "1"}},
        }]
        first = cfo_table_to_treasury_receipts(table(rows))
        second = cfo_table_to_treasury_receipts(table(rows))
        self.assertEqual(first["receipts"], second["receipts"])
        self.assertEqual(first["receipts"][0]["source_receipt_ids"], ["stripe:b", "stripe:a"])

        duplicate = cfo_table_to_treasury_receipts(table([{
            "loop_id": "self-build",
            "revenue": cell("verified", {"USD": "1"}, ["stripe:a", "stripe:a"]),
            "refund": cell(),
            "cost": cell(),
            "net": {"status": "verified", "amounts": {"USD": "1"}},
        }]))
        self.assertEqual(duplicate["evidence_status"], "blocked")
        self.assertEqual(duplicate["reason"], "duplicate_source_receipt_id")
        self.assertEqual(duplicate["receipts"], [])

    def test_malformed_table_blocks_without_partial_receipts(self):
        result = cfo_table_to_treasury_receipts(
            {"reporting_date": "2026-09-28", "sources": [], "rows": "bad"}, "2026-09"
        )
        self.assertEqual(result["evidence_status"], "blocked")
        self.assertEqual(result["reason"], "rows_invalid")
        self.assertEqual(result["receipts"], [])


if __name__ == "__main__":
    unittest.main()
