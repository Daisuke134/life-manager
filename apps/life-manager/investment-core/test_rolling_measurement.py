import unittest
from datetime import date, timedelta

from rolling_measurement import rolling_30d


END_DAY = "2026-09-28"


def daily(day, net="1.00", owner_flow="0.00", receipt_id=None, *, status="delivered", measurement_status="measured"):
    return {
        "day": day,
        "status": status,
        "aggregate": {
            "measurement_status": measurement_status,
            "net_pnl_usd": net,
            "owner_cash_flow_usd": owner_flow,
            "source_receipt_ids": [receipt_id or f"provider-{day}"],
        },
    }


def thirty_days(**kwargs):
    end = date.fromisoformat(END_DAY)
    return [
        daily((end - timedelta(days=offset)).isoformat(), receipt_id=f"provider-{offset}", **kwargs)
        for offset in range(29, -1, -1)
    ]


class RollingMeasurementTests(unittest.TestCase):
    def test_sums_exactly_thirty_measured_days_and_keeps_owner_flow_separate(self):
        receipts = thirty_days(net="2.50", owner_flow="100.00")

        result = rolling_30d(receipts, END_DAY)

        self.assertEqual(result["measurement_status"], "measured")
        self.assertEqual(result["period_start"], "2026-08-30")
        self.assertEqual(result["period_end"], END_DAY)
        self.assertEqual(result["days_observed"], 30)
        self.assertEqual(result["net_pnl_usd"], "75.00")
        self.assertEqual(result["owner_cash_flow_usd"], "3000.00")
        self.assertEqual(result["target_gap_usd"], "9925.00")
        self.assertEqual(len(result["source_receipt_ids"]), 30)

    def test_missing_day_returns_unknown_without_zero_filling(self):
        receipts = thirty_days()
        receipts.pop(9)

        result = rolling_30d(receipts, END_DAY)

        self.assertEqual(result["measurement_status"], "unknown")
        self.assertEqual(result["reason"], "daily_receipt_missing")
        self.assertEqual(result["net_pnl_usd"], None)
        self.assertEqual(result["target_gap_usd"], None)
        self.assertEqual(result["missing_days"], ["2026-09-08"])

    def test_partial_or_undelivered_day_returns_unknown(self):
        receipts = thirty_days()
        receipts[4]["aggregate"]["measurement_status"] = "partial"

        result = rolling_30d(receipts, END_DAY)

        self.assertEqual(result["measurement_status"], "unknown")
        self.assertEqual(result["reason"], "daily_measurement_incomplete")
        self.assertEqual(result["net_pnl_usd"], None)

        receipts = thirty_days()
        receipts[4]["status"] = "delivery_uncertain"
        result = rolling_30d(receipts, END_DAY)
        self.assertEqual(result["measurement_status"], "unknown")
        self.assertEqual(result["reason"], "daily_receipt_not_delivered")
        self.assertEqual(result["net_pnl_usd"], None)

    def test_duplicate_day_and_cross_day_source_receipt_block(self):
        receipts = thirty_days()
        receipts[1]["day"] = receipts[0]["day"]
        result = rolling_30d(receipts, END_DAY)
        self.assertEqual(result["measurement_status"], "blocked")
        self.assertEqual(result["reason"], "daily_receipt_duplicate")
        self.assertIsNone(result["net_pnl_usd"])

        receipts = thirty_days()
        receipts[1]["aggregate"]["source_receipt_ids"] = receipts[0]["aggregate"]["source_receipt_ids"]
        result = rolling_30d(receipts, END_DAY)
        self.assertEqual(result["measurement_status"], "blocked")
        self.assertEqual(result["reason"], "source_receipt_duplicate")
        self.assertIsNone(result["net_pnl_usd"])

    def test_invalid_net_or_missing_source_evidence_blocks(self):
        receipts = thirty_days()
        receipts[0]["aggregate"]["net_pnl_usd"] = "not-a-number"
        result = rolling_30d(receipts, END_DAY)
        self.assertEqual(result["measurement_status"], "blocked")
        self.assertEqual(result["reason"], "daily_net_pnl_invalid")
        self.assertIsNone(result["net_pnl_usd"])

        receipts = thirty_days()
        receipts[0]["aggregate"]["source_receipt_ids"] = []
        result = rolling_30d(receipts, END_DAY)
        self.assertEqual(result["measurement_status"], "blocked")
        self.assertEqual(result["reason"], "source_receipt_missing")
        self.assertIsNone(result["net_pnl_usd"])


if __name__ == "__main__":
    unittest.main()
