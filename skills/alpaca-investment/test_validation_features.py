from __future__ import annotations

import copy
import unittest
from datetime import datetime, timedelta, timezone

from strategy_policy import build_validation_candles


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
