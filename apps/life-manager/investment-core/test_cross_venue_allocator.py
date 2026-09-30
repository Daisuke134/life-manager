import unittest
from datetime import datetime, timezone

from cross_venue_allocator import build_candidates, rank
from net_pnl import aggregate
from venue_snapshot import VenueSnapshot


NOW = datetime(2026, 9, 28, 8, 0, tzinfo=timezone.utc)
CAPS = {
    "cash_reserve_usd": "100",
    "max_allocation_usd": "100",
    "current_cap_usd": "100",
    "max_drawdown_fraction": "0.20",
    "min_round_trips": 30,
}


def snapshot(venue="alpaca", receipt_id=None, **changes):
    payload = {
        "venue": venue,
        "observed_at": "2026-09-28T07:59:00Z",
        "equity_usd": "1000",
        "free_cash_usd": "500",
        "gross_pnl_usd": "10",
        "trading_fees_usd": "1",
        "funding_or_borrow_usd": "0.5",
        "slippage_usd": "0.25",
        "gas_usd": "0.1",
        "model_cost_usd": "0.15",
        "source_receipt_ids": [receipt_id or f"{venue}-receipt"],
        "risk": {"drawdown_fraction": "0.01", "round_trips": 30, "capital_at_risk_usd": "100"},
        "measurement_status": "measured",
    }
    payload.update(changes)
    return VenueSnapshot.from_mapping(payload)


def measured_aggregate(*rows):
    return aggregate("2026-09-01T00:00:00Z", NOW.isoformat(), list(rows), "0")


class CrossVenueAllocatorTests(unittest.TestCase):
    def test_positive_measured_net_is_a_candidate_but_unknown_cost_is_not(self):
        good = snapshot("alpaca")
        unknown = snapshot("hyperliquid", gas_usd=None)

        candidates = build_candidates([good, unknown], measured_aggregate(good), CAPS)

        self.assertEqual([row["candidate_ref"] for row in candidates], ["venue://alpaca"])
        self.assertTrue(candidates[0]["verified"])

    def test_stale_candidate_is_excluded(self):
        row = build_candidates([snapshot()], measured_aggregate(snapshot()), CAPS)[0]
        row["stale"] = True

        result = rank([row], "500", CAPS)

        self.assertEqual(result["action"], "hold")
        self.assertEqual(result["excluded"][0]["reason"], "stale_snapshot")

    def test_drawdown_breach_halts_allocation(self):
        row = build_candidates([snapshot()], measured_aggregate(snapshot()), CAPS)[0]
        row["risk"]["drawdown_fraction"] = "0.30"

        result = rank([row], "500", CAPS)

        self.assertEqual(result["action"], "halt")
        self.assertEqual(result["reason"], "drawdown_breach")
        self.assertEqual(result["allocation_usd"], "0.00")

    def test_cash_reserve_is_kept_out_of_allocation(self):
        row = build_candidates([snapshot()], measured_aggregate(snapshot()), CAPS)[0]

        result = rank([row], "50", CAPS)

        self.assertEqual(result["action"], "hold")
        self.assertEqual(result["reason"], "cash_reserve")
        self.assertEqual(result["allocation_usd"], "0.00")

    def test_tie_break_is_deterministic_by_venue(self):
        first = snapshot("zeta", "zeta-receipt")
        second = snapshot("alpha", "alpha-receipt")
        rows = build_candidates([first, second], measured_aggregate(first, second), CAPS)

        result = rank(rows, "500", CAPS)

        self.assertEqual(result["action"], "allocate")
        self.assertEqual([row["venue"] for row in result["ranked"]], ["alpha", "zeta"])
        self.assertEqual(result["allocation_usd"], "100.00")

    def test_capital_expansion_is_denied_below_sample_threshold(self):
        row_snapshot = snapshot()
        row_snapshot.risk["round_trips"] = 1
        row = build_candidates([row_snapshot], measured_aggregate(row_snapshot), CAPS)[0]
        row["requested_cap_usd"] = "1000"

        result = rank([row], "500", {**CAPS, "max_allocation_usd": "10000", "current_cap_usd": "100"})

        self.assertEqual(result["action"], "hold")
        self.assertEqual(result["excluded"][0]["reason"], "sample_below_threshold")
        self.assertFalse(result["capital_expansion_allowed"])


if __name__ == "__main__":
    unittest.main()
