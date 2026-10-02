"""Pure Affiliate financial readback adapter for the B0 attribution contract."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, DecimalException
from pathlib import Path

from skills.cfo import economic_attribution as contract


LOOP_ID = "affiliate"
SOURCE_ID = "affiliate-partnerstack-financial-record"
PROVIDER = "partnerstack-elevenlabs"
UPSTREAM_PROVIDER = "elevenlabs"
SUPPORTED_CURRENCIES = {"USD"}
# The default Decimal precision is 28; USD cents reserve two fractional places.
MAX_B0_AMOUNT_INTEGER_DIGITS = 26
USD_COMMISSION_AMOUNT = re.compile(
    rf"(?:0|[1-9][0-9]{{0,{MAX_B0_AMOUNT_INTEGER_DIGITS - 1}}})(?:\.[0-9]{{1,2}})?"
)
FINANCIAL_CATEGORIES = (
    "settled_external_revenue", "refund", "provider_fee", "payment_fee",
)
COMMISSION_MINOR_FIELDS = (
    "gross_commission_minor", "reversal_minor", "net_commission_minor",
)
PENDING = {"pending", "hold"}
APPROVED = {"approved", "scheduled"}
PAID = {"paid", "settled"}
REVERSED = {"reversed", "chargeback"}
STATUS_GROUP = {
    **{value: "pending" for value in PENDING},
    **{value: "approved" for value in APPROVED},
    **{value: "paid" for value in PAID},
    **{value: "reversed" for value in (*REVERSED, "declined")},
}
PRODUCER_COMMISSION_STATUS = {
    "pending": "pending", "hold": "pending",
    "approved": "approved", "scheduled": "approved",
    "declined": "reversed", "reversed": "reversed", "paid": "paid",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _canonical_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _artifact_evidence(digest: str) -> str:
    return f"lm-affiliate://partnerstack/artifacts/{digest}"


def _minor(value) -> str:
    """Convert the currently observed USD minor unit to a B0 decimal amount."""
    if type(value) is not int:
        raise ValueError("amount_invalid")
    try:
        amount = Decimal(str(value)) / 100
        if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal("0.01")):
            raise ValueError("amount_invalid")
        return format(amount.normalize(), "f")
    except (ArithmeticError, ValueError):
        raise ValueError("amount_invalid") from None


def _require_exact_int_fields(row: dict, fields: tuple[str, ...]) -> None:
    if any(type(row.get(field)) is not int for field in fields):
        raise ValueError("unverified_receipt")


def _instant(value) -> str:
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        value += "T00:00:00Z"
    probe = {
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "coverage",
        "product_loop_id": LOOP_ID,
        "source_id": SOURCE_ID,
        "projection": "historical",
        "window_start": None,
        "window_end": value,
        "coverage_state": "gap",
        "reason": "missing_coverage",
        "covered_categories": [],
        "observed_at": value,
        "evidence_refs": ["lm-affiliate://validation/timestamp"],
    }
    return contract.validate_record(probe)["window_end"]


def _identity(value, field: str) -> str:
    if not isinstance(value, str) or not contract.IDENTITY.fullmatch(value):
        raise ValueError(f"{field}_invalid")
    return value


def _currency(row: dict) -> str:
    value = row.get("currency")
    if value not in SUPPORTED_CURRENCIES:
        raise ValueError("unsupported_currency")
    return value


def _provider(row: dict) -> None:
    if row.get("provider") != UPSTREAM_PROVIDER:
        raise ValueError("unverified_receipt")


def _raw_optional_id(row: dict, *keys: str):
    return next(
        (value.strip() for key in keys if isinstance((value := row.get(key)), str) and value.strip()),
        None,
    )


def _hash_optional(value):
    return hashlib.sha256(value.encode()).hexdigest() if isinstance(value, str) and value else None


def _expected_normalized_commission(raw: dict, status_map: dict[str, str]) -> dict:
    transaction_id = raw.get("reward_key")
    provider_status = raw.get("reward_status")
    if not isinstance(transaction_id, str) or not transaction_id or provider_status not in status_map:
        raise ValueError("unverified_receipt")
    raw_currency = next(
        (raw.get(name) for name in ("currency", "currency_code", "currency_iso")
         if raw.get(name) not in (None, "")),
        "USD",
    )
    if not isinstance(raw_currency, str) or not re.fullmatch(r"[A-Za-z]{3}", raw_currency):
        raise ValueError("unsupported_currency")
    currency = raw_currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError("unsupported_currency")
    raw_amount = raw.get("commission_amount")
    if type(raw_amount) is not str or not USD_COMMISSION_AMOUNT.fullmatch(raw_amount):
        raise ValueError("unverified_receipt")
    try:
        minor = Decimal(raw_amount) * 100
    except (DecimalException, ValueError):
        raise ValueError("unverified_receipt") from None
    if not minor.is_finite() or minor < 0:
        raise ValueError("unverified_receipt")
    major_integer_digits = max(1, minor.adjusted() - 1)
    if (
        major_integer_digits > MAX_B0_AMOUNT_INTEGER_DIGITS
        or minor != minor.to_integral_value()
    ):
        raise ValueError("unverified_receipt")
    gross = int(minor)
    status = status_map[provider_status]
    reversal = gross if status == "reversed" else 0
    return {
        "provider_transaction_id": transaction_id,
        "provider_status": provider_status,
        "status": status,
        "currency": currency,
        "gross_commission_minor": gross,
        "reversal_minor": reversal,
        "net_commission_minor": gross - reversal,
        "created_at": raw.get("created_at_date"),
        "offer": raw.get("reward_description"),
        "target_type": raw.get("target_type"),
        "action": raw.get("action_external_type"),
        "attribution": {
            "sub_id_1": raw.get("sub_id_1"),
            "sub_id_2": raw.get("sub_id_2"),
            "sub_id_3": raw.get("sub_id_3"),
            "shared_id": raw.get("shared_id"),
            "clicked_at": raw.get("click_created_at_date"),
            "link_sha256": _hash_optional(raw.get("link_path")),
            "referrer_sha256": _hash_optional(raw.get("referral_source")),
            "landing_page_sha256": _hash_optional(raw.get("link_destination_path")),
        },
        "provider_settlement_id": _raw_optional_id(
            raw, "settlement_id", "settlement_key", "settlementId",
        ),
        "provider_payout_id": _raw_optional_id(
            raw, "payout_id", "payout_key", "payoutId", "payment_id", "withdrawal_id",
        ),
    }


def _receipt(*, receipt_id: str, currency: str, occurred_at: str,
             settled_at: str | None, state: str, revenue_class: str | None,
             category: str, amount: str, evidence: str) -> dict:
    return contract.validate_record({
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "receipt",
        "receipt_id": receipt_id,
        "product_loop_id": LOOP_ID,
        "provider": PROVIDER,
        "currency": currency,
        "occurred_at": occurred_at,
        "settled_at": settled_at,
        "verification_state": state,
        "revenue_class": revenue_class,
        "evidence_refs": [evidence],
        "components": [{"category": category, "amount": amount}],
    })


def _commission(row: dict, evidence: str) -> dict | None:
    _require_exact_int_fields(row, COMMISSION_MINOR_FIELDS)
    transaction_id = _identity(row.get("provider_transaction_id"), "provider_transaction_id")
    status = row.get("status")
    provider_status = row.get("provider_status")
    if status not in {"pending", "approved", "paid", "reversed"}:
        raise ValueError("unverified_receipt")
    if STATUS_GROUP.get(provider_status) != STATUS_GROUP.get(status):
        raise ValueError("unverified_receipt")
    currency = _currency(row)
    occurred_at = _instant(row.get("created_at") or row.get("observed_at"))
    receipt_id = f"{PROVIDER}:commission:{transaction_id}:{status}"
    if status in PENDING | APPROVED:
        return _receipt(
            receipt_id=receipt_id, currency=currency, occurred_at=occurred_at,
            settled_at=None, state="pending", revenue_class="one_time",
            category="pending_revenue", amount=_minor(row.get("gross_commission_minor")),
            evidence=evidence,
        )
    if status in PAID:
        _identity(row.get("provider_settlement_id"), "provider_settlement_id")
        settled_at = _instant(row.get("settled_at"))
        return _receipt(
            receipt_id=receipt_id, currency=currency, occurred_at=occurred_at,
            settled_at=settled_at, state="verified", revenue_class="one_time",
            category="settled_external_revenue",
            # Revenue is gross commission. A separately itemized fee is a cost;
            # using net here would subtract that same fee twice.
            amount=_minor(row.get("gross_commission_minor")), evidence=evidence,
        )
    if provider_status == "declined":
        return None
    if provider_status not in REVERSED:
        raise ValueError("unverified_receipt")
    settled_at = _instant(
        row.get("reversed_at") or row.get("settled_at") or row.get("observed_at")
    )
    return _receipt(
        receipt_id=receipt_id, currency=currency, occurred_at=occurred_at,
        settled_at=settled_at, state="verified", revenue_class=None,
        category="refund",
        amount=_minor(row.get("reversal_minor") or row.get("gross_commission_minor")),
        evidence=evidence,
    )


def _fee(row: dict, evidence: str) -> dict:
    _provider(row)
    if row.get("status") not in PAID:
        raise ValueError("unverified_receipt")
    fee_id = _identity(row.get("provider_fee_id"), "provider_fee_id")
    category = {
        "network": "provider_fee", "provider": "provider_fee", "payment": "payment_fee",
    }.get(row.get("fee_type"))
    if category is None:
        raise ValueError("unverified_receipt")
    return _receipt(
        receipt_id=f"{PROVIDER}:fee:{fee_id}:{row['status']}",
        currency=_currency(row), occurred_at=_instant(row.get("occurred_at")),
        settled_at=_instant(row.get("settled_at")), state="verified",
        revenue_class=None, category=category, amount=_minor(row.get("amount_minor")),
        evidence=evidence,
    )


def _payout(row: dict, evidence: str) -> dict:
    _provider(row)
    status = row.get("status")
    if status not in {"paid", "completed", "deposited", "withdrawn"}:
        raise ValueError("unverified_receipt")
    payout_id = _identity(row.get("provider_payout_id"), "provider_payout_id")
    return _receipt(
        receipt_id=f"{PROVIDER}:payout:{payout_id}:{status}",
        currency=_currency(row), occurred_at=_instant(row.get("occurred_at")),
        settled_at=_instant(row.get("settled_at")), state="verified",
        revenue_class=None, category="payout", amount=_minor(row.get("amount_minor")),
        evidence=evidence,
    )


def _cash(row: dict, evidence: str) -> dict:
    _provider(row)
    kind = row.get("kind")
    if kind not in {"owner_deposit", "self_payment", "internal_transfer"}:
        raise ValueError("unverified_receipt")
    movement_id = _identity(row.get("movement_id"), "movement_id")
    occurred_at = _instant(row.get("occurred_at"))
    return _receipt(
        receipt_id=f"{PROVIDER}:cash:{movement_id}:{kind}",
        currency=_currency(row), occurred_at=occurred_at, settled_at=occurred_at,
        state="verified", revenue_class=None, category=kind,
        amount=_minor(row.get("amount_minor")), evidence=evidence,
    )


def _validate_commission_pairs(artifact: dict, status_map: dict[str, str]) -> list[dict]:
    raw_rows = artifact.get("commission_rows")
    normalized = artifact.get("normalized_commissions")
    if not isinstance(raw_rows, list) or not isinstance(normalized, list):
        raise ValueError("unverified_receipt")
    if len(raw_rows) != len(normalized):
        raise ValueError("unverified_receipt")
    result = []
    for raw, row in zip(raw_rows, normalized):
        if not isinstance(raw, dict) or not isinstance(row, dict):
            raise ValueError("unverified_receipt")
        _require_exact_int_fields(row, COMMISSION_MINOR_FIELDS)
        if row.get("currency") not in SUPPORTED_CURRENCIES:
            raise ValueError("unsupported_currency")
        expected = _expected_normalized_commission(raw, status_map)
        if row != expected:
            raise ValueError("unverified_receipt")
        enriched = dict(expected)
        enriched["observed_at"] = artifact.get("observed_at")
        for field in ("settled_at", "reversed_at"):
            if raw.get(field) is not None:
                enriched[field] = raw[field]
        result.append(enriched)
    return result


def _validate_bundle(payload: dict) -> tuple[dict, list[dict], str, str]:
    capture, artifact = payload.get("capture"), payload.get("artifact")
    if not isinstance(capture, dict) or not isinstance(artifact, dict):
        raise ValueError("unverified_receipt")
    if (
        type(capture.get("schema_version")) is not int
        or capture.get("schema_version") != 1
        or capture.get("receipt_type") != "PARTNERSTACK_REPORT_CAPTURE"
        or capture.get("provider") != UPSTREAM_PROVIDER
        or capture.get("currency_display") not in SUPPORTED_CURRENCIES
        or type(artifact.get("schema_version")) is not int
        or artifact.get("schema_version") != 1
        or artifact.get("receipt_type") != "PARTNERSTACK_RENDERED_REPORT_ARTIFACT"
    ):
        reason = (
            "unsupported_currency"
            if capture.get("currency_display") not in SUPPORTED_CURRENCIES
            else "unverified_receipt"
        )
        raise ValueError(reason)
    digest = _canonical_hash(artifact)
    if capture.get("rendered_artifact_sha256") != digest or not SHA256.fullmatch(digest):
        raise ValueError("unverified_receipt")
    if capture.get("observed_at") != artifact.get("observed_at"):
        raise ValueError("unverified_receipt")
    if "commission_status_extension" in capture:
        raise ValueError("unverified_receipt")
    rows = _validate_commission_pairs(artifact, PRODUCER_COMMISSION_STATUS)
    row_count = capture.get("commission_row_count")
    if type(row_count) is not int or row_count < 0 or row_count != len(rows):
        raise ValueError("unverified_receipt")
    row_state = "EMPTY" if not rows else "ROWS_PRESENT"
    normalizer_state = "NO_LIVE_ROWS" if not rows else "NORMALIZED"
    if (
        capture.get("commission_row_state") != row_state
        or capture.get("normalizer_state") != normalizer_state
    ):
        raise ValueError("unverified_receipt")
    unsupported_capture_keys = {
        "financial_extension", "normalized_fees", "normalized_payouts",
        "cash_movements", "fees", "payouts",
    }
    unsupported_artifact_keys = {
        "normalized_fees", "normalized_payouts", "cash_movements", "fees", "payouts",
        "commission_status_extension", "financial_extension",
    }
    if unsupported_capture_keys.intersection(capture) or unsupported_artifact_keys.intersection(artifact):
        raise ValueError("unverified_receipt")
    return artifact, rows, _instant(capture.get("observed_at")), digest


def _coverage(projection: str, *, start: str | None, end: str, observed_at: str,
              reason: str, evidence: str) -> dict:
    return contract.validate_record({
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "coverage",
        "product_loop_id": LOOP_ID,
        "source_id": SOURCE_ID,
        "projection": projection,
        "window_start": start,
        "window_end": end,
        "coverage_state": "gap",
        "reason": reason,
        "covered_categories": [],
        "observed_at": observed_at,
        "evidence_refs": [evidence],
    })


def _read_failed_records(*, snapshot_at: str, trailing_start: str) -> list[dict]:
    end, start = _instant(snapshot_at), _instant(trailing_start)
    evidence = _artifact_evidence(_canonical_hash({"read_failed": True}))
    return [
        _coverage("historical", start=None, end=end, observed_at=end,
                  reason="read_failed", evidence=evidence),
        _coverage("trailing", start=start, end=end, observed_at=end,
                  reason="read_failed", evidence=evidence),
        _coverage("as_of", start=None, end=end, observed_at=end,
                  reason="missing_category", evidence=evidence),
    ]


def adapt(payload: dict, *, snapshot_at: str, trailing_start: str,
          evidence_base: str) -> list[dict]:
    """Convert a hash-bound PartnerStack capture/artifact pair to B0 records."""
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")
    del evidence_base  # Evidence is derived from verified content, never caller input.
    end, start = _instant(snapshot_at), _instant(trailing_start)
    receipts, failures = [], []
    observed_at = end
    digest = _canonical_hash({"unverified_receipt": True})
    artifact: dict = {}
    rows: list[dict] = []
    try:
        digest = _canonical_hash(payload)
        artifact, rows, observed_at, digest = _validate_bundle(payload)
    except (contract.ContractError, KeyError, TypeError, ValueError) as error:
        capture = payload.get("capture") if isinstance(payload.get("capture"), dict) else {}
        raw_artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else payload
        candidate = capture.get("observed_at") or raw_artifact.get("observed_at")
        try:
            observed_at = _instant(candidate)
        except (contract.ContractError, TypeError, ValueError):
            observed_at = end
        failures.append(
            "unsupported_currency" if str(error) == "unsupported_currency"
            else "unverified_receipt"
        )

    evidence = _artifact_evidence(digest)
    if artifact:
        groups = [(rows, _commission)]
        for values, converter in groups:
            if not isinstance(values, list):
                failures.append("read_failed")
                continue
            for row in values:
                try:
                    if not isinstance(row, dict):
                        raise ValueError("unverified_receipt")
                    receipt = converter(row, evidence)
                    if receipt is not None:
                        receipts.append(receipt)
                except contract.ContractError:
                    failures.append("unverified_receipt")
                except (KeyError, TypeError, ValueError) as error:
                    failures.append(
                        "unsupported_currency" if str(error) == "unsupported_currency"
                        else "unverified_receipt"
                    )

    if failures:
        receipts = []
    if observed_at != end:
        failures.append("stale_readback")
    failures.append("missing_coverage")
    reason = next(candidate for candidate in (
        "stale_readback", "unsupported_currency", "unverified_receipt",
        "read_failed", "missing_coverage",
    ) if candidate in failures)
    coverage = [
        _coverage("historical", start=None, end=end, observed_at=observed_at,
                  reason=reason, evidence=evidence),
        _coverage("trailing", start=start, end=end, observed_at=observed_at,
                  reason=reason, evidence=evidence),
        _coverage("as_of", start=None, end=end, observed_at=observed_at,
                  reason="missing_category", evidence=evidence),
    ]
    return [*receipts, *coverage]


def _native_bundle(artifact: dict, digest: str) -> dict:
    rows = artifact.get("commission_rows")
    normalized = artifact.get("normalized_commissions")
    count = len(rows) if isinstance(rows, list) and isinstance(normalized, list) else -1
    return {
        "capture": {
            "schema_version": 1,
            "receipt_type": "PARTNERSTACK_REPORT_CAPTURE",
            "provider": UPSTREAM_PROVIDER,
            "currency_display": "USD",
            "commission_row_count": count,
            "commission_row_state": "EMPTY" if count == 0 else "ROWS_PRESENT",
            "normalizer_state": "NO_LIVE_ROWS" if count == 0 else "NORMALIZED",
            "rendered_artifact_sha256": digest,
            "observed_at": artifact.get("observed_at"),
        },
        "artifact": artifact,
    }


def _transition_source(row: dict) -> str:
    if (
        not isinstance(row, dict)
        or type(row.get("schema_version")) is not int
        or row.get("schema_version") != 1
        or row.get("receipt_type") != "COMMISSION_TRANSITION"
        or row.get("provider") != UPSTREAM_PROVIDER
    ):
        raise ValueError("unverified_receipt")
    _require_exact_int_fields(row, COMMISSION_MINOR_FIELDS)
    source_hash = row.get("source_artifact_sha256")
    if not isinstance(source_hash, str) or not SHA256.fullmatch(source_hash):
        raise ValueError("unverified_receipt")
    identity = {
        "provider": row.get("provider"),
        "provider_transaction_id": row.get("provider_transaction_id"),
        "provider_status": row.get("provider_status"),
        "gross_commission_minor": row.get("gross_commission_minor"),
        "reversal_minor": row.get("reversal_minor"),
        "net_commission_minor": row.get("net_commission_minor"),
        "currency": row.get("currency"),
        "provider_settlement_id": row.get("provider_settlement_id"),
        "provider_payout_id": row.get("provider_payout_id"),
        "attribution": row.get("attribution"),
        "placement": row.get("placement"),
    }
    if row.get("transition_id") != _canonical_hash(identity):
        raise ValueError("unverified_receipt")
    return source_hash


def _transition_matches(row: dict, commission: dict) -> bool:
    return (
        row.get("provider") == UPSTREAM_PROVIDER
        and all(row.get(key) == commission.get(key) for key in (
            "provider_transaction_id", "provider_status", "status",
            "gross_commission_minor", "reversal_minor", "net_commission_minor",
            "currency", "provider_settlement_id", "provider_payout_id", "created_at",
            "attribution", "offer", "target_type", "action",
        ))
    )


def _adapt_ledger(path: Path, *, snapshot_at: str, trailing_start: str) -> list[dict]:
    try:
        rows = [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return _read_failed_records(
            snapshot_at=snapshot_at, trailing_start=trailing_start,
        )
    try:
        if not rows:
            raise ValueError("unverified_receipt")
        artifact_root = path.parent / "provider-reports" / "partnerstack"
        sources = {}
        receipts = {}
        for transition in rows:
            source_hash = _transition_source(transition)
            if source_hash not in sources:
                artifact_path = artifact_root / f"{source_hash}.json"
                try:
                    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                    return _read_failed_records(
                        snapshot_at=snapshot_at, trailing_start=trailing_start,
                    )
                if not isinstance(artifact, dict) or _canonical_hash(artifact) != source_hash:
                    raise ValueError("unverified_receipt")
                bundle = _native_bundle(artifact, source_hash)
                _, commissions, observed_at, _ = _validate_bundle(bundle)
                coverage = [
                    record for record in adapt(
                        bundle, snapshot_at=snapshot_at, trailing_start=trailing_start,
                        evidence_base="lm-affiliate://ignored",
                    )
                    if record["record_type"] == "coverage"
                ]
                sources[source_hash] = (commissions, observed_at, coverage)
            commissions = sources[source_hash][0]
            matches = [
                commission for commission in commissions
                if commission.get("provider_transaction_id") ==
                transition.get("provider_transaction_id")
            ]
            if len(matches) != 1 or not _transition_matches(transition, matches[0]):
                raise ValueError("unverified_receipt")
            receipt = _commission(matches[0], _artifact_evidence(source_hash))
            if receipt is None:
                continue
            key = (receipt["provider"], receipt["receipt_id"])
            if key in receipts:
                prior = {name: value for name, value in receipts[key].items()
                         if name != "evidence_refs"}
                current = {name: value for name, value in receipt.items()
                           if name != "evidence_refs"}
                if prior != current:
                    raise ValueError("unverified_receipt")
                continue
            receipts[key] = receipt
    except (TypeError, ValueError):
        return adapt(
            {}, snapshot_at=snapshot_at, trailing_start=trailing_start,
            evidence_base="lm-affiliate://ignored",
        )
    latest = max(sources.values(), key=lambda value: value[1])
    return [*receipts.values(), *latest[2]]


def adapt_path(path: str | Path, *, snapshot_at: str, trailing_start: str) -> list[dict]:
    """Read a JSON artifact and adapt it without provider or browser calls."""
    source_path = Path(path)
    if source_path.suffix == ".jsonl":
        return _adapt_ledger(
            source_path, snapshot_at=snapshot_at, trailing_start=trailing_start,
        )
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return _read_failed_records(
            snapshot_at=snapshot_at, trailing_start=trailing_start,
        )
    if not isinstance(payload, dict):
        return _read_failed_records(
            snapshot_at=snapshot_at, trailing_start=trailing_start,
        )
    if payload.get("receipt_type") == "PARTNERSTACK_REPORT_CAPTURE":
        digest = payload.get("rendered_artifact_sha256")
        if isinstance(digest, str) and SHA256.fullmatch(digest):
            try:
                artifact = json.loads(
                    (source_path.parent / f"{digest}.json").read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                artifact = None
            if isinstance(artifact, dict):
                payload = {"capture": payload, "artifact": artifact}
    if (
        payload.get("receipt_type") == "PARTNERSTACK_RENDERED_REPORT_ARTIFACT"
    ):
        digest = _canonical_hash(payload)
        try:
            capture = json.loads((source_path.parent / "latest.json").read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            capture = {}
        # A content-addressed artifact is official only when the captured
        # provider receipt in the same readback directory binds the same hash.
        if source_path.stem == digest and capture.get("rendered_artifact_sha256") == digest:
            payload = {"capture": capture, "artifact": payload}
    return adapt(
        payload, snapshot_at=snapshot_at, trailing_start=trailing_start,
        evidence_base="lm-affiliate://ignored",
    )
