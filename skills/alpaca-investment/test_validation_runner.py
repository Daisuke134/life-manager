from __future__ import annotations

from datetime import date
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import validation_runner


def _report(report_id: str = "fresh-report") -> dict[str, object]:
    return {
        "report_id": report_id,
        "strategy_id": "alpaca-etf-126d-momentum-v1",
        "release_sha": "a" * 40,
        "card": {"strategy_id": "alpaca-etf-126d-momentum-v1"},
        "status": "measured",
        "decision": "paper",
        "holdout": {"trades": 14, "net_pnl_usd": "1.62", "max_drawdown_usd": "1.25"},
        "cost_model": {},
        "turnover": "14",
        "evidence_ids": ["alpaca://stock-bars/test"],
        "fresh": True,
        "observed_at": "2026-09-29T00:00:00Z",
        "expires_at": "2099-01-01T00:00:00Z",
    }


def _history(start: date, count: int = 2) -> dict[str, object]:
    rows = [
        {
            "t": f"{date.fromordinal(start.toordinal() + offset).isoformat()}T15:00:00Z",
            "o": "100",
            "c": "101",
        }
        for offset in range(count)
    ]
    return {
        "daily_bars": {symbol: rows for symbol in validation_runner.ETF_MOMENTUM_UNIVERSE},
        "completed_through_session": rows[-1]["t"][:10],
        "source_receipt_ids": [f"receipt-{start.isoformat()}"],
        "observed_at": "2026-09-29T00:00:00Z",
    }


class CryptoValidationReportTests(unittest.TestCase):
    def _history(self, count=900):
        from datetime import datetime, timedelta, timezone
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [{"t": (start + timedelta(minutes=5 * i)).isoformat(),
                 "o": str(100 + i % 20), "h": str(102 + i % 20),
                 "l": str(99 + i % 20), "c": str(101 + i % 20)} for i in range(count)]

    def test_long_history_requests_disjoint_six_hour_chunks_and_reuses_report_builder(self):
        from datetime import datetime, timedelta, timezone
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        def chunk(**kwargs):
            first, end = kwargs["start"], kwargs["end"]
            rows = [{"t": (first + timedelta(minutes=5 * i)).isoformat(),
                     "o": "100", "h": "102", "l": "99", "c": "101"}
                    for i in range(int((end-first).total_seconds()/300))]
            return {"crypto_history": rows, "quote_conversions": [],
                    "source_receipt_ids": ["source-" + first.isoformat()]}
        with patch.object(validation_runner, "read_crypto_validation_history", side_effect=chunk) as read, \
             patch.object(validation_runner, "build_crypto_reports_from_history", return_value=[{"fixture": True}]) as build:
            result = validation_runner.build_crypto_reports_for_period(
                start=start, end=start+timedelta(hours=13), observed_at="2026-01-05T00:00:00Z",
                credentials_path=Path("credentials"), cli_path=Path("alpaca"), release_sha="a"*40)
        self.assertEqual(read.call_count, 3)
        self.assertEqual([c.kwargs["start"] for c in read.call_args_list],
                         [start, start+timedelta(hours=6), start+timedelta(hours=12)])
        self.assertEqual(len(build.call_args.args[0]), 156)
        self.assertEqual(len(build.call_args.kwargs["source_receipt_ids"]), 3)
        self.assertEqual(result, [{"fixture": True}])

    def test_crypto_reports_use_real_feature_builder_and_common_evaluator(self):
        bars = self._history()
        fx = [{"timestamp": row["t"], "currency": "USDC", "rate": "0.99",
               "evidence_ref": "alpaca://fixture/fx"} for row in bars]
        reports = validation_runner.build_crypto_reports_from_history(
            bars, quote_conversions=fx, source_receipt_ids=["alpaca://fixture/btc"],
            release_sha="a" * 40, observed_at="2026-01-05T00:00:00Z")
        self.assertEqual(len(reports), 2)
        self.assertEqual({r["strategy_id"] for r in reports},
                         {"alpaca-btc-5m-reversion-400-v2", "alpaca-btc-5m-trend-400-v2"})
        for report in reports:
            self.assertEqual(report["release_sha"], "a" * 40)
            self.assertEqual(report["card"]["instruments"], ["BTC/USDC"])
            self.assertEqual(report["expires_at"], "2026-01-12T00:00:00Z")
            self.assertIn("alpaca://fixture/fx", report["source_receipt_ids"])
            self.assertIn("parameter_sensitivity", report)
            self.assertNotEqual(report.get("reason"), "quote_conversion_unknown")
            self.assertEqual(report["measurement_kind"], "modeled_validation")

    def test_two_btc_reports_can_share_market_sources_without_duplicate_evidence(self):
        from datetime import datetime, timezone
        from strategy_validation import select_strategy
        measured = {"status": "measured", "decision": "paper", "lookahead_detected": False,
                    "holdout": {"trades": 3, "net_pnl_usd": "2", "max_drawdown_usd": "1"},
                    "turnover": "3"}
        with patch.object(validation_runner, "validate_series",
                          side_effect=lambda card, *_args: {**measured, "strategy_id": card.strategy_id}):
            reports = validation_runner.build_crypto_reports_from_history(
                self._history(), quote_conversions=[], source_receipt_ids=["alpaca://fixture/btc"],
                release_sha="a"*40, observed_at=datetime.now(timezone.utc).isoformat())
        self.assertEqual(select_strategy(reports)["selection"], "selected")
        self.assertEqual(len({ref for report in reports for ref in report["evidence_ids"]}), 2)
        self.assertEqual(reports[0]["source_receipt_ids"], reports[1]["source_receipt_ids"])

    def test_unstable_v2_history_cannot_be_selected_as_profitable(self):
        from decimal import Decimal
        from strategy_validation import select_strategy
        bars=self._history(1200)
        for i,row in enumerate(bars):
            close=Decimal("100000" if i<800 else "100" if i<1199 else "100.02")
            row.update(o=str(close),h=str(close+Decimal(".01")),l=str(close-Decimal(".01")),c=str(close))
        fx=[{"timestamp": row["t"], "currency": "USDC", "rate": "1", "evidence_ref": "fixture-fx"}
            for row in bars]
        reports=validation_runner.build_crypto_reports_from_history(
            bars,quote_conversions=fx,source_receipt_ids=["fixture-source"],
            release_sha="a"*40,observed_at="2026-01-06T00:00:00Z")
        trend=next(report for report in reports if "trend" in report["strategy_id"])
        self.assertEqual(trend["status"],"unknown")
        self.assertEqual(trend["reason"],"indicator_history_unstable")
        self.assertIsNone(trend["net_pnl_usd"])
        self.assertEqual(select_strategy(reports)["selection"],"no_strategy")

    def test_insufficient_indicator_warmup_is_not_zero_dollar_profit(self):
        reports = validation_runner.build_crypto_reports_from_history(
            self._history()[:12], quote_conversions=[], source_receipt_ids=["alpaca://fixture/btc"],
            release_sha="a"*40, observed_at="2026-01-05T00:00:00Z")
        for report in reports:
            self.assertEqual(report["status"], "unknown")
            self.assertIsNone(report["net_pnl_usd"])
            self.assertIsNone(report["holdout"]["net_pnl_usd"])

    def test_crypto_reports_missing_fx_remain_unknown_and_not_selected(self):
        from strategy_validation import select_strategy
        reports = validation_runner.build_crypto_reports_from_history(
            self._history(), quote_conversions=[], source_receipt_ids=["alpaca://fixture/btc"],
            release_sha="a" * 40, observed_at="2026-01-05T00:00:00Z")
        for report in reports:
            self.assertEqual(report["status"], "unknown")
            self.assertEqual(report["decision"], "rejected")
            self.assertIsNone(report["net_pnl_usd"])
        self.assertEqual(select_strategy(reports)["strategy_id"], "NO_STRATEGY")

    def test_crypto_reports_reject_future_or_ambiguous_history_and_fx(self):
        bars = self._history()
        base = dict(quote_conversions=[], source_receipt_ids=["alpaca://fixture/btc"],
                    release_sha="a" * 40, observed_at="2026-01-05T00:00:00Z")
        for bad_bars, changes in ((bars + [bars[-1]], {}),
                                  (bars[::-1], {}),
                                  (bars, {"observed_at": bars[-1]["t"]}),
                                  (bars, {"source_receipt_ids": []}),
                                  (bars, {"release_sha": "main"}),
                                  (bars, {"quote_conversions": [{"timestamp": bars[0]["t"]}] * 2})):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    validation_runner.build_crypto_reports_from_history(bad_bars, **{**base, **changes})


class ValidationRunnerTests(unittest.TestCase):
    def test_real_report_builder_retains_modeled_benchmark_comparison(self):
        history = _history(date(2025, 1, 1), count=600)

        report = validation_runner.build_report_from_history(
            history["daily_bars"],
            source_receipt_ids=history["source_receipt_ids"],
            release_sha="a" * 40,
            observed_at=history["observed_at"],
            completed_through_session=history["completed_through_session"],
        )

        self.assertEqual(report["holdout"]["net_pnl_usd"], "0.40")
        self.assertIn("benchmark", report)
        self.assertEqual(report["benchmark"]["measurement_kind"], "modeled_reference_pnl")
        self.assertEqual(report["benchmark"]["holdout"]["net_pnl_usd"], "0.08")
        self.assertEqual(report["benchmark"]["holdout"]["excess_net_pnl_usd"], "0.32")
        self.assertEqual(report["evidence_ids"], ["receipt-2025-01-01"])

    def test_chunk_ranges_are_bounded_and_non_overlapping(self):
        ranges = list(validation_runner._chunk_ranges(date(2026, 1, 1), date(2026, 4, 1)))

        self.assertEqual(ranges, [
            (date(2026, 1, 1), date(2026, 3, 31)),
            (date(2026, 4, 1), date(2026, 4, 1)),
        ])

    def test_report_builder_adds_expiry_and_official_source_receipts(self):
        result = {"status": "measured", "holdout": {"trades": 1, "net_pnl_usd": "1", "max_drawdown_usd": "0"}}
        grid = {"gate": True, "positive_count": 9, "median_holdout_net_pnl_usd": "1", "grid": []}
        history = _history(date(2026, 9, 1))

        with patch.object(validation_runner, "simulate", return_value=result) as simulate, patch.object(
            validation_runner, "screen_grid", return_value=grid
        ) as screen:
            report = validation_runner.build_report_from_history(
                history["daily_bars"],
                source_receipt_ids=history["source_receipt_ids"],
                release_sha="a" * 40,
                observed_at=history["observed_at"],
                completed_through_session=history["completed_through_session"],
            )

        self.assertEqual(report["decision"], "paper")
        self.assertEqual(report["expires_at"], "2026-10-06T00:00:00Z")
        self.assertEqual(report["evidence_ids"], ["receipt-2026-09-01"])
        simulate.assert_called_once()
        screen.assert_called_once()

    def test_run_once_fetches_chunks_writes_report_and_refreshes_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports_path = root / "reports.json"
            selection_path = root / "selected-strategy.json"
            history = _history(date(2026, 1, 1))
            with patch.object(
                validation_runner, "read_etf_daily_history", return_value=history
            ) as read_history, patch.object(
                validation_runner, "build_report_from_history", return_value=_report()
            ) as build, patch.object(
                validation_runner, "build_crypto_reports_for_period", return_value=[_report("btc-fixture")]
            ) as crypto, patch.object(
                validation_runner, "provision_selection", return_value={"status": "created"}
            ) as provision:
                result = validation_runner.run_once(
                    reports_path=reports_path,
                    selection_path=selection_path,
                    credentials_path=Path("credentials"),
                    cli_path=Path("alpaca"),
                    release_sha="b" * 40,
                    start_date=date(2026, 1, 1),
                    end_date=date(2026, 1, 30),
                )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(read_history.call_count, 1)
            build.assert_called_once()
            crypto.assert_called_once()
            self.assertEqual(len(json.loads(reports_path.read_text())["reports"]), 2)
            provision.assert_called_once_with(
                selection_path,
                reports_path,
                runtime_release_sha="b" * 40,
                refresh=True,
            )

    def test_run_once_provisions_independent_live_and_paper_selection_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports_path = root / "reports.json"
            live_selection = root / "live" / "selected-strategy.json"
            paper_selection = root / "paper" / "selected-strategy.json"
            history = _history(date(2026, 1, 1))
            with patch.object(
                validation_runner, "read_etf_daily_history", return_value=history
            ), patch.object(
                validation_runner, "build_report_from_history", return_value=_report()
            ), patch.object(
                validation_runner, "build_crypto_reports_for_period", return_value=[]
            ), patch.object(
                validation_runner, "provision_selection", return_value={"status": "created"}
            ) as provision:
                result = validation_runner.run_once(
                    reports_path=reports_path,
                    selection_paths=[live_selection, paper_selection],
                    credentials_path=Path("credentials"),
                    cli_path=Path("alpaca"),
                    release_sha="b" * 40,
                    start_date=date(2026, 1, 1),
                    end_date=date(2026, 1, 30),
                )

            self.assertEqual(result["selection_statuses"], ["created", "created"])
            self.assertEqual(provision.call_count, 2)
            self.assertEqual(provision.call_args_list[0].args[0], live_selection)
            self.assertEqual(provision.call_args_list[1].args[0], paper_selection)

    def test_btc_history_failure_keeps_legacy_report_without_claiming_full_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = _history(date(2026, 1, 1))
            with patch.object(validation_runner, "read_etf_daily_history", return_value=history), \
                 patch.object(validation_runner, "build_report_from_history", return_value=_report()), \
                 patch.object(validation_runner, "build_crypto_reports_for_period",
                              side_effect=ValueError("alpaca_crypto_validation_history_invalid")), \
                 patch.object(validation_runner, "provision_selection", return_value={"status": "existing"}) as provision:
                result = validation_runner.run_once(
                    reports_path=root/"reports.json", selection_path=root/"selected-strategy.json",
                    credentials_path=Path("credentials"), cli_path=Path("alpaca"),
                    release_sha="b"*40, start_date=date(2026,1,1), end_date=date(2026,1,30))
            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["crypto_report_count"], 0)
            self.assertEqual(result["crypto_error_class"], "alpaca_crypto_validation_history_invalid")
            self.assertEqual(len(json.loads((root/"reports.json").read_text())["reports"]), 1)
            provision.assert_called_once()

    def test_write_reports_is_atomic_and_private(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "reports.json"

            validation_runner.write_reports(path, _report())

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["reports"][0]["report_id"], "fresh-report")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)

    def test_runner_has_no_order_submission_boundary(self):
        self.assertNotIn("submit_order", validation_runner.__dict__)
        self.assertNotIn("fund", validation_runner.__dict__)


if __name__ == "__main__":
    unittest.main()
