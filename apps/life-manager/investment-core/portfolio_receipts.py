"""Provider-neutral, read-only receipt snapshots for investment venues."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional, Tuple

from risk_policy import parse_instant


_MONEY_FIELDS = (
    "equity_usd",
    "free_cash_usd",
    "gross_pnl_usd",
    "trading_fees_usd",
    "funding_or_borrow_usd",
    "slippage_usd",
    "gas_usd",
    "model_cost_usd",
)
_COST_FIELDS = (
    "trading_fees_usd",
    "funding_or_borrow_usd",
    "slippage_usd",
    "gas_usd",
    "model_cost_usd",
)
_NON_NEGATIVE_COST_FIELDS = frozenset({
    "trading_fees_usd",
    "slippage_usd",
    "gas_usd",
    "model_cost_usd",
})


def _number(value: Any) -> Optional[Decimal]:
    if value is None or value == "unknown":
        return None
    if isinstance(value, bool):
        raise ValueError("snapshot_number_invalid")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("snapshot_number_invalid") from error
    if not number.is_finite():
        raise ValueError("snapshot_number_invalid")
    return number


@dataclass(frozen=True)
class VenueSnapshot:
    """A provider-read snapshot with no order submission capability."""

    venue: Optional[str]
    observed_at: Optional[str]
    equity_usd: Optional[Decimal]
    free_cash_usd: Optional[Decimal]
    gross_pnl_usd: Optional[Decimal]
    trading_fees_usd: Optional[Decimal]
    funding_or_borrow_usd: Optional[Decimal]
    slippage_usd: Optional[Decimal]
    gas_usd: Optional[Decimal]
    model_cost_usd: Optional[Decimal]
    source_receipt_ids: Tuple[str, ...]
    risk: Optional[Mapping[str, Any]]
    measurement_status: Optional[str]
    cost_evidence: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "VenueSnapshot":
        if not isinstance(value, Mapping):
            raise ValueError("snapshot_invalid")
        observed_at = value.get("observed_at")
        if observed_at is not None:
            if not isinstance(observed_at, str):
                raise ValueError("snapshot_time_invalid")
            try:
                parse_instant(observed_at)
            except (TypeError, ValueError):
                raise ValueError("snapshot_time_invalid")

        receipt_ids = value.get("source_receipt_ids")
        if receipt_ids is None:
            receipt_ids = ()
        if not isinstance(receipt_ids, (list, tuple)):
            raise ValueError("source_receipt_invalid")
        if any(not isinstance(item, str) or not item for item in receipt_ids):
            raise ValueError("source_receipt_invalid")

        risk = value.get("risk")
        if risk is not None and not isinstance(risk, Mapping):
            raise ValueError("risk_invalid")
        raw_cost_evidence = value.get("cost_evidence") or {}
        if not isinstance(raw_cost_evidence, Mapping):
            raise ValueError("cost_evidence_invalid")
        cost_evidence = {}
        for field_name, evidence_ids in raw_cost_evidence.items():
            if not isinstance(field_name, str) or not isinstance(evidence_ids, (list, tuple)):
                raise ValueError("cost_evidence_invalid")
            if any(not isinstance(item, str) or not item for item in evidence_ids):
                raise ValueError("cost_evidence_invalid")
            cost_evidence[field_name] = tuple(evidence_ids)

        numbers = {field: _number(value.get(field)) for field in _MONEY_FIELDS}
        venue = value.get("venue")
        if venue is not None and not isinstance(venue, str):
            raise ValueError("venue_invalid")
        status = value.get("measurement_status")
        if status is not None and not isinstance(status, str):
            raise ValueError("measurement_status_invalid")
        return cls(
            venue=venue,
            observed_at=observed_at,
            equity_usd=numbers["equity_usd"],
            free_cash_usd=numbers["free_cash_usd"],
            gross_pnl_usd=numbers["gross_pnl_usd"],
            trading_fees_usd=numbers["trading_fees_usd"],
            funding_or_borrow_usd=numbers["funding_or_borrow_usd"],
            slippage_usd=numbers["slippage_usd"],
            gas_usd=numbers["gas_usd"],
            model_cost_usd=numbers["model_cost_usd"],
            source_receipt_ids=tuple(receipt_ids),
            risk=risk,
            measurement_status=status,
            cost_evidence=cost_evidence,
        )

    def validation_reason(self) -> Optional[str]:
        if not self.venue:
            return "venue_unknown"
        if not self.observed_at:
            return "snapshot_time_invalid"
        if self.risk is None:
            return "risk_unknown"
        if not self.source_receipt_ids:
            return "source_receipt_invalid"
        for field in _COST_FIELDS:
            if getattr(self, field) is None:
                return "cost_unknown"
        for field in _MONEY_FIELDS:
            if getattr(self, field) is None:
                return "snapshot_number_unknown"
        for field in _NON_NEGATIVE_COST_FIELDS:
            if getattr(self, field) < 0:
                return "cost_invalid"
        if self.equity_usd < 0 or self.free_cash_usd < 0:
            return "snapshot_number_invalid"
        if self.measurement_status != "measured":
            return "measurement_not_measured"
        return None
