import importlib
import unittest


PERFORMANCE = {
    "measurement_status": "measured",
    "observed_at": "2026-09-29T00:00:00Z",
    "gross_strategy_pnl_usd": "-0.14",
    "fees_usd": "0.01",
    "slippage_usd": "0.00",
    "completed_round_trips": 1,
    "observed_endpoint_drawdown_usd": "0.15",
    "capital_cap_usd": "100.00",
    "source_receipt_ids": ["order-1", "fill-1", "fee-1"],
}

OBSERVATION = {
    "account": {"equity": "66.63", "cash": "0.00"},
    "clock": {"observed_at": "2026-09-29T00:00:01Z"},
}

RISK = {"drawdown_fraction": "0.0015"}


class AlpacaSnapshotTests(unittest.TestCase):
    def _builder(self):
        try:
            module = importlib.import_module("alpaca_snapshot")
        except ModuleNotFoundError as error:
            self.fail(f"Alpaca snapshot adapter is missing: {error}")
        builder = getattr(module, "build_alpaca_snapshot", None)
        if builder is None:
            self.fail("build_alpaca_snapshot is missing")
        return builder

    def test_snapshot_preserves_missing_costs_as_partial_not_zero(self):
        snapshot = self._builder()(PERFORMANCE, OBSERVATION, RISK)

        self.assertEqual(snapshot["venue"], "alpaca")
        self.assertEqual(snapshot["observed_at"], PERFORMANCE["observed_at"])
        self.assertEqual(snapshot["equity_usd"], "66.63")
        self.assertEqual(snapshot["free_cash_usd"], "0.00")
        self.assertEqual(snapshot["gross_pnl_usd"], "-0.14")
        self.assertEqual(snapshot["trading_fees_usd"], "0.01")
        self.assertIsNone(snapshot["funding_or_borrow_usd"])
        self.assertIsNone(snapshot["gas_usd"])
        self.assertIsNone(snapshot["model_cost_usd"])
        self.assertEqual(snapshot["measurement_status"], "partial")
        self.assertEqual(snapshot["cost_evidence"], {})
        self.assertEqual(snapshot["source_receipt_ids"], PERFORMANCE["source_receipt_ids"])
        self.assertEqual(snapshot["risk"]["round_trips"], 1)
        self.assertEqual(snapshot["risk"]["drawdown_usd"], "0.15")

    def test_snapshot_becomes_measured_only_when_every_cost_is_explicit(self):
        performance = {
            **PERFORMANCE,
            "funding_or_borrow_usd": "0.00",
            "gas_usd": "0.00",
            "model_cost_usd": "0.00",
        }

        snapshot = self._builder()(performance, OBSERVATION, RISK)

        self.assertEqual(snapshot["measurement_status"], "measured")
        self.assertEqual(snapshot["funding_or_borrow_usd"], "0.00")
        self.assertEqual(snapshot["gas_usd"], "0.00")
        self.assertEqual(snapshot["model_cost_usd"], "0.00")


if __name__ == "__main__":
    unittest.main()
