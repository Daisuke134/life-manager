"""Regression: x-article/ja became dormant 2026-09-29 (Dais: X moves to Postiz link
posts; the X Articles editor is permanently unreachable for our account).

A same-day run created under the still-persisted "active-four" contract label
can have no x-article/ja key at all (it was active when the run started but
staging never got that far) or a pre-transition terminal "unavailable" entry
(the earlier permanent-unavailable skip receipt). Both shapes must still
resume/plan honestly for the three revenue pairs; neither pair-set shape may
be read as "missing-targets".
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from publication_contract import ACTIVE_PAIRS, DORMANT_PAIRS  # noqa: E402
from publication_resume import PublicationStore  # noqa: E402


def _dormant_skip(pair: str) -> dict:
    return {
        "platform": pair.split("/", 1)[0],
        "lang": pair.split("/", 1)[1],
        "status": "skipped",
        "skip_receipt": {
            "type": "dormant-destination",
            "pair": pair,
            "reason": "dormant-destination",
            "slo": "not-applicable",
            "recorded_at": "2026-09-29T01:11:10.270438Z",
        },
    }


def _intent(pair: str, target: str) -> dict:
    platform, lang = pair.split("/", 1)
    return {
        "platform": platform,
        "lang": lang,
        "target_kind": "opaque",
        "target": target,
        "status": "intent",
        "intent_at": "2026-09-29T01:12:00Z",
    }


def _base_pairs() -> dict:
    pairs = {
        pair: _dormant_skip(pair)
        for pair in DORMANT_PAIRS
        if pair != "x-article/ja"
    }
    for pair in ACTIVE_PAIRS:
        pairs[pair] = _intent(pair, f"target-{pair.replace('/', '-')}")
    return pairs


def test_active_four_state_missing_x_article_ja_key_entirely_is_pair_set_valid() -> None:
    """Today's run (20260929-010128 shape): x-article/ja never got a key."""
    state = {
        "publication_contract": "active-four",
        "pairs": _base_pairs(),
    }
    assert "x-article/ja" not in state["pairs"]
    assert PublicationStore._pair_set_valid(state) is True


def test_active_four_state_with_permanent_unavailable_x_article_ja_is_pair_set_valid() -> None:
    """A run that already recorded the 2026-09-28 x-editor-unreachable failure."""
    state = {
        "publication_contract": "active-four",
        "pairs": {
            **_base_pairs(),
            "x-article/ja": {
                "platform": "x-article",
                "lang": "ja",
                "status": "unavailable",
                "error": "x-editor-unreachable:no-editor",
                "unavailable_at": "2026-09-28T12:00:00Z",
                "skip_receipt": {
                    "type": "permanent-unavailable",
                    "pair": "x-article/ja",
                    "reason": "x-editor-unreachable:no-editor",
                    "slo": "not-applicable",
                    "recorded_at": "2026-09-28T12:00:00Z",
                },
            },
        },
    }
    assert PublicationStore._pair_set_valid(state) is True


def test_active_four_state_with_bare_unavailable_x_article_ja_and_no_skip_receipt_is_invalid() -> None:
    """An unavailable entry without a skip receipt is still open work, not history."""
    state = {
        "publication_contract": "active-four",
        "pairs": {
            **_base_pairs(),
            "x-article/ja": {
                "platform": "x-article",
                "lang": "ja",
                "status": "unavailable",
                "error": "some-transient-error",
                "unavailable_at": "2026-09-28T12:00:00Z",
            },
        },
    }
    assert PublicationStore._pair_set_valid(state) is False


def test_active_four_state_missing_a_different_dormant_pair_is_still_invalid() -> None:
    """Only the newly-dormant x-article/ja may be entirely absent."""
    pairs = _base_pairs()
    del pairs["devto/en"]
    state = {"publication_contract": "active-four", "pairs": pairs}
    assert PublicationStore._pair_set_valid(state) is False


def test_active_pairs_no_longer_require_x_article_ja() -> None:
    assert "x-article/ja" not in ACTIVE_PAIRS
    assert "x-article/ja" in DORMANT_PAIRS


if __name__ == "__main__":
    test_active_four_state_missing_x_article_ja_key_entirely_is_pair_set_valid()
    test_active_four_state_with_permanent_unavailable_x_article_ja_is_pair_set_valid()
    test_active_four_state_with_bare_unavailable_x_article_ja_and_no_skip_receipt_is_invalid()
    test_active_four_state_missing_a_different_dormant_pair_is_still_invalid()
    test_active_pairs_no_longer_require_x_article_ja()
    print("ok")
