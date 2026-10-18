"""Paper measurements must never become live capital/profit evidence."""
import unittest

from alpaca_snapshot import build_alpaca_snapshot
from cross_venue_allocator import build_candidates, rank
from net_pnl import aggregate, venue_net
from rolling_measurement import rolling_30d
from venue_receipts import normalize_receipts
from test_alpaca_snapshot import PERFORMANCE, OBSERVATION, RISK
from test_cross_venue_allocator import CAPS
from test_net_pnl import NOW, snapshot
from test_portfolio_performance import snapshot_payload
from test_rolling_measurement import END_DAY, thirty_days


class MeasurementModeTests(unittest.TestCase):
    def test_adapter_net_and_aggregate_preserve_paper_mode(self):
        performance = {**PERFORMANCE, "mode": "paper", "paper": True,
            "slippage_included_in_gross_pnl": True,
            "funding_or_borrow_usd": "0", "gas_usd": "0",
            "model_cost_usd": "0", "system_cost_usd": "0"}
        converted = build_alpaca_snapshot(performance, OBSERVATION, RISK)
        self.assertEqual(converted.get("measurement_mode"), "paper")
        row = snapshot(measurement_mode="paper", paper=True)
        for result in (venue_net(row), aggregate("2026-09-01T00:00:00Z", NOW.isoformat(), [row], "0")):
            self.assertEqual(result.get("measurement_mode"), "paper")
            self.assertIs(result.get("paper"), True)
            self.assertEqual(result["measurement_status"], "measured")

    def test_mixed_venue_and_receipt_modes_are_rejected(self):
        rows = [snapshot(measurement_mode="live", paper=False),
            snapshot("other", "b", measurement_mode="paper", paper=True)]
        result = aggregate("2026-09-01T00:00:00Z", NOW.isoformat(), rows, "0")
        self.assertEqual(result.get("reason"), "measurement_mode_mixed")
        self.assertNotIn("net_pnl_usd", result)
        receipts = [dict(snapshot_payload(), receipt_id="a", measurement_mode="live", paper=False),
            dict(snapshot_payload(), receipt_id="b", measurement_mode="paper", paper=True)]
        result = normalize_receipts("alpaca", receipts)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("reason"), "measurement_mode_mixed")

    def test_missing_or_inconsistent_mode_cannot_be_measured(self):
        for mode, paper in ((None, None), ("live", True), ("paper", False), ("live", 0), ("live", None), ("other", False)):
            with self.subTest(mode=mode, paper=paper):
                result = venue_net(snapshot(measurement_mode=mode, paper=paper))
                self.assertNotEqual(result["measurement_status"], "measured")
                self.assertNotIn("net_pnl_usd", result)

    def test_paper_and_shadow_never_become_live_candidates(self):
        for mode, paper in (("paper", True), ("shadow", False)):
            row = snapshot(measurement_mode=mode, paper=paper)
            combined = aggregate("2026-09-01T00:00:00Z", NOW.isoformat(), [row], "0")
            self.assertEqual(build_candidates([row], combined, CAPS), [])
        live = snapshot(measurement_mode="live", paper=False)
        combined = aggregate("2026-09-01T00:00:00Z", NOW.isoformat(), [live], "0")
        candidate = build_candidates([live], combined, CAPS)[0]
        self.assertEqual(candidate.get("measurement_mode"), "live")
        for mode, paper in (("paper", True), ("shadow", False), (None, None), ("live", True)):
            result = rank([{**candidate, "measurement_mode": mode, "paper": paper}], "500", CAPS)
            self.assertEqual(result["action"], "hold")
            self.assertEqual(result["ranked"], [])

    def test_non_live_aggregate_cannot_authorize_live_candidate_rows(self):
        live = snapshot(measurement_mode="live", paper=False)
        paper = snapshot(measurement_mode="paper", paper=True)
        combined = aggregate("2026-09-01T00:00:00Z", NOW.isoformat(), [paper], "0")
        self.assertEqual(build_candidates([live], combined, CAPS), [])

    def test_rolling_profit_requires_explicit_live_on_every_day(self):
        for mode, paper in (("paper", True), ("shadow", False), (None, None), ("live", True)):
            receipts = thirty_days()
            for row in receipts:
                row["aggregate"].update(measurement_mode="live", paper=False)
            receipts[5]["aggregate"].update(measurement_mode=mode, paper=paper)
            result = rolling_30d(receipts, END_DAY)
            self.assertNotEqual(result["measurement_status"], "measured")
            self.assertIsNone(result["net_pnl_usd"])
