import json
import copy
import importlib.util
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import ExitStack, nullcontext, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import reporter as REPORTER
import alpaca_cli as CLI
import effect_store as EFFECT_STORE
SPEC = importlib.util.spec_from_file_location("alpaca_investment_run", ROOT / "run.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _entry_selection_fixture(state: Path, decision: dict, mode="paper"):
    from strategy_policy import candidate_cards
    card = candidate_cards()["alpaca-btc-5m-trend-400-v2"]
    decision.update(action="ENTER", owner_id=f"alpaca-investment-{mode}", mode=mode,
                    strategy_id=card.strategy_id, release_sha="a" * 40, policy_card=card.to_mapping())
    state.mkdir(parents=True, exist_ok=True)
    selection = {"selection": "selected", "strategy_id": card.strategy_id,
                 "release_sha": "a" * 40, "card": card.to_mapping(),
                 "holdout": {"net_pnl_usd": "1.00"},
                 "benchmark": {"symbol": "BTC/USDC", "method": "observed_window_buy_and_hold",
                               "measurement_kind": "modeled_reference_pnl", "status": "measured",
                               "holdout": {"status": "measured", "net_pnl_usd": "0.00",
                                           "strategy_net_pnl_usd": "1.00",
                                           "excess_net_pnl_usd": "1.00"}},
                 "expires_at": "2099-01-01T00:00:00Z", "report_id": "entry-fixture"}
    (state / "selected-strategy.json").write_text(json.dumps(selection))
    return selection


def _publisher_probe(root: Path) -> tuple[Path, Path]:
    marker = root / "publisher-called"
    executable = root / "node"
    executable.write_text('#!/bin/sh\n: > "$ALPACA_MARKER"\n', encoding="utf-8")
    executable.chmod(0o700)
    return executable, marker


class DeploymentProfileTest(unittest.TestCase):
    def test_reconciliation_pending_is_a_hold_not_a_generic_failure(self):
        self.assertTrue(MODULE._reconciliation_is_pending({
            "pending": 1, "reconciled": 0, "unresolved": 1, "deferred": 1,
        }))
        self.assertFalse(MODULE._reconciliation_is_pending({
            "pending": 1, "reconciled": 0, "unresolved": 1,
        }))
        self.assertFalse(MODULE._reconciliation_is_pending({
            "pending": 0, "reconciled": 0, "unresolved": 0,
        }))

    def test_accepts_only_exact_local_or_cloud(self):
        for value in ("local", "cloud"):
            with patch.dict(MODULE.os.environ, {
                "LIFE_MANAGER_INVESTMENT_DEPLOYMENT": value,
            }):
                self.assertEqual(MODULE._deployment(), value)

    def test_rejects_missing_or_non_exact_values(self):
        invalid_values = (None, "", "local,cloud", " local", "LOCAL")
        for value in invalid_values:
            environment = {} if value is None else {
                "LIFE_MANAGER_INVESTMENT_DEPLOYMENT": value,
            }
            with self.subTest(value=value), patch.dict(
                MODULE.os.environ, environment, clear=True
            ):
                with self.assertRaisesRegex(
                    ValueError, "^investment_deployment_invalid$"
                ):
                    MODULE._deployment()


class InvestmentModeTest(unittest.TestCase):
    def test_paper_campaign_allows_only_owned_etf_symbol(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            MODULE._atomic_json(state / "etf-owned-position.json", {
                "schema_version": 1,
                "status": "open",
                "owner_id": "alpaca-investment-paper",
                "strategy_id": "alpaca-etf-126d-momentum-v1",
                "symbol": "QQQ",
                "decision_session": "2026-09-29",
                "client_order_id": "lm-ai-" + "a" * 24,
                "provider_order_id": "provider-order",
                "position_qty": "0.013",
            })
            snapshot = {"paper": True, "unexpected_positions": ["QQQ"]}
            with patch.dict(MODULE.os.environ, {
                "LIFE_MANAGER_INVESTMENT_OWNER_ID": "alpaca-investment-paper",
            }, clear=True), patch.object(
                MODULE, "read_campaign_snapshot", return_value=snapshot
            ), patch.object(MODULE, "reconcile", return_value={"status": "CLOSED"}) as reconcile:
                result = MODULE._paper_campaign(
                    state=state, credentials_path=Path("credentials"), cli_path=Path("alpaca")
                )
            self.assertEqual(result, {"status": "CLOSED"})
            self.assertEqual(reconcile.call_args.args, (snapshot,))
            self.assertEqual(
                reconcile.call_args.kwargs["allowed_external_symbols"], frozenset({"QQQ"})
            )

    def test_production_import_uses_reconciliation_callback_contract(self):
        script = """
import inspect
import sys
from pathlib import Path
sys.path.insert(0, 'skills/alpaca-investment')
import run
assert 'on_reconciled' in inspect.signature(run.reconcile_started).parameters
skill_root = Path('skills/alpaca-investment').resolve()
for module_name in (
    'alpaca_cli', 'campaign', 'control', 'effect_store', 'etf_ownership',
    'paper_performance', 'position_manager', 'reporter', 'review_status',
    'risk_day', 'risk_policy',
):
    module_path = Path(sys.modules[module_name].__file__).resolve()
    assert module_path.parent == skill_root, (module_name, module_path)
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT.parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_requires_exact_mode_before_broker_access(self):
        for value in ("paper", "shadow", "live", None, "", " paper", "PAPER", "paper,live"):
            with self.subTest(value=value):
                if value in {"paper", "shadow", "live"}:
                    with patch.dict(MODULE.os.environ, {"LIFE_MANAGER_INVESTMENT_MODE": value}):
                        self.assertEqual(MODULE._mode(), value)
                    continue
                with patch.dict(MODULE.os.environ, {
                    "LIFE_MANAGER_INVESTMENT_DEPLOYMENT": "local",
                    **({} if value is None else {"LIFE_MANAGER_INVESTMENT_MODE": value}),
                }, clear=True), patch.object(MODULE, "reconcile_started", return_value={"pending": 0, "reconciled": 0, "unresolved": 0}), \
                        patch.object(MODULE, "observe", side_effect=RuntimeError("broker-called")) as observe, \
                        patch.object(MODULE, "deliver_failure", return_value={"status": "delivered"}):
                    MODULE.main(wake_id="mode-validation")
                self.assertEqual(observe.call_count, 0)

    def test_paper_mode_selects_configured_paper_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            credentials, state = root / "paper.json", root / "paper-state"
            observed = []
            def broker_boundary(**kwargs):
                observed.append(kwargs)
                raise RuntimeError("stop-at-broker-boundary")
            with patch.dict(MODULE.os.environ, {
                "LIFE_MANAGER_INVESTMENT_DEPLOYMENT": "local",
                "LIFE_MANAGER_INVESTMENT_MODE": "paper",
                "ALPACA_INVESTMENT_PAPER_CREDENTIALS_FILE": str(credentials),
                "ALPACA_INVESTMENT_PAPER_STATE_DIR": str(state),
            }, clear=True), patch.object(MODULE, "reconcile_started", return_value={"pending": 0, "reconciled": 0, "unresolved": 0}) as reconcile, \
                    patch.object(MODULE, "observe", side_effect=broker_boundary), \
                    patch.object(MODULE, "deliver_failure", return_value={"status": "delivered"}):
                MODULE.main(wake_id="paper-paths")
        self.assertEqual(observed[0]["credentials_path"], credentials)
        self.assertEqual(reconcile.call_args.args[0], state / "receipts.jsonl")

    def test_mode_state_paths_reject_shared_namespaces(self):
        with tempfile.TemporaryDirectory() as directory:
            root, paper, shared = Path(directory), Path(directory) / "paper", Path(directory) / "shared"
            base = {
                "ALPACA_INVESTMENT_PAPER_STATE_DIR": str(paper),
                "ALPACA_INVESTMENT_SHADOW_CREDENTIALS_FILE": str(root / "shadow.json"),
                "ALPACA_INVESTMENT_LIVE_CREDENTIALS_FILE": str(root / "live.json"),
                "ALPACA_INVESTMENT_SHADOW_STATE_DIR": str(root / "shadow"),
                "ALPACA_INVESTMENT_LIVE_STATE_DIR": str(root / "live"),
            }
            for mode, selected in (("shadow", {"ALPACA_INVESTMENT_SHADOW_STATE_DIR": str(paper)}), ("live", {"ALPACA_INVESTMENT_LIVE_STATE_DIR": str(shared), "ALPACA_INVESTMENT_SHADOW_STATE_DIR": str(shared)})):
                with self.subTest(mode=mode), patch.dict(MODULE.os.environ, {**base, **selected}, clear=True):
                    with self.assertRaisesRegex(ValueError, "^investment_mode_state_path_conflict$"):
                        MODULE._mode_paths(mode)

    def test_receipts_and_reconciled_rows_expose_top_level_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "receipts.jsonl"
            EFFECT_STORE.record_no_trade(ledger, {"mode": "shadow", "candidate_ref": "NO_TRADE"})
            sealed = EFFECT_STORE.seal(ledger, {"mode": "paper", "candidate_ref": "TRADE"}, {"asset_class": "crypto"})
            EFFECT_STORE.mark_started(ledger, sealed)
            EFFECT_STORE.reconcile_started(ledger, lambda _: {"found": True, "status": "filled"})
            rows = [json.loads(line) for line in ledger.read_text().splitlines()]
        self.assertTrue(all(row.get("mode") in {"paper", "shadow"} for row in rows))

    def test_review_polling_is_local_paper_only_and_fails_soft(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "account-status.json").write_text(
                '{"application_status":"in_review","observed_at":"2026-09-05T00:00:00Z"}'
            )
            with patch.object(MODULE, "refresh_application_status", side_effect=RuntimeError("browser")) as refresh:
                self.assertEqual(MODULE._review_status(state, "paper", "local")["application_status"], "in_review")
                self.assertEqual(refresh.call_count, 1)
                MODULE._review_status(state, "paper", "cloud")
                MODULE._review_status(state, "live", "local")
                self.assertEqual(refresh.call_count, 1)

    def test_legacy_paper_intent_reconciliation_writes_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "receipts.jsonl"
            ledger.write_text(json.dumps({
                "client_order_id": "legacy-order", "effect_id": "legacy-effect",
                "paper": True, "receipt_type": "effect_intent", "status": "started",
            }) + "\n")
            EFFECT_STORE.reconcile_started(ledger, lambda _: {"found": True, "status": "filled"})
            rows = [json.loads(line) for line in ledger.read_text().splitlines()]
        self.assertTrue(all(row.get("mode") == "paper" for row in rows[1:]))


class BrokerContextTest(unittest.TestCase):
    def _credential(self, root, row):
        private = root / "private"
        private.mkdir(parents=True, mode=0o700)
        path = private / "credentials.json"
        path.write_text(json.dumps({"credentials": [row]}))
        path.chmod(0o600)
        return path

    def test_paper_and_live_contexts_use_separate_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root, cli = Path(directory), Path(directory) / "alpaca"
            cli.write_text("#!/bin/sh\n[ \"$1\" = version ] && echo 0.0.14\n")
            cli.chmod(0o700)
            paper = self._credential(root / "paper", {
                "service": "app.alpaca.markets", "paper_endpoint": CLI.PAPER_ENDPOINT,
                "api_key": "paper-key", "api_secret": "paper-secret"})
            live = self._credential(root / "live", {
                "service": "app.alpaca.markets", "live_endpoint": "https://api.alpaca.markets/v2",
                "live_api_key": "live-key", "live_api_secret": "live-secret"})
            for mode, path, key, live_trade in (
                ("paper", paper, "paper-key", "false"),
                ("shadow", live, "live-key", "true"), ("live", live, "live-key", "true")):
                context = CLI._context(path, cli, mode=mode)
                self.assertEqual((context["ALPACA_API_KEY"], context["ALPACA_LIVE_TRADE"]),
                                 (key, live_trade))
            with self.assertRaises(ValueError):
                CLI._context(paper, cli, mode="live")

    def test_submit_rejects_shadow_before_cli_or_order(self):
        with patch.object(CLI, "_context") as context, patch.object(CLI, "_run") as run, \
                patch.object(CLI.subprocess, "run") as process:
            for mode in ("shadow",):
                with self.subTest(mode=mode), self.assertRaisesRegex(
                    ValueError, "^investment_mode_effect_forbidden$"):
                    CLI.submit_order(
                        credentials_path=Path("missing"), cli_path=Path("missing"),
                        client_order_id="lm-ai-" + "a" * 24,
                        order={"asset_class": "crypto", "symbol": "BTC/USD", "notional_usd": "1"},
                        mode=mode,
                    )
        context.assert_not_called()
        run.assert_not_called()
        process.assert_not_called()

    def test_live_submit_accepts_only_bounded_btc_usdc(self):
        acknowledgement = {"client_order_id": "lm-ai-" + "a" * 24, "symbol": "BTC/USDC"}
        valid = {"asset_class": "crypto", "notional_usd": "10.00", "side": "buy",
                 "symbol": "BTC/USDC", "time_in_force": "gtc", "type": "market"}
        with patch.object(CLI, "_context", return_value={}), patch.object(
                CLI, "_run", return_value=acknowledgement) as run:
            self.assertEqual(CLI.submit_order(credentials_path=Path("credentials"),
                cli_path=Path("alpaca"), client_order_id=acknowledgement["client_order_id"],
                order=valid, mode="live"), acknowledgement)
        self.assertIn("--notional", run.call_args.args[1])
        for invalid in ({**valid, "notional_usd": "10.01"},
                        {**valid, "symbol": "ETH/USDC"},
                        {**valid, "side": "sell"}):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                    ValueError, "^unsupported_live_order_shape$"):
                CLI.submit_order(credentials_path=Path("credentials"), cli_path=Path("alpaca"),
                    client_order_id=acknowledgement["client_order_id"], order=invalid, mode="live")

    def test_live_submit_accepts_exact_btc_exit_qty(self):
        client_id = "lm-ai-" + "b" * 24
        order = {"asset_class": "crypto", "qty": "0.000123456", "side": "sell",
                 "symbol": "BTC/USDC", "time_in_force": "gtc", "type": "market"}
        with patch.object(CLI, "_context", return_value={}), patch.object(
                CLI, "_run", return_value={"client_order_id": client_id}) as run:
            CLI.submit_order(credentials_path=Path("credentials"), cli_path=Path("alpaca"),
                             client_order_id=client_id, order=order, mode="live")
        self.assertIn("--qty", run.call_args.args[1])

    def test_live_ownership_selects_btc_not_usdc_and_opens_from_fill(self):
        from test_crypto_entry import entry_fixture
        from crypto_ownership_proof import entry_fill_proof_from_rows
        with tempfile.TemporaryDirectory() as directory,patch.dict(MODULE.os.environ,{
                "LIFE_MANAGER_INVESTMENT_MODE":"live","LIFE_MANAGER_INVESTMENT_OWNER_ID":"alpaca-investment-live"}):
            state=Path(directory);marker,broker,observation,owner=entry_fixture(state,owned_qty="0.049875")
            proof=entry_fill_proof_from_rows(EFFECT_STORE._rows(state/"receipts.jsonl"),marker,broker,observation,mode="live",owner_id=owner)
            EFFECT_STORE.reconcile_started(state/"receipts.jsonl",lambda _:broker,on_reconciled=lambda *_:proof)
            observation=MODULE._normalize_live_position_symbols(observation)
            with patch.object(MODULE,"find_order_by_client_id",return_value=broker):
                ownership=MODULE._sync_live_ownership(state,Path("unused"),Path("unused"),observation)
            self.assertEqual(ownership["status"],"open")
            self.assertEqual(ownership["owned_qty"],"0.049875")
            MODULE._owned_live_position(ownership,observation)

    def test_provider_symbol_is_normalized_before_regular_ownership_sync(self):
        from test_crypto_entry import entry_fixture
        from crypto_ownership_proof import entry_fill_proof_from_rows
        with tempfile.TemporaryDirectory() as directory,patch.dict(MODULE.os.environ,{
                "LIFE_MANAGER_INVESTMENT_MODE":"live","LIFE_MANAGER_INVESTMENT_OWNER_ID":"alpaca-investment-live"}):
            state=Path(directory);marker,broker,observation,owner=entry_fixture(state)
            proof=entry_fill_proof_from_rows(EFFECT_STORE._rows(state/"receipts.jsonl"),marker,broker,observation,mode="live",owner_id=owner)
            EFFECT_STORE.reconcile_started(state/"receipts.jsonl",lambda _:broker,on_reconciled=lambda *_:proof)
            marker.update(status="open",entry_filled_qty="0.05",owned_qty="0.05")
            MODULE._atomic_json(state/"live-owned-position.json",marker)
            observation=MODULE._normalize_live_position_symbols(observation)
            with patch.object(MODULE,"find_order_by_client_id",return_value=broker):
                ownership=MODULE._sync_live_ownership(state,Path("unused"),Path("unused"),observation)
            self.assertEqual(ownership["status"],"open")
            self.assertEqual(observation["positions"][1]["symbol"],"BTCUSD")
            MODULE._owned_live_position(ownership,observation)

    def test_live_observation_and_sync_hold_fence_against_canary_open_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            pending = {"entry_client_order_id": "lm-ai-" + "c" * 24,
                "entry_effect_id": "effect", "entry_filled_qty": "0",
                "status": "entry_pending", "symbol": "BTCUSD"}
            opened = {**pending, "entry_filled_qty": "0.00002",
                      "owned_qty": "0.00001995", "status": "open"}
            MODULE._atomic_json(state / "live-owned-position.json", pending)
            observing, release = threading.Event(), threading.Event()

            def slow_observe(**_kwargs):
                observing.set()
                release.wait(2)
                return {"positions": []}

            def regular_sync():
                MODULE._observe_and_sync_live_ownership(
                    state, Path("credentials"), Path("alpaca"))

            def canary_open():
                with MODULE.control_fence(state):
                    MODULE._atomic_json(state / "live-owned-position.json", opened)

            with patch.object(MODULE, "observe", side_effect=slow_observe), patch.object(
                    MODULE, "find_order_by_client_id", return_value={"status": "absent"}):
                regular = threading.Thread(target=regular_sync)
                canary = threading.Thread(target=canary_open)
                regular.start()
                self.assertTrue(observing.wait(1))
                canary.start()
                self.assertTrue(canary.is_alive())
                release.set()
                regular.join(2)
                canary.join(2)
            self.assertFalse(regular.is_alive())
            self.assertFalse(canary.is_alive())
            marker = json.loads((state / "live-owned-position.json").read_text())
            self.assertEqual(marker["status"], "open")

    def test_live_ownership_remains_open_when_position_disappears(self):
        from test_crypto_entry import entry_fixture
        from crypto_ownership_proof import entry_fill_proof_from_rows
        with tempfile.TemporaryDirectory() as directory,patch.dict(MODULE.os.environ,{
                "LIFE_MANAGER_INVESTMENT_MODE":"live","LIFE_MANAGER_INVESTMENT_OWNER_ID":"alpaca-investment-live"}):
            state=Path(directory);marker,broker,observation,owner=entry_fixture(state)
            proof=entry_fill_proof_from_rows(EFFECT_STORE._rows(state/"receipts.jsonl"),marker,broker,observation,mode="live",owner_id=owner)
            EFFECT_STORE.reconcile_started(state/"receipts.jsonl",lambda _:broker,on_reconciled=lambda *_:proof)
            marker.update(status="open",entry_filled_qty="0.05",owned_qty="0.05")
            MODULE._atomic_json(state/"live-owned-position.json",marker)
            observation["positions"]=observation["positions"][:1]
            from test_crypto_performance import activity_fixture
            empty_activities=activity_fixture({'fills':[],'fees':[]},mode='live',
                start=broker['submitted_at'],end=observation['clock']['observed_at'])
            with patch.object(MODULE,"find_order_by_client_id",return_value=broker), \
                 patch.object(MODULE,"read_crypto_activity_evidence",return_value=empty_activities):
                ownership=MODULE._sync_live_ownership(state,Path("unused"),Path("unused"),observation)
            self.assertEqual(ownership["status"],"open")

    def test_rejected_close_without_receipt_remains_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            MODULE._atomic_json(state / "live-owned-position.json", {
                "entry_client_order_id": "lm-ai-" + "e" * 24,
                "entry_effect_id": "entry", "entry_filled_qty": "0.0001", "owned_qty": "0.0001",
                "close_client_order_id": "lm-ai-" + "f" * 24,
                "close_effect_id": "close", "status": "closing", "symbol": "BTCUSD"})
            with patch.object(MODULE, "find_order_by_client_id", return_value={
                    "status": "rejected", "filled_qty": "0"}):
                ownership = MODULE._sync_live_ownership(state, Path("credentials"),
                    Path("alpaca"), {"positions": [{"symbol": "BTCUSD", "qty": "0.0001"}]})
            self.assertEqual(ownership["status"], "closing")
            self.assertEqual(ownership["owned_qty"], "0.0001")

    def test_partial_terminal_close_without_receipt_cannot_change_owned_qty(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            MODULE._atomic_json(state / "live-owned-position.json", {
                "entry_client_order_id": "lm-ai-" + "1" * 24,
                "entry_effect_id": "entry", "entry_filled_qty": "0.00010",
                "owned_qty": "0.00010", "close_client_order_id": "lm-ai-" + "2" * 24,
                "close_effect_id": "close", "status": "closing", "symbol": "BTCUSD"})
            observation = {"positions": [{"symbol": "BTCUSD", "qty": "0.00004"}]}
            with patch.object(MODULE, "find_order_by_client_id", return_value={
                    "status": "canceled", "filled_qty": "0.00006"}):
                ownership = MODULE._sync_live_ownership(
                    state, Path("credentials"), Path("alpaca"), observation)
            self.assertEqual(ownership["owned_qty"], "0.00010")
            self.assertEqual(ownership["status"], "closing")
            with self.assertRaises(ValueError):
                MODULE._owned_live_position(ownership, observation)

    def test_second_close_marker_replaces_rejected_close_identity(self):
        ownership = {"entry_client_order_id": "entry", "entry_effect_id": "entry-effect",
            "owned_qty": "0.0001", "close_client_order_id": "old-close",
            "close_effect_id": "old-effect", "status": "open", "symbol": "BTCUSD"}
        marker = MODULE._closing_marker(ownership, {
            "client_order_id": "new-close", "effect_id": "new-effect"})
        self.assertEqual(marker["close_client_order_id"], "new-close")
        self.assertEqual(marker["close_effect_id"], "new-effect")
        self.assertEqual(marker["status"], "closing")

    def test_replacement_btc_quantity_is_not_owned(self):
        ownership = {"entry_client_order_id": "entry", "entry_filled_qty": "0.0001",
            "owned_qty": "0.00009", "status": "open", "symbol": "BTCUSD"}
        with self.assertRaisesRegex(ValueError, "^live_position_not_owned$"):
            MODULE._owned_live_position(ownership, {
                "positions": [{"symbol": "BTCUSD", "qty": "0.00008"}]})


class PolicyHistoryDispatchTest(unittest.TestCase):
    def test_owned_history_follows_entry_policy_without_a_current_selection(self):
        from test_owned_policy import seed
        from strategy_policy import candidate_cards
        for mode in ("paper","live"):
            for strategy_id,required in (("alpaca-btc-5m-trend-v1",None),
                                         ("alpaca-btc-5m-trend-400-v2",800)):
                with self.subTest(mode=mode,strategy=strategy_id),tempfile.TemporaryDirectory() as directory:
                    root=Path(directory)
                    card=candidate_cards()[strategy_id]
                    ownership,owner=seed(root,mode,decision_changes={"strategy_id":strategy_id,"policy_card":card.to_mapping()})
                    (root/"selected-strategy.json").unlink()
                    with patch.dict(MODULE.os.environ,{"LIFE_MANAGER_INVESTMENT_OWNER_ID":owner}), \
                         patch.object(MODULE,"read_crypto_history",return_value={"BTC/USDC":[]}) as read:
                        history=MODULE._policy_crypto_history(root,ownership,mode=mode,
                            credentials_path=Path("c"),cli_path=Path("a"),observed_at="2026-01-01T04:15:00Z")
                    self.assertEqual(history,{"BTC/USDC":[]})
                    self.assertEqual(read.call_count,1)
                    if required is None: self.assertNotIn("history_bars",read.call_args.kwargs)
                    else: self.assertEqual(read.call_args.kwargs["history_bars"],required)

    def test_flat_new_candidate_requests_800_and_etf_does_not_request_crypto(self):
        from strategy_policy import candidate_cards
        for strategy in ("alpaca-btc-5m-trend-400-v2","alpaca-etf-126d-momentum-v1"):
            with self.subTest(strategy=strategy),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                card=candidate_cards()[strategy]
                (root/"selected-strategy.json").write_text(json.dumps({
                    "strategy_id":strategy,"card":card.to_mapping(),"release_sha":"a"*40,
                    "holdout":{"net_pnl_usd":"1.00"},
                    "benchmark":{"symbol":"SPY" if strategy.endswith("momentum-v1") else "BTC/USDC",
                        "method":"buy_and_hold" if strategy.endswith("momentum-v1") else "observed_window_buy_and_hold",
                        "measurement_kind":"modeled_reference_pnl","status":"measured",
                        "holdout":{"status":"measured","net_pnl_usd":"0.00",
                            "strategy_net_pnl_usd":"1.00","excess_net_pnl_usd":"1.00"}},
                    "expires_at":"2099-01-01T00:00:00Z"}))
                with patch.object(MODULE,"read_crypto_history",return_value={}) as read:
                    MODULE._policy_crypto_history(root,None,mode="paper",credentials_path=Path("c"),
                                                  cli_path=Path("a"),observed_at="2026-01-01T04:15:00Z")
                self.assertEqual(read.call_count,0 if strategy.endswith("momentum-v1") else 1)
                if read.called: self.assertEqual(read.call_args.kwargs["history_bars"],800)

    def test_unknown_owned_policy_never_falls_back_to_a_current_candidate(self):
        from test_owned_policy import seed
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            ownership,owner=seed(root)
            (root/"receipts.jsonl").unlink()
            with patch.dict(MODULE.os.environ,{"LIFE_MANAGER_INVESTMENT_OWNER_ID":owner}), \
                 patch.object(MODULE,"read_crypto_history") as read:
                result=MODULE._policy_crypto_history(root,ownership,mode="live",credentials_path=Path("c"),
                                                    cli_path=Path("a"),observed_at="2026-01-01T04:15:00Z")
            self.assertEqual(result,{})
            read.assert_not_called()


class VersionedCryptoHistoryTest(unittest.TestCase):
    def _read(self, observed="2026-09-10T08:05:00Z", mutate=None):
        def serve(_cli, args, _env):
            start=datetime.fromisoformat(args[args.index("--start")+1].replace("Z","+00:00"))
            end=datetime.fromisoformat(args[args.index("--end")+1].replace("Z","+00:00"))
            self.assertEqual((end-start).total_seconds(),800*300)
            self.assertEqual(args[args.index("--symbols")+1],"BTC/USDC")
            payload={"next_page_token":None,"rows":[{"symbol":"BTC/USDC","bars":[
                {"t":(start+timedelta(minutes=5*i)).isoformat(),"o":"100","h":"102","l":"99","c":"101"}
                for i in range(801)]}]}
            if mutate: mutate(payload)
            return payload
        with patch.object(CLI,"_context",return_value={}),patch.object(CLI,"_run",side_effect=serve):
            return CLI.read_crypto_history(credentials_path=Path("credentials"),cli_path=Path("alpaca"),
                                           observed_at=observed,history_bars=800)

    def test_v2_closed_end_has_identical_800_inputs_at_both_clock_offsets(self):
        aligned=self._read()
        unaligned=self._read("2026-09-10T08:05:29Z")
        self.assertEqual(aligned,unaligned)
        self.assertEqual(len(aligned["BTC/USDC"]),800)
        self.assertEqual(aligned["BTC/USDC"][-1]["t"],"2026-09-10T08:00:00+00:00")

    def test_v2_incomplete_or_paginated_history_is_not_filled(self):
        for mutate in (lambda p:p.update(next_page_token="more"),
                       lambda p:p["rows"][0]["bars"].pop(5),
                       lambda p:p["rows"][0]["bars"].insert(2,p["rows"][0]["bars"][1]),
                       lambda p:p["rows"][0]["bars"][-1].update(c="NaN")):
            with self.subTest(mutation=mutate),self.assertRaises(ValueError):
                self._read(mutate=mutate)

    def test_large_output_budget_is_limited_to_bounded_btc_bars(self):
        payload=json.dumps({"payload":"x"*CLI.MAX_OUTPUT_BYTES}).encode()
        completed=type("Completed",(),{"returncode":0,"stdout":payload})()
        with patch.object(CLI.subprocess,"run",return_value=completed):
            CLI._run(Path("alpaca"),["data","crypto","bars","--symbols","BTC/USDC"],{})
            for command in (["data","crypto","quotes","--symbols","BTC/USDC"],
                            ["data","crypto","bars","--symbols","BTC/USDC,ETH/USDC"]):
                with self.subTest(command=command),self.assertRaisesRegex(ValueError,"output_too_large"):
                    CLI._run(Path("alpaca"),command,{})


class BrokerSnapshotTest(unittest.TestCase):
    def test_crypto_history_accepts_bounded_official_ohlc(self):
        rows = [{"symbol": "BTC/USDC", "bars": [
            {"t": f"2026-09-10T07:{minute:02d}:00Z", "o": 100, "h": 102, "l": 99, "c": 101}
            for minute in (35, 40, 45, 50, 55)] + [
            {"t": "2026-09-10T08:00:00Z", "o": 100, "h": 102, "l": 99, "c": 101}]}]
        with patch.object(CLI, "_context", return_value={}), patch.object(
                CLI, "_run", return_value=rows):
            result = CLI.read_crypto_history(credentials_path=Path("credentials"),
                cli_path=Path("alpaca"), observed_at="2026-09-10T08:05:00Z")
        self.assertEqual(result["BTC/USDC"][0]["c"], "101")

    def test_crypto_history_accepts_inclusive_eight_hour_window_and_returns_completed_bars(self):
        start = datetime(2026, 9, 10, 0, 5, tzinfo=timezone.utc)
        rows = [{"symbol": "BTC/USDC", "bars": [
            {"t": (start + timedelta(minutes=5 * index)).isoformat().replace("+00:00", "Z"),
             "o": 100, "h": 102, "l": 99, "c": 101}
            for index in range(97)]}]
        with patch.object(CLI, "_context", return_value={}), patch.object(
                CLI, "_run", return_value=rows):
            result = CLI.read_crypto_history(credentials_path=Path("credentials"),
                cli_path=Path("alpaca"), observed_at="2026-09-10T08:05:00Z")
        self.assertEqual(len(result["BTC/USDC"]), 96)
        self.assertEqual(result["BTC/USDC"][-1]["t"], "2026-09-10T08:00:00Z")
        excessive = [{"symbol": "BTC/USDC", "bars": [*rows[0]["bars"], rows[0]["bars"][-1]]}]
        with patch.object(CLI, "_context", return_value={}), patch.object(CLI, "_run", return_value=excessive), \
                self.assertRaisesRegex(ValueError, "^alpaca_crypto_history_invalid$"):
            CLI.read_crypto_history(credentials_path=Path("credentials"),
                cli_path=Path("alpaca"), observed_at="2026-09-10T08:05:00Z")

    def test_crypto_history_supplies_the_existing_trend_indicator_warmup(self):
        from strategy_policy import candidate_cards, evaluate
        observed = "2026-09-10T08:05:00Z"
        def serve(_cli, args, _env):
            start = datetime.fromisoformat(args[args.index("--start") + 1].replace("Z", "+00:00"))
            end = datetime.fromisoformat(args[args.index("--end") + 1].replace("Z", "+00:00"))
            count = int((end - start).total_seconds() // 300) + 1
            return [{"symbol": "BTC/USDC", "bars": [
                {"t": (start + timedelta(minutes=5 * index)).isoformat(),
                 "o": 100 + index, "h": 102 + index, "l": 99 + index, "c": 101 + index}
                for index in range(count)]}]
        with patch.object(CLI, "_context", return_value={}), patch.object(CLI, "_run", side_effect=serve) as run:
            history = CLI.read_crypto_history(credentials_path=Path("credentials"),
                cli_path=Path("alpaca"), observed_at=observed)
        decision = evaluate({"clock": {"timestamp": observed},
            "crypto": [{"symbol": "BTC/USDC", "bid": "195", "ask": "196", "quote_at": observed}],
            "crypto_history": history, "positions": 0, "position": None},
            candidate_cards()["alpaca-btc-5m-trend-v1"])
        self.assertNotEqual(decision["reason"], "history_insufficient")
        self.assertIn("ema_50", decision["signal_inputs"])
        args = run.call_args.args[1]
        self.assertEqual(args[args.index("--start") + 1], "2026-09-10T00:05:00Z")
        self.assertEqual(args[args.index("--limit") + 1], "1000")

    def test_crypto_history_omits_the_forming_interval_at_aligned_and_unaligned_times(self):
        bars = [{"t": f"2026-09-10T07:{minute:02d}:00Z", "o": 100, "h": 102, "l": 99, "c": 101}
                for minute in (35, 40, 45, 50, 55)] + [
                {"t": "2026-09-10T08:00:00Z", "o": 100, "h": 102, "l": 99, "c": 101},
                {"t": "2026-09-10T08:05:00Z", "o": 100, "h": 102, "l": 99, "c": 101}]
        for observed in ("2026-09-10T08:05:00Z", "2026-09-10T08:07:00Z"):
            with self.subTest(observed=observed), patch.object(CLI, "_context", return_value={}), \
                    patch.object(CLI, "_run", return_value=[{"symbol": "BTC/USDC", "bars": bars}]):
                result = CLI.read_crypto_history(credentials_path=Path("credentials"),
                    cli_path=Path("alpaca"), observed_at=observed)
                self.assertEqual(len(result["BTC/USDC"]), 6)
                self.assertEqual(result["BTC/USDC"][-1]["t"], "2026-09-10T08:00:00Z")

    def test_crypto_history_rejects_future_or_malformed_bars(self):
        cases = [
            [{"symbol": "BTC/USDC", "bars": [{"t": "2026-09-10T08:06:00Z",
                "o": 100, "h": 102, "l": 99, "c": 101}]}],
            [{"symbol": "BTC/USDC", "bars": [{"t": "2026-09-10T08:00:00Z",
                "o": 100, "h": 98, "l": 99, "c": 101}]}],
        ]
        for rows in cases:
            with self.subTest(rows=rows), patch.object(CLI, "_context", return_value={}), \
                    patch.object(CLI, "_run", return_value=rows), self.assertRaisesRegex(
                        ValueError, "^alpaca_crypto_history_invalid$"):
                CLI.read_crypto_history(credentials_path=Path("credentials"),
                    cli_path=Path("alpaca"), observed_at="2026-09-10T08:05:00Z")

    def test_crypto_history_rejects_unusable_btc_timeline(self):
        valid = [{"t": f"2026-09-10T07:{minute:02d}:00Z",
                  "o": 100, "h": 102, "l": 99, "c": 101}
                 for minute in (35, 40, 45, 50, 55)] + [
                 {"t": "2026-09-10T08:00:00Z", "o": 100, "h": 102, "l": 99, "c": 101}]
        cases = [
            [],
            [{"symbol": "ETH/USDC", "bars": valid}],
            [{"symbol": "BTC/USDC", "bars": valid[:5]}],
            [{"symbol": "BTC/USDC", "bars": [{**valid[0], "t": "2026-09-10T00:00:00Z"}, *valid[1:]]}],
            [{"symbol": "BTC/USDC", "bars": [valid[1], valid[0], *valid[2:]]}],
            [{"symbol": "BTC/USDC", "bars": [valid[0], valid[0], *valid[2:]]}],
            [{"symbol": "BTC/USDC", "bars": [valid[0], {**valid[1], "t": "2026-09-10T07:41:00Z"}, *valid[2:]]}],
            [{"symbol": "BTC/USDC", "bars": [
                {**valid[index], "t": f"2026-09-10T06:{minute:02d}:00Z"}
                for index, minute in enumerate((0, 5, 10, 15, 20, 25))]}],
        ]
        for rows in cases:
            with self.subTest(rows=rows), patch.object(CLI, "_context", return_value={}), \
                    patch.object(CLI, "_run", return_value=rows), self.assertRaisesRegex(
                        ValueError, "^alpaca_crypto_history_invalid$"):
                CLI.read_crypto_history(credentials_path=Path("credentials"),
                    cli_path=Path("alpaca"), observed_at="2026-09-10T08:05:00Z")

    def test_crypto_history_accepts_missing_five_minute_bars(self):
        rows = [{"symbol": "BTC/USDC", "bars": [
            {"t": f"2026-09-10T07:{minute:02d}:00Z", "o": 100, "h": 102, "l": 99, "c": 101}
            for minute in (25, 30, 40, 45, 55)] + [
            {"t": "2026-09-10T08:00:00Z", "o": 100, "h": 102, "l": 99, "c": 101}]}]
        with patch.object(CLI, "_context", return_value={}), patch.object(
                CLI, "_run", return_value=rows):
            result = CLI.read_crypto_history(credentials_path=Path("credentials"),
                cli_path=Path("alpaca"), observed_at="2026-09-10T08:05:00Z")
        self.assertEqual(len(result["BTC/USDC"]), 6)

    def test_shadow_and_live_snapshots_are_nonpaper(self):
        for mode in ("shadow", "live"):
            with self.subTest(mode=mode), patch.dict(
                CLI.os.environ, {"LIFE_MANAGER_INVESTMENT_MODE": mode}, clear=True
            ), patch.object(CLI, "_context", return_value={}), patch.object(
                CLI, "_run", side_effect=[
                    {"cash": "101", "equity": "102"},
                    {"is_open": False, "observed_at": "2026-09-05T00:00:00Z"},
                    [], 0, 0, {"symbol": "SPY"}, 0,
                ]
            ):
                observation = CLI.observe(credentials_path=Path("missing"), cli_path=Path("missing"))
            self.assertEqual((observation["mode"], observation["paper"]), (mode, False))
            with patch.dict(
                CLI.os.environ, {"LIFE_MANAGER_INVESTMENT_MODE": mode}, clear=True
            ), patch.object(CLI, "_context", return_value={}), patch.object(
                CLI, "_run", side_effect=[
                    {"cash": "101", "equity": "102"}, [], [],
                    {"is_open": False, "observed_at": "2026-09-05T00:00:00Z"}, [],
                ]
            ):
                snapshot = CLI.read_campaign_snapshot(
                    credentials_path=Path("missing"), cli_path=Path("missing"), symbols=("A", "B")
                )
            self.assertEqual((snapshot["mode"], snapshot["paper"]), (mode, False))


class ShadowReadOnlyTest(unittest.TestCase):
    def test_shadow_never_submits_campaign_exit_or_allocator_order(self):
        observation = {"account": {"cash": "100000", "equity": "100000"},
                       "activities_count": 0, "clock": {"observed_at": "2026-09-05T00:00:00Z"},
                       "open_and_closed_orders_count": 0,
                       "positions": [{"unrealized_pl": "-0.25"}]}
        with tempfile.TemporaryDirectory() as directory, patch.dict(MODULE.os.environ, {
            "LIFE_MANAGER_INVESTMENT_MODE": "shadow", "LIFE_MANAGER_INVESTMENT_DEPLOYMENT": "local",
            "ALPACA_INVESTMENT_SHADOW_CREDENTIALS_FILE": str(Path(directory) / "live.json"),
            "ALPACA_INVESTMENT_SHADOW_STATE_DIR": str(Path(directory) / "shadow-state"),
        }, clear=True), patch.object(MODULE, "reconcile_started", return_value={"pending": 0, "reconciled": 0, "unresolved": 0}), \
                patch.object(MODULE, "observe", return_value=observation), patch.object(MODULE, "read_campaign_snapshot") as campaign_read, \
                patch.object(MODULE, "reconcile", return_value={"exit_status": "EXIT_READY", "exit_credit_usd": "0.50", "unrealized_pnl_usd": "0.00"}) as campaign_reconcile, \
                patch.object(MODULE, "exit_order", return_value={"asset_class": "option_spread_close"}), \
                patch.object(MODULE, "read_allocator_snapshot", return_value={"risk": {}}), patch.object(MODULE, "build_candidates", return_value=[]), \
                patch.object(MODULE, "choose", return_value={"approved": True, "candidate_ref": "crypto://BTC/USD", "candidate": {"asset_class": "crypto"}, "gate": "approved", "observed_at": "2026-09-05T00:00:00Z"}), \
                patch.object(MODULE, "order_for", return_value={"asset_class": "crypto"}), patch.object(MODULE, "submit_order") as submit, \
                patch.object(MODULE, "deliver", return_value={"message_id": "123"}):
            self.assertEqual(MODULE.main(wake_id="shadow-read-only"), 0)
        campaign_read.assert_not_called()
        campaign_reconcile.assert_not_called()
        submit.assert_not_called()


class CampaignEffectFenceTest(unittest.TestCase):
    def test_campaign_exit_does_not_submit_when_effect_was_already_started(self):
        observation = {"account": {"cash": "100", "equity": "100"},
            "activities_count": 0, "clock": {"observed_at": "2026-09-05T00:00:00Z"},
            "open_and_closed_orders_count": 0, "positions": []}
        campaign = {"exit_status": "EXIT_READY", "exit_credit_usd": "0.50",
            "unrealized_pnl_usd": "0.00", "paper": True, "positions": [],
            "realized_pnl_usd": None}
        with tempfile.TemporaryDirectory() as directory, patch.dict(MODULE.os.environ, {
            "LIFE_MANAGER_INVESTMENT_MODE": "paper", "LIFE_MANAGER_INVESTMENT_DEPLOYMENT": "local",
            "LIFE_MANAGER_INVESTMENT_OWNER_ID": "alpaca-investment-paper",
            "LIFE_MANAGER_RUN_ID": "campaign-exit",
            "LIFE_MANAGER_OCCURRENCE_ID": "alpaca-investment-paper:campaign-exit",
            "LIFE_MANAGER_RELEASE_SHA": "b" * 40,
            "ALPACA_INVESTMENT_PAPER_CREDENTIALS_FILE": str(Path(directory) / "credentials.json"),
            "ALPACA_INVESTMENT_PAPER_STATE_DIR": str(Path(directory) / "state"),
        }, clear=True), \
            patch.object(MODULE, "reconcile_started", return_value={"pending": 0, "reconciled": 0, "unresolved": 0}), \
            patch.object(MODULE, "record_source_inventory", return_value={"coverage_state": "complete"}), \
            patch.object(MODULE, "_observe_and_sync_live_ownership", return_value=(observation, None)), \
            patch.object(MODULE, "_paper_campaign", return_value=campaign), \
            patch.object(MODULE, "exit_order", return_value={"asset_class": "option_spread_close"}), \
            patch.object(MODULE, "control_fence", side_effect=lambda *_: nullcontext({"paused": False, "killed": False})), \
            patch.object(MODULE, "begin_effect", return_value=False), \
            patch.object(MODULE, "submit_order", side_effect=AssertionError("duplicate campaign submit")) as submit, \
            patch.object(MODULE, "deliver_failure", return_value={"status": "delivered"}), \
            patch.object(MODULE, "_retry_allowed", return_value=False), \
            redirect_stdout(StringIO()):
            MODULE.main(wake_id="campaign-exit-replay")
        submit.assert_not_called()


class PaperEtfFreshFenceTest(unittest.TestCase):
    def run_approved_trade(self, *, action="EXIT", fresh_changes=None,
                           broker_positions=None, changed_owned_qty=None, selection_change=None,
                           pending_entry_at_fence=False):
        from test_etf_allocator import _snapshot, _candidate, ETF_ID

        owner = "alpaca-investment-paper"
        position = {"owner_id": owner, "strategy_id": ETF_ID, "symbol": "QQQ",
                    "qty": "0.025", "entry_session": "2026-09-29"}
        candidate = _candidate() if action == "EXIT" else {
            **_candidate("BTC/USDC"), "asset_class": "crypto", "candidate_ref": "crypto://BTC/USDC",
        }
        raw = _snapshot()
        if action == 'ENTER': raw['account']['id'] = 'synthetic-native-account-paper'
        raw.pop("mode")  # The real broker reader does not return this caller context.
        raw["positions"] = 1 if action == "EXIT" else 0
        raw["source_receipt_ids"] = ["alpaca://stock-bars/iex/split/fixture" if action == "EXIT"
                                     else "alpaca://crypto-bars/us/fixture"]
        initial = {**copy.deepcopy(raw), "mode": "paper",
                   "position": position if action == "EXIT" else None}
        decision = MODULE.allocation_gate(initial, [candidate], {
            "action": action, "mode": "paper", "candidate_ref": candidate["candidate_ref"], "symbol": candidate["symbol"],
            "strategy_id": ETF_ID if action == "EXIT" else "alpaca-btc-5m-trend-400-v2", "owner_id": owner,
            "position": position if action == "EXIT" else None,
            "decision_session": "2026-10-20", "expected_cost_usd": "0.02",
            "observed_at": raw["clock"]["timestamp"], "reason": "hold_sessions_elapsed",
        })
        self.assertTrue(decision["approved"], decision)
        held = [{"symbol": "QQQ", "qty": "0.025"}] if action == "EXIT" else []
        observation = {"mode":"paper", "paper":True, "account": raw["account"], "activities_count": 0,
                       "clock": {"observed_at": raw["clock"]["timestamp"]},
                       "open_and_closed_orders_count": 0, "positions": held}
        observed = []
        reads = []
        allocation_gate = MODULE.allocation_gate
        def fresh_gate(snapshot, candidates, decision):
            self.assertEqual(snapshot.get("mode"), "paper")
            return allocation_gate(snapshot, candidates, decision)
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            state = Path(directory) / "state"
            state.mkdir()
            selection = _entry_selection_fixture(state, decision) if action == "ENTER" else None
            ownership = {"schema_version": 1, "status": "open", "owner_id": owner,
                         "strategy_id": ETF_ID, "symbol": "QQQ",
                         "decision_session": "2026-09-29",
                         "client_order_id": "lm-ai-" + "a" * 24,
                         "provider_order_id": "paper-entry", "position_qty": "0.025"}
            if action == "EXIT":
                MODULE._atomic_json(state / "etf-owned-position.json", ownership)

            def allocator_read(**_kwargs):
                value = copy.deepcopy(raw)
                if reads:
                    value.update(fresh_changes or {})
                    if pending_entry_at_fence:
                        MODULE._atomic_json(state / "live-owned-position.json", {
                            "status":"entry_pending","symbol":"BTCUSD","entry_effect_id":"b"*64,
                            "entry_client_order_id":"lm-ai-"+"b"*24,"entry_filled_qty":"0"})
                    if selection_change is not None:
                        selected = copy.deepcopy(selection)
                        if selection_change == "missing":
                            (state / "selected-strategy.json").unlink()
                        else:
                            if selection_change == "strategy":
                                from strategy_policy import candidate_cards
                                card = candidate_cards()["alpaca-btc-5m-reversion-400-v2"]
                                selected.update(strategy_id=card.strategy_id, card=card.to_mapping())
                            elif selection_change == "release": selected["release_sha"] = "b" * 40
                            elif selection_change == "expired": selected["expires_at"] = "2020-01-01T00:00:00Z"
                            elif selection_change == "report": selected["report_id"] = "new-report-same-policy"
                            elif selection_change == "card": selected["card"]["entry_rules"] = {"all": ["close > 0"]}
                            elif selection_change == "not_selected": selected["selection"] = "rejected"
                            elif selection_change == "report_missing": selected["report_id"] = ""
                            MODULE._atomic_json(state / "selected-strategy.json", selected)
                    if changed_owned_qty is not None:
                        MODULE._atomic_json(state / "etf-owned-position.json", {
                            **ownership, "position_qty": changed_owned_qty,
                        })
                reads.append(value)
                return value

            def observe_read(**_kwargs):
                value = copy.deepcopy(observation)
                if observed and broker_positions is not None:
                    value["positions"] = copy.deepcopy(broker_positions)
                observed.append(value)
                return value

            stack.enter_context(patch.dict(MODULE.os.environ, {
                "LIFE_MANAGER_INVESTMENT_DEPLOYMENT": "local",
                "LIFE_MANAGER_INVESTMENT_MODE": "paper",
                "LIFE_MANAGER_INVESTMENT_OWNER_ID": owner,
                "ALPACA_INVESTMENT_PAPER_STATE_DIR": str(state),
                "ALPACA_INVESTMENT_PAPER_CREDENTIALS_FILE": str(Path(directory) / "credentials"),
            }, clear=True))
            stack.enter_context(patch.object(CLI, "_run", side_effect=AssertionError("unexpected broker call")))
            stack.enter_context(patch.object(MODULE, "reconcile_started", return_value={
                "pending": 0, "reconciled": 0, "unresolved": 0,
            }))
            stack.enter_context(patch.object(MODULE, "find_order_by_client_id", return_value={"status":"new"}))
            stack.enter_context(patch.object(MODULE, "observe", side_effect=observe_read))
            stack.enter_context(patch.object(MODULE, "_paper_campaign", return_value={
                "exit_status": "CLOSED", "unrealized_pnl_usd": "0",
            }))
            stack.enter_context(patch.object(MODULE, "read_allocator_snapshot", side_effect=allocator_read))
            stack.enter_context(patch.object(MODULE, "build_candidates", return_value=[candidate]))
            stack.enter_context(patch.object(MODULE, "read_crypto_history", return_value={}))
            stack.enter_context(patch.object(MODULE, "choose", return_value=copy.deepcopy(decision)))
            stack.enter_context(patch.object(MODULE, "allocation_gate", side_effect=fresh_gate))
            stack.enter_context(patch.object(MODULE, "_review_status", return_value={}))
            stack.enter_context(patch.object(MODULE, "deliver", return_value={"message_id": "fixture"}))
            stack.enter_context(patch.object(MODULE, "deliver_failure", return_value={"status": "delivered"}))
            stack.enter_context(patch.object(MODULE, "_retry_allowed", return_value=False))
            submit = stack.enter_context(patch.object(MODULE, "submit_order", return_value={"status": "accepted"}))
            with redirect_stdout(StringIO()) as output:
                code = MODULE.main(wake_id="paper-fresh-fence")
            return code, json.loads(output.getvalue()), submit.call_args_list, observed

    def test_owned_paper_exit_with_one_position_reaches_broker_once(self):
        code, result, calls, observed = self.run_approved_trade()
        self.assertEqual(code, 0, result)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].kwargs["order"], {
            "asset_class": "us_equity", "qty": "0.025", "side": "sell",
            "symbol": "QQQ", "time_in_force": "day", "type": "market",
        })
        self.assertEqual(calls[0].kwargs["mode"], "paper")
        self.assertEqual(calls[0].kwargs["owner_id"], "alpaca-investment-paper")
        self.assertEqual(len(observed), 2)

    def test_paper_entry_retains_mode_in_fresh_gate(self):
        code, result, calls, _ = self.run_approved_trade(action="ENTER")
        self.assertEqual(code, 0, result)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].kwargs["order"]["side"], "buy")

    def test_entry_rejects_changed_missing_or_expired_selection_before_submit(self):
        for change in ("strategy", "release", "expired", "missing", "card", "not_selected", "report_missing"):
            with self.subTest(change=change):
                code, result, calls, _ = self.run_approved_trade(action="ENTER", selection_change=change)
                self.assertEqual(code, 78, result)
                self.assertEqual(result["error_code"], "entry_policy_changed_before_submit")
                self.assertEqual(calls, [])

    def test_entry_accepts_fresh_report_for_same_policy_and_release(self):
        code, result, calls, _ = self.run_approved_trade(action="ENTER", selection_change="report")
        self.assertEqual(code, 0, result)
        self.assertEqual(len(calls), 1)

    def test_entry_rejects_another_buy_marker_appearing_before_submit(self):
        code,result,calls,_=self.run_approved_trade(action="ENTER",pending_entry_at_fence=True)
        self.assertEqual(code,78,result)
        self.assertEqual(result["error_code"],"entry_position_changed_before_submit")
        self.assertEqual(calls,[])

    def test_entry_rejects_account_position_appearing_after_initial_observation(self):
        for positions in ([{"symbol":"BTCUSDC","qty":"0.01"}], [{"symbol":"QQQ","qty":"1"}]):
            with self.subTest(positions=positions):
                code,result,calls,_=self.run_approved_trade(action="ENTER",broker_positions=positions)
                self.assertEqual(code,78,result)
                self.assertEqual(result["error_code"],"entry_position_changed_before_submit")
                self.assertEqual(calls,[])

    def test_exit_rejects_broker_quantity_symbol_or_extra_position_drift(self):
        variants = [[], [{"symbol": "QQQ", "qty": "0.024"}],
                    [{"symbol": "SPY", "qty": "0.025"}],
                    [{"symbol": "QQQ", "qty": "0.025"}, {"symbol": "SPY", "qty": "1"}],
                    [{"symbol": "QQQ", "qty": "NaN"}]]
        for positions in variants:
            with self.subTest(positions=positions):
                code, _, calls, _ = self.run_approved_trade(broker_positions=positions)
                self.assertEqual(code, 78)
                self.assertEqual(calls, [])

    def test_exit_rejects_stale_order_when_owned_and_broker_quantity_change_together(self):
        code, _, calls, _ = self.run_approved_trade(
            changed_owned_qty="0.03", broker_positions=[{"symbol": "QQQ", "qty": "0.03"}],
        )
        self.assertEqual(code, 78)
        self.assertEqual(calls, [])

    def test_entry_and_exit_keep_fresh_position_and_order_limits(self):
        for action, changes in (("EXIT", {"positions": 0}), ("EXIT", {"open_orders": 1}),
                                ("ENTER", {"positions": 1}), ("ENTER", {"open_orders": 1})):
            with self.subTest(action=action, changes=changes):
                code, _, calls, _ = self.run_approved_trade(action=action, fresh_changes=changes)
                self.assertEqual(code, 78)
                self.assertEqual(calls, [])


class LiveRunTest(unittest.TestCase):
    def test_submit_marks_effect_attempted_before_provider_mutation(self):
        observation = {"mode":"live", "paper":False, "account": {"id":"synthetic-native-account-live","cash": "0", "equity": "66"}, "activities_count": 0,
            "clock": {"observed_at": "2026-09-10T08:00:00Z"},
            "open_and_closed_orders_count": 0,
            "positions": [{"symbol": "USDCUSD", "qty": "66", "unrealized_pl": "0"}]}
        snapshot = {"account": {"id":"synthetic-native-account-live","cash": "0", "equity": "66"},
            "available_cash_usd": "66", "clock": {"timestamp": "2026-09-10T08:00:00Z"},
            "crypto": [], "open_orders": 0, "option_quotes": [], "positions": 0,
            "risk": {}, "qqq_asset": {}, "qqq_quote": {}, "spy": {}}
        decision = {"approved": True, "candidate_ref": "crypto://BTC/USDC",
            "candidate": {"asset_class": "crypto"}, "gate": "approved",
            "observed_at": "2026-09-10T08:00:00Z"}
        order = {"asset_class": "crypto", "notional_usd": "10.00", "side": "buy",
            "symbol": "BTC/USDC", "time_in_force": "gtc", "type": "market"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _entry_selection_fixture(root / "state", decision, "live")
            hint = root / "entrypoint-result.json"
            hint.write_text('{"status":"pre_effect_failure","effect":0}\n', encoding="utf-8")
            hint.chmod(0o600)

            def submit_and_check(**_kwargs):
                self.assertEqual(json.loads(hint.read_text(encoding="utf-8")), {
                    "status": "effect_attempted", "effect": 1,
                })
                return {"submitted_at": "now"}

            with patch.dict(MODULE.os.environ, {
                "LIFE_MANAGER_INVESTMENT_MODE": "live", "LIFE_MANAGER_INVESTMENT_DEPLOYMENT": "local",
                "LIFE_MANAGER_INVESTMENT_OWNER_ID": "alpaca-investment-live",
                "LIFE_MANAGER_RUN_ID": "live-entry-hint",
                "LIFE_MANAGER_OCCURRENCE_ID": "alpaca-investment-live:live-entry-hint",
                "LIFE_MANAGER_RELEASE_SHA": "b" * 40,
                "ALPACA_INVESTMENT_LIVE_CREDENTIALS_FILE": str(root / "credentials.json"),
                "ALPACA_INVESTMENT_LIVE_STATE_DIR": str(root / "state"),
                "LIFE_MANAGER_RESULT_HINT_PATH": str(hint),
            }, clear=True), \
                patch.object(MODULE, "reconcile_started", return_value={"pending": 0, "reconciled": 0, "unresolved": 0}), \
                patch.object(MODULE, "observe", return_value=observation), \
                patch.object(MODULE, "read_allocator_snapshot", return_value=snapshot), \
                patch.object(MODULE, "read_crypto_history", return_value={}), \
                patch.object(MODULE, "build_candidates", return_value=[]), \
                patch.object(MODULE, "choose", return_value=decision), \
                patch.object(MODULE, "order_for", return_value=order), \
                patch.object(MODULE, "evaluate_entry", return_value={"approved": True}), \
                patch.object(MODULE, "allocation_gate", return_value={"approved": True}), \
                patch.object(MODULE, "submit_order", side_effect=submit_and_check), \
                patch.object(MODULE, "deliver", return_value={"message_id": "live"}):
                self.assertEqual(MODULE.main(wake_id="live-entry-hint"), 0)
            self.assertEqual(json.loads(hint.read_text(encoding="utf-8")), {
                "status": "effect_attempted", "effect": 1,
            })

    def test_live_entry_persists_execution_identity_and_pending_ownership(self):
        observation = {"mode":"live", "paper":False, "account": {"id":"synthetic-native-account-live","cash": "0", "equity": "66"}, "activities_count": 0,
            "clock": {"observed_at": "2026-09-10T08:00:00Z"},
            "open_and_closed_orders_count": 0,
            "positions": [{"symbol": "USDCUSD", "qty": "66", "unrealized_pl": "0"}]}
        snapshot = {"account": {"id":"synthetic-native-account-live","cash": "0", "equity": "66"},
            "available_cash_usd": "66", "clock": {"timestamp": "2026-09-10T08:00:00Z"},
            "crypto": [], "open_orders": 0, "option_quotes": [], "positions": 0,
            "risk": {}, "qqq_asset": {}, "qqq_quote": {}, "spy": {}}
        decision = {"approved": True, "candidate_ref": "crypto://BTC/USDC",
            "candidate": {"asset_class": "crypto"}, "gate": "approved",
            "observed_at": "2026-09-10T08:00:00Z"}
        order = {"asset_class": "crypto", "notional_usd": "10.00", "side": "buy",
            "symbol": "BTC/USDC", "time_in_force": "gtc", "type": "market"}
        with tempfile.TemporaryDirectory() as directory:
            _entry_selection_fixture(Path(directory) / "state", decision, "live")
            with patch.dict(MODULE.os.environ, {
            "LIFE_MANAGER_INVESTMENT_MODE": "live", "LIFE_MANAGER_INVESTMENT_DEPLOYMENT": "local",
            "LIFE_MANAGER_INVESTMENT_OWNER_ID": "alpaca-investment-live",
            "LIFE_MANAGER_RUN_ID": "live-entry",
            "LIFE_MANAGER_OCCURRENCE_ID": "alpaca-investment-live:live-entry",
            "LIFE_MANAGER_RELEASE_SHA": "d" * 40,
            "ALPACA_INVESTMENT_LIVE_CREDENTIALS_FILE": str(Path(directory) / "credentials.json"),
            "ALPACA_INVESTMENT_LIVE_STATE_DIR": str(Path(directory) / "state")}, clear=True), \
            patch.object(MODULE, "reconcile_started", return_value={"pending": 0, "reconciled": 0, "unresolved": 0}), \
            patch.object(MODULE, "observe", return_value=observation), \
            patch.object(MODULE, "read_allocator_snapshot", return_value=snapshot), \
            patch.object(MODULE, "read_crypto_history", return_value={}), \
            patch.object(MODULE, "build_candidates", return_value=[]), \
            patch.object(MODULE, "choose", return_value=decision), \
            patch.object(MODULE, "order_for", return_value=order), \
            patch.object(MODULE, "evaluate_entry", return_value={"approved": True}), \
            patch.object(MODULE, "allocation_gate", return_value={"approved": True}), \
            patch.object(MODULE, "submit_order", return_value={"submitted_at": "now"}) as submit, \
            patch.object(MODULE, "deliver", return_value={"message_id": "live"}):
                self.assertEqual(MODULE.main(wake_id="live-entry"), 0)
                marker = json.loads((Path(directory) / "state/live-owned-position.json").read_text())
                receipts = [json.loads(line) for line in
                            (Path(directory) / "state/receipts.jsonl").read_text().splitlines()]
                replay_decision = next(row for row in receipts if row["receipt_type"] == "decision")
                replay_intent = next(row for row in receipts if row["receipt_type"] == "effect_intent")
                with patch.dict(EFFECT_STORE.os.environ, {
                    "LIFE_MANAGER_INVESTMENT_DEPLOYMENT": "local",
                    "LIFE_MANAGER_RELEASE_SHA": "e" * 40,
                    "LIFE_MANAGER_RUN_ID": "live-replay",
                    "LIFE_MANAGER_OCCURRENCE_ID": "alpaca-investment-live:live-replay",
                }, clear=True):
                    replay = EFFECT_STORE.seal(
                        Path(directory) / "state/receipts.jsonl",
                        replay_decision["decision"], replay_intent["order"],
                    )
                    self.assertEqual(replay["client_order_id"], replay_intent["client_order_id"])
                    durable_intents = [row for
                                       row in (json.loads(line) for line in
                                               (Path(directory) / "state/receipts.jsonl").read_text().splitlines())
                                       if row.get("receipt_type") == "effect_intent"]
                    self.assertEqual(len(durable_intents), sum(
                        row.get("receipt_type") == "effect_intent" for row in receipts))
                    self.assertEqual(durable_intents[0]["execution_identity"]["run_id"], "live-entry")
        submit.assert_called_once()
        self.assertEqual(marker["status"], "entry_pending")
        self.assertEqual(marker["symbol"], "BTCUSD")
        expected_identity = {
            "owner_id": "alpaca-investment-live",
            "mode": "live",
            "deployment": "local",
            "strategy_id": "alpaca-btc-5m-trend-400-v2",
            "policy_release_sha": "a" * 40,
            "runtime_release_sha": "d" * 40,
            "run_id": "live-entry",
            "occurrence_id": "alpaca-investment-live:live-entry",
            "native_trading_account_id": "synthetic-native-account-live",
        }
        decision_receipt = next(row for row in receipts if row["receipt_type"] == "decision")
        intent_receipts = [row for row in receipts if row["receipt_type"] == "effect_intent"]
        self.assertEqual(decision_receipt.get("execution_identity"), expected_identity)
        self.assertTrue(intent_receipts)
        self.assertTrue(all(row.get("execution_identity") == expected_identity
                            for row in intent_receipts))


class PortablePassTest(unittest.TestCase):
    def _capture_case(self, *, configured_owner=None, occurrence_owner="alpaca-investment-paper", capture_io_error=False,
                      control_status=None, observe_error=False, terminal_summaries=None, allocation_capture=None, initial_owner_costs=None):
        import cost_inventory
        from test_cost_inventory import release_fixture
        steps = []
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            state = Path(directory) / "state"; state.mkdir()
            if initial_owner_costs is not None:
                (state/'allocation-latest.json').write_text(json.dumps({'owner_period_operating_costs':initial_owner_costs}))
            release = Path(directory) / "release"; catalog = release_fixture(release, "b" * 40)
            data = json.loads(catalog.read_text())
            data["loops"][0]["job_ids"].append("alpaca-investment-live")
            catalog.write_text(json.dumps(data))
            environment = {"LIFE_MANAGER_INVESTMENT_DEPLOYMENT": "local", "LIFE_MANAGER_INVESTMENT_MODE": "paper",
                "LIFE_MANAGER_RELEASE_ROOT": str(release), "ALPACA_INVESTMENT_PAPER_STATE_DIR": str(state),
                "ALPACA_INVESTMENT_PAPER_CREDENTIALS_FILE": str(Path(directory) / "credentials"),
                "LIFE_MANAGER_RUN_ID": "capture-run", "LIFE_MANAGER_OCCURRENCE_ID": f"{occurrence_owner}:capture-run"}
            if configured_owner is not None:
                environment["LIFE_MANAGER_INVESTMENT_OWNER_ID"] = configured_owner
            stack.enter_context(patch.dict(MODULE.os.environ, environment, clear=True))
            if capture_io_error:
                sealed = EFFECT_STORE.seal(state / "receipts.jsonl", {"mode": "paper"},
                    {"asset_class": "crypto", "side": "buy", "symbol": "BTC/USDC"})
                EFFECT_STORE.mark_started(state / "receipts.jsonl", sealed)
                def readback(**kwargs):
                    steps.append("readback")
                    return {"status": "accepted", "id": "pending-order", "client_order_id": sealed["client_order_id"]}
                stack.enter_context(patch.object(MODULE, "find_order_by_client_id", side_effect=readback))
                def write_failure(*args, **kwargs):
                    steps.append("capture-error")
                    raise OSError("isolated capture write failure")
                stack.enter_context(patch.object(cost_inventory, "_append_once", side_effect=write_failure))
            observation = {"account": {"cash": "100000", "equity": "100000"}, "activities_count": 0,
                "clock": {"observed_at": "2026-10-18T04:11:18Z"}, "open_and_closed_orders_count": 0, "positions": []}
            for name, value in {"observe": observation, "read_campaign_snapshot": {},
                "reconcile": {"exit_status": "CLOSED", "unrealized_pnl_usd": "0"},
                "read_allocator_snapshot": {"risk": {}}, "build_candidates": [],
                "choose": {"approved": False, "action": "HOLD", "strategy_id": "other-strategy",
                    "candidate_ref": "NO_TRADE", "gate": "policy_hold", "observed_at": "2026-10-18T04:11:18Z"},
                "deliver": {"message_id": "isolated-test"}, "deliver_failure": {"status": "delivered"}}.items():
                stack.enter_context(patch.object(MODULE, name, return_value=value))
            if control_status:
                stack.enter_context(patch.object(MODULE, "read_control", return_value={
                    "paused": control_status == "paused", "killed": control_status == "killed"}))
                stack.enter_context(patch.object(MODULE, "deliver_control", return_value={"message_id": "control-test"}))
            if observe_error:
                stack.enter_context(patch.object(MODULE, "observe", side_effect=ValueError("isolated observe failure")))
                stack.enter_context(patch.object(MODULE, "_retry_allowed", return_value=False))
            submit = stack.enter_context(patch.object(MODULE, "submit_order"))
            with redirect_stdout(StringIO()) as output:
                code = MODULE.main(wake_id="capture-run")
            if terminal_summaries is not None:
                terminal_summaries.extend(json.loads(line) for line in output.getvalue().splitlines())
            rows = [json.loads(line) for line in (state / "receipts.jsonl").read_text().splitlines()]
            pending = EFFECT_STORE.unresolved_intent_count(state / "receipts.jsonl")
            submit.assert_not_called()
            if allocation_capture is not None and (state/'allocation-latest.json').exists():
                allocation_capture.update(json.loads((state/'allocation-latest.json').read_text()))
            return code, rows, steps, pending

    def test_local_hold_reports_owner_period_costs_without_a_trade(self):
        snapshot={'report_scope':'owner_period_operating_costs','model_cost_usd':None,'net_pnl_usd':None,
            'capital_expansion_allowed':False}
        saved={}
        with patch.object(MODULE,'read_owner_period_costs',return_value=snapshot,create=True) as costs:
            code,rows,_steps,pending=self._capture_case(configured_owner='alpaca-investment-paper',allocation_capture=saved)
        self.assertEqual(code,0);self.assertEqual(pending,0)
        costs.assert_called_once()
        self.assertEqual(saved.get('owner_period_operating_costs'),snapshot)
        self.assertEqual(saved['action'],'HOLD')

    def test_owner_period_reader_gets_full_paper_economic_context(self):
        scope={'owner_id':'alpaca-investment-paper','mode':'paper','paper':True,'order_ids':['buy','sell'],
            'period_start':'2026-10-16T00:00:00Z','closed_at':'2026-10-17T01:00:00Z','source_receipt_ids':['native-fill']}
        producer={'completed_round_trips':0,'completed_round_trips_total':1,'expected_cost_inventory':{'scopes':[]},
            'economic_cost_scopes':[scope]}
        with patch.object(MODULE,'write_paper_performance',return_value=producer),              patch.object(MODULE,'read_owner_period_costs',return_value={},create=True) as costs:
            code,_rows,_steps,_pending=self._capture_case(configured_owner='alpaca-investment-paper')
        self.assertEqual(code,0)
        self.assertEqual(costs.call_args.kwargs['economic_scopes'],[scope])

    def test_owner_period_reporting_interruption_retains_previous_snapshot(self):
        previous={'report_scope':'owner_period_operating_costs','owner_id':'alpaca-investment-paper',
            'mode':'paper','paper':True,'observed_at':'2026-10-17T01:00:00Z',
            'known_operating_cost_source_evidence':[],'model_cost_usd':None}
        saved={}
        with patch.object(MODULE,'read_owner_period_costs',side_effect=RuntimeError('isolated reporting interruption'),create=True):
            code,_rows,_steps,pending=self._capture_case(configured_owner='alpaca-investment-paper',
                initial_owner_costs=previous,allocation_capture=saved)
        self.assertNotEqual(code,0);self.assertEqual(pending,0)
        self.assertEqual(saved['owner_period_operating_costs'],previous)
        self.assertEqual(saved['action'],'HOLD')

    def test_paper_capture_does_not_accept_live_or_default_live_owner(self):
        for owner in (None, "alpaca-investment-live"):
            with self.subTest(owner=owner):
                code, rows, _steps, _pending = self._capture_case(configured_owner=owner,
                    occurrence_owner="alpaca-investment-live")
                self.assertEqual(code, 0)
                self.assertFalse(any(row["receipt_type"] == "cost_source_inventory" for row in rows))

    def test_inventory_gap_survives_control_and_failure_terminal_summaries(self):
        for status in ("paused", "killed", "blocked"):
            with self.subTest(status=status):
                summaries = []
                code, _rows, steps, pending = self._capture_case(
                    configured_owner="alpaca-investment-paper", capture_io_error=True,
                    control_status=status if status != "blocked" else None,
                    observe_error=status == "blocked", terminal_summaries=summaries)
                self.assertEqual(code, 78 if status == "blocked" else 0)
                self.assertEqual(summaries[-1]["status"], status)
                self.assertEqual(summaries[-1]["cost_inventory_capture"]["reason"], "source_inventory_write_failed")
                self.assertIsNone(summaries[-1]["cost_inventory_capture"]["appended"])
                self.assertEqual(pending, 1)
                self.assertLess(steps.index("readback"), steps.index("capture-error"))

    def test_inventory_io_failure_cannot_prevent_pending_order_readback(self):
        code, _rows, steps, pending = self._capture_case(configured_owner="alpaca-investment-paper", capture_io_error=True)
        self.assertIn("readback", steps)
        self.assertLess(steps.index("readback"), steps.index("capture-error"))
        self.assertEqual(code, 0)
        self.assertEqual(pending, 1)


    def test_paper_etf_hold_binds_nonfinancial_evidence_to_exact_execution(self):
        cases = (
            ("paper", "alpaca-etf-126d-momentum-v1", "HOLD", True, True),
            ("paper", "alpaca-etf-126d-momentum-v1", "HOLD", False, True),
            ("shadow", "alpaca-etf-126d-momentum-v1", "HOLD", True, False),
            ("paper", "other-strategy", "HOLD", True, False),
            ("paper", "alpaca-etf-126d-momentum-v1", "NO_TRADE", True, False),
        )
        for mode, strategy, action, bound, expected in cases:
            with self.subTest(mode=mode, strategy=strategy, action=action, bound=bound), \
                    tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                from test_cost_inventory import release_fixture
                release = Path(directory) / "release"
                release_fixture(release, "b" * 40)
                state = Path(directory) / "state"
                environment = {
                    "LIFE_MANAGER_INVESTMENT_DEPLOYMENT": "local",
                    "LIFE_MANAGER_RELEASE_ROOT": str(release),
                    "LIFE_MANAGER_INVESTMENT_OWNER_ID": "alpaca-investment-paper" if mode == "paper" else "alpaca-investment-live",
                    "LIFE_MANAGER_INVESTMENT_MODE": mode,
                    f"ALPACA_INVESTMENT_{mode.upper()}_STATE_DIR": str(state),
                    f"ALPACA_INVESTMENT_{mode.upper()}_CREDENTIALS_FILE": str(Path(directory) / "credentials"),
                }
                if bound:
                    environment.update({"LIFE_MANAGER_RUN_ID": "hold-run-1",
                        "LIFE_MANAGER_OCCURRENCE_ID": "alpaca-investment-paper:hold-run-1"})
                stack.enter_context(patch.dict(MODULE.os.environ, environment, clear=True))
                observation = {"account": {"cash": "100000", "equity": "100000"},
                    "activities_count": 0, "clock": {"observed_at": "2026-10-18T04:11:18Z"},
                    "open_and_closed_orders_count": 0, "positions": []}
                decision = {"approved": False, "action": action, "strategy_id": strategy,
                    "candidate_ref": "NO_TRADE", "gate": "policy_hold",
                    "release_sha": "a" * 40, "expected_cost_usd": None,
                    "observed_at": "2026-10-18T04:11:18Z"}
                for name, value in {
                    "reconcile_started": {"pending": 0, "reconciled": 0, "unresolved": 0},
                    "observe": observation, "read_campaign_snapshot": {},
                    "reconcile": {"exit_status": "CLOSED", "unrealized_pnl_usd": "0"},
                    "read_allocator_snapshot": {"risk": {}}, "build_candidates": [],
                    "choose": decision, "deliver": {"message_id": "local-test"},
                }.items():
                    stack.enter_context(patch.object(MODULE, name, return_value=value))
                submit = stack.enter_context(patch.object(MODULE, "submit_order"))
                with redirect_stdout(StringIO()):
                    self.assertEqual(MODULE.main(wake_id="hold-run-1"), 0)
                allocation = json.loads((state / "allocation-latest.json").read_text())
                rows = [json.loads(line) for line in (state / "receipts.jsonl").read_text().splitlines()]
                saved = next(row["decision"] for row in rows if row["receipt_type"] == "decision")
                for actual in (allocation, saved):
                    if expected:
                        self.assertEqual(actual.get("decision_execution"), {
                            "run_id": "hold-run-1" if bound else None,
                            "occurrence_id": "alpaca-investment-paper:hold-run-1" if bound else None,
                            "scope": "allocation_decision", "model_invocation": "not_invoked",
                        })
                    else:
                        self.assertNotIn("decision_execution", actual)
                    self.assertEqual(actual["release_sha"], "a" * 40)
                    self.assertIsNone(actual["expected_cost_usd"])
                    self.assertNotIn("model_cost_usd", actual)
                snapshots = [row for row in rows if row["receipt_type"] == "cost_source_inventory"]
                self.assertEqual(len(snapshots), int(mode == "paper" and bound))
                if snapshots:
                    self.assertEqual(snapshots[0]["release_sha"], "b" * 40)
                submit.assert_not_called()

    @patch.object(MODULE, "reconcile_started", return_value={"pending": 0, "reconciled": 0, "unresolved": 0})
    @patch.object(MODULE, "observe")
    @patch.object(MODULE, "read_campaign_snapshot", return_value={})
    @patch.object(MODULE, "reconcile")
    @patch.object(MODULE, "read_allocator_snapshot", return_value={"risk": {}})
    @patch.object(MODULE, "build_candidates", return_value=[])
    @patch.object(MODULE, "choose")
    @patch.object(MODULE, "deliver", return_value={"message_id": "123"})
    def test_success_has_no_dashboard_effect_or_public_summary(
        self, _deliver, choose, _build, _allocator, reconcile,
        _campaign, observe, _reconcile_started,
    ):
        observe.return_value = {
            "account": {"cash": "100000", "equity": "100000"},
            "activities_count": 0, "clock": {"observed_at": "2026-09-05T00:00:00Z"},
            "open_and_closed_orders_count": 0, "positions": [],
        }
        reconcile.return_value = {"exit_status": "CLOSED", "unrealized_pnl_usd": "0"}
        choose.return_value = {
            "approved": False, "candidate_ref": "NO_TRADE", "gate": "model_no_trade",
            "observed_at": "2026-09-05T00:00:00Z",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable, marker = _publisher_probe(root)
            result_hint = root / "entrypoint-result.json"
            result_hint.write_text('{"status":"pre_effect_failure","effect":0}\n', encoding="utf-8")
            result_hint.chmod(0o600)
            with patch.dict(MODULE.os.environ, {
                "ALPACA_INVESTMENT_STATE_DIR": str(root / "state"),
                "NODE_BIN": str(executable), "ALPACA_MARKER": str(marker),
                "LIFE_MANAGER_INVESTMENT_DEPLOYMENT": "local",
                "LIFE_MANAGER_INVESTMENT_MODE": "paper",
                "LIFE_MANAGER_OCCURRENCE_ID": "alpaca-investment-paper:wake-success",
                "LIFE_MANAGER_RESULT_HINT_PATH": str(result_hint),
            }), redirect_stdout(StringIO()) as output:
                self.assertEqual(MODULE.main(wake_id="wake-success"), 0)
            self.assertFalse(marker.exists())
            self.assertEqual(json.loads(result_hint.read_text(encoding="utf-8")), {
                "schema_version": 1,
                "kind": "life_manager_no_effect_result",
                "status": "verified_no_effect",
                "effect": 0,
                "owner_id": "alpaca-investment-paper",
                "occurrence_id": "alpaca-investment-paper:wake-success",
                "reason": "no_broker_order_submitted",
            })
            summary = json.loads(output.getvalue())
            self.assertNotIn("public_snapshot_published", summary)
            self.assertEqual(summary["deployment"], "local")
            self.assertEqual(summary["mode"], "paper")
            receipts = [
                json.loads(line)
                for line in (root / "state" / "receipts.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            decision_receipt = next(
                receipt for receipt in receipts
                if receipt["receipt_type"] == "decision"
            )
            self.assertEqual(decision_receipt["decision"]["deployment"], "local")

    @patch.object(MODULE, "reconcile_started", return_value={"pending": 0, "reconciled": 0, "unresolved": 0})
    @patch.object(MODULE, "observe", side_effect=RuntimeError("provider unavailable"))
    @patch.object(MODULE, "deliver_failure", return_value={"message_id": "123", "status": "delivered"})
    def test_terminal_failure_has_no_dashboard_effect(self, _deliver, _observe, _reconcile):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable, marker = _publisher_probe(root)
            with patch.dict(MODULE.os.environ, {
                "ALPACA_INVESTMENT_STATE_DIR": str(root / "state"),
                "NODE_BIN": str(executable), "ALPACA_MARKER": str(marker),
                "LIFE_MANAGER_INVESTMENT_DEPLOYMENT": "local",
                "LIFE_MANAGER_INVESTMENT_MODE": "paper",
            }), redirect_stdout(StringIO()) as output:
                self.assertEqual(MODULE.main(wake_id="wake-failure"), 78)
            self.assertFalse(marker.exists())
            self.assertEqual(json.loads(output.getvalue())["mode"], "paper")


class FailureTelegramTest(unittest.TestCase):
    @patch.object(CLI.subprocess, "run")
    def test_cli_failure_code_identifies_only_the_safe_operation(self, run):
        run.return_value.returncode = 1
        with self.assertRaisesRegex(
            ValueError, "^alpaca_cli_failed:account_get$"
        ):
            CLI._run(Path("/safe/alpaca"), ["account", "get", "--secret", "hidden"], {})

    def test_prefixed_provider_payload_is_not_emitted(self):
        error = ValueError("alpaca_cli_failed:account_get:provider-payload-SECRET")
        self.assertEqual(MODULE._error_code(error), "ValueError")

    def test_known_internal_failure_code_is_emitted_exactly(self):
        error = ValueError("alpaca_allocator_shape_invalid")
        self.assertEqual(MODULE._error_code(error), "alpaca_allocator_shape_invalid")
        tainted = ValueError("alpaca_allocator_shape_invalid:provider-payload-SECRET")
        self.assertEqual(MODULE._error_code(tainted), "ValueError")

    @patch.object(MODULE, "deliver_failure", create=True)
    @patch.object(MODULE, "observe", side_effect=RuntimeError("provider payload must stay private"))
    @patch.object(MODULE, "reconcile_started", return_value={"pending": 0, "reconciled": 0, "unresolved": 0})
    def test_terminal_failure_reports_once_after_internal_retries(
        self, _reconcile, observe, deliver_failure
    ):
        deliver_failure.return_value = {"message_id": "123", "status": "delivered"}
        with patch.dict(MODULE.os.environ, {
            "LIFE_MANAGER_INVESTMENT_DEPLOYMENT": "local",
            "LIFE_MANAGER_INVESTMENT_MODE": "paper",
        }), redirect_stdout(StringIO()) as output:
            self.assertEqual(MODULE.main(), 78)
        self.assertEqual(observe.call_count, 3)
        deliver_failure.assert_called_once()
        self.assertEqual(deliver_failure.call_args.kwargs["stage"], "observe")
        self.assertFalse(deliver_failure.call_args.kwargs["effect_uncertain"])
        self.assertNotIn("provider payload", str(deliver_failure.call_args))
        receipt = json.loads(output.getvalue())
        self.assertEqual(receipt["error_code"], "RuntimeError")
        self.assertNotIn("provider payload", output.getvalue())

    def test_telegram_delivery_failure_is_not_retried(self):
        self.assertFalse(MODULE._retry_allowed("telegram_deliver", False, 0))
        self.assertTrue(MODULE._retry_allowed("observe", False, 0))

    def test_reconciliation_failure_does_not_claim_that_no_order_exists(self):
        message = REPORTER.render_failure(
            stage="reconcile_started", effect_uncertain=True,
            wake_id="2026-09-04T00:00:00Z",
        )
        self.assertIn("送信した可能性", message)
        self.assertNotIn("注文は実行していません", message)

    def test_terminal_effect_is_unknown_after_submit(self):
        self.assertEqual(MODULE._terminal_effect(False), "none")
        self.assertEqual(MODULE._terminal_effect(True), "unknown")


if __name__ == "__main__":
    unittest.main()
