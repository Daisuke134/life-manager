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

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import effect_store
import allocator
import alpaca_cli
import position_manager
from strategy_policy import candidate_cards


def seed(root: Path, mode: str = "live", decision_changes=None):
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
    broker = {"id": "provider-entry", "client_order_id": sealed["client_order_id"],
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
            _ownership,owner=seed(root)
            state,observation=snapshot("live")
            with patch.dict(os.environ,{"LIFE_MANAGER_INVESTMENT_OWNER_ID":owner}):
                decision=position_manager.choose(state,observation,root,Path("unused"),root)
            self.assertEqual(decision["action"],"EXIT")
            self.assertEqual(decision["strategy_id"],"alpaca-btc-5m-trend-v1")
            self.assertEqual(decision["reason"],"hard_stop")
            self.assertEqual(decision["release_sha"],"a"*40)

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


if __name__ == "__main__":
    unittest.main()
