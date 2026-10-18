from __future__ import annotations

import copy
import unittest
from datetime import datetime, timedelta, timezone

from strategy_policy import build_validation_candles, candidate_cards, evaluate


def _bars(count: int = 60) -> list[dict[str, str]]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(count):
        close = 100 + index
        rows.append({
            "t": (start + timedelta(minutes=5 * index)).isoformat().replace("+00:00", "Z"),
            "o": str(close),
            "h": str(close + 1),
            "l": str(close - 1),
            "c": str(close),
        })
    return rows


class ValidationFeatureTests(unittest.TestCase):
    def test_v2_uses_identical_finite_input_for_runtime_and_validation(self):
        from decimal import Decimal
        from strategy_validation import _condition
        source = _bars(800)
        for index, row in enumerate(source):
            close = Decimal(1000 if index < 705 else 100+index-705)
            row.update(o=str(close), h=str(close+Decimal(".01")), l=str(close-Decimal(".01")), c=str(close))
        strategy = "alpaca-btc-5m-trend-400-v2"
        card = candidate_cards()[strategy]
        candle = build_validation_candles(source, strategy)[-1]
        clock = (datetime.fromisoformat(source[-1]["t"].replace("Z", "+00:00"))+timedelta(minutes=5)).isoformat()
        snapshot = {"clock": {"timestamp": clock}, "crypto_history": {"BTC/USDC": source},
                    "crypto": [{"symbol": "BTC/USDC", "bid": "193.99", "ask": "194", "quote_at": clock}],
                    "positions": 0, "position": None, "open_orders": 0, "unresolved_intents": 0}
        decision = evaluate(snapshot, card)
        self.assertEqual(decision["action"] == "ENTER", _condition(card.entry_rules, candle))
        self.assertEqual(decision["action"], "NO_TRADE")
        self.assertEqual(decision["reason"], "signal_false")
        self.assertEqual(candle["indicator_history_stable"], "1")
        # Prefixes older than the declared comparison window cannot affect inputs.
        changed = _bars(400)+source
        start = datetime(2025,12,30,14,40,tzinfo=timezone.utc)
        for i,row in enumerate(changed):
            row["t"] = (start+timedelta(minutes=5*i)).isoformat()
        self.assertEqual({k:v for k,v in candle.items() if k != "timestamp"},
                         {k:v for k,v in build_validation_candles(changed,strategy)[-1].items() if k != "timestamp"})

    def test_v2_does_not_assume_400_bars_are_universally_stable(self):
        from decimal import Decimal
        source = _bars(1200)
        for i,row in enumerate(source):
            close=Decimal("100000" if i<800 else "100" if i<1199 else "100.02")
            row.update(o=str(close),h=str(close+Decimal(".01")),l=str(close-Decimal(".01")),c=str(close))
        candle=build_validation_candles(source,"alpaca-btc-5m-trend-400-v2")[-1]
        self.assertEqual(candle["indicator_history_stable"],"0")
        self.assertEqual(build_validation_candles(source[:400],"alpaca-btc-5m-trend-400-v2"),[])

    def test_trend_features_start_after_warmup_and_use_only_past_bars(self):
        source = _bars()
        changed_future = copy.deepcopy(source)
        changed_future[-1]["c"] = "9999"
        changed_future[-1]["o"] = "9999"
        changed_future[-1]["h"] = "10000"
        changed_future[-1]["l"] = "9998"

        original = build_validation_candles(source, "alpaca-btc-5m-trend-v1")
        changed = build_validation_candles(changed_future, "alpaca-btc-5m-trend-v1")

        self.assertEqual(len(original), 10)
        self.assertEqual(original[0]["timestamp"], "2026-01-01T04:10:00+00:00")
        self.assertEqual(original[0]["close"], "150")
        self.assertEqual(original[0]["prior_20_high"], "150")
        self.assertEqual(
            {key: original[0][key] for key in ("ema_20", "ema_50", "atr_14", "prior_20_high")},
            {key: changed[0][key] for key in ("ema_20", "ema_50", "atr_14", "prior_20_high")},
        )

    def test_gap_splits_history_without_filling_or_bridging_indicators(self):
        source = _bars(120)
        gap_timestamp = source.pop(60)["t"]

        candles = build_validation_candles(source, "alpaca-btc-5m-trend-v1")

        self.assertEqual(len(candles), 19)
        self.assertEqual(candles[0]["timestamp"], "2026-01-01T04:10:00+00:00")
        self.assertEqual(candles[10]["timestamp"], "2026-01-01T09:15:00+00:00")
        self.assertNotIn(gap_timestamp, {row["timestamp"] for row in candles})


if __name__ == "__main__":
    unittest.main()
