"""2026-10-16: the conscience judge BLOCKed run 20261016-014724 because the mandatory CTA link
carried run_id/click_id/ct attribution params, so a draft that passed every other gate never shipped."""
from pathlib import Path

GATE = Path(__file__).resolve().parents[1] / "scripts" / "conscience-gate.sh"


def test_conscience_prompt_exempts_own_cta_attribution_params():
    text = GATE.read_text(encoding="utf-8")
    assert "standard marketing attribution" in text
    for key in ("run_id", "click_id", "ct", "utm_"):
        assert key in text.split("standard marketing attribution")[0].rsplit("Query parameters", 1)[-1]
