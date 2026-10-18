"""Append-only paper effect receipts and reconciliation fence."""

from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from crypto_ownership_proof import (_digest, ReconciliationPending, BROKER_TERMINAL_FAILURE_STATUSES, owned_entry_decision_from_rows,
                                    recorded_close_proof_from_rows, no_fill_entry_proof_from_rows,
                                    recorded_no_fill_proof_from_rows, recorded_entry_proof_from_rows,
                                    _filled_qty_positive, _filled_qty_is_zero, _terminal_no_fill_proven,
                                    owned_quantity_state_from_rows, native_fee_debit_proof_from_rows,
                                    native_fee_debit_id)


MODES = frozenset({"paper", "shadow", "live"})
UNRESOLVED_INTENT_STATUSES = frozenset({
    "started", "reconciliation_blocked", "reconciliation_pending", "applied",
})



def _mode(value: Any) -> str:
    if value not in MODES:
        raise ValueError("investment_mode_invalid")
    return value



def _rows(path: Path) -> list[dict[str, Any]]:
    try:
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except FileNotFoundError:
        return []
    if not all(isinstance(value, dict) for value in values):
        raise ValueError("receipt_ledger_invalid")
    return values


def _append_once(path: Path, row: dict[str, Any] | Callable[[list[dict[str, Any]]], dict[str, Any] | None],
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
        if row is None:
            return False
        if any(all(item.get(key) == row.get(key) for key in identity) for item in existing):
            return False
        payload = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
        os.write(descriptor, payload)
        os.fsync(descriptor)
        return True
    finally:
        os.close(descriptor)


def record_native_fee_debit(ledger: Path, ownership: dict[str, Any], observation: dict[str, Any], *,
                            activity_readback: dict[str, Any], mode: str, owner_id: str) -> bool:
    if ledger.is_symlink():
        raise ValueError('owned_fee_debit_invalid')
    def candidate(rows):
        try:
            state=owned_quantity_state_from_rows(rows,ownership,mode=mode,owner_id=owner_id)
            current=ownership
            if Decimal(str(ownership.get('owned_qty')))!=Decimal(state['owned_qty']):
                fee=state['last_fee_debit']
                if (not fee or Decimal(str(ownership.get('owned_qty')))!=Decimal(fee['before_owned_qty'])
                        or Decimal(fee['remaining_owned_qty'])!=Decimal(state['owned_qty'])
                        or any(ownership.get(k)!=fee['last_'+k] or ownership.get(k)!=state['last_'+k]
                            for k in ('close_effect_id','close_client_order_id'))):
                    raise ValueError
                current={**ownership,'owned_qty':state['owned_qty']}
            proof=native_fee_debit_proof_from_rows(rows,current,observation,
                activity_readback=activity_readback,mode=mode,owner_id=owner_id)
            receipt=proof['receipt']
            if Decimal(receipt['debit_qty'])==0: return None
            return {'schema_version':1,'receipt_type':'native_fee_debit','paper':mode=='paper',
                **{key:receipt[key] for key in ('owner_id','mode','strategy_id','release_sha','entry_effect_id')},
                'fee_debit_id':native_fee_debit_id(receipt),'strategy_receipt':proof,
                'recorded_at':datetime.now(timezone.utc).isoformat()}
        except ReconciliationPending: raise
        except (ValueError,KeyError,TypeError,AttributeError,InvalidOperation) as error:
            raise ValueError('owned_fee_debit_invalid') from error
    return _append_once(ledger,candidate,('receipt_type','fee_debit_id'))


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


def _owned_rows(ledger: Path) -> list[dict[str, Any]]:
    if ledger.is_symlink():
        raise ValueError("owned_entry_identity_invalid")
    try:
        return _rows(ledger)
    except OSError as error:
        raise ValueError("owned_entry_ledger_unavailable") from error


def owned_entry_decision(ledger: Path, ownership: dict[str, Any], *, owner_id: str, mode: str) -> dict[str, Any]:
    return owned_entry_decision_from_rows(_owned_rows(ledger), ownership, owner_id=owner_id, mode=mode)




def record_no_fill_account_receipt(ledger: Path, ownership: dict[str, Any], broker: dict[str, Any],
                                   observation: dict[str, Any], *, owner_id: str, mode: str) -> dict[str, Any]:
    rows = _owned_rows(ledger)
    proof = no_fill_entry_proof_from_rows(rows, ownership, broker, observation, owner_id=owner_id, mode=mode)
    if any(row.get("receipt_type") == "outcome" and row.get("effect_id") == ownership["entry_effect_id"]
           and row.get("strategy_receipt") is not None for row in rows):
        return recorded_no_fill_proof_from_rows(rows, ownership, broker, observation, owner_id=owner_id, mode=mode)
    _append_once(ledger, {
        "schema_version": 1, "receipt_type": "outcome", "outcome": "broker_terminal_failure",
        "effect_id": ownership["entry_effect_id"], "client_order_id": ownership["entry_client_order_id"],
        "mode": mode, "paper": mode == "paper", "broker": broker, "broker_status": broker["status"],
        "broker_receipt_id": broker["id"], "strategy_receipt": proof,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }, ("receipt_type", "effect_id", "outcome", "broker_status", "broker_receipt_id", "strategy_receipt"))
    return proof


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



def _crypto_account_pending(intent: dict[str, Any], outcome: dict[str, Any] | None,
                          rows: list[dict[str, Any]]) -> bool:
    """Use the same historical proof as the position owner, without current state/env."""
    order = intent.get("order", {})
    if (not isinstance(order, dict) or order.get("asset_class") != "crypto" or order.get("side") not in {"buy", "sell"}
            or not isinstance(outcome, dict) or outcome.get("outcome") not in {"broker_reconciled", "broker_terminal_failure"}):
        return False
    try:
        if order["side"] == "buy":
            if outcome.get("outcome") != "broker_reconciled":
                return False
            ownership = {"status": "entry_pending", "symbol": "BTCUSD", "entry_filled_qty": "0",
                         "entry_effect_id": intent["effect_id"], "entry_client_order_id": intent["client_order_id"]}
            recorded_entry_proof_from_rows(rows, ownership, outcome["broker"],
                outcome["strategy_receipt"]["account_readback"], mode=intent["mode"], owner_id=intent["owner_id"])
            return False
        decisions = [r["decision"] for r in rows if r.get("receipt_type") == "decision"
                     and r.get("decision_id") == intent.get("decision_id")]
        if len(decisions) != 1:
            return True
        decision = decisions[0]
        entries = [r for r in rows if r.get("receipt_type") == "outcome"
                   and r.get("effect_id") == decision["entry_effect_id"]]
        ownership = {"status": "closing", "symbol": "BTCUSD",
            "entry_effect_id": decision["entry_effect_id"], "entry_client_order_id": decision["entry_client_order_id"],
            "entry_filled_qty": entries[-1]["broker"]["filled_qty"], "owned_qty": order["qty"],
            "close_effect_id": intent["effect_id"], "close_client_order_id": intent["client_order_id"]}
        recorded_close_proof_from_rows(rows, ownership, outcome["broker"],
            outcome["strategy_receipt"]["account_readback"], mode=intent["mode"], owner_id=intent["owner_id"])
    except (KeyError, IndexError, ValueError, TypeError, AttributeError):
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
            if (row.get("status") in UNRESOLVED_INTENT_STATUSES
                or (row.get("status") == "planned" and effect_id in latest_outcome))
            and (not _outcome_closed(latest_outcome.get(effect_id), rows)
                 or _crypto_account_pending(row, latest_outcome.get(effect_id), rows)
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
                       and ((row["order"].get("asset_class") == "crypto" and row["order"].get("side") in {"buy", "sell"})
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


def _outcome_closed(outcome: dict[str, Any] | None, rows: list[dict[str, Any]]) -> bool:
    if not isinstance(outcome, dict):
        return False
    kind = outcome.get("outcome")
    if kind in {"broker_terminal_failure", "broker_reconciled"}:
        broker = outcome.get("broker")
        if not isinstance(broker, dict):
            return False
        status = broker.get("status")
        if kind == "broker_reconciled" and status == "filled":
            return True
        if status not in BROKER_TERMINAL_FAILURE_STATUSES:
            return False
        intents = [row for row in rows if row.get("receipt_type") == "effect_intent"
                   and row.get("status") == "planned" and row.get("effect_id") == outcome.get("effect_id")]
        crypto_sells = [r for r in intents if isinstance(r.get("order"), dict)
                        and r["order"].get("asset_class") == "crypto" and r["order"].get("side") == "sell"]
        if crypto_sells:
            return len(intents) == 1 and not _crypto_account_pending(intents[0], outcome, rows)
        if kind == "broker_reconciled" and _filled_qty_positive(broker):
            return (len(intents) == 1 and isinstance(intents[0].get("order"), dict)
                    and intents[0]["order"].get("asset_class") == "crypto"
                    and intents[0]["order"].get("side") == "buy"
                    and not _crypto_account_pending(intents[0], outcome, rows))
        return _terminal_no_fill_proven(broker, rows, outcome.get("effect_id"))
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
        "broker_receipt_id": order.get("id"), "filled_qty": order.get("filled_qty"),
        "effect_id": intent["effect_id"],
        "mode": intent.get("mode", "paper"),
        "paper": intent.get("paper") is True,
        "receipt_type": "effect_intent",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
        "status": "reconciliation_pending",
        **({"reason": reason} if reason else {}),
        **({"strategy_readback_pending": True} if strategy_readback_pending else {}),
    }, ("receipt_type", "effect_id", "status", "broker_status", "strategy_readback_pending", "broker_receipt_id", "filled_qty"))


def unresolved_intent_count(ledger: Path) -> int:
    return len(_unresolved(_rows(ledger)))


def effect_state(ledger: Path, effect_id: str) -> str:
    """Return the durable state of one sealed effect without changing the ledger."""
    all_rows = _rows(ledger)
    if any(row.get("effect_id") == effect_id for row in _unresolved(all_rows)):
        return "started"
    rows = [row for row in all_rows if row.get("effect_id") == effect_id]
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
        terminal_crypto = (status in BROKER_TERMINAL_FAILURE_STATUSES and on_reconciled is not None
                       and intent.get("order", {}).get("asset_class") == "crypto"
                       and (_filled_qty_positive(order) or (intent["order"].get("side") == "sell" and _filled_qty_is_zero(order))))
        if status != "filled" and not terminal_crypto:
            if status in BROKER_TERMINAL_FAILURE_STATUSES and _terminal_no_fill_proven(order, rows, intent["effect_id"]):
                _append_once(ledger, {
                    "broker": order, "broker_receipt_id": order.get("id"),
                    "broker_status": status,
                    "client_order_id": intent["client_order_id"],
                    "effect_id": intent["effect_id"], "outcome": "broker_terminal_failure",
                    "mode": mode, "paper": mode == "paper", "receipt_type": "outcome",
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "schema_version": 1,
                }, ("receipt_type", "effect_id", "outcome", "broker_status",
                    "broker_receipt_id", "broker"))
                reconciled += 1
                continue
            _pending_status(
                ledger, intent, order,
                reason=("partial_fill_requires_reconciliation" if _filled_qty_positive(order)
                        else "fill_quantity_conflict" if _filled_qty_is_zero(order) else "fill_quantity_unknown") if status in BROKER_TERMINAL_FAILURE_STATUSES else None,
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
