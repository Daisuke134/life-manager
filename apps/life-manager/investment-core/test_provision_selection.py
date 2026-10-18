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
    def test_owned_position_preserves_canonical_policy_and_allows_only_same_policy_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports, destination = root / "reports.json", root / "selected-strategy.json"
            reports.write_text(json.dumps([_report()]))
            provision_selection(destination, reports)
            marker = {"status": "open", "strategy_id": "alpaca-etf-126d-momentum-v1",
                      "owner_id": "alpaca-investment-paper", "symbol": "QQQ", "position_qty": "1",
                      "client_order_id": "lm-ai-"+"1"*24, "provider_order_id": "provider-entry",
                      "decision_session": "2026-10-18"}
            (root / "etf-owned-position.json").write_text(json.dumps(marker))
            changed = _report(report_id="changed-rules")
            changed["card"]["entry_rules"] = {"all": ["close > 1"]}
            reports.write_text(json.dumps([changed]))
            before = destination.read_bytes()
            self.assertEqual(provision_selection(destination, reports, refresh=True)["status"], "existing")
            self.assertEqual(destination.read_bytes(), before)
            reports.write_text(json.dumps([_report(report_id="same-policy-fresh")]))
            self.assertEqual(provision_selection(destination, reports, refresh=True)["status"], "created")
            self.assertEqual(json.loads(destination.read_text())["report_id"], "same-policy-fresh")

    def test_planned_intent_prevents_policy_replacement_before_broker_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports, destination = root / "reports.json", root / "selected-strategy.json"
            reports.write_text(json.dumps([_report()]))
            provision_selection(destination, reports)
            (root / "receipts.jsonl").write_text(json.dumps({
                "receipt_type": "effect_intent", "effect_id": "pending", "status": "planned"})+"\n")
            changed = _report(report_id="changed-rules")
            changed["card"]["entry_rules"] = {"all": ["close > 1"]}
            reports.write_text(json.dumps([changed]))
            before = destination.read_bytes()
            self.assertEqual(provision_selection(destination, reports, refresh=True)["status"], "existing")
            self.assertEqual(destination.read_bytes(), before)
            self.assertTrue((root / ".control.lock").exists())

    def test_corrupt_ownership_is_an_error_even_when_selection_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports, destination = root/"reports.json", root/"selected-strategy.json"
            reports.write_text(json.dumps([_report()]))
            provision_selection(destination, reports)
            (root/"etf-owned-position.json").write_text("{}")
            with self.assertRaisesRegex(SelectionProvisionError, "ownership_state_invalid"):
                provision_selection(destination, reports, refresh=True)

    def test_closed_marker_without_matching_official_outcome_is_not_flat(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports, destination = root/"reports.json", root/"selected-strategy.json"
            reports.write_text(json.dumps([_report()]))
            provision_selection(destination, reports)
            marker = {"status": "closed", "strategy_id": "alpaca-etf-126d-momentum-v1",
                      "owner_id": "alpaca-investment-paper", "symbol": "QQQ", "position_qty": "1",
                      "client_order_id": "lm-ai-"+"1"*24, "provider_order_id": "provider-entry",
                      "decision_session": "2026-10-18", "close_provider_order_id": "unproven",
                      "close_source_receipt_ids": [None]}
            (root/"etf-owned-position.json").write_text(json.dumps(marker))
            with self.assertRaisesRegex(SelectionProvisionError, "owned_close_evidence_unknown"):
                provision_selection(destination, reports, refresh=True)

    def test_matching_official_closed_fill_allows_flat_policy_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports, destination = root/"reports.json", root/"selected-strategy.json"
            reports.write_text(json.dumps([_report()]))
            provision_selection(destination, reports)
            client = "lm-ai-"+"2"*24
            marker = {"status": "closed", "strategy_id": "alpaca-etf-126d-momentum-v1",
                      "owner_id": "alpaca-investment-paper", "symbol": "QQQ", "position_qty": "1",
                      "client_order_id": "lm-ai-"+"1"*24, "provider_order_id": "entry",
                      "decision_session": "2026-10-18", "close_provider_order_id": "exit",
                      "close_client_order_id": client, "close_filled_avg_price": "101",
                      "close_source_receipt_ids": ["official-close-source"],
                      "close_account_cash_usd": "101", "close_account_equity_usd": "101",
                      "close_account_readback_at": "2026-10-18T00:00:00Z"}
            (root/"etf-owned-position.json").write_text(json.dumps(marker))
            broker = {"id": "exit", "status": "filled", "client_order_id": client,
                      "symbol": "QQQ", "side": "sell", "type": "market", "time_in_force": "day",
                      "filled_qty": "1", "filled_avg_price": "101"}
            intent = {"receipt_type": "effect_intent", "effect_id": "close-effect", "status": "planned",
                      "client_order_id": client, "owner_id": marker["owner_id"],
                      "strategy_id": marker["strategy_id"], "mode": "paper",
                      "order": {"symbol": "QQQ", "side": "sell"}}
            outcome = {"receipt_type": "outcome", "outcome": "broker_reconciled", "mode": "paper",
                       "effect_id": "close-effect", "client_order_id": client, "broker_receipt_id": "exit",
                       "broker": broker, "strategy_receipt": {"receipt": marker,
                           "account_readback": {"account": {"cash": "101", "equity": "101"},
                               "positions": [], "clock": {"observed_at": "2026-10-18T00:00:00Z"}}}}
            ledger = root/"receipts.jsonl"
            ledger.write_text(json.dumps(intent)+"\n"+json.dumps(outcome)+"\n")
            changed = _report(report_id="flat-next-policy")
            changed["card"]["entry_rules"] = {"all": ["close > 1"]}
            reports.write_text(json.dumps([changed]))
            self.assertEqual(provision_selection(destination, reports, refresh=True)["status"], "created")
            for mutation in ("wrong-mode", "missing-intent", "wrong-qty", "missing-account"):
                with self.subTest(mutation=mutation):
                    altered = json.loads(json.dumps(outcome))
                    altered_intent = dict(intent)
                    if mutation == "wrong-mode":
                        altered["mode"] = "live"
                    elif mutation == "missing-intent":
                        altered_intent = {}
                    elif mutation == "wrong-qty":
                        altered["broker"]["filled_qty"] = "2"
                    else:
                        altered["strategy_receipt"].pop("account_readback")
                    ledger.write_text(json.dumps(altered_intent)+"\n"+json.dumps(altered)+"\n")
                    with self.assertRaisesRegex(SelectionProvisionError, "owned_close_evidence_unknown"):
                        provision_selection(destination, reports, refresh=True)

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
