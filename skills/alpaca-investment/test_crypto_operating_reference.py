"""Known cycle costs adjust reference cashflow without proving settled profit."""
import copy
import json
import os
from decimal import localcontext
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import crypto_performance as perf
from paper_operating_costs import summarize
from test_operating_cost_inventory import window_fixture
from test_crypto_fx_performance import value
from test_crypto_fx_performance import quote
from test_crypto_fx_quote import seal
from test_crypto_performance import cycle_fixture, activity_fixture
from skills.cfo.test_actual_cost_inventory import fixture as billing_fixture
import effect_store as store


FIELD = 'cashflow_after_observed_fees_and_scoped_operating_costs_usd'


def fixture(mode='paper'):
    payload, inventory, trip = window_fixture(mode)
    costs = summarize([trip], payload, owner_id=trip['owner_id'], mode=mode,
        observed_at=inventory['observed_at'], expected_inventory=inventory)
    cycle = {**trip, 'cycle_id':'cycle-1', 'strategy_id':'strategy-1', 'release_sha':'a'*40,
        'positive_sell_count':1, 'execution_cashflow_usdc':'0.5',
        'fx_reference':{'measurement_status':'reference_only', 'cash_conversion_proven':False,
            'cashflow_after_observed_quote_fees_usd':perf._reference_amount(Fraction('0.48'))}}
    return cycle, costs


class CryptoOperatingReferenceTests(unittest.TestCase):
    def test_builder_and_writer_use_final_costs_and_persist_daily_reference(self):
        observed='2026-01-02T00:00:03Z';billing_at='2026-01-02T00:00:02Z'
        for mode in ('paper', 'live'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);orders,frame,_=cycle_fixture(root,mode)
                fee={'id':'quote-fee','activity_type':'CFEE','order_id':orders[1]['id'],'symbol':'USDCUSD',
                    'qty':'-0.1','date':'2026-01-01','created_at':'2026-01-01T05:00:00Z','net_amount':'0','status':'executed'}
                frame=activity_fixture(frame,mode=mode,start=frame['requested_period_start'],end=frame['requested_period_end'],fees=[fee])
                rows=store._rows(root/'receipts.jsonl');owner='alpaca-investment-'+mode
                activity={o['id']:frame for o in orders}
                cycle=perf.build_crypto_performance(rows,mode=mode,owner_id=owner,activity_readbacks=activity)['cycles'][0]
                payload,inventory=billing_fixture(mode);scope=payload['readback']['cost_scopes'][0]
                scope.update(order_ids=cycle['order_ids'],period_start=cycle['period_start'],period_end=cycle['closed_at'],source_receipt_ids=cycle['source_receipt_ids'])
                payload['job_joins'][0].update(scope)
                payload['readback'].update(observed_at=billing_at,historical={'complete':True,'window_start':None,'window_end':billing_at},
                    trailing={'complete':True,'window_start':cycle['period_start'],'window_end':billing_at})
                payload['sources'][0]['queries'][0].update(window_start=cycle['period_start'],window_end=billing_at,observed_at=billing_at,finalized_through=billing_at)
                inventory['scopes'][0].update({k:copy.deepcopy(scope[k]) for k in ('order_ids','period_start','period_end','source_receipt_ids')})
                for ref in inventory['scopes'][0]['execution_refs']:ref.update(started_at=cycle['period_start'],finished_at=cycle['closed_at'])
                inventory['observed_at']=observed
                inventory['input_reads'][owner]['runtime'].update(first_event_at=cycle['period_start'],last_event_at=observed)
                fx={f['transaction_time']:quote(f['transaction_time'],mode) for f in frame['fills']}
                direct=perf.build_crypto_performance(rows,mode=mode,owner_id=owner,activity_readbacks=activity,fx_readbacks=fx,
                    operating_cost_readback=payload,observed_at=observed,expected_inventory=inventory)
                self.assertEqual(value(direct[FIELD]),Fraction('0.4'))
                path=root/'billing.json';path.write_text(json.dumps(payload))
                def read(**kw):return activity_fixture(frame,mode=mode,start=kw['period_start'],end=kw['period_end'],fees=[fee])
                def read_fx(**kw):
                    snapshot=copy.deepcopy(fx[kw['asof_at']]);snapshot['observed_at']=kw['observed_at']
                    return seal(snapshot)
                with patch.dict(os.environ,{'LM_CFO_ACTUAL_COST_READBACK':str(path),'LM_CFO_ACTUAL_COST':''}), \
                     patch.object(perf,'read_expected_inventory',return_value=inventory):
                    report=perf.write_crypto_performance(root,{'mode':mode,'paper':mode=='paper','clock':{'observed_at':observed}},
                        mode=mode,owner_id=owner,activity_reader=read,fx_reader=read_fx)
                daily=json.loads((root/'performance-crypto-daily-2026-01-01.json').read_text())
                for result in (report,daily):
                    self.assertEqual(value(result[FIELD]),Fraction('0.4'))
                    self.assertEqual(value(result['strategy_reports'][0][FIELD]),Fraction('0.4'))
                    self.assertEqual(value(result['cycles'][0]['fx_reference'][FIELD]),Fraction('0.4'))
                    self.assertIsNone(result['net_pnl_usd']);self.assertFalse(result['capital_expansion_allowed'])

    def test_exact_paid_cost_is_deducted_once_and_remains_reference_only(self):
        for mode in ('paper', 'live'):
            with self.subTest(mode=mode):
                cycle, costs = fixture(mode)
                self.assertEqual(costs['model_cost_usd'], '1')
                original = copy.deepcopy(costs)
                with localcontext() as context:
                    context.prec = 2
                    for signal in context.traps: context.traps[signal] = True
                    perf._operating_references([cycle], costs)
                    perf._operating_references([cycle], costs)
                ref = cycle['fx_reference']
                self.assertEqual(value(ref[FIELD]), Fraction('-0.52'))
                self.assertEqual(ref['scoped_model_cost_usd'], '1')
                self.assertEqual(ref['scoped_system_cost_usd'], '0')
                self.assertFalse(ref['cash_conversion_proven'])
                self.assertEqual(ref['measurement_status'], 'reference_only')
                self.assertEqual(costs, original)

    def test_missing_fx_quote_fee_or_scoped_coverage_never_becomes_zero(self):
        for case in ('fx_or_fee', 'coverage', 'different_scope'):
            with self.subTest(case=case):
                cycle, costs = fixture()
                if case == 'fx_or_fee':
                    cycle['fx_reference']['cashflow_after_observed_quote_fees_usd'] = None
                elif case == 'coverage':
                    costs['operating_cost_scope_coverages'][0]['coverage_state'] = 'gap'
                else:
                    cycle['order_ids'] = ['other-entry', 'other-exit']
                perf._operating_references([cycle], costs)
                self.assertIsNone(cycle['fx_reference'][FIELD])
                self.assertIsNone(perf._summary([cycle])[FIELD])

    def test_strategy_and_day_selection_aggregate_only_their_own_cycles(self):
        first, costs = fixture()
        second = copy.deepcopy(first)
        second.update(cycle_id='cycle-2', strategy_id='strategy-2')
        perf._operating_references([first], costs)
        second['fx_reference'][FIELD] = perf._reference_amount(Fraction('0.25'))
        both = perf._summary([first, second])
        self.assertEqual(value(both[FIELD]), Fraction('-0.27'))
        self.assertEqual([value(r[FIELD]) for r in both['strategy_reports']],
            [Fraction('-0.52'), Fraction('0.25')])
        self.assertEqual(value(perf._summary([second])[FIELD]), Fraction('0.25'))
        self.assertIsNone(perf._summary([])[FIELD])
        second['fx_reference'][FIELD] = None
        self.assertIsNone(perf._summary([first, second])[FIELD])


if __name__ == '__main__': unittest.main()
