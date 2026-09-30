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


class ValidationRunnerTests(unittest.TestCase):
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
