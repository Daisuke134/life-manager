"""One historical quantity fold serves sell boundaries and future native debits."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import crypto_ownership_proof as proofs
import effect_store as store
from test_crypto_entry import entry_fixture
from test_crypto_performance import cycle_fixture


class CryptoQuantityStateTests(unittest.TestCase):
    def state(self,rows,owned,mode='paper',**kwargs):
        reader=getattr(proofs,'owned_quantity_state_from_rows',None)
        self.assertTrue(callable(reader),'owned quantity must share the existing historical proof fold')
        return reader(rows,owned,mode=mode,owner_id=f'alpaca-investment-{mode}',**kwargs)

    def test_initial_state_uses_observed_credit_and_requires_a_valid_cutoff(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);marker,broker,account,owner=entry_fixture(root,mode,owned_qty='0.049875')
                ledger=root/'receipts.jsonl'
                proof=proofs.entry_fill_proof_from_rows(store._rows(ledger),marker,broker,account,mode=mode,owner_id=owner)
                store.reconcile_started(ledger,lambda _:broker,on_reconciled=lambda *_:proof)
                marker.update(status='open',owned_qty='0.049875',entry_filled_qty='0.05')
                rows=store._rows(ledger);result=self.state(rows,marker,mode)
                self.assertEqual(result['owned_qty'],'0.049875')
                self.assertEqual(result['sold_qty'],'0')
                self.assertIsNone(result['last_close_effect_id'])
                for cutoff in (True,-1,len(rows)+1):
                    with self.subTest(cutoff=cutoff),self.assertRaises(ValueError):
                        self.state(rows,marker,mode,upto_index=cutoff)

    def test_cutoff_partial_zero_and_full_close_share_one_quantity_history(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);orders,_,owned=cycle_fixture(root,mode,partial=True,zero=True)
                ledger=root/'receipts.jsonl';rows=store._rows(ledger);old=copy.deepcopy(owned);before=ledger.read_bytes()
                cutoff=next(i for i,r in enumerate(rows) if r.get('receipt_type')=='effect_intent'
                    and r.get('status')=='planned' and r.get('effect_id')==owned['close_effect_id'])
                prior=self.state(rows,owned,mode,upto_index=cutoff)
                self.assertEqual(prior['owned_qty'],'0.03');self.assertEqual(prior['sold_qty'],'0.02')
                self.assertNotIn(orders[-1]['id'],prior['provider_order_ids'])
                final=self.state(rows,owned,mode)
                self.assertEqual(final['owned_qty'],'0');self.assertEqual(final['sold_qty'],'0.05')
                self.assertEqual(final['last_close_effect_id'],owned['close_effect_id'])
                self.assertEqual(final['provider_order_ids'],{o['id'] for o in orders})
                self.assertEqual(owned,old);self.assertEqual(ledger.read_bytes(),before)

    def test_past_receipt_tampering_and_reselling_after_flat_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,_,owned=cycle_fixture(root,partial=True)
            ledger=root/'receipts.jsonl';rows=store._rows(ledger);bad=copy.deepcopy(rows)
            leg=next(r for r in bad if r.get('strategy_receipt',{}).get('receipt',{}).get('kind')=='owned_crypto_sell_remainder')
            leg['strategy_receipt']['receipt']['remaining_owned_qty']='0.031'
            with self.assertRaises(ValueError): self.state(bad,owned)
            intent=next(r for r in rows if r.get('receipt_type')=='effect_intent' and r.get('status')=='planned'
                and r.get('effect_id')==owned['close_effect_id'])
            decision=copy.deepcopy(next(r['decision'] for r in rows if r.get('receipt_type')=='decision'
                and r.get('decision_id')==intent['decision_id']))
            decision.update(observed_at='2026-01-01T05:00:00Z',position_qty='0.01')
            store.seal(ledger,decision,{**intent['order'],'qty':'0.01'})
            with self.assertRaises(ValueError): self.state(store._rows(ledger),owned)
