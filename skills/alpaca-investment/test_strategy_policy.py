from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from strategy_policy import candidate_cards, evaluate, load_selected_card


NOW = "2026-01-01T04:00:00+00:00"


def _bar(index: int, close: int, timestamp: str | None = None) -> dict[str, str]:
    return {
        "t": timestamp or f"2026-01-01T{index // 12:02d}:{(index % 12) * 5:02d}:00+00:00",
        "o": str(close),
        "h": str(close + 1),
        "l": str(close - 1),
        "c": str(close),
    }


def _snapshot(history, *, bid="99", ask="100", quote_at=NOW, positions=0,
              position=None, clock=NOW):
    return {
        "account": {"cash": "66.00", "equity": "66.00"},
        "available_cash_usd": "66.00",
        "clock": {"timestamp": clock, "is_open": True},
        "crypto": [{"symbol": "BTC/USDC", "bid": bid, "ask": ask, "quote_at": quote_at}],
        "crypto_history": {"BTC/USDC": history},
        "positions": positions,
        "position": position,
        "open_orders": 0,
        "unresolved_intents": 0,
    }


def _reversion_entry_history():
    return [_bar(index, 110 if index < 24 else 90) for index in range(25)]


def _reversion_exit_history():
    return [_bar(index, 100 if index < 24 else 115) for index in range(25)]


def _trend_entry_history():
    return [_bar(index, 100 + index) for index in range(50)] + [_bar(50, 200)]


def _trend_exit_history():
    return [_bar(index, 100 + index) for index in range(50)] + [_bar(50, 100)]


class StrategyPolicyTests(unittest.TestCase):
    def test_reversion_candidate_enters_only_on_declared_signal(self):
        result = evaluate(_snapshot(_reversion_entry_history()), candidate_cards()["alpaca-btc-5m-reversion-v1"])

        self.assertEqual(result["action"], "ENTER")
        self.assertEqual(result["strategy_id"], "alpaca-btc-5m-reversion-v1")
        self.assertEqual(set(result), {"action", "strategy_id", "signal_inputs", "reason", "expected_cost_usd"})
        self.assertEqual(result["signal_inputs"]["rsi_14"], "0.00")

    def test_reversion_candidate_exits_on_declared_profit_or_risk_signal(self):
        position = {"symbol": "BTCUSD", "qty": "0.5", "entry_price": "100",
                    "entry_timestamp": "2026-01-01T03:55:00+00:00"}
        result = evaluate(
            _snapshot(_reversion_exit_history(), positions=1, position=position),
            candidate_cards()["alpaca-btc-5m-reversion-v1"],
        )

        self.assertEqual(result["action"], "EXIT")
        self.assertIn(result["reason"], {"rsi_exit", "bollinger_exit"})

    def test_trend_candidate_enters_on_ema_and_breakout(self):
        result = evaluate(_snapshot(_trend_entry_history()), candidate_cards()["alpaca-btc-5m-trend-v1"])

        self.assertEqual(result["action"], "ENTER")
        self.assertTrue(float(result["signal_inputs"]["ema_20"]) > float(result["signal_inputs"]["ema_50"]))

    def test_trend_candidate_exits_when_price_falls_below_ema(self):
        position = {"symbol": "BTCUSD", "qty": "0.5", "entry_price": "150",
                    "entry_timestamp": "2026-01-01T03:55:00+00:00"}
        result = evaluate(
            _snapshot(_trend_exit_history(), positions=1, position=position),
            candidate_cards()["alpaca-btc-5m-trend-v1"],
        )

        self.assertEqual(result["action"], "EXIT")
        self.assertEqual(result["reason"], "ema_exit")

    def test_stale_quote_fails_closed(self):
        stale = (datetime.fromisoformat(NOW) - timedelta(seconds=31)).isoformat()
        result = evaluate(
            _snapshot(_reversion_entry_history(), quote_at=stale),
            candidate_cards()["alpaca-btc-5m-reversion-v1"],
        )

        self.assertEqual(result["action"], "NO_TRADE")
        self.assertEqual(result["reason"], "quote_stale")

    def test_wide_spread_fails_closed(self):
        result = evaluate(
            _snapshot(_reversion_entry_history(), bid="80", ask="100"),
            candidate_cards()["alpaca-btc-5m-reversion-v1"],
        )

        self.assertEqual(result["action"], "NO_TRADE")
        self.assertEqual(result["reason"], "spread_too_wide")

    def test_missing_history_fails_closed(self):
        result = evaluate(
            _snapshot([]), candidate_cards()["alpaca-btc-5m-reversion-v1"]
        )

        self.assertEqual(result["action"], "NO_TRADE")
        self.assertEqual(result["reason"], "history_insufficient")

    def test_missing_candle_fails_closed(self):
        history = _reversion_entry_history()
        history[10] = _bar(11, 110)
        result = evaluate(
            _snapshot(history), candidate_cards()["alpaca-btc-5m-reversion-v1"]
        )

        self.assertEqual(result["action"], "NO_TRADE")
        self.assertEqual(result["reason"], "history_invalid")

    def test_cost_threshold_blocks_signal_when_cost_exceeds_declared_edge(self):
        card = deepcopy(candidate_cards()["alpaca-btc-5m-reversion-v1"].to_mapping())
        card["cost_model"] = {
            "entry_fee_bps": "10000", "exit_fee_bps": "10000",
            "entry_slippage_bps": "0", "exit_slippage_bps": "0",
        }
        from strategy_policy import StrategyCard
        expensive = StrategyCard.from_mapping(card)

        result = evaluate(_snapshot(_reversion_entry_history()), expensive)

        self.assertEqual(result["action"], "NO_TRADE")
        self.assertEqual(result["reason"], "fee_threshold")
        self.assertGreater(float(result["expected_cost_usd"]), 0)

    def test_existing_position_must_be_owned_btc(self):
        position = {"symbol": "ETHUSD", "qty": "0.5", "entry_price": "100",
                    "entry_timestamp": "2026-01-01T03:55:00+00:00"}
        result = evaluate(
            _snapshot(_reversion_exit_history(), positions=1, position=position),
            candidate_cards()["alpaca-btc-5m-reversion-v1"],
        )

        self.assertEqual(result["action"], "NO_TRADE")
        self.assertEqual(result["reason"], "position_not_owned")

    def test_false_signal_is_no_trade_not_model_decision(self):
        result = evaluate(
            _snapshot([_bar(index, 100) for index in range(25)]),
            candidate_cards()["alpaca-btc-5m-reversion-v1"],
        )

        self.assertEqual(result["action"], "NO_TRADE")
        self.assertEqual(result["reason"], "signal_false")

    def test_unlisted_instrument_is_rejected(self):
        card = deepcopy(candidate_cards()["alpaca-btc-5m-reversion-v1"].to_mapping())
        card["instruments"] = ["ETH/USDC"]
        from strategy_policy import StrategyCard
        unlisted = StrategyCard.from_mapping(card)

        result = evaluate(_snapshot(_reversion_entry_history()), unlisted)

        self.assertEqual(result["action"], "NO_TRADE")
        self.assertEqual(result["reason"], "instrument_not_allowed")

    def test_selected_release_is_required_and_stale_card_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            with self.assertRaisesRegex(ValueError, "^strategy_release_missing$"):
                load_selected_card(state)
            payload = candidate_cards()["alpaca-btc-5m-reversion-v1"].to_mapping()
            payload["entry_rules"]["all"][0] = "rsi_14 <= 31"
            (state / "selected-strategy.json").write_text(json.dumps({
                "release_sha": "a" * 40,
                "strategy_id": payload["strategy_id"],
                "card": payload,
            }))
            with self.assertRaisesRegex(ValueError, "^strategy_release_stale$"):
                load_selected_card(state)


if __name__ == "__main__":
    unittest.main()
