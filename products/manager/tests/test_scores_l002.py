"""L002: error metrics for synthetic forecasts; these are not causal estimates."""
import unittest
from pathlib import Path
import subprocess
import sys

from manager_core.evaluation import brier_score, total_variation


class TotalVariationL002Tests(unittest.TestCase):
    def test_simulated_purchase_distribution_has_tvd_point_two(self):
        prediction = {'buy': 0.7, 'no_buy': 0.3}
        observation = {'buy': 0.5, 'no_buy': 0.5}
        self.assertAlmostEqual(total_variation(prediction, observation), 0.2)

    def test_symmetric_and_counts_missing_categories(self):
        p = {'a': 0.6, 'b': 0.4}
        q = {'a': 0.6, 'c': 0.4}
        self.assertAlmostEqual(total_variation(p, q), 0.4)
        self.assertAlmostEqual(total_variation(q, p), 0.4)

    def test_extreme_values_tvd_zero_and_one(self):
        self.assertEqual(total_variation({'a': 1.0}, {'a': 1.0}), 0.0)
        self.assertEqual(total_variation({'a': 1.0}, {'b': 1.0}), 1.0)

    def test_rejects_boolean_probability_and_wrong_type(self):
        for bad in (True, '0.7', None, float('nan'), float('inf'), -0.3):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    total_variation({'buy': bad, 'no_buy': 0.3}, {'buy': 0.5, 'no_buy': 0.5})

    def test_boolean_must_not_be_interpreted_as_certain_probability(self):
        with self.assertRaises(ValueError):
            total_variation({'buy': True, 'no_buy': 0.0}, {'buy': 1.0})

    def test_rejects_missing_probability_mass(self):
        for distribution in ({'a': 0.5, 'b': 0.2}, {'a': 0.5, 'b': 0.7}, {}):
            with self.subTest(distribution=distribution):
                with self.assertRaises(ValueError):
                    total_variation(distribution, {'a': 1.0})


class BrierL002Tests(unittest.TestCase):
    def test_score_demo_prints_labeled_synthetic_values(self):
        result = subprocess.run(
            [sys.executable, '-m', 'examples.02_scores'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True,
            text=True, check=True)
        self.assertIn('SYNTHETIC', result.stdout)
        self.assertIn('TVD = 0.20', result.stdout)
        self.assertIn('Brier aligned = 0.01', result.stdout)
        self.assertIn('Brier reversed = 0.81', result.stdout)
        self.assertIn('NOT a causal effect', result.stdout)

    def test_brier_perfect_inverted_and_coinflip(self):
        true = [1, 0, 1, 0]
        self.assertAlmostEqual(brier_score([1.0, 0.0, 1.0, 0.0], true), 0.0)
        self.assertAlmostEqual(brier_score([0.0, 1.0, 0.0, 1.0], true), 1.0)
        self.assertAlmostEqual(brier_score([0.5] * 4, true), 0.25)

    def test_individual_forecasts_matter_even_if_group_share_same(self):
        confident_predictions = [0.9, 0.1]
        self.assertAlmostEqual(brier_score(confident_predictions, [1, 0]), 0.01)
        self.assertAlmostEqual(brier_score(confident_predictions, [0, 1]), 0.81)
        # Both groups have 50% observed positive share; TVD cannot capture
        # which individual received which prediction.
        self.assertAlmostEqual(total_variation({'yes': 0.5, 'no': 0.5}, {'yes': 0.5, 'no': 0.5}), 0)

    def test_matches_authoritative_binary_brier_example(self):
        # scikit-learn's published brier_score_loss example.
        self.assertAlmostEqual(brier_score([0.1, 0.9, 0.8, 0.3], [0, 1, 1, 0]), 0.0375)

    def test_rejects_invalid_forecast_probability_values(self):
        for bad in (True, '0.8', None, float('nan'), float('inf'), -0.1, 1.1):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    brier_score([bad, 0.2], [1, 0])

    def test_rejects_invalid_outcome_values(self):
        for bad in (True, False, 0.5, 2, '1', None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    brier_score([0.8, 0.2], [bad, 0])

    def test_rejects_empty_or_unequal_length_pairs(self):
        for predictions, outcomes in (([], []), ([0.8], []), ([], [1]), ([0.8], [1, 0])):
            with self.subTest(predictions=predictions, outcomes=outcomes):
                with self.assertRaises(ValueError):
                    brier_score(predictions, outcomes)


if __name__ == '__main__':
    unittest.main()