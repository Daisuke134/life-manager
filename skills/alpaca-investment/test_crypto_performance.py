"""Closed BTC cycles are counted once; quote cashflow is never USD net profit."""
import copy
from contextlib import ExitStack,redirect_stdout
from io import StringIO
import importlib
import importlib.util
import json
import os
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import alpaca_cli as cli
import effect_store as store
import crypto_ownership_proof as proofs
from strategy_policy import candidate_cards

PERF=importlib.import_module('crypto_performance') if importlib.util.find_spec('crypto_performance') else None
NOW='2026-01-01T06:00:00Z'


def cycle_fixture(root,mode='paper',index=0,partial=False,zero=False):
    owner=f'alpaca-investment-{mode}';base=datetime(2026,1,1,4,tzinfo=timezone.utc)+timedelta(minutes=20*index)
    stamp=lambda seconds:(base+timedelta(seconds=seconds)).isoformat()
    card=candidate_cards()['alpaca-btc-5m-trend-400-v2']
    decision={'action':'ENTER','mode':mode,'owner_id':owner,'strategy_id':card.strategy_id,'release_sha':'a'*40,
              'policy_card':card.to_mapping(),'observed_at':stamp(0)}
    ledger=root/'receipts.jsonl';sealed=store.seal(ledger,decision,{'asset_class':'crypto','symbol':'BTC/USDC',
        'side':'buy','type':'market','time_in_force':'gtc','notional_usd':'10'});store.mark_started(ledger,sealed)
    buy={'id':f'buy-{index}','client_order_id':sealed['client_order_id'],'status':'filled','symbol':'BTCUSDC',
         'side':'buy','type':'market','time_in_force':'gtc','filled_qty':'0.05','filled_avg_price':'200',
         'submitted_at':stamp(0),'filled_at':stamp(1)}
    owned={'status':'entry_pending','symbol':'BTCUSD','entry_effect_id':sealed['effect_id'],
           'entry_client_order_id':sealed['client_order_id'],'entry_filled_qty':'0'}
    account={'mode':mode,'paper':mode=='paper','account':{'cash':'0','equity':'100'},
             'positions':[{'symbol':'BTCUSDC','qty':'0.05'}],'clock':{'observed_at':stamp(2)}}
    acquisition=proofs.entry_fill_proof_from_rows(store._rows(ledger),owned,buy,account,mode=mode,owner_id=owner)
    store.reconcile_started(ledger,lambda _:buy,on_reconciled=lambda *_:acquisition)
    owned.update(status='open',entry_filled_qty='0.05',owned_qty='0.05')
    fills=[{'id':f'buy-fill-{index}','activity_type':'FILL','order_id':buy['id'],'symbol':'BTCUSDC','side':'buy',
            'qty':'0.05','price':'200','transaction_time':stamp(1)}]
    orders=[buy];quantities=(['0'] if zero else [])+(['0.02','0.03'] if partial else ['0.05'])
    before='0.05'
    for n,qty in enumerate(quantities):
        price='211' if partial and qty=='0.03' else '210';seconds=300*(n+1)
        parent=proofs._owned_policy(proofs.owned_entry_decision_from_rows(store._rows(ledger),owned,mode=mode,owner_id=owner),owned,mode=mode)
        exit_decision={'action':'EXIT','mode':mode,'owner_id':owner,'strategy_id':card.strategy_id,'release_sha':'a'*40,
            'position_qty':before,'observed_at':stamp(seconds),**{k:parent[k] for k in (
                'entry_effect_id','entry_client_order_id','entry_provider_order_id','entry_price','entry_timestamp')}}
        close=store.seal(ledger,exit_decision,{'asset_class':'crypto','symbol':'BTC/USDC','side':'sell',
            'type':'market','time_in_force':'gtc','qty':before});store.mark_started(ledger,close)
        owned.update(status='closing',close_effect_id=close['effect_id'],close_client_order_id=close['client_order_id'])
        terminal=qty=='0' or (partial and qty=='0.02')
        sell={'id':f'sell-{index}-{n}','client_order_id':close['client_order_id'],'status':'canceled' if terminal else 'filled',
            'symbol':'BTCUSDC','side':'sell','type':'market','time_in_force':'gtc','qty':before,'filled_qty':qty,
            'filled_avg_price':None if terminal else price,'submitted_at':stamp(seconds),'filled_at':None if terminal else stamp(seconds+1)}
        if qty!='0': fills.append({'id':f'sell-fill-{index}-{n}','activity_type':'FILL','order_id':sell['id'],'symbol':'BTCUSDC',
            'side':'sell','qty':qty,'price':price,'transaction_time':stamp(seconds+1)})
        remaining=proofs.Fraction(before)-proofs.Fraction(qty);before=proofs._quantity_text(remaining)
        after={**account,'positions':[] if remaining==0 else [{'symbol':'BTCUSDC','qty':before}],
               'clock':{'observed_at':stamp(seconds+2)}}
        if terminal:
            with patch.object(cli,'_context',return_value={}),patch.object(cli,'_run',side_effect=[copy.deepcopy(fills),[]]):
                activities=cli.read_crypto_activity_evidence(credentials_path=Path('unused'),cli_path=Path('unused'),mode=mode,
                    period_start=sell['submitted_at'],period_end=after['clock']['observed_at'])
            result=proofs.sell_remainder_proof_from_rows(store._rows(ledger),owned,sell,after,mode=mode,owner_id=owner,activity_readback=activities)
        else: result=proofs.close_fill_proof_from_rows(store._rows(ledger),owned,sell,after,mode=mode,owner_id=owner)
        store.reconcile_started(ledger,lambda _:sell,on_reconciled=lambda *_:result)
        if remaining: owned.update(status='open',owned_qty=before)
        else: owned['status']='closed'
        orders.append(sell)
    with patch.object(cli,'_context',return_value={}),patch.object(cli,'_run',side_effect=[copy.deepcopy(fills),[]]):
        activities=cli.read_crypto_activity_evidence(credentials_path=Path('unused'),cli_path=Path('unused'),mode=mode,
            period_start=buy['submitted_at'],period_end=NOW)
    return orders,activities,owned


class CryptoPerformanceTests(unittest.TestCase):
    def project(self,rows,mode='paper',activities=None):
        self.assertIsNotNone(PERF,'common crypto performance projector is required')
        return PERF.build_crypto_performance(rows,mode=mode,owner_id=f'alpaca-investment-{mode}',activity_readbacks=activities)

    def test_partial_and_zero_legs_form_one_cycle_with_exact_native_cashflow(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);orders,activity,_=cycle_fixture(root,mode,partial=True,zero=True)
                rows=store._rows(root/'receipts.jsonl');before=copy.deepcopy(rows)
                result=self.project(rows,mode,{o['id']:activity for o in orders})
                self.assertEqual(result['completed_round_trips'],1)
                cycle=result['cycles'][0]
                self.assertEqual(cycle['execution_cashflow_usdc'],'0.53')
                self.assertEqual(cycle['order_ids'],[o['id'] for o in orders])
                self.assertEqual(cycle['positive_sell_count'],2)
                self.assertIsNone(result['net_pnl_usd']);self.assertIsNone(result['fees_usd'])
                self.assertFalse(result['capital_expansion_allowed'])
                self.assertEqual(result['measurement_status'],'partial')
                self.assertEqual(rows,before)

    def test_order_average_is_not_used_when_full_fill_activities_are_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cycle_fixture(root)
            result=self.project(store._rows(root/'receipts.jsonl'))
            self.assertEqual(result['completed_round_trips'],1)
            self.assertIsNone(result['cycles'][0]['execution_cashflow_usdc'])
            self.assertEqual(len(result['missing_activity_order_ids']),2)

    def test_incomplete_last_exit_is_not_a_closed_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,activity,owned=cycle_fixture(root)
            rows=[r for r in store._rows(root/'receipts.jsonl') if not (r.get('receipt_type')=='outcome' and r.get('effect_id')==owned['close_effect_id'])]
            result=self.project(rows,activities={o['id']:activity for o in orders})
            self.assertEqual(result['completed_round_trips'],0)
            self.assertEqual(len(result['pending_entries']),1)
            self.assertIsNone(result['net_pnl_usd'])

    def test_corrupt_parent_or_cached_execution_cannot_become_measured(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,activity,_=cycle_fixture(root)
            activity['fills'][0]['price']='999'
            with self.assertRaises(ValueError): self.project(store._rows(root/'receipts.jsonl'),activities={o['id']:activity for o in orders})

    def test_writer_adds_second_cycle_and_replays_without_provider_read(self):
        self.assertIsNotNone(PERF,'crypto performance writer is required')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,activity,_=cycle_fixture(root)
            obs={'mode':'paper','paper':True,'clock':{'observed_at':NOW},'account':{'cash':'0','equity':'100'},'positions':[]}
            with patch.object(PERF,'_read_activity',return_value=activity) as reader:
                first=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper')
            self.assertEqual(first['completed_round_trips'],1);self.assertEqual(reader.call_count,1)
            with patch.object(PERF,'_read_activity',side_effect=AssertionError('completed facts replayed')):
                replay=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper')
            self.assertEqual(replay['completed_round_trips'],1)
            more,new_activity,_=cycle_fixture(root,index=1)
            with patch.object(PERF,'_read_activity',return_value=new_activity):
                second=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper')
            self.assertEqual(second['completed_round_trips'],2)
            daily=json.loads((root/'performance-crypto-daily-2026-01-01.json').read_text())
            self.assertEqual(daily['completed_round_trips'],2)
            self.assertFalse((root/'performance-latest.json').exists())

    def test_readback_failure_preserves_previously_verified_execution_cache(self):
        self.assertIsNotNone(PERF)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,activity,_=cycle_fixture(root)
            obs={'mode':'paper','paper':True,'clock':{'observed_at':NOW}}
            with patch.object(PERF,'_read_activity',return_value=activity):
                PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper')
            more,new_activity,_=cycle_fixture(root,index=1)
            with patch.object(PERF,'_read_activity',side_effect=ValueError('crypto_activity_invalid')):
                failed=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper')
            self.assertIsNone(failed['completed_round_trips'])
            with patch.object(PERF,'_read_activity',return_value=new_activity):
                recovered=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper')
            self.assertEqual(recovered['completed_round_trips'],2)
            self.assertTrue(all(c['native_execution_status']=='complete' for c in recovered['cycles']))

    def test_real_main_uses_the_same_crypto_writer_in_paper_and_live(self):
        from test_crypto_close import native_run
        from test_owned_policy import snapshot
        self.assertIsNotNone(PERF)
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
                root=Path(directory);orders,activity,owned=cycle_fixture(root,mode)
                (root/'live-owned-position.json').write_text(json.dumps(owned));native=native_run()
                obs={'mode':mode,'paper':mode=='paper','clock':{'observed_at':NOW},'account':{'cash':'0','equity':'100'},
                     'positions':[{'symbol':'USDCUSD','qty':'100','unrealized_pl':'0'}],
                     'activities_count':0,'open_and_closed_orders_count':0}
                raw,_=snapshot(mode);raw.pop('crypto_history');raw['positions']=0
                stack.enter_context(patch.dict(os.environ,{'LIFE_MANAGER_INVESTMENT_MODE':mode,
                    'LIFE_MANAGER_INVESTMENT_DEPLOYMENT':'local','LIFE_MANAGER_INVESTMENT_OWNER_ID':f'alpaca-investment-{mode}',
                    f'ALPACA_INVESTMENT_{mode.upper()}_STATE_DIR':str(root),
                    f'ALPACA_INVESTMENT_{mode.upper()}_CREDENTIALS_FILE':str(root/'unused')},clear=True))
                stack.enter_context(patch.object(native,'observe',return_value=obs))
                stack.enter_context(patch.object(native,'read_allocator_snapshot',return_value=raw))
                stack.enter_context(patch.object(native,'find_order_by_client_id',side_effect=lambda **kw:
                    next(o for o in orders if o['client_order_id']==kw['client_order_id'])))
                stack.enter_context(patch.object(native,'read_crypto_activity_evidence',return_value=activity))
                writer=stack.enter_context(patch.object(native,'write_crypto_performance',wraps=PERF.write_crypto_performance,create=True))
                for name,value in (('read_crypto_history',{}),('build_candidates',[]),('_review_status',{}),
                    ('read_campaign_snapshot',{'paper':True,'unexpected_positions':[],'fills':[],'positions':[],'options':[]}),
                    ('deliver',{'message_id':'fixture'}),('deliver_failure',{'status':'delivered'}),('_retry_allowed',False)):
                    stack.enter_context(patch.object(native,name,return_value=value))
                stack.enter_context(patch.object(cli,'_context',side_effect=AssertionError('provider forbidden')))
                stack.enter_context(patch.object(cli,'_run',side_effect=AssertionError('provider forbidden')))
                with redirect_stdout(StringIO()) as output: code=native.main(wake_id='crypto-performance-fixture')
                self.assertEqual(code,0,output.getvalue());self.assertEqual(writer.call_count,1)
                saved=json.loads((root/'performance-crypto-latest.json').read_text())
                self.assertEqual(saved['completed_round_trips'],1);self.assertIsNone(saved['net_pnl_usd'])

    def test_cached_completed_cycle_cannot_be_reported_before_its_close(self):
        self.assertIsNotNone(PERF)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,activity,_=cycle_fixture(root)
            obs={'mode':'paper','paper':True,'clock':{'observed_at':NOW}}
            with patch.object(PERF,'_read_activity',return_value=activity):
                PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper')
            obs['clock']['observed_at']='2026-01-01T03:00:00Z'
            with patch.object(PERF,'_read_activity',side_effect=AssertionError('stale-clock readback forbidden')):
                result=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper')
            self.assertIsNone(result['completed_round_trips'])
            self.assertEqual(result['reason'],'crypto_performance_time_invalid')

    def test_legacy_etf_only_state_is_not_overwritten(self):
        self.assertIsNotNone(PERF,'crypto performance writer is required')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'receipts.jsonl').write_text('')
            (root/'performance-latest.json').write_text('{"legacy":true}')
            result=PERF.write_crypto_performance(root,{},mode='paper',owner_id='alpaca-investment-paper')
            self.assertEqual(result['status'],'not_applicable')
            self.assertEqual((root/'performance-latest.json').read_text(),'{"legacy":true}')
