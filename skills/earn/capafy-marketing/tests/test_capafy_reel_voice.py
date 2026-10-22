import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import capafy_reel_voice as voice  # noqa: E402


def test_narration_is_demo_first_and_contains_no_fabricated_first_person_story():
    text = voice.narration(
        ["Day 1 is where you quit.", "One topic. Five hooks."],
        [
            "Hook Lab: gym video",
            "Hooks Hook Lab wrote. Swipe.",
            "“You're not lazy. You're doing week one wrong.”",
            "“Stop going to the gym every day.”",
            "“Why does everyone quit by January 20th?”",
        ],
        ["Search Hook Lab", "on Capafy", "5+ hooks. A timed script."],
    )

    assert "I have a confession" not in text
    assert "I used to spend an hour" not in text
    assert "Day 1 is where you quit" in text
    assert "Search Hook Lab on Capafy" in text
    assert "promise" not in text.lower()


def test_opening_frame_shows_product_value_and_is_not_held_for_five_seconds():
    assert voice.OPENING_LINES == ("ONE TOPIC.", "FIVE HOOKS.")
    assert voice.LEAD <= 1.0
