"""K011: net-impact ACCOUNTING, not automatic proof of welfare or causation."""
from dataclasses import dataclass
from math import isfinite
from .models.source import _text, _url


@dataclass(frozen=True)
class Comparator:
    method: str
    preregistered: bool
    preregistration_url: str
    independent: bool

    def __post_init__(self):
        if self.method not in ("randomized","observational","pre_post"):
            raise ValueError("explicit comparator design required")
        if type(self.preregistered) is not bool or type(self.independent) is not bool:
            raise ValueError("pre-registration and independence must be explicit")
        _url(self.preregistration_url)


@dataclass(frozen=True)
class ImpactEvaluation:
    status: str
    net_effect: float | None
    net_lower: float | None
    net_upper: float | None
    causal_design_valid: bool
    proof_level: str = "P0"


def evaluate_outcome(effect: float,ci_lower: float,ci_upper: float,cost: float,
                     harm: float | None, comparator: Comparator | None,
                     metric_type: str) -> ImpactEvaluation:
    quantities=(effect,ci_lower,ci_upper,cost)
    if any(type(x) not in (float,int) or not isfinite(x) for x in quantities):
        raise ValueError("numeric finite effect/interval/cost required")
    if ci_lower>effect or effect>ci_upper or cost<0:
        raise ValueError("invalid effect bounds or cost")
    if metric_type not in ("welfare","activity"):
        raise ValueError("explicit welfare vs activity metric required")
    if metric_type!="welfare":
        return ImpactEvaluation("ACTIVITY_ONLY",None,None,None,False)
    if not isinstance(comparator,Comparator):
        return ImpactEvaluation("NO_COMPARATOR",None,None,None,False)
    if harm is None:
        return ImpactEvaluation("UNKNOWN_HARMS",None,None,None,False)
    if type(harm) not in (float,int) or not isfinite(harm) or harm<0:
        raise ValueError("harms must be measured finite nonnegative, never imputed zero")
    net=effect-cost-harm
    lower=ci_lower-cost-harm
    upper=ci_upper-cost-harm
    valid=(comparator.method=="randomized" and comparator.preregistered and comparator.independent)
    if net<0:
        status="NEGATIVE"
    elif not valid:
        status="EXPLORATORY_COMPARATOR"
    elif lower<=0:
        status="UNCERTAIN_NET_BENEFIT"
    else:
        status="OFFLINE_ESTIMATE"
    # Even rigorous-looking fixture numbers are not beneficiary evidence.
    return ImpactEvaluation(status,net,lower,upper,valid,"P0")
