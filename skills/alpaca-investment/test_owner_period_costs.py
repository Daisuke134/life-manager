"""Idle-day operating reports use native execution anchors, not invented trades."""
import copy,json,os,tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import paper_operating_costs as costs
import cost_inventory
from test_operating_cost_inventory import setup
from test_cost_inventory import IndependentCensusTests,OWNER


class OwnerPeriodCostsTests(unittest.TestCase):
    def reader(self):
        reader=getattr(costs,'read_owner_period_costs',None)
        self.assertTrue(callable(reader),'owner-period cost reader is missing')
        return reader

    def fixture(self,mode):
        payload,inventory,scope=setup(mode,orders=[])
        scope.update(period_start='2026-09-30T00:00:00+00:00',period_end='2026-10-01T00:00:00+00:00')
        ref=inventory['scopes'][0]['execution_refs'][0]
        ref.update(started_at='2026-09-30T00:00:00Z',finished_at='2026-09-30T00:01:00Z')
        scope['source_receipt_ids']=[ref['start_event_id'],ref['terminal_event_id']]
        payload['readback']['cost_scopes'][0].update(scope)
        payload['job_joins'][0].update(scope)
        inventory['scopes'][0].update(scope)
        return payload,inventory,scope

    def test_census_fills_only_owner_period_anchors_from_native_events(self):
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

    def test_invalid_mode_owner_does_not_read_private_inventory(self):
        reader=self.reader()
        with patch.object(cost_inventory,'read_expected_inventory') as census:
            result=reader(Path('/unused'),observed_at='2026-10-01T01:00:00Z',owner_id='alpaca-investment-live',mode='paper')
            self.assertIsNone(result['model_cost_usd']);self.assertFalse(result['capital_expansion_allowed'])
            census.assert_not_called()

if __name__=='__main__':unittest.main()
