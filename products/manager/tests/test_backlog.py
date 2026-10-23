"""Machine-check the dependency graph, task clarity, and vendored imozuru evidence check."""
import json
import subprocess
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BacklogTest(unittest.TestCase):
    def test_tasks_acyclic_and_atomic(self):
        tasks = json.loads((ROOT/'docs/roadmap/tasks.json').read_text(encoding='utf8'))
        seen = set()
        for t in tasks:
            self.assertNotIn(t['id'], seen)
            self.assertTrue(t['learn'])
            self.assertTrue(t['change'])
            self.assertTrue(t['verify'])
            self.assertTrue(set(t['depends']) <= seen,
                            f"unresolved dependency in {t['id']}")
            self.assertIn(t['status'], ('done', 'todo', 'blocked', 'skipped'))
            if t['status'] == 'skipped':
                self.assertTrue(t.get('waiver_reason') and t.get('waiver_scope'))
            seen.add(t['id'])
        self.assertGreaterEqual(len(seen), 60)

    def test_official_imozuru_source_blob_matches(self):
        # GitHub exposed upstream blob SHA at read time, checked via Git-compatible SHA1.
        expected = '493b759fcee8328c3dcfc61ba21148afe5957040'
        import hashlib
        blob = (ROOT/'tools/imozuru/report.py').read_bytes()
        actual = hashlib.sha1(f'blob {len(blob)}\0'.encode()+blob).hexdigest()
        self.assertEqual(expected, actual)

    def test_imozuru_official_report_passes(self):
        p = subprocess.run([sys.executable, 'tools/imozuru/report.py',
                           'research/imozuru/manager-foundations', '--check'],
                           cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertIn('7', p.stdout)

    def test_imozuru_report_rejects_false_quotes(self):
        import importlib.util
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            topic = Path(tmp)
            (topic/'sources').mkdir()
            (topic/'sources/quote.md').write_text('true\n',encoding='utf8')
            (topic/'extracts.json').write_text(json.dumps({
                'title': 'test', 'question':'test', 'stopped':'test',
                'claims':[{'claim':'false claim','status':'付いた',
                           'quotes':[{'file':'quote.md','line':1,'text':'false'}]}]
            }),encoding='utf8')
            p=subprocess.run([sys.executable,'tools/imozuru/report.py',str(topic),'--check'],
                             cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(p.returncode, 1)
            self.assertIn('原文に見つからない',p.stdout)

    def test_phase06_checkpoint_keeps_scope_waivers_and_scientific_fences(self):
        """Research progress never proves a retired trial or human outcome."""
        tasks=json.loads((ROOT/'docs/roadmap/tasks.json').read_text(encoding='utf8'))
        by_id={t['id']:t for t in tasks}
        self.assertEqual(by_id['F004']['status'],'skipped')
        self.assertEqual(by_id['F007']['status'],'skipped')
        for task_id in ('F005', 'F006', 'F008', 'F009'):
            self.assertEqual(by_id[task_id]['evidence_scope'], 'OWNED_PUBLIC_DIGITAL_P2_ONLY')
            self.assertEqual(by_id[task_id]['beneficiary_outcome'], 'NOT_MEASURED')
        demo=json.loads((ROOT/'docs/verification/PHASE05_OFFLINE_DEMO_RESULTS.json').read_text(encoding='utf8'))
        self.assertEqual(demo['field_beneficiary_improvements_verified'],0)
        self.assertEqual(demo['scientific_gate1'],'UNMET')

    def test_waived_h005_preserves_unmet_causal_replication(self):
        tasks=json.loads((ROOT/'docs/roadmap/tasks.json').read_text(encoding='utf8'))
        by_id={t['id']:t for t in tasks}
        self.assertEqual(by_id['H005']['status'],'skipped')
        self.assertNotIn('H005',by_id['H006']['depends'])
        self.assertTrue(all(by_id[f'H{i:03d}']['status']=='done' for i in range(6,11)))
        self.assertTrue(all(by_id[f'H{i:03d}'].get('original_verify') for i in range(6,11)))
        metrics=json.loads((ROOT/'docs/research/heartsteps/PHASE03_PUBLIC_METRICS.json').read_text(encoding='utf8'))
        self.assertEqual(metrics['original_paper_replication'],'NOT_ACHIEVED')
        self.assertFalse(metrics['exploratory_associations']['causal_effect_estimated'])
        self.assertEqual(metrics['selected_available_decisions'],6330)
