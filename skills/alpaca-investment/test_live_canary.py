import io
import json
import os
import tempfile
import threading
import unittest
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import alpaca_cli
import effect_store
import live_canary


def snapshot():
    return {
        "account": {"equity": "66.70"}, "available_cash_usd": "66.70",
        "open_orders": 0, "positions": 0,
        "risk": {"risk_day_ready": True, "official_pnl_ny_day_usd": "0",
                 "allocated_capital_usd": "0"},
    }


class LiveCanaryTest(unittest.TestCase):
    def env(self, root, deployment="local"):
        return patch.dict(os.environ, {
            "LIFE_MANAGER_INVESTMENT_MODE": "live",
            "LIFE_MANAGER_INVESTMENT_DEPLOYMENT": deployment,
            "ALPACA_INVESTMENT_LIVE_CREDENTIALS_FILE": str(root / "credentials.json"),
            "ALPACA_INVESTMENT_LIVE_STATE_DIR": str(root / "state"),
            "ALPACA_CLI": str(root / "alpaca"),
        }, clear=True)

    def common(self, broker_reads, submit):
        candidate = {"candidate_ref": "crypto://BTC/USDC", "quote_age_seconds": 0,
                     "spread_fraction": .01}
        return (patch.object(live_canary, "read_allocator_snapshot", return_value=snapshot()),
                patch.object(live_canary, "build_candidates", return_value=[candidate]),
                patch.object(live_canary, "evaluate_entry", return_value={"approved": True}),
                patch.object(live_canary, "read_live_canary", side_effect=broker_reads),
                patch.object(live_canary, "submit_live_canary", side_effect=submit),
                patch.object(live_canary.time, "sleep"))

    def test_planned_receipt_is_sealed_under_shared_selection_fence(self):
        import fcntl
        def checked_seal(path, decision, order):
            with (path.parent/".control.lock").open("a+") as probe:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return effect_store.seal(path, decision, order)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/"state").mkdir()
            verified = {"status": "verified", "verified": True, "order": {"id": "one"}}
            with self.env(root), patch.object(live_canary, "read_live_canary", return_value=verified), \
                 patch.object(live_canary, "seal", side_effect=checked_seal):
                self.assertEqual(live_canary.main(), 0)

    def test_local_output_shape_remains_unchanged(self):
        output = io.StringIO()
        sealed = {"client_order_id": "lm-ai-" + "a" * 24, "effect_id": "b" * 64}
        with redirect_stdout(output):
            self.assertEqual(live_canary._output(
                sealed, {"status": "verified", "verified": True}, False, "local"), 0)
        value = json.loads(output.getvalue())
        self.assertNotIn("deployment", value)
        self.assertEqual(value["canary_ref"], "L09_LOCAL_CANARY_V1")

    def test_legacy_local_canary_stays_read_only_without_strategy_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mocks = self.common([{"status": "absent", "verified": False}], None)
            with self.env(root), mocks[0], mocks[1], mocks[2], mocks[3], mocks[4] as submit, mocks[5]:
                with self.assertRaisesRegex(ValueError, "investment_execution_identity_invalid"):
                    live_canary.main()
            submit.assert_not_called()
            rows = [json.loads(line) for line in
                    (root / "state/receipts.jsonl").read_text().splitlines()]
            self.assertEqual([row["status"] for row in rows if row.get("receipt_type") == "effect_intent"],
                             ["planned"])
            self.assertFalse((root / "state/live-canary.json").exists())

    def test_legacy_canary_retry_never_submits_without_strategy_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for _ in range(2):
                mocks = self.common([{"status": "absent", "verified": False}], None)
                with self.env(root), mocks[0], mocks[1], mocks[2], mocks[3], mocks[4] as submit, mocks[5]:
                    with self.assertRaisesRegex(ValueError, "investment_execution_identity_invalid"):
                        live_canary.main()
                submit.assert_not_called()

    def test_restart_reconciles_fill_before_new_entry_gate(self):
        verified = {"status": "verified", "verified": True, "order": {"id": "one"}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.common([{"status": "absent", "verified": False}], None)
            with self.env(root), first[0], first[1], first[2], first[3], first[4] as first_submit, first[5]:
                with self.assertRaisesRegex(ValueError, "investment_execution_identity_invalid"):
                    live_canary.main()
            first_submit.assert_not_called()
            second = self.common([verified], None)
            with self.env(root), second[0] as observe, second[1], second[2], second[3], \
                    second[4] as submit, second[5]:
                self.assertEqual(live_canary.main(), 0)
            observe.assert_not_called()
            submit.assert_not_called()

    def test_two_workers_share_one_submit_fence(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "LIFE_MANAGER_INVESTMENT_MODE": "live",
            "LIFE_MANAGER_INVESTMENT_DEPLOYMENT": "local",
            "LIFE_MANAGER_INVESTMENT_OWNER_ID": "alpaca-investment-live",
            "LIFE_MANAGER_RELEASE_SHA": "b" * 40,
            "LIFE_MANAGER_RUN_ID": "parallel-run",
            "LIFE_MANAGER_OCCURRENCE_ID": "alpaca-investment-live:parallel-run",
        }, clear=True):
            ledger = Path(directory) / "receipts.jsonl"
            decision = {**live_canary.DECISION, "owner_id": "alpaca-investment-live",
                        "strategy_id": "btc-v2", "release_sha": "a" * 40,
                        "native_trading_account_id": "native-account"}
            sealed = effect_store.seal(ledger, decision, live_canary.ORDER)
            barrier = threading.Barrier(2)
            results = []
            def worker():
                barrier.wait()
                results.append(effect_store.begin_effect(ledger, sealed))
            threads = [threading.Thread(target=worker) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self.assertEqual(sorted(results), [False, True])

    def test_cloud_order_rejection_leaves_no_pending_ownership_or_submit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.common([{"status": "absent", "verified": False}], None)
            with self.env(root, "cloud"), first[0], first[1], first[2], first[3], \
                    first[4] as submit, first[5]:
                with self.assertRaisesRegex(ValueError, "investment_execution_identity_invalid"):
                    live_canary.main()
            submit.assert_not_called()
            self.assertFalse((root / "state/live-owned-position.json").exists())

    def test_cloud_fence_rechecks_official_slots_before_submit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stale, occupied = snapshot(), snapshot()
            occupied["positions"] = 1
            first = self.common([{"status": "absent", "verified": False}], None)
            with self.env(root, "cloud"), first[0], first[1], first[2], first[3], \
                    first[4] as submit, first[5], patch.object(
                        live_canary, "read_allocator_snapshot",
                        side_effect=[stale, occupied]):
                with self.assertRaisesRegex(ValueError, "live_canary_gate_rejected"):
                    live_canary.main()
            submit.assert_not_called()
            self.assertFalse((root / "state/live-owned-position.json").exists())

    def test_verified_replay_never_rolls_closing_ownership_back_to_open(self):
        verified = {"status": "verified", "verified": True,
                    "order": {"filled_qty": "0.00002"},
                    "position": {"symbol": "BTCUSDC", "qty": "0.00001995"}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sealed = effect_store.seal(root / "state/receipts.jsonl",
                live_canary._decision("cloud"), live_canary.ORDER)
            closing = {"entry_client_order_id": sealed["client_order_id"],
                "entry_effect_id": sealed["effect_id"], "entry_filled_qty": "0.00002",
                "owned_qty": "0.00001995", "close_client_order_id": "close-one",
                "close_effect_id": "close-effect", "status": "closing", "symbol": "BTCUSD"}
            live_canary._write_result(root / "state/live-owned-position.json", closing)
            live_canary._write_cloud_ownership(root / "state", sealed, verified)
            self.assertEqual(json.loads(
                (root / "state/live-owned-position.json").read_text()), closing)

    def test_verified_write_and_regular_close_share_one_ownership_fence(self):
        verified = {"status": "verified", "verified": True,
                    "order": {"filled_qty": "0.00002"},
                    "position": {"symbol": "BTCUSDC", "qty": "0.00001995"}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state"
            sealed = effect_store.seal(state / "receipts.jsonl",
                live_canary._decision("cloud"), live_canary.ORDER)
            live_canary._write_cloud_ownership(state, sealed)
            closing = {"entry_client_order_id": sealed["client_order_id"],
                "entry_effect_id": sealed["effect_id"], "entry_filled_qty": "0.00002",
                "owned_qty": "0.00001995", "close_client_order_id": "close-one",
                "close_effect_id": "close-effect", "status": "closing", "symbol": "BTCUSD"}
            entered, release = threading.Event(), threading.Event()
            original_write = live_canary._write_result

            def delayed_write(path, value):
                if threading.current_thread().name == "canary-writer":
                    entered.set()
                    release.wait(2)
                original_write(path, value)

            def canary_writer():
                live_canary._write_cloud_ownership_fenced(state, sealed, verified)

            def regular_writer():
                with live_canary.control_fence(state):
                    original_write(state / "live-owned-position.json", closing)

            with patch.object(live_canary, "_write_result", side_effect=delayed_write):
                canary = threading.Thread(target=canary_writer, name="canary-writer")
                regular = threading.Thread(target=regular_writer, name="regular-writer")
                canary.start()
                self.assertTrue(entered.wait(1))
                regular.start()
                self.assertTrue(regular.is_alive())
                release.set()
                canary.join(2)
                regular.join(2)
            self.assertFalse(canary.is_alive())
            self.assertFalse(regular.is_alive())
            self.assertEqual(json.loads(
                (state / "live-owned-position.json").read_text()), closing)

    def test_submit_boundary_rejects_every_nonfrozen_shape(self):
        expected = dict(live_canary.ORDER)
        changes = {"asset_class": "us_equity", "notional_usd": "2.01", "side": "sell",
                   "symbol": "ETH/USDC", "time_in_force": "ioc", "type": "limit"}
        with patch.dict(os.environ, {"LIFE_MANAGER_INVESTMENT_MODE": "live"}, clear=True), \
                patch.object(alpaca_cli, "_context") as context, patch.object(alpaca_cli, "_run") as run:
            for key, value in changes.items():
                order = dict(expected); order[key] = value
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, "shape_invalid"):
                    alpaca_cli.submit_live_canary(credentials_path=Path("c"), cli_path=Path("a"),
                                                  client_order_id="lm-ai-" + "a" * 24, order=order)
            context.assert_not_called()
            run.assert_not_called()

    def test_submit_boundary_rejects_nonlive_mode_and_bad_client_id(self):
        for mode, client_id in (("shadow", "lm-ai-" + "a" * 24),
                                ("live", "user-supplied-id")):
            with self.subTest(mode=mode), patch.dict(
                    os.environ, {"LIFE_MANAGER_INVESTMENT_MODE": mode}, clear=True), patch.object(
                    alpaca_cli, "_context") as context, patch.object(alpaca_cli, "_run") as run:
                with self.assertRaises(ValueError):
                    alpaca_cli.submit_live_canary(
                        credentials_path=Path("c"), cli_path=Path("a"),
                        client_order_id=client_id, order=dict(live_canary.ORDER))
                context.assert_not_called()
                run.assert_not_called()

    def test_gate_rejects_unresolved_and_nonfinite_money(self):
        candidate = {"candidate_ref": "crypto://BTC/USDC", "quote_age_seconds": 0,
                     "spread_fraction": .01}
        base = snapshot(); base["unresolved_intents"] = 0
        with tempfile.TemporaryDirectory() as directory, patch.object(
                live_canary, "build_candidates", return_value=[candidate]), patch.object(
                live_canary, "evaluate_entry", return_value={"approved": True}):
            for change in ({"unresolved_intents": 1}, {"available_cash_usd": "nan"},
                           {"account": {"equity": "nan"}}):
                value = {**base, **change}
                with self.subTest(change=change), self.assertRaisesRegex(
                        ValueError, "live_canary_gate_rejected"):
                    live_canary._gate(value, Path(directory))


class LiveCanaryVerifierTest(unittest.TestCase):
    ORDER = {"found": True, "id": "order-1", "client_order_id": "lm-ai-" + "a" * 24,
             "status": "filled", "filled_qty": "0.00002", "filled_avg_price": "100000",
             "symbol": "BTCUSDC", "side": "buy", "notional": "2", "type": "market",
             "time_in_force": "gtc"}

    def verify(self, responses):
        with patch.object(alpaca_cli, "_context", return_value={}), patch.object(
                alpaca_cli, "_run", side_effect=responses):
            return alpaca_cli.read_live_canary(
                credentials_path=Path("c"), cli_path=Path("a"),
                client_order_id=self.ORDER["client_order_id"])

    def test_multiple_fills_sum_to_order_and_position(self):
        fills = [{"order_id": "order-1", "symbol": "BTCUSDC", "side": "buy",
                  "qty": "0.00001", "price": "100000",
                  "transaction_time": datetime.now(timezone.utc).isoformat()}] * 2
        result = self.verify([self.ORDER, fills,
                              [{"symbol": "BTCUSDC", "qty": "0.00002"}]])
        self.assertTrue(result["verified"])
        self.assertEqual(len(result["fills"]), 2)

    def test_btcusd_position_allows_broker_deducted_crypto_fee(self):
        fill = {"order_id": "order-1", "symbol": "BTC/USDC", "side": "buy",
                "qty": "0.00002", "price": "100000", "transaction_time": "fixture"}
        result = self.verify([self.ORDER, [fill],
                              [{"symbol": "BTCUSD", "qty": "0.00001995"}]])
        self.assertTrue(result["verified"])

    def test_position_fee_over_one_percent_fails_closed(self):
        fill = {"order_id": "order-1", "symbol": "BTC/USDC", "side": "buy",
                "qty": "0.00002", "price": "100000", "transaction_time": "fixture"}
        with self.assertRaisesRegex(ValueError, "live_canary_fill_mismatch"):
            self.verify([self.ORDER, [fill], [{"symbol": "BTCUSD", "qty": "0.000019"}]])

    def test_partial_cancel_is_not_closed_as_terminal_outcome(self):
        order = {**self.ORDER, "status": "canceled", "filled_qty": "0.00001"}
        result = self.verify([order])
        self.assertEqual(result["status"], "partial_terminal")
        self.assertFalse(result["verified"])

    def test_fill_or_position_mismatch_fails_closed(self):
        fill = {"order_id": "wrong", "symbol": "BTCUSDC", "side": "buy",
                "qty": "0.00002", "price": "100000", "transaction_time": "fixture"}
        with self.assertRaisesRegex(ValueError, "live_canary_fill_mismatch"):
            self.verify([self.ORDER, [fill], [{"symbol": "BTCUSDC", "qty": "0.00002"}]])


if __name__ == "__main__":
    unittest.main()
