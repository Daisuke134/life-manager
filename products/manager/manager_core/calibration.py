"""L003 reliability diagrams on held-out, synthetic binary outcomes only.

Mean predicted probability versus observed frequency within predetermined bins.
An illustrative metric, not a certificate of transfer to new populations.
"""
from math import isfinite


def reliability_bins(probabilities, outcomes, edges=(0, .2, .4, .6, .8, 1)):
    if not isinstance(probabilities, (list, tuple)) or not probabilities or not isinstance(outcomes, (list, tuple)) or len(probabilities) != len(outcomes):
        raise ValueError('nonempty equal-length observations required')
    if any(type(p) not in (int, float) or not isfinite(p) or not (0 <= p <= 1) for p in probabilities):
        raise ValueError('predicted probabilities must be finite numbers in [0,1]')
    if any(type(y) is not int or y not in (0, 1) for y in outcomes):
        raise ValueError('actual outcomes must be binary integers, not booleans')
    if not isinstance(edges,(tuple,list)) or len(edges)<2 or type(edges[0]) not in (int,float) or type(edges[-1]) not in (int,float) or edges[0]!=0 or edges[-1]!=1 or any(type(x) not in (int,float) or not isfinite(x) for x in edges) or any(a>=b for a,b in zip(edges,edges[1:])):
        raise ValueError('edges must be strictly increasing from 0 to 1')
    bins=[]
    for i,(low,high) in enumerate(zip(edges,edges[1:])):
        group=[(p,y) for p,y in zip(probabilities,outcomes) if low<=p <high or (i==len(edges)-2 and p==1)]
        bins.append({'bin_index':i,'low':low,'high':high,'count':len(group),
                     'mean_probability':sum(p for p,_ in group)/len(group) if group else None,
                     'event_rate':sum(y for _,y in group)/len(group) if group else None})
    return bins


def assert_disjoint_groups(train_ids, test_ids):
    """Prevent same unit/study IDs in a training and evaluation split."""
    if not train_ids or not test_ids or any(not isinstance(i,str) or not i for i in (*train_ids,*test_ids)):
        raise ValueError('two nonempty groups of IDs required')
    if set(train_ids) & set(test_ids):
        raise ValueError('data leakage: shared group/study in train and test')

# Reuse the existing calibration facade; scoped regression stays a focused unit.
from .error_calibration import (ErrorReference, PredictionCase, ErrorEstimate,
    ErrorCalibrator, RiskPoint, fit_error_calibrator, selective_risk_curve)
