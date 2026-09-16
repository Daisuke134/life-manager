"""One unreachable source must not end the pass, and the exit must say which happened.

Measured 2026-09-06: `hf-gig-apply-direct` delivered its report (`message_id 62188`,
`transport: sent`) and still ended `entrypoint_exit_1`, every wake. The only non-empty stderr was
`{"error":"source_not_found:single:new","error_type":"ParentContractError"}`.

A 403 on one source was already absorbed -- recorded, cursor moved on, pass ends ok. A page whose
title matched the not-found pattern was not, so it reached the wrapper as an unrecognised parent
failure and killed the pass. That made two very different things produce the same exit 1: "one of
several sources is missing" and "this lane never reported at all".

Run: python3 -m pytest skills/earn/gig/tests/test_source_failure_absorption.py
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import application_direct  # noqa: E402
import b2_result_gate  # noqa: E402


def _completed(error: str | None, *, error_type: str = "ParentContractError") -> subprocess.CompletedProcess:
    stderr = ""
    if error is not None:
        stderr = json.dumps({"ok": False, "error": error, "error_type": error_type,
                             "error_at": "application_parent.py:953"}) + "\n"
    return subprocess.CompletedProcess(args=["parent"], returncode=2, stdout="", stderr=stderr)


def test_access_denial_is_recognised_as_a_survivable_source_failure():
    assert application_direct._temporary_source_denial(
        _completed("source_access_denied:single:new")
    ) == ("single:new", "source_access_denied")


def test_not_found_is_recognised_too_and_its_diagnostic_detail_is_not_read_as_the_id():
    """The parent appends the observed title; the id must survive that."""
    observed = application_direct._temporary_source_denial(
        _completed("source_not_found:single:new title='お探しのページは見つかりません | ココナラ'")
    )
    assert observed == ("single:new", "source_not_found")


def test_an_unrelated_contract_error_still_ends_the_pass():
    assert application_direct._temporary_source_denial(
        _completed("snapshot_required_sources_invalid")
    ) is None


def test_single_source_failure_advances_to_retainer_source(tmp_path):
    context = tmp_path / "b2-context.json"
    context.write_text(json.dumps({
        "required_search_source_ids": ["single:new", "retainer:new"],
    }), encoding="utf-8")

    assert b2_result_gate.next_required_source_cursor(
        context, "single:new", skipped_source_ids={"single:new"},
    ) == {
        "source_id": "retainer:new",
        "previous_url": "",
        "next_url": "https://coconala.com/job_matching/outsources",
        "reason": "continue_after_temporary_source_failure",
    }


def test_a_non_contract_failure_still_ends_the_pass():
    assert application_direct._temporary_source_denial(
        _completed("boom", error_type="RuntimeError")
    ) is None
    assert application_direct._temporary_source_denial(_completed(None)) is None


@pytest.mark.parametrize(
    "kind,temporary",
    [("source_access_denied", True), ("source_not_found", False)],
)
def test_recorded_failure_separates_what_clears_by_itself_from_what_does_not(tmp_path, kind, temporary):
    """A 403 is expected to clear. A page that is not there will not, and must not be retried
    forever under a label that says it is temporary."""
    failures: dict[str, dict] = {}
    application_direct._record_temporary_source_failure(
        tmp_path, failures, "single:new", "refresh", kind,
    )
    assert failures["single:new"] == {
        "source_id": "single:new",
        "phase": "refresh",
        "error": kind,
        "temporary": temporary,
        "exhausted": False,
    }
    written = json.loads((tmp_path / "temporary-source-failures.json").read_text(encoding="utf-8"))
    assert written["sources"] == [failures["single:new"]]


def test_the_default_kind_stays_access_denied_for_callers_that_pass_none():
    failures: dict[str, dict] = {}
    application_direct._record_temporary_source_failure(
        Path("/tmp"), failures, "single:new", "refresh",
    )
    assert failures["single:new"]["error"] == "source_access_denied"


def _cursor(tmp_path: Path, next_url: str, source_id: str = "single:new") -> Path:
    path = tmp_path / "b2-coverage-cursor.json"
    path.write_text(json.dumps({
        "source_id": source_id,
        "previous_url": "https://coconala.com/requests?page=8&recruiting=true&sort=new",
        "next_url": next_url,
        "reason": "next_page",
        "prior_inspected_request_ids": [],
    }), encoding="utf-8")
    return path


def test_running_off_the_last_page_restarts_the_source_instead_of_failing(tmp_path):
    """The exact production shape: page 8 rendered, page 9 does not exist.

    Measured 2026-09-06 on run gig-apply-direct-1788704318844213000-62661. `single:new` was the
    only required source, so 'missing source' left no successor to move to and the pass failed --
    every wake, with nothing actually wrong.
    """
    path = _cursor(tmp_path, "https://coconala.com/requests?page=9&recruiting=true&sort=new")

    assert application_direct._restart_cursor_after_pagination_end(
        path, "single:new", "source_not_found") is True

    cursor = json.loads(path.read_text(encoding="utf-8"))
    assert cursor["reason"] == "restart_after_pagination_end"
    assert cursor["previous_url"] == ""
    # Back to the first page, with the source's own filters intact and no page parameter.
    assert cursor["next_url"] == "https://coconala.com/requests?recruiting=true&sort=new"


def test_a_first_page_that_is_missing_is_a_real_missing_source(tmp_path):
    """No page parameter means the source itself answered 404, which must still fail loudly."""
    path = _cursor(tmp_path, "https://coconala.com/requests?recruiting=true&sort=new")
    assert application_direct._restart_cursor_after_pagination_end(
        path, "single:new", "source_not_found") is False


def test_page_one_is_not_treated_as_an_overrun(tmp_path):
    path = _cursor(tmp_path, "https://coconala.com/requests?page=1&recruiting=true&sort=new")
    assert application_direct._restart_cursor_after_pagination_end(
        path, "single:new", "source_not_found") is False


def test_an_access_denial_is_never_restarted_as_pagination(tmp_path):
    path = _cursor(tmp_path, "https://coconala.com/requests?page=9&recruiting=true&sort=new")
    assert application_direct._restart_cursor_after_pagination_end(
        path, "single:new", "source_access_denied") is False


def test_a_cursor_for_another_source_is_left_alone(tmp_path):
    path = _cursor(tmp_path, "https://coconala.com/requests?page=9&recruiting=true&sort=new")
    assert application_direct._restart_cursor_after_pagination_end(
        path, "single:keyword", "source_not_found") is False
    assert json.loads(path.read_text(encoding="utf-8"))["reason"] == "next_page"


def test_a_missing_or_unreadable_cursor_does_not_pretend_to_restart(tmp_path):
    assert application_direct._restart_cursor_after_pagination_end(
        tmp_path / "absent.json", "single:new", "source_not_found") is False
    broken = tmp_path / "broken.json"
    broken.write_text("{ not json", encoding="utf-8")
    assert application_direct._restart_cursor_after_pagination_end(
        broken, "single:new", "source_not_found") is False
