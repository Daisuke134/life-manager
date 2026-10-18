"""Terminal partial buys retain raw provider facts and recover via the real main."""
import copy
import json
import os
from contextlib import ExitStack, redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import alpaca_cli as cli
import effect_store as store
import crypto_ownership_proof as proofs
import position_manager
from test_crypto_entry import entry_fixture
from test_crypto_close import native_run
from test_crypto_activity_evidence import FILL


def partial_fixture(root,mode='live',status='canceled'):
    marker,broker,observation,owner=entry_fixture(root,mode,owned_qty='0.03')
    broker.update(status=status,filled_qty='0.03',filled_avg_price=None,filled_at=None)
    observation['clock']['observed_at']='2026-01-01T04:00:03Z'
    fills=[copy.deepcopy(FILL),{**FILL,'id':'fill-2','qty':'0.01','price':'203',
                               'transaction_time':'2026-01-01T04:00:02Z'}]
    with patch.object(cli,'_context',return_value={}),patch.object(cli,'_run',side_effect=[fills,[]]):
        activities=cli.read_crypto_activity_evidence(credentials_path=Path('unused'),cli_path=Path('unused'),
            mode=mode,period_start=broker['submitted_at'],period_end=observation['clock']['observed_at'])
    return marker,broker,observation,owner,activities


class PartialEntryTests(unittest.TestCase):
    def proof(self,root,marker,broker,observation,owner,activities,mode):
        try:
            return proofs.entry_fill_proof_from_rows(store._rows(root/'receipts.jsonl'),marker,broker,observation,
                mode=mode,owner_id=owner,activity_readback=activities)
        except TypeError as error:
            self.fail(f'partial acquisition requires activity evidence: {error}')

    def test_terminal_partial_proof_keeps_raw_order_and_records_fill_derived_entry_facts(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);marker,broker,observation,owner,activities=partial_fixture(root,mode)
                before=copy.deepcopy((broker,observation,activities));ledger=(root/'receipts.jsonl').read_bytes()
                proof=self.proof(root,marker,broker,observation,owner,activities,mode)
                self.assertEqual(proof['receipt']['entry_filled_qty'],'0.03')
                self.assertEqual(proof['receipt']['account_owned_qty'],'0.03')
                self.assertEqual(proof['receipt']['entry_price'],'201')
                self.assertEqual(proof['receipt']['entry_timestamp'],'2026-01-01T04:00:02+00:00')
                self.assertEqual(proof['receipt']['entry_execution']['broker_status'],'canceled')
                self.assertEqual(proof['activity_readback'],activities)
                self.assertIsNone(proof['receipt']['net_realized_pnl_usd'])
                self.assertEqual((broker,observation,activities),before)
                self.assertEqual((root/'receipts.jsonl').read_bytes(),ledger)

    def flow(self,mode,*,status='canceled',lag=None):
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            root=Path(directory);marker,broker,observation,owner,activities=partial_fixture(root,mode,status)
            complete=copy.deepcopy(activities)
            if lag=='account': observation['positions']=observation['positions'][:1]
            if lag=='fills':
                activities['fills']=activities['fills'][:1]
                body={k:v for k,v in activities.items() if k!='source_receipt_id'}
                activities['source_receipt_id']='alpaca-crypto-activities:'+proofs._digest([body])
            raw={'account':observation['account'],'clock':{'timestamp':'2026-01-01T04:00:03Z'},
                 'risk':{'allocated_capital_usd':'10'},'positions':0 if lag=='account' else 1,
                 'open_orders':0,'crypto':[],'option_quotes':[]}
            native=native_run()
            stack.enter_context(patch.dict(os.environ,{'LIFE_MANAGER_INVESTMENT_MODE':mode,
                'LIFE_MANAGER_INVESTMENT_DEPLOYMENT':'local','LIFE_MANAGER_INVESTMENT_OWNER_ID':owner,
                f'ALPACA_INVESTMENT_{mode.upper()}_STATE_DIR':str(root),
                f'ALPACA_INVESTMENT_{mode.upper()}_CREDENTIALS_FILE':str(root/'unused')},clear=True))
            stack.enter_context(patch.object(native,'observe',side_effect=lambda **_:copy.deepcopy(observation)))
            stack.enter_context(patch.object(native,'read_allocator_snapshot',side_effect=lambda **_:copy.deepcopy(raw)))
            stack.enter_context(patch.object(native,'find_order_by_client_id',return_value=broker))
            activity_reader=stack.enter_context(patch.object(native,'read_crypto_activity_evidence',
                side_effect=lambda **_:copy.deepcopy(activities),create=True))
            for name,value in (('read_crypto_history',{}),('build_candidates',[]),('_review_status',{}),
                    ('read_campaign_snapshot',{'paper':True,'unexpected_positions':['BTCUSD'],'fills':[],'positions':[],'options':[]}),
                    ('deliver',{'message_id':'fixture'}),('deliver_failure',{'status':'delivered'}),('_retry_allowed',False)):
                stack.enter_context(patch.object(native,name,return_value=value))
            submit=stack.enter_context(patch.object(native,'submit_order',side_effect=AssertionError('duplicate entry')))
            stack.enter_context(patch.object(cli,'_context',side_effect=AssertionError('provider forbidden')))
            stack.enter_context(patch.object(cli,'_run',side_effect=AssertionError('provider forbidden')))
            def run(wake):
                with redirect_stdout(StringIO()) as output: code=native.main(wake_id=wake)
                value=json.loads(output.getvalue().splitlines()[-1]);self.assertEqual(code,0,value)
                return value
            result=run('partial-entry')
            if lag:
                self.assertEqual(result['reconciliation']['unresolved'],1)
                self.assertEqual(result['reconciliation']['deferred'],1)
                self.assertEqual(json.loads((root/'live-owned-position.json').read_text()),marker)
                self.assertFalse(any(r.get('receipt_type')=='outcome' for r in store._rows(root/'receipts.jsonl')))
                activities.clear();activities.update(complete)
                if lag=='account':
                    observation['positions'].append({'symbol':'BTCUSDC','qty':'0.03','unrealized_pl':'0'})
                    raw['positions']=1
                result=run('partial-entry-recovered')
            self.assertEqual(result['reconciliation']['unresolved'],0)
            owned=json.loads((root/'live-owned-position.json').read_text())
            self.assertEqual(owned['status'],'open');self.assertEqual(owned['owned_qty'],'0.03')
            self.assertEqual(owned['entry_filled_qty'],'0.03')
            saved=proofs.entry_receipt_row(store._rows(root/'receipts.jsonl'),marker['entry_effect_id'])
            self.assertEqual(saved['broker'],broker)
            self.assertEqual(saved['strategy_receipt']['receipt']['entry_execution']['filled_qty'],'0.03')
            self.assertEqual(activity_reader.call_args.kwargs['mode'],mode)
            before=(root/'receipts.jsonl').read_bytes();calls=activity_reader.call_count
            run('partial-entry-replay')
            self.assertEqual(activity_reader.call_count,calls)
            self.assertEqual((root/'receipts.jsonl').read_bytes(),before)
            parent=position_manager.load_owned_policy(root,owned,mode=mode)
            self.assertEqual(parent['entry_price'],'201')
            self.assertEqual(parent['entry_provider_order_id'],broker['id'])
            # A normal owned full EXIT still binds to this partial acquisition.
            decision={'action':'EXIT','mode':mode,'owner_id':owner,'strategy_id':parent['card'].strategy_id,
                'release_sha':parent['release_sha'],'position_qty':'0.03','observed_at':'2026-01-01T04:15:00Z',
                **{key:parent[key] for key in ('entry_effect_id','entry_client_order_id','entry_provider_order_id',
                                             'entry_price','entry_timestamp')}}
            close=store.seal(root/'receipts.jsonl',decision,{'asset_class':'crypto','symbol':'BTC/USDC',
                'side':'sell','qty':'0.03','type':'market','time_in_force':'gtc'})
            store.mark_started(root/'receipts.jsonl',close)
            owned.update(status='closing',close_effect_id=close['effect_id'],close_client_order_id=close['client_order_id'])
            sell={'id':'official-exit','client_order_id':close['client_order_id'],'symbol':'BTCUSDC','side':'sell',
                'type':'market','time_in_force':'gtc','status':'filled','qty':'0.03','filled_qty':'0.03',
                'filled_avg_price':'210','submitted_at':'2026-01-01T04:15:00Z','filled_at':'2026-01-01T04:15:01Z'}
            flat={**observation,'positions':observation['positions'][:1],
                  'clock':{'observed_at':'2026-01-01T04:15:02Z'}}
            proof=position_manager.close_fill_proof(root,owned,sell,flat,mode=mode)
            self.assertEqual(proof['receipt']['entry_provider_order_id'],broker['id'])
            store.reconcile_started(root/'receipts.jsonl',lambda _:sell,on_reconciled=lambda *_:proof)
            self.assertEqual(store.unresolved_intent_count(root/'receipts.jsonl'),0)
            submit.assert_not_called()

    def test_real_main_recovers_terminal_partial_buy_and_preserves_owned_exit(self):
        for mode in ('paper','live'):
            for status in ('canceled','expired','rejected'):
                with self.subTest(mode=mode,status=status): self.flow(mode,status=status)

    def test_fill_and_account_lag_recover_without_additional_order(self):
        for mode in ('paper','live'):
            for lag in ('fills','account'):
                with self.subTest(mode=mode,lag=lag): self.flow(mode,lag=lag)

    def test_active_partial_or_paused_orders_do_not_invoke_completion_callback(self):
        for status in ('partially_filled','done_for_day','stopped','suspended'):
            with self.subTest(status=status),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);marker,broker,*_=partial_fixture(root,status=status)
                result=store.reconcile_started(root/'receipts.jsonl',lambda _:broker,
                    on_reconciled=lambda *_:self.fail('active order cannot complete'))
                self.assertEqual(result['unresolved'],1)
                self.assertEqual(store.effect_state(root/'receipts.jsonl',marker['entry_effect_id']),'started')

    def test_saved_partial_proof_cannot_hide_invalid_activity_without_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);marker,broker,observation,owner,activities=partial_fixture(root)
            proof=self.proof(root,marker,broker,observation,owner,activities,'live')
            store.reconcile_started(root/'receipts.jsonl',lambda _:broker,on_reconciled=lambda *_:proof)
            self.assertEqual(store.unresolved_intent_count(root/'receipts.jsonl'),0)
            (root/'live-owned-position.json').unlink()
            rows=store._rows(root/'receipts.jsonl')
            rows[-1]['strategy_receipt']['activity_readback']['fills'][0]['qty']='0.03'
            (root/'receipts.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            self.assertEqual(store.unresolved_intent_count(root/'receipts.jsonl'),1)
            self.assertEqual(store.effect_state(root/'receipts.jsonl',marker['entry_effect_id']),'started')
