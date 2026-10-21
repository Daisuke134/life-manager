"""Permanent public aggregate metrics must preserve observed evidence limits."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "docs/research/public_aggregate/PHASE04_BIKESHARE_METRICS.json"


class Phase04PublicReceipt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = json.loads(METRICS.read_text(encoding="utf-8"))

    def test_verified_official_source_only_aggregate(self):
        src = self.m["source"]
        self.assertEqual(src["verified_against_official_archive"], "BYTE_IDENTICAL")
        self.assertEqual(src["file_bytes"], 57569)
        self.assertEqual(src["git_blob_sha1"],
                         "d39017f2f1ad2e70a4a854d17aada04d45608575")
        self.assertEqual(self.m["train"]["days"], 365)
        self.assertEqual(self.m["heldout"]["days"], 366)
        self.assertIn("39545601251", self.m["evidence_run"])

    def test_bootstrap_zero_crossing_is_not_claimed_significant(self):
        a = self.m["models"]["frequency"]["mae_daily_rentals"]
        b = self.m["models"]["season_only"]["mae_daily_rentals"]
        self.assertAlmostEqual(a - b, self.m["observed_mae_global_minus_season"])
        low, high = self.m["paired_week_block_bootstrap"]["confidence_interval_global_minus_season"]
        self.assertLess(low, 0)
        self.assertGreater(high, 0)
        self.assertTrue(self.m["paired_week_block_bootstrap"]["crosses_zero"])
        self.assertFalse(self.m["paired_week_block_bootstrap"]["causal_interval"])

    def test_two_new_temporal_contexts_are_not_human_benchmark(self):
        self.assertEqual(
            {z["name"]: z["days"] for z in self.m["heldout_environments"]},
            {"winter_2012": 91, "summer_2012": 94},
        )
        limits = self.m["limits"]
        self.assertEqual(limits["individual_person_records"], 0)
        self.assertEqual(limits["socsci210_studies_evaluated"], 0)
        self.assertFalse(limits["causal_social_fidelity_established"])
        self.assertFalse(limits["randomized_intervention_effects_estimated"])
        self.assertFalse(limits["real_welfare_benefit_established"])
        self.assertFalse(limits["unknown_person_behavior_validated"])


if __name__ == "__main__":
    unittest.main()
