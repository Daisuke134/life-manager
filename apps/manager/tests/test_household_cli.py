from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from manager.cli import main
from manager.artifacts import read_artifact
from household_helpers import fixture

class HouseholdCliTests(unittest.TestCase):
    def run_offline(self,root):
        root=Path(root);fixture(root/'input')
        self.assertEqual(main(['prepare-households','--input',str(root/'input'),'--out',str(root/'prepared')]),0)
        for method in ('baseline','calibrated'):
            self.assertEqual(main(['synthesize-households','--prepared',str(root/'prepared'),'--method',method,'--out',str(root/method)]),0)
        self.assertEqual(main(['score-households','--prepared',str(root/'prepared'),'--run',str(root/'baseline'),'--run',str(root/'calibrated'),'--out',str(root/'report')]),0)
        return read_artifact(root/'report/report.json')

    def test_cli_runs_offline_and_outputs_reproduce(self):
        with tempfile.TemporaryDirectory() as d,patch('manager.population.household_sources.urlopen',side_effect=AssertionError('offline')):
            root=Path(d);a=self.run_offline(root/'a');b=self.run_offline(root/'b')
            self.assertEqual(a['results'],b['results'])
            for name in ('weights.json','households.csv','persons.csv'):
                # Provenance hashes are deterministic for identical fixture bytes.
                self.assertEqual((root/'a/calibrated'/name).read_bytes(),(root/'b/calibrated'/name).read_bytes())
            self.assertEqual(a['stage'],'empirical_household_synthesis');self.assertEqual(a['paid_model_calls'],0)
            self.assertEqual(a['tracks']['field'],'not_run');self.assertEqual(a['sample']['occupied_households'],5)

    def test_synthesize_never_opens_reference(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.run_offline(root);original=Path.open
            def guard(path,*args,**kwargs):
                if path.name=='reference.json':raise AssertionError('reference leakage')
                return original(path,*args,**kwargs)
            with patch.object(Path,'open',guard):
                self.assertEqual(main(['synthesize-households','--prepared',str(root/'prepared'),'--method','calibrated','--out',str(root/'fresh')]),0)

    def test_tampered_csv_and_missing_method_do_not_make_report(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.run_offline(root)
            args=['score-households','--prepared',str(root/'prepared'),'--run',str(root/'baseline'),'--out',str(root/'bad')]
            self.assertEqual(main(args),2)
            path=root/'calibrated/persons.csv';path.write_text(path.read_text()+'bad\n')
            args+=['--run',str(root/'calibrated')]
            self.assertEqual(main(args),2);self.assertFalse((root/'bad/report.json').exists())

    def test_tampered_prepared_input_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.run_offline(root)
            p=root/'prepared/controls.json';p.write_text(p.read_text().replace('"total":10','"total":11'))
            self.assertEqual(main(['synthesize-households','--prepared',str(root/'prepared'),'--method','calibrated','--out',str(root/'bad')]),2)
