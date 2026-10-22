"""R008 evidence labels: source provenance and study design are not proof levels.

These rules prevent internal relabeling, not deliberate falsification of source
metadata. A reviewed source, sound experiment and external outcome evidence are
still required. Neither an RCT label nor a passing test proves Manager impact.
"""
from __future__ import annotations
from collections import Counter
from .evidence import validate_record

_DESIGN_LABELS = {
    'randomized_trial': 'rct',
    'observational_survey': 'survey',
    'simulation': 'simulation',
    'benchmark': 'benchmark',
}
_TITLES = {
    'rct': "Human randomized trial (authors' report; not Manager field impact)",
    'survey': 'Human observational survey (not an intervention effect)',
    'simulation': 'Simulation study (not a human field trial)',
    'benchmark': 'Offline benchmark (not a new human field trial)',
    'company_claim': 'Company-reported claim (not an independent RCT)',
    'review': 'Literature review (not an additional independent trial)',
    'tool_documentation': 'Tool documentation (not evidence of beneficiary benefit)',
}


def evidence_type(record: dict) -> str:
    """Derive a label from declared, source-reviewed metadata; never from score."""
    r = validate_record(record)
    source, design = r['source']['kind'], r['study']['design']
    if source == 'company_page':
        return 'company_claim'
    if source == 'official_docs':
        if design != 'software_documentation':
            raise ValueError('official documentation cannot be labeled an empirical study')
        return 'tool_documentation'
    if source == 'review_paper':
        if design != 'review':
            raise ValueError('review cannot be labeled a new primary trial')
        return 'review'
    if design not in _DESIGN_LABELS:
        raise ValueError('primary paper needs an explicit empirical/simulation design')
    return _DESIGN_LABELS[design]


def require_type(record: dict, requested: str) -> None:
    """Reject a display/consumer attempting to upgrade the source's category."""
    if requested not in _TITLES or evidence_type(record) != requested:
        raise ValueError(f'evidence type mismatch: requested {requested}')


def label(record: dict) -> str:
    return f"{_TITLES[evidence_type(record)]}; reading={record['review']['status']}"


def count_by_type(records: list[dict]) -> dict[str, int]:
    """Research inventory counts, NEVER counts of successful interventions."""
    return dict(sorted(Counter(evidence_type(r) for r in records).items()))

# E03: mutually distinct observation, fictional scenario and model prediction
# records. Neither a URL nor a hash string authenticates the public origin.
from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from types import MappingProxyType
from hashlib import sha256 as _sha256
import json as _json
from .models.source import Source, _aware


@dataclass(frozen=True)
class SyntheticScenario:
    scenario_id: str
    version: str
    payload: dict
    evidence_kind: str = field(default="SYNTHETIC_SCENARIO", init=False)
    proof_level: str = field(default="P0", init=False)

    def __post_init__(self):
        if (type(self.scenario_id) is not str or not self.scenario_id.strip() or
            len(self.scenario_id) > 128 or type(self.version) is not str or
            not self.version.strip() or len(self.version) > 64 or
            type(self.payload) is not dict or not self.payload):
            raise ValueError("bounded fictional scenario fields required")
        try:
            packed = _json.dumps(self.payload, allow_nan=False, ensure_ascii=False)
        except (ValueError, TypeError) as exc:
            raise ValueError("JSON-only fictional payload required") from exc
        if len(packed.encode("utf8")) > 16384:
            raise ValueError("fictional payload exceeds limit")
        # Shallow immutable public view; callers cannot overwrite its top-level
        # identity after acceptance. E10 provides the actual collection boundary.
        object.__setattr__(self, "payload", MappingProxyType(_json.loads(packed)))


@dataclass(frozen=True, init=False)
class ObservedSnapshot:
    """Only real bytes match a supplied source digest; origin NOT authenticated.

    The read-only public observer (E10) must supply actual network evidence to
    establish origin. This P0 record does not certify an official page.
    """
    source: Source
    body_sha256: str
    collected_at: datetime
    origin_verified: bool = field(default=False, init=False)
    status: str = field(default="CONTENT_HASH_MATCH_ORIGIN_UNVERIFIED", init=False)
    proof_level: str = field(default="P0", init=False)
    causal_support: bool = field(default=False, init=False)

    @classmethod
    def from_bytes(cls, source: Source, body: bytes,
                   collected_at: datetime) -> "ObservedSnapshot":
        if type(source) is not Source:
            raise ValueError("typed rights-cleared source required")
        if source.source_id.lower().startswith(("synthetic:", "fixture:", "mock:")):
            raise ValueError("fictional source cannot become observed reality")
        _aware(collected_at)
        source.require_fresh(collected_at, max_age_hours=48)
        if type(body) is not bytes or not body or len(body) > 1048576:
            raise ValueError("bounded downloaded bytes required")
        source.verify_content(body)
        result = object.__new__(cls)
        object.__setattr__(result, "source", source)
        object.__setattr__(result, "body_sha256", _sha256(body).hexdigest())
        object.__setattr__(result, "collected_at", collected_at)
        object.__setattr__(result, "origin_verified", False)
        object.__setattr__(result, "status", "CONTENT_HASH_MATCH_ORIGIN_UNVERIFIED")
        object.__setattr__(result, "proof_level", "P0")
        object.__setattr__(result, "causal_support", False)
        return result


@dataclass(frozen=True)
class Prediction:
    """Predicted probabilities are P0, never human outcomes or grants."""
    source_refs: tuple[str, ...]
    model_id: str
    distribution: tuple[float, ...]
    proof_level: str = field(default="P0", init=False)
    human_outcome: str = field(default="NOT_MEASURED", init=False)
    authorized_execution: bool = field(default=False, init=False)
    causal_support: bool = field(default=False, init=False)

    def __post_init__(self):
        if (type(self.source_refs) is not tuple or not self.source_refs or
            any(type(ref) is not str or not ref.strip() for ref in self.source_refs) or
            len(set(self.source_refs)) != len(self.source_refs)):
            raise ValueError("unique typed source refs required")
        if type(self.model_id) is not str or not self.model_id.strip():
            raise ValueError("model ID required")
        if (type(self.distribution) is not tuple or not self.distribution or
            len(self.distribution) > 100 or
            any(type(p) not in (float, int) or not isfinite(p) or p < 0 or p > 1
                for p in self.distribution) or
            abs(sum(self.distribution) - 1) > 1e-9):
            raise ValueError("finite normalized probability distribution required")
