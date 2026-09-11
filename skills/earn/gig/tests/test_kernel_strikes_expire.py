"""A rejection stops being evidence once the thing that produced it has changed.

The title guard refused `line_bot_dev` three times. All three predated the two prompt
changes that taught the model the shapes it kept getting wrong, and the three-strike rule
counted them anyway -- so the gap was closed permanently on a claim that had already been
answered, and the filled draft behind it could never be finished. Shipping the fix must be
what clears the count, or a fix can never prove itself.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "_kernel_strikes",
    Path(__file__).resolve().parents[1] / "scripts" / "storefront_kernel.py")
KERNEL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(KERNEL)

RELEASE = 1_000_000
GUARD = "storefront_create_title_stem_not_continuative"


def _r(epoch, guard=GUARD, detail=""):
    return {"observed_at_epoch": epoch, "rejection": guard + (f":{detail}" if detail else "")}


def test_three_strikes_before_this_release_no_longer_count():
    old = [_r(RELEASE - 900), _r(RELEASE - 600), _r(RELEASE - 300)]
    assert KERNEL.three_strike_same_guard(old, since_epoch=RELEASE) is None


def test_three_strikes_since_this_release_still_count():
    fresh = [_r(RELEASE + 10), _r(RELEASE + 20), _r(RELEASE + 30)]
    assert KERNEL.three_strike_same_guard(fresh, since_epoch=RELEASE) == GUARD


def test_a_rejection_exactly_at_the_release_moment_counts():
    rows = [_r(RELEASE), _r(RELEASE + 1), _r(RELEASE + 2)]
    assert KERNEL.three_strike_same_guard(rows, since_epoch=RELEASE) == GUARD


def test_two_fresh_and_one_stale_is_not_three():
    rows = [_r(RELEASE - 100), _r(RELEASE + 10), _r(RELEASE + 20)]
    assert KERNEL.three_strike_same_guard(rows, since_epoch=RELEASE) is None


def test_without_a_release_time_the_old_behaviour_stands():
    # A caller that cannot say when its configuration changed has no basis for discarding.
    old = [_r(RELEASE - 900), _r(RELEASE - 600), _r(RELEASE - 300)]
    assert KERNEL.three_strike_same_guard(old) == GUARD


def test_guard_identity_still_decides_not_the_full_message():
    rows = [_r(RELEASE + 1, detail="スプレッドシート"), _r(RELEASE + 2, detail="Dropbox"),
            _r(RELEASE + 3, detail="firestorage")]
    assert KERNEL.three_strike_same_guard(rows, since_epoch=RELEASE) == GUARD


def test_different_guards_are_never_three_strikes():
    rows = [_r(RELEASE + 1), _r(RELEASE + 2, guard="storefront_copy_names_prohibited_tool"),
            _r(RELEASE + 3)]
    assert KERNEL.three_strike_same_guard(rows, since_epoch=RELEASE) is None


@pytest.mark.parametrize("missing", [{}, {"rejection": GUARD}])
def test_a_row_with_no_timestamp_is_treated_as_stale_not_as_now(missing):
    rows = [_r(RELEASE + 1), _r(RELEASE + 2), missing]
    assert KERNEL.three_strike_same_guard(rows, since_epoch=RELEASE) is None
