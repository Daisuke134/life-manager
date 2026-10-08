#!/usr/bin/env python3
"""due_slot.py -- the slot currently due for a daily JST (or other tz) cadence.

Python port of apps/life-manager/lib/honne-ja-shadow-schedule.js's
marketingVideoDueSlot: the due slot for `now` is the latest "HH:MM" entry of
the current local day whose wall time has already passed, returned as the
exact UTC instant (so re-polling inside the same slot window always resolves
to the same instant -- the idempotency key for the per-slot ledger).
"""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

SLOT_PATTERN = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")


def due_slot_iso(now_utc: datetime, tz_name: str, slots: list[str]) -> str | None:
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    local = now_utc.astimezone(ZoneInfo(tz_name))
    now_minutes = local.hour * 60 + local.minute
    due = None
    for slot in slots:
        match = SLOT_PATTERN.match(str(slot))
        if not match:
            raise ValueError(f"invalid slot: {slot!r}")
        hour, minute = int(match.group(1)), int(match.group(2))
        if now_minutes >= hour * 60 + minute:
            due = (hour, minute)
    if due is None:
        return None
    hour, minute = due
    local_slot = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return local_slot.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")
