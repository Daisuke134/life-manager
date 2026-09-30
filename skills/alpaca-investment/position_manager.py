"""Declared-card HOLD/EXIT judgment with a deterministic live close boundary."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from strategy_policy import ACTION_EXIT, ACTION_HOLD, evaluate, load_selected_card


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
        card, release_sha = load_selected_card(state)
    except ValueError as error:
        return {"action": ACTION_HOLD, "policy_action": "NO_TRADE", "strategy_id": None,
                "signal_inputs": {}, "reason": str(error), "expected_cost_usd": None,
                "release_sha": None, "qty": str(qty)}
    policy_snapshot = dict(snapshot)
    policy_snapshot["positions"] = 1
    policy_position = dict(positions[0])
    if "entry_price" not in policy_position and "avg_entry_price" in policy_position:
        policy_position["entry_price"] = policy_position["avg_entry_price"]
    if "entry_timestamp" not in policy_position and ownership.get("entry_timestamp"):
        policy_position["entry_timestamp"] = ownership["entry_timestamp"]
    policy_snapshot["position"] = policy_position
    decision = evaluate(policy_snapshot, card)
    action = ACTION_EXIT if decision["action"] == ACTION_EXIT else ACTION_HOLD
    return {**decision, "action": action, "policy_action": decision["action"],
            "release_sha": release_sha, "qty": str(qty)}


def exit_order(decision: dict[str, Any]) -> dict[str, Any]:
    return {"asset_class": "crypto", "qty": decision["qty"], "side": "sell",
            "symbol": "BTC/USDC", "time_in_force": "gtc", "type": "market"}
