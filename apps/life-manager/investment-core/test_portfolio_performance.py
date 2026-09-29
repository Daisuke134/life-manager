import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from portfolio_performance import aggregate
from portfolio_receipts import VenueSnapshot


NOW = datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc)


def snapshot_payload(**changes):
    payload = {
        "venue": "alpaca",
        "observed_at": "2026-09-27T23:59:00Z",
        "equity_usd": "100.00",
        "free_cash_usd": "90.00",
        "gross_pnl_usd": "0.00",
        "trading_fees_usd": "0.00",
        "funding_or_borrow_usd": "0.00",
        "slippage_usd": "0.00",
        "gas_usd": "0.00",
        "model_cost_usd": "0.00",
        "source_receipt_ids": ["alpaca-receipt-1"],
        "risk": {"drawdown_usd": "0.00"},
        "measurement_status": "measured",
    }
    payload.update(changes)
    return payload


class PortfolioPerformanceTest(unittest.TestCase):
    def test_owner_deposit_is_principal_and_not_net_pnl(self):
        result = aggregate(
            [VenueSnapshot.from_mapping(snapshot_payload())],
            owner_cash_flow_usd="50.00",
            now=NOW,
        )

        self.assertEqual(result["measurement_status"], "measured")
        self.assertEqual(result["owner_cash_flow_usd"], "50.00")
        self.assertEqual(result["net_pnl_usd"], "0.00")
        self.assertNotEqual(result["net_pnl_usd"], result["owner_cash_flow_usd"])

    def test_net_pnl_subtracts_every_known_cost_once(self):
        snapshot = VenueSnapshot.from_mapping(snapshot_payload(
            gross_pnl_usd="10.00",
            trading_fees_usd="1.00",
            funding_or_borrow_usd="0.50",
            slippage_usd="0.25",
            gas_usd="0.10",
            model_cost_usd="0.15",
        ))

        result = aggregate([snapshot], owner_cash_flow_usd="0", now=NOW)

        self.assertEqual(result["net_pnl_usd"], "8.00")
        self.assertEqual(result["gross_pnl_usd"], "10.00")
        self.assertEqual(result["trading_fees_usd"], "1.00")
        self.assertEqual(result["funding_or_borrow_usd"], "0.50")
        self.assertEqual(result["slippage_usd"], "0.25")
        self.assertEqual(result["gas_usd"], "0.10")
        self.assertEqual(result["model_cost_usd"], "0.15")

    def test_duplicate_receipt_within_snapshot_blocks_aggregation(self):
        snapshot = VenueSnapshot.from_mapping(snapshot_payload(
            source_receipt_ids=["same-receipt", "same-receipt"],
        ))

        result = aggregate([snapshot], owner_cash_flow_usd="0", now=NOW)

        self.assertEqual(result["measurement_status"], "blocked")
        self.assertEqual(result["reason"], "source_receipt_duplicate")
        self.assertNotIn("net_pnl_usd", result)

    def test_missing_cost_blocks_without_treating_unknown_as_zero(self):
        snapshot = VenueSnapshot.from_mapping(snapshot_payload(gas_usd=None))

        result = aggregate([snapshot], owner_cash_flow_usd="0", now=NOW)

        self.assertEqual(result["measurement_status"], "blocked")
        self.assertEqual(result["reason"], "cost_unknown")
        self.assertNotIn("net_pnl_usd", result)

    def test_stale_snapshot_is_excluded_and_blocks_measurement(self):
        stale = VenueSnapshot.from_mapping(snapshot_payload(
            venue="hyperliquid",
            observed_at="2026-09-27T23:00:00Z",
            source_receipt_ids=["hl-stale"],
        ))

        result = aggregate([stale], owner_cash_flow_usd="0", now=NOW)

        self.assertEqual(result["measurement_status"], "blocked")
        self.assertEqual(result["reason"], "stale_snapshot")
        self.assertEqual(result["excluded_venues"], ["hyperliquid"])
        self.assertNotIn("net_pnl_usd", result)

    def test_same_receipt_id_across_venues_blocks_aggregation(self):
        alpaca = VenueSnapshot.from_mapping(snapshot_payload(
            source_receipt_ids=["shared-receipt"],
        ))
        hyperliquid = VenueSnapshot.from_mapping(snapshot_payload(
            venue="hyperliquid",
            source_receipt_ids=["shared-receipt"],
        ))

        result = aggregate([alpaca, hyperliquid], owner_cash_flow_usd="0", now=NOW)

        self.assertEqual(result["measurement_status"], "blocked")
        self.assertEqual(result["reason"], "source_receipt_cross_venue_duplicate")
        self.assertNotIn("net_pnl_usd", result)


if __name__ == "__main__":
    unittest.main()
