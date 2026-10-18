"""The existing receipt ledger applies each proven native debit once."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import crypto_ownership_proof as proofs
import effect_store as store
from test_crypto_fee_debit import debit_fixture,END
from test_crypto_performance import activity_fixture


def write_rows(path,rows):
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))


def record_sell(root,owned,frame,*,mode,before,qty,remaining,start,partial):
    owner=f'alpaca-investment-{mode}';ledger=root/'receipts.jsonl'
    parent=proofs._owned_policy(proofs.owned_entry_decision_from_rows(store._rows(ledger),owned,
        mode=mode,owner_id=owner),owned,mode=mode)
    decision={'action':'EXIT','mode':mode,'owner_id':owner,'strategy_id':parent['card'].strategy_id,
        'release_sha':parent['release_sha'],'position_qty':before,'observed_at':start,
        **{k:parent[k] for k in ('entry_effect_id','entry_client_order_id','entry_provider_order_id','entry_price','entry_timestamp')}}
    sealed=store.seal(ledger,decision,{'asset_class':'crypto','symbol':'BTC/USDC','side':'sell','type':'market',
        'time_in_force':'gtc','qty':before});store.mark_started(ledger,sealed)
    owned.update(status='closing',close_effect_id=sealed['effect_id'],close_client_order_id=sealed['client_order_id'])
    filled=(proofs.parse_instant(start)+timedelta(seconds=1)).isoformat()
    observed=(proofs.parse_instant(start)+timedelta(seconds=2)).isoformat()
    broker={'id':f'sell-{start}','client_order_id':sealed['client_order_id'],'status':'canceled' if partial else 'filled',
        'symbol':'BTCUSDC','side':'sell','type':'market','time_in_force':'gtc','qty':before,'filled_qty':qty,
        'filled_avg_price':None if partial else '210','submitted_at':start,'filled_at':None if partial else filled}
    account={'mode':mode,'paper':mode=='paper','account':{'cash':'0','equity':'100'},
        'positions':[] if remaining=='0' else [{'symbol':'BTCUSDC','qty':remaining}], 'clock':{'observed_at':observed}}
    if partial:
        activity=activity_fixture({'fills':[{'id':f'fill-{start}','activity_type':'FILL','order_id':broker['id'],
            'symbol':'BTCUSDC','side':'sell','qty':qty,'price':'210','transaction_time':filled}],'fees':frame['fees']},
            mode=mode,start=start,end=observed)
        proof=proofs.sell_remainder_proof_from_rows(store._rows(ledger),owned,broker,account,
            mode=mode,owner_id=owner,activity_readback=activity)
    else:
        proof=proofs.close_fill_proof_from_rows(store._rows(ledger),owned,broker,account,mode=mode,owner_id=owner)
    store.reconcile_started(ledger,lambda _:broker,on_reconciled=lambda *_:proof)
    if remaining=='0':owned['status']='closed'
    else:owned.update(status='open',owned_qty=remaining)
    return broker,account


class CryptoFeeLedgerTests(unittest.TestCase):
    def record(self,root,owned,frame,account,mode='paper'):
        writer=getattr(store,'record_native_fee_debit',None)
        self.assertTrue(callable(writer),'native fee proof must persist under the existing ledger lock')
        return writer(root/'receipts.jsonl',owned,account,activity_readback=frame,
            mode=mode,owner_id=f'alpaca-investment-{mode}')

    def state(self,root,owned,mode='paper',**kwargs):
        return proofs.owned_quantity_state_from_rows(store._rows(root/'receipts.jsonl'),owned,
            mode=mode,owner_id=f'alpaca-investment-{mode}',**kwargs)

    def test_concurrent_replay_after_save_preserves_the_original_acquisition_and_marker(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);_,owned,frame,account=debit_fixture(root,mode)
                old=copy.deepcopy(owned);ledger=root/'receipts.jsonl';before=ledger.read_bytes()
                with ThreadPoolExecutor(max_workers=4) as pool:
                    results=list(pool.map(lambda _:self.record(root,owned,frame,account,mode),range(8)))
                self.assertEqual(results.count(True),1);self.assertEqual(results.count(False),7)
                rows=store._rows(ledger);events=[r for r in rows if r.get('receipt_type')=='native_fee_debit']
                self.assertEqual(len(events),1);self.assertEqual(events[0]['strategy_receipt']['receipt']['debit_qty'],'0.000075')
                self.assertTrue(ledger.read_bytes().startswith(before));self.assertEqual(owned,old)
                self.assertEqual(ledger.stat().st_mode&0o777,0o600)
                state=self.state(root,owned,mode)
                self.assertEqual(state['owned_qty'],'0.049925');self.assertEqual(state['debited_qty'],'0.000075')
                self.assertEqual(store.unresolved_intent_count(ledger),0)
                self.assertEqual(self.state(root,owned,mode,upto_index=len(rows)-1)['owned_qty'],'0.05')
                stable=ledger.read_bytes();self.assertFalse(self.record(root,owned,frame,account,mode))
                self.assertEqual(ledger.read_bytes(),stable)

    def test_already_embedded_fee_is_not_appended_and_wrong_stale_marker_is_not_recovered(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,owned,frame,account=debit_fixture(root,credit='0.049925')
            ledger=root/'receipts.jsonl';before=ledger.read_bytes()
            self.assertFalse(self.record(root,owned,frame,account));self.assertEqual(ledger.read_bytes(),before)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,owned,frame,account=debit_fixture(root)
            self.assertTrue(self.record(root,owned,frame,account));before=(root/'receipts.jsonl').read_bytes()
            for change in ({'owned_qty':'0.0499'},{'entry_filled_qty':'0.06'},{'status':'closing'},
                           {'close_effect_id':'a'*64},{'entry_client_order_id':'foreign'}):
                with self.subTest(change=change),self.assertRaises(ValueError):
                    self.record(root,{**owned,**change},frame,account)
            self.assertEqual((root/'receipts.jsonl').read_bytes(),before)

    def test_multiple_adjustments_use_cumulative_fees_and_only_the_new_debit(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);_,owned,frame,account=debit_fixture(root,mode,credit='0.04995')
                self.assertTrue(self.record(root,owned,frame,account,mode));owned['owned_qty']='0.049925'
                extra={**frame['fees'][0],'id':'later-fee','qty':'-0.000025','created_at':'2026-01-03T00:00:03Z'}
                later=activity_fixture(frame,mode=mode,start=frame['requested_period_start'],
                    end='2026-01-03T04:00:00Z',fees=frame['fees']+[extra])
                current={**account,'clock':{'observed_at':'2026-01-03T04:00:00Z'},'positions':[{'symbol':'BTCUSDC','qty':'0.0499'}]}
                self.assertTrue(self.record(root,owned,later,current,mode))
                state=self.state(root,owned,mode)
                self.assertEqual(state['owned_qty'],'0.0499');self.assertEqual(state['debited_qty'],'0.00005')
                events=[r for r in store._rows(root/'receipts.jsonl') if r.get('receipt_type')=='native_fee_debit']
                self.assertEqual([r['strategy_receipt']['receipt']['debit_qty'] for r in events],['0.000025','0.000025'])
                self.assertNotEqual(events[0]['fee_debit_id'],events[1]['fee_debit_id'])

    def test_fee_then_partial_and_full_sell_use_the_same_quantity_chain(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);_,owned,frame,account=debit_fixture(root,mode)
                self.assertTrue(self.record(root,owned,frame,account,mode));owned['owned_qty']='0.049925'
                record_sell(root,owned,frame,mode=mode,before='0.049925',qty='0.02',remaining='0.029925',
                    start='2026-01-02T04:05:00Z',partial=True)
                self.assertEqual(self.state(root,owned,mode)['owned_qty'],'0.029925')
                record_sell(root,owned,frame,mode=mode,before='0.029925',qty='0.029925',remaining='0',
                    start='2026-01-02T04:10:00Z',partial=False)
                state=self.state(root,owned,mode)
                self.assertEqual(state['owned_qty'],'0');self.assertEqual(state['sold_qty'],'0.049925')
                self.assertEqual(state['debited_qty'],'0.000075')
                self.assertEqual(store.unresolved_intent_count(root/'receipts.jsonl'),0)

    def test_saved_event_tampering_duplicate_and_pre_acquisition_order_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,owned,frame,account=debit_fixture(root)
            self.assertTrue(self.record(root,owned,frame,account));rows=store._rows(root/'receipts.jsonl')
            variants=[]
            for key,value in (('mode','live'),('owner_id','foreign'),('fee_debit_id','forged'),('schema_version',True)):
                bad=copy.deepcopy(rows);bad[-1][key]=value;variants.append(bad)
            bad=copy.deepcopy(rows);bad[-1]['strategy_receipt']['receipt']['remaining_owned_qty']='0.04';variants.append(bad)
            bad=copy.deepcopy(rows);bad[-1].update(entry_effect_id='foreign',strategy_receipt=None);variants.append(bad)
            variants.extend((copy.deepcopy(rows)+[copy.deepcopy(rows[-1])], [copy.deepcopy(rows[-1])]+copy.deepcopy(rows[:-1])))
            for i,bad in enumerate(variants):
                write_rows(root/'receipts.jsonl',bad)
                with self.subTest(case=i),self.assertRaises(ValueError):self.state(root,owned)

    def test_fee_after_partial_sell_preserves_its_receipt_and_requires_that_receipt_first(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);rows,owned,frame,account=debit_fixture(root,mode,partial=True)
                ledger=root/'receipts.jsonl';write_rows(ledger,rows);before=ledger.read_bytes()
                self.assertTrue(self.record(root,owned,frame,account,mode))
                self.assertTrue(ledger.read_bytes().startswith(before))
                state=self.state(root,owned,mode)
                self.assertEqual(state['owned_qty'],'0.029925');self.assertEqual(state['sold_qty'],'0.02')
                saved=store._rows(ledger);event=saved[-1]
                receipt_index=next(i for i,r in enumerate(saved) if r.get('receipt_type')=='outcome'
                    and r.get('effect_id')==owned['close_effect_id'])
                write_rows(ledger,saved[:receipt_index]+[event]+saved[receipt_index:-1])
                with self.assertRaises(ValueError):self.state(root,owned,mode)
                write_rows(ledger,saved);owned['owned_qty']='0.029925'
                record_sell(root,owned,frame,mode=mode,before='0.029925',qty='0.029925',remaining='0',
                    start='2026-01-02T04:10:00Z',partial=False)
                final=self.state(root,owned,mode)
                self.assertEqual(final['owned_qty'],'0');self.assertEqual(final['sold_qty'],'0.049925')

    def test_pending_sell_prevents_a_fee_event_from_being_appended(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,owned,frame,account=debit_fixture(root)
            ledger=root/'receipts.jsonl'
            parent=proofs._owned_policy(proofs.owned_entry_decision_from_rows(store._rows(ledger),owned,
                mode='paper',owner_id='alpaca-investment-paper'),owned,mode='paper')
            decision={'action':'EXIT','mode':'paper','owner_id':'alpaca-investment-paper',
                'strategy_id':parent['card'].strategy_id,'release_sha':parent['release_sha'],
                'position_qty':'0.05','observed_at':'2026-01-01T04:05:00Z',
                **{k:parent[k] for k in ('entry_effect_id','entry_client_order_id','entry_provider_order_id','entry_price','entry_timestamp')}}
            sealed=store.seal(ledger,decision,{'asset_class':'crypto','symbol':'BTC/USDC','side':'sell','type':'market',
                'time_in_force':'gtc','qty':'0.05'});store.mark_started(ledger,sealed)
            before=ledger.read_bytes()
            with self.assertRaises(ValueError):self.record(root,owned,frame,account)
            self.assertEqual(ledger.read_bytes(),before)

    def test_explicit_fee_consuming_all_remaining_btc_replays_without_another_debit(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);_,owned,frame,account=debit_fixture(root,mode)
                frame=activity_fixture(frame,mode=mode,start=frame['requested_period_start'],end=END,
                    fees=[{**frame['fees'][0],'qty':'-0.05'}]);account['positions']=[]
                self.assertTrue(self.record(root,owned,frame,account,mode))
                before=(root/'receipts.jsonl').read_bytes()
                self.assertEqual(self.state(root,owned,mode)['owned_qty'],'0')
                self.assertFalse(self.record(root,owned,frame,account,mode))
                self.assertEqual((root/'receipts.jsonl').read_bytes(),before)
