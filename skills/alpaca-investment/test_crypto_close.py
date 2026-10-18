"""Crypto close receipts use sealed ownership and official readback fixtures only."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import effect_store
import position_manager
from test_owned_policy import seed


def close_fixture(root, mode='live'):
    owned,owner=seed(root,mode=mode)
    parent=position_manager.load_owned_policy(root,owned,mode=mode)
    decision={'action':'EXIT','position_action':'EXIT','mode':mode,'owner_id':owner,
              'strategy_id':parent['card'].strategy_id,'release_sha':parent['release_sha'],
              'position_qty':'0.05','observed_at':'2026-01-01T04:15:00Z',
              **{key:parent[key] for key in ('entry_effect_id','entry_client_order_id',
                                           'entry_provider_order_id','entry_price','entry_timestamp')}}
    order={'asset_class':'crypto','side':'sell','symbol':'BTC/USDC',
           'qty':'0.05','type':'market','time_in_force':'gtc'}
    sealed=effect_store.seal(root/'receipts.jsonl',decision,order)
    effect_store.mark_started(root/'receipts.jsonl',sealed)
    owned.update(status='closing',close_effect_id=sealed['effect_id'],
                 close_client_order_id=sealed['client_order_id'])
    (root/'live-owned-position.json').write_text(json.dumps(owned))
    broker={'id':'official-exit','client_order_id':sealed['client_order_id'],
            'symbol':'BTCUSDC','side':'sell','status':'filled','type':'market',
            'time_in_force':'gtc','qty':'0.05','filled_qty':'0.05','filled_avg_price':'210',
            'submitted_at':'2026-01-01T04:15:00Z','filled_at':'2026-01-01T04:15:01Z'}
    observation={'clock':{'observed_at':'2026-01-01T04:15:02Z'},
                 'account':{'cash':'0','equity':'100'},
                 'positions':[{'symbol':'USDCUSD','qty':'100'}]}
    return owned,broker,observation,owner


def native_run():
    spec=importlib.util.spec_from_file_location('crypto_close_native',ROOT/'run.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class CryptoCloseTests(unittest.TestCase):
    def proof(self,*args,**kwargs):
        function=getattr(position_manager,'close_fill_proof',None)
        self.assertTrue(callable(function),'official close/account proof reader is required')
        return function(*args,**kwargs)

    def test_filled_status_and_missing_btc_without_receipt_cannot_close_marker(self):
        native=native_run()
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{
                'LIFE_MANAGER_INVESTMENT_MODE':'live','LIFE_MANAGER_INVESTMENT_OWNER_ID':'alpaca-investment-live'}):
            root=Path(directory);owned,broker,observation,_owner=close_fixture(root)
            with patch.object(native,'find_order_by_client_id',return_value=broker):
                with self.assertRaisesRegex(ValueError,'owned_close_receipt_missing'):
                    native._sync_live_ownership(root,Path('unused'),Path('unused'),observation)
            self.assertEqual(json.loads((root/'live-owned-position.json').read_text()),owned)

    def test_complete_close_receipt_is_mode_scoped_and_replay_does_not_append(self):
        for mode in ('live','paper'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{
                    'LIFE_MANAGER_INVESTMENT_MODE':mode,'LIFE_MANAGER_INVESTMENT_OWNER_ID':f'alpaca-investment-{mode}'}):
                root=Path(directory);owned,broker,observation,owner=close_fixture(root,mode)
                proof=self.proof(root,owned,broker,observation,mode=mode)
                self.assertEqual(proof['receipt']['owner_id'],owner)
                self.assertEqual(proof['receipt']['quote_currency'],'USDC')
                self.assertIsNone(proof['receipt']['net_realized_pnl_usd'])
                effect_store.reconcile_started(root/'receipts.jsonl',lambda _client:broker,
                                               on_reconciled=lambda _intent,_broker:proof)
                before=(root/'receipts.jsonl').read_bytes()
                native=native_run()
                with patch.object(native,'find_order_by_client_id',return_value=broker):
                    closed=native._sync_live_ownership(root,Path('unused'),Path('unused'),observation)
                    replay=native._sync_live_ownership(root,Path('unused'),Path('unused'),observation)
                self.assertEqual(closed['status'],'closed')
                self.assertEqual(replay,closed)
                self.assertEqual(closed['entry_effect_id'],owned['entry_effect_id'])
                self.assertEqual((root/'receipts.jsonl').read_bytes(),before)

    def test_invalid_order_quantity_time_account_and_parent_cannot_make_close_proof(self):
        variants=[('broker','client_order_id','foreign'),('broker','id',''),
                  ('broker','side','buy'),('broker','symbol','ETH/USDC'),
                  ('broker','status','partially_filled'),('broker','filled_qty','0.04'),
                  ('broker','filled_avg_price','NaN'),('broker','filled_at',None),
                  ('broker','filled_at','2026-01-01T04:16:00Z'),
                  ('broker','submitted_at','2026-01-01T04:14:00Z'),
                  ('owned','close_effect_id','b'*64),('owned','entry_effect_id','c'*64),
                  ('owned','owned_qty','0.04'),('observation','positions',[{'symbol':'BTCUSDC','qty':'0.05'}]),
                  ('observation','clock',{'observed_at':'invalid'}),
                  ('observation','account',{'cash':'0','equity':'NaN'})]
        for section,key,value in variants:
            with self.subTest(section=section,key=key),tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{
                    'LIFE_MANAGER_INVESTMENT_OWNER_ID':'alpaca-investment-live'}):
                root=Path(directory);owned,broker,observation,_owner=close_fixture(root)
                {'broker':broker,'owned':owned,'observation':observation}[section][key]=value
                before=(root/'receipts.jsonl').read_bytes()
                with self.assertRaises(ValueError): self.proof(root,owned,broker,observation,mode='live')
                self.assertEqual((root/'receipts.jsonl').read_bytes(),before)


if __name__=='__main__': unittest.main()
