"""G001-G006 bounded governance preparation, with no live authority or effects.

Reuse Manager's offline authority verifier, policy learner and audit store.
These contracts do not establish a legal charter, an external auditor, executed
API permission or universal impact. Standing authority is checked, never issued.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import re
from types import MappingProxyType
from typing import Mapping

from .audit import AuditTrail
from .authority import AuthorityVerifier, Grant
from .learning import PolicyLearner
from .models.source import Source, _aware, _text, _url
from .outcome_bench import (
    GeneralizationDecision, HoldoutEvaluation, PopulationScope, PortfolioSummary,
    assess_target, _currency, _minor, _number,
)


STOP_CONDITIONS = frozenset({"operator_stop", "unknown_effect", "harm", "authority_revoked", "out_of_distribution"})
INCIDENT_OUTCOMES = frozenset({"INEFFECTIVE", "WORSENED", "UNKNOWN", "HARM", "APPEAL", "RESOLVED"})


def _sha(value):
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("immutable lowercase SHA256 reference required")


def _texts(values, *, nonempty=False):
    if type(values) is not tuple or (nonempty and not values):
        raise ValueError("immutable explicit text collection required")
    for value in values:
        _text(value)
    if len(set(values)) != len(values):
        raise ValueError("duplicate references or scopes are not additional evidence")


@dataclass(frozen=True)
class PublicInterestCharter:
    charter_id: str
    version_sha256: str
    owner_id: str
    standing_grant: Grant
    budget_unit: str
    audit_url: str
    appeal_url: str
    stop_conditions: tuple[str, ...]

    def __post_init__(self):
        for value in (self.charter_id, self.owner_id, self.budget_unit):
            _text(value)
        _sha(self.version_sha256)
        if type(self.standing_grant) is not Grant or self.owner_id != self.standing_grant.issuer:
            raise ValueError("charter owner must be the independently checked grant issuer")
        _url(self.audit_url)
        _url(self.appeal_url)
        _texts(self.stop_conditions, nonempty=True)
        if not STOP_CONDITIONS <= set(self.stop_conditions):
            raise ValueError("operator, effect, harm, revocation and distribution stop rules required")


@dataclass(frozen=True)
class GovernanceDecision:
    status: str
    action: str
    can_execute: bool = False


def governance_preflight(*, charter: PublicInterestCharter, proposed_grant: Grant,
                         signature: str, verifier: AuthorityVerifier, cost: float,
                         at: datetime, assessment: GeneralizationDecision | None,
                         stopped: bool, unresolved_effects: int) -> GovernanceDecision:
    if (type(charter) is not PublicInterestCharter or type(proposed_grant) is not Grant
            or type(verifier) is not AuthorityVerifier):
        raise ValueError("typed charter, scoped proposal and existing authority verifier required")
    if type(stopped) is not bool:
        raise ValueError("explicit operator stop state required")
    _minor(unresolved_effects)
    _number(cost, nonnegative=True)
    _aware(at)

    def deny(reason):
        return GovernanceDecision(reason, "NO_ACTION")

    if stopped:
        return deny("OPERATOR_STOP")
    if unresolved_effects:
        return deny("UNKNOWN_EFFECT")
    if (type(assessment) is not GeneralizationDecision
            or assessment.status != "WITHIN_DECLARED_HOLDOUT"
            or assessment.action != "OFFLINE_CANDIDATE_ONLY"):
        return deny("EVALUATION_NOT_READY")
    original = charter.standing_grant
    scope_fields = ("grant_id", "issuer", "domain", "action", "target")
    if (any(getattr(original, name) != getattr(proposed_grant, name) for name in scope_fields)
            or proposed_grant.limit > original.limit
            or proposed_grant.not_before < original.not_before
            or proposed_grant.expires_at > original.expires_at):
        return deny("AUTHORITY_EXPANSION_BLOCKED")
    try:
        verifier.authorize(original, signature, proposed_grant.domain, proposed_grant.action,
                           proposed_grant.target, cost, at)
        if not proposed_grant.not_before <= at < proposed_grant.expires_at or cost > proposed_grant.limit:
            raise PermissionError("outside narrowed proposal")
    except (PermissionError, ValueError):
        return deny("GRANT_NOT_AUTHORIZED")
    return GovernanceDecision("OFFLINE_PREFLIGHT_PASSED", "OFFLINE_CANDIDATE_ONLY")


@dataclass(frozen=True)
class PolicyPromotion:
    promoted: bool
    active_version: str
    rollback_version: str
    can_execute: bool = False


def promote_offline_policy(learner: PolicyLearner, candidate_version: str, *, baseline_loss: float,
                           preflight: GovernanceDecision, rollback_version: str) -> PolicyPromotion:
    """Promote an isolated/heldout/shadow candidate only in the existing registry.

    The learner's persisted previous version and observe_loss implement rollback.
    No grant, budget, provider, runtime setting or live rollout is modified.
    """
    if type(learner) is not PolicyLearner or type(preflight) is not GovernanceDecision:
        raise ValueError("existing offline learner and typed preflight required")
    _text(candidate_version)
    _text(rollback_version)
    active = learner.active()
    if active != rollback_version or candidate_version == rollback_version:
        raise ValueError("actual current policy must remain the rollback target")
    promoted = False
    if preflight.status == "OFFLINE_PREFLIGHT_PASSED" and preflight.action == "OFFLINE_CANDIDATE_ONLY":
        promoted = learner.promote(candidate_version, baseline_loss=baseline_loss)
    return PolicyPromotion(promoted, learner.active(), rollback_version)


@dataclass(frozen=True)
class IncidentReport:
    run_id: str
    outcome: str
    reason: str
    evidence_sha256: str | None
    recorded_at: datetime

    def __post_init__(self):
        _text(self.run_id)
        _text(self.reason)
        if self.outcome not in INCIDENT_OUTCOMES:
            raise ValueError("explicit harm, ineffective, worsening, unknown or dispute event required")
        if self.evidence_sha256 is not None:
            _sha(self.evidence_sha256)
        _aware(self.recorded_at)


def record_incident(audit: AuditTrail, incident: IncidentReport) -> str:
    if type(audit) is not AuditTrail or type(incident) is not IncidentReport:
        raise ValueError("existing Manager audit trail and typed incident required")
    return audit.append(incident.run_id, "evaluation", {
        "status": incident.outcome, "reason": incident.reason,
        "evidence_refs": incident.evidence_sha256, "recorded_at": incident.recorded_at.isoformat(),
        "benefit_status": "NOT_MEASURED", "proof_level": "P0",
    })


@dataclass(frozen=True)
class IncidentInventory:
    events: Mapping[str, tuple[dict, ...]]
    counts: Mapping[str, int]
    chain_valid: bool
    external_audit_status: str = "NOT_PERFORMED"
    population_reconciled: bool | None = None
    missing_population_run_ids: tuple[str, ...] = ()
    unexpected_run_ids: tuple[str, ...] = ()
    missing_trace_run_ids: tuple[str, ...] = ()


def incident_inventory(audit: AuditTrail, run_ids: tuple[str, ...], *,
                       population_run_ids: tuple[str, ...] | None = None) -> IncidentInventory:
    """Count requested traces and optionally reconcile a declared finite population.

    The caller must obtain the population independently from execution/outbox
    records, never infer it from incident counts. Its authenticity and completeness
    are not established here. None leaves reconciliation unassessed; an explicit
    population permits an empty selection, including a declared empty population.
    Legacy calls without a population still require nonempty run_ids.

    True means only equal declared/requested IDs with valid nonempty traces. It
    proves neither complete outcome classification/receipts nor an external audit
    or world-wide absence of incidents. Events/counts and missing-trace IDs cover
    requested runs only; omitted population runs are reported without loading them.
    """
    if type(audit) is not AuditTrail:
        raise ValueError("existing Manager audit trail required")
    _texts(run_ids, nonempty=population_run_ids is None)
    if population_run_ids is not None:
        _texts(population_run_ids)
    events = {run_id: tuple(audit.trace(run_id)) for run_id in run_ids}
    counts = Counter(event["data"]["status"] for trace in events.values() for event in trace
                     if event["stage"] == "evaluation" and event["data"].get("status") in INCIDENT_OUTCOMES)
    chain_valid = all(audit.verify_chain(run_id) for run_id in run_ids)
    missing_traces = tuple(run_id for run_id, trace in events.items() if not trace)
    missing_population, unexpected = (), ()
    reconciled = None
    if population_run_ids is not None:
        requested, population = set(run_ids), set(population_run_ids)
        missing_population = tuple(run_id for run_id in population_run_ids if run_id not in requested)
        unexpected = tuple(run_id for run_id in run_ids if run_id not in population)
        reconciled = not missing_population and not unexpected and not missing_traces and chain_valid
    return IncidentInventory(MappingProxyType(events), MappingProxyType(dict(counts)),
                             chain_valid, population_reconciled=reconciled,
                             missing_population_run_ids=missing_population,
                             unexpected_run_ids=unexpected, missing_trace_run_ids=missing_traces)


@dataclass(frozen=True)
class CoverageInventory:
    decisions: Mapping[PopulationScope, GeneralizationDecision]
    unmeasured_domains: tuple[str, ...]
    inequalities: tuple[str, ...]
    failures: tuple[str, ...]
    next_questions: tuple[str, ...]
    universal_claim_allowed: bool = False
    human_welfare_status: str = "NOT_MEASURED"


def coverage_inventory(evaluation: HoldoutEvaluation, targets: tuple[PopulationScope, ...], *,
                       unmeasured_domains: tuple[str, ...], inequalities: tuple[str, ...],
                       failures: tuple[str, ...], next_questions: tuple[str, ...]) -> CoverageInventory:
    if (type(targets) is not tuple or not targets or any(type(t) is not PopulationScope for t in targets)
            or len(set(targets)) != len(targets)):
        raise ValueError("explicit distinct target populations required")
    for values in (unmeasured_domains, inequalities, failures, next_questions):
        _texts(values)
    if not next_questions:
        raise ValueError("finite evidence requires an explicit next unresolved question")
    decisions = {target: assess_target(evaluation, target) for target in targets}
    return CoverageInventory(MappingProxyType(decisions), unmeasured_domains, inequalities, failures, next_questions)


@dataclass(frozen=True)
class PublicAPIContract:
    contract_id: str
    counterpart_kind: str
    endpoint_url: str
    public_sources: tuple[Source, ...]
    permission_refs: tuple[str, ...]
    scope: tuple[str, str, str]
    budget_minor: int
    currency: str
    responsibility_owner: str

    def __post_init__(self):
        _text(self.contract_id)
        _text(self.responsibility_owner)
        if self.counterpart_kind not in {"oversight", "nonprofit", "municipality", "company", "researcher"}:
            raise ValueError("explicit integration counterpart category required")
        _url(self.endpoint_url)
        if (type(self.public_sources) is not tuple or not self.public_sources
                or any(type(s) is not Source for s in self.public_sources)
                or len({s.source_id for s in self.public_sources}) != len(self.public_sources)):
            raise ValueError("distinct rights-reviewed public source references required")
        _texts(self.permission_refs, nonempty=True)
        for url in self.permission_refs:
            _url(url)
        if type(self.scope) is not tuple or len(self.scope) != 3:
            raise ValueError("explicit domain, action and target scope required")
        for value in self.scope:
            _text(value)
        _minor(self.budget_minor)
        _currency(self.currency)


def api_contract_manifest(contract: PublicAPIContract) -> dict:
    if type(contract) is not PublicAPIContract:
        raise ValueError("typed connection-specific public API contract required")
    return {
        "schema": "manager.public-api.v1", "contract_id": contract.contract_id,
        "counterpart_kind": contract.counterpart_kind, "endpoint_url": contract.endpoint_url,
        "public_sources": [{"source_id": s.source_id, "url": s.url, "sha256": s.content_sha256,
                            "license_id": s.license_id, "rights": s.rights,
                            "privacy_class": s.privacy_class, "retrieved_at": s.retrieved_at.isoformat()}
                           for s in contract.public_sources],
        "permission_refs": list(contract.permission_refs), "scope": list(contract.scope),
        "budget_minor": contract.budget_minor, "currency": contract.currency,
        "responsibility_owner": contract.responsibility_owner,
        "permission_status": "DECLARED_NOT_AUTHENTICATED", "can_connect": False,
    }


@dataclass(frozen=True)
class OperatingCostModel:
    currency: str
    operating_minor: int | None
    ongoing_support_minor: int | None
    measurement_minor: int | None
    funding_minor: int | None
    company_revenue_minor: int | None

    def __post_init__(self):
        _currency(self.currency)
        for field in ("operating_minor", "ongoing_support_minor", "measurement_minor", "funding_minor", "company_revenue_minor"):
            _minor(getattr(self, field), optional=True)


@dataclass(frozen=True)
class OperatingCostReport:
    currency: str
    total_declared_cost_minor: int | None
    declared_company_margin_minor: int | None
    declared_cash_balance_delta_minor: int | None
    beneficiary_portfolio: PortfolioSummary
    missing_fields: tuple[str, ...]
    cumulative_human_benefit: None = None
    human_welfare_status: str = "NOT_MEASURED"


def evaluate_operating_model(model: OperatingCostModel, portfolio: PortfolioSummary) -> OperatingCostReport:
    if type(model) is not OperatingCostModel or type(portfolio) is not PortfolioSummary:
        raise ValueError("separate typed operating costs and beneficiary portfolio required")
    fields = ("operating_minor", "ongoing_support_minor", "measurement_minor", "funding_minor", "company_revenue_minor")
    missing = tuple(field for field in fields if getattr(model, field) is None)
    expenses = (model.operating_minor, model.ongoing_support_minor, model.measurement_minor)
    total = None if any(value is None for value in expenses) else sum(expenses)
    margin = None if total is None or model.company_revenue_minor is None else model.company_revenue_minor - total
    cash_delta = None if margin is None or model.funding_minor is None else margin + model.funding_minor
    return OperatingCostReport(model.currency, total, margin, cash_delta, portfolio, missing)
