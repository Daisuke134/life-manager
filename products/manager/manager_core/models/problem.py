"""K003: competing causal stories with traceable observational evidence, never proof."""
from dataclasses import dataclass
from .source import _text
from .observation import Observation


@dataclass(frozen=True)
class CausalHypothesis:
    claim: str
    mechanism: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self):
        _text(self.claim)
        _text(self.mechanism)
        if not isinstance(self.evidence_refs, tuple) or not self.evidence_refs:
            raise ValueError("causal claim must cite evidence")
        for ref in self.evidence_refs:
            _text(ref)


@dataclass(frozen=True)
class Problem:
    problem_id: str
    target_metric: str
    observations: tuple[Observation, ...]
    causal_hypotheses: tuple[CausalHypothesis, ...]
    alternative_explanations: tuple[str, ...]

    def __post_init__(self):
        _text(self.problem_id)
        _text(self.target_metric)
        if not isinstance(self.observations, tuple) or not self.observations or any(
                not isinstance(x, Observation) for x in self.observations):
            raise ValueError("validated observations required")
        if not isinstance(self.causal_hypotheses, tuple) or not self.causal_hypotheses or any(
                not isinstance(x, CausalHypothesis) for x in self.causal_hypotheses):
            raise ValueError("explicit causal hypotheses required")
        if not isinstance(self.alternative_explanations, tuple) or not self.alternative_explanations:
            raise ValueError("alternative explanations required")
        for explanation in self.alternative_explanations:
            _text(explanation)
        refs = {o.source.source_id for o in self.observations}
        for hypothesis in self.causal_hypotheses:
            if not set(hypothesis.evidence_refs) <= refs:
                raise ValueError("unsupported causal claim: unknown evidence reference")
