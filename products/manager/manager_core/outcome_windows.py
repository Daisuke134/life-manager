"""L009: enforce the exact outcome and time window for a measured claim."""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class EvidenceWindow:
    outcome_name: str
    duration_minutes: int
    value: float|None
    source_url: str
    causal_established: bool=False

    def __post_init__(self):
        if not isinstance(self.outcome_name,str) or not self.outcome_name.strip() or type(self.duration_minutes) is not int or self.duration_minutes < 1:
            raise ValueError('valid outcome name and time window required')
        if self.value is not None and (type(self.value) not in (int,float) or not isfinite(self.value)):
            raise ValueError('finite number or explicit missing value required')
        if not isinstance(self.source_url,str) or not self.source_url.startswith('https://') or type(self.causal_established) is not bool:
            raise ValueError('HTTPS source and an explicit causal flag required')


def supports_claim(evidence, requested_name, window_minutes, causal=False):
    if not isinstance(evidence,EvidenceWindow) or type(causal) is not bool:
        raise ValueError('evidence object and boolean request required')
    return (evidence.value is not None and evidence.outcome_name==requested_name
            and evidence.duration_minutes==window_minutes
            and (not causal or evidence.causal_established))
