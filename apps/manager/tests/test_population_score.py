from dataclasses import replace
import unittest
from manager.population.contracts import JointTable, FitResult, PopulationDataError
from manager.population.fit import independent_population
from manager.population.prepare import marginalize
from manager.benchmarks.population import score_population, summarize_population
from helpers import source

class ScoreTests(unittest.TestCase):
    def reference(self):return JointTable('0400000US01',source(),(15,10,5,5,50,15),100)

    def test_same_marginals_can_have_wrong_joint(self):
        r=self.reference();p=independent_population(marginalize(r));s=score_population(p,r)
        self.assertAlmostEqual(s.tvd,.18);self.assertAlmostEqual(s.max_cell_error_pp,9)
        self.assertAlmostEqual(s.poverty_rate_error_pp[0],45)

    def test_zero_age_rate_is_unknown(self):
        r=JointTable('0400000US01',source(),(0,30,0,0,70,0),100)
        s=score_population(independent_population(marginalize(r)),r)
        self.assertEqual(s.poverty_rate_error_pp,(None,0,None))

    def test_mismatched_scope_or_total_is_rejected(self):
        r=self.reference();p=independent_population(marginalize(r))
        for q in [replace(p,geo_id='0400000US02'),replace(p,target_source_sha256='b'*64),
                  replace(p,counts=tuple(v*2 for v in p.counts))]:
            with self.assertRaises(PopulationDataError):score_population(q,r)

    def test_weighted_and_unweighted_scores_are_distinct(self):
        r=self.reference();r2=JointTable('0400000US02',source(),tuple(v*9 for v in r.counts),900)
        p=independent_population(marginalize(r));p2=FitResult(r2.geo_id,'independent',r2.counts,0,0,None,source().extract_sha256)
        scores=(score_population(p,r),score_population(p2,r2))
        s=summarize_population(scores,(r,r2))['methods']['independent']
        self.assertAlmostEqual(s['mean_tvd'],.09);self.assertAlmostEqual(s['population_weighted_mean_tvd'],.018)
        with self.assertRaises(PopulationDataError):summarize_population(scores[:1],(r,r2))

    def test_stage_never_claims_field_improvement(self):
        r=self.reference();s=summarize_population((score_population(independent_population(marginalize(r)),r),),(r,))
        self.assertEqual(s['stage'],'empirical_reconstruction')
        self.assertEqual(s['tracks'],{'population_fidelity':'measured','behavior_prediction':'not_run','policy':'not_run','execution':'not_run','field':'not_run'})
