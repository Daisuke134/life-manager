"""Cost source declarations come from execution releases, never billing payloads."""
import importlib
import copy
import json
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import effect_store
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

    def test_capture_io_failure_is_a_visible_gap_with_unknown_append_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); release_fixture(root / 'release')
            module = self.module()
            with patch.object(module, '_append_once', side_effect=OSError('isolated write failure')):
                result = module.record_source_inventory(root / 'receipts.jsonl', release_root=root / 'release',
                    owner_id=OWNER, run_id='run', occurrence_id=f'{OWNER}:run')
            self.assertEqual(result['coverage_state'], 'gap')
            self.assertEqual(result['reason'], 'source_inventory_write_failed')
            self.assertEqual(result['error_class'], 'OSError')
            self.assertIsNone(result['appended'])
            self.assertFalse((root / 'receipts.jsonl').exists())

    def test_concurrent_divergent_declarations_use_one_atomic_ledger_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); release_fixture(root / 'release-a')
            catalog = release_fixture(root / 'release-b')
            data = json.loads(catalog.read_text())
            data['loops'][0]['cost_source_inventory']['status'] = 'verified'
            catalog.write_text(json.dumps(data))
            ledger = root / 'receipts.jsonl'
            barrier = threading.Barrier(2)
            flock = effect_store.fcntl.flock
            def synchronize(descriptor, operation):
                if operation == effect_store.fcntl.LOCK_EX:
                    barrier.wait(timeout=3)
                return flock(descriptor, operation)
            def capture(name):
                return self.module().record_source_inventory(ledger, release_root=root / name,
                    owner_id=OWNER, run_id=name, occurrence_id=f'{OWNER}:{name}')
            with patch.object(effect_store.fcntl, 'flock', side_effect=synchronize):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    results = list(executor.map(capture, ('release-a', 'release-b')))
            rows = [json.loads(line) for line in ledger.read_text().splitlines()]
            self.assertEqual(sum(row['receipt_type'] == 'cost_source_inventory' for row in rows), 1)
            self.assertEqual(sum(row['receipt_type'] == 'cost_source_inventory_conflict' for row in rows), 1)
            self.assertEqual(sum(row['reason'] == 'source_declaration_conflict' for row in results), 1)

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


class IndependentCensusTests(unittest.TestCase):
    def fixture(self):
        trip = {'order_ids': ['entry', 'exit'], 'period_start': '2026-10-18T01:00:00Z',
                'closed_at': '2026-10-18T02:00:00Z', 'source_receipt_ids': ['fill://entry', 'fill://exit']}
        def event(run, sha, phase, stamp):
            return {'event_id': run + '-' + phase, 'owner_id': OWNER, 'job_id': OWNER,
                'run_id': run, 'occurrence_id': f'{OWNER}:claimed-before-{run}', 'release_sha': sha,
                'timestamp': stamp, 'phase': phase, 'status': 'running' if phase == 'execute' else 'pass',
                'loaded_argv_sha256': 'd' * 64, 'loaded_env_sha256': 'e' * 64,
                'evidence_refs': [f'lm-loop://{OWNER}/{run}/summary.json']}
        runtime = {OWNER: [event('physical-a', 'a' * 40, 'execute', '2026-10-18T01:01:00Z'),
                           event('physical-a', 'a' * 40, 'report', '2026-10-18T01:02:00Z'),
                           event('physical-b', 'b' * 40, 'execute', '2026-10-18T01:30:00Z'),
                           event('physical-b', 'b' * 40, 'report', '2026-10-18T01:31:00Z')]}
        admissions = {OWNER: [{'owner_id': OWNER, 'occurrence_id': f'{OWNER}:claimed-before-{run}',
                    'queued_at': '2026-10-18T00:59:00Z', 'state': 'released', 'effect_unknown': 0}
                    for run in ('physical-a', 'physical-b')]}
        releases = {}
        for letter in ('a', 'b'):
            releases[letter * 40] = [{'receipt_type': 'cost_source_inventory', 'release_sha': letter * 40,
                'catalog_sha256': letter * 64, 'execution_owner_ids': [OWNER],
                'source_declaration': {'schema_version': 1, 'status': 'verified', 'sources': [{
                    'execution_owner_id': OWNER, 'beneficiary_owner_id': OWNER, 'beneficiary_mode': 'paper',
                    'provider': 'provider-' + letter, 'billing_account_ref': 'account-' + letter,
                    'covered_categories': ['model_cost', 'tool_cost', 'browser_cost', 'infra_cost'],
                    'attribution': 'exact_evidence_required', 'evidence_refs': ['registry://source/' + letter]}]},
                'evidence_refs': ['lm-release://' + letter * 40 + '/catalog']}]
        return [trip], dict(beneficiary_owner_id=OWNER, observed_at='2026-10-18T03:00:00Z',
            runtime_rows_by_owner=runtime, occurrence_rows_by_owner=admissions,
            release_inputs=releases, paid_bindings=[])

    def invoke(self, trips, kwargs):
        function = getattr(importlib.import_module('cost_inventory'), 'build_expected_inventory', None)
        self.assertTrue(callable(function), 'independent runtime census is missing')
        before = copy.deepcopy((trips, kwargs))
        result = function(trips, **kwargs)
        self.assertEqual((trips, kwargs), before, 'pure census must not mutate its inputs')
        return result

    def reasons(self, result):
        return {gap['reason'] for gap in result.get('gaps', [])
                + [gap for scope in result['scopes'] for gap in scope['gaps']]}

    def test_union_is_from_executing_releases_and_known_paid_lower_bound(self):
        trips, kwargs = self.fixture()
        kwargs['paid_bindings'] = [{'receipt_id': 'paid://known', 'provider': 'older-provider',
            'billing_account_ref': 'older-account', 'category': 'infra_cost',
            'order_ids': ['entry', 'exit'], 'period_start': trips[0]['period_start'],
            'period_end': trips[0]['closed_at'], 'evidence_refs': ['invoice://known'],
            'charge_identity': ['older-provider', 'invoice', 'document', 'line', 'allocation'],
            'identity_aliases': [['charge', 'older-provider', 'invoice', 'document', 'line', 'allocation'],
                                 ['receipt', 'paid://alias']]}]
        result = self.invoke(trips, kwargs)
        scope = result['scopes'][0]
        self.assertEqual({row['provider'] for row in scope['required_sources']},
                         {'provider-a', 'provider-b', 'older-provider'})
        self.assertEqual(len(scope['required_sources']), 9)
        self.assertEqual(result['coverage_state'], 'gap')
        self.assertEqual(result['reason'], 'cost_coverage_not_evaluated')
        self.assertIn('history_coverage_unverified', self.reasons(result))
        self.assertNotIn('model_cost_usd', result)
        self.assertNotIn('net_realized_pnl_usd', result)
        self.assertEqual(scope['known_paid_bindings'][0]['charge_identity'],
                         kwargs['paid_bindings'][0]['charge_identity'])

    def test_physical_runs_keep_actual_claimed_occurrences(self):
        trips, kwargs = self.fixture(); result = self.invoke(trips, kwargs)
        refs = result['scopes'][0]['execution_refs']
        self.assertEqual({row['run_id'] for row in refs}, {'physical-a', 'physical-b'})
        self.assertEqual({row['occurrence_id'] for row in refs},
                         {f'{OWNER}:claimed-before-physical-a', f'{OWNER}:claimed-before-physical-b'})
        self.assertNotIn('admission_missing', self.reasons(result))
        kwargs['occurrence_rows_by_owner'][OWNER][0]['occurrence_id'] = f'{OWNER}:physical-a'
        self.assertIn('admission_missing', self.reasons(self.invoke(trips, kwargs)))

    def test_conflicting_events_and_unfinished_runs_stay_gaps(self):
        for defect in ('event', 'unfinished', 'release', 'hash', 'admission'):
            with self.subTest(defect=defect):
                trips, kwargs = self.fixture(); rows = kwargs['runtime_rows_by_owner'][OWNER]
                if defect == 'event':
                    changed = dict(rows[0], loaded_env_sha256='f' * 64); rows.append(changed)
                    expected = 'runtime_event_conflict'
                elif defect == 'unfinished':
                    rows.pop(); expected = 'runtime_terminal_missing'
                elif defect == 'release':
                    kwargs['release_inputs'].pop('a' * 40); expected = 'source_release_missing'
                elif defect == 'hash':
                    rows[1]['loaded_argv_sha256'] = 'f' * 64; expected = 'runtime_identity_mismatch'
                else:
                    kwargs['occurrence_rows_by_owner'][OWNER][0]['effect_unknown'] = 1
                    expected = 'admission_unresolved'
                self.assertIn(expected, self.reasons(self.invoke(trips, kwargs)))

    def test_source_conflicts_unverified_accounts_and_paid_unknowns_are_not_zero(self):
        for defect, expected in [('conflict', 'source_declaration_conflict'),
                                 ('unverified', 'source_declaration_unverified'),
                                 ('account', 'source_account_missing'),
                                 ('paid', 'paid_account_missing')]:
            with self.subTest(defect=defect):
                trips, kwargs = self.fixture(); row = kwargs['release_inputs']['a' * 40][0]
                if defect == 'conflict':
                    kwargs['release_inputs']['a' * 40].append(dict(row,
                        receipt_type='cost_source_inventory_conflict', catalog_sha256='f' * 64))
                elif defect == 'unverified': row['source_declaration']['status'] = 'unverified'
                elif defect == 'account': row['source_declaration']['sources'][0].pop('billing_account_ref')
                else:
                    kwargs['paid_bindings'] = [{'receipt_id': 'paid://known', 'provider': 'old-provider',
                        'category': 'model_cost', 'order_ids': ['entry', 'exit'],
                        'period_start': trips[0]['period_start'], 'period_end': trips[0]['closed_at'],
                        'charge_identity': ['old-provider', 'invoice', 'doc', 'line', 'allocation'],
                        'evidence_refs': ['invoice://known']}]
                self.assertIn(expected, self.reasons(self.invoke(trips, kwargs)))

    def test_owner_period_is_explicit_and_empty_trips_are_not_a_free_day(self):
        trips, kwargs = self.fixture()
        scope = {**trips[0], 'scope_kind': 'owner_period', 'owner_id': OWNER, 'mode': 'paper',
                 'paper': True, 'period_end': trips[0]['closed_at'], 'order_ids': []}
        result = self.invoke([scope], kwargs)
        self.assertEqual(result['scopes'][0]['scope_kind'], 'owner_period')
        self.assertEqual(result['scopes'][0]['order_ids'], [])
        self.assertIn('scope_missing', self.reasons(self.invoke([], kwargs)))
        scope['owner_id'] = 'alpaca-investment-live'
        self.assertIn('scope_invalid', self.reasons(self.invoke([scope], kwargs)))

    def test_historical_conflict_outside_scope_does_not_poison_future_period(self):
        trips, kwargs = self.fixture()
        old = copy.deepcopy(kwargs['runtime_rows_by_owner'][OWNER][:2])
        for row in old:
            row['run_id'] = 'historical-run'
            row['event_id'] = 'historical-' + row['phase']
            row['timestamp'] = row['timestamp'].replace('2026-10-18', '2026-10-17')
            row['release_sha'] = 'f' * 40
        kwargs['runtime_rows_by_owner'][OWNER].extend([*old, dict(old[0], loaded_env_sha256='f' * 64)])
        result = self.invoke(trips, kwargs)
        self.assertNotIn('runtime_event_conflict', self.reasons(result))
        self.assertNotIn('source_release_missing', self.reasons(result))
        self.assertEqual(len(result['scopes'][0]['execution_refs']), 2)

    def test_paid_lower_bound_keeps_scope_and_source_identity_and_rejects_foreign_mode(self):
        trips, kwargs = self.fixture()
        paid = {'receipt_id': 'paid://known', 'provider': 'older-provider',
            'billing_account_ref': 'older-account', 'category': 'infra_cost',
            'owner_id': OWNER, 'mode': 'paper', 'paper': True,
            'order_ids': ['entry', 'exit'], 'period_start': trips[0]['period_start'],
            'period_end': trips[0]['closed_at'], 'evidence_refs': ['invoice://known'],
            'charge_identity': ['older-provider', 'invoice', 'document', 'line', 'allocation'],
            'identity_aliases': [['charge', 'older-provider', 'invoice', 'document', 'line', 'allocation'],
                                 ['receipt', 'paid://alias']], 'amount_usd': 'DO_NOT_COPY_MONEY'}
        kwargs['paid_bindings'] = [paid]
        result = self.invoke(trips, kwargs)
        preserved = result['scopes'][0]['known_paid_bindings'][0]
        for key in ('provider', 'billing_account_ref', 'category', 'order_ids', 'period_start', 'period_end'):
            self.assertEqual(preserved[key], paid[key])
        self.assertNotIn('amount_usd', preserved)
        for key, value in [('owner_id', 'alpaca-investment-live'), ('mode', 'live'), ('paper', False)]:
            with self.subTest(key=key):
                kwargs['paid_bindings'] = [{**paid, key: value}]
                result = self.invoke(trips, kwargs)
                self.assertIn('paid_binding_scope_invalid', self.reasons(result))
                self.assertFalse(result['scopes'][0]['known_paid_bindings'])

    def test_shared_validation_execution_is_not_relabelled_as_paper_execution(self):
        trips, kwargs = self.fixture(); validation = 'investment-strategy-validation'
        snapshot = kwargs['release_inputs']['a' * 40][0]
        snapshot['execution_owner_ids'].append(validation)
        source = copy.deepcopy(snapshot['source_declaration']['sources'][0])
        source.update(execution_owner_id=validation, provider='validation-provider',
                      billing_account_ref='validation-account', covered_categories=['model_cost'])
        snapshot['source_declaration']['sources'].append(source)
        kwargs['runtime_rows_by_owner'][validation] = [
            {**row, 'owner_id': validation, 'job_id': validation, 'run_id': 'validation-run',
             'occurrence_id': f'{validation}:claimed-validation', 'event_id': 'validation-' + row['phase']}
            for row in kwargs['runtime_rows_by_owner'][OWNER][:2]]
        kwargs['occurrence_rows_by_owner'][validation] = [{'owner_id': validation,
            'occurrence_id': f'{validation}:claimed-validation', 'queued_at': '2026-10-18T00:59:00Z',
            'state': 'released', 'effect_unknown': 0}]
        result = self.invoke(trips, kwargs); scope = result['scopes'][0]
        self.assertEqual(scope['owner_id'], OWNER)
        self.assertEqual({row['execution_owner_id'] for row in scope['execution_refs']}, {OWNER, validation})
        self.assertIn('shared_attribution_unproven', self.reasons(result))
        self.assertEqual(next(row for row in scope['required_sources'] if row['provider'] == 'validation-provider')
                         ['execution_owner_ids'], [validation])

    def test_malformed_runtime_status_and_unassigned_sources_are_visible_gaps(self):
        for defect in ('runtime-status', 'source-beneficiary'):
            with self.subTest(defect=defect):
                trips, kwargs = self.fixture()
                if defect == 'runtime-status':
                    kwargs['runtime_rows_by_owner'][OWNER][1]['status'] = []
                    expected = 'runtime_event_invalid'
                else:
                    source = copy.deepcopy(kwargs['release_inputs']['a' * 40][0]['source_declaration']['sources'][0])
                    source.pop('beneficiary_owner_id')
                    source['provider'] = 'unassigned-provider'
                    kwargs['release_inputs']['a' * 40][0]['source_declaration']['sources'].append(source)
                    expected = 'source_invalid'
                self.assertIn(expected, self.reasons(self.invoke(trips, kwargs)))
