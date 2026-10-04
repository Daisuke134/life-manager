#!/usr/bin/env python3
"""Read Stripe Writer objects into a PII-free append-only receipt outbox."""

from __future__ import annotations

import argparse
import base64
import fcntl
import getpass
import hashlib
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


API_VERSION = "2026-04-22.dahlia"
ENDPOINTS = {
    "checkout_sessions": (
        "/v1/checkout/sessions",
        ["data.payment_intent.latest_charge.balance_transaction"],
    ),
    "payment_intents": (
        "/v1/payment_intents",
        ["data.latest_charge.balance_transaction"],
    ),
    "subscriptions": ("/v1/subscriptions", ["data.items.data.price"]),
    "invoices": (
        "/v1/invoices",
        ["data.subscription", "data.payments.data.payment.payment_intent.latest_charge.balance_transaction"],
    ),
    "balance_transactions": ("/v1/balance_transactions", []),
    "refunds": ("/v1/refunds", ["data.payment_intent"]),
    "payouts": ("/v1/payouts", ["data.balance_transaction"]),
}
SHA256 = re.compile(r"[0-9a-f]{64}")
CHARGE_TYPES = {"charge", "payment"}
REFUND_TYPES = {"refund", "payment_refund"}


class StripeReceiptInvariant(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _iso(epoch: Any) -> str:
    if not isinstance(epoch, (int, float)) or isinstance(epoch, bool) or epoch < 0:
        raise StripeReceiptInvariant("Stripe timestamp is invalid")
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")


def _major(value: Any) -> float:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise StripeReceiptInvariant("Stripe minor-unit amount is invalid")
    return value / 100


def _metadata(value: Any, *, product: str | None = None) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    expected_product = value.get("product")
    if expected_product not in {"writer_article", "writer_archive"}:
        return None
    if product is not None and expected_product != product:
        return None
    fields = {
        key: value.get(key)
        for key in (
            "product", "slug", "artifact_id", "run_id", "lang", "client_reference_id"
        )
    }
    if not all(isinstance(item, str) and item.strip() for item in fields.values()):
        return None
    if fields["lang"] not in {"ja", "en"}:
        return None
    if fields["artifact_id"] != f"{fields['run_id']}__self-owned__{fields['lang']}":
        return None
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,99}", fields["slug"]) is None:
        return None
    return fields  # type: ignore[return-value]


def _dashboard(kind: str, identifier: str, test: bool) -> str:
    prefix = "test/" if test else ""
    sections = {
        "checkout": "payments",
        "payment": "payments",
        "subscription": "subscriptions",
        "invoice": "invoices",
        "refund": "refunds",
        "payout": "payouts",
        "balance": "balance",
    }
    return f"https://dashboard.stripe.com/{prefix}{sections[kind]}/{identifier}"


def _balance(
    value: Any, *, currency: str, require_available: bool = True
) -> dict[str, Any] | None:
    allowed = {"available"} if require_available else {"available", "pending"}
    if not isinstance(value, dict) or value.get("status") not in allowed:
        return None
    if value.get("currency") != currency:
        return None
    try:
        amount = _major(abs(value["amount"]))
        fee = _major(value["fee"])
        net = _major(abs(value["net"]))
        occurred_at = _iso(value["created"])
        settled_at = _iso(value["available_on"]) if value.get("available_on") is not None else None
    except (KeyError, StripeReceiptInvariant):
        return None
    if abs(amount - fee - net) > 1e-9:
        return None
    if require_available and settled_at is None:
        return None
    identifier = value.get("id")
    if not isinstance(identifier, str) or not identifier.startswith("txn_"):
        return None
    return {
        "id": identifier, "amount": amount, "fee": fee, "net": net,
        "currency": currency.upper(), "occurred_at": occurred_at,
        "settled_at": settled_at,
    }


def _resolve_balance(value: Any, by_id: dict[str, dict[str, Any]]) -> Any:
    return by_id.get(value) if isinstance(value, str) else value


def _reference_id(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict) and isinstance(value.get("id"), str):
        return value["id"]
    return None


def _payment_parent(intent: Any) -> dict[str, Any] | None:
    if not isinstance(intent, dict):
        return None
    intent_id = _reference_id(intent.get("id"))
    livemode = intent.get("livemode")
    charge = intent.get("latest_charge")
    charge_id = _reference_id(charge)
    if not isinstance(charge, dict) or not isinstance(livemode, bool):
        return None
    amount, captured, refunded = (
        charge.get("amount"), charge.get("amount_captured"), charge.get("amount_refunded")
    )
    if (intent.get("object") != "payment_intent" or not intent_id
            or intent.get("status") != "succeeded"
            or charge.get("object") != "charge" or charge.get("id") != charge_id
            or _reference_id(charge.get("payment_intent")) != intent_id
            or not isinstance(charge.get("livemode"), bool)
            or charge["livemode"] is not livemode
            or charge.get("status") != "succeeded" or charge.get("paid") is not True
            or charge.get("captured") is not True or charge.get("disputed") is not False
            or isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0
            or isinstance(captured, bool) or not isinstance(captured, int) or captured != amount
            or isinstance(refunded, bool) or not isinstance(refunded, int)
            or not 0 <= refunded <= captured
            or not isinstance(intent.get("currency"), str)
            or charge.get("currency") != intent.get("currency")):
        return None
    return {
        "intent_id": intent_id, "livemode": livemode, "charge_id": charge_id,
        "charge": charge, "currency": str(intent["currency"]),
    }


def _charge_settlement(intent: dict[str, Any], parent: dict[str, Any],
                       balances: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    charge = parent["charge"]
    balance_reference = charge.get("balance_transaction")
    balance = _resolve_balance(balance_reference, balances)
    transaction = _balance(balance, currency=parent["currency"])
    if not isinstance(balance, dict) or transaction is None:
        return None
    amount_received = intent.get("amount_received")
    captured = charge.get("amount_captured")
    raw_amount = balance.get("amount")
    if (balance.get("object") != "balance_transaction"
            or balance.get("id") != _reference_id(balance_reference)
            or _reference_id(balance.get("source")) != parent["charge_id"]
            or balance.get("type") not in CHARGE_TYPES
            or balance.get("status") != "available"
            or balance.get("currency") != parent["currency"]
            or isinstance(amount_received, bool) or not isinstance(amount_received, int)
            or isinstance(captured, bool) or not isinstance(captured, int)
            or isinstance(raw_amount, bool) or not isinstance(raw_amount, int)
            or raw_amount <= 0):
        return None
    try:
        received = _major(amount_received)
        captured_amount = _major(captured)
    except StripeReceiptInvariant:
        return None
    if transaction["amount"] != captured_amount or received != captured_amount:
        return None
    if datetime.fromisoformat(transaction["settled_at"].replace("Z", "+00:00")) < datetime.fromisoformat(
        transaction["occurred_at"].replace("Z", "+00:00")
    ):
        return None
    return transaction


def _invoice_payment_intent(
    invoice: dict[str, Any], payment_intents: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    payments = invoice.get("payments")
    values = payments.get("data", []) if isinstance(payments, dict) else []
    candidates = [
        row.get("payment", {}).get("payment_intent")
        for row in values if isinstance(row, dict) and isinstance(row.get("payment"), dict)
    ]
    candidates.append(invoice.get("payment_intent"))
    for candidate in candidates:
        if isinstance(candidate, dict):
            identifier = _reference_id(candidate)
            mapped = payment_intents.get(identifier or "")
            if mapped is not None and not isinstance(candidate.get("latest_charge"), dict):
                return mapped
            return candidate
        identifier = _reference_id(candidate)
        if identifier in payment_intents:
            return payment_intents[identifier]
    return None


def _invoice_balance(
    invoice: dict[str, Any], by_id: dict[str, dict[str, Any]],
    payment_intents: dict[str, dict[str, Any]],
) -> Any:
    direct = _resolve_balance(invoice.get("balance_transaction"), by_id)
    if isinstance(direct, dict):
        return direct
    payments = invoice.get("payments")
    values = payments.get("data", []) if isinstance(payments, dict) else []
    for item in values:
        payment = item.get("payment") if isinstance(item, dict) else None
        intent = payment.get("payment_intent") if isinstance(payment, dict) else None
        if not isinstance(intent, dict):
            identifier = _reference_id(intent)
            intent = payment_intents.get(identifier or "")
        charge = intent.get("latest_charge") if isinstance(intent, dict) else None
        transaction = charge.get("balance_transaction") if isinstance(charge, dict) else None
        resolved = _resolve_balance(transaction, by_id)
        if isinstance(resolved, dict):
            return resolved
    intent = _invoice_payment_intent(invoice, payment_intents)
    charge = intent.get("latest_charge") if isinstance(intent, dict) else None
    transaction = charge.get("balance_transaction") if isinstance(charge, dict) else None
    resolved = _resolve_balance(transaction, by_id)
    if isinstance(resolved, dict):
        return resolved
    return None


def _add_receipt(rows: list[dict[str, Any]], row: dict[str, Any]) -> None:
    immutable = {key: value for key, value in row.items() if key != "observed_at"}
    row["receipt_sha256"] = _hash(immutable)
    rows.append(row)


def normalize_objects(objects: dict[str, Any], *, observed_at: str) -> list[dict[str, Any]]:
    """Project Stripe objects to exact accounting fields and discard all PII."""
    try:
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise StripeReceiptInvariant("observed_at is invalid") from error
    if observed.tzinfo is None:
        raise StripeReceiptInvariant("observed_at requires timezone")
    rows: list[dict[str, Any]] = []
    payment_context: dict[str, dict[str, Any]] = {}
    subscription_lineage: dict[str, dict[str, str]] = {}
    payment_intents = {
        str(item["id"]): item for item in objects.get("payment_intents", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    balances = {
        str(item["id"]): item
        for item in objects.get("balance_transactions", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }

    for item in objects.get("checkout_sessions", []):
        lineage = _metadata(item.get("metadata")) if isinstance(item, dict) else None
        if lineage is None:
            continue
        test = item.get("livemode") is not True
        _add_receipt(rows, {
            "receipt_type": "checkout_observation", "stripe_id": item.get("id"),
            "product": lineage["product"], "artifact_id": lineage["artifact_id"],
            "run_id": lineage["run_id"], "lang": lineage["lang"],
            "slug": lineage["slug"], "client_reference_id": lineage["client_reference_id"],
            "payment_status": item.get("payment_status"),
            "status": "test" if test else "observed",
            "test": test, "observed_at": observed_at,
            "source_url": _dashboard("checkout", str(item.get("id")), test),
        })

    for item in payment_intents.values():
        lineage = _metadata(item.get("metadata"), product="writer_article")
        parent = _payment_parent(item)
        if lineage is None or parent is None:
            continue
        identifier = parent["intent_id"]
        transaction = _charge_settlement(item, parent, balances)
        payment_context[identifier] = {"lineage": lineage, "parent": parent,
                                       "transaction": transaction}
        if transaction is None:
            continue
        test = not parent["livemode"]
        money_status = "test" if test else "verified_received"
        common = {
            "artifact_id": lineage["artifact_id"], "run_id": lineage["run_id"],
            "lang": lineage["lang"], "slug": lineage["slug"],
            "stream": "self_owned_article", "revenue_class": "direct_writing",
            "currency": transaction["currency"], "test": test,
        }
        _add_receipt(rows, {
            "receipt_type": "money", **common, "kind": "sale",
            "amount": transaction["amount"], "status": money_status,
            "external_receipt_id": identifier, "counterparty": "external_reader",
            "source_url": _dashboard("payment", identifier, test),
            "occurred_at": transaction["occurred_at"],
            "settled_at": transaction["settled_at"], "observed_at": observed_at,
        })
        _add_receipt(rows, {
            "receipt_type": "fee", **common,
            "money_external_receipt_id": identifier, "fee_kind": "stripe",
            "amount": transaction["fee"], "status": "test" if test else "verified",
            "external_receipt_id": transaction["id"],
            "source_url": _dashboard("balance", transaction["id"], test),
            "occurred_at": transaction["occurred_at"],
            "settled_at": transaction["settled_at"], "observed_at": observed_at,
        })

    for item in objects.get("subscriptions", []):
        if not isinstance(item, dict):
            continue
        lineage = _metadata(item.get("metadata"), product="writer_archive")
        identifier = item.get("id")
        prices = item.get("items", {}).get("data", []) if isinstance(item.get("items"), dict) else []
        price = prices[0].get("price") if len(prices) == 1 and isinstance(prices[0], dict) else None
        recurring = price.get("recurring") if isinstance(price, dict) else None
        if lineage is None or not isinstance(identifier, str) or not isinstance(recurring, dict):
            continue
        test = item.get("livemode") is not True
        status = {
            "active": "active", "trialing": "trial", "past_due": "past_due",
            "canceled": "canceled", "unpaid": "past_due",
        }.get(item.get("status"), "unknown")
        if test:
            status = "test"
        subscription_lineage[identifier] = lineage
        unit_amount = price.get("unit_amount")
        currency = price.get("currency")
        if status == "unknown":
            amount = None
            normalized_currency = None
        else:
            try:
                amount = _major(unit_amount)
            except StripeReceiptInvariant:
                continue
            normalized_currency = str(currency).upper()
        _add_receipt(rows, {
            "receipt_type": "subscription", "stripe_id": identifier,
            "artifact_id": lineage["artifact_id"], "run_id": lineage["run_id"],
            "lang": lineage["lang"], "slug": lineage["slug"],
            "stream": "self_owned_subscription", "status": status,
            "amount": amount, "currency": normalized_currency,
            "interval": recurring.get("interval", "unknown"),
            "interval_count": recurring.get("interval_count"),
            "external_contract_id": identifier,
            "source_url": _dashboard("subscription", identifier, test),
            "test": test, "started_at": _iso(item.get("created")),
            "ended_at": _iso(item["canceled_at"]) if item.get("canceled_at") else None,
            "observed_at": observed_at,
        })

    for item in objects.get("invoices", []):
        if not isinstance(item, dict):
            continue
        subscription = item.get("subscription")
        subscription_id = (
            subscription.get("id") if isinstance(subscription, dict) else subscription
        )
        lineage = (
            _metadata(item.get("metadata"), product="writer_archive")
            or (
                _metadata(subscription.get("metadata"), product="writer_archive")
                if isinstance(subscription, dict) else None
            )
            or subscription_lineage.get(str(subscription_id))
        )
        identifier = item.get("id")
        intent = _invoice_payment_intent(item, payment_intents)
        parent = _payment_parent(intent)
        invoice_mode = item.get("livemode")
        transaction = _charge_settlement(intent, parent, balances) if parent else None
        invoice_balance = _invoice_balance(item, balances, payment_intents)
        paid_at = item.get("status_transitions", {}).get("paid_at") if isinstance(item.get("status_transitions"), dict) else None
        if (
            lineage is None or not isinstance(identifier, str)
            or item.get("status") != "paid" or item.get("paid") is not True
            or not isinstance(invoice_mode, bool) or parent is None
            or invoice_mode is not parent["livemode"]
            or transaction is None or not isinstance(invoice_balance, dict)
            or invoice_balance.get("id") != transaction["id"] or paid_at is None
            or str(item.get("currency") or "").upper() != transaction["currency"]
        ):
            continue
        try:
            amount = _major(item.get("amount_paid"))
        except StripeReceiptInvariant:
            continue
        if amount != transaction["amount"]:
            continue
        test = not parent["livemode"]
        common = {
            "artifact_id": lineage["artifact_id"], "run_id": lineage["run_id"],
            "lang": lineage["lang"], "slug": lineage["slug"],
            "stream": "self_owned_subscription", "revenue_class": "direct_writing",
            "currency": transaction["currency"], "test": test,
        }
        _add_receipt(rows, {
            "receipt_type": "money", **common, "kind": "subscription_charge",
            "amount": amount, "status": "test" if test else "verified_received",
            "external_receipt_id": identifier, "counterparty": "external_reader",
            "source_url": _dashboard("invoice", identifier, test),
            "external_contract_id": _reference_id(subscription_id),
            "occurred_at": _iso(paid_at),
            "settled_at": transaction["settled_at"], "observed_at": observed_at,
        })
        _add_receipt(rows, {
            "receipt_type": "fee", **common,
            "money_external_receipt_id": identifier, "fee_kind": "stripe",
            "amount": transaction["fee"], "status": "test" if test else "verified",
            "external_receipt_id": transaction["id"],
            "source_url": _dashboard("balance", transaction["id"], test),
            "occurred_at": transaction["occurred_at"],
            "settled_at": transaction["settled_at"], "observed_at": observed_at,
        })

    for item in objects.get("refunds", []):
        if not isinstance(item, dict) or item.get("status") != "succeeded":
            continue
        payment_intent = item.get("payment_intent")
        payment_intent_id = _reference_id(payment_intent)
        context = payment_context.get(payment_intent_id or "")
        if context is None and isinstance(payment_intent, dict):
            lineage = _metadata(payment_intent.get("metadata"), product="writer_article")
            parent = _payment_parent(payment_intent)
            original_transaction = (
                _charge_settlement(payment_intent, parent, balances) if parent else None
            )
            if lineage is not None and parent is not None:
                context = {
                    "lineage": lineage, "parent": parent,
                    "transaction": original_transaction,
                }
        identifier = item.get("id")
        if context is None or context["transaction"] is None or not isinstance(identifier, str):
            continue
        parent = context["parent"]
        lineage = context["lineage"]
        charge = parent["charge"]
        if (_reference_id(payment_intent) != parent["intent_id"]
                or _reference_id(item.get("charge")) != parent["charge_id"]
                or ("livemode" in item
                    and (not isinstance(item["livemode"], bool)
                         or item["livemode"] is not parent["livemode"]))
                or (isinstance(payment_intent, dict) and "livemode" in payment_intent
                    and payment_intent["livemode"] is not parent["livemode"])):
            continue
        refund_test = not parent["livemode"]
        balance_reference = item.get("balance_transaction")
        if balance_reference is not None:
            balance_receipt = _resolve_balance(balance_reference, balances)
        else:
            balance_receipt = next((transaction for transaction in balances.values()
                                    if transaction.get("source") == identifier
                                    and transaction.get("type") in REFUND_TYPES), None)
        transaction = _balance(
            balance_receipt, currency=parent["currency"]
        )
        try:
            refund_amount = _major(item.get("amount"))
            refund_occurred_at = _iso(item.get("created"))
        except StripeReceiptInvariant:
            continue
        refund_settled_at = transaction.get("settled_at") if transaction else None
        amount_refunded = charge.get("amount_refunded")
        if (transaction is None or _reference_id(balance_receipt.get("source")) != identifier
                or balance_receipt.get("type") not in REFUND_TYPES
                or _reference_id(balance_reference) not in (None, balance_receipt.get("id"))
                or balance_receipt.get("amount", 0) >= 0
                or transaction["amount"] != refund_amount
                or str(item.get("currency") or "").upper() != parent["currency"].upper()
                or isinstance(amount_refunded, bool) or not isinstance(amount_refunded, int)
                or not refund_amount <= _major(amount_refunded) <= _major(charge["amount_captured"])
                or refund_settled_at is None
                or datetime.fromisoformat(refund_settled_at.replace("Z", "+00:00"))
                   < datetime.fromisoformat(refund_occurred_at.replace("Z", "+00:00"))):
            continue
        test = refund_test
        _add_receipt(rows, {
            "receipt_type": "refund", "artifact_id": lineage["artifact_id"],
            "run_id": lineage["run_id"], "lang": lineage["lang"],
            "slug": lineage["slug"], "stream": "self_owned_article",
            "revenue_class": "direct_writing", "kind": "refund",
            "amount": _major(item.get("amount")),
            "currency": str(item.get("currency")).upper(),
            "status": "test" if test else "refunded", "test": test,
            "external_receipt_id": identifier, "counterparty": "external_reader",
            "source_url": _dashboard("refund", identifier, test),
            "occurred_at": refund_occurred_at,
            "settled_at": transaction["settled_at"], "observed_at": observed_at,
        })

    for item in objects.get("payouts", []):
        if not isinstance(item, dict):
            continue
        identifier = item.get("id")
        transaction = _balance(
            _resolve_balance(item.get("balance_transaction"), balances),
            currency=str(item.get("currency") or ""), require_available=False,
        )
        if not isinstance(identifier, str) or transaction is None:
            continue
        test = item.get("livemode") is not True
        status = {
            "paid": "paid", "pending": "pending", "in_transit": "pending",
            "failed": "failed", "canceled": "failed",
        }.get(item.get("status"), "unknown")
        if test:
            status = "test"
        if status == "unknown":
            gross_amount = fee_amount = net_amount = normalized_currency = None
        else:
            gross_amount = transaction["amount"]
            fee_amount = transaction["fee"]
            net_amount = transaction["net"]
            normalized_currency = transaction["currency"]
        _add_receipt(rows, {
            "receipt_type": "payout", "stream": "self_owned_publication",
            "status": status, "gross_amount": gross_amount,
            "fee_amount": fee_amount, "net_amount": net_amount,
            "currency": normalized_currency, "test": test,
            "external_receipt_id": identifier,
            "source_url": _dashboard("payout", identifier, test),
            "occurred_at": _iso(item.get("arrival_date") or item.get("created")),
            "observed_at": observed_at,
        })
    return sorted(rows, key=lambda row: (str(row.get("occurred_at") or row.get("started_at") or ""), row["receipt_type"], str(row.get("external_receipt_id") or row.get("stripe_id") or "")))


def _atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _collect_once_unlocked(
    *, state_dir: Path, objects: dict[str, Any], observed_at: str,
) -> dict[str, Any]:
    state_dir = Path(state_dir)
    cursor_path = state_dir / "writer-stripe-cursor.json"
    outbox_path = state_dir / "writer-stripe-receipts.jsonl"
    try:
        cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cursor = {"schema_version": 1, "seen": []}
    seen = set(cursor.get("seen", []))
    rows = normalize_objects(objects, observed_at=observed_at)
    pending = [row for row in rows if row["receipt_sha256"] not in seen]
    if pending:
        outbox_path.parent.mkdir(parents=True, exist_ok=True)
        with outbox_path.open("a", encoding="utf-8") as handle:
            for row in pending:
                handle.write(_canonical(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        seen.update(row["receipt_sha256"] for row in pending)
    next_cursor = {"schema_version": 1, "seen": sorted(seen)}
    _atomic(cursor_path, next_cursor)
    return {
        "status": "ok", "observed": len(rows), "appended": len(pending),
        "cursor_sha256": _hash(next_cursor), "outbox": str(outbox_path),
    }


def collect_once(
    *, state_dir: Path, objects: dict[str, Any], observed_at: str,
) -> dict[str, Any]:
    state_dir = Path(state_dir)
    lock_path = state_dir / ".writer-stripe-sync.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        return _collect_once_unlocked(
            state_dir=state_dir, objects=objects, observed_at=observed_at
        )


def _request(secret: str, path: str, params: list[tuple[str, str]]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    token = base64.b64encode(f"{secret}:".encode()).decode()
    request = urllib.request.Request(
        f"https://api.stripe.com{path}?{query}",
        headers={
            "Authorization": f"Basic {token}",
            "Stripe-Version": API_VERSION,
            "User-Agent": "Writer-Stripe-Read/1.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise StripeReceiptInvariant("Stripe response is not an object")
    return value


def read_objects(secret: str, *, max_pages: int = 3) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(secret, str) or not secret.startswith("rk_"):
        raise StripeReceiptInvariant(
            "WRITER_STRIPE_READ_KEY must be a restricted read key"
        )
    result: dict[str, list[dict[str, Any]]] = {}
    for name, (path, expansions) in ENDPOINTS.items():
        values: list[dict[str, Any]] = []
        starting_after = None
        for _ in range(max_pages):
            params = [("limit", "100"), *[("expand[]", item) for item in expansions]]
            if starting_after:
                params.append(("starting_after", starting_after))
            page = _request(secret, path, params)
            data = page.get("data")
            if not isinstance(data, list):
                raise StripeReceiptInvariant(f"Stripe {name} list is malformed")
            clean = [item for item in data if isinstance(item, dict)]
            values.extend(clean)
            if page.get("has_more") is not True or not clean:
                break
            starting_after = clean[-1].get("id")
            if not isinstance(starting_after, str):
                raise StripeReceiptInvariant("Stripe pagination ID is absent")
        result[name] = values
    return result


def load_read_key() -> str:
    secret = os.environ.get("WRITER_STRIPE_READ_KEY", "")
    if secret:
        return secret
    service = os.environ.get(
        "WRITER_STRIPE_KEYCHAIN_SERVICE", "ai.anicca.writer-stripe-read"
    )
    result = subprocess.run(
        [
            "security", "find-generic-password", "-s", service, "-a",
            os.environ.get("WRITER_STRIPE_KEYCHAIN_ACCOUNT", getpass.getuser()), "-w",
        ],
        text=True, capture_output=True, check=False,
    )
    if result.returncode != 0:
        raise StripeReceiptInvariant("restricted Stripe read key is unavailable")
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=Path(__file__).resolve().parents[1] / "state")
    args = parser.parse_args(argv)
    secret = load_read_key()
    objects = read_objects(secret)
    result = collect_once(
        state_dir=args.state_dir, objects=objects,
        observed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
