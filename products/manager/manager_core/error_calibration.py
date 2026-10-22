"""Grouped, reference-based prediction-error regression with scoped abstention.

A bounded diagnostic of squared binary forecast error, not a statistical
coverage guarantee, human behavioral certificate or execution authorization.
"""
from dataclasses import dataclass, field
from hashlib import sha256
from math import isfinite
import json
from .evidence_types import Prediction


def _identity(*values):
    if any(type(v) is not str or not v.strip() or len(v)>200 for v in values):
        raise ValueError('bounded explicit reference identity/scope/language required')


def _distribution(value):
    if type(value) is not tuple or len(value)!=2:raise ValueError('binary probability tuple required')
    Prediction(('reference_probability',),'reference_model',value)


@dataclass(frozen=True)
class PredictionCase:
    reference_id: str
    scope: str
    language: str
    distribution: tuple[float,float]
    out_of_distribution: bool = False

    def __post_init__(self):
        _identity(self.reference_id,self.scope,self.language);_distribution(self.distribution)
        if type(self.out_of_distribution) is not bool:raise ValueError('explicit shift flag required')


@dataclass(frozen=True)
class ErrorReference:
    reference_id: str
    group_id: str
    scope: str
    language: str
    distribution: tuple[float,float]
    outcome: int

    def __post_init__(self):
        _identity(self.reference_id,self.group_id,self.scope,self.language)
        _distribution(self.distribution)
        if type(self.outcome) is not int or self.outcome not in (0,1):
            raise ValueError('observed binary reference required')


@dataclass(frozen=True)
class ErrorEstimate:
    reference_id: str
    scope: str
    distribution: tuple[float,float]
    estimated_error: float | None
    accepted: bool
    status: str
    proof_level: str = field(default='P0',init=False)
    human_outcome: str = field(default='NOT_MEASURED',init=False)


@dataclass(frozen=True)
class ErrorCalibrator:
    scope: str
    language: str
    intercept: float | None
    slope: float | None
    threshold: float | None
    training_group_ids: tuple[str,...]
    validation_group_ids: tuple[str,...]
    reference_hash: str

    def predict_error(self,case: PredictionCase) -> ErrorEstimate:
        if type(case) is not PredictionCase:raise ValueError('typed prediction case required')
        status='ESTIMATED';estimate=None
        if self.intercept is None:status='REFERENCE_DATA_REQUIRED'
        elif case.scope!=self.scope or case.language!=self.language:status='ABSTAIN_SCOPE'
        elif case.out_of_distribution:status='ABSTAIN_DISTRIBUTION_SHIFT'
        else:
            estimate=max(0.,min(1.,self.intercept+self.slope*case.distribution[1]))
            if self.threshold is None or estimate>self.threshold:status='ABSTAIN_RISK'
        return ErrorEstimate(case.reference_id,case.scope,case.distribution,estimate,
                             status=='ESTIMATED',status)


def fit_error_calibrator(training_groups,validation_groups,*,scope: str,language='en',
                         max_validation_risk=.25) -> ErrorCalibrator:
    from .calibration import assert_disjoint_groups
    _identity(scope,language)
    if (type(max_validation_risk) not in (int,float) or not isfinite(max_validation_risk)
            or not 0<=max_validation_risk<=1):raise ValueError('bounded validation-only risk budget required')
    if type(training_groups) is not tuple or type(validation_groups) is not tuple:
        raise ValueError('immutable grouped references required')
    rows=training_groups+validation_groups
    if any(type(r) is not ErrorReference or r.scope!=scope or r.language!=language for r in rows):
        raise ValueError('references must match the declared target scope/language')
    ids=[r.reference_id for r in rows]
    if len(set(ids))!=len(ids):raise ValueError('reference leakage/duplicate identity')
    train_ids=tuple(sorted({r.group_id for r in training_groups}))
    validation_ids=tuple(sorted({r.group_id for r in validation_groups}))
    digest=sha256(json.dumps(dict(training=[r.__dict__ for r in training_groups],
        validation=[r.__dict__ for r in validation_groups],scope=scope,language=language,
        max_validation_risk=max_validation_risk),sort_keys=True,allow_nan=False).encode()).hexdigest()
    if not training_groups or not validation_groups:
        return ErrorCalibrator(scope,language,None,None,None,train_ids,validation_ids,digest)
    assert_disjoint_groups(train_ids,validation_ids)
    xs=[r.distribution[1] for r in training_groups]
    ys=[(r.distribution[1]-r.outcome)**2 for r in training_groups]
    mx=sum(xs)/len(xs);my=sum(ys)/len(ys);den=sum((x-mx)**2 for x in xs)
    slope=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/den if den>1e-12 else 0.
    intercept=my-slope*mx
    validation=[(max(0.,min(1.,intercept+slope*r.distribution[1])),
                 (r.distribution[1]-r.outcome)**2) for r in validation_groups]
    threshold=None
    # Keep all ties together and select solely on validation observations.
    for candidate in sorted({x for x,y in validation}):
        errors=[y for x,y in validation if x<=candidate]
        if sum(errors)/len(errors)<=max_validation_risk:threshold=candidate
    return ErrorCalibrator(scope,language,intercept,slope,threshold,train_ids,validation_ids,digest)


@dataclass(frozen=True)
class RiskPoint:
    coverage: float
    risk: float | None
    count: int
    groups: int


def selective_risk_curve(predictions,references) -> tuple[RiskPoint,...]:
    if (not predictions or not references or len(predictions)!=len(references)
            or any(type(x) is not ErrorEstimate for x in predictions)
            or any(type(r) is not ErrorReference for r in references)):
        raise ValueError('nonempty paired estimates and observed references required')
    lookup={r.reference_id:r for r in references}
    if len(lookup)!=len(references) or {x.reference_id for x in predictions}!=set(lookup):
        raise ValueError('exact reference identity match required')
    pairs=[]
    for x in predictions:
        r=lookup[x.reference_id]
        if x.scope!=r.scope or x.distribution!=r.distribution:
            raise ValueError('prediction/reference scope or probability mismatch')
        if x.estimated_error is not None:pairs.append((x.estimated_error,r))
    points=[RiskPoint(0.,None,0,0)]
    for threshold in sorted({x for x,r in pairs}):
        selected=[r for x,r in pairs if x<=threshold]
        errors=[(r.distribution[1]-r.outcome)**2 for r in selected]
        points.append(RiskPoint(len(selected)/len(references),sum(errors)/len(errors),
                                len(selected),len({r.group_id for r in selected})))
    return tuple(points)
