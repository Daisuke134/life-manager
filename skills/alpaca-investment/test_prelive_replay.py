"""LP06: one sealed pre-live trajectory across every remaining safety boundary."""

from __future__ import annotations

import importlib
from datetime import timedelta
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(REPO))

import alpaca_cli
import effect_store
import reporter
import risk_policy
from strategy_policy import candidate_cards
from crypto_ownership_proof import entry_fill_proof_from_rows


class _TelegramClient:
    def __init__(self, sends: list[str]):
        self.sends = sends

    def send_text(self, message: str, *, chat_id: str):
        self.sends.append(message)
        return {"message_ids": ["prelive-message-1"]}


class PreliveReplayTest(unittest.TestCase):
    def test_sealed_trajectory_reconciles_once_and_never_reaches_shadow_broker(self):
        fixture = json.loads(
            (ROOT / "fixtures/prelive-replay.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("credential", json.dumps(fixture).lower())

        rejected = fixture["risk_rejection"]
        risk = risk_policy.evaluate_entry(
            rejected["snapshot"], rejected["max_loss_usd"],
            now=risk_policy.parse_instant(rejected["now"]),
        )
        self.assertFalse(risk["approved"])
        self.assertEqual(risk["gate"], "fixed_risk_rejected")

        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            ledger = state / "receipts.jsonl"
            no_trade_id = effect_store.record_no_trade(ledger, fixture["no_trade"])
            self.assertEqual(
                no_trade_id, effect_store.record_no_trade(ledger, fixture["no_trade"])
            )

            card=candidate_cards()["alpaca-btc-5m-trend-400-v2"]
            proposal={**fixture["paper_proposal"],"action":"ENTER","owner_id":"alpaca-investment-paper",
                      "strategy_id":card.strategy_id,"policy_card":card.to_mapping(),"release_sha":"a"*40}
            sealed = effect_store.seal(ledger,proposal,fixture["paper_order"])
            effect_store.mark_started(ledger, sealed)
            broker_reads: list[str] = []

            def missing_order(client_order_id: str):
                broker_reads.append(client_order_id)
                return None

            with self.assertRaisesRegex(ValueError, "^reconciliation_blocked$"):
                effect_store.reconcile_started(ledger, missing_order)

            restarted = importlib.reload(effect_store)

            submitted=risk_policy.parse_instant(proposal["observed_at"])
            broker={"id":"official-prelive-entry","client_order_id":sealed["client_order_id"],"status":"filled",
                    "symbol":"BTCUSDC","side":"buy","type":"market","time_in_force":"gtc",
                    "filled_qty":"0.05","filled_avg_price":"200","submitted_at":submitted.isoformat(),
                    "filled_at":(submitted+timedelta(seconds=1)).isoformat()}
            ownership={"status":"entry_pending","symbol":"BTCUSD","entry_effect_id":sealed["effect_id"],
                       "entry_client_order_id":sealed["client_order_id"],"entry_filled_qty":"0"}
            account={"mode":"paper","paper":True,"account":{"cash":"99990","equity":"100000"},
                     "positions":[{"symbol":"BTCUSDC","qty":"0.05"}],
                     "clock":{"observed_at":(submitted+timedelta(seconds=2)).isoformat()}}
            def found_order(client_order_id: str):
                broker_reads.append(client_order_id)
                return dict(broker)
            def acquisition(_intent,order):
                return entry_fill_proof_from_rows(restarted._rows(ledger),ownership,order,account,
                                                 mode="paper",owner_id="alpaca-investment-paper")
            recovered = restarted.reconcile_started(ledger, found_order,on_reconciled=acquisition)
            replayed = restarted.reconcile_started(
                ledger, lambda value: self.fail(f"duplicate broker read: {value}")
            )
            self.assertEqual(recovered, {"pending": 1, "reconciled": 1, "unresolved": 0})
            self.assertEqual(replayed, {"pending": 0, "reconciled": 0, "unresolved": 0})
            self.assertEqual(broker_reads, [sealed["client_order_id"]] * 2)

            sends: list[str] = []
            with patch.object(
                reporter, "_telegram_client",
                return_value=(_TelegramClient(sends), "fixture-chat"),
            ):
                delivered = reporter.deliver(
                    state, fixture["observation"], fixture["campaign"],
                    fixture["no_trade"], "none",
                )
                duplicate = reporter.deliver(
                    state, fixture["observation"], fixture["campaign"],
                    fixture["no_trade"], "none",
                )
            self.assertEqual(delivered["message_id"], duplicate["message_id"])
            self.assertEqual(delivered["status"], duplicate["status"])
            self.assertEqual(len(sends), 1)

            with patch.object(alpaca_cli, "_context") as context, patch.object(
                alpaca_cli, "_run"
            ) as broker:
                shadow = fixture["shadow_proposal"]
                self.assertTrue(shadow["approved"])
                with self.assertRaisesRegex(
                    ValueError, "^investment_mode_effect_forbidden$"
                ):
                    alpaca_cli.submit_order(
                        credentials_path=Path("unused"), cli_path=Path("unused"),
                        client_order_id=sealed["client_order_id"],
                        order=fixture["paper_order"], mode=shadow["mode"],
                    )
            context.assert_not_called()
            broker.assert_not_called()

            rows = [json.loads(line) for line in ledger.read_text().splitlines()]
            self.assertEqual(sum(row.get("outcome") == "no_trade" for row in rows), 1)
            self.assertEqual(sum(row.get("receipt_type") == "outcome" for row in rows), 1)
            self.assertEqual(restarted.unresolved_intent_count(ledger), 0)


if __name__ == "__main__":
    unittest.main()
