"""Pure, fail-closed Capafy and mobile readback attribution adapters."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, DecimalException, InvalidOperation
from pathlib import Path
from typing import Any

from skills.cfo import economic_attribution as contract


CAPAFY_LOOP = "capafy"
MOBILE_LOOP = "mobile-apps"
MOBILE_PRODUCTS = (
    "anicca-ios",
    "honne-ai",
    "breath-reset",
    "sleep-ritual",
    "desk-stretch-timer",
    "micro-mood",
)
MOBILE_PRODUCT_BINDINGS = {
    "anicca-ios": {
        "asc_app_id": "6755129214",
        "revenuecat_app_id": "app511ef26659",
    },
    "honne-ai": {
        "asc_app_id": "6759667221",
        "revenuecat_app_id": "app3bbd298d22",
    },
    "breath-reset": {
        "asc_app_id": "6760253231",
        "revenuecat_app_id": "app498e23effc",
    },
    "sleep-ritual": {
        "asc_app_id": "6759916261",
        "revenuecat_app_id": "app92143da86e",
    },
    "desk-stretch-timer": {
        "asc_app_id": "6760048397",
        "revenuecat_app_id": "appca8d955a75",
    },
    "micro-mood": {
        "asc_app_id": "6759877003",
        "revenuecat_app_id": "appdda58236fa",
    },
}
COUNTED = ("provider_fee", "refund", "settled_external_revenue")
MOBILE_COMPLETE_PERIOD_MAX_LAG = timedelta(days=1)
MAX_B0_AMOUNT_INTEGER_DIGITS = 26


def _instant(value: Any) -> str:
    if not isinstance(value, str) or not contract.RFC3339.fullmatch(value):
        raise ValueError("timestamp_invalid")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp_naive")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _epoch_millis(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("timestamp_invalid")
    try:
        return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        raise ValueError("timestamp_invalid") from None


def _bounded_decimal(value: Any, *, signed: bool = False) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("amount_invalid")
    raw = str(value)
    unsigned = raw[1:] if signed and raw.startswith("-") else raw
    if (
        not contract.AMOUNT.fullmatch(unsigned)
        or len(unsigned.partition(".")[0]) > MAX_B0_AMOUNT_INTEGER_DIGITS
    ):
        raise ValueError("amount_invalid")
    try:
        amount = Decimal(raw)
        if not amount.is_finite():
            raise ValueError("amount_invalid")
        return amount
    except (DecimalException, ArithmeticError, ValueError):
        raise ValueError("amount_invalid") from None


def _money(value: Any, *, allow_zero: bool = True) -> str:
    try:
        amount = _bounded_decimal(value)
        if not amount.is_finite() or amount < 0 or (not allow_zero and amount == 0):
            raise ValueError("amount_invalid")
        return format(amount.normalize(), "f") if amount else "0"
    except (DecimalException, ArithmeticError, ValueError):
        raise ValueError("amount_invalid") from None


def _currency(value: Any) -> str:
    currency = value.upper() if isinstance(value, str) else ""
    if (
        not contract.CURRENCY.fullmatch(currency)
        or currency in {"UNKNOWN", "USD_API_EQUIV"}
    ):
        raise ValueError("unsupported_currency")
    return currency


def _sha256(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError("evidence_invalid")
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode()
    except (TypeError, ValueError):
        raise ValueError("content_hash_invalid") from None


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _capafy_content_sha256(payload: dict) -> str:
    keys = (
        "schema_version", "kind", "observed_at", "window_start", "window_end",
        "history_complete", "currency", "pagination", "account_inventory", "orders",
    )
    try:
        content = {key: payload[key] for key in keys}
    except KeyError:
        raise ValueError("content_hash_invalid") from None
    return _canonical_sha256(content)


def _capafy_account_inventory_sha256(inventory: dict) -> str:
    keys = (
        "schema_version", "kind", "observed_at", "developer_id",
        "owner_buyer_ids", "complete",
    )
    try:
        content = {key: inventory[key] for key in keys}
    except KeyError:
        raise ValueError("account_inventory_invalid") from None
    return _canonical_sha256(content)


def _capafy_settlement_row_sha256(order: dict, currency: str) -> str:
    return _canonical_sha256({
        "order_id": order["orderId"],
        "subscription_id": order.get("subscriptionId"),
        "buyer_id": order["buyerId"],
        "developer_id": order["developerId"],
        "currency": currency,
        "amount": order["amount"],
        "platform_fee_amount": order["platformFeeAmount"],
        "payment_at": order["paymentAt"],
        "completed_at": order["completedAt"],
    })


def _capafy_pending_row_sha256(order: dict, currency: str) -> str:
    return _canonical_sha256({
        "order_id": order["orderId"],
        "subscription_id": order.get("subscriptionId"),
        "buyer_id": order["buyerId"],
        "developer_id": order["developerId"],
        "currency": currency,
        "amount": order["amount"],
        "created_at": order["createdAt"],
        "status": order["status"],
        "is_settled": order["isSettled"],
    })


def _capafy_refund_row_sha256(order: dict, currency: str) -> str:
    return _canonical_sha256({
        "order_id": order["orderId"],
        "refund_id": order["refundId"],
        "buyer_id": order["buyerId"],
        "developer_id": order["developerId"],
        "currency": currency,
        "refund_amount": order["refundAmount"],
        "refunded_at": order["refundedAt"],
    })


def _load(source: Any) -> tuple[Any | None, str | None]:
    if isinstance(source, (dict, list)):
        return source, None
    try:
        path = Path(source)
    except TypeError:
        return None, "read_failed"
    if not path.exists():
        return None, "source_unconnected"
    try:
        text = path.read_text()
        if path.suffix == ".jsonl":
            return [json.loads(line) for line in text.splitlines() if line.strip()], None
        return json.loads(text), None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, "read_failed"


def _coverage(
    *,
    loop_id: str,
    source_id: str,
    projection: str,
    snapshot_at: str,
    trailing_start: str,
    observed_at: str,
    evidence_ref: str,
    complete: bool,
    reason: str | None,
    categories: tuple[str, ...],
) -> dict:
    return contract.validate_record({
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "coverage",
        "product_loop_id": loop_id,
        "source_id": source_id,
        "projection": projection,
        "window_start": trailing_start if projection == "trailing" else None,
        "window_end": snapshot_at,
        "coverage_state": "complete" if complete else "gap",
        "reason": None if complete else reason,
        "covered_categories": list(categories) if complete else [],
        "observed_at": observed_at,
        "evidence_refs": [evidence_ref],
    })


def _gap_set(
    *, loop_id: str, source_ids: tuple[str, ...], reason: str,
    snapshot_at: str, trailing_start: str,
) -> list[dict]:
    projections = {
        CAPAFY_LOOP: ("historical", "trailing", "as_of"),
        MOBILE_LOOP: ("historical", "trailing", "as_of"),
    }[loop_id]
    rows = []
    for source_id, projection in zip(source_ids, projections, strict=True):
        rows.append(_coverage(
            loop_id=loop_id,
            source_id=source_id,
            projection=projection,
            snapshot_at=snapshot_at,
            trailing_start=trailing_start,
            observed_at=snapshot_at,
            evidence_ref=f"adapter://{source_id}/{reason}",
            complete=False,
            reason=reason,
            categories=(),
        ))
    return rows


def _capafy_gaps(reason: str, snapshot_at: str, trailing_start: str) -> list[dict]:
    return _gap_set(
        loop_id=CAPAFY_LOOP,
        source_ids=("capafy-orders", "capafy-orders", "capafy-orders"),
        reason=reason,
        snapshot_at=snapshot_at,
        trailing_start=trailing_start,
    )


def adapt_capafy(
    source: Any, *, snapshot_at: str, trailing_start: str,
) -> list[dict]:
    """Convert a passed Capafy order readback; never performs provider I/O."""
    snapshot_at, trailing_start = _instant(snapshot_at), _instant(trailing_start)
    payload, load_error = _load(source)
    if load_error:
        return _capafy_gaps(load_error, snapshot_at, trailing_start)
    required = {
        "schema_version", "kind", "observed_at", "window_start", "window_end",
        "history_complete", "currency", "pagination", "content_sha256",
        "evidence_ref", "account_inventory", "orders",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != required
        or type(payload.get("schema_version")) is not int
        or payload["schema_version"] != 1
        or payload.get("kind") != "capafy_order_readback_snapshot"
        or not isinstance(payload.get("orders"), list)
    ):
        return _capafy_gaps("missing_coverage", snapshot_at, trailing_start)
    try:
        pagination = payload["pagination"]
        inventory = payload["account_inventory"]
        content_sha = _sha256(payload["content_sha256"])
        if (
            not isinstance(pagination, dict)
            or set(pagination) != {
                "complete", "pages_fetched", "records_fetched", "next_cursor",
            }
            or pagination.get("complete") is not True
            or isinstance(pagination.get("pages_fetched"), bool)
            or not isinstance(pagination.get("pages_fetched"), int)
            or pagination["pages_fetched"] < 1
            or isinstance(pagination.get("records_fetched"), bool)
            or not isinstance(pagination.get("records_fetched"), int)
            or pagination.get("records_fetched") != len(payload["orders"])
            or pagination.get("next_cursor") is not None
            or content_sha != _capafy_content_sha256(payload)
            or payload.get("evidence_ref")
            != f"capafy://orders/readback/sha256/{content_sha}"
        ):
            raise ValueError("content_proof_invalid")
        observed_at = _instant(payload["observed_at"])
        window_start = _instant(payload["window_start"])
        window_end = _instant(payload["window_end"])
        currency = _currency(payload["currency"])
        evidence_ref = payload["evidence_ref"]
        if not isinstance(evidence_ref, str) or not contract.EVIDENCE.fullmatch(evidence_ref):
            raise ValueError("missing_coverage")
        inventory_required = {
            "schema_version", "kind", "observed_at", "developer_id",
            "owner_buyer_ids", "complete", "content_sha256", "evidence_ref",
        }
        if not isinstance(inventory, dict) or set(inventory) != inventory_required:
            raise ValueError("account_inventory_invalid")
        inventory_sha = _sha256(inventory["content_sha256"])
        inventory_developer = inventory.get("developer_id")
        owner_buyer_ids = inventory.get("owner_buyer_ids")
        if (
            type(inventory.get("schema_version")) is not int
            or inventory["schema_version"] != 1
            or inventory.get("kind") != "capafy_account_inventory_readback"
            or inventory.get("complete") is not True
            or _instant(inventory.get("observed_at")) != observed_at
            or not isinstance(inventory_developer, str)
            or not contract.IDENTITY.fullmatch(inventory_developer)
            or not isinstance(owner_buyer_ids, list)
            or not owner_buyer_ids
            or any(
                not isinstance(owner_id, str)
                or not contract.IDENTITY.fullmatch(owner_id)
                for owner_id in owner_buyer_ids
            )
            or len(owner_buyer_ids) != len(set(owner_buyer_ids))
            or inventory_developer not in owner_buyer_ids
            or inventory_sha != _capafy_account_inventory_sha256(inventory)
            or inventory.get("evidence_ref")
            != f"capafy://accounts/readback/sha256/{inventory_sha}"
        ):
            raise ValueError("account_inventory_invalid")
    except (ValueError, TypeError):
        reason = "unsupported_currency" if payload.get("currency") in {
            "UNKNOWN", "unknown", "USD_API_EQUIV"
        } else "missing_coverage"
        return _capafy_gaps(reason, snapshot_at, trailing_start)

    receipts: list[dict] = []
    has_unverified = False
    has_missing_identity = False
    malformed = False
    order_ids = [
        order.get("orderId") for order in payload["orders"] if isinstance(order, dict)
    ]
    if (
        len(order_ids) != len(payload["orders"])
        or any(not isinstance(order_id, str) for order_id in order_ids)
        or len(order_ids) != len(set(order_ids))
    ):
        return _capafy_gaps("missing_coverage", snapshot_at, trailing_start)
    for order in payload["orders"]:
        try:
            if (
                not isinstance(order, dict)
                or not isinstance(order.get("orderId"), str)
                or not contract.IDENTITY.fullmatch(order["orderId"])
            ):
                raise ValueError("missing_coverage")
            order_id = order["orderId"]
            subscription_id = order.get("subscriptionId")
            if subscription_id is None:
                recurring = False
            elif isinstance(subscription_id, str) and contract.IDENTITY.fullmatch(subscription_id):
                recurring = True
            else:
                raise ValueError("subscription_identity_invalid")
            buyer_id = order.get("buyerId")
            developer_id = order.get("developerId")
            if (
                not isinstance(buyer_id, str)
                or not isinstance(developer_id, str)
                or not buyer_id
                or not developer_id
                or developer_id != inventory_developer
            ):
                has_unverified = True
                continue
            if buyer_id in owner_buyer_ids:
                has_unverified = True
                continue
            if order.get("isSettled") is True and order.get("status") in {
                "paid", "completed", "refunded",
            }:
                gross = _money(order.get("amount"))
                refund = _money(order.get("refundAmount"))
                actual = _money(order.get("actualAmount"))
                developer_actual = _money(order.get("developerActualAmount"))
                fee = _money(order.get("platformFeeAmount"))
                if (
                    Decimal(gross) - Decimal(refund) != Decimal(actual)
                    or Decimal(developer_actual) + Decimal(fee) != Decimal(actual)
                ):
                    raise ValueError("amount_inconsistent")
                occurred_at = _epoch_millis(order.get("paymentAt"))
                settled_at = _epoch_millis(order.get("completedAt"))
                settlement_sha = _capafy_settlement_row_sha256(order, currency)
                order_evidence = (
                    f"capafy://orders/{order_id}/row-sha256/{settlement_sha}"
                )
                if Decimal(fee) > 0:
                    receipts.append(contract.validate_record({
                        "schema_version": contract.SCHEMA_VERSION,
                        "record_type": "receipt",
                        "receipt_id": f"capafy:fee:{order_id}",
                        "product_loop_id": CAPAFY_LOOP,
                        "provider": "capafy",
                        "currency": currency,
                        "occurred_at": occurred_at,
                        "settled_at": settled_at,
                        "verification_state": "verified",
                        "revenue_class": None,
                        "evidence_refs": [order_evidence],
                        "components": [{"category": "provider_fee", "amount": fee}],
                    }))
                if Decimal(gross) > 0:
                    receipts.append(contract.validate_record({
                        "schema_version": contract.SCHEMA_VERSION,
                        "record_type": "receipt",
                        "receipt_id": f"capafy:payment:{order_id}",
                        "product_loop_id": CAPAFY_LOOP,
                        "provider": "capafy",
                        "currency": currency,
                        "occurred_at": occurred_at,
                        "settled_at": settled_at,
                        "verification_state": "verified",
                        "revenue_class": "monthly_recurring" if recurring else "one_time",
                        "evidence_refs": [order_evidence],
                        "components": [{
                            "category": "settled_external_revenue", "amount": gross,
                        }],
                    }))
                if Decimal(refund) > 0:
                    refund_id = order.get("refundId")
                    if not isinstance(refund_id, str) or not refund_id:
                        has_missing_identity = True
                    else:
                        refunded_at = _epoch_millis(order.get("refundedAt"))
                        refund_sha = _capafy_refund_row_sha256(order, currency)
                        receipts.append(contract.validate_record({
                            "schema_version": contract.SCHEMA_VERSION,
                            "record_type": "receipt",
                            "receipt_id": f"capafy:refund:{refund_id}",
                            "product_loop_id": CAPAFY_LOOP,
                            "provider": "capafy",
                            "currency": currency,
                            "occurred_at": refunded_at,
                            "settled_at": refunded_at,
                            "verification_state": "verified",
                            "revenue_class": None,
                            "evidence_refs": [
                                f"capafy://refunds/{refund_id}/row-sha256/{refund_sha}"
                            ],
                            "components": [{"category": "refund", "amount": refund}],
                        }))
            elif order.get("isSettled") is False and order.get("status") == "pending_payment":
                has_unverified = True
                amount = _money(order.get("amount"), allow_zero=False)
                occurred_at = _epoch_millis(order.get("createdAt"))
                pending_sha = _capafy_pending_row_sha256(order, currency)
                receipts.append(contract.validate_record({
                    "schema_version": contract.SCHEMA_VERSION,
                    "record_type": "receipt",
                    "receipt_id": f"capafy:order:{order_id}",
                    "product_loop_id": CAPAFY_LOOP,
                    "provider": "capafy",
                    "currency": currency,
                    "occurred_at": occurred_at,
                    "settled_at": None,
                    "verification_state": "pending",
                    "revenue_class": "monthly_recurring" if recurring else "one_time",
                    "evidence_refs": [
                        f"capafy://orders/{order_id}/row-sha256/{pending_sha}"
                    ],
                    "components": [{"category": "pending_revenue", "amount": amount}],
                }))
            elif order.get("isSettled") is False and order.get("status") in {
                "payment_failed", "declined", "canceled", "cancelled",
            }:
                continue
            else:
                has_unverified = True
        except (ValueError, contract.ContractError):
            malformed = True

    if malformed:
        return _capafy_gaps("missing_coverage", snapshot_at, trailing_start)
    fresh = observed_at == snapshot_at and window_end == snapshot_at
    reason = "stale_readback" if not fresh else (
        "missing_coverage" if has_missing_identity else (
            "unverified_receipt" if has_unverified else None
        )
    )
    historical_complete = (
        fresh and payload["history_complete"] is True
        and not has_unverified and not has_missing_identity
    )
    trailing_complete = (
        fresh and not has_unverified and not has_missing_identity
        and window_start <= trailing_start and window_end == snapshot_at
    )
    coverage = [
        _coverage(
            loop_id=CAPAFY_LOOP, source_id="capafy-orders", projection="historical",
            snapshot_at=snapshot_at, trailing_start=trailing_start,
            observed_at=observed_at, evidence_ref=evidence_ref,
            complete=historical_complete,
            reason=reason or "missing_coverage", categories=COUNTED,
        ),
        _coverage(
            loop_id=CAPAFY_LOOP, source_id="capafy-orders", projection="trailing",
            snapshot_at=snapshot_at, trailing_start=trailing_start,
            observed_at=observed_at, evidence_ref=evidence_ref,
            complete=trailing_complete,
            reason=reason or "missing_coverage", categories=COUNTED,
        ),
        _coverage(
            loop_id=CAPAFY_LOOP, source_id="capafy-orders", projection="as_of",
            snapshot_at=snapshot_at, trailing_start=trailing_start,
            observed_at=observed_at, evidence_ref=evidence_ref,
            complete=False, reason=reason or "missing_coverage", categories=(),
        ),
    ]
    return sorted(receipts, key=lambda row: row["receipt_id"]) + coverage


def _mobile_gaps(reason: str, snapshot_at: str, trailing_start: str) -> list[dict]:
    return [
        _coverage(
            loop_id=MOBILE_LOOP, source_id=source_id, projection=projection,
            snapshot_at=snapshot_at, trailing_start=trailing_start,
            observed_at=snapshot_at, evidence_ref=f"adapter://{source_id}/{reason}",
            complete=False, reason=reason, categories=(),
        )
        for source_id, projection in (
            ("app-store-connect-financial", "historical"),
            ("app-store-connect-financial", "trailing"),
            ("revenuecat-mrr", "as_of"),
        )
    ]


def _business_date(value: Any) -> date:
    if not isinstance(value, str):
        raise ValueError("date_invalid")
    return date.fromisoformat(value)


def _revenuecat_content_sha256(source: dict) -> str:
    return _canonical_sha256({
        "status": source.get("status"),
        "reason": source.get("reason"),
        "data": source.get("data"),
    })


def _validated_financial_report(
    latest: dict[str, dict], products: tuple[str, ...],
) -> tuple[date, date]:
    report_identity: tuple[str, str, str, str, str] | None = None
    report_rows: list[dict] = []
    row_identities: set[tuple[str, int]] = set()
    for product in products:
        sources = latest[product].get("sources")
        if not isinstance(sources, dict):
            raise ValueError("missing_coverage")
        financial = sources.get("app_store_financial")
        if (
            not isinstance(financial, dict)
            or financial.get("status") != "available"
            or not isinstance(financial.get("data"), dict)
        ):
            raise ValueError("missing_coverage")
        data = financial["data"]
        report_id = data.get("report_id")
        report_sha = _sha256(data.get("report_sha256"))
        if (
            data.get("report_status") != "final"
            or not isinstance(report_id, str)
            or not contract.IDENTITY.fullmatch(report_id)
            or data.get("apple_identifier")
            != MOBILE_PRODUCT_BINDINGS[product]["asc_app_id"]
            or not isinstance(data.get("rows"), list)
        ):
            raise ValueError("missing_coverage")
        period_start = data.get("period_start")
        period_end = data.get("period_end")
        start = _business_date(period_start)
        end = _business_date(period_end)
        if start > end:
            raise ValueError("missing_coverage")
        identity = (
            report_id, report_sha, data["report_status"], period_start, period_end,
        )
        if report_identity is None:
            report_identity = identity
        elif identity != report_identity:
            raise ValueError("report_identity_mismatch")
        for item in data["rows"]:
            if not isinstance(item, dict):
                raise ValueError("missing_coverage")
            row_index = item.get("source_row_index")
            if isinstance(row_index, bool) or not isinstance(row_index, int) or row_index < 0:
                raise ValueError("missing_coverage")
            if item.get("apple_identifier") != data["apple_identifier"]:
                raise ValueError("product_identity_mismatch")
            row_identity = (report_id, row_index)
            if row_identity in row_identities:
                raise ValueError("duplicate_report_row")
            row_identities.add(row_identity)
            report_rows.append(item)

    if report_identity is None:
        raise ValueError("missing_coverage")
    report_id, report_sha, report_status, period_start, period_end = report_identity
    report_content = {
        "report_id": report_id,
        "report_status": report_status,
        "period_start": period_start,
        "period_end": period_end,
        "rows": sorted(report_rows, key=lambda item: item["source_row_index"]),
    }
    if report_sha != _canonical_sha256(report_content):
        raise ValueError("content_hash_invalid")
    return _business_date(period_start), _business_date(period_end)


def adapt_mobile(
    source: Any,
    *,
    snapshot_at: str,
    trailing_start: str,
    products: tuple[str, ...] = MOBILE_PRODUCTS,
) -> list[dict]:
    """Convert passed ASC/RevenueCat snapshots; never performs provider I/O."""
    snapshot_at, trailing_start = _instant(snapshot_at), _instant(trailing_start)
    snapshot_date = datetime.fromisoformat(snapshot_at.replace("Z", "+00:00")).date()
    latest_complete_date = snapshot_date - MOBILE_COMPLETE_PERIOD_MAX_LAG
    if len(products) != len(MOBILE_PRODUCTS) or set(products) != set(MOBILE_PRODUCTS):
        return _mobile_gaps("missing_coverage", snapshot_at, trailing_start)
    products = MOBILE_PRODUCTS
    payload, load_error = _load(source)
    if load_error:
        return _mobile_gaps(load_error, snapshot_at, trailing_start)
    if not isinstance(payload, list) or not payload:
        return _mobile_gaps("missing_coverage", snapshot_at, trailing_start)

    try:
        if any(
            not isinstance(row, dict) or row.get("product_id") not in products
            for row in payload
        ):
            raise ValueError("product_scope_invalid")
        rows_by_identity: dict[tuple[str, date], tuple[bytes, dict]] = {}
        for row in payload:
            if (
                type(row.get("schema_version")) is not int
                or row["schema_version"] != 1
            ):
                raise ValueError("missing_coverage")
            identity = (row["product_id"], _business_date(row.get("business_date")))
            canonical_row = _canonical_json_bytes(row)
            existing = rows_by_identity.get(identity)
            if existing is not None and existing[0] != canonical_row:
                raise ValueError("snapshot_identity_conflict")
            if existing is None:
                rows_by_identity[identity] = (canonical_row, row)
        rows = [row for _, row in rows_by_identity.values()]
        if not rows:
            raise ValueError("missing_coverage")
        latest_date = max(_business_date(row.get("business_date")) for row in rows)
        latest_product_ids = {
            row.get("product_id")
            for row in payload
            if isinstance(row, dict)
            and _business_date(row.get("business_date")) == latest_date
        }
        if latest_product_ids != set(MOBILE_PRODUCTS):
            raise ValueError("product_scope_invalid")
        latest = {
            product: max(
                (row for row in rows if row.get("product_id") == product
                 and _business_date(row.get("business_date")) == latest_date),
                key=lambda row: _instant(row.get("observed_at")),
            )
            for product in products
            if any(
                row.get("product_id") == product
                and _business_date(row.get("business_date")) == latest_date
                for row in rows
            )
        }
    except (ValueError, TypeError):
        return _mobile_gaps("missing_coverage", snapshot_at, trailing_start)

    unsupported = False
    for row in latest.values():
        sources = row.get("sources")
        if not isinstance(sources, dict):
            continue
        financial = sources.get("app_store_financial", {})
        rc = sources.get("revenuecat", {})
        try:
            if isinstance(financial, dict) and financial.get("status") == "available":
                financial_data = financial.get("data")
                financial_rows = (
                    financial_data.get("rows") if isinstance(financial_data, dict) else None
                )
                if isinstance(financial_rows, list):
                    for item in financial_rows:
                        if isinstance(item, dict):
                            _currency(item.get("partner_share_currency"))
            if isinstance(rc, dict) and rc.get("status") == "available":
                rc_data = rc.get("data")
                if isinstance(rc_data, dict):
                    _currency(rc_data.get("currency"))
        except (KeyError, TypeError, ValueError) as exc:
            if str(exc) == "unsupported_currency":
                unsupported = True
    if unsupported:
        return _mobile_gaps("unsupported_currency", snapshot_at, trailing_start)
    if set(latest) != set(products):
        return _mobile_gaps("missing_coverage", snapshot_at, trailing_start)

    try:
        financial_period = _validated_financial_report(latest, products)
        financial_report_valid = True
    except (KeyError, TypeError, ValueError):
        financial_period = None
        financial_report_valid = False

    financial_receipts: list[dict] = []
    snapshots: list[dict] = []
    financial_complete = financial_report_valid
    rc_complete = True
    observed_values: list[str] = []
    report_periods: list[tuple[date, date]] = []
    for product in products:
        row = latest[product]
        try:
            observed_at = _instant(row["observed_at"])
            observed_values.append(observed_at)
            business_date = row["business_date"]
            sources = row["sources"]
            if not isinstance(sources, dict):
                raise ValueError("missing_coverage")
        except (KeyError, TypeError, ValueError):
            financial_complete = rc_complete = False
            continue

        financial = sources.get("app_store_financial", {})
        product_receipts: list[dict] = []
        try:
            if not financial_report_valid:
                raise ValueError("missing_coverage")
            binding = MOBILE_PRODUCT_BINDINGS[product]
            if not isinstance(financial, dict) or financial.get("status") != "available" or not isinstance(
                financial.get("data"), dict
            ):
                raise ValueError("missing_coverage")
            data = financial["data"]
            report_id = data["report_id"]
            report_sha = _sha256(data["report_sha256"])
            if (
                data.get("report_status") != "final"
                or not isinstance(report_id, str)
                or not contract.IDENTITY.fullmatch(report_id)
                or data.get("apple_identifier") != binding["asc_app_id"]
                or not isinstance(data.get("rows"), list)
            ):
                raise ValueError("missing_coverage")
            expected_apple_identifier = binding["asc_app_id"]
            period_start = _business_date(data.get("period_start"))
            period_end = _business_date(data.get("period_end"))
            if period_start > period_end:
                raise ValueError("missing_coverage")
            for item in data["rows"]:
                if not isinstance(item, dict):
                    raise ValueError("missing_coverage")
                row_index = item.get("source_row_index")
                if isinstance(row_index, bool) or not isinstance(row_index, int) or row_index < 0:
                    raise ValueError("missing_coverage")
                currency = _currency(item.get("partner_share_currency"))
                if item.get("apple_identifier") != expected_apple_identifier:
                    raise ValueError("product_identity_mismatch")
                raw_amount = _bounded_decimal(
                    item.get("extended_partner_share"), signed=True,
                )
                transaction_kind = item.get("sale_or_return")
                product_type = item.get("product_type_identifier")
                if transaction_kind == "S" and raw_amount > 0:
                    category = "settled_external_revenue"
                    if product_type in {"1", "IA1"}:
                        revenue_class = "one_time"
                    elif product_type in {"IA9", "IAY"}:
                        revenue_class = "other_recurring"
                    else:
                        raise ValueError("revenue_class_unresolved")
                    amount = _money(raw_amount)
                elif transaction_kind == "R" and raw_amount < 0:
                    category = "refund"
                    revenue_class = None
                    amount = _money(-raw_amount)
                elif raw_amount == 0:
                    continue
                else:
                    raise ValueError("amount_invalid")
                settlement_date = _business_date(item.get("settlement_date"))
                transaction_date = _business_date(
                    item.get("transaction_date") or item.get("settlement_date")
                )
                if transaction_date > settlement_date:
                    raise ValueError("settlement_before_occurrence")
                product_receipts.append(contract.validate_record({
                        "schema_version": contract.SCHEMA_VERSION,
                        "record_type": "receipt",
                        "receipt_id": f"app-store-connect-financial:{report_id}:{row_index}",
                        "product_loop_id": MOBILE_LOOP,
                        "provider": "app-store-connect-financial",
                        "currency": currency,
                        "occurred_at": f"{transaction_date.isoformat()}T00:00:00Z",
                        "settled_at": f"{settlement_date.isoformat()}T00:00:00Z",
                        "verification_state": "verified",
                        "revenue_class": revenue_class,
                        "evidence_refs": [
                            f"appstoreconnect://financial-reports/{report_id}/{report_sha}#{row_index}"
                        ],
                        "components": [{"category": category, "amount": amount}],
                    }))
            financial_receipts.extend(product_receipts)
            report_periods.append((period_start, period_end))
        except (KeyError, TypeError, InvalidOperation, ValueError, contract.ContractError):
            financial_complete = False

        rc = sources.get("revenuecat", {})
        try:
            if not isinstance(rc, dict) or rc.get("status") != "available" or not isinstance(
                rc.get("data"), dict
            ):
                raise ValueError("missing_coverage")
            rc_data = rc["data"]
            evidence_sha = _sha256(rc.get("evidence_sha256"))
            if evidence_sha != _revenuecat_content_sha256(rc):
                raise ValueError("content_hash_invalid")
            if rc_data.get("app_id") != MOBILE_PRODUCT_BINDINGS[product]["revenuecat_app_id"]:
                raise ValueError("product_identity_mismatch")
            currency = _currency(rc_data.get("currency"))
            if rc_data.get("revenue_definition") != {
                "metric": "mrr",
                "scope": "active_paid_subscriptions",
                "normalization": "monthly",
            }:
                raise ValueError("missing_coverage")
            point = rc_data["charts"]["mrr"]["latest_complete"]["MRR"]
            if (
                not isinstance(point, dict)
                or point.get("incomplete") is not False
                or point.get("period") != business_date
            ):
                raise ValueError("missing_coverage")
            point_date = _business_date(point["period"])
            if (
                point_date > snapshot_date
                or snapshot_date - point_date > MOBILE_COMPLETE_PERIOD_MAX_LAG
            ):
                raise ValueError("missing_coverage")
            amount = _money(point.get("value"))
            status = "active" if Decimal(amount) > 0 else "inactive"
            snapshots.append(contract.validate_record({
                "schema_version": contract.SCHEMA_VERSION,
                "record_type": "subscription_snapshot",
                "snapshot_id": f"revenuecat:{product}:mrr:{business_date}",
                "subscription_id": f"revenuecat:{product}:mrr",
                "product_loop_id": MOBILE_LOOP,
                "provider": "revenuecat",
                "currency": currency,
                "normalized_monthly_amount": amount,
                "normalization_basis": "provider_monthly",
                "status": status,
                "observed_at": observed_at,
                "verification_state": "verified",
                "evidence_refs": [
                    f"revenuecat://charts/mrr/{product}/{business_date}/{evidence_sha}"
                ],
            }))
        except (KeyError, TypeError, ValueError, contract.ContractError):
            rc_complete = False

    fresh = bool(observed_values) and all(value == snapshot_at for value in observed_values)
    receipts = financial_receipts if financial_complete else []
    reason = "stale_readback" if not fresh else "missing_coverage"
    trailing_date = datetime.fromisoformat(trailing_start.replace("Z", "+00:00")).date()
    trailing_complete = (
        fresh and financial_complete and len(report_periods) == len(products)
        and latest_date == latest_complete_date
        and financial_period is not None and financial_period[1] == latest_complete_date
        and all(
            start <= trailing_date and end == latest_complete_date
            for start, end in report_periods
        )
    )
    observed_at = max(observed_values) if observed_values else snapshot_at
    coverage = [
        _coverage(
            loop_id=MOBILE_LOOP, source_id="app-store-connect-financial",
            projection="historical", snapshot_at=snapshot_at,
            trailing_start=trailing_start, observed_at=observed_at,
            evidence_ref=f"appstoreconnect://financial-reports/readback/{latest_date.isoformat()}",
            complete=False, reason=reason, categories=(),
        ),
        _coverage(
            loop_id=MOBILE_LOOP, source_id="app-store-connect-financial",
            projection="trailing", snapshot_at=snapshot_at,
            trailing_start=trailing_start, observed_at=observed_at,
            evidence_ref=f"appstoreconnect://financial-reports/readback/{latest_date.isoformat()}",
            complete=trailing_complete, reason=reason,
            categories=("refund", "settled_external_revenue"),
        ),
        _coverage(
            loop_id=MOBILE_LOOP, source_id="revenuecat-mrr", projection="as_of",
            snapshot_at=snapshot_at, trailing_start=trailing_start,
            observed_at=observed_at,
            evidence_ref=f"revenuecat://charts/mrr/readback/{latest_date.isoformat()}",
            complete=fresh and rc_complete and len(snapshots) == len(products),
            reason=reason, categories=("mrr",),
        ),
    ]
    return (
        sorted(receipts, key=lambda row: (row["provider"], row["receipt_id"]))
        + sorted(snapshots if rc_complete else [], key=lambda row: row["subscription_id"])
        + coverage
    )
