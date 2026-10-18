#!/usr/bin/env python3
"""One finite Alpaca investment pass."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from allocator import _read_selection, build_candidates, choose, gate as allocation_gate, order_for
from alpaca_cli import (CLI_OPERATIONS, SAFE_ERROR_CODES, find_order_by_client_id, observe,
                        read_allocator_snapshot, read_campaign_snapshot, read_crypto_history,
                        read_paper_etf_cost_evidence, read_crypto_activity_evidence, read_crypto_activity_page_chunk, submit_order)
from campaign import CANDIDATE_REF, SYMBOLS, exit_order, reconcile
from control import control_fence, read_control
from effect_store import (ReconciliationPending, mark_started, record_no_fill_account_receipt, reconcile_started, record_no_trade, seal,
                          unresolved_intent_count)
from etf_ownership import ETF_PAPER_OWNER_ID, ETF_STRATEGY_ID, investment_owner_id
from etf_ownership import _account_position as validate_etf_position_readback
from etf_ownership import read_state as read_etf_state
from etf_ownership import record_closed as record_etf_closed
from etf_ownership import record_filled as record_etf_filled
from paper_performance import write_paper_performance
from crypto_performance import write_crypto_performance
from cost_inventory import record_source_inventory
from reporter import deliver, deliver_control, deliver_failure
from position_manager import choose as choose_position, exit_order as live_exit_order, load_owned_policy, close_fill_proof, recorded_close_fill_proof
from position_manager import recorded_entry_fill_proof, historical_entry_fill_proof
from crypto_ownership_proof import BROKER_TERMINAL_FAILURE_STATUSES, _filled_qty_positive, entry_fill_proof_from_rows, recorded_entry_proof_from_rows, sell_remainder_proof_from_rows
from strategy_policy import INDICATOR_HISTORY_CONTRACTS, load_selected_card, validate_policy_card
from review_status import read_receipt as read_application_status
from review_status import refresh as refresh_application_status
from risk_policy import evaluate_entry, parse_instant


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _mark_external_effect_attempted() -> None:
    """Invalidate the host's pre-effect proof immediately before submission."""
    hint = os.environ.get("LIFE_MANAGER_RESULT_HINT_PATH")
    if hint:
        _atomic_json(Path(hint), {"status": "effect_attempted", "effect": 1})


def _mark_no_broker_order_submitted(mode: str, effect_attempted: bool,
                                    effect: str) -> None:
    """Bind a successful no-order pass to its exact managed occurrence."""
    if effect_attempted or effect != "none":
        return
    owner_id = {
        "paper": "alpaca-investment-paper",
        "live": "alpaca-investment-live",
    }.get(mode)
    occurrence_id = os.environ.get("LIFE_MANAGER_OCCURRENCE_ID", "")
    hint = os.environ.get("LIFE_MANAGER_RESULT_HINT_PATH")
    prefix, separator, suffix = occurrence_id.partition(":")
    if (owner_id is None or prefix != owner_id or not separator or not suffix
            or len(suffix) > 200 or not suffix.isascii()
            or any(not (character.isalnum() or character in "._-")
                   for character in suffix) or not hint):
        return
    _atomic_json(Path(hint), {
        "schema_version": 1,
        "kind": "life_manager_no_effect_result",
        "status": "verified_no_effect",
        "effect": 0,
        "owner_id": owner_id,
        "occurrence_id": occurrence_id,
        "reason": "no_broker_order_submitted",
    })


def _retry_allowed(stage: str, effect_attempted: bool, attempt: int) -> bool:
    return stage != "telegram_deliver" and not effect_attempted and attempt < 2


def _terminal_effect(effect_attempted: bool) -> str:
    return "unknown" if effect_attempted else "none"


def _reconciliation_is_pending(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    deferred = value.get("deferred", 0)
    unresolved = value.get("unresolved")
    return (
        isinstance(deferred, int) and not isinstance(deferred, bool) and deferred > 0
        and unresolved == deferred
    )


def _error_code(error: Exception) -> str:
    value = str(error)
    if value in SAFE_ERROR_CODES:
        return value
    for prefix in ("alpaca_cli_failed:", "alpaca_cli_timeout:"):
        if value.startswith(prefix) and value.removeprefix(prefix) in CLI_OPERATIONS:
            return value
    return type(error).__name__


def _deployment() -> str:
    value = os.environ.get("LIFE_MANAGER_INVESTMENT_DEPLOYMENT")
    if value not in {"local", "cloud"}:
        raise ValueError("investment_deployment_invalid")
    return value


def _mode() -> str:
    value = os.environ.get("LIFE_MANAGER_INVESTMENT_MODE")
    if value not in {"paper", "shadow", "live"}:
        raise ValueError("investment_mode_invalid")
    return value


def _mode_paths(mode: str) -> tuple[Path, Path]:
    if mode not in {"paper", "shadow", "live"}:
        raise ValueError("investment_mode_invalid")
    suffix = mode.upper()
    credentials = os.environ.get(f"ALPACA_INVESTMENT_{suffix}_CREDENTIALS_FILE")
    state = os.environ.get(f"ALPACA_INVESTMENT_{suffix}_STATE_DIR")
    if mode == "paper":
        credentials = credentials or os.environ.get("ANICCA_CREDENTIALS_FILE") \
            or "~/.local/share/anicca/credentials.json"
        state = state or os.environ.get("ALPACA_INVESTMENT_STATE_DIR") \
            or "~/.local/state/life-manager/alpaca-investment"
    elif not credentials or not state:
        raise ValueError("investment_mode_paths_missing")
    selected_state = Path(state).expanduser()
    selected_resolved = selected_state.resolve()
    paper_state = (os.environ.get("ALPACA_INVESTMENT_PAPER_STATE_DIR")
                   or os.environ.get("ALPACA_INVESTMENT_STATE_DIR")
                   or "~/.local/state/life-manager/alpaca-investment")
    for other, other_state in (
        ("paper", paper_state),
        ("shadow", os.environ.get("ALPACA_INVESTMENT_SHADOW_STATE_DIR")),
        ("live", os.environ.get("ALPACA_INVESTMENT_LIVE_STATE_DIR")),
    ):
        if other != mode and other_state and selected_resolved == Path(other_state).expanduser().resolve():
            raise ValueError("investment_mode_state_path_conflict")
    return Path(credentials).expanduser(), selected_state


def _review_status(state: Path, mode: str, deployment: str) -> dict:
    current = read_application_status(state)
    if mode != "paper" or deployment != "local" or not current:
        return current
    try:
        return refresh_application_status(state)
    except Exception:
        return current


def _nonpaper_campaign(observation: dict) -> dict:
    try:
        positions = observation["positions"]
        if not isinstance(positions, list):
            raise ValueError
        unrealized = sum((Decimal(str(row["unrealized_pl"])) for row in positions), Decimal("0"))
        if not unrealized.is_finite():
            raise ValueError
    except (KeyError, InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("investment_nonpaper_observation_invalid") from error
    return {"exit_status": "NOT_APPLICABLE", "paper": False,
            "positions": positions, "realized_pnl_usd": None,
            "unrealized_pnl_usd": str(unrealized)}


def _owned_paper_symbols(state: Path) -> frozenset[str]:
    etf_state = read_etf_state(
        state / "etf-owned-position.json", owner_id=investment_owner_id(),
    )
    position = etf_state["position"]
    symbols = {position["symbol"]} if position is not None else set()
    try:
        ownership = json.loads((state / "live-owned-position.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        ownership = None
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("live_position_not_owned") from error
    if ownership is not None:
        if not isinstance(ownership, dict):
            raise ValueError("live_position_not_owned")
        if ownership.get("status") in {"open", "closing"}:
            load_owned_policy(state, ownership, mode="paper")
            symbols.update({"BTCUSD", "BTCUSDC", "BTC/USDC"})
    return frozenset(symbols)


def _paper_campaign(*, state: Path, credentials_path: Path, cli_path: Path) -> dict:
    return reconcile(
        read_campaign_snapshot(
            credentials_path=credentials_path, cli_path=cli_path, symbols=SYMBOLS,
        ),
        allowed_external_symbols=_owned_paper_symbols(state),
    )


def _normalize_live_position_symbols(observation: dict) -> dict:
    positions = observation.get("positions")
    if not isinstance(positions, list):
        raise ValueError("live_position_not_owned")
    for row in positions:
        if not isinstance(row, dict):
            raise ValueError("live_position_not_owned")
        if row.get("symbol") in {"BTCUSD", "BTCUSDC", "BTC/USDC"}:
            row["symbol"] = "BTCUSD"
    return observation


def _sync_live_ownership(state: Path, credentials_path: Path, cli_path: Path,
                         observation: dict) -> dict | None:
    path = state / "live-owned-position.json"
    try:
        ownership = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as error:
        raise ValueError("live_position_not_owned") from error
    btc = [row for row in observation.get("positions", []) if row.get("symbol") == "BTCUSD"]
    if len(btc) > 1 or ownership.get("symbol") != "BTCUSD":
        raise ValueError("live_position_not_owned")
    if (ownership.get("status") in {"open", "closing", "closed"}
            and ((ownership.get("close_effect_id") is None) != (ownership.get("close_client_order_id") is None))):
        raise ValueError("owned_closed_identity_invalid")
    order_key = ("close_client_order_id" if ownership.get("status") in {"open", "closing", "closed"}
                 and ownership.get("close_client_order_id") is not None else "entry_client_order_id")
    broker = find_order_by_client_id(credentials_path=credentials_path, cli_path=cli_path,
                                     client_order_id=ownership.get(order_key, ""))
    status = broker.get("status") if broker else "absent"
    if ownership.get("status") == "entry_pending":
        if btc and (status == "filled" or (status in BROKER_TERMINAL_FAILURE_STATUSES and _filled_qty_positive(broker))):
            try:
                proof = recorded_entry_fill_proof(state, ownership, broker, observation,
                                                  mode=os.environ.get("LIFE_MANAGER_INVESTMENT_MODE"))
            except ValueError:
                return ownership
            try:
                for key, expected in (("entry_filled_qty", proof["receipt"]["entry_filled_qty"]),
                                      ("owned_qty", proof["receipt"]["account_owned_qty"])):
                    if key == "owned_qty" and ownership.get(key) is None:
                        continue
                    known = Decimal(str(ownership.get(key)))
                    if (not known.is_finite() or known < 0
                            or (known != Decimal(expected) and not (key == "entry_filled_qty" and known == 0))):
                        raise ValueError
            except (InvalidOperation, ValueError, TypeError) as error:
                raise ValueError("owned_entry_account_invalid") from error
            ownership["status"] = "open"
            ownership["entry_filled_qty"] = proof["receipt"]["entry_filled_qty"]
            ownership["owned_qty"] = proof["receipt"]["account_owned_qty"]
            ownership["entry_timestamp"] = proof["receipt"]["entry_timestamp"]
            _atomic_json(path, ownership)
        elif status in BROKER_TERMINAL_FAILURE_STATUSES and not btc:
            try:
                record_no_fill_account_receipt(state / "receipts.jsonl", ownership, broker, observation,
                    mode=os.environ.get("LIFE_MANAGER_INVESTMENT_MODE"), owner_id=investment_owner_id())
            except ValueError:
                return ownership
            ownership["status"] = "closed"
            _atomic_json(path, ownership)
    elif ownership.get("status") == "open":
        mode = os.environ.get("LIFE_MANAGER_INVESTMENT_MODE")
        if observation.get("mode") != mode or observation.get("paper") is not (mode == "paper"):
            raise ValueError("owned_entry_account_invalid")
        try:
            historical_entry_fill_proof(state, ownership, mode=mode)
        except ValueError:
            return {**ownership, "status": "entry_pending"}
        if ownership.get("close_effect_id") is not None:
            proof = recorded_close_fill_proof(state, ownership, broker, observation, mode=mode)
            if (proof['receipt'].get('kind') != 'owned_crypto_sell_remainder'
                    or Decimal(proof['receipt']['remaining_owned_qty']) <= 0):
                raise ValueError('owned_sell_proof_invalid')
    elif ownership.get("status") == "closing":
        if status in BROKER_TERMINAL_FAILURE_STATUSES:
            try:
                proof = recorded_close_fill_proof(state, ownership, broker, observation,
                    mode=os.environ.get("LIFE_MANAGER_INVESTMENT_MODE"))
            except ReconciliationPending:
                return ownership
            except ValueError as error:
                if str(error) == 'owned_sell_receipt_missing':
                    return ownership
                raise
            remaining = Decimal(proof['receipt']['remaining_owned_qty'])
            ownership['status'] = 'open' if remaining > 0 else 'closed'
            if remaining > 0:
                ownership['owned_qty'] = proof['receipt']['remaining_owned_qty']
            _atomic_json(path, ownership)
        elif status == "filled" and not btc:
            mode = os.environ.get("LIFE_MANAGER_INVESTMENT_MODE")
            try:
                recorded_close_fill_proof(state, ownership, broker, observation, mode=mode)
            except ReconciliationPending:
                return ownership
            ownership["status"] = "closed"
            _atomic_json(path, ownership)
    elif ownership.get("status") == "closed":
        if ownership.get("close_effect_id") is not None:
            try:
                recorded_close_fill_proof(state, ownership, broker, observation,
                                          mode=os.environ.get("LIFE_MANAGER_INVESTMENT_MODE"))
            except ReconciliationPending:
                return {**ownership, "status": "closing"}
        else:
            record_no_fill_account_receipt(state / "receipts.jsonl", ownership, broker, observation,
                mode=os.environ.get("LIFE_MANAGER_INVESTMENT_MODE"), owner_id=investment_owner_id())
    return ownership


def _owned_live_position(ownership: dict | None, observation: dict) -> None:
    btc = [row for row in observation.get("positions", []) if row.get("symbol") == "BTCUSD"]
    if ownership is None or ownership.get("status") != "open" or len(btc) != 1:
        raise ValueError("live_position_not_owned")
    try:
        qty = Decimal(str(btc[0]["qty"]))
        filled = Decimal(str(ownership["entry_filled_qty"]))
        owned = Decimal(str(ownership["owned_qty"]))
    except (InvalidOperation, KeyError, TypeError) as error:
        raise ValueError("live_position_not_owned") from error
    if qty <= 0 or qty > filled or qty != owned:
        raise ValueError("live_position_not_owned")


def _reconcile_etf_intent(
    intent: dict,
    provider_order: dict,
    *,
    credentials_path: Path,
    cli_path: Path,
    state_path: Path,
) -> dict:
    """Close an ETF effect only after fill, account, and ownership readback."""
    if (intent.get("mode") != "paper" or intent.get("owner_id") != investment_owner_id()
            or intent.get("strategy_id") != ETF_STRATEGY_ID
            or not isinstance(intent.get("order"), dict)
            or intent["order"].get("asset_class") != "us_equity"):
        raise ValueError("etf_order_identity_invalid")
    account_readback = observe(credentials_path=credentials_path, cli_path=cli_path)
    side = intent["order"].get("side")
    if side == "sell":
        record = record_etf_closed
    elif side == "buy":
        record = record_etf_filled
    else:
        raise ValueError("etf_order_shape_invalid")
    receipt = record(
        state_path,
        owner_id=intent["owner_id"],
        strategy_id=intent["strategy_id"],
        decision_session=intent.get("decision_session"),
        client_order_id=intent["client_order_id"],
        order=provider_order,
        account_readback=account_readback,
        source_receipt_ids=intent.get("source_receipt_ids", []),
    )
    return {"receipt": receipt, "observation": account_readback}




def _reconcile_crypto_entry(intent: dict, provider_order: dict, *, state: Path,
                            credentials_path: Path, cli_path: Path) -> dict:
    mode = _mode()
    if (intent.get("mode") != mode or intent.get("owner_id") != investment_owner_id()
            or intent.get("order", {}).get("asset_class") != "crypto" or intent["order"].get("side") != "buy"):
        raise ValueError("owned_entry_account_invalid")
    with control_fence(state):
        ownership = json.loads((state / "live-owned-position.json").read_text(encoding="utf-8"))
        if (not isinstance(ownership, dict) or ownership.get("status") not in {"entry_pending", "open"}
                or ownership.get("entry_effect_id") != intent.get("effect_id")
                or ownership.get("entry_client_order_id") != intent.get("client_order_id")):
            raise ValueError("owned_entry_account_invalid")
        observation = _normalize_live_position_symbols(observe(
            credentials_path=credentials_path, cli_path=cli_path))
        from effect_store import _owned_rows
        rows = _owned_rows(state / "receipts.jsonl")
        if any(r.get("receipt_type") == "outcome" and r.get("effect_id") == intent["effect_id"]
               and r.get("strategy_receipt") is not None for r in rows):
            return recorded_entry_proof_from_rows(rows, ownership, provider_order, observation,
                                                  mode=mode, owner_id=investment_owner_id())
        activity = None
        if provider_order.get("status") in BROKER_TERMINAL_FAILURE_STATUSES:
            activity = read_crypto_activity_evidence(credentials_path=credentials_path, cli_path=cli_path,
                mode=mode, period_start=provider_order.get("submitted_at"),
                period_end=observation["clock"]["observed_at"])
        return entry_fill_proof_from_rows(rows, ownership, provider_order, observation,
                                         mode=mode, owner_id=investment_owner_id(), activity_readback=activity)


def _reconcile_crypto_close(intent: dict, provider_order: dict, *, state: Path,
                            credentials_path: Path, cli_path: Path) -> dict:
    mode = _mode()
    if (intent.get("mode") != mode or intent.get("owner_id") != investment_owner_id()
            or intent.get("order", {}).get("asset_class") != "crypto"
            or intent["order"].get("side") != "sell"):
        raise ValueError("owned_close_proof_invalid")
    with control_fence(state):
        ownership = json.loads((state / "live-owned-position.json").read_text(encoding="utf-8"))
        if (not isinstance(ownership, dict) or ownership.get("close_effect_id") != intent.get("effect_id")
                or ownership.get("close_client_order_id") != intent.get("client_order_id")):
            raise ValueError("owned_close_proof_invalid")
        observation = _normalize_live_position_symbols(observe(
            credentials_path=credentials_path, cli_path=cli_path))
        if provider_order.get('status') in BROKER_TERMINAL_FAILURE_STATUSES:
            from effect_store import _owned_rows
            rows = _owned_rows(state / 'receipts.jsonl')
            if any(r.get('receipt_type') == 'outcome' and r.get('effect_id') == intent['effect_id']
                   and r.get('strategy_receipt') is not None for r in rows):
                return recorded_close_fill_proof(state, ownership, provider_order, observation, mode=mode)
            activities = read_crypto_activity_evidence(credentials_path=credentials_path, cli_path=cli_path,
                mode=mode, period_start=provider_order.get('submitted_at'), period_end=observation['clock']['observed_at'])
            return sell_remainder_proof_from_rows(rows, ownership, provider_order, observation,
                mode=mode, owner_id=investment_owner_id(), activity_readback=activities)
        return close_fill_proof(state, ownership, provider_order, observation, mode=mode)


def _observe_and_sync_live_ownership(
        state: Path, credentials_path: Path, cli_path: Path) -> tuple[dict, dict | None]:
    with control_fence(state):
        observation = _normalize_live_position_symbols(observe(
            credentials_path=credentials_path, cli_path=cli_path))
        ownership = _sync_live_ownership(state, credentials_path, cli_path, observation)
    return observation, ownership


def _closing_marker(ownership: dict, sealed: dict) -> dict:
    return {**ownership, "close_client_order_id": sealed["client_order_id"],
            "close_effect_id": sealed["effect_id"], "status": "closing"}


def _policy_crypto_history(state: Path, ownership: dict | None, *, mode: str,
                           credentials_path: Path, cli_path: Path, observed_at: str) -> dict:
    """Resolve the data contract from the owned entry before a new selection."""
    if ownership is not None and not isinstance(ownership, dict):
        raise ValueError("live_position_not_owned")
    if ownership and ownership.get("status") in {"entry_pending", "closing"}:
        return {}
    try:
        if ownership and ownership.get("status") == "open":
            card = load_owned_policy(state, ownership, mode=mode)["card"]
        else:
            card, _release = load_selected_card(state)
    except ValueError:
        # The decision path reports the exact policy error; do not substitute
        # a different policy or a shorter history for an unresolved owned entry.
        return {}
    if tuple(card.instruments) != ("BTC/USDC",):
        return {}
    contract = INDICATOR_HISTORY_CONTRACTS.get(card.strategy_id)
    options = {"history_bars": contract[2]} if contract is not None else {}
    return read_crypto_history(credentials_path=credentials_path, cli_path=cli_path,
                               observed_at=observed_at, **options)


def main(*, attempt: int = 0, wake_id=None) -> int:
    wake_id = (wake_id or os.environ.get("LIFE_MANAGER_INVESTMENT_WAKE_ID")
               or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    cloud_event_key = os.environ.get("LIFE_MANAGER_INVESTMENT_EVENT_KEY")
    mode = os.environ.get("LIFE_MANAGER_INVESTMENT_MODE")
    state = Path(os.environ.get("ALPACA_INVESTMENT_STATE_DIR",
                               "~/.local/state/life-manager/alpaca-investment")).expanduser()
    effect_attempted = False
    observation = None
    campaign = None
    inventory_capture = None
    stage = "start"
    try:
        mode = _mode()
        credentials_path, state = _mode_paths(mode)
        deployment = _deployment()
        cli_path = Path(os.environ.get("ALPACA_CLI", "~/.local/bin/alpaca")).expanduser()
        reconciled_observation: dict[str, dict] = {}

        def on_reconciled(intent: dict, provider_order: dict) -> dict | None:
            if (intent.get("order", {}).get("asset_class") == "crypto" and intent["order"].get("side") == "buy"):
                result = _reconcile_crypto_entry(intent, provider_order, state=state,
                    credentials_path=credentials_path, cli_path=cli_path)
                reconciled_observation["value"] = result["account_readback"]
                return result
            if (intent.get("order", {}).get("asset_class") == "crypto"
                    and intent["order"].get("side") == "sell"):
                result = _reconcile_crypto_close(intent, provider_order, state=state,
                    credentials_path=credentials_path, cli_path=cli_path)
                reconciled_observation["value"] = result["account_readback"]
                return result
            if intent.get("order", {}).get("asset_class") != "us_equity":
                return
            result = _reconcile_etf_intent(
                intent,
                provider_order,
                credentials_path=credentials_path,
                cli_path=cli_path,
                state_path=state / "etf-owned-position.json",
            )
            reconciled_observation["value"] = result["observation"]
            return {
                "account_readback": result["observation"],
                "receipt": result["receipt"],
            }

        stage = "reconcile_started"
        reconciliation = reconcile_started(
            state / "receipts.jsonl",
            lambda client_order_id: find_order_by_client_id(
                credentials_path=credentials_path,
                cli_path=cli_path,
                client_order_id=client_order_id,
            ),
            on_reconciled=on_reconciled,
        )
        if mode == "paper":
            stage = "cost_inventory_capture"
            if investment_owner_id() != ETF_PAPER_OWNER_ID:
                inventory_capture = {"coverage_state": "gap", "reason": "source_owner_mode_mismatch", "appended": False}
            else:
                inventory_capture = record_source_inventory(state / "receipts.jsonl",
                    release_root=Path(os.environ.get("LIFE_MANAGER_RELEASE_ROOT", str(Path(__file__).resolve().parents[2]))),
                    owner_id=ETF_PAPER_OWNER_ID, run_id=os.environ.get("LIFE_MANAGER_RUN_ID"),
                    occurrence_id=os.environ.get("LIFE_MANAGER_OCCURRENCE_ID"))
        stage = "control_read"
        control = read_control(state / "control.json")
        if control["paused"] or control["killed"]:
            stage = "telegram_deliver"
            telegram = deliver_control(
                state, control=control, wake_id=wake_id, mode=mode,
                event_key=cloud_event_key)
            _mark_no_broker_order_submitted(mode, effect_attempted, "none")
            print(json.dumps({
                **({"cost_inventory_capture": inventory_capture} if inventory_capture is not None else {}),
                "effect": "none", "loop_id": "alpaca-investment", "mode": mode,
                "reconciliation": reconciliation,
                "status": "killed" if control["killed"] else "paused",
                "telegram_message_id": telegram["message_id"],
            }, separators=(",", ":")))
            return 0
        stage = "observe"
        if mode in {"paper", "live"}:
            observation, ownership = _observe_and_sync_live_ownership(
                state, credentials_path, cli_path)
        else:
            observation = observe(
                credentials_path=credentials_path,
                cli_path=cli_path,
            )
            ownership = None
        if "value" in reconciled_observation:
            observation = reconciled_observation["value"]
        stage = "campaign_read"
        if mode == "paper" and ownership and ownership.get("status") in {"entry_pending", "closing"}:
            campaign = {"exit_status": "OWNERSHIP_PENDING", "paper": True,
                        "positions": observation["positions"], "realized_pnl_usd": None,
                        "unrealized_pnl_usd": None}
        else:
            campaign = (_paper_campaign(
                state=state, credentials_path=credentials_path, cli_path=cli_path)
                if mode == "paper" else _nonpaper_campaign(observation))
        effect = "none"
        if campaign["exit_status"] == "EXIT_READY":
            exit_decision = {
                "candidate_ref": CANDIDATE_REF,
                "deployment": deployment,
                "mode": mode,
                "gate": "campaign_exit_ready",
                "paper": mode == "paper",
                "reason": "sealed_campaign_regular_session_positive_credit",
            }
            if mode != "paper":
                exit_decision.update({"approved": False, "gate": f"{mode}_read_only"})
                record_no_trade(state / "receipts.jsonl", exit_decision)
            else:
                exit_order_path = state / "campaign-exit-order.json"
                if exit_order_path.is_file():
                    stage = "campaign_exit_order_read"
                    order = json.loads(exit_order_path.read_text(encoding="utf-8"))
                else:
                    stage = "campaign_exit_order_build"
                    order = exit_order(campaign)
                    _atomic_json(exit_order_path, order)
                stage = "campaign_exit_submit"
                with control_fence(state) as current_control:
                    if current_control["paused"] or current_control["killed"]:
                        telegram = deliver_control(
                            state, control=current_control, wake_id=wake_id, mode=mode,
                            event_key=cloud_event_key)
                        _mark_no_broker_order_submitted(mode, effect_attempted, effect)
                        print(json.dumps({
                            **({"cost_inventory_capture": inventory_capture} if inventory_capture is not None else {}),
                            "effect": "none", "loop_id": "alpaca-investment", "mode": mode,
                            "reconciliation": reconciliation,
                            "status": "killed" if current_control["killed"] else "paused",
                            "telegram_message_id": telegram["message_id"],
                        }, separators=(",", ":")))
                        return 0
                    sealed = seal(state / "receipts.jsonl", exit_decision, order)
                    mark_started(state / "receipts.jsonl", sealed)
                    _mark_external_effect_attempted()
                    effect_attempted = True
                    submit_order(credentials_path=credentials_path, cli_path=cli_path,
                                 client_order_id=sealed["client_order_id"], order=order)
                stage = "campaign_exit_reconcile"
                reconcile_started(
                    state / "receipts.jsonl",
                    lambda value: find_order_by_client_id(
                        credentials_path=credentials_path, cli_path=cli_path, client_order_id=value),
                )
                effect = sealed["effect_id"]
                stage = "campaign_exit_observe"
                observation = observe(credentials_path=credentials_path, cli_path=cli_path)
                if mode == "live":
                    observation = _normalize_live_position_symbols(observation)
                stage = "campaign_exit_campaign_read"
                campaign = _paper_campaign(
                    state=state, credentials_path=credentials_path, cli_path=cli_path)
        stage = "allocator_read"
        allocator_snapshot = read_allocator_snapshot(
            credentials_path=credentials_path, cli_path=cli_path,
            risk_day_path=state / "risk-day.json", include_etf_bars=True)
        allocator_snapshot["mode"] = mode
        if mode == "paper" and not (ownership and ownership.get("status") in {"entry_pending", "open", "closing"}):
            etf_state = read_etf_state(
                state / "etf-owned-position.json", owner_id=investment_owner_id(),
            )
            allocator_snapshot["position"] = etf_state["position"]
            allocator_snapshot["last_decision_session"] = etf_state["last_decision_session"]
        if mode in {"paper", "live"}:
            stage = "market_history_read"
            allocator_snapshot["crypto_history"] = _policy_crypto_history(
                state, ownership, mode=mode, credentials_path=credentials_path, cli_path=cli_path,
                observed_at=allocator_snapshot.get("clock", {}).get("timestamp"))
        unresolved = reconciliation.get("unresolved")
        if isinstance(unresolved, bool) or not isinstance(unresolved, int) or unresolved != 0:
            if not _reconciliation_is_pending(reconciliation):
                raise ValueError("investment_unresolved_intent")
        allocator_snapshot["unresolved_intents"] = unresolved
        candidates = build_candidates(allocator_snapshot)
        stage = "allocation_decide"
        runner = Path(os.environ.get(
            "LIFE_MANAGER_INVESTMENT_AGENT_RUNNER",
            str(Path(__file__).resolve().parents[2] / "runtime/agent-runner/agent_runner.py"),
        )).expanduser()
        workdir = Path(__file__).resolve().parents[2]
        btc_positions = (mode in {"paper", "live"}
            and not (ownership and ownership.get("status") in {"entry_pending", "closing"})
            and ((mode == "live" and allocator_snapshot.get("positions", 0) > 0)
                 or any(row.get("symbol") == "BTCUSD" for row in observation.get("positions", []))))
        if btc_positions:
            _owned_live_position(ownership, observation)
            position = choose_position(allocator_snapshot, observation, state, runner, workdir)
            decision = {"action": position["action"], "owner_id": position.get("owner_id"),
                        **{key: position.get(key) for key in ("entry_effect_id", "entry_client_order_id",
                            "entry_provider_order_id", "entry_price", "entry_timestamp")},
                        "approved": position["action"] == "EXIT",
                        "candidate_ref": "position://BTCUSD", "gate": "position_exit" if position["action"] == "EXIT" else "position_hold",
                        "reason": position["reason"], "position_action": position["action"],
                        "policy_action": position.get("policy_action"),
                        "strategy_id": position.get("strategy_id"),
                        "signal_inputs": position.get("signal_inputs", {}),
                        "expected_cost_usd": position.get("expected_cost_usd"),
                        "release_sha": position.get("release_sha"),
                        "position_qty": position["qty"],
                        "observed_at": allocator_snapshot["clock"]["timestamp"]}
        else:
            if mode in {"paper", "live"} and ownership and ownership.get("status") in {"entry_pending", "open", "closing"}:
                decision = {"approved": False, "candidate_ref": "NO_TRADE",
                            "gate": "ownership_pending", "reason": "既存注文の公式確定を待つ。",
                            "observed_at": allocator_snapshot["clock"]["timestamp"]}
            else:
                decision = choose(allocator_snapshot, candidates, state, runner, workdir)
                if (mode == "paper" and decision.get("strategy_id") == ETF_STRATEGY_ID
                        and decision.get("action") == "HOLD"):
                    # Scope this fact to the pure policy call, never to billed costs.
                    decision["decision_execution"] = {
                        "run_id": os.environ.get("LIFE_MANAGER_RUN_ID"),
                        "occurrence_id": os.environ.get("LIFE_MANAGER_OCCURRENCE_ID"),
                        "scope": "allocation_decision", "model_invocation": "not_invoked",
                    }
        decision["deployment"] = deployment
        decision["mode"] = mode
        decision["risk"] = allocator_snapshot["risk"]
        if decision.get("strategy_id") == ETF_STRATEGY_ID:
            decision["source_receipt_ids"] = allocator_snapshot.get("source_receipt_ids", [])
        if effect != "none" and decision["approved"]:
            decision["approved"] = False
            decision["gate"] = "campaign_exit_used_effect_limit"
        if decision["approved"] and mode in {"paper", "live"}:
            stage = "allocation_order_build"
            order = (live_exit_order({"qty": decision["position_qty"]})
                     if btc_positions else order_for(decision))
            if mode == "live" and not btc_positions:
                if order.get("asset_class") != "crypto" or order.get("symbol") != "BTC/USDC":
                    decision.update({"approved": False, "gate": "live_asset_rejected"})
                    record_no_trade(state / "receipts.jsonl", decision)
                    order = None
            if order is None:
                effect = "none"
            else:
                is_etf_order = order.get("asset_class") == "us_equity"
                stage = "allocation_submit"
                with control_fence(state) as current_control:
                    if current_control["paused"] or current_control["killed"]:
                        telegram = deliver_control(state, control=current_control,
                            wake_id=wake_id, mode=mode, event_key=cloud_event_key)
                        _mark_no_broker_order_submitted(mode, effect_attempted, effect)
                        print(json.dumps({**({"cost_inventory_capture": inventory_capture} if inventory_capture is not None else {}),
                            "effect":"none","loop_id":"alpaca-investment","mode":mode,
                            "reconciliation":reconciliation,"status":"killed" if current_control["killed"] else "paused",
                            "telegram_message_id":telegram["message_id"]}, separators=(",", ":")))
                        return 0
                    # Re-read official slots under the exclusive effect fence so two
                    # overlapping wakes cannot both act on the same stale snapshot.
                    fresh = read_allocator_snapshot(credentials_path=credentials_path,
                        cli_path=cli_path, risk_day_path=state / "risk-day.json",
                        include_etf_bars=True)
                    fresh["mode"] = mode
                    if mode == "paper" and not btc_positions:
                        fresh_etf_state = read_etf_state(
                            state / "etf-owned-position.json", owner_id=investment_owner_id(),
                        )
                        fresh["position"] = fresh_etf_state["position"]
                        fresh["last_decision_session"] = fresh_etf_state["last_decision_session"]
                    fresh["unresolved_intents"] = unresolved_intent_count(state / "receipts.jsonl")
                    paper_etf_exit = (mode == "paper" and is_etf_order
                                      and decision.get("strategy_id") == ETF_STRATEGY_ID
                                      and decision.get("action") == "EXIT")
                    expected_positions = 1 if btc_positions or paper_etf_exit else 0
                    if (fresh.get("open_orders") != 0 or unresolved_intent_count(
                            state / "receipts.jsonl") != 0 or
                            fresh.get("positions") != expected_positions):
                        raise ValueError("investment_effect_fence_rejected")
                    if btc_positions:
                        fresh_observation = _normalize_live_position_symbols(observe(
                            credentials_path=credentials_path, cli_path=cli_path))
                        fresh_ownership = _sync_live_ownership(state, credentials_path, cli_path, fresh_observation)
                        try:
                            _owned_live_position(fresh_ownership, fresh_observation)
                            policy = load_owned_policy(state, fresh_ownership, mode=mode)
                            if (any(policy[key] != decision.get(key) for key in (
                                    "entry_effect_id", "entry_client_order_id", "entry_provider_order_id", "owner_id", "mode"))
                                    or policy["card"].strategy_id != decision.get("strategy_id")
                                    or policy["release_sha"] != decision.get("release_sha")
                                    or Decimal(policy["entry_price"]) != Decimal(decision["entry_price"])
                                    or parse_instant(policy["entry_timestamp"]) != parse_instant(decision["entry_timestamp"])
                                    or parse_instant(policy["entry_timestamp"]) > parse_instant(fresh["clock"]["timestamp"])
                                    or Decimal(policy["owned_qty"]) != Decimal(order["qty"])
                                    or Decimal(policy["owned_qty"]) != Decimal(decision["position_qty"])
                                    or order.get("asset_class") != "crypto" or order.get("symbol") != "BTC/USDC"
                                    or order.get("side") != "sell" or order.get("type") != "market"
                                    or order.get("time_in_force") != "gtc"):
                                raise ValueError("owned_position_changed_before_submit")
                        except (ValueError, KeyError, TypeError, InvalidOperation) as error:
                            raise ValueError("owned_position_changed_before_submit") from error
                        ownership, observation = fresh_ownership, fresh_observation
                    if order.get("asset_class") == "crypto" and order.get("side") == "buy":
                        fresh_observation = _normalize_live_position_symbols(observe(
                            credentials_path=credentials_path, cli_path=cli_path))
                        fresh_ownership = _sync_live_ownership(state, credentials_path, cli_path, fresh_observation)
                        if ((fresh_ownership and fresh_ownership.get("status") != "closed")
                                or any(row.get("symbol") != "USDCUSD"
                                       for row in fresh_observation["positions"])):
                            raise ValueError("entry_position_changed_before_submit")
                        try:
                            selected = _read_selection(state)
                            card, release = load_selected_card(state)
                            frozen, frozen_release = validate_policy_card(decision.get("policy_card"),
                                decision.get("release_sha"), strategy_id=decision.get("strategy_id"))
                            if (not isinstance(selected, dict) or selected.get("selection") != "selected"
                                    or not isinstance(selected.get("report_id"), str) or not selected["report_id"].strip()
                                    or selected.get("strategy_id") != card.strategy_id
                                    or decision.get("action") != "ENTER"
                                    or card.strategy_id != frozen.strategy_id or release != frozen_release):
                                raise ValueError("entry_policy_changed_before_submit")
                        except (ValueError, OSError, KeyError, TypeError) as error:
                            raise ValueError("entry_policy_changed_before_submit") from error
                    if mode == "live" and not btc_positions and not evaluate_entry(
                            fresh.get("risk"), order.get("notional_usd"))["approved"]:
                        raise ValueError("investment_effect_fence_rejected")
                    if mode in {"paper", "live"} and not btc_positions:
                        refreshed = allocation_gate(fresh, build_candidates(fresh), decision)
                        if not refreshed["approved"]:
                            raise ValueError("investment_effect_fence_rejected")
                        decision = {**decision, **refreshed}
                    if paper_etf_exit:
                        position = fresh["position"]
                        qty = Decimal(order["qty"])
                        if (order.get("side") != "sell"
                                or order.get("symbol") != position["symbol"]
                                or qty != Decimal(position["qty"])):
                            raise ValueError("investment_effect_fence_rejected")
                        broker_readback = observe(
                            credentials_path=credentials_path, cli_path=cli_path,
                        )
                        positions = broker_readback.get("positions")
                        if (not isinstance(positions, list)
                                or any(not isinstance(row, dict) for row in positions)
                                or sum(row.get("symbol") != "USDCUSD" for row in positions) != 1):
                            raise ValueError("investment_effect_fence_rejected")
                        validate_etf_position_readback(
                            broker_readback, symbol=order["symbol"], expected_qty=qty,
                        )
                    sealed = seal(state / "receipts.jsonl", decision, order)
                    if not mark_started(state / "receipts.jsonl", sealed):
                        raise ValueError("investment_effect_already_started")
                    if order.get("asset_class") == "crypto":
                        marker = (_closing_marker(ownership, sealed) if btc_positions else {
                            "entry_client_order_id": sealed["client_order_id"],
                            "entry_effect_id": sealed["effect_id"], "entry_filled_qty": "0",
                            "status": "entry_pending", "symbol": "BTCUSD",
                            "entry_timestamp": allocator_snapshot["clock"]["timestamp"]})
                        _atomic_json(state / "live-owned-position.json", marker)
                    _mark_external_effect_attempted()
                    effect_attempted = True
                    submit_kwargs = {
                        "credentials_path": credentials_path,
                        "cli_path": cli_path,
                        "client_order_id": sealed["client_order_id"],
                        "order": order,
                        "mode": mode,
                    }
                    if is_etf_order:
                        submit_kwargs.update({
                            "owner_id": decision.get("owner_id"),
                            "strategy_id": decision.get("strategy_id"),
                        })
                    acknowledgement = submit_order(**submit_kwargs)
                stage = "allocation_reconcile"
                reconciliation = reconcile_started(
                    state / "receipts.jsonl",
                    lambda value: find_order_by_client_id(
                        credentials_path=credentials_path, cli_path=cli_path, client_order_id=value),
                    on_reconciled=on_reconciled,
                )
                if "value" in reconciled_observation:
                    observation = reconciled_observation["value"]
                effect = sealed["effect_id"]
        else:
            if decision["approved"]:
                decision.update({"approved": False, "gate": f"{mode}_read_only"})
            record_no_trade(state / "receipts.jsonl", decision)
        review = _review_status(state, mode, deployment)
        decision["application_status"] = review.get("application_status", "unknown")
        stage = "state_write"
        _atomic_json(state / "allocation-latest.json", decision)
        _atomic_json(state / "risk-latest.json", allocator_snapshot["risk"])
        _atomic_json(state / "observation-latest.json", observation)
        _atomic_json(state / "campaign.json", campaign)
        if mode == "paper":
            # This is a reporting-only read of the append-only effect ledger.
            # Missing fees/slippage/model/system costs remain partial and never become
            # a numeric zero or a promotion signal.
            write_paper_performance(
                state, observation, allocator_snapshot["risk"],
                broker_cost_reader=lambda **kwargs: read_paper_etf_cost_evidence(
                    credentials_path=credentials_path, cli_path=cli_path, **kwargs,
                ),
            )
        if mode in {"paper", "live"} and investment_owner_id() == f"alpaca-investment-{mode}":
            write_crypto_performance(state, observation, mode=mode, owner_id=investment_owner_id(),
                activity_reader=lambda **kwargs: read_crypto_activity_evidence(
                    credentials_path=credentials_path, cli_path=cli_path, **kwargs),
                activity_page_reader=lambda **kwargs: read_crypto_activity_page_chunk(
                    credentials_path=credentials_path, cli_path=cli_path, **kwargs))
        stage = "telegram_deliver"
        telegram = deliver(state, observation, campaign, decision, effect,
                           event_key=cloud_event_key if deployment == "cloud" else None)
        _mark_no_broker_order_submitted(mode, effect_attempted, effect)
        summary = {
            "account": observation["account"],
            "activities_count": observation["activities_count"],
            "candidate_count": len(candidates),
            "decision": decision["candidate_ref"],
            "deployment": deployment,
            "effect": effect,
            "exit_status": campaign["exit_status"],
            "loop_id": "alpaca-investment",
            "orders_count": observation["open_and_closed_orders_count"],
            "mode": mode,
            "paper": mode == "paper",
            "positions_count": len(observation["positions"]),
            "unrealized_pnl_usd": campaign["unrealized_pnl_usd"],
            "reconciliation": reconciliation,
            "status": "allocated",
            "telegram_message_id": telegram["message_id"],
        }
        if inventory_capture is not None:
            summary["cost_inventory_capture"] = inventory_capture
        print(json.dumps(summary, separators=(",", ":")))
        return 0
    except Exception as error:
        # Read/agent/report failures before an effect are transient-safe to retry. Once submit_order
        # was called, never retry: an unknown broker acknowledgement must reconcile on the next wake.
        if _retry_allowed(stage, effect_attempted, attempt):
            return main(attempt=attempt + 1, wake_id=wake_id)
        telegram = {"status": "delivery_uncertain"}
        if stage != "telegram_deliver":
            try:
                telegram = deliver_failure(
                    state,
                    stage=stage,
                    effect_uncertain=effect_attempted or stage == "reconcile_started",
                    wake_id=wake_id,
                    event_key=cloud_event_key,
                    observation=observation,
                    campaign=campaign,
                    mode=mode if mode in {"paper", "shadow", "live"} else "unknown",
                )
            except Exception:
                pass
        print(json.dumps({
            **({"cost_inventory_capture": inventory_capture} if inventory_capture is not None else {}),
            "blocker": "alpaca_pass_failed",
            "effect": _terminal_effect(effect_attempted),
            "error_code": _error_code(error),
            "loop_id": "alpaca-investment",
            "mode": mode if mode in {"paper", "shadow", "live"} else "unknown",
            "stage": stage,
            "status": "blocked",
            "telegram_status": telegram["status"],
        }, separators=(",", ":")))
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
