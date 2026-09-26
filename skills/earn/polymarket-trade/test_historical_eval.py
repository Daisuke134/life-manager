import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import historical_eval as he  # noqa: E402


def market(mid, event, prices='["1", "0"]', start="2026-07-01T00:00:00Z",
           closed="2026-07-03 00:00:00+00", fees=True, sched=None, end="2026-07-03T00:00:00Z"):
    return {"id": mid, "question": mid, "outcomes": '["Yes", "No"]', "outcomePrices": prices,
            "clobTokenIds": '["111", "222"]', "startDate": start, "closedTime": closed, "endDate": end,
            "feesEnabled": fees, "feeSchedule": sched or {"exponent": 1, "rate": 0.05},
            "events": [{"id": event}]}


class HistoricalEvalTest(unittest.TestCase):
    def test_parse_ts_gamma_formats(self):
        self.assertEqual(he.parse_ts("2026-07-03 00:00:00+00"), he.parse_ts("2026-07-03T00:00:00Z"))
        self.assertEqual(he.parse_ts("2026-09-26 10:21:52.235331+00") // 1, he.parse_ts("2026-09-26T10:21:52Z"))
        self.assertIsNone(he.parse_ts(None))

    def test_select_markets_filters_and_dedupes(self):
        raw = [
            market("a", "e1"),
            market("b", "e1"),  # same event
            market("c", "e2", prices='["0.5", "0.5"]'),  # not cleanly resolved
            market("d", "e3", start="2026-07-02T12:00:00Z"),  # opened after entry
            market("e", "e4", sched={"exponent": 2, "rate": 0.05}),  # unknown fee curve
            market("f", "e5", prices='["0", "1"]', fees=False),
            {**market("g", "e6"), "feeSchedule": "broken"},  # malformed: skipped, not fatal
            market("h", "e7", end="2026-08-01T00:00:00Z"),  # resolved early: would leak outcome
        ]
        keep, funnel = he.select_markets(raw, horizon_h=24)
        self.assertEqual([m["id"] for m in keep], ["a", "f"])
        self.assertTrue(keep[0]["yes_won"])
        self.assertFalse(keep[1]["yes_won"])
        self.assertEqual(keep[0]["fee_rate"], 0.05)
        self.assertEqual(keep[1]["fee_rate"], 0.0)
        self.assertEqual(funnel, {"fetched": 8, "not_binary_resolved": 1, "fee_unknown": 1,
                                  "too_young": 1, "closed_before_entry": 1,
                                  "duplicate_event": 1, "malformed": 1, "eligible": 2})

    def test_price_at_uses_last_point_and_rejects_stale(self):
        hist = [{"t": 100, "p": 0.4}, {"t": 200, "p": 0.8}, {"t": 400, "p": 0.1}]
        self.assertEqual(he.price_at(hist, 300), 0.8)
        self.assertIsNone(he.price_at(hist, 50))
        self.assertIsNone(he.price_at(hist, 400 + he.MAX_STALENESS_S + 1))

    def test_favorite_trade_fee_and_slippage(self):
        t = he.favorite_trade(0.80, True, (0.7, 0.95), fee_rate=0.05, slippage=0.01)
        fill = 0.81
        fee = 0.05 * fill * (1 - fill)
        self.assertEqual(t["side"], "YES")
        self.assertAlmostEqual(t["net_return"], 1 / (fill + fee) - 1)
        self.assertAlmostEqual(t["gross_return"], 1 / 0.80 - 1)
        self.assertLess(t["net_return"], t["gross_return"])

    def test_favorite_trade_no_side_and_loss(self):
        t = he.favorite_trade(0.10, True, (0.7, 0.95), fee_rate=0.0, slippage=0.0)
        self.assertEqual(t["side"], "NO")
        self.assertFalse(t["won"])
        self.assertEqual(t["net_return"], -1.0)
        self.assertIsNone(he.favorite_trade(0.5, True, (0.7, 0.95), 0.0, 0.0))

    def test_summarize_support(self):
        self.assertTrue(he.summarize([0.01] * 50, seed=1)["statistically_supported"])
        flat = he.summarize([1.0, -1.0] * 50, seed=1)
        self.assertFalse(flat["statistically_supported"])
        self.assertAlmostEqual(flat["mean"], 0.0)
        self.assertFalse(he.summarize([0.5], seed=1)["statistically_supported"])

    def test_fetch_markets_offset_skips_recent_days(self):
        import datetime as dt
        seen = []
        orig_get, orig_sleep = he._get, he.time.sleep
        he._get = lambda url, params: seen.append(params["end_date_min"][:10]) or []
        he.time.sleep = lambda s: None
        try:
            he.fetch_markets(2, 5, 0, dt.date(2026, 9, 27), offset_days=60)
        finally:
            he._get, he.time.sleep = orig_get, orig_sleep
        self.assertEqual(seen, ["2026-07-28", "2026-07-27"])

    def test_clustered_bootstrap_resamples_whole_days(self):
        rets = [1.0, 1.0, 1.0, -1.0]
        s = he.summarize(rets, seed=1, clusters=["d1", "d1", "d1", "d2"])
        self.assertEqual(s["clusters"], 2)
        self.assertFalse(s["statistically_supported"])

    def test_robustness_rejects_edge_carried_by_one_trade(self):
        trades = [{"net_return": r, "close_ts": 1790000000 + i * 86400}
                  for i, r in enumerate([9.0] + [-0.05] * 30)]
        r = he.robustness(trades, seed=1)
        self.assertFalse(r["drop_top_1"]["statistically_supported"])
        self.assertFalse(r["robustly_supported"])

    def test_module_is_read_only(self):
        src = open(he.__file__).read()
        for banned in ("post_order", "create_market_order", "PRIVATE_KEY", "private_key",
                       "SecureClient", "requests.post"):
            self.assertNotIn(banned, src)
        json.dumps({})


if __name__ == "__main__":
    unittest.main()
