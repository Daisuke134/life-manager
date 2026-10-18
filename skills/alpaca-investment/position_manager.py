"""Declared-card HOLD/EXIT judgment with a deterministic live close boundary."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from strategy_policy import ACTION_EXIT, ACTION_HOLD, evaluate, validate_policy_card
from effect_store import ReconciliationPending, _digest, _rows, owned_entry_decision
from etf_ownership import investment_owner_id
from risk_policy import parse_instant


def load_owned_policy(state: Path, ownership: dict[str, Any], *, mode: str) -> dict[str, Any]:
    proof = owned_entry_decision(state / "receipts.jsonl", ownership,
                                 owner_id=investment_owner_id(), mode=mode)
    decision, broker = proof["decision"], proof["broker"]
    card, release_sha = validate_policy_card(decision["policy_card"], decision.get("release_sha"),
                                             strategy_id=decision.get("strategy_id"))
    if tuple(card.instruments) != ("BTC/USDC",):
        raise ValueError("owned_entry_policy_scope_invalid")
    try:
        filled_at = broker["filled_at"]
        if not (parse_instant(decision["observed_at"]) <= parse_instant(broker["submitted_at"])
                <= parse_instant(filled_at)):
            raise ValueError
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("owned_entry_fill_time_invalid") from error
    return {"card": card, "release_sha": release_sha, "entry_price": broker["filled_avg_price"],
            "entry_timestamp": filled_at, "owned_qty": proof["owned_qty"],
            "entry_effect_id": ownership["entry_effect_id"], "entry_client_order_id": broker["client_order_id"],
            "entry_provider_order_id": broker["id"], "owner_id": decision["owner_id"], "mode": mode}



def close_fill_proof(state: Path, ownership: dict[str, Any], broker: dict[str, Any],
                     observation: dict[str, Any], *, mode: str) -> dict[str, Any]:
    """Prove a sealed owned BTC close in native quote, without inventing costs."""
    parent = load_owned_policy(state, ownership, mode=mode)
    try:
        if observation.get("mode") != mode or observation.get("paper") is not (mode == "paper"):
            raise ValueError
        effect = ownership["close_effect_id"]
        client = ownership["close_client_order_id"]
        if (ownership.get("status") != "closing" or not isinstance(effect, str)
                or len(effect) != 64 or any(c not in "0123456789abcdef" for c in effect)
                or client != "lm-ai-" + effect[:24]):
            raise ValueError
        rows = _rows(state / "receipts.jsonl")
        intents = [r for r in rows if r.get("receipt_type") == "effect_intent"
                   and r.get("status") == "planned" and r.get("effect_id") == effect]
        if len(intents) != 1:
            raise ValueError
        intent = intents[0]
        decisions = [r for r in rows if r.get("receipt_type") == "decision"
                     and r.get("decision_id") == intent.get("decision_id")]
        if len(decisions) != 1:
            raise ValueError
        decision, order = decisions[0]["decision"], intent["order"]
        if (intent.get("client_order_id") != client or intent.get("mode") != mode
                or intent.get("paper") is not (mode == "paper")
                or intent.get("owner_id") != parent["owner_id"]
                or intent.get("strategy_id") != parent["card"].strategy_id
                or decisions[0].get("mode") != mode or decisions[0].get("paper") is not (mode == "paper")
                or decision.get("action") != "EXIT" or decision.get("mode") != mode
                or decision.get("owner_id") != parent["owner_id"]
                or decision.get("strategy_id") != parent["card"].strategy_id
                or decision.get("release_sha") != parent["release_sha"]
                or any(decision.get(key) != parent[key] for key in (
                    "entry_effect_id", "entry_client_order_id", "entry_provider_order_id"))
                or Decimal(str(decision.get("entry_price"))) != Decimal(parent["entry_price"])
                or parse_instant(decision.get("entry_timestamp")) != parse_instant(parent["entry_timestamp"])
                or intent.get("decision_id") != _digest({"mode": mode, "decision": decision})
                or effect != _digest({"decision_id": intent["decision_id"], "order": order})
                or set(order) != {"asset_class", "symbol", "side", "type", "time_in_force", "qty"}
                or order.get("asset_class") != "crypto" or order.get("symbol") != "BTC/USDC"
                or order.get("side") != "sell" or order.get("type") != "market"
                or order.get("time_in_force") != "gtc"):
            raise ValueError
        if (not isinstance(broker.get("id"), str) or not broker["id"].strip()
                or broker.get("client_order_id") != client or broker.get("status") != "filled"
                or broker.get("symbol") not in {"BTCUSDC", "BTC/USDC"}
                or broker.get("side") != "sell" or broker.get("type") != "market"
                or broker.get("time_in_force") != "gtc"):
            raise ValueError
        qty = Decimal(str(broker.get("filled_qty")))
        price = Decimal(str(broker.get("filled_avg_price")))
        if (not qty.is_finite() or qty <= 0 or not price.is_finite() or price <= 0
                or qty != Decimal(str(order["qty"])) or qty != Decimal(str(decision.get("position_qty")))
                or qty != Decimal(parent["owned_qty"])):
            raise ValueError
        submitted, filled, observed = (parse_instant(value) for value in (
            broker.get("submitted_at"), broker.get("filled_at"), observation["clock"]["observed_at"]))
        if not (parse_instant(parent["entry_timestamp"]) <= parse_instant(decision.get("observed_at"))
                <= submitted <= filled <= observed):
            raise ValueError
        for key in ("cash", "equity"):
            if not Decimal(str(observation["account"][key])).is_finite():
                raise ValueError
        positions = observation["positions"]
        if not isinstance(positions, list):
            raise ValueError
        for position in positions:
            if (not isinstance(position, dict) or not isinstance(position.get("symbol"), str)
                    or not position["symbol"].strip()
                    or not Decimal(str(position.get("qty"))).is_finite()):
                raise ValueError
            if position["symbol"] in {"BTCUSD", "BTCUSDC", "BTC/USDC", "BTC/USD", "BTC"}:
                raise ReconciliationPending("owned_close_account_pending")
        for row in rows:
            if row.get("receipt_type") != "outcome" or row.get("effect_id") != effect:
                continue
            previous = row.get("broker")
            if (row.get("mode") != mode or row.get("paper") is not (mode == "paper")
                    or row.get("client_order_id") != client or row.get("outcome") != "broker_reconciled"
                    or row.get("broker_receipt_id") != broker["id"] or not isinstance(previous, dict)):
                raise ValueError
            for key in ("id", "client_order_id", "status", "side", "type", "time_in_force",
                        "symbol", "filled_qty", "filled_avg_price", "submitted_at", "filled_at"):
                old, current = previous.get(key), broker.get(key)
                if old is None or old == "":
                    continue
                if key in {"filled_qty", "filled_avg_price"}:
                    if Decimal(str(old)) != Decimal(str(current)):
                        raise ValueError
                elif key in {"submitted_at", "filled_at"}:
                    if parse_instant(old) != parse_instant(current):
                        raise ValueError
                elif key == "symbol":
                    if old.replace("/", "") != current.replace("/", ""):
                        raise ValueError
                elif old != current:
                    raise ValueError
    except ReconciliationPending:
        raise
    except (ValueError, KeyError, TypeError, AttributeError, InvalidOperation) as error:
        raise ValueError("owned_close_proof_invalid") from error
    return {"account_readback": observation, "receipt": {
        "schema_version": 1, "kind": "owned_crypto_close", "owner_id": parent["owner_id"], "mode": mode,
        "strategy_id": parent["card"].strategy_id, "release_sha": parent["release_sha"],
        **{key: parent[key] for key in ("entry_effect_id", "entry_client_order_id", "entry_provider_order_id")},
        "close_effect_id": effect, "close_client_order_id": client, "close_provider_order_id": broker["id"],
        "entry_price": parent["entry_price"], "entry_timestamp": parent["entry_timestamp"],
        "exit_filled_qty": format(qty.normalize(), "f"), "exit_price": format(price.normalize(), "f"),
        "exit_timestamp": filled.isoformat(), "quote_currency": "USDC", "net_realized_pnl_usd": None}}


def choose(snapshot: dict[str, Any], observation: dict[str, Any], state: Path,
           runner: Path, workdir: Path) -> dict[str, Any]:
    del runner, workdir
    positions = [row for row in observation.get("positions", [])
                 if row.get("symbol") != "USDCUSD"]
    try:
        ownership = json.loads((state / "live-owned-position.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise ValueError("live_position_not_owned") from error
    if (ownership.get("status") != "open" or ownership.get("symbol") != "BTCUSD"
            or not isinstance(ownership.get("entry_client_order_id"), str)
            or not ownership["entry_client_order_id"].startswith("lm-ai-")):
        raise ValueError("live_position_not_owned")
    if len(positions) != 1 or positions[0].get("symbol") != "BTCUSD" \
            or snapshot.get("open_orders") != 0 or snapshot.get("unresolved_intents") != 0:
        raise ValueError("live_position_gate_rejected")
    try:
        qty = Decimal(str(positions[0]["qty"]))
        allocated = Decimal(str(snapshot["risk"]["allocated_capital_usd"]))
        if (not qty.is_finite() or qty <= 0 or qty.as_tuple().exponent < -9
                or not allocated.is_finite() or allocated <= 0 or allocated > Decimal("100")):
            raise ValueError
    except (InvalidOperation, KeyError, TypeError, ValueError) as error:
        raise ValueError("live_position_gate_rejected") from error
    try:
        policy = load_owned_policy(state, ownership, mode=snapshot.get("mode"))
        card, release_sha = policy["card"], policy["release_sha"]
        if qty != Decimal(policy["owned_qty"]):
            raise ValueError("owned_position_quantity_mismatch")
        if parse_instant(policy["entry_timestamp"]) > parse_instant(snapshot["clock"]["timestamp"]):
            raise ValueError("owned_entry_fill_time_invalid")
    except ValueError as error:
        return {"action": ACTION_HOLD, "policy_action": "NO_TRADE", "strategy_id": None,
                "signal_inputs": {}, "reason": str(error), "expected_cost_usd": None,
                "release_sha": None, "qty": str(qty)}
    policy_snapshot = dict(snapshot)
    policy_snapshot["positions"] = 1
    policy_position = dict(positions[0])
    policy_position["entry_price"] = policy["entry_price"]
    policy_position["entry_timestamp"] = policy["entry_timestamp"]
    policy_snapshot["position"] = policy_position
    decision = evaluate(policy_snapshot, card)
    action = ACTION_EXIT if decision["action"] == ACTION_EXIT else ACTION_HOLD
    return {**decision, "action": action, "policy_action": decision["action"],
            "release_sha": release_sha, "qty": str(qty),
            **{key: policy[key] for key in ("entry_effect_id", "entry_client_order_id",
                                           "entry_provider_order_id", "entry_price", "entry_timestamp", "owner_id", "mode")}}


def exit_order(decision: dict[str, Any]) -> dict[str, Any]:
    return {"asset_class": "crypto", "qty": decision["qty"], "side": "sell",
            "symbol": "BTC/USDC", "time_in_force": "gtc", "type": "market"}
