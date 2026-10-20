"""L001: a toy joint distribution teaches conditional probability, not causality."""
import copy
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / 'examples/01_probability.py'
spec = importlib.util.spec_from_file_location('manager_l001_probability', FILE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    return {
        'morning': {'walk': 0.18, 'rest': 0.12},
        'evening': {'walk': 0.14, 'rest': 0.56},
    }


class ConditionalProbabilityTest(unittest.TestCase):
    def test_joint_distribution_sums_to_one(self):
        self.assertIsNone(module.validate_joint_distribution(fixture()))

    def test_conditional_probability_is_joint_divided_by_context(self):
        self.assertAlmostEqual(module.conditional_probability(fixture(), 'morning', 'walk'), 0.60)
        self.assertAlmostEqual(module.conditional_probability(fixture(), 'evening', 'walk'), 0.20)

    def test_marginal_probability_aggregates_contexts(self):
        self.assertAlmostEqual(module.marginal_probability(fixture(), 'walk'), 0.32)

    def test_absent_outcome_is_zero_probability_but_unknown_context_fails(self):
        self.assertEqual(module.conditional_probability(fixture(), 'morning', 'sleep'), 0)
        with self.assertRaisesRegex(ValueError, 'unknown context'):
            module.conditional_probability(fixture(), 'night', 'walk')

    def test_zero_marginal_context_does_not_create_nan(self):
        table = {'morning': {'walk': 0.0}, 'evening': {'walk': 1.0}}
        with self.assertRaisesRegex(ValueError, 'zero'): module.conditional_probability(table, 'morning', 'walk')

    def test_rejects_unnormalized_probability_mass(self):
        table = fixture(); table['evening']['rest'] = 0.66
        with self.assertRaisesRegex(ValueError, 'sum to 1'):
            module.validate_joint_distribution(table)

    def test_rejects_invalid_numbers_and_illformed_tables(self):
        for invalid in (-0.1, True, '0.18', float('nan'), float('inf')):
            with self.subTest(invalid=invalid):
                table = fixture(); table['morning']['walk'] = invalid
                with self.assertRaises(ValueError): module.validate_joint_distribution(table)
        for bad in ({}, {'morning': {}}, {'morning': {'walk': 1}, 'evening': None}):
            with self.assertRaises(ValueError): module.validate_joint_distribution(bad)

    def test_does_not_mutate_data(self):
        table=fixture(); before=copy.deepcopy(table)
        module.conditional_probability(table, 'morning', 'walk')
        self.assertEqual(table, before)

    def test_demo_is_labeled_hypothetical_and_not_causal(self):
        proc=subprocess.run([sys.executable,str(FILE)],capture_output=True,text=True,check=True)
        self.assertIn('SYNTHETIC', proc.stdout)
        self.assertIn('NOT a causal', proc.stdout)
        self.assertIn('60.0%', proc.stdout)

if __name__ == '__main__':unittest.main()