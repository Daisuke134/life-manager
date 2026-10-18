"""Read existing private runtime/ledger/admission evidence without writes."""
from datetime import datetime
import hashlib
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import cost_inventory as inventory
import test_cost_inventory as fixtures
from runtime.loop import lm_loop
from runtime.loop.runtime_event import build_runtime_event,build_runtime_start_event


def fixture(root,mode='paper'):
    trips,inputs=fixtures.IndependentCensusTests().fixture()
    if mode=='live':
        trips,inputs=json.loads(json.dumps([trips,inputs]).replace('alpaca-investment-paper','alpaca-investment-live'))
        for rows in inputs['release_inputs'].values():
            for source in rows[0]['source_declaration']['sources']:source['beneficiary_mode']='live'
    owner='alpaca-investment-'+mode;state=root/'state';state.mkdir()
    registry=root/'config/loop-registry.json';registry.parent.mkdir()
    registry.write_text(json.dumps({'loops':{owner:{'state_root':str(state)}}}))
    (root/'RELEASE.json').write_text(json.dumps({'sha':'b'*40,'release_paths':'ALL'}))
    catalog=root/inventory.CATALOG_PATH;catalog.parent.mkdir(parents=True)
    catalog.write_text(json.dumps({'loops':[{'id':'investment','job_ids':[owner],
        'cost_source_inventory':inputs['release_inputs']['b'*40][0]['source_declaration']}]}))
    captured={**inputs['release_inputs']['a'*40][0],'owner_id':owner}
    ledger=state/'receipts.jsonl';ledger.write_text(json.dumps(captured)+'\n');ledger.chmod(0o600)
    events=[]
    for row in inputs['runtime_rows_by_owner'][owner]:
        context=dict(loop_id=owner,domain='financial',run_id=row['run_id'],release_sha=row['release_sha'],
            provider='alpaca',profile_alias=None,effect_class='trade',product_loop_id='investment',
            job_id=owner,owner_id=owner,loaded_argv_sha256=row['loaded_argv_sha256'],loaded_env_sha256=row['loaded_env_sha256'])
        if row['phase']=='execute':native=build_runtime_start_event(**context,occurrence_id=row['occurrence_id'])
        else:native=build_runtime_event(**context,succeeded=True,blocker=None,claimed_occurrence_id=row['occurrence_id'])
        native['timestamp']=row['timestamp'];events.append(native)
    journal=state/'events.jsonl';journal.write_text(''.join(json.dumps(row)+'\n' for row in events));journal.chmod(0o600)
    db=root/'admission-v2.sqlite3'
    with closing(sqlite3.connect(db)) as connection:
        connection.execute('CREATE TABLE occurrences(owner_id TEXT,occurrence_id TEXT,queued_at REAL,state TEXT,effect_unknown INTEGER)')
        connection.executemany('INSERT INTO occurrences VALUES(?,?,?,?,?)',[(owner,r['occurrence_id'],
            datetime.fromisoformat(r['queued_at'].replace('Z','+00:00')).timestamp(),r['state'],r['effect_unknown'])
            for r in inputs['occurrence_rows_by_owner'][owner]])
        connection.commit()
    db.chmod(0o600)
    return owner,state,trips,inputs['observed_at']


def snapshot(root):
    return {str(p.relative_to(root)):(p.stat().st_mode,hashlib.sha256(p.read_bytes()).hexdigest())
        for p in root.rglob('*') if p.is_file()}


def reasons(result):return {g['reason'] for g in result['gaps']+[g for s in result['scopes'] for g in s['gaps']]}


class CostInventoryReaderTests(unittest.TestCase):
    def read(self,root,state,trips,observed,owner):
        reader=getattr(inventory,'read_expected_inventory',None)
        self.assertTrue(callable(reader),'runtime/source inventory needs its real readonly producer')
        with patch.object(lm_loop,'admission_root',return_value=root):
            return reader(state,trips,owner_id=owner,observed_at=observed,release_root=root)

    def test_real_private_events_sqlite_and_exact_release_fallback_in_both_modes(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);owner,state,trips,observed=fixture(root,mode);before=snapshot(root)
                result=self.read(root,state,trips,observed,owner);scope=result['scopes'][0]
                self.assertEqual({r['provider'] for r in scope['required_sources']},{'provider-a','provider-b'})
                self.assertEqual({r['run_id'] for r in scope['execution_refs']},{'physical-a','physical-b'})
                self.assertEqual({r['occurrence_id'] for r in scope['execution_refs']},
                    {owner+':claimed-before-physical-a',owner+':claimed-before-physical-b'})
                self.assertNotIn('admission_missing',reasons(result));self.assertEqual(result['input_reads'][owner]['admission']['status'],'ok')
                self.assertIn('history_coverage_unverified',reasons(result));self.assertEqual(result['coverage_state'],'gap')
                self.assertNotIn('net_pnl_usd',result);self.assertEqual(snapshot(root),before)

    def test_state_owner_mismatch_never_reads_another_owners_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);owner,state,trips,observed=fixture(root)
            with patch.object(lm_loop,'_owner_runtime_rows',side_effect=AssertionError('foreign runtime forbidden')):
                result=self.read(root,root/'other-state',trips,observed,owner)
            self.assertIn('inventory_state_owner_mismatch',reasons(result))

    def test_missing_admission_is_unknown_without_creating_a_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);owner,state,trips,observed=fixture(root);db=root/'admission-v2.sqlite3';db.unlink()
            result=self.read(root,state,trips,observed,owner)
            self.assertFalse(db.exists());self.assertIn('admission_read_unavailable',reasons(result))
            self.assertIn('admission_missing',reasons(result))

    def test_broken_ledger_is_not_silently_read_as_a_partial_source_list(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);owner,state,trips,observed=fixture(root)
            with (state/'receipts.jsonl').open('a') as stream:stream.write('{broken\n')
            result=self.read(root,state,trips,observed,owner)
            self.assertIn('source_ledger_unavailable',reasons(result))
            self.assertIn('source_release_missing',reasons(result))

    def test_current_release_never_substitutes_for_missing_historical_sha(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);owner,state,trips,observed=fixture(root)
            (root/'RELEASE.json').write_text(json.dumps({'sha':'c'*40,'release_paths':'ALL'}))
            result=self.read(root,state,trips,observed,owner)
            self.assertIn('source_release_missing',reasons(result))
            self.assertEqual({r['provider'] for r in result['scopes'][0]['required_sources']},{'provider-a'})

    def test_strict_private_jsonl_option_rejects_invalid_rows_without_changing_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'rows.jsonl';path.write_text('{"ok":1}\n{broken\n{"ok":2}\n');path.chmod(0o600)
            self.assertEqual(lm_loop._private_jsonl_rows(path),[{'ok':1},{'ok':2}])
            self.assertEqual(lm_loop._private_jsonl_rows(path,strict=True),[])

    def test_admission_read_closes_its_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);owner,state,trips,observed=fixture(root)
            class Connection(sqlite3.Connection):
                closed=False
                def close(self):self.closed=True;return super().close()
            connection=sqlite3.connect(root/'admission-v2.sqlite3',factory=Connection)
            try:
                with patch.object(lm_loop.sqlite3,'connect',return_value=connection):
                    lm_loop._read_admission_rows(root/'admission-v2.sqlite3','SELECT COUNT(*) FROM occurrences')
                self.assertTrue(connection.closed)
            finally:connection.close()

    def test_bad_declaration_returns_gap_and_never_reads_an_unauthorized_executor(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);owner,state,trips,observed=fixture(root)
            ledger=state/'receipts.jsonl';row=json.loads(ledger.read_text());row['source_declaration']['sources']=None
            ledger.write_text(json.dumps(row)+'\n')
            result=self.read(root,state,trips,observed,owner)
            self.assertIn('source_release_invalid',reasons(result))
            row['source_declaration']['sources']=[{'execution_owner_id':'unrelated-owner',
                'beneficiary_owner_id':owner,'beneficiary_mode':'paper'}]
            ledger.write_text(json.dumps(row)+'\n')
            result=self.read(root,state,trips,observed,owner)
            self.assertNotIn('unrelated-owner',result['input_reads'])

    def test_known_paid_cache_is_a_lower_bound_without_copying_money_or_changing_owner(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);owner,state,trips,observed=fixture(root,mode)
                component={'receipt_id':'paid://older','provider':'older-provider','category':'infra_cost',
                    'billing_account_ref':'older-account','order_ids':trips[0]['order_ids'],
                    'period_start':trips[0]['period_start'],'period_end':trips[0]['closed_at'],
                    'charge_identity':['older-provider','invoice','doc','line','allocation'],
                    'evidence_refs':['invoice://older'],'amount_usd':'DO_NOT_COPY_MONEY'}
                cached={'owner_id':owner,'mode':mode,'paper':mode=='paper','known_operating_cost_components':[component]}
                path=state/'performance-crypto-latest.json';path.write_text(json.dumps(cached,indent=2));path.chmod(0o600)
                result=self.read(root,state,trips,observed,owner);scope=result['scopes'][0]
                self.assertIn('older-provider',{r['provider'] for r in scope['required_sources']})
                bound=scope['known_paid_bindings'][0]
                self.assertEqual(bound['owner_id'],owner);self.assertNotIn('amount_usd',bound)
                cached['owner_id']='foreign-owner';path.write_text(json.dumps(cached))
                result=self.read(root,state,trips,observed,owner)
                self.assertIn('paid_cache_scope_invalid',reasons(result))
                self.assertEqual(result['scopes'][0]['known_paid_bindings'],[])

    def test_crypto_and_paper_writers_forward_and_persist_the_inventory(self):
        import crypto_performance as crypto
        import paper_performance as paper
        from test_crypto_performance import cycle_fixture,activity_fixture,NOW
        from test_paper_performance import _rows,OBSERVATION,RISK
        expected={'coverage_state':'gap','scopes':[],'gaps':[{'reason':'fixture_inventory'}]}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,frame,_=cycle_fixture(root)
            def read(**kw):return activity_fixture(frame,mode='paper',start=kw['period_start'],end=kw['period_end'])
            with patch.object(crypto,'read_expected_inventory',return_value=expected,create=True) as producer:
                result=crypto.write_crypto_performance(root,{'mode':'paper','paper':True,'clock':{'observed_at':NOW}},
                    mode='paper',owner_id='alpaca-investment-paper',activity_reader=read)
            self.assertEqual(producer.call_count,1)
            self.assertEqual(result['expected_cost_inventory'],expected)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'receipts.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in _rows()))
            with patch.object(paper,'read_expected_inventory',return_value=expected,create=True) as producer:
                result=paper.write_paper_performance(root,OBSERVATION,RISK)
            self.assertEqual(producer.call_count,1)
            self.assertEqual(result['expected_cost_inventory'],expected)

    def test_fee_only_and_partial_order_groups_are_not_excluded_from_cost_census(self):
        trips,inputs=fixtures.IndependentCensusTests().fixture()
        for ids in (['entry'],['entry','partial','exit']):
            with self.subTest(ids=ids):
                selected=[{**trips[0],'order_ids':ids}]
                result=inventory.build_expected_inventory(selected,**inputs)
                self.assertEqual(result['scopes'][0]['order_ids'],ids)
        for ids in ([],['entry','entry']):
            result=inventory.build_expected_inventory([{**trips[0],'order_ids':ids}],**inputs)
            self.assertIn('scope_invalid',reasons(result))

if __name__=='__main__':unittest.main()
