"""Test-only UTC clock. Never import this helper from production or release code."""
from datetime import datetime, timezone

class FixedReviewDate(datetime):
    @classmethod
    def now(cls, tz=None):
        value=cls(2026,10,21,12,0,tzinfo=timezone.utc)
        return value.astimezone(tz) if tz is not None else value.replace(tzinfo=None)
