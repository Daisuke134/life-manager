"""Performance uses the same native quantity conservation without double fees."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import crypto_performance as perf
import crypto_ownership_proof as proofs
import effect_store as store
from test_crypto_closing_fee import closing_fee_fixture,NOW
from test_crypto_fee_debit import debit_fixture
from test_crypto_fee_ledger import record_sell,write_rows
from test_crypto_performance import activity_fixture


def save_close(root,args,mode):
    proof=proofs.sell_remainder_proof_from_rows(store._rows(root/'receipts.jsonl'),args[0],args[1],args[2],
        mode=mode,owner_id=args[3],activity_readback=args[4])
    store.reconcile_started(root/'receipts.jsonl',lambda _:args[1],on_reconciled=lambda *_:proof)
    return proof


def complete_frame(root,base,mode):
    orders=[r['broker'] for r in store._rows(root/'receipts.jsonl') if r.get('receipt_type')=='outcome'
        and r.get('strategy_receipt') is not None]
    fills=[]
    for order in orders:
        known=[r for r in base['fills'] if r.get('order_id')==order['id']]
        if known:fills.extend(known)
        elif order['filled_qty']!='0':fills.append({'id':'fill-'+order['id'],'activity_type':'FILL',
            'order_id':order['id'],'symbol':'BTCUSDC','side':order['side'],'qty':order['filled_qty'],
            'price':order['filled_avg_price'],'transaction_time':order['filled_at']})
    end=max((r['strategy_receipt']['account_readback']['clock']['observed_at'] for r in store._rows(root/'receipts.jsonl')
        if isinstance(r.get('strategy_receipt'),dict)),key=proofs.parse_instant)
    frame=activity_fixture({'fills':fills,'fees':base['fees']},mode=mode,start=orders[0]['submitted_at'],end=end)
    return frame,{o['id']:frame for o in orders}


class CryptoFeePerformanceTests(unittest.TestCase):
    def build(self,root,mode,cache=None):
        return perf.build_crypto_performance(store._rows(root/'receipts.jsonl'),mode=mode,
            owner_id=f'alpaca-investment-{mode}',activity_readbacks=cache)

    def test_standalone_fee_before_full_sell_is_counted_once_in_native_cashflow_and_daily_writer(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);_,owned,frame,account=debit_fixture(root,mode)
                store.record_native_fee_debit(root/'receipts.jsonl',owned,account,activity_readback=frame,
                    mode=mode,owner_id=f'alpaca-investment-{mode}')
                owned['owned_qty']='0.049925'
                _,closed=record_sell(root,owned,frame,mode=mode,before='0.049925',qty='0.049925',remaining='0',
                    start='2026-01-02T04:05:00Z',partial=False)
                full,cache=complete_frame(root,frame,mode);result=self.build(root,mode,cache);cycle=result['cycles'][0]
                self.assertEqual(result['completed_round_trips'],1)
                self.assertEqual(cycle['post_acquisition_fee_debited_qty'],'0.000075')
                self.assertEqual(cycle['execution_cashflow_usdc'],'0.48425')
                self.assertEqual(cycle['closure_kind'],'sell');self.assertIsNone(result['net_pnl_usd'])
                calls=[]
                def read(**kwargs):
                    calls.append(kwargs)
                    return activity_fixture(full,mode=mode,start=kwargs['period_start'],end=kwargs['period_end'])
                written=perf.write_crypto_performance(root,closed,mode=mode,owner_id=f'alpaca-investment-{mode}',activity_reader=read)
                self.assertEqual(written['completed_round_trips'],1)
                count=len(calls);self.assertGreater(count,0)
                replay=perf.write_crypto_performance(root,closed,mode=mode,owner_id=f'alpaca-investment-{mode}',activity_reader=read)
                self.assertEqual(replay['completed_round_trips'],1);self.assertEqual(len(calls),count)
                self.assertTrue((root/'performance-crypto-daily-2026-01-02.json').exists())

    def test_fee_inside_partial_sell_and_later_full_sell_use_one_proven_cycle(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);args=closing_fee_fixture(root,mode);save_close(root,args,mode)
                owned={**args[0],'status':'open','owned_qty':'0.029925'}
                record_sell(root,owned,args[4],mode=mode,before='0.029925',qty='0.029925',remaining='0',
                    start='2026-01-01T04:20:00Z',partial=False)
                _,cache=complete_frame(root,args[4],mode);result=self.build(root,mode,cache);cycle=result['cycles'][0]
                self.assertEqual(result['completed_round_trips'],1);self.assertEqual(cycle['positive_sell_count'],2)
                self.assertEqual(cycle['post_acquisition_fee_debited_qty'],'0.000075')
                self.assertEqual(cycle['execution_cashflow_usdc'],'0.48425')
                self.assertEqual(len(result['fee_evidence']['attributed_native_fees']),1)

    def test_fee_only_flat_cycles_never_inflate_completed_round_trips(self):
        for mode in ('paper','live'):
            for zero_sell in (False,True):
                with self.subTest(mode=mode,zero_sell=zero_sell),tempfile.TemporaryDirectory() as directory:
                    root=Path(directory)
                    if zero_sell:
                        args=list(closing_fee_fixture(root,mode,sold='0',remaining='0'))
                        args[4]=activity_fixture(args[4],mode=mode,start=args[4]['requested_period_start'],end=NOW,
                            fees=[{**args[4]['fees'][0],'qty':'-0.05'}]);save_close(root,args,mode);frame=args[4]
                    else:
                        _,owned,frame,account=debit_fixture(root,mode)
                        frame=activity_fixture(frame,mode=mode,start=frame['requested_period_start'],end=frame['requested_period_end'],
                            fees=[{**frame['fees'][0],'qty':'-0.05'}]);account['positions']=[]
                        store.record_native_fee_debit(root/'receipts.jsonl',owned,account,activity_readback=frame,
                            mode=mode,owner_id=f'alpaca-investment-{mode}')
                    _,cache=complete_frame(root,frame,mode);result=self.build(root,mode,cache)
                    self.assertEqual(result['closed_cycle_count'],1);self.assertEqual(result['completed_round_trips'],0)
                    self.assertEqual(result['strategy_reports'][0]['completed_round_trips'],0)
                    cycle=result['cycles'][0]
                    self.assertEqual(cycle['positive_sell_count'],0);self.assertEqual(cycle['closure_kind'],'native_fee_debit')
                    self.assertEqual(cycle['execution_cashflow_usdc'],'-10');self.assertEqual(cycle['post_acquisition_fee_debited_qty'],'0.05')
                    self.assertTrue(cycle['closed_at']);self.assertIsNone(cycle['net_pnl_usd'])
                    self.assertFalse(result['capital_expansion_allowed'])

    def test_fee_after_partial_sell_can_close_the_position_without_another_sell(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);args=list(closing_fee_fixture(root,remaining='0.03'))
            args[4]=activity_fixture(args[4],mode='paper',start=args[4]['requested_period_start'],end=NOW,fees=[])
            save_close(root,args,'paper');owned={**args[0],'status':'open','owned_qty':'0.03'}
            fee={'id':'flat-after-partial','activity_type':'CFEE','order_id':args[4]['fills'][0]['order_id'],
                'symbol':'BTCUSD','qty':'-0.03','date':'2026-01-01','created_at':'2026-01-01T04:16:00Z','net_amount':'0','status':'executed'}
            late=activity_fixture(args[4],mode='paper',start=args[4]['requested_period_start'],end='2026-01-01T04:16:02Z',fees=[fee])
            account={**args[2],'positions':[],'clock':{'observed_at':'2026-01-01T04:16:02Z'}}
            store.record_native_fee_debit(root/'receipts.jsonl',owned,account,activity_readback=late,mode='paper',owner_id=args[3])
            _,cache=complete_frame(root,late,'paper');result=self.build(root,'paper',cache);cycle=result['cycles'][0]
            self.assertEqual(cycle['positive_sell_count'],1);self.assertEqual(result['completed_round_trips'],1)
            self.assertEqual(cycle['closure_kind'],'native_fee_debit');self.assertEqual(cycle['execution_cashflow_usdc'],'-5.8')
            self.assertEqual(cycle['post_acquisition_fee_debited_qty'],'0.03')

    def test_open_quantity_and_tamper_failures_use_the_same_fee_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,owned,frame,account=debit_fixture(root)
            store.record_native_fee_debit(root/'receipts.jsonl',owned,account,activity_readback=frame,
                mode='paper',owner_id='alpaca-investment-paper')
            result=self.build(root,'paper')
            self.assertEqual(result['open_entries'][0]['recorded_owned_qty'],'0.049925')
            self.assertEqual(result['completed_round_trips'],0)
            rows=store._rows(root/'receipts.jsonl');rows[-1]['strategy_receipt']['receipt']['debit_qty']='0.0001'
            write_rows(root/'receipts.jsonl',rows)
            with self.assertRaises(ValueError):self.build(root,'paper')

    def test_partial_sell_closed_by_next_day_fee_uses_the_flat_account_day(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);args=list(closing_fee_fixture(root,mode,remaining='0'))
                end='2026-01-02T00:00:02Z'
                args[2]={**args[2],'clock':{'observed_at':end}}
                args[4]=activity_fixture(args[4],mode=mode,start=args[4]['requested_period_start'],end=end,
                    fees=[{**args[4]['fees'][0],'qty':'-0.03','created_at':'2026-01-02T00:00:01Z'}])
                save_close(root,args,mode);frame,cache=complete_frame(root,args[4],mode)
                result=self.build(root,mode,cache);cycle=result['cycles'][0]
                self.assertEqual(proofs.parse_instant(cycle['closed_at']),proofs.parse_instant(end))
                self.assertEqual(cycle['closure_kind'],'sell_and_native_fee')
                def read(**kwargs):return activity_fixture(frame,mode=mode,start=kwargs['period_start'],end=kwargs['period_end'])
                report=perf.write_crypto_performance(root,args[2],mode=mode,owner_id=args[3],activity_reader=read)
                self.assertEqual(report['completed_round_trips'],1)
                self.assertTrue((root/'performance-crypto-daily-2026-01-02.json').exists())
                self.assertFalse((root/'performance-crypto-daily-2026-01-01.json').exists())
