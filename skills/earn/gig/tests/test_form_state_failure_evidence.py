"""form_state="absent" must say which of its two causes it was.

Measured 2026-09-05..07: every listing the Coconala Apply lane observed was rejected with the
single reason `form_state:absent` -- 100% of them, across every retained run. The listings were
open: page present, accepting control present, deadline in the future. Only the form was not
found.

Two very different faults collapse into that one word, and they have opposite fixes:
`application_form_redirected` is a session or routing problem, `application_form_controls_missing`
means the provider changed the markup. Neither string appeared anywhere in the run evidence, so
four days of zero applications carried no way to tell which.

The reason is written beside the lifecycle row, never inside it: that row is content-hashed over a
fixed field list, so an extra key there fails contract validation instead of helping.

Run: python3 -m pytest skills/earn/gig/tests/test_form_state_failure_evidence.py
"""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import application_parent  # noqa: E402


class _Recorder:
    """Only the two attributes _record_form_failure touches."""

    def __init__(self, evidence_dir: Path):
        self.evidence_dir = evidence_dir
        self.pass_id = "test-pass"

    record = application_parent.CdpParentEffects._record_form_failure


def _rows(evidence_dir: Path) -> list[dict]:
    path = evidence_dir / "form-state-failures.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_a_redirected_form_records_where_it_actually_landed(tmp_path):
    error = application_parent.ParentContractError("application_form_redirected")
    error.observed = {"url": "https://coconala.com/login", "title": "ログイン | ココナラ"}

    _Recorder(tmp_path).record("5247633", error)

    row = _rows(tmp_path)[0]
    assert row["request_id"] == "5247633"
    assert row["error"] == "application_form_redirected"
    assert row["observed"]["url"] == "https://coconala.com/login"


def test_missing_controls_record_which_control_was_missing(tmp_path):
    error = application_parent.ParentContractError("application_form_controls_missing")
    error.observed = {"url": "https://coconala.com/requests/5247633/offers/new",
                      "title": "見積り | ココナラ",
                      "has_content": True, "has_price": False, "has_date": True}

    _Recorder(tmp_path).record("5247633", error)

    observed = _rows(tmp_path)[0]["observed"]
    assert observed["has_price"] is False
    assert observed["has_content"] is True


def test_each_listing_appends_its_own_line(tmp_path):
    recorder = _Recorder(tmp_path)
    for request_id in ("1", "2", "3"):
        error = application_parent.ParentContractError("application_form_controls_missing")
        error.observed = {"url": "u", "title": "t"}
        recorder.record(request_id, error)
    assert [row["request_id"] for row in _rows(tmp_path)] == ["1", "2", "3"]


def test_an_error_without_detail_is_still_recorded(tmp_path):
    """An unexpected exception type must not silently produce no evidence at all."""
    _Recorder(tmp_path).record("5247633", RuntimeError("boom"))
    row = _rows(tmp_path)[0]
    assert (row["error"], row["error_type"], row["observed"]) == ("boom", "RuntimeError", None)


def test_recording_never_raises_into_the_lane(tmp_path):
    """Diagnostics must not be able to fail a pass."""
    unwritable = tmp_path / "file-not-a-dir"
    unwritable.write_text("x", encoding="utf-8")
    _Recorder(unwritable).record("5247633", RuntimeError("boom"))


def test_raw_cdp_control_count_uses_shared_dom_contract_and_stable_code(tmp_path):
    effects = object.__new__(application_parent.CdpParentEffects)
    effects.evidence_dir = tmp_path
    observed = {"url": "https://coconala.com/offers/add/1", "title": "提案"}

    with pytest.raises(application_parent.ParentContractError,
                       match="application_form_controls_missing") as caught:
        effects._require_dom_one('textarea[name="data[Offer][content]"]', 0, observed,
                                 "application_form_controls_missing")

    assert caught.value.observed == observed
    row = json.loads((tmp_path / "dom-contract-failures.jsonl").read_text().splitlines()[0])
    assert (row["platform"], row["selector"], row["found"], row["observed"]) == (
        "coconala", 'textarea[name="data[Offer][content]"]', 0, observed,
    )


def test_the_listing_page_apply_route_is_recorded_beside_the_failure(tmp_path):
    """Coconala's own apply button is the tiebreaker.

    Measured 2026-09-07: `/offers/add/<id>` redirects to the fully-rendered top page for every
    listing. If the button points somewhere else, the provider moved the form; if it points at the
    same route, the account cannot use it. Those have opposite fixes, and only its existence was
    ever read.
    """
    error = application_parent.ParentContractError("application_form_redirected")
    error.observed = {"url": "https://coconala.com/", "title": "ココナラ"}

    _Recorder(tmp_path).record(
        "5256493", error, control={"href": "/requests/5256493/offers/new", "tag": "a"},
    )

    row = _rows(tmp_path)[0]
    assert row["accepting_control"]["href"] == "/requests/5256493/offers/new"
    assert row["accepting_control"]["tag"] == "a"


def test_a_failure_without_a_control_still_records(tmp_path):
    error = application_parent.ParentContractError("application_form_controls_missing")
    _Recorder(tmp_path).record("5256493", error)
    assert _rows(tmp_path)[0]["accepting_control"] is None
