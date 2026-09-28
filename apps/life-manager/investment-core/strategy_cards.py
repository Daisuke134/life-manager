"""Immutable, evidence-backed investment strategy contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any
from urllib.parse import urlparse


VALID_STATUSES = frozenset({"research", "paper", "shadow", "live_candidate", "rejected"})


def _freeze(value: Any) -> Any:
    """Copy JSON-like card data into immutable containers.

    Decimal values are deliberately serialized as strings so a card cannot
    lose precision when it crosses the JSON/evidence boundary.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class StrategyCard:
    """A complete strategy declaration, without venue side effects."""

    strategy_id: Any = None
    venue: Any = None
    instruments: Any = None
    timeframe: Any = None
    entry_rules: Any = None
    exit_rules: Any = None
    sizing_rule: Any = None
    cost_model: Any = None
    risk_limits: Any = None
    kill_conditions: Any = None
    evidence_refs: Any = None
    status: Any = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "StrategyCard":
        if not isinstance(value, Mapping):
            raise TypeError("strategy_card_mapping_required")
        fields = (
            "strategy_id",
            "venue",
            "instruments",
            "timeframe",
            "entry_rules",
            "exit_rules",
            "sizing_rule",
            "cost_model",
            "risk_limits",
            "kill_conditions",
            "evidence_refs",
            "status",
        )
        return cls(**{field: _freeze(value.get(field)) for field in fields})

    def to_mapping(self) -> dict[str, Any]:
        return {
            "strategy_id": _thaw(self.strategy_id),
            "venue": _thaw(self.venue),
            "instruments": _thaw(self.instruments),
            "timeframe": _thaw(self.timeframe),
            "entry_rules": _thaw(self.entry_rules),
            "exit_rules": _thaw(self.exit_rules),
            "sizing_rule": _thaw(self.sizing_rule),
            "cost_model": _thaw(self.cost_model),
            "risk_limits": _thaw(self.risk_limits),
            "kill_conditions": _thaw(self.kill_conditions),
            "evidence_refs": _thaw(self.evidence_refs),
            "status": _thaw(self.status),
        }


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonempty_mapping(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value)


def _nonempty_sequence(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and bool(value)


def _valid_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_strategy_card(card: StrategyCard) -> tuple[str, ...]:
    """Return deterministic validation errors; an empty tuple means valid."""
    if not isinstance(card, StrategyCard):
        raise TypeError("strategy_card_required")

    errors: list[str] = []
    if not _nonempty_text(card.strategy_id):
        errors.append("strategy_id_missing")
    if not _nonempty_text(card.venue):
        errors.append("venue_missing")
    if not _nonempty_sequence(card.instruments):
        errors.append("instruments_empty")
    if not _nonempty_text(card.timeframe):
        errors.append("timeframe_missing")
    if not _nonempty_mapping(card.entry_rules):
        errors.append("entry_rules_missing")
    if not _nonempty_mapping(card.exit_rules):
        errors.append("exit_rules_missing")
    if not _nonempty_mapping(card.sizing_rule):
        errors.append("sizing_rule_missing")
    if not _nonempty_mapping(card.cost_model):
        errors.append("cost_model_missing")
    if not _nonempty_mapping(card.risk_limits):
        errors.append("risk_limits_missing")
    if not _nonempty_sequence(card.kill_conditions):
        errors.append("kill_conditions_missing")
    if not _nonempty_sequence(card.evidence_refs):
        errors.append("evidence_refs_missing")
    elif any(not _valid_url(ref) for ref in card.evidence_refs):
        errors.append("evidence_ref_invalid")
    if card.status not in VALID_STATUSES:
        errors.append("status_invalid")
    return tuple(errors)


__all__ = ["StrategyCard", "VALID_STATUSES", "validate_strategy_card"]
