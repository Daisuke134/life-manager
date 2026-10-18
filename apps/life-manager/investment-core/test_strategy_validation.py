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
    def test_sensitivity_changes_numeric_literals_not_indicator_names(self):
        from strategy_validation import _find_parameter, _replace_path
        expressions = {"all": ["ema_20 > ema_50", "close > prior_20_high"]}
        self.assertIsNone(_find_parameter(expressions))
        for text, literal in (("rsi_14 <= 30", "30"),
                              ("close <= entry_price - 2 * atr_14", "2"),
                              ("tema_9 < bollinger_middle_20_2", None),
                              ("close <= 1e-3", "1e-3")):
            with self.subTest(expression=text):
                found=_find_parameter({"all":[text]})
                if literal is None:
                    self.assertIsNone(found)
                else:
                    self.assertIsNotNone(found)
                    path,_step=found
                    self.assertEqual(text[path[-2]:path[-1]],literal)
                    changed=_replace_path({"all":[text]},path,"7")
                    self.assertNotIn("rsi_17",changed["all"][0])
                    self.assertNotIn("atr_17",changed["all"][0])

    def test_reference_dummy_does_not_fill_missing_comparison_from_actual(self):
        mapping=_card().to_mapping()
        mapping["kill_conditions"].append("indicator_history_unstable")
        candles=_candles([90,110]*5)
        for row in candles:
            row.update(indicator_history_stable="1",reference_dummy="1")
        result=validate_series(StrategyCard.from_mapping(mapping),candles,_split(),_costs())
        self.assertEqual(result["status"],"unknown")
        self.assertEqual(result["decision"],"rejected")
        self.assertIsNone(result["net_pnl_usd"])

    def test_required_indicator_history_comparison_is_not_optional(self):
        mapping=_card().to_mapping()
        mapping["kill_conditions"].append("indicator_history_unstable")
        result=validate_series(StrategyCard.from_mapping(mapping),_candles([90,110]*5),_split(),_costs())
        self.assertEqual(result["status"],"unknown")
        self.assertEqual(result["reason"],"indicator_history_unknown")
        self.assertIsNone(result["net_pnl_usd"])

    def test_indicator_reference_predicate_disagreement_is_unknown(self):
        candles=_candles([90,110]*5)
        for row in candles:
            row["indicator_history_stable"]="1"
            row["reference_close"]="1000"
        result=validate_series(_card(),candles,_split(),_costs())
        self.assertEqual(result["status"],"unknown")
        self.assertEqual(result["decision"],"rejected")
        self.assertIsNone(result["net_pnl_usd"])

    def test_non_usd_quotes_use_entry_and_exit_fx_without_changing_signals(self):
        mapping = _card().to_mapping()
        mapping["instruments"] = ["TEST/USDC"]
        candles = _candles([90, 100, 110, 90, 100, 110, 90, 110, 90, 110])
        for row in candles:
            row["quote_to_usd"] = {
                "currency": "USDC", "rate": "0.8" if row["close"] == "110" else "0.9",
                "timestamp": row["timestamp"], "evidence_ref": "official-fx-bar-fixture",
            }
        result = validate_series(StrategyCard.from_mapping(mapping), candles, _split(), _costs())
        trade = result["trades"][0]
        self.assertEqual(trade["entry_price"], "90")
        self.assertEqual(trade["exit_price"], "110")
        self.assertEqual(trade["gross_pnl_usd"], "8.64")
        self.assertEqual(trade["fees_usd"], "0.21")
        self.assertEqual(trade["slippage_usd"], "0.10")
        self.assertEqual(trade["net_pnl_usd"], "8.33")
        self.assertEqual(trade["entry_quote_to_usd"]["rate"], "0.9")
        self.assertEqual(trade["exit_quote_to_usd"]["rate"], "0.8")

    def test_missing_or_invalid_quote_conversion_cannot_report_usd_profit(self):
        mapping = _card().to_mapping()
        mapping["instruments"] = ["TEST/USDC"]
        base = {"currency": "USDC", "rate": "0.9",
                "timestamp": "2026-01-01T00:00:00+00:00", "evidence_ref": "official-fx"}
        for invalid in (None, {}, {**base, "currency": "EUR"},
                        {**base, "rate": "NaN"}, {**base, "rate": "Infinity"},
                        {**base, "rate": "0"}, {**base, "rate": "-1"},
                        {**base, "rate": True}, {**base, "evidence_ref": " "},
                        {**base, "timestamp": "2026-01-01T00:01:00+00:00"}):
            with self.subTest(conversion=invalid):
                candles = _candles([90, 110] * 5)
                for row in candles:
                    row["quote_to_usd"] = {**base, "timestamp": row["timestamp"]}
                candles[0]["quote_to_usd"] = invalid
                result = validate_series(StrategyCard.from_mapping(mapping), candles, _split(), _costs())
                self.assertEqual(result["status"], "unknown")
                self.assertEqual(result["decision"], "rejected")
                self.assertIsNone(result["net_pnl_usd"])
                self.assertIsNone(result["holdout"]["net_pnl_usd"])
                self.assertEqual(result["trades"], [])

    def test_ambiguous_instrument_currency_is_not_assumed_usd(self):
        for instruments in (["TEST"], ["TEST/USD", "OTHER/USDC"], ["/USD"], [None], [1], [{}], [[]]):
            with self.subTest(instruments=instruments):
                mapping = _card().to_mapping()
                mapping["instruments"] = instruments
                result = validate_series(StrategyCard.from_mapping(mapping), _candles([90, 110] * 5),
                                         _split(), _costs())
                self.assertEqual(result["status"], "unknown")
                self.assertIsNone(result["net_pnl_usd"])

    def test_quote_conversion_metadata_is_detached_and_json_serializable(self):
        from datetime import datetime
        from decimal import Decimal
        mapping = _card().to_mapping()
        mapping["instruments"] = ["TEST/USDC"]
        candles = _candles([90, 110] * 5)
        for row in candles:
            row["quote_to_usd"] = {"currency": "USDC", "rate": Decimal("1"),
                "timestamp": datetime.fromisoformat(row["timestamp"]), "evidence_ref": "fx"}
        result = validate_series(StrategyCard.from_mapping(mapping), candles, _split(), _costs())
        json.dumps(result)
        self.assertIsInstance(result["trades"][0]["entry_quote_to_usd"]["rate"], str)
        self.assertIsInstance(candles[0]["quote_to_usd"]["rate"], Decimal)

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

    def test_exit_rule_evaluates_entry_price_and_indicator_arithmetic(self):
        card = _card(exit={"any": ["close <= entry_price - 1.5 * atr_14"]})
        candles = _candles([100, 98, 100, 98, 100, 98, 100, 98, 100, 98])
        for candle in candles:
            candle["atr_14"] = "1"

        result = validate_series(card, candles, _split(), _costs())

        self.assertEqual(result["status"], "measured")
        self.assertEqual(len(result["trades"]), 5)
        self.assertEqual(result["trades"][0]["entry_price"], "100")
        self.assertEqual(result["trades"][0]["exit_price"], "98")


if __name__ == "__main__":
    unittest.main()
