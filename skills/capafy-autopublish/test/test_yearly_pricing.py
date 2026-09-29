"""Yearly plan support in build_config.py / lint_listing.py.

Capafy's live billing data (market snapshot 20260929, e.g. agent 5133292529)
confirms `cycleType: "year"` is the exact subscription cycle value alongside
`day`/`week`/`month` — a `| year | $149.99 | 156 | No Free Trial |` row in
LISTING.md's pricing table must parse the same way the other cycles do.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1] / "scripts"
BUILD_CONFIG = ROOT / "build_config.py"
LINT = ROOT / "lint_listing.py"

YEARLY_LISTING = """Primary Model: DeepSeek V4.1 Flash · category: 生産性 · tags: slides, presentation, deck

| cycle | price | cap | trial |
|---|---|---|---|
| week | $9.99 | 15 | No Free Trial |
| month | $24.99 | 35 | No Free Trial |
| year | $149.99 | 156 | No Free Trial |

## Title
Test Agent

## shortDescription
Test short description.

## welcomeMessage
Welcome. Example: "test input"

## detailedDescription
Detailed body.
"""


def test_build_config_parses_year_plan(tmp_path: Path) -> None:
    listing = tmp_path / "LISTING.md"
    listing.write_text(YEARLY_LISTING, encoding="utf-8")
    icon = tmp_path / "icon.svg"
    icon.write_text("<svg/>", encoding="utf-8")
    out = tmp_path / "config.json"

    result = subprocess.run(
        [sys.executable, str(BUILD_CONFIG), str(listing), str(icon), str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    cfg = json.loads(out.read_text(encoding="utf-8"))
    cycles = {p["cycle"]: p for p in cfg["plans"]}
    assert set(cycles) == {"week", "month", "year"}
    assert cycles["year"]["price"] == "149.99"
    assert cycles["year"]["cap"] == "156"
    assert cycles["year"]["trial"] is None


def test_lint_listing_accepts_year_row(tmp_path: Path) -> None:
    listing = tmp_path / "LISTING.md"
    listing.write_text(YEARLY_LISTING, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(LINT), str(listing)], capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESULT: PASS" in result.stdout
