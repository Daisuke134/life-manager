from dataclasses import replace
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from manager.population.contracts import PopulationDataError
from manager.population.households import Person, Household, HouseholdControls
from manager.population.pums import read_pums, read_controls
from manager.population.household_sources import verify_sources, fetch_household_sources
from household_helpers import fixture,rows,zip_rows,H_FIELDS,P_FIELDS

class PumsTests(unittest.TestCase):
    def test_join_preserves_whole_households_and_excludes_vacant_gq(self):
        with tempfile.TemporaryDirectory() as d:
            root=fixture(d);hs,stats=read_pums(root/'housing.zip',root/'persons.zip')
            self.assertEqual(len(hs),5);self.assertEqual(sum(h.size for h in hs),11)
            self.assertEqual(tuple(p.age for p in hs[2].persons),(38,10,7))
            self.assertEqual(stats['vacant_units'],1);self.assertEqual(stats['group_quarters_persons'],1)
            self.assertEqual(verify_sources(root)['state'],'44')

    def test_missing_duplicate_or_mismatched_person_rejected(self):
        hs,ps=rows()
        variants=[ps[:-2]+ps[-1:],ps+[ps[0]],[dict(p,STATE='06') if i==0 else p for i,p in enumerate(ps)],
                  [dict(p,PWGTP='-1') if i==0 else p for i,p in enumerate(ps)],
                  [dict(p,SERIALNO='unknown') if i==0 else p for i,p in enumerate(ps)]]
        for people in variants:
            with tempfile.TemporaryDirectory() as d,self.assertRaises(PopulationDataError):
                root=fixture(d,persons=people);read_pums(root/'housing.zip',root/'persons.zip')

    def test_invalid_household_and_mutable_members_rejected(self):
        p=Person('A',1,40,1,20,1)
        with self.assertRaises(PopulationDataError):Household('A',1,4,1,[p])
        for args in [('A',0,40,1,20,1),('A',1,100,1,20,1),('A',1,40,3,20,1),('A',1,40,1,20,0)]:
            with self.assertRaises(PopulationDataError):Person(*args)
        with self.assertRaises(PopulationDataError):Household('A',1,1,1,(p,))
        with self.assertRaises(PopulationDataError):HouseholdControls(10,(9,1),(5,3,2))

    def test_controls_are_marginals_without_joint(self):
        with tempfile.TemporaryDirectory() as d:
            root=fixture(d);c,reference=read_controls(root/'b11016.dat')
            self.assertEqual(reference,(0,3,2,4,1,0));self.assertEqual(c.family,(5,5));self.assertEqual(c.size,(4,4,2))
            self.assertEqual(set(c.__dataclass_fields__),{'total','family','size'})

    def test_tampered_input_and_wrong_zip_member_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=fixture(d);(root/'housing.zip').write_bytes(b'bad')
            with self.assertRaises(PopulationDataError):verify_sources(root)
            with self.assertRaises(PopulationDataError):read_pums(root/'housing.zip',root/'persons.zip')
        with tempfile.TemporaryDirectory() as d:
            root=fixture(d)
            with zipfile.ZipFile(root/'housing.zip','w') as z:z.writestr('../psam_h44.csv','bad')
            with self.assertRaises(PopulationDataError):read_pums(root/'housing.zip',root/'persons.zip')

    def test_fetch_roundtrip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=fixture(Path(d)/'mock');out=Path(d)/'out'
            def response(url,**kwargs):
                from manager.population.household_sources import URLS
                name=next(k for k,v in URLS.items() if v==url)
                return io.BytesIO((root/name).read_bytes())
            with patch('manager.population.household_sources.urlopen',side_effect=response):fetch_household_sources(out)
            self.assertEqual(verify_sources(out)['state'],'44')
            with self.assertRaises(PopulationDataError):fetch_household_sources(out)

    def test_duplicate_member_and_limit_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=fixture(d)
            with zipfile.ZipFile(root/'housing.zip','a') as z:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore');z.writestr('psam_h44.csv','bad')
            with self.assertRaises(PopulationDataError):read_pums(root/'housing.zip',root/'persons.zip')
        with tempfile.TemporaryDirectory() as d,patch('manager.population.household_sources.urlopen',return_value=io.BytesIO(b'x'*100)):
            with self.assertRaises(PopulationDataError):fetch_household_sources(Path(d)/'out',max_zip_bytes=10)
            self.assertFalse((Path(d)/'out/source.json').exists())
