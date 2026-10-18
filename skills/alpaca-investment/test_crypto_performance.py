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


def activity_fixture(original,*,mode,start,end,fees=None):
    with patch.object(cli,'_context',return_value={}),patch.object(cli,'_run',side_effect=[
            copy.deepcopy(original['fills']),copy.deepcopy(fees if fees is not None else original['fees'])]):
        return cli.read_crypto_activity_evidence(credentials_path=Path('unused'),cli_path=Path('unused'),
            mode=mode,period_start=start,period_end=end)


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

    def test_native_fee_inventory_deduplicates_and_attributes_only_exact_order_ids(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);orders,activity,_=cycle_fixture(root,mode)
                fees=[{'id':'fee-buy','activity_type':'CFEE','order_id':orders[0]['id'],
                       'symbol':'BTCUSD','qty':'-0.00005','price':'200','date':'2026-01-01',
                       'net_amount':'0','status':'executed'},
                      {'id':'fee-sell','activity_type':'CFEE','order_id':orders[-1]['id'],
                       'symbol':'USDCUSD','qty':'-0.01','price':'1','date':'2026-01-01',
                       'net_amount':'0','status':'executed'}]
                activity['fees']=fees
                activity['source_receipt_id']='alpaca-crypto-activities:'+proofs._digest([
                    {k:v for k,v in activity.items() if k!='source_receipt_id'}])
                result=self.project(store._rows(root/'receipts.jsonl'),mode,{o['id']:activity for o in orders})
                inventory=result.get('fee_evidence',{})
                self.assertEqual(inventory.get('observed_fee_count'),2)
                self.assertEqual([(f['asset'],f['quantity']) for f in inventory['attributed_native_fees']],
                                 [('BTC','0.00005'),('USDC','0.01')])
                self.assertEqual(inventory['unattributed_fees'],[])
                self.assertEqual(inventory['fee_settlement_status'],'unknown')
                self.assertIsNone(result['fees_usd']);self.assertIsNone(result['net_pnl_usd'])
                self.assertEqual(result['cycles'][0]['execution_cashflow_usdc'],'0.5')

    def test_orderless_and_invalid_native_fees_never_become_zero_or_guessed_costs(self):
        variants=[({},'order_id_missing'),({'order_id':'foreign'},'order_outside_closed_cycles'),
            ({'symbol':'BTCUSDC'},'received_asset_unproved'),({'status':'pending'},'fee_not_executed'),
            ({'qty':'0'},'fee_amount_invalid'),({'qty':'-0.5'},'fee_amount_invalid'),({'qty':'NaN'},'fee_amount_invalid'),
            ({'qty':'-1e1000000'},'fee_amount_invalid'),({'net_amount':'3'},'fee_amount_invalid'),
            ({'date':'2030-01-01'},'fee_date_invalid')]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,activity,_=cycle_fixture(root)
            rows=store._rows(root/'receipts.jsonl')
            for changes,reason in variants:
                fee={'id':'unproved-fee','activity_type':'CFEE','symbol':'BTCUSD','qty':'-0.00005',
                     'price':'200','date':'2026-01-01','net_amount':'0','status':'executed',**changes}
                if reason!='order_id_missing': fee.setdefault('order_id',orders[0]['id'])
                frame=copy.deepcopy(activity);frame['fees']=[fee]
                frame['source_receipt_id']='alpaca-crypto-activities:'+proofs._digest([
                    {k:v for k,v in frame.items() if k!='source_receipt_id'}])
                with self.subTest(changes=changes):
                    result=self.project(rows,activities={o['id']:frame for o in orders})
                    inventory=result.get('fee_evidence',{})
                    self.assertEqual(inventory.get('attributed_native_fees'),[])
                    self.assertEqual(inventory['unattributed_fees'][0]['reason'],reason)
                    self.assertIsNone(result['fees_usd'])

    def test_backdated_fee_date_is_valid_in_raw_bundle_and_paged_creation_windows(self):
        from test_crypto_activity_pages import read_chunk
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);orders,original,_=cycle_fixture(root,mode)
                rows=store._rows(root/'receipts.jsonl')
                fee={'id':'late-date-fee','activity_type':'CFEE','order_id':orders[0]['id'],
                    'symbol':'BTCUSD','qty':'-0.00005','date':'2026-01-01',
                    'created_at':'2026-01-02T06:00:00Z','net_amount':'0','status':'executed'}
                empty={'fills':[],'fees':[]};start='2026-01-02T00:00:00Z';end='2026-01-03T00:00:00Z'
                raw=activity_fixture(empty,mode=mode,start=start,end=end,fees=[fee])
                prefix=activity_fixture(empty,mode=mode,start=start,end='2026-01-02T05:00:00Z')
                tail=activity_fixture(empty,mode=mode,start='2026-01-02T05:00:00Z',end=end,fees=[fee])
                bundle=proofs.combine_crypto_activity_snapshots([prefix,tail],mode=mode)
                chunks=[read_chunk(kind,mode=mode,rows=[] if kind=='FILL' else [fee],
                    period_start=start,period_end=end) for kind in ('FILL','CFEE')]
                paged=proofs.crypto_activity_paged_snapshot(chunks,mode=mode)
                for form in (raw,bundle,paged):
                    with self.subTest(schema=form['schema_version']):
                        result=PERF.build_crypto_performance(rows,mode=mode,owner_id=f'alpaca-investment-{mode}',
                            activity_readbacks={o['id']:original for o in orders},fee_activity_readbacks=[form])
                        inventory=result['fee_evidence']
                        self.assertEqual(len(inventory['attributed_native_fees']),1)
                        self.assertEqual(inventory['attributed_native_fees'][0]['quantity'],'0.00005')
                        self.assertEqual(inventory['unattributed_fees'],[])
                        self.assertIsNone(result['fees_usd']);self.assertIsNone(result['net_pnl_usd'])

    def test_fee_creation_time_and_activity_date_are_validated_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,original,_=cycle_fixture(root)
            variants=[({'created_at':'2026-01-01T23:59:59Z'},'fee_creation_time_invalid'),
                ({'created_at':'2026-01-03T00:00:01Z'},'fee_creation_time_invalid'),
                ({'created_at':'invalid'},'fee_creation_time_invalid'),
                ({'date':'2026-01-04'},'fee_date_invalid'),({'date':'2025-12-31'},'fee_date_invalid')]
            for changes,reason in variants:
                fee={'id':'late-date-fee','activity_type':'CFEE','order_id':orders[0]['id'],
                    'symbol':'BTCUSD','qty':'-0.00005','date':'2026-01-01',
                    'created_at':'2026-01-02T06:00:00Z','net_amount':'0','status':'executed',**changes}
                raw=activity_fixture({'fills':[],'fees':[]},mode='paper',start='2026-01-02T00:00:00Z',
                    end='2026-01-03T00:00:00Z',fees=[fee])
                with self.subTest(changes=changes):
                    result=PERF.build_crypto_performance(store._rows(root/'receipts.jsonl'),mode='paper',
                        owner_id='alpaca-investment-paper',activity_readbacks={o['id']:original for o in orders},fee_activity_readbacks=[raw])
                    self.assertEqual(result['fee_evidence']['attributed_native_fees'],[])
                    self.assertEqual(result['fee_evidence']['unattributed_fees'][0]['reason'],reason)

    def test_fee_id_conflicting_across_snapshots_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,activity,_=cycle_fixture(root)
            frames=[]
            for qty in ('-0.00005','-0.00006'):
                frame=copy.deepcopy(activity);frame['fees']=[{'id':'same-fee','activity_type':'CFEE',
                    'symbol':'BTCUSD','qty':qty,'price':'200','date':'2026-01-01','net_amount':'0','status':'executed'}]
                frame['source_receipt_id']='alpaca-crypto-activities:'+proofs._digest([
                    {k:v for k,v in frame.items() if k!='source_receipt_id'}]);frames.append(frame)
            with self.assertRaisesRegex(ValueError,'crypto_fee_evidence_conflict'):
                self.project(store._rows(root/'receipts.jsonl'),activities=dict(zip([o['id'] for o in orders],frames)))

    def test_sell_fee_cannot_exceed_actual_received_quote_notional(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,frame,_=cycle_fixture(root)
            frame['fees']=[{'id':'oversized-sell-fee','activity_type':'CFEE','order_id':orders[-1]['id'],
                'symbol':'USDCUSD','qty':'-11','date':'2026-01-01','net_amount':'0','status':'executed'}]
            frame['source_receipt_id']='alpaca-crypto-activities:'+proofs._digest([
                {k:v for k,v in frame.items() if k!='source_receipt_id'}])
            result=self.project(store._rows(root/'receipts.jsonl'),activities={o['id']:frame for o in orders})
            inventory=result['fee_evidence']
            self.assertEqual(inventory['attributed_native_fees'],[])
            self.assertEqual(inventory['unattributed_fees'][0]['reason'],'fee_amount_invalid')

    def test_fee_cannot_reuse_a_target_fill_id_from_another_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,activity,_=cycle_fixture(root)
            frames={}
            for index,order in enumerate(orders):
                frame=copy.deepcopy(activity)
                frame['fills']=[f for f in frame['fills'] if f['order_id']==order['id']]
                if index:
                    frame['fees']=[{'id':activity['fills'][0]['id'],'activity_type':'CFEE',
                        'symbol':'BTCUSD','qty':'-0.00005','date':'2026-01-01','net_amount':'0','status':'executed'}]
                frame['source_receipt_id']='alpaca-crypto-activities:'+proofs._digest([
                    {k:v for k,v in frame.items() if k!='source_receipt_id'}]);frames[order['id']]=frame
            with self.assertRaisesRegex(ValueError,'crypto_fee_evidence_conflict'):
                self.project(store._rows(root/'receipts.jsonl'),activities=frames)

    def test_daily_fee_attribution_excludes_other_days_closed_cycles(self):
        with tempfile.TemporaryDirectory() as directory,patch(__name__+'.NOW','2026-01-03T06:00:00Z'):
            root=Path(directory);orders,first,_=cycle_fixture(root)
            more,second,_=cycle_fixture(root,index=72)
            frame=copy.deepcopy(first);frame['fills']+=second['fills']
            frame['fees']=[{'id':f'fee-{i}','activity_type':'CFEE','order_id':order['id'],
                'symbol':'BTCUSD','qty':'-0.00005','date':day,'net_amount':'0','status':'executed'}
                for i,(order,day) in enumerate(((orders[0],'2026-01-01'),(more[0],'2026-01-02')))]
            frame['source_receipt_id']='alpaca-crypto-activities:'+proofs._digest([
                {k:v for k,v in frame.items() if k!='source_receipt_id'}])
            obs={'mode':'paper','paper':True,'clock':{'observed_at':NOW}}
            result=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',
                activity_reader=lambda **_:frame)
            self.assertEqual(result['closed_cycle_count'],2)
            for day in ('2026-01-01','2026-01-02'):
                daily=json.loads((root/f'performance-crypto-daily-{day}.json').read_text())
                evidence=daily['fee_evidence'];ids={c['cycle_id'] for c in daily['cycles']}
                self.assertEqual(len(evidence['attributed_native_fees']),1)
                self.assertTrue(all(f['cycle_id'] in ids for f in evidence['attributed_native_fees']))
                self.assertEqual(evidence['observation_scope'],'account_activity_windows')
                self.assertEqual(set(evidence['attribution_cycle_ids']),ids)
                self.assertEqual(evidence['observed_fee_count'],2)

    def test_empty_fee_inventory_remains_unsettled(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,activity,_=cycle_fixture(root)
            result=self.project(store._rows(root/'receipts.jsonl'),activities={o['id']:activity for o in orders})
            inventory=result.get('fee_evidence',{})
            self.assertEqual(inventory.get('observed_fee_count'),0)
            self.assertEqual(inventory['fee_settlement_status'],'unknown')
            self.assertIsNone(result['fees_usd'])

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

    def test_late_fee_readback_keeps_execution_cache_and_replays_without_reads(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);orders,frame,_=cycle_fixture(root,mode)
                owner=f'alpaca-investment-{mode}'
                obs={'mode':mode,'paper':mode=='paper','clock':{'observed_at':NOW}}
                first=PERF.write_crypto_performance(root,obs,mode=mode,owner_id=owner,activity_reader=lambda **_:frame)
                later='2026-01-02T06:00:00Z';obs['clock']['observed_at']=later
                fee={'id':'late-fee','activity_type':'CFEE','order_id':orders[0]['id'],
                    'symbol':'BTCUSD','qty':'-0.00005','date':'2026-01-02','net_amount':'0','status':'executed'}
                calls=[]
                def reader(**kw):
                    calls.append(kw)
                    return activity_fixture(frame,mode=mode,start=kw['period_start'],end=kw['period_end'],fees=[fee])
                second=PERF.write_crypto_performance(root,obs,mode=mode,owner_id=owner,activity_reader=reader)
                self.assertEqual(second['fee_evidence']['observed_fee_count'],1)
                self.assertEqual(second['fee_evidence']['attributed_native_fees'][0]['quantity'],'0.00005')
                self.assertEqual(second['order_activity_refs'],first['order_activity_refs'])
                self.assertEqual(len(calls),1);self.assertEqual(calls[0]['period_start'],NOW)
                self.assertEqual(second['fee_readback_through'],later)
                with patch.object(PERF,'_read_activity',side_effect=AssertionError('same clock replay')):
                    replay=PERF.write_crypto_performance(root,obs,mode=mode,owner_id=owner)
                self.assertEqual(replay['fee_evidence'],second['fee_evidence'])
                obs['clock']['observed_at']='2026-01-02T06:05:00Z'
                with patch.object(PERF,'_read_activity',side_effect=AssertionError('same UTC day')):
                    same_day=PERF.write_crypto_performance(root,obs,mode=mode,owner_id=owner)
                self.assertEqual(same_day['fee_evidence']['observed_fee_count'],1)
                daily=json.loads((root/'performance-crypto-daily-2026-01-01.json').read_text())
                self.assertEqual(daily['generated_as_of'],obs['clock']['observed_at'])
                self.assertIsNone(second['fees_usd']);self.assertFalse(second['capital_expansion_allowed'])

    def test_fee_backlog_uses_one_ninety_day_window_per_new_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,frame,_=cycle_fixture(root)
            obs={'mode':'paper','paper':True,'clock':{'observed_at':NOW}}
            PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=lambda **_:frame)
            calls=[]
            def reader(**kw):
                calls.append(kw)
                return activity_fixture(frame,mode='paper',start=kw['period_start'],end=kw['period_end'])
            obs['clock']['observed_at']='2026-07-01T06:00:00Z'
            first=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=reader)
            self.assertEqual(len(calls),1)
            self.assertEqual(first.get('fee_readback_through'),'2026-04-01T00:00:00Z')
            PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=reader)
            self.assertEqual(len(calls),1)
            obs['clock']['observed_at']='2026-07-01T06:05:00Z'
            second=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=reader)
            self.assertEqual(len(calls),2)
            self.assertEqual(second['fee_readback_through'],'2026-06-30T00:00:00Z')
            obs['clock']['observed_at']='2026-07-01T06:10:00Z'
            third=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=reader)
            self.assertEqual(len(calls),3);self.assertEqual(third['fee_readback_through'],obs['clock']['observed_at'])
            self.assertTrue(all(proofs.parse_instant(c['period_end'])-proofs.parse_instant(c['period_start'])<=timedelta(days=90) for c in calls))

    def test_page_limits_shrink_the_actual_window_for_fills_and_fees(self):
        for cached in (False,True):
            with self.subTest(cached=cached),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);orders,frame,_=cycle_fixture(root)
                obs={'mode':'paper','paper':True,'clock':{'observed_at':NOW}}
                if cached:
                    PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=lambda **_:frame)
                calls=[]
                def reader(**kw):
                    calls.append(kw)
                    after=proofs.parse_instant(kw['period_start']).replace(hour=0,minute=0,second=0,microsecond=0)
                    if proofs.parse_instant(kw['period_end'])-after>timedelta(days=7):
                        raise ValueError('crypto_activity_limit_exceeded')
                    return activity_fixture(frame,mode='paper',start=kw['period_start'],end=kw['period_end'])
                for index,want_days in enumerate((16,8,4)):
                    obs['clock']['observed_at']=f'2026-02-01T06:{index:02}:00Z'
                    result=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=reader)
                    self.assertEqual(result.get('activity_window_days'),want_days)
                    self.assertEqual(result['next_action'],'retry_activity_readback_with_smaller_window')
                obs['clock']['observed_at']='2026-02-01T06:03:00Z'
                result=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=reader)
                self.assertEqual(result['completed_round_trips'],1)
                self.assertEqual(result['fee_readback_through'],'2026-01-05T00:00:00Z')
                self.assertEqual(len(calls),4)
                self.assertEqual(len({c['period_end'] for c in calls}),4)
                PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=reader)
                self.assertEqual(len(calls),4)
                obs['clock']['observed_at']='2026-02-01T06:04:00Z'
                next_result=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=reader)
                self.assertEqual(next_result['fee_readback_through'],'2026-01-09T00:00:00Z')
                self.assertIsNone(next_result['fees_usd'])

    def test_fill_spanning_a_shrunk_day_advances_and_combines_real_evidence(self):
        with tempfile.TemporaryDirectory() as directory,patch(__name__+'.NOW','2026-01-10T06:00:00Z'):
            root=Path(directory);orders,frame,owned=cycle_fixture(root,index=59)
            ledger=root/'receipts.jsonl';rows=store._rows(ledger)
            sell=copy.deepcopy(orders[-1]);sell['filled_at']='2026-01-02T00:00:01Z'
            old=next(r for r in rows if r.get('receipt_type')=='outcome' and r.get('effect_id')==owned['close_effect_id'])
            account=copy.deepcopy(old['strategy_receipt']['account_readback'])
            account['clock']['observed_at']='2026-01-02T00:00:02Z'
            base=[r for r in rows if r is not old]
            verified=proofs.close_fill_proof_from_rows(base,{**owned,'status':'closing'},sell,account,
                mode='paper',owner_id='alpaca-investment-paper')
            old['broker']=sell;old['strategy_receipt']=verified
            ledger.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            frame['fills'][-1]['transaction_time']=sell['filled_at']
            obs={'mode':'paper','paper':True,'clock':{'observed_at':NOW}}
            calls=[]
            def reader(**kw):
                calls.append(kw)
                after=proofs.parse_instant(kw['period_start']).replace(hour=0,minute=0,second=0,microsecond=0)
                end=proofs.parse_instant(kw['period_end'])
                if end-after>timedelta(days=1): raise ValueError('crypto_activity_limit_exceeded')
                selected=copy.deepcopy(frame)
                selected['fills']=[f for f in frame['fills'] if after<=proofs.parse_instant(f['transaction_time'])<=end]
                return activity_fixture(selected,mode='paper',start=kw['period_start'],end=kw['period_end'])
            for minute in range(5):
                obs['clock']['observed_at']=f'2026-01-10T06:{minute:02}:00Z'
                result=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=reader)
            self.assertEqual(len(calls),5)
            self.assertEqual(calls[-1]['period_start'],'2026-01-02T00:00:00Z')
            self.assertEqual(result['missing_activity_order_ids'],[])
            self.assertEqual(result['cycles'][0]['execution_cashflow_usdc'],'0.5')
            reference=result['order_activity_refs'][sell['id']]
            evidence=result['activity_readbacks'][reference]
            self.assertEqual(evidence['kind'],'crypto_activity_bundle')
            self.assertEqual(len(evidence['segments']),2)
            self.assertEqual(proofs.crypto_fill_activity_proof(evidence,sell,mode='paper')['filled_qty'],'0.05')

    def test_bundle_hash_cannot_be_bypassed_by_equal_python_scalar_types(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,frame,_=cycle_fixture(root)
            later=activity_fixture(frame,mode='paper',start=NOW,end='2026-01-02T06:00:00Z')
            bundle=proofs.combine_crypto_activity_snapshots([frame,later],mode='paper')
            for key,value in (('paper',1),('schema_version',2.0),('page_size',100.0)):
                bad=copy.deepcopy(bundle)
                if key=='page_size': bad['request'][key]=value
                else: bad[key]=value
                with self.subTest(key=key),self.assertRaisesRegex(ValueError,'owned_crypto_activities_invalid'):
                    proofs.validate_crypto_activity_snapshot(bad,mode='paper')

    def test_bundle_fee_keeps_its_original_segment_date_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,frame,_=cycle_fixture(root)
            fee={'id':'future-segment-fee','activity_type':'CFEE','order_id':orders[0]['id'],
                'symbol':'BTCUSD','qty':'-0.00005','date':'2026-01-02','net_amount':'0','status':'executed'}
            earlier=activity_fixture(frame,mode='paper',start=frame['requested_period_start'],end=NOW,fees=[fee])
            later=activity_fixture(frame,mode='paper',start=NOW,end='2026-01-02T06:00:00Z',fees=[])
            bundle=proofs.combine_crypto_activity_snapshots([earlier,later],mode='paper')
            result=self.project(store._rows(root/'receipts.jsonl'),activities={o['id']:bundle for o in orders})
            self.assertEqual(result['fee_evidence']['attributed_native_fees'],[])
            self.assertEqual(result['fee_evidence']['unattributed_fees'][0]['reason'],'fee_date_invalid')

    def test_writer_resumes_page_chunks_without_replay_and_preserves_failed_resume(self):
        from test_crypto_activity_pages import read_chunk,activity_rows
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);orders,frame,_=cycle_fixture(root,mode)
                owner=f'alpaca-investment-{mode}'
                obs={'mode':mode,'paper':mode=='paper','clock':{'observed_at':'2026-01-02T00:01:00Z'}}
                records={'FILL':frame['fills']+[{**f,'order_id':'foreign'} for f in activity_rows('FILL',399)],
                         'CFEE':activity_rows('CFEE')}
                calls=[];fail=[False]
                def page_reader(**kw):
                    if fail[0]: raise ValueError('crypto_page_transport_failed')
                    calls.append(kw)
                    return read_chunk(kw['activity_type'],kw['page_token'],kw['mode'],records[kw['activity_type']],
                        period_start=kw['period_start'],period_end=kw['period_end'])
                def regular(**_): raise ValueError('crypto_activity_limit_exceeded')
                def write():
                    try: return PERF.write_crypto_performance(root,obs,mode=mode,owner_id=owner,
                        activity_reader=regular,activity_page_reader=page_reader)
                    except TypeError as error: self.fail('writer needs page continuation: '+str(error))
                write();obs['clock']['observed_at']='2026-01-02T00:02:00Z';write()
                obs['clock']['observed_at']='2026-01-02T00:03:00Z';partial=write()
                self.assertEqual(len(partial['activity_page_chunks']),1)
                self.assertEqual(partial['reason'],'crypto_activity_pagination_pending')
                self.assertEqual(len(calls),1);write();self.assertEqual(len(calls),1)
                fail[0]=True;obs['clock']['observed_at']='2026-01-02T00:04:00Z';failed=write()
                self.assertEqual(failed['activity_page_chunks'],partial['activity_page_chunks'])
                self.assertEqual(failed['known_closed_cycle_ids'],partial['known_closed_cycle_ids'])
                fail[0]=False
                for minute in (5,6,7):
                    obs['clock']['observed_at']=f'2026-01-02T00:{minute:02}:00Z';result=write()
                self.assertEqual([c['activity_type'] for c in calls],['FILL','FILL','CFEE','CFEE'])
                self.assertEqual(calls[1]['page_token'],partial['activity_page_chunks'][0]['next_page_token'])
                self.assertEqual(result['cycles'][0]['execution_cashflow_usdc'],'0.5')
                self.assertEqual(result['fee_evidence']['observed_fee_count'],401)
                self.assertEqual(result['activity_page_chunks'],[]);self.assertIsNone(result['activity_limit_window'])
                self.assertEqual(result['fee_readback_through'],'2026-01-02T00:00:00Z')
                write();self.assertEqual(len(calls),4)
                self.assertIsNone(result['fees_usd']);self.assertIsNone(result['net_pnl_usd'])

    def test_one_day_limit_keeps_evidence_and_avoids_larger_prefix_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,frame,_=cycle_fixture(root)
            obs={'mode':'paper','paper':True,'clock':{'observed_at':NOW}}
            first=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=lambda **_:frame)
            calls=[]
            def reader(**kw):
                calls.append(kw);raise ValueError('crypto_activity_limit_exceeded')
            # Actual provider window is one UTC day plus one minute, then one day.
            obs['clock']['observed_at']='2026-01-02T00:01:00Z'
            first_fail=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=reader)
            self.assertEqual(first_fail.get('activity_window_days'),1)
            obs['clock']['observed_at']='2026-01-02T00:02:00Z'
            minimum=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=reader)
            self.assertEqual(minimum['next_action'],'inspect_single_day_activity_pagination')
            for clock in ('2026-01-02T00:03:00Z','2026-01-03T00:00:00Z'):
                obs['clock']['observed_at']=clock
                held=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=reader)
                self.assertEqual(held['reason'],'crypto_activity_single_day_limit')
                self.assertEqual(held['order_activity_refs'],first['order_activity_refs'])
                self.assertIsNone(held['net_pnl_usd'])
            self.assertEqual(len(calls),2)

    def test_invalid_window_state_preserves_anchors_and_other_errors_do_not_shrink(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,frame,_=cycle_fixture(root)
            obs={'mode':'paper','paper':True,'clock':{'observed_at':NOW}}
            first=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=lambda **_:frame)
            path=root/'performance-crypto-latest.json'
            for invalid in (True,0,91,'4'):
                bad={**first,'activity_window_days':invalid};path.write_text(json.dumps(bad))
                result=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper')
                self.assertEqual(result.get('reason'),'crypto_performance_activity_cache_invalid')
                self.assertEqual(result['known_closed_cycle_ids'],first['known_closed_cycle_ids'])
            path.write_text(json.dumps(first));obs['clock']['observed_at']='2026-02-01T06:00:00Z'
            result=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',
                activity_reader=lambda **_:(_ for _ in ()).throw(ValueError('crypto_transport_failed')))
            self.assertEqual(result['reason'],'crypto_transport_failed')
            self.assertEqual(result.get('activity_window_days'),90)

    def test_failed_or_wrong_window_fee_readback_keeps_verified_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,frame,_=cycle_fixture(root)
            obs={'mode':'paper','paper':True,'clock':{'observed_at':NOW}}
            first=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=lambda **_:frame)
            obs['clock']['observed_at']='2026-01-02T06:00:00Z'
            for reader,reason in ((lambda **_:(_ for _ in ()).throw(ValueError('crypto_activity_invalid')),'crypto_activity_invalid'),
                    (lambda **_:frame,'crypto_fee_readback_window_invalid')):
                result=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=reader)
                self.assertEqual(result.get('reason'),reason)
                self.assertEqual(result['activity_readbacks'],first['activity_readbacks'])
                self.assertEqual(result['order_activity_refs'],first['order_activity_refs'])

    def test_fee_only_snapshot_cannot_change_known_execution_or_contain_future_fill(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,original,_=cycle_fixture(root)
            rows=store._rows(root/'receipts.jsonl')
            for change,reason in (({'price':'999'},'crypto_cycle_execution_conflict'),
                    ({'transaction_time':'2026-01-03T06:00:01Z'},'owned_crypto_activities_invalid')):
                frame=activity_fixture(original,mode='paper',start=NOW,end='2026-01-02T06:00:00Z')
                frame['fills'][0].update(change)
                frame['source_receipt_id']='alpaca-crypto-activities:'+proofs._digest([
                    {k:v for k,v in frame.items() if k!='source_receipt_id'}])
                with self.subTest(change=change),self.assertRaisesRegex(ValueError,reason):
                    PERF.build_crypto_performance(rows,mode='paper',owner_id='alpaca-investment-paper',
                        activity_readbacks={o['id']:original for o in orders},fee_activity_readbacks=[frame])

    def test_fee_refresh_cannot_add_or_omit_known_order_execution_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,original,_=cycle_fixture(root)
            rows=store._rows(root/'receipts.jsonl')
            for action in ('add','omit'):
                frame=activity_fixture(original,mode='paper',start=NOW,end='2026-01-02T06:00:00Z')
                if action=='add': frame['fills'].append({**frame['fills'][0],'id':'new-extra-buy-fill','qty':'0.01'})
                else: frame['fills']=frame['fills'][1:]
                frame['source_receipt_id']='alpaca-crypto-activities:'+proofs._digest([
                    {k:v for k,v in frame.items() if k!='source_receipt_id'}])
                with self.subTest(action=action),self.assertRaisesRegex(ValueError,'crypto_cycle_execution_conflict'):
                    PERF.build_crypto_performance(rows,mode='paper',owner_id='alpaca-investment-paper',
                        activity_readbacks={o['id']:original for o in orders},fee_activity_readbacks=[frame])

    def test_bad_cache_metadata_never_erases_known_fee_or_cycle_anchors(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,frame,_=cycle_fixture(root)
            fee={'id':'known-fee','activity_type':'CFEE','symbol':'BTCUSD','qty':'-0.00005',
                'date':'2026-01-01','net_amount':'0','status':'executed'}
            frame=activity_fixture(frame,mode='paper',start=frame['requested_period_start'],end=NOW,fees=[fee])
            obs={'mode':'paper','paper':True,'clock':{'observed_at':NOW}}
            first=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=lambda **_:frame)
            path=root/'performance-crypto-latest.json';bad=copy.deepcopy(first);bad['order_activity_refs']=[]
            path.write_text(json.dumps(bad))
            result=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper')
            self.assertEqual(result['known_fee_activity_ids'],['known-fee'])
            self.assertEqual(result['known_closed_cycle_ids'],first['known_closed_cycle_ids'])
            self.assertEqual(result['reason'],'crypto_performance_activity_cache_invalid')
            empty=activity_fixture(frame,mode='paper',start=frame['requested_period_start'],end=NOW,fees=[])
            recovered=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper',activity_reader=lambda **_:empty)
            self.assertEqual(recovered['reason'],'crypto_performance_fee_history_missing')
            self.assertEqual(recovered['known_fee_activity_ids'],['known-fee'])

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
        for mode,paged in ((m,p) for m in ('paper','live') for p in (False,True)):
            with self.subTest(mode=mode,paged=paged),tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
                root=Path(directory);orders,activity,owned=cycle_fixture(root,mode)
                (root/'live-owned-position.json').write_text(json.dumps(owned));native=native_run()
                obs={'mode':mode,'paper':mode=='paper','clock':{'observed_at':NOW},'account':{'cash':'0','equity':'100'},
                     'positions':[{'symbol':'USDCUSD','qty':'100','unrealized_pl':'0'}],
                     'activities_count':0,'open_and_closed_orders_count':0}
                raw,_=snapshot(mode);raw.pop('crypto_history');raw['positions']=0
                if paged:
                    from test_crypto_activity_pages import read_chunk,activity_rows
                    def limited(**_): raise ValueError('crypto_activity_limit_exceeded')
                    for minute in (1,2):
                        obs['clock']['observed_at']=f'2026-01-02T00:{minute:02}:00Z'
                        PERF.write_crypto_performance(root,obs,mode=mode,owner_id=f'alpaca-investment-{mode}',activity_reader=limited)
                    obs['clock']['observed_at']='2026-01-02T00:03:00Z'
                    chunk=read_chunk('FILL',mode=mode,rows=activity['fills']+[
                        {**f,'order_id':'foreign'} for f in activity_rows('FILL',399)],
                        period_start='2026-01-01T00:00:00Z',period_end='2026-01-02T00:00:00Z')
                    stack.enter_context(patch.object(native,'read_crypto_activity_page_chunk',return_value=chunk))
                stack.enter_context(patch.dict(os.environ,{'LIFE_MANAGER_INVESTMENT_MODE':mode,
                    'LIFE_MANAGER_INVESTMENT_DEPLOYMENT':'local','LIFE_MANAGER_INVESTMENT_OWNER_ID':f'alpaca-investment-{mode}',
                    f'ALPACA_INVESTMENT_{mode.upper()}_STATE_DIR':str(root),
                    f'ALPACA_INVESTMENT_{mode.upper()}_CREDENTIALS_FILE':str(root/'unused')},clear=True))
                stack.enter_context(patch.object(native,'observe',return_value=obs))
                stack.enter_context(patch.object(native,'read_allocator_snapshot',return_value=raw))
                stack.enter_context(patch.object(native,'find_order_by_client_id',side_effect=lambda **kw:
                    next(o for o in orders if o['client_order_id']==kw['client_order_id'])))
                stack.enter_context(patch.object(native,'read_crypto_activity_evidence',return_value=activity))
                from test_crypto_fx_performance import quote
                from test_crypto_fx_quote import seal as seal_fx
                def fx_response(**kwargs):
                    frame=quote(kwargs['asof_at'],mode);frame['observed_at']=kwargs['observed_at']
                    return seal_fx(frame)
                fx_reader=stack.enter_context(patch.object(native,'read_crypto_fx_evidence',side_effect=fx_response))
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
                self.assertEqual(fx_reader.call_count,0 if paged else 2)
                if not paged:self.assertIsNotNone(saved['cycles'][0]['fx_reference']['execution_cashflow_usd'])
                if paged:
                    self.assertEqual(len(saved['activity_page_chunks']),1)
                    self.assertEqual(saved['reason'],'crypto_activity_pagination_pending')
                    self.assertIsNone(saved['completed_round_trips'])
                else: self.assertEqual(saved['completed_round_trips'],1)
                self.assertIsNone(saved['net_pnl_usd'])

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

    def test_partial_history_loss_stays_unknown_across_retries(self):
        self.assertIsNotNone(PERF)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,activity,_=cycle_fixture(root)
            obs={'mode':'paper','paper':True,'clock':{'observed_at':NOW}}
            with patch.object(PERF,'_read_activity',return_value=activity):
                PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper')
            count=len(store._rows(root/'receipts.jsonl'))
            more,next_activity,_=cycle_fixture(root,index=1)
            with patch.object(PERF,'_read_activity',return_value=next_activity):
                self.assertEqual(PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper')['completed_round_trips'],2)
            rows=store._rows(root/'receipts.jsonl');(root/'receipts.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows[count:]))
            for _ in range(2):
                with patch.object(PERF,'_read_activity',side_effect=AssertionError('history loss must be diagnosed first')):
                    result=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper')
                self.assertIsNone(result['completed_round_trips'])
                self.assertEqual(result['reason'],'crypto_performance_history_missing')
            daily=json.loads((root/'performance-crypto-daily-2026-01-01.json').read_text())
            self.assertEqual(daily['completed_round_trips'],2)

    def test_cache_reference_corruption_cannot_erase_known_history(self):
        self.assertIsNotNone(PERF)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,activity,_=cycle_fixture(root)
            count=len(store._rows(root/'receipts.jsonl'))
            more,second,_=cycle_fixture(root,index=1)
            obs={'mode':'paper','paper':True,'clock':{'observed_at':NOW}}
            # One complete official observation contains both cycles' fills.
            combined=copy.deepcopy(activity);combined['fills']+=second['fills']
            body={k:v for k,v in combined.items() if k!='source_receipt_id'}
            combined['source_receipt_id']='alpaca-crypto-activities:'+proofs._digest([body])
            with patch.object(PERF,'_read_activity',return_value=combined):
                result=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper')
            self.assertEqual(result['completed_round_trips'],2)
            path=root/'performance-crypto-latest.json';payload=json.loads(path.read_text())
            payload['order_activity_refs']['orphan']='missing-frame';path.write_text(json.dumps(payload))
            error=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper')
            self.assertEqual(error['reason'],'crypto_performance_activity_cache_invalid')
            self.assertEqual(len(error['known_closed_cycle_ids']),2)
            rows=store._rows(root/'receipts.jsonl')
            (root/'receipts.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows[count:]))
            retry=PERF.write_crypto_performance(root,obs,mode='paper',owner_id='alpaca-investment-paper')
            self.assertEqual(retry['reason'],'crypto_performance_history_missing')
            self.assertIsNone(retry['completed_round_trips'])

    def test_no_fill_provider_cannot_be_reused_for_a_filled_entry(self):
        from test_closed_audit import no_fill_fixture
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'LIFE_MANAGER_INVESTMENT_OWNER_ID':'alpaca-investment-paper'}):
            root=Path(directory);owned,broker,account,owner=no_fill_fixture(root,'paper')
            rows=store._rows(root/'receipts.jsonl')
            for row in rows:
                if row.get('broker_receipt_id')==broker['id']: row['broker_receipt_id']='buy-1'
                if isinstance(row.get('broker'),dict) and row['broker'].get('id')==broker['id']: row['broker']['id']='buy-1'
            broker['id']='buy-1';(root/'receipts.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            store.record_no_fill_account_receipt(root/'receipts.jsonl',owned,broker,account,mode='paper',owner_id=owner)
            orders,activity,_=cycle_fixture(root,index=1)
            with self.assertRaises(ValueError): self.project(store._rows(root/'receipts.jsonl'),activities={o['id']:activity for o in orders})

    def test_legacy_etf_only_state_is_not_overwritten(self):
        self.assertIsNotNone(PERF,'crypto performance writer is required')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'receipts.jsonl').write_text('')
            (root/'performance-latest.json').write_text('{"legacy":true}')
            result=PERF.write_crypto_performance(root,{},mode='paper',owner_id='alpaca-investment-paper')
            self.assertEqual(result['status'],'not_applicable')
            self.assertEqual((root/'performance-latest.json').read_text(),'{"legacy":true}')
