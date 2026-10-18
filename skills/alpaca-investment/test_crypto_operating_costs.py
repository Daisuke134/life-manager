"""Known paid components are cycle/mode scoped, never complete net profit."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import crypto_performance as perf
import effect_store as store
from test_crypto_performance import cycle_fixture,activity_fixture
from test_paper_operating_costs import _readback

OBSERVED='2026-01-02T00:00:03Z'


def billing(cycle,mode):
    payload=_readback();doc=payload['documents'][0]
    doc.update(billing_period_start='2026-01-01T00:00:00Z',billing_period_end='2026-01-02T00:00:00Z',paid_at='2026-01-02T00:00:01Z')
    rb=payload['readback'];rb['observed_at']='2026-01-02T00:00:02Z'
    for key in ('historical','trailing'):
        rb[key].update(window_start='2026-01-01T00:00:00Z',window_end=rb['observed_at'])
    rb['historical']['window_start']=None
    for line in doc['line_items']:line['occurred_at']=cycle['closed_at']
    for join in payload['job_joins']:
        join.update(owner_id='alpaca-investment-'+mode,mode=mode,paper=mode=='paper',order_ids=cycle['order_ids'],
            period_start=cycle['period_start'],period_end=cycle['closed_at'],source_receipt_ids=cycle['source_receipt_ids'])
    return payload


class CryptoOperatingCostTests(unittest.TestCase):
    def build(self,root,mode,frame,payload=None):
        return perf.build_crypto_performance(store._rows(root/'receipts.jsonl'),mode=mode,owner_id='alpaca-investment-'+mode,
            activity_readbacks={f['order_id']:frame for f in frame['fills']},operating_cost_readback=payload,observed_at=OBSERVED)

    def test_exact_cycle_scoped_paid_subtotals_reuse_adapter_in_both_modes(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);_,frame,_=cycle_fixture(root,mode,partial=True)
                cycle=self.build(root,mode,frame)['cycles'][0];payload=billing(cycle,mode);original=copy.deepcopy(payload)
                result=self.build(root,mode,frame,payload)
                self.assertEqual(result['verified_model_cost_subtotal_usd'],'0.01')
                self.assertEqual(result['verified_system_cost_subtotal_usd'],'0.09')
                self.assertEqual(len(result['operating_cost_components']),4)
                self.assertEqual(result['operating_cost_coverage']['coverage_state'],'gap')
                self.assertIsNone(result['net_pnl_usd']);self.assertIsNone(result['model_cost_usd'])
                self.assertFalse(result['capital_expansion_allowed']);self.assertEqual(payload,original)
                self.assertEqual(set(cycle['source_receipt_ids']),{f['id'] for f in frame['fills']}|set(cycle['order_ids']))

    def test_foreign_scope_is_not_reassigned_to_the_requested_beneficiary(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,frame,_=cycle_fixture(root,'live');cycle=self.build(root,'live',frame)['cycles'][0]
            payload=billing(cycle,'live')
            for key,value in (('owner_id','alpaca-investment-paper'),('mode','paper'),('paper',True),('order_ids',['foreign','orders'])):
                changed=copy.deepcopy(payload)
                for join in changed['job_joins']:join[key]=value
                result=self.build(root,'live',frame,changed)
                self.assertIsNone(result['verified_model_cost_subtotal_usd']);self.assertEqual(result['operating_cost_components'],[])

    def test_components_are_selected_by_exact_closed_order_group(self):
        from paper_operating_costs import select_components
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,first,_=cycle_fixture(root);_,second,_=cycle_fixture(root,index=1,partial=True)
            frame=activity_fixture({'fills':first['fills']+second['fills'],'fees':[]},mode='paper',
                start=first['requested_period_start'],end=first['requested_period_end'])
            cycles=self.build(root,'paper',frame)['cycles'];payload=billing(cycles[0],'paper');other=billing(cycles[1],'paper')
            other['documents'][0]['invoice_id']='invoice-other'
            for join in other['job_joins']:
                join['document_id']='invoice-other';join['job_id']='other-'+join['job_id']
            for line in other['documents'][0]['line_items']:
                for allocation in line['allocations']:allocation['job_id']='other-'+allocation['job_id']
            payload['documents']+=other['documents'];payload['job_joins']+=other['job_joins']
            result=self.build(root,'paper',frame,payload)
            self.assertEqual(result['verified_model_cost_subtotal_usd'],'0.02')
            subset=select_components(result,[cycles[1]])
            self.assertEqual(subset['verified_system_cost_subtotal_usd'],'0.09')
            self.assertTrue(all(c['order_ids']==cycles[1]['order_ids'] for c in subset['operating_cost_components']))

    def test_writer_and_daily_keep_known_paid_components_when_input_disappears_or_regresses(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,frame,_=cycle_fixture(root);cycle=self.build(root,'paper',frame)['cycles'][0]
            path=root/'billing.json';path.write_text(json.dumps(billing(cycle,'paper')))
            observation={'mode':'paper','paper':True,'clock':{'observed_at':OBSERVED}}
            def read(**kw):return activity_fixture(frame,mode='paper',start=kw['period_start'],end=kw['period_end'])
            def write():return perf.write_crypto_performance(root,observation,mode='paper',owner_id='alpaca-investment-paper',activity_reader=read)
            with patch.dict(os.environ,{'LM_CFO_ACTUAL_COST_READBACK':str(path),'LM_CFO_ACTUAL_COST':''}):
                first=write();self.assertEqual(first['verified_model_cost_subtotal_usd'],'0.01')
                path.unlink();missing=write();self.assertEqual(missing['operating_cost_components'],first['operating_cost_components'])
                regressed=billing(cycle,'paper');regressed['job_joins']=[];path.write_text(json.dumps(regressed))
                result=write();self.assertEqual(result['operating_cost_components'],first['operating_cost_components'])
                self.assertEqual(result['operating_costs_reason'],'crypto_operating_cost_history_missing')
                daily=json.loads((root/'performance-crypto-daily-2026-01-01.json').read_text())
                self.assertEqual(daily['verified_model_cost_subtotal_usd'],'0.01')
                self.assertIsNone(result['net_pnl_usd'])

if __name__=='__main__':unittest.main()
