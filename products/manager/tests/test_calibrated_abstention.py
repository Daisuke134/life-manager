"""Reference-based, scope-bound error estimates; no human calibration fiction."""
import unittest
from dataclasses import replace
from manager_core.calibration import (ErrorReference, PredictionCase,
    fit_error_calibrator, selective_risk_curve)

SCOPE='observed_daily_aggregate'


def ref(identity,group,p=.3,y=0):
    return ErrorReference(identity,group,SCOPE,'en',(1-p,p),y)


def fitted():
    return fit_error_calibrator((ref('a','train',.1,0),ref('b','train',.9,1)),
                                (ref('c','validation',.2,0),ref('d','validation',.8,1)),
                                scope=SCOPE,max_validation_risk=.1)


class CalibratedAbstentionTests(unittest.TestCase):
    def test_group_leakage_rejected(self):
        with self.assertRaises(ValueError):
            fit_error_calibrator((ref('a','same'),),(ref('b','same'),),scope=SCOPE)

    def test_probability_mass_must_be_one(self):
        with self.assertRaises(ValueError):ref('a','train',.2).__class__('a','train',SCOPE,'en',(.2,.3),0)

    def test_confidence_with_no_reference_labels_is_unavailable(self):
        c=fit_error_calibrator((),(),scope=SCOPE)
        r=c.predict_error(PredictionCase('new',SCOPE,'en',(.3,.7)))
        self.assertEqual(r.status,'REFERENCE_DATA_REQUIRED')
        self.assertIsNone(r.estimated_error)

    def test_unseen_population_abstains(self):
        c=fitted();r=c.predict_error(PredictionCase('new',SCOPE,'en',(.3,.7),out_of_distribution=True))
        self.assertEqual(r.status,'ABSTAIN_DISTRIBUTION_SHIFT')
        self.assertFalse(r.accepted)

    def test_unsupported_language_abstains(self):
        self.assertEqual(fitted().predict_error(PredictionCase('new',SCOPE,'ja',(.3,.7))).status,'ABSTAIN_SCOPE')

    def test_aggregate_calibration_cannot_authorize_owned_digital_or_human_claim(self):
        for scope in ('owned_digital','human_wellbeing'):
            r=fitted().predict_error(PredictionCase('new',scope,'en',(.3,.7)))
            self.assertEqual(r.status,'ABSTAIN_SCOPE')
            self.assertIsNone(r.estimated_error)

    def test_curve_reports_coverage_and_real_squared_error(self):
        c=fitted();references=(ref('one','test',.2,0),ref('two','test',.8,0))
        estimates=tuple(c.predict_error(PredictionCase(r.reference_id,r.scope,r.language,r.distribution)) for r in references)
        curve=selective_risk_curve(estimates,references)
        self.assertEqual(curve[0].coverage,0)
        self.assertIsNone(curve[0].risk)
        self.assertEqual(curve[-1].coverage,1)
        self.assertAlmostEqual(curve[-1].risk,(.04+.64)/2)

    def test_curve_cannot_join_an_unrelated_prediction(self):
        c=fitted();r=ref('one','test',.2,0)
        e=c.predict_error(PredictionCase('other',SCOPE,'en',(.8,.2)))
        with self.assertRaises(ValueError):selective_risk_curve((e,),(r,))

    def test_reference_digest_binds_partition_boundary(self):
        rows=tuple(ref(str(i),'group_'+str(i),.1*i,i%2) for i in range(1,5))
        a=fit_error_calibrator(rows[:2],rows[2:],scope=SCOPE)
        b=fit_error_calibrator(rows[:1],rows[1:],scope=SCOPE)
        self.assertNotEqual(a.reference_hash,b.reference_hash)

    def test_report_comparison_tolerates_roundoff_but_not_changed_evidence(self):
        from scripts.phase_calibration_reference import assert_reference_report
        actual={'source_hash':'abc','risk':.2409337384067183,'count':366,'status':'DENIED'}
        expected={'source_hash':'abc','risk':.2409337384067195,'count':366,'status':'DENIED'}
        assert_reference_report(actual,expected)
        for field,value in (('source_hash','wrong'),('risk',.3),('count',365),('status','PROMOTED')):
            changed=dict(actual);changed[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                assert_reference_report(changed,expected)

    def test_validation_threshold_does_not_use_test_labels(self):
        c=fitted();before=c.threshold
        r=ref('one','test',.8,0);e=c.predict_error(PredictionCase('one',SCOPE,'en',r.distribution))
        a=selective_risk_curve((e,),(r,));b=selective_risk_curve((e,),(replace(r,outcome=1),))
        self.assertNotEqual(a[-1].risk,b[-1].risk)
        self.assertEqual(c.threshold,before)


if __name__=='__main__':unittest.main()
