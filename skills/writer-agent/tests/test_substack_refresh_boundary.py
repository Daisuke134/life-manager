from __future__ import annotations

import importlib.util
from types import SimpleNamespace
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "substack-publish" / "substack_refresh_intent.py"
SPEC = importlib.util.spec_from_file_location("substack_refresh_boundary", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_pair_publication_prefers_language_specific_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUBSTACK_PUBLICATION", "aniccabuddha.substack.com")
    monkeypatch.setenv("SUBSTACK_PUBLICATION_EN", "aniccaai2026.substack.com")

    assert MODULE._publication_for_pair("substack/en") == "aniccaai2026.substack.com"


def test_english_pair_does_not_fall_back_to_generic_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUBSTACK_PUBLICATION", "aniccabuddha.substack.com")
    monkeypatch.delenv("SUBSTACK_PUBLICATION_EN", raising=False)

    assert MODULE._publication_for_pair("substack/en") == ""


def test_refresh_accepts_authenticated_post_bylines_shape() -> None:
    assert MODULE._owned_byline_ids({"postBylines": [{"user_id": 336441894}]}) == {336441894}


def test_refresh_rebuilds_mermaid_media_before_same_id_put() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "embed-mermaid-substack.py" in source
    assert "embedded_markdown" in source


def test_refresh_creates_rebuild_output_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "article.md"
    headline = tmp_path / "headline.png"
    body = tmp_path / "body.png"
    source.write_text("# title\n", encoding="utf-8")
    headline.write_bytes(b"headline")
    body.write_bytes(b"body")
    output = tmp_path / "run" / "gates" / "substack-refresh" / "article-ja-embedded.md"
    observed: list[Path] = []

    def fake_run(command, **_kwargs):  # type: ignore[no-untyped-def]
        out = Path(command[command.index("--out") + 1])
        observed.append(out.parent)
        assert out.parent.is_dir()
        out.write_text("# embedded\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)
    state = {
        "run_dir": str(tmp_path / "run"),
        "drafts": {"ja": {"path": str(source)}},
        "media": {
            "headline_image": {"path": str(headline)},
            "body_assets": [{"path": str(body)}],
        },
    }

    result = MODULE._build_embedded_markdown(state, "ja")

    assert result == "# embedded\n"
    assert observed == [output.parent]


@pytest.mark.parametrize(
    "draft",
    [
        {"postBylines": [{"user_id": 336441894}, {}]},
        {
            "draft_bylines": [{"id": 336441894}],
            "postBylines": [{"user_id": 999}],
        },
    ],
)
def test_refresh_rejects_unknown_or_conflicting_byline_shapes(draft: dict) -> None:
    with pytest.raises(MODULE.m.SubstackRepairRefused, match="byline"):
        MODULE._owned_byline_ids(draft)


@pytest.mark.parametrize(
    "draft",
    [
        {"is_published": True, "post_date": "2026-08-21T00:00:00Z"},
        {"is_published": False, "post_date": "2026-08-21T00:00:00Z"},
        {"post_date": None},
    ],
)
def test_refresh_refuses_live_or_ambiguous_target_before_media_put(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, draft: dict
) -> None:
    image = tmp_path / "headline.png"
    image.write_bytes(b"immutable")
    state = {
        "pairs": {"substack/ja": {"status": "intent", "target": "123"}},
        "media": {
            "headline_image": {"path": str(image), "sha256": MODULE.m.sha256(image)},
            "body_assets": [],
        },
    }
    calls: list[tuple[str, str]] = []
    old = {
        "id": 123,
        "publication": "aniccabuddha.substack.com",
        "draft_title": "title",
        "draft_bylines": [{"id": 42}],
        **draft,
    }
    monkeypatch.setattr(MODULE.m, "_state", lambda: state)
    monkeypatch.setattr(MODULE.m, "_publication", lambda: "aniccabuddha.substack.com")
    monkeypatch.setattr(MODULE.m, "_identity", lambda: 42)
    monkeypatch.setattr(MODULE.m, "_cookie", lambda: "cookie")

    def request(method: str, path: str, **kwargs):  # type: ignore[no-untyped-def]
        calls.append((method, path))
        if method == "GET":
            return old
        raise AssertionError("refresh attempted a PUT after unsafe readback")

    monkeypatch.setattr(MODULE.m, "_request", request)
    monkeypatch.setattr(
        MODULE.m,
        "upload_image",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("media upload occurred before unsafe readback was rejected")
        ),
    )
    with pytest.raises(MODULE.m.SubstackRepairRefused, match="live or ambiguous"):
        MODULE.refresh("substack/ja")
    assert calls == [("GET", "/api/v1/drafts/123")]
