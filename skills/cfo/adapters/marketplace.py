"""Pure, fail-closed adapter for official generic marketplace readbacks.

The adapter consumes an already captured readback envelope.  It never imports a
provider client, opens a network connection, or infers revenue from an
aggregate.  A complete immutable receipt map is required before any receipt is
emitted; aggregate-only readbacks become B0 coverage gaps instead of zeroes.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from skills.cfo import economic_attribution as contract


READBACK_RECORD_TYPE = "marketplace_financial_readback"
DEFAULT_AGGREGATE_PLATFORM = "promptbase"
DEFAULT_AGGREGATE_PRODUCT_LOOP = "writer"
UNOWNED_PLATFORMS = {"taskmarket", "x402"}
SUPPORTED_PLATFORM = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_MINOR = 9_007_199_254_740_991
ZERO_DECIMAL_CURRENCIES = {
    "BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG",
    "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF",
}
THREE_DECIMAL_CURRENCIES = {"BHD", "JOD", "KWD", "OMR", "TND"}
OWNED_CATEGORIES = (
    contract.REVENUE,
    contract.REFUND,
    "provider_fee",
    "payment_fee",
)

READBACK_KEYS = (
    "schema_version", "record_type", "platform", "product_loop_id", "observed_at",
    "coverage", "pagination", "receipt_map", "aggregate", "content_sha256",
    "evidence_ref",
)
COVERAGE_KEYS = ("historical", "trailing")
COVERAGE_WINDOW_KEYS = ("complete", "window_start", "window_end")
PAGINATION_KEYS = ("complete", "pages_fetched", "records_fetched", "next_cursor")
RECEIPT_MAP_KEYS = ("complete", "records")
PAYMENT_KEYS = (
    "schema_version", "record_type", "platform", "work_external_id",
    "payment_external_id", "receipt_id", "gross_amount_minor", "fee_amount_minor",
    "cost_amount_minor", "net_amount_minor", "currency", "status", "occurred_at",
    "observed_at",
)
FEE_KEYS = (
    "schema_version", "record_type", "platform", "payment_external_id", "receipt_id",
    "fee_type", "amount_minor", "currency", "occurred_at", "settled_at", "observed_at",
)
REFUND_KEYS = (
    "schema_version", "record_type", "platform", "payment_external_id", "receipt_id",
    "refund_amount_minor", "currency", "status", "occurred_at", "observed_at",
)
PAYOUT_KEYS = (
    "schema_version", "record_type", "platform", "payment_external_id",
    "payout_external_id", "bank_transaction_external_id", "status", "amount_minor",
    "currency", "observed_at",
)
PENDING_KEYS = (
    "schema_version", "record_type", "platform", "payment_external_id", "receipt_id",
    "amount_minor", "currency", "occurred_at", "observed_at",
)
MOVEMENT_KEYS = (
    "schema_version", "record_type", "platform", "movement_external_id", "category",
    "amount_minor", "currency", "occurred_at", "settled_at", "observed_at",
)
RECEIPT_MONEY_KEYS = (
    "gross_amount_minor", "fee_amount_minor", "cost_amount_minor", "net_amount_minor",
    "amount_minor", "refund_amount_minor",
)
ENVELOPE_AGGREGATE_KEYS = ("currency", "sales_count", "net_amount_minor")
PROMPTBASE_AGGREGATE_KEYS = ("observed_at", "source", "sales_count", "net_usd", "by_item")
EVIDENCE_TRANSIENT_KEYS = frozenset({
    "observed_at", "window_end", "content_sha256", "evidence_ref",
    "pages_fetched", "records_fetched", "next_cursor",
})
SOURCE_ROW_TRANSIENT_PATHS = frozenset({("observed_at",)})
PROMPTBASE_TRANSIENT_PATHS = frozenset({("observed_at",)})
FALLBACK_TRANSIENT_PATHS = frozenset({
    ("observed_at",),
    ("content_sha256",),
    ("evidence_ref",),
    ("coverage", "historical", "window_end"),
    ("coverage", "trailing", "window_end"),
    ("pagination", "pages_fetched"),
    ("pagination", "records_fetched"),
    ("pagination", "next_cursor"),
})


class MarketplaceAttributionError(ValueError):
    """Payload error that contains no provider payload data."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _fail(code: str) -> None:
    raise MarketplaceAttributionError(code)


def _schema_version(value: object, *, error: str = "unverified_receipt") -> None:
    if type(value) is not int or value != 1:
        _fail(error)


def _exact_keys(value: object, expected: tuple[str, ...]) -> None:
    if not isinstance(value, dict):
        _fail("read_failed")
    required = set(expected)
    keys = set(value)
    missing = required - keys
    extra = keys - required
    if missing or extra:
        _fail("unverified_receipt")


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not contract.IDENTITY.fullmatch(value):
        _fail("unverified_receipt")
    return value


def _platform(value: object) -> str:
    if not isinstance(value, str) or not SUPPORTED_PLATFORM.fullmatch(value):
        _fail("unverified_receipt")
    return value


def _product_loop(value: object) -> str:
    if value not in contract.PRODUCT_LOOP_IDS:
        _fail("unverified_receipt")
    return value


def _instant(value: object) -> str:
    if not isinstance(value, str) or not contract.RFC3339.fullmatch(value):
        _fail("read_failed")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail("read_failed")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("read_failed")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _minor(value: object, *, positive: bool = False) -> int:
    if type(value) is not int or value < 0 or value > MAX_MINOR or (positive and value == 0):
        _fail("unverified_receipt")
    return value


def _currency(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{3}", value):
        _fail("unsupported_currency")
    if value in {"UNK", "XXX"}:
        _fail("unsupported_currency")
    return value


def _amount(minor: int, currency: str) -> str:
    exponent = (
        0 if currency in ZERO_DECIMAL_CURRENCIES
        else 3 if currency in THREE_DECIMAL_CURRENCIES
        else 2
    )
    value = Decimal(minor) / (Decimal(10) ** exponent)
    amount = format(value.normalize(), "f")
    if not contract.AMOUNT.fullmatch(amount) or amount == "0":
        _fail("unverified_receipt")
    return amount


def _validate_json_value(value: object, active: set[int]) -> None:
    value_type = type(value)
    if value_type in {type(None), bool, int, str}:
        return
    if value_type is float:
        if not math.isfinite(value):
            raise ValueError("canonical_non_finite")
        return
    if value_type is dict:
        identity = id(value)
        if identity in active:
            raise ValueError("canonical_cycle")
        active.add(identity)
        try:
            for key, item in value.items():
                if type(key) is not str:
                    raise TypeError("canonical_key_type")
                _validate_json_value(item, active)
        finally:
            active.remove(identity)
        return
    if value_type is list:
        identity = id(value)
        if identity in active:
            raise ValueError("canonical_cycle")
        active.add(identity)
        try:
            for item in value:
                _validate_json_value(item, active)
        finally:
            active.remove(identity)
        return
    raise TypeError("canonical_json_type")


def _canonical(value: object) -> str:
    _validate_json_value(value, set())
    serialized = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


def _canonical_exact(value: object) -> tuple:
    if isinstance(value, dict):
        return (
            "dict",
            tuple(sorted(
                (key, _canonical_exact(item))
                for key, item in value.items()
            )),
        )
    if isinstance(value, list):
        return ("list", tuple(_canonical_exact(item) for item in value))
    return (type(value).__name__, value)


def _immutable_source_facts(
    value: object,
    *,
    transient_paths: frozenset[tuple[str, ...]] = frozenset(),
    path: tuple[str, ...] = (),
    active: set[int] | None = None,
) -> object:
    if active is None:
        active = set()
    if type(value) is dict:
        identity = id(value)
        if identity in active:
            raise ValueError("evidence_cycle")
        active.add(identity)
        try:
            return {
                key: _immutable_source_facts(
                    item,
                    transient_paths=transient_paths,
                    path=(*path, key),
                    active=active,
                )
                for key, item in value.items()
                if not (
                    type(key) is str
                    and (*path, key) in transient_paths
                    and key in EVIDENCE_TRANSIENT_KEYS
                )
            }
        finally:
            active.remove(identity)
    if type(value) is list:
        identity = id(value)
        if identity in active:
            raise ValueError("evidence_cycle")
        active.add(identity)
        try:
            return [
                _immutable_source_facts(
                    item,
                    transient_paths=transient_paths,
                    path=(*path, str(index)),
                    active=active,
                )
                for index, item in enumerate(value)
            ]
        finally:
            active.remove(identity)
    return value


def _source_row_evidence(row: dict, platform: str) -> str:
    digest = _canonical(_immutable_source_facts(
        row, transient_paths=SOURCE_ROW_TRANSIENT_PATHS,
    ))
    return f"marketplace://{platform}/financial-readback/source-row/sha256/{digest}"


def _receipt_map_source_facts(rows: list[dict]) -> list[object]:
    facts = [
        _immutable_source_facts(row, transient_paths=SOURCE_ROW_TRANSIENT_PATHS)
        for row in rows
    ]
    return sorted(
        facts,
        key=lambda item: json.dumps(
            item, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ),
    )


def _source_facts_evidence(payload: dict, platform: str, rows: list[dict]) -> str:
    facts = {
        "platform": platform,
        "product_loop_id": payload.get("product_loop_id"),
        "aggregate": _immutable_source_facts(payload.get("aggregate")),
        "records": _receipt_map_source_facts(rows),
    }
    digest = _canonical(facts)
    return f"marketplace://{platform}/financial-readback/source-facts/sha256/{digest}"


def _validate_payload_integrity(payload: dict, platform: str) -> None:
    digest = payload.get("content_sha256")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        _fail("unverified_receipt")
    unsigned = {
        key: value for key, value in payload.items()
        if key not in {"content_sha256", "evidence_ref"}
    }
    if _canonical(unsigned) != digest:
        _fail("unverified_receipt")
    expected = f"marketplace://{platform}/financial-readback/sha256/{digest}"
    if payload.get("evidence_ref") != expected:
        _fail("unverified_receipt")


def _aggregate_evidence(payload: dict) -> str:
    digest = _canonical(_immutable_source_facts(
        payload, transient_paths=PROMPTBASE_TRANSIENT_PATHS,
    ))
    return f"marketplace://promptbase/aggregate-readback/sha256/{digest}"


def _record_type(row: dict) -> str:
    value = row.get("record_type")
    if value not in {
        "payment_receipt", "fee_receipt", "refund_receipt", "payout_match_receipt",
        "pending_payment_receipt", "movement_receipt",
    }:
        _fail("unverified_receipt")
    return value


def _row_identity(row: dict) -> tuple[str, str] | None:
    kind = row.get("record_type")
    field = {
        "payment_receipt": "payment_external_id",
        "fee_receipt": "receipt_id",
        "refund_receipt": "receipt_id",
        "payout_match_receipt": "payout_external_id",
        "pending_payment_receipt": "payment_external_id",
        "movement_receipt": "movement_external_id",
    }.get(kind)
    if field is None or not isinstance(row.get(field), str):
        return None
    return kind, row[field]


def _deduplicate_source_rows(
    rows: list[object],
    *,
    platform: str,
    product_loop_id: str,
    observed_at: str,
) -> list[dict]:
    indexed: dict[tuple[str, str], tuple[tuple, dict]] = {}
    ordered: list[dict] = []
    for raw in rows:
        if not isinstance(raw, dict):
            _fail("unverified_receipt")
        _validate_source_row(
            raw,
            platform=platform,
            product_loop_id=product_loop_id,
            observed_at=observed_at,
        )
        identity = _row_identity(raw)
        if identity is None:
            _fail("unverified_receipt")
        previous = indexed.get(identity)
        if previous is not None:
            if previous[0] != _canonical_exact(raw):
                _fail("unverified_receipt")
            continue
        indexed[identity] = (_canonical_exact(raw), raw)
        ordered.append(raw)
    return ordered


def _observed(row: dict, readback_observed: str) -> None:
    if _instant(row.get("observed_at")) != readback_observed:
        _fail("stale_readback")


def _check_platform(row: dict, platform: str) -> None:
    if _platform(row.get("platform")) != platform:
        _fail("unverified_receipt")


def _receipt(
    *,
    receipt_id: str,
    product_loop_id: str,
    provider: str,
    currency: str,
    occurred_at: str,
    settled_at: str | None,
    verification_state: str,
    revenue_class: str | None,
    components: list[dict],
    evidence: str,
) -> dict:
    return contract.validate_record({
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "receipt",
        "receipt_id": receipt_id,
        "product_loop_id": product_loop_id,
        "provider": provider,
        "currency": currency,
        "occurred_at": occurred_at,
        "settled_at": settled_at,
        "verification_state": verification_state,
        "revenue_class": revenue_class,
        "evidence_refs": [evidence],
        "components": components,
    })


def _payment(
    row: dict,
    *,
    platform: str,
    product_loop_id: str,
    observed_at: str,
    evidence: str,
) -> dict:
    _exact_keys(row, PAYMENT_KEYS)
    _schema_version(row["schema_version"])
    if row["record_type"] != "payment_receipt":
        _fail("unverified_receipt")
    _check_platform(row, platform)
    _identifier(row["work_external_id"])
    payment_external_id = _identifier(row["payment_external_id"])
    receipt_external_id = _identifier(row["receipt_id"])
    if row["status"] != "settled":
        _fail("unverified_receipt")
    _observed(row, observed_at)
    currency = _currency(row["currency"])
    occurred_at = _instant(row["occurred_at"])
    if occurred_at > observed_at:
        _fail("unverified_receipt")
    gross = _minor(row["gross_amount_minor"], positive=True)
    fee = _minor(row["fee_amount_minor"])
    cost = _minor(row["cost_amount_minor"])
    # A settled receipt with no positive net is not an expansion candidate. Keep
    # the source visible as an unverified gap instead of allowing zero-margin
    # work into the revenue projection.
    net = _minor(row["net_amount_minor"], positive=True)
    if gross - fee - cost != net:
        _fail("unverified_receipt")
    # B6 owns generic actual-cost attribution. Do not silently turn a producer
    # cost into revenue or a marketplace fee when this adapter cannot classify it.
    if cost:
        _fail("unverified_receipt")
    components = [{
        "category": contract.REVENUE,
        "amount": _amount(gross, currency),
    }]
    if fee:
        components.append({"category": "provider_fee", "amount": _amount(fee, currency)})
    return {
        "kind": "payment",
        "payment_external_id": payment_external_id,
        "receipt_external_id": receipt_external_id,
        "source_identity": ("payment", payment_external_id, receipt_external_id),
        "currency": currency,
        "occurred_at": occurred_at,
        "gross": gross,
        "fee": fee,
        "net": net,
        "receipt": _receipt(
            receipt_id=f"marketplace:{platform}:payment:{receipt_external_id}",
            product_loop_id=product_loop_id,
            provider=f"marketplace-{platform}",
            currency=currency,
            occurred_at=occurred_at,
            settled_at=occurred_at,
            verification_state="verified",
            revenue_class="one_time",
            components=components,
            evidence=evidence,
        ),
    }


def _fee(
    row: dict,
    *,
    platform: str,
    product_loop_id: str,
    observed_at: str,
    evidence: str,
) -> dict:
    _exact_keys(row, FEE_KEYS)
    _schema_version(row["schema_version"])
    if row["record_type"] != "fee_receipt":
        _fail("unverified_receipt")
    _check_platform(row, platform)
    payment_external_id = _identifier(row["payment_external_id"])
    receipt_external_id = _identifier(row["receipt_id"])
    if row["fee_type"] not in {"provider_fee", "payment_fee"}:
        _fail("unverified_receipt")
    _observed(row, observed_at)
    currency = _currency(row["currency"])
    occurred_at = _instant(row["occurred_at"])
    settled_at = _instant(row["settled_at"])
    amount = _minor(row["amount_minor"], positive=True)
    if settled_at < occurred_at:
        _fail("unverified_receipt")
    return {
        "kind": "fee",
        "payment_external_id": payment_external_id,
        "receipt_external_id": receipt_external_id,
        "source_identity": ("fee", payment_external_id, receipt_external_id),
        "currency": currency,
        "amount": amount,
        "fee_type": row["fee_type"],
        "occurred_at": occurred_at,
        "settled_at": settled_at,
        "receipt": _receipt(
            receipt_id=f"marketplace:{platform}:fee:{receipt_external_id}",
            product_loop_id=product_loop_id,
            provider=f"marketplace-{platform}",
            currency=currency,
            occurred_at=occurred_at,
            settled_at=settled_at,
            verification_state="verified",
            revenue_class=None,
            components=[{"category": row["fee_type"], "amount": _amount(amount, currency)}],
            evidence=evidence,
        ),
    }


def _refund(
    row: dict,
    *,
    platform: str,
    product_loop_id: str,
    observed_at: str,
    evidence: str,
) -> dict:
    _exact_keys(row, REFUND_KEYS)
    _schema_version(row["schema_version"])
    if row["record_type"] != "refund_receipt":
        _fail("unverified_receipt")
    _check_platform(row, platform)
    payment_external_id = _identifier(row["payment_external_id"])
    receipt_external_id = _identifier(row["receipt_id"])
    if row["status"] != "settled":
        _fail("unverified_receipt")
    _observed(row, observed_at)
    currency = _currency(row["currency"])
    occurred_at = _instant(row["occurred_at"])
    amount = _minor(row["refund_amount_minor"], positive=True)
    return {
        "kind": "refund",
        "payment_external_id": payment_external_id,
        "receipt_external_id": receipt_external_id,
        "source_identity": ("refund", payment_external_id, receipt_external_id),
        "currency": currency,
        "amount": amount,
        "occurred_at": occurred_at,
        "settled_at": occurred_at,
        "receipt": _receipt(
            receipt_id=f"marketplace:{platform}:refund:{receipt_external_id}",
            product_loop_id=product_loop_id,
            provider=f"marketplace-{platform}",
            currency=currency,
            occurred_at=occurred_at,
            settled_at=occurred_at,
            verification_state="verified",
            revenue_class=None,
            components=[{"category": contract.REFUND, "amount": _amount(amount, currency)}],
            evidence=evidence,
        ),
    }


def _payout(
    row: dict,
    *,
    platform: str,
    product_loop_id: str,
    observed_at: str,
    evidence: str,
) -> dict:
    _exact_keys(row, PAYOUT_KEYS)
    _schema_version(row["schema_version"])
    if row["record_type"] != "payout_match_receipt":
        _fail("unverified_receipt")
    _check_platform(row, platform)
    payment_external_id = _identifier(row["payment_external_id"])
    payout_external_id = _identifier(row["payout_external_id"])
    _identifier(row["bank_transaction_external_id"])
    if row["status"] != "matched":
        _fail("unverified_receipt")
    _observed(row, observed_at)
    currency = _currency(row["currency"])
    amount = _minor(row["amount_minor"], positive=True)
    return {
        "kind": "payout",
        "payment_external_id": payment_external_id,
        "payout_external_id": payout_external_id,
        "source_identity": ("payout", payment_external_id, payout_external_id),
        "currency": currency,
        "amount": amount,
        "evidence": evidence,
    }


def _pending(
    row: dict,
    *,
    platform: str,
    product_loop_id: str,
    observed_at: str,
    evidence: str,
) -> dict:
    _exact_keys(row, PENDING_KEYS)
    _schema_version(row["schema_version"])
    if row["record_type"] != "pending_payment_receipt":
        _fail("unverified_receipt")
    _check_platform(row, platform)
    _identifier(row["payment_external_id"])
    receipt_external_id = _identifier(row["receipt_id"])
    _observed(row, observed_at)
    currency = _currency(row["currency"])
    occurred_at = _instant(row["occurred_at"])
    amount = _minor(row["amount_minor"], positive=True)
    if occurred_at > observed_at:
        _fail("unverified_receipt")
    return {
        "kind": "pending",
        "payment_external_id": row["payment_external_id"],
        "receipt_external_id": receipt_external_id,
        "source_identity": ("pending", row["payment_external_id"], receipt_external_id),
        "receipt": _receipt(
            receipt_id=f"marketplace:{platform}:pending:{receipt_external_id}",
            product_loop_id=product_loop_id,
            provider=f"marketplace-{platform}",
            currency=currency,
            occurred_at=occurred_at,
            settled_at=None,
            verification_state="pending",
            revenue_class="one_time",
            components=[{"category": "pending_revenue", "amount": _amount(amount, currency)}],
            evidence=evidence,
        ),
    }


def _movement(
    row: dict,
    *,
    platform: str,
    product_loop_id: str,
    observed_at: str,
    evidence: str,
) -> dict:
    _exact_keys(row, MOVEMENT_KEYS)
    _schema_version(row["schema_version"])
    if row["record_type"] != "movement_receipt":
        _fail("unverified_receipt")
    _check_platform(row, platform)
    movement_external_id = _identifier(row["movement_external_id"])
    category = row["category"]
    if category not in {"payout", "owner_deposit", "self_payment", "internal_transfer"}:
        _fail("unverified_receipt")
    _observed(row, observed_at)
    currency = _currency(row["currency"])
    occurred_at = _instant(row["occurred_at"])
    settled_at = _instant(row["settled_at"])
    amount = _minor(row["amount_minor"], positive=True)
    if not occurred_at <= settled_at <= observed_at:
        _fail("unverified_receipt")
    return {
        "kind": "movement",
        "movement_external_id": movement_external_id,
        "source_identity": ("movement", movement_external_id),
        "receipt": _receipt(
            receipt_id=f"marketplace:{platform}:movement:{movement_external_id}",
            product_loop_id=product_loop_id,
            provider=f"marketplace-{platform}",
            currency=currency,
            occurred_at=occurred_at,
            settled_at=settled_at,
            verification_state="verified",
            revenue_class=None,
            components=[{"category": category, "amount": _amount(amount, currency)}],
            evidence=evidence,
        ),
    }


def _validate_source_row(
    row: dict,
    *,
    platform: str,
    product_loop_id: str,
    observed_at: str,
) -> None:
    kind = _record_type(row)
    {
        "payment_receipt": _payment,
        "fee_receipt": _fee,
        "refund_receipt": _refund,
        "payout_match_receipt": _payout,
        "pending_payment_receipt": _pending,
        "movement_receipt": _movement,
    }[kind](
        row,
        platform=platform,
        product_loop_id=product_loop_id,
        observed_at=observed_at,
        evidence=_source_row_evidence(row, platform),
    )


def _append_receipt(
    receipts: list[dict],
    output_identities: dict[tuple[str, str], tuple[str, ...]],
    converted: dict,
) -> None:
    receipt = converted.get("receipt")
    source_identity = converted.get("source_identity")
    if not isinstance(receipt, dict) or not isinstance(source_identity, tuple):
        _fail("unverified_receipt")
    provider = receipt.get("provider")
    receipt_id = receipt.get("receipt_id")
    if (not isinstance(provider, str) or not isinstance(receipt_id, str)
            or not provider.startswith("marketplace-")
            or not receipt_id.startswith(
                f"marketplace:{provider.removeprefix('marketplace-')}:"
            )):
        _fail("unverified_receipt")
    output_identity = (provider, receipt_id)
    if output_identity in output_identities:
        _fail("unverified_receipt")
    output_identities[output_identity] = source_identity
    receipts.append(receipt)


def _validate_linked_window(
    payment: dict,
    *,
    occurred_at: str,
    settled_at: str,
    observed_at: str,
) -> None:
    payment_occurred_at = payment["occurred_at"]
    if not (
        payment_occurred_at <= occurred_at <= settled_at <= observed_at
    ):
        _fail("unverified_receipt")


def _payout_receipt(
    payout: dict,
    payment: dict,
    *,
    platform: str,
    product_loop_id: str,
    evidence: str,
) -> dict:
    occurred_at = payment["occurred_at"]
    return _receipt(
        receipt_id=f"marketplace:{platform}:payout:{payout['payout_external_id']}",
        product_loop_id=product_loop_id,
        provider=f"marketplace-{platform}",
        currency=payout["currency"],
        # payout_match_receipt has no settlement timestamp.  The linked
        # settled payment occurrence is stable across later readbacks.
        occurred_at=occurred_at,
        settled_at=occurred_at,
        verification_state="verified",
        revenue_class=None,
        components=[{
            "category": "payout",
            "amount": _amount(payout["amount"], payout["currency"]),
        }],
        evidence=evidence,
    )


def _validate_envelope_aggregate(aggregate: object, metrics: dict) -> None:
    _exact_keys(aggregate, ENVELOPE_AGGREGATE_KEYS)
    currency = _currency(aggregate["currency"])
    if type(aggregate["sales_count"]) is not int or aggregate["sales_count"] < 0:
        _fail("unverified_receipt")
    declared_net = _minor(aggregate["net_amount_minor"])
    expected_net = (
        metrics["gross_amount_minor"]
        - metrics["embedded_provider_fee_minor"]
        - metrics["itemized_fee_minor"]
        - metrics["refund_minor"]
    )
    if (
        aggregate["sales_count"] != metrics["settled_payment_count"]
        or expected_net < 0
        or expected_net > MAX_MINOR
        or declared_net != expected_net
    ):
        _fail("unverified_receipt")
    settlement_currencies = metrics["settlement_currencies"]
    if settlement_currencies:
        if settlement_currencies != {currency}:
            _fail("unverified_receipt")
        return
    if (
        aggregate["sales_count"] != 0
        or expected_net != 0
        or declared_net != 0
        or metrics["settled_payment_count"] != 0
        or metrics["receipt_derived_money_minor"] != 0
        or any(
            metrics[name] != 0
            for name in (
                "gross_amount_minor",
                "embedded_provider_fee_minor",
                "itemized_fee_minor",
                "refund_minor",
            )
        )
    ):
        _fail("unverified_receipt")


def _convert_receipt_map(
    rows: list[object],
    *,
    platform: str,
    product_loop_id: str,
    observed_at: str,
) -> dict:
    payments: dict[str, dict] = {}
    fees: list[dict] = []
    refunds: list[dict] = []
    payouts: list[dict] = []
    receipts: list[dict] = []
    output_identities: dict[tuple[str, str], tuple[str, ...]] = {}
    receipt_derived_money_minor = 0
    source_rows = _deduplicate_source_rows(
        rows,
        platform=platform,
        product_loop_id=product_loop_id,
        observed_at=observed_at,
    )
    for row in source_rows:
        receipt_derived_money_minor += sum(
            row[field]
            for field in RECEIPT_MONEY_KEYS
            if type(row.get(field)) is int
        )
        kind = _record_type(row)
        converted = {
            "payment_receipt": _payment,
            "fee_receipt": _fee,
            "refund_receipt": _refund,
            "payout_match_receipt": _payout,
            "pending_payment_receipt": _pending,
            "movement_receipt": _movement,
        }[kind](
            row,
            platform=platform,
            product_loop_id=product_loop_id,
            observed_at=observed_at,
            evidence=_source_row_evidence(row, platform),
        )
        if converted["kind"] == "payment":
            payments[converted["payment_external_id"]] = converted
        elif converted["kind"] == "fee":
            fees.append(converted)
        elif converted["kind"] == "refund":
            refunds.append(converted)
        elif converted["kind"] == "payout":
            payouts.append(converted)
        else:
            _append_receipt(receipts, output_identities, converted)

    itemized_fee_minor = 0
    for fee in fees:
        payment = payments.get(fee["payment_external_id"])
        if payment is None or payment["currency"] != fee["currency"]:
            _fail("unverified_receipt")
        _validate_linked_window(
            payment,
            occurred_at=fee["occurred_at"],
            settled_at=fee["settled_at"],
            observed_at=observed_at,
        )
        if fee["fee_type"] == "provider_fee":
            if payment["fee"]:
                # Embedded and itemized provider fees are ambiguous: recording
                # both would make the same fee count twice.
                _fail("unverified_receipt")
        itemized_fee_minor += fee["amount"]
        _append_receipt(receipts, output_identities, fee)

    refunds_by_payment: dict[str, int] = {}
    refund_minor = 0
    for refund in refunds:
        payment = payments.get(refund["payment_external_id"])
        if payment is None or payment["currency"] != refund["currency"]:
            _fail("unverified_receipt")
        _validate_linked_window(
            payment,
            occurred_at=refund["occurred_at"],
            settled_at=refund["settled_at"],
            observed_at=observed_at,
        )
        total = refunds_by_payment.get(refund["payment_external_id"], 0) + refund["amount"]
        if total > payment["gross"]:
            _fail("unverified_receipt")
        refunds_by_payment[refund["payment_external_id"]] = total
        refund_minor += refund["amount"]
        _append_receipt(receipts, output_identities, refund)

    payouts_by_payment: dict[str, int] = {}
    for payout in payouts:
        payment = payments.get(payout["payment_external_id"])
        if payment is None or payment["currency"] != payout["currency"]:
            _fail("unverified_receipt")
        total = payouts_by_payment.get(payout["payment_external_id"], 0) + payout["amount"]
        if total > payment["net"] or payout["amount"] != payment["net"]:
            _fail("unverified_receipt")
        payouts_by_payment[payout["payment_external_id"]] = total
        payout["receipt"] = _payout_receipt(
            payout,
            payment,
            platform=platform,
            product_loop_id=product_loop_id,
            evidence=payout["evidence"],
        )
        _append_receipt(receipts, output_identities, payout)

    for payment in payments.values():
        _append_receipt(receipts, output_identities, payment)
    return {
        "receipts": sorted(receipts, key=lambda row: row["receipt_id"]),
        "source_rows": source_rows,
        "metrics": {
            "settled_payment_count": len(payments),
            "gross_amount_minor": sum(payment["gross"] for payment in payments.values()),
            "embedded_provider_fee_minor": sum(payment["fee"] for payment in payments.values()),
            "itemized_fee_minor": itemized_fee_minor,
            "refund_minor": refund_minor,
            "settlement_currencies": {
                payment["currency"] for payment in payments.values()
            } | {fee["currency"] for fee in fees}
              | {refund["currency"] for refund in refunds},
            "receipt_derived_money_minor": receipt_derived_money_minor,
        },
    }


def _context(
    payload: dict,
    *,
    product_loop_id: str | None,
    platform: str | None,
) -> dict:
    raw_platform = payload.get("platform", platform)
    if platform is not None and payload.get("platform") not in (None, platform):
        _fail("unverified_receipt")
    raw_product_loop = payload.get("product_loop_id", product_loop_id)
    if product_loop_id is not None and payload.get("product_loop_id") not in (None, product_loop_id):
        _fail("unverified_receipt")
    actual_platform = _platform(raw_platform)
    actual_product_loop = _product_loop(raw_product_loop)
    return {
        "platform": actual_platform,
        "product_loop_id": actual_product_loop,
        "provider": f"marketplace-{actual_platform}",
        "source_id": f"marketplace-{actual_platform}-financial-record",
    }


def _fallback_context(
    payload: object,
    *,
    product_loop_id: str | None,
    platform: str | None,
) -> dict | None:
    if not isinstance(payload, dict):
        return None
    try:
        raw_platform = payload.get("platform", platform)
        if raw_platform is None and payload.get("source", "").startswith("https://promptbase.com/"):
            raw_platform = DEFAULT_AGGREGATE_PLATFORM
        raw_product = payload.get("product_loop_id", product_loop_id)
        if raw_product is None and raw_platform == DEFAULT_AGGREGATE_PLATFORM:
            raw_product = DEFAULT_AGGREGATE_PRODUCT_LOOP
        actual_platform = _platform(raw_platform)
        actual_product = _product_loop(raw_product)
    except MarketplaceAttributionError:
        return None
    return {
        "platform": actual_platform,
        "product_loop_id": actual_product,
        "provider": f"marketplace-{actual_platform}",
        "source_id": f"marketplace-{actual_platform}-financial-record",
    }


def _fallback_evidence(payload: object, platform: str) -> str:
    try:
        facts = _immutable_source_facts(
            payload, transient_paths=FALLBACK_TRANSIENT_PATHS,
        )
        if type(facts) is dict:
            receipt_map = facts.get("receipt_map")
            if type(receipt_map) is dict and type(receipt_map.get("records")) is list:
                receipt_map["records"] = [
                    _immutable_source_facts(
                        row, transient_paths=SOURCE_ROW_TRANSIENT_PATHS,
                    )
                    for row in receipt_map["records"]
                ]
        digest = _canonical(facts)
    except (TypeError, ValueError, RecursionError):
        digest = hashlib.sha256(b"marketplace-invalid-readback").hexdigest()
    return f"marketplace://{platform}/validation/sha256/{digest}"


def _coverage(
    *,
    context: dict,
    projection: str,
    window_start: str | None,
    window_end: str,
    observed_at: str,
    state: str,
    reason: str | None,
    categories: list[str],
    evidence: str,
) -> dict:
    return contract.validate_record({
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "coverage",
        "product_loop_id": context["product_loop_id"],
        "source_id": context["source_id"],
        "projection": projection,
        "window_start": window_start,
        "window_end": window_end,
        "coverage_state": state,
        "reason": reason,
        "covered_categories": categories,
        "observed_at": observed_at,
        "evidence_refs": [evidence],
    })


def _coverage_rows(
    *,
    context: dict,
    snapshot_at: str,
    trailing_start: str,
    evidence: str,
    historical_reason: str | None,
    trailing_reason: str | None,
    categories: list[str],
) -> list[dict]:
    rows = [
        _coverage(
            context=context,
            projection="historical",
            window_start=None,
            window_end=snapshot_at,
            observed_at=snapshot_at,
            state="complete" if historical_reason is None else "gap",
            reason=historical_reason,
            categories=categories if historical_reason is None else [],
            evidence=evidence,
        ),
        _coverage(
            context=context,
            projection="trailing",
            window_start=trailing_start,
            window_end=snapshot_at,
            observed_at=snapshot_at,
            state="complete" if trailing_reason is None else "gap",
            reason=trailing_reason,
            categories=categories if trailing_reason is None else [],
            evidence=evidence,
        ),
        _coverage(
            context=context,
            projection="as_of",
            window_start=None,
            window_end=snapshot_at,
            observed_at=snapshot_at,
            state="gap",
            reason="missing_category",
            categories=[],
            evidence=evidence,
        ),
    ]
    return rows


def _aggregate_only(
    payload: dict,
    *,
    snapshot_at: str,
    trailing_start: str,
    product_loop_id: str | None,
    platform: str | None,
) -> list[dict]:
    _exact_keys(payload, PROMPTBASE_AGGREGATE_KEYS)
    context = _context(
        {"platform": platform or DEFAULT_AGGREGATE_PLATFORM,
         "product_loop_id": product_loop_id or DEFAULT_AGGREGATE_PRODUCT_LOOP},
        product_loop_id=product_loop_id,
        platform=platform,
    )
    observed_at = _instant(payload["observed_at"])
    if observed_at != snapshot_at:
        reason = "stale_readback"
    else:
        source = payload["source"]
        if not isinstance(source, str) or not source.startswith("https://promptbase.com/"):
            _fail("read_failed")
        if type(payload["sales_count"]) is not int or payload["sales_count"] < 0:
            _fail("read_failed")
        if (isinstance(payload["net_usd"], bool)
                or not isinstance(payload["net_usd"], (int, float))
                or not math.isfinite(payload["net_usd"])
                or payload["net_usd"] < 0
                or not isinstance(payload["by_item"], dict)):
            _fail("read_failed")
        reason = "missing_coverage"
    evidence = _aggregate_evidence(payload)
    return _coverage_rows(
        context=context,
        snapshot_at=snapshot_at,
        trailing_start=trailing_start,
        evidence=evidence,
        historical_reason=reason,
        trailing_reason=reason,
        categories=[],
    )


def _envelope(
    payload: dict,
    *,
    snapshot_at: str,
    trailing_start: str,
    product_loop_id: str | None,
    platform: str | None,
) -> list[dict]:
    _exact_keys(payload, READBACK_KEYS)
    _schema_version(payload["schema_version"], error="read_failed")
    if payload["record_type"] != READBACK_RECORD_TYPE:
        _fail("read_failed")
    context = _context(payload, product_loop_id=product_loop_id, platform=platform)
    if context["platform"] in UNOWNED_PLATFORMS:
        _fail("missing_coverage")
    _validate_payload_integrity(payload, context["platform"])
    observed_at = _instant(payload["observed_at"])
    if observed_at != snapshot_at:
        _fail("stale_readback")
    _exact_keys(payload["coverage"], COVERAGE_KEYS)
    coverage_windows = {}
    for projection in COVERAGE_KEYS:
        window = payload["coverage"][projection]
        _exact_keys(window, COVERAGE_WINDOW_KEYS)
        if type(window["complete"]) is not bool:
            _fail("read_failed")
        window_end = _instant(window["window_end"])
        if window_end != snapshot_at:
            _fail("stale_readback")
        window_start = None if window["window_start"] is None else _instant(window["window_start"])
        if projection == "historical" and window_start is not None:
            _fail("read_failed")
        if projection == "trailing":
            if window_start != trailing_start or window_start >= window_end:
                _fail("stale_readback")
        coverage_windows[projection] = window["complete"]

    pagination = payload["pagination"]
    _exact_keys(pagination, PAGINATION_KEYS)
    if (pagination["complete"] is not True
            or type(pagination["pages_fetched"]) is not int
            or pagination["pages_fetched"] < 1
            or type(pagination["records_fetched"]) is not int
            or pagination["records_fetched"] < 0
            or pagination["next_cursor"] is not None):
        _fail("missing_coverage")
    receipt_map = payload["receipt_map"]
    if receipt_map is None:
        _fail("missing_coverage")
    _exact_keys(receipt_map, RECEIPT_MAP_KEYS)
    if receipt_map["complete"] is not True or not isinstance(receipt_map["records"], list):
        _fail("missing_coverage")
    if pagination["records_fetched"] != len(receipt_map["records"]):
        _fail("missing_coverage")
    converted = _convert_receipt_map(
        receipt_map["records"],
        platform=context["platform"],
        product_loop_id=context["product_loop_id"],
        observed_at=observed_at,
    )
    _validate_envelope_aggregate(payload["aggregate"], converted["metrics"])
    receipts = converted["receipts"]
    evidence = _source_facts_evidence(
        payload,
        context["platform"],
        converted["source_rows"],
    )
    historical_reason = None if coverage_windows["historical"] else "missing_coverage"
    trailing_reason = None if coverage_windows["trailing"] else "missing_coverage"
    return [
        *receipts,
        *_coverage_rows(
            context=context,
            snapshot_at=snapshot_at,
            trailing_start=trailing_start,
            evidence=evidence,
            historical_reason=historical_reason,
            trailing_reason=trailing_reason,
            categories=list(OWNED_CATEGORIES),
        ),
    ]


def adapt(
    payload: dict,
    *,
    snapshot_at: str | None = None,
    trailing_start: str,
    observed_at: str | None = None,
    product_loop_id: str | None = None,
    platform: str | None = None,
) -> list[dict]:
    """Convert one passed official readback payload into validated B0 records.

    The optional ``product_loop_id``/``platform`` parameters are only for the
    provider's aggregate-only shape (currently PromptBase); an envelope must
    carry and bind both fields itself.  Invalid or incomplete payloads return
    coverage gaps and never return inferred revenue.
    """
    if snapshot_at is None:
        snapshot_at = observed_at
    elif observed_at is not None and observed_at != snapshot_at:
        return []
    if snapshot_at is None:
        return []
    try:
        snapshot = _instant(snapshot_at)
        trailing = _instant(trailing_start)
        if trailing >= snapshot:
            _fail("read_failed")
        if (isinstance(payload, dict)
                and set(payload) == set(PROMPTBASE_AGGREGATE_KEYS)):
            return _aggregate_only(
                payload,
                snapshot_at=snapshot,
                trailing_start=trailing,
                product_loop_id=product_loop_id,
                platform=platform,
            )
        return _envelope(
            payload,
            snapshot_at=snapshot,
            trailing_start=trailing,
            product_loop_id=product_loop_id,
            platform=platform,
        )
    except (
        MarketplaceAttributionError, TypeError, ValueError, KeyError, RecursionError,
    ) as error:
        context = _fallback_context(
            payload, product_loop_id=product_loop_id, platform=platform,
        )
        if context is None:
            return []
        try:
            snapshot = _instant(snapshot_at)
            trailing = _instant(trailing_start)
            if trailing >= snapshot:
                return []
        except (MarketplaceAttributionError, TypeError, ValueError, RecursionError):
            return []
        reason = (
            error.code
            if isinstance(error, MarketplaceAttributionError)
            and error.code in contract.GAP_REASONS
            else "unverified_receipt"
        )
        if isinstance(payload, dict) and set(payload) == set(PROMPTBASE_AGGREGATE_KEYS):
            reason = "missing_coverage"
            if isinstance(payload.get("observed_at"), str):
                try:
                    if _instant(payload["observed_at"]) != snapshot:
                        reason = "stale_readback"
                except MarketplaceAttributionError:
                    reason = "read_failed"
        else:
            # Keep provider/source failures observable without exposing raw
            # payload details. Valid contexts still get a B0 gap row.
            try:
                raw_observed = _instant(payload.get("observed_at")) if isinstance(payload, dict) else None
                if raw_observed is not None and raw_observed != snapshot:
                    reason = "stale_readback"
            except MarketplaceAttributionError:
                pass
        evidence = _fallback_evidence(payload, context["platform"])
        return _coverage_rows(
            context=context,
            snapshot_at=snapshot,
            trailing_start=trailing,
            evidence=evidence,
            historical_reason=reason,
            trailing_reason=reason,
            categories=[],
        )


def adapt_path(
    path: str | Path,
    *,
    snapshot_at: str | None = None,
    trailing_start: str,
    observed_at: str | None = None,
    product_loop_id: str | None = None,
    platform: str | None = None,
) -> list[dict]:
    """Read a local captured JSON artifact and delegate to :func:`adapt`."""
    try:
        payload = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError, TypeError):
        return []
    return adapt(
        payload,
        snapshot_at=snapshot_at,
        trailing_start=trailing_start,
        observed_at=observed_at,
        product_loop_id=product_loop_id,
        platform=platform,
    )


adapt_marketplace = adapt
