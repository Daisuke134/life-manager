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

if __name__=='__main__':unittest.main()
