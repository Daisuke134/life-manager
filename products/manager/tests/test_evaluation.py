import unittest
from manager_core.evaluation import (
    total_variation, brier_score, exploratory_mean_difference,
    ActionProposal, gate_action
)


class FoundationsTest(unittest.TestCase):
    def test_tvd_identical(self):
        self.assertAlmostEqual(total_variation({'yes':0.4,'no':0.6},{'no':0.6,'yes':0.4}),0.0)

    def test_tvd_disjoint(self):
        self.assertAlmostEqual(total_variation({'yes':1.0},{'no':1.0}),1.0)

    def test_tvd_illustrative(self):
        self.assertAlmostEqual(total_variation({'yes':0.93,'no':0.07},{'yes':0.87,'no':0.13}),0.06)

    def test_invalid_probabilities_rejected(self):
        with self.assertRaises(ValueError):
            total_variation({'a':0.6,'b':0.5},{'a':0.5,'b':0.5})

    def test_brier(self):
        self.assertAlmostEqual(brier_score([0.8,0.2],[1,0]),0.04)

    def test_group_difference_is_descriptive(self):
        self.assertAlmostEqual(exploratory_mean_difference([10,12],[4,6]),6)

    def test_no_implicit_permission(self):
        p=ActionProposal('https://example.org/public',True,False,0,100,False,False)
        self.assertEqual(gate_action(p),(False,'not_authorized'))

    def test_no_irreversible_unapproved_action(self):
        p=ActionProposal('https://example.org/public',True,True,5,100,True,False)
        self.assertEqual(gate_action(p),(False,'requires_explicit_approval'))

    def test_no_budget_overrun(self):
        p=ActionProposal('https://example.org/public',True,True,101,100,False,False)
        self.assertEqual(gate_action(p),(False,'over_budget'))

    def test_no_private_source(self):
        p=ActionProposal('https://example.org',False,True,0,100,False,False)
        self.assertEqual(gate_action(p),(False,'source_not_public'))

    def test_allowed_is_not_execution(self):
        p=ActionProposal('https://example.org',True,True,0,100,False,False)
        self.assertTrue(gate_action(p)[0])


if __name__=='__main__':
    unittest.main()
