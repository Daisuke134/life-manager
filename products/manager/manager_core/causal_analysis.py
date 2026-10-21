"""Optional DoWhy 0.14 diagnostics for independent public aggregate units.

This is a deliberately narrow adapter: binary assignment, one pretreatment
baseline in the outcome's units, and DoWhy's existing linear adjustment, interval,
placebo and unobserved-confounding sensitivity methods. No estimator is invented
here. Repeated/clustered observations need a separately justified estimator.
Supplied provenance is never authenticated by this module; all outputs remain P0.
"""
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from importlib.metadata import version
import json
import warnings

from manager_core.models.source import Source, _aware, _text
from manager_core.outcome_bench import _currency, _minor, _number


def _optional_source(source):
    if source is not None and not isinstance(source, Source):
        raise ValueError("public nonpersonal Source or explicit unknown required")


def _endpoint(domain, metric, unit):
    if domain not in ("financial", "physical", "mental"):
        raise ValueError("separate financial, physical or mental endpoint required")
    _text(metric)
    _text(unit)


@dataclass(frozen=True)
class CausalAnalysisPlan:
    study_id: str
    domain: str
    metric: str
    unit: str
    analysis_unit: str
    started_at: datetime
    ended_at: datetime
    protocol: Source | None
    min_per_arm: int
    placebo_tolerance: float
    minimum_robustness: float
    confidence_level: float = .95
    overlap_min: float = .05
    simulations: int = 100
    random_seed: int = 42

    def __post_init__(self):
        _text(self.study_id)
        _text(self.analysis_unit)
        _endpoint(self.domain, self.metric, self.unit)
        _aware(self.started_at)
        _aware(self.ended_at)
        if self.started_at >= self.ended_at:
            raise ValueError("ordered observation window required")
        _optional_source(self.protocol)
        if type(self.min_per_arm) is not int or self.min_per_arm < 3:
            raise ValueError("predeclared minimum of at least three independent units per arm required")
        _number(self.placebo_tolerance, nonnegative=True)
        _number(self.minimum_robustness, nonnegative=True)
        _number(self.confidence_level)
        _number(self.overlap_min)
        if not (0 <= self.minimum_robustness <= 1 and .5 < self.confidence_level < 1 and 0 < self.overlap_min < .5):
            raise ValueError("valid confidence, overlap and robustness thresholds required")
        if type(self.simulations) is not int or not 20 <= self.simulations <= 1000:
            raise ValueError("20–1000 placebo simulations required")
        if type(self.random_seed) is not int or not 0 <= self.random_seed < 2**32:
            raise ValueError("bounded explicit random seed required")


@dataclass(frozen=True)
class CausalObservation:
    unit_id: str
    assigned: int
    outcome: float | None
    baseline: float | None
    propensity: float | None

    def __post_init__(self):
        _text(self.unit_id)
        if type(self.assigned) is not int or self.assigned not in (0, 1):
            raise ValueError("binary integer assignment required")
        _number(self.outcome, optional=True)
        _number(self.baseline, optional=True)
        _number(self.propensity, optional=True)
        if self.propensity is not None and not 0 <= self.propensity <= 1:
            raise ValueError("assignment probability must be in [0,1] or unknown")


@dataclass(frozen=True)
class CausalDataset:
    study_id: str
    domain: str
    metric: str
    unit: str
    observations: tuple[CausalObservation, ...]
    source: Source | None
    kind: str = "synthetic"

    def __post_init__(self):
        _text(self.study_id)
        _endpoint(self.domain, self.metric, self.unit)
        if not isinstance(self.observations, tuple) or any(not isinstance(row, CausalObservation) for row in self.observations):
            raise ValueError("typed immutable observation tuple required")
        if len({row.unit_id for row in self.observations}) != len(self.observations):
            raise ValueError("duplicate analytical units cannot masquerade as independent samples")
        _optional_source(self.source)
        if self.kind not in ("synthetic", "declared_public_aggregate"):
            raise ValueError("input kind cannot self-assert verified human outcomes")


@dataclass(frozen=True)
class CausalSafety:
    cost_minor: int | None
    currency: str | None
    cost_source: Source | None
    harm_value: float | None
    harm_metric: str | None
    harm_unit: str | None
    harm_source: Source | None

    def __post_init__(self):
        _minor(self.cost_minor, optional=True)
        if self.currency is not None:
            _currency(self.currency)
        if self.cost_minor is not None and self.currency is None:
            raise ValueError("known cost needs currency")
        _number(self.harm_value, optional=True, nonnegative=True)
        if self.harm_value is not None:
            _text(self.harm_metric)
            _text(self.harm_unit)
        _optional_source(self.cost_source)
        _optional_source(self.harm_source)


def _snapshot(values):
    return json.dumps(values, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def plan_snapshot(plan: CausalAnalysisPlan) -> bytes:
    """Canonical declared plan bytes, for binding its source hash to parameters."""
    values = asdict(plan)
    values.pop("protocol")
    values["started_at"] = plan.started_at.isoformat()
    values["ended_at"] = plan.ended_at.isoformat()
    values["assumptions"] = ["independent_aggregate_units", "no_interference", "baseline_pretreatment_same_unit",
                             "linear_additive_model", "baseline_sufficient_for_adjustment"]
    values["engine"] = "dowhy==0.14/backdoor.linear_regression"
    values["sensitivity_benchmark_fraction"] = .1
    return _snapshot(values)


def dataset_snapshot(data: CausalDataset) -> bytes:
    """Canonical public aggregate export; a hash match is consistency, not truth."""
    values = asdict(data)
    values.pop("source")
    return _snapshot(values)


@dataclass(frozen=True)
class CausalAnalysisResult:
    study_id: str
    domain: str
    metric: str
    unit: str
    observation_count: int
    status: str
    reasons: tuple[str, ...]
    sources: tuple[Source, ...]
    safety: CausalSafety | None
    harms_status: str
    cost_status: str
    overlap_status: str
    estimate: float | None = None
    confidence_interval: tuple[float, float] | None = None
    confidence_level: float | None = None
    placebo_effect: float | None = None
    robustness_value: float | None = None
    engine_version: str | None = None
    engine_error: str | None = None
    engine_warnings: tuple[str, ...] = ()
    measurement_authentication: str = "NOT_VERIFIED"
    human_welfare_status: str = "NOT_MEASURED"
    power_status: str = "NOT_ESTABLISHED"
    proof_level: str = "P0"
    action: str = "NO_ACTION"
    verified_causal_effect: None = None
    net_benefit: None = None


def _load_engine():
    # Lazy imports keep all ordinary Manager paths standard-library only.
    import dowhy
    import numpy as np
    import pandas as pd
    if version("dowhy") != "0.14":
        raise ImportError("only pinned DoWhy 0.14 is validated")
    return dowhy, np, pd


def analyze_causal_study(plan: CausalAnalysisPlan, data: CausalDataset, *, safety: CausalSafety | None = None):
    """Calculate bounded diagnostics without authorizing action or P3/P4 claims.

    All study fields, thresholds and exported observations bind to supplied source
    hashes. There is no authentication backend. Missing outcomes are not deleted,
    assumed random, or imputed; known quantities can be analyzed but never certify
    net welfare. Propensity/range checks are necessary diagnostics, not proof of
    joint positivity, randomization, baseline timing or sufficient adjustment.
    """
    if not isinstance(plan, CausalAnalysisPlan) or not isinstance(data, CausalDataset):
        raise ValueError("typed analysis plan and dataset required")
    if safety is not None and not isinstance(safety, CausalSafety):
        raise ValueError("typed separate safety/cost record required")
    if (plan.study_id, plan.domain, plan.metric, plan.unit) != (data.study_id, data.domain, data.metric, data.unit):
        raise ValueError("dataset must match exact study, domain, metric and unit")
    preconditions = []
    if plan.protocol is None:
        preconditions.append("PROTOCOL_MISSING")
    else:
        plan.protocol.verify_content(plan_snapshot(plan))
        if plan.protocol.retrieved_at > plan.started_at:
            preconditions.append("PROTOCOL_NOT_PROSPECTIVE")
    if data.source is None:
        preconditions.append("OUTCOME_SOURCE_MISSING")
    else:
        data.source.verify_content(dataset_snapshot(data))
        if data.source.retrieved_at < plan.ended_at:
            preconditions.append("OUTCOME_SOURCE_PRECEDES_END")
    arms = {arm: [row for row in data.observations if row.assigned == arm] for arm in (0, 1)}
    if any(len(rows) < plan.min_per_arm for rows in arms.values()):
        preconditions.append("INSUFFICIENT_ARM_COUNTS")
    if any(row.outcome is None for row in data.observations):
        preconditions.append("MISSING_OUTCOMES")
    if any(row.baseline is None for row in data.observations):
        preconditions.append("MISSING_BASELINES")
    overlap = "DECLARED_SUPPORT_ONLY"
    if any(row.propensity is None for row in data.observations):
        preconditions.append("PROPENSITY_UNKNOWN")
        overlap = "UNKNOWN"
    elif any(not plan.overlap_min <= row.propensity <= 1 - plan.overlap_min for row in data.observations):
        preconditions.append("NO_PROPENSITY_OVERLAP")
        overlap = "FAILED"
    if all(arms.values()) and all(row.baseline is not None for row in data.observations):
        bounds = [(min(row.baseline for row in rows), max(row.baseline for row in rows)) for rows in arms.values()]
        if max(bound[0] for bound in bounds) > min(bound[1] for bound in bounds):
            preconditions.append("NO_BASELINE_OVERLAP")
            overlap = "FAILED"
    costs = "DECLARED_ONLY" if safety and safety.cost_minor is not None and safety.cost_source else "UNKNOWN_COSTS"
    harms = "DECLARED_ONLY" if safety and safety.harm_value is not None and safety.harm_source else "UNKNOWN_HARMS"
    qualifications = [label for label in (costs, harms) if label.startswith("UNKNOWN")]
    if data.kind != "synthetic":
        qualifications.append("UNAUTHENTICATED_INPUTS")
    sources = tuple(ref for ref in (plan.protocol, data.source,
                    safety.cost_source if safety else None, safety.harm_source if safety else None) if ref is not None)
    result = CausalAnalysisResult(plan.study_id, plan.domain, plan.metric, plan.unit, len(data.observations),
                                  "INCONCLUSIVE", tuple(preconditions + qualifications), sources, safety, harms, costs, overlap)
    if preconditions:
        return result
    try:
        dowhy, np, pd = _load_engine()
    except ImportError:
        return replace(result, reasons=result.reasons + ("DEPENDENCY_UNAVAILABLE",))
    recorded = []
    try:
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always", RuntimeWarning)
            frame = pd.DataFrame([{"assigned": row.assigned, "outcome": row.outcome, "baseline": row.baseline} for row in data.observations])
            model = dowhy.CausalModel(data=frame, treatment="assigned", outcome="outcome", common_causes=["baseline"])
            estimand = model.identify_effect(proceed_when_unidentifiable=False)
            estimate = model.estimate_effect(estimand, method_name="backdoor.linear_regression", confidence_intervals=True,
                                             method_params={"confidence_level": plan.confidence_level})
            effect = float(estimate.value)
            interval = tuple(float(value) for value in np.asarray(estimate.get_confidence_intervals(confidence_level=plan.confidence_level)).reshape(-1))
            placebo = model.refute_estimate(estimand, estimate, method_name="placebo_treatment_refuter", placebo_type="permute",
                                            num_simulations=plan.simulations, random_state=np.random.RandomState(plan.random_seed), n_jobs=1)
            placebo_effect = float(placebo.new_effect)
            sensitivity = model.refute_estimate(estimand, estimate, method_name="add_unobserved_common_cause",
                                                simulation_method="linear-partial-R2", benchmark_common_causes=["baseline"],
                                                effect_fraction_on_treatment=[.1], effect_fraction_on_outcome=[.1],
                                                significance_level=1 - plan.confidence_level, plot_estimate=False)
            robustness = float(sensitivity.stats["robustness_value"])
        for value in (effect, placebo_effect, robustness, *interval):
            _number(value)
        if len(interval) != 2 or interval[0] > interval[1] or not 0 <= robustness <= 1:
            raise ValueError("invalid library diagnostic output")
    except Exception as error:
        return replace(result, reasons=result.reasons + ("ENGINE_DIAGNOSTIC_FAILED",), engine_version="0.14",
                       engine_error=type(error).__name__ + ": " + str(error)[:200],
                       engine_warnings=tuple(str(w.message) for w in recorded if isinstance(w.message, RuntimeWarning)))
    reasons = list(result.reasons)
    numerical_warnings = tuple(str(w.message) for w in recorded if isinstance(w.message, RuntimeWarning))
    if numerical_warnings:
        reasons.append("NUMERICAL_DIAGNOSTIC_WARNING")
    if abs(placebo_effect) > plan.placebo_tolerance:
        reasons.append("PLACEBO_DIAGNOSTIC_FAILED")
    if robustness < plan.minimum_robustness:
        reasons.append("CONFOUNDING_SENSITIVITY")
    if interval[0] <= 0 <= interval[1]:
        reasons.append("INTERVAL_CONTAINS_NULL")
    return replace(result, status="INCONCLUSIVE" if reasons else "SYNTHETIC_DIAGNOSTICS_ONLY", reasons=tuple(reasons),
                   estimate=effect, confidence_interval=interval, confidence_level=plan.confidence_level,
                   placebo_effect=placebo_effect, robustness_value=robustness, engine_version="0.14", engine_warnings=numerical_warnings)
