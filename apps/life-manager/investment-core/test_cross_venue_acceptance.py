import inspect
import unittest
from datetime import datetime, timezone

import cross_venue_allocator
from cross_venue_allocator import build_candidates, rank
from net_pnl import aggregate
from venue_snapshot import VenueSnapshot


NOW = datetime(2026, 9, 28, 8, 0, tzinfo=timezone.utc)


def snapshot(venue, receipt_id, gross, fees, funding, slippage, gas, model):
    return VenueSnapshot.from_mapping({
        "venue": venue,
        "observed_at": "2026-09-28T07:59:30Z",
        "equity_usd": "1000",
        "free_cash_usd": "500",
        "gross_pnl_usd": gross,
        "trading_fees_usd": fees,
        "funding_or_borrow_usd": funding,
        "slippage_usd": slippage,
        "gas_usd": gas,
        "model_cost_usd": model,
        "source_receipt_ids": [receipt_id],
        "risk": {"drawdown_fraction": "0.01", "round_trips": 30, "capital_at_risk_usd": "100"},
        "measurement_status": "measured",
    })


class CrossVenueAcceptanceTests(unittest.TestCase):
    def test_three_venue_fixture_has_exact_net_breakdown_and_no_execution_import(self):
        alpaca = snapshot("alpaca", "alpaca-1", "10", "1", "0.5", "0.25", "0.1", "0.15")
        hyperliquid = snapshot("hyperliquid", "hl-1", "4", "0.5", "0.25", "0.1", "0.05", "0.05")
        solana = snapshot("solana", "sol-1", "-2", "0.1", "0", "0.1", "0.1", "0.05")

        result = aggregate("2026-09-01T00:00:00Z", NOW.isoformat(), [alpaca, hyperliquid, solana], "100")
        candidates = build_candidates([alpaca, hyperliquid, solana], result, {
            "cash_reserve_usd": "100",
            "max_allocation_usd": "100",
            "current_cap_usd": "100",
            "max_drawdown_fraction": "0.20",
            "min_round_trips": 30,
        })
        allocation = rank(candidates, "500", {
            "cash_reserve_usd": "100",
            "max_allocation_usd": "100",
            "current_cap_usd": "100",
            "max_drawdown_fraction": "0.20",
            "min_round_trips": 30,
        })

        self.assertEqual(result["net_pnl_usd"], "8.70")
        self.assertEqual(result["owner_cash_flow_usd"], "100.00")
        self.assertEqual([row["venue"] for row in result["venue_rows"]], ["alpaca", "hyperliquid", "solana"])
        self.assertEqual(all("source_receipt_ids" in row for row in result["venue_rows"]), True)
        self.assertEqual(all("submit" not in inspect.getsource(cross_venue_allocator).lower() for _ in [0]), True)
        self.assertEqual(all("sign(" not in inspect.getsource(cross_venue_allocator).lower() for _ in [0]), True)
        self.assertEqual(all(row["venue"] != "solana" for row in allocation["ranked"]), True)
        self.assertEqual(all(row["allocation_usd"] == "100.00" for row in allocation["ranked"]), True)


if __name__ == "__main__":
    unittest.main()
