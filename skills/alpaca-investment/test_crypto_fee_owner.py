"""Automatic owner synchronization consumes the same proven fee quantity chain."""
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
import alpaca_cli as cli
import crypto_ownership_proof as proofs
import effect_store as store
import position_manager as positions
from test_crypto_close import native_run
from test_crypto_fee_debit import debit_fixture,END
from test_crypto_fee_ledger import write_rows
from test_crypto_performance import activity_fixture


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
