"""A terminal SELL and a concurrent BUY base fee conserve one owned quantity."""
import copy
from decimal import Inexact,localcontext
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import crypto_ownership_proof as proofs
import effect_store as store
import position_manager
from test_crypto_entry import entry_fixture
from test_crypto_close import native_run
from test_crypto_performance import activity_fixture
from test_crypto_fee_ledger import record_sell,write_rows
from test_crypto_fee_owner import core_guard

NOW='2026-01-01T04:15:02Z'


def closing_fee_fixture(root,mode='paper',*,sold='0.02',remaining='0.029925',credit='0.05',prior=False):
    owned,buy,account,owner=entry_fixture(root,mode,owned_qty=credit);ledger=root/'receipts.jsonl'
    acquired=proofs.entry_fill_proof_from_rows(store._rows(ledger),owned,buy,account,mode=mode,owner_id=owner)
    store.reconcile_started(ledger,lambda _:buy,on_reconciled=lambda *_:acquired)
    owned.update(status='open',owned_qty=credit,entry_filled_qty='0.05')
    fee={'id':'closing-buy-fee','activity_type':'CFEE','order_id':buy['id'],'symbol':'BTCUSD','qty':'-0.000075',
        'date':'2026-01-01','created_at':NOW,'net_amount':'0','status':'executed'}
    fees=[fee]
    if prior:
        old={**fee,'id':'prior-buy-fee','qty':'-0.00005','created_at':'2026-01-01T04:05:00Z'}
        evidence=activity_fixture({'fills':[],'fees':[old]},mode=mode,start=buy['submitted_at'],end='2026-01-01T04:10:00Z')
        observed={**account,'positions':[{'symbol':'BTCUSD','qty':'0.04995'}],'clock':{'observed_at':'2026-01-01T04:10:00Z'}}
        store.record_native_fee_debit(ledger,owned,observed,activity_readback=evidence,mode=mode,owner_id=owner)
        owned['owned_qty']='0.04995';fees=[old,{**fee,'qty':'-0.000025'}]
    parent=proofs._owned_policy(proofs.owned_entry_decision_from_rows(store._rows(ledger),owned,
        mode=mode,owner_id=owner),owned,mode=mode)
    before=owned['owned_qty']
    decision={'action':'EXIT','mode':mode,'owner_id':owner,'strategy_id':parent['card'].strategy_id,
        'release_sha':parent['release_sha'],'position_qty':before,'observed_at':'2026-01-01T04:15:00Z',
        **{k:parent[k] for k in ('entry_effect_id','entry_client_order_id','entry_provider_order_id','entry_price','entry_timestamp')}}
    sealed=store.seal(ledger,decision,{'asset_class':'crypto','symbol':'BTC/USDC','side':'sell','type':'market',
        'time_in_force':'gtc','qty':before});store.mark_started(ledger,sealed)
    owned.update(status='closing',close_effect_id=sealed['effect_id'],close_client_order_id=sealed['client_order_id'])
    (root/'live-owned-position.json').write_text(json.dumps(owned))
    broker={'id':'closing-sell','client_order_id':sealed['client_order_id'],'symbol':'BTCUSDC','side':'sell',
        'type':'market','time_in_force':'gtc','status':'canceled','qty':before,'filled_qty':sold,
        'filled_avg_price':None,'filled_at':None,'submitted_at':'2026-01-01T04:15:00Z'}
    fills=[{'id':'buy-fill','activity_type':'FILL','order_id':buy['id'],'symbol':'BTCUSDC','side':'buy',
        'qty':'0.05','price':'200','transaction_time':buy['filled_at']}]
    if sold!='0':fills.append({'id':'closing-sell-fill','activity_type':'FILL','order_id':broker['id'],
        'symbol':'BTCUSDC','side':'sell','qty':sold,'price':'210','transaction_time':'2026-01-01T04:15:01Z'})
    activity=activity_fixture({'fills':fills,'fees':fees},mode=mode,start=buy['submitted_at'],end=NOW)
    observation={**account,'clock':{'observed_at':NOW},'positions':[] if remaining=='0' else [{'symbol':'BTCUSD','qty':remaining}]}
    return owned,broker,observation,owner,activity


class CryptoClosingFeeTests(unittest.TestCase):
    def proof(self,root,args,mode='paper'):
        owned,broker,account,owner,activity=args
        return proofs.sell_remainder_proof_from_rows(store._rows(root/'receipts.jsonl'),owned,broker,account,
            mode=mode,owner_id=owner,activity_readback=activity)

    def save(self,root,args,mode='paper'):
        proof=self.proof(root,args,mode)
        store.reconcile_started(root/'receipts.jsonl',lambda _:args[1],on_reconciled=lambda *_:proof)
        return proof

    def test_partial_zero_and_fee_exhausted_legs_separate_sold_and_debited_quantities(self):
        for mode in ('paper','live'):
            for sold,remaining,fee_qty in (('0.02','0.029925','-0.000075'),('0','0.049925','-0.000075'),
                                            ('0.02','0','-0.03'),('0','0','-0.05')):
                with self.subTest(mode=mode,sold=sold,remaining=remaining),tempfile.TemporaryDirectory() as directory:
                    root=Path(directory);args=list(closing_fee_fixture(root,mode,sold=sold,remaining=remaining))
                    args[4]=activity_fixture(args[4],mode=mode,start=args[4]['requested_period_start'],end=NOW,
                        fees=[{**args[4]['fees'][0],'qty':fee_qty}])
                    original=copy.deepcopy(args);proof=self.save(root,args,mode);receipt=proof['receipt']
                    self.assertEqual(receipt['exit_filled_qty'],sold);self.assertEqual(receipt['remaining_owned_qty'],remaining)
                    self.assertEqual(receipt['native_fee_debit']['debit_qty'],fee_qty[1:])
                    self.assertIsNone(receipt['net_realized_pnl_usd']);self.assertEqual(args,original)
                    self.assertEqual(store.unresolved_intent_count(root/'receipts.jsonl'),0)
                    state=proofs.owned_quantity_state_from_rows(store._rows(root/'receipts.jsonl'),args[0],mode=mode,owner_id=args[3])
                    self.assertEqual(state['owned_qty'],remaining);self.assertEqual(state['sold_qty'],sold)
                    self.assertEqual(state['debited_qty'],fee_qty[1:])

    def test_embedded_and_prior_recorded_fees_are_not_deducted_twice(self):
        for mode in ('paper','live'):
            for prior in (False,True):
                with self.subTest(mode=mode,prior=prior),tempfile.TemporaryDirectory() as directory:
                    root=Path(directory);args=closing_fee_fixture(root,mode,credit='0.05' if prior else '0.049925',prior=prior)
                    receipt=self.save(root,args,mode)['receipt']
                    self.assertEqual(receipt['remaining_owned_qty'],'0.029925')
                    if prior:self.assertEqual(receipt['native_fee_debit']['debit_qty'],'0.000025')
                    else:self.assertNotIn('native_fee_debit',receipt)

    def test_existing_producer_counter_owner_and_next_full_exit_share_the_proof(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{
                'LIFE_MANAGER_INVESTMENT_MODE':mode,'LIFE_MANAGER_INVESTMENT_OWNER_ID':f'alpaca-investment-{mode}'}):
                root=Path(directory);args=closing_fee_fixture(root,mode);owned,broker,account,owner,activity=args
                native=native_run();ledger=root/'receipts.jsonl'
                with patch.object(native,'observe',return_value=account),patch.object(native,'read_crypto_activity_evidence',return_value=activity) as reader:
                    result=store.reconcile_started(ledger,lambda _:broker,on_reconciled=lambda intent,bk:
                        native._reconcile_crypto_close(intent,bk,state=root,credentials_path=Path('unused'),cli_path=Path('unused')))
                self.assertEqual(result['unresolved'],0)
                self.assertEqual(reader.call_args.kwargs['period_start'],activity['requested_period_start'])
                with patch.object(native,'find_order_by_client_id',return_value=broker),\
                     patch.object(native,'read_crypto_activity_evidence',side_effect=AssertionError('replay read')):
                    opened=native._sync_live_ownership(root,Path('unused'),Path('unused'),account)
                    stable=ledger.read_bytes()
                    self.assertEqual(native._sync_live_ownership(root,Path('unused'),Path('unused'),account),opened)
                self.assertEqual(opened['status'],'open');self.assertEqual(opened['owned_qty'],'0.029925')
                self.assertEqual(ledger.read_bytes(),stable)
                self.assertEqual(position_manager.load_owned_policy(root,opened,mode=mode)['owned_qty'],'0.029925')
                record_sell(root,opened,activity,mode=mode,before='0.029925',qty='0.029925',remaining='0',
                    start='2026-01-01T04:20:00Z',partial=False)
                state=proofs.owned_quantity_state_from_rows(store._rows(ledger),opened,mode=mode,owner_id=owner)
                self.assertEqual(state['sold_qty'],'0.049925');self.assertEqual(state['debited_qty'],'0.000075')
                self.assertEqual(state['owned_qty'],'0');self.assertTrue(core_guard()(opened,store._rows(ledger)))

    def test_missing_foreign_late_or_unscoped_fees_never_repair_a_quantity_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);args=closing_fee_fixture(root)
            owned,broker,account,owner,activity=args;before=(root/'receipts.jsonl').read_bytes()
            frames=[activity_fixture(activity,mode='paper',start=activity['requested_period_start'],end=NOW,fees=[]),
                activity_fixture(activity,mode='paper',start=activity['requested_period_start'],end=NOW,
                    fees=[{**activity['fees'][0],'order_id':'foreign'}]),
                activity_fixture(activity,mode='paper',start=activity['requested_period_start'],end=NOW,
                    fees=[{**activity['fees'][0],'created_at':'2026-01-01T04:15:03Z'}]),
                activity_fixture(activity,mode='paper',start=broker['submitted_at'],end=NOW)]
            for i,frame in enumerate(frames):
                with self.subTest(case=i),self.assertRaises(ValueError):self.proof(root,(*args[:4],frame))
                self.assertEqual((root/'receipts.jsonl').read_bytes(),before)
                self.assertEqual(store.unresolved_intent_count(root/'receipts.jsonl'),1)

    def test_explicit_fee_cannot_make_an_overdrawn_fully_executed_sell_look_flat(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);args=closing_fee_fixture(root,sold='0.05',remaining='0')
            with self.assertRaises(ValueError):self.proof(root,args)

    def test_tiny_native_fee_survives_small_decimal_precision_and_traps(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);args=list(closing_fee_fixture(root,remaining='0.029999999999999999999999999999'))
            args[4]=activity_fixture(args[4],mode='paper',start=args[4]['requested_period_start'],end=NOW,
                fees=[{**args[4]['fees'][0],'qty':'-0.000000000000000000000000000001'}])
            with localcontext() as context:
                context.prec=8;context.traps[Inexact]=True
                receipt=self.save(root,args)['receipt']
                self.assertEqual(receipt['native_fee_debit']['debit_qty'],'0.000000000000000000000000000001')

    def test_nested_fee_proof_tampering_keeps_the_sell_counter_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);args=closing_fee_fixture(root);self.save(root,args)
            ledger=root/'receipts.jsonl';rows=store._rows(ledger)
            row=next(r for r in rows if r.get('strategy_receipt',{}).get('receipt',{}).get('native_fee_debit'))
            row['strategy_receipt']['receipt']['native_fee_debit']['debit_qty']='0.0001';write_rows(ledger,rows)
            self.assertEqual(store.unresolved_intent_count(ledger),1)
            with self.assertRaises(ValueError):
                proofs.owned_quantity_state_from_rows(rows,args[0],mode='paper',owner_id=args[3])

    def test_parent_buy_fills_cannot_contradict_the_order_even_without_a_fee_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);args=list(closing_fee_fixture(root,remaining='0.03'))
            fills=copy.deepcopy(args[4]['fills']);fills[0]['qty']='0.051'
            args[4]=activity_fixture({'fills':fills,'fees':[]},mode='paper',start=args[4]['requested_period_start'],end=NOW)
            with self.assertRaises(ValueError):self.proof(root,args)

    def test_a_buy_fill_set_observed_during_close_cannot_be_replaced_by_new_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);args=closing_fee_fixture(root);self.save(root,args)
            owned={**args[0],'status':'open','owned_qty':'0.029925'}
            old=args[4];later=activity_fixture({'fills':[{**old['fills'][0],'id':'different-buy-fill'}],
                'fees':old['fees']+[{**old['fees'][0],'id':'later-buy-fee','qty':'-0.000025',
                    'created_at':'2026-01-01T04:16:00Z'}]},mode='paper',start=old['requested_period_start'],end='2026-01-01T04:16:02Z')
            account={**args[2],'positions':[{'symbol':'BTCUSD','qty':'0.0299'}],
                'clock':{'observed_at':'2026-01-01T04:16:02Z'}}
            before=(root/'receipts.jsonl').read_bytes()
            with self.assertRaises(ValueError):
                store.record_native_fee_debit(root/'receipts.jsonl',owned,account,activity_readback=later,
                    mode='paper',owner_id=args[3])
            self.assertEqual((root/'receipts.jsonl').read_bytes(),before)
