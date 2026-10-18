"""Exact fee observations do not by themselves change owned quantity or USD profit."""
import copy
from decimal import localcontext
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import crypto_ownership_proof as proofs
from test_crypto_entry import entry_fixture
from test_crypto_performance import activity_fixture
from test_crypto_activity_pages import read_chunk,activity_rows

END='2026-01-02T04:00:00Z'


def fee_fixture(root,mode='paper'):
    _,broker,_,_=entry_fixture(root,mode)
    fill={'id':'entry-fill','activity_type':'FILL','order_id':broker['id'],'symbol':'BTCUSDC',
        'side':'buy','qty':'0.05','price':'200','transaction_time':'2026-01-01T04:00:01Z'}
    fees=[{'id':f'entry-fee-{i}','activity_type':'CFEE','order_id':broker['id'],'symbol':'BTCUSD',
        'qty':qty,'date':'2026-01-01','created_at':created,'net_amount':'0','status':'executed'}
        for i,(qty,created) in enumerate((('-0.00005','2026-01-01T04:00:03Z'),
                                         ('-0.000025','2026-01-02T00:00:03Z')))]
    frame=activity_fixture({'fills':[fill],'fees':fees},mode=mode,start=broker['submitted_at'],end=END)
    return broker,frame


class CryptoBuyFeeProofTests(unittest.TestCase):
    def proof(self,frame,broker,mode='paper'):
        reader=getattr(proofs,'crypto_buy_fee_activity_proof',None)
        self.assertTrue(callable(reader),'shared native buy fee proof is required')
        return reader(frame,broker,mode=mode)

    def test_exact_native_debits_in_all_snapshot_forms_and_both_modes(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);broker,frame=fee_fixture(root,mode)
                tail=activity_fixture({'fills':[],'fees':[frame['fees'][1]]},mode=mode,
                    start='2026-01-02T00:00:00Z',end='2026-01-03T04:00:00Z')
                bundle=proofs.combine_crypto_activity_snapshots([frame,tail],mode=mode)
                fee_rows=frame['fees']+[{**r,'order_id':'foreign','symbol':'unknown'} for r in activity_rows('CFEE',399)]
                chunks=[read_chunk('FILL',mode=mode,rows=frame['fills'],period_start=broker['submitted_at'],period_end=END)]
                first=read_chunk('CFEE',mode=mode,rows=fee_rows,period_start=broker['submitted_at'],period_end=END)
                chunks.extend((first,read_chunk('CFEE',first['next_page_token'],mode,fee_rows,
                    period_start=broker['submitted_at'],period_end=END)))
                paged=proofs.crypto_activity_paged_snapshot(chunks,mode=mode)
                for form in (frame,bundle,paged):
                    old=copy.deepcopy(form);before=(root/'receipts.jsonl').read_bytes()
                    with self.subTest(schema=form['schema_version']):
                        result=self.proof(form,broker,mode)
                        self.assertEqual(result['kind'],'crypto_buy_fee_debits')
                        self.assertEqual(result['provider_order_id'],broker['id'])
                        self.assertEqual(result['asset'],'BTC')
                        self.assertEqual(result['cumulative_fee_qty'],'0.000075')
                        self.assertEqual(result['fee_activity_ids'],['entry-fee-0','entry-fee-1'])
                        self.assertEqual(result['first_created_at'],'2026-01-01T04:00:03Z')
                        self.assertEqual(result['last_created_at'],'2026-01-02T00:00:03Z')
                        self.assertEqual(result['fee_completeness_status'],'unknown')
                        self.assertIsNone(result['net_realized_pnl_usd'])
                        self.assertEqual(form,old);self.assertEqual((root/'receipts.jsonl').read_bytes(),before)

    def test_missing_fee_or_creation_time_is_pending_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            broker,frame=fee_fixture(Path(directory))
            for fees,reason in (([],'owned_crypto_fees_pending'),
                    ([{k:v for k,v in frame['fees'][0].items() if k!='created_at'}],'owned_crypto_fee_time_pending')):
                variant=activity_fixture(frame,mode='paper',start=broker['submitted_at'],end=END,fees=fees)
                with self.subTest(reason=reason),self.assertRaisesRegex(proofs.ReconciliationPending,reason):
                    self.proof(variant,broker)

    def test_wrong_fee_identity_asset_status_amount_date_or_creation_time_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            broker,frame=fee_fixture(Path(directory))
            changes=[{'symbol':'USDCUSD'},{'status':'pending'},{'qty':'0'},{'qty':'0.001'},
                {'qty':'NaN'},{'qty':'-1e1000000'},{'net_amount':'-1'},
                {'date':'2025-12-31'},{'date':'2026-01-03'},
                {'created_at':'2026-01-01T03:59:59Z'},{'created_at':'2026-01-02T04:00:01Z'}]
            for change in changes:
                fee={**frame['fees'][0],**change}
                variant=activity_fixture(frame,mode='paper',start=broker['submitted_at'],end=END,fees=[fee])
                with self.subTest(change=change),self.assertRaisesRegex(ValueError,'owned_crypto_fees_invalid'):
                    self.proof(variant,broker)
            for change in ({'side':'sell'},{'status':'partially_filled'},{'status':'done_for_day'},{'filled_qty':'0'}):
                with self.subTest(broker=change),self.assertRaisesRegex(ValueError,'owned_crypto_fees_invalid'):
                    self.proof(frame,{**broker,**change})

    def test_cumulative_bound_is_exact_under_small_decimal_context(self):
        with tempfile.TemporaryDirectory() as directory:
            broker,frame=fee_fixture(Path(directory))
            for qty,want in (('-0.000000000000000000000000000001','0.000050000000000000000000000001'),):
                fees=[frame['fees'][0],{**frame['fees'][1],'qty':qty}]
                variant=activity_fixture(frame,mode='paper',start=broker['submitted_at'],end=END,fees=fees)
                with localcontext() as ctx:
                    ctx.prec=8
                    self.assertEqual(self.proof(variant,broker)['cumulative_fee_qty'],want)
            fees=[{**frame['fees'][0],'qty':'-0.05'},
                  {**frame['fees'][1],'qty':'-0.000000000000000000000000000001'}]
            variant=activity_fixture(frame,mode='paper',start=broker['submitted_at'],end=END,fees=fees)
            with localcontext() as ctx:
                ctx.prec=8
                with self.assertRaisesRegex(ValueError,'owned_crypto_fees_invalid'): self.proof(variant,broker)
