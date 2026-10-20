import importlib
import json
import tempfile
import unittest
from pathlib import Path


PERFORMANCE = {
    "measurement_status": "measured", "mode": "live", "paper": False,
    "observed_at": "2026-09-29T00:00:00Z",
    "gross_strategy_pnl_usd": "-0.14",
    "fees_usd": "0.01",
    "slippage_usd": "0.00",
    "completed_round_trips": 1,
    "observed_endpoint_drawdown_usd": "0.15",
    "capital_cap_usd": "100.00",
    "source_receipt_ids": ["order-1", "fill-1", "fee-1"],
}

OBSERVATION = {
    "account": {"equity": "66.63", "cash": "0.00"},
    "clock": {"observed_at": "2026-09-29T00:00:01Z"},
}

RISK = {"drawdown_fraction": "0.0015"}


class AlpacaSnapshotTests(unittest.TestCase):
    def test_crypto_verified_operating_costs_remain_partial_in_root_and_daily_reader(self):
        from alpaca_snapshot import _read_performance
        base={'schema_version':1,'report_scope':'owned_crypto_cycles','mode':'live','paper':False,
            'owner_id':'alpaca-investment-live','measurement_status':'partial','net_pnl_usd':None,
            'capital_expansion_allowed':False,'model_cost_usd':'1','system_cost_usd':'0',
            'operating_costs_status':'complete','operating_cost_coverage':{'coverage_state':'complete'}}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for mode in ('paper','live'):
                for day in (None,'2026-01-01'):
                    with self.subTest(mode=mode,day=day):
                        payload={**base,'mode':mode,'paper':mode=='paper','owner_id':'alpaca-investment-'+mode}
                        path=root/'performance-crypto-latest.json'
                        if day:
                            payload.update(report_scope='owned_crypto_cycles_daily',performance_day=day,
                                observed_at=day+'T23:00:00Z')
                            path=root/f'performance-crypto-daily-{day}.json'
                        path.write_text(json.dumps(payload))
                        value,error=_read_performance(root,day)
                        self.assertIsNone(error)
                        snapshot=self._builder()(value,OBSERVATION,RISK)
                        self.assertEqual(snapshot['model_cost_usd'],'1')
                        self.assertEqual(snapshot['system_cost_usd'],'0')
                        self.assertEqual(snapshot['measurement_status'],'partial')
                        self.assertIsNone(snapshot['gross_pnl_usd'])
                        self.assertIsNone(snapshot['trading_fees_usd'])

    def test_crypto_operating_amounts_need_complete_coverage_and_finite_nonnegative_strings(self):
        from alpaca_snapshot import _read_performance
        base={'schema_version':1,'report_scope':'owned_crypto_cycles','mode':'live','paper':False,
            'owner_id':'alpaca-investment-live','measurement_status':'partial','net_pnl_usd':None,
            'capital_expansion_allowed':False,'model_cost_usd':'1','system_cost_usd':'0',
            'operating_costs_status':'complete','operating_cost_coverage':{'coverage_state':'complete'}}
        changes=[{'operating_costs_status':'partial'},{'operating_cost_coverage':{'coverage_state':'gap'}},
            {'operating_cost_coverage':None},{'model_cost_usd':None},{'system_cost_usd':None}]
        changes += [{'model_cost_usd':raw} for raw in (True,1,1.2,[],{},'','NaN','sNaN','Infinity','-1')]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'performance-crypto-latest.json'
            for change in changes:
                with self.subTest(change=change):
                    path.write_text(json.dumps({**base,**change}))
                    value,error=_read_performance(root,None)
                    self.assertIsNone(value);self.assertEqual(error,'alpaca_crypto_performance_invalid')

    def test_crypto_derived_source_is_selected_without_legacy_measured_fallback(self):
        from alpaca_snapshot import _read_performance
        import tempfile,json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'performance-latest.json').write_text(json.dumps({'measurement_status':'measured','net_pnl_usd':'999'}))
            path=root/'performance-crypto-latest.json'
            path.write_text(json.dumps({'schema_version':1,'report_scope':'owned_crypto_cycles','mode':'paper','paper':True,'owner_id':'alpaca-investment-paper','measurement_status':'partial','net_pnl_usd':None,'capital_expansion_allowed':False}))
            value,error=_read_performance(root,None)
            self.assertIsNone(error);self.assertEqual(value['measurement_status'],'partial');self.assertIsNone(value['net_pnl_usd'])
            path.write_text('{broken')
            value,error=_read_performance(root,None)
            self.assertIsNone(value);self.assertEqual(error,'alpaca_crypto_performance_invalid')
            value,error=_read_performance(root,'2026-01-01')
            self.assertIsNone(value);self.assertEqual(error,'alpaca_crypto_daily_performance_missing')

    def test_crypto_phase_one_contract_rejects_measured_or_invented_usd(self):
        from alpaca_snapshot import _read_performance
        import tempfile,json
        from pathlib import Path
        base={'schema_version':1,'report_scope':'owned_crypto_cycles','mode':'live','paper':False,
              'owner_id':'alpaca-investment-live','measurement_status':'partial','net_pnl_usd':None,
              'capital_expansion_allowed':False}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'performance-crypto-latest.json'
            for change in ({'measurement_status':'measured'},{'gross_strategy_pnl_usd':'999'},
                           {'fees_usd':'0'},{'net_pnl_usd':'1'},{'capital_expansion_allowed':True},
                           {'owner_id':'alpaca-investment-paper'}):
                with self.subTest(change=change):
                    path.write_text(json.dumps({**base,**change}))
                    value,error=_read_performance(root,None)
                    self.assertIsNone(value);self.assertEqual(error,'alpaca_crypto_performance_invalid')

    def test_crypto_daily_without_latest_cannot_fall_back_to_legacy_measured(self):
        from alpaca_snapshot import _read_performance
        import tempfile,json
        from pathlib import Path
        payload={'schema_version':1,'report_scope':'owned_crypto_cycles_daily','mode':'live','paper':False,
                 'owner_id':'alpaca-investment-live','measurement_status':'partial','net_pnl_usd':None,
                 'capital_expansion_allowed':False,'performance_day':'2026-01-01','observed_at':'2026-01-01T23:00:00Z'}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'performance-crypto-daily-2026-01-01.json').write_text(json.dumps(payload))
            (root/'performance-daily-2026-01-01.json').write_text(json.dumps({**payload,'measurement_status':'measured','net_pnl_usd':'999'}))
            (root/'performance-latest.json').write_text(json.dumps({'measurement_status':'measured'}))
            value,error=_read_performance(root,'2026-01-01')
            self.assertIsNone(error);self.assertEqual(value['measurement_status'],'partial');self.assertIsNone(value['net_pnl_usd'])
            value,error=_read_performance(root,None)
            self.assertIsNone(value);self.assertEqual(error,'alpaca_crypto_performance_invalid')

    def test_paper_fill_gross_does_not_deduct_signed_slippage_twice(self):
        from net_pnl import venue_net
        for slippage in ("0.30", "-0.25"):
            with self.subTest(slippage=slippage):
                performance = {**PERFORMANCE, "paper": True, "mode": "paper",
                    "gross_strategy_pnl_usd": "10", "slippage_included_in_gross_pnl": True,
                    "fees_usd": "0.20", "funding_or_borrow_usd": "0.10",
                    "slippage_usd": slippage, "gas_usd": "0.05",
                    "model_cost_usd": "0.50", "system_cost_usd": "1.00"}
                result = venue_net(self._builder()(performance, OBSERVATION, RISK))
                self.assertEqual(result["measurement_status"], "measured")
                self.assertEqual(result["net_pnl_usd"], "8.15")
                self.assertEqual(result.get("system_cost_usd"), "1.00")
                self.assertEqual(performance["gross_strategy_pnl_usd"], "10")

    def test_paper_unknown_slippage_basis_stays_partial(self):
        for basis in (None, False, "true"):
            with self.subTest(basis=basis):
                performance = {**PERFORMANCE, "paper": True,
                    "slippage_included_in_gross_pnl": basis,
                    "funding_or_borrow_usd": "0", "gas_usd": "0",
                    "model_cost_usd": "0", "system_cost_usd": "0"}
                result = self._builder()(performance, OBSERVATION, RISK)
                self.assertEqual(result["measurement_status"], "partial")

    def _builder(self):
        try:
            module = importlib.import_module("alpaca_snapshot")
        except ModuleNotFoundError as error:
            self.fail(f"Alpaca snapshot adapter is missing: {error}")
        builder = getattr(module, "build_alpaca_snapshot", None)
        if builder is None:
            self.fail("build_alpaca_snapshot is missing")
        return builder

    def test_snapshot_preserves_missing_costs_as_partial_not_zero(self):
        snapshot = self._builder()(PERFORMANCE, OBSERVATION, RISK)

        self.assertEqual(snapshot["venue"], "alpaca")
        self.assertEqual(snapshot["observed_at"], PERFORMANCE["observed_at"])
        self.assertEqual(snapshot["equity_usd"], "66.63")
        self.assertEqual(snapshot["free_cash_usd"], "0.00")
        self.assertEqual(snapshot["gross_pnl_usd"], "-0.14")
        self.assertEqual(snapshot["trading_fees_usd"], "0.01")
        self.assertIsNone(snapshot["funding_or_borrow_usd"])
        self.assertIsNone(snapshot["gas_usd"])
        self.assertIsNone(snapshot["model_cost_usd"])
        self.assertIsNone(snapshot["system_cost_usd"])
        self.assertEqual(snapshot["measurement_status"], "partial")
        self.assertEqual(snapshot["cost_evidence"], {})
        self.assertEqual(snapshot["source_receipt_ids"], PERFORMANCE["source_receipt_ids"])
        self.assertEqual(snapshot["risk"]["round_trips"], 1)
        self.assertEqual(snapshot["risk"]["drawdown_usd"], "0.15")

    def test_snapshot_becomes_measured_only_when_every_cost_is_explicit(self):
        performance = {
            **PERFORMANCE,
            "funding_or_borrow_usd": "0.00",
            "gas_usd": "0.00",
            "model_cost_usd": "0.00",
            "system_cost_usd": "0.00",
        }

        snapshot = self._builder()(performance, OBSERVATION, RISK)

        self.assertEqual(snapshot["measurement_status"], "measured")
        self.assertEqual(snapshot["funding_or_borrow_usd"], "0.00")
        self.assertEqual(snapshot["gas_usd"], "0.00")
        self.assertEqual(snapshot["model_cost_usd"], "0.00")

    def test_snapshot_uses_cumulative_round_trip_count_when_daily_pnl_is_delta(self):
        performance = {
            **PERFORMANCE,
            "completed_round_trips": 0,
            "completed_round_trips_total": 4,
        }

        snapshot = self._builder()(performance, OBSERVATION, RISK)

        self.assertEqual(snapshot["risk"]["round_trips"], 4)

    def test_daily_reader_does_not_fallback_to_new_day_latest(self):
        module = importlib.import_module("alpaca_snapshot")
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "performance-latest.json").write_text(json.dumps({
                "measurement_status": "measured",
                "observed_at": "2026-09-29T00:00:00Z",
                "gross_strategy_pnl_usd": "0",
                "source_receipt_ids": ["new-day-zero"],
            }), encoding="utf-8")

            result = module.read_alpaca_snapshot(
                state,
                performance_day="2026-09-28",
            )

        self.assertEqual(result, {
            "status": "unknown",
            "reason": "alpaca_daily_performance_missing",
        })

    def test_daily_reader_rejects_payload_day_timestamp_mismatch(self):
        module = importlib.import_module("alpaca_snapshot")
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "performance-daily-2026-09-28.json").write_text(json.dumps({
                **PERFORMANCE,
                "performance_day": "2026-09-28",
                "observed_at": "2026-09-29T00:00:00Z",
            }), encoding="utf-8")

            result = module.read_alpaca_snapshot(
                state,
                performance_day="2026-09-28",
            )

        self.assertEqual(result, {
            "status": "unknown",
            "reason": "alpaca_daily_performance_timestamp_mismatch",
        })

    def test_daily_reader_accepts_legacy_latest_only_when_its_day_matches(self):
        module = importlib.import_module("alpaca_snapshot")
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "performance-latest.json").write_text(json.dumps({
                **PERFORMANCE,
                "observed_at": "2026-09-28T23:59:00Z",
            }), encoding="utf-8")
            observation = {
                **OBSERVATION,
                "clock": {"observed_at": "2026-09-29T00:00:01Z"},
            }
            (state / "observation-latest.json").write_text(
                json.dumps(observation), encoding="utf-8"
            )
            (state / "risk-latest.json").write_text(json.dumps(RISK), encoding="utf-8")

            result = module.read_alpaca_snapshot(
                state,
                performance_day="2026-09-28",
            )

        self.assertEqual(result["gross_pnl_usd"], PERFORMANCE["gross_strategy_pnl_usd"])
        self.assertIn(
            "alpaca-account-readback:2026-09-29T00:00:01Z",
            result["source_receipt_ids"],
        )


if __name__ == "__main__":
    unittest.main()
