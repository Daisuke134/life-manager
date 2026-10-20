"""Phase 02 L003-L012: synthetic-only test-first acceptance contracts."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class L003Calibration(unittest.TestCase):
    def test_50_percent_predictions_match_50_percent_outcomes(self):
        from manager_core.calibration import reliability_bins
        bins = reliability_bins([.5] * 10, [0, 1] * 5)
        matching = [x for x in bins if x['count']]
        self.assertEqual(len(matching), 1)
        self.assertAlmostEqual(matching[0]['mean_probability'], .5)
        self.assertAlmostEqual(matching[0]['event_rate'], .5)

    def test_one_is_in_final_bin_and_empty_bins_have_no_fake_rate(self):
        from manager_core.calibration import reliability_bins
        bins = reliability_bins([1.0], [1])
        self.assertEqual(bins[-1]['count'], 1)
        self.assertIsNone(bins[0]['event_rate'])

    def test_rejects_invalid_observations_and_probabilities(self):
        from manager_core.calibration import reliability_bins
        for p, y in [([True], [1]), ([float('nan')], [1]), ([.2], [True]), ([1.1], [0]), ([.5, .5], [1]), ([], [])]:
            with self.subTest(p=p, y=y), self.assertRaises(ValueError):
                reliability_bins(p, y)

    def test_group_holdout_rejects_leakage_and_empty(self):
        from manager_core.calibration import assert_disjoint_groups
        assert_disjoint_groups(['study-1'], ['study-2'])
        for train, test in [(['A'], ['A']), ([], ['A']), (['A'], [])]:
            with self.subTest(train=train), self.assertRaises(ValueError):
                assert_disjoint_groups(train, test)


class L004JITAI(unittest.TestCase):
    def test_glossary_defines_study_components_and_cites_primary_study(self):
        doc = (ROOT/'docs/learning/JITAI_GLOSSARY.md').read_text()
        for item in ['decision point','availability','intervention option', 'tailoring variable',
                     'decision rule', 'proximal', 'https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/',
                     'https://pmc.ncbi.nlm.nih.gov/articles/PMC5364076/']:
            self.assertIn(item, doc.lower() if not item.startswith('https') else doc)
        self.assertIn('NO_ACTION', doc)


class L005CausalDAG(unittest.TestCase):
    def test_synthetic_observational_difference_is_not_intervention_effect(self):
        from manager_core.causal_examples import confounded_toy
        result = confounded_toy()
        self.assertGreater(result['observed_gap'], 0)
        self.assertEqual(result['oracle_effect_of_changing_label'], 0)
        self.assertTrue(result['synthetic_only'])

    def test_dag_shows_common_cause_and_randomized_assignment(self):
        d = (ROOT/'docs/learning/CAUSAL_DAG.md').read_text()
        for term in ['mermaid','U --> X','U --> Y','A --> Y','P(Y|X)','do(X)']:
            self.assertIn(term, d)
        # This specific confounded toy sets the effect of X to zero.
        self.assertNotIn(' X --> Y\n', d)


class L006PotentialOutcomes(unittest.TestCase):
    def test_oracle_ate_only_synthetic(self):
        from manager_core.potential_outcomes import oracle_ate
        units = [{'id':'a','y0':1,'y1':3}, {'id':'b','y0':5,'y1':7}]
        self.assertEqual(oracle_ate(units), 2)

    def test_observed_rows_do_not_leak_unobserved_potential_outcomes(self):
        from manager_core.potential_outcomes import observed_only
        units=[{'id':'a','y0':1,'y1':3}, {'id':'b','y0':5,'y1':7}]
        rec=observed_only(units,{'a':1,'b':0})
        self.assertEqual(rec,[{'id':'a','treatment':1,'outcome':3}, {'id':'b','treatment':0,'outcome':5}])
        self.assertFalse(any('y1' in o or 'y0' in o for o in rec))

    def test_example_command_is_importable_as_module(self):
        d=(ROOT/'docs/learning/POTENTIAL_OUTCOMES.md').read_text()
        self.assertIn('python3 -m examples.03_potential_outcomes',d)

    def test_rejects_duplicate_ids_or_unknown_assignment(self):
        from manager_core.potential_outcomes import observed_only
        unit={'id':'a','y0':0,'y1':1}
        for units, assigned in [([unit,unit],{'a':1}),([unit],{}),([unit],{'a':True})]:
            with self.assertRaises(ValueError): observed_only(units,assigned)


class L007Randomization(unittest.TestCase):
    def test_fixed_seed_is_reproducible_and_binary(self):
        from manager_core.randomization import assign_randomly
        a=assign_randomly(100,.5,17)
        self.assertEqual(a,assign_randomly(100,.5,17))
        self.assertNotEqual(a,assign_randomly(100,.5,18))
        self.assertTrue(set(a)<={0,1})

    def test_randomized_large_toy_recovers_known_effect_approximately(self):
        from manager_core.randomization import toy_rct_estimate
        result=toy_rct_estimate(n=25000,seed=23)
        self.assertAlmostEqual(result['known_synthetic_ate'],2.0)
        self.assertLess(abs(result['observed_group_difference']-2),.1)
        self.assertEqual(result['design'],'synthetic_individually_randomized')

    def test_invalid_randomization_rejected(self):
        from manager_core.randomization import assign_randomly
        for args in [(0,.5,1),(10,True,1),(10,1.1,1),(10,.5,True)]:
            with self.subTest(args=args),self.assertRaises(ValueError): assign_randomly(*args)


class L008MRT(unittest.TestCase):
    def test_five_points_per_day_and_no_randomization_when_unavailable(self):
        from manager_core.mrt_demo import simulate_decision_points
        result=simulate_decision_points([True,False,True,True,True]*2,seed=2)
        self.assertEqual(len(result),10)
        self.assertEqual([x['day'] for x in result],[1]*5+[2]*5)
        self.assertTrue(all(x['slot'] in range(1,6) for x in result))
        self.assertFalse(result[1]['randomized'])
        self.assertIsNone(result[1]['assignment_probability'])
        self.assertTrue(result[0]['randomized'])
        self.assertEqual(result[0]['proximal_window_minutes'],30)
        self.assertEqual(simulate_decision_points([True]*5,seed=4),simulate_decision_points([True]*5,seed=4))

    def test_reject_incomplete_days_and_non_bool_availability(self):
        from manager_core.mrt_demo import simulate_decision_points
        for availability in ([True]*4,[1]*5,[]):
            with self.subTest(data=availability),self.assertRaises(ValueError):
                simulate_decision_points(availability,seed=1)

    def test_doc_differentiates_original_study_from_toy(self):
        d=(ROOT/'docs/learning/MRT.md').read_text()
        for phrase in ['0.4','0.3','30','availability','HeartSteps','架空']:
            self.assertIn(phrase,d)


class L009Outcomes(unittest.TestCase):
    def test_proximal_steps_not_proof_of_longterm_health(self):
        from manager_core.outcome_windows import EvidenceWindow, supports_claim
        short=EvidenceWindow('steps',30,59,'https://example.org/data',False)
        self.assertTrue(supports_claim(short,'steps',30,causal=False))
        self.assertFalse(supports_claim(short,'health',42*24*60,causal=False))
        self.assertFalse(supports_claim(short,'steps',30,causal=True))

    def test_missing_evidence_never_supports_any_claim(self):
        from manager_core.outcome_windows import EvidenceWindow, supports_claim
        unmeasured=EvidenceWindow('health',42*24*60,None,'https://example.org/data',False)
        self.assertFalse(supports_claim(unmeasured,'health',42*24*60))

    def test_windows_document_explains_differences(self):
        d=(ROOT/'docs/learning/PROXIMAL_VS_LONG_TERM.md').read_text()
        for x in ['30','42','proximal','distal','欠測']:
            self.assertIn(x,d)


class L010Spillovers(unittest.TestCase):
    def test_support_gains_may_be_displaced_and_costly(self):
        from manager_core.spillover import net_additional_resources
        self.assertEqual(net_additional_resources(100,[-90],20),-10)
        self.assertEqual(net_additional_resources(100,[0],20),80)

    def test_invalid_spillover_values_rejected(self):
        from manager_core.spillover import net_additional_resources
        with self.assertRaises(ValueError): net_additional_resources(True,[0],0)
        with self.assertRaises(ValueError): net_additional_resources(100,[float('inf')],0)
        with self.assertRaises(ValueError): net_additional_resources(100,[], -1)

    def test_spillover_doc_warns_arithmetic_is_not_causality(self):
        d=(ROOT/'docs/learning/INTERFERENCE.md').read_text()
        self.assertIn('因果',d)
        self.assertIn('-10',d)


class L011DecisionRules(unittest.TestCase):
    def test_ips_toy_with_known_randomized_propensities(self):
        from manager_core.policy_basics import ips_estimate
        logs=[{'action':'A','reward':1,'logging_propensity':.5,'target_propensity':1},
              {'action':'B','reward':0,'logging_propensity':.5,'target_propensity':0}]*2
        self.assertEqual(ips_estimate(logs,{'A'},{'A','B'}),1)

    def test_ips_rejects_unknown_logging_or_no_support(self):
        from manager_core.policy_basics import ips_estimate
        good=[{'action':'A','reward':1,'logging_propensity':.5,'target_propensity':1}]
        bad=[{'action':'A','reward':1,'target_propensity':1}]
        with self.assertRaises(ValueError): ips_estimate(bad,{'A'},{'A'})
        with self.assertRaises(ValueError): ips_estimate(good,{'A'},{'B'})
        with self.assertRaises(ValueError): ips_estimate(good,{'A','C'},{'A','B'})
        with self.assertRaises(ValueError): ips_estimate([{**good[0],'logging_propensity':0}],{'A'},{'A'})

    def test_decision_rules_doc_covers_bandit_mdp_support_assumption(self):
        d=(ROOT/'docs/learning/DECISION_RULES.md').read_text()
        for key in ['bandit','MDP','off-policy','positivity','no_action','未知']:
            self.assertIn(key,d)


class L012OutcomeLadder(unittest.TestCase):
    def test_no_receipt_cannot_claim_real_world_impact(self):
        from manager_core.outcome_ladder import proof_level
        self.assertEqual(proof_level({}),0)
        self.assertEqual(proof_level({'external_receipt':True}),1)
        self.assertEqual(proof_level({'external_receipt':True,'independent_readback':True}),2)

    def test_benefit_needs_measurement_and_causal_effect_needs_comparator(self):
        from manager_core.outcome_ladder import proof_level
        b={'external_receipt':True,'independent_readback':True,'tangible_benefit':True}
        self.assertEqual(proof_level(b),3)
        self.assertEqual(proof_level({**b,'preregistered_comparison':True}),3)
        p4={**b,'preregistered_comparison':True,'uncertainty_quantified':True,'harms_and_costs_measured':True}
        self.assertEqual(proof_level(p4),4)
        self.assertEqual(proof_level({**p4,'replicated_across_populations':True}),5)

    def test_rejects_nonboolean_proof_and_unknown_keys(self):
        from manager_core.outcome_ladder import proof_level
        for e in [{'external_receipt':1},{'replicated_across_populations':True,'mystery':0}]:
            with self.assertRaises(ValueError): proof_level(e)

    def test_document_explains_proxy_is_not_suffering_reduction(self):
        d=(ROOT/'docs/learning/OUTCOME_LADDER.md').read_text()
        for marker in ['P0','P1','P2','P3','P4','P5','苦しみ','クリック']:
            self.assertIn(marker,d)


if __name__=='__main__':
    unittest.main()
