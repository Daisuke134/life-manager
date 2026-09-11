"""A changed proposal field must name itself.

Measured 2026-09-07: 81 of the recent Lancers wake summaries skipped with the single code
`proposal_form_changed`, against 7 genuine declines (`video_or_animation`,
`mandatory_human_presence`). The lane was not short of work -- it could not fill the form. Every
strict matcher in application_tick.py raises the same bare error, so one changed attribute anywhere
in the form produced a failure nobody could act on, and Lancers submitted nothing today.

Run: python3 -m pytest apps/lancers-revenue/tests/test_form_change_evidence.py
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

TICK = Path(__file__).resolve().parents[3] / "skills" / "earn" / "lancers" / "scripts" / "application_tick.py"


def _module():
    spec = importlib.util.spec_from_file_location("lancers_tick_under_test", TICK)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Locator:
    """Enough of a Playwright locator for the matchers: a count, a visibility, and a repr."""

    def __init__(self, count, visible=True, selector="form#ProposalProposeForm"):
        self._count, self._visible, self._selector = count, visible, selector

    def count(self):
        return self._count

    def is_visible(self):
        if self._visible == "raise":
            raise RuntimeError("detached")
        return self._visible

    def __str__(self):
        return f"<Locator selector='{self._selector}'>"


@pytest.fixture()
def tick(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "FORM_EVIDENCE", tmp_path / "proposal-form-changes.jsonl")
    return module


def _rows(tick):
    path = tick.FORM_EVIDENCE
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_a_selector_that_matches_nothing_names_itself(tick):
    with pytest.raises(RuntimeError, match="proposal_form_changed"):
        tick._one(_Locator(0, selector="textarea#ProposalDescription"))
    row = _rows(tick)[0]
    assert "ProposalDescription" in row["selector"]
    assert (row["why"], row["found"]) == ("count_not_one", 0)


def test_a_selector_that_matches_several_names_itself(tick):
    """Ambiguity breaks the form as surely as absence, and looks identical without this."""
    with pytest.raises(RuntimeError):
        tick._one(_Locator(3, selector="#FeeApp input[type=text]"))
    assert _rows(tick)[0]["found"] == 3


def test_a_present_but_hidden_field_is_distinguished_from_a_missing_one(tick):
    with pytest.raises(RuntimeError):
        tick._visible_one(_Locator(1, visible=False, selector="#form_end"))
    row = _rows(tick)[0]
    assert (row["why"], row["found"]) == ("not_visible", 1)


def test_a_visibility_check_that_throws_is_still_recorded(tick):
    with pytest.raises(RuntimeError):
        tick._visible_one(_Locator(1, visible="raise", selector="#FeeApp input"))
    assert _rows(tick)[0]["why"] == "visibility_check_failed"


def test_a_matching_field_records_nothing(tick):
    tick._visible_one(_Locator(1, visible=True))
    assert _rows(tick) == []


def test_recording_never_raises_into_the_lane(tick, tmp_path):
    """Diagnostics must not be able to fail a submission."""
    blocked = tmp_path / "file"
    blocked.write_text("x", encoding="utf-8")
    tick.FORM_EVIDENCE = blocked / "nested.jsonl"
    with pytest.raises(RuntimeError, match="proposal_form_changed"):
        tick._one(_Locator(0))
