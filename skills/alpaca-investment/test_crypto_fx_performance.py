"""Execution FX reference remains distinct from cash settlement and full net."""
import copy
from decimal import localcontext
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest

import crypto_performance as perf
import crypto_ownership_proof as proofs
import effect_store as store
from test_crypto_performance import cycle_fixture,activity_fixture
from test_crypto_fx_quote import seal


def quote(asof,mode='paper',bid='0.9',ask='1.1'):
    observed='2026-01-01T06:00:00Z'
    return seal({'schema_version':1,'kind':'crypto_fx_asof_quote','mode':mode,'paper':mode=='paper',
        'symbol':'USDC/USD','base_currency':'USDC','quote_currency':'USD','asof_at':asof,'observed_at':observed,
        'request':proofs.crypto_fx_quote_request(mode=mode,asof_at=asof,observed_at=observed),
        'response':{'next_page_token':None,'quotes':{'USDC/USD':[{'t':asof,'bp':bid,'ap':ask}]}}})


def value(item):return Fraction(int(item['numerator']),int(item['denominator']))


class CryptoFxPerformanceTests(unittest.TestCase):
    def build(self,root,mode,frame,fx):
        return perf.build_crypto_performance(store._rows(root/'receipts.jsonl'),mode=mode,
            owner_id=f'alpaca-investment-{mode}',activity_readbacks={f['order_id']:frame for f in frame['fills']},
            fx_readbacks=fx)

    def test_each_fill_uses_its_own_mode_time_and_midpoint_without_promoting_net(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);_,frame,_=cycle_fixture(root,mode)
                buy,sell=frame['fills'];fx={buy['transaction_time']:quote(buy['transaction_time'],mode),
                    sell['transaction_time']:quote(sell['transaction_time'],mode,bid='1.1',ask='1.3')}
                result=self.build(root,mode,frame,fx);cycle=result['cycles'][0];ref=cycle['fx_reference']
                self.assertEqual(value(ref['execution_cashflow_usd']),Fraction('2.6'))
                self.assertEqual(cycle['execution_cashflow_usdc'],'0.5')
                self.assertEqual(ref['valuation_basis'],'asof_bbo_midpoint');self.assertFalse(ref['cash_conversion_proven'])
                self.assertEqual({c['fill_activity_id'] for c in ref['components']},{buy['id'],sell['id']})
                self.assertIsNone(ref['cashflow_after_observed_quote_fees_usd'])
                self.assertIsNone(result['net_pnl_usd']);self.assertFalse(result['capital_expansion_allowed'])
                self.assertEqual(result['fx_requests'],[])

    def test_missing_or_stale_fx_keeps_native_value_and_requests_exact_raw_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,frame,_=cycle_fixture(root)
            frame['fills'][0]['transaction_time']='2026-01-01T04:00:01.000000001+00:00'
            frame=activity_fixture(frame,mode='paper',start=frame['requested_period_start'],end=frame['requested_period_end'])
            for fx in ({}, {frame['fills'][0]['transaction_time']:quote(frame['fills'][0]['transaction_time'])}):
                result=self.build(root,'paper',frame,fx)
                self.assertEqual(result['cycles'][0]['execution_cashflow_usdc'],'0.5')
                self.assertIsNone(result['cycles'][0]['fx_reference']['execution_cashflow_usd'])
                requested={r['asof_at'] for r in result['fx_requests']}
                self.assertIn(frame['fills'][1]['transaction_time'],requested)
            stale=quote(frame['fills'][0]['transaction_time'])
            stale['response']['quotes']['USDC/USD'][0]['t']='2026-01-01T03:59:30Z'
            result=self.build(root,'paper',frame,{frame['fills'][0]['transaction_time']:seal(stale)})
            self.assertEqual(len(result['fx_requests']),2)

    def test_fee_cost_basis_uses_execution_not_posting_and_base_fee_is_not_deducted_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,frame,_=cycle_fixture(root)
            fees=[{'id':'quote-fee','activity_type':'CFEE','order_id':orders[1]['id'],'symbol':'USDCUSD',
                'qty':'-0.1','date':'2026-01-01','created_at':'2026-01-01T05:00:00Z','net_amount':'0','status':'executed'},
                {'id':'base-fee','activity_type':'CFEE','order_id':orders[0]['id'],'symbol':'BTCUSD',
                'qty':'-0.001','date':'2026-01-01','created_at':'2026-01-01T05:00:00Z','net_amount':'0','status':'executed'}]
            frame=activity_fixture(frame,mode='paper',start=frame['requested_period_start'],end=frame['requested_period_end'],fees=fees)
            fx={f['transaction_time']:quote(f['transaction_time'],bid='1.1',ask='1.3') for f in frame['fills']}
            ref=self.build(root,'paper',frame,fx)['cycles'][0]['fx_reference']
            self.assertEqual(value(ref['execution_cashflow_usd']),Fraction('0.6'))
            self.assertEqual(value(ref['observed_base_fee_cost_basis_usd']),Fraction('0.24'))
            self.assertEqual(value(ref['observed_quote_fee_cost_basis_usd']),Fraction('0.12'))
            self.assertEqual(value(ref['cashflow_after_observed_quote_fees_usd']),Fraction('0.48'))

    def test_foreign_mode_tamper_and_conflicting_physical_time_alias_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,frame,_=cycle_fixture(root);at=frame['fills'][0]['transaction_time']
            for snapshot in (quote(at,'live'),{**quote(at),'source_receipt_id':'bad'}):
                with self.assertRaises(ValueError):self.build(root,'paper',frame,{at:snapshot})
            alias=at.replace('+00:00','Z')
            with self.assertRaises(ValueError):self.build(root,'paper',frame,{at:quote(at),alias:quote(alias,bid='1.1',ask='1.3')})
            fx={at:quote(at),alias:quote(alias)}
            with localcontext() as context:
                context.prec=2
                for signal in context.traps:context.traps[signal]=True
                result=self.build(root,'paper',frame,fx)
            self.assertEqual(len(result['fx_requests']),1)

class CryptoFxExactIdentityTests(unittest.TestCase):
    def test_numeric_provider_fields_match_the_shared_decimal_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,frame,_=cycle_fixture(root)
            for fill in frame['fills']:fill['qty']=float(fill['qty']);fill['price']=float(fill['price'])
            frame=activity_fixture(frame,mode='paper',start=frame['requested_period_start'],end=frame['requested_period_end'])
            fx={f['transaction_time']:quote(f['transaction_time']) for f in frame['fills']}
            report=CryptoFxPerformanceTests().build(root,'paper',frame,fx)
            self.assertEqual(value(report['cycles'][0]['fx_reference']['execution_cashflow_usd']),Fraction('0.5'))

    def test_same_fill_id_cannot_change_nanosecond_between_execution_and_fee_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,original,_=cycle_fixture(root);frames=[]
            for nano in ('000000001','000000002'):
                frame=copy.deepcopy(original);frame['fills'][0]['transaction_time']='2026-01-01T04:00:01.'+nano+'Z'
                frames.append(activity_fixture(frame,mode='paper',start=frame['requested_period_start'],end=frame['requested_period_end']))
            for frame,other in (frames,frames[::-1]):
                with self.assertRaises(ValueError):
                    perf.build_crypto_performance(store._rows(root/'receipts.jsonl'),mode='paper',owner_id='alpaca-investment-paper',
                        activity_readbacks={f['order_id']:frame for f in frame['fills']},fee_activity_readbacks=[other])


if __name__=='__main__':unittest.main()
