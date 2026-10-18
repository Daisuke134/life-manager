"""Owned-policy contract fixtures; no provider or production state is used."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from contextlib import ExitStack, contextmanager, redirect_stdout
from io import StringIO

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import effect_store
import allocator
import alpaca_cli
import position_manager
from strategy_policy import candidate_cards


def seed(root: Path, mode: str = "live", decision_changes=None, broker_id="provider-entry"):
    owner = f"alpaca-investment-{mode}"
    card = candidate_cards()["alpaca-btc-5m-trend-v1"]
    decision = {"action": "ENTER", "mode": mode, "owner_id": owner,
                "strategy_id": card.strategy_id, "policy_card": card.to_mapping(),
                "release_sha": "a"*40, "observed_at": "2026-01-01T04:00:00Z"}
    if decision_changes:
        decision.update(decision_changes)
    order = {"asset_class": "crypto", "notional_usd": "10.00", "side": "buy",
             "symbol": "BTC/USDC", "time_in_force": "gtc", "type": "market"}
    ledger = root / "receipts.jsonl"
    sealed = effect_store.seal(ledger, decision, order)
    effect_store.mark_started(ledger, sealed)
    broker = {"id": broker_id, "client_order_id": sealed["client_order_id"],
              "status": "filled", "symbol": "BTC/USDC", "side": "buy", "type": "market",
              "time_in_force": "gtc", "filled_qty": "0.05", "filled_avg_price": "200",
              "submitted_at": "2026-01-01T04:00:00Z", "filled_at": "2026-01-01T04:00:30Z"}
    effect_store.reconcile_started(ledger, lambda client: copy.deepcopy(broker))
    ownership = {"status": "open", "symbol": "BTCUSD", "entry_effect_id": sealed["effect_id"],
                 "entry_client_order_id": sealed["client_order_id"], "entry_filled_qty": "0.05",
                 "owned_qty": "0.05", "entry_timestamp": "2026-01-01T04:00:00Z"}
    (root / "live-owned-position.json").write_text(json.dumps(ownership))
    other = candidate_cards()["alpaca-btc-5m-reversion-v1"]
    (root / "selected-strategy.json").write_text(json.dumps({
        "strategy_id": other.strategy_id, "release_sha": "b"*40, "card": other.to_mapping(),
        "expires_at": "2020-01-01T00:00:00Z", "selection": "selected", "report_id": "expired-other"}))
    return ownership, owner


def snapshot(mode):
    start = datetime(2026,1,1,tzinfo=timezone.utc)
    bars = [{"t": (start+timedelta(minutes=5*i)).isoformat(), "o":str(100+i),
             "h":str(101+i), "l":str(99+i), "c":str(100+i)} for i in range(51)]
    clock = "2026-01-01T04:15:00Z"
    state = {"mode":mode, "positions":1, "open_orders":0, "unresolved_intents":0,
             "risk":{"allocated_capital_usd":"10"}, "clock":{"timestamp":clock},
             "crypto_history":{"BTC/USDC":bars},
             "crypto":[{"symbol":"BTC/USDC","bid":"149.99","ask":"150","quote_at":clock}]}
    observation = {"positions":[{"symbol":"BTCUSD","qty":"0.05","avg_entry_price":"100"}]}
    return state, observation


class OwnedPolicyTests(unittest.TestCase):
    def test_new_entry_freezes_the_canonical_card_with_mode_and_owner(self):
        from test_etf_allocator import _snapshot, _candidate
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            card=candidate_cards()["alpaca-btc-5m-trend-400-v2"]
            (root/"selected-strategy.json").write_text(json.dumps({
                "selection":"selected","report_id":"entry-fixture","strategy_id":card.strategy_id,
                "release_sha":"a"*40,"card":card.to_mapping(),"expires_at":"2099-01-01T00:00:00Z"}))
            candidate={**_candidate("BTC/USDC"),"asset_class":"crypto","candidate_ref":"crypto://BTC/USDC"}
            policy={"action":"ENTER","strategy_id":card.strategy_id,"signal_inputs":{},
                    "reason":"signal_entry","expected_cost_usd":"0.06"}
            with patch.dict(os.environ,{"LIFE_MANAGER_INVESTMENT_OWNER_ID":"alpaca-investment-paper"}), \
                 patch.object(allocator,"evaluate",return_value=policy):
                decision=allocator.choose(_snapshot("paper"),[candidate],root,Path("unused"),root)
            self.assertTrue(decision["approved"],decision)
            self.assertEqual(decision["owner_id"],"alpaca-investment-paper")
            self.assertEqual(decision["mode"],"paper")
            self.assertEqual(decision["policy_card"],card.to_mapping())
            policy["action"]="HOLD"
            with patch.dict(os.environ,{"LIFE_MANAGER_INVESTMENT_OWNER_ID":"alpaca-investment-paper"}), \
                 patch.object(allocator,"evaluate",return_value=policy):
                hold=allocator.choose(_snapshot("paper"),[candidate],root,Path("unused"),root)
            self.assertNotIn("policy_card",hold)

    def test_new_entry_refuses_mismatched_mode_owner(self):
        from test_etf_allocator import _snapshot, _candidate
        candidate={**_candidate("BTC/USDC"),"asset_class":"crypto","candidate_ref":"crypto://BTC/USDC"}
        decision={"action":"ENTER","strategy_id":"alpaca-btc-5m-trend-400-v2",
                  "candidate_ref":candidate["candidate_ref"],"owner_id":"alpaca-investment-live",
                  "expected_cost_usd":"0.06"}
        result=allocator.gate(_snapshot("paper"),[candidate],decision)
        self.assertFalse(result["approved"])
        self.assertFalse(result["checks"]["owner_mode"])

    def test_order_readback_keeps_the_official_fill_time(self):
        row={"found":True,"filled_at":"2026-01-01T04:00:30Z"}
        with patch.object(alpaca_cli,"_context",return_value={}), \
             patch.object(alpaca_cli,"_run",return_value=row) as read:
            result=alpaca_cli.find_order_by_client_id(credentials_path=Path("c"),cli_path=Path("a"),
                                                    client_order_id="lm-ai-"+"a"*24)
        self.assertIn("filled_at:.filled_at",read.call_args.args[1][-1])
        self.assertEqual(result["filled_at"],row["filled_at"])

    def test_actual_entry_receipts_resolve_original_policy_despite_expired_other_selection(self):
        for mode in ("paper", "live"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                ownership, owner=seed(root, mode)
                with patch.dict(os.environ,{"LIFE_MANAGER_INVESTMENT_OWNER_ID":owner}):
                    policy=position_manager.load_owned_policy(root,ownership,mode=mode)
                self.assertEqual(policy["card"].strategy_id,"alpaca-btc-5m-trend-v1")
                self.assertEqual(policy["release_sha"],"a"*40)
                self.assertEqual(policy["entry_price"],"200")
                self.assertEqual(policy["entry_timestamp"],"2026-01-01T04:00:30Z")

    def test_owned_exit_uses_original_native_fill_price_and_not_current_selection_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            ownership,owner=seed(root)
            state,observation=snapshot("live")
            with patch.dict(os.environ,{"LIFE_MANAGER_INVESTMENT_OWNER_ID":owner}):
                decision=position_manager.choose(state,observation,root,Path("unused"),root)
            self.assertEqual(decision["action"],"EXIT")
            self.assertEqual(decision["strategy_id"],"alpaca-btc-5m-trend-v1")
            self.assertEqual(decision["reason"],"hard_stop")
            self.assertEqual(decision["release_sha"],"a"*40)
            self.assertEqual(decision["entry_effect_id"],ownership["entry_effect_id"])
            self.assertEqual(decision["entry_client_order_id"],ownership["entry_client_order_id"])
            self.assertEqual(decision["entry_provider_order_id"],"provider-entry")
            self.assertEqual(decision["owner_id"],owner)
            self.assertEqual(decision["mode"],"live")
            self.assertEqual(decision["signal_inputs"]["age_bars"],"2")

    def test_missing_entry_evidence_cannot_fall_back_to_fresh_other_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            _ownership,owner=seed(root)
            (root/"receipts.jsonl").unlink()
            selected=json.loads((root/"selected-strategy.json").read_text())
            selected["expires_at"]="2099-01-01T00:00:00Z"
            (root/"selected-strategy.json").write_text(json.dumps(selected))
            state,observation=snapshot("live")
            with patch.dict(os.environ,{"LIFE_MANAGER_INVESTMENT_OWNER_ID":owner}):
                decision=position_manager.choose(state,observation,root,Path("unused"),root)
            self.assertEqual(decision["action"],"HOLD")
            self.assertEqual(decision["reason"],"owned_entry_intent_missing")

    def test_conflicting_provider_identity_cannot_replace_the_original_fill(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            ownership,owner=seed(root)
            ledger=root/"receipts.jsonl"
            rows=[json.loads(line) for line in ledger.read_text().splitlines()]
            foreign=copy.deepcopy(next(row for row in rows if row["receipt_type"]=="outcome"))
            foreign["broker_receipt_id"]="foreign-provider-entry"
            foreign["broker"]["id"]="foreign-provider-entry"
            ledger.write_text("".join(json.dumps(row)+"\n" for row in [*rows,foreign]))
            with patch.dict(os.environ,{"LIFE_MANAGER_INVESTMENT_OWNER_ID":owner}), \
                 self.assertRaisesRegex(ValueError,"owned_entry_fill_conflict"):
                position_manager.load_owned_policy(root,ownership,mode="live")

    def test_same_provider_fill_cannot_be_overridden_by_contradictory_values(self):
        for field,value in (("filled_avg_price","100"),("filled_qty","0.1"),
                            ("filled_at","2026-01-01T04:01:30Z"),("submitted_at","2026-01-01T03:59:00Z")):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                ownership,owner=seed(root)
                ledger=root/"receipts.jsonl"
                rows=[json.loads(line) for line in ledger.read_text().splitlines()]
                altered=copy.deepcopy(next(row for row in rows if row["receipt_type"]=="outcome"))
                altered["broker"][field]=value
                ledger.write_text("".join(json.dumps(row)+"\n" for row in [*rows,altered]))
                with patch.dict(os.environ,{"LIFE_MANAGER_INVESTMENT_OWNER_ID":owner}), \
                     self.assertRaisesRegex(ValueError,"owned_entry_fill_conflict"):
                    position_manager.load_owned_policy(root,ownership,mode="live")

    def test_equivalent_fill_formats_and_receipt_enrichment_remain_usable(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            ownership,owner=seed(root)
            ledger=root/"receipts.jsonl"
            rows=[json.loads(line) for line in ledger.read_text().splitlines()]
            enriched=copy.deepcopy(next(row for row in rows if row["receipt_type"]=="outcome"))
            enriched["broker"].update(filled_avg_price="200.0",filled_qty="0.050000",symbol="BTCUSDC",
                                     filled_at="2026-01-01T04:00:30+00:00")
            enriched["strategy_receipt"]={"fixture":"enriched"}
            ledger.write_text("".join(json.dumps(row)+"\n" for row in [*rows,enriched]))
            with patch.dict(os.environ,{"LIFE_MANAGER_INVESTMENT_OWNER_ID":owner}):
                policy=position_manager.load_owned_policy(root,ownership,mode="live")
            self.assertEqual(policy["card"].strategy_id,"alpaca-btc-5m-trend-v1")

    def test_entry_policy_identity_scope_and_time_cannot_be_inferred(self):
        cases=({"strategy_id":None},
               {"strategy_id":"alpaca-etf-126d-momentum-v1",
                "policy_card":candidate_cards()["alpaca-etf-126d-momentum-v1"].to_mapping()},
               {"observed_at":"2026-01-02T00:00:00Z"})
        for changes in cases:
            with self.subTest(changes=changes),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                ownership,owner=seed(root,decision_changes=changes)
                with patch.dict(os.environ,{"LIFE_MANAGER_INVESTMENT_OWNER_ID":owner}),self.assertRaises(ValueError):
                    position_manager.load_owned_policy(root,ownership,mode="live")

    def test_unreadable_entry_ledger_has_a_typed_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            ownership,owner=seed(root)
            with patch.dict(os.environ,{"LIFE_MANAGER_INVESTMENT_OWNER_ID":owner}), \
                 patch.object(effect_store,"_rows",side_effect=PermissionError("fixture")), \
                 self.assertRaisesRegex(ValueError,"owned_entry_ledger_unavailable"):
                position_manager.load_owned_policy(root,ownership,mode="live")

    def test_invalid_or_foreign_entry_receipts_are_rejected(self):
        changes = ("decision", "mode", "provider", "quantity", "price", "time", "owner", "paperflag", "order-type")
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                ownership,owner=seed(root)
                rows=[json.loads(line) for line in (root/"receipts.jsonl").read_text().splitlines()]
                decision=next(row for row in rows if row["receipt_type"]=="decision")
                outcome=next(row for row in rows if row["receipt_type"]=="outcome")
                intent=next(row for row in rows if row["receipt_type"]=="effect_intent" and row["status"]=="planned")
                if change=="decision": decision["decision"]["policy_card"]["entry_rules"]={"all":["close > 1"]}
                elif change=="mode": outcome["mode"]="paper"
                elif change=="provider": outcome["broker_receipt_id"]="foreign"
                elif change=="quantity": outcome["broker"]["filled_qty"]="0.1"
                elif change=="price": outcome["broker"]["filled_avg_price"]="NaN"
                elif change=="time": outcome["broker"]["filled_at"]="invalid"
                elif change=="paperflag": outcome["paper"]=True
                elif change=="order-type": outcome["broker"]["type"]="limit"
                else: intent["owner_id"]="alpaca-investment-paper"
                (root/"receipts.jsonl").write_text("".join(json.dumps(row)+"\n" for row in rows))
                with patch.dict(os.environ,{"LIFE_MANAGER_INVESTMENT_OWNER_ID":owner}),self.assertRaises(ValueError):
                    position_manager.load_owned_policy(root,ownership,mode="live")


class OwnedSubmitFenceTests(unittest.TestCase):
    def _flow(self, *, quantity_drift=False, replace_entry=False):
        import importlib.util
        spec=importlib.util.spec_from_file_location("owned_policy_native_run",ROOT/"run.py")
        native=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(native)
        self.assertEqual(Path(native.__file__).resolve(),ROOT/"run.py")
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            root=Path(directory)
            original,owner=seed(root)
            allocator_snapshot,observation=snapshot("live")
            history=allocator_snapshot.pop("crypto_history")
            observation.update(account={"cash":"90","equity":"97.5"},activities_count=1,
                               open_and_closed_orders_count=1,clock={"observed_at":"2026-01-01T04:15:00Z"})
            observation["positions"][0]["unrealized_pl"]="0"
            reads=[0]; current_qty=["0.05"]; observation_reads=[0]; fences=[0]
            def observe(**_kwargs):
                observation_reads[0]+=1
                value=copy.deepcopy(observation)
                value["positions"][0]["qty"]=current_qty[0]
                return value
            def fresh_snapshot(**_kwargs):
                reads[0]+=1
                if reads[0]>=2 and quantity_drift: current_qty[0]="0.04"
                return copy.deepcopy(allocator_snapshot)
            real_fence=native.control_fence
            @contextmanager
            def fenced(state):
                fences[0]+=1
                if fences[0]==2 and replace_entry:
                    # Model another writer completing before this submit lock.
                    with real_fence(state):
                        replacement,_=seed(root,decision_changes={"observed_at":"2026-01-01T03:59:59Z"},
                                           broker_id="provider-entry-b")
                    self.assertNotEqual(replacement["entry_effect_id"],original["entry_effect_id"])
                with real_fence(state) as control:
                    yield control
            def find(*,client_order_id,**_kwargs):
                rows=effect_store._rows(root/"receipts.jsonl")
                for row in reversed(rows):
                    broker=row.get("broker")
                    if isinstance(broker,dict) and broker.get("client_order_id")==client_order_id:
                        return copy.deepcopy(broker)
                return {"found":True,"id":"provider-exit","client_order_id":client_order_id,
                        "status":"filled","symbol":"BTC/USDC","side":"sell","type":"market",
                        "time_in_force":"gtc","filled_qty":"0.05","filled_avg_price":"150",
                        "submitted_at":"2026-01-01T04:15:00Z","filled_at":"2026-01-01T04:15:00Z"}
            stack.enter_context(patch.dict(os.environ,{
                "LIFE_MANAGER_INVESTMENT_DEPLOYMENT":"local","LIFE_MANAGER_INVESTMENT_MODE":"live",
                "LIFE_MANAGER_INVESTMENT_OWNER_ID":owner,
                "ALPACA_INVESTMENT_LIVE_STATE_DIR":str(root),
                "ALPACA_INVESTMENT_LIVE_CREDENTIALS_FILE":str(root/"credentials")},clear=True))
            for name,replacement in (("observe",observe),("read_allocator_snapshot",fresh_snapshot),
                                     ("find_order_by_client_id",find),("control_fence",fenced)):
                stack.enter_context(patch.object(native,name,side_effect=replacement))
            stack.enter_context(patch.object(native,"read_crypto_history",return_value=history))
            stack.enter_context(patch.object(native,"build_candidates",return_value=[]))
            stack.enter_context(patch.object(native,"_review_status",return_value={}))
            stack.enter_context(patch.object(native,"deliver",return_value={"message_id":"fixture"}))
            stack.enter_context(patch.object(native,"deliver_failure",return_value={"status":"delivered"}))
            stack.enter_context(patch.object(native,"_retry_allowed",return_value=False))
            stack.enter_context(patch.object(alpaca_cli,"_context",side_effect=AssertionError("unexpected provider context")))
            stack.enter_context(patch.object(alpaca_cli,"_run",side_effect=AssertionError("unexpected provider call")))
            submit=stack.enter_context(patch.object(native,"submit_order",return_value={"status":"accepted"}))
            with redirect_stdout(StringIO()) as output:
                code=native.main(wake_id="owned-fresh-fixture")
            summary=json.loads(output.getvalue().splitlines()[-1])
            rows=effect_store._rows(root/"receipts.jsonl")
            return code,summary,submit.call_args_list,rows,observation_reads[0],original

    def test_unchanged_owned_exit_preserves_parent_identity_through_real_main(self):
        code,summary,calls,rows,reads,original=self._flow()
        self.assertEqual(code,0,summary)
        self.assertEqual(len(calls),1)
        self.assertGreaterEqual(reads,2)
        decisions=[row["decision"] for row in rows if row.get("receipt_type")=="decision"
                   and row["decision"].get("position_action")=="EXIT"]
        self.assertEqual(len(decisions),1)
        self.assertEqual(decisions[0]["entry_effect_id"],original["entry_effect_id"])
        self.assertEqual(decisions[0]["owner_id"],"alpaca-investment-live")

    def test_quantity_drift_at_submit_time_cannot_sell_the_old_quantity(self):
        code,summary,calls,rows,_reads,_original=self._flow(quantity_drift=True)
        self.assertEqual(code,78,summary)
        self.assertEqual(summary["error_code"],"owned_position_changed_before_submit")
        self.assertEqual(calls,[])
        self.assertFalse(any(row.get("receipt_type")=="effect_intent" and
                             row.get("order",{}).get("side")=="sell" for row in rows))

    def test_replaced_entry_with_same_quantity_cannot_receive_an_old_exit(self):
        code,summary,calls,_rows,_reads,_original=self._flow(replace_entry=True)
        self.assertEqual(code,78,summary)
        self.assertEqual(summary["error_code"],"owned_position_changed_before_submit")
        self.assertEqual(calls,[])


if __name__ == "__main__":
    unittest.main()
