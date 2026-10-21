"""K005: calibrated description and randomized causal accuracy are distinct estimands."""
from dataclasses import dataclass
from math import isfinite
from manager_core.evaluation import _valid_distribution, total_variation
from manager_core.models.source import _text


@dataclass(frozen=True)
class Score:
    kind: str
    value: float


@dataclass(frozen=True)
class ForecastDistribution:
    probabilities: dict[str, float]
    task_id: str
    calibrated_on_ids: tuple[str, ...]

    def __post_init__(self):
        _valid_distribution(self.probabilities)
        _text(self.task_id)
        if not isinstance(self.calibrated_on_ids, tuple) or not self.calibrated_on_ids:
            raise ValueError("named calibration dataset required")
        for x in self.calibrated_on_ids:
            _text(x)


@dataclass(frozen=True)
class RCTEffectEstimate:
    estimate: float
    ci_lower: float
    ci_upper: float
    experiment_id: str

    def __post_init__(self):
        _text(self.experiment_id)
        if any(type(x) not in (int,float) or not isfinite(x) for x in (
            self.estimate,self.ci_lower,self.ci_upper)):
            raise ValueError("finite randomized effect and uncertainty required")
        if not self.ci_lower <= self.estimate <= self.ci_upper:
            raise ValueError("effect estimate outside interval")


def prediction_score(forecast: ForecastDistribution, observed: dict[str, float]) -> Score:
    if not isinstance(forecast, ForecastDistribution):
        raise TypeError("descriptive distribution required")
    return Score("descriptive_tvd",total_variation(forecast.probabilities,observed))


def effect_error(predicted: RCTEffectEstimate, observed_randomized_ate: float) -> Score:
    if not isinstance(predicted, RCTEffectEstimate):
        raise TypeError("randomized causal-effect estimate required")
    if type(observed_randomized_ate) not in (float,int) or not isfinite(observed_randomized_ate):
        raise ValueError("verified numeric randomized effect required")
    return Score("causal_ate_absolute_error", abs(predicted.estimate-observed_randomized_ate))
