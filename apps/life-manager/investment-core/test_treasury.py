import unittest

from treasury import treasury_snapshot


def row(receipt_id, category, amount, **overrides):
    value = {
        "receipt_id": receipt_id,
        "category": category,
        "amount_usd": amount,
        "status": "verified",
    }
    value.update(overrides)
    return value


class TreasuryTests(unittest.TestCase):
    def test_separates_principal_revenue_and_investment_pnl(self):
        result = treasury_snapshot(
            "2026-09",
            [
                row("rev-1", "customer_revenue", "100"),
                row("refund-1", "customer_refund", "0"),
                row("pnl-1", "investment_net_pnl", "10"),
                row("flow-1", "owner_cash_flow", "1000"),
                row("op-1", "operating_cost", "0", included_in_investment_net=False),
                row("model-1", "model_cost", "5", included_in_investment_net=False),
            ],
            {"tax_rate": "0.20", "cash_reserve_usd": "50"},
        )

        self.assertEqual(result["evidence_status"], "measured")
        self.assertEqual(result["customer_revenue_usd"], "100.00")
        self.assertEqual(result["investment_net_pnl_usd"], "10.00")
        self.assertEqual(result["owner_cash_flow_usd"], "1000.00")
        self.assertEqual(result["model_cost_usd"], "5.00")
        self.assertEqual(result["tax_reserve_usd"], "21.00")
        self.assertEqual(result["investable_surplus_usd"], "34.00")
        self.assertEqual(result["investment_net_pnl_target_usd"], "10000.00")
        self.assertEqual(result["investment_net_pnl_target_gap_usd"], "9990.00")
        self.assertIsNone(result["treasury_surplus_target_usd"])

    def test_missing_cost_evidence_is_partial_and_not_zero(self):
        result = treasury_snapshot(
            "2026-09",
            [row("rev-1", "customer_revenue", "100"), row("pnl-1", "investment_net_pnl", "10")],
            {"tax_rate": "0.20", "cash_reserve_usd": "0"},
        )

        self.assertEqual(result["evidence_status"], "partial")
        self.assertIsNone(result["model_cost_usd"])
        self.assertIsNone(result["investable_surplus_usd"])

    def test_duplicate_receipt_ids_block_the_snapshot(self):
        result = treasury_snapshot(
            "2026-09",
            [row("same", "customer_revenue", "100"), row("same", "model_cost", "5", included_in_investment_net=False)],
            {"tax_rate": "0.20", "cash_reserve_usd": "0"},
        )

        self.assertEqual(result["evidence_status"], "blocked")
        self.assertEqual(result["reason"], "duplicate_receipt_id")
        self.assertIsNone(result["investable_surplus_usd"])

    def test_reserve_and_tax_calculation_is_decimal_safe(self):
        result = treasury_snapshot(
            "2026-09",
            [
                row("rev-1", "customer_revenue", "1000"),
                row("refund-1", "customer_refund", "0"),
                row("pnl-1", "investment_net_pnl", "100"),
                row("flow-1", "owner_cash_flow", "0"),
                row("op-1", "operating_cost", "0", included_in_investment_net=False),
                row("model-1", "model_cost", "50", included_in_investment_net=False),
            ],
            {"tax_rate": "0.25", "cash_reserve_usd": "200", "treasury_surplus_target_usd": "1000"},
        )

        self.assertEqual(result["tax_reserve_usd"], "262.50")
        self.assertEqual(result["investable_surplus_usd"], "587.50")
        self.assertEqual(result["investment_net_pnl_target_usd"], "10000.00")
        self.assertEqual(result["investment_net_pnl_target_gap_usd"], "9900.00")
        self.assertEqual(result["treasury_surplus_target_usd"], "1000.00")
        self.assertEqual(result["treasury_surplus_target_gap_usd"], "412.50")

    def test_negative_investable_surplus_is_visible(self):
        result = treasury_snapshot(
            "2026-09",
            [
                row("rev-1", "customer_revenue", "10"),
                row("refund-1", "customer_refund", "0"),
                row("pnl-1", "investment_net_pnl", "-20"),
                row("flow-1", "owner_cash_flow", "0"),
                row("op-1", "operating_cost", "0", included_in_investment_net=False),
                row("model-1", "model_cost", "5", included_in_investment_net=False),
            ],
            {"tax_rate": "0.25", "cash_reserve_usd": "0"},
        )

        self.assertEqual(result["evidence_status"], "measured")
        self.assertEqual(result["investable_surplus_usd"], "-16.25")

    def test_refunds_and_operating_costs_reduce_surplus_without_touching_owner_flow(self):
        result = treasury_snapshot(
            "2026-09",
            [
                row("rev-1", "customer_revenue", "100"),
                row("refund-1", "customer_refund", "10"),
                row("pnl-1", "investment_net_pnl", "10"),
                row("flow-1", "owner_cash_flow", "1000"),
                row("op-1", "operating_cost", "20", included_in_investment_net=False),
                row("model-1", "model_cost", "5", included_in_investment_net=False),
            ],
            {"tax_rate": "0.20", "cash_reserve_usd": "0"},
        )

        self.assertEqual(result["evidence_status"], "measured")
        self.assertEqual(result["customer_revenue_usd"], "100.00")
        self.assertEqual(result["customer_refund_usd"], "10.00")
        self.assertEqual(result["net_customer_revenue_usd"], "90.00")
        self.assertEqual(result["operating_cost_usd"], "20.00")
        self.assertEqual(result["operating_cost_deducted_usd"], "20.00")
        self.assertEqual(result["model_cost_deducted_usd"], "5.00")
        self.assertEqual(result["taxable_base_usd"], "75.00")
        self.assertEqual(result["tax_reserve_usd"], "15.00")
        self.assertEqual(result["investable_surplus_usd"], "60.00")
        self.assertEqual(result["owner_cash_flow_usd"], "1000.00")


if __name__ == "__main__":
    unittest.main()
