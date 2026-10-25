from __future__ import annotations

import json
import stat
import subprocess
import sys
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
        "benchmark": {
            "symbol": "SPY",
            "method": "buy_and_hold",
            "measurement_kind": "modeled_reference_pnl",
            "status": "measured",
            "holdout": {
                "status": "measured",
                "net_pnl_usd": "0.00",
                "strategy_net_pnl_usd": net,
                "excess_net_pnl_usd": net,
            },
        },
        "cost_model": card["cost_model"],
        "turnover": "14",
        "evidence_ids": ["alpaca-paper://stock-bars/iex/split/20200929-20260928"],
        "fresh": True,
        "observed_at": "2026-09-29T00:00:00Z",
        "expires_at": "2099-01-01T00:00:00Z",
    }


def _crypto_closed_fixture(root: Path, *, no_fill: bool):
    from provision_selection import _effects
    from crypto_ownership_proof import close_fill_proof_from_rows, entry_fill_proof_from_rows
    from strategy_policy import candidate_cards
    mode,owner='paper','alpaca-investment-paper'
    card=candidate_cards()['alpaca-btc-5m-trend-400-v2']
    decision={'action':'ENTER','mode':mode,'owner_id':owner,'strategy_id':card.strategy_id,
              'policy_card':card.to_mapping(),'release_sha':'a'*40,'observed_at':'2026-01-01T04:00:00Z'}
    order={'asset_class':'crypto','symbol':'BTC/USDC','side':'buy','type':'market','time_in_force':'gtc','notional_usd':'10'}
    ledger=root/'receipts.jsonl';entry=_effects.seal(ledger,decision,order);_effects.mark_started(ledger,entry)
    buy={'id':'official-entry','client_order_id':entry['client_order_id'],'symbol':'BTCUSDC',
         'side':'buy','type':'market','time_in_force':'gtc','status':'rejected' if no_fill else 'filled',
         'filled_qty':'0' if no_fill else '0.05','filled_avg_price':None if no_fill else '200',
         'submitted_at':'2026-01-01T04:00:00Z','filled_at':None if no_fill else '2026-01-01T04:00:01Z'}
    _effects.reconcile_started(ledger,lambda _:buy)
    owned={'status':'closed' if no_fill else 'closing','symbol':'BTCUSD',
           'entry_effect_id':entry['effect_id'],'entry_client_order_id':entry['client_order_id'],
           'entry_filled_qty':buy['filled_qty']}
    account={'mode':mode,'paper':True,'account':{'cash':'0','equity':'100'},'positions':[],
             'clock':{'observed_at':'2026-01-01T04:15:02Z'}}
    if no_fill:
        _effects.record_no_fill_account_receipt(ledger,owned,buy,account,mode=mode,owner_id=owner)
    else:
        owned.update(owned_qty='0.05',status='open')
        acquired={**account,'clock':{'observed_at':'2026-01-01T04:00:02Z'},
                  'positions':[{'symbol':'BTCUSDC','qty':'0.05'}]}
        entry_proof=entry_fill_proof_from_rows(_effects._rows(ledger),owned,buy,acquired,mode=mode,owner_id=owner)
        _effects.reconcile_started(ledger,lambda _:buy,on_reconciled=lambda *_:entry_proof)
        owned['status']='closing'
        sell_decision={'action':'EXIT','mode':mode,'owner_id':owner,'strategy_id':card.strategy_id,
            'release_sha':'a'*40,'observed_at':'2026-01-01T04:15:00Z','position_qty':'0.05',
            'entry_effect_id':entry['effect_id'],'entry_client_order_id':entry['client_order_id'],
            'entry_provider_order_id':buy['id'],'entry_price':'200','entry_timestamp':buy['filled_at']}
        exit_order={'asset_class':'crypto','symbol':'BTC/USDC','side':'sell','type':'market','time_in_force':'gtc','qty':'0.05'}
        close=_effects.seal(ledger,sell_decision,exit_order);_effects.mark_started(ledger,close)
        owned.update(close_effect_id=close['effect_id'],close_client_order_id=close['client_order_id'])
        sell={**buy,'id':'official-exit','client_order_id':close['client_order_id'],'side':'sell',
              'filled_avg_price':'210','submitted_at':'2026-01-01T04:15:00Z','filled_at':'2026-01-01T04:15:01Z'}
        proof=close_fill_proof_from_rows(_effects._rows(ledger),owned,sell,account,mode=mode,owner_id=owner)
        _effects.reconcile_started(ledger,lambda _:sell,on_reconciled=lambda *_:proof)
        owned['status']='closed'
    (root/'live-owned-position.json').write_text(json.dumps(owned))


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

    def test_known_positive_fill_with_legacy_zero_outcome_keeps_policy_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            reports,destination=root/'reports.json',root/'selected-strategy.json'
            reports.write_text(json.dumps([_report()]))
            provision_selection(destination,reports)
            rows=[{'receipt_type':'effect_intent','effect_id':'pending','status':'planned'},
                  {'receipt_type':'effect_intent','effect_id':'pending','status':'reconciliation_pending',
                   'broker_status':'canceled','filled_qty':'0.01'},
                  {'receipt_type':'outcome','effect_id':'pending','outcome':'broker_terminal_failure',
                   'broker':{'status':'canceled','filled_qty':'0'}}]
            (root/'receipts.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            changed=_report(report_id='changed-rules')
            changed['card']['entry_rules']={'all':['close > 1']}
            reports.write_text(json.dumps([changed]))
            before=destination.read_bytes()
            self.assertEqual(provision_selection(destination,reports,refresh=True)['status'],'existing')
            self.assertEqual(destination.read_bytes(),before)

    def test_core_guard_keeps_unproven_crypto_close_on_the_shared_contract(self):
        from provision_selection import _effects
        from crypto_ownership_proof import ReconciliationPending
        self.assertIs(_effects.ReconciliationPending,ReconciliationPending)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            reports,destination=root/'reports.json',root/'selected-strategy.json'
            reports.write_text(json.dumps([_report()]))
            provision_selection(destination,reports)
            sealed=_effects.seal(root/'receipts.jsonl',{
                'action':'EXIT','mode':'paper','owner_id':'alpaca-investment-paper',
                'strategy_id':'alpaca-btc-5m-trend-400-v2'},
                {'asset_class':'crypto','side':'sell','symbol':'BTC/USDC','qty':'0.01',
                 'type':'market','time_in_force':'gtc'})
            _effects.mark_started(root/'receipts.jsonl',sealed)
            _effects.reconcile_started(root/'receipts.jsonl',lambda _: {
                'id':'official-order','client_order_id':sealed['client_order_id'],
                'symbol':'BTCUSDC','side':'sell','status':'filled','filled_qty':'0.01'})
            self.assertEqual(_effects.unresolved_intent_count(root/'receipts.jsonl'),1)
            changed=_report(report_id='changed-rules')
            changed['card']['entry_rules']={'all':['close > 1']}
            reports.write_text(json.dumps([changed]))
            before=destination.read_bytes()
            self.assertEqual(provision_selection(destination,reports,refresh=True)['status'],'existing')
            self.assertEqual(destination.read_bytes(),before)

    def test_recorded_crypto_close_or_no_fill_allows_flat_policy_refresh(self):
        for no_fill in (False,True):
            with self.subTest(no_fill=no_fill),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);reports,destination=root/'reports.json',root/'selected-strategy.json'
                reports.write_text(json.dumps([_report()]))
                provision_selection(destination,reports)
                _crypto_closed_fixture(root,no_fill=no_fill)
                changed=_report(report_id='changed-rules')
                changed['card']['entry_rules']={'all':['close > 1']}
                reports.write_text(json.dumps([changed]))
                self.assertEqual(provision_selection(destination,reports,refresh=True)['status'],'created')
                self.assertEqual(json.loads(destination.read_text())['report_id'],'changed-rules')

    def test_crypto_closed_symbol_mismatch_never_grants_policy_refresh(self):
        for no_fill in (False,True):
            with self.subTest(no_fill=no_fill),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);reports,destination=root/'reports.json',root/'selected-strategy.json'
                reports.write_text(json.dumps([_report()]))
                provision_selection(destination,reports)
                _crypto_closed_fixture(root,no_fill=no_fill)
                marker=root/'live-owned-position.json'
                value=json.loads(marker.read_text());value['symbol']='ETHUSD';marker.write_text(json.dumps(value))
                changed=_report(report_id='changed-rules');changed['card']['entry_rules']={'all':['close > 1']}
                reports.write_text(json.dumps([changed]))
                before=destination.read_bytes()
                with self.assertRaisesRegex(SelectionProvisionError,'owned_close_evidence_unknown'):
                    provision_selection(destination,reports,refresh=True)
                self.assertEqual(destination.read_bytes(),before)

    def test_unproven_crypto_closed_marker_is_not_a_flat_policy_permission(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);reports,destination=root/'reports.json',root/'selected-strategy.json'
            reports.write_text(json.dumps([_report()]))
            provision_selection(destination,reports)
            (root/'live-owned-position.json').write_text(json.dumps({'status':'closed','symbol':'BTCUSD'}))
            before=destination.read_bytes()
            with self.assertRaisesRegex(SelectionProvisionError,'owned_close_evidence_unknown'):
                provision_selection(destination,reports,refresh=True)
            self.assertEqual(destination.read_bytes(),before)

    def test_known_live_close_evidence_blocker_is_held_without_rewriting_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports, destination = root / "reports.json", root / "selected-strategy.json"
            reports.write_text(json.dumps([_report()]), encoding="utf-8")
            provision_selection(destination, reports, runtime_release_sha="a" * 40)
            before = destination.read_bytes()
            (root / "live-owned-position.json").write_text(
                json.dumps({"status": "closed", "symbol": "BTCUSD"}),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("provision_selection.py")),
                    "--path", str(destination),
                    "--reports", str(reports),
                    "--release-sha", "b" * 40,
                    "--refresh",
                    "--hold-on-known-blocker",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(result.stdout),
                {
                    "next_action": "reconcile_selection_evidence",
                    "path": str(destination),
                    "reason": "owned_close_evidence_unknown",
                    "status": "held",
                },
            )
            self.assertEqual(destination.read_bytes(), before)

    def test_known_hold_flag_does_not_mask_corrupt_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports, destination = root / "reports.json", root / "selected-strategy.json"
            reports.write_text(json.dumps([_report()]), encoding="utf-8")
            provision_selection(destination, reports, runtime_release_sha="a" * 40)
            before = destination.read_bytes()
            (root / "etf-owned-position.json").write_text("{}", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("provision_selection.py")),
                    "--path", str(destination),
                    "--reports", str(reports),
                    "--release-sha", "b" * 40,
                    "--refresh",
                    "--hold-on-known-blocker",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["error"], "ownership_state_invalid")
            self.assertEqual(destination.read_bytes(), before)

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

    def test_all_legacy_seal_callers_hold_the_shared_control_fence(self):
        import ast
        repo = Path(__file__).resolve().parents[3]
        for folder in (repo/"skills/alpaca-investment", Path(__file__).resolve().parent):
            for name in ("live_canary.py", "live_close.py"):
                path = folder/name
                def walk(node, held=False):
                    if isinstance(node, ast.With):
                        held = held or any(isinstance(item.context_expr, ast.Call)
                            and isinstance(item.context_expr.func, ast.Name)
                            and item.context_expr.func.id == "control_fence" for item in node.items)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "seal":
                        self.assertTrue(held, str(path))
                    for child in ast.iter_child_nodes(node):
                        walk(child, held)
                walk(ast.parse(path.read_text()))

    def test_valid_etf_report_is_not_hidden_by_rejected_btc_report(self):
        from strategy_policy import candidate_cards
        from strategy_validation import select_strategy

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports.json"
            destination = root / "selected-strategy.json"
            etf = _report(report_id="positive-etf")
            btc_card = candidate_cards()["alpaca-btc-5m-reversion-400-v2"].to_mapping()
            btc = _report(net="-0.69", report_id="rejected-btc")
            btc.update({
                "strategy_id": btc_card["strategy_id"],
                "card": btc_card,
                "decision": "rejected",
                "holdout": {"trades": 11, "net_pnl_usd": "-0.69",
                            "max_drawdown_usd": "0.69"},
                "cost_model": btc_card["cost_model"],
                "benchmark": None,
                "evidence_ids": ["alpaca-paper://crypto-bars/rejected-btc"],
                "turnover": "11",
            })
            reports.write_text(json.dumps([etf, btc]), encoding="utf-8")

            self.assertEqual(
                select_strategy([etf, btc])["strategy_id"],
                "alpaca-etf-126d-momentum-v1",
            )

            result = provision_selection(destination, reports)

            self.assertEqual(result["status"], "created")
            selection = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(selection["selection"], "selected")
            self.assertEqual(selection["strategy_id"], "alpaca-etf-126d-momentum-v1")
            self.assertEqual(selection["report_id"], "positive-etf")

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
            self.assertEqual(payload["benchmark"]["holdout"]["excess_net_pnl_usd"], "1.62")
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

    def test_refresh_expires_existing_selection_when_new_report_is_rejected(self):
        from datetime import datetime, timezone
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
            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("provision_selection.py")),
                    "--path", str(destination),
                    "--reports", str(reports),
                    "--release-sha", "b" * 40,
                    "--refresh",
                    "--hold-on-known-blocker",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "expired")
            payload = json.loads(destination.read_text(encoding="utf-8"))
            expires_at = datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))
            self.assertLessEqual(expires_at, datetime.now(timezone.utc))
            self.assertNotEqual(destination.read_bytes(), before)
            self.assertEqual(payload["report_id"], "report-etf")

    def test_no_strategy_without_existing_selection_is_held(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports.json"
            destination = root / "selected-strategy.json"
            reports.write_text(json.dumps([_report(report_id="rejected", net="0")]), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("provision_selection.py")),
                    "--path", str(destination),
                    "--reports", str(reports),
                    "--release-sha", "b" * 40,
                    "--refresh",
                    "--hold-on-known-blocker",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["reason"], "no_strategy_selected")
            self.assertEqual(json.loads(result.stdout)["status"], "held")
            self.assertFalse(destination.exists())

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
