"""Pure, fail-closed Capafy and mobile readback attribution adapters."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
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


def _money(value: Any, *, allow_zero: bool = True) -> str:
    if isinstance(value, bool) or value is None:
        raise ValueError("amount_invalid")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("amount_invalid") from None
    if not amount.is_finite() or amount < 0 or (not allow_zero and amount == 0):
        raise ValueError("amount_invalid")
    return format(amount.normalize(), "f") if amount else "0"


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


def _capafy_content_sha256(payload: dict) -> str:
    keys = (
        "schema_version", "kind", "observed_at", "window_start", "window_end",
        "history_complete", "currency", "pagination", "orders",
    )
    try:
        canonical = json.dumps(
            {key: payload[key] for key in keys},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    except (KeyError, TypeError, ValueError):
        raise ValueError("content_hash_invalid") from None
    return hashlib.sha256(canonical).hexdigest()


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
        "evidence_ref", "orders",
    }
    if (
        not isinstance(payload, dict)
        or not required.issubset(payload)
        or payload.get("schema_version") != 1
        or payload.get("kind") != "capafy_order_readback_snapshot"
        or not isinstance(payload.get("orders"), list)
    ):
        return _capafy_gaps("missing_coverage", snapshot_at, trailing_start)
    try:
        pagination = payload["pagination"]
        content_sha = _sha256(payload["content_sha256"])
        if (
            not isinstance(pagination, dict)
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
            order_evidence = f"capafy://orders/{order_id}"
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
                or buyer_id == developer_id
            ):
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
                            "evidence_refs": [f"capafy://refunds/{refund_id}"],
                            "components": [{"category": "refund", "amount": refund}],
                        }))
            elif order.get("isSettled") is False and order.get("status") == "pending_payment":
                has_unverified = True
                amount = _money(order.get("amount"), allow_zero=False)
                occurred_at = _epoch_millis(order.get("createdAt"))
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
                    "evidence_refs": [order_evidence],
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


def adapt_mobile(
    source: Any,
    *,
    snapshot_at: str,
    trailing_start: str,
    products: tuple[str, ...] = MOBILE_PRODUCTS,
) -> list[dict]:
    """Convert passed ASC/RevenueCat snapshots; never performs provider I/O."""
    snapshot_at, trailing_start = _instant(snapshot_at), _instant(trailing_start)
    if len(products) != len(MOBILE_PRODUCTS) or set(products) != set(MOBILE_PRODUCTS):
        return _mobile_gaps("missing_coverage", snapshot_at, trailing_start)
    products = MOBILE_PRODUCTS
    payload, load_error = _load(source)
    if load_error:
        return _mobile_gaps(load_error, snapshot_at, trailing_start)
    if not isinstance(payload, list) or not payload:
        return _mobile_gaps("missing_coverage", snapshot_at, trailing_start)

    try:
        rows = [row for row in payload if isinstance(row, dict) and row.get("product_id") in products]
        if not rows or any(row.get("schema_version") != 1 for row in rows):
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

    receipts: list[dict] = []
    snapshots: list[dict] = []
    financial_complete = True
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
                raw_amount = Decimal(str(item.get("extended_partner_share")))
                if not raw_amount.is_finite():
                    raise ValueError("amount_invalid")
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
            receipts.extend(product_receipts)
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
    reason = "stale_readback" if not fresh else "missing_coverage"
    trailing_date = datetime.fromisoformat(trailing_start.replace("Z", "+00:00")).date()
    trailing_complete = (
        fresh and financial_complete and len(report_periods) == len(products)
        and all(start <= trailing_date and end >= latest_date for start, end in report_periods)
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
        + sorted(snapshots, key=lambda row: row["subscription_id"])
        + coverage
    )
