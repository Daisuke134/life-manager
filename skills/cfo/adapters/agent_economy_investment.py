"""Pure, fail-closed B5 adapters for finalized agent and investment readbacks.

The input is an already verified, sanitized provider payload.  This module only
normalizes that payload into the B0 contract; it never discovers a receipt,
contacts a provider, or mutates a wallet.

B0 has no ``realized_investment`` revenue class.  Positive realized sale P&L is
therefore represented as a one-time settled revenue component, while a realized
loss is represented as ``other_measured_cost``.  Fees and slippage stay separate
so the result can be recomputed from the provider receipt units.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any, Iterable

from skills.cfo import economic_attribution as contract


AGENT_LOOP = "agent-economy"
INVESTMENT_LOOP = "investment"
BASE_CHAIN_ID = 8453
AGENT_CATEGORIES = (contract.REVENUE, contract.REFUND, "provider_fee")
INVESTMENT_CATEGORIES = (contract.REVENUE, "provider_fee", "other_measured_cost")
EXCLUDED = {
    "pending_revenue", "owner_deposit", "self_payment", "internal_transfer",
    "payout", "fundraising", "token_appreciation", "unrealized_investment_pnl",
}
SUCCESS_STATES = {
    "0x1", "1", "success", "succeeded", "settled", "paid", "received",
    "completed", "broker_reconciled", "filled", "closed", "marked", "snapshot",
}
PENDING_STATES = {"pending", "processing", "submitted", "accepted", "open"}
TX_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
ATOMIC_RE = re.compile(r"^[0-9]+$")
SIGNED_DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]{1,18})?$")
MAX_B0_AMOUNT_INTEGER_DIGITS = 26
ATOMIC_DECIMAL_PLACES = 6


class AttributionError(ValueError):
    """Sanitized input failure; provider payload details never enter the message."""


def _first(mapping: Any, *keys: str) -> Any:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _strict_bool(*mappings: Any, keys: tuple[str, ...]) -> bool | None:
    values = [
        mapping[key]
        for mapping in mappings
        if isinstance(mapping, dict)
        for key in keys
        if key in mapping
    ]
    if any(type(value) is not bool for value in values):
        raise AttributionError("unverified_receipt")
    if values and any(value != values[0] for value in values[1:]):
        raise AttributionError("unverified_receipt")
    return values[0] if values else None


def _strict_int(*mappings: Any, keys: tuple[str, ...]) -> int | None:
    values = [
        mapping[key]
        for mapping in mappings
        if isinstance(mapping, dict)
        for key in keys
        if key in mapping
    ]
    if any(type(value) is not int or isinstance(value, bool) for value in values):
        raise AttributionError("unverified_receipt")
    if values and any(value != values[0] for value in values[1:]):
        raise AttributionError("unverified_receipt")
    return values[0] if values else None


def _instant(value: Any) -> str:
    if not isinstance(value, str) or not contract.RFC3339.fullmatch(value):
        raise AttributionError("timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise AttributionError("timestamp_invalid")
        return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
    except AttributionError:
        raise
    except (ValueError, OverflowError) as error:
        raise AttributionError("timestamp_invalid") from error


def _strict_timestamp(
    *sources: tuple[Any, tuple[str, ...]],
    error: str,
) -> str | None:
    values = [
        _instant(mapping[key])
        for mapping, keys in sources
        if isinstance(mapping, dict)
        for key in keys
        if key in mapping and mapping[key] is not None
    ]
    if values and any(value != values[0] for value in values[1:]):
        raise AttributionError(error)
    return values[0] if values else None


def _probe_instant(value: Any) -> str:
    """Use B0's timestamp validator without importing a second contract."""
    return _instant(value)


def _canonical_money_text(number: Decimal) -> str:
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _bounded_decimal(
    value: Any, *, signed: bool = False, atomic: bool = False,
) -> Decimal:
    if value is None or isinstance(value, bool):
        raise AttributionError("amount_invalid")
    raw = format(value, "f") if isinstance(value, Decimal) else None
    if atomic:
        if raw is None and type(value) is int:
            raw = str(value)
        elif raw is None and isinstance(value, str):
            raw = value.strip()
        elif raw is None:
            raise AttributionError("amount_invalid")
        if not ATOMIC_RE.fullmatch(raw):
            raise AttributionError("amount_invalid")
        if len(raw.lstrip("0") or "0") > MAX_B0_AMOUNT_INTEGER_DIGITS + ATOMIC_DECIMAL_PLACES:
            raise AttributionError("amount_invalid")
    else:
        if raw is None and type(value) is int:
            raw = str(value)
        elif raw is None and isinstance(value, str):
            raw = value.strip()
        elif raw is None:
            raise AttributionError("amount_invalid")
        unsigned = raw[1:] if signed and raw.startswith("-") else raw
        if (
            not (SIGNED_DECIMAL_RE if signed else contract.AMOUNT).fullmatch(unsigned)
            or len(unsigned.partition(".")[0]) > MAX_B0_AMOUNT_INTEGER_DIGITS
        ):
            raise AttributionError("amount_invalid")
    try:
        number = Decimal(raw)
        exact = _canonical_money_text(number.copy_abs())
        normalized = _canonical_money_text(number.copy_abs().normalize())
        if not number.is_finite() or normalized != exact:
            raise AttributionError("amount_invalid")
    except (ArithmeticError, ValueError) as error:
        raise AttributionError("amount_invalid") from error
    if not signed and number < 0:
        raise AttributionError("amount_invalid")
    return number


def _decimal(value: Any, *, signed: bool = False, atomic: bool = False) -> Decimal:
    return _bounded_decimal(value, signed=signed, atomic=atomic)


def _money(number: Decimal, *, allow_zero: bool = False) -> str:
    number = _bounded_decimal(number)
    if number < 0 or (not allow_zero and number == 0):
        raise AttributionError("amount_invalid")
    return _canonical_money_text(number) if number else "0"


def _signed_money(number: Decimal) -> str:
    number = _bounded_decimal(number, signed=True)
    return format(number.normalize(), "f")


def _exact_add(*numbers: Decimal) -> Decimal:
    if not numbers:
        return Decimal("0")
    min_exponent = min(number.as_tuple().exponent for number in numbers)
    max_adjusted = max(number.adjusted() if number else 0 for number in numbers)
    precision = max(1, max_adjusted - min_exponent + 1) + len(numbers)
    with localcontext() as context:
        context.prec = precision
        return sum(numbers, Decimal("0"))


def _scale_atomic(number: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = max(2, len(number.as_tuple().digits) + 1)
        return number / Decimal("1000000")


def _amount_from_fields(
    row: dict[str, Any],
    atomic_keys: Iterable[str],
    decimal_keys: Iterable[str],
    *,
    signed: bool = False,
    default: Decimal | None = None,
) -> Decimal:
    atomic_values = [row[key] for key in atomic_keys if key in row and row[key] is not None]
    decimal_values = [row[key] for key in decimal_keys if key in row and row[key] is not None]
    if atomic_values and decimal_values:
        atomic_value = _decimal(atomic_values[0], atomic=True)
        decimal_value = _decimal(decimal_values[0], signed=signed)
        if _scale_atomic(atomic_value) != decimal_value:
            raise AttributionError("amount_inconsistent")
        if len(atomic_values) > 1 and any(
            _decimal(value, atomic=True) != atomic_value for value in atomic_values[1:]
        ):
            raise AttributionError("amount_conflict")
        if len(decimal_values) > 1 and any(
            _decimal(value, signed=signed) != decimal_value for value in decimal_values[1:]
        ):
            raise AttributionError("amount_conflict")
        return decimal_value
    values = atomic_values or decimal_values
    if not values:
        if default is None:
            raise AttributionError("amount_missing")
        return default
    parsed = [
        _decimal(value, atomic=bool(atomic_values), signed=signed)
        for value in values
    ]
    if any(value != parsed[0] for value in parsed[1:]):
        raise AttributionError("amount_conflict")
    return _scale_atomic(parsed[0]) if atomic_values else parsed[0]


def _currency(value: Any, expected: str) -> str:
    if value is None:
        return expected
    if not isinstance(value, str) or value.upper() != expected:
        raise AttributionError("unsupported_currency")
    return expected


def _identity(value: Any, field: str = "identity") -> str:
    if not isinstance(value, str) or not contract.IDENTITY.fullmatch(value):
        raise AttributionError(f"{field}_invalid")
    return value


def _tx(value: Any) -> str:
    if not isinstance(value, str) or not TX_RE.fullmatch(value):
        raise AttributionError("receipt_identity_invalid")
    return value.lower()


def _address(value: Any) -> str:
    if not isinstance(value, str) or not ADDRESS_RE.fullmatch(value):
        raise AttributionError("address_invalid")
    return value.lower()


def _optional_rank(mapping: dict[str, Any]) -> int | None:
    values = [mapping[key] for key in ("rank", "award_rank") if key in mapping]
    if not values:
        return None
    parsed: list[int] = []
    for value in values:
        if type(value) is int:
            rank = value
        elif isinstance(value, str) and value.strip().isdigit():
            rank = int(value.strip())
        else:
            raise AttributionError("rank_invalid")
        if rank < 1:
            raise AttributionError("rank_invalid")
        parsed.append(rank)
    if any(value != parsed[0] for value in parsed[1:]):
        raise AttributionError("rank_conflict")
    return parsed[0]


def _chain_id(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        raise AttributionError("chain_invalid")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str):
        text = value.strip().lower()
        if text in {"base", "base-mainnet", "base_mainnet", "eip155:8453"}:
            result = BASE_CHAIN_ID
        else:
            try:
                result = int(text, 0)
            except ValueError as error:
                raise AttributionError("chain_invalid") from error
    else:
        raise AttributionError("chain_invalid")
    if result != BASE_CHAIN_ID:
        raise AttributionError("chain_invalid")
    return result


def _log_index(value: Any) -> int:
    if isinstance(value, bool):
        raise AttributionError("receipt_identity_invalid")
    try:
        text = str(value).strip()
        result = int(text, 0) if text.lower().startswith("0x") else int(text)
    except (TypeError, ValueError):
        raise AttributionError("receipt_identity_invalid") from None
    if result < 0:
        raise AttributionError("receipt_identity_invalid")
    return result


def _evidence(row: dict[str, Any], fallback: str) -> list[str]:
    refs = row.get("evidence_refs")
    if refs is None:
        return [fallback]
    if not isinstance(refs, list) or not refs:
        raise AttributionError("evidence_invalid")
    if any(not isinstance(ref, str) or not contract.EVIDENCE.fullmatch(ref) for ref in refs):
        raise AttributionError("evidence_invalid")
    if len(set(refs)) != len(refs):
        raise AttributionError("evidence_duplicate")
    if len(refs) > 32:
        raise AttributionError("evidence_invalid")
    return refs


def _digest(value: Any) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as error:
        raise AttributionError("read_failed") from error
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _digest_material(value: Any) -> Any:
    """Make evidence identity insensitive to exact duplicate replay rows."""
    if isinstance(value, dict):
        return {key: _digest_material(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        unique = {_digest(item): _digest_material(item) for item in value}
        return [unique[key] for key in sorted(unique)]
    return value


def _readback_meta(payload: dict[str, Any], end: str) -> tuple[str, str | None, bool, str]:
    readback = payload.get("readback") if isinstance(payload.get("readback"), dict) else {}
    observed = _strict_timestamp(
        (payload, ("observed_at", "read_at")),
        (readback, ("observed_at", "read_at")),
        error="read_failed",
    ) or end
    window_end = _strict_timestamp(
        (payload, ("window_end",)), (readback, ("window_end",)), error="read_failed",
    ) or observed
    window_start = _strict_timestamp(
        (payload, ("window_start",)), (readback, ("window_start",)), error="read_failed",
    )
    history_complete = (
        payload.get("history_complete") is True
        or readback.get("history_complete") is True
        or readback.get("historical_complete") is True
    )
    return observed, window_start, history_complete and window_end == end, _digest(payload)


def _bundle_reorg_detected(payload: dict[str, Any]) -> bool:
    readback = payload.get("readback") if isinstance(payload.get("readback"), dict) else {}
    return _strict_bool(payload, readback, keys=("reorg_detected",)) is True


def _row_settlement(row: dict[str, Any], root: dict[str, Any]) -> None:
    settlement = row.get("receipt") if isinstance(row.get("receipt"), dict) else {}
    if not settlement:
        settlement = row.get("settlement") if isinstance(row.get("settlement"), dict) else {}
    finality = _first(row, "finality") or _first(settlement, "finality") or root.get("finality")
    explicit_finalized = _strict_bool(row, settlement, root, keys=("finalized",))
    finalized = (
        explicit_finalized is not False
        and (explicit_finalized is True or finality == "finalized")
    )
    status = str(
        _first(row, "receipt_status", "status", "terminal_state")
        or _first(settlement, "receipt_status", "status", "terminal_state")
        or ""
    ).lower()
    if not finalized or status not in SUCCESS_STATES:
        raise AttributionError("unverified_receipt")
    if _strict_bool(row, settlement, keys=("reorg_detected",)) is True:
        raise AttributionError("unverified_receipt")
    block = _first(row, "block_number", "block") or _first(settlement, "block_number", "block")
    finalized_block = _first(row, "finalized_block") or _first(settlement, "finalized_block")
    if block is not None and finalized_block is not None:
        try:
            if int(block) > int(finalized_block):
                raise AttributionError("unverified_receipt")
        except (TypeError, ValueError):
            raise AttributionError("unverified_receipt") from None


def _chain_proof(row: dict[str, Any], settlement: dict[str, Any] | None = None) -> tuple[str, str]:
    settlement = settlement or {}
    proof = row.get("proof") if isinstance(row.get("proof"), dict) else {}
    if not proof:
        proof = row.get("chain_provider_proof") if isinstance(row.get("chain_provider_proof"), dict) else {}
    provider_receipt_id = (
        _first(row, "provider_receipt_id", "providerReceiptId")
        or _first(proof, "provider_receipt_id", "providerReceiptId", "receipt_id", "receiptId")
    )
    if provider_receipt_id is not None:
        if proof.get("verified") is not True:
            raise AttributionError("unverified_receipt")
        provider_id = _identity(provider_receipt_id, "provider_receipt_id")
        return f"provider:{provider_id}", provider_id
    tx_value = (
        _first(proof, "tx_hash", "txHash", "transaction_hash", "transactionHash")
        or _first(row, "tx", "tx_hash", "transaction_hash", "transactionHash")
        or _first(settlement, "tx_hash", "txHash", "transaction_hash", "transactionHash")
    )
    log_value = _first(proof, "log_index", "logIndex")
    if log_value is None:
        log_value = _first(row, "log_index", "logIndex")
    if log_value is None:
        log_value = _first(settlement, "log_index", "logIndex")
    chain_value = _first(proof, "chain_id", "chainId")
    if chain_value is None:
        chain_value = _first(row, "chain_id", "chainId", "network")
    if chain_value is None:
        chain_value = _first(settlement, "chain_id", "chainId", "network")
    _chain_id(chain_value)
    tx = _tx(tx_value)
    index = _log_index(log_value)
    if proof and proof.get("verified") is not True:
        raise AttributionError("unverified_receipt")
    identity = f"base:{tx}:{index}"
    return identity, identity


def _owned_wallets(payload: dict[str, Any]) -> tuple[set[str], set[str]]:
    values = payload.get("owned_pay_tos") or payload.get("owned_wallets")
    if not isinstance(values, list) or not values:
        raise AttributionError("owner_boundary_missing")
    owned = {_address(value) for value in values}
    self_values = payload.get("self_wallets") or []
    if not isinstance(self_values, list):
        raise AttributionError("owner_boundary_invalid")
    self_wallets = owned | {_address(value) for value in self_values}
    return owned, self_wallets


def _receipt(
    *,
    loop_id: str,
    provider: str,
    receipt_id: str,
    currency: str,
    occurred_at: str,
    settled_at: str | None,
    state: str,
    revenue_class: str | None,
    components: list[dict[str, str]],
    evidence: list[str],
) -> dict[str, Any]:
    return contract.validate_record({
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "receipt",
        "receipt_id": _identity(receipt_id, "receipt_id"),
        "product_loop_id": loop_id,
        "provider": _identity(provider, "provider").lower(),
        "currency": currency,
        "occurred_at": occurred_at,
        "settled_at": settled_at,
        "verification_state": state,
        "revenue_class": revenue_class,
        "evidence_refs": evidence,
        "components": components,
    })


def _coverage(
    *,
    loop_id: str,
    source_id: str,
    projection: str,
    end: str,
    start: str | None,
    observed_at: str,
    complete: bool,
    reason: str | None,
    categories: tuple[str, ...],
    evidence: str,
) -> dict[str, Any]:
    return contract.validate_record({
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "coverage",
        "product_loop_id": loop_id,
        "source_id": source_id,
        "projection": projection,
        "window_start": start,
        "window_end": end,
        "coverage_state": "complete" if complete else "gap",
        "reason": None if complete else reason or "missing_coverage",
        "covered_categories": list(categories) if complete else [],
        "observed_at": observed_at,
        "evidence_refs": [evidence],
    })


def _coverage_set(
    *,
    loop_id: str,
    source_id: str,
    end: str,
    start: str,
    observed_at: str,
    history_complete: bool,
    window_start: str | None,
    categories: tuple[str, ...],
    evidence: str,
    reason: str | None = None,
    as_of: bool = False,
) -> list[dict[str, Any]]:
    stale = observed_at != end
    window_ok = window_start is not None and window_start <= start and observed_at == end
    effective_reason = "stale_readback" if stale else reason
    historical_complete = history_complete and not stale and reason is None
    trailing_complete = history_complete and window_ok and reason is None
    rows = [
        _coverage(
            loop_id=loop_id, source_id=source_id, projection="historical", end=end,
            start=None, observed_at=observed_at, complete=historical_complete,
            reason=effective_reason, categories=categories, evidence=evidence,
        ),
        _coverage(
            loop_id=loop_id, source_id=source_id, projection="trailing", end=end,
            start=start, observed_at=observed_at, complete=trailing_complete,
            reason=effective_reason, categories=categories, evidence=evidence,
        ),
    ]
    if as_of:
        as_of_complete = observed_at == end and reason is None
        rows.append(_coverage(
            loop_id=loop_id, source_id=source_id, projection="as_of", end=end,
            start=None, observed_at=observed_at, complete=as_of_complete,
            reason=effective_reason, categories=categories, evidence=evidence,
        ))
    return rows


def _failure_coverages(
    *,
    loop_id: str,
    source_id: str,
    end: str,
    start: str,
    reason: str,
    evidence: str,
    as_of: bool = False,
) -> list[dict[str, Any]]:
    return _coverage_set(
        loop_id=loop_id, source_id=source_id, end=end, start=start,
        observed_at=end, history_complete=False, window_start=None,
        categories=(), evidence=evidence, reason=reason, as_of=as_of,
    )


def _classify_agent(row: dict[str, Any], payer: str, recipient: str, self_wallets: set[str]) -> str | None:
    explicit = row.get("classification") or row.get("kind")
    if explicit in EXCLUDED:
        return explicit
    if payer in self_wallets or recipient in self_wallets and payer == recipient:
        return "self_payment"
    if row.get("external") is not True:
        if payer in self_wallets and recipient in self_wallets:
            return "internal_transfer"
        return "owner_deposit"
    return None


def _x402_row(
    row: dict[str, Any],
    root: dict[str, Any],
    owned: set[str],
    self_wallets: set[str],
    fallback_evidence: str,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    if not isinstance(row, dict):
        raise AttributionError("row_invalid")
    _strict_bool(row, root, keys=("finalized",))
    _strict_bool(row, keys=("reorg_detected",))
    sale_id = _identity(_first(row, "source_sale_id", "sale_id", "id"), "source_sale_id")
    currency = _currency(_first(row, "currency", "asset"), "USDC")
    payer = _address(_first(row, "from", "payer", "external_payer"))
    recipient = _address(_first(row, "to", "payTo", "pay_to", "recipient"))
    pay_to = _address(_first(row, "payTo", "pay_to", "recipient", "to"))
    if pay_to not in owned:
        raise AttributionError("owner_boundary_invalid")
    evidence = _evidence(row, f"{fallback_evidence}/{sale_id}")
    status = str(_first(row, "status", "receipt_status", "terminal_state") or "").lower()
    if status in PENDING_STATES:
        amount = _amount_from_fields(
            row, ("usdc_atomic", "amount_atomic", "gross_atomic"),
            ("gross_decimal", "gross", "amount_usdc", "usdc"),
        )
        occurred = _strict_timestamp(
            (row, ("occurred_at", "observed_at")), error="unverified_receipt",
        )
        if occurred is None:
            raise AttributionError("timestamp_invalid")
        return _receipt(
            loop_id=AGENT_LOOP, provider="x402", receipt_id=f"x402:pending:{sale_id}",
            currency=currency, occurred_at=occurred, settled_at=None,
            state="pending", revenue_class="one_time",
            components=[{"category": "pending_revenue", "amount": _money(amount)}],
            evidence=evidence,
        ), "pending_revenue", None
    _row_settlement(row, root)
    proof_key, proof_suffix = _chain_proof(row)
    amount = _amount_from_fields(
        row, ("usdc_atomic", "amount_atomic", "gross_atomic"),
        ("gross_decimal", "gross", "amount_usdc", "usdc"),
    )
    fee = _amount_from_fields(
        row, ("fee_atomic", "provider_fee_atomic"), ("fee_decimal", "fee", "provider_fee"),
        default=Decimal("0"),
    )
    refund = _amount_from_fields(
        row, ("refund_atomic",), ("refund_decimal", "refund"), default=Decimal("0"),
    )
    classification_row = row
    inferred_external = "external" not in row and payer not in self_wallets
    if inferred_external:
        classification_row = {**row, "external": True}
    classification = _classify_agent(classification_row, payer, recipient, self_wallets)
    if classification is None and recipient != pay_to:
        raise AttributionError("owner_boundary_invalid")
    occurred = _strict_timestamp(
        (row, ("occurred_at", "observed_at")), error="unverified_receipt",
    )
    if occurred is None:
        raise AttributionError("timestamp_invalid")
    settled = _strict_timestamp(
        (row, ("settled_at",)), error="unverified_receipt",
    ) or occurred
    if classification is not None:
        return _receipt(
            loop_id=AGENT_LOOP, provider="x402", receipt_id=f"x402:{proof_suffix}",
            currency=currency, occurred_at=occurred, settled_at=settled,
            state="verified", revenue_class=None,
            components=[{"category": classification, "amount": _money(amount)}],
            evidence=evidence,
        ), None, proof_key
    if not inferred_external and row.get("external") is not True:
        raise AttributionError("unverified_receipt")
    components: list[dict[str, str]] = []
    if amount > 0:
        components.append({"category": contract.REVENUE, "amount": _money(amount)})
    if refund > 0:
        components.append({"category": contract.REFUND, "amount": _money(refund)})
    if fee > 0:
        components.append({"category": "provider_fee", "amount": _money(fee)})
    if not components:
        raise AttributionError("amount_missing")
    revenue_class = "one_time" if amount > 0 else None
    return _receipt(
        loop_id=AGENT_LOOP, provider="x402", receipt_id=f"x402:{proof_suffix}",
        currency=currency, occurred_at=occurred, settled_at=settled,
        state="verified", revenue_class=revenue_class, components=components,
        evidence=evidence,
    ), None, proof_key


def _taskmarket_row(
    row: dict[str, Any],
    root: dict[str, Any],
    owned: set[str],
    self_wallets: set[str],
    fallback_evidence: str,
) -> tuple[dict[str, Any], str]:
    if not isinstance(row, dict):
        raise AttributionError("row_invalid")
    task = row.get("task") if isinstance(row.get("task"), dict) else row
    award = row.get("award") if isinstance(row.get("award"), dict) else row
    settlement = row.get("receipt") if isinstance(row.get("receipt"), dict) else row.get("settlement", {})
    if not isinstance(settlement, dict):
        raise AttributionError("receipt_invalid")
    if task.get("status") != "completed":
        raise AttributionError("unverified_receipt")
    self_award = _strict_bool(task, keys=("selfAward", "self_award"))
    if self_award is True:
        classification = "self_payment"
    else:
        classification = None
    task_id = _identity(_first(task, "id", "task_id"), "task_id")
    requester = _address(_first(task, "requester", "requester_wallet", "external_payer"))
    worker = _address(_first(award, "workerAddress", "worker_address", "worker"))
    if worker not in owned:
        raise AttributionError("owner_boundary_invalid")
    if requester in self_wallets:
        classification = "self_payment"
    tx_value = _first(award, "settlementTxHash", "settlement_tx_hash", "tx")
    tx = _tx(tx_value)
    payment = _decimal(_first(award, "workerPayment", "worker_payment", "worker_payment_atomic"), atomic=True)
    fee = _decimal(_first(award, "platformFee", "platform_fee", "platform_fee_atomic"), atomic=True)
    gross = _decimal(_first(award, "grossAmount", "gross_amount", "gross_amount_atomic"), atomic=True)
    rank = _optional_rank(award)
    if _exact_add(payment, fee) != gross:
        raise AttributionError("amount_inconsistent")
    awards = task.get("awards")
    award_count = _strict_int(task, keys=("awardCount", "award_count"))
    if not isinstance(awards, list) or award_count != len(awards):
        raise AttributionError("unverified_receipt")
    matching = []
    for item in awards:
        if not isinstance(item, dict):
            continue
        try:
            item_tx = _tx(_first(item, "settlementTxHash", "settlement_tx_hash", "tx"))
            item_worker = _address(_first(item, "workerAddress", "worker_address", "worker"))
            item_payment = _decimal(
                _first(item, "workerPayment", "worker_payment", "worker_payment_atomic"),
                atomic=True,
            )
            item_fee = _decimal(
                _first(item, "platformFee", "platform_fee", "platform_fee_atomic"),
                atomic=True,
            )
            item_gross = _decimal(
                _first(item, "grossAmount", "gross_amount", "gross_amount_atomic"),
                atomic=True,
            )
            item_rank = _optional_rank(item)
        except AttributionError:
            continue
        if (
            item_tx == tx
            and item_worker == worker
            and item_payment == payment
            and item_fee == fee
            and item_gross == gross
            and item_rank == rank
        ):
            matching.append(item)
    if len(matching) != 1:
        raise AttributionError("unverified_receipt")
    receipt_transfer = settlement.get("transfer") if isinstance(settlement.get("transfer"), dict) else {}
    transfers = settlement.get("transfers")
    transfer_count = _strict_int(row, settlement, keys=("transfer_count",))
    if transfer_count is None and isinstance(transfers, list):
        transfer_count = len(transfers)
    elif isinstance(transfers, list) and transfer_count != len(transfers):
        raise AttributionError("unverified_receipt")
    if transfer_count != 1:
        raise AttributionError("unverified_receipt")
    if not receipt_transfer and isinstance(transfers, list):
        receipt_transfer = transfers[0] if transfers else {}
    if (
        _address(_first(receipt_transfer, "from", "sender")) != requester
        or _address(_first(receipt_transfer, "to", "recipient")) != worker
        or _decimal(_first(receipt_transfer, "amount_atomic", "amount"), atomic=True) != payment
    ):
        raise AttributionError("unverified_receipt")
    receipt_tx = _tx(_first(
        settlement, "tx_hash", "txHash", "transaction_hash", "transactionHash",
    ))
    if receipt_tx != tx:
        raise AttributionError("unverified_receipt")
    merged = {**row, **settlement}
    _row_settlement(merged, root)
    proof_key, proof_suffix = _chain_proof(merged, settlement)
    occurred = _strict_timestamp(
        (row, ("occurred_at", "created_at")), error="unverified_receipt",
    )
    if occurred is None:
        occurred = _strict_timestamp(
            (award, ("settledAt", "settled_at")), error="unverified_receipt",
        )
    if occurred is None:
        raise AttributionError("timestamp_invalid")
    settled = _strict_timestamp(
        (row, ("settled_at",)),
        (award, ("settledAt", "settled_at")),
        error="unverified_receipt",
    ) or occurred
    evidence = _evidence(row, f"{fallback_evidence}/{task_id}")
    components: list[dict[str, str]] = []
    payment_amount = _scale_atomic(payment)
    gross_amount = _scale_atomic(gross)
    fee_amount = _scale_atomic(fee)
    if classification is not None:
        components.append({"category": classification, "amount": _money(payment_amount)})
    else:
        components.append({
            "category": contract.REVENUE,
            "amount": _money(gross_amount),
        })
        if fee > 0:
            components.append({
                "category": "provider_fee",
                "amount": _money(fee_amount),
            })
    refund = _amount_from_fields(
        row, ("refund_atomic",), ("refund_decimal", "refund"), default=Decimal("0"),
    )
    if classification is None and refund > 0:
        components.append({"category": contract.REFUND, "amount": _money(refund)})
    return _receipt(
        loop_id=AGENT_LOOP, provider="taskmarket", receipt_id=f"taskmarket:{proof_suffix}",
        currency="USDC", occurred_at=occurred, settled_at=settled,
        state="verified", revenue_class="one_time" if classification is None else None,
        components=components, evidence=evidence,
    ), proof_key


def _dedupe_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["provider"], row["receipt_id"])
        previous = by_key.get(key)
        if previous is not None and previous != row:
            return [], True
        by_key[key] = row
    return list(by_key.values()), False


def adapt_agent_economy(
    payload: Any,
    *,
    snapshot_at: str,
    trailing_start: str,
    evidence_base: str | None = None,
) -> list[dict[str, Any]]:
    """Convert x402 and TaskMarket readbacks without provider I/O."""
    end = _probe_instant(snapshot_at)
    start = _probe_instant(trailing_start)
    if start >= end:
        raise ValueError("projection_window_invalid")
    if not isinstance(payload, dict):
        evidence = f"lm-agent-economy://readback/{_digest({'read_failed': True})}"
        return [
            *_failure_coverages(loop_id=AGENT_LOOP, source_id="x402-readback", end=end, start=start,
                                reason="read_failed", evidence=evidence),
            *_failure_coverages(loop_id=AGENT_LOOP, source_id="taskmarket-readback", end=end, start=start,
                                reason="read_failed", evidence=evidence, as_of=True),
        ]
    del evidence_base
    evidence = f"lm-agent-economy://readback/{_digest(_digest_material(payload))}"
    try:
        root_reorg = _bundle_reorg_detected(payload)
    except AttributionError:
        root_reorg = True
    if root_reorg:
        return [
            *_failure_coverages(loop_id=AGENT_LOOP, source_id="x402-readback", end=end, start=start,
                                reason="unverified_receipt", evidence=evidence),
            *_failure_coverages(loop_id=AGENT_LOOP, source_id="taskmarket-readback", end=end, start=start,
                                reason="unverified_receipt", evidence=evidence, as_of=True),
        ]
    try:
        observed, window_start, history_complete, _ = _readback_meta(payload, end)
        owned, self_wallets = _owned_wallets(payload)
    except AttributionError:
        return [
            *_failure_coverages(loop_id=AGENT_LOOP, source_id="x402-readback", end=end, start=start,
                                reason="read_failed", evidence=evidence),
            *_failure_coverages(loop_id=AGENT_LOOP, source_id="taskmarket-readback", end=end, start=start,
                                reason="read_failed", evidence=evidence, as_of=True),
        ]
    records: list[dict[str, Any]] = []
    failures: dict[str, str | None] = {"x402-readback": None, "taskmarket-readback": None}
    fatal_failure = False
    proof_rows: dict[str, dict[str, Any]] = {}
    source_items = (("x402", "x402-readback"), ("taskmarket", "taskmarket-readback"))
    for kind, source_id in source_items:
        if kind not in payload:
            failures[source_id] = "source_unconnected"
            continue
        items = payload.get(kind)
        if not isinstance(items, list):
            failures[source_id] = "read_failed"
            continue
        source_records: list[dict[str, Any]] = []
        try:
            for item in items:
                if kind == "x402":
                    record, marker, proof = _x402_row(
                        item, payload, owned, self_wallets, evidence,
                    )
                    if record is not None:
                        source_records.append(record)
                    if marker == "pending_revenue":
                        failures[source_id] = "unverified_receipt"
                    if proof is not None:
                        current = {"record": record, "source": source_id}
                        previous = proof_rows.get(proof)
                        if previous is not None and previous != current:
                            raise AttributionError("receipt_conflict")
                        proof_rows[proof] = current
                else:
                    record, proof = _taskmarket_row(
                        item, payload, owned, self_wallets, evidence,
                    )
                    current = {"record": record, "source": source_id}
                    previous = proof_rows.get(proof)
                    if previous is not None and previous != current:
                        raise AttributionError("receipt_conflict")
                    if previous is None:
                        source_records.append(record)
                    proof_rows[proof] = current
        except (AttributionError, contract.ContractError, KeyError, TypeError, ValueError):
            failures[source_id] = "unverified_receipt"
            fatal_failure = True
            source_records = []
        deduped, conflict = _dedupe_rows(source_records)
        if conflict:
            failures[source_id] = "unverified_receipt"
            fatal_failure = True
            deduped = []
        records.extend(deduped)
    if observed != end:
        records = []
        for source_id in failures:
            if failures[source_id] is None:
                failures[source_id] = "stale_readback"
    elif fatal_failure:
        # A conflicting proof makes the whole agent-economy bundle unsafe to sum.
        records = []
        failures = {
            source_id: (reason or "unverified_receipt")
            for source_id, reason in failures.items()
        }
    rows: list[dict[str, Any]] = records
    for source_id in ("x402-readback", "taskmarket-readback"):
        reason = failures[source_id]
        complete = reason is None and observed == end
        rows.extend(_coverage_set(
            loop_id=AGENT_LOOP, source_id=source_id, end=end, start=start,
            observed_at=observed, history_complete=history_complete,
            window_start=window_start, categories=AGENT_CATEGORIES, evidence=evidence,
            reason=reason,
        ))
        rows.append(_coverage(
            loop_id=AGENT_LOOP, source_id=source_id, projection="as_of", end=end,
            start=None, observed_at=observed, complete=False,
            reason="missing_coverage" if complete else (reason or "missing_coverage"),
            categories=(), evidence=evidence,
        ))
    return _sort_records(rows)


def _investment_identity(row: dict[str, Any]) -> str:
    nested = row.get("broker") if isinstance(row.get("broker"), dict) else {}
    strategy = row.get("strategy_receipt") if isinstance(row.get("strategy_receipt"), dict) else {}
    receipt = strategy.get("receipt") if isinstance(strategy.get("receipt"), dict) else {}
    value = (
        _first(row, "provider_receipt_id", "receipt_id", "source_receipt_id", "id")
        or _first(nested, "id", "order_id", "provider_order_id")
        or _first(receipt, "provider_order_id", "receipt_id")
    )
    return _identity(value, "provider_receipt_id")


def _investment_times(row: dict[str, Any], root: dict[str, Any]) -> tuple[str, str]:
    nested = row.get("broker") if isinstance(row.get("broker"), dict) else {}
    occurred = _strict_timestamp(
        (row, ("occurred_at", "filled_at", "recorded_at", "observed_at")),
        (nested, ("filled_at", "occurred_at")),
        error="unverified_receipt",
    )
    if occurred is None:
        occurred = _strict_timestamp(
            (root, ("observed_at",)), error="unverified_receipt",
        )
    if occurred is None:
        raise AttributionError("timestamp_invalid")
    settled = _strict_timestamp(
        (row, ("settled_at", "completed_at", "recorded_at")),
        error="unverified_receipt",
    ) or occurred
    return occurred, settled


def _investment_finalized(row: dict[str, Any], root: dict[str, Any]) -> None:
    broker = row.get("broker") if isinstance(row.get("broker"), dict) else {}
    status = str(_first(row, "status", "outcome") or _first(broker, "status") or "").lower()
    explicit_finalized = _strict_bool(row, broker, root, keys=("finalized",))
    finalized = (
        explicit_finalized is not False
        and (explicit_finalized is True
             or row.get("finality") == "finalized"
             or root.get("finality") == "finalized")
    )
    if not finalized or status not in SUCCESS_STATES:
        raise AttributionError("unverified_receipt")
    if _strict_bool(row, broker, keys=("reorg_detected",)) is True:
        raise AttributionError("unverified_receipt")


def _investment_pnl_basis(row: dict[str, Any]) -> str:
    values = [
        row[key] for key in ("pnl_basis", "realized_pnl_basis", "realized_basis", "basis")
        if key in row
    ]
    if not values:
        raise AttributionError("pnl_basis_missing")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise AttributionError("pnl_basis_unknown")
        basis = value.strip().lower()
        if basis in {"net", "net_after_costs", "net_after_fee_slippage", "net_after_fee_and_slippage"}:
            normalized.append("net")
        elif basis in {"gross", "gross_pre_cost", "gross_before_costs"}:
            normalized.append("gross")
        else:
            raise AttributionError("pnl_basis_unknown")
    if any(value != normalized[0] for value in normalized[1:]):
        raise AttributionError("pnl_basis_conflict")
    return normalized[0]


def _investment_metric_receipt(
    row: dict[str, Any],
    root: dict[str, Any],
    provider: str,
    base_id: str,
    category: str,
    amount: Decimal,
    occurred: str,
    settled: str,
    fallback_evidence: str,
    revenue_class: str | None = None,
    metric_suffix: str | None = None,
) -> dict[str, Any]:
    suffix = metric_suffix or {
        contract.REVENUE: "pnl",
        "provider_fee": "fee",
        "other_measured_cost": "slippage",
    }[category]
    return _receipt(
        loop_id=INVESTMENT_LOOP,
        provider=provider,
        receipt_id=f"{base_id}:{suffix}",
        currency="USD",
        occurred_at=occurred,
        settled_at=settled,
        state="verified",
        revenue_class=revenue_class,
        components=[{"category": category, "amount": _money(amount)}],
        evidence=_evidence(row, f"{fallback_evidence}/{base_id}"),
    )


def _investment_outcome_rows(
    row: dict[str, Any], root: dict[str, Any], fallback_evidence: str,
) -> list[dict[str, Any]]:
    if not isinstance(row, dict):
        raise AttributionError("row_invalid")
    identity = _investment_identity(row)
    occurred, settled = _investment_times(row, root)
    paper = row.get("paper") is True or row.get("mode") == "paper"
    realized_present = any(key in row for key in ("realized_pnl_usd", "realized_pnl", "realizedPnlUsd"))
    unrealized = _amount_from_fields(
        row, (), ("unrealized_pnl_usd", "unrealized_pnl", "unrealizedPnlUsd"),
        signed=True, default=Decimal("0"),
    )
    token_appreciation = _amount_from_fields(
        row, (), ("token_appreciation_usd", "token_appreciation", "tokenAppreciationUsd"), default=Decimal("0"),
    )
    _investment_finalized(row, root)
    if paper:
        if realized_present:
            _investment_pnl_basis(row)
        paper_value = _amount_from_fields(
            row, (), ("realized_pnl_usd", "realized_pnl", "realizedPnlUsd"),
            signed=True, default=Decimal("0"),
        )
        if paper_value == 0:
            paper_value = unrealized
        if paper_value == 0:
            return []
        return [_receipt(
            loop_id=INVESTMENT_LOOP, provider="alpaca",
            receipt_id=f"{identity if identity.startswith('alpaca:') else f'alpaca:{identity}'}:paper",
            currency="USD", occurred_at=occurred, settled_at=settled, state="verified",
            revenue_class=None,
            components=[{"category": "unrealized_investment_pnl", "amount": _money(abs(paper_value))}],
            evidence=_evidence(row, f"{fallback_evidence}/{identity}"),
        )]
    base_id = identity if identity.startswith("alpaca:") else f"alpaca:{identity}"
    rows: list[dict[str, Any]] = []
    fee = _amount_from_fields(
        row, ("fee_atomic",), ("fee_usd", "fees_usd", "trading_fee_usd", "buy_fee_usd", "sell_fee_usd"),
        default=Decimal("0"),
    )
    slippage = _amount_from_fields(
        row, ("slippage_atomic",), ("slippage_usd", "slippage"), default=Decimal("0"),
    )
    if unrealized != 0:
        rows.append(_receipt(
            loop_id=INVESTMENT_LOOP, provider="alpaca", receipt_id=f"{base_id}:unrealized",
            currency="USD", occurred_at=occurred, settled_at=settled, state="verified",
            revenue_class=None,
            components=[{"category": "unrealized_investment_pnl", "amount": _money(abs(unrealized))}],
            evidence=_evidence(row, f"{fallback_evidence}/{identity}"),
        ))
    if token_appreciation > 0:
        rows.append(_receipt(
            loop_id=INVESTMENT_LOOP, provider="alpaca", receipt_id=f"{base_id}:token-appreciation",
            currency="USD", occurred_at=occurred, settled_at=settled, state="verified",
            revenue_class=None,
            components=[{"category": "token_appreciation", "amount": _money(token_appreciation)}],
            evidence=_evidence(row, f"{fallback_evidence}/{identity}"),
        ))
    if realized_present:
        realized = _amount_from_fields(
            row, (), ("realized_pnl_usd", "realized_pnl", "realizedPnlUsd"), signed=True,
        )
        basis = _investment_pnl_basis(row)
        broker = row.get("broker") if isinstance(row.get("broker"), dict) else {}
        side = str(_first(row, "side") or _first(broker, "side") or "").lower()
        if side != "sell":
            raise AttributionError("realized_sale_invalid")
        gross_realized = _exact_add(realized, fee, slippage) if basis == "net" else realized
        if gross_realized > 0:
            rows.append(_investment_metric_receipt(
                row, root, "alpaca", base_id, contract.REVENUE,
                gross_realized, occurred, settled, fallback_evidence, revenue_class="one_time",
                metric_suffix="pnl",
            ))
        elif gross_realized < 0:
            rows.append(_investment_metric_receipt(
                row, root, "alpaca", base_id, "other_measured_cost",
                -gross_realized, occurred, settled, fallback_evidence, metric_suffix="pnl",
            ))
    if fee > 0:
        rows.append(_investment_metric_receipt(
            row, root, "alpaca", base_id, "provider_fee", fee,
            occurred, settled, fallback_evidence,
        ))
    if slippage > 0:
        rows.append(_investment_metric_receipt(
            row, root, "alpaca", base_id, "other_measured_cost", slippage,
            occurred, settled, fallback_evidence,
        ))
    return rows


def _investment_cash_flow(row: dict[str, Any], root: dict[str, Any], fallback_evidence: str) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise AttributionError("row_invalid")
    finalized_value = _strict_bool(row, keys=("finalized",))
    if _strict_bool(row, keys=("reorg_detected",)) is True:
        raise AttributionError("unverified_receipt")
    category = row.get("classification") or row.get("kind")
    if category not in EXCLUDED:
        raise AttributionError("cash_flow_invalid")
    identity = _identity(_first(row, "receipt_id", "source_receipt_id", "id"), "receipt_id")
    if finalized_value is not True or str(row.get("status", "")).lower() not in SUCCESS_STATES:
        raise AttributionError("unverified_receipt")
    amount = _amount_from_fields(row, (), ("amount_usd", "amount"))
    occurred, settled = _investment_times(row, root)
    output_id = identity if identity.startswith("alpaca:") else f"alpaca:{identity}"
    return _receipt(
        loop_id=INVESTMENT_LOOP, provider="alpaca", receipt_id=output_id,
        currency="USD", occurred_at=occurred, settled_at=settled, state="verified",
        revenue_class=None, components=[{"category": category, "amount": _money(amount)}],
        evidence=_evidence(row, f"{fallback_evidence}/{identity}"),
    )


def _investment_balance(payload: dict[str, Any], end: str, evidence: str) -> dict[str, Any]:
    balance = payload.get("balance")
    if not isinstance(balance, dict):
        account_readback = payload.get("account_readback")
        balance = account_readback if isinstance(account_readback, dict) else {}
    finalized = _strict_bool(balance, keys=("finalized",))
    if balance.get("verification_state") != "verified" or finalized is not True:
        raise AttributionError("unverified_receipt")
    if _strict_bool(balance, keys=("reorg_detected",)) is True:
        raise AttributionError("unverified_receipt")
    observed = _instant(balance.get("observed_at"))
    if observed != end:
        raise AttributionError("stale_readback")
    snapshot_id = _identity(_first(balance, "snapshot_id", "readback_id", "receipt_id"), "snapshot_id")
    account_id = _identity(
        _first(balance, "account_id") or payload.get("account_id"), "account_id",
    )
    amount = _amount_from_fields(balance, (), ("amount", "free_cash_usd", "cash_usd", "cash"), default=None)
    currency = _currency(balance.get("currency"), "USD")
    output_snapshot_id = snapshot_id if snapshot_id.startswith("alpaca:") else f"alpaca:{snapshot_id}"
    return contract.validate_record({
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "liquid_balance",
        "snapshot_id": output_snapshot_id,
        "account_id": account_id,
        "provider": "alpaca",
        "currency": currency,
        "amount": _money(amount, allow_zero=True),
        "observed_at": observed,
        "verification_state": "verified",
        "evidence_refs": _evidence(balance, f"{evidence}/{snapshot_id}"),
    })


def adapt_investment(
    payload: Any,
    *,
    snapshot_at: str,
    trailing_start: str,
    evidence_base: str | None = None,
) -> list[dict[str, Any]]:
    """Convert finalized live investment outcomes and verified balance readback."""
    end = _probe_instant(snapshot_at)
    start = _probe_instant(trailing_start)
    if start >= end:
        raise ValueError("projection_window_invalid")
    if not isinstance(payload, dict):
        evidence = f"lm-investment://readback/{_digest({'read_failed': True})}"
        return [
            *_failure_coverages(loop_id=INVESTMENT_LOOP, source_id="alpaca-orders", end=end, start=start,
                                reason="read_failed", evidence=evidence),
            *_failure_coverages(loop_id=INVESTMENT_LOOP, source_id="alpaca-account", end=end, start=start,
                                reason="read_failed", evidence=evidence, as_of=True),
        ]
    del evidence_base
    evidence = f"lm-investment://readback/{_digest(_digest_material(payload))}"
    try:
        root_reorg = _bundle_reorg_detected(payload)
    except AttributionError:
        root_reorg = True
        observed, window_start, history_complete = end, None, False
        root_failure = "unverified_receipt"
    else:
        try:
            observed, window_start, history_complete, _ = _readback_meta(payload, end)
        except AttributionError:
            observed, window_start, history_complete = end, None, False
            root_failure = "read_failed"
        else:
            root_failure = None
        if root_reorg:
            root_failure = "unverified_receipt"
    provider = payload.get("provider", "alpaca")
    if provider != "alpaca":
        root_failure = "unverified_receipt"
    outcomes = payload.get("outcomes", payload.get("fills", payload.get("receipts")))
    cash_flows = payload.get("cash_flows", [])
    records: list[dict[str, Any]] = []
    order_failure = root_failure
    if not isinstance(outcomes, list):
        order_failure = order_failure or "missing_coverage"
    elif order_failure is None:
        try:
            for row in outcomes:
                records.extend(_investment_outcome_rows(row, payload, evidence))
            for row in cash_flows:
                records.append(_investment_cash_flow(row, payload, evidence))
        except (AttributionError, contract.ContractError, KeyError, TypeError, ValueError):
            order_failure = "unverified_receipt"
            records = []
    deduped, conflict = _dedupe_rows(records)
    if conflict:
        order_failure = "unverified_receipt"
        deduped = []
    records = deduped
    balance_failure = root_failure
    balance: dict[str, Any] | None = None
    if balance_failure is None:
        try:
            balance = _investment_balance(payload, end, evidence)
        except (AttributionError, contract.ContractError, KeyError, TypeError, ValueError) as error:
            balance_failure = "stale_readback" if str(error) == "stale_readback" else "unverified_receipt"
    if observed != end:
        records = []
        order_failure = order_failure or "stale_readback"
        balance = None
        balance_failure = "unverified_receipt" if root_reorg else "stale_readback"
    if order_failure is not None:
        records = []
    if balance is not None and balance_failure is None:
        records.append(balance)
    rows: list[dict[str, Any]] = records
    order_complete = order_failure is None and observed == end
    rows.extend(_coverage_set(
        loop_id=INVESTMENT_LOOP, source_id="alpaca-orders", end=end, start=start,
        observed_at=observed, history_complete=history_complete,
        window_start=window_start, categories=INVESTMENT_CATEGORIES, evidence=evidence,
        reason=order_failure,
    ))
    rows.extend(_coverage_set(
        loop_id=INVESTMENT_LOOP, source_id="alpaca-account", end=end, start=start,
        observed_at=observed, history_complete=True, window_start=window_start,
        categories=("liquid_balance",), evidence=evidence, reason=balance_failure,
        as_of=True,
    ))
    del order_complete
    return _sort_records(rows)


def adapt(
    payload: Any,
    *,
    snapshot_at: str,
    trailing_start: str,
    evidence_base: str | None = None,
) -> list[dict[str, Any]]:
    """Adapt either a combined B5 bundle or one source payload."""
    if isinstance(payload, dict) and ("agent_economy" in payload or "investment" in payload):
        rows: list[dict[str, Any]] = []
        if "agent_economy" in payload:
            rows.extend(adapt_agent_economy(
                payload["agent_economy"], snapshot_at=snapshot_at,
                trailing_start=trailing_start, evidence_base=evidence_base,
            ))
        if "investment" in payload:
            rows.extend(adapt_investment(
                payload["investment"], snapshot_at=snapshot_at,
                trailing_start=trailing_start, evidence_base=evidence_base,
            ))
        return _sort_records(rows)
    if isinstance(payload, dict) and any(key in payload for key in ("x402", "taskmarket")) and any(
        key in payload for key in ("outcomes", "fills", "receipts", "balance", "account_readback")
    ):
        return _sort_records([
            *adapt_agent_economy(
                payload, snapshot_at=snapshot_at, trailing_start=trailing_start,
                evidence_base=evidence_base,
            ),
            *adapt_investment(
                payload, snapshot_at=snapshot_at, trailing_start=trailing_start,
                evidence_base=evidence_base,
            ),
        ])
    if isinstance(payload, dict) and any(key in payload for key in ("x402", "taskmarket")):
        return adapt_agent_economy(
            payload, snapshot_at=snapshot_at, trailing_start=trailing_start,
            evidence_base=evidence_base,
        )
    return adapt_investment(
        payload, snapshot_at=snapshot_at, trailing_start=trailing_start,
        evidence_base=evidence_base,
    )


def adapt_path(
    path: str | Path,
    *,
    snapshot_at: str,
    trailing_start: str,
    evidence_base: str | None = None,
) -> list[dict[str, Any]]:
    """Read one local JSON artifact and apply the same pure conversion."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        payload = None
    return adapt(
        payload, snapshot_at=snapshot_at, trailing_start=trailing_start,
        evidence_base=evidence_base,
    )


def _sort_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            row.get("product_loop_id", ""), row.get("record_type", ""),
            row.get("provider", ""), row.get("receipt_id", row.get("snapshot_id", row.get("source_id", ""))),
            row.get("projection", ""),
        ),
    )


__all__ = ["adapt", "adapt_agent_economy", "adapt_investment", "adapt_path", "AttributionError"]
