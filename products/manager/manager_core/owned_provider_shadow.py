"""Explicit opt-in P0 shadow comparison for verified public catalog corrections.

This caller reuses the existing catalog planner, static handoff validation,
baselines, and checkpointed provider. Its records never grant publisher authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import math
import time

from .ampersand_api import DEFAULT_INSTRUCTIONS, MODEL, SessionFailure
from .candidate_verification import TechnicalAssessment, TechnicalCriteria
from .collaboration import advisory_receipt, render_prompt
from .digital_handoff import OwnedChangeContext, prepare_owned_change
from .owned_checkpoint import CheckpointUnavailable, PrivateCheckpoint
from .owned_provider import CheckpointedProvider
from .provider_budget import BudgetExceeded
from .provider_sessions import SessionConflict
from . import collaboration_baselines
from . import owned_catalog_planner

_SCHEMA = "manager.catalog-shadow.v1"
_ALLOWED_ACTIONS = frozenset({"CORRECT_LINK", "IMPROVE_ACCESSIBILITY"})


def _record(status, reason, run_id, **fields):
    return {
        **fields,
        "schema": _SCHEMA,
        "status": status,
        "reason": reason,
        "run_id": run_id,
        "proof_level": "P0",
        "authorized_execution": False,
        "causal_support": False,
        "human_outcome": "NOT_MEASURED",
        "action_writes": 0,
        "settled_cost_usd": None,
    }


def _canonical_operation(context, assessment):
    criteria = context.criteria
    sources = sorted((source.source_id, source.url, source.content_sha256.lower())
                     for source in criteria.official_sources)
    payload = {
        "protocol": _SCHEMA,
        "model": MODEL,
        "instructions": DEFAULT_INSTRUCTIONS,
        "baseline_digest": assessment.baseline_digest,
        "candidate_digest": assessment.candidate_digest,
        "criteria_version": criteria.version,
        "action": criteria.candidate.action,
        "target": criteria.candidate.target,
        "sources": [list(row) for row in sources],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False)
    return "catalog_shadow_" + sha256(canonical.encode("utf-8")).hexdigest()


def _source_records(context):
    return [{"source_id": source.source_id, "url": source.url,
             "content_sha256": source.content_sha256.lower()}
            for source in sorted(context.criteria.official_sources,
                                 key=lambda item: (item.source_id, item.url, item.content_sha256))]


def _base_fields(context, assessment, prompt, operation_id):
    return {
        "operation_id": operation_id,
        "context_sha256": sha256(prompt.encode("utf-8")).hexdigest(),
        "baseline_digest": assessment.baseline_digest,
        "candidate_digest": assessment.candidate_digest,
        "candidate": {"action": context.criteria.candidate.action,
                      "target": context.criteria.candidate.target},
        "sources": _source_records(context),
    }


def run_catalog_shadow(checkpoint, client, checkout, workspace, source_commit, *,
                       run_id: str, enabled: bool = False, cap_usd: Decimal,
                       upper_usd: Decimal, deadline_monotonic: float) -> dict:
    """Run one opt-in comparison for a source- and browser-verified legacy fix.

    `checkpoint` must be the caller's already acquired exact PrivateCheckpoint.
    No identity, lease, provider client, planner history clock, or publisher
    packet is created by this function.
    """
    if type(enabled) is not bool:
        raise ValueError("exact boolean opt-in required")
    if not enabled:
        return _record("SKIPPED", "DISABLED", run_id)
    if (type(run_id) is not str or not run_id.isdecimal() or run_id.startswith("0")
            or type(cap_usd) is not Decimal or not cap_usd.is_finite()
            or type(upper_usd) is not Decimal or not upper_usd.is_finite()
            or type(deadline_monotonic) not in (int, float)
            or not math.isfinite(deadline_monotonic)):
        raise ValueError("bounded run, finite Decimal limits, and absolute deadline required")
    if (type(checkpoint) is not PrivateCheckpoint or checkpoint.db is None
            or checkpoint.revision is None or checkpoint.broken):
        raise CheckpointUnavailable("active acquired private checkpoint required")
    if time.monotonic() >= deadline_monotonic:
        return _record("SKIPPED", "DEADLINE_EXPIRED", run_id)

    planning_now = datetime.now(timezone.utc)
    try:
        planned = owned_catalog_planner.plan_catalog_change(
            checkout, workspace, source_commit, planning_now, run_id=run_id)
    except CheckpointUnavailable:
        raise
    except Exception:
        return _record("UNKNOWN", "PLANNER_UNCERTAIN", run_id)
    after_planning = datetime.now(timezone.utc)
    if planned is None:
        return _record("SKIPPED", "NO_CANDIDATE", run_id)
    if (type(planned) is not tuple or len(planned) != 3
            or type(planned[0]) is not OwnedChangeContext
            or type(planned[1]) is not TechnicalAssessment):
        return _record("SKIPPED", "UNSUPPORTED_CONTEXT", run_id)
    context, assessment, scope = planned
    if (type(context.criteria) is not TechnicalCriteria
            or context.criteria.candidate.action not in _ALLOWED_ACTIONS):
        return _record("SKIPPED", "UNSUPPORTED_ACTION", run_id)
    try:
        prepared = prepare_owned_change(context, assessment, scope, after_planning,
                                        schema="manager.digital-handoff.v2")
        prompt = render_prompt(context.planner, fictional=False)
    except Exception:
        return _record("SKIPPED", "CONTEXT_REVALIDATION_FAILED", run_id)
    if prepared.status != "PREPARED_PLATFORM_AUTHORITY_REQUIRED":
        return _record("SKIPPED", "CONTEXT_REVALIDATION_FAILED", run_id)
    fields = _base_fields(context, assessment, prompt,
                          _canonical_operation(context, assessment))
    fields.update({
        "baseline": {
            "no_action": advisory_receipt(collaboration_baselines.no_action_baseline(context.planner)),
            "rules": advisory_receipt(collaboration_baselines.rule_baseline(context.planner)),
        },
        "provider": None,
        "model_comparison": None,
    })
    if time.monotonic() >= deadline_monotonic:
        return _record("SKIPPED", "DEADLINE_EXPIRED", run_id, **fields)

    try:
        owner = CheckpointedProvider(checkpoint, cap_usd=cap_usd)
        try:
            intent = owner.journal.get(fields["operation_id"])
        except SessionConflict:
            intent = None
        if intent is not None:
            fields["provider"] = {"session_id": intent.session_id,
                                   "turn_id": None, "status": intent.status,
                                   "input_tokens": None, "output_tokens": None}
            return _record("SKIPPED", "PRIOR_INTENT_RECONCILIATION_REQUIRED", run_id, **fields)
        advice = owner.initial(client, context.planner,
                               request_id=fields["operation_id"],
                               upper_usd=upper_usd,
                               deadline_monotonic=deadline_monotonic)
    except CheckpointUnavailable:
        raise
    except BudgetExceeded:
        if checkpoint.broken:
            raise CheckpointUnavailable("private checkpoint fenced; reconcile only")
        return _record("SKIPPED", "BUDGET_EXCEEDED", run_id, **fields)
    except SessionFailure:
        if checkpoint.broken:
            raise CheckpointUnavailable("private checkpoint fenced; reconcile only")
        intent = None
        try:
            intent = owner.journal.get(fields["operation_id"])
        except SessionConflict:
            pass
        fields["provider"] = {"session_id": intent.session_id if intent else None,
                              "turn_id": None,
                              "status": intent.status if intent else "UNKNOWN",
                              "input_tokens": None, "output_tokens": None}
        return _record("UNKNOWN", "PROVIDER_TRANSPORT_UNKNOWN", run_id, **fields)

    evidence = advice.evidence
    fields["provider"] = {
        "session_id": evidence.session_id,
        "turn_id": evidence.turn_id,
        "status": evidence.status,
        "input_tokens": evidence.input_tokens,
        "output_tokens": evidence.output_tokens,
    }
    if advice.advice.status == "INVALID_MODEL_OUTPUT":
        fields["model_status"] = "INVALID_MODEL_OUTPUT"
    else:
        model_receipt = advisory_receipt(advice.advice)
        fields["model_status"] = advice.advice.status
        fields["model_advice"] = model_receipt
        fields["model_comparison"] = {
            "no_action_same_decision": model_receipt["decision"] == fields["baseline"]["no_action"]["decision"],
            "rules_same_decision": model_receipt["decision"] == fields["baseline"]["rules"]["decision"],
        }
    return _record("COMPARED_P0", "MODEL_RESPONSE_PARSED", run_id, **fields)
