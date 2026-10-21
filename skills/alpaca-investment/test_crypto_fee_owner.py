"""Automatic owner synchronization consumes the same proven fee quantity chain."""
import copy
from contextlib import ExitStack,redirect_stdout
import importlib.util
from io import StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import alpaca_cli as cli
import crypto_ownership_proof as proofs
import effect_store as store
import position_manager as positions
from test_crypto_close import native_run
from test_crypto_fee_debit import debit_fixture,END
from test_crypto_fee_ledger import write_rows
from test_crypto_performance import activity_fixture
from test_owned_policy import seed,snapshot


def owner_fixture(root,mode,*,partial=False):
    rows,owned,frame,account=debit_fixture(root,mode,partial=partial)
    write_rows(root/'receipts.jsonl',rows)
    (root/'live-owned-position.json').write_text(json.dumps(owned))
    effect=owned['close_effect_id'] if partial else owned['entry_effect_id']
    broker=next(r['broker'] for r in reversed(rows) if r.get('receipt_type')=='outcome' and r.get('effect_id')==effect)
    account['positions'][0]['symbol']='BTCUSD'
    return owned,frame,account,broker


def core_guard():
    root=ROOT.parents[1]/'apps/life-manager/investment-core'
    spec=importlib.util.spec_from_file_location('fee_owner_core_guard',root/'provision_selection.py')
    module=importlib.util.module_from_spec(spec)
    with patch.object(sys,'path',[str(root)]+sys.path):spec.loader.exec_module(module)
    return module._official_crypto_closed


class CryptoFeeOwnerTests(unittest.TestCase):
    def environment(self,mode):
        return patch.dict(os.environ,{'LIFE_MANAGER_INVESTMENT_MODE':mode,
            'LIFE_MANAGER_INVESTMENT_OWNER_ID':f'alpaca-investment-{mode}'})

    def test_policy_requires_the_latest_proven_quantity_and_never_guesses_marker_drift(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory,self.environment(mode):
                root=Path(directory);owned,frame,account,_=owner_fixture(root,mode)
                with self.assertRaises(ValueError):positions.load_owned_policy(root,{**owned,'owned_qty':'0.04'},mode=mode)
                store.record_native_fee_debit(root/'receipts.jsonl',owned,account,activity_readback=frame,
                    mode=mode,owner_id=f'alpaca-investment-{mode}')
                with self.assertRaises(ValueError):positions.load_owned_policy(root,owned,mode=mode)
                current={**owned,'owned_qty':'0.049925'}
                policy=positions.load_owned_policy(root,current,mode=mode)
                self.assertEqual(policy['owned_qty'],'0.049925');self.assertEqual(policy['entry_price'],'200')
                rows=store._rows(root/'receipts.jsonl');rows[-1]['strategy_receipt']['receipt']['debit_qty']='0.0001'
                write_rows(root/'receipts.jsonl',rows)
                with self.assertRaises(ValueError):positions.load_owned_policy(root,current,mode=mode)

    def test_saved_fee_before_marker_update_is_adopted_without_activity_reads(self):
        for mode in ('paper','live'):
            for partial in (False,True):
                with self.subTest(mode=mode,partial=partial),tempfile.TemporaryDirectory() as directory,self.environment(mode):
                    root=Path(directory);owned,frame,account,broker=owner_fixture(root,mode,partial=partial)
                    store.record_native_fee_debit(root/'receipts.jsonl',owned,account,activity_readback=frame,
                        mode=mode,owner_id=f'alpaca-investment-{mode}')
                    ledger=(root/'receipts.jsonl').read_bytes();native=native_run()
                    with patch.object(native,'find_order_by_client_id',return_value=broker),\
                         patch.object(native,'read_crypto_activity_evidence',side_effect=AssertionError('replay read')):
                        result=native._sync_live_ownership(root,Path('unused'),Path('unused'),account)
                        again=native._sync_live_ownership(root,Path('unused'),Path('unused'),account)
                    self.assertEqual(result['owned_qty'],'0.029925' if partial else '0.049925')
                    self.assertEqual(result,again);self.assertEqual(json.loads((root/'live-owned-position.json').read_text()),result)
                    self.assertEqual((root/'receipts.jsonl').read_bytes(),ledger)
                    self.assertEqual(positions.load_owned_policy(root,result,mode=mode)['owned_qty'],result['owned_qty'])

    def test_open_owner_discovers_a_proven_fee_once_and_preserves_historical_sell_receipts(self):
        for mode in ('paper','live'):
            for partial in (False,True):
                with self.subTest(mode=mode,partial=partial),tempfile.TemporaryDirectory() as directory,self.environment(mode):
                    root=Path(directory);owned,frame,account,broker=owner_fixture(root,mode,partial=partial)
                    ledger=root/'receipts.jsonl';before=ledger.read_bytes();native=native_run()
                    with patch.object(native,'find_order_by_client_id',return_value=broker),\
                         patch.object(native,'read_crypto_activity_evidence',return_value=frame) as reader:
                        current=native._sync_live_ownership(root,Path('unused'),Path('unused'),account)
                        stable=ledger.read_bytes()
                        self.assertEqual(native._sync_live_ownership(root,Path('unused'),Path('unused'),account),current)
                    self.assertEqual(reader.call_count,1)
                    self.assertEqual(reader.call_args.kwargs['mode'],mode)
                    self.assertEqual(reader.call_args.kwargs['period_start'],frame['requested_period_start'])
                    self.assertEqual(reader.call_args.kwargs['period_end'],END)
                    self.assertEqual(current['owned_qty'],'0.029925' if partial else '0.049925')
                    self.assertTrue(stable.startswith(before));self.assertEqual(ledger.read_bytes(),stable)
                    self.assertEqual(len([r for r in store._rows(ledger) if r.get('receipt_type')=='native_fee_debit']),1)

    def test_missing_or_foreign_fees_keep_marker_and_ledger_unchanged(self):
        for mode in ('paper','live'):
            for fees in ([],[{'foreign':True}]):
                with self.subTest(mode=mode,fees=fees),tempfile.TemporaryDirectory() as directory,self.environment(mode):
                    root=Path(directory);owned,frame,account,broker=owner_fixture(root,mode)
                    evidence=activity_fixture(frame,mode=mode,start=frame['requested_period_start'],end=END,
                        fees=[] if not fees else [{**frame['fees'][0],'order_id':'foreign'}])
                    ledger=(root/'receipts.jsonl').read_bytes();marker=(root/'live-owned-position.json').read_bytes();native=native_run()
                    with patch.object(native,'find_order_by_client_id',return_value=broker),\
                         patch.object(native,'read_crypto_activity_evidence',return_value=evidence),\
                         self.assertRaises(ValueError):
                        native._sync_live_ownership(root,Path('unused'),Path('unused'),account)
                    self.assertEqual((root/'receipts.jsonl').read_bytes(),ledger)
                    self.assertEqual((root/'live-owned-position.json').read_bytes(),marker)

    def test_fresh_order_identity_is_checked_even_when_quantity_has_not_changed(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory,self.environment(mode):
                root=Path(directory);owned,frame,account,broker=owner_fixture(root,mode)
                account['positions'][0]['qty']='0.05';native=native_run()
                with patch.object(native,'find_order_by_client_id',return_value={**broker,'id':'different-order'}),\
                     patch.object(native,'read_crypto_activity_evidence',side_effect=AssertionError('not a fee gap')),\
                     self.assertRaises(ValueError):
                    native._sync_live_ownership(root,Path('unused'),Path('unused'),account)

    def test_fee_flat_is_proven_without_a_sell_and_replays_through_the_core_guard(self):
        guard=core_guard()
        for mode in ('paper','live'):
            for partial in (False,True):
                with self.subTest(mode=mode,partial=partial),tempfile.TemporaryDirectory() as directory,self.environment(mode):
                    root=Path(directory);owned,frame,account,broker=owner_fixture(root,mode,partial=partial)
                    frame=activity_fixture(frame,mode=mode,start=frame['requested_period_start'],end=END,
                        fees=[{**frame['fees'][0],'qty':'-0.03' if partial else '-0.05'}]);account['positions']=[]
                    native=native_run()
                    with patch.object(native,'find_order_by_client_id',return_value=broker),\
                         patch.object(native,'read_crypto_activity_evidence',return_value=frame) as reader:
                        current=native._sync_live_ownership(root,Path('unused'),Path('unused'),account)
                        ledger=(root/'receipts.jsonl').read_bytes()
                        self.assertEqual(native._sync_live_ownership(root,Path('unused'),Path('unused'),account),current)
                    self.assertEqual(current['status'],'closed');self.assertEqual(current['owned_qty'],'0')
                    self.assertEqual(current['close_reason'],'native_fee_debit');self.assertTrue(current['fee_close_id'])
                    self.assertEqual(reader.call_count,1);self.assertEqual((root/'receipts.jsonl').read_bytes(),ledger)
                    rows=store._rows(root/'receipts.jsonl')
                    self.assertTrue(guard(current,rows))
                    self.assertFalse(guard({**current,'owned_qty':'0.001'},rows))
                    self.assertFalse(guard({**current,'fee_close_id':'forged'},rows))

    def test_real_main_uses_adjusted_qty_and_defers_a_fee_first_seen_at_submit(self):
        for mode in ('paper','live'):
            for at_submit in (False,True):
                with self.subTest(mode=mode,at_submit=at_submit),tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
                    root=Path(directory);owned,owner=seed(root,mode=mode,
                        native_account_id=f'synthetic-native-account-{mode}' if mode=='live' else None);native=native_run()
                    broker=next(r['broker'] for r in store._rows(root/'receipts.jsonl') if r.get('receipt_type')=='outcome')
                    raw,account=snapshot(mode);history=raw.pop('crypto_history')
                    clock=raw['clock']['timestamp'];account.update(mode=mode,paper=mode=='paper',
                        account={'id':f'synthetic-native-account-{mode}','cash':'90','equity':'97.5'},activities_count=1,open_and_closed_orders_count=1,
                        clock={'observed_at':clock})
                    fee={'id':'native-main-fee','activity_type':'CFEE','order_id':broker['id'],'symbol':'BTCUSD',
                        'qty':'-0.000075','date':'2026-01-01','created_at':'2026-01-01T04:10:00Z','net_amount':'0','status':'executed'}
                    frame=activity_fixture({'fills':[],'fees':[fee]},mode=mode,start=broker['submitted_at'],end=clock)
                    observes=[0]
                    def observe(**_):
                        observes[0]+=1;value=copy.deepcopy(account)
                        value['positions'][0]['qty']='0.05' if at_submit and observes[0]==1 else '0.049925'
                        value['positions'][0]['unrealized_pl']='0'
                        return value
                    def find(*,client_order_id,**_):
                        if client_order_id==broker['client_order_id']:return copy.deepcopy(broker)
                        return {'id':'main-sell','client_order_id':client_order_id,'status':'filled','symbol':'BTCUSDC',
                            'side':'sell','type':'market','time_in_force':'gtc','qty':'0.049925','filled_qty':'0.049925',
                            'filled_avg_price':'150','submitted_at':clock,'filled_at':clock}
                    stack.enter_context(patch.dict(os.environ,{'LIFE_MANAGER_INVESTMENT_DEPLOYMENT':'local',
                        'LIFE_MANAGER_INVESTMENT_MODE':mode,'LIFE_MANAGER_INVESTMENT_OWNER_ID':owner,
                        'LIFE_MANAGER_RUN_ID':'fee-owner-main',
                        'LIFE_MANAGER_OCCURRENCE_ID':f'{owner}:fee-owner-main',
                        'LIFE_MANAGER_RELEASE_SHA':'b'*40,
                        f'ALPACA_INVESTMENT_{mode.upper()}_STATE_DIR':str(root),
                        f'ALPACA_INVESTMENT_{mode.upper()}_CREDENTIALS_FILE':str(root/'unused')},clear=True))
                    stack.enter_context(patch.object(native,'observe',side_effect=observe))
                    stack.enter_context(patch.object(native,'find_order_by_client_id',side_effect=find))
                    for name,value in (('read_allocator_snapshot',raw),('read_crypto_history',history),
                        ('read_campaign_snapshot',{'paper':True,'unexpected_positions':['BTCUSD'],'fills':[],'positions':[],'options':[]}),
                        ('build_candidates',[]),('_review_status',{}),('deliver',{'message_id':'fixture'}),
                        ('deliver_failure',{'status':'delivered'}),('_retry_allowed',False)):
                        stack.enter_context(patch.object(native,name,side_effect=lambda *args,value=value,**_:copy.deepcopy(value)))
                    reader=stack.enter_context(patch.object(native,'read_crypto_activity_evidence',return_value=frame))
                    submit=stack.enter_context(patch.object(native,'submit_order',return_value={'status':'accepted'}))
                    stack.enter_context(patch.object(cli,'_context',side_effect=AssertionError('provider forbidden')))
                    with redirect_stdout(StringIO()) as output:code=native.main(wake_id='fee-main-first')
                    summary=json.loads(output.getvalue().splitlines()[-1])
                    if at_submit:
                        self.assertEqual(code,78,summary);self.assertEqual(summary['error_code'],'owned_position_changed_before_submit')
                        self.assertEqual(submit.call_count,0);self.assertEqual(reader.call_count,0)
                        self.assertFalse(any(r.get('order',{}).get('side')=='sell' for r in store._rows(root/'receipts.jsonl')))
                        with redirect_stdout(StringIO()) as output:code=native.main(wake_id='fee-main-next-wake')
                        summary=json.loads(output.getvalue().splitlines()[-1])
                    self.assertEqual(code,0,summary);self.assertEqual(submit.call_count,1)
                    self.assertEqual(reader.call_count,1)
                    rows=store._rows(root/'receipts.jsonl')
                    sells=[r for r in rows if r.get('receipt_type')=='effect_intent' and r.get('status')=='planned'
                        and r.get('order',{}).get('side')=='sell']
                    self.assertEqual(len(sells),1);self.assertEqual(sells[0]['order']['qty'],'0.049925')
                    self.assertEqual(json.loads((root/'live-owned-position.json').read_text())['owned_qty'],'0.049925')
