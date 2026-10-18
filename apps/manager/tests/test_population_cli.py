import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from manager.cli import main
from manager.artifacts import read_artifact, write_artifact
from manager.population.contracts import PopulationDataError
from helpers import write_fixture

class CliTests(unittest.TestCase):
    def run_offline(self,root):
        root=Path(root);extract=write_fixture(root/'input');prepared=root/'prepared'
        self.assertEqual(main(['prepare-population','--input',str(extract),'--out',str(prepared)]),0)
        paths=[]
        for method in ('independent','ipf'):
            p=root/(method+'.jsonl');paths.append(p)
            self.assertEqual(main(['reconstruct','--seed',str(prepared/'seed.json'),'--marginals',str(prepared/'marginals.jsonl'),'--method',method,'--out',str(p)]),0)
        args=['score-population','--reference',str(prepared/'reference/all.jsonl'),'--manifest',str(prepared/'manifest.json'),'--out',str(root/'report')]
        for p in paths:args+=['--predictions',str(p)]
        self.assertEqual(main(args),0)
        return read_artifact(root/'report/report.json')

    def test_offline_cli_is_reproducible(self):
        with tempfile.TemporaryDirectory() as d,patch('manager.population.acs.urlopen',side_effect=AssertionError('offline')):
            a=self.run_offline(Path(d)/'a');b=self.run_offline(Path(d)/'b')
            self.assertEqual(a['partitions'],b['partitions'])
            self.assertEqual((Path(d)/'a/ipf.jsonl').read_bytes(),(Path(d)/'b/ipf.jsonl').read_bytes())

    def test_reconstruct_never_opens_reference(self):
        with tempfile.TemporaryDirectory() as d:
            self.run_offline(d);root=Path(d)
            original=Path.read_text
            def guarded(path,*a,**k):
                if 'reference' in path.parts:raise AssertionError('reference leakage')
                return original(path,*a,**k)
            with patch.object(Path,'read_text',guarded):
                self.assertEqual(main(['reconstruct','--seed',str(root/'prepared/seed.json'),'--marginals',str(root/'prepared/marginals.jsonl'),'--method','ipf','--out',str(root/'fresh.jsonl')]),0)

    def test_hash_mismatch_and_existing_different_output_fail(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.json';write_artifact(p,{'x':1})
            self.assertEqual(read_artifact(p),{'x':1})
            with self.assertRaises(PopulationDataError):write_artifact(p,{'x':2})
            p.write_text(p.read_text().replace('"x":1','"x":2'))
            with self.assertRaises(PopulationDataError):read_artifact(p)

    def test_complete_report_has_all_methods_regions_and_cost_scope(self):
        with tempfile.TemporaryDirectory() as d:
            report=self.run_offline(d)
            self.assertEqual(report['coverage'],{'regions':51,'methods':2})
            self.assertEqual(report['paid_model_calls'],0)
            self.assertEqual(report['tracks']['field'],'not_run')
            self.assertEqual({k:v['region_count'] for k,v in report['partitions'].items()},{'development':6,'validation':4,'test':41})

    def test_score_rejects_tampered_prediction_and_stale_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            self.run_offline(d);root=Path(d)
            args=['score-population','--reference',str(root/'prepared/reference/all.jsonl'),'--manifest',str(root/'prepared/manifest.json'),'--predictions',str(root/'ipf.jsonl'),'--predictions',str(root/'independent.jsonl'),'--out',str(root/'bad-report')]
            p=root/'ipf.jsonl';p.write_text(p.read_text().replace('"method":"ipf"','"method":"independent"',1))
            self.assertEqual(main(args),2);self.assertFalse((root/'bad-report/report.json').exists())

    def test_rejects_duplicate_prediction_method(self):
        with tempfile.TemporaryDirectory() as d:
            self.run_offline(d);root=Path(d)
            args=['score-population','--reference',str(root/'prepared/reference/all.jsonl'),'--manifest',str(root/'prepared/manifest.json'),'--predictions',str(root/'ipf.jsonl'),'--predictions',str(root/'ipf.jsonl'),'--out',str(root/'bad-report')]
            self.assertEqual(main(args),2)
