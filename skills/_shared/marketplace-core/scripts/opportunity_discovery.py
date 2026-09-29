"""Bounded read-only discovery runner for the shared marketplace contract."""

from __future__ import annotations

import re
from typing import Any, Mapping


_HASH = re.compile(r"^[0-9a-f]{64}$")


class OpportunityDiscoveryError(ValueError):
    """Discovery, inspect, judgement, or persistence violated the contract."""


def _text(value: Any, reason: str, *, max_length: int = 1024) -> str:
    if not isinstance(value, str):
        raise OpportunityDiscoveryError(reason)
    text = value.strip()
    if not text or len(text) > max_length or "\x00" in text:
        raise OpportunityDiscoveryError(reason)
    return text


def _string_list(value: Any, reason: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 128:
        raise OpportunityDiscoveryError(reason)
    return [_text(item, reason, max_length=1024) for item in value]


def _opportunity_identity(opportunity: Any) -> tuple[str, str, str, str, str, str, str]:
    provider = _text(getattr(opportunity, "provider", None), "opportunity_provider_invalid", max_length=32)
    opportunity_id = _text(getattr(opportunity, "opportunity_id", None), "opportunity_id_invalid", max_length=192)
    source_url = _text(getattr(opportunity, "source_url", None), "opportunity_source_url_invalid", max_length=2048)
    if not source_url.startswith("https://"):
        raise OpportunityDiscoveryError("opportunity_source_url_invalid")
    title = _text(getattr(opportunity, "title", None), "opportunity_title_invalid", max_length=512)
    currency = _text(getattr(opportunity, "currency", None), "opportunity_currency_invalid", max_length=3)
    if len(currency) != 3 or not currency.isupper() or not currency.isalpha():
        raise OpportunityDiscoveryError("opportunity_currency_invalid")
    source_hash = _text(getattr(opportunity, "source_hash", None), "opportunity_source_hash_invalid", max_length=64)
    if _HASH.fullmatch(source_hash) is None:
        raise OpportunityDiscoveryError("opportunity_source_hash_invalid")
    observed_at = _text(getattr(opportunity, "observed_at", None), "opportunity_observed_at_invalid")
    return provider, opportunity_id, source_url, title, currency, source_hash, observed_at


def _judgement(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != {"decision", "reasons", "evidence_refs", "next_action"}:
        raise OpportunityDiscoveryError("judgement_invalid")
    decision = _text(raw.get("decision"), "decision_invalid", max_length=16)
    if decision not in {"eligible", "hold"}:
        raise OpportunityDiscoveryError("decision_invalid")
    return {
        "decision": decision,
        "reasons": _string_list(raw.get("reasons"), "reasons_invalid"),
        "evidence_refs": _string_list(raw.get("evidence_refs"), "evidence_refs_invalid"),
        "next_action": _text(raw.get("next_action"), "next_action_invalid", max_length=1024),
    }


def run_opportunity_discovery(
    adapter: Any,
    judge: Any,
    store: Any,
    *,
    max_items: int = 40,
) -> dict[str, Any]:
    """Discover, inspect, judge, and persist opportunities without any mutation."""

    if type(max_items) is not int or not 1 <= max_items <= 1000:
        raise OpportunityDiscoveryError("discovery_bound_invalid")
    discover = getattr(adapter, "discover", None)
    inspect = getattr(adapter, "inspect", None)
    if not callable(discover) or not callable(inspect) or not callable(judge):
        raise OpportunityDiscoveryError("read_only_adapter_invalid")
    try:
        iterable = iter(discover())
    except Exception as error:
        raise OpportunityDiscoveryError("discover_failed") from error

    summary: dict[str, Any] = {
        "status": "ok", "inspected": 0, "persisted": 0, "duplicates": 0,
        "eligible": 0, "held": 0, "next_actions": [],
    }
    for index in range(max_items + 1):
        try:
            opportunity = next(iterable)
        except StopIteration:
            break
        except Exception as error:
            raise OpportunityDiscoveryError("discover_iteration_failed") from error
        if index >= max_items:
            raise OpportunityDiscoveryError("discovery_bound_exceeded")
        provider, opportunity_id, source_url, title, currency, source_hash, observed_at = _opportunity_identity(opportunity)
        try:
            detail = inspect(opportunity_id)
        except Exception as error:
            raise OpportunityDiscoveryError("inspect_failed") from error
        inspected_opportunity = getattr(detail, "opportunity", None)
        inspected_identity = _opportunity_identity(inspected_opportunity)
        if inspected_identity[:3] != (provider, opportunity_id, source_url):
            raise OpportunityDiscoveryError("inspect_identity_mismatch")
        inspected_source_hash = _text(
            getattr(detail, "source_hash", None), "inspect_source_hash_invalid", max_length=64,
        )
        if _HASH.fullmatch(inspected_source_hash) is None:
            raise OpportunityDiscoveryError("inspect_source_hash_invalid")
        if inspected_source_hash != inspected_identity[5]:
            raise OpportunityDiscoveryError("inspect_source_hash_mismatch")
        judgement = _judgement(judge(opportunity, detail))
        record = {
            "schema_version": 1,
            "provider": provider,
            "opportunity_id": opportunity_id,
            "source_url": source_url,
            "title": title,
            "currency": currency,
            "source_hash": inspected_source_hash,
            "observed_at": observed_at,
            "decision": judgement["decision"],
            "reasons": judgement["reasons"],
            "evidence_refs": judgement["evidence_refs"],
            "next_action": judgement["next_action"],
            "idempotency_key": f"marketplace-opportunity:v1:{provider}:{opportunity_id}:{inspected_source_hash}",
        }
        try:
            persistence = store.record(record)
        except Exception as error:
            raise OpportunityDiscoveryError("observation_persist_failed") from error
        if not isinstance(persistence, Mapping) or persistence.get("status") not in {"appended", "duplicate"}:
            raise OpportunityDiscoveryError("observation_persist_result_invalid")
        summary["inspected"] += 1
        if persistence["status"] == "appended":
            summary["persisted"] += 1
        else:
            summary["duplicates"] += 1
        summary["eligible" if judgement["decision"] == "eligible" else "held"] += 1
        summary["next_actions"].append({
            "provider": provider,
            "opportunity_id": opportunity_id,
            "decision": judgement["decision"],
            "next_action": judgement["next_action"],
        })
    return summary


__all__ = ["OpportunityDiscoveryError", "run_opportunity_discovery"]
