"""Existing closed markers require fresh official evidence, never just a label."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import effect_store as store
import position_manager
from test_crypto_close import close_fixture, native_run
from test_owned_policy import seed


def no_fill_fixture(root,mode='live'):
    owned,owner=seed(root,mode=mode)
    rows=[r for r in store._rows(root/'receipts.jsonl')
          if r.get('receipt_type')!='outcome' and r.get('status')!='applied']
    (root/'receipts.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    owned.update(status='closed',entry_filled_qty='0');owned.pop('owned_qty',None)
    (root/'live-owned-position.json').write_text(json.dumps(owned))
    broker={'id':'official-no-fill','client_order_id':owned['entry_client_order_id'],
            'symbol':'BTCUSDC','side':'buy','type':'market','time_in_force':'gtc',
            'status':'rejected','filled_qty':'0','filled_at':None,'submitted_at':'2026-01-01T04:00:00Z'}
    store.reconcile_started(root/'receipts.jsonl',lambda _:copy.deepcopy(broker))
    observation={'mode':mode,'paper':mode=='paper','positions':[],
                 'account':{'cash':'90','equity':'100'},'clock':{'observed_at':'2026-01-01T04:15:02Z'}}
    return owned,broker,observation,owner


class ClosedAuditTests(unittest.TestCase):
    def test_closed_sell_requeries_the_close_and_validates_its_recorded_proof(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{
                    'LIFE_MANAGER_INVESTMENT_MODE':mode,'LIFE_MANAGER_INVESTMENT_OWNER_ID':f'alpaca-investment-{mode}'}):
                root=Path(directory);owned,broker,observation,_=close_fixture(root,mode)
                proof=position_manager.close_fill_proof(root,owned,broker,observation,mode=mode)
                store.reconcile_started(root/'receipts.jsonl',lambda _:broker,on_reconciled=lambda *_:proof)
                owned['status']='closed'
                (root/'live-owned-position.json').write_text(json.dumps(owned))
                before=(root/'receipts.jsonl').read_bytes()
                native=native_run()
                with patch.object(native,'find_order_by_client_id',return_value=broker) as find:
                    self.assertEqual(native._sync_live_ownership(root,Path('unused'),Path('unused'),observation),owned)
                self.assertEqual(find.call_args.kwargs['client_order_id'],owned['close_client_order_id'])
                self.assertEqual((root/'receipts.jsonl').read_bytes(),before)

    def test_closed_sell_without_a_receipt_is_not_accepted_or_rewritten(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{
                'LIFE_MANAGER_INVESTMENT_MODE':'live','LIFE_MANAGER_INVESTMENT_OWNER_ID':'alpaca-investment-live'}):
            root=Path(directory);owned,broker,observation,_=close_fixture(root)
            owned['status']='closed';(root/'live-owned-position.json').write_text(json.dumps(owned))
            before=(root/'live-owned-position.json').read_bytes()
            native=native_run()
            with patch.object(native,'find_order_by_client_id',return_value=broker):
                with self.assertRaises(ValueError):
                    native._sync_live_ownership(root,Path('unused'),Path('unused'),observation)
            self.assertEqual((root/'live-owned-position.json').read_bytes(),before)

    def test_zero_fill_closed_is_verified_once_and_then_replays_without_ledger_append(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{
                    'LIFE_MANAGER_INVESTMENT_MODE':mode,'LIFE_MANAGER_INVESTMENT_OWNER_ID':f'alpaca-investment-{mode}'}):
                root=Path(directory);owned,broker,observation,_=no_fill_fixture(root,mode)
                native=native_run()
                with patch.object(native,'find_order_by_client_id',return_value=broker):
                    actual=native._sync_live_ownership(root,Path('unused'),Path('unused'),observation)
                    self.assertEqual(actual,owned)
                    rows=store._rows(root/'receipts.jsonl')
                    receipt=rows[-1].get('strategy_receipt',{}).get('receipt',{})
                    self.assertEqual(receipt.get('kind'),'owned_crypto_no_fill')
                    self.assertIsNone(receipt.get('net_realized_pnl_usd'))
                    before=(root/'receipts.jsonl').read_bytes()
                    native._sync_live_ownership(root,Path('unused'),Path('unused'),observation)
                self.assertEqual((root/'receipts.jsonl').read_bytes(),before)

    def test_conflicting_terminal_owner_policy_or_status_cannot_be_enriched(self):
        for key,value in (('owner_id','alpaca-investment-paper'),('strategy_id','foreign'),
                          ('release_sha','b'*40),('broker_status','accepted')):
            with self.subTest(key=key),tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{
                    'LIFE_MANAGER_INVESTMENT_MODE':'live','LIFE_MANAGER_INVESTMENT_OWNER_ID':'alpaca-investment-live'}):
                root=Path(directory);_owned,broker,observation,_=no_fill_fixture(root)
                rows=store._rows(root/'receipts.jsonl')
                rows[-1][key]=value
                (root/'receipts.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
                before=(root/'receipts.jsonl').read_bytes()
                native=native_run()
                with patch.object(native,'find_order_by_client_id',return_value=broker):
                    with self.assertRaises(ValueError): native._sync_live_ownership(root,Path('unused'),Path('unused'),observation)
                self.assertEqual((root/'receipts.jsonl').read_bytes(),before)

    def test_closed_label_cannot_hide_wrong_quantity_identity_mode_or_missing_evidence(self):
        variants=(('broker','filled_qty',None),('broker','filled_qty','0.01'),
                  ('broker','client_order_id','foreign'),('broker','id','foreign'),
                  ('broker','status','filled'),('observation','mode','paper'),
                  ('observation','paper',True),('observation','account',{'cash':'0','equity':'NaN'}),
                  ('owned','entry_filled_qty','0.01'),('owned','close_effect_id','a'*64))
        for section,key,value in variants:
            with self.subTest(section=section,key=key),tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{
                    'LIFE_MANAGER_INVESTMENT_MODE':'live','LIFE_MANAGER_INVESTMENT_OWNER_ID':'alpaca-investment-live'}):
                root=Path(directory);owned,broker,observation,_=no_fill_fixture(root)
                {'broker':broker,'observation':observation,'owned':owned}[section][key]=value
                (root/'live-owned-position.json').write_text(json.dumps(owned))
                before=(root/'receipts.jsonl').read_bytes()
                native=native_run()
                with patch.object(native,'find_order_by_client_id',return_value=broker):
                    with self.assertRaises(ValueError): native._sync_live_ownership(root,Path('unused'),Path('unused'),observation)
                self.assertEqual((root/'receipts.jsonl').read_bytes(),before)


if __name__=='__main__': unittest.main()
