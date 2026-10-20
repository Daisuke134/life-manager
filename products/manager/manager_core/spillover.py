"""L010: accounting example of displacement, NOT causal impact estimation."""
from math import isfinite


def _num(value):
    if type(value) not in (int,float) or not isfinite(value):
        raise ValueError('finite numeric value required')
    return float(value)


def net_additional_resources(target_change, other_changes, program_cost):
    """Pure arithmetic for hypothetically known changes; never a causal estimator."""
    target=_num(target_change); cost=_num(program_cost)
    if cost<0 or not isinstance(other_changes,(list,tuple)):
        raise ValueError('nonnegative cost and list of affected other causes required')
    return target + sum(_num(x) for x in other_changes) - cost
