"""Cost source declarations come from execution releases, never billing payloads."""
import importlib
import json
import tempfile
import unittest
from pathlib import Path


OWNER = 'alpaca-investment-paper'
CATALOG_RELATIVE = 'apps/life-manager/config/product-loop-catalog.json'


def release_fixture(root, sha='a' * 40):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'RELEASE.json').write_text(json.dumps({'sha': sha, 'release_paths': 'ALL'}))
    path = root / 'apps/life-manager/config/product-loop-catalog.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'loops': [{'id': 'investment', 'job_ids': [OWNER],
        'cost_source_inventory': {'schema_version': 1, 'status': 'unverified', 'sources': []}}]}))
    return path


class CostInventoryTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module('cost_inventory')
        except ModuleNotFoundError:
            self.fail('cost_inventory producer is missing')

    def test_declaration_is_recorded_once_and_never_a_zero_cost_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); release_fixture(root / 'release')
            ledger = root / 'receipts.jsonl'
            kwargs = dict(release_root=root / 'release', owner_id=OWNER,
                          run_id='physical-run', occurrence_id=f'{OWNER}:claimed-old-run')
            first = self.module().record_source_inventory(ledger, **kwargs)
            second = self.module().record_source_inventory(ledger, **kwargs)
            rows = [json.loads(line) for line in ledger.read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertTrue(first['appended']); self.assertFalse(second['appended'])
            self.assertEqual(first['coverage_state'], 'gap')
            self.assertEqual(rows[0]['release_sha'], 'a' * 40)
            self.assertEqual(rows[0]['run_id'], 'physical-run')
            self.assertEqual(rows[0]['occurrence_id'], f'{OWNER}:claimed-old-run')
            self.assertEqual(rows[0]['receipt_type'], 'cost_source_inventory')
            self.assertNotIn('amount', rows[0]); self.assertNotIn('model_cost_usd', rows[0])
            release_fixture(root / 'release-b', 'b' * 40)
            self.module().record_source_inventory(ledger, **{**kwargs, 'release_root': root / 'release-b'})
            self.assertEqual(len(ledger.read_text().splitlines()), 2)

    def test_catalog_declares_unverified_sources_without_guessing_accounts(self):
        root = Path(__file__).resolve().parents[2]
        catalog = json.loads((root / CATALOG_RELATIVE).read_text())
        investment = next(row for row in catalog['loops'] if row['id'] == 'investment')
        self.assertEqual(investment.get('cost_source_inventory'),
                         {'schema_version': 1, 'status': 'unverified', 'sources': []})

    def test_missing_release_or_host_identity_does_not_fabricate_a_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); ledger=root/'receipts.jsonl'
            kwargs=dict(release_root=root/'missing', owner_id=OWNER,
                        run_id='run', occurrence_id=f'{OWNER}:run')
            result=self.module().record_source_inventory(ledger, **kwargs)
            self.assertEqual(result['coverage_state'], 'gap')
            self.assertFalse(ledger.exists())
            release_fixture(root/'release')
            result=self.module().record_source_inventory(ledger, **{**kwargs,'release_root':root/'release','run_id':None})
            self.assertEqual(result['coverage_state'], 'gap')
            self.assertFalse(ledger.exists())

    def test_same_release_changed_catalog_preserves_original_and_records_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); catalog=release_fixture(root/'release'); ledger=root/'receipts.jsonl'
            kwargs=dict(release_root=root/'release',owner_id=OWNER,run_id='run',occurrence_id=f'{OWNER}:run')
            self.module().record_source_inventory(ledger, **kwargs)
            original=ledger.read_text().splitlines()[0]
            data=json.loads(catalog.read_text()); data['loops'][0]['cost_source_inventory']['status']='verified'
            catalog.write_text(json.dumps(data))
            result=self.module().record_source_inventory(ledger, **kwargs)
            self.assertEqual(result['reason'],'source_declaration_conflict')
            rows=ledger.read_text().splitlines()
            self.assertEqual(rows[0],original)
            self.assertEqual(json.loads(rows[1])['receipt_type'],'cost_source_inventory_conflict')
