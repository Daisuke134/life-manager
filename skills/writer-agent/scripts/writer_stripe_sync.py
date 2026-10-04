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


def _invoice_balance(
    invoice: dict[str, Any], by_id: dict[str, dict[str, Any]]
) -> Any:
    direct = _resolve_balance(invoice.get("balance_transaction"), by_id)
    if isinstance(direct, dict):
        return direct
    payments = invoice.get("payments")
    values = payments.get("data", []) if isinstance(payments, dict) else []
    for item in values:
        payment = item.get("payment") if isinstance(item, dict) else None
        intent = payment.get("payment_intent") if isinstance(payment, dict) else None
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
    payment_lineage: dict[str, dict[str, str]] = {}
    subscription_lineage: dict[str, dict[str, str]] = {}
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

    for item in objects.get("payment_intents", []):
        if not isinstance(item, dict):
            continue
        lineage = _metadata(item.get("metadata"), product="writer_article")
        identifier = item.get("id")
        if lineage is None or not isinstance(identifier, str):
            continue
        payment_lineage[identifier] = lineage
        test = item.get("livemode") is not True
        charge = item.get("latest_charge")
        transaction = _balance(
            _resolve_balance(
                charge.get("balance_transaction") if isinstance(charge, dict) else None,
                balances,
            ),
            currency=str(item.get("currency") or ""),
        )
        if item.get("status") != "succeeded" or transaction is None:
            continue
        if _major(item.get("amount_received")) != transaction["amount"]:
            continue
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
        transaction = _balance(
            _invoice_balance(item, balances), currency=str(item.get("currency") or "")
        )
        paid_at = item.get("status_transitions", {}).get("paid_at") if isinstance(item.get("status_transitions"), dict) else None
        if (
            lineage is None or not isinstance(identifier, str)
            or item.get("status") != "paid" or item.get("paid") is not True
            or transaction is None or paid_at is None
        ):
            continue
        amount = _major(item.get("amount_paid"))
        if amount != transaction["amount"]:
            continue
        test = item.get("livemode") is not True
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
            "external_contract_id": (
                subscription_id if isinstance(subscription_id, str) and subscription_id else None
            ),
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
        payment_intent_id = (
            payment_intent.get("id")
            if isinstance(payment_intent, dict) else payment_intent
        )
        lineage = (
            _metadata(payment_intent.get("metadata"), product="writer_article")
            if isinstance(payment_intent, dict) else None
        ) or payment_lineage.get(str(payment_intent_id))
        identifier = item.get("id")
        if lineage is None or not isinstance(identifier, str):
            continue
        test = item.get("livemode") is not True
        balance_receipt = _resolve_balance(item.get("balance_transaction"), balances)
        if not isinstance(balance_receipt, dict):
            balance_receipt = next((transaction for transaction in balances.values()
                                    if transaction.get("source") == identifier
                                    and transaction.get("type") in {"refund", "payment_refund"}), None)
        transaction = _balance(
            balance_receipt, currency=str(item.get("currency") or "")
        )
        try:
            refund_amount = _major(item.get("amount"))
        except StripeReceiptInvariant:
            continue
        if (transaction is None or balance_receipt.get("source") != identifier
                or balance_receipt.get("type") not in {"refund", "payment_refund"}
                or transaction["amount"] != refund_amount):
            continue
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
            "occurred_at": _iso(item.get("created")),
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
