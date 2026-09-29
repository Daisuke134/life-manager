from __future__ import annotations

import json
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import alpaca_cli
import etf_ownership

EFFECT_SPEC = importlib.util.spec_from_file_location(
    "investment_effect_store_for_etf_test", ROOT / "effect_store.py"
)
EFFECT = importlib.util.module_from_spec(EFFECT_SPEC)
EFFECT_SPEC.loader.exec_module(EFFECT)

RUN_SPEC = importlib.util.spec_from_file_location("etf_execution_run", ROOT / "run.py")
RUN = importlib.util.module_from_spec(RUN_SPEC)
RUN_SPEC.loader.exec_module(RUN)


CLIENT_ID = "lm-ai-" + "a" * 24
OWNER_ID = "alpaca-investment-live"
STRATEGY_ID = "alpaca-etf-126d-momentum-v1"
ORDER = {
    "asset_class": "us_equity",
    "notional_usd": "10.00",
    "side": "buy",
    "symbol": "QQQ",
    "time_in_force": "day",
    "type": "market",
}
PROVIDER_ORDER = {
    "found": True,
    "id": "paper-order-1",
    "client_order_id": CLIENT_ID,
    "status": "filled",
    "symbol": "QQQ",
    "side": "buy",
    "type": "market",
    "time_in_force": "day",
    "notional": "10",
    "filled_qty": "0.025",
    "filled_avg_price": "400",
    "submitted_at": "2026-09-29T14:31:00Z",
}
ACCOUNT_READBACK = {
    "account": {"cash": "90", "equity": "100"},
    "clock": {"observed_at": "2026-09-29T14:31:05Z"},
    "positions": [{"symbol": "QQQ", "qty": "0.025", "avg_entry_price": "400"}],
}


class PaperEtfOrderBoundaryTest(unittest.TestCase):
    def test_paper_submit_accepts_exact_stock_order_and_validates_provider_identity(self):
        acknowledgement = {**PROVIDER_ORDER, "status": "new"}
        with patch.dict(os.environ, {"LIFE_MANAGER_INVESTMENT_OWNER_ID": "alpaca-investment-paper"}), \
                patch.object(alpaca_cli, "_context", return_value={}), patch.object(
            alpaca_cli, "_run", return_value=acknowledgement
        ) as run:
            result = alpaca_cli.submit_order(
                credentials_path=Path("credentials"), cli_path=Path("alpaca"),
                client_order_id=CLIENT_ID, order=ORDER, mode="paper",
                owner_id="alpaca-investment-paper", strategy_id=STRATEGY_ID,
            )

        self.assertEqual(result, acknowledgement)
        args = run.call_args.args[1]
        self.assertEqual(args[:5], ["order", "submit", "--quiet", "--symbol", "QQQ"])
        self.assertIn("--notional", args)
        self.assertIn("10.00", args)
        self.assertIn("--time-in-force", args)
        self.assertIn("day", args)

    def test_live_etf_submit_is_rejected_before_provider_access(self):
        with patch.object(alpaca_cli, "_context") as context, patch.object(
            alpaca_cli, "_run"
        ) as run:
            with self.assertRaisesRegex(ValueError, "^live_etf_rejected$"):
                alpaca_cli.submit_order(
                    credentials_path=Path("credentials"), cli_path=Path("alpaca"),
                    client_order_id=CLIENT_ID, order=ORDER, mode="live",
                    owner_id=OWNER_ID, strategy_id=STRATEGY_ID,
                )
        context.assert_not_called()
        run.assert_not_called()

    def test_paper_etf_submit_rejects_wrong_identity_and_shape(self):
        for owner_id, strategy_id, order in (
            ("foreign-owner", STRATEGY_ID, ORDER),
            (OWNER_ID, "foreign-strategy", ORDER),
            (OWNER_ID, STRATEGY_ID, {**ORDER, "symbol": "AAPL"}),
            (OWNER_ID, STRATEGY_ID, {**ORDER, "notional_usd": "10.01"}),
            (OWNER_ID, STRATEGY_ID, {**ORDER, "time_in_force": "gtc"}),
        ):
            with self.subTest(owner_id=owner_id, strategy_id=strategy_id, order=order), \
                    patch.object(alpaca_cli, "_context") as context, \
                    patch.object(alpaca_cli, "_run") as run:
                with self.assertRaisesRegex(ValueError, "^etf_order_(identity|shape)_invalid$"):
                    alpaca_cli.submit_order(
                        credentials_path=Path("credentials"), cli_path=Path("alpaca"),
                        client_order_id=CLIENT_ID, order=order, mode="paper",
                        owner_id=owner_id, strategy_id=strategy_id,
                    )
                context.assert_not_called()
                run.assert_not_called()


class EtfOwnershipTest(unittest.TestCase):
    def _record(self, path: Path, *, order: dict | None = None,
                owner_id: str = OWNER_ID, strategy_id: str = STRATEGY_ID):
        return etf_ownership.record_filled(
            path,
            owner_id=owner_id,
            strategy_id=strategy_id,
            decision_session="2026-09-29",
            client_order_id=CLIENT_ID,
            order=order or PROVIDER_ORDER,
            account_readback=ACCOUNT_READBACK,
            source_receipt_ids=["alpaca://stock-bars/iex/split/2026-09-28/abc"],
        )

    def test_filled_provider_and_account_readback_creates_owned_position(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "etf-owned-position.json"
            value = self._record(state)
            persisted = json.loads(state.read_text(encoding="utf-8"))

        self.assertFalse(value["replay_zero"])
        self.assertEqual(persisted["owner_id"], OWNER_ID)
        self.assertEqual(persisted["strategy_id"], STRATEGY_ID)
        self.assertEqual(persisted["symbol"], "QQQ")
        self.assertEqual(persisted["provider_order_id"], "paper-order-1")
        self.assertEqual(persisted["position_qty"], "0.025")
        self.assertEqual(persisted["decision_session"], "2026-09-29")

    def test_missing_fill_does_not_create_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "etf-owned-position.json"
            with self.assertRaisesRegex(ValueError, "^etf_fill_missing$"):
                self._record(state, order={**PROVIDER_ORDER, "status": "new", "filled_qty": "0"})
            self.assertFalse(state.exists())

    def test_foreign_state_is_never_adopted(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "etf-owned-position.json"
            state.write_text(json.dumps({
                "status": "open", "owner_id": "foreign-owner", "strategy_id": STRATEGY_ID,
                "symbol": "QQQ", "position_qty": "0.025",
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "^etf_position_not_owned$"):
                etf_ownership.read_state(state)
            with self.assertRaisesRegex(ValueError, "^etf_position_not_owned$"):
                self._record(state)
            self.assertIn("foreign-owner", state.read_text(encoding="utf-8"))

    def test_same_provider_and_client_identity_is_replay_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "etf-owned-position.json"
            first = self._record(state)
            second = self._record(state)
        self.assertFalse(first["replay_zero"])
        self.assertTrue(second["replay_zero"])
        self.assertEqual(second["provider_order_id"], "paper-order-1")

    def test_different_provider_identity_cannot_replace_open_position(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "etf-owned-position.json"
            self._record(state)
            with self.assertRaisesRegex(ValueError, "^etf_position_ownership_conflict$"):
                self._record(state, order={**PROVIDER_ORDER, "id": "paper-order-2"})


class EtfReconciliationTest(unittest.TestCase):
    def test_effect_callback_runs_before_outcome_and_can_replay_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "receipts.jsonl"
            sealed = EFFECT.seal(
                ledger,
                {"mode": "paper", "strategy_id": STRATEGY_ID, "owner_id": OWNER_ID},
                ORDER,
            )
            EFFECT.mark_started(ledger, sealed)
            callbacks = []
            result = EFFECT.reconcile_started(
                ledger,
                lambda _: PROVIDER_ORDER,
                on_reconciled=lambda intent, order: callbacks.append((intent, order)),
            )
            again = EFFECT.reconcile_started(
                ledger,
                lambda _: self.fail("replay must not read a completed provider order"),
                on_reconciled=lambda *_: self.fail("replay must not callback"),
            )

        self.assertEqual(result["reconciled"], 1)
        self.assertEqual(again["unresolved"], 0)
        self.assertEqual(callbacks[0][1]["id"], "paper-order-1")

    def test_run_reconciliation_callback_requires_provider_fill_and_account_readback(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            RUN, "observe", return_value=ACCOUNT_READBACK
        ):
            state = Path(directory) / "etf-owned-position.json"
            result = RUN._reconcile_etf_intent(
                {
                    "mode": "paper",
                    "owner_id": OWNER_ID,
                    "strategy_id": STRATEGY_ID,
                    "decision_session": "2026-09-29",
                    "client_order_id": CLIENT_ID,
                    "source_receipt_ids": ["bars-receipt"],
                    "order": ORDER,
                },
                PROVIDER_ORDER,
                credentials_path=Path("credentials"),
                cli_path=Path("alpaca"),
                state_path=state,
            )
            persisted = json.loads(state.read_text(encoding="utf-8"))

        self.assertEqual(result["observation"], ACCOUNT_READBACK)
        self.assertEqual(persisted["provider_order_id"], "paper-order-1")

    def test_run_reconciliation_callback_rejects_missing_fill_before_state_write(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            RUN, "observe", return_value=ACCOUNT_READBACK
        ):
            state = Path(directory) / "etf-owned-position.json"
            with self.assertRaisesRegex(ValueError, "^etf_fill_missing$"):
                RUN._reconcile_etf_intent(
                    {
                        "mode": "paper", "owner_id": OWNER_ID, "strategy_id": STRATEGY_ID,
                        "decision_session": "2026-09-29", "client_order_id": CLIENT_ID,
                        "source_receipt_ids": ["bars-receipt"], "order": ORDER,
                    },
                    {**PROVIDER_ORDER, "status": "new", "filled_qty": "0"},
                    credentials_path=Path("credentials"), cli_path=Path("alpaca"),
                    state_path=state,
                )
            self.assertFalse(state.exists())


if __name__ == "__main__":
    unittest.main()
