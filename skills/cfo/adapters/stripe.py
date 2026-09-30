"""Pure Stripe readback adapter for the B0 economic attribution contract."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from skills.cfo import economic_attribution as contract


ZERO_DECIMAL = {
    "BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG",
    "RWF", "VND", "VUV", "XAF", "XOF", "XPF",
}
PAYOUT_TYPES = {
    "payout", "payout_cancel", "payout_failure", "payout_minimum_balance_hold",
    "payout_minimum_balance_release",
}
TOPUP_TYPES = {"topup", "topup_reversal"}
TRANSFER_TYPES = {
    "connect_collection_transfer", "transfer", "transfer_cancel", "transfer_failure",
    "transfer_refund",
}
CHARGE_TYPES = {"charge", "payment"}
REFUND_TYPES = {"refund", "payment_refund"}
FEE_TYPES = {"stripe_fee", "stripe_fx_fee"}
SUBSCRIPTION_STATUSES = {
    "active", "canceled", "incomplete", "incomplete_expired", "past_due", "paused",
    "trialing", "unpaid",
}
FINANCIAL_CATEGORIES = [contract.REVENUE, contract.REFUND, "payment_fee", "provider_fee"]


class StripeAttributionError(ValueError):
    """Typed payload conflict without embedding provider payloads."""


def _fail(code: str, object_type: str, object_id: object = "unknown") -> None:
    raise StripeAttributionError(f"{code}:{object_type}:{object_id}")


def _identifier(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _instant(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _record_instant(value: object) -> str | None:
    if not isinstance(value, str) or not contract.RFC3339.fullmatch(value):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _currency(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    result = value.upper()
    return result if contract.CURRENCY.fullmatch(result) else None


def _minor(value: object, currency: str) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    try:
        amount = Decimal(str(value)) / (Decimal(1) if currency in ZERO_DECIMAL else Decimal(100))
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return format(amount.normalize(), "f") if amount else "0"


def _absolute_minor(value: object, currency: str) -> tuple[str | None, int | None]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None, None
    return _minor(abs(value), currency), abs(value)


def _integer_minor(value: object, currency: str) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return _minor(value, currency)


def _read_list(payloads: dict, name: str) -> tuple[list[dict], bool]:
    value = payloads.get(name)
    if (not isinstance(value, dict) or value.get("object") != "list"
            or not isinstance(value.get("data"), list) or value.get("has_more") is not False):
        return [], False
    return value["data"], True


def _index(rows: list[dict], name: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for row in rows:
        object_id = _identifier(row.get("id")) if isinstance(row, dict) else None
        if object_id is None:
            _fail("payload_invalid", name)
        if object_id in result and result[object_id] != row:
            _fail("payload_conflict", name, object_id)
        result[object_id] = row
    return result


def _evidence(kind: str, object_id: str | None = None) -> str:
    return f"stripe://{kind}" + (f"/{object_id}" if object_id else "")


def _receipt(*, transaction: dict, product_loop_id: str, occurred_at: str,
             settled_at: str | None, state: str, revenue_class: str | None,
             components: list[dict], refs: list[str], suffix: str = "") -> dict:
    record = {
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "receipt",
        "receipt_id": f"stripe:balance_transaction:{transaction['id']}{suffix}",
        "product_loop_id": product_loop_id,
        "provider": "stripe",
        "currency": transaction["currency"].upper(),
        "occurred_at": occurred_at,
        "settled_at": settled_at,
        "verification_state": state,
        "revenue_class": revenue_class,
        "evidence_refs": refs,
        "components": components,
    }
    return contract.validate_record(record)


def _movement(transaction: dict, product_loop_id: str, category: str) -> dict | None:
    currency = _currency(transaction.get("currency"))
    amount, _ = _absolute_minor(transaction.get("amount"), currency) if currency else (None, None)
    occurred_at = _instant(transaction.get("created"))
    settled_at = _instant(transaction.get("available_on"))
    if not all((currency, amount, occurred_at, settled_at)):
        return None
    transaction = {**transaction, "currency": currency}
    return _receipt(
        transaction=transaction, product_loop_id=product_loop_id, occurred_at=occurred_at,
        settled_at=settled_at, state="verified", revenue_class=None,
        components=[{"category": category, "amount": amount}],
        refs=[_evidence("balance_transactions", transaction["id"])],
    )


def _charge(transaction: dict, charge: dict | None, product_loop_id: str) -> list[dict] | None:
    currency = _currency(transaction.get("currency"))
    source = _identifier(transaction.get("source"))
    if not currency or not source or not isinstance(charge, dict):
        return None
    status, transaction_status = charge.get("status"), transaction.get("status")
    amount = _integer_minor(transaction.get("amount"), currency)
    fee = _integer_minor(transaction.get("fee"), currency)
    occurred_at = _instant(charge.get("created"))
    settled_at = _instant(transaction.get("available_on"))
    if (charge.get("object") != "charge" or charge.get("id") != source
            or charge.get("balance_transaction") != transaction.get("id")
            or _currency(charge.get("currency")) != currency or charge.get("livemode") is not True
            or charge.get("disputed") is not False or amount in (None, "0") or fee is None
            or not occurred_at or not settled_at):
        return None
    metadata = charge.get("metadata")
    if not isinstance(metadata, dict):
        return None
    economic_category = metadata.get("lm_economic_category")
    if economic_category not in (contract.REVENUE, "owner_deposit", "self_payment"):
        return None
    transaction = {**transaction, "currency": currency}
    refs = [_evidence("balance_transactions", transaction["id"]), _evidence("charges", source)]
    pending_charge = status == "pending" or (
        status == "succeeded" and charge.get("paid") is True and charge.get("captured") is True
        and charge.get("amount_captured") == transaction.get("amount")
    )
    if transaction_status == "pending" and pending_charge and economic_category == contract.REVENUE:
        return [_receipt(
            transaction=transaction, product_loop_id=product_loop_id, occurred_at=occurred_at,
            settled_at=None, state="pending", revenue_class="one_time",
            components=[{"category": "pending_revenue", "amount": amount}], refs=refs,
            suffix=":pending",
        )]
    if (transaction_status != "available" or status != "succeeded" or charge.get("paid") is not True
            or charge.get("captured") is not True or charge.get("amount_captured") != transaction.get("amount")):
        return None
    category = economic_category
    revenue_class = metadata.get("lm_revenue_class", "one_time") if category == contract.REVENUE else None
    if revenue_class is not None and revenue_class not in contract.REVENUE_CLASSES:
        return None
    components = [{"category": category, "amount": amount}]
    if category == contract.REVENUE and fee != "0":
        components.append({"category": "payment_fee", "amount": fee})
    return [_receipt(
        transaction=transaction, product_loop_id=product_loop_id, occurred_at=occurred_at,
        settled_at=settled_at, state="verified", revenue_class=revenue_class,
        components=components, refs=refs,
    )]


def _refund(transaction: dict, refund: dict | None, charges: dict[str, dict],
            product_loop_id: str) -> list[dict] | None:
    currency = _currency(transaction.get("currency"))
    source = _identifier(transaction.get("source"))
    if not currency or not source or not isinstance(refund, dict):
        return None
    charge_id = _identifier(refund.get("charge"))
    charge = charges.get(charge_id or "")
    charge_metadata = charge.get("metadata") if isinstance(charge, dict) else None
    amount, amount_minor = _absolute_minor(transaction.get("amount"), currency)
    fee = _integer_minor(transaction.get("fee"), currency)
    occurred_at = _instant(refund.get("created"))
    settled_at = _instant(transaction.get("available_on"))
    if (refund.get("object") != "refund" or refund.get("id") != source
            or refund.get("balance_transaction") != transaction.get("id")
            or refund.get("status") != "succeeded" or transaction.get("status") != "available"
            or _currency(refund.get("currency")) != currency or refund.get("amount") != amount_minor
            or not isinstance(charge, dict) or charge.get("id") != charge_id
            or charge.get("livemode") is not True or amount in (None, "0") or fee is None
            or not isinstance(charge_metadata, dict)
            or charge_metadata.get("lm_economic_category") != contract.REVENUE
            or not occurred_at or not settled_at):
        return None
    transaction = {**transaction, "currency": currency}
    components = [{"category": contract.REFUND, "amount": amount}]
    if fee != "0":
        components.append({"category": "payment_fee", "amount": fee})
    return [_receipt(
        transaction=transaction, product_loop_id=product_loop_id, occurred_at=occurred_at,
        settled_at=settled_at, state="verified", revenue_class=None, components=components,
        refs=[_evidence("balance_transactions", transaction["id"]), _evidence("refunds", source),
              _evidence("charges", charge_id)],
    )]


def _subscription(row: dict, product_loop_id: str, observed_at: str) -> dict | None:
    subscription_id = _identifier(row.get("id"))
    currency = _currency(row.get("currency"))
    status = row.get("status")
    if (row.get("object") != "subscription" or not subscription_id or not currency
            or status not in SUBSCRIPTION_STATUSES or not isinstance(row.get("livemode"), bool)):
        return None
    active = status == "active"
    amount = Decimal(0)
    if active:
        items = row.get("items")
        if (not isinstance(items, dict) or items.get("object") != "list"
                or items.get("has_more") is not False or not items.get("data")):
            return None
        for item in items["data"]:
            price = item.get("price") if isinstance(item, dict) else None
            recurring = price.get("recurring") if isinstance(price, dict) else None
            quantity = item.get("quantity") if isinstance(item, dict) else None
            if (not isinstance(recurring, dict) or recurring.get("interval") != "month"
                    or recurring.get("interval_count") != 1 or price.get("type") != "recurring"
                    or price.get("active") is not True or _currency(price.get("currency")) != currency
                    or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0):
                return None
            unit = _minor(price.get("unit_amount_decimal"), currency)
            if unit is None:
                return None
            amount += Decimal(unit) * quantity
    identity_at = observed_at.replace(".000000Z", "Z")
    record = {
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "subscription_snapshot",
        "snapshot_id": f"stripe:subscription:{subscription_id}:{identity_at}",
        "subscription_id": f"stripe:subscription:{subscription_id}",
        "product_loop_id": product_loop_id,
        "provider": "stripe",
        "currency": currency,
        "normalized_monthly_amount": format(amount.normalize(), "f") if amount else "0",
        "normalization_basis": "provider_monthly",
        "status": "active" if active else "inactive",
        "observed_at": observed_at,
        "verification_state": "verified" if row["livemode"] else "unverified",
        "evidence_refs": [_evidence("subscriptions", subscription_id)],
    }
    return contract.validate_record(record)


def _coverage(*, product_loop_id: str, projection: str, observed_at: str,
              trailing_start: str, state: str, reason: str | None,
              categories: list[str], refs: list[str]) -> dict:
    source_id = "stripe-subscription-receipt" if projection == "as_of" else "stripe-financial-record"
    record = {
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "coverage",
        "product_loop_id": product_loop_id,
        "source_id": source_id,
        "projection": projection,
        "window_start": trailing_start if projection == "trailing" else None,
        "window_end": observed_at,
        "coverage_state": state,
        "reason": reason,
        "covered_categories": categories,
        "observed_at": observed_at,
        "evidence_refs": sorted(set(refs))[:32],
    }
    return contract.validate_record(record)


def adapt(payloads: dict, *, product_loop_id: str, observed_at: str,
          trailing_start: str) -> list[dict]:
    """Convert already-read Stripe list payloads; never calls Stripe or any network."""
    if not isinstance(payloads, dict):
        _fail("payload_invalid", "root")
    observed_at = _record_instant(observed_at)
    trailing_start = _record_instant(trailing_start)
    if observed_at is None:
        _fail("payload_invalid", "observed_at")
    if trailing_start is None:
        _fail("payload_invalid", "trailing_start")
    balance_rows, balance_complete = _read_list(payloads, "balance_transactions")
    charge_rows, charges_complete = _read_list(payloads, "charges")
    refund_rows, refunds_complete = _read_list(payloads, "refunds")
    subscription_rows, subscriptions_complete = _read_list(payloads, "subscriptions")

    charges = _index(charge_rows, "charges") if charges_complete else {}
    refunds = _index(refund_rows, "refunds") if refunds_complete else {}
    records: list[dict] = []
    financial_refs: list[str] = []
    financial_complete = balance_complete and charges_complete and refunds_complete
    if financial_complete:
        transactions = _index(balance_rows, "balance_transactions")
        for transaction_id, transaction in sorted(transactions.items()):
            kind = transaction.get("type")
            produced = None
            if kind in PAYOUT_TYPES:
                produced = [_movement(transaction, product_loop_id, "payout")]
            elif kind in TOPUP_TYPES:
                produced = [_movement(transaction, product_loop_id, "owner_deposit")]
            elif kind in TRANSFER_TYPES:
                produced = [_movement(transaction, product_loop_id, "internal_transfer")]
            elif kind in FEE_TYPES and transaction.get("status") == "available":
                produced = [_movement(transaction, product_loop_id, "provider_fee")]
            elif kind in CHARGE_TYPES:
                produced = _charge(transaction, charges.get(str(transaction.get("source"))), product_loop_id)
            elif kind in REFUND_TYPES:
                produced = _refund(transaction, refunds.get(str(transaction.get("source"))), charges,
                                   product_loop_id)
            if produced and all(produced):
                records.extend(produced)
            else:
                financial_refs.append(_evidence("balance_transactions", transaction_id))
    else:
        financial_refs.append(_evidence("balance_transactions"))

    subscription_refs: list[str] = []
    if subscriptions_complete:
        subscriptions = _index(subscription_rows, "subscriptions")
        for subscription_id, row in sorted(subscriptions.items()):
            snapshot = _subscription(row, product_loop_id, observed_at)
            if snapshot is None:
                subscription_refs.append(_evidence("subscriptions", subscription_id))
            else:
                records.append(snapshot)
    else:
        subscription_refs.append(_evidence("subscriptions"))

    financial_state = "complete" if financial_complete and not financial_refs else "gap"
    financial_reason = None if financial_state == "complete" else (
        "read_failed" if not financial_complete else "unverified_receipt"
    )
    financial_evidence = [_evidence("balance_transactions"), _evidence("charges"),
                          _evidence("refunds"), *financial_refs]
    for projection in ("historical", "trailing"):
        records.append(_coverage(
            product_loop_id=product_loop_id, projection=projection, observed_at=observed_at,
            trailing_start=trailing_start, state=financial_state, reason=financial_reason,
            categories=FINANCIAL_CATEGORIES if financial_state == "complete" else [],
            refs=financial_evidence,
        ))
    subscription_state = "complete" if subscriptions_complete and not subscription_refs else "gap"
    records.append(_coverage(
        product_loop_id=product_loop_id, projection="as_of", observed_at=observed_at,
        trailing_start=trailing_start, state=subscription_state,
        reason=None if subscription_state == "complete" else (
            "read_failed" if not subscriptions_complete else "unverified_receipt"
        ), categories=["mrr"] if subscription_state == "complete" else [],
        refs=[_evidence("subscriptions"), *subscription_refs],
    ))
    return sorted(records, key=lambda row: (
        row["record_type"], row.get("receipt_id", row.get("snapshot_id", row.get("projection", "")))
    ))
