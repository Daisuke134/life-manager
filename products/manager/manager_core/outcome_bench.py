"""Offline OutcomeBench contracts, never an authenticator or welfare certificate.

Reuse the existing score, source, split and potential-outcome implementations.
P1-P4 slots describe evidence supplied for review, not achieved proof levels.
A public URL, matching SHA256, different source name, or a complete packet does
not establish authenticity, independence, consent, clinical validity or causality.
No network, private records, execution permission, or publication is introduced.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import isfinite
import re
from types import MappingProxyType
from typing import Mapping

from .calibration import assert_disjoint_groups
from .evaluation import total_variation
from .models.source import Source, _text
from .potential_outcomes import oracle_ate


EVIDENCE_KINDS = frozenset({
    "simulation", "execution_receipt", "world_readback", "human_outcome",
    "causal_analysis", "preregistration", "costs", "harms", "sensitivity",
})
METRIC_KINDS = frozenset({"technical", "financial", "physical", "mental"})


def _number(value, *, optional=False, nonnegative=False):
    if optional and value is None:
        return None
    if (type(value) not in (int, float) or abs(value) > 10**15
            or not isfinite(value) or (nonnegative and value < 0)):
        raise ValueError("finite bounded numeric value required; unknown is not zero")
    return value


def _minor(value, *, optional=False):
    if optional and value is None:
        return None
    if type(value) is not int or not 0 <= value <= 10**15:
        raise ValueError("nonnegative integer minor units required")
    return value


def _currency(value):
    if type(value) is not str or re.fullmatch(r"[A-Z]{3}", value) is None:
        raise ValueError("explicit uppercase three-letter currency required")
    return value


@dataclass(frozen=True)
class PredictionMetrics:
    mae: float
    tvd: float | None
    sample_count: int
    proof_level: str = "P0"


def prediction_metrics(predicted, observed, predicted_distribution=None,
                       observed_distribution=None) -> PredictionMetrics:
    if (type(predicted) not in (tuple, list) or type(observed) not in (tuple, list)
            or not predicted or len(predicted) != len(observed)):
        raise ValueError("nonempty paired predictions and observations required")
    for value in (*predicted, *observed):
        _number(value)
    if (predicted_distribution is None) != (observed_distribution is None):
        raise ValueError("both distributions or neither are required")
    tvd = None if predicted_distribution is None else total_variation(
        predicted_distribution, observed_distribution)
    return PredictionMetrics(sum(abs(p - y) for p, y in zip(predicted, observed)) / len(predicted),
                             tvd, len(predicted))


@dataclass(frozen=True)
class EvidenceReference:
    source: Source
    subject_id: str
    kind: str
    metric_kind: str

    def __post_init__(self):
        if type(self.source) is not Source:
            raise ValueError("rights-reviewed public nonpersonal source reference required")
        _text(self.subject_id)
        if self.kind not in EVIDENCE_KINDS or self.metric_kind not in METRIC_KINDS:
            raise ValueError("explicit evidence and metric categories required")


@dataclass(frozen=True)
class EvidenceBundle:
    subject_id: str
    executor_source_id: str
    references: tuple[EvidenceReference, ...]

    def __post_init__(self):
        _text(self.subject_id)
        _text(self.executor_source_id)
        if type(self.references) is not tuple or any(type(r) is not EvidenceReference for r in self.references):
            raise ValueError("immutable typed evidence references required")
        if any(r.subject_id != self.subject_id for r in self.references):
            raise ValueError("evidence from a different intervention is not a match")
        if (len({r.source.source_id for r in self.references}) != len(self.references)
                or len({r.source.content_sha256.lower() for r in self.references}) != len(self.references)):
            raise ValueError("duplicate source/snapshot cannot inflate evidence")


@dataclass(frozen=True)
class EvidenceSlot:
    status: str
    reference_hashes: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceAssessment:
    levels: Mapping[str, EvidenceSlot]
    real_world_proof_level: str = "P0"
    human_welfare_status: str = "NOT_MEASURED"


def assess_evidence(bundle: EvidenceBundle, snapshots: Mapping[str, bytes] | None = None) -> EvidenceAssessment:
    """Check binding and byte consistency; never trust self-asserted verification.

    Source.verify_content checks only a supplied snapshot against a supplied
    hash. Even matching bytes remain unauthenticated. Genuine provider intake
    and an independently reviewed study are external prerequisites.
    """
    if type(bundle) is not EvidenceBundle:
        raise ValueError("typed intervention-bound evidence required")
    if snapshots is not None:
        sources = {r.source.source_id: r.source for r in bundle.references}
        if not isinstance(snapshots, Mapping) or not set(snapshots) <= set(sources):
            raise ValueError("snapshots must match declared sources")
        for source_id, payload in snapshots.items():
            sources[source_id].verify_content(payload)

    def slot(kind, *, human=False):
        refs = tuple(r for r in bundle.references if r.kind == kind)
        hashes = tuple(r.source.content_sha256.lower() for r in refs)
        if not refs:
            status = "MISSING"
        elif human and all(r.metric_kind == "technical" for r in refs):
            status = "PROXY_ONLY"
        elif all(r.source.source_id == bundle.executor_source_id for r in refs):
            status = "EXECUTOR_ONLY"
        elif not any(r.source.source_id != bundle.executor_source_id
                     and (not human or r.metric_kind != "technical") for r in refs):
            status = "INCOMPLETE"
        else:
            status = "UNAUTHENTICATED"
        return EvidenceSlot(status, hashes)

    levels = {"P0": EvidenceSlot("OFFLINE_ONLY", tuple(
        r.source.content_sha256.lower() for r in bundle.references if r.kind == "simulation")),
        "P1": slot("execution_receipt"), "P2": slot("world_readback"),
        "P3": slot("human_outcome", human=True)}
    causal_kinds = {"causal_analysis", "preregistration", "costs", "harms", "sensitivity"}
    causal_refs = tuple(r for r in bundle.references if r.kind in causal_kinds)
    complete = (causal_kinds <= {r.kind for r in causal_refs}
                and all(levels[p].status == "UNAUTHENTICATED" for p in ("P1", "P2", "P3")))
    levels["P4"] = EvidenceSlot("UNAUTHENTICATED" if complete else "INCOMPLETE",
                                tuple(r.source.content_sha256.lower() for r in causal_refs))
    return EvidenceAssessment(MappingProxyType(levels))


def reproduction_manifest(bundle: EvidenceBundle, *, code_version: str) -> dict:
    """Deterministic public metadata export; caller still owns publication rights.

    No raw snapshots are copied. This manifest can reproduce the unverified
    classification, not manufacture P1-P4 or authorize public distribution.
    """
    if type(code_version) is not str or re.fullmatch(r"[a-f0-9]{40}", code_version) is None:
        raise ValueError("immutable git commit version required")
    assessment = assess_evidence(bundle)
    return {
        "schema": "manager.outcome-bench.evidence.v1", "code_version": code_version,
        "subject_id": bundle.subject_id, "executor_source_id": bundle.executor_source_id,
        "references": [{
            "source_id": r.source.source_id, "url": r.source.url,
            "sha256": r.source.content_sha256.lower(), "retrieved_at": r.source.retrieved_at.isoformat(),
            "license_id": r.source.license_id, "rights": r.source.rights,
            "privacy_class": r.source.privacy_class, "kind": r.kind, "metric_kind": r.metric_kind,
        } for r in sorted(bundle.references, key=lambda r: r.source.source_id)],
        "assessment": {
            "levels": {p: {"status": s.status, "reference_hashes": sorted(s.reference_hashes)}
                       for p, s in assessment.levels.items()},
            "real_world_proof_level": assessment.real_world_proof_level,
            "human_welfare_status": assessment.human_welfare_status,
        },
    }


@dataclass(frozen=True)
class SyntheticCausalReference:
    unit: str
    control_outcomes: tuple[float, ...]
    treatment_outcomes: tuple[float, ...]

    def __post_init__(self):
        _text(self.unit)
        if (type(self.control_outcomes) is not tuple or type(self.treatment_outcomes) is not tuple
                or not self.control_outcomes or len(self.control_outcomes) != len(self.treatment_outcomes)):
            raise ValueError("paired synthetic potential outcomes required")
        for value in (*self.control_outcomes, *self.treatment_outcomes):
            _number(value)


@dataclass(frozen=True)
class CausalError:
    absolute_error: float | None
    status: str
    proof_level: str = "P0"


def causal_error(predicted_ate, unit: str,
                 reference: SyntheticCausalReference | EvidenceReference | None) -> CausalError:
    _number(predicted_ate)
    _text(unit)
    if reference is None:
        return CausalError(None, "REFERENCE_MISSING")
    if type(reference) is EvidenceReference:
        return CausalError(None, "EXTERNAL_REFERENCE_NOT_VALIDATED")
    if type(reference) is not SyntheticCausalReference or reference.unit != unit:
        raise ValueError("valid synthetic reference with matching outcome unit required")
    units = [{"id": str(i), "y0": y0, "y1": y1} for i, (y0, y1) in
             enumerate(zip(reference.control_outcomes, reference.treatment_outcomes))]
    return CausalError(abs(predicted_ate - oracle_ate(units)), "SYNTHETIC_REFERENCE_ONLY")


@dataclass(frozen=True)
class PopulationScope:
    country: str
    income_group: str
    domain: str
    period: str

    def __post_init__(self):
        for value in (self.country, self.income_group, self.domain, self.period):
            _text(value)
            if value.strip().lower() in {"*", "all", "world", "global", "unknown"}:
                raise ValueError("explicit bounded public population scope required")


@dataclass(frozen=True)
class HoldoutEvaluation:
    train_ids: tuple[str, ...]
    holdout_ids: tuple[str, ...]
    scopes: tuple[PopulationScope, ...]
    errors: tuple[float | None, ...]
    max_error: float
    public_scope: str
    error_metric: str | None = None
    error_unit: str | None = None

    def __post_init__(self):
        if any(type(values) is not tuple for values in (self.train_ids, self.holdout_ids, self.scopes, self.errors)):
            raise ValueError("immutable split and scope collections required")
        assert_disjoint_groups(self.train_ids, self.holdout_ids)
        if len(set(self.train_ids)) != len(self.train_ids) or len(set(self.holdout_ids)) != len(self.holdout_ids):
            raise ValueError("duplicate sample IDs are not independent observations")
        if (not self.scopes or len(self.scopes) != len(self.errors)
                or any(type(s) is not PopulationScope for s in self.scopes)
                or len(set(self.scopes)) != len(self.scopes)):
            raise ValueError("unique explicit evaluated scopes and paired errors required")
        for value in self.errors:
            _number(value, optional=True, nonnegative=True)
        _number(self.max_error, nonnegative=True)
        _text(self.public_scope)
        _text(self.error_metric)
        _text(self.error_unit)


@dataclass(frozen=True)
class GeneralizationDecision:
    action: str
    status: str
    error: float | None
    can_execute: bool = False
    error_metric: str | None = None
    error_unit: str | None = None


def assess_target(evaluation: HoldoutEvaluation, target: PopulationScope) -> GeneralizationDecision:
    if type(evaluation) is not HoldoutEvaluation or type(target) is not PopulationScope:
        raise ValueError("typed holdout and target scope required")
    def result(action, status, error):
        return GeneralizationDecision(action, status, error, False,
                                      evaluation.error_metric, evaluation.error_unit)
    if target not in evaluation.scopes:
        return result("NO_ACTION", "OUT_OF_DISTRIBUTION", None)
    error = evaluation.errors[evaluation.scopes.index(target)]
    if error is None:
        return result("NO_ACTION", "ERROR_UNKNOWN", None)
    if error > evaluation.max_error:
        return result("NO_ACTION", "ERROR_TOO_HIGH", error)
    return result("OFFLINE_CANDIDATE_ONLY", "WITHIN_DECLARED_HOLDOUT", error)


@dataclass(frozen=True)
class PortfolioEntry:
    case_id: str
    scope: PopulationScope
    metric: str
    unit: str
    effect: float | None
    lower: float | None
    upper: float | None
    cost_minor: int | None
    currency: str
    harms: float | None
    harm_metric: str | None = None
    harm_unit: str | None = None

    def __post_init__(self):
        for value in (self.case_id, self.metric, self.unit):
            _text(value)
        if type(self.scope) is not PopulationScope:
            raise ValueError("explicit scope required")
        for value in (self.effect, self.lower, self.upper):
            _number(value, optional=True)
        if self.effect is None:
            if self.lower is not None or self.upper is not None:
                raise ValueError("missing effect cannot have a confidence interval")
        elif (self.lower is None) != (self.upper is None):
            raise ValueError("complete interval or explicit unknown required")
        elif self.lower is not None and not self.lower <= self.effect <= self.upper:
            raise ValueError("effect must lie within supplied interval")
        _minor(self.cost_minor, optional=True)
        _currency(self.currency)
        _number(self.harms, optional=True, nonnegative=True)
        if self.harms is not None or self.harm_metric is not None or self.harm_unit is not None:
            _text(self.harm_metric)
            _text(self.harm_unit)


@dataclass(frozen=True)
class PortfolioSummary:
    entries: tuple[PortfolioEntry, ...]
    counts: Mapping[str, int]
    costs_by_currency: Mapping[str, int | None]
    cumulative_welfare: None = None
    human_welfare_status: str = "NOT_MEASURED"


def summarize_portfolio(entries: tuple[PortfolioEntry, ...]) -> PortfolioSummary:
    if type(entries) is not tuple or any(type(e) is not PortfolioEntry for e in entries):
        raise ValueError("immutable typed portfolio required")
    if len({e.case_id for e in entries}) != len(entries):
        raise ValueError("duplicate intervention cannot inflate portfolio")
    counts = Counter({"POSITIVE_ESTIMATE": 0, "NEGATIVE_ESTIMATE": 0, "NULL_ESTIMATE": 0, "UNKNOWN": 0})
    costs = {}
    for row in entries:
        # These are signs of supplied estimates, not verified welfare claims.
        status = "UNKNOWN"
        if row.lower is not None:
            if row.upper < 0:
                status = "NEGATIVE_ESTIMATE"
            elif row.lower > 0 and row.harms is not None:
                status = "POSITIVE_ESTIMATE"
            elif row.lower == row.upper == 0 and row.harms is not None:
                status = "NULL_ESTIMATE"
        counts[status] += 1
        if row.cost_minor is None or (row.currency in costs and costs[row.currency] is None):
            costs[row.currency] = None
        else:
            costs[row.currency] = costs.get(row.currency, 0) + row.cost_minor
    # No effect total: even matching units may have overlapping populations,
    # different denominators or incompatible estimands.
    return PortfolioSummary(entries, MappingProxyType(dict(counts)), MappingProxyType(costs))

# Same OutcomeBench facade; scoring implementation stays focused and reusable.
from .collaboration_evaluation import ScenarioCase, ValidationResult, ScoreVector, score_case
