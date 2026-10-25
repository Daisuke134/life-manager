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

# Owned digital candidates do not reuse the fixture-only scalar effect arithmetic.
from dataclasses import field
from decimal import Decimal


@dataclass(frozen=True)
class OutcomeEndpoint:
    metric: str
    unit: str
    value: float | None
    comparator: str
    evidence_kind: str = field(default='PREDICTION_OR_UNKNOWN',init=False)
    causal_support: bool = field(default=False,init=False)

    def __post_init__(self):
        for text in (self.metric,self.unit,self.comparator):_text(text)
        if self.value is not None and (type(self.value) not in (int,float) or not isfinite(self.value)):
            raise ValueError('finite native-unit estimate or unknown required')


def combine_outcomes(*endpoints):
    if not endpoints or any(type(e) is not OutcomeEndpoint for e in endpoints):
        raise ValueError('typed native-unit endpoints required')
    first=endpoints[0]
    if any((e.metric,e.unit,e.comparator)!=(first.metric,first.unit,first.comparator) for e in endpoints):
        raise ValueError('incompatible metrics, units or comparisons cannot be added')
    value=None if any(e.value is None for e in endpoints) else sum(e.value for e in endpoints)
    return OutcomeEndpoint(first.metric,first.unit,value,first.comparator)


@dataclass(frozen=True)
class OutcomeVector:
    endpoints: tuple[OutcomeEndpoint,...] = ()

    def __post_init__(self):
        if type(self.endpoints) is not tuple or any(type(e) is not OutcomeEndpoint for e in self.endpoints):
            raise ValueError('typed outcome vector required')
        keys=[(e.metric,e.unit,e.comparator) for e in self.endpoints]
        if len(set(keys))!=len(keys):raise ValueError('duplicate endpoint must not silently double-count')


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    action: str
    target: str
    source_refs: tuple[str,...]
    technical_criterion: str
    outcomes: OutcomeVector = OutcomeVector()
    command_cost_usd: Decimal = Decimal('0')
    opportunity_cost: None = field(default=None,init=False)
    causal_support: bool = field(default=False,init=False)
    authorized_execution: bool = field(default=False,init=False)
    proof_level: str = field(default='P0',init=False)

    def __post_init__(self):
        for text in (self.candidate_id,self.action,self.target,self.technical_criterion):_text(text)
        if self.action not in {'NO_ACTION','ASK','PASS','CORRECT_LINK','IMPROVE_ACCESSIBILITY'}:
            raise ValueError('outside bounded candidate catalog')
        if (type(self.source_refs) is not tuple or any(type(r) is not str or not r.strip() for r in self.source_refs)
                or len(set(self.source_refs))!=len(self.source_refs) or type(self.outcomes) is not OutcomeVector):
            raise ValueError('explicit source references and outcome vector required')
        if (type(self.command_cost_usd) is not Decimal or not self.command_cost_usd.is_finite()
                or self.command_cost_usd!=0):raise ValueError('initial owned release has no financial transfer')
        if self.action in {'CORRECT_LINK','IMPROVE_ACCESSIBILITY'} and not self.source_refs:
            raise ValueError('technical action needs source evidence')

    @property
    def no_action(self):return self.action=='NO_ACTION'
