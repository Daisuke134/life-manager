"""Pure, fail-closed Capafy and mobile readback attribution adapters."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, DecimalException, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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


def _canonical_money_text(amount: Decimal) -> str:
    text = format(amount, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


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
        exact = _canonical_money_text(amount.copy_abs())
        normalized = _canonical_money_text(amount.copy_abs().normalize())
        if not amount.is_finite() or normalized != exact:
            raise ValueError("amount_invalid")
        return amount
    except (DecimalException, ArithmeticError, ValueError):
        raise ValueError("amount_invalid") from None


def _money(value: Any, *, allow_zero: bool = True) -> str:
    try:
        amount = _bounded_decimal(value)
        if not amount.is_finite() or amount < 0 or (not allow_zero and amount == 0):
            raise ValueError("amount_invalid")
        return _canonical_money_text(amount) if amount else "0"
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


def _mobile_financial_packet_gaps(
    *, snapshot_at: str, trailing_start: str, observed_at: str,
    reason: str, evidence_ref: str,
) -> list[dict]:
    return [
        _coverage(
            loop_id=MOBILE_LOOP, source_id="app-store-connect-financial",
            projection=projection, snapshot_at=snapshot_at,
            trailing_start=trailing_start, observed_at=observed_at,
            evidence_ref=evidence_ref, complete=False, reason=reason, categories=(),
        )
        for projection in ("historical", "trailing")
    ]


def _asc_packet_report(report: Any, *, report_type: str, region_code: str):
    if not isinstance(report, dict) or not isinstance(report.get("metadata"), dict):
        raise ValueError("missing_coverage")
    metadata = report["metadata"]
    if (
        metadata.get("reportType") != report_type
        or metadata.get("regionCode") != region_code
        or not isinstance(metadata.get("vendorNumber"), str)
        or not metadata["vendorNumber"]
        or not isinstance(metadata.get("reportDate"), str)
        or not re.fullmatch(r"\d{4}-\d{2}", metadata["reportDate"])
        or metadata.get("decompressed") is not True
    ):
        raise ValueError("missing_coverage")
    compressed_path = metadata.get("filePath")
    artifact_path = report.get("artifact_path")
    decompressed_path = metadata.get("decompressedPath")
    if not all(isinstance(path, str) and path for path in (
        compressed_path, artifact_path, decompressed_path,
    )):
        raise ValueError("missing_coverage")
    if Path(artifact_path).expanduser().resolve() != Path(decompressed_path).expanduser().resolve():
        raise ValueError("missing_coverage")
    compressed = Path(compressed_path).expanduser().read_bytes()
    raw = Path(artifact_path).expanduser().read_bytes()
    if (
        Path(compressed_path).suffix != ".gz"
        or type(metadata.get("fileSize")) is not int
        or metadata["fileSize"] != len(compressed)
        or type(metadata.get("decompressedSize")) is not int
        or metadata["decompressedSize"] != len(raw)
        or gzip.decompress(compressed) != raw
    ):
        raise ValueError("read_failed")
    expected_sha = _sha256(report.get("artifact_sha256"))
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("content_hash_invalid")
    return metadata, raw, expected_sha


def _asc_tsv_rows(raw: bytes, required_headers: tuple[str, ...], date_headers: tuple[str, ...]):
    try:
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig")), delimiter="\t")
        headers: list[str] | None = None
        rows: list[tuple[int, dict[str, str]]] = []
        for cells in reader:
            line_number = reader.line_num
            if headers is None:
                if set(required_headers).issubset(cells):
                    headers = cells
                continue
            if not any(cell.strip() for cell in cells):
                continue
            row = {
                header: cells[index].strip()
                for index, header in enumerate(headers)
                if header and index < len(cells)
            }
            parsed_dates = []
            for field in date_headers:
                try:
                    parsed_dates.append(_asc_business_date(row.get(field)))
                except ValueError:
                    parsed_dates.append(None)
            if not any(parsed_dates):
                continue  # provider preamble/footer and footer summary tables are not dated rows
            if any(value is None for value in parsed_dates):
                raise ValueError("missing_coverage")
            rows.append((line_number, row))
        if headers is None or not rows:
            raise ValueError("missing_coverage")
        return rows
    except (csv.Error, UnicodeError):
        raise ValueError("read_failed") from None


def _asc_business_date(value: Any) -> date:
    if not isinstance(value, str):
        raise ValueError("date_invalid")
    for format_string in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, format_string).date()
        except ValueError:
            pass
    raise ValueError("date_invalid") from None


def _asc_quantity(value: Any) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,25}", value):
        raise ValueError("amount_invalid")
    return int(value)


def _asc_subscription_mapping(source: Any, expected_sha: Any = None) -> dict:
    if isinstance(source, list):
        artifacts = source
    elif isinstance(source, dict) and isinstance(source.get("artifacts"), list):
        artifacts = source["artifacts"]
    elif isinstance(source, dict) and isinstance(source.get("artifact_path"), str):
        artifacts = [source]
    else:
        raise ValueError("missing_coverage")
    if not artifacts:
        raise ValueError("missing_coverage")

    mapped = {}
    seen_group_subscription_ids = set()
    seen_included_subscription_ids = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict) or not isinstance(artifact.get("artifact_path"), str):
            raise ValueError("missing_coverage")
        path = Path(artifact["artifact_path"]).expanduser()
        raw = path.read_bytes()
        relationship_sha = _sha256(artifact.get("artifact_sha256", expected_sha))
        if hashlib.sha256(raw).hexdigest() != relationship_sha:
            raise ValueError("content_hash_invalid")
        try:
            payload = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError):
            raise ValueError("read_failed") from None
        self_url = (payload.get("links") or {}).get("self") if isinstance(payload, dict) else None
        parsed = urlsplit(self_url) if isinstance(self_url, str) else None
        match = re.fullmatch(
            r"/v1/apps/([A-Za-z0-9-]+)/subscriptionGroups/?", parsed.path
        ) if parsed and parsed.scheme == "https" and parsed.netloc == "api.appstoreconnect.apple.com" else None
        if not match:
            raise ValueError("missing_coverage")
        app_id = match.group(1)
        product = next((name for name, binding in MOBILE_PRODUCT_BINDINGS.items()
                        if binding["asc_app_id"] == app_id), None)
        if product is None:
            continue
        if not isinstance(payload.get("data"), list) or not isinstance(payload.get("included"), list):
            raise ValueError("missing_coverage")
        groups: dict[str, list[int]] = {}
        for group_index, group in enumerate(payload["data"], start=1):
            if not isinstance(group, dict) or group.get("type") != "subscriptionGroups":
                continue
            group_id = group.get("id")
            subscriptions = ((group.get("relationships") or {}).get("subscriptions") or {}).get("data")
            if not isinstance(group_id, str) or not isinstance(subscriptions, list):
                continue
            for subscription in subscriptions:
                if isinstance(subscription, dict) and subscription.get("type") == "subscriptions":
                    subscription_id = subscription.get("id")
                    if isinstance(subscription_id, str):
                        if subscription_id in seen_group_subscription_ids:
                            raise ValueError("subscription_relationship_duplicate")
                        seen_group_subscription_ids.add(subscription_id)
                        groups.setdefault(subscription_id, []).append(group_index)
        included: dict[str, list[tuple[int, str]]] = {}
        for included_index, subscription in enumerate(payload["included"], start=1):
            if not isinstance(subscription, dict) or subscription.get("type") != "subscriptions":
                continue
            subscription_id = subscription.get("id")
            product_id = (subscription.get("attributes") or {}).get("productId")
            if isinstance(subscription_id, str):
                if subscription_id in seen_included_subscription_ids:
                    raise ValueError("subscription_relationship_duplicate")
                seen_included_subscription_ids.add(subscription_id)
                if isinstance(product_id, str) and product_id:
                    included.setdefault(subscription_id, []).append((included_index, product_id))
        for subscription_id, group_positions in groups.items():
            details = included.get(subscription_id, [])
            if len(group_positions) == 1 and len(details) == 1:
                if subscription_id in mapped:
                    raise ValueError("subscription_relationship_duplicate")
                included_position, product_id = details[0]
                mapped[subscription_id] = (
                    product, product_id, relationship_sha,
                    group_positions[0], included_position,
                )
    return mapped


def adapt_mobile_financial_packet(
    source: Any, *, snapshot_at: str, trailing_start: str,
) -> list[dict]:
    """Normalize one private, read-only ASC FINANCIAL + FINANCE_DETAIL evidence packet."""
    snapshot_at, trailing_start = _instant(snapshot_at), _instant(trailing_start)
    payload, load_error = _load(source)
    if load_error:
        return _mobile_financial_packet_gaps(
            snapshot_at=snapshot_at, trailing_start=trailing_start,
            observed_at=snapshot_at, reason=load_error,
            evidence_ref=f"adapter://app-store-connect-financial/{load_error}",
        )
    observed_at = snapshot_at
    evidence_ref = "adapter://app-store-connect-financial/missing_coverage"
    try:
        if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int \
                or payload["schema_version"] != 1:
            raise ValueError("missing_coverage")
        observed_at = _instant(payload.get("observed_at"))
        financial_meta, financial_raw, financial_sha = _asc_packet_report(
            payload.get("financial"), report_type="FINANCIAL", region_code="ZZ",
        )
        detail_meta, detail_raw, detail_sha = _asc_packet_report(
            payload.get("detail"), report_type="FINANCE_DETAIL", region_code="Z1",
        )
        if (
            financial_meta["vendorNumber"] != detail_meta["vendorNumber"]
            or financial_meta["reportDate"] != detail_meta["reportDate"]
        ):
            raise ValueError("missing_coverage")
        period = payload["detail"].get("period")
        if not isinstance(period, dict):
            raise ValueError("missing_coverage")
        period_start = _asc_business_date(period.get("start"))
        period_end = _asc_business_date(period.get("end"))
        financial_period = payload["financial"].get("period")
        if not isinstance(financial_period, dict) or (
            _asc_business_date(financial_period.get("start")) != period_start
            or _asc_business_date(financial_period.get("end")) != period_end
        ) or period_start > period_end:
            raise ValueError("missing_coverage")

        financial_rows = _asc_tsv_rows(financial_raw, (
            "Start Date", "End Date", "Vendor Identifier", "Quantity",
            "Extended Partner Share", "Partner Share Currency", "Sales or Return",
            "Apple Identifier", "Product Type Identifier", "Country Of Sale",
        ), ("Start Date", "End Date"))
        detail_rows = _asc_tsv_rows(detail_raw, (
            "Transaction Date", "Settlement Date", "Apple Identifier", "SKU",
            "Product Type Identifier", "Country of Sale", "Quantity",
            "Extended Partner Share", "Partner Share Currency", "Sale or Return",
        ), ("Transaction Date", "Settlement Date"))
        report_keys: dict[tuple, list[Any]] = {}
        summary_lines: dict[tuple, list[int]] = {}
        for line_number, row in financial_rows:
            start, end = _asc_business_date(row["Start Date"]), _asc_business_date(row["End Date"])
            if start != period_start or end != period_end:
                raise ValueError("missing_coverage")
            currency = _currency(row.get("Partner Share Currency"))
            key = (
                row.get("Apple Identifier"), row.get("Vendor Identifier"),
                row.get("Product Type Identifier"), row.get("Country Of Sale"),
                currency, row.get("Sales or Return"), start, end,
            )
            if not all(isinstance(value, str) and value for value in key[:4]) or key[5] not in {"S", "R"}:
                raise ValueError("missing_coverage")
            total = report_keys.setdefault(key, [0, Decimal(0)])
            total[0] += _asc_quantity(row.get("Quantity"))
            total[1] += _bounded_decimal(row.get("Extended Partner Share"), signed=True)
            summary_lines.setdefault(key, []).append(line_number)

        detail_totals: dict[tuple, list[Any]] = {}
        parsed_detail: list[tuple[tuple, int, dict, Decimal]] = []
        for line_number, row in detail_rows:
            transaction_date = _asc_business_date(row.get("Transaction Date"))
            settlement_date = _asc_business_date(row.get("Settlement Date"))
            if (
                transaction_date > settlement_date
                or transaction_date < period_start or settlement_date > period_end
            ):
                raise ValueError("missing_coverage")
            currency = _currency(row.get("Partner Share Currency"))
            key = (
                row.get("Apple Identifier"), row.get("SKU"),
                row.get("Product Type Identifier"), row.get("Country of Sale"),
                currency, row.get("Sale or Return"), period_start, period_end,
            )
            if not all(isinstance(value, str) and value for value in key[:4]) or key[5] not in {"S", "R"}:
                raise ValueError("missing_coverage")
            amount = _bounded_decimal(row.get("Extended Partner Share"), signed=True)
            total = detail_totals.setdefault(key, [0, Decimal(0)])
            total[0] += _asc_quantity(row.get("Quantity"))
            total[1] += amount
            parsed_detail.append((key, line_number, row, amount))
        if report_keys.keys() != detail_totals.keys() or any(
            report_keys[key] != detail_totals[key] for key in report_keys
        ):
            raise ValueError("missing_coverage")

        relationships = payload.get("relationships")
        if not isinstance(relationships, dict):
            raise ValueError("missing_coverage")
        mapping = _asc_subscription_mapping(
            relationships,
            relationships.get("artifact_sha256") if isinstance(relationships, dict) else None,
        )
        evidence_ref = (
            f"appstoreconnect://financial-packet/{financial_sha}/{detail_sha}"
        )
        receipts = []
        for key, line_number, row, raw_amount in parsed_detail:
            subscription_id, sku = key[0], key[1]
            relation = mapping.get(subscription_id)
            if not relation or relation[1] != sku:
                continue
            product, _, relationship_sha, group_line, included_line = relation
            transaction_date = _asc_business_date(row["Transaction Date"])
            settlement_date = _asc_business_date(row["Settlement Date"])
            sale_or_return = row["Sale or Return"]
            if sale_or_return == "S" and raw_amount > 0:
                category, revenue_class, amount = "settled_external_revenue", (
                    "one_time" if row["Product Type Identifier"] in {"1", "IA1"}
                    else "other_recurring" if row["Product Type Identifier"] in {"IA9", "IAY"}
                    else None
                ), _money(raw_amount)
                if revenue_class is None:
                    continue
            elif sale_or_return == "R" and raw_amount < 0:
                category, revenue_class, amount = "refund", None, _money(-raw_amount)
            elif raw_amount == 0:
                continue
            else:
                raise ValueError("missing_coverage")
            summary_ref = ",".join(str(index) for index in summary_lines[key])
            receipts.append(contract.validate_record({
                "schema_version": contract.SCHEMA_VERSION,
                "record_type": "receipt",
                "receipt_id": f"app-store-connect-financial:normalized:{detail_sha}:{line_number}",
                "product_loop_id": MOBILE_LOOP,
                "provider": "app-store-connect-financial",
                "currency": key[4],
                "occurred_at": f"{transaction_date.isoformat()}T00:00:00Z",
                "settled_at": f"{settlement_date.isoformat()}T00:00:00Z",
                "verification_state": "verified",
                "revenue_class": revenue_class,
                "evidence_refs": [
                    f"appstoreconnect://financial-reports/sha256/{financial_sha}#rows/{summary_ref}",
                    f"appstoreconnect://finance-detail/sha256/{detail_sha}#row/{line_number}",
                    f"appstoreconnect://subscription-relationships/sha256/{relationship_sha}#data/{group_line}",
                    f"appstoreconnect://subscription-relationships/sha256/{relationship_sha}#included/{included_line}",
                ],
                "components": [{"category": category, "amount": amount}],
            }))
        return sorted(receipts, key=lambda row: row["receipt_id"]) + _mobile_financial_packet_gaps(
            snapshot_at=snapshot_at, trailing_start=trailing_start,
            observed_at=observed_at, reason="missing_coverage", evidence_ref=evidence_ref,
        )
    except (OSError, EOFError, gzip.BadGzipFile, UnicodeError, json.JSONDecodeError,
            AttributeError, TypeError, KeyError):
        reason = "read_failed"
    except ValueError as exc:
        reason = "unsupported_currency" if str(exc) == "unsupported_currency" else "missing_coverage"
    except contract.ContractError:
        reason = "missing_coverage"
    return _mobile_financial_packet_gaps(
        snapshot_at=snapshot_at, trailing_start=trailing_start,
        observed_at=observed_at, reason=reason,
        evidence_ref=evidence_ref if evidence_ref.startswith("appstoreconnect://")
        else f"adapter://app-store-connect-financial/{reason}",
    )


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

    financial_fresh = bool(observed_values) and all(
        value == snapshot_at for value in observed_values
    )
    mrr_fresh = bool(observed_values) and all(
        contract.mobile_mrr_is_fresh(value, snapshot_at) for value in observed_values
    )
    receipts = financial_receipts if financial_complete else []
    financial_reason = "stale_readback" if not financial_fresh else "missing_coverage"
    mrr_reason = "stale_readback" if not mrr_fresh else "missing_coverage"
    trailing_date = datetime.fromisoformat(trailing_start.replace("Z", "+00:00")).date()
    trailing_complete = (
        financial_fresh and financial_complete and len(report_periods) == len(products)
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
            complete=False, reason=financial_reason, categories=(),
        ),
        _coverage(
            loop_id=MOBILE_LOOP, source_id="app-store-connect-financial",
            projection="trailing", snapshot_at=snapshot_at,
            trailing_start=trailing_start, observed_at=observed_at,
            evidence_ref=f"appstoreconnect://financial-reports/readback/{latest_date.isoformat()}",
            complete=trailing_complete, reason=financial_reason,
            categories=("refund", "settled_external_revenue"),
        ),
        _coverage(
            loop_id=MOBILE_LOOP, source_id="revenuecat-mrr", projection="as_of",
            snapshot_at=snapshot_at, trailing_start=trailing_start,
            observed_at=observed_at,
            evidence_ref=f"revenuecat://charts/mrr/readback/{latest_date.isoformat()}",
            complete=mrr_fresh and rc_complete and len(snapshots) == len(products),
            reason=mrr_reason, categories=("mrr",),
        ),
    ]
    return (
        sorted(receipts, key=lambda row: (row["provider"], row["receipt_id"]))
        + sorted(snapshots if rc_complete else [], key=lambda row: row["subscription_id"])
        + coverage
    )
