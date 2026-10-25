"""Native units, structural no-action, and non-authorizing scope feasibility."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from dataclasses import replace
import unittest
from manager_core.models.intervention import OutcomeEndpoint,OutcomeVector,Candidate,combine_outcomes
from manager_core.candidate_catalog import generate_candidates,CandidateCatalog,validate_candidates,feasible
from manager_core.authority import OwnedDigitalScope
from manager_core.models.problem import Problem,CausalHypothesis
from manager_core.models.observation import Observation
from manager_core.models.source import Source

NOW=datetime(2026,10,22,12,tzinfo=timezone.utc)
TARGET='manager-support/finance.html'


def problem(target=TARGET):
    source=Source('current-source-ref','https://www.gov.uk/help/accessibility-statement','OGL-3.0',
                  'allowed_with_conditions','a'*64,NOW,'public_nonpersonal')
    obs=Observation(source,'broken_official_links',target,1,'count',NOW)
    return Problem('link-problem','broken_official_links',(obs,),
        (CausalHypothesis('One route is outdated.','Correct a cited link.',('current-source-ref',)),),
        ('The destination may be temporarily unavailable.',))


class CandidateUnitTests(unittest.TestCase):
    def test_dollars_cannot_be_added_to_pm25_or_minutes(self):
        dollars=OutcomeEndpoint('financial','USD',1,'baseline')
        for metric,unit in (('air','ug/m3'),('time','minutes')):
            with self.assertRaises(ValueError):combine_outcomes(dollars,OutcomeEndpoint(metric,unit,1,'baseline'))

    def test_candidate_set_cannot_omit_no_action(self):
        candidates=generate_candidates(problem(),CandidateCatalog())
        self.assertEqual(sum(c.no_action for c in candidates),1)
        with self.assertRaises(ValueError):validate_candidates(tuple(c for c in candidates if not c.no_action))

    def test_predicted_benefit_cannot_become_causal_support(self):
        c=generate_candidates(problem(),CandidateCatalog())[-1]
        self.assertFalse(c.causal_support)
        self.assertFalse(c.authorized_execution)
        with self.assertRaises(ValueError):replace(c,causal_support=True)

    def test_no_action_opportunity_cost_is_unknown_not_zero_command_cost(self):
        c=generate_candidates(problem(),CandidateCatalog())[0]
        self.assertEqual(c.command_cost_usd,Decimal('0'))
        self.assertIsNone(c.opportunity_cost)

    def test_live_plan_requires_host_scope_and_technical_criterion(self):
        c=generate_candidates(problem(),CandidateCatalog())[-1]
        self.assertFalse(feasible(c,None,Decimal('0'),at=NOW))
        scope=OwnedDigitalScope('owner-scope',frozenset({TARGET}),NOW,NOW+timedelta(hours=1),7)
        self.assertTrue(feasible(c,scope,Decimal('0'),at=NOW))
        self.assertFalse(feasible(c,scope,Decimal('0'),at=NOW+timedelta(hours=2)))
        self.assertIsNone(c.outcomes.endpoints[0].value)

    def test_third_party_route_does_not_enter_catalog(self):
        c=generate_candidates(problem('https://third-party.example/account'),CandidateCatalog())
        self.assertEqual(tuple(x.action for x in c),('NO_ACTION',))

    def test_host_scope_cannot_widen_publisher_paths(self):
        with self.assertRaises(ValueError):
            OwnedDigitalScope('scope',frozenset({'unrelated.html'}),NOW,NOW+timedelta(hours=1),7)


if __name__=='__main__':unittest.main()
