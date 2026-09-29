"""Fail-closed promotion gate for the marketplace Meta Loop.

The Meta Loop may discover and score candidates, but it must not register a
provider owner from a name, a stale snapshot, or a successful local test.  A
provider is promotable only when policy, the thin shared-contract adapter,
funded work, an official canary readback, replay-zero, and measured positive
net economics are all present in one candidate record.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Mapping


_HASH = re.compile(r"^[0-9a-f]{64}$")
_PROVIDER = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")
_CANDIDATE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_RECEIPT = re.compile(r"^provider-receipt://[^/]+/[^/]+$")
_DISCOVERY_ITEM_FIELDS = frozenset({
    "candidate", "candidate_id", "observed_at", "source_url", "snapshot_sha256",
    "evidence_refs",
})
REQUIRED_ACTIONS = (
    "discover",
    "inspect",
    "propose",
    "message",
    "accept_offer",
    "deliver",
    "read_payments",
    "read_payouts",
)
_CANDIDATE_FIELDS = frozenset({
    "version", "provider", "policy", "adapter", "funded_work", "canary",
    "unit_economics",
})


class EnrollmentError(ValueError):
    """The candidate envelope is malformed and cannot be evaluated safely."""


def _mapping(value: Any, reason: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EnrollmentError(reason)
    return value


def _text(value: Any, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EnrollmentError(reason)
    return value.strip()


def _timestamp(value: Any, reason: str) -> str:
    text = _text(value, reason)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise EnrollmentError(reason) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EnrollmentError(reason)
    return text


def _receipt(value: Any, reason: str, provider: str | None = None) -> str:
    text = _text(value, reason)
    if _RECEIPT.fullmatch(text) is None:
        raise EnrollmentError(reason)
    if provider is not None:
        observed_provider = text[len("provider-receipt://"):].split("/", 1)[0]
        if observed_provider != provider:
            raise EnrollmentError("receipt_provider_mismatch")
    return text


def _hash(value: Any, reason: str) -> str:
    text = _text(value, reason)
    if _HASH.fullmatch(text) is None:
        raise EnrollmentError(reason)
    return text


def _validate_envelope(candidate: Mapping[str, Any]) -> str:
    if set(candidate) != _CANDIDATE_FIELDS or candidate.get("version") != 1:
        raise EnrollmentError("candidate_fields_invalid")
    provider = _text(candidate.get("provider"), "provider_invalid")
    if _PROVIDER.fullmatch(provider) is None:
        raise EnrollmentError("provider_invalid")
    return provider


def _gate_policy(raw: Any) -> tuple[str, list[str]]:
    policy = _mapping(raw, "policy_invalid")
    if set(policy) != {"status", "source_url", "observed_at"}:
        raise EnrollmentError("policy_invalid")
    status = _text(policy.get("status"), "policy_invalid")
    source = _text(policy.get("source_url"), "policy_invalid")
    if not source.startswith("https://"):
        raise EnrollmentError("policy_invalid")
    _timestamp(policy.get("observed_at"), "policy_invalid")
    return ("pass", []) if status == "allowed" else ("fail", ["policy_not_allowed"])


def _gate_adapter(raw: Any) -> tuple[str, list[str]]:
    adapter = _mapping(raw, "adapter_invalid")
    if set(adapter) != {"contract", "actions", "source_sha256"}:
        raise EnrollmentError("adapter_invalid")
    if adapter.get("contract") != "marketplace-core-v1":
        return "fail", ["adapter_contract_invalid"]
    actions = adapter.get("actions")
    if not isinstance(actions, list) or any(not isinstance(item, str) for item in actions):
        raise EnrollmentError("adapter_invalid")
    if tuple(actions) != REQUIRED_ACTIONS:
        return "fail", ["adapter_actions_incomplete"]
    _hash(adapter.get("source_sha256"), "adapter_invalid")
    return "pass", []


def _gate_funded_work(raw: Any, provider: str) -> tuple[str, list[str]]:
    funded = _mapping(raw, "funded_work_invalid")
    if set(funded) != {"status", "receipt_ref", "observed_at"}:
        raise EnrollmentError("funded_work_invalid")
    status = _text(funded.get("status"), "funded_work_invalid")
    _receipt(funded.get("receipt_ref"), "funded_work_invalid", provider)
    _timestamp(funded.get("observed_at"), "funded_work_invalid")
    return ("pass", []) if status == "funded" else ("fail", ["funded_work_missing"])


def _gate_canary(raw: Any, provider: str) -> tuple[str, list[str]]:
    canary = _mapping(raw, "canary_invalid")
    if set(canary) != {"status", "official_receipt_ref", "replay_zero", "observed_at"}:
        raise EnrollmentError("canary_invalid")
    reasons: list[str] = []
    if _text(canary.get("status"), "canary_invalid") != "verified":
        reasons.append("canary_not_verified")
    if canary.get("official_receipt_ref") is None:
        reasons.append("canary_receipt_missing")
    else:
        _receipt(canary.get("official_receipt_ref"), "canary_invalid", provider)
    if canary.get("replay_zero") is not True:
        reasons.append("replay_not_zero")
    _timestamp(canary.get("observed_at"), "canary_invalid")
    return ("pass", []) if not reasons else ("fail", reasons)


def _gate_unit_economics(raw: Any) -> tuple[str, list[str]]:
    economics = _mapping(raw, "unit_economics_invalid")
    if set(economics) != {"status", "net_amount_minor", "currency", "evidence_refs"}:
        raise EnrollmentError("unit_economics_invalid")
    reasons: list[str] = []
    if _text(economics.get("status"), "unit_economics_invalid") != "measured":
        reasons.append("economics_not_measured")
    net = economics.get("net_amount_minor")
    if type(net) is not int:
        raise EnrollmentError("unit_economics_invalid")
    if net <= 0:
        reasons.append("net_not_positive")
    currency = _text(economics.get("currency"), "unit_economics_invalid")
    if _CURRENCY.fullmatch(currency) is None:
        raise EnrollmentError("unit_economics_invalid")
    refs = economics.get("evidence_refs")
    if not isinstance(refs, list) or not refs or any(
        not isinstance(item, str) or not item.strip() for item in refs
    ):
        raise EnrollmentError("unit_economics_invalid")
    return ("pass", []) if not reasons else ("fail", reasons)


def evaluate_platform_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate one discovered platform without opening a provider transport."""

    candidate = _mapping(candidate, "candidate_fields_invalid")
    provider = _validate_envelope(candidate)
    gates: dict[str, str] = {}
    reasons: list[str] = []
    for name, checker in (
        ("policy", lambda raw: _gate_policy(raw)),
        ("adapter", lambda raw: _gate_adapter(raw)),
        ("funded_work", lambda raw: _gate_funded_work(raw, provider)),
        ("canary", lambda raw: _gate_canary(raw, provider)),
        ("unit_economics", lambda raw: _gate_unit_economics(raw)),
    ):
        status, gate_reasons = checker(candidate[name])
        gates[name] = status
        reasons.extend(gate_reasons)
    decision = "promote" if not reasons else "hold"
    return {
        "provider": provider,
        "decision": decision,
        "owner_registration_allowed": decision == "promote",
        "gates": gates,
        "reasons": reasons,
    }


def evaluate_and_record_candidate(
    candidate: Mapping[str, Any],
    store: Any,
    *,
    candidate_id: str,
    observed_at: str,
    source_url: str,
    snapshot_sha256: str,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Evaluate a candidate and persist only the resulting state envelope.

    ``store`` is deliberately a tiny dependency with one ``record`` method.
    The function does not know how to discover, register, or contact a
    provider; a store implementation may only persist the already-evaluated
    evidence.
    """

    evaluation = evaluate_platform_candidate(candidate)
    candidate_id = _text(candidate_id, "candidate_id_invalid")
    if _CANDIDATE_ID.fullmatch(candidate_id) is None:
        raise EnrollmentError("candidate_id_invalid")
    observed_at = _timestamp(observed_at, "observed_at_invalid")
    source_url = _text(source_url, "source_url_invalid")
    if not source_url.startswith("https://"):
        raise EnrollmentError("source_url_invalid")
    snapshot_sha256 = _hash(snapshot_sha256, "snapshot_sha256_invalid")
    if evidence_refs is None:
        evidence_refs = []
    if not isinstance(evidence_refs, list) or any(
        not isinstance(item, str) or not item.strip() for item in evidence_refs
    ):
        raise EnrollmentError("evidence_refs_invalid")
    record = {
        "schema_version": 1,
        "provider": evaluation["provider"],
        "candidate_id": candidate_id,
        "observed_at": observed_at,
        "source_url": source_url,
        "snapshot_sha256": snapshot_sha256,
        "decision": evaluation["decision"],
        "gates": evaluation["gates"],
        "reasons": evaluation["reasons"],
        "evidence_refs": [item.strip() for item in evidence_refs],
        "next_action": (
            "provision_owner_after_release_readback"
            if evaluation["decision"] == "promote"
            else "collect_missing_gates"
        ),
        "idempotency_key": (
            f"marketplace-candidate:v1:{evaluation['provider']}:{candidate_id}:{snapshot_sha256}"
        ),
    }
    try:
        record_result = store.record(record)
    except AttributeError as error:
        raise EnrollmentError("candidate_store_invalid") from error
    return {"evaluation": evaluation, "persistence": record_result}


def run_discovery_cycle(
    sources: Mapping[str, Any],
    store: Any,
    *,
    max_candidates_per_source: int = 50,
) -> dict[str, Any]:
    """Run bounded, read-only discovery sources and persist their evaluations.

    Each source returns mappings containing a candidate envelope plus its
    observation metadata.  This orchestrator never calls a provider mutation
    operation; source failures are typed in the summary and other sources may
    still be processed safely.
    """

    if not isinstance(sources, Mapping):
        raise EnrollmentError("discovery_sources_invalid")
    if type(max_candidates_per_source) is not int or not 1 <= max_candidates_per_source <= 1000:
        raise EnrollmentError("discovery_bound_invalid")
    if any(not isinstance(name, str) or not name.strip() for name in sources):
        raise EnrollmentError("discovery_source_invalid")
    summary: dict[str, Any] = {
        "status": "ok",
        "sources": len(sources),
        "inspected": 0,
        "persisted": 0,
        "duplicates": 0,
        "promoted": 0,
        "held": 0,
        "source_errors": [],
        "next_actions": [],
    }
    for source_name in sorted(sources):
        source_label = _text(source_name, "discovery_source_invalid")
        discover = sources[source_name]
        if not callable(discover):
            raise EnrollmentError("discovery_source_invalid")
        try:
            iterable = discover()
            iterator = iter(iterable)
        except Exception as error:
            summary["source_errors"].append({
                "source": source_label,
                "error_class": type(error).__name__,
                "next_action": "retry_source_read_only",
            })
            continue
        for index in range(max_candidates_per_source + 1):
            try:
                item = next(iterator)
            except StopIteration:
                break
            except Exception as error:
                summary["source_errors"].append({
                    "source": source_label,
                    "error_class": type(error).__name__,
                    "next_action": "retry_source_read_only",
                })
                break
            if index >= max_candidates_per_source:
                raise EnrollmentError("discovery_bound_exceeded")
            if (
                not isinstance(item, Mapping)
                or not set(item).issubset(_DISCOVERY_ITEM_FIELDS)
                or not {"candidate", "candidate_id", "observed_at", "source_url", "snapshot_sha256"}
                .issubset(item)
            ):
                raise EnrollmentError("discovery_item_invalid")
            result = evaluate_and_record_candidate(
                item["candidate"],
                store,
                candidate_id=item["candidate_id"],
                observed_at=item["observed_at"],
                source_url=item["source_url"],
                snapshot_sha256=item["snapshot_sha256"],
                evidence_refs=item.get("evidence_refs"),
            )
            summary["inspected"] += 1
            persistence_status = result["persistence"].get("status")
            if persistence_status == "appended":
                summary["persisted"] += 1
            elif persistence_status == "duplicate":
                summary["duplicates"] += 1
            else:
                raise EnrollmentError("candidate_store_result_invalid")
            decision = result["evaluation"]["decision"]
            summary["promoted" if decision == "promote" else "held"] += 1
            summary["next_actions"].append({
                "provider": result["evaluation"]["provider"],
                "candidate_id": item["candidate_id"],
                "decision": decision,
                "next_action": result["persistence"]["record"]["next_action"],
            })
    if summary["source_errors"]:
        summary["status"] = "partial"
    elif summary["inspected"] == 0:
        summary["status"] = "empty"
    return summary


__all__ = [
    "EnrollmentError",
    "REQUIRED_ACTIONS",
    "evaluate_platform_candidate",
    "evaluate_and_record_candidate",
    "run_discovery_cycle",
]
