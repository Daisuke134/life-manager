"""K001: provenance is mandatory; URLs never imply ingestion, privacy or use rights."""
from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from manager_core.evidence import _url


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("nonempty text required")
    return value


def _aware(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    return value


@dataclass(frozen=True)
class Source:
    source_id: str
    url: str
    license_id: str
    rights: str
    content_sha256: str
    retrieved_at: datetime
    privacy_class: str

    def __post_init__(self):
        _text(self.source_id)
        _url(self.url)
        _text(self.license_id)
        if self.rights != "allowed_with_conditions":
            raise ValueError("unknown, held or prohibited source rights")
        if not isinstance(self.content_sha256, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", self.content_sha256):
            raise ValueError("verified SHA-256 reference required")
        _aware(self.retrieved_at)
        if self.privacy_class != "public_nonpersonal":
            raise ValueError("private/uncategorized records cannot enter Manager")

    def require_fresh(self, now: datetime, max_age_hours: float) -> None:
        _aware(now)
        if type(max_age_hours) not in (int, float) or not (0 < max_age_hours < 1e6):
            raise ValueError("positive bounded max age required")
        age = now - self.retrieved_at
        if age < timedelta(0) or age > timedelta(hours=max_age_hours):
            raise ValueError("source is stale or future-dated")
