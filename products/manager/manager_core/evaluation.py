"""Tiny transparent baselines to understand measurement, not a prediction model.

All inputs and demo numbers in this file are synthetic/illustrative.
No results here are evidence that Manager has improved anyone's life.
"""
from dataclasses import dataclass
from math import isfinite
from numbers import Real
from typing import Mapping, Sequence


def _is_probability(value: object) -> bool:
    """Reject bool/strings/NaN rather than implicitly coercing them to probabilities."""
    return (isinstance(value, Real) and not isinstance(value, bool)
            and isfinite(value) and 0 <= value <= 1)


def _valid_distribution(d: Mapping[str, float]) -> None:
    if not isinstance(d, Mapping) or not d or any(not _is_probability(x) for x in d.values()):
        raise ValueError('Distribution must be nonempty, finite, and contain probabilities in [0,1]')
    if abs(sum(d.values()) - 1) > 1e-9:
        raise ValueError('Distribution probabilities must sum to 1')


def total_variation(p: Mapping[str, float], q: Mapping[str, float]) -> float:
    """TVD(P,Q)=0.5 sum(abs(p_i-q_i)), in [0,1]."""
    _valid_distribution(p)
    _valid_distribution(q)
    return 0.5 * sum(abs(p.get(k, 0.) - q.get(k, 0.)) for k in p.keys() | q.keys())


def brier_score(predictions: Sequence[float], outcomes: Sequence[int]) -> float:
    """Mean squared error of binary event probabilities; lower is better."""
    if not predictions or len(predictions) != len(outcomes):
        raise ValueError('Nonempty equal-length lists required')
    if any(not _is_probability(p) for p in predictions):
        raise ValueError('Probabilities must be real, finite, non-boolean values in [0,1]')
    if any(type(y) is not int or y not in (0, 1) for y in outcomes):
        raise ValueError('Outcomes must be integer 0/1, not booleans')
    return sum((p-y)**2 for p,y in zip(predictions,outcomes)) / len(predictions)


def exploratory_mean_difference(treated: Sequence[float], control: Sequence[float]) -> float:
    """Descriptive treated-control difference; NOT automatically causal.

    Randomization validity, cluster dependence, attrition, interference,
    missingness, standard errors, and sampling design are NOT checked.
    """
    if not treated or not control or any(not isfinite(x) for x in list(treated)+list(control)):
        raise ValueError('Need finite results from both nonempty groups')
    return sum(treated)/len(treated)-sum(control)/len(control)


@dataclass(frozen=True)
class ActionProposal:
    source_url: str
    source_is_public: bool
    operator_authorized: bool
    cost: float
    budget_remaining: float
    irreversible: bool
    prior_approval_for_irreversible: bool


def gate_action(proposal: ActionProposal) -> tuple[bool, str]:
    """No public-data-only agent may infer authority from publication.

    A conservative toy gate, NOT adequate for production legal/safety checks.
    """
    if not proposal.source_url.startswith(('https://','http://')) or not proposal.source_is_public:
        return False, 'source_not_public'
    if not proposal.operator_authorized:
        return False, 'not_authorized'
    if not (isfinite(proposal.cost) and isfinite(proposal.budget_remaining)) or proposal.cost < 0 or proposal.budget_remaining < 0:
        return False, 'invalid_budget'
    if proposal.cost > proposal.budget_remaining:
        return False, 'over_budget'
    if proposal.irreversible and not proposal.prior_approval_for_irreversible:
        return False, 'requires_explicit_approval'
    return True, 'allowed_for_toy_demo_only'


if __name__ == '__main__':
    prediction = {'yes':0.93,'no':0.07}  # illustrative only
    observed = {'yes':0.87,'no':0.13}  # illustrative only
    print('Synthetic distribution TVD:', round(total_variation(prediction, observed),4))
    print('Synthetic exploratory mean difference:', exploratory_mean_difference([8,9,10],[5,6,7]))
    print('Neither number demonstrates real human impact or causal effects.')