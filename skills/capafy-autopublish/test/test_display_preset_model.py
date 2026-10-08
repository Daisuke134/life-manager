"""Claude Sonnet 5.5 hosted-model factory default (2026-10-08).

Capafy's "LLM モデル" display combobox has no "Claude Sonnet 5.5" preset, so a
listing whose `Primary Model:` is 5.5 must still run on the real
`anthropic/claude-sonnet-5.5` OpenRouter id while displaying the existing
"Claude Sonnet 5" preset (drive_checkpoint2.py's _raw_fix_display_model only
accepts an exact preset match -- see skills/capafy-autopublish/scripts/
drive_checkpoint2.py).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1] / "scripts"
BUILD_CONFIG = ROOT / "build_config.py"

LISTING_SONNET_5_5 = """Primary Model: Claude Sonnet 5.5 · category: 生産性 · tags: a, b, c

| cycle | price | cap | trial |
|---|---|---|---|
| week | $9.99 | 25 | No Free Trial |

## Title
Test Agent

## shortDescription
Test short description.

## welcomeMessage
Welcome. Example: "test input"

## detailedDescription
Detailed body.
"""


def _build(tmp_path: Path, listing_text: str) -> dict:
    listing = tmp_path / "LISTING.md"
    listing.write_text(listing_text, encoding="utf-8")
    icon = tmp_path / "icon.svg"
    icon.write_text("<svg/>", encoding="utf-8")
    out = tmp_path / "config.json"
    result = subprocess.run(
        [sys.executable, str(BUILD_CONFIG), str(listing), str(icon), str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(out.read_text(encoding="utf-8"))


def test_sonnet_5_5_runs_on_real_id_but_displays_sonnet_5_preset(tmp_path: Path) -> None:
    cfg = _build(tmp_path, LISTING_SONNET_5_5)
    assert cfg["model_id"] == "anthropic/claude-sonnet-5.5"
    assert cfg["model"] == "Claude Sonnet 5"


def test_sonnet_5_has_no_display_remap(tmp_path: Path) -> None:
    cfg = _build(tmp_path, LISTING_SONNET_5_5.replace("Claude Sonnet 5.5", "Claude Sonnet 5"))
    assert cfg["model_id"] == "anthropic/claude-sonnet-5"
    assert cfg["model"] == "Claude Sonnet 5"
