"""Only complete independent scope proof propagates; monetary totals stay unknown."""
import copy
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


def window_fixture(mode='paper',moment='after'):
    payload,inventory,trip=setup(mode,paid=True);owner=trip['owner_id'];scope=inventory['scopes'][0]
    entry=scope['execution_refs'][0]
    entry.update(started_at='2026-09-23T23:59:50Z',finished_at='2026-09-24T00:00:10Z')
    closing={**entry,'run_id':'closing-run','occurrence_id':owner+':closing-claim',
        'start_event_id':'3'*24,'terminal_event_id':'4'*24,'started_at':'2026-09-29T23:59:50Z','finished_at':'2026-09-30T00:00:10Z'}
    scope['execution_refs'].append(closing)
    metadata=inventory['input_reads'][owner];metadata['runtime'].update(row_count=4,first_event_at=entry['started_at'])
    metadata['admission']['row_count']=2
    query=payload['sources'][0]['queries'][0];query['window_start']=entry['started_at']
    payload['documents'][0]['billing_period_start']=entry['started_at']
    payload['documents'][0]['line_items'][0]['occurred_at']=('2026-09-23T23:59:55Z' if moment=='before' else '2026-09-30T00:00:05Z')
    selected=entry if moment=='before' else closing
    allocation=payload['job_joins'][0]
    def refs(rows):return [{k:r[k] for k in ('execution_owner_id','run_id','occurrence_id')} for r in rows]
    allocation.update(execution_refs=refs([selected]),run_ids=[selected['run_id']],occurrence_ids=[selected['occurrence_id']])
    query_join=copy.deepcopy(allocation)
    query_join.update(join_type='scope_query',job_id=None,execution_refs=refs([entry,closing]),
        run_ids=[entry['run_id'],closing['run_id']],occurrence_ids=[entry['occurrence_id'],closing['occurrence_id']])
    payload['job_joins'].append(query_join)
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
        self.assertEqual(result['model_cost_usd'],'1')
        self.assertEqual(result['system_cost_usd'],'0')

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
                for ref in trusted['execution_refs']:ref.update(started_at=cycle['period_start'],finished_at=cycle['closed_at'])
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
                self.assertIsNone(result['net_pnl_usd']);self.assertEqual(result['model_cost_usd'],'0')
                self.assertEqual(result['system_cost_usd'],'0')
                direct=crypto.build_crypto_performance(store._rows(root/'receipts.jsonl'),mode=mode,owner_id='alpaca-investment-'+mode,
                    activity_readbacks={o['id']:frame for o in orders},operating_cost_readback=payload,observed_at=observed,expected_inventory=inventory)
                self.assertEqual(direct['model_cost_usd'],'0');self.assertEqual(direct['system_cost_usd'],'0')
                self.assertFalse(result['capital_expansion_allowed'])

    def test_rejection_reason_is_saved_with_the_exact_scope(self):
        payload,inventory,trip=setup();payload['sources'][0]['product_loop_ids']='not-investment'
        result=summarize([trip],payload,owner_id=trip['owner_id'],observed_at=inventory['observed_at'],expected_inventory=inventory)
        self.assertEqual(result['operating_cost_coverage']['coverage_state'],'gap')
        errors=result['operating_cost_query_rejections']
        self.assertEqual(len(errors),1)
        self.assertEqual(errors[0]['reason'],'cost_query_source_missing')
        self.assertEqual(errors[0]['order_ids'],trip['order_ids'])
        self.assertEqual(select_components(result,[])['operating_cost_query_rejections'],[])

    def test_exact_run_expenses_before_intent_and_after_close_are_not_dropped(self):
        for mode in ('paper','live'):
            for moment in ('before','after'):
                with self.subTest(mode=mode,moment=moment):
                    payload,inventory,trip=window_fixture(mode,moment);original=copy.deepcopy((payload,inventory,trip))
                    result=summarize([trip],payload,owner_id=trip['owner_id'],mode=mode,
                        observed_at=inventory['observed_at'],expected_inventory=inventory)
                    self.assertEqual(Decimal(result['verified_model_cost_subtotal_usd']),Decimal('1'))
                    self.assertEqual(result['operating_cost_coverage']['coverage_state'],'complete')
                    self.assertEqual(result['operating_cost_components'][0]['attribution_basis'],'verified_execution_window')
                    self.assertEqual((payload,inventory,trip),original)
                    self.assertNotIn('net_pnl_usd',result)

    def test_wrong_run_or_unproven_time_never_becomes_zero_cost(self):
        for change in ('wrong_ref','outside','no_inventory_proof'):
            with self.subTest(change=change):
                payload,inventory,trip=window_fixture(moment='after')
                if change=='wrong_ref':
                    entry=inventory['scopes'][0]['execution_refs'][0]
                    payload['job_joins'][0].update(execution_refs=[{k:entry[k] for k in ('execution_owner_id','run_id','occurrence_id')}],
                        run_ids=[entry['run_id']],occurrence_ids=[entry['occurrence_id']])
                elif change=='outside':payload['documents'][0]['line_items'][0]['occurred_at']='2026-09-30T00:00:15Z'
                else:inventory['gaps']=[{'reason':'source_declaration_unverified'}]
                result=summarize([trip],payload,owner_id=trip['owner_id'],observed_at=inventory['observed_at'],expected_inventory=inventory)
                self.assertIsNone(result['verified_model_cost_subtotal_usd'])
                self.assertEqual(result['operating_cost_coverage']['coverage_state'],'gap')
                self.assertEqual(len(result['operating_cost_component_gaps']),1)
                self.assertTrue(result['operating_cost_component_gaps'][0]['receipt_id'])

    def test_calendar_costs_do_not_leak_across_the_exclusive_period_end(self):
        for occurred in ('2026-09-30T00:00:00Z','2026-09-30T00:00:05Z'):
            with self.subTest(occurred=occurred):
                payload,inventory,trip=window_fixture()
                end=trip.pop('closed_at');trip.update(scope_kind='owner_period',period_end=end,order_ids=[])
                scope=payload['readback']['cost_scopes'][0];scope.update(scope_kind='owner_period',order_ids=[])
                inventory['scopes'][0].update(scope_kind='owner_period',order_ids=[])
                for join in payload['job_joins']:join.update(scope_kind='owner_period',order_ids=[])
                payload['documents'][0]['line_items'][0]['occurred_at']=occurred
                result=summarize([trip],payload,owner_id=trip['owner_id'],observed_at=inventory['observed_at'],expected_inventory=inventory)
                self.assertEqual(result['operating_cost_components'],[])
                self.assertEqual(result['operating_cost_coverage']['coverage_state'],'gap')

    def test_category_uses_its_own_declared_executor_not_the_query_union(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode):
                payload,inventory,trip=window_fixture(mode)
                owner=trip['owner_id'];other='investment-strategy-validation';scope=inventory['scopes'][0]
                scope['execution_refs'][1].update(execution_owner_id=other,occurrence_id=other+':closing-claim')
                inventory['input_reads'][other]=copy.deepcopy(inventory['input_reads'][owner])
                inventory['input_reads'][owner]['runtime']['row_count']=2
                inventory['input_reads'][owner]['admission']['row_count']=1
                for source in scope['required_sources']:
                    if source['category']!='model_cost':source['execution_owner_ids']=[other]
                for join in payload['job_joins']:
                    for ref in join['execution_refs']:
                        if ref['run_id']=='closing-run':ref.update(execution_owner_id=other,occurrence_id=other+':closing-claim')
                    join['occurrence_ids']=[r['occurrence_id'] for r in join['execution_refs']]
                wrong=summarize([trip],payload,owner_id=owner,mode=mode,observed_at=inventory['observed_at'],expected_inventory=inventory)
                self.assertIsNone(wrong['verified_model_cost_subtotal_usd'])
                self.assertEqual(wrong['operating_cost_coverage']['coverage_state'],'gap')
                self.assertTrue(wrong['operating_cost_component_gaps'])
                payload['documents'][0]['line_items'][0]['category']='infra_cost'
                correct=summarize([trip],payload,owner_id=owner,mode=mode,observed_at=inventory['observed_at'],expected_inventory=inventory)
                self.assertEqual(Decimal(correct['verified_system_cost_subtotal_usd']),Decimal('1'))
                self.assertEqual(correct['operating_cost_coverage']['coverage_state'],'complete')
                closing=next(w for w in correct['operating_cost_query_observations'][0]['execution_windows'] if w['run_id']=='closing-run')
                self.assertNotIn('model_cost',closing['covered_categories'])
                self.assertIn('infra_cost',closing['covered_categories'])

    def test_modern_contradicted_proof_does_not_fall_back_inside_economic_interval(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode):
                payload,inventory,trip=window_fixture(mode)
                owner=trip['owner_id'];other='investment-strategy-validation';scope=inventory['scopes'][0]
                scope['execution_refs'][1].update(execution_owner_id=other,occurrence_id=other+':closing-claim')
                inventory['input_reads'][other]=copy.deepcopy(inventory['input_reads'][owner])
                inventory['input_reads'][owner]['runtime']['row_count']=2
                inventory['input_reads'][owner]['admission']['row_count']=1
                for source in scope['required_sources']:
                    if source['category']!='model_cost':source['execution_owner_ids']=[other]
                for join in payload['job_joins']:
                    for ref in join['execution_refs']:
                        if ref['run_id']=='closing-run':ref.update(execution_owner_id=other,occurrence_id=other+':closing-claim')
                    join['occurrence_ids']=[ref['occurrence_id'] for ref in join['execution_refs']]
                payload['documents'][0]['line_items'][0]['occurred_at']='2026-09-29T23:59:55Z'
                result=summarize([trip],payload,owner_id=owner,mode=mode,observed_at=inventory['observed_at'],expected_inventory=inventory)
                self.assertIsNone(result['verified_model_cost_subtotal_usd'])
                self.assertEqual(result['operating_cost_components'],[])
                self.assertEqual(result['operating_cost_coverage']['coverage_state'],'gap')
                self.assertTrue(result['operating_cost_component_gaps'])

if __name__=='__main__':unittest.main()
