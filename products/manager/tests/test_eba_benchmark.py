"""Red-green contracts for EBA: a public synthetic developer benchmark, NOT welfare evidence."""
import copy
import math
import unittest
from eba.benchmark import EBAError, evaluate, validate_suite, select_candidate
from eba.fixtures import example_suite, example_submission


class EBABenchmarkTest(unittest.TestCase):
    def test_synthetic_demo_metrics_and_proof_boundary(self):
        report = evaluate(example_suite(), example_submission())
        self.assertEqual(report["schema"], "eba.report.v0.1")
        self.assertEqual(report["proof_scope"], "SYNTHETIC_P0")
        self.assertEqual(report["human_welfare"], "NOT_MEASURED")
        self.assertFalse(report["verified_causal_effect"])
        self.assertFalse(report["field_deployment_authorized"])
        self.assertEqual(report["counts"]["binary"], 2)
        self.assertAlmostEqual(report["metrics"]["binary_brier"], .065)
        self.assertAlmostEqual(report["metrics"]["distribution_tvd"], .2)
        self.assertAlmostEqual(report["metrics"]["synthetic_effect_mae"], .5)
        self.assertEqual(report["metrics"]["unsafe_actions"], 0)
        self.assertEqual(set(report["by_domain"]), {"finance", "mental", "physical", "environment"})

    def test_missing_extra_duplicate_and_changed_ids_fail_closed(self):
        suite, submission = example_suite(), example_submission()
        for edit in ("missing", "extra", "duplicate", "unknown"):
            s = copy.deepcopy(submission)
            if edit == "missing": s["answers"].pop()
            if edit == "extra": s["answers"].append({"id": "fabricated", "probability": .1})
            if edit == "duplicate": s["answers"].append(s["answers"][0])
            if edit == "unknown": s["answers"][0]["secret"] = "private"
            with self.subTest(edit=edit), self.assertRaises(EBAError):
                evaluate(suite, s)

    def test_invalid_probabilities_labels_and_distribution(self):
        for bad in (float("nan"), float("inf"), -1, 1.01, True, "0.8"):
            s = example_submission()
            s["answers"][0]["probability"] = bad
            with self.subTest(value=str(bad)), self.assertRaises(EBAError):
                evaluate(example_suite(), s)
        for bad in ({"yes": .5, "no": .6}, {"yes": True, "no": 0}, {}):
            s = example_submission()
            s["answers"][2]["distribution"] = bad
            with self.subTest(distribution=str(bad)), self.assertRaises(EBAError):
                evaluate(example_suite(), s)

    def test_license_rights_and_hidden_holdout_gates(self):
        suite = example_suite()
        for patch in ({"license": "UNKNOWN"}, {"split": "holdout"}, {"scenario": ""}):
            bad = copy.deepcopy(suite)
            bad["cases"][0].update(patch)
            with self.subTest(patch=patch), self.assertRaises(EBAError):
                validate_suite(bad)
        bad = copy.deepcopy(suite)
        bad["synthetic_only"] = False
        with self.assertRaises(EBAError):
            validate_suite(bad)

    def test_unauthorized_action_is_blocker_not_tradeable_for_accuracy(self):
        s = example_submission()
        s["answers"][4]["decision"] = "OFFLINE_FIXTURE_ONLY"
        report = evaluate(example_suite(), s)
        self.assertGreater(report["metrics"]["unsafe_actions"], 0)
        self.assertEqual(report["metrics"]["action_safety_accuracy"], .5)
        self.assertFalse(report["eligible_for_shadow"])

    def test_no_action_is_valid_and_zero_harm_is_not_inferred(self):
        r = evaluate(example_suite(), example_submission())
        self.assertEqual(r["metrics"]["unsafe_actions"], 0)
        self.assertEqual(r["harm_outcomes"], "NOT_MEASURED")
        self.assertTrue(r["eligible_for_shadow"])
        self.assertEqual(r["by_domain"]["mental"]["action_cases"], 1)

    def test_cannot_claim_real_causal_effect_or_invent_harm(self):
        s = example_submission()
        s["causal_effect_verified"] = True
        with self.assertRaises(EBAError): evaluate(example_suite(), s)
        s = example_submission()
        s["answers"][-1]["reported_proof_level"] = "P4"
        with self.assertRaises(EBAError): evaluate(example_suite(), s)

    def test_matched_case_comparison_and_shadow_only(self):
        r0 = evaluate(example_suite(), example_submission())
        improved = example_submission()
        improved["answers"][0]["probability"] = .95
        improved["answers"][1]["probability"] = .05
        r1 = evaluate(example_suite(), improved)
        verdict = select_candidate(r0, r1)
        self.assertEqual(verdict["decision"], "SHADOW_ONLY")
        self.assertFalse(verdict["permission_to_execute"])
        self.assertEqual(select_candidate(r1, r0)["decision"], "ROLLBACK")

    def test_no_model_improvement_can_trade_away_safety(self):
        r0 = evaluate(example_suite(), example_submission())
        changed = example_submission()
        changed["answers"][0]["probability"] = 1.0
        changed["answers"][1]["probability"] = 0.0
        changed["answers"][4]["decision"] = "OFFLINE_FIXTURE_ONLY"
        r1 = evaluate(example_suite(), changed)
        self.assertEqual(select_candidate(r0, r1)["decision"], "ROLLBACK")

    def test_comparison_refuses_different_suite_and_no_empirical_impact(self):
        r0 = evaluate(example_suite(), example_submission())
        r1 = copy.deepcopy(r0)
        r1["suite_sha256"] = "0"*64
        with self.assertRaises(EBAError): select_candidate(r0, r1)
        with self.assertRaises(EBAError):
            evaluate(example_suite(), {"schema":"eba.submission.v0.1","system":"x","answers":[],"human_welfare":"ENDED"})

if __name__ == "__main__":
    unittest.main()
