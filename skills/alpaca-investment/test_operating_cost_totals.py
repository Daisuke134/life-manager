"""Full operating totals need scope proof and every owned paid obligation."""
import copy
from decimal import Decimal
import unittest
from paper_operating_costs import summarize,select_components
from test_operating_cost_inventory import setup,window_fixture


def report(payload,inventory,trip,mode='paper'):
    return summarize([trip],payload,owner_id=trip['owner_id'],mode=mode,observed_at=inventory['observed_at'],expected_inventory=inventory)


class OperatingCostTotalsTests(unittest.TestCase):
    def test_scope_proof_does_not_lose_paid_cost_to_whole_loop_gap(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode):
                payload,inventory,trip=window_fixture(mode)
                payload['readback']['historical']['complete']=False
                result=report(payload,inventory,trip,mode)
                self.assertEqual(Decimal(result['verified_model_cost_subtotal_usd']),Decimal('1'))
                self.assertEqual(result['model_cost_usd'],'1')
                self.assertEqual(result['system_cost_usd'],'0')
                self.assertEqual(result['operating_costs_status'],'complete')

    def test_final_no_charge_is_zero_but_missing_or_unverified_is_not(self):
        payload,inventory,trip=setup()
        result=report(payload,inventory,trip)
        self.assertEqual(result['model_cost_usd'],'0');self.assertEqual(result['system_cost_usd'],'0')
        self.assertEqual(result['operating_cost_components'],[])
        self.assertEqual(result['operating_cost_source_receipt_ids'],[])
        for value in (None,{'read_error':'missing'}):
            result=report(value,inventory,trip)
            self.assertIsNone(result['model_cost_usd']);self.assertIsNone(result['system_cost_usd'])
        inventory['gaps']=[{'reason':'history_coverage_unverified'}]
        self.assertIsNone(report(payload,inventory,trip)['model_cost_usd'])

    def test_missing_paid_binding_never_becomes_zero(self):
        payload,inventory,trip=window_fixture()
        allocation=payload['job_joins'].pop(0)
        self.assertEqual(payload['job_joins'][0]['join_type'],'scope_query')
        result=report(payload,inventory,trip)
        self.assertIsNone(result['model_cost_usd'])
        self.assertEqual(result['operating_cost_coverage']['coverage_state'],'gap')
        self.assertTrue(result['operating_cost_component_gaps'])
        payload['job_joins'].append(allocation)
        self.assertEqual(report(payload,inventory,trip)['model_cost_usd'],'1')

    def test_other_mode_binding_is_not_reassigned_and_unknown_context_is_not_free(self):
        payload,inventory,trip=window_fixture()
        allocation=payload['job_joins'][0]
        allocation.update(scope_id='other-scope',owner_id='alpaca-investment-live',mode='live',paper=False,order_ids=['other-entry','other-exit'])
        result=report(payload,inventory,trip)
        self.assertIsNone(result['model_cost_usd'])
        self.assertEqual(result['operating_cost_components'],[])
        self.assertTrue(result['operating_cost_component_gaps'])
        allocation.pop('owner_id')
        result=report(payload,inventory,trip)
        self.assertIsNone(result['model_cost_usd'])
        self.assertTrue(result['operating_cost_component_gaps'])

    def test_aliases_are_once_and_scoped_totals_survive_selection(self):
        payload,inventory,trip=window_fixture();other=copy.deepcopy(payload['documents'][0])
        other.update(document_type='paid_receipt',source_type='official_paid_receipt',receipt_id='alias')
        other['line_items'][0]['allocations'][0]['job_id']='alias-job'
        join=copy.deepcopy(payload['job_joins'][0]);join.update(document_type='paid_receipt',document_id='alias',job_id='alias-job')
        payload['documents'].append(other);payload['job_joins'].append(join)
        payload['sources'][0]['queries'][0]['document_ids'].append('alias')
        payload['provider_pagination']['pages'][0]['document_ids'].append('alias')
        result=report(payload,inventory,trip)
        self.assertEqual(result['model_cost_usd'],'1');self.assertEqual(len(result['operating_cost_components']),1)
        self.assertEqual(select_components(result,[trip])['model_cost_usd'],'1')
        self.assertIsNone(select_components(result,[])['model_cost_usd'])

if __name__=='__main__':unittest.main()
