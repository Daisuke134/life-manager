import unittest
from pathlib import Path

from scout import rank_assets
from backtest import momentum_trades, summarize

HERE = Path(__file__).parent


class TestRankAssets(unittest.TestCase):
    def test_orders_by_volume_and_skips_delisted(self):
        meta = {
            "universe": [
                {"name": "BTC", "szDecimals": 5},
                {"name": "DEAD", "szDecimals": 2, "isDelisted": True},
                {"name": "ETH", "szDecimals": 4},
            ]
        }
        ctxs = [
            {
                "funding": "0.00001",
                "openInterest": "100",
                "prevDayPx": "90000",
                "dayNtlVlm": "1000000",
                "markPx": "100000",
                "midPx": "100000",
                "impactPxs": ["99990", "100010"],
            },
            {
                "funding": "0.0",
                "openInterest": "1",
                "prevDayPx": "1",
                "dayNtlVlm": "999999999",
                "markPx": "1",
                "midPx": "1",
                "impactPxs": None,
            },
            {
                "funding": "0.00002",
                "openInterest": "500",
                "prevDayPx": "4000",
                "dayNtlVlm": "5000000",
                "markPx": "4200",
                "midPx": "4200",
                "impactPxs": ["4195", "4205"],
            },
        ]
        out = rank_assets(meta, ctxs, top=10)
        coins = [r["coin"] for r in out]
        self.assertEqual(coins, ["ETH", "BTC"])  # DEAD skipped, ETH has higher volume

    def test_impact_spread_and_apr_math(self):
        meta = {"universe": [{"name": "BTC", "szDecimals": 5}]}
        ctxs = [
            {
                "funding": "0.0001",
                "openInterest": "10",
                "prevDayPx": "100",
                "dayNtlVlm": "1000",
                "markPx": "110",
                "midPx": "110",
                "impactPxs": ["109", "111"],
            }
        ]
        out = rank_assets(meta, ctxs, top=1)
        row = out[0]
        self.assertAlmostEqual(row["impact_spread_bps"], (111 - 109) / 110 * 1e4)
        self.assertAlmostEqual(row["funding_apr"], 0.0001 * 24 * 365)
        self.assertAlmostEqual(row["day_change_pct"], (110 / 100 - 1) * 100)
        self.assertAlmostEqual(row["open_interest_usd"], 10 * 110)

    def test_null_mid_gives_no_impact_spread(self):
        meta = {"universe": [{"name": "BTC", "szDecimals": 5}]}
        ctxs = [
            {
                "funding": "0.0",
                "openInterest": "10",
                "prevDayPx": "100",
                "dayNtlVlm": "1000",
                "markPx": "100",
                "midPx": None,
                "impactPxs": None,
            }
        ]
        out = rank_assets(meta, ctxs, top=1)
        self.assertIsNone(out[0]["impact_spread_bps"])

    def test_top_limits_result_count(self):
        meta = {"universe": [{"name": f"C{i}"} for i in range(5)]}
        ctxs = [
            {
                "funding": "0",
                "openInterest": "1",
                "prevDayPx": "1",
                "dayNtlVlm": str(i),
                "markPx": "1",
                "midPx": "1",
                "impactPxs": None,
            }
            for i in range(5)
        ]
        out = rank_assets(meta, ctxs, top=2)
        self.assertEqual(len(out), 2)


def make_candles(closes, start_ms=0, step_ms=3600_000):
    return [{"t": start_ms + i * step_ms, "c": str(c)} for i, c in enumerate(closes)]


class TestMomentumTrades(unittest.TestCase):
    def test_long_signal_and_cost_subtraction(self):
        # close[1]/close[0]-1 = 0.1 > 0 -> long at i=1, exit i=2
        closes = [100, 110, 121]
        candles = make_candles(closes)
        trades = momentum_trades(candles, [], lookback=1, hold=1, taker_fee=0.001, slippage_bps=0)
        self.assertEqual(len(trades), 1)
        t = trades[0]
        self.assertEqual(t["side"], 1)
        self.assertAlmostEqual(t["gross"], 121 / 110 - 1)
        self.assertAlmostEqual(t["costs"], 2 * 0.001)
        self.assertAlmostEqual(t["net"], t["gross"] - t["costs"] - t["funding_cost"])

    def test_short_signal_on_falling_series(self):
        closes = [100, 100, 90, 90, 80]
        candles = make_candles(closes)
        trades = momentum_trades(candles, [], lookback=2, hold=2, taker_fee=0.0, slippage_bps=0)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["side"], -1)
        self.assertAlmostEqual(trades[0]["gross"], -1 * (80 / 90 - 1))

    def test_zero_base_return_is_skipped(self):
        closes = [100, 100, 100, 100, 100]
        candles = make_candles(closes)
        trades = momentum_trades(candles, [], lookback=2, hold=2, taker_fee=0.0, slippage_bps=0)
        self.assertEqual(trades, [])

    def test_funding_sign_long_pays_short_receives(self):
        closes = [100, 110, 121]
        candles = make_candles(closes)
        # funding accrues in (t_entry, t_exit] = (candles[1].t, candles[2].t]
        funding = [{"time": candles[2]["t"], "fundingRate": "0.001"}]
        long_trades = momentum_trades(candles, funding, lookback=1, hold=1, taker_fee=0.0, slippage_bps=0)
        self.assertEqual(long_trades[0]["side"], 1)
        self.assertAlmostEqual(long_trades[0]["funding_cost"], 0.001)  # long pays -> positive cost
        self.assertAlmostEqual(long_trades[0]["net"], long_trades[0]["gross"] - 0.001)

        short_trades = momentum_trades(
            candles, funding, lookback=1, hold=1, taker_fee=0.0, slippage_bps=0, force_side=-1
        )
        self.assertAlmostEqual(short_trades[0]["funding_cost"], -0.001)  # short receives

    def test_non_overlapping_stepping(self):
        # 9 candles, lookback=2, hold=2 -> entries at i=2,4,6 (i+hold<9)
        closes = list(range(100, 109))
        candles = make_candles(closes)
        trades = momentum_trades(candles, [], lookback=2, hold=2, taker_fee=0.0, slippage_bps=0)
        entries = [t["t_entry"] for t in trades]
        self.assertEqual(entries, [candles[2]["t"], candles[4]["t"], candles[6]["t"]])


class TestSummarize(unittest.TestCase):
    def test_constant_positive_series_is_supported(self):
        returns = [0.01] * 30
        s = summarize(returns, seed=1, n_boot=500)
        self.assertTrue(s["statistically_supported"])
        self.assertGreater(s["ci95"][0], 0)

    def test_zero_mean_symmetric_series_is_not_supported(self):
        returns = [0.01, -0.01] * 20
        s = summarize(returns, seed=1, n_boot=500)
        self.assertFalse(s["statistically_supported"])

    def test_empty_returns(self):
        s = summarize([], seed=1)
        self.assertEqual(s["n"], 0)
        self.assertFalse(s["statistically_supported"])


class TestNoSigningOrExchangeCode(unittest.TestCase):
    def test_source_has_no_signing_or_private_key_references(self):
        for fname in ("scout.py", "backtest.py"):
            src = (HERE / fname).read_text()
            self.assertNotIn('"/exchange"', src)
            self.assertNotIn("private_key", src)
            self.assertNotIn("PRIVATE_KEY", src)
            self.assertNotIn("eth_account", src)
            self.assertNotIn("sign_", src)


if __name__ == "__main__":
    unittest.main()
