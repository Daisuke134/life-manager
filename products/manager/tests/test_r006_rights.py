"""R006: public availability cannot silently imply commercial or redistribution rights."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SourceRightsTests(unittest.TestCase):
    def test_manifest_explicit_rights_and_evidence(self):
        records = json.loads((ROOT/'docs/research/source-rights.json').read_text(encoding='utf-8'))
        expected = {'heartsteps-v1-data', 'socsci210-data', 'concordia-code', 'imozuru-code'}
        by_id = {x['id']: x for x in records['sources']}
        self.assertTrue(expected <= set(by_id))
        for rec in records['sources']:
            self.assertTrue(rec['source_url'].startswith('https://'))
            self.assertTrue(rec['license_evidence_url'].startswith('https://'))
            self.assertTrue(rec['license_expression'])
            for key in ('study_read', 'local_research', 'raw_redistribution', 'product_use'):
                self.assertIn(rec['permissions'][key], ('allowed_with_conditions', 'hold', 'not_applicable'))
        self.assertEqual(by_id['socsci210-data']['permissions']['raw_redistribution'], 'hold')
        self.assertEqual(by_id['socsci210-data']['permissions']['product_use'], 'hold')
        self.assertEqual(by_id['heartsteps-v1-data']['permissions']['raw_redistribution'], 'hold')
        self.assertEqual(by_id['concordia-code']['license_expression'], 'Apache-2.0')
        self.assertEqual(by_id['imozuru-code']['license_expression'], 'MIT')
        self.assertEqual(by_id['socrates-llama3-model']['permissions']['product_use'], 'hold')

    def test_study_note_includes_lawful_boundaries(self):
        md = (ROOT/'docs/research-rights.md').read_text(encoding='utf-8')
        self.assertIn('HeartSteps', md)
        self.assertIn('SocSci210', md)
        self.assertIn('imozuru', md)
        self.assertIn('Concordia', md)
        self.assertIn('再配布', md)
        self.assertIn('個人情報', md)
        self.assertIn('不明', md)

    def test_task_is_done_and_generator_non_destructive(self):
        tasks = json.loads((ROOT/'docs/roadmap/tasks.json').read_text(encoding='utf-8'))
        self.assertEqual(next(t['status'] for t in tasks if t['id']=='R006'), 'done')
        with TemporaryDirectory() as tmp:
            tr = Path(tmp)
            (tr/'docs/roadmap').mkdir(parents=True)
            (tr/'scripts').mkdir()
            original = ROOT/'docs/roadmap/tasks.json'
            shutil.copyfile(original,tr/'docs/roadmap/tasks.json')
            shutil.copyfile(ROOT/'docs/roadmap/ATOMIC_BACKLOG.md',tr/'docs/roadmap/ATOMIC_BACKLOG.md')
            shutil.copyfile(ROOT/'scripts/make_roadmap.py',tr/'scripts/make_roadmap.py')
            p = subprocess.run([sys.executable, str(tr/'scripts/make_roadmap.py'), '--check'],
                               cwd=tr, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual((tr/'docs/roadmap/tasks.json').read_bytes(), original.read_bytes(),
                             'roadmap renderer must NEVER discard statuses or extra tasks')

if __name__ == '__main__':
    unittest.main()
