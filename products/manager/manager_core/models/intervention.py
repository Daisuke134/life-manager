"""K004: NO_ACTION is structural, not something a planner can omit."""
from dataclasses import dataclass
from math import isfinite
from .source import _text


def _nonnegative(value):
    if type(value) not in (int, float) or not isfinite(value) or value < 0:
        raise ValueError("nonnegative finite quantity required")
    return float(value)


@dataclass(frozen=True)
class InterventionOption:
    option_id: str
    domain: str
    target: str
    action: str
    cost: float
    risk: float
    expected_effect: tuple[float, float] | None
    no_action: bool = False

    def __post_init__(self):
        for field in ("option_id", "domain", "target", "action"):
            _text(getattr(self, field))
        _nonnegative(self.cost)
        _nonnegative(self.risk)
        if type(self.no_action) is not bool:
            raise ValueError("no_action must be a boolean")
        if self.no_action:
            if self.action != "NO_ACTION" or self.cost != 0 or self.risk != 0 or self.expected_effect is not None:
                raise ValueError("NO_ACTION cannot carry hidden effects or costs")
        else:
            if self.action == "NO_ACTION" or not isinstance(self.expected_effect, tuple) or len(self.expected_effect) != 2:
                raise ValueError("an action needs a bounded uncertain effect")
            lower, upper = self.expected_effect
            if any(type(x) not in (int, float) or not isfinite(x) for x in (lower, upper)) or lower > upper:
                raise ValueError("invalid effect interval")


@dataclass(frozen=True)
class InterventionPlan:
    options: tuple[InterventionOption, ...]

    def __post_init__(self):
        if not isinstance(self.options, tuple) or not self.options or any(
                not isinstance(x, InterventionOption) for x in self.options):
            raise ValueError("nonempty typed options required")
        if sum(o.no_action for o in self.options) != 1 or len({o.option_id for o in self.options}) != len(self.options):
            raise ValueError("exactly one NO_ACTION and unique option ids required")
        if len({o.domain for o in self.options}) != 1:
            raise ValueError("plans cannot blend authority across domains")

    def choose(self, *, supports_causal: bool) -> InterventionOption:
        no_action = next(o for o in self.options if o.no_action)
        if supports_causal is not True:
            return no_action
        candidates = [o for o in self.options if not o.no_action and o.expected_effect[0] > o.cost + o.risk]
        return max(candidates, key=lambda o: o.expected_effect[0]-o.cost-o.risk) if candidates else no_action
