"""capafy_free_article.py publishes ONE fully free aniccaai.com blog page for
the Capafy distribute loop (Dais decision 2026-09-29: dev.to/Zenn are dropped
for this loop; aniccaai.com is the new free destination). These tests prove
the pieces that run before any git side effect (the CTA requirement, the
plain-JSON shape with no preview/paid split), the immutable write/commit
transaction against a real throwaway git repo, and the public-readback
verification -- with no network call anywhere in this file.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
CTA_URL = "https://capafy.ai/agent/8828622062?ct=capafy-distribute-slide-maker"


def load():
    path = ROOT / "skills/earn/capafy-marketing/scripts/capafy_free_article.py"
    spec = importlib.util.spec_from_file_location("capafy_free_article_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _draft(title: str = "Slide Maker turns any outline into a deck", cta: str = CTA_URL) -> str:
    return (
        f"# {title}\n\n"
        "Writing slides from a raw outline eats hours before a pitch.\n\n"
        f"Try it: {cta}\n"
    )


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "capafy@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Capafy Test"], cwd=path, check=True)
    (path / "README.md").write_text("landing repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


def test_build_free_article_requires_capafy_cta_link() -> None:
    module = load()
    with pytest.raises(ValueError, match="CTA"):
        module.build_free_article(
            "# Title\n\nNo link here.\n", slug="capafy-slide-maker-2026-09-29",
            date="2026-09-29", cta_url=CTA_URL,
        )


def test_build_free_article_has_no_preview_paid_split() -> None:
    module = load()
    article = module.build_free_article(
        _draft(), slug="capafy-slide-maker-2026-09-29", date="2026-09-29", cta_url=CTA_URL,
    )
    assert article["slug"] == "capafy-slide-maker-2026-09-29"
    assert article["title"] == "Slide Maker turns any outline into a deck"
    assert CTA_URL in article["markdown"]
    assert "access_model" not in article
    assert "paid_markdown" not in article
    assert "preview_markdown" not in article


def test_build_free_article_uses_frontmatter_title_when_h1_missing() -> None:
    module = load()
    draft = f'---\ntitle: "Fallback title"\n---\n\nbody text.\n\nTry it: {CTA_URL}\n'
    article = module.build_free_article(
        draft, slug="capafy-slide-maker-2026-09-29", date="2026-09-29", cta_url=CTA_URL,
    )
    assert article["title"] == "Fallback title"


def test_write_free_article_writes_plain_public_json(tmp_path: Path) -> None:
    module = load()
    landing = tmp_path / "landing"
    _init_repo(landing)
    article = module.build_free_article(
        _draft(), slug="capafy-slide-maker-2026-09-29", date="2026-09-29", cta_url=CTA_URL,
    )
    result = module.write_free_article(landing, article)
    assert result["status"] == "staged"
    written = landing / "apps/landing/data/research/capafy-slide-maker-2026-09-29.json"
    assert json.loads(written.read_text(encoding="utf-8")) == article

    # Re-writing the identical article is idempotent.
    again = module.write_free_article(landing, article)
    assert again["status"] == "already-present"


def test_write_free_article_refuses_a_slug_conflict_with_different_bytes(tmp_path: Path) -> None:
    module = load()
    landing = tmp_path / "landing"
    _init_repo(landing)
    article = module.build_free_article(
        _draft(), slug="capafy-slide-maker-2026-09-29", date="2026-09-29", cta_url=CTA_URL,
    )
    module.write_free_article(landing, article)
    other = module.build_free_article(
        _draft(title="A different article"), slug="capafy-slide-maker-2026-09-29",
        date="2026-09-29", cta_url=CTA_URL,
    )
    with pytest.raises(ValueError, match="conflict"):
        module.write_free_article(landing, other)


def test_write_free_article_refuses_a_dirty_worktree(tmp_path: Path) -> None:
    module = load()
    landing = tmp_path / "landing"
    _init_repo(landing)
    (landing / "uncommitted.txt").write_text("oops\n", encoding="utf-8")
    article = module.build_free_article(
        _draft(), slug="capafy-slide-maker-2026-09-29", date="2026-09-29", cta_url=CTA_URL,
    )
    with pytest.raises(ValueError, match="dirty"):
        module.write_free_article(landing, article)


def test_verify_live_requires_title_and_cta() -> None:
    module = load()
    module.verify_live("<h1>Slide Maker</h1> ... " + CTA_URL, title="Slide Maker", cta_url=CTA_URL)
    with pytest.raises(ValueError, match="title"):
        module.verify_live("no title here " + CTA_URL, title="Slide Maker", cta_url=CTA_URL)
    with pytest.raises(ValueError, match="CTA"):
        module.verify_live("<h1>Slide Maker</h1>", title="Slide Maker", cta_url=CTA_URL)


def test_publish_end_to_end_commits_pushes_and_verifies_readback(tmp_path: Path) -> None:
    module = load()
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    landing = tmp_path / "landing"
    _init_repo(landing)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=landing, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=landing, check=True)

    draft = tmp_path / "article-en.md"
    draft.write_text(_draft(), encoding="utf-8")

    published_markup: dict[str, str] = {
        "https://aniccaai.com/blog/capafy-slide-maker-2026-09-29": (
            f"<h1>Slide Maker turns any outline into a deck</h1> ... {CTA_URL}"
        ),
    }

    def fake_fetch(url: str) -> str:
        return published_markup[url]

    result = module.publish(
        draft_path=draft,
        slug="capafy-slide-maker-2026-09-29",
        cta_url=CTA_URL,
        landing_root=landing,
        remote="origin",
        branch="main",
        base_url="https://aniccaai.com",
        date="2026-09-29",
        retries=1,
        fetch=fake_fetch,
    )
    assert result["status"] == "published"
    assert result["url"] == "https://aniccaai.com/blog/capafy-slide-maker-2026-09-29"
    assert result["title"] == "Slide Maker turns any outline into a deck"
    pushed = subprocess.run(
        ["git", "log", "--oneline", "main"], cwd=remote, check=True, text=True, capture_output=True,
    ).stdout
    assert "publish free article capafy-slide-maker-2026-09-29" in pushed

    # A second call for the same slug is idempotent: no duplicate commit, still verifies live.
    second = module.publish(
        draft_path=draft,
        slug="capafy-slide-maker-2026-09-29",
        cta_url=CTA_URL,
        landing_root=landing,
        remote="origin",
        branch="main",
        base_url="https://aniccaai.com",
        date="2026-09-29",
        retries=1,
        fetch=fake_fetch,
    )
    assert second["status"] == "published"
    assert second["commit"] == result["commit"]


def test_publish_retries_before_the_deploy_goes_live(tmp_path: Path) -> None:
    module = load()
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    landing = tmp_path / "landing"
    _init_repo(landing)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=landing, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=landing, check=True)

    draft = tmp_path / "article-en.md"
    draft.write_text(_draft(), encoding="utf-8")

    calls = {"n": 0}

    def flaky_fetch(url: str) -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("not deployed yet")
        return f"<h1>Slide Maker turns any outline into a deck</h1> ... {CTA_URL}"

    result = module.publish(
        draft_path=draft,
        slug="capafy-slide-maker-2026-09-29",
        cta_url=CTA_URL,
        landing_root=landing,
        remote="origin",
        branch="main",
        base_url="https://aniccaai.com",
        date="2026-09-29",
        retries=5,
        retry_interval_seconds=0,
        fetch=flaky_fetch,
    )
    assert result["status"] == "published"
    assert calls["n"] == 3


def test_publish_raises_when_deploy_never_confirms(tmp_path: Path) -> None:
    module = load()
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    landing = tmp_path / "landing"
    _init_repo(landing)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=landing, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=landing, check=True)

    draft = tmp_path / "article-en.md"
    draft.write_text(_draft(), encoding="utf-8")

    def never_fetch(url: str) -> str:
        raise TimeoutError("never deployed")

    with pytest.raises(SystemExit, match="never confirmed"):
        module.publish(
            draft_path=draft,
            slug="capafy-slide-maker-2026-09-29",
            cta_url=CTA_URL,
            landing_root=landing,
            remote="origin",
            branch="main",
            base_url="https://aniccaai.com",
            date="2026-09-29",
            retries=2,
            retry_interval_seconds=0,
            fetch=never_fetch,
        )
