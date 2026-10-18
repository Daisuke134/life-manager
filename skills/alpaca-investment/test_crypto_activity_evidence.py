"""Bounded official activity snapshots; no provider calls in these fixtures."""
from pathlib import Path
import copy
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import alpaca_cli as cli

START='2026-01-01T04:00:00Z'
END='2026-01-02T04:00:00Z'
FILL={'id':'fill-1','activity_type':'FILL','order_id':'official-entry','symbol':'BTCUSDC',
      'side':'buy','qty':'0.02','price':'200','transaction_time':'2026-01-01T04:00:01Z'}
FEE={'id':'fee-1','activity_type':'CFEE','symbol':'BTCUSD','qty':'-0.00005','price':'200',
     'date':'2026-01-02','net_amount':'0','status':'executed'}


class CryptoActivityEvidenceTests(unittest.TestCase):
    def read(self,mode='paper',**kwargs):
        reader=getattr(cli,'read_crypto_activity_evidence',None)
        self.assertTrue(callable(reader),'bounded FILL/CFEE reader is required')
        return reader(credentials_path=Path('unused'),cli_path=Path('unused'),mode=mode,
            period_start=kwargs.get('period_start',START),period_end=kwargs.get('period_end',END))

    def test_mode_scoped_snapshot_keeps_unattributed_fee_and_raw_native_facts(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),patch.object(cli,'_context',return_value={}) as context,\
                    patch.object(cli,'_run',side_effect=[[copy.deepcopy(FILL)],[copy.deepcopy(FEE)]]) as run:
                value=self.read(mode)
                self.assertEqual(value['mode'],mode)
                self.assertIs(value['paper'],mode=='paper')
                self.assertEqual(value['fills'],[FILL]);self.assertEqual(value['fees'],[FEE])
                self.assertEqual(value['pagination'],'exhausted')
                self.assertEqual(value['fee_attribution_status'],'unknown')
                self.assertEqual(value['fee_settlement_status'],'unknown')
                self.assertIsNone(value['net_realized_pnl_usd'])
                self.assertTrue(value['source_receipt_id'].startswith('alpaca-crypto-activities:'))
                context.assert_called_once_with(Path('unused'),Path('unused'),mode=mode)
                self.assertEqual(run.call_count,2)
                for call in run.call_args_list:
                    args=call.args[1]
                    self.assertEqual(args[:3],['account','activity','list'])
                    self.assertNotIn('--order-id',args)
                    self.assertEqual(args[args.index('--after')+1],'2026-01-01T00:00:00Z')
                    self.assertEqual(args[args.index('--until')+1],END)

    def test_empty_fees_do_not_prove_zero_or_settlement(self):
        with patch.object(cli,'_context',return_value={}),patch.object(cli,'_run',side_effect=[[FILL],[]]):
            value=self.read()
        self.assertEqual(value['fees'],[])
        self.assertEqual(value['fee_settlement_status'],'unknown')
        self.assertEqual(value['fee_attribution_status'],'unknown')
        self.assertNotIn('fees_usd',value)

    def test_second_page_uses_last_activity_id_without_dropping_foreign_order_fills(self):
        page=[{**FILL,'id':f'fill-{i}','order_id':'other-order'} for i in range(100)]
        with patch.object(cli,'_context',return_value={}),\
                patch.object(cli,'_run',side_effect=[page,[{**FILL,'id':'fill-target'}],[]]) as run:
            value=self.read()
        self.assertEqual(len(value['fills']),101)
        args=run.call_args_list[1].args[1]
        self.assertEqual(args[args.index('--page-token')+1],'fill-99')
        self.assertEqual(value['fills'][0]['order_id'],'other-order')

    def test_duplicate_wrong_kind_missing_id_or_nonarray_pages_rejected(self):
        variants=([FILL,FILL],[{**FILL,'id':''}],[{**FILL,'activity_type':'CFEE'}],{'rows':[FILL]})
        for page in variants:
            with self.subTest(page=page),patch.object(cli,'_context',return_value={}),\
                    patch.object(cli,'_run',return_value=page):
                with self.assertRaisesRegex(ValueError,'crypto_activity_invalid'):
                    self.read()

    def test_page_bound_does_not_claim_exhaustion(self):
        pages=[[{**FILL,'id':f'{p}-{i}'} for i in range(100)] for p in range(4)]
        with patch.object(cli,'_context',return_value={}),patch.object(cli,'_run',side_effect=pages) as run:
            with self.assertRaisesRegex(ValueError,'crypto_activity_limit_exceeded'): self.read()
        self.assertEqual(run.call_count,4)

    def test_same_activity_id_cannot_describe_both_a_fill_and_a_fee(self):
        with patch.object(cli,'_context',return_value={}),\
                patch.object(cli,'_run',side_effect=[[FILL],[{**FEE,'id':FILL['id']}]]):
            with self.assertRaisesRegex(ValueError,'crypto_activity_invalid'): self.read()

    def test_invalid_mode_or_period_never_opens_credentials(self):
        for mode,start,end in (('shadow',START,END),('paper',END,START),
                ('paper','invalid',END),('paper','2025-01-01T00:00:00Z',END)):
            with self.subTest(mode=mode,start=start),patch.object(cli,'_context') as context:
                with self.assertRaises(ValueError): self.read(mode,period_start=start,period_end=end)
                context.assert_not_called()
