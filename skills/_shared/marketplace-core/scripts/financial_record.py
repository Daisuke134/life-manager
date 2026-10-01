"""Thin adapters from verified marketplace receipts to common FinancialRecord values."""

import hashlib
import importlib.util
from pathlib import Path
import re
import sys
import argparse
from copy import deepcopy
import json
from typing import Mapping


_CONTRACTS_PATH = Path(__file__).with_name("contracts.py")
_SPEC = importlib.util.spec_from_file_location("marketplace_financial_contracts", _CONTRACTS_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("marketplace contracts unavailable")
_CONTRACTS = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _CONTRACTS
_SPEC.loader.exec_module(_CONTRACTS)

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CHAIN_RECORD_TYPES = frozenset({
    "application_receipt", "contract_receipt", "authorization_receipt",
    "qa_receipt", "delivery_receipt", "payment_receipt", "payout_match_receipt",
})
_CHAIN_PREFIX_RECORD_TYPES = frozenset(_CHAIN_RECORD_TYPES - {
    "payment_receipt", "payout_match_receipt",
})
_CHAIN_RECORD_ORDER = (
    "application_receipt", "contract_receipt", "authorization_receipt",
    "qa_receipt", "delivery_receipt", "payment_receipt", "payout_match_receipt",
)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _record_id(subject_id: str, idempotency_key: str) -> str:
    identity = f"{subject_id}\n{idempotency_key}"
    return f"financial:{_hash(identity)}"


def _subject(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("FinancialRecord subject_id is invalid")
    return value


def _base(*, subject_id: str, platform: str, external_ref: str, identity: str,
          occurred_at: str, observed_at: str) -> dict[str, object]:
    subject = _subject(subject_id)
    scoped = _hash(f"{subject}\n{platform}\n{identity}")
    return {
        "schema_version": 1,
        "record_type": "financial_record",
        "subject_id": subject,
        "scope": "business",
        "currency": None,
        "occurred_at": occurred_at,
        "recorded_at": observed_at,
        "source": {"provider": platform, "source_type": "marketplace", "external_ref": external_ref},
        "verification": {
            "status": "verified", "observed_at": observed_at,
            "evidence_refs": [f"marketplace://{platform}/receipt/{_hash(identity)}"],
        },
        "_scoped": scoped,
    }


def payment_to_financial_records(value: Mapping[str, object], *, subject_id: str) -> list[dict[str, object]]:
    receipt = _CONTRACTS.parse_payment_receipt(value)
    base = _base(
        subject_id=subject_id, platform=receipt.platform, external_ref=receipt.payment_external_id,
        identity=receipt.receipt_id, occurred_at=receipt.occurred_at, observed_at=receipt.observed_at,
    )
    scoped = base.pop("_scoped")
    base["currency"] = receipt.currency
    components = (
        ("gross", "business_revenue", "credit", receipt.gross_amount_minor),
        ("fee", "fee", "debit", receipt.fee_amount_minor),
        ("cost", "business_cost", "debit", receipt.cost_amount_minor),
    )
    records: list[dict[str, object]] = []
    for component, kind, direction, amount in components:
        if amount <= 0:
            continue
        component_identity = f"{scoped}\n{component}"
        idempotency_key = f"marketplace-financial:v1:{_hash(component_identity)}"
        records.append({
            **deepcopy(base),
            "record_id": _record_id(str(base["subject_id"]), idempotency_key),
            "kind": kind,
            "direction": direction,
            "amount_minor": amount,
            "idempotency_key": idempotency_key,
        })
    return records


def payout_to_financial_record(value: Mapping[str, object], *, subject_id: str) -> dict[str, object]:
    receipt = _CONTRACTS.parse_payout_match_receipt(value)
    base = _base(
        subject_id=subject_id, platform=receipt.platform, external_ref=receipt.payout_external_id,
        identity=(f"{receipt.payment_external_id}\n{receipt.payout_external_id}\n"
                  f"{receipt.bank_transaction_external_id}"),
        occurred_at=receipt.observed_at, observed_at=receipt.observed_at,
    )
    scoped = base.pop("_scoped")
    idempotency_key = f"marketplace-payout:v1:{scoped}"
    return {
        **base,
        "record_id": _record_id(str(base["subject_id"]), idempotency_key),
        "kind": "payout",
        "direction": "credit",
        "amount_minor": receipt.amount_minor,
        "currency": receipt.currency,
        "idempotency_key": idempotency_key,
    }


def project_receipts(values: list[Mapping[str, object]], *, subject_id: str) -> list[dict[str, object]]:
    record_types = [value.get("record_type") for value in values]
    if any(record_type in _CHAIN_PREFIX_RECORD_TYPES for record_type in record_types):
        return project_receipt_chains(values, subject_id=subject_id)
    records: list[dict[str, object]] = []
    for value in values:
        if value.get("record_type") == "payment_receipt":
            records.extend(payment_to_financial_records(value, subject_id=subject_id))
        elif value.get("record_type") == "payout_match_receipt":
            records.append(payout_to_financial_record(value, subject_id=subject_id))
        else:
            raise ValueError("unsupported marketplace financial receipt")
    return records


def project_receipt_chains(
    values: list[Mapping[str, object]], *, subject_id: str
) -> list[dict[str, object]]:
    """Project one or more contiguous, complete provider receipt chains.

    A provider journal may contain several jobs in one readback. Every seven-row
    slice is validated before any projected records are returned; a partial or
    interleaved slice therefore fails closed instead of leaking a partial P&L.
    """

    width = len(_CHAIN_RECORD_ORDER)
    if not values or len(values) % width:
        raise _CONTRACTS.ContractValidationError(
            ("$: incomplete_or_out_of_order_receipt_chain",)
        )
    records: list[dict[str, object]] = []
    for start in range(0, len(values), width):
        chain = values[start:start + width]
        if tuple(value.get("record_type") for value in chain) != _CHAIN_RECORD_ORDER:
            raise _CONTRACTS.ContractValidationError(
                ("$: incomplete_or_out_of_order_receipt_chain",)
            )
        records.extend(project_receipt_chain(chain, subject_id=subject_id))
    return records


def project_receipt_chain(
    values: list[Mapping[str, object]], *, subject_id: str
) -> list[dict[str, object]]:
    """Project one complete provider chain only when it is profitable.

    ``validate_receipt_chain`` is the single ordering/identity/status gate.  The
    chain's payment net is then used as the positive-unit-economics gate before
    any financial record is emitted.  The payout remains a separate transfer
    record; it is never counted as additional revenue.  Every emitted record
    carries the same chain evidence URI so CFO joins can prove they came from
    one occurrence without provider-specific fields.
    """

    parsed = _CONTRACTS.validate_receipt_chain(values)
    payment = parsed[5]
    if payment.net_amount_minor <= 0:
        raise ValueError("receipt chain net amount must be positive")

    records = payment_to_financial_records(values[5], subject_id=subject_id)
    records.append(payout_to_financial_record(values[6], subject_id=subject_id))
    chain_identity = "\n".join(
        (
            payment.platform,
            parsed[1].contract_external_id,
            payment.work_external_id,
            payment.payment_external_id,
            parsed[6].payout_external_id,
            parsed[6].bank_transaction_external_id,
        )
    )
    chain_ref = f"marketplace://{payment.platform}/chain/{_hash(chain_identity)}"
    for record in records:
        evidence = record["verification"]["evidence_refs"]
        if chain_ref not in evidence:
            evidence.append(chain_ref)
    return records


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject-id", required=True)
    args = parser.parse_args()
    values = json.load(sys.stdin)
    if not isinstance(values, list):
        raise ValueError("marketplace receipt batch must be a list")
    print(json.dumps(project_receipts(values, subject_id=args.subject_id), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "payment_to_financial_records", "payout_to_financial_record", "project_receipts",
    "project_receipt_chain", "project_receipt_chains",
]
