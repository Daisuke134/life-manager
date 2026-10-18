"""Single pure contract for sealed BTC ownership and recorded close evidence.

No provider, environment, marker-file or ledger writes occur in these readers.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any

from risk_policy import parse_instant
from strategy_policy import validate_policy_card


class ReconciliationPending(ValueError):
    """An official order exists but its strategy account readback is not settled."""



def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()



def owned_entry_decision_from_rows(rows: list[dict[str, Any]], ownership: dict[str, Any], *, owner_id: str, mode: str) -> dict[str, Any]:
    """Read the sealed policy and official filled buy for one owned entry."""
    if (not isinstance(mode, str) or mode not in {"paper", "live"}
            or owner_id != f"alpaca-investment-{mode}" or not isinstance(ownership, dict)):
        raise ValueError("owned_entry_identity_invalid")
    effect_id, client = ownership.get("entry_effect_id"), ownership.get("entry_client_order_id")
    if (not isinstance(effect_id, str) or re.fullmatch(r"[0-9a-f]{64}", effect_id) is None
            or client != f"lm-ai-{effect_id[:24]}"):
        raise ValueError("owned_entry_identity_invalid")
    intents = [row for row in rows if row.get("receipt_type") == "effect_intent"
               and row.get("status") == "planned" and row.get("effect_id") == effect_id]
    if len(intents) != 1:
        raise ValueError("owned_entry_intent_missing" if not intents else "owned_entry_intent_conflict")
    intent = intents[0]
    if (intent.get("client_order_id") != client or intent.get("mode") != mode
            or intent.get("paper") is not (mode == "paper") or intent.get("owner_id") != owner_id):
        raise ValueError("owned_entry_identity_invalid")
    decisions = [row for row in rows if row.get("receipt_type") == "decision"
                 and row.get("decision_id") == intent.get("decision_id")]
    if len(decisions) != 1 or not isinstance(decisions[0].get("decision"), dict):
        raise ValueError("owned_entry_policy_missing")
    decision, order = decisions[0]["decision"], intent.get("order")
    if (decisions[0].get("mode") != mode or decisions[0].get("paper") is not (mode == "paper")
            or decision.get("mode") != mode or decision.get("owner_id") != owner_id
            or decision.get("action") != "ENTER" or not isinstance(decision.get("strategy_id"), str)
            or not decision["strategy_id"]
            or decision.get("strategy_id") != intent.get("strategy_id")
            or not isinstance(decision.get("policy_card"), dict) or not isinstance(order, dict)
            or order.get("asset_class") != "crypto" or order.get("symbol") != "BTC/USDC"
            or order.get("side") != "buy" or order.get("type") != "market"
            or order.get("time_in_force") != "gtc"):
        raise ValueError("owned_entry_policy_missing")
    if (intent.get("decision_id") != _digest({"mode": mode, "decision": decision})
            or effect_id != _digest({"decision_id": intent["decision_id"], "order": order})):
        raise ValueError("owned_entry_digest_mismatch")
    outcomes = [row for row in rows if row.get("receipt_type") == "outcome"
                and row.get("effect_id") == effect_id]
    if not outcomes:
        raise ValueError("owned_entry_fill_missing")
    # Enrichment may append another view of the same immutable fill. Known
    # values must agree; a later contradictory row is not an authority override.
    identity_fields = ("mode", "paper", "client_order_id", "outcome", "broker_receipt_id")
    if any(tuple(row.get(key) for key in identity_fields) !=
           tuple(outcomes[0].get(key) for key in identity_fields) for row in outcomes):
        raise ValueError("owned_entry_fill_conflict")
    for key in ("id", "client_order_id", "symbol", "side", "status", "type", "time_in_force",
                "filled_qty", "filled_avg_price", "submitted_at", "filled_at"):
        known = []
        for row in outcomes:
            value = row.get("broker", {}).get(key) if isinstance(row.get("broker"), dict) else None
            if value is None or value == "":
                continue
            try:
                if key in {"filled_qty", "filled_avg_price"}:
                    value = Decimal(str(value))
                    if not value.is_finite() or value <= 0:
                        raise ValueError
                elif key in {"submitted_at", "filled_at"}:
                    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if value.tzinfo is None:
                        raise ValueError
                elif key == "symbol" and isinstance(value, str):
                    value = value.replace("/", "")
            except (InvalidOperation, TypeError, ValueError, AttributeError) as error:
                raise ValueError("owned_entry_fill_invalid") from error
            known.append(value)
        if known and any(value != known[0] for value in known):
            raise ValueError("owned_entry_fill_conflict")
    outcome = outcomes[-1]
    broker = outcome.get("broker")
    if (outcome.get("outcome") != "broker_reconciled" or outcome.get("mode") != mode
            or outcome.get("paper") is not (mode == "paper")
            or outcome.get("client_order_id") != client or not isinstance(broker, dict)
            or broker.get("status") != "filled" or broker.get("side") != "buy"
            or broker.get("symbol") not in {"BTC/USDC", "BTCUSDC"}
            or broker.get("client_order_id") != client or broker.get("type") != order["type"]
            or broker.get("time_in_force") != order["time_in_force"]
            or not isinstance(broker.get("id"), str)
            or not broker["id"] or outcome.get("broker_receipt_id") != broker["id"]):
        raise ValueError("owned_entry_fill_invalid")
    try:
        filled, marker_filled, owned, price = [Decimal(str(value)) for value in (
            broker.get("filled_qty"), ownership.get("entry_filled_qty"),
            ownership.get("owned_qty"), broker.get("filled_avg_price"))]
        if (any(not number.is_finite() or number <= 0 for number in (filled, marker_filled, owned, price))
                or filled != marker_filled or owned > filled):
            raise ValueError
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError("owned_entry_fill_invalid") from error
    return {"decision": decision, "broker": broker, "owned_qty": str(owned)}



def _owned_policy(proof: dict[str, Any], ownership: dict[str, Any], *, mode: str) -> dict[str, Any]:
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




def close_fill_proof_from_rows(rows: list[dict[str, Any]], ownership: dict[str, Any], broker: dict[str, Any],
                              observation: dict[str, Any], *, mode: str, owner_id: str) -> dict[str, Any]:
    parent = _owned_policy(owned_entry_decision_from_rows(rows, ownership, owner_id=owner_id, mode=mode),
                           ownership, mode=mode)
    try:
        if observation.get("mode") != mode or observation.get("paper") is not (mode == "paper"):
            raise ValueError
        effect = ownership["close_effect_id"]
        client = ownership["close_client_order_id"]
        if (ownership.get("status") != "closing" or not isinstance(effect, str)
                or len(effect) != 64 or any(c not in "0123456789abcdef" for c in effect)
                or client != "lm-ai-" + effect[:24]):
            raise ValueError
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




def recorded_close_proof_from_rows(rows: list[dict[str, Any]], ownership: dict[str, Any],
                                  broker: dict[str, Any], observation: dict[str, Any], *,
                                  mode: str, owner_id: str) -> dict[str, Any]:
    proof = close_fill_proof_from_rows(rows, ownership, broker, observation, mode=mode, owner_id=owner_id)
    matched = False
    for row in rows:
        if row.get("receipt_type") != "outcome" or row.get("effect_id") != ownership.get("close_effect_id"):
            continue
        recorded = row.get("strategy_receipt")
        if recorded is None:
            continue
        if not isinstance(recorded, dict) or recorded.get("receipt") != proof["receipt"]:
            raise ValueError("owned_close_receipt_conflict")
        expected = close_fill_proof_from_rows(rows, ownership, row.get("broker"),
            recorded.get("account_readback"), mode=mode, owner_id=owner_id)
        if recorded != expected:
            raise ValueError("owned_close_receipt_conflict")
        matched = True
    if not matched:
        raise ValueError("owned_close_receipt_missing")
    return proof

