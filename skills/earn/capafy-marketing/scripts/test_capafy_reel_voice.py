#!/usr/bin/env python3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import capafy_reel_voice
from capafy_reel_voice import CONFESSION, narration

CTA_HOOKLAB = ["Search Hook Lab", "on Capafy", "Win the first 3 seconds.", "Open Capafy →", "CAPAFY.AI"]

HOOK = ["Your coding video is good.", "They swipe in 3 seconds."]
CARDS = ["Learn-to-code TikTok: 3 hooks", "Contrarian",
         "“AI didn't kill learning to code. It killed learning it badly.”", "→", "On-screen: Self-taught in the AI era",
         "Stakes", "“If you quit at month three, this is probably why.”", "→", "On-screen: Why self-taught coders quit",
         "Contrarian", "Recommended", "“You don't need a bootcamp. You need what bootcamps secretly sell.”", "→",
         "On-screen: Bootcamps sell 1 thing", "✓", "Script"]


def test_narration_reads_hook_three_quotes_and_one_cta():
    assert narration(HOOK, CARDS, CTA_HOOKLAB) == (
        "I have a confession. I used to spend an hour on the first line of every video. "
        "Your coding video is good. They swipe in three seconds. "
        "The solution? Hook Lab. Here are three hooks it wrote for a learn-to-code TikTok. "
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
    assert "The solution? TikTok Script Pro. Here is the script it wrote for a home-workout TikTok." in text
    assert text.endswith("Search TikTok Script Pro on Capafy. Hook-first scripts, timed.")


def test_narration_keeps_platform_names_and_uses_an_before_vowels():
    cards = ["Instagram small business: 3 hooks", "“A.”", "“B.”", "“C.”"]
    assert "for an Instagram small business." in narration(HOOK, cards, CTA_HOOKLAB)
    cards = ["Learn-to-code TikTok: 3 hooks", "“A.”", "“B.”", "“C.”"]
    assert "for a learn-to-code TikTok." in narration(HOOK, cards, CTA_HOOKLAB)


def test_narration_opens_with_the_confession_winners_use():
    assert narration(HOOK, CARDS, CTA_HOOKLAB).startswith(CONFESSION)


def test_tts_falls_back_to_macos_say_when_edge_tts_is_refused(tmp_path, monkeypatch):
    calls = []

    def fake_run(*cmd):
        calls.append(cmd[0])
        if cmd[0] == "edge-tts":
            raise capafy_reel_voice.subprocess.CalledProcessError(1, cmd, stderr=b"403")
        if cmd[0] == "ffmpeg":
            Path(cmd[-1]).write_bytes(b"mp3")

    monkeypatch.setattr(capafy_reel_voice, "_run", fake_run)
    (tmp_path / "n.txt").write_text("hi")
    assert capafy_reel_voice.tts(tmp_path / "n.txt", tmp_path / "v.mp3") == capafy_reel_voice.FALLBACK_VOICE
    assert calls == ["edge-tts", "say", "ffmpeg"]
