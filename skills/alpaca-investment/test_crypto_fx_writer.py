"""Bounded FX cache reads preserve native performance on transport failure."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import crypto_performance as perf
import crypto_ownership_proof as proofs
from test_crypto_performance import cycle_fixture,activity_fixture,NOW
from test_crypto_fx_performance import quote,value


class CryptoFxWriterTests(unittest.TestCase):
    def prepare(self,root,mode='paper',partial=False):
        _,frame,_=cycle_fixture(root,mode,partial=partial)
        observation={'mode':mode,'paper':mode=='paper','clock':{'observed_at':NOW}}
        def read(**kwargs):return activity_fixture(frame,mode=mode,start=kwargs['period_start'],end=kwargs['period_end'])
        return observation,read

    def write(self,root,observation,read,fx):
        return perf.write_crypto_performance(root,observation,mode=observation['mode'],
            owner_id='alpaca-investment-'+observation['mode'],activity_reader=read,fx_reader=fx)

    def test_two_point_budget_success_cache_and_same_clock_zero_read_replay(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);observation,read=self.prepare(root,mode,partial=True);calls=[]
                def fx(**kwargs):
                    calls.append(kwargs);return quote(kwargs['asof_at'],mode)
                first=self.write(root,observation,read,fx)
                self.assertEqual(len(calls),2);self.assertEqual(len(first['fx_requests']),1)
                self.assertIsNone(first['cycles'][0]['fx_reference']['execution_cashflow_usd'])
                second=self.write(root,observation,read,fx)
                self.assertEqual(len(calls),3)
                self.assertEqual(value(second['cycles'][0]['fx_reference']['execution_cashflow_usd']),proofs.Fraction('0.53'))
                third=self.write(root,observation,read,fx);self.assertEqual(len(calls),3)
                self.assertEqual(third['fx_quote_readbacks'],second['fx_quote_readbacks'])
                self.assertIsNone(third['net_pnl_usd']);self.assertFalse(third['capital_expansion_allowed'])
                daily=json.loads((root/'performance-crypto-daily-2026-01-01.json').read_text())
                self.assertEqual(daily['cycles'][0]['fx_reference'],third['cycles'][0]['fx_reference'])

    def test_transport_failure_preserves_native_and_retries_only_on_next_clock(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);observation,read=self.prepare(root);calls=[]
            def bad(**kwargs):calls.append(kwargs);raise RuntimeError('private transport detail')
            first=self.write(root,observation,read,bad)
            self.assertEqual(first['cycles'][0]['execution_cashflow_usdc'],'0.5')
            self.assertEqual(len(calls),2);self.assertNotIn('private transport detail',json.dumps(first))
            replay=self.write(root,observation,read,bad);self.assertEqual(len(calls),2)
            self.assertEqual(replay['completed_round_trips'],1)
            later={**observation,'clock':{'observed_at':'2026-01-01T06:00:01Z'}}
            def fx(**kwargs):
                calls.append(kwargs);frame=quote(kwargs['asof_at']);frame['observed_at']=kwargs['observed_at']
                from test_crypto_fx_quote import seal
                return seal(frame)
            recovered=self.write(root,later,read,fx);self.assertEqual(len(calls),4)
            self.assertEqual(value(recovered['cycles'][0]['fx_reference']['execution_cashflow_usd']),proofs.Fraction('0.5'))
            self.assertEqual(recovered['fx_readback_errors'],[])

    def test_future_or_wrong_mode_incoming_snapshot_never_enters_the_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);observation,read=self.prepare(root)
            report=self.write(root,observation,read,lambda **kw:quote(kw['asof_at'],'live'))
            self.assertEqual(report['fx_quote_readbacks'],{})
            self.assertEqual(report['completed_round_trips'],1)
            self.assertEqual(len(report['fx_readback_errors']),2)

if __name__=='__main__':unittest.main()
