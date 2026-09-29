from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "capafy_devto_post.py"

DRAFT_WITH_CTA = """---
title: Slide Maker turns any outline into a deck in minutes
tags: productivity, slides, ai
---
Writing slides from a raw outline eats hours before a pitch.

Try it: https://capafy.ai/agent/8828622062?ct=capafy-distribute-slide-maker
"""


def load_module():
    spec = importlib.util.spec_from_file_location("capafy_devto_post", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_article_payload_is_published_true_with_title_and_tags() -> None:
    module = load_module()
    devto_module = module._load_devto_module()  # noqa: SLF001
    payload = module.build_article_payload(DRAFT_WITH_CTA, devto_module)
    article = payload["article"]
    assert article["published"] is True
    assert article["title"] == "Slide Maker turns any outline into a deck in minutes"
    assert article["tags"] == ["productivity", "slides", "ai"]
    assert "ct=capafy-distribute-slide-maker" in article["body_markdown"]


def test_build_article_payload_rejects_missing_title() -> None:
    module = load_module()
    devto_module = module._load_devto_module()  # noqa: SLF001
    import pytest

    with pytest.raises(ValueError):
        module.build_article_payload("---\ntags: a, b\n---\nbody", devto_module)


def test_find_existing_by_title_matches_case_and_whitespace_insensitively() -> None:
    module = load_module()
    rows = [{"id": 1, "title": "  Slide   Maker Turns Any Outline Into A Deck In Minutes "}]
    found = module.find_existing_by_title(rows, "Slide Maker turns any outline into a deck in minutes")
    assert found is not None
    assert found["id"] == 1


def test_find_existing_by_title_no_match_returns_none() -> None:
    module = load_module()
    assert module.find_existing_by_title([{"title": "Something else"}], "New title") is None


def test_cli_dry_run_builds_payload_with_no_network(tmp_path: Path) -> None:
    draft = tmp_path / "article-en.md"
    draft.write_text(DRAFT_WITH_CTA)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--draft-file", str(draft), "--dry-run"],
        capture_output=True, text=True, check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["action"] == "would-create"
    assert payload["payload"]["article"]["published"] is True


def test_cli_duplicate_guard_skips_without_network_when_title_already_exists(tmp_path: Path) -> None:
    draft = tmp_path / "article-en.md"
    draft.write_text(DRAFT_WITH_CTA)
    existing = tmp_path / "existing.json"
    existing.write_text(json.dumps([
        {"id": 42, "title": "Slide Maker turns any outline into a deck in minutes",
         "url": "https://dev.to/anicca/slide-maker-42"},
    ]))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--draft-file", str(draft),
         "--existing-articles-json", str(existing), "--dry-run"],
        capture_output=True, text=True, check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["action"] == "duplicate-skip"
    assert payload["existing"]["id"] == 42
