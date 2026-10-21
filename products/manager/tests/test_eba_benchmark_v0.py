"""Red/green contracts for EBA v0: all data synthetic, no human-benefit claims."""
import copy
import json
from pathlib import Path
import unittest

from manager_core.eba_benchmark import validate_suite, score_suite, paired_loss_interval, promotion_verdict

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "benchmarks/eba_v0/fixtures.json"
PREDICTIONS = ROOT / "benchmarks/eba_v0/predictions.json"

class EBABenchmarkTests(unittest.TestCase):
    def load(self):
        return json.loads(FIXTURE.read_text()), json.loads(PREDICTIONS.read_text())

    def test_01_public_synthetic_cases_and_group_isolated_holdout(self):
        cases, predictions = self.load()
        summary = validate_suite(cases)
        self.assertEqual(summary["license_scope"], "ORIGINAL_SYNTHETIC_FIXTURES_ONLY")
        self.assertEqual(summary["evidence_level"], "P0")
        self.assertGreaterEqual(summary["train_cases"], 2)
        self.assertGreaterEqual(summary["test_cases"], 4)
        self.assertTrue({"finance", "mental", "physical", "environment"} <= set(summary["domains"]))
        self.assertEqual(len(predictions), summary["test_cases"])

    def test_02_no_alias_or_group_leakage(self):
        cases, _ = self.load()
        other = copy.deepcopy(cases)
        other[0]["group_id"] = next(x["group_id"] for x in cases if x["split"] == "test")
        with self.assertRaisesRegex(ValueError, "leakage"):
            validate_suite(other)

    def test_03_no_future_evidence_in_forecast(self):
        cases, _ = self.load()
        other = copy.deepcopy(cases)
        other[0]["source_published_at"] = "2031-01-01"
        with self.assertRaisesRegex(ValueError, "future"):
            validate_suite(other)

    def test_04_outcomes_must_follow_forecast_cutoff(self):
        cases, _ = self.load()
        other = copy.deepcopy(cases)
        other[0]["outcome_observed_at"] = "2024-01-01"
        with self.assertRaisesRegex(ValueError, "outcome"):
            validate_suite(other)

    def test_05_scorecard_splits_prediction_causality_actions_welfare(self):
        cases, predictions = self.load()
        r = score_suite(cases, predictions)
        self.assertEqual(r["benchmark"], "EBA-v0")
        self.assertEqual(r["evidence_level"], "P0")
        self.assertEqual(r["human_welfare"], "NOT_MEASURED")
        self.assertFalse(r["general_live_effect_authorized"])
        self.assertEqual(r["test_n"], 4)
        self.assertTrue({"finance", "mental", "physical", "environment"} <= set(r["domains"]))
        for key in ("tvd_mean","brier_mean","synthetic_causal_mae","synthetic_regret_mean","unsafe_actions","abstentions"):
            self.assertIn(key, r)
        self.assertNotIn("ended_suffering", r)
        self.assertNotIn("universal_score", r)

    def test_06_forged_approval_and_unauthorized_intervention_fail(self):
        cases, predictions = self.load()
        target = next(c["case_id"] for c in cases if c["split"] == "test")
        altered = copy.deepcopy(predictions)
        altered[target]["action"] = "PAY_OUT"
        result = score_suite(cases, altered)
        self.assertGreater(result["unsafe_actions"], 0)
        self.assertFalse(result["eligible_for_offline_candidate"])

    def test_07_missing_prediction_is_unknown_never_zero(self):
        cases, predictions = self.load()
        altered = copy.deepcopy(predictions)
        altered.pop(next(iter(altered)))
        with self.assertRaisesRegex(ValueError, "missing"):
            score_suite(cases, altered)

    def test_08_bad_distributions_and_nonfinite_or_boolean_scores_rejected(self):
        cases, predictions = self.load()
        for value in (1.2, float("nan"), True, "0.9"):
            altered = copy.deepcopy(predictions)
            altered[next(iter(altered))]["predicted_distribution"]["yes"] = value
            with self.subTest(value=str(value)), self.assertRaises(ValueError):
                score_suite(cases, altered)

    def test_09_no_real_world_evidence_promotion(self):
        cases, predictions = self.load()
        r = score_suite(cases, predictions)
        self.assertEqual(promotion_verdict(r)["status"], "NOT_ELIGIBLE_FOR_FIELD_EFFECT")
        self.assertFalse(promotion_verdict(r)["can_claim_causal_welfare"])

    def test_10_paired_bootstrap_requires_n_and_defends_regressions(self):
        with self.assertRaises(ValueError):
            paired_loss_interval([0.2], [0.1])
        ci = paired_loss_interval([0.4]*12, [0.1]*12, seed=2026, reps=500)
        self.assertGreater(ci["improvement_lower"], 0)
        self.assertGreater(ci["improvement_upper"], 0)
        self.assertLess(ci["improvement_upper"], 1)
        loser = paired_loss_interval([0.1]*12, [0.4]*12, seed=2026, reps=500)
        self.assertLess(loser["improvement_upper"], 0)

    def test_11_readonly_and_no_personal_information(self):
        cases, _ = self.load()
        for c in cases:
            self.assertEqual(c["rights"], "SYNTHETIC_ORIGINAL")
            self.assertEqual(c["data_classification"], "FICTIONAL")
            self.assertNotIn("email", json.dumps(c).lower())
            self.assertNotIn("phone", json.dumps(c).lower())
            self.assertIn("NO_ACTION", c["allowed_actions"])

if __name__ == "__main__":
    unittest.main()
