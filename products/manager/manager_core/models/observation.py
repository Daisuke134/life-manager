"""K002: an observation is scoped, timestamped and typed; missing is not zero."""
from dataclasses import dataclass
from math import isfinite
from .source import Source, _text, _aware


@dataclass(frozen=True)
class Observation:
    source: Source
    measure_id: str
    scope: str
    value: float | None
    unit: str
    recorded_at: object
    missing_reason: str | None = None

    def __post_init__(self):
        if not isinstance(self.source, Source):
            raise ValueError("validated public source required")
        for name in ("measure_id", "scope", "unit"):
            _text(getattr(self, name))
        _aware(self.recorded_at)
        if self.value is None:
            _text(self.missing_reason)
        elif (type(self.value) not in (int, float) or not isfinite(self.value)
              or self.missing_reason is not None):
            raise ValueError("finite measured value or explicit missing reason required")
