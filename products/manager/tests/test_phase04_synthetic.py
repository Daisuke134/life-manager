"""Phase 04 engineering checks use only constructed, nonhuman observations."""
import json
import unittest

from manager_core.phase04_synthetic import (
    binary_baselines, compare_on_unseen_studies,
    constructed_causal_gap, synthetic_phase04_report, wasserstein_ordinal
)


class Phase04SyntheticContractTest(unittest.TestCase):
    def test_majority_and_frequency_baselines_are_trained_only_on_train(self):
        model = binary_baselines([1, 1, 0, 0])
        self.assertEqual(model["frequency"], 0.5)
        self.assertEqual(model["majority"], 1)
        self.assertEqual(binary_baselines([0, 0, 1])["majority"], 0)
        with self.assertRaises(ValueError):
            binary_baselines([True, 0])

    def test_unseen_study_overlap_is_hard_failure(self):
        observations = [
            {"study_id": "A", "scenario": "novel-A", "outcome": 0},
            {"study_id": "B", "scenario": "novel-B", "outcome": 1},
        ]
        with self.assertRaises(ValueError):
            compare_on_unseen_studies(["A"], ["A", "B"], [1, 0], observations)
        with self.assertRaises(ValueError):
            compare_on_unseen_studies(["train"], ["A", "B"], [1, 0],
                                      observations + [{"study_id": "train", "scenario": "oops", "outcome": 1}])

    def test_accuracy_brier_tvd_are_distinct_and_reject_drift(self):
        observations = [
            *[{"study_id": "testA", "scenario": "new-A", "outcome": x}
              for x in (1, 0, 0, 0)],
            *[{"study_id": "testB", "scenario": "new-B", "outcome": x}
              for x in (1, 1, 1, 0)],
        ]
        report = compare_on_unseen_studies(["train"], ["testA", "testB"],
                                           [1, 1, 0, 0], observations,
                                           max_scenario_tvd=0.2, min_scenario_n=4)
        self.assertAlmostEqual(report["baselines"]["frequency"]["accuracy"], 0.5)
        self.assertAlmostEqual(report["baselines"]["frequency"]["brier"], 0.25)
        self.assertAlmostEqual(report["baselines"]["frequency"]["overall_tvd"], 0)
        self.assertAlmostEqual(report["baselines"]["majority"]["overall_tvd"], 0.5)
        self.assertEqual(len(report["novel_scenarios"]), 2)
        self.assertTrue(all(x["decision"] == "ABSTAIN" for x in report["novel_scenarios"]))
        self.assertEqual(report["total_heldout_records"], 8)
        self.assertFalse(report["real_study_evaluated"])
        self.assertEqual(report["basis"], "SYNTHETIC_ONLY")

    def test_realized_outcomes_are_binary_and_no_identifiers(self):
        with self.assertRaises(ValueError):
            compare_on_unseen_studies(["train"], ["test"], [0, 1],
                                      [{"study_id": "test", "scenario": "novel", "outcome": None}])
        report = synthetic_phase04_report()
        as_text = json.dumps(report, sort_keys=True)
        self.assertNotIn("participant", as_text.lower())
        self.assertNotIn("SocSci210_human_benchmark_pass", as_text)
        self.assertEqual(report["real_beneficiaries"], 0)

    def test_descriptive_fidelity_does_not_prove_intervention_response(self):
        report = constructed_causal_gap()
        self.assertAlmostEqual(report["marginal_tvd"], 0)
        self.assertAlmostEqual(report["known_treatment_effect_in_constructed_world"], 0.4)
        self.assertAlmostEqual(report["treatment_blind_predicted_effect"], 0)
        self.assertAlmostEqual(report["effect_error"], 0.4)
        self.assertFalse(report["real_world_causal_validation"])

    def test_ordinal_wasserstein_differs_from_unordered_tvd(self):
        self.assertAlmostEqual(
            wasserstein_ordinal([0.5, 0.5, 0], [0, 0.5, 0.5],
                                [0, 0.5, 1]), 0.5
        )
        self.assertAlmostEqual(
            wasserstein_ordinal([0, 1], [0, 1], [0, 1]), 0
        )
        with self.assertRaises(ValueError):
            wasserstein_ordinal([0.5, 0.5], [0.5, 0.5], [1, 0])

if __name__ == "__main__":
    unittest.main()
