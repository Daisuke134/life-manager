"""The Substack done gate accepts only the audience the publication's payments_state allows."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "publication_remote_audience_gate", SCRIPTS / "publication_remote.py"
)
REMOTE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(REMOTE)

HOST = "aniccaai2026.substack.com"


def _page(payments_state: str | None) -> str:
    if payments_state is None:
        return "<html><h1>Title</h1></html>"
    data = {"pub": {"subdomain": "aniccaai2026", "payments_state": payments_state}}
    return (
        '<html><script type="application/json" id="preloads-json">'
        + json.dumps(data)
        + "</script><h1>Title</h1></html>"
    )


def _draft(audience: str, paywalls: int) -> dict:
    content = [{"type": "paragraph", "content": [{"type": "text", "text": "body"}]}]
    content += [{"type": "paywall"}] * paywalls
    return {
        "id": 77,
        "publication": HOST,
        "is_published": True,
        "post_date": "2026-10-18T00:00:00Z",
        "slug": "post",
        "audience": audience,
        "should_send_free_preview": audience == "only_paid",
        "draft_body": json.dumps({"type": "doc", "content": content}),
    }


@pytest.mark.parametrize(
    ("payments_state", "audience", "paywalls", "verified", "expected"),
    [
        ("disabled", "everyone", 0, True, "everyone"),
        ("enabled", "only_paid", 1, True, "only_paid"),
        ("disabled", "only_paid", 1, False, "everyone"),
        ("enabled", "everyone", 0, False, "only_paid"),
        (None, "everyone", 0, False, None),
    ],
)
def test_substack_readback_binds_audience_to_live_payments_state(
    monkeypatch: pytest.MonkeyPatch,
    payments_state: str | None,
    audience: str,
    paywalls: int,
    verified: bool,
    expected: str | None,
) -> None:
    monkeypatch.setenv("SUBSTACK_SESSION_COOKIE_EN", "session=test")
    monkeypatch.setattr(REMOTE, "get_json", lambda *_a, **_k: _draft(audience, paywalls))
    monkeypatch.setattr(
        REMOTE,
        "get_text_with_final_url",
        lambda url: (_page(payments_state), url),
    )
    monkeypatch.setattr(REMOTE, "prove_remote_assets", lambda *_a: [])
    monkeypatch.setattr(REMOTE, "content_matches", lambda *_a: True)
    monkeypatch.setattr(REMOTE, "_publisher_content_path", lambda *_a: Path("x"))
    observed: list[dict] = []
    monkeypatch.setattr(
        REMOTE, "finalize_live", lambda _s, _p, _t, value: observed.append(value) or value
    )

    REMOTE.substack("77", "substack/en", {"destination_identities": {"substack/en": HOST}})

    assert observed[0]["monetization_verified"] is verified
    assert observed[0]["paywall_verified"] is verified
    assert observed[0]["audience"] == audience
    assert observed[0]["expected_audience"] == expected


@pytest.mark.parametrize(
    ("audience", "expected", "reason"),
    [
        ("everyone", "everyone", "public-asset-readback-failed"),
        ("only_paid", "only_paid", "public-asset-readback-failed"),
        ("only_paid", "everyone", "substack-monetization-readback-failed"),
        ("everyone", "only_paid", "substack-monetization-readback-failed"),
        ("everyone", None, "substack-monetization-readback-failed"),
    ],
)
def test_receipt_requires_audience_to_match_payments_state(
    audience: str, expected: str | None, reason: str
) -> None:
    result = REMOTE.finalize_live(
        {},
        "substack/en",
        "77",
        {
            "status": "live",
            "verified": True,
            "content_verified": True,
            "monetization_verified": True,
            "paywall_verified": True,
            "audience": audience,
            "expected_audience": expected,
            "asset_verified": False,
        },
    )

    assert result == {"status": "unknown", "reason": reason}
