#!/usr/bin/env python3
import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capafy_reel_daily import NICHES, caption, pick_niche, slots, validate_spec

SPEC = {"noun": "baking video", "hook_a": "Your baking video is good.", "hook_b": "They swipe in 3 seconds.",
        "title": "Baking Reel: 3 hooks",
        "cards": [["Mistake", "Your sourdough isn't flat because of the flour.", "The real reason it's flat"],
                  ["Question", "Why do bakery loaves rise higher than yours?", "Bakery loaves vs yours"],
                  ["Result", "One fold, one night, one perfect loaf.", "One fold. One night."]]}


def test_pick_niche_rotates_by_date_and_covers_every_niche():
    start = dt.date(2026, 10, 22)
    picked = {pick_niche(start + dt.timedelta(days=i))["key"] for i in range(len(NICHES))}
    assert picked == {n["key"] for n in NICHES}


def test_slots_match_existing_queue_times():
    assert slots(dt.date(2026, 10, 22)) == {"ig": "2026-10-22T13:00:00.000Z", "x": "2026-10-22T17:00:00.000Z"}


def test_caption_copies_the_live_queue_format():
    assert caption(SPEC) == ("Your baking video is good. They swipe in 3 seconds.\n\n"
                             "Hook Lab turns one line about your video into 5+ first-3-second hooks, "
                             "a timed script and a caption.\n\nSearch \"Hook Lab\" on Capafy to try it.")


def test_validate_spec_accepts_layout_safe_copy_and_rejects_overflow():
    validate_spec(SPEC)
    long = {**SPEC, "cards": [["Mistake", "x" * 120, "ok"]] + SPEC["cards"][1:]}
    with pytest.raises(ValueError):
        validate_spec(long)
    with pytest.raises(ValueError):
        validate_spec({**SPEC, "cards": SPEC["cards"][:2]})
