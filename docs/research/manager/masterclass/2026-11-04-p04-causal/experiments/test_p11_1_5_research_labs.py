"""Independent correctness and boundary tests for all five P11 offline lessons."""
import unittest
from dataclasses import replace
from math import isfinite

from p11_1_5_research_labs import (
    LoggedChoice, synthetic_contextual_log, evaluate_contextual_ope,
    p11_1_demo, peer_exposure, simulated_social_outcomes,
    synthetic_homophily_not_contagion, p11_2_demo,
    compare_agent_architecture, p11_3_demo, fit_logistic_1d,
    logistic_log_loss, synthetic_two_domain_choices, p11_4_demo,
    transport_stratified_ate, backtest_selection_bias, p11_5_demo, run_all
)


class P111OfflineRL(unittest.TestCase):
    def test_ips_dr_within_tolerance_of_oracle(self):
        r = p11_1_demo()
        self.assertLess(abs(r["ips"] - r["oracle_population_value"]), 0.04)
        self.assertLess(abs(r["doubly_robust"] - r["oracle_population_value"]), 0.025)

    def test_sample_size_valid(self):
        r = p11_1_demo()
        self.assertEqual(r["n"], 20000)
        self.assertGreater(r["effective_sample_size"], 0)
        self.assertLessEqual(r["effective_sample_size"], r["n"])

    def test_realized_reward_binary(self):
        self.assertTrue(all(row.reward in (0.0, 1.0) for row in synthetic_contextual_log(100)))

    def test_positivity_gap_is_refused(self):
        behavior = {(0, 0): .9, (0, 1): 0.0, (1, 0): .25, (1, 1): .75}
        with self.assertRaisesRegex(ValueError, "positivity"):
            evaluate_contextual_ope(synthetic_contextual_log(10), behavior)

    def test_corrupt_propensity_rejected(self):
        rows = synthetic_contextual_log(10)
        rows[0] = replace(rows[0], logged_propensity=0.5)
        with self.assertRaisesRegex(ValueError, "contradicts"):
            evaluate_contextual_ope(rows, {(0, 0): .9, (0, 1): .1, (1, 0): .25, (1, 1): .75})

    def test_zero_propensity_rejected(self):
        rows = synthetic_contextual_log(10)
        rows[0] = replace(rows[0], logged_propensity=0.0)
        with self.assertRaisesRegex(ValueError, "bad logging"):
            evaluate_contextual_ope(rows, {(0, 0): .9, (0, 1): .1, (1, 0): .25, (1, 1): .75})

    def test_no_data_rejected(self):
        with self.assertRaisesRegex(ValueError, "rows"):
            evaluate_contextual_ope([], {(0, 0): .9, (0, 1): .1, (1, 0): .25, (1, 1): .75})

    def test_no_real_policy_deployed(self):
        self.assertFalse(p11_1_demo()["policy_deployed"])


class P112SocialSimulation(unittest.TestCase):
    def test_neighbor_exposure(self):
        self.assertAlmostEqual(peer_exposure("a", {"a": ["b", "c"]}, {"a": 0, "b": 1, "c": 0}), .5)

    def test_isolated_node_exposure_zero(self):
        self.assertEqual(peer_exposure("a", {"a": []}, {"a": 0}), 0)

    def test_missing_assignments(self):
        with self.assertRaisesRegex(ValueError, "assignment missing"):
            peer_exposure("a", {"a": ["b"]}, {"a": 0})

    def test_synthetic_direct_and_peer_effect(self):
        r = p11_2_demo()["network"]
        # a unassigned, both neighbors assigned so E[Y_a]=0.20+0.30=0.50
        self.assertAlmostEqual(r["expected_outcome_probability"]["a"], .5)

    def test_structural_homophily_has_zero_peer_effect(self):
        r = synthetic_homophily_not_contagion()
        self.assertEqual(r["neighbor_association_accuracy"], 1)
        self.assertEqual(r["structural_peer_effect"], 0)

    def test_cross_graph_edge_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid network"):
            simulated_social_outcomes({"a": ["ghost"]}, {"a": 0}, {"a": .2})

    def test_missing_person_rejected(self):
        with self.assertRaisesRegex(ValueError, "identities"):
            simulated_social_outcomes({"a": []}, {}, {"a": .2})

    def test_invalid_treatment_rejected(self):
        with self.assertRaisesRegex(ValueError, "binary"):
            simulated_social_outcomes({"a": []}, {"a": 3}, {"a": .2})


class P113DistributedCognition(unittest.TestCase):
    def test_parallel_tasks_can_pay_off(self):
        r = p11_3_demo()["parallel"]
        self.assertLess(r["multi_duration_units"], r["single_duration_units"])

    def test_sequential_tasks_worse(self):
        r = p11_3_demo()["sequential"]
        self.assertGreater(r["multi_duration_units"], r["single_duration_units"])

    def test_more_agents_more_tokens_in_model(self):
        r = compare_agent_architecture(10, 1., .10)
        self.assertGreater(r["multi_tokens"], r["single_tokens"])

    def test_shared_error_not_independent(self):
        r = compare_agent_architecture(10, 1., .2)
        self.assertAlmostEqual(r["perfectly_correlated_two_agents_both_wrong_probability"], .2)
        self.assertAlmostEqual(r["independent_two_agents_both_wrong_probability"], .04)

    def test_probability_out_of_range(self):
        with self.assertRaisesRegex(ValueError, "probability"):
            compare_agent_architecture(10, 1.1, .2)

    def test_cannot_claim_real_agent_eval(self):
        self.assertFalse(compare_agent_architecture(10, .5, .2)["quality_of_real_agents_evaluated"])


class P114FoundationModelTransfer(unittest.TestCase):
    def test_task_specific_synthetic_outperforms_for_opposite_rules(self):
        r = p11_4_demo()
        for k in ("A", "B"):
            self.assertLess(r["specific_test_logloss"][k], r["pooled_test_logloss"][k])

    def test_direction_of_weights_opposed(self):
        r = p11_4_demo()
        self.assertGreater(r["task_specific_weights"]["A"], 0)
        self.assertLess(r["task_specific_weights"]["B"], 0)

    def test_model_is_not_real_bfm(self):
        r = p11_4_demo()
        self.assertTrue(r["not_a_trained_BFM"])
        self.assertFalse(r["model_weight_release"])

    def test_logistic_fit_is_directional(self):
        param = fit_logistic_1d([(-1, 0)] * 20 + [(1, 1)] * 20)
        self.assertGreater(param[1], 0)

    def test_eval_requires_data(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            logistic_log_loss([], (0., 0.))

    def test_nonsensical_labels_rejected(self):
        with self.assertRaisesRegex(ValueError, "labels"):
            fit_logistic_1d([(1, 2)])

    def test_deterministic_dataset(self):
        self.assertEqual(synthetic_two_domain_choices(20, 5), synthetic_two_domain_choices(20, 5))


class P115CrossDomain(unittest.TestCase):
    def test_transport_stratification(self):
        self.assertAlmostEqual(p11_5_demo()["transport_example"]["standardized_ate"], .14)

    def test_bad_target_population(self):
        with self.assertRaisesRegex(ValueError, "valid target"):
            transport_stratified_ate({"A": .1}, {"A": 1.5})

    def test_missing_effect_modifier_stratum(self):
        with self.assertRaisesRegex(ValueError, "overlap"):
            transport_stratified_ate({"A": .1}, {"B": 1})

    def test_backtest_reproducible(self):
        self.assertEqual(backtest_selection_bias(), backtest_selection_bias())

    def test_best_training_score_optimistic_in_seeded_null(self):
        r = backtest_selection_bias()
        self.assertGreater(r["best_in_sample_mean"], r["same_selected_future_mean"])

    def test_selected_backtest_does_not_claim_market_profit(self):
        self.assertFalse(backtest_selection_bias()["real_market_test"])

    def test_imbalanced_training_shape_invalid(self):
        with self.assertRaisesRegex(ValueError, "shape"):
            backtest_selection_bias(n_train=0)


class IntegratedBoundary(unittest.TestCase):
    def test_no_real_human_outcomes_or_production(self):
        r = run_all()
        self.assertEqual(r["actual_user_outcomes"], "NOT_MEASURED")
        self.assertEqual(r["actual_shared_BFM_training"], "NOT_PERFORMED")
        self.assertEqual(r["actual_autonomous_operations"], "NOT_PERFORMED")
        self.assertEqual(set(k for k in r if k.startswith("P11")), set(f"P11-{i}" for i in range(1, 6)))

    def test_all_metrics_are_finite(self):
        r = run_all()
        self.assertTrue(all(isfinite(r["P11-1"][k]) for k in
                            ["ips", "snips", "direct_method", "doubly_robust"]))
        self.assertTrue(isfinite(r["P11-5"]["backtest_multiple_search"]["same_selected_future_mean"]))


if __name__ == "__main__":
    unittest.main()
