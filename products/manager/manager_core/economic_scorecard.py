"""Read-only economic-autonomy / beneficiary-wealth *research* scorecards.

Input is anonymized aggregate evidence, NOT provider-verified money.
No external calls, permission grants, actor profiles, source imports from Life
Manager, or live execution. Every result is P0 until an independent source
verification and a valid field study are established in separate systems.

Reuse the existing K011 evaluator for strictly offline causal accounting.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from re import fullmatch
from types import MappingProxyType
from typing import Mapping

from .evaluator import Comparator, evaluate_outcome


COST_CATEGORIES = (
    "platform", "compute", "goods", "marketing",
    "labor", "refunds", "tax", "other",
)
SOURCES = {"simulation", "historical_task_value", "provider_claim"}
RECEIPT_STATES = {"settled", "pending", "reversed", "disputed"}


def _minor_units(n, *, optional=False, signed=False):
    if optional and n is None:
        return None
    # Require integers: floats lose minor-unit precision. bool is an int subclass.
    if type(n) is not int or (n < 0 and not signed) or abs(n) > 10**15:
        raise ValueError("bounded integer minor-units required")
    return n


def _count(n, field):
    if type(n) is not int or n < 0 or n > 10**12:
        raise ValueError(f"invalid {field}")
    return n


@dataclass(frozen=True)
class HashedReceipt:
    reference_sha256: str
    amount_minor: int
    status: str
    external_customer: bool

    def __post_init__(self):
        if type(self.reference_sha256) is not str or fullmatch(r"[a-f0-9]{64}", self.reference_sha256) is None:
            raise ValueError("opaque SHA256 receipt reference required; no raw customer IDs")
        _minor_units(self.amount_minor)
        if self.status not in RECEIPT_STATES:
            raise ValueError("unknown receipt state")
        if type(self.external_customer) is not bool:
            raise ValueError("external customer flag required")


@dataclass(frozen=True)
class CostCoverage:
    amounts_minor: Mapping[str, int | None]

    def __post_init__(self):
        a=self.amounts_minor
        if not isinstance(a, Mapping) or set(a) != set(COST_CATEGORIES):
            raise ValueError("all cost categories must be explicitly covered or UNKNOWN")
        for value in a.values():
            _minor_units(value, optional=True)
        # Guard the source dict against mutation after validation.
        object.__setattr__(self, "amounts_minor", MappingProxyType(dict(a)))


@dataclass(frozen=True)
class EconomicExperiment:
    method: str
    preregistered: bool
    independent: bool
    preregistration_url: str
    effect_minor: int
    lower_minor: int
    upper_minor: int
    harms_minor: int | None

    def __post_init__(self):
        if self.method not in {"randomized", "observational", "pre_post"}:
            raise ValueError("known comparator methodology required")
        if type(self.preregistered) is not bool or type(self.independent) is not bool:
            raise ValueError("comparator status required")
        # Reuse canonical K011 URL validation, not a locally invented URL rule.
        Comparator(self.method, self.preregistered,
                   self.preregistration_url, self.independent)
        for x in (self.effect_minor,self.lower_minor,self.upper_minor):
            _minor_units(x, signed=True)
        _minor_units(self.harms_minor, optional=True)
        if not self.lower_minor <= self.effect_minor <= self.upper_minor:
            raise ValueError("effect outside claimed interval")


@dataclass(frozen=True)
class AggregateEconomicEpisode:
    episode_id: str
    source_kind: str
    currency: str
    receipts: tuple[HashedReceipt, ...]
    cost_coverage: CostCoverage
    human_rescue_seconds: int
    unresolved_effects: int
    policy_violations: int
    experiment: EconomicExperiment | None = None

    def __post_init__(self):
        if type(self.episode_id) is not str or fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}",self.episode_id) is None:
            raise ValueError("opaque safe episode ID required")
        if self.source_kind not in SOURCES:
            raise ValueError("source provenance category required")
        if type(self.currency) is not str or fullmatch(r"[A-Z]{3}",self.currency) is None:
            raise ValueError("ISO-style uppercase 3 letter currency required")
        if type(self.receipts) is not tuple or any(type(r) is not HashedReceipt for r in self.receipts):
            raise ValueError("only typed hashed receipt aggregates accepted")
        if type(self.cost_coverage) is not CostCoverage:
            raise ValueError("explicit cost coverage required")
        _count(self.human_rescue_seconds,"human rescue time")
        _count(self.unresolved_effects,"unresolved external effects")
        _count(self.policy_violations,"policy violations")
        if self.experiment is not None and type(self.experiment) is not EconomicExperiment:
            raise ValueError("unrecognized causal experiment")


@dataclass(frozen=True)
class DualScorecard:
    economic_status: str
    settled_external_revenue_minor: int | None
    signed_net_contribution_minor: int | None
    autonomy_status: str
    autonomy_claim_eligible: bool
    beneficiary_status: str
    net_welfare_effect_minor: int | None
    net_welfare_lower_minor: int | None
    real_world_proof_level: str
    limitations: tuple[str, ...]


def score_economic_episode(ep: AggregateEconomicEpisode) -> DualScorecard:
    """Validate aggregate arithmetic without claiming real outcome verification.

    Calling this function cannot be a substitute for K010 independent provider
    readback, a recorded authority grant or a preregistered field intervention.
    """
    if type(ep) is not AggregateEconomicEpisode:
        raise ValueError("typed economic episode required")
    rescue=ep.human_rescue_seconds>0
    autonomy=("HUMAN_INTERVENTION_REPORTED" if rescue
              else "NO_HUMAN_RESCUES_REPORTED_UNVERIFIED")

    state="UNAUTHENTICATED_RECONCILED_INPUT"
    revenue=None
    contribution=None
    receipts=ep.receipts
    if ep.source_kind in ("simulation","historical_task_value"):
        state="PROXY_NOT_SETTLED_REVENUE"
    elif len({r.reference_sha256 for r in receipts})!=len(receipts):
        state="DUPLICATE_RECEIPT"
    elif ep.policy_violations:
        state="POLICY_VIOLATION"
    elif ep.unresolved_effects:
        state="UNKNOWN_EXTERNAL_EFFECT"
    elif any(v is None for v in ep.cost_coverage.amounts_minor.values()):
        state="UNKNOWN_COST_COVERAGE"
    elif any(r.status!="settled" for r in receipts):
        state="SETTLEMENT_NOT_COMPLETE"
    else:
        revenue=sum(r.amount_minor for r in receipts if r.external_customer)
        contribution=revenue-sum(ep.cost_coverage.amounts_minor.values())
        if abs(contribution)>10**16:
            raise ValueError("aggregate amount outside supported bound")
    possible_autonomy=(not rescue and ep.unresolved_effects==0 and
                       ep.policy_violations==0 and
                       state=="UNAUTHENTICATED_RECONCILED_INPUT")
    welfare_status="NOT_MEASURED"
    welfare_effect=None
    welfare_lower=None
    if ep.experiment is not None and contribution is not None:
        trial=ep.experiment
        if (trial.method=="randomized" and trial.preregistered and
                trial.independent and trial.harms_minor is not None):
            comparator=Comparator(trial.method,trial.preregistered,
                                  trial.preregistration_url,trial.independent)
            # The trial's effect represents gross beneficiary value BEFORE
            # incremental business costs and independently quantified harms.
            estimated=evaluate_outcome(
                float(trial.effect_minor),float(trial.lower_minor),
                float(trial.upper_minor),
                float(sum(ep.cost_coverage.amounts_minor.values())),
                float(trial.harms_minor),comparator,"welfare")
            if estimated.causal_design_valid:
                if estimated.net_effect < 0:
                    welfare_status="OFFLINE_NEGATIVE_NET_EFFECT"
                elif estimated.net_lower <= 0:
                    welfare_status="OFFLINE_UNCERTAIN_NET_EFFECT"
                else:
                    welfare_status="OFFLINE_CAUSAL_ESTIMATE_ONLY"
                welfare_effect=int(estimated.net_effect)
                welfare_lower=int(estimated.net_lower)
    return DualScorecard(
        economic_status=state,
        settled_external_revenue_minor=revenue,
        signed_net_contribution_minor=contribution,
        autonomy_status=autonomy,
        autonomy_claim_eligible=possible_autonomy,
        beneficiary_status=welfare_status,
        net_welfare_effect_minor=welfare_effect,
        net_welfare_lower_minor=welfare_lower,
        real_world_proof_level="P0",
        limitations=(
            "Declared provider receipt hashes are not authenticated by this evaluator",
            "No live external spending, actions, or beneficiary measurement occurs",
            "Human rescue count is self-reported aggregate until independently audited",
            "Any test experiment is only a K011 P0 offline estimate, not field P3/P4",
        ),
    )
