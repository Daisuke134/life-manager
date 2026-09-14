"""The offer form must be read on the document we navigated to, not the one we are leaving.

Measured 2026-09-07: every Coconala listing reported `form_state:absent` with
`url='https://coconala.com/'` and an **empty title**. The real top page has a title, so the
document had not rendered -- `document.readyState` is still 'complete' for the previous document
until `Page.navigate` commits, so the first evaluate read the old page's location and the offer
form was judged 'redirected' against it. Coconala had applied to nothing since 2026-09-02.

Run: python3 -m pytest skills/earn/gig/tests/test_offer_form_settling.py
"""

import asyncio
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import application_parent  # noqa: E402

FORM_URL = "https://coconala.com/offers/add/5256493"


class _Page:
    """Replays a sequence of (url, readyState) observations, then repeats the last one."""

    def __init__(self, observations):
        self.observations = list(observations)
        self.reads = 0

    async def eval_json(self, ws, expression, call_id):
        index = min(self.reads, len(self.observations) - 1)
        self.reads += 1
        url, ready = self.observations[index]
        return {"url": url, "ready": ready}, call_id + 1


def _settle(observations, seconds=1.0):
    page = _Page(observations)
    settler = application_parent.CdpParentEffects._settle_on_application_form
    target = type("T", (), {"_eval_json": page.eval_json})()
    asyncio.run(settler(target, object(), "5256493", 1, seconds=seconds))
    return page


def test_it_waits_through_the_document_it_is_leaving():
    """The production shape: the old page answers first, the form arrives a poll later."""
    page = _settle([
        ("https://coconala.com/", "complete"),
        ("https://coconala.com/", "loading"),
        (FORM_URL, "interactive"),
    ])
    assert page.reads == 3


def test_it_returns_immediately_once_the_form_is_the_document():
    page = _settle([(FORM_URL, "complete")])
    assert page.reads == 1


def test_a_url_that_matches_but_has_not_rendered_is_not_accepted_yet():
    page = _settle([(FORM_URL, "loading"), (FORM_URL, "complete")])
    assert page.reads == 2


def test_a_genuine_redirect_still_ends_so_the_caller_can_report_it():
    """Never block forever: a real redirect must be reported, with the settled page's identity."""
    page = _settle([("https://coconala.com/login", "complete")], seconds=0.5)
    assert page.reads >= 1
