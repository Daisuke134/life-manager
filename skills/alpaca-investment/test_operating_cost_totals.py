"""Full operating totals need scope proof and every owned paid obligation."""
import copy
from decimal import Decimal
import unittest
from paper_operating_costs import summarize,select_components
from test_operating_cost_inventory import setup,window_fixture


def report(payload,inventory,trip,mode='paper'):
    return summarize([trip],payload,owner_id=trip['owner_id'],mode=mode,observed_at=inventory['observed_at'],expected_inventory=inventory)


def calendar_fixture(mode="paper"):
    payload,inventory,child=window_fixture(mode)
    owner=child['owner_id'];parent=copy.deepcopy(payload['readback']['cost_scopes'][0])
    parent.update(scope_id='calendar-scope',scope_kind='owner_period',order_ids=[],period_end='2026-10-01T00:00:00Z')
    payload['readback']['cost_scopes'].append(parent)
    query=copy.deepcopy(payload['sources'][0]['queries'][0]);query.update(query_id='calendar-query',scope_id='calendar-scope')
    payload['sources'][0]['queries'].append(query)
    page=copy.deepcopy(payload['provider_pagination']['pages'][0]);page['query_id']='calendar-query'
    payload['provider_pagination']['pages'].append(page)
    join=copy.deepcopy(payload['job_joins'][1]);join.update(parent,query_id='calendar-query')
    payload['job_joins'].append(join)
    scope=copy.deepcopy(inventory['scopes'][0]);scope.update({k:parent[k] for k in ('scope_kind','order_ids','period_start','period_end','source_receipt_ids')})
    inventory['scopes'].append(scope)
    return payload,inventory,child,parent


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

    def test_paid_or_unpaid_owned_document_with_unknown_account_does_not_hitchhike_on_zero_query(self):
        for status in ('paid','unpaid'):
            with self.subTest(status=status):
                payload,inventory,trip=setup()
                paid,_,_=setup(paid=True);doc=paid['documents'][0];doc.pop('billing_account_ref');doc['status']=status
                join=paid['job_joins'][0]
                for key in ('query_id','scope_id','join_type','execution_refs','run_ids','occurrence_ids'):join.pop(key,None)
                payload['documents']=[doc];payload['job_joins'].append(join)
                result=report(payload,inventory,trip)
                self.assertIsNone(result['model_cost_usd'])
                self.assertEqual(result['operating_cost_coverage']['coverage_state'],'gap')
                self.assertTrue(result['operating_cost_component_gaps'])
                if status=='paid':self.assertEqual(Decimal(result['verified_model_cost_subtotal_usd']),Decimal('1'))

    def test_paper_build_preserves_confirmed_operating_totals_and_remaining_unknowns(self):
        from unittest.mock import patch
        import paper_performance as paper
        from test_paper_performance import _rows,OBSERVATION,RISK
        base=summarize([],None,owner_id='alpaca-investment-paper',observed_at=OBSERVATION['clock']['observed_at'])
        confirmed={**base,'model_cost_usd':'1','system_cost_usd':'2','operating_costs_status':'complete',
            'operating_cost_coverage':{'coverage_state':'complete','reason':None}}
        with patch.object(paper,'summarize_operating_costs',return_value=confirmed):
            result=paper.build_paper_performance(_rows(),OBSERVATION,RISK)
        self.assertEqual(result['model_cost_usd'],'1');self.assertEqual(result['system_cost_usd'],'2')
        self.assertNotIn('model',result['unknown_cost_categories']);self.assertNotIn('system',result['unknown_cost_categories'])
        self.assertIn('fees',result['unknown_cost_categories']);self.assertIsNone(result['net_realized_pnl_usd'])
        self.assertEqual(result['measurement_status'],'partial')

    def test_durable_binding_rejection_and_identity_conflict_do_not_become_zero(self):
        import json,tempfile
        from pathlib import Path
        from paper_performance import _bind_operating_costs
        payload,inventory,current=window_fixture()
        confirmed=report(payload,inventory,current)
        old=copy.deepcopy(current)
        old.update(order_ids=['old-entry','old-exit'],period_start='2026-09-27T00:00:00Z',
            closed_at='2026-09-28T00:00:00Z',source_receipt_ids=['old-trade-receipt'])
        prior=copy.deepcopy(confirmed['operating_cost_components'][0])
        prior.update(order_ids=old['order_ids'],period_start=old['period_start'],period_end=old['closed_at'])
        for conflict in (False,True):
            with self.subTest(conflict=conflict),tempfile.TemporaryDirectory() as directory:
                state=Path(directory);incoming=copy.deepcopy(confirmed)
                if conflict:
                    duplicate=copy.deepcopy(incoming['operating_cost_components'][0]);duplicate['amount_usd']='2'
                    incoming['operating_cost_components'].append(duplicate)
                else:
                    (state/'performance-daily-2026-09-28.json').write_text(json.dumps({
                        'mode':'paper','paper':True,'performance_day':'2026-09-28',
                        'report_scope':'daily_accumulation','observed_at':'2026-09-28T00:01:00Z',
                        'source_receipt_ids':['old-trade-receipt',prior['receipt_id']],
                        'operating_cost_components':[prior]}))
                bound,_=_bind_operating_costs(state,[old,current],incoming)
                day=select_components(bound,[current])
                self.assertIsNone(day['model_cost_usd'])
                self.assertEqual(day['operating_cost_coverage']['coverage_state'],'gap')
                self.assertTrue(day['operating_cost_component_gaps'])

    def test_historical_refresh_removes_only_confirmed_unknown_categories(self):
        import json,tempfile
        from pathlib import Path
        from paper_performance import build_paper_performance,_closed_round_trips,_refresh_historical_costs
        from test_paper_performance import _rows,OBSERVATION,RISK
        trips,_=_closed_round_trips(_rows())
        previous=build_paper_performance(_rows(),OBSERVATION,RISK)
        previous.update(report_scope='daily_accumulation',performance_day='2026-10-20',risk=RISK)
        previous['source_receipt_ids'].append('alpaca-account-readback:'+previous['observed_at'])
        summary=summarize([],None,owner_id='alpaca-investment-paper',observed_at=OBSERVATION['clock']['observed_at'])
        summary['operating_cost_scope_coverages']=[{'order_ids':t['order_ids'],'period_start':t['period_start'],
            'period_end':t['closed_at'],'coverage_state':'complete'} for t in trips]
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory);path=state/'performance-daily-2026-10-20.json'
            path.write_text(json.dumps(previous))
            _refresh_historical_costs(state,trips,[],'2026-10-21',summary)
            saved=json.loads(path.read_text())
            self.assertEqual(saved['model_cost_usd'],'0');self.assertEqual(saved['system_cost_usd'],'0')
            self.assertNotIn('model',saved['unknown_cost_categories'])
            self.assertNotIn('system',saved['unknown_cost_categories'])
            self.assertIn('fees',saved['unknown_cost_categories'])
            self.assertIsNone(saved['net_realized_pnl_usd'])
            self.assertEqual(_refresh_historical_costs(state,trips,[],'2026-10-21',summary)[0]['status'],'unchanged')

    def test_exact_totals_do_not_round_tiny_paid_amount_beside_large_amount(self):
        from decimal import localcontext
        payload,inventory,trip=window_fixture()
        first=payload['documents'][0]['line_items'][0]
        first['amount']=first['allocations'][0]['amount']='9999.99'
        extra=copy.deepcopy(first);extra.update(line_item_id='tiny-line',amount='0.00000001')
        extra['allocations'][0].update(allocation_id='tiny-allocation',job_id='tiny-job',amount='0.00000001')
        payload['documents'][0]['line_items'].append(extra)
        join=copy.deepcopy(payload['job_joins'][0]);join.update(line_item_id='tiny-line',allocation_id='tiny-allocation',job_id='tiny-job')
        payload['job_joins'].append(join)
        with localcontext() as context:
            context.prec=1
            for signal in context.traps:context.traps[signal]=True
            result=report(payload,inventory,trip)
        self.assertEqual(result['model_cost_usd'],'9999.99000001')

    def test_calendar_view_includes_verified_child_once_without_rebinding(self):
        payload,inventory,child,parent=calendar_fixture()
        owner=child["owner_id"]
        result=summarize([child,parent],payload,owner_id=owner,observed_at=inventory['observed_at'],expected_inventory=inventory)
        calendar=select_components(result,[parent])
        self.assertEqual(calendar['model_cost_usd'],'1')
        self.assertEqual(calendar['operating_cost_coverage']['coverage_state'],'complete')
        self.assertEqual(calendar['operating_cost_components'][0]['order_ids'],child['order_ids'])
        self.assertEqual(result['model_cost_usd'],'1')
        alone=summarize([parent],payload,owner_id=owner,observed_at=inventory['observed_at'],expected_inventory=inventory)
        self.assertEqual(alone['model_cost_usd'],'1')
        self.assertEqual(alone['operating_cost_components'][0]['order_ids'],child['order_ids'])
        self.assertEqual(select_components(alone,[parent])['model_cost_usd'],'1')
        self.assertEqual(select_components(result,[child])['model_cost_usd'],'1')

    def test_calendar_rollup_requires_parent_and_child_proof_and_ignores_other_modes(self):
        for mode in ('paper','live'):
            for broken in ('parent_query','child_join','foreign_mode','foreign_account'):
                with self.subTest(mode=mode,broken=broken):
                    payload,inventory,child,parent=calendar_fixture(mode)
                    if broken=='parent_query':payload['sources'][0]['queries'].pop()
                    elif broken=='child_join':payload['job_joins'].pop(0)
                    elif broken=='foreign_mode':
                        payload['job_joins'][0].update(owner_id='alpaca-investment-'+('live' if mode=='paper' else 'paper'),mode='live' if mode=='paper' else 'paper',paper=mode!='paper')
                    else:payload['documents'][0]['billing_account_ref']='foreign-account'
                    value=summarize([parent],payload,owner_id=child['owner_id'],mode=mode,
                        observed_at=inventory['observed_at'],expected_inventory=inventory)
                    self.assertIsNone(value['model_cost_usd'])
                    self.assertEqual(value['operating_cost_coverage']['coverage_state'],'gap')

    def test_parent_zero_query_cannot_hide_unverified_owned_child_cost(self):
        for mode in ('paper','live'):
            for unpaid in (False,True):
                for only_parent in (False,True):
                    with self.subTest(mode=mode,unpaid=unpaid,only_parent=only_parent):
                        payload,inventory,child,parent=calendar_fixture(mode)
                        payload['sources'][0]['queries'][-1].update(settlement_state='no_charge_final',document_ids=[])
                        payload['provider_pagination']['pages'][-1]['document_ids']=[]
                        if unpaid:
                            payload['documents'][0].pop('billing_account_ref')
                            payload['documents'][0]['status']='unpaid'
                        else:payload['documents'][0]['billing_account_ref']='foreign-account'
                        result=summarize([parent] if only_parent else [parent,child],payload,
                            owner_id=child['owner_id'],mode=mode,observed_at=inventory['observed_at'],expected_inventory=inventory)
                        requested=[parent] if only_parent else [parent,child]
                        self.assertEqual(select_components(result,requested),result)
                        selected=select_components(result,[parent])
                        self.assertIsNone(selected['model_cost_usd'])
                        self.assertEqual(selected['operating_cost_coverage']['coverage_state'],'gap')
                        self.assertTrue(selected['operating_cost_component_gaps'])

    def test_calendar_rollup_retains_rejected_child_gap_and_half_open_boundary(self):
        for mode in ('paper','live'):
            payload,inventory,child,parent=calendar_fixture(mode)
            value=summarize([parent,child],payload,owner_id=child['owner_id'],mode=mode,
                observed_at=inventory['observed_at'],expected_inventory=inventory)
            self.assertEqual(value['model_cost_usd'],'1')
            selected=select_components(value,[parent])
            self.assertEqual(selected['model_cost_usd'],'1')
            component=selected['operating_cost_components'][0]
            rejected=copy.deepcopy(value);rejected['operating_cost_components']=[]
            rejected['operating_cost_component_gaps']=[{**component,'reason':'operating_cost_receipt_reassigned'}]
            self.assertIsNone(select_components(rejected,[parent])['model_cost_usd'])
            from paper_operating_costs import _calendar_contains
            self.assertFalse(_calendar_contains({**component,'occurred_at':parent['period_end']},parent))
            self.assertTrue(_calendar_contains({**component,'occurred_at':parent['period_start']},parent))

if __name__=='__main__':unittest.main()
