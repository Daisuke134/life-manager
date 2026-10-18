"""Append-only paper effect receipts and reconciliation fence."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable


MODES = frozenset({"paper", "shadow", "live"})
BROKER_TERMINAL_FAILURE_STATUSES = frozenset({
    "canceled", "done_for_day", "expired", "rejected", "stopped", "suspended",
})
UNRESOLVED_INTENT_STATUSES = frozenset({
    "started", "reconciliation_blocked", "reconciliation_pending", "applied",
})


class ReconciliationPending(ValueError):
    """An official order exists but its strategy account readback is not settled."""


def _mode(value: Any) -> str:
    if value not in MODES:
        raise ValueError("investment_mode_invalid")
    return value


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _rows(path: Path) -> list[dict[str, Any]]:
    try:
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except FileNotFoundError:
        return []
    if not all(isinstance(value, dict) for value in values):
        raise ValueError("receipt_ledger_invalid")
    return values


def _append_once(path: Path, row: dict[str, Any] | Callable[[list[dict[str, Any]]], dict[str, Any]],
                 identity: tuple[str, ...]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        with os.fdopen(os.dup(descriptor), "r", encoding="utf-8") as handle:
            existing = [json.loads(line) for line in handle if line.strip()]
        if callable(row):
            row = row(existing)
        if any(all(item.get(key) == row.get(key) for key in identity) for item in existing):
            return False
        payload = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
        os.write(descriptor, payload)
        os.fsync(descriptor)
        return True
    finally:
        os.close(descriptor)


def seal(ledger: Path, decision: dict[str, Any], order: dict[str, Any]) -> dict[str, str]:
    mode = _mode(decision.get("mode"))
    paper = mode == "paper"
    decision_id = _digest({"mode": mode, "decision": decision})
    effect_id = _digest({"decision_id": decision_id, "order": order})
    client_order_id = f"lm-ai-{effect_id[:24]}"
    now = datetime.now(timezone.utc).isoformat()
    _append_once(ledger, {
        "decision": decision, "decision_id": decision_id, "mode": mode, "paper": paper,
        "receipt_type": "decision", "recorded_at": now, "schema_version": 1,
    }, ("receipt_type", "decision_id"))
    _append_once(ledger, {
        "client_order_id": client_order_id, "decision_id": decision_id,
        "effect_id": effect_id, "order": order, "mode": mode, "paper": paper,
        "owner_id": decision.get("owner_id"),
        "strategy_id": decision.get("strategy_id"),
        "decision_session": decision.get("decision_session"),
        "source_receipt_ids": decision.get("source_receipt_ids", []),
        "receipt_type": "effect_intent", "recorded_at": now,
        "schema_version": 1, "status": "planned",
    }, ("receipt_type", "effect_id", "status"))
    return {"client_order_id": client_order_id, "decision_id": decision_id,
            "effect_id": effect_id, "mode": mode}


def owned_entry_decision(ledger: Path, ownership: dict[str, Any], *, owner_id: str, mode: str) -> dict[str, Any]:
    """Read the sealed policy and official filled buy for one owned entry."""
    if (not isinstance(mode, str) or mode not in {"paper", "live"}
            or owner_id != f"alpaca-investment-{mode}" or not isinstance(ownership, dict)):
        raise ValueError("owned_entry_identity_invalid")
    effect_id, client = ownership.get("entry_effect_id"), ownership.get("entry_client_order_id")
    if (not isinstance(effect_id, str) or re.fullmatch(r"[0-9a-f]{64}", effect_id) is None
            or client != f"lm-ai-{effect_id[:24]}" or ledger.is_symlink()):
        raise ValueError("owned_entry_identity_invalid")
    try:
        rows = _rows(ledger)
    except OSError as error:
        raise ValueError("owned_entry_ledger_unavailable") from error
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


def record_no_trade(ledger: Path, decision: dict[str, Any]) -> str:
    mode = _mode(decision.get("mode"))
    decision_id = _digest({"mode": mode, "decision": decision})
    _append_once(ledger, {
        "decision": decision, "decision_id": decision_id, "outcome": "no_trade",
        "mode": mode, "paper": mode == "paper", "receipt_type": "decision",
        "recorded_at": datetime.now(timezone.utc).isoformat(), "schema_version": 1,
    }, ("receipt_type", "decision_id"))
    return decision_id


def mark_started(ledger: Path, sealed: dict[str, str]) -> bool:
    mode = _mode(sealed.get("mode"))
    if any(row.get("receipt_type") == "outcome" and row.get("effect_id") == sealed["effect_id"]
           for row in _rows(ledger)):
        raise ValueError("effect_already_completed")
    planned = next(
        (
            row for row in reversed(_rows(ledger))
            if row.get("receipt_type") == "effect_intent"
            and row.get("effect_id") == sealed["effect_id"]
            and row.get("status") == "planned"
        ),
        {},
    )
    preserved = {
        key: planned[key]
        for key in (
            "order", "owner_id", "strategy_id", "decision_session",
            "source_receipt_ids",
        )
        if key in planned
    }
    return _append_once(ledger, {
        **preserved, **sealed, "mode": mode, "paper": mode == "paper",
        "receipt_type": "effect_intent",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1, "status": "started",
    }, ("receipt_type", "effect_id", "status"))



def _crypto_close_pending(intent: dict[str, Any], outcome: dict[str, Any] | None) -> bool:
    """A filled managed sell remains fenced until its scoped account receipt exists."""
    order = intent.get("order", {})
    if (not isinstance(order, dict) or order.get("asset_class") != "crypto" or order.get("side") != "sell"
            or not isinstance(outcome, dict) or outcome.get("outcome") != "broker_reconciled"):
        return False
    try:
        wrapper = outcome["strategy_receipt"]
        proof, account = wrapper["receipt"], wrapper["account_readback"]
        mode, owner, broker = intent["mode"], intent["owner_id"], outcome["broker"]
        if (mode not in {"paper", "live"} or owner != f"alpaca-investment-{mode}"
                or proof.get("schema_version") != 1 or proof.get("kind") != "owned_crypto_close"
                or proof.get("mode") != mode or proof.get("owner_id") != owner
                or proof.get("strategy_id") != intent.get("strategy_id")
                or not isinstance(proof.get("strategy_id"), str) or not proof["strategy_id"]
                or proof.get("close_effect_id") != intent.get("effect_id")
                or proof.get("close_client_order_id") != intent.get("client_order_id")
                or proof.get("close_provider_order_id") != broker.get("id")
                or not isinstance(broker.get("id"), str) or not broker["id"]
                or proof.get("quote_currency") != "USDC"
                or account.get("mode") != mode or account.get("paper") is not (mode == "paper")
                or not isinstance(proof.get("entry_provider_order_id"), str) or not proof["entry_provider_order_id"]
                or not re.fullmatch(r"[0-9a-f]{64}", proof["entry_effect_id"])
                or proof.get("entry_client_order_id") != "lm-ai-" + proof["entry_effect_id"][:24]
                or not re.fullmatch(r"[0-9a-f]{40,64}", proof["release_sha"])):
            return True
        qty, price, entry_price = (Decimal(str(proof[key])) for key in ("exit_filled_qty", "exit_price", "entry_price"))
        if (any(not q.is_finite() or q <= 0 for q in (qty, price, entry_price))
                or qty != Decimal(str(order["qty"])) or qty != Decimal(str(broker["filled_qty"]))
                or price != Decimal(str(broker["filled_avg_price"]))):
            return True
        times = [datetime.fromisoformat(value.replace("Z", "+00:00")) for value in (
            proof["entry_timestamp"], proof["exit_timestamp"], account["clock"]["observed_at"], broker["filled_at"])]
        if (any(value.tzinfo is None for value in times) or not times[0] <= times[1] <= times[2]
                or times[1] != times[3]):
            return True
        if any(not Decimal(str(account["account"][key])).is_finite() for key in ("cash", "equity")):
            return True
        if not isinstance(account["positions"], list):
            return True
        for position in account["positions"]:
            if (not isinstance(position, dict) or not isinstance(position.get("symbol"), str)
                    or not position["symbol"].strip()
                    or position["symbol"] in {"BTCUSD", "BTCUSDC", "BTC/USDC", "BTC/USD", "BTC"}
                    or not Decimal(str(position.get("qty"))).is_finite()):
                return True
    except (KeyError, ValueError, TypeError, AttributeError, InvalidOperation):
        return True
    return False


def _unresolved(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_outcome: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("receipt_type") == "outcome" and isinstance(row.get("effect_id"), str):
            latest_outcome[row["effect_id"]] = row
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("receipt_type") == "effect_intent" and isinstance(row.get("effect_id"), str):
            latest[row["effect_id"]] = {**latest.get(row["effect_id"], {}), **row}
    return [row for effect_id, row in latest.items()
            if row.get("status") in UNRESOLVED_INTENT_STATUSES
            and (not _outcome_closed(latest_outcome.get(effect_id))
                 or _crypto_close_pending(row, latest_outcome.get(effect_id))
                 or (row.get("strategy_readback_pending") is True
                     and not isinstance((latest_outcome.get(effect_id) or {}).get("strategy_receipt"), dict))) ]


def _completed_without_strategy_receipt(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find filled broker outcomes whose strategy-specific readback was never recorded."""
    intents: dict[str, list[dict[str, Any]]] = {}
    latest_outcome: dict[str, dict[str, Any]] = {}
    for row in rows:
        effect_id = row.get("effect_id")
        if not isinstance(effect_id, str):
            continue
        if row.get("receipt_type") == "effect_intent":
            intents.setdefault(effect_id, []).append(row)
        elif row.get("receipt_type") == "outcome":
            latest_outcome[effect_id] = row
    candidates: list[dict[str, Any]] = []
    for effect_id, outcome in latest_outcome.items():
        broker = outcome.get("broker")
        intent = next((row for row in reversed(intents.get(effect_id, []))
                       if isinstance(row.get("order"), dict)
                       and isinstance(row.get("owner_id"), str)
                       and isinstance(row.get("strategy_id"), str)
                       and ((row["order"].get("asset_class") == "crypto" and row["order"].get("side") == "sell")
                            or (isinstance(row.get("decision_session"), str)
                                and isinstance(row.get("source_receipt_ids"), list)))), None)
        if (outcome.get("outcome") != "broker_reconciled"
                or not isinstance(broker, dict)
                or broker.get("status") != "filled"
                or not isinstance(intent, dict)
                or not isinstance(intent.get("client_order_id"), str)
                or (outcome.get("client_order_id") is not None
                    and outcome.get("client_order_id") != intent["client_order_id"])
                or (intent["order"].get("asset_class") == "crypto"
                    and outcome.get("client_order_id") != intent["client_order_id"])
                or isinstance(outcome.get("strategy_receipt"), dict)):
            continue
        candidates.append(intent)
    return candidates


def _filled_qty_positive(order: dict[str, Any]) -> bool:
    value = order.get("filled_qty")
    if value is None or value == "":
        return False
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return True
    return quantity.is_finite() and quantity > 0


def _outcome_closed(outcome: dict[str, Any] | None) -> bool:
    if not isinstance(outcome, dict):
        return False
    kind = outcome.get("outcome")
    if kind == "broker_terminal_failure":
        broker = outcome.get("broker")
        return isinstance(broker, dict) and (
            broker.get("status") in BROKER_TERMINAL_FAILURE_STATUSES
            and not _filled_qty_positive(broker)
        )
    if kind == "broker_reconciled":
        broker = outcome.get("broker")
        if not isinstance(broker, dict):
            return False
        status = broker.get("status")
        return status == "filled" or (
            status in BROKER_TERMINAL_FAILURE_STATUSES and not _filled_qty_positive(broker)
        )
    return kind in {
        "live_canary_verified", "live_canary_terminal_failure",
        "live_close_verified", "live_close_terminal_failure",
    }


def _pending_status(ledger: Path, intent: dict[str, Any], order: dict[str, Any],
                    *, reason: str | None = None, strategy_readback_pending: bool = False) -> None:
    status = order.get("status")
    preserved = {
        key: intent[key]
        for key in (
            "decision_id", "order", "owner_id", "strategy_id",
            "decision_session", "source_receipt_ids",
        )
        if key in intent
    }
    _append_once(ledger, {
        **preserved,
        "client_order_id": intent["client_order_id"],
        "broker_status": status,
        "effect_id": intent["effect_id"],
        "mode": intent.get("mode", "paper"),
        "paper": intent.get("paper") is True,
        "receipt_type": "effect_intent",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
        "status": "reconciliation_pending",
        **({"reason": reason} if reason else {}),
        **({"strategy_readback_pending": True} if strategy_readback_pending else {}),
    }, ("receipt_type", "effect_id", "status", "broker_status", "strategy_readback_pending"))


def unresolved_intent_count(ledger: Path) -> int:
    return len(_unresolved(_rows(ledger)))


def effect_state(ledger: Path, effect_id: str) -> str:
    """Return the durable state of one sealed effect without changing the ledger."""
    rows = [row for row in _rows(ledger) if row.get("effect_id") == effect_id]
    if _unresolved(rows):
        return "started"
    if any(row.get("receipt_type") == "outcome" for row in rows):
        return "outcome"
    statuses = {row.get("status") for row in rows if row.get("receipt_type") == "effect_intent"}
    if "started" in statuses or "applied" in statuses or "reconciliation_blocked" in statuses:
        return "started"
    return "planned"


def record_terminal_outcome(ledger: Path, sealed: dict[str, str], broker: dict[str, Any],
                            outcome: str) -> bool:
    """Close a canary intent only after an official terminal broker readback."""
    if outcome not in {"live_canary_verified", "live_canary_terminal_failure",
                       "live_close_verified", "live_close_terminal_failure"}:
        raise ValueError("effect_outcome_invalid")
    mode = _mode(sealed.get("mode"))
    return _append_once(ledger, {
        "broker": broker, "client_order_id": sealed["client_order_id"],
        "effect_id": sealed["effect_id"], "mode": mode, "outcome": outcome,
        "paper": mode == "paper", "receipt_type": "outcome",
        "recorded_at": datetime.now(timezone.utc).isoformat(), "schema_version": 1,
    }, ("receipt_type", "effect_id"))


def reconcile_started(
    ledger: Path,
    find_order: Callable[[str], dict[str, Any] | None],
    *,
    on_reconciled: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any] | None] | None = None,
) -> dict[str, int]:
    rows = _rows(ledger)
    pending = _unresolved(rows)
    if len(pending) > 1:
        raise ValueError("multiple_unresolved_intents")
    reconciled = 0
    deferred = 0
    for intent in pending:
        mode = intent.get("mode")
        if mode is None:
            if intent.get("paper") is not True:
                raise ValueError("investment_mode_invalid")
            mode = "paper"
        mode = _mode(mode)
        order = find_order(intent["client_order_id"])
        if order is None:
            _append_once(ledger, {
                "client_order_id": intent["client_order_id"], "effect_id": intent["effect_id"],
                "mode": mode, "paper": mode == "paper", "receipt_type": "effect_intent",
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "schema_version": 1, "status": "reconciliation_blocked",
            }, ("receipt_type", "effect_id", "status"))
            raise ValueError("reconciliation_blocked")
        status = order.get("status")
        if status != "filled":
            if status in BROKER_TERMINAL_FAILURE_STATUSES and not _filled_qty_positive(order):
                _append_once(ledger, {
                    "broker": order, "broker_receipt_id": order.get("id"),
                    "broker_status": status,
                    "client_order_id": intent["client_order_id"],
                    "effect_id": intent["effect_id"], "outcome": "broker_terminal_failure",
                    "mode": mode, "paper": mode == "paper", "receipt_type": "outcome",
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "schema_version": 1,
                }, ("receipt_type", "effect_id", "outcome", "broker_status",
                    "broker_receipt_id"))
                reconciled += 1
                continue
            _pending_status(
                ledger, intent, order,
                reason="partial_fill_requires_reconciliation" if status in BROKER_TERMINAL_FAILURE_STATUSES
                else None,
            )
            deferred += 1
            continue
        strategy_receipt = None
        if on_reconciled is not None:
            # The callback owns any additional provider/account readback needed
            # for a strategy-specific receipt.  It runs before this effect is
            # closed so a missing fill or foreign position remains retry-fenced.
            try:
                strategy_receipt = on_reconciled(intent, order)
            except ReconciliationPending as error:
                _pending_status(ledger, intent, order, reason=str(error), strategy_readback_pending=True)
                deferred += 1
                continue
            if strategy_receipt is not None and not isinstance(strategy_receipt, dict):
                raise ValueError("strategy_receipt_invalid")
        _append_once(ledger, {
            "client_order_id": intent["client_order_id"], "effect_id": intent["effect_id"],
            "mode": mode, "paper": mode == "paper", "receipt_type": "effect_intent",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "schema_version": 1, "status": "applied",
        }, ("receipt_type", "effect_id", "status"))
        outcome = {
            "broker": order, "broker_receipt_id": order.get("id"),
            "broker_status": status, "client_order_id": intent["client_order_id"],
            "effect_id": intent["effect_id"],
            "outcome": "broker_reconciled",
            "mode": mode, "paper": mode == "paper", "receipt_type": "outcome",
            "recorded_at": datetime.now(timezone.utc).isoformat(), "schema_version": 1,
        }
        if strategy_receipt is not None:
            outcome["strategy_receipt"] = strategy_receipt
        _append_once(ledger, outcome, (
            "receipt_type", "effect_id", "outcome", "broker_status", "broker_receipt_id", "strategy_receipt",
        ))
        reconciled += 1
    strategy_reconciled = 0
    if on_reconciled is not None:
        pending_effects = {intent["effect_id"] for intent in pending}
        for intent in _completed_without_strategy_receipt(_rows(ledger)):
            if intent["effect_id"] in pending_effects:
                continue
            order = find_order(intent["client_order_id"])
            if order is None or order.get("status") != "filled":
                raise ValueError("reconciliation_blocked")
            try:
                strategy_receipt = on_reconciled(intent, order)
            except ReconciliationPending as error:
                _pending_status(ledger, intent, order, reason=str(error), strategy_readback_pending=True)
                deferred += 1
                continue
            if strategy_receipt is None:
                continue
            if not isinstance(strategy_receipt, dict):
                raise ValueError("strategy_receipt_invalid")
            mode = _mode(intent.get("mode", "paper"))
            _append_once(ledger, {
                "broker": order,
                "broker_receipt_id": order.get("id"),
                "broker_status": order.get("status"),
                "client_order_id": intent["client_order_id"],
                "effect_id": intent["effect_id"],
                "mode": mode,
                "outcome": "broker_reconciled",
                "paper": mode == "paper",
                "receipt_type": "outcome",
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "schema_version": 1,
                "strategy_receipt": strategy_receipt,
            }, (
                "receipt_type", "effect_id", "outcome", "broker_status", "broker_receipt_id",
                "strategy_receipt",
            ))
            strategy_reconciled += 1
    result = {"pending": len(pending), "reconciled": reconciled,
              "unresolved": unresolved_intent_count(ledger)}
    if deferred:
        result["deferred"] = deferred
    if strategy_reconciled:
        result["strategy_reconciled"] = strategy_reconciled
    return result
