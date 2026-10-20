"""L001: conditional probability from an illustrative joint distribution.

Purely synthetic numbers; observational conditional probability is NOT an
estimated causal effect of changing a person's context or sending a message.
No network access, personal records, or real-world actions.
"""
from math import isfinite
from typing import Mapping


def validate_joint_distribution(joint: Mapping[str, Mapping[str, float]]) -> None:
    """Require a finite nonnegative joint P(context, outcome) summing to 1."""
    if not isinstance(joint, dict) or not joint:
        raise ValueError('nonempty joint probability table required')
    total = 0.0
    for context, outcomes in joint.items():
        if not isinstance(context, str) or not context.strip():
            raise ValueError('context must have a nonempty name')
        if not isinstance(outcomes, dict) or not outcomes:
            raise ValueError('each context needs a nonempty outcome distribution')
        for outcome, mass in outcomes.items():
            if not isinstance(outcome, str) or not outcome.strip():
                raise ValueError('outcome must have a nonempty name')
            if type(mass) not in (int, float) or not isfinite(mass) or mass < 0:
                raise ValueError('probability must be finite, nonnegative and numeric')
            total += mass
    if abs(total - 1.0) > 1e-9:
        raise ValueError('joint probabilities must sum to 1')


def conditional_probability(joint: dict, context: str, outcome: str) -> float:
    """P(outcome | context) = P(outcome AND context) / P(context)."""
    validate_joint_distribution(joint)
    if context not in joint:
        raise ValueError('unknown context')
    mass = sum(joint[context].values())
    if mass == 0:
        raise ValueError('conditional probability is undefined for a zero-mass context')
    return joint[context].get(outcome, 0.0) / mass


def marginal_probability(joint: dict, outcome: str) -> float:
    """P(outcome) by summing the joint mass across all contexts."""
    validate_joint_distribution(joint)
    return sum(outcomes.get(outcome, 0.0) for outcomes in joint.values())


if __name__ == '__main__':
    # Illustrative probabilities for two times of day, not measured humans.
    joint = {
        'morning': {'walk': 0.18, 'rest': 0.12},
        'evening': {'walk': 0.14, 'rest': 0.56},
    }
    print('SYNTHETIC joint probability table (not participant data)')
    for context in joint:
        p = conditional_probability(joint, context, 'walk')
        print(f'P(walk | {context}) = {p:.1%}')
    print(f'P(walk) = {marginal_probability(joint, "walk"):.1%}')
    print('These are observational conditionals, NOT a causal estimate.')