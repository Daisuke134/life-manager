from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path

from etf_momentum import strategy_card
from provision_selection import SelectionProvisionError, provision_selection


def _report(*, net: str = "1.62", report_id: str = "report-etf") -> dict[str, object]:
    card = strategy_card().to_mapping()
    return {
        "report_id": report_id,
        "strategy_id": card["strategy_id"],
        "release_sha": "a" * 40,
        "card": card,
        "status": "measured",
        "decision": "paper",
        "lookahead_detected": False,
        "holdout": {
            "trades": 14,
            "net_pnl_usd": net,
            "max_drawdown_usd": "1.25",
        },
        "cost_model": card["cost_model"],
        "turnover": "14",
        "evidence_ids": ["alpaca-paper://stock-bars/iex/split/20200929-20260928"],
        "fresh": True,
        "observed_at": "2026-09-29T00:00:00Z",
        "expires_at": "2099-01-01T00:00:00Z",
    }


class ProvisionSelectionTests(unittest.TestCase):
    def test_selected_report_is_written_as_release_pinned_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports.json"
            destination = root / "state" / "selected-strategy.json"
            reports.write_text(json.dumps([_report()]), encoding="utf-8")

            result = provision_selection(destination, reports)

            self.assertEqual(result["status"], "created")
            payload = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(payload["selection"], "selected")
            self.assertEqual(payload["strategy_id"], "alpaca-etf-126d-momentum-v1")
            self.assertEqual(payload["report_id"], "report-etf")
            self.assertEqual(payload["release_sha"], "a" * 40)
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(destination.parent.stat().st_mode), 0o700)

    def test_handoff_release_sha_overrides_evaluation_sha_and_preserves_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports.json"
            destination = root / "state" / "selected-strategy.json"
            reports.write_text(json.dumps([_report()]), encoding="utf-8")

            provision_selection(destination, reports, runtime_release_sha="b" * 40)

            payload = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(payload["release_sha"], "b" * 40)
            self.assertEqual(payload["report_release_sha"], "a" * 40)

    def test_rejected_reports_do_not_create_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports.json"
            destination = root / "selected-strategy.json"
            reports.write_text(json.dumps([_report(net="0")]), encoding="utf-8")

            with self.assertRaisesRegex(SelectionProvisionError, "no_strategy_selected"):
                provision_selection(destination, reports)

            self.assertFalse(destination.exists())

    def test_unbounded_report_does_not_create_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports.json"
            destination = root / "selected-strategy.json"
            report = _report()
            del report["expires_at"]
            reports.write_text(json.dumps([report]), encoding="utf-8")

            with self.assertRaisesRegex(SelectionProvisionError, "validation_report_expiry_missing"):
                provision_selection(destination, reports)

            self.assertFalse(destination.exists())

    def test_existing_selection_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports.json"
            destination = root / "selected-strategy.json"
            reports.write_text(json.dumps([_report()]), encoding="utf-8")
            provision_selection(destination, reports)
            before = destination.read_bytes()

            reports.write_text(json.dumps([_report(report_id="different")]), encoding="utf-8")
            result = provision_selection(destination, reports)

            self.assertEqual(result["status"], "existing")
            self.assertEqual(destination.read_bytes(), before)

    def test_refresh_replaces_existing_selection_with_fresh_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports.json"
            destination = root / "selected-strategy.json"
            reports.write_text(json.dumps([_report()]), encoding="utf-8")
            provision_selection(destination, reports, runtime_release_sha="a" * 40)

            reports.write_text(
                json.dumps([_report(report_id="refreshed-report")]),
                encoding="utf-8",
            )
            result = provision_selection(
                destination,
                reports,
                runtime_release_sha="b" * 40,
                refresh=True,
            )

            self.assertEqual(result["status"], "created")
            payload = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(payload["report_id"], "refreshed-report")
            self.assertEqual(payload["release_sha"], "b" * 40)

    def test_refresh_keeps_existing_selection_when_new_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports.json"
            destination = root / "selected-strategy.json"
            reports.write_text(json.dumps([_report()]), encoding="utf-8")
            provision_selection(destination, reports)
            before = destination.read_bytes()

            reports.write_text(
                json.dumps([_report(report_id="rejected", net="0")]),
                encoding="utf-8",
            )
            result = provision_selection(destination, reports, refresh=True)

            self.assertEqual(result["status"], "existing")
            self.assertEqual(destination.read_bytes(), before)

    def test_expired_selection_is_replaced_by_fresh_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports.json"
            destination = root / "selected-strategy.json"
            reports.write_text(json.dumps([_report()]), encoding="utf-8")
            provision_selection(destination, reports, runtime_release_sha="a" * 40)

            expired = json.loads(destination.read_text(encoding="utf-8"))
            expired["expires_at"] = "2020-01-01T00:00:00Z"
            destination.write_text(json.dumps(expired), encoding="utf-8")
            reports.write_text(
                json.dumps([_report(report_id="fresh-report")]),
                encoding="utf-8",
            )

            result = provision_selection(destination, reports, runtime_release_sha="b" * 40)

            self.assertEqual(result["status"], "created")
            payload = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(payload["report_id"], "fresh-report")
            self.assertEqual(payload["release_sha"], "b" * 40)

    def test_invalid_existing_selection_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports.json"
            destination = root / "selected-strategy.json"
            reports.write_text(json.dumps([_report()]), encoding="utf-8")
            destination.write_text('{"selection":"selected"}', encoding="utf-8")
            before = destination.read_bytes()

            with self.assertRaisesRegex(SelectionProvisionError, "existing_selection_invalid"):
                provision_selection(destination, reports)

            self.assertEqual(destination.read_bytes(), before)

    def test_selection_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports.json"
            destination = root / "selected-strategy.json"
            target = root / "target.json"
            reports.write_text(json.dumps([_report()]), encoding="utf-8")
            target.write_text("{}", encoding="utf-8")
            destination.symlink_to(target)

            with self.assertRaisesRegex(SelectionProvisionError, "selection_symlink_refused"):
                provision_selection(destination, reports)


if __name__ == "__main__":
    unittest.main()
