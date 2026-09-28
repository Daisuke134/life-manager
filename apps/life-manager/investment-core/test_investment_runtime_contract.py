import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class InvestmentRuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(
            (ROOT / "config/loop-registry.json").read_text(encoding="utf-8")
        )
        cls.catalog = json.loads(
            (ROOT / "apps/life-manager/config/product-loop-catalog.json")
            .read_text(encoding="utf-8")
        )

    def test_life_manager_owns_a_daily_cross_venue_receipt_job(self):
        job = self.registry["loops"]["investment-cross-venue-report"]
        self.assertEqual(job["entrypoint"], "apps/life-manager/investment-core/cross_venue_run.py")
        self.assertEqual(job["cadence"], {"start_interval_seconds": 86400})
        self.assertEqual(job["domain"], "financial")
        self.assertEqual(job["effect_class"], "message")
        self.assertEqual(job["admission_class"], "revenue")
        self.assertEqual(job["priority"], "revenue")
        self.assertEqual(job["state_root"], "~/.local/state/life-manager/investment-cross-venue")
        self.assertEqual(job["command"][:2], ["--state-dir", "~/.local/state/life-manager/investment-cross-venue"])
        self.assertIn("--alpaca-state-dir", job["command"])
        alpaca_index = job["command"].index("--alpaca-state-dir")
        self.assertEqual(job["command"][alpaca_index + 1],
                         "~/.local/state/life-manager/alpaca-investment-live")

    def test_investment_product_maps_the_daily_receipt_job(self):
        investment = next(loop for loop in self.catalog["loops"] if loop["id"] == "investment")
        self.assertIn("alpaca-investment-live", investment["job_ids"])
        self.assertIn("investment-cross-venue-report", investment["job_ids"])
        self.assertEqual(investment["recovery_classes"], ["external_effect_owner"])


if __name__ == "__main__":
    unittest.main()
