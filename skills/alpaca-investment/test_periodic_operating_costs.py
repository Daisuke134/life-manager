"""Paid fixed service costs need explicit attribution, never guessed daily proration."""
import copy
from decimal import Decimal
import unittest
from paper_operating_costs import summarize,select_components
from test_operating_cost_inventory import setup


def fixture(mode='paper',short_run=True):
    payload,inventory,scope=setup(mode,orders=[],paid=True)
    line=payload['documents'][0]['line_items'][0]
    period={key:scope[key] for key in ('period_start','period_end')}
    line.update(service_period_start=period['period_start'],service_period_end=period['period_end'])
    payload['job_joins'][0].update(attribution_basis='service_period',
        service_period_start=period['period_start'],service_period_end=period['period_end'])
    if short_run:inventory['scopes'][0]['execution_refs'][0]['finished_at']='2026-09-24T00:01:00Z'
    return payload,inventory,scope


def report(payload,inventory,scope,mode='paper'):
    return summarize([scope],payload,owner_id=scope['owner_id'],mode=mode,
        observed_at=inventory['observed_at'],expected_inventory=inventory)


class PeriodicOperatingCostsTests(unittest.TestCase):
    def test_paid_full_service_period_does_not_require_cost_to_occur_during_a_run(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode):
                payload,inventory,scope=fixture(mode);before=copy.deepcopy((payload,inventory,scope))
                value=report(payload,inventory,scope,mode)
                self.assertIsNotNone(value['model_cost_usd'])
                self.assertEqual(Decimal(value['model_cost_usd']),Decimal('1'))
                self.assertEqual(value['operating_costs_status'],'complete')
                self.assertEqual(value['operating_cost_components'][0]['attribution_basis'],'verified_service_period')
                self.assertEqual(value['operating_cost_components'][0]['order_ids'],[])
                self.assertEqual(select_components(value,[scope]),value)
                self.assertEqual((payload,inventory,scope),before)

    def test_service_metadata_never_falls_back_to_execution_time_attribution(self):
        for broken in ('missing_basis','missing_line_start','wrong_join_end','reverse_period','order_pair'):
            with self.subTest(broken=broken):
                payload,inventory,scope=fixture(short_run=False)
                line=payload['documents'][0]['line_items'][0];join=payload['job_joins'][0]
                if broken=='missing_basis':join.pop('attribution_basis')
                elif broken=='missing_line_start':line.pop('service_period_start')
                elif broken=='wrong_join_end':join['service_period_end']='2026-09-29T00:00:00Z'
                elif broken=='reverse_period':line['service_period_end']=line['service_period_start']
                else:
                    scope.update(scope_kind='order_pair',order_ids=['entry','exit'])
                    payload['readback']['cost_scopes'][0].update(scope)
                    inventory['scopes'][0].update(scope)
                    join.update(scope)
                value=report(payload,inventory,scope)
                self.assertIsNone(value['model_cost_usd'])
                self.assertTrue(value['operating_cost_component_gaps'])

    def test_partial_period_cannot_be_zero_or_the_full_monthly_charge(self):
        for mode in ('paper','live'):
            for paid in (True,False):
                with self.subTest(mode=mode,paid=paid):
                    payload,inventory,monthly=fixture(mode)
                    day=copy.deepcopy(monthly);day.update(scope_id='day-scope',period_end='2026-09-25T00:00:00Z')
                    payload['readback']['cost_scopes'].append(day)
                    query=copy.deepcopy(payload['sources'][0]['queries'][0])
                    query.update(query_id='day-query',scope_id='day-scope',settlement_state='no_charge_final',document_ids=[])
                    payload['sources'][0]['queries'].append(query)
                    page=copy.deepcopy(payload['provider_pagination']['pages'][0]);page.update(query_id='day-query',document_ids=[])
                    payload['provider_pagination']['pages'].append(page)
                    join=copy.deepcopy(payload['job_joins'][0]);join.update(day,query_id='day-query',join_type='scope_query',job_id=None)
                    payload['job_joins'].append(join)
                    inv=copy.deepcopy(inventory['scopes'][0]);inv.update(day);inventory['scopes'].append(inv)
                    if not paid:payload['documents'][0]['status']='unpaid'
                    value=report(payload,inventory,day,mode)
                    self.assertIsNone(value['model_cost_usd'])
                    self.assertEqual(value['operating_cost_coverage']['coverage_state'],'gap')
                    self.assertTrue(value['operating_cost_component_gaps'])
                    self.assertEqual(value['operating_cost_components'],[])

    def test_missing_final_query_or_unpaid_service_never_becomes_confirmed(self):
        for broken in ('query','unpaid','account','mode'):
            with self.subTest(broken=broken):
                payload,inventory,scope=fixture()
                if broken=='query':payload['sources'][0]['queries']=[]
                elif broken=='unpaid':payload['documents'][0]['status']='unpaid'
                elif broken=='account':payload['documents'][0]['billing_account_ref']='other-account'
                else:payload['job_joins'][0].update(mode='live',paper=False,owner_id='alpaca-investment-live')
                value=report(payload,inventory,scope)
                self.assertIsNone(value['model_cost_usd'])
                self.assertEqual(value['operating_cost_components'],[])

if __name__=='__main__':unittest.main()
