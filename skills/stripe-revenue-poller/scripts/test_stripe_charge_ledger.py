"""Tests for stripe_charge_ledger: no network, fake recorded Stripe charge objects only."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import stripe_charge_ledger as m  # noqa: E402

CHARGE_1 = {
    "id": "ch_1AAA",
    "object": "charge",
    "created": 1758931200,  # 2025-09-27T00:00:00Z
    "amount": 300,
    "currency": "usd",
    "amount_refunded": 0,
    "status": "succeeded",
    "paid": True,
    "refunded": False,
    "description": "sutra-candle",
    "metadata": {"product_id": "sutra-candle"},
    "livemode": True,
}

CHARGE_2_REFUNDED = {
    "id": "ch_2BBB",
    "object": "charge",
    "created": 1758931300,
    "amount": 450,
    "currency": "jpy",
    "amount_refunded": 450,
    "status": "succeeded",
    "paid": True,
    "refunded": True,
    "description": None,
    "statement_descriptor": "SUTRA",
    "metadata": {},
    "livemode": True,
}


class AppendTest(unittest.TestCase):
    def test_new_charge_appended_once(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = Path(d) / "stripe-charges.jsonl"
            n = m.append(ledger, [CHARGE_1])
            self.assertEqual(n, 1)
            rows = [json.loads(l) for l in ledger.read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["id"], "ch_1AAA")
            self.assertEqual(rows[0]["created"], "2025-09-27T00:00:00Z")
            self.assertEqual(rows[0]["amount"], 300)
            self.assertEqual(rows[0]["currency"], "usd")
            self.assertEqual(rows[0]["product_id"], "sutra-candle")
            self.assertEqual(oct(ledger.stat().st_mode)[-3:], "600")

    def test_duplicate_id_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = Path(d) / "stripe-charges.jsonl"
            m.append(ledger, [CHARGE_1])
            n = m.append(ledger, [CHARGE_1])  # same id fetched again by the poller
            self.assertEqual(n, 0)
            rows = ledger.read_text().splitlines()
            self.assertEqual(len(rows), 1)

    def test_refund_fields_captured(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = Path(d) / "stripe-charges.jsonl"
            m.append(ledger, [CHARGE_2_REFUNDED])
            row = json.loads(ledger.read_text().splitlines()[0])
            self.assertTrue(row["refunded"])
            self.assertEqual(row["amount_refunded"], 450)
            self.assertEqual(row["description"], "SUTRA")
            self.assertIsNone(row["product_id"])


class SummarizeTest(unittest.TestCase):
    def test_totals_by_currency_and_product(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = Path(d) / "stripe-charges.jsonl"
            m.append(ledger, [CHARGE_1, CHARGE_2_REFUNDED])
            # last 30 days from now includes only charges within window; use a huge window
            # so the fixed 2025 fixture timestamps are always "recent" relative to test run time.
            since_days = 3650
            result = m.summarize(ledger, since_days)
            self.assertEqual(result["by_currency"]["usd"], {"amount": 300, "count": 1})
            # refunded charge nets to 0 (450 - 450)
            self.assertEqual(result["by_currency"]["jpy"], {"amount": 0, "count": 1})
            self.assertEqual(result["by_product"]["sutra-candle"]["usd"], {"amount": 300, "count": 1})
            self.assertEqual(result["by_product"]["unknown"]["jpy"], {"amount": 0, "count": 1})

    def test_since_window_excludes_old_rows(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = Path(d) / "stripe-charges.jsonl"
            m.append(ledger, [CHARGE_1])
            result = m.summarize(ledger, since_days=0)
            self.assertEqual(result["by_currency"], {})


if __name__ == "__main__":
    unittest.main()
