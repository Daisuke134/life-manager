"""Research-only proof firewall: simulated earnings != real wealth.

Tests use constructed data, never user/seller source rows or live payments.
"""
import unittest
from dataclasses import replace
from manager_core.economic_scorecard import (
    AggregateEconomicEpisode, HashedReceipt, CostCoverage,
    EconomicExperiment, score_economic_episode, COST_CATEGORIES,
)


def costs(**changes):
    amounts={k:0 for k in COST_CATEGORIES}
    amounts.update({"compute":150, "platform":250,"labor":100})
    amounts.update(changes)
    return CostCoverage(amounts)


def receipt(ch="a", *, amount=2000, status="settled", external=True):
    return HashedReceipt(ch * 64,amount,status,external)


def ep(**kwargs):
    args=dict(
        episode_id="example-episode-v1", source_kind="provider_claim",
        currency="USD", receipts=(receipt(),), cost_coverage=costs(),
        human_rescue_seconds=0, unresolved_effects=0, policy_violations=0,
    )
    args.update(kwargs)
    return AggregateEconomicEpisode(**args)


class EconomicScorecardContract(unittest.TestCase):
    def test_reconciled_input_not_a_blessing_even_if_positive(self):
        result=score_economic_episode(ep())
        self.assertEqual(result.settled_external_revenue_minor,2000)
        self.assertEqual(result.signed_net_contribution_minor,1500)
        self.assertEqual(result.economic_status,"UNAUTHENTICATED_RECONCILED_INPUT")
        self.assertEqual(result.real_world_proof_level,"P0")
        self.assertEqual(result.beneficiary_status,"NOT_MEASURED")
        self.assertEqual(result.autonomy_status,"NO_HUMAN_RESCUES_REPORTED_UNVERIFIED")
        self.assertNotIn("2000",result.__dict__)

    def test_negative_profit_remains_negative(self):
        out=score_economic_episode(ep(cost_coverage=costs(compute=3000)))
        self.assertEqual(out.signed_net_contribution_minor,-1350)
        self.assertNotEqual(out.signed_net_contribution_minor,0)

    def test_simulation_and_dollar_valued_task_not_real_cash(self):
        for origin in ("simulation", "historical_task_value"):
            x=score_economic_episode(ep(source_kind=origin))
            self.assertIsNone(x.settled_external_revenue_minor)
            self.assertIsNone(x.signed_net_contribution_minor)
            self.assertEqual(x.economic_status,"PROXY_NOT_SETTLED_REVENUE")
            self.assertEqual(x.real_world_proof_level,"P0")

    def test_missing_cost_category_is_unknown_never_zero(self):
        c={k:0 for k in COST_CATEGORIES}
        c["compute"]=None
        out=score_economic_episode(ep(cost_coverage=CostCoverage(c)))
        self.assertEqual(out.economic_status,"UNKNOWN_COST_COVERAGE")
        self.assertIsNone(out.signed_net_contribution_minor)

    def test_pending_receipt_cannot_be_profit(self):
        out=score_economic_episode(ep(receipts=(receipt(status="pending"),)))
        self.assertEqual(out.economic_status,"SETTLEMENT_NOT_COMPLETE")
        self.assertIsNone(out.signed_net_contribution_minor)

    def test_duplication_policy_violation_and_unknown_effect_fail_closed(self):
        for episode,status in (
            (ep(receipts=(receipt(),receipt())), "DUPLICATE_RECEIPT"),
            (ep(unresolved_effects=1), "UNKNOWN_EXTERNAL_EFFECT"),
            (ep(policy_violations=1), "POLICY_VIOLATION"),
        ):
            out=score_economic_episode(episode)
            self.assertEqual(out.economic_status,status)
            self.assertIsNone(out.signed_net_contribution_minor)

    def test_human_rescues_are_disclosed_and_strict_autonomy_fails(self):
        out=score_economic_episode(ep(human_rescue_seconds=45))
        self.assertEqual(out.autonomy_status,"HUMAN_INTERVENTION_REPORTED")
        self.assertEqual(out.signed_net_contribution_minor,1500)
        self.assertFalse(out.autonomy_claim_eligible)

    def test_internal_money_transfer_is_not_external_customer_revenue(self):
        out=score_economic_episode(ep(receipts=(receipt(external=False),)))
        self.assertEqual(out.settled_external_revenue_minor,0)
        self.assertEqual(out.signed_net_contribution_minor,-500)

    def test_experiment_without_independent_comparator_never_real_benefit(self):
        x=score_economic_episode(ep(experiment=EconomicExperiment(
            method="pre_post",preregistered=False,independent=False,
            effect_minor=1400,lower_minor=300,upper_minor=2100,harms_minor=None
        )))
        self.assertEqual(x.beneficiary_status,"NOT_MEASURED")
        self.assertEqual(x.real_world_proof_level,"P0")

    def test_randomized_fixture_causal_result_stays_p0(self):
        x=score_economic_episode(ep(experiment=EconomicExperiment(
            method="randomized",preregistered=True,independent=True,
            effect_minor=1400,lower_minor=1100,upper_minor=2000,harms_minor=100,
        )))
        self.assertEqual(x.beneficiary_status,"OFFLINE_CAUSAL_ESTIMATE_ONLY")
        self.assertEqual(x.real_world_proof_level,"P0")
        self.assertEqual(x.net_welfare_effect_minor,800)
        self.assertEqual(x.net_welfare_lower_minor,500)

    def test_reject_invalid_units_identifiers_and_costs(self):
        with self.assertRaises(ValueError):
            ep(currency="USDT")
        with self.assertRaises(ValueError):
            receipt(ch="x")
        with self.assertRaises(ValueError):
            HashedReceipt("a"*64,-1,"settled",True)
        with self.assertRaises(ValueError):
            CostCoverage({"compute":3})
        with self.assertRaises(ValueError):
            ep(unresolved_effects=-1)


if __name__=="__main__":
    unittest.main()
