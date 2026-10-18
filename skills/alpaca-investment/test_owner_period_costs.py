"""Idle-day operating reports use native execution anchors, not invented trades."""
import copy,json,os,tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import paper_operating_costs as costs
import cost_inventory
from test_operating_cost_inventory import setup
from test_cost_inventory import OWNER


class OwnerPeriodCostsTests(unittest.TestCase):
    def reader(self):
        reader=getattr(costs,'read_owner_period_costs',None)
        self.assertTrue(callable(reader),'owner-period cost reader is missing')
        return reader

    def fixture(self,mode,paid=False):
        payload,inventory,scope=setup(mode,orders=[],paid=paid)
        scope.update(period_start='2026-09-30T00:00:00+00:00',period_end='2026-10-01T00:00:00+00:00')
        ref=inventory['scopes'][0]['execution_refs'][0]
        ref.update(started_at='2026-09-30T00:00:00Z',finished_at='2026-09-30T00:01:00Z')
        scope['source_receipt_ids']=[ref['start_event_id'],ref['terminal_event_id']]
        payload['readback']['cost_scopes'][0].update(scope)
        payload['job_joins'][0].update(scope)
        inventory['scopes'][0].update(scope)
        if paid:payload['documents'][0]['line_items'][0]['occurred_at']='2026-09-30T00:00:30Z'
        return payload,inventory,scope

    def test_census_fills_only_owner_period_anchors_from_native_events(self):
        from test_cost_inventory import IndependentCensusTests
        trips,kwargs=IndependentCensusTests().fixture()
        scope={**trips[0],'scope_kind':'owner_period','owner_id':OWNER,'mode':'paper','paper':True,
            'order_ids':[],'period_end':trips[0]['closed_at'],'source_receipt_ids':[]}
        before=copy.deepcopy((scope,kwargs))
        result=cost_inventory.build_expected_inventory([scope],**kwargs)
        actual=result['scopes'][0]
        expected=sorted({row['event_id'] for row in kwargs['runtime_rows_by_owner'][OWNER]})
        self.assertEqual(actual['source_receipt_ids'],expected)
        self.assertNotIn('scope_evidence_missing',{g['reason'] for g in actual['gaps']})
        self.assertEqual((scope,kwargs),before)
        self.assertNotIn('model_cost_usd',actual)
        kwargs['runtime_rows_by_owner']={OWNER:[]}
        missing=cost_inventory.build_expected_inventory([scope],**kwargs)['scopes'][0]
        self.assertEqual(missing['source_receipt_ids'],[])
        self.assertIn('scope_evidence_missing',{g['reason'] for g in missing['gaps']})

    def test_no_trades_still_has_previous_utc_day_cost_scope_and_durable_history(self):
        reader=self.reader()
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);state=root/'state';state.mkdir()
                payload,inventory,scope=self.fixture(mode)
                billing=root/'billing.json';billing.write_text(json.dumps(payload))
                with patch.dict(os.environ,{'LM_CFO_ACTUAL_COST_READBACK':str(billing),'LM_CFO_ACTUAL_COST':''}),                      patch.object(cost_inventory,'read_expected_inventory',return_value=inventory) as census:
                    first=reader(state,observed_at=inventory['observed_at'],owner_id=scope['owner_id'],mode=mode)
                    self.assertEqual(first['model_cost_usd'],'0')
                    self.assertEqual(first['period_timezone'],'UTC')
                    self.assertEqual(first['period_start'],scope['period_start'])
                    self.assertEqual(first['period_end'],scope['period_end'])
                    self.assertEqual(first['source_receipt_ids'],scope['source_receipt_ids'])
                    self.assertEqual(first['cost_scope']['order_ids'],[])
                    self.assertEqual(census.call_args.args[1][-1]['source_receipt_ids'],[])
                    billing.unlink()
                    second=reader(state,observed_at=inventory['observed_at'],owner_id=scope['owner_id'],mode=mode,previous=first)
                    self.assertIsNone(second['model_cost_usd'])
                    self.assertEqual(second['operating_cost_coverage']['coverage_state'],'gap')
                    self.assertEqual(second['known_operating_cost_source_evidence'],first['known_operating_cost_source_evidence'])
                    self.assertIsNone(second['net_pnl_usd']);self.assertFalse(second['capital_expansion_allowed'])
                self.assertEqual(list(state.iterdir()),[])

    def test_confirmed_paid_owner_costs_cannot_disappear_or_change(self):
        reader=self.reader()
        for mode in ('paper','live'):
            for changed in ('zero','amount'):
                with self.subTest(mode=mode,changed=changed),tempfile.TemporaryDirectory() as directory:
                    root=Path(directory);payload,inventory,scope=self.fixture(mode,paid=True)
                    billing=root/'billing.json';billing.write_text(json.dumps(payload))
                    def read(previous=None):return reader(root,observed_at=inventory['observed_at'],
                        owner_id=scope['owner_id'],mode=mode,previous=previous)
                    with patch.dict(os.environ,{'LM_CFO_ACTUAL_COST_READBACK':str(billing),'LM_CFO_ACTUAL_COST':''}),                          patch.object(cost_inventory,'read_expected_inventory',return_value=inventory):
                        first=read();self.assertEqual(first['model_cost_usd'],'1')
                        bad=copy.deepcopy(payload)
                        if changed=='zero':
                            bad['documents']=[]
                            bad['sources'][0]['queries'][0].update(settlement_state='no_charge_final',document_ids=[])
                            bad['provider_pagination']['pages'][0]['document_ids']=[]
                            bad['job_joins'][0].update(join_type='scope_query',job_id=None)
                        else:
                            line=bad['documents'][0]['line_items'][0]
                            line['amount']=line['allocations'][0]['amount']='2'
                        billing.write_text(json.dumps(bad));regressed=read(first)
                        self.assertIsNone(regressed['model_cost_usd'])
                        self.assertEqual(regressed['operating_cost_coverage']['coverage_state'],'gap')
                        self.assertEqual(regressed['known_operating_cost_components'],first['known_operating_cost_components'])
                        billing.write_text(json.dumps(payload));recovered=read(regressed)
                        self.assertEqual(recovered['model_cost_usd'],'1')
                        self.assertEqual(recovered['known_operating_cost_components'],first['known_operating_cost_components'])

    def test_paper_producer_keeps_prior_day_economic_scopes_in_native_shape(self):
        from paper_performance import write_paper_performance
        from test_paper_performance import _rows,OBSERVATION,RISK
        for next_day in (False,True):
            with self.subTest(next_day=next_day),tempfile.TemporaryDirectory() as directory:
                state=Path(directory);state.joinpath('receipts.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in _rows()))
                observation=copy.deepcopy(OBSERVATION)
                if next_day:observation['clock']['observed_at']='2026-10-21T00:00:10Z'
                with patch.dict(os.environ,{'LM_CFO_ACTUAL_COST_READBACK':'','LM_CFO_ACTUAL_COST':''}):
                    result=write_paper_performance(state,observation,RISK)
                self.assertEqual(result['completed_round_trips_total'],1)
                scopes=result.get('economic_cost_scopes',[])
                self.assertEqual(len(scopes),1)
                self.assertIn('closed_at',scopes[0])
                census=cost_inventory.build_expected_inventory(scopes,beneficiary_owner_id=OWNER,
                    observed_at=observation['clock']['observed_at'],runtime_rows_by_owner={},occurrence_rows_by_owner={},
                    release_inputs={},paid_bindings=[])
                self.assertEqual(len(census['scopes']),1)
                self.assertNotIn('scope_invalid',{g['reason'] for g in census['gaps']})

    def test_invalid_mode_owner_does_not_read_private_inventory(self):
        reader=self.reader()
        with patch.object(cost_inventory,'read_expected_inventory') as census:
            result=reader(Path('/unused'),observed_at='2026-10-01T01:00:00Z',owner_id='alpaca-investment-live',mode='paper')
            self.assertIsNone(result['model_cost_usd']);self.assertFalse(result['capital_expansion_allowed'])
            census.assert_not_called()

if __name__=='__main__':unittest.main()
