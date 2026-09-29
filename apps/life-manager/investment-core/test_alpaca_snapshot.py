import importlib
import json
import tempfile
import unittest
from pathlib import Path


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

    def test_snapshot_uses_cumulative_round_trip_count_when_daily_pnl_is_delta(self):
        performance = {
            **PERFORMANCE,
            "completed_round_trips": 0,
            "completed_round_trips_total": 4,
        }

        snapshot = self._builder()(performance, OBSERVATION, RISK)

        self.assertEqual(snapshot["risk"]["round_trips"], 4)

    def test_daily_reader_does_not_fallback_to_new_day_latest(self):
        module = importlib.import_module("alpaca_snapshot")
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "performance-latest.json").write_text(json.dumps({
                "measurement_status": "measured",
                "observed_at": "2026-09-29T00:00:00Z",
                "gross_strategy_pnl_usd": "0",
                "source_receipt_ids": ["new-day-zero"],
            }), encoding="utf-8")

            result = module.read_alpaca_snapshot(
                state,
                performance_day="2026-09-28",
            )

        self.assertEqual(result, {
            "status": "unknown",
            "reason": "alpaca_daily_performance_missing",
        })

    def test_daily_reader_rejects_payload_day_timestamp_mismatch(self):
        module = importlib.import_module("alpaca_snapshot")
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "performance-daily-2026-09-28.json").write_text(json.dumps({
                **PERFORMANCE,
                "performance_day": "2026-09-28",
                "observed_at": "2026-09-29T00:00:00Z",
            }), encoding="utf-8")

            result = module.read_alpaca_snapshot(
                state,
                performance_day="2026-09-28",
            )

        self.assertEqual(result, {
            "status": "unknown",
            "reason": "alpaca_daily_performance_timestamp_mismatch",
        })

    def test_daily_reader_accepts_legacy_latest_only_when_its_day_matches(self):
        module = importlib.import_module("alpaca_snapshot")
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "performance-latest.json").write_text(json.dumps({
                **PERFORMANCE,
                "observed_at": "2026-09-28T23:59:00Z",
            }), encoding="utf-8")
            observation = {
                **OBSERVATION,
                "clock": {"observed_at": "2026-09-29T00:00:01Z"},
            }
            (state / "observation-latest.json").write_text(
                json.dumps(observation), encoding="utf-8"
            )
            (state / "risk-latest.json").write_text(json.dumps(RISK), encoding="utf-8")

            result = module.read_alpaca_snapshot(
                state,
                performance_day="2026-09-28",
            )

        self.assertEqual(result["gross_pnl_usd"], PERFORMANCE["gross_strategy_pnl_usd"])
        self.assertIn(
            "alpaca-account-readback:2026-09-29T00:00:01Z",
            result["source_receipt_ids"],
        )


if __name__ == "__main__":
    unittest.main()
