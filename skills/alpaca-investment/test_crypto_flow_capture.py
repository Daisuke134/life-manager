"""Optional raw flow retention does not change risk or declare fee completeness."""
import copy
import inspect
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import alpaca_cli as cli
import test_crypto_entry_account as entry_fixtures
from test_alpaca_cli import CLOCK

ACCOUNT='synthetic-flow-native-account'
WALLET=[{'id':'synthetic-transfer','asset':'USDC','amount':'66.12345678901234567890123456789',
    'usd_value':'65.99','direction':'INCOMING','status':'COMPLETE','created_at':'2026-01-01T00:00:00Z',
    'fees':'0.01','network_fee':'0.02','native_extra':'keep-raw'}]


def records(count):
    kinds=('FILL','CFEE','OCT')
    return [{'id':f'synthetic-activity-{i}','activity_type':kinds[i%3],
        'qty':'0.12345678901234567890123456789','native_extra':{'sequence':i}} for i in range(count)]


class FlowCaptureTests(unittest.TestCase):
    def read(self,mode,*,capture=True,pages=None,fail=None,account_id=ACCOUNT):
        if capture:self.assertIn('flow_sink',inspect.signature(cli.read_allocator_snapshot).parameters)
        env={'synthetic-env':mode};calls=[];sink=[];pages=copy.deepcopy(pages if pages is not None else [records(3)])
        raw_wallet=copy.deepcopy(WALLET)
        common=iter([{'id':account_id,'cash':'0','equity':'66','last_equity':'66'},copy.deepcopy(CLOCK),[],
            *([] if mode=='paper' else [raw_wallet]),[],
            [{'symbol':'USDCUSD','market_value':'66','unrealized_pl':'0'}],0,
            {'price':'100','timestamp':CLOCK['timestamp']},[],{'tradable':False,'status':'inactive'},
            {'bid':'99','ask':'100','quote_at':CLOCK['timestamp']},[]])
        def run(_path,args,context):
            self.assertIs(context,env);calls.append(copy.deepcopy(args))
            if args[:3]==['account','activity','list'] and '--activity-types' not in args:
                if fail:raise ValueError(fail)
                return pages.pop(0)
            value=copy.deepcopy(next(common))
            if args[:2]==['api','GET'] and args[-1]!='.':
                value=[{k:r[k] for k in ('id','asset','usd_value','direction','status')} for r in value]
            return value
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'LIFE_MANAGER_INVESTMENT_MODE':mode},clear=True),\
                patch.object(cli,'_context',return_value=env),patch.object(cli,'_run',side_effect=run):
            root=Path(directory);kwargs={'flow_sink':sink} if capture else {}
            result=cli.read_allocator_snapshot(credentials_path=Path('unused'),cli_path=Path('unused'),
                risk_day_path=root/'risk-day.json',**kwargs)
            risk_state=json.loads((root/'risk-day.json').read_text())
        return result,sink,calls,risk_state

    def test_optional_capture_keeps_raw_fields_and_existing_result_and_risk_identical(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode):
                baseline,_,old_calls,old_risk=self.read(mode,capture=False)
                result,sink,calls,risk=self.read(mode)
                self.assertEqual(result,baseline);self.assertEqual(risk,old_risk)
                self.assertEqual(len(calls),len(old_calls)+1)
                self.assertEqual(len(sink),1);frame=sink[0]
                self.assertEqual(frame['native_trading_account_id'],ACCOUNT)
                self.assertEqual(frame['mode'],mode);self.assertIs(frame['paper'],mode=='paper')
                self.assertEqual(frame['activity_pages'],[records(3)])
                self.assertEqual(frame['activity_pagination'],'exhausted')
                self.assertEqual(frame['capture_status'],'captured')
                self.assertEqual(frame['fee_completeness_status'],'unknown');self.assertIsNone(frame['net_pnl_usd'])
                self.assertNotIn('pre_trade_flow_readbacks',result)
                if mode=='paper':
                    self.assertIsNone(frame['wallet_transfers'])
                    self.assertEqual(frame['wallet_status'],'unsupported_on_paper')
                    self.assertFalse(any(c[:2]==['api','GET'] for c in calls))
                else:
                    self.assertEqual(frame['wallet_transfers'],WALLET)
                    self.assertEqual(frame['wallet_status'],'observed')
                    self.assertEqual(next(c[-1] for c in calls if c[:2]==['api','GET']),'.')
                    self.assertNotEqual(next(c[-1] for c in old_calls if c[:2]==['api','GET']),'.')

    def test_fixed_window_tokens_and_terminal_page_are_saved_without_type_filter(self):
        rows=records(101)
        result,sink,calls,_=self.read('live',pages=[rows[:100],rows[100:]])
        frame=sink[0];requests=[c for c in calls if c[:3]==['account','activity','list'] and '--activity-types' not in c]
        self.assertEqual(frame['activity_pages'],[rows[:100],rows[100:]])
        self.assertEqual(len(requests),2)
        query=frame['activity_request']
        for c in requests:
            self.assertEqual(c[c.index('--after')+1],query['after'])
            self.assertEqual(c[c.index('--until')+1],CLOCK['timestamp'])
            self.assertEqual(c[c.index('--page-size')+1],'100');self.assertEqual(c[c.index('--direction')+1],'asc')
            self.assertEqual(c[-1] if '--page-token' not in c else c[c.index('--jq')+1],'.')
        self.assertNotIn('--page-token',requests[0])
        self.assertEqual(requests[1][requests[1].index('--page-token')+1],rows[99]['id'])
        self.assertIsNone(frame['next_page_token'])
        self.assertEqual(result['risk']['cash_flow_ny_day_usd'],'0')

    def test_page_limit_keeps_four_raw_pages_and_next_token_as_partial_not_complete(self):
        rows=records(400);pages=[rows[i:i+100] for i in range(0,400,100)]
        _,sink,calls,_=self.read('live',pages=pages)
        frame=sink[0]
        self.assertEqual(frame['activity_pages'],pages)
        self.assertEqual(frame['capture_status'],'partial');self.assertEqual(frame['activity_pagination'],'partial')
        self.assertEqual(frame['next_page_token'],rows[-1]['id'])
        self.assertEqual(frame['capture_error_code'],'crypto_flow_activity_limit_exceeded')
        self.assertEqual(sum(c[:3]==['account','activity','list'] and '--activity-types' not in c for c in calls),4)
        self.assertEqual(frame['wallet_transfers'],WALLET)
        self.assertIsNone(frame['net_pnl_usd'])

    def test_capture_errors_keep_prior_valid_page_and_wallet_without_changing_risk(self):
        first=records(100)
        bad_pages=[first[:1],[{'id':'bad','activity_type':''}],[{'id':'bad','activity_type':None}],{},records(101)]
        for bad in bad_pages:
            with self.subTest(bad_type=type(bad).__name__):
                baseline,_,_,old_risk=self.read('live',capture=False)
                result,sink,_,risk=self.read('live',pages=[first,bad])
                frame=sink[0]
                self.assertEqual(result,baseline);self.assertEqual(risk,old_risk)
                self.assertEqual(frame['activity_pages'],[first]);self.assertEqual(frame['wallet_transfers'],WALLET)
                self.assertEqual(frame['capture_status'],'partial')
                self.assertEqual(frame['capture_error_code'],'crypto_flow_activity_invalid')
                self.assertIsNone(frame['net_pnl_usd'])

    def test_fetch_failure_and_missing_native_account_are_unknown_not_a_new_risk_gate(self):
        for account,fail in ((ACCOUNT,'alpaca_cli_timeout:account_activity'),(None,None)):
            with self.subTest(account_known=account is not None):
                baseline,_,_,old_risk=self.read('live',capture=False,account_id=account)
                result,sink,_,risk=self.read('live',fail=fail,account_id=account)
                self.assertEqual(result,baseline);self.assertEqual(risk,old_risk)
                self.assertEqual(sink[0]['activity_pages'],[])
                self.assertEqual(sink[0]['capture_status'],'failed')
                self.assertEqual(sink[0]['activity_pagination'],'unknown')
                self.assertEqual(sink[0]['fee_completeness_status'],'unknown')
                self.assertIsNone(sink[0]['net_pnl_usd'])

    def test_real_main_requests_only_fenced_fresh_sink_and_seals_independent_raw_copy(self):
        for mode in ('paper','live'):
            for status in ('captured','partial','failed',None):
                with self.subTest(mode=mode,status=status),tempfile.TemporaryDirectory() as directory:
                    root=Path(directory);trace=[]
                    frame={'capture_status':status,'mode':mode,'native_trading_account_id':entry_fixtures.ACCOUNT_A,
                        'wallet_transfers':copy.deepcopy(WALLET),'activity_pages':[records(3)],
                        'fee_completeness_status':'unknown','net_pnl_usd':None} if status else None
                    before=copy.deepcopy(frame)
                    code,rows,output=entry_fixtures.CryptoEntryAccountTests().entry_main(root,mode,
                        filled=True,flow_readback=frame,flow_requests=trace)
                    self.assertEqual(code,0,output)
                    self.assertEqual(trace,[{'has_sink':False,'read_index':0},{'has_sink':True,'read_index':1}])
                    decision=next(r['decision'] for r in rows if r.get('receipt_type')=='decision' and r['decision'].get('action')=='ENTER')
                    self.assertEqual(decision.get('pre_trade_flow_readbacks'),[before] if before else None)
                    self.assertEqual(frame,before)
                    self.assertNotIn('synthetic-transfer',output)
                    self.assertNotIn('66.12345678901234567890123456789',output)
                    self.assertNotIn('native_extra',output)
                    receipt=next(r['strategy_receipt']['receipt'] for r in rows if r.get('strategy_receipt'))
                    self.assertIsNone(receipt['net_realized_pnl_usd'])


if __name__=='__main__':unittest.main()
