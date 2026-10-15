#!/usr/bin/env python3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capafy_reel_voice import narration

CTA_HOOKLAB = ["Search Hook Lab", "on Capafy", "Win the first 3 seconds.", "Open Capafy →", "CAPAFY.AI"]

HOOK = ["Your coding video is good.", "They swipe in 3 seconds."]
CARDS = ["Learn-to-code TikTok: 3 hooks", "Contrarian",
         "“AI didn't kill learning to code. It killed learning it badly.”", "→", "On-screen: Self-taught in the AI era",
         "Stakes", "“If you quit at month three, this is probably why.”", "→", "On-screen: Why self-taught coders quit",
         "Contrarian", "Recommended", "“You don't need a bootcamp. You need what bootcamps secretly sell.”", "→",
         "On-screen: Bootcamps sell 1 thing", "✓", "Script"]


def test_narration_reads_hook_three_quotes_and_one_cta():
    assert narration(HOOK, CARDS, CTA_HOOKLAB) == (
        "Your coding video is good. They swipe in three seconds. "
        "Here are three hooks Hook Lab wrote for a learn-to-code TikTok. "
        "One. AI didn't kill learning to code. It killed learning it badly. "
        "Two. If you quit at month three, this is probably why. "
        "Three. You don't need a bootcamp. You need what bootcamps secretly sell. "
        "Search Hook Lab on Capafy. Win the first three seconds.")


def test_narration_refuses_reel_without_three_quotes():
    with pytest.raises(ValueError):
        narration(HOOK, CARDS[:5], CTA_HOOKLAB)


def test_narration_names_the_product_on_the_cta_and_reads_a_script_reel():
    hook = ["Your workout video is good.", "Your script loses them."]
    cards = ["Home-workout TikTok: the 30s script", "Hook 0-3s", "“No gym. No equipment. No babysitter. Just 20 minutes.”",
             "Build 3-7s", "“Five moves, 40 seconds on, 20 off. Four rounds.”", "Payoff 22-26s",
             "“20 minutes, and you're back before anyone notices.”"]
    cta = ["Search TikTok Script Pro", "on Capafy", "Hook-first scripts, timed.", "Open Capafy →", "CAPAFY.AI"]
    text = narration(hook, cards, cta)
    assert "Hook Lab" not in text
    assert "Here is the script TikTok Script Pro wrote for a home-workout TikTok." in text
    assert text.endswith("Search TikTok Script Pro on Capafy. Hook-first scripts, timed.")
