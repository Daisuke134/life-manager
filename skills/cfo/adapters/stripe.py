"""Pure Stripe readback adapter for the B0 economic attribution contract."""

from __future__ import annotations

from datetime import datetime, timezone

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
CHARGE_STATUSES = {"failed", "pending", "succeeded"}
REFUND_STATUSES = {"canceled", "failed", "pending", "requires_action", "succeeded"}
CLASSIFIED_CHARGE_CATEGORIES = {contract.REVENUE, "owner_deposit", "self_payment"}
# B0 normalizes amounts with Decimal's 28-significant-digit default context.
MAX_MINOR = 10**28 - 1
MAX_EVIDENCE_REFS = 32
TRUNCATED_EVIDENCE = "stripe://evidence/truncated"
COLLECTION_MANIFESTS = {
    "stripe://balance_transactions", "stripe://charges", "stripe://refunds",
    "stripe://subscriptions",
}
MOVEMENT_SIGNS = {
    "payout": -1,
    "payout_cancel": 1,
    "payout_failure": 1,
    "payout_minimum_balance_hold": -1,
    "payout_minimum_balance_release": 1,
    "topup": 1,
    "topup_reversal": -1,
    "connect_collection_transfer": -1,
    "transfer": -1,
    "transfer_cancel": 1,
    "transfer_failure": 1,
    "transfer_refund": 1,
    "stripe_fee": -1,
    "stripe_fx_fee": -1,
}
SUBSCRIPTION_STATUSES = {
    "active", "canceled", "incomplete", "incomplete_expired", "past_due", "paused",
    "trialing", "unpaid",
}
FINANCIAL_CATEGORIES = [contract.REVENUE, contract.REFUND, "payment_fee", "provider_fee"]
LIST_URLS = {
    "balance_transactions": "/v1/balance_transactions",
    "charges": "/v1/charges",
    "refunds": "/v1/refunds",
    "subscriptions": "/v1/subscriptions",
}


class StripeAttributionError(ValueError):
    """Typed payload conflict without embedding provider payloads."""


def _fail(code: str, object_type: str, object_id: object = "unknown") -> None:
    raise StripeAttributionError(f"{code}:{object_type}:{object_id}")


def _identifier(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _instant(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return None


def _record_instant(value: object) -> str | None:
    if not isinstance(value, str) or not contract.RFC3339.fullmatch(value):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
    except (OverflowError, OSError, ValueError):
        return None


def _currency(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    result = value.upper()
    return result if contract.CURRENCY.fullmatch(result) else None


def _minor(value: object, currency: str) -> str | None:
    if (isinstance(value, bool) or not isinstance(value, int)
            or value < 0 or value > MAX_MINOR):
        return None
    if currency in ZERO_DECIMAL:
        return str(value)
    whole, fractional = divmod(value, 100)
    if fractional == 0:
        return str(whole)
    return f"{whole}.{fractional:02d}".rstrip("0")


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
            or value.get("url") != LIST_URLS[name]
            or not isinstance(value.get("data"), list) or value.get("has_more") is not False):
        return [], False
    return value["data"], True


def _readback_reasons(payloads: dict, observed_at: str,
                      trailing_start: str) -> tuple[str | None, str | None]:
    readback = payloads.get("readback")
    if (not isinstance(readback, dict) or readback.get("provider") != "stripe"
            or readback.get("provenance") != "stripe_api"):
        return "read_failed", "read_failed"
    queries = readback.get("queries")
    trailing = queries.get("trailing") if isinstance(queries, dict) else None
    if not isinstance(trailing, dict) or trailing.get("has_more") is not False:
        return "read_failed", "read_failed"
    read_at = _record_instant(readback.get("read_at"))
    window_start = _record_instant(trailing.get("start"))
    window_end = _record_instant(trailing.get("end"))
    if read_at is None or window_start is None or window_end is None:
        return "read_failed", "read_failed"
    if (read_at != observed_at or window_start != trailing_start or window_end != observed_at
            or window_start >= window_end):
        return "stale_readback", "stale_readback"

    historical = queries.get("historical")
    if not isinstance(historical, dict) or historical.get("has_more") is not False:
        return None, "read_failed"
    historical_end = _record_instant(historical.get("end"))
    history_start = _record_instant(historical.get("history_start"))
    account_inception = historical.get("account_inception") is True
    if historical_end is None or history_start is None or not account_inception:
        return None, "read_failed"
    if (historical_end != observed_at or history_start >= historical_end
            or history_start > trailing_start):
        return None, "stale_readback"
    return None, None


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


def _refund_consistency_refs(transactions: dict[str, dict], charges: dict[str, dict],
                             refunds: dict[str, dict]) -> list[str]:
    refund_totals: dict[str, int] = {}
    transaction_totals: dict[str, int] = {}
    refs: list[str] = []
    for refund_id, refund in refunds.items():
        if (refund.get("object") != "refund"
                or refund.get("status") not in REFUND_STATUSES):
            refs.append(_evidence("refunds", refund_id))
            continue
        if refund.get("status") != "succeeded":
            continue
        charge_id = _identifier(refund.get("charge"))
        transaction_id = _identifier(refund.get("balance_transaction"))
        amount = refund.get("amount")
        transaction = transactions.get(transaction_id or "")
        if (not charge_id or isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0
                or not isinstance(transaction, dict)
                or transaction.get("object") != "balance_transaction"
                or transaction.get("type") not in REFUND_TYPES
                or transaction.get("source") != refund_id
                or transaction.get("amount") != -amount):
            refs.append(_evidence("refunds", refund_id))
            continue
        refund_totals[charge_id] = refund_totals.get(charge_id, 0) + amount
        transaction_totals[charge_id] = transaction_totals.get(charge_id, 0) - transaction["amount"]

    for charge_id, charge in charges.items():
        claimed = charge.get("amount_refunded")
        if (charge.get("object") != "charge" or isinstance(claimed, bool)
                or not isinstance(claimed, int) or claimed < 0
                or claimed != refund_totals.get(charge_id, 0)
                or claimed != transaction_totals.get(charge_id, 0)):
            refs.append(_evidence("charges", charge_id))
    return refs


def _charge_consistency_refs(transactions: dict[str, dict],
                             charges: dict[str, dict]) -> list[str]:
    refs: list[str] = []
    for charge_id, charge in charges.items():
        if (charge.get("object") != "charge"
                or charge.get("status") not in CHARGE_STATUSES):
            refs.append(_evidence("charges", charge_id))
            continue
        status = charge.get("status")
        if status not in {"pending", "succeeded"}:
            continue
        captured = charge.get("captured")
        livemode = charge.get("livemode")
        if captured is False or livemode is False:
            continue
        metadata = charge.get("metadata")
        economic_category = (metadata.get("lm_economic_category")
                             if isinstance(metadata, dict) else None)
        charge_amount = charge.get("amount")
        captured_amount = charge.get("amount_captured")
        full_capture = (
            not isinstance(charge_amount, bool) and isinstance(charge_amount, int)
            and charge_amount > 0
            and not isinstance(captured_amount, bool) and isinstance(captured_amount, int)
            and captured_amount == charge_amount
        )
        if (status == "succeeded" and charge.get("paid") is True and full_capture
                and economic_category == contract.REVENUE
                and (not isinstance(captured, bool) or not isinstance(livemode, bool))):
            refs.append(_evidence("charges", charge_id))
            continue
        if captured is not True or livemode is not True:
            continue
        if economic_category not in CLASSIFIED_CHARGE_CATEGORIES:
            if status == "succeeded":
                refs.append(_evidence("charges", charge_id))
            continue
        transaction_id = _identifier(charge.get("balance_transaction"))
        transaction = transactions.get(transaction_id or "")
        if (charge.get("paid") is not True or charge.get("disputed") is not False
                or transaction_id is None or not isinstance(transaction, dict)
                or transaction.get("object") != "balance_transaction"
                or transaction.get("type") not in CHARGE_TYPES
                or transaction.get("source") != charge_id):
            refs.append(_evidence("charges", charge_id))
    return refs


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


def _fee_receipt(*, transaction: dict, product_loop_id: str, occurred_at: str,
                 settled_at: str, fee: str, refs: list[str]) -> dict:
    return _receipt(
        transaction=transaction, product_loop_id=product_loop_id, occurred_at=occurred_at,
        settled_at=settled_at, state="verified", revenue_class=None,
        components=[{"category": "payment_fee", "amount": fee}], refs=refs, suffix=":fee",
    )


def _movement(transaction: dict, product_loop_id: str,
              category: str) -> list[dict] | None:
    currency = _currency(transaction.get("currency"))
    raw_amount = transaction.get("amount")
    raw_fee = transaction.get("fee")
    raw_net = transaction.get("net")
    expected_sign = MOVEMENT_SIGNS.get(transaction.get("type"))
    if (transaction.get("object") != "balance_transaction"
            or transaction.get("status") != "available" or expected_sign is None
            or isinstance(raw_amount, bool) or not isinstance(raw_amount, int)
            or isinstance(raw_fee, bool) or not isinstance(raw_fee, int) or raw_fee < 0
            or isinstance(raw_net, bool) or not isinstance(raw_net, int)
            or raw_amount * expected_sign <= 0 or raw_amount - raw_fee != raw_net):
        return None
    amount, _ = _absolute_minor(raw_amount, currency) if currency else (None, None)
    fee = _integer_minor(raw_fee, currency) if currency else None
    occurred_at = _instant(transaction.get("created"))
    settled_at = _instant(transaction.get("available_on"))
    if (not all((currency, amount, fee is not None, occurred_at, settled_at))
            or settled_at < occurred_at):
        return None
    transaction = {**transaction, "currency": currency}
    refs = [_evidence("balance_transactions", transaction["id"])]
    receipts = [_receipt(
        transaction=transaction, product_loop_id=product_loop_id, occurred_at=occurred_at,
        settled_at=settled_at, state="verified", revenue_class=None,
        components=[{"category": category, "amount": amount}],
        refs=refs,
    )]
    if fee != "0":
        receipts.append(_fee_receipt(
            transaction=transaction, product_loop_id=product_loop_id,
            occurred_at=occurred_at, settled_at=settled_at, fee=fee, refs=refs,
        ))
    return receipts


def _charge(transaction: dict, charge: dict | None, product_loop_id: str) -> list[dict] | None:
    currency = _currency(transaction.get("currency"))
    source = _identifier(transaction.get("source"))
    if not currency or not source or not isinstance(charge, dict):
        return None
    raw_amount = transaction.get("amount")
    raw_fee = transaction.get("fee")
    raw_net = transaction.get("net")
    charge_amount = charge.get("amount")
    captured_amount = charge.get("amount_captured")
    refunded_amount = charge.get("amount_refunded")
    transaction_amounts_valid = (
        not isinstance(raw_amount, bool) and isinstance(raw_amount, int)
        and not isinstance(raw_fee, bool) and isinstance(raw_fee, int)
        and not isinstance(raw_net, bool) and isinstance(raw_net, int)
        and raw_amount > 0 and raw_fee >= 0 and raw_amount - raw_fee == raw_net
    )
    charge_amounts_valid = (
        not isinstance(charge_amount, bool) and isinstance(charge_amount, int)
        and not isinstance(captured_amount, bool) and isinstance(captured_amount, int)
        and not isinstance(refunded_amount, bool) and isinstance(refunded_amount, int)
        and charge_amount > 0 and 0 <= captured_amount <= charge_amount
        and 0 <= refunded_amount <= captured_amount
    )
    status, transaction_status = charge.get("status"), transaction.get("status")
    amount = _integer_minor(raw_amount, currency)
    fee = _integer_minor(raw_fee, currency)
    occurred_at = _instant(charge.get("created"))
    settled_at = _instant(transaction.get("available_on"))
    if (transaction.get("object") != "balance_transaction" or not transaction_amounts_valid
            or not charge_amounts_valid
            or charge.get("object") != "charge" or charge.get("id") != source
            or charge.get("balance_transaction") != transaction.get("id")
            or _currency(charge.get("currency")) != currency or charge.get("livemode") is not True
            or charge.get("disputed") is not False or amount in (None, "0") or fee is None
            or not occurred_at or not settled_at or settled_at < occurred_at):
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
        and captured_amount == raw_amount
    )
    if (transaction_status == "pending" and pending_charge
            and economic_category == contract.REVENUE and fee == "0"):
        return [_receipt(
            transaction=transaction, product_loop_id=product_loop_id, occurred_at=occurred_at,
            settled_at=None, state="pending", revenue_class="one_time",
            components=[{"category": "pending_revenue", "amount": amount}], refs=refs,
            suffix=":pending",
        )]
    if (transaction_status != "available" or status != "succeeded" or charge.get("paid") is not True
            or charge.get("captured") is not True or captured_amount != raw_amount):
        return None
    category = economic_category
    revenue_class = metadata.get("lm_revenue_class", "one_time") if category == contract.REVENUE else None
    if revenue_class is not None and revenue_class not in contract.REVENUE_CLASSES:
        return None
    components = [{"category": category, "amount": amount}]
    if category == contract.REVENUE and fee != "0":
        components.append({"category": "payment_fee", "amount": fee})
    receipts = [_receipt(
        transaction=transaction, product_loop_id=product_loop_id, occurred_at=occurred_at,
        settled_at=settled_at, state="verified", revenue_class=revenue_class,
        components=components, refs=refs,
    )]
    if category != contract.REVENUE and fee != "0":
        receipts.append(_fee_receipt(
            transaction=transaction, product_loop_id=product_loop_id,
            occurred_at=occurred_at, settled_at=settled_at, fee=fee, refs=refs,
        ))
    return receipts


def _refund(transaction: dict, refund: dict | None, transactions: dict[str, dict],
            charges: dict[str, dict], product_loop_id: str) -> list[dict] | None:
    currency = _currency(transaction.get("currency"))
    source = _identifier(transaction.get("source"))
    if not currency or not source or not isinstance(refund, dict):
        return None
    charge_id = _identifier(refund.get("charge"))
    charge = charges.get(charge_id or "")
    charge_metadata = charge.get("metadata") if isinstance(charge, dict) else None
    original_transaction_id = (_identifier(charge.get("balance_transaction"))
                               if isinstance(charge, dict) else None)
    original_transaction = transactions.get(original_transaction_id or "")
    original_amount = (original_transaction.get("amount")
                       if isinstance(original_transaction, dict) else None)
    original_fee = (original_transaction.get("fee")
                    if isinstance(original_transaction, dict) else None)
    original_net = (original_transaction.get("net")
                    if isinstance(original_transaction, dict) else None)
    original_amounts_valid = (
        not isinstance(original_amount, bool) and isinstance(original_amount, int)
        and not isinstance(original_fee, bool) and isinstance(original_fee, int)
        and not isinstance(original_net, bool) and isinstance(original_net, int)
        and original_fee >= 0 and original_amount - original_fee == original_net
    )
    raw_amount = transaction.get("amount")
    raw_fee = transaction.get("fee")
    raw_net = transaction.get("net")
    transaction_amounts_valid = (
        not isinstance(raw_amount, bool) and isinstance(raw_amount, int)
        and not isinstance(raw_fee, bool) and isinstance(raw_fee, int)
        and not isinstance(raw_net, bool) and isinstance(raw_net, int)
        and raw_amount - raw_fee == raw_net
    )
    amount, amount_minor = _absolute_minor(raw_amount, currency)
    refund_amount = refund.get("amount")
    if isinstance(refund_amount, bool) or not isinstance(refund_amount, int):
        refund_amount = None
    fee = _integer_minor(raw_fee, currency)
    occurred_at = _instant(refund.get("created"))
    settled_at = _instant(transaction.get("available_on"))
    if (transaction.get("object") != "balance_transaction" or not transaction_amounts_valid
            or refund.get("object") != "refund" or refund.get("id") != source
            or refund.get("balance_transaction") != transaction.get("id")
            or refund.get("status") != "succeeded" or transaction.get("status") != "available"
            or _currency(refund.get("currency")) != currency or refund_amount != amount_minor
            or refund_amount is None or refund_amount <= 0
            or transaction.get("amount") != -refund_amount
            or not isinstance(charge, dict) or charge.get("object") != "charge"
            or charge.get("id") != charge_id or _currency(charge.get("currency")) != currency
            or charge.get("status") != "succeeded" or charge.get("paid") is not True
            or charge.get("captured") is not True or charge.get("disputed") is not False
            or charge.get("livemode") is not True
            or not isinstance(original_transaction, dict)
            or original_transaction.get("object") != "balance_transaction"
            or original_transaction.get("id") != original_transaction_id
            or original_transaction.get("source") != charge_id
            or original_transaction.get("type") not in CHARGE_TYPES
            or original_transaction.get("status") != "available"
            or _currency(original_transaction.get("currency")) != currency
            or not original_amounts_valid
            or isinstance(charge.get("amount"), bool) or not isinstance(charge.get("amount"), int)
            or isinstance(charge.get("amount_captured"), bool)
            or not isinstance(charge.get("amount_captured"), int)
            or isinstance(charge.get("amount_refunded"), bool)
            or not isinstance(charge.get("amount_refunded"), int)
            or charge.get("amount") < charge.get("amount_captured")
            or charge.get("amount_captured") != original_amount
            or not (refund_amount <= charge.get("amount_refunded")
                    <= charge.get("amount_captured"))
            or amount in (None, "0") or fee is None
            or not isinstance(charge_metadata, dict)
            or charge_metadata.get("lm_economic_category") != contract.REVENUE
            or not occurred_at or not settled_at or settled_at < occurred_at):
        return None
    transaction = {**transaction, "currency": currency}
    components = [{"category": contract.REFUND, "amount": amount}]
    if fee != "0":
        components.append({"category": "payment_fee", "amount": fee})
    return [_receipt(
        transaction=transaction, product_loop_id=product_loop_id, occurred_at=occurred_at,
        settled_at=settled_at, state="verified", revenue_class=None, components=components,
        refs=[_evidence("balance_transactions", transaction["id"]),
              _evidence("balance_transactions", original_transaction_id),
              _evidence("refunds", source), _evidence("charges", charge_id)],
    )]


def _subscription(row: dict, product_loop_id: str, observed_at: str) -> dict | None:
    subscription_id = _identifier(row.get("id"))
    currency = _currency(row.get("currency"))
    status = row.get("status")
    metadata = row.get("metadata")
    if (row.get("object") != "subscription" or not subscription_id or not currency
            or status not in SUBSCRIPTION_STATUSES or not isinstance(row.get("livemode"), bool)
            or not isinstance(metadata, dict)
            or metadata.get("lm_economic_category") != contract.REVENUE):
        return None
    active = status == "active"
    amount_minor = 0
    if active:
        items = row.get("items")
        if (not isinstance(items, dict) or items.get("object") != "list"
                or items.get("url") != f"/v1/subscription_items?subscription={subscription_id}"
                or items.get("has_more") is not False
                or not isinstance(items.get("data"), list) or not items["data"]):
            return None
        unique_items: dict[str, dict] = {}
        for item in items["data"]:
            item_id = _identifier(item.get("id")) if isinstance(item, dict) else None
            if item_id is None:
                return None
            if item_id in unique_items:
                if unique_items[item_id] != item:
                    return None
                continue
            unique_items[item_id] = item
        for item in unique_items.values():
            price = item.get("price") if isinstance(item, dict) else None
            recurring = price.get("recurring") if isinstance(price, dict) else None
            quantity = item.get("quantity") if isinstance(item, dict) else None
            interval_count = recurring.get("interval_count") if isinstance(recurring, dict) else None
            unit_amount = price.get("unit_amount") if isinstance(price, dict) else None
            if (not isinstance(item, dict) or item.get("object") != "subscription_item"
                    or not isinstance(price, dict) or price.get("object") != "price"
                    or price.get("livemode") is not True
                    or price.get("billing_scheme") != "per_unit"
                    or not isinstance(recurring, dict) or recurring.get("usage_type") != "licensed"
                    or recurring.get("interval") != "month"
                    or isinstance(interval_count, bool) or not isinstance(interval_count, int)
                    or interval_count != 1 or price.get("type") != "recurring"
                    or price.get("active") is not True or _currency(price.get("currency")) != currency
                    or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0
                    or isinstance(unit_amount, bool) or not isinstance(unit_amount, int)
                    or unit_amount <= 0):
                return None
            if _minor(unit_amount, currency) is None:
                return None
            amount_minor += unit_amount * quantity
            if amount_minor > MAX_MINOR:
                return None
    amount = _minor(amount_minor, currency)
    if amount is None:
        return None
    identity_at = observed_at.replace(".000000Z", "Z")
    record = {
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "subscription_snapshot",
        "snapshot_id": f"stripe:subscription:{subscription_id}:{identity_at}",
        "subscription_id": f"stripe:subscription:{subscription_id}",
        "product_loop_id": product_loop_id,
        "provider": "stripe",
        "currency": currency,
        "normalized_monthly_amount": amount,
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
        "evidence_refs": _bounded_evidence(refs),
    }
    return contract.validate_record(record)


def _bounded_evidence(refs: list[str]) -> list[str]:
    unique = set(refs)
    manifests = sorted(unique & COLLECTION_MANIFESTS)
    individual = sorted(unique - COLLECTION_MANIFESTS - {TRUNCATED_EVIDENCE})
    if len(manifests) + len(individual) <= MAX_EVIDENCE_REFS:
        return sorted([*manifests, *individual])
    slots = MAX_EVIDENCE_REFS - len(manifests) - 1
    return sorted([*manifests, *individual[:slots], TRUNCATED_EVIDENCE])


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
    readback_reason, historical_readback_reason = _readback_reasons(
        payloads, observed_at, trailing_start,
    )
    if readback_reason is not None:
        records = []
        for projection in ("historical", "trailing", "as_of"):
            records.append(_coverage(
                product_loop_id=product_loop_id, projection=projection,
                observed_at=observed_at, trailing_start=trailing_start, state="gap",
                reason=readback_reason, categories=[],
                refs=[_evidence("balance_transactions"), _evidence("charges"),
                      _evidence("refunds"), _evidence("subscriptions")],
            ))
        return sorted(records, key=lambda row: row["projection"])
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
        financial_refs.extend(_charge_consistency_refs(transactions, charges))
        financial_refs.extend(_refund_consistency_refs(transactions, charges, refunds))
        for transaction_id, transaction in sorted(transactions.items()):
            kind = transaction.get("type")
            produced = None
            if kind in PAYOUT_TYPES:
                produced = _movement(transaction, product_loop_id, "payout")
            elif kind in TOPUP_TYPES:
                produced = _movement(transaction, product_loop_id, "owner_deposit")
            elif kind in TRANSFER_TYPES:
                produced = _movement(transaction, product_loop_id, "internal_transfer")
            elif kind in FEE_TYPES and transaction.get("status") == "available":
                produced = _movement(transaction, product_loop_id, "provider_fee")
            elif kind in CHARGE_TYPES:
                produced = _charge(transaction, charges.get(str(transaction.get("source"))), product_loop_id)
            elif kind in REFUND_TYPES:
                produced = _refund(transaction, refunds.get(str(transaction.get("source"))),
                                   transactions, charges, product_loop_id)
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
        projection_state = financial_state
        projection_reason = financial_reason
        if (projection == "historical" and projection_state == "complete"
                and historical_readback_reason is not None):
            projection_state = "gap"
            projection_reason = historical_readback_reason
        records.append(_coverage(
            product_loop_id=product_loop_id, projection=projection, observed_at=observed_at,
            trailing_start=trailing_start, state=projection_state, reason=projection_reason,
            categories=FINANCIAL_CATEGORIES if projection_state == "complete" else [],
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
