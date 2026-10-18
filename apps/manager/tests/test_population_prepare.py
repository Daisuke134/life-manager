from dataclasses import fields, replace
import tempfile
import unittest
from manager.population.prepare import aggregate_b17001, marginalize, partition_tables, build_seed
from manager.population.acs import read_acs_extract
from manager.population.contracts import Marginals, PopulationDataError
from helpers import write_fixture, source

class PrepareTests(unittest.TestCase):
    def tables(self):
        with tempfile.TemporaryDirectory() as d:
            src,rows=read_acs_extract(write_fixture(d))
        return tuple(aggregate_b17001(r,src) for r in rows if not r['GEO_ID'].endswith('72'))

    def test_leaf_mapping_and_total(self):
        row={'GEO_ID':'0400000US01',**{f'B17001_E{i:03}':str(i) for i in range(1,60)}}
        row.update(B17001_E001='1638',B17001_E002='442',B17001_E031='1196')
        table=aggregate_b17001(row,source())
        self.assertEqual(table.counts,(162,190,90,510,480,206))
        row['B17001_E002']='443'
        with self.assertRaises(PopulationDataError):aggregate_b17001(row,source())

    def test_split_is_fixed_and_order_independent(self):
        tables=self.tables();a=partition_tables(tables);b=partition_tables(tuple(reversed(tables)))
        self.assertEqual(a,b)
        self.assertEqual([len(a[k]) for k in ('development','validation','test')],[6,4,41])
        with self.assertRaises(PopulationDataError):partition_tables(tables[:-1])
        with self.assertRaises(PopulationDataError):partition_tables(tables+(tables[0],))

    def test_test_joint_cannot_change_seed(self):
        tables=self.tables();before=partition_tables(tables)
        test_geo=before['test'][0].geo_id
        changed=tuple(replace(t,counts=tuple(x*2 for x in t.counts),total=t.total*2) if t.geo_id==test_geo else t for t in tables)
        self.assertEqual(build_seed(before['development']),build_seed(partition_tables(changed)['development']))
        with self.assertRaises(PopulationDataError):build_seed(before['test'][:6])

    def test_marginals_carry_no_joint_fields(self):
        self.assertEqual([x.name for x in fields(Marginals)],['geo_id','source','poverty','age','total'])
        m=marginalize(self.tables()[0]);self.assertEqual(m.poverty,(26,26));self.assertEqual(m.age,(24,20,8))
