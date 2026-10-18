"""Native fee recovery requires immutable history and an exact fresh account."""
import copy
from decimal import Inexact, localcontext
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import crypto_ownership_proof as proofs
import effect_store as store
from test_crypto_entry import entry_fixture
from test_crypto_performance import activity_fixture,cycle_fixture

END='2026-01-02T04:00:00Z'


def debit_fixture(root,mode='paper',credit='0.05',*,partial=False):
    ledger=root/'receipts.jsonl'
    if partial:
        orders,_,owned=cycle_fixture(root,mode,partial=True)
        rows=store._rows(ledger)
        cutoff=next(i for i,r in enumerate(rows) if r.get('receipt_type')=='effect_intent'
            and r.get('status')=='planned' and r.get('effect_id')==owned['close_effect_id'])
        rows=rows[:cutoff]
        state=proofs.owned_quantity_state_from_rows(rows,owned,mode=mode,owner_id=f'alpaca-investment-{mode}')
        owned.update(status='open',owned_qty='0.03',close_effect_id=state['last_close_effect_id'],
                     close_client_order_id=state['last_close_client_order_id'])
        broker=orders[0];current='0.029925'
    else:
        owned,broker,account,owner=entry_fixture(root,mode,owned_qty=credit)
        proof=proofs.entry_fill_proof_from_rows(store._rows(ledger),owned,broker,account,mode=mode,owner_id=owner)
        store.reconcile_started(ledger,lambda _:broker,on_reconciled=lambda *_:proof)
        owned.update(status='open',owned_qty=credit,entry_filled_qty='0.05')
        rows=store._rows(ledger);current='0.049925'
    fee={'id':'native-fee','activity_type':'CFEE','order_id':broker['id'],'symbol':'BTCUSD',
        'qty':'-0.000075','date':'2026-01-01','created_at':'2026-01-02T00:00:03Z','net_amount':'0','status':'executed'}
    frame=activity_fixture({'fills':[],'fees':[fee]},mode=mode,start=broker['submitted_at'],end=END)
    account={'mode':mode,'paper':mode=='paper','account':{'cash':'0','equity':'100'},
        'positions':[{'symbol':'BTCUSDC','qty':current}],'clock':{'observed_at':END}}
    return rows,owned,frame,account


class CryptoFeeDebitTests(unittest.TestCase):
    def proof(self,rows,owned,frame,account,mode='paper'):
        reader=getattr(proofs,'native_fee_debit_proof_from_rows',None)
        self.assertTrue(callable(reader),'native fee recovery must compose the existing exact proofs')
        return reader(rows,owned,account,activity_readback=frame,mode=mode,owner_id=f'alpaca-investment-{mode}')

    def test_only_unaccounted_debit_is_recovered_in_both_modes(self):
        # Subtracting the cumulative fee directly from credited qty would fail.
        for mode in ('paper','live'):
            for credit,debit in (('0.05','0.000075'),('0.04995','0.000025'),('0.049925','0')):
                with self.subTest(mode=mode,credit=credit),tempfile.TemporaryDirectory() as directory:
                    root=Path(directory);args=debit_fixture(root,mode,credit)
                    old=copy.deepcopy(args);before=(root/'receipts.jsonl').read_bytes()
                    result=self.proof(*args,mode);receipt=result['receipt']
                    self.assertEqual(receipt['kind'],'owned_crypto_fee_debit')
                    self.assertEqual(receipt['before_owned_qty'],credit)
                    self.assertEqual(receipt['remaining_owned_qty'],'0.049925')
                    self.assertEqual(receipt['debit_qty'],debit)
                    self.assertEqual(receipt['sold_qty'],'0')
                    self.assertEqual(receipt['fee_evidence']['fee_activity_ids'],['native-fee'])
                    self.assertEqual(receipt['fee_completeness_status'],'unknown')
                    self.assertIsNone(receipt['net_realized_pnl_usd'])
                    self.assertEqual(self.proof(*args,mode),result)
                    self.assertEqual(args,old);self.assertEqual((root/'receipts.jsonl').read_bytes(),before)

    def test_prior_partial_sell_is_subtracted_exactly_once(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                args=debit_fixture(Path(directory),mode,partial=True)
                receipt=self.proof(*args,mode)['receipt']
                self.assertEqual(receipt['sold_qty'],'0.02')
                self.assertEqual(receipt['before_owned_qty'],'0.03')
                self.assertEqual(receipt['remaining_owned_qty'],'0.029925')
                self.assertEqual(receipt['debit_qty'],'0.000075')

    def test_lag_and_missing_fees_remain_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            rows,owned,frame,account=debit_fixture(Path(directory))
            lag=copy.deepcopy(account);lag['positions'][0]['qty']='0.05'
            with self.assertRaisesRegex(proofs.ReconciliationPending,'owned_fee_account_pending'):
                self.proof(rows,owned,frame,lag)
            missing=activity_fixture(frame,mode='paper',start=frame['requested_period_start'],end=END,fees=[])
            with self.assertRaisesRegex(proofs.ReconciliationPending,'owned_crypto_fees_pending'):
                self.proof(rows,owned,missing,account)

    def test_inconsistent_identity_history_account_and_window_never_adjust_quantity(self):
        with tempfile.TemporaryDirectory() as directory:
            args=debit_fixture(Path(directory));rows,owned,frame,account=args
            variants=[]
            for qty in ('0.0499','0.06','-1','NaN'):
                bad=list(copy.deepcopy(args));bad[3]['positions'][0]['qty']=qty;variants.append(bad)
            for change in ({'owned_qty':'0.04'},{'entry_filled_qty':'0.06'},{'status':'closing'},
                           {'close_effect_id':'a'*64},{'entry_client_order_id':'foreign'}):
                bad=list(copy.deepcopy(args));bad[1].update(change);variants.append(bad)
            for change in ({'mode':'live'},{'paper':False},{'clock':{'observed_at':'2026-01-02T03:59:59Z'}}):
                bad=list(copy.deepcopy(args));bad[3].update(change);variants.append(bad)
            bad=list(copy.deepcopy(args));bad[3]['positions'].append({'symbol':'BTCUSD','qty':'0.000075'});variants.append(bad)
            bad=list(copy.deepcopy(args));bad[2]=activity_fixture(frame,mode='paper',start='2026-01-02T00:00:00Z',end=END);variants.append(bad)
            bad=list(copy.deepcopy(args));bad[0][-1]['strategy_receipt']['receipt']['account_owned_qty']='0.06';variants.append(bad)
            for i,bad in enumerate(variants):
                with self.subTest(case=i),self.assertRaisesRegex(ValueError,'owned_fee_debit_invalid'):
                    self.proof(*bad)

    def test_tiny_debit_and_explicit_zero_remaining_use_exact_arithmetic(self):
        with tempfile.TemporaryDirectory() as directory:
            rows,owned,frame,account=debit_fixture(Path(directory))
            for fee,qty,debit in (('-0.000000000000000000000000000001','0.049999999999999999999999999999','0.000000000000000000000000000001'),
                                  ('-0.05','0','0.05')):
                evidence=activity_fixture(frame,mode='paper',start=frame['requested_period_start'],end=END,
                    fees=[{**frame['fees'][0],'qty':fee}])
                current={**account,'positions':[] if qty=='0' else [{'symbol':'BTCUSDC','qty':qty}]}
                with self.subTest(fee=fee),localcontext() as context:
                    context.prec=8;context.traps[Inexact]=True
                    receipt=self.proof(rows,owned,evidence,current)['receipt']
                    self.assertEqual(receipt['debit_qty'],debit)
                    self.assertEqual(receipt['remaining_owned_qty'],qty)

    def test_incomplete_cumulative_fee_cannot_increase_owned_quantity(self):
        with tempfile.TemporaryDirectory() as directory:
            args=debit_fixture(Path(directory),credit='0.0499')
            with self.assertRaisesRegex(ValueError,'owned_fee_debit_invalid'):self.proof(*args)

    def test_new_observation_cannot_conflict_with_known_execution_ids_or_facts(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                rows,owned,frame,account=debit_fixture(Path(directory),mode,partial=True)
                partial=next(r['strategy_receipt'] for r in rows if r.get('strategy_receipt',{}).get('receipt',{}).get('kind')=='owned_crypto_sell_remainder')
                known=next(r for r in partial['activity_readback']['fills'] if r['id']=='sell-fill-0-0')
                observed=activity_fixture({'fills':[known],'fees':frame['fees']},mode=mode,
                    start=frame['requested_period_start'],end=END)
                self.assertEqual(self.proof(rows,owned,observed,account,mode)['receipt']['debit_qty'],'0.000075')
                variants=[([], [{**frame['fees'][0],'id':known['id']}]),
                    ([{**known,'qty':'0.021'}],frame['fees']),
                    ([{**known,'id':'unexpected-extra-fill','qty':'0.001'}],frame['fees'])]
                for fills,fees in variants:
                    bad=activity_fixture({'fills':fills,'fees':fees},mode=mode,
                        start=frame['requested_period_start'],end=END)
                    with self.subTest(fills=fills),self.assertRaisesRegex(ValueError,'owned_fee_debit_invalid'):
                        self.proof(rows,owned,bad,account,mode)
