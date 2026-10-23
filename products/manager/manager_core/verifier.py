"""K010: a provider receipt is not an independent result; fixtures are ALWAYS P0."""
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from .outbox import EffectRecord
from .models.source import _aware


@dataclass(frozen=True)
class ExternalReadback:
    effect_key: str
    source: str
    executor_source: str
    recorded_at: datetime
    observed_value: float | None
    receipt_ref: str

    def __post_init__(self):
        _aware(self.recorded_at)


@dataclass(frozen=True)
class Verification:
    status: str
    proof_level: str
    evidence_ref: str | None


def verify_outcome(effect: EffectRecord,readback: ExternalReadback | None) -> Verification:
    bad=Verification("NOT_VERIFIED","P0",None)
    if not isinstance(effect,EffectRecord) or effect.status not in ("SUBMITTED","PRESENT"):
        return bad
    if not isinstance(readback,ExternalReadback) or not effect.receipt_ref:
        return bad
    if (readback.effect_key!=effect.key or readback.source==readback.executor_source
        or not readback.source or not readback.executor_source or
        readback.receipt_ref!=effect.receipt_ref or
        readback.observed_value is None or type(readback.observed_value) not in (int,float)
        or not isfinite(readback.observed_value) or
        (effect.dispatched_at is not None and readback.recorded_at<effect.dispatched_at)):
        return bad
    # Distinct fixture sensor, NEVER a field observation or P2 proof.
    return Verification("VERIFIED_FIXTURE_ONLY","P0",readback.source)
