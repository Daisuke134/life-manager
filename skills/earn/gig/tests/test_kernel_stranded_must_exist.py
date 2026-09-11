"""A ledger row is not a draft. The seller's card census decides which drafts exist.

`new-listing-drafts.jsonl` outlives the drafts it describes: a draft deleted on an earlier
wake leaves its row behind as soon as the evidence directory naming that deletion is
collected, and `observed_deleted_draft_ids` can only report deletions it can still see.

Four such rows were live in production. Because the caller prefers the longest-waiting
draft, the stalest row -- the one most likely to name something already gone -- won every
time, and the one real filled draft sitting on the account was never chosen.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "_kernel_stranded",
    Path(__file__).resolve().parents[1] / "scripts" / "storefront_kernel.py")
KERNEL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(KERNEL)

NONE_DELETED = lambda evidence_dir: set()

# The four families the production ledger reported, oldest ledger position first. Only
# 4387924 still existed on the platform.
ROWS = [
    {"draft_service_id": "4371796", "capability_family": "ai-automation-builder",
     "status": "draft_created", "public_effect": 0},
    {"draft_service_id": "4384702", "capability_family": "user-interview-synthesizer",
     "status": "draft_created", "public_effect": 0},
    {"draft_service_id": "4385965", "capability_family": "mobile_app_dev",
     "status": "prepared", "public_effect": 0},
    {"draft_service_id": "4387924", "capability_family": "line_bot_dev",
     "status": "draft_created", "public_effect": 0},
]


@pytest.fixture
def state(tmp_path):
    (tmp_path / "evidence").mkdir()
    with (tmp_path / "new-listing-drafts.jsonl").open("w", encoding="utf-8") as handle:
        for row in ROWS:
            handle.write(json.dumps(row) + "\n")
    return tmp_path


def _call(state, live=None):
    return KERNEL.families_with_unpublished_drafts(
        state, set(), observed_deleted_draft_ids=NONE_DELETED, live_draft_ids=live)


def test_without_a_census_the_ledger_is_all_there_is(state):
    # Unchanged behaviour for callers that cannot say what exists.
    assert set(_call(state)) == {
        "ai-automation-builder", "user-interview-synthesizer", "mobile_app_dev", "line_bot_dev"}


def test_the_census_removes_every_draft_that_no_longer_exists(state):
    assert set(_call(state, live={"4356229", "4387924"})) == {"line_bot_dev"}


def test_the_one_real_draft_keeps_its_id_and_position(state):
    assert _call(state, live={"4387924"})["line_bot_dev"][0] == "4387924"


def test_an_empty_census_means_nothing_is_in_flight(state):
    assert _call(state, live=set()) == {}


def test_a_published_draft_is_still_excluded_even_if_the_census_lists_it(state):
    result = KERNEL.families_with_unpublished_drafts(
        state, {"4387924"}, observed_deleted_draft_ids=NONE_DELETED,
        live_draft_ids={"4387924"})
    assert "line_bot_dev" not in result


def test_a_deleted_draft_is_still_excluded_even_if_the_census_lists_it(state):
    result = KERNEL.families_with_unpublished_drafts(
        state, set(), observed_deleted_draft_ids=lambda _: {"4387924"},
        live_draft_ids={"4387924"})
    assert "line_bot_dev" not in result
