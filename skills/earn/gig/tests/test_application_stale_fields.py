from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import application_parent as parent  # noqa: E402


def test_stale_fields_names_the_changed_payload_field_and_first_brief_line():
    snapshot = {"title": "依頼", "brief": "本文\n予算は5千円\n以上", "budget_max_jpy": 10000}
    fresh = {"title": "依頼", "brief": "本文\n予算は8千円\n以上", "budget_max_jpy": 10000}

    assert parent._stale_fields(snapshot, fresh) == [
        "brief@2:予算は5千円|予算は8千円",
    ]


def test_stale_fields_is_empty_for_identical_payloads():
    payload = {"title": "依頼", "brief": "本文"}
    assert parent._stale_fields(payload, dict(payload)) == []
