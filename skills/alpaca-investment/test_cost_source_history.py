"""Prior source coverage is durable evidence, never authority for current money."""
import copy,json,os,tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from paper_operating_costs import summarize
from test_operating_cost_inventory import setup

FIELD='known_operating_cost_source_evidence'


class CostSourceHistoryTests(unittest.TestCase):
    def test_paper_zero_source_evidence_survives_missing_current_input(self):
        from paper_performance import _bind_operating_costs
        payload,inventory,trip=setup()
        confirmed=summarize([trip],payload,owner_id=trip['owner_id'],observed_at=inventory['observed_at'],expected_inventory=inventory)
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)
            first,_=_bind_operating_costs(state,[trip],confirmed)
            self.assertTrue(first.get(FIELD))
            saved={**first,'mode':'paper','paper':True,'performance_day':'2026-09-30',
                'report_scope':'daily_accumulation','observed_at':'2026-09-30T00:01:00Z',
                'source_receipt_ids':trip['source_receipt_ids']}
            history=state/'performance-daily-2026-09-30.json';history.write_text(json.dumps(saved))
            missing=summarize([trip],None,owner_id=trip['owner_id'],observed_at=inventory['observed_at'])
            second,_=_bind_operating_costs(state,[trip],missing)
            self.assertEqual(second.get(FIELD),first[FIELD])
            self.assertIsNone(second['model_cost_usd'])
            self.assertEqual(second['operating_cost_coverage']['coverage_state'],'gap')
            again,_=_bind_operating_costs(state,[trip],confirmed)
            self.assertEqual(again[FIELD],first[FIELD])
            self.assertEqual(again['model_cost_usd'],'0')
            self.assertEqual(json.loads(history.read_text()),saved)

    def test_history_record_requires_traceable_query_identity_and_window(self):
        from paper_operating_costs import remember_source_evidence
        payload,inventory,trip=setup()
        confirmed=summarize([trip],payload,owner_id=trip['owner_id'],observed_at=inventory['observed_at'],expected_inventory=inventory)
        known=remember_source_evidence([],confirmed,owner_id=trip['owner_id'],mode='paper')
        missing=summarize([trip],None,owner_id=trip['owner_id'],observed_at=inventory['observed_at'])
        for field in ('query_id','scope_id','window_start','window_end','finalized_through','execution_windows'):
            with self.subTest(field=field):
                damaged=copy.deepcopy(known);damaged[0]['queries'][0].pop(field)
                before=copy.deepcopy(damaged)
                with self.assertRaisesRegex(ValueError,'operating_cost_source_history_invalid'):
                    remember_source_evidence(damaged,missing,owner_id=trip['owner_id'],mode='paper')
                self.assertEqual(damaged,before)
        for target,field,value in (('scope','owner_id','alpaca-investment-live'),
                ('queries','scope_id','foreign-scope'),('queries','window_end','2026-09-23T00:00:00Z')):
            with self.subTest(target=target,field=field):
                damaged=copy.deepcopy(known)
                row=damaged[0]['scope'] if target=='scope' else damaged[0]['queries'][0]
                row[field]=value
                with self.assertRaisesRegex(ValueError,'operating_cost_source_history_invalid'):
                    remember_source_evidence(damaged,missing,owner_id=trip['owner_id'],mode='paper')

    def test_shared_execution_can_finish_after_billing_observation(self):
        from paper_operating_costs import remember_source_evidence
        for mode in ('paper','live'):
            for paid in (False,True):
                with self.subTest(mode=mode,paid=paid):
                    payload,inventory,trip=setup(mode,orders=[],paid=paid)
                    owner=trip['owner_id'];executor='investment-strategy-validation'
                    ref=inventory['scopes'][0]['execution_refs'][0]
                    ref.update(execution_owner_id=executor,occurrence_id=executor+':shared-run',
                        finished_at='2026-10-01T00:00:00.500000Z')
                    for source in inventory['scopes'][0]['required_sources']:source['execution_owner_ids']=[executor]
                    inventory['input_reads'][executor]=inventory['input_reads'].pop(owner)
                    inventory['input_reads'][executor]['runtime']['last_event_at']=inventory['observed_at']
                    for join in payload['job_joins']:
                        join['execution_refs']=[{k:ref[k] for k in ('execution_owner_id','run_id','occurrence_id')}]
                        join['occurrence_ids']=[ref['occurrence_id']]
                    result=summarize([trip],payload,owner_id=owner,mode=mode,
                        observed_at=inventory['observed_at'],expected_inventory=inventory)
                    self.assertEqual(result['operating_cost_coverage']['coverage_state'],'complete')
                    recorded=remember_source_evidence([],result,owner_id=owner,mode=mode)
                    self.assertEqual(len(recorded),1)
                    self.assertEqual(recorded[0]['queries'][0]['execution_windows'][0]['execution_owner_id'],executor)
                    self.assertFalse(recorded[0]['current_cost_authority'])

    def test_crypto_history_survives_regression_and_missing_input_without_restoring_zero(self):
        import crypto_performance as crypto
        import effect_store as store
        from test_crypto_performance import cycle_fixture,activity_fixture
        from skills.cfo.test_actual_cost_inventory import fixture
        observed='2026-01-02T00:00:03Z';billing_at='2026-01-02T00:00:02Z'
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);orders,frame,_=cycle_fixture(root,mode,partial=True)
                built=crypto.build_crypto_performance(store._rows(root/'receipts.jsonl'),
                    mode=mode,owner_id='alpaca-investment-'+mode,activity_readbacks={o['id']:frame for o in orders})
                cycle=built['cycles'][0];payload,inventory=fixture(mode)
                scope=payload['readback']['cost_scopes'][0]
                scope.update(order_ids=cycle['order_ids'],period_start=cycle['period_start'],period_end=cycle['closed_at'],source_receipt_ids=cycle['source_receipt_ids'])
                payload['job_joins'][0].update(scope)
                payload['readback'].update(observed_at=billing_at,
                    historical={'complete':True,'window_start':None,'window_end':billing_at},
                    trailing={'complete':True,'window_start':cycle['period_start'],'window_end':billing_at})
                payload['sources'][0]['queries'][0].update(window_start=cycle['period_start'],window_end=billing_at,observed_at=billing_at,finalized_through=billing_at)
                trusted=inventory['scopes'][0]
                trusted.update({k:copy.deepcopy(scope[k]) for k in ('order_ids','period_start','period_end','source_receipt_ids')})
                for ref in trusted['execution_refs']:ref.update(started_at=cycle['period_start'],finished_at=cycle['closed_at'])
                inventory['observed_at']=observed
                inventory['input_reads']['alpaca-investment-'+mode]['runtime'].update(first_event_at=cycle['period_start'],last_event_at=observed)
                billing=root/'billing.json';billing.write_text(json.dumps(payload))
                def read(**kw):return activity_fixture(frame,mode=mode,start=kw['period_start'],end=kw['period_end'])
                def write():return crypto.write_crypto_performance(root,{'mode':mode,'paper':mode=='paper','clock':{'observed_at':observed}},
                    mode=mode,owner_id='alpaca-investment-'+mode,activity_reader=read)
                with patch.dict(os.environ,{'LM_CFO_ACTUAL_COST_READBACK':str(billing),'LM_CFO_ACTUAL_COST':''}),patch.object(crypto,'read_expected_inventory',return_value=inventory):
                    first=write();self.assertTrue(first.get(FIELD));self.assertEqual(first['model_cost_usd'],'0')
                    broken=copy.deepcopy(payload);broken['sources'][0]['queries']=[];billing.write_text(json.dumps(broken))
                    second=write();billing.unlink();third=write()
                    for value in (second,third):
                        self.assertEqual(value.get(FIELD),first[FIELD])
                        self.assertIsNone(value['model_cost_usd'])
                        self.assertEqual(value['operating_cost_coverage']['coverage_state'],'gap')
                        self.assertIsNone(value['net_pnl_usd']);self.assertFalse(value['capital_expansion_allowed'])
                    daily=json.loads((root/'performance-crypto-daily-2026-01-01.json').read_text())
                    self.assertEqual(daily[FIELD],first[FIELD])
                    billing.write_text(json.dumps(payload));recovered=write()
                    self.assertEqual(recovered[FIELD],first[FIELD])
                    self.assertEqual(recovered['model_cost_usd'],'0')
                    latest=root/'performance-crypto-latest.json';damaged=json.loads(latest.read_text())
                    damaged[FIELD][0]['scope']['mode']='live' if mode=='paper' else 'paper'
                    latest.write_text(json.dumps(damaged));invalid=write()
                    self.assertEqual(invalid['reason'],'crypto_operating_cost_source_history_invalid')
                    self.assertEqual(invalid['known_entry_effect_ids'],recovered['known_entry_effect_ids'])
                    self.assertEqual(invalid['known_closed_cycle_ids'],recovered['known_closed_cycle_ids'])
                    self.assertEqual(invalid['activity_readbacks'],recovered['activity_readbacks'])
                    self.assertEqual(invalid[FIELD],damaged[FIELD])
                    self.assertIsNone(invalid['net_pnl_usd']);self.assertFalse(invalid['capital_expansion_allowed'])

if __name__=='__main__':unittest.main()
