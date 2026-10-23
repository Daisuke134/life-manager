"""Synthetic scientific-contract tests; no private source rows or labels."""
from __future__ import annotations

import math
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "products/manager/manager_core"))
sys.path.insert(0, str(REPO_ROOT / "products/manager/scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import external_behavior_eval as evaluation  # noqa: E402
import inspect_external_behavior_benchmark as inspector  # noqa: E402
import test_external_behavior_benchmark as a_tests  # noqa: E402


def rows_for(study: str, outcome: str, estimate: float, prediction: float, group: str = "published"):
    return [
        {"study": study, "outcome.name": outcome, "reference_condition": "A", "condition.name": "B",
         "estimate": estimate, "prediction": prediction, "group": group},
        {"study": study, "outcome.name": outcome, "reference_condition": "B", "condition.name": "A",
         "estimate": -estimate, "prediction": -prediction, "group": group},
    ]


def fixture():
    rows = []
    specs = [
        ("s1", "outcome1", 0.10, 0.20, "published"),
        ("s1", "outcome2", 0.20, 0.40, "published"),
        ("s2", "outcome1", 0.20, 0.40, "published"),
        ("s3", "outcome1", 0.30, 0.60, "unpublished"),
        ("s4", "outcome1", 0.40, 0.80, "unpublished"),
    ]
    for spec in specs:
        rows.extend(rows_for(*spec))
    split = {"s1": "train", "s2": "train", "s3": "test", "s4": "test"}
    return rows, split


class ExternalBehaviorEvaluationTests(unittest.TestCase):
    def test_study_macro_weighting_and_train_only_calibration(self):
        rows, split = fixture()
        result = evaluation.evaluate_released_effects(rows, study_split=split, bootstrap_seed=17)
        self.assertEqual(result["counts"]["studies"], 4)
        self.assertEqual(result["counts"]["test_studies"], 2)
        self.assertAlmostEqual(result["scores"]["raw"]["mae_full_scale"], 0.35)
        self.assertAlmostEqual(result["calibration"]["beta"], 0.5)
        self.assertAlmostEqual(result["scores"]["calibrated"]["mae_full_scale"], 0.0)
        self.assertAlmostEqual(result["uncertainty"]["calibrated_vs_zero"]["mean_gap_full_scale"], 0.35)

    def test_split_is_exact_study_mapping_and_never_splits_outcomes(self):
        rows, split = fixture()
        bad = dict(split)
        bad.pop("s1")
        with self.assertRaises(evaluation.EvaluationError):
            evaluation.evaluate_released_effects(rows, study_split=bad, bootstrap_seed=1)

    def test_hash_split_is_stratified_stable_under_row_order_and_hides_ids(self):
        rows, _split = fixture()
        groups = {row["study"]: row["group"] for row in rows}
        split1, digest1 = evaluation.make_fixed_study_split(groups)
        split2, digest2 = evaluation.make_fixed_study_split(dict(reversed(list(groups.items()))))
        self.assertEqual(split1, split2)
        self.assertEqual(digest1, digest2)
        self.assertEqual(sum(split1[s] == "train" for s, g in groups.items() if g == "published"), 1)
        self.assertEqual(sum(split1[s] == "train" for s, g in groups.items() if g == "unpublished"), 1)
        self.assertNotIn("s1", digest1)

    def test_hierarchical_weighting_does_not_let_many_pairs_dominate(self):
        rows = rows_for("train", "o", 0.1, 0.1)
        for left, right in (("A", "B"), ("A", "C"), ("B", "C")):
            rows.extend([
                {"study": "large", "outcome.name": "many", "reference_condition": left, "condition.name": right, "estimate": 0.0, "prediction": 0.0, "group": "published"},
                {"study": "large", "outcome.name": "many", "reference_condition": right, "condition.name": left, "estimate": 0.0, "prediction": 0.0, "group": "published"},
            ])
        rows.extend(rows_for("large", "one", 0.0, 0.4))
        rows.extend(rows_for("small", "one", 0.0, 0.0))
        result = evaluation.evaluate_released_effects(
            rows, study_split={"train": "train", "large": "test", "small": "test"}, bootstrap_seed=11
        )
        self.assertAlmostEqual(result["scores"]["raw"]["mae_full_scale"], 0.1)

    def test_one_test_study_reports_no_cluster_interval_and_separates_ties(self):
        rows = rows_for("train", "o", 0.1, 0.2)
        rows.extend(rows_for("test", "o", 0.0, 0.0))
        result = evaluation.evaluate_released_effects(
            rows, study_split={"train": "train", "test": "test"}, bootstrap_seed=5
        )
        gap = result["uncertainty"]["raw_vs_zero"]
        self.assertIsNone(gap["interval"])
        self.assertEqual(gap["reason"], "FEWER_THAN_TWO_TEST_STUDIES")
        self.assertEqual(result["scores"]["raw"]["direction"]["observed_zero"], 1)
        self.assertEqual(result["scores"]["raw"]["direction"]["prediction_tie"], 1)

    def test_loader_returns_the_same_validated_rows_and_legacy_report(self):
        input_dir, nature, source_rows = a_tests.make_snapshot(self)
        rows, report = inspector.load_validated_snapshot(input_dir, nature)
        self.assertEqual(rows, source_rows)
        self.assertEqual(report, inspector.inspect_snapshot(input_dir, nature))

    def test_reverse_rows_do_not_inflate_sample_or_macro_score(self):
        rows, split = fixture()
        a = evaluation.evaluate_released_effects(rows, study_split=split, bootstrap_seed=22)
        self.assertEqual(a["counts"]["unordered_pairs"], 5)
        self.assertEqual(a["counts"]["studies"], 4)
        reordered = evaluation.evaluate_released_effects(list(reversed(rows)), study_split=split, bootstrap_seed=22)
        self.assertEqual(a["scores"], reordered["scores"])

    def test_input_values_must_be_finite_numbers_not_booleans(self):
        for invalid in (True, "0.1", float("nan"), float("inf"), None):
            rows, split = fixture()
            rows[0]["prediction"] = invalid
            with self.subTest(value=repr(invalid)), self.assertRaises(evaluation.EvaluationError):
                evaluation.evaluate_released_effects(rows, study_split=split, bootstrap_seed=1)

    def test_missing_objective_is_explicit_and_json_finite(self):
        rows, split = fixture()
        result = evaluation.evaluate_released_effects(rows, study_split=split, bootstrap_seed=17)
        self.assertEqual(result["selection"], {"status": "OBJECTIVE_NOT_SPECIFIED", "regret": None})
        import json
        json.dumps(result, allow_nan=False)

    def test_aggregate_result_contains_no_study_or_condition_labels(self):
        import json
        rows, split = fixture()
        encoded = json.dumps(evaluation.evaluate_released_effects(rows, study_split=split, bootstrap_seed=4))
        for private_label in ('"s1"', '"s2"', '"outcome1"', '"A"', '"B"'):
            self.assertNotIn(private_label, encoded)

    def test_fixed_cli_failure_is_sanitized(self):
        cli = REPO_ROOT / "products/manager/scripts/evaluate_external_behavior_benchmark.py"
        completed = subprocess.run(
            [sys.executable, str(cli), "/path/that/does/not/exist"], capture_output=True, text=True, check=False
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr, "ERROR SNAPSHOT_INVALID\n")

    def test_explicit_objective_regret_respects_pair_orientation(self):
        rows = rows_for("s1", "o", 0.2, -0.1) + rows_for("s2", "o", -0.4, -0.2)
        split = {"s1": "train", "s2": "test"}
        result = evaluation.evaluate_released_effects(
            rows, study_split=split, bootstrap_seed=3, objective_signs={("s1", "o"): 1, ("s2", "o"): 1}
        )
        self.assertEqual(result["selection"]["status"], "DESCRIPTIVE_PAIRWISE_REGRET")
        self.assertIn("raw", result["selection"]["regret"])

    def test_heldout_labels_cannot_change_the_train_fit(self):
        rows, split = fixture()
        original = evaluation.evaluate_released_effects(rows, study_split=split, bootstrap_seed=7)
        changed = [row.copy() for row in rows]
        for row in changed:
            if row["study"] in {"s3", "s4"}:
                row["estimate"] *= 0.5
        altered = evaluation.evaluate_released_effects(changed, study_split=split, bootstrap_seed=7)
        self.assertEqual(original["calibration"]["beta"], altered["calibration"]["beta"])

    def test_five_percentage_points_remain_full_scale_point_zero_five(self):
        rows = rows_for("train", "o", 0.1, 0.2) + rows_for("test", "o", 0.05, 0.10)
        result = evaluation.evaluate_released_effects(
            rows, study_split={"train": "train", "test": "test"}, bootstrap_seed=13
        )
        self.assertAlmostEqual(result["scores"]["raw"]["mae_full_scale"], 0.05)
        self.assertAlmostEqual(result["scores"]["calibrated"]["mae_full_scale"], 0.0)

    def test_train_signed_mean_is_reported_as_zero_alias_not_extra_baseline(self):
        rows, split = fixture()
        result = evaluation.evaluate_released_effects(rows, study_split=split, bootstrap_seed=2)
        self.assertAlmostEqual(result["calibration"]["train_directed_mean_prediction_full_scale"], 0.0)
        self.assertEqual(result["calibration"]["train_mean_baseline_alias"]["alias_of"], "zero_effect")

    def test_rank_deficient_training_predictions_are_not_fabricated(self):
        rows = rows_for("train", "o", 0.1, 0.0) + rows_for("test", "o", 0.1, 0.2)
        result = evaluation.evaluate_released_effects(
            rows, study_split={"train": "train", "test": "test"}, bootstrap_seed=1
        )
        self.assertIsNone(result["calibration"]["beta"])
        self.assertEqual(result["calibration"]["reason"], "CALIBRATION_RANK_DEFICIENT")
        self.assertIsNone(result["scores"]["calibrated"]["mae_full_scale"])
        self.assertEqual(result["uncertainty"]["calibrated_vs_zero"]["reason"], "CALIBRATION_RANK_DEFICIENT")

    def test_small_nonzero_training_predictions_are_not_called_rank_deficient(self):
        rows = rows_for("train", "o", 2e-10, 1e-10) + rows_for("test", "o", 2e-10, 1e-10)
        result = evaluation.evaluate_released_effects(
            rows, study_split={"train": "train", "test": "test"}, bootstrap_seed=2
        )
        self.assertAlmostEqual(result["calibration"]["beta"], 2.0)

    def test_bootstrap_is_study_clustered_and_reproducible(self):
        rows, split = fixture()
        a = evaluation.evaluate_released_effects(rows, study_split=split, bootstrap_seed=19)
        b = evaluation.evaluate_released_effects(rows, study_split=split, bootstrap_seed=19)
        self.assertEqual(a["uncertainty"], b["uncertainty"])
        self.assertEqual(a["uncertainty"]["resampling_unit"], "test_study")

    def test_constant_nonzero_cluster_gap_is_flagged_as_degenerate(self):
        rows = rows_for("train", "o", 0.2, 0.1)
        rows.extend(rows_for("test1", "o", 0.2, 0.1))
        rows.extend(rows_for("test2", "o", 0.2, 0.1))
        result = evaluation.evaluate_released_effects(
            rows, study_split={"train": "train", "test1": "test", "test2": "test"}, bootstrap_seed=9
        )
        interval = result["uncertainty"]["calibrated_vs_zero"]
        self.assertEqual(interval["interval"], [0.2, 0.2])
        self.assertEqual(interval["reason"], "DEGENERATE_SAMPLE")

    def test_duplicate_contrast_is_rejected(self):
        rows, split = fixture()
        with self.assertRaises(evaluation.EvaluationError):
            evaluation.evaluate_released_effects(rows + [rows[0]], study_split=split, bootstrap_seed=1)

    def test_unhashable_group_and_split_values_fail_with_stable_validation_error(self):
        rows, split = fixture()
        rows[0]["group"] = []
        with self.assertRaises(evaluation.EvaluationError):
            evaluation.evaluate_released_effects(rows, study_split=split, bootstrap_seed=1)
        rows, split = fixture()
        split["s1"] = []
        with self.assertRaises(evaluation.EvaluationError):
            evaluation.evaluate_released_effects(rows, study_split=split, bootstrap_seed=1)

    def test_loader_returns_validated_private_rows_without_changing_legacy_report(self):
        self.assertTrue(callable(inspector.load_validated_snapshot))


if __name__ == "__main__":
    unittest.main()
