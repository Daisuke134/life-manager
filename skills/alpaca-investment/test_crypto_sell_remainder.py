"""Sell remainder receipts conserve recorded acquisition quantity across legs."""
import copy
import json
import os
from decimal import Decimal
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
from test_crypto_close import close_fixture,native_run
from test_owned_policy import snapshot


def remainder_fixture(root,mode='live',qty='0.02',status='canceled'):
    with patch.dict(os.environ,{'LIFE_MANAGER_INVESTMENT_OWNER_ID':f'alpaca-investment-{mode}'}):
        owned,broker,obs,owner=close_fixture(root,mode)
    broker.update(status=status,filled_qty=qty,filled_avg_price=None,filled_at=None)
    obs.update(activities_count=0,open_and_closed_orders_count=0)
    for position in obs['positions']: position['unrealized_pl']='0'
    remaining=Decimal('0.05')-Decimal(qty)
    if remaining:
        obs['positions'].append({'symbol':'BTCUSDC','qty':str(remaining),'unrealized_pl':'0'})
    fills=[] if qty=='0' else [{'id':'sell-fill','activity_type':'FILL','order_id':broker['id'],
        'symbol':'BTCUSDC','side':'sell','qty':qty,'price':'210','transaction_time':'2026-01-01T04:15:01Z'}]
    with patch.object(cli,'_context',return_value={}),patch.object(cli,'_run',side_effect=[fills,[]]):
        activities=cli.read_crypto_activity_evidence(credentials_path=Path('unused'),cli_path=Path('unused'),
            mode=mode,period_start=broker['submitted_at'],period_end=obs['clock']['observed_at'])
    return owned,broker,obs,owner,activities


class SellRemainderTests(unittest.TestCase):
    def proof(self,root,owned,broker,obs,owner,activities,mode):
        reader=getattr(proofs,'sell_remainder_proof_from_rows',None)
        self.assertTrue(callable(reader),'shared chained sell remainder proof is required')
        return reader(store._rows(root/'receipts.jsonl'),owned,broker,obs,
            mode=mode,owner_id=owner,activity_readback=activities)

    def test_partial_and_zero_proofs_preserve_raw_order_and_quantity(self):
        for mode in ('paper','live'):
            for qty,remaining in (('0.02','0.03'),('0','0.05'),('0.05','0')):
                with self.subTest(mode=mode,qty=qty),tempfile.TemporaryDirectory() as directory:
                    root=Path(directory);owned,broker,obs,owner,activities=remainder_fixture(root,mode,qty)
                    before=copy.deepcopy((owned,broker,obs,activities))
                    proof=self.proof(root,owned,broker,obs,owner,activities,mode)
                    self.assertEqual(proof['receipt']['kind'],'owned_crypto_sell_remainder')
                    self.assertEqual(proof['receipt']['before_owned_qty'],'0.05')
                    self.assertEqual(proof['receipt']['exit_filled_qty'],qty)
                    self.assertEqual(proof['receipt']['remaining_owned_qty'],remaining)
                    self.assertIsNone(proof['receipt']['net_realized_pnl_usd'])
                    if qty=='0': self.assertIsNone(proof['receipt']['exit_price'])
                    self.assertEqual((owned,broker,obs,activities),before)

    def flow(self,mode,qty='0.02',*,lag=None,legacy=False):
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            root=Path(directory);owned,broker,obs,owner,activities=remainder_fixture(root,mode,qty)
            complete=copy.deepcopy(activities);remaining=Decimal('0.05')-Decimal(qty)
            if legacy: store.reconcile_started(root/'receipts.jsonl',lambda _:broker)
            if lag=='account':
                obs['positions']=[obs['positions'][0],{'symbol':'BTCUSDC','qty':'0.05','unrealized_pl':'0'}]
            if lag=='fills':
                activities['fills']=[]
                body={k:v for k,v in activities.items() if k!='source_receipt_id'}
                activities['source_receipt_id']='alpaca-crypto-activities:'+proofs._digest([body])
            raw,_=snapshot(mode);raw.pop('crypto_history');raw['positions']=1 if remaining or lag=='account' else 0
            native=native_run()
            stack.enter_context(patch.dict(os.environ,{'LIFE_MANAGER_INVESTMENT_MODE':mode,
                'LIFE_MANAGER_INVESTMENT_DEPLOYMENT':'local','LIFE_MANAGER_INVESTMENT_OWNER_ID':owner,
                f'ALPACA_INVESTMENT_{mode.upper()}_STATE_DIR':str(root),
                f'ALPACA_INVESTMENT_{mode.upper()}_CREDENTIALS_FILE':str(root/'unused')},clear=True))
            entry=proofs.entry_receipt_row(store._rows(root/'receipts.jsonl'),owned['entry_effect_id'])['broker']
            stack.enter_context(patch.object(native,'observe',side_effect=lambda **_:copy.deepcopy(obs)))
            stack.enter_context(patch.object(native,'read_allocator_snapshot',side_effect=lambda **_:copy.deepcopy(raw)))
            stack.enter_context(patch.object(native,'find_order_by_client_id',side_effect=lambda **kw:
                copy.deepcopy(broker if kw['client_order_id']==broker['client_order_id'] else entry)))
            activity_reader=stack.enter_context(patch.object(native,'read_crypto_activity_evidence',side_effect=lambda **_:copy.deepcopy(activities)))
            for name,value in (('read_crypto_history',{}),('build_candidates',[]),('_review_status',{}),
                    ('read_campaign_snapshot',{'paper':True,'unexpected_positions':['BTCUSD'] if remaining else [],
                                              'fills':[],'positions':[],'options':[]}),
                    ('deliver',{'message_id':'fixture'}),('deliver_failure',{'status':'delivered'}),('_retry_allowed',False)):
                stack.enter_context(patch.object(native,name,return_value=value))
            submit=stack.enter_context(patch.object(native,'submit_order',side_effect=AssertionError('unexpected order')))
            stack.enter_context(patch.object(cli,'_context',side_effect=AssertionError('provider forbidden')))
            stack.enter_context(patch.object(cli,'_run',side_effect=AssertionError('provider forbidden')))
            def run(wake):
                with redirect_stdout(StringIO()) as output: code=native.main(wake_id=wake)
                result=json.loads(output.getvalue().splitlines()[-1]);self.assertEqual(code,0,result)
                return result
            result=run('sell-remainder')
            if lag:
                self.assertEqual(result['reconciliation']['unresolved'],1)
                self.assertEqual(result['reconciliation']['deferred'],1)
                self.assertEqual(json.loads((root/'live-owned-position.json').read_text()),owned)
                activities.clear();activities.update(complete)
                if lag=='account':
                    obs['positions']=obs['positions'][:1]
                    if remaining: obs['positions'].append({'symbol':'BTCUSDC','qty':str(remaining),'unrealized_pl':'0'})
                    raw['positions']=1 if remaining else 0
                result=run('sell-remainder-recovered')
            self.assertEqual(result['reconciliation']['unresolved'],0)
            adopted=json.loads((root/'live-owned-position.json').read_text())
            self.assertEqual(adopted['status'],'open' if remaining else 'closed')
            if remaining: self.assertEqual(Decimal(adopted['owned_qty']),remaining)
            before=(root/'receipts.jsonl').read_bytes();reads=activity_reader.call_count
            run('sell-remainder-replay')
            self.assertEqual((root/'receipts.jsonl').read_bytes(),before)
            self.assertEqual(activity_reader.call_count,reads)
            submit.assert_not_called()

    def test_real_main_partial_zero_and_fully_executed_terminal_sell(self):
        for mode in ('paper','live'):
            for qty in ('0.02','0','0.05'):
                with self.subTest(mode=mode,qty=qty): self.flow(mode,qty)

    def test_lag_and_legacy_missing_receipt_recover_without_replay(self):
        for mode in ('paper','live'):
            for lag in ('account','fills'):
                with self.subTest(mode=mode,lag=lag): self.flow(mode,lag=lag)
            with self.subTest(mode=mode,legacy=True): self.flow(mode,legacy=True)

    def test_unproved_terminal_zero_sell_stays_in_common_fence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);owned,broker,*_=remainder_fixture(root,qty='0')
            store.reconcile_started(root/'receipts.jsonl',lambda _:broker)
            self.assertEqual(store.unresolved_intent_count(root/'receipts.jsonl'),1)
            self.assertEqual(store.effect_state(root/'receipts.jsonl',owned['close_effect_id']),'started')

    def test_partial_leg_then_full_exit_conserves_initial_owned_quantity(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{
                    'LIFE_MANAGER_INVESTMENT_MODE':mode,'LIFE_MANAGER_INVESTMENT_OWNER_ID':f'alpaca-investment-{mode}'}):
                root=Path(directory);owned,broker,obs,owner,activities=remainder_fixture(root,mode)
                proof=self.proof(root,owned,broker,obs,owner,activities,mode)
                store.reconcile_started(root/'receipts.jsonl',lambda _:broker,on_reconciled=lambda *_:proof)
                native=native_run()
                with patch.object(native,'find_order_by_client_id',return_value=broker):
                    opened=native._sync_live_ownership(root,Path('unused'),Path('unused'),native._normalize_live_position_symbols(copy.deepcopy(obs)))
                parent=position_manager.load_owned_policy(root,opened,mode=mode)
                decision={'action':'EXIT','mode':mode,'owner_id':owner,'strategy_id':parent['card'].strategy_id,
                    'release_sha':parent['release_sha'],'position_qty':'0.03','observed_at':'2026-01-01T04:20:00Z',
                    **{k:parent[k] for k in ('entry_effect_id','entry_client_order_id','entry_provider_order_id','entry_price','entry_timestamp')}}
                close=store.seal(root/'receipts.jsonl',decision,{'asset_class':'crypto','symbol':'BTC/USDC','side':'sell',
                    'type':'market','time_in_force':'gtc','qty':'0.03'});store.mark_started(root/'receipts.jsonl',close)
                closing={**opened,'status':'closing','close_effect_id':close['effect_id'],'close_client_order_id':close['client_order_id']}
                sell={**broker,'id':'next-exit','client_order_id':close['client_order_id'],'status':'filled',
                    'qty':'0.03','filled_qty':'0.03','filled_avg_price':'211','submitted_at':'2026-01-01T04:20:00Z',
                    'filled_at':'2026-01-01T04:20:01Z'}
                flat={**obs,'positions':obs['positions'][:1],'clock':{'observed_at':'2026-01-01T04:20:02Z'}}
                final=position_manager.close_fill_proof(root,closing,sell,flat,mode=mode)
                store.reconcile_started(root/'receipts.jsonl',lambda _:sell,on_reconciled=lambda *_:final)
                self.assertEqual(store.unresolved_intent_count(root/'receipts.jsonl'),0)
                rows=store._rows(root/'receipts.jsonl')
                first=next(r for r in rows if r.get('receipt_type')=='outcome' and r.get('effect_id')==owned['close_effect_id'])
                first['strategy_receipt']['receipt']['remaining_owned_qty']='0.04'
                (root/'receipts.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
                with self.assertRaises(ValueError): position_manager.close_fill_proof(root,closing,sell,flat,mode=mode)

    def test_reopened_position_rejects_half_missing_close_identity(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{
                'LIFE_MANAGER_INVESTMENT_MODE':'live','LIFE_MANAGER_INVESTMENT_OWNER_ID':'alpaca-investment-live'}):
            root=Path(directory);owned,broker,obs,owner,activities=remainder_fixture(root)
            proof=self.proof(root,owned,broker,obs,owner,activities,'live')
            store.reconcile_started(root/'receipts.jsonl',lambda _:broker,on_reconciled=lambda *_:proof)
            owned.update(status='open',owned_qty='0.03',close_effect_id=None)
            (root/'live-owned-position.json').write_text(json.dumps(owned));before=(root/'live-owned-position.json').read_bytes()
            native=native_run()
            with patch.object(native,'find_order_by_client_id',return_value=broker):
                with self.assertRaisesRegex(ValueError,'owned_closed_identity_invalid'):
                    native._sync_live_ownership(root,Path('unused'),Path('unused'),native._normalize_live_position_symbols(copy.deepcopy(obs)))
            self.assertEqual((root/'live-owned-position.json').read_bytes(),before)

    def test_two_partial_sell_legs_keep_the_same_parent_and_exact_remaining_qty(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{
                    'LIFE_MANAGER_INVESTMENT_MODE':mode,'LIFE_MANAGER_INVESTMENT_OWNER_ID':f'alpaca-investment-{mode}'}):
                root=Path(directory);owned,broker,obs,owner,activities=remainder_fixture(root,mode)
                first=self.proof(root,owned,broker,obs,owner,activities,mode)
                store.reconcile_started(root/'receipts.jsonl',lambda _:broker,on_reconciled=lambda *_:first)
                opened={**owned,'status':'open','owned_qty':'0.03'}
                parent=position_manager.load_owned_policy(root,opened,mode=mode)
                decision={'action':'EXIT','mode':mode,'owner_id':owner,'strategy_id':parent['card'].strategy_id,
                    'release_sha':parent['release_sha'],'position_qty':'0.03','observed_at':'2026-01-01T04:20:00Z',
                    **{k:parent[k] for k in ('entry_effect_id','entry_client_order_id','entry_provider_order_id','entry_price','entry_timestamp')}}
                sealed=store.seal(root/'receipts.jsonl',decision,{'asset_class':'crypto','symbol':'BTC/USDC','side':'sell',
                    'type':'market','time_in_force':'gtc','qty':'0.03'});store.mark_started(root/'receipts.jsonl',sealed)
                closing={**opened,'status':'closing','close_effect_id':sealed['effect_id'],'close_client_order_id':sealed['client_order_id']}
                second={**broker,'id':'next-exit','client_order_id':sealed['client_order_id'],'qty':'0.03',
                        'filled_qty':'0.01','submitted_at':'2026-01-01T04:20:00Z'}
                after={**obs,'clock':{'observed_at':'2026-01-01T04:20:02Z'},
                       'positions':[obs['positions'][0],{'symbol':'BTCUSDC','qty':'0.02'}]}
                fill={'id':'sell-fill-2','activity_type':'FILL','order_id':second['id'],'symbol':'BTCUSDC','side':'sell',
                      'qty':'0.01','price':'211','transaction_time':'2026-01-01T04:20:01Z'}
                with patch.object(cli,'_context',return_value={}),patch.object(cli,'_run',side_effect=[[fill],[]]):
                    snapshot=cli.read_crypto_activity_evidence(credentials_path=Path('unused'),cli_path=Path('unused'),mode=mode,
                        period_start=second['submitted_at'],period_end=after['clock']['observed_at'])
                proof=self.proof(root,closing,second,after,owner,snapshot,mode)
                self.assertEqual(proof['receipt']['remaining_owned_qty'],'0.02')
                store.reconcile_started(root/'receipts.jsonl',lambda _:second,on_reconciled=lambda *_:proof)
                self.assertEqual(store.unresolved_intent_count(root/'receipts.jsonl'),0)
                (root/'live-owned-position.json').write_text(json.dumps(closing));native=native_run()
                with patch.object(native,'find_order_by_client_id',return_value=second):
                    actual=native._sync_live_ownership(root,Path('unused'),Path('unused'),native._normalize_live_position_symbols(copy.deepcopy(after)))
                self.assertEqual(actual['owned_qty'],'0.02');self.assertEqual(actual['entry_effect_id'],owned['entry_effect_id'])

    def test_positive_remainder_cannot_certify_closed_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);owned,broker,obs,owner,activities=remainder_fixture(root)
            proof=self.proof(root,owned,broker,obs,owner,activities,'live')
            store.reconcile_started(root/'receipts.jsonl',lambda _:broker,on_reconciled=lambda *_:proof)
            with self.assertRaises(ValueError):
                proofs.recorded_close_proof_from_rows(store._rows(root/'receipts.jsonl'),{**owned,'status':'closed'},
                    broker,obs,mode='live',owner_id=owner)
