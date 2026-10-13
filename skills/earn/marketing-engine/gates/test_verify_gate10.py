import json
import unittest
from pathlib import Path

from product_router import load_registry
from verify_gate10 import verify_gate10


ENGINE = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAFE_PLANS_FIXTURE = FIXTURES / "gate10-safe-plans.contract-test-fixture.jsonl"
QUARANTINE_FIXTURE = FIXTURES / "gate10-quarantine.contract-test-fixture.json"
CORE_GATE10_PRODUCTS = {"anicca-ios", "honne-ai", "ebook-en", "ebook-ja"}
SAFE_PLAN_IDENTITIES = {
    ("ebook-en", "tiktok.monk_anicca", "hook.tiktok.7609309883912965390.001",
     "tactic.faceless-visual-refresh-captions.v1", "omniavatar-monk"),
    ("ebook-ja", "tiktok.obou_anicca", "hook.tiktok.7468922143619812626.001",
     "tactic.faceless-visual-refresh-captions.v1", "watercolor-monk"),
}
SAFE_EXPERIMENT_IDS = [
    "experiment.7481b64f311f43cd6ff13db3",
    "experiment.de65c60f9e94a33eeef67d67",
]


class Gate10VerifierTest(unittest.TestCase):
    def test_gate10_core_routes_survive_additive_marketplace_product(self):
        registry = load_registry(ENGINE)
        self.assertLessEqual(CORE_GATE10_PRODUCTS, set(registry.products))
        self.assertIn("hook-lab", registry.products)

        result = verify_gate10(
            ENGINE,
            plans_path=SAFE_PLANS_FIXTURE,
            quarantine_path=QUARANTINE_FIXTURE,
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["counts"]["safe_plans"], 2)
        self.assertEqual(result["plans_by_product"], {"ebook-en": 1, "ebook-ja": 1})
        self.assertEqual(result["safe_experiment_ids"], SAFE_EXPERIMENT_IDS)
        self.assertEqual(result["legacy_production_references"], 0)
        self.assertEqual(result["enabled_legacy_publishers"], 0)
        self.assertEqual(result["app_candidate_counts"], {"anicca-ios": 0, "honne-ai": 0})

        plans = [json.loads(line) for line in SAFE_PLANS_FIXTURE.read_text().splitlines()]
        identities = {
            (row["product_id"], row["account_id"], row["hook_id"],
             row["tactic_id"], row["renderer_id"])
            for row in plans
        }
        self.assertEqual(identities, SAFE_PLAN_IDENTITIES)

    def test_missing_live_plan_evidence_fails_closed(self):
        with self.assertRaises(FileNotFoundError):
            verify_gate10(ENGINE)

    def test_test_fixture_does_not_replace_missing_live_quarantine_evidence(self):
        with self.assertRaises(FileNotFoundError):
            verify_gate10(ENGINE, plans_path=SAFE_PLANS_FIXTURE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
