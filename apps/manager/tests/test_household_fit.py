import math
from pathlib import Path
import tempfile
import unittest
from manager.population.contracts import PopulationDataError
from manager.population.households import HouseholdControls,cell_index
from manager.population.pums import read_pums
from manager.population.household_fit import household_weights
from manager.population.integerize import integerize
from household_helpers import fixture

class HouseholdFitTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();root=fixture(self.directory.name)
        self.households,_=read_pums(root/'housing.zip',root/'persons.zip')
        self.controls=HouseholdControls(10,(5,5),(4,4,2))
    def tearDown(self):self.directory.cleanup()
    def cells(self,weights):return tuple(math.fsum(w for h,w in zip(self.households,weights) if cell_index(h)==i) for i in range(6))

    def test_baseline_preserves_weight_ratios_and_total(self):
        weights=household_weights(self.households,self.controls,'baseline')
        self.assertAlmostEqual(sum(weights),10);self.assertAlmostEqual(weights[0]/weights[1],2)

    def test_calibrated_matches_marginals_and_keeps_structural_zero(self):
        weights=household_weights(self.households,self.controls,'calibrated');cells=self.cells(weights)
        self.assertEqual(cells[0],0)
        for got,want in zip((sum(cells[:3]),sum(cells[3:]),*(cells[i]+cells[i+3] for i in range(3))),(*self.controls.family,*self.controls.size)):
            self.assertAlmostEqual(got,want,places=8)
        reverse=tuple(reversed(self.households));rw=household_weights(reverse,self.controls,'calibrated')
        self.assertEqual(dict(zip((h.serialno for h in reverse),rw)),dict(zip((h.serialno for h in self.households),weights)))

    def test_support_nonconvergence_and_invalid_method_fail(self):
        for method in ('llm','unknown'):
            with self.assertRaises(PopulationDataError):household_weights(self.households,self.controls,method)
        with self.assertRaises(PopulationDataError):household_weights(self.households[1:],self.controls,'calibrated')
        with self.assertRaises(PopulationDataError):household_weights(self.households,self.controls,'calibrated',max_iterations=1)

    def test_zero_target_row_becomes_zero(self):
        c=HouseholdControls(10,(0,10),(4,4,2));weights=household_weights(self.households,c,'calibrated')
        self.assertEqual(weights[1:3],(0,0));self.assertAlmostEqual(sum(weights),10)

    def test_trs_is_deterministic_integer_and_total_preserving(self):
        result=integerize((1.4,1.4,1.2),4,20261018)
        self.assertEqual(sum(result),4);self.assertTrue(all(type(v) is int and v>=1 for v in result))
        self.assertEqual(result,integerize((1.4,1.4,1.2),4,20261018))
        self.assertEqual(integerize((0,2,3),5,1),(0,2,3))
        self.assertEqual(integerize((0,1.5,1.5),3,1)[0],0)

    def test_trs_rejects_bad_values_total_and_seed(self):
        for weights,total,seed in [((-1,5),4,1),((float('nan'),4),4,1),((1,2),4,1),((1,2),3,True),((1,2),3,-1)]:
            with self.assertRaises(PopulationDataError):integerize(weights,total,seed)
