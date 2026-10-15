#!/usr/bin/env python3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capafy_reel_voice import narration

HOOK = ["Your coding video is good.", "They swipe in 3 seconds."]
CARDS = ["Learn-to-code TikTok: 3 hooks", "Contrarian",
         "“AI didn't kill learning to code. It killed learning it badly.”", "→", "On-screen: Self-taught in the AI era",
         "Stakes", "“If you quit at month three, this is probably why.”", "→", "On-screen: Why self-taught coders quit",
         "Contrarian", "Recommended", "“You don't need a bootcamp. You need what bootcamps secretly sell.”", "→",
         "On-screen: Bootcamps sell 1 thing", "✓", "Script"]


def test_narration_reads_hook_three_quotes_and_one_cta():
    assert narration(HOOK, CARDS) == (
        "Your coding video is good. They swipe in three seconds. "
        "Here are three hooks Hook Lab wrote for a learn-to-code TikTok. "
        "One. AI didn't kill learning to code. It killed learning it badly. "
        "Two. If you quit at month three, this is probably why. "
        "Three. You don't need a bootcamp. You need what bootcamps secretly sell. "
        "Search Hook Lab on Capafy, and win the first three seconds.")


def test_narration_refuses_reel_without_three_quotes():
    with pytest.raises(ValueError):
        narration(HOOK, CARDS[:5])
