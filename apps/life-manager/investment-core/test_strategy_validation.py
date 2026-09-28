from __future__ import annotations

import json
import unittest

from strategy_cards import StrategyCard
from strategy_validation import validate_series


def _card(entry=None, exit=None, risk=None):
    return StrategyCard.from_mapping({
        "strategy_id": "fixture-close-v1",
        "venue": "fixture",
        "instruments": ["TEST/USD"],
        "timeframe": "1m",
        "entry_rules": entry or {"all": [{"field": "close", "op": "lte", "value": "100"}]},
        "exit_rules": exit or {"any": [{"field": "close", "op": "gte", "value": "110"}]},
        "sizing_rule": {"notional_usd": "100"},
        "cost_model": {"fee_bps": "10", "slippage_bps": "5"},
        "risk_limits": risk or {"max_drawdown_usd": "1000"},
        "kill_conditions": ["stale_quote", "effect_unknown"],
        "evidence_refs": ["https://example.test/fixture-strategy"],
        "status": "research",
    })


def _candles(closes):
    return [
        {
            "timestamp": f"2026-01-01T00:{index:02d}:00+00:00",
            "open": str(close),
            "high": str(close),
            "low": str(close),
            "close": str(close),
        }
        for index, close in enumerate(closes)
    ]


def _split():
    return {"train": "60%", "validation": "20%", "holdout": "20%"}


def _costs():
    return {"fee_bps": "10", "slippage_bps": "5"}


class StrategyValidationTests(unittest.TestCase):
    def test_train_validation_holdout_are_separate(self):
        result = validate_series(
            _card(),
            _candles([90, 100, 110, 90, 100, 110, 90, 110, 90, 110]),
            _split(),
            _costs(),
        )

        self.assertEqual(result["train"]["trades"], 2)
        self.assertEqual(result["validation"]["trades"], 1)
        self.assertEqual(result["holdout"]["trades"], 1)
        self.assertEqual(
            {trade["period"] for trade in result["trades"]},
            {"train", "validation", "holdout"},
        )

    def test_future_looking_signal_is_rejected(self):
        card = _card(entry={"all": [{"field": "future_close", "op": "gte", "value": "100"}]})

        result = validate_series(card, _candles([110, 90] * 5), _split(), _costs())

        self.assertTrue(result["lookahead_detected"])
        self.assertEqual(result["decision"], "rejected")
        self.assertEqual(result["reason"], "lookahead_detected")

    def test_fees_and_slippage_are_subtracted_from_gross_pnl(self):
        result = validate_series(
            _card(),
            _candles([90, 100, 110, 90, 100, 110, 90, 110, 90, 110]),
            _split(),
            {"fee_bps": "100", "slippage_bps": "50"},
        )

        self.assertGreater(float(result["fees_usd"]), 0)
        self.assertGreater(float(result["slippage_usd"]), 0)
        gross = sum(float(trade["gross_pnl_usd"]) for trade in result["trades"])
        self.assertLess(float(result["net_pnl_usd"]), gross)

    def test_no_trade_is_explicit_and_not_zero_profit(self):
        card = _card(entry={"all": [{"field": "close", "op": "gt", "value": "1000"}]})

        result = validate_series(card, _candles([90] * 10), _split(), _costs())

        self.assertEqual(result["status"], "no_trade")
        self.assertEqual(result["decision"], "rejected")
        self.assertEqual(result["reason"], "no_trades")
        self.assertEqual(result["net_pnl_usd"], "0.00")

    def test_duplicate_candle_timestamps_are_rejected(self):
        candles = _candles([110, 90] * 5)
        candles[1]["timestamp"] = candles[0]["timestamp"]

        result = validate_series(_card(), candles, _split(), _costs())

        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "duplicate_candle_timestamp")

    def test_missing_costs_remain_unknown(self):
        result = validate_series(_card(), _candles([110, 90] * 5), _split(), {})

        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["decision"], "rejected")
        self.assertEqual(result["reason"], "cost_model_incomplete")

    def test_repeated_runs_are_deterministic(self):
        args = (
            _card(),
            _candles([90, 100, 110, 90, 100, 110, 90, 110, 90, 110]),
            _split(),
            _costs(),
        )

        first = validate_series(*args)
        second = validate_series(*args)

        self.assertEqual(
            json.dumps(first, sort_keys=True, separators=(",", ":")),
            json.dumps(second, sort_keys=True, separators=(",", ":")),
        )

    def test_positive_holdout_and_robust_neighbors_can_become_paper(self):
        result = validate_series(
            _card(),
            _candles([90, 100, 110, 90, 100, 110, 90, 110, 90, 110]),
            _split(),
            _costs(),
        )

        self.assertEqual(result["status"], "measured")
        self.assertEqual(result["decision"], "paper")
        self.assertGreaterEqual(result["parameter_sensitivity"]["positive_count"], 5)


if __name__ == "__main__":
    unittest.main()
