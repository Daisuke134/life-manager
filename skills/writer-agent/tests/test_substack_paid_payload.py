from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "substack-publish" / "substack_paid_payload.py"
SPEC = importlib.util.spec_from_file_location("substack_paid_payload_display", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_substack_image_display_width_keeps_portrait_headline_under_preview_gate() -> None:
    node = MODULE._image_node("headline", "https://substack-post-media.s3.amazonaws.com/image.png")

    attrs = node["content"][0]["attrs"]
    assert attrs["resizeWidth"] == 600
    assert 1536 * attrs["resizeWidth"] / 1024 <= 950


import json

import pytest


ARTICLE = "\n\n".join(
    [f"Paragraph {index} " + "x" * 300 for index in range(6)]
    + ["Read the full guide: [Get the kit](https://aniccaai.com/kit?ct=article-kit)"]
)


def _preloads(subdomain: str, payments_state: str) -> str:
    data = {"pub": {"subdomain": subdomain, "payments_state": payments_state}}
    return (
        '<html><script type="application/json" id="preloads-json">'
        + json.dumps(data)
        + "</script></html>"
    )


def _paywalls(payload: dict) -> int:
    return payload["draft_body"].count('"type":"paywall"')


@pytest.mark.parametrize(
    ("state", "audience"),
    [("enabled", "only_paid"), ("disabled", "everyone"), ("pending", "everyone")],
)
def test_audience_follows_publication_payments_state(state: str, audience: str) -> None:
    assert MODULE.audience_for_payments_state(state) == audience


@pytest.mark.parametrize("state", ["", None, 1])
def test_unreadable_payments_state_refuses_to_guess(state: object) -> None:
    with pytest.raises(ValueError, match="payments_state"):
        MODULE.audience_for_payments_state(state)


def test_payments_state_is_bound_to_the_publication_subdomain() -> None:
    page = _preloads("aniccaai2026", "disabled")

    assert MODULE.payments_state_from_html(page, "aniccaai2026.substack.com") == "disabled"
    with pytest.raises(ValueError, match="publication"):
        MODULE.payments_state_from_html(page, "aniccabuddha.substack.com")
    with pytest.raises(ValueError, match="preloads"):
        MODULE.payments_state_from_html("<html></html>", "aniccaai2026.substack.com")


def test_paid_payload_keeps_one_paywall_after_free_preview() -> None:
    payload = MODULE.build_paid_draft_payload(
        title="T", subtitle="", markdown=ARTICLE, byline_id=7, audience="only_paid"
    )

    assert payload["audience"] == "only_paid"
    assert payload["write_comment_permissions"] == "only_paid"
    assert payload["should_send_free_preview"] is True
    assert _paywalls(payload) == 1


def test_free_payload_has_no_paywall_and_keeps_the_closing_cta() -> None:
    payload = MODULE.build_paid_draft_payload(
        title="T", subtitle="", markdown=ARTICLE, byline_id=7, audience="everyone"
    )

    assert payload["audience"] == "everyone"
    assert payload["write_comment_permissions"] == "everyone"
    assert payload["should_send_free_preview"] is False
    assert _paywalls(payload) == 0
    last = json.loads(payload["draft_body"])["content"][-1]
    hrefs = [
        mark["attrs"]["href"]
        for node in last["content"]
        for mark in node.get("marks", [])
        if mark["type"] == "link"
    ]
    assert hrefs == ["https://aniccaai.com/kit?ct=article-kit"]


def test_payload_requires_a_known_audience() -> None:
    with pytest.raises(TypeError):
        MODULE.build_paid_draft_payload(title="T", subtitle="", markdown=ARTICLE, byline_id=7)
    with pytest.raises(ValueError, match="audience"):
        MODULE.build_paid_draft_payload(
            title="T", subtitle="", markdown=ARTICLE, byline_id=7, audience="founding"
        )


@pytest.mark.parametrize("audience", ["only_paid", "everyone"])
def test_readback_verifies_the_built_audience(audience: str) -> None:
    payload = MODULE.build_paid_draft_payload(
        title="T", subtitle="", markdown=ARTICLE, byline_id=7, audience=audience
    )

    assert MODULE.verify_paid_draft_response({**payload, "id": 9}, audience) == 9


@pytest.mark.parametrize(
    ("built", "expected"), [("only_paid", "everyone"), ("everyone", "only_paid")]
)
def test_readback_refuses_audience_that_disagrees_with_payments_state(
    built: str, expected: str
) -> None:
    payload = MODULE.build_paid_draft_payload(
        title="T", subtitle="", markdown=ARTICLE, byline_id=7, audience=built
    )

    with pytest.raises(ValueError, match="audience"):
        MODULE.verify_paid_draft_response({**payload, "id": 9}, expected)


def test_free_readback_refuses_a_leftover_paywall() -> None:
    payload = MODULE.build_paid_draft_payload(
        title="T", subtitle="", markdown=ARTICLE, byline_id=7, audience="only_paid"
    )

    with pytest.raises(ValueError, match="paywall"):
        MODULE.verify_paid_draft_response({**payload, "id": 9, "audience": "everyone"}, "everyone")


def test_cli_read_audience_prints_live_audience(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        MODULE, "read_publication_audience", lambda host: seen.append(host) or "everyone"
    )
    monkeypatch.setattr(
        MODULE.sys, "argv", ["x", "--read-audience", "--publication", "aniccaai2026.substack.com"]
    )

    assert MODULE.main() == 0
    assert capsys.readouterr().out.strip() == "everyone"
    assert seen == ["aniccaai2026.substack.com"]


def test_cli_read_audience_blocks_when_payments_state_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unreadable(_host: str) -> str:
        raise OSError("network down")

    monkeypatch.setattr(MODULE, "read_publication_audience", unreadable)
    monkeypatch.setattr(
        MODULE.sys, "argv", ["x", "--read-audience", "--publication", "aniccaai2026.substack.com"]
    )

    with pytest.raises(SystemExit) as raised:
        MODULE.main()
    assert raised.value.code != 0


def test_cli_build_requires_explicit_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MODULE.sys, "argv", ["x", "--title", "T", "--byline-id", "7"])

    with pytest.raises(SystemExit) as raised:
        MODULE.main()
    assert raised.value.code != 0
