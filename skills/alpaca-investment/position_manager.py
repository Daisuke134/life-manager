"""Declared-card HOLD/EXIT judgment with a deterministic live close boundary."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from strategy_policy import ACTION_EXIT, ACTION_HOLD, evaluate, validate_policy_card
from effect_store import owned_entry_decision
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
                                           "entry_provider_order_id", "owner_id", "mode")}}


def exit_order(decision: dict[str, Any]) -> dict[str, Any]:
    return {"asset_class": "crypto", "qty": decision["qty"], "side": "sell",
            "symbol": "BTC/USDC", "time_in_force": "gtc", "type": "market"}
