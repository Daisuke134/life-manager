"""Independent execution/source evidence governs scope coverage, never money."""
import copy
import unittest
from skills.cfo.adapters import actual_cost
from skills.cfo.test_actual_cost_attribution import query_payload,paid_query_payload,SNAPSHOT,TRAILING_START


def fixture(mode='paper',orders=None,paid=False):
    payload=paid_query_payload() if paid else query_payload()
    owner='alpaca-investment-'+mode;scope=payload['readback']['cost_scopes'][0]
    scope.update(owner_id=owner,mode=mode,paper=mode=='paper',order_ids=['entry','exit'] if orders is None else orders)
    if scope['order_ids']==[]:scope['scope_kind']='owner_period'
    ref={'execution_owner_id':owner,'run_id':'physical-run','occurrence_id':owner+':claimed-earlier',
        'release_sha':'a'*40,'loaded_argv_sha256':'b'*64,'loaded_env_sha256':'c'*64,
        'start_event_id':'1'*24,'terminal_event_id':'2'*24,'started_at':scope['period_start'],'finished_at':scope['period_end']}
    join=payload['job_joins'][0];join.update(scope)
    join.update(execution_refs=[{k:ref[k] for k in ('execution_owner_id','run_id','occurrence_id')}],
        run_ids=[ref['run_id']],occurrence_ids=[ref['occurrence_id']])
    selected={k:copy.deepcopy(scope[k]) for k in ('owner_id','mode','paper','order_ids','period_start','period_end','source_receipt_ids')}
    selected.update(scope_kind=scope.get('scope_kind','order_pair'),
        required_sources=[{'provider':'openai','billing_account_ref':'billing-account','category':category,
            'execution_owner_ids':[owner],'release_refs':['a'*40],'evidence_refs':['registry://cost-source']}
            for category in actual_cost.ACTUAL_COST_CATEGORIES],
        execution_refs=[ref],known_paid_bindings=[],evidence_refs=['lm-release://'+'a'*40+'/catalog'],
        gaps=[{'reason':'history_coverage_unverified'}])
    reads={'runtime':{'status':'ok','row_count':2,'archives_available':0,'first_event_at':TRAILING_START,'last_event_at':SNAPSHOT},
        'ledger':{'status':'ok','row_count':1},'admission':{'status':'ok','row_count':1}}
    inventory={'schema_version':1,'beneficiary_owner_id':owner,'observed_at':SNAPSHOT,'coverage_state':'gap',
        'reason':'cost_coverage_not_evaluated','scopes':[selected],'gaps':[],'input_reads':{owner:reads},
        'read_limits':{'owners':16,'admission_rows_per_owner':50000,'runtime_archives_per_owner':4}}
    return payload,inventory


def paid_records(payload):
    return [r for r in actual_cost.adapt(payload,snapshot_at=SNAPSHOT,trailing_start=TRAILING_START) if r['record_type']=='receipt']


class ActualCostInventoryTests(unittest.TestCase):
    def validate(self,payload,inventory,*,scope=True):
        return actual_cost.validate_official_cost_queries(payload,snapshot_at=SNAPSHOT,paid_records=paid_records(payload),
            scope=payload['readback']['cost_scopes'][0] if scope else None,expected_inventory=inventory)

    def test_real_occurrence_and_all_order_group_shapes_have_scoped_coverage_without_money(self):
        for mode in ('paper','live'):
            for orders in (['entry'],['entry','exit'],['entry','partial','exit'],[]):
                with self.subTest(mode=mode,orders=orders):
                    payload,inventory=fixture(mode,orders);before=copy.deepcopy((payload,inventory))
                    result=self.validate(payload,inventory)
                    self.assertEqual(result['coverage_state'],'complete');self.assertEqual(result['rejections'],[])
                    self.assertEqual(len(result['observations']),1)
                    self.assertNotIn('amount',result['observations'][0]);self.assertNotIn('paid_at',result['observations'][0])
                    self.assertEqual((payload,inventory),before)
                    legacy=self.validate(payload,None)
                    self.assertEqual(len(legacy['observations']),1);self.assertEqual(legacy['coverage_state'],'gap')

    def test_invalid_inventory_preserves_only_unverified_provider_diagnostics(self):
        payload,inventory=fixture();inventory['gaps']=[{'reason':'source_declaration_unverified'}]
        result=self.validate(payload,inventory)
        self.assertEqual(result['coverage_state'],'gap');self.assertEqual(len(result['observations']),1)
        self.assertEqual(result['observations'][0]['inventory_verification'],'unverified')
        self.assertTrue(result['rejections'])

    def test_scope_type_boolean_and_join_kind_mismatch_do_not_complete(self):
        for change in ('missing_kind','bool_alias','join_kind'):
            with self.subTest(change=change):
                payload,inventory=fixture()
                if change=='missing_kind':inventory['scopes'][0].pop('scope_kind')
                elif change=='bool_alias':inventory['scopes'][0]['paper']=1
                else:payload['job_joins'][0]['scope_kind']='owner_period'
                self.assertEqual(self.validate(payload,inventory)['coverage_state'],'gap')

    def test_equivalent_scope_timezone_and_unordered_evidence_ids_are_accepted(self):
        payload,inventory=fixture();join=payload['job_joins'][0]
        join['period_start']=join['period_start'].replace('Z','+00:00')
        join['source_receipt_ids']=join['source_receipt_ids'][::-1]
        self.assertEqual(self.validate(payload,inventory)['coverage_state'],'complete')

    def test_missing_source_account_or_category_never_shrinks_required_universe(self):
        payload,inventory=fixture()
        inventory['scopes'][0]['required_sources'].append({**inventory['scopes'][0]['required_sources'][0],
            'billing_account_ref':'another-account'})
        result=self.validate(payload,inventory)
        self.assertEqual(len(result['observations']),1);self.assertEqual(result['coverage_state'],'gap')
        for value in (None,''):
            changed=copy.deepcopy(inventory);changed['scopes'][0]['required_sources'][0]['billing_account_ref']=value
            self.assertEqual(self.validate(payload,changed)['coverage_state'],'gap')
        payload,inventory=fixture();inventory['scopes'][0]['required_sources'].pop()
        self.assertEqual(self.validate(payload,inventory)['coverage_state'],'gap')

    def test_wrong_history_bounds_gap_mode_owner_or_execution_is_not_complete(self):
        for change in ('future','root_gap','source_gap','mode','owner','late_start','early_end','archive_limit','missing_ledger','hash'):
            with self.subTest(change=change):
                payload,inventory=fixture();scope=inventory['scopes'][0];reads=inventory['input_reads'][scope['owner_id']]
                if change=='future':inventory['observed_at']='2026-10-01T00:00:01Z'
                elif change=='root_gap':inventory['gaps']=[{'reason':'admission_read_limit'}]
                elif change=='source_gap':scope['gaps'].append({'reason':'source_release_missing'})
                elif change=='mode':scope['mode']='live'
                elif change=='owner':inventory['beneficiary_owner_id']='other-owner'
                elif change=='late_start':reads['runtime']['first_event_at']='2026-09-25T00:00:00Z'
                elif change=='early_end':reads['runtime']['last_event_at']=TRAILING_START
                elif change=='archive_limit':reads['runtime']['archives_available']=5
                elif change=='missing_ledger':reads['ledger']['status']='unavailable'
                else:scope['execution_refs'][0]['loaded_env_sha256']='not-a-hash'
                self.assertEqual(self.validate(payload,inventory)['coverage_state'],'gap')

    def test_execution_pair_swap_and_synthetic_fallback_are_rejected(self):
        for change in ('swap','synthetic','missing','foreign'):
            with self.subTest(change=change):
                payload,inventory=fixture();join=payload['job_joins'][0]
                if change=='swap':join['execution_refs'][0]['occurrence_id']=join['occurrence_ids'][0]=inventory['beneficiary_owner_id']+':another-claim'
                elif change=='synthetic':join.pop('execution_refs');join['occurrence_ids']=[inventory['beneficiary_owner_id']+':physical-run']
                elif change=='missing':join['execution_refs']=[]
                else:join['execution_refs'][0]['execution_owner_id']='other-owner'
                self.assertEqual(self.validate(payload,inventory)['coverage_state'],'gap')

    def test_shared_executor_keeps_its_identity_with_exact_beneficiary_scope(self):
        payload,inventory=fixture();scope=inventory['scopes'][0];owner=inventory['beneficiary_owner_id'];executor='investment-strategy-validation'
        ref={**scope['execution_refs'][0],'execution_owner_id':executor,'run_id':'shared-run','occurrence_id':executor+':claimed-old',
             'start_event_id':'3'*24,'terminal_event_id':'4'*24}
        scope['execution_refs'].append(ref);inventory['input_reads'][executor]=copy.deepcopy(inventory['input_reads'][owner])
        scope['gaps'].append({'reason':'shared_attribution_unproven','execution_owner_id':executor})
        for row in scope['required_sources']:row['execution_owner_ids']=[executor]
        join=payload['job_joins'][0];join.update(execution_refs=[{k:ref[k] for k in ('execution_owner_id','run_id','occurrence_id')}],
            run_ids=[ref['run_id']],occurrence_ids=[ref['occurrence_id']])
        self.assertEqual(self.validate(payload,inventory)['coverage_state'],'complete')
        join['execution_refs'][0]['execution_owner_id']=owner
        self.assertEqual(self.validate(payload,inventory)['coverage_state'],'gap')

    def test_explicit_scope_does_not_reject_other_scope_and_global_requires_every_scope(self):
        payload,inventory=fixture();other_scope=copy.deepcopy(payload['readback']['cost_scopes'][0]);other_scope.update(scope_id='scope-2',order_ids=['entry-2','exit-2'])
        payload['readback']['cost_scopes'].append(other_scope)
        query=copy.deepcopy(payload['sources'][0]['queries'][0]);query.update(query_id='query-2',scope_id='scope-2')
        payload['sources'][0]['queries'].append(query)
        page=copy.deepcopy(payload['provider_pagination']['pages'][0]);page['query_id']='query-2';payload['provider_pagination']['pages'].append(page)
        join=copy.deepcopy(payload['job_joins'][0]);join.update(other_scope,query_id='query-2');payload['job_joins'].append(join)
        scope=copy.deepcopy(inventory['scopes'][0]);scope['order_ids']=other_scope['order_ids'];inventory['scopes'].append(scope)
        self.assertEqual(self.validate(payload,inventory)['coverage_state'],'complete')
        self.assertEqual(self.validate(payload,inventory,scope=False)['coverage_state'],'complete')
        query['complete']=False;payload['sources'][0]['queries'][-1]['complete']=False
        partly=self.validate(payload,inventory,scope=False)
        by_scope={row['scope_id']:row for row in partly['scope_coverages']}
        self.assertEqual(by_scope['scope-1']['coverage_state'],'complete')
        self.assertEqual(by_scope['scope-2']['coverage_state'],'gap')
        payload['sources'][0]['queries'].pop()
        self.assertEqual(self.validate(payload,inventory,scope=False)['coverage_state'],'gap')

    def test_paid_lower_bound_cannot_be_replaced_with_final_no_charge(self):
        payload,inventory=fixture(paid=True);record=paid_records(payload)[0];scope=inventory['scopes'][0]
        binding={**{k:scope[k] for k in ('owner_id','mode','paper','order_ids','period_start','period_end')},
            'provider':'openai','billing_account_ref':'billing-account','category':'model_cost',
            'receipt_id':record['receipt_id'],'charge_identity':['openai','invoice','same-id','line','allocation'],
            'evidence_refs':record['evidence_refs']}
        scope['known_paid_bindings']=[binding]
        self.assertEqual(self.validate(payload,inventory)['coverage_state'],'complete')
        empty,_=fixture();self.assertEqual(self.validate(empty,inventory)['coverage_state'],'gap')
        scope['known_paid_bindings'][0]['receipt_id']='paid://missing'
        scope['known_paid_bindings'][0]['charge_identity'][2]='other-invoice'
        self.assertEqual(self.validate(payload,inventory)['coverage_state'],'gap')

    def test_known_paid_charge_is_not_rebound_by_another_owner_allocation(self):
        payload,inventory=fixture(paid=True);scope=inventory['scopes'][0];record=paid_records(payload)[0]
        scope['known_paid_bindings']=[{**{k:scope[k] for k in ('owner_id','mode','paper','order_ids','period_start','period_end')},
            'provider':'openai','billing_account_ref':'billing-account','category':'model_cost','receipt_id':record['receipt_id'],
            'charge_identity':['openai','invoice','same-id','line','allocation'],'evidence_refs':record['evidence_refs']}]
        allocation=payload['job_joins'][0]
        query_join=copy.deepcopy(allocation);query_join.update(join_type='scope_query',job_id=None)
        payload['job_joins'].append(query_join)
        allocation.update(scope_id='foreign-scope',owner_id='alpaca-investment-live',mode='live',paper=False,order_ids=['foreign-entry','foreign-exit'])
        self.assertEqual(self.validate(payload,inventory)['coverage_state'],'gap')

    def test_paid_receipt_alias_keeps_the_same_underlying_charge(self):
        payload,inventory=fixture(paid=True);scope=inventory['scopes'][0];record=paid_records(payload)[0]
        scope['known_paid_bindings']=[{**{k:scope[k] for k in ('owner_id','mode','paper','order_ids','period_start','period_end')},
            'provider':'openai','billing_account_ref':'billing-account','category':'model_cost','receipt_id':record['receipt_id'],
            'charge_identity':['openai','invoice','same-id','line','allocation'],'evidence_refs':record['evidence_refs']}]
        document=payload['documents'][0]
        document.update(document_type='paid_receipt',source_type='official_paid_receipt',receipt_id='receipt-alias')
        payload['sources'][0]['queries'][0]['document_ids']=['receipt-alias']
        payload['provider_pagination']['pages'][0]['document_ids']=['receipt-alias']
        payload['job_joins'][0].update(document_type='paid_receipt',document_id='receipt-alias')
        self.assertEqual(self.validate(payload,inventory)['coverage_state'],'complete')

    def test_alias_cannot_contradict_charge_context_outside_selected_scope(self):
        for change in ('owner','orders','period','amount','category'):
            with self.subTest(change=change):
                payload,inventory=fixture(paid=True)
                document=copy.deepcopy(payload['documents'][0]);document.update(document_type='paid_receipt',
                    source_type='official_paid_receipt',receipt_id='alias-outside')
                document['line_items'][0]['allocations'][0]['job_id']='alias-job'
                alias=copy.deepcopy(payload['job_joins'][0]);alias.update(job_id='alias-job',document_type='paid_receipt',
                    document_id='alias-outside',scope_id='foreign-scope')
                if change=='owner':alias.update(owner_id='alpaca-investment-live',mode='live',paper=False)
                elif change=='orders':alias['order_ids']=['foreign-entry','foreign-exit']
                elif change=='period':alias['period_start']='2026-09-24T00:00:01Z'
                elif change=='amount':
                    document['line_items'][0]['amount']='2'
                    document['line_items'][0]['allocations'][0]['amount']='2'
                else:document['line_items'][0]['category']='infra_cost'
                payload['documents'].append(document);payload['job_joins'].append(alias)
                payload['sources'][0]['queries'][0]['document_ids'].append('alias-outside')
                payload['provider_pagination']['pages'][0]['document_ids'].append('alias-outside')
                self.assertEqual(self.validate(payload,inventory)['coverage_state'],'gap')
        payload,inventory=fixture(paid=True)
        document=copy.deepcopy(payload['documents'][0]);document.update(document_type='paid_receipt',
            source_type='official_paid_receipt',receipt_id='same-context-alias')
        document['line_items'][0]['allocations'][0]['job_id']='alias-job'
        alias=copy.deepcopy(payload['job_joins'][0]);alias.update(job_id='alias-job',document_type='paid_receipt',
            document_id='same-context-alias',period_start=TRAILING_START.replace('Z','+00:00'))
        alias['source_receipt_ids']=alias['source_receipt_ids'][::-1]
        payload['documents'].append(document);payload['job_joins'].append(alias)
        payload['sources'][0]['queries'][0]['document_ids'].append('same-context-alias')
        payload['provider_pagination']['pages'][0]['document_ids'].append('same-context-alias')
        self.assertEqual(self.validate(payload,inventory)['coverage_state'],'complete')

    def test_product_loop_declaration_is_a_typed_list_not_string_or_mapping_membership(self):
        for value in ('not-investment',{'investment':False},['investment','investment'],['investment','not-real'],None):
            with self.subTest(value=value):
                payload,inventory=fixture();payload['sources'][0]['product_loop_ids']=value
                self.assertEqual(self.validate(payload,inventory)['coverage_state'],'gap')

    def test_malformed_explicit_scope_never_escapes_fail_closed(self):
        for scope in ([],False,'not-parsed'):
            with self.subTest(scope=scope):
                payload,inventory=fixture()
                result=actual_cost.validate_official_cost_queries(payload,snapshot_at=SNAPSHOT,
                    paid_records=[],scope=scope,expected_inventory=inventory)
                self.assertEqual(result['coverage_state'],'gap')
                self.assertTrue(result['rejections'])

    def test_query_covers_full_seeded_run_before_intent_and_after_close(self):
        payload,inventory=fixture();ref=inventory['scopes'][0]['execution_refs'][0]
        ref.update(started_at='2026-09-23T23:59:50Z',finished_at='2026-09-30T00:00:10Z')
        reads=inventory['input_reads'][inventory['beneficiary_owner_id']]['runtime']
        reads['first_event_at']=ref['started_at']
        self.assertEqual(self.validate(payload,inventory)['coverage_state'],'gap')
        payload['sources'][0]['queries'][0]['window_start']=ref['started_at']
        result=self.validate(payload,inventory)
        self.assertEqual(result['coverage_state'],'complete')
        windows=result['observations'][0]['execution_windows']
        self.assertEqual(windows[0]['started_at'],'2026-09-23T23:59:50.000000Z')
        self.assertEqual(windows[0]['finished_at'],'2026-09-30T00:00:10.000000Z')
        payload['sources'][0]['queries'][0]['window_end']='2026-09-30T00:00:05Z'
        self.assertEqual(self.validate(payload,inventory)['coverage_state'],'gap')

    def test_invalid_execution_time_never_falls_back_to_scope_or_current_clock(self):
        for change in ('missing','missing_both','reversed','future','outside','bad','history_end'):
            with self.subTest(change=change):
                payload,inventory=fixture();ref=inventory['scopes'][0]['execution_refs'][0]
                if change=='missing':ref.pop('started_at')
                elif change=='missing_both':ref.pop('started_at');ref.pop('finished_at')
                elif change=='reversed':ref['started_at']=SNAPSHOT
                elif change=='future':ref['finished_at']='2026-10-01T00:00:01Z'
                elif change=='outside':ref.update(started_at='2026-09-23T00:00:00Z',finished_at='2026-09-23T01:00:00Z')
                elif change=='bad':ref['finished_at']=False
                else:
                    ref['finished_at']='2026-09-30T01:00:00Z'
                    inventory['input_reads'][inventory['beneficiary_owner_id']]['runtime']['last_event_at']='2026-09-30T00:00:00Z'
                self.assertEqual(self.validate(payload,inventory)['coverage_state'],'gap')

if __name__=='__main__':unittest.main()
