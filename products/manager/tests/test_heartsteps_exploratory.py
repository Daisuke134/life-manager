"""H005 waiver and H006-H010 alternative public-dataset study: synthetic tests only."""
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import heartsteps_phase3_exploratory as alt


def sample(u=0, idx=0, arm='none', **updates):
    send = arm != 'none'
    walk = arm == 'walk'
    sed = arm == 'sedentary'
    out = {
        'user.index': str(u),
        'decision.index.nogap': str(idx),
        'avail': 'True',
        'send': str(send), 'send.active': str(walk),
        'send.sedentary': str(sed),
        'jbsteps30': '100', 'jbsteps30.zero': '100',
        'jbsteps30pre.zero': '80',
    }
    out.update(updates)
    return out


class PublicOnlyAlternativeTests(unittest.TestCase):
    def test_never_uses_unsupported_2019_day_42_cutoff(self):
        items,counts = alt.select_public_assignments([sample(idx=220),sample(idx=0)])
        self.assertEqual(len(items),2)
        self.assertEqual(items[0]['decision_index'],220)
        self.assertEqual(counts['retained'],2)

    def test_missing_assignment_is_never_no_action(self):
        items,counts = alt.select_public_assignments([sample(send=''),sample(idx=1)])
        self.assertEqual(len(items),1)
        self.assertEqual(counts['missing_send'],1)

    def test_absent_availability_and_missing_decision_index_are_excluded(self):
        items,c=alt.select_public_assignments([sample(idx=0,avail='False'),sample(idx=1,**{'decision.index.nogap':''}),sample(idx=2)])
        self.assertEqual(len(items),1)
        self.assertEqual(c['unavailable'],1)
        self.assertEqual(c['missing_decision_index'],1)

    def test_ambiguous_treatment_assignment_is_rejected(self):
        items,c=alt.select_public_assignments([sample(idx=0,arm='walk',**{'send.sedentary':'True'}),sample(idx=1)])
        self.assertEqual(len(items),1)
        self.assertEqual(c['ambiguous_action'],1)

    def test_missing_outcome_and_negative_outcome_are_not_zero(self):
        items,c=alt.select_public_assignments([sample(idx=0,**{'jbsteps30.zero':''}),sample(idx=1,**{'jbsteps30.zero':'-2'}),sample(idx=2)])
        self.assertEqual(len(items),1)
        self.assertEqual(c['missing_outcome'],1)
        self.assertEqual(c['invalid_outcome'],1)

    def test_rejected_user_values_are_not_serialized(self):
        rows,c=alt.select_public_assignments([sample(u='SECRET-PERSON-XYZ',idx=0)])
        summary=alt.descriptive_summary(rows,c)
        self.assertNotIn('SECRET-PERSON-XYZ',str(summary))
        self.assertNotIn('user.index',str(summary))
        self.assertFalse(summary['causal_effect_estimated'])

    def test_raw_missing_is_counted_even_when_zero_imputed(self):
        rows,c=alt.select_public_assignments([sample(idx=0,jbsteps30=''),sample(idx=1,jbsteps30='0')])
        summary=alt.descriptive_summary(rows,c)
        self.assertEqual(summary['raw_outcome_missing'],1)

    def test_empirical_report_requires_multiple_clusters(self):
        rows,_=alt.select_public_assignments([sample(u=0,idx=i,arm='walk' if i%2 else 'none') for i in range(80)])
        with self.assertRaisesRegex(ValueError,'clusters'):
            alt.fit_exploratory_models(rows)

    def test_simulation_fixture_estimates_effect_but_does_not_claim_causality(self):
        rows=[]
        for u in range(14):
            for ix in range(100):
                arm= 'none' if ix%10<4 else 'walk' if ix%10<7 else 'sedentary'
                pre=50+u+ix%9
                ratio=.18 if arm!='none' else 0
                outcome=math.exp(math.log(pre+.5)+.22+ratio+.001*(ix-50)*(arm!='none'))-.5
                rows.append(sample(u,ix,arm,**{'jbsteps30.zero':str(outcome),'jbsteps30pre.zero':str(pre)}))
        selected,c=alt.select_public_assignments(rows)
        model=alt.fit_exploratory_models(selected)
        self.assertGreater(model['any_ratio'],1.1)
        self.assertLess(model['any_ratio'],1.3)
        self.assertEqual(model['clusters'],14)
        self.assertTrue(math.isfinite(model['any_ci_95'][0]))
        self.assertNotEqual(model['any_time_index_interaction'],0)
        report=alt.build_public_report(selected,c)
        self.assertEqual(report['source_comparison']['replicated_2019_trial'],'NO')
        self.assertEqual(report['scientific_status'],'exploratory_nonidentical')
        self.assertEqual(report['outcomes']['causal_effect_estimated'],False)
        self.assertEqual(report['source_comparison']['unmet_original_selection_requirement'],True)

    def test_can_preserve_nonidentical_result_even_if_counts_match_by_accident(self):
        rows=[]
        for u in range(12):
            for ix in range(20):
                rows.append(sample(u,ix,'walk' if ix%2 else 'none',**{'jbsteps30.zero':str(80+u+ix)}))
        selected,c=alt.select_public_assignments(rows)
        r=alt.build_public_report(selected,c)
        self.assertNotIn('original_reproduction_passed',r)
        self.assertFalse(r['source_comparison']['replicated_2019_trial']=='YES')
        self.assertTrue(r['privacy']['individual_rows_in_report'] is False)
        self.assertNotIn('user.index',str(r))

if __name__=='__main__':unittest.main()