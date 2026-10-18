"""Only complete independent scope proof propagates; monetary totals stay unknown."""
from decimal import Decimal
import unittest
from paper_operating_costs import summarize,select_components
from skills.cfo.test_actual_cost_inventory import fixture
from skills.cfo.test_actual_cost_attribution import SNAPSHOT,TRAILING_START


def setup(mode='paper',orders=None,paid=False):
    payload,inventory=fixture(mode,orders,paid)
    payload['readback'].update(historical={'complete':True,'window_start':None,'window_end':SNAPSHOT},
        trailing={'complete':True,'window_start':TRAILING_START,'window_end':SNAPSHOT})
    scope=payload['readback']['cost_scopes'][0]
    trip={**scope}
    if scope.get('scope_kind','order_pair')=='order_pair':trip['closed_at']=trip.pop('period_end')
    inventory['observed_at']='2026-10-01T00:00:01Z'
    return payload,inventory,trip


class OperatingCostInventoryTests(unittest.TestCase):
    def test_source_coverage_reaches_summary_without_creating_zero_money(self):
        for mode in ('paper','live'):
            for orders in (['entry','exit'],['entry','partial','exit'],[]):
                with self.subTest(mode=mode,orders=orders):
                    payload,inventory,trip=setup(mode,orders)
                    result=summarize([trip],payload,owner_id=trip['owner_id'],mode=mode,
                        observed_at=inventory['observed_at'],expected_inventory=inventory)
                    self.assertEqual(result['operating_cost_coverage']['coverage_state'],'complete')
                    self.assertEqual(len(result['operating_cost_scope_coverages']),1)
                    self.assertIsNone(result['verified_model_cost_subtotal_usd'])
                    self.assertIsNone(result['verified_system_cost_subtotal_usd'])
                    self.assertEqual(result['operating_cost_components'],[])
                    self.assertNotIn('net_pnl_usd',result)

    def test_paid_component_retains_account_and_uses_the_existing_charge_identity(self):
        payload,inventory,trip=setup(paid=True)
        result=summarize([trip],payload,owner_id=trip['owner_id'],observed_at=inventory['observed_at'],expected_inventory=inventory)
        self.assertEqual(result['operating_cost_coverage']['coverage_state'],'complete')
        self.assertEqual(Decimal(result['verified_model_cost_subtotal_usd']),Decimal('1'))
        component=result['operating_cost_components'][0]
        self.assertEqual(component['billing_account_ref'],'billing-account')
        self.assertEqual(component['charge_identity'],['openai','invoice','same-id','line','allocation'])
        self.assertNotIn('model_cost_usd',result)

    def test_scope_selector_uses_period_as_well_as_order_group_including_idle_periods(self):
        payload,inventory,trip=setup(orders=[])
        result=summarize([trip],payload,owner_id=trip['owner_id'],observed_at=inventory['observed_at'],expected_inventory=inventory)
        original=result['operating_cost_scope_coverages'][0]
        other={**original,'scope_id':'other','period_start':'2026-09-30T00:00:00Z','period_end':SNAPSHOT,
            'coverage_state':'gap','reason':'query_missing'}
        result['operating_cost_scope_coverages'].append(other)
        selected=select_components(result,[trip])
        self.assertEqual(selected['operating_cost_scope_coverages'],[original])
        self.assertEqual(selected['operating_cost_coverage']['coverage_state'],'complete')
        self.assertEqual(select_components(result,[trip,other])['operating_cost_coverage']['coverage_state'],'gap')
        self.assertEqual(select_components(result,[])['operating_cost_coverage']['coverage_state'],'gap')

    def test_crypto_writer_and_daily_forward_exact_native_group_to_scope_coverage(self):
        import copy,json,os,tempfile
        from pathlib import Path
        from unittest.mock import patch
        import crypto_performance as crypto
        import effect_store as store
        from test_crypto_performance import cycle_fixture,activity_fixture
        observed='2026-01-02T00:00:03Z';billing_at='2026-01-02T00:00:02Z'
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);orders,frame,_=cycle_fixture(root,mode,partial=True)
                built=crypto.build_crypto_performance(store._rows(root/'receipts.jsonl'),
                    mode=mode,owner_id='alpaca-investment-'+mode,activity_readbacks={o['id']:frame for o in orders})
                cycle=built['cycles'][0];payload,inventory=fixture(mode)
                scope=payload['readback']['cost_scopes'][0]
                scope.update(order_ids=cycle['order_ids'],period_start=cycle['period_start'],period_end=cycle['closed_at'],
                    source_receipt_ids=cycle['source_receipt_ids'])
                payload['job_joins'][0].update(scope)
                payload['readback'].update(observed_at=billing_at,
                    historical={'complete':True,'window_start':None,'window_end':billing_at},
                    trailing={'complete':True,'window_start':cycle['period_start'],'window_end':billing_at})
                payload['sources'][0]['queries'][0].update(window_start=cycle['period_start'],window_end=billing_at,
                    observed_at=billing_at,finalized_through=billing_at)
                trusted=inventory['scopes'][0]
                trusted.update({k:copy.deepcopy(scope[k]) for k in ('order_ids','period_start','period_end','source_receipt_ids')})
                inventory['observed_at']=observed
                runtime=inventory['input_reads']['alpaca-investment-'+mode]['runtime']
                runtime.update(first_event_at=cycle['period_start'],last_event_at=observed)
                billing=root/'billing.json';billing.write_text(json.dumps(payload))
                def read(**kw):return activity_fixture(frame,mode=mode,start=kw['period_start'],end=kw['period_end'])
                with patch.dict(os.environ,{'LM_CFO_ACTUAL_COST_READBACK':str(billing),'LM_CFO_ACTUAL_COST':''}), \
                     patch.object(crypto,'read_expected_inventory',return_value=inventory) as producer:
                    result=crypto.write_crypto_performance(root,{'mode':mode,'paper':mode=='paper','clock':{'observed_at':observed}},
                        mode=mode,owner_id='alpaca-investment-'+mode,activity_reader=read)
                self.assertEqual(result['operating_cost_coverage']['coverage_state'],'complete')
                self.assertNotIn('period_end',producer.call_args.args[1][0])
                self.assertEqual(producer.call_args.args[1][0]['closed_at'],cycle['closed_at'])
                daily=json.loads((root/'performance-crypto-daily-2026-01-01.json').read_text())
                self.assertEqual(daily['operating_cost_coverage']['coverage_state'],'complete')
                self.assertEqual(result['operating_cost_source_receipt_ids'],[])
                self.assertIsNone(result['net_pnl_usd']);self.assertIsNone(result['model_cost_usd'])
                self.assertFalse(result['capital_expansion_allowed'])

if __name__=='__main__':unittest.main()
