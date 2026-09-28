import unittest
from datetime import datetime, timezone

from net_pnl import aggregate, venue_net
from venue_snapshot import VenueSnapshot


NOW = datetime(2026, 9, 28, 8, 0, tzinfo=timezone.utc)


def snapshot(venue="alpaca", receipt_id="a-1", **changes):
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
        "source_receipt_ids": [receipt_id],
        "risk": {"drawdown_fraction": "0.01"},
        "measurement_status": "measured",
    }
    payload.update(changes)
    return VenueSnapshot.from_mapping(payload)


class NetPnlTests(unittest.TestCase):
    def test_venue_net_subtracts_every_cost_once(self):
        result = venue_net(snapshot())

        self.assertEqual(result["net_pnl_usd"], "8.00")
        self.assertEqual(result["source_receipt_ids"], ["a-1"])

    def test_aggregate_keeps_owner_cash_flow_out_of_pnl(self):
        result = aggregate("2026-09-01T00:00:00Z", NOW.isoformat(), [snapshot()], "250")

        self.assertEqual(result["net_pnl_usd"], "8.00")
        self.assertEqual(result["owner_cash_flow_usd"], "250.00")
        self.assertEqual(result["period_start"], "2026-09-01T00:00:00Z")

    def test_missing_cost_is_blocked_not_zero(self):
        result = aggregate("2026-09-01T00:00:00Z", NOW.isoformat(), [snapshot(gas_usd=None)], "0")

        self.assertEqual(result["measurement_status"], "blocked")
        self.assertEqual(result["reason"], "cost_unknown")
        self.assertNotIn("net_pnl_usd", result)

    def test_duplicate_receipt_ids_are_blocked(self):
        result = aggregate(
            "2026-09-01T00:00:00Z",
            NOW.isoformat(),
            [snapshot(receipt_id="same"), snapshot("hyperliquid", "same")],
            "0",
        )

        self.assertEqual(result["measurement_status"], "blocked")
        self.assertEqual(result["reason"], "source_receipt_cross_venue_duplicate")

    def test_negative_net_is_measured_and_not_hidden(self):
        result = aggregate(
            "2026-09-01T00:00:00Z",
            NOW.isoformat(),
            [snapshot(gross_pnl_usd="1", trading_fees_usd="3")],
            "0",
        )

        self.assertEqual(result["measurement_status"], "measured")
        self.assertEqual(result["net_pnl_usd"], "-3.00")


if __name__ == "__main__":
    unittest.main()
