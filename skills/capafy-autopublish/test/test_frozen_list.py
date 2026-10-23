"""skills/capafy/FROZEN.json: three views of the same seller list must agree."""
import json
from pathlib import Path

FROZEN = json.loads((Path(__file__).resolve().parents[2] / "capafy" / "FROZEN.json").read_text())


def test_the_three_lists_name_the_same_agents() -> None:
    ids = set(FROZEN["agent_ids"])
    assert ids == set(FROZEN["sellers"]) == set(FROZEN["names"])


def test_tiktok_series_continuity_planner_is_frozen_after_its_first_paid_sale() -> None:
    # 2026-10-23: first paid order since 9/29 ($9.99 week, no trial). Every earlier seller stopped
    # selling after a version update, so it is never edited, repriced or re-submitted.
    assert "9425449917" in FROZEN["agent_ids"]
