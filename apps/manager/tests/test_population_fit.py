import unittest
import numpy as np
from manager.population.fit import independent_population, fit_population
from manager.population.contracts import Marginals, PopulationDataError
from helpers import source

class FitTests(unittest.TestCase):
    def target(self,poverty=(30,70),age=(20,60,20)):
        return Marginals('0400000US01',source(),poverty,age,100)

    def test_independent_exact_product(self):
        self.assertEqual(independent_population(self.target()).counts,(6,18,6,14,42,14))

    def test_ipf_matches_marginals_without_erasing_seed_relation(self):
        seed=(40,10,5,10,20,15)
        p=fit_population(seed,self.target());x=np.array(p.counts).reshape(2,3)
        np.testing.assert_allclose(x.sum(axis=1),(30,70),atol=1e-8)
        np.testing.assert_allclose(x.sum(axis=0),(20,60,20),atol=1e-8)
        self.assertLessEqual(p.max_residual,1e-10)
        self.assertAlmostEqual(x[0,0]*x[1,1]/(x[0,1]*x[1,0]),8,places=7)
        self.assertLessEqual(p.iterations,1000)

    def test_zero_target_is_zero_without_nan(self):
        for target in [self.target((0,100)),self.target(age=(0,80,20))]:
            p=fit_population((1,2,3,4,5,6),target)
            self.assertTrue(all(np.isfinite(p.counts)))
            x=np.array(p.counts).reshape(2,3)
            np.testing.assert_allclose(x.sum(axis=1),target.poverty)
            np.testing.assert_allclose(x.sum(axis=0),target.age)

    def test_zero_seed_and_nonconvergence_fail(self):
        for seed,kwargs in [((0,1,1,1,1,1),{}),((40,10,5,10,20,15),{'max_iterations':1}),
                             ((1,)*6,{'max_iterations':True}),((1,)*6,{'tolerance':float('nan')})]:
            with self.subTest(seed=seed,kwargs=kwargs),self.assertRaises(PopulationDataError):fit_population(seed,self.target(),**kwargs)

    def test_uniform_seed_matches_independent(self):
        np.testing.assert_allclose(fit_population((1,)*6,self.target()).counts,independent_population(self.target()).counts)
