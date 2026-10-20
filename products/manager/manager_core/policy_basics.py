"""L011 tiny IPS example; requires correct externally established propensities.

A known toy formula is not safe off-policy causal evidence without assumptions.
"""
from math import isfinite


def ips_estimate(logs, target_support, logging_support):
    """Mean(r * pi_target(action|x) / pi_logging(action|x)); no model fitting."""
    if not isinstance(logs,(list,tuple)) or not logs or not isinstance(target_support,set) or not target_support or not isinstance(logging_support,set) or not target_support<=logging_support:
        raise ValueError('nonempty log and positive action support required')
    total=0.
    for row in logs:
        if not isinstance(row,dict) or not {'action','reward','logging_propensity','target_propensity'}<=row.keys() or row['action'] not in logging_support:
            raise ValueError('complete logged action and propensity required')
        p,q,r=row['logging_propensity'],row['target_propensity'],row['reward']
        if any(type(v) not in (int,float) or not isfinite(v) for v in (p,q,r)) or not 0<p<=1 or not 0<=q<=1:
            raise ValueError('finite valid logging and target propensities required')
        if row['action'] not in target_support and q != 0:
            raise ValueError('target positive propensity outside declared support')
        total+=q/p*r
    return total/len(logs)
