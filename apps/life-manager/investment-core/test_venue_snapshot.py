import unittest
from decimal import Decimal

from venue_receipts import normalize_receipts
from venue_snapshot import VenueSnapshot


def receipt(receipt_id="r1", **overrides):
    row = {
        "receipt_id": receipt_id,
        "observed_at": "2026-09-28T08:00:00Z",
        "equity_usd": "1000",
        "free_cash_usd": "500",
        "gross_pnl_usd": "10",
        "trading_fees_usd": "1",
        "funding_or_borrow_usd": "0.5",
        "slippage_usd": "0.25",
        "gas_usd": "0.10",
        "model_cost_usd": "0.15",
        "risk": {"drawdown_fraction": "0.01"},
        "measurement_status": "measured",
    }
    row.update(overrides)
    return row


class VenueSnapshotTests(unittest.TestCase):
    def test_normalizes_valid_receipts_and_preserves_cost_evidence(self):
        snapshot = normalize_receipts("alpaca", [receipt(), receipt("r2", gross_pnl_usd="2")])

        self.assertIsInstance(snapshot, VenueSnapshot)
        self.assertEqual(snapshot.venue, "alpaca")
        self.assertEqual(snapshot.equity_usd, Decimal("1000"))
        self.assertEqual(snapshot.free_cash_usd, Decimal("500"))
        self.assertEqual(snapshot.gross_pnl_usd, Decimal("12"))
        self.assertEqual(snapshot.source_receipt_ids, ("r1", "r2"))
        self.assertEqual(snapshot.cost_evidence["model_cost_usd"], ("r1", "r2"))

    def test_missing_model_cost_is_unknown_not_zero(self):
        result = normalize_receipts("alpaca", [receipt(model_cost_usd=None)])

        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "cost_unknown")

    def test_duplicate_receipt_ids_are_rejected(self):
        result = normalize_receipts("alpaca", [receipt("same"), receipt("same")])

        self.assertEqual(result, {"status": "unknown", "reason": "source_receipt_duplicate"})

    def test_malformed_numbers_are_unknown(self):
        result = normalize_receipts("alpaca", [receipt(gross_pnl_usd="not-a-number")])

        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "snapshot_number_invalid")

    def test_effect_unknown_receipt_is_not_measured(self):
        result = normalize_receipts("solana", [receipt(status="effect_unknown")])

        self.assertEqual(result, {"status": "unknown", "reason": "effect_unknown"})


if __name__ == "__main__":
    unittest.main()
