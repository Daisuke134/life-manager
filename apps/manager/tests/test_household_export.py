import csv
from pathlib import Path
import tempfile
import unittest
from manager.population.contracts import PopulationDataError
from manager.population.pums import read_pums,read_controls
from manager.population.household_export import export_population,audit_population
from manager.population.household_fit import household_weights
from manager.population.integerize import integerize
from manager.benchmarks.households import evaluate_households
from household_helpers import fixture

class HouseholdExportTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.root=fixture(Path(self.directory.name)/'input')
        self.hs,_=read_pums(self.root/'housing.zip',self.root/'persons.zip')
        self.controls,self.reference=read_controls(self.root/'b11016.dat')
    def tearDown(self):self.directory.cleanup()

    def test_three_person_household_twice_is_two_households_six_people(self):
        out=self.root/'out';copies=(0,0,2,0,0)
        result=export_population(self.hs,copies,out);audit=audit_population(self.hs,copies,out)
        self.assertEqual(audit['households'],2);self.assertEqual(audit['persons'],6)
        with (out/'persons.csv').open() as f:people=list(csv.DictReader(f))
        self.assertEqual(len({p['person_id'] for p in people}),6)
        self.assertEqual(len({p['household_id'] for p in people}),2)
        self.assertEqual([int(p['age']) for p in people],[38,10,7,38,10,7])
        self.assertIn('persons.csv',result['artifacts'])
        out2=self.root/'out2';export_population(self.hs,copies,out2)
        self.assertEqual((out/'persons.csv').read_bytes(),(out2/'persons.csv').read_bytes())

    def test_missing_duplicate_changed_or_orphan_person_rejected(self):
        for change in ('missing','duplicate','attribute','orphan'):
            out=self.root/change;copies=(1,1,1,1,1);export_population(self.hs,copies,out)
            path=out/'persons.csv';lines=path.read_text().splitlines(keepends=True)
            if change=='missing':lines.pop()
            elif change=='duplicate':lines.append(lines[-1])
            elif change=='attribute':lines[1]=lines[1].replace(',70,',',69,')
            else:lines[1]=lines[1].replace('hh000000001','unknown')
            path.write_text(''.join(lines))
            with self.assertRaises(PopulationDataError):audit_population(self.hs,copies,out)

    def test_export_refuses_overwrite_invalid_copies_and_limits(self):
        out=self.root/'out';export_population(self.hs,(1,0,0,0,0),out)
        with self.assertRaises(PopulationDataError):export_population(self.hs,(0,1,0,0,0),out)
        for copies in [(1,),(True,0,0,0,0),(-1,2,0,0,0),(1000001,0,0,0,0)]:
            with self.assertRaises(PopulationDataError):export_population(self.hs,copies,self.root/'bad')

    def test_weighted_integer_and_person_reference_are_separate(self):
        weights=household_weights(self.hs,self.controls,'baseline');copies=integerize(weights,10,20261018)
        result=evaluate_households(self.hs,weights,copies,self.controls,self.reference)
        self.assertAlmostEqual(result['weighted']['tvd'],7/30)
        self.assertEqual(result['integer']['households'],10)
        self.assertEqual(result['integer']['persons'],sum(h.size*n for h,n in zip(self.hs,copies)))
        self.assertNotEqual(result['weighted']['persons'],result['person_reference']['persons'])
        self.assertEqual(result['person_reference']['weight'],'PWGTP')
