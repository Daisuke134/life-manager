import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import capafy_reel_daily as reel  # noqa: E402


SPEC = {
    "hook_a": "Day 1 is where you quit",
    "hook_b": "One topic. Five hooks.",
    "title": "Hook Lab: gym video",
    "cards": [
        ("Mistake", "You're not lazy. You're doing week one wrong.", "Week 1 mistake"),
        ("Contrarian", "Stop going to the gym every day.", "Do less, keep going"),
        ("Question", "Why does everyone quit by January 20th?", "The January 20th wall"),
    ],
    "cta_head": "Search Hook Lab on Capafy",
    "cta_sub": "5+ hooks. A timed script.",
}
UPLOADS = [{"id": "video-id", "path": "https://cdn.example/video.mp4"}]


def test_winner_reference_is_injected_as_structure_not_copy():
    prompt = reel.build_hook_lab_prompt({"key": "gym", "topic": "beginner gym video"}, ["A creator short title"])

    assert "https://www.youtube.com/watch?v=8dxSOdnkAlk" in prompt
    assert "copy its structure, not its words" in prompt.lower()
    assert "show the actual output in the opening seconds" in prompt.lower()
    assert "do not claim views, virality, sales, or time saved" in prompt.lower()


def test_spec_prompt_requires_a_real_hook_and_drops_generic_unsupported_openers():
    prompt = reel.build_spec_prompt("Recommended hook: Day 1 is where you quit")

    assert "hook_a must be copied verbatim from the Hook Lab output" in prompt
    assert "Your video is good" not in prompt
    assert "They swipe in 3 seconds" not in prompt


def test_hook_a_must_be_real_output_and_cta_is_the_listing_contract():
    output = (
        "Recommended hook: Day 1 is where you quit. "
        "You're not lazy. You're doing week one wrong. "
        "Stop going to the gym every day. "
        "Why does everyone quit by January 20th?"
    )
    spec = {**SPEC, "hook_a": "They swipe in 3 seconds"}
    with pytest.raises(ValueError, match="hook_a must be copied from the output"):
        reel.validate_spec(spec, output)

    spec = {**SPEC, "hook_a": "Day 1 is where you quit"}
    reel.validate_spec(spec, output)


def test_x_video_uses_registered_self_reply_ct_and_other_channels_do_not_fake_one():
    values = reel.post_values("x", SPEC, UPLOADS)

    assert len(values) == 2
    assert values[0]["image"] == UPLOADS
    assert "https://" not in values[0]["content"]
    assert values[1]["content"] == (
        "Try Hook Lab on Capafy: https://capafy.ai/agent/8123079349?ct=hooklab_x"
    )
    for network in ("ig", "tt", "tc"):
        values = reel.post_values(network, SPEC, UPLOADS)
        assert len(values) == 1
        assert "Search Hook Lab on Capafy" in values[0]["content"]
        assert "ct=capafy-reel-" not in values[0]["content"]
    ig = reel.post_values("ig", SPEC, UPLOADS)[0]["content"]
    assert "ct=hooklab_ig" in ig
    for network in ("tt", "tc"):
        assert "ct=hooklab_tiktok" not in reel.post_values(network, SPEC, UPLOADS)[0]["content"]
