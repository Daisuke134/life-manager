"""Closed-cycle raw flow history stays scoped, resumable and nonfinancial."""
import copy
from contextlib import ExitStack,redirect_stdout
from io import StringIO
import inspect
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import crypto_performance as perf
import effect_store as store
from test_crypto_performance import cycle_fixture,activity_fixture,NOW

LATER='2026-01-02T06:00:00Z'
NEXT='2026-01-01T06:05:00Z'
AFTER='2026-01-01T06:10:00Z'


def rows(start,count):
    return [{'id':f'synthetic-raw-{i}','activity_type':('FILL','CFEE','OCT')[i%3],
        'qty':'0.12345678901234567890123456789','native_extra':i} for i in range(start,start+count)]


def frame(request,*,start=0,count=3,partial=False,wallet_error=False):
    raw=rows(start,count);pages=[raw[i:i+100] for i in range(0,count,100)] or [[]]
    query={'after':request['period_start'],'until':request['period_end'],'direction':'asc','page_size':100}
    if request.get('page_token') is not None:query['page_token']=request['page_token']
    result={'mode':request['mode'],'paper':request['mode']=='paper',
        'native_trading_account_id':request['native_trading_account_id'],'clock':None,
        'activity_request':query,'activity_pages':pages,
        'activity_pagination':'partial' if partial else 'exhausted',
        'next_page_token':raw[-1]['id'] if partial else None,
        'wallet_transfers':None if request['mode']=='paper' or wallet_error else [],
        'wallet_status':'unsupported_on_paper' if request['mode']=='paper' else 'failed' if wallet_error else 'observed',
        'capture_status':'partial' if partial or wallet_error else 'captured',
        'fee_completeness_status':'unknown','net_pnl_usd':None}
    if partial:result.update(capture_error_class='ValueError',capture_error_code='crypto_flow_activity_limit_exceeded')
    if wallet_error:result.update(wallet_error_class='ValueError',wallet_error_code='alpaca_cli_output_too_large')
    return result


class FlowWriterTests(unittest.TestCase):
    def setup_cycle(self,root,mode,*,legacy=False):
        account='synthetic-native-account-'+mode
        orders,activity,_=cycle_fixture(root,mode,native_account_id=None if legacy else account)
        obs={'mode':mode,'paper':mode=='paper','account':{'id':account,'cash':'0','equity':'100'},
            'positions':[{'symbol':'USDCUSD','qty':'100.12345678901234567890123456789'}],
            'clock':{'observed_at':NOW}}
        return orders,activity,obs

    def write(self,root,obs,activity,flow_reader,typed=None):
        self.assertIn('flow_reader',inspect.signature(perf.write_crypto_performance).parameters)
        mode=obs['mode']
        with patch.dict(os.environ,{},clear=True):
            return perf.write_crypto_performance(root,obs,mode=mode,owner_id='alpaca-investment-'+mode,
                activity_reader=typed or (lambda **_:activity),flow_reader=flow_reader)

    def test_closed_and_late_fee_wakes_save_native_quote_and_raw_in_latest_and_daily(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);orders,activity,obs=self.setup_cycle(root,mode);calls=[];native=[]
                def reader(**kw):
                    calls.append(copy.deepcopy(kw));value=frame(kw);native.append(value);return value
                first=self.write(root,obs,activity,reader)
                self.assertEqual(len(calls),1)
                self.assertEqual(calls[0]['period_start'],'2026-01-01T00:00:00Z')
                self.assertEqual(calls[0]['period_end'],NOW)
                refs=copy.deepcopy(first['order_activity_refs']);before=copy.deepcopy(first['flow_readbacks'])
                obs['clock']['observed_at']=LATER;obs['positions'][0]['qty']='100.99999999999999999999999999999'
                fee={'id':'synthetic-late-fee','activity_type':'CFEE','order_id':orders[0]['id'],
                    'symbol':'BTCUSD','qty':'-0.00005','date':'2026-01-02','net_amount':'0','status':'executed'}
                def typed(**kw):return activity_fixture(activity,mode=mode,start=kw['period_start'],end=kw['period_end'],fees=[fee])
                second=self.write(root,obs,activity,reader,typed)
                self.assertEqual(len(calls),2);self.assertEqual(calls[1]['period_start'],NOW)
                self.assertEqual(calls[1]['period_end'],LATER)
                self.assertEqual(second['order_activity_refs'],refs)
                self.assertTrue(all(second['flow_readbacks'][k]==v for k,v in before.items()))
                last=list(second['flow_readbacks'].values())[-1]
                self.assertEqual(last['account_readback'],obs)
                self.assertIsNone(last['readback']['clock'])
                self.assertEqual(second['flow_readback_through'],LATER)
                obs['positions'][0]['qty']='1'
                self.assertNotEqual(last['account_readback'],obs)
                daily=json.loads((root/'performance-crypto-daily-2026-01-01.json').read_text())
                self.assertEqual(daily['flow_readbacks'],second['flow_readbacks'])
                self.assertIsNone(second['net_pnl_usd']);self.assertFalse(second['capital_expansion_allowed'])
                self.assertTrue(all(f['fee_completeness_status']=='unknown' for f in native))

    def test_acquired_open_and_close_pending_entries_keep_their_flow_scope(self):
        mode='paper';account='synthetic-native-account-paper';observed='2026-01-01T06:00:00Z'
        baseline={'mode':mode,'paper':True,'account':{'id':account,'cash':'100','equity':'100'},
            'positions':[{'symbol':'USDCUSD','qty':'100'}],
            'clock':{'observed_at':'2026-01-01T04:00:00Z'}}
        for close_receipt_waiting in (False,True):
            with self.subTest(close_receipt_waiting=close_receipt_waiting),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);orders,activity,owned=cycle_fixture(root,mode,
                    native_account_id=account,pre_trade_readback=baseline)
                close_id=owned['close_effect_id'];ledger=root/'receipts.jsonl'
                rows=[row for row in store._rows(ledger) if not (
                    row.get('effect_id')==close_id and
                    (not close_receipt_waiting or row.get('receipt_type')=='outcome'))]
                ledger.write_text(''.join(json.dumps(row,separators=(',',':'))+'\n' for row in rows))
                buy_fills=[fill for fill in activity['fills'] if fill['order_id']==orders[0]['id']]
                typed_source={**activity,'fills':buy_fills,'fees':[]}
                obs={'mode':mode,'paper':True,'account':{'id':account,'cash':'0','equity':'100'},
                    'positions':[{'symbol':'BTCUSDC','qty':'0.05'},{'symbol':'USDCUSD','qty':'90'}],
                    'clock':{'observed_at':observed}}
                calls=[]
                def reader(**kw):
                    calls.append(copy.deepcopy(kw));raw=frame(kw,count=0)
                    raw['activity_pages']=[copy.deepcopy(buy_fills)]
                    return raw
                def typed(**kw):
                    return activity_fixture(typed_source,mode=mode,start=kw['period_start'],end=kw['period_end'])

                result=self.write(root,obs,activity,reader,typed)

                self.assertEqual(len(result['cycles']),0)
                active_entries=result['pending_entries'] if close_receipt_waiting else result['open_entries']
                self.assertEqual(len(active_entries),1)
                active=active_entries[0]
                self.assertEqual(active['entry_effect_id'],owned['entry_effect_id'])
                self.assertEqual(active['native_trading_account_id'],account)
                self.assertEqual(active['period_start'],'2026-01-01T04:00:00+00:00')
                self.assertEqual(len(calls),1,'an acquired open position still needs account flow coverage')
                self.assertEqual(calls[0]['native_trading_account_id'],account)
                self.assertEqual(calls[0]['period_end'],observed)
                flow=next(iter(result['flow_readbacks'].values()))
                self.assertIn(active['cycle_id'],flow['cycle_ids'])
                report=result['native_quantity_reconciliation']
                self.assertEqual(report['baseline']['cycle_id'],active['cycle_id'])
                self.assertEqual(report['baseline']['quantities']['USDC'],'100')
                self.assertEqual(report['current']['observed_at'],observed)
                self.assertNotIn(orders[0]['id'],report.get('unattributed_order_ids',[]))
                gap=next(item for item in report['buy_credit_gaps'] if item['cycle_id']==active['cycle_id'])
                self.assertEqual(gap['provider_order_id'],orders[0]['id'])
                self.assertEqual(gap['initial_gross_minus_credited_btc'],'0')
                self.assertEqual(report['status'],'observed_match')
                self.assertEqual(result['flow_readback_through'],observed)
                self.assertIsNone(result['net_pnl_usd']);self.assertFalse(result['capital_expansion_allowed'])

    def test_raw_partial_resumes_same_fixed_query_on_new_clock_after_typed_complete(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);_,activity,obs=self.setup_cycle(root,mode);calls=[]
                def reader(**kw):
                    calls.append(copy.deepcopy(kw));return frame(kw,count=400,partial=True) if len(calls)==1 else frame(kw,start=400,count=2)
                first=self.write(root,obs,activity,reader)
                self.assertEqual(first['flow_pending']['page_token'],'synthetic-raw-399')
                same=self.write(root,obs,activity,reader)
                self.assertEqual(len(calls),1);self.assertEqual(same['flow_readbacks'],first['flow_readbacks'])
                obs['clock']['observed_at']=NEXT
                def no_typed(**_):raise AssertionError('typed history must replay')
                finished=self.write(root,obs,activity,reader,no_typed)
                self.assertEqual(len(calls),2);self.assertEqual(calls[1]['page_token'],'synthetic-raw-399')
                self.assertEqual(calls[1]['period_start'],calls[0]['period_start'])
                self.assertEqual(calls[1]['period_end'],NOW)
                self.assertIsNone(finished['flow_pending'])
                self.assertEqual(finished['flow_readback_through'],NOW)
                last=list(finished['flow_readbacks'].values())[-1]
                self.assertEqual(last['account_readback']['clock']['observed_at'],NEXT)
                self.assertEqual(last['readback']['activity_request']['until'],NOW)
                self.assertEqual(finished['fee_checked_at'],first['fee_checked_at'])
                self.assertIsNone(finished['net_pnl_usd'])

    def test_failed_resume_keeps_raw_prefix_quote_and_token_then_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,activity,obs=self.setup_cycle(root,'live');calls=[]
            def reader(**kw):
                calls.append(copy.deepcopy(kw))
                if len(calls)==2:raise TimeoutError('synthetic-timeout')
                return frame(kw,count=400,partial=True) if len(calls)==1 else frame(kw,start=400,count=1)
            first=self.write(root,obs,activity,reader);before=copy.deepcopy(first['flow_readbacks'])
            obs['clock']['observed_at']=NEXT
            failed=self.write(root,obs,activity,reader)
            self.assertEqual(failed['flow_pending']['page_token'],'synthetic-raw-399')
            self.assertTrue(all(failed['flow_readbacks'][k]==v for k,v in before.items()))
            self.assertEqual(len(calls),2)
            self.assertTrue(any(r['account_readback']['clock']['observed_at']==NEXT for r in failed['flow_readbacks'].values()))
            self.assertEqual(failed['completed_round_trips'],1)
            replay=self.write(root,obs,activity,reader);self.assertEqual(len(calls),2)
            obs['clock']['observed_at']=AFTER
            recovered=self.write(root,obs,activity,reader)
            self.assertEqual(calls[2]['page_token'],'synthetic-raw-399');self.assertIsNone(recovered['flow_pending'])
            self.assertEqual(recovered['completed_round_trips'],1);self.assertFalse(recovered['capital_expansion_allowed'])

    def test_wallet_only_failure_retries_same_suffix_without_losing_valid_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,activity,obs=self.setup_cycle(root,'live');calls=[]
            def reader(**kw):
                calls.append(copy.deepcopy(kw))
                if len(calls)==1:return frame(kw,count=400,partial=True)
                return frame(kw,start=400,count=1,wallet_error=len(calls)==2)
            first=self.write(root,obs,activity,reader)
            obs['clock']['observed_at']=NEXT
            failed=self.write(root,obs,activity,reader)
            self.assertEqual(failed['flow_pending']['page_token'],'synthetic-raw-399')
            self.assertEqual(failed['completed_round_trips'],1)
            obs['clock']['observed_at']=AFTER
            done=self.write(root,obs,activity,reader)
            self.assertEqual(calls[1]['page_token'],calls[2]['page_token'])
            self.assertIsNone(done['flow_pending']);self.assertEqual(len(done['flow_readbacks']),3)
            self.assertIsNone(done['fees_usd'])

    def test_foreign_raw_and_cache_corruption_do_not_destroy_execution_or_known_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,activity,obs=self.setup_cycle(root,'live');calls=[]
            def reader(**kw):
                calls.append(kw);return frame(kw)
            first=self.write(root,obs,activity,reader)
            latest=root/'performance-crypto-latest.json';bad=json.loads(latest.read_text())
            ref=next(iter(bad['flow_readbacks']));bad['flow_readbacks'][ref]['account_readback']['positions'][0]['qty']='2'
            bad['flow_pending']={'after':'1900-01-01T00:00:00Z','until':NOW,'page_token':'wrong','readback_refs':[]}
            latest.write_text(json.dumps(bad));obs['clock']['observed_at']=NEXT
            fixed=self.write(root,obs,activity,reader)
            self.assertEqual(fixed['completed_round_trips'],1);self.assertEqual(fixed['order_activity_refs'],first['order_activity_refs'])
            self.assertTrue(fixed['flow_cache_rejected'])
            self.assertEqual(calls[-1]['period_start'],'2026-01-01T00:00:00Z')
            self.assertIsNone(fixed['net_pnl_usd'])
            obs['clock']['observed_at']=LATER
            def foreign(**kw):
                raw=frame(kw);raw['native_trading_account_id']='synthetic-foreign';return raw
            wrong=self.write(root,obs,activity,foreign,
                lambda **kw:activity_fixture(activity,mode='live',start=kw['period_start'],end=kw['period_end']))
            self.assertEqual(wrong['completed_round_trips'],1)
            self.assertTrue(wrong['flow_readback_errors']);self.assertFalse(wrong['capital_expansion_allowed'])

    def test_malformed_rejection_slot_preserves_original_and_recovers_on_new_clock(self):
        for mode in ('paper','live'):
            for malformed in ({'synthetic':'original'},None,'synthetic-original',17):
                with self.subTest(mode=mode,malformed=malformed),tempfile.TemporaryDirectory() as directory:
                    root=Path(directory);_,activity,obs=self.setup_cycle(root,mode);calls=[]
                    def reader(**kw):
                        calls.append(copy.deepcopy(kw));return frame(kw)
                    first=self.write(root,obs,activity,reader)
                    latest=root/'performance-crypto-latest.json';bad=json.loads(latest.read_text())
                    bad['flow_readbacks']=[]
                    bad['flow_cache_rejected']={'flow_readbacks':copy.deepcopy(malformed)}
                    latest.write_text(json.dumps(bad));obs['clock']['observed_at']=NEXT
                    recovered=self.write(root,obs,activity,reader)
                    self.assertEqual(len(calls),2)
                    self.assertEqual(recovered['completed_round_trips'],1)
                    self.assertEqual(recovered['order_activity_refs'],first['order_activity_refs'])
                    self.assertEqual(recovered['flow_cache_rejected']['flow_readbacks'],[malformed,[]])
                    self.assertTrue(recovered['flow_readbacks'])
                    self.assertIsNone(recovered['net_pnl_usd']);self.assertFalse(recovered['capital_expansion_allowed'])
                    prior=copy.deepcopy(recovered['flow_readbacks'])
                    self.write(root,obs,activity,reader);self.assertEqual(len(calls),2)
                    obs['clock']['observed_at']=AFTER
                    again=self.write(root,obs,activity,reader)
                    self.assertEqual(again['flow_cache_rejected']['flow_readbacks'],[malformed,[]])
                    self.assertTrue(all(again['flow_readbacks'][k]==v for k,v in prior.items()))
                    self.assertEqual(again['completed_round_trips'],1)
                    self.assertIsNone(again['net_pnl_usd'])

    def test_legacy_unbound_cycle_does_not_adopt_current_native_account(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);_,activity,obs=self.setup_cycle(root,mode,legacy=True);calls=[]
                result=self.write(root,obs,activity,lambda **kw:calls.append(kw))
                self.assertEqual(calls,[]);self.assertEqual(result['completed_round_trips'],1)
                self.assertNotIn('native_trading_account_id',result['cycles'][0])
                self.assertIsNone(result['net_pnl_usd'])


    def test_full_terminal_page_without_next_read_is_not_exhausted_evidence(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);_,activity,obs=self.setup_cycle(root,mode)
                def unproven(**kw):return frame(kw,count=100)
                result=self.write(root,obs,activity,unproven)
                self.assertIsNotNone(result['flow_pending'])
                self.assertEqual(result['flow_windows'],[])
                self.assertEqual(result['completed_round_trips'],1)
                self.assertEqual(result['flow_readback_errors'][-1]['reason'],'crypto_flow_readback_invalid')
                self.assertTrue(result['flow_readbacks'])
                self.assertIsNone(result['net_pnl_usd'])

    def test_real_main_injects_the_same_scoped_flow_reader_after_close(self):
        from test_crypto_close import native_run
        from test_owned_policy import snapshot
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
                root=Path(directory);account='synthetic-native-account-'+mode
                orders,activity,owned=cycle_fixture(root,mode,native_account_id=account)
                (root/'live-owned-position.json').write_text(json.dumps(owned));native=native_run()
                obs={'mode':mode,'paper':mode=='paper','account':{'id':account,'cash':'0','equity':'100'},
                    'positions':[{'symbol':'USDCUSD','qty':'100','unrealized_pl':'0'}],
                    'clock':{'observed_at':NOW},'activities_count':0,'open_and_closed_orders_count':0}
                raw,_=snapshot(mode);raw.pop('crypto_history');raw['positions']=0;raw['account']={'id':account,'cash':'0','equity':'100'}
                initial_intents=sum(r.get('receipt_type')=='effect_intent' for r in store._rows(root/'receipts.jsonl'))
                stack.enter_context(patch.dict(os.environ,{'LIFE_MANAGER_INVESTMENT_MODE':mode,
                    'LIFE_MANAGER_INVESTMENT_DEPLOYMENT':'local','LIFE_MANAGER_INVESTMENT_OWNER_ID':'alpaca-investment-'+mode,
                    'ALPACA_INVESTMENT_'+mode.upper()+'_STATE_DIR':str(root),
                    'ALPACA_INVESTMENT_'+mode.upper()+'_CREDENTIALS_FILE':str(root/'unused')},clear=True))
                stack.enter_context(patch.object(native,'observe',return_value=obs))
                stack.enter_context(patch.object(native,'read_allocator_snapshot',return_value=raw))
                stack.enter_context(patch.object(native,'find_order_by_client_id',side_effect=lambda **kw:
                    next(o for o in orders if o['client_order_id']==kw['client_order_id'])))
                stack.enter_context(patch.object(native,'read_crypto_activity_evidence',return_value=activity))
                def captured(**kw):return frame(kw)
                reader=stack.enter_context(patch.object(native,'read_crypto_flow_evidence',side_effect=captured,create=True))
                for name,value in (('read_crypto_history',{}),('build_candidates',[]),('_review_status',{}),
                    ('read_campaign_snapshot',{'paper':True,'unexpected_positions':[],'fills':[],'positions':[],'options':[]}),
                    ('deliver',{'message_id':'fixture'}),('deliver_failure',{'status':'delivered'}),('_retry_allowed',False)):
                    stack.enter_context(patch.object(native,name,return_value=value))
                import alpaca_cli
                stack.enter_context(patch.object(alpaca_cli,'_context',side_effect=AssertionError('provider forbidden')))
                stack.enter_context(patch.object(alpaca_cli,'_run',side_effect=AssertionError('provider forbidden')))
                with redirect_stdout(StringIO()) as output:code=native.main(wake_id='synthetic-flow-report')
                self.assertEqual(code,0,output.getvalue());self.assertEqual(reader.call_count,1)
                self.assertEqual(reader.call_args.kwargs['native_trading_account_id'],account)
                self.assertEqual(reader.call_args.kwargs['mode'],mode)
                self.assertEqual(reader.call_args.kwargs['credentials_path'],root/'unused')
                saved=json.loads((root/'performance-crypto-latest.json').read_text())
                self.assertEqual(len(saved['flow_readbacks']),1);self.assertIsNone(saved['net_pnl_usd'])
                self.assertEqual(sum(r.get('receipt_type')=='effect_intent' for r in store._rows(root/'receipts.jsonl')),initial_intents)
                self.assertNotIn(account,output.getvalue())


if __name__=='__main__':unittest.main()
