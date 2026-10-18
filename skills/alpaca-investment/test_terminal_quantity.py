"""Terminal broker status is not proof that an unknown fill quantity is zero."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import effect_store as store


class TerminalQuantityTests(unittest.TestCase):
    def test_only_explicit_finite_zero_closes_terminal_orders(self):
        for qty in (None,'','NaN','Infinity','-1','0.01','0'):
            for mode in ('paper','live'):
                with self.subTest(mode=mode,qty=qty),tempfile.TemporaryDirectory() as directory:
                    ledger=Path(directory)/'receipts.jsonl'
                    sealed=store.seal(ledger,{'mode':mode},
                        {'asset_class':'crypto','side':'buy','symbol':'BTC/USDC'})
                    store.mark_started(ledger,sealed)
                    broker={'id':'official-order','client_order_id':sealed['client_order_id'],
                            'status':'canceled','filled_qty':qty}
                    outcome={'outcome':'broker_terminal_failure','broker':broker}
                    self.assertEqual(store._outcome_closed(outcome),qty=='0')
                    result=store.reconcile_started(ledger,lambda _:broker)
                    if qty=='0':
                        self.assertEqual(result['unresolved'],0)
                        self.assertEqual(store.effect_state(ledger,sealed['effect_id']),'outcome')
                    else:
                        self.assertEqual(result['unresolved'],1)
                        self.assertEqual(result['deferred'],1)
                        self.assertEqual(store.unresolved_intent_count(ledger),1)
                        self.assertEqual(store.effect_state(ledger,sealed['effect_id']),'started')
                        last=store._rows(ledger)[-1]
                        self.assertEqual(last.get('broker_receipt_id'),'official-order')
                        self.assertIn('filled_qty',last)
                        self.assertEqual(last['filled_qty'],qty)
                        self.assertEqual(last['reason'],'partial_fill_requires_reconciliation'
                                         if qty=='0.01' else 'fill_quantity_unknown')

    def test_a_known_positive_fill_cannot_be_reset_to_zero_by_a_later_status(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                ledger=Path(directory)/'receipts.jsonl'
                sealed=store.seal(ledger,{'mode':mode},{'asset_class':'crypto','side':'buy','symbol':'BTC/USDC'})
                store.mark_started(ledger,sealed)
                broker={'id':'official-order','client_order_id':sealed['client_order_id'],
                        'status':'canceled','filled_qty':'0.01'}
                store.reconcile_started(ledger,lambda _:broker)
                broker['filled_qty']='0'
                result=store.reconcile_started(ledger,lambda _:broker)
                self.assertEqual(result['unresolved'],1)
                self.assertEqual(store.unresolved_intent_count(ledger),1)
                self.assertEqual(store.effect_state(ledger,sealed['effect_id']),'started')
                self.assertEqual(store._rows(ledger)[-1]['reason'],'fill_quantity_conflict')
                self.assertFalse(any(r.get('outcome')=='broker_terminal_failure' for r in store._rows(ledger)))

    def test_unknown_quantity_can_recover_to_an_official_explicit_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger=Path(directory)/'receipts.jsonl'
            sealed=store.seal(ledger,{'mode':'paper'},{'side':'buy'})
            store.mark_started(ledger,sealed)
            broker={'id':'official-order','client_order_id':sealed['client_order_id'],
                    'status':'rejected','filled_qty':None}
            pending=store.reconcile_started(ledger,lambda _:broker)
            self.assertEqual(pending['unresolved'],1)
            broker['filled_qty']='0'
            result=store.reconcile_started(ledger,lambda _:broker)
            self.assertEqual(result['unresolved'],0)
            before=ledger.read_bytes()
            store.reconcile_started(ledger,lambda _:self.fail('completed no-fill should not be queried again'))
            self.assertEqual(ledger.read_bytes(),before)


if __name__=='__main__': unittest.main()
