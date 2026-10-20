"""Reported native balance arithmetic never confers fee finality or net authority."""
import copy
from decimal import localcontext
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import crypto_performance as perf
from test_crypto_performance import cycle_fixture,activity_fixture,NOW
from test_crypto_flow_writer import frame


class QuantityReconciliationTests(unittest.TestCase):
    def setup_cycle(self,root,mode='paper',*,partial=False,credited_qty='0.05',baseline_qty='100',legacy=False):
        account='synthetic-native-account-'+mode
        before={'mode':mode,'paper':mode=='paper','account':{'id':account,'cash':'0','equity':'100'},
            'positions':[{'symbol':'USDCUSD','qty':baseline_qty}],'clock':{'observed_at':'2026-01-01T04:00:00Z'}}
        orders,activity,_=cycle_fixture(root,mode,partial=partial,native_account_id=account,
            pre_trade_readback=None if legacy else before,credited_qty=credited_qty)
        current=copy.deepcopy(before);current['clock']['observed_at']=NOW
        current['positions'][0]['qty']='100.5'
        return orders,activity,current

    def write(self,root,activity,current,*,fees=None,extras=None,wallets=None,reader=None):
        mode=current['mode']
        def raw(**kw):
            value=frame(kw,count=0);value['activity_pages']=[copy.deepcopy([*activity['fills'],*(fees or []),*(extras or [])])]
            if wallets is not None:value['wallet_transfers']=copy.deepcopy(wallets)
            return value
        with patch.dict(os.environ,{},clear=True):
            result=perf.write_crypto_performance(root,current,mode=mode,owner_id='alpaca-investment-'+mode,
                activity_reader=lambda **kw:activity_fixture(activity,mode=mode,start=kw['period_start'],end=kw['period_end'],fees=fees),
                flow_reader=reader or raw)
        self.assertIn('native_quantity_reconciliation',result)
        return result,result['native_quantity_reconciliation']

    def fee(self,order,asset,qty,*,created='2026-01-01T05:00:00Z'):
        return {'id':'synthetic-fee-'+asset,'activity_type':'CFEE','order_id':order['id'],
            'symbol':asset+'USD','qty':qty,'net_amount':'0','status':'executed',
            'date':'2026-01-01','created_at':created}

    def test_exact_native_balance_match_is_not_fee_zero_or_net(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);_,activity,current=self.setup_cycle(root,mode)
                result,report=self.write(root,activity,current)
                self.assertEqual(report['status'],'observed_match')
                self.assertEqual(report['account_delta'],{'BTC':'0','USDC':'0.5'})
                self.assertEqual(report['known_flow_delta'],{'BTC':'0','USDC':'0.5'})
                self.assertEqual(report['unexplained_delta'],{'BTC':'0','USDC':'0'})
                self.assertEqual(report['observed_fee_quantities'],{'BTC':None,'USDC':None})
                self.assertEqual(report['fee_completeness_status'],'unknown')
                self.assertIsNone(report['net_pnl_usd']);self.assertFalse(report['capital_expansion_allowed'])
                self.assertIsNone(result['net_pnl_usd']);self.assertEqual(result['measurement_status'],'partial')
                daily=json.loads((root/'performance-crypto-daily-2026-01-01.json').read_text())
                self.assertEqual(daily['native_quantity_reconciliation'],report)

    def test_buy_credit_gap_and_sell_fee_are_counted_in_the_received_asset(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);orders,activity,current=self.setup_cycle(root,mode,credited_qty='0.049875')
                fees=[self.fee(orders[0],'BTC','-0.000125',created='2026-01-01T04:00:02Z'),self.fee(orders[-1],'USDC','-0.01')]
                current['positions'][0]['qty']='100.46375'
                _,report=self.write(root,activity,current,fees=fees)
                self.assertEqual(report['status'],'observed_match')
                self.assertEqual(report['observed_fee_quantities'],{'BTC':'0.000125','USDC':'0.01'})
                self.assertEqual(report['known_flow_delta'],{'BTC':'0','USDC':'0.46375'})
                self.assertEqual(report['buy_credit_gaps'][0]['initial_gross_minus_credited_btc'],'0.000125')
                self.assertEqual(report['buy_credit_gaps'][0]['unexplained_btc'],'0')

    def test_partial_sell_and_late_fee_refresh_keep_the_original_baseline_clock(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);orders,activity,current=self.setup_cycle(root,'live',partial=True)
            current['positions'][0]['qty']='100.53'
            _,first=self.write(root,activity,current)
            self.assertEqual(first['status'],'observed_match')
            current['clock']['observed_at']='2026-01-02T06:00:00Z';current['positions'][0]['qty']='100.52'
            fee=self.fee(orders[-1],'USDC','-0.01',created='2026-01-02T01:00:00Z')
            _,later=self.write(root,activity,current,fees=[fee])
            self.assertEqual(later['status'],'observed_match')
            self.assertEqual(later['known_flow_delta']['USDC'],'0.52')
            self.assertEqual(later['baseline']['observed_at'],'2026-01-01T04:00:00Z')
            self.assertEqual(later['current']['observed_at'],'2026-01-02T06:00:00Z')
            self.assertEqual(later['observed_fee_quantities']['USDC'],'0.01')

    def test_other_native_fill_counts_for_account_but_not_owner_profit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,activity,current=self.setup_cycle(root)
            other={'id':'synthetic-other-fill','activity_type':'FILL','order_id':'synthetic-other-order',
                'symbol':'BTCUSDC','side':'buy','qty':'0.01','price':'200','transaction_time':'2026-01-01T05:00:00Z'}
            current['positions']=[{'symbol':'USDCUSD','qty':'98.5'},{'symbol':'BTCUSDC','qty':'0.01'}]
            _,report=self.write(root,activity,current,extras=[other])
            self.assertEqual(report['status'],'observed_match')
            self.assertEqual(report['known_flow_delta'],{'BTC':'0.01','USDC':'-1.5'})
            self.assertEqual(report['unattributed_order_ids'],['synthetic-other-order'])
            self.assertIsNone(report['net_pnl_usd'])

    def test_unexplained_balance_and_unlocated_wallet_or_activity_do_not_become_matches(self):
        for kind in ('difference','wallet','OCT','OCT_without_time'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);_,activity,current=self.setup_cycle(root,'live')
                extras=[];wallets=[]
                if kind=='difference':current['positions'][0]['qty']='100.49'
                elif kind in {'OCT','OCT_without_time'}:
                    extras=[{'id':'synthetic-oct','activity_type':'OCT','qty':'1','net_amount':'1'}]
                    if kind=='OCT':extras[0]['created_at']='2026-01-01T05:00:00Z'
                else:wallets=[
                    {'id':'synthetic-wallet-1','asset':'USDC','amount':'1','status':'COMPLETE','created_at':'2025-12-31T01:00:00Z'},
                    {'id':'synthetic-wallet-2','asset':'BTC','amount':'0.01','status':'COMPLETE','created_at':'2025-12-31T02:00:00Z'}]
                result,report=self.write(root,activity,current,extras=extras,wallets=wallets)
                self.assertEqual(report['status'],'unexplained' if kind=='difference' else 'unknown')
                if kind=='difference':self.assertEqual(report['unexplained_delta']['USDC'],'-0.01')
                else:self.assertTrue(report['reasons'])
                if kind=='wallet':
                    transfer_refs=report['unlocated_wallet_transfer_refs']
                    ref=next(iter(result['flow_readbacks']))
                    self.assertEqual(report['unlocated_wallet_transfer_count'],2)
                    self.assertEqual(transfer_refs,[{'flow_readback_ref':ref,'row_index':0},
                        {'flow_readback_ref':ref,'row_index':1}])
                    self.assertEqual([result['flow_readbacks'][item['flow_readback_ref']]['readback']['wallet_transfers'][item['row_index']]['id']
                        for item in transfer_refs],['synthetic-wallet-1','synthetic-wallet-2'])
                    daily=json.loads((root/'performance-crypto-daily-2026-01-01.json').read_text())
                    self.assertEqual(daily['native_quantity_reconciliation']['unlocated_wallet_transfer_refs'],transfer_refs)
                    self.assertIn(ref,daily['flow_readbacks'])
                if kind=='OCT_without_time':self.assertEqual(report['unsupported_activity_ids'],['synthetic-oct'])
                self.assertIsNone(report['net_pnl_usd'])

    def test_wallet_transfer_status_changes_are_recorded_without_activity_attribution(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,activity,current=self.setup_cycle(root,'live');calls=[]
            transfer={'id':'synthetic-wallet-transfer','asset':'USDC','amount':'1',
                'direction':'INCOMING','created_at':'2025-12-31T01:00:00Z'}
            def reader(**kw):
                calls.append(copy.deepcopy(kw));raw=frame(kw,count=0)
                snapshot={**transfer,'status':'PROCESSING' if len(calls)==1 else 'COMPLETE'}
                raw['wallet_transfers']=[copy.deepcopy(snapshot)]*(2 if len(calls)==1 else 1)
                raw['activity_pages']=[copy.deepcopy(activity['fills'])] if len(calls)==1 else [[]]
                return raw

            first,_=self.write(root,activity,current,reader=reader)
            current['clock']['observed_at']='2026-01-02T06:00:00Z'
            second,report=self.write(root,activity,current,reader=reader)

            self.assertEqual(len(calls),2)
            self.assertEqual(first['net_pnl_usd'],None)
            self.assertEqual(len(report['wallet_transfer_status_evidence']),1)
            evidence=report['wallet_transfer_status_evidence'][0]
            self.assertEqual(evidence['transfer_id'],transfer['id'])
            self.assertEqual([row['status'] for row in evidence['observations']],['PROCESSING','COMPLETE'])
            self.assertEqual([row['observed_at'] for row in evidence['observations']],
                [NOW,'2026-01-02T06:00:00Z'])
            self.assertTrue(evidence['status_transition_observed'])
            self.assertIsNone(evidence['effect_time'])
            self.assertEqual(evidence['activity_link_status'],'not_documented')
            self.assertEqual(report['status'],'unknown')
            self.assertIn('native_wallet_effect_time_unproved',report['reasons'])
            self.assertIsNone(second['net_pnl_usd']);self.assertFalse(second['capital_expansion_allowed'])

    def test_wallet_transfer_missing_identity_or_same_snapshot_conflict_remains_unknown(self):
        for kind in ('missing_id','missing_status','same_snapshot_conflict'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);_,activity,current=self.setup_cycle(root,'live')
                transfer={'id':'synthetic-wallet-transfer','asset':'USDC','amount':'1',
                    'direction':'INCOMING','created_at':'2025-12-31T01:00:00Z','status':'COMPLETE'}
                if kind=='missing_id': transfer.pop('id')
                if kind=='missing_status': transfer.pop('status')
                wallets=[transfer]
                if kind=='same_snapshot_conflict':
                    wallets=[{**transfer,'status':'PROCESSING'},{**transfer,'status':'COMPLETE'}]
                def reader(**kw):
                    raw=frame(kw,count=0);raw['wallet_transfers']=copy.deepcopy(wallets)
                    raw['activity_pages']=[copy.deepcopy(activity['fills'])]
                    return raw

                _,report=self.write(root,activity,current,reader=reader)

                self.assertEqual(report['status'],'unknown')
                expected=('native_wallet_transfer_snapshot_conflict' if kind=='same_snapshot_conflict'
                    else 'native_wallet_transfer_identity_invalid')
                self.assertIn(expected,report['reasons'])
                self.assertIsNone(report['net_pnl_usd']);self.assertFalse(report['capital_expansion_allowed'])

    def test_missing_quote_or_legacy_baseline_never_uses_cash_equity_or_current_value(self):
        for kind in ('missing_quote','legacy'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);_,activity,current=self.setup_cycle(root,legacy=kind=='legacy')
                if kind=='missing_quote':current['positions']=[]
                _,report=self.write(root,activity,current)
                self.assertEqual(report['status'],'unknown');self.assertTrue(report['reasons'])
                self.assertIsNone(report['account_delta']['USDC']);self.assertIsNone(report['net_pnl_usd'])

    def test_quote_precision_survives_decimal_context_and_replay(self):
        for precision in (8,28):
            with self.subTest(precision=precision),localcontext() as context,tempfile.TemporaryDirectory() as directory:
                context.prec=precision
                root=Path(directory);_,activity,current=self.setup_cycle(root,baseline_qty='100.00000000000000000000000000001')
                current['positions'][0]['qty']='100.50000000000000000000000000001'
                first,report=self.write(root,activity,current)
                _,again=self.write(root,activity,current,reader=lambda **_:self.fail('same clock must not read'))
                self.assertEqual(report,again);self.assertEqual(report['account_delta']['USDC'],'0.5')
                self.assertIsNone(first['fees_usd'])


if __name__=='__main__':unittest.main()
