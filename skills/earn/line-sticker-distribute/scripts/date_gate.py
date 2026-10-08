#!/usr/bin/env python3
"""date_gate.py -- shared "has this local calendar date arrived yet" check.

Used by the bio-link rollout (setup_profile.py --website, once), the per-account
link_in_caption date (both 2026-10-10, Dais 2026-10-07: a brand-new account's first
days carry no outbound link), and the day-3+ engagement gate (ig-account-warmer
research: aggressive activity in the first 72h risks a ban). Pure date arithmetic,
copied shape from due_slot.py's own ZoneInfo use -- no new dependency.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


def local_date(now_utc: datetime, tz_name: str) -> date:
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    return now_utc.astimezone(ZoneInfo(tz_name)).date()


def is_on_or_after(now_utc: datetime, tz_name: str, date_str: str) -> bool:
    return local_date(now_utc, tz_name) >= date.fromisoformat(date_str)


def days_since(now_utc: datetime, tz_name: str, date_str: str) -> int:
    return (local_date(now_utc, tz_name) - date.fromisoformat(date_str)).days
