"""Append-only paper effect receipts and reconciliation fence."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
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


def _append_once(path: Path, row: dict[str, Any], identity: tuple[str, ...]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        with os.fdopen(os.dup(descriptor), "r", encoding="utf-8") as handle:
            existing = [json.loads(line) for line in handle if line.strip()]
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


def _unresolved(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_outcome: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("receipt_type") == "outcome" and isinstance(row.get("effect_id"), str):
            latest_outcome[row["effect_id"]] = row
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("receipt_type") == "effect_intent" and isinstance(row.get("effect_id"), str):
            latest[row["effect_id"]] = row
    return [row for effect_id, row in latest.items()
            if row.get("status") in UNRESOLVED_INTENT_STATUSES
            and not _outcome_closed(latest_outcome.get(effect_id))]


def _completed_without_strategy_receipt(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find filled broker outcomes whose strategy-specific readback was never recorded."""
    latest_intent: dict[str, dict[str, Any]] = {}
    latest_outcome: dict[str, dict[str, Any]] = {}
    for row in rows:
        effect_id = row.get("effect_id")
        if not isinstance(effect_id, str):
            continue
        if row.get("receipt_type") == "effect_intent":
            latest_intent[effect_id] = row
        elif row.get("receipt_type") == "outcome":
            latest_outcome[effect_id] = row
    candidates: list[dict[str, Any]] = []
    for effect_id, outcome in latest_outcome.items():
        broker = outcome.get("broker")
        intent = latest_intent.get(effect_id)
        if (outcome.get("outcome") != "broker_reconciled"
                or not isinstance(broker, dict)
                or broker.get("status") != "filled"
                or not isinstance(intent, dict)
                or not isinstance(intent.get("client_order_id"), str)
                or isinstance(outcome.get("client_order_id"), str)
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
                    *, reason: str | None = None) -> None:
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
    }, ("receipt_type", "effect_id", "status", "broker_status"))


def unresolved_intent_count(ledger: Path) -> int:
    return len(_unresolved(_rows(ledger)))


def effect_state(ledger: Path, effect_id: str) -> str:
    """Return the durable state of one sealed effect without changing the ledger."""
    rows = [row for row in _rows(ledger) if row.get("effect_id") == effect_id]
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
            strategy_receipt = on_reconciled(intent, order)
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
            "receipt_type", "effect_id", "outcome", "broker_status", "broker_receipt_id",
        ))
        reconciled += 1
    strategy_reconciled = 0
    if on_reconciled is not None:
        for intent in _completed_without_strategy_receipt(_rows(ledger)):
            order = find_order(intent["client_order_id"])
            if order is None or order.get("status") != "filled":
                raise ValueError("reconciliation_blocked")
            strategy_receipt = on_reconciled(intent, order)
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
