import unittest

from x402_inflow_receipts import x402_inflows_to_cash_receipts


def row(sale_id="sale-1", tx_digit="a", observed_at="2026-09-10T00:00:00Z", amount="0.01", **overrides):
    value = {
        "source": "x402-railway",
        "source_sale_id": sale_id,
        "offer_id": "/funding-rates",
        "tx": f"0x{tx_digit * 64}",
        "block": 100,
        "from": "0x2222222222222222222222222222222222222222",
        "to": "0x6592eb8ef820abc092e8c3474fb2042dffccedc7",
        "payTo": "0x6592eb8ef820abc092e8c3474fb2042dffccedc7",
        "usdc": amount,
        "finalized": True,
        "status": "success",
        "external": True,
        "observed_at": observed_at,
    }
    value.update(overrides)
    return value


class X402InflowReceiptTests(unittest.TestCase):
    def test_maps_only_verified_external_usdc_and_keeps_usd_unset(self):
        result = x402_inflows_to_cash_receipts(
            [
                row("sale-1", "a", amount="0.01"),
                row("sale-2", "b", amount="0.01"),
                row("sale-old", "c", observed_at="2026-08-31T23:59:59Z"),
            ],
            "2026-09",
        )

        self.assertEqual(result["evidence_status"], "measured")
        self.assertEqual(result["revenue_usdc"], "0.020000")
        self.assertEqual(result["outside_period_count"], 1)
        self.assertEqual(len(result["cash_receipts"]), 2)
        self.assertEqual(result["cash_receipts"][0]["currency"], "USDC")
        self.assertEqual(result["cash_receipts"][0]["amount_usdc"], "0.010000")
        self.assertNotIn("amount_usd", result["cash_receipts"][0])

    def test_missing_period_receipts_is_partial_not_zero_revenue(self):
        result = x402_inflows_to_cash_receipts([row(observed_at="2026-08-31T00:00:00Z")], "2026-09")

        self.assertEqual(result["evidence_status"], "partial")
        self.assertEqual(result["reason"], "no_usdc_receipts")
        self.assertIsNone(result["revenue_usdc"])
        self.assertEqual(result["cash_receipts"], [])

    def test_unfinalized_self_or_malformed_rows_block(self):
        for overrides, reason in (
            ({"finalized": False}, "inflow_not_finalized"),
            ({"external": False}, "inflow_not_external"),
            ({"usdc": "not-a-number"}, "amount_invalid"),
            ({"to": "0x3333333333333333333333333333333333333333"}, "pay_to_mismatch"),
        ):
            result = x402_inflows_to_cash_receipts([row(**overrides)], "2026-09")
            self.assertEqual(result["evidence_status"], "blocked")
            self.assertEqual(result["reason"], reason)
            self.assertIsNone(result["revenue_usdc"])

    def test_duplicate_tx_or_sale_id_blocks_before_summing(self):
        result = x402_inflows_to_cash_receipts(
            [row("sale-1", "a"), row("sale-2", "a")],
            "2026-09",
        )
        self.assertEqual(result["evidence_status"], "blocked")
        self.assertEqual(result["reason"], "duplicate_transaction")
        self.assertIsNone(result["revenue_usdc"])

        result = x402_inflows_to_cash_receipts(
            [row("sale-1", "a"), row("sale-1", "b")],
            "2026-09",
        )
        self.assertEqual(result["evidence_status"], "blocked")
        self.assertEqual(result["reason"], "duplicate_source_sale")
        self.assertIsNone(result["revenue_usdc"])

    def test_invalid_period_or_input_blocks(self):
        self.assertEqual(
            x402_inflows_to_cash_receipts([], "2026-9")["reason"],
            "period_invalid",
        )
        self.assertEqual(
            x402_inflows_to_cash_receipts(None, "2026-09")["reason"],
            "rows_invalid",
        )


if __name__ == "__main__":
    unittest.main()
