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


def test_publish_pushes_when_remote_moved_ahead(tmp_path: Path) -> None:
    """2026-10-02: another writer pushed to the landing repo's main; every later
    run died with `! [rejected] HEAD -> main (non-fast-forward)` and no article
    went live for three days. The publish must sync with the remote first."""
    module = load()
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    landing = tmp_path / "landing"
    _init_repo(landing)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=landing, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=landing, check=True)

    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(remote), str(other)], check=True)
    subprocess.run(["git", "config", "user.email", "o@example.com"], cwd=other, check=True)
    subprocess.run(["git", "config", "user.name", "Other"], cwd=other, check=True)
    (other / "OTHER.md").write_text("moved ahead\n", encoding="utf-8")
    subprocess.run(["git", "add", "OTHER.md"], cwd=other, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "other writer"], cwd=other, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=other, check=True)

    draft = tmp_path / "article-en.md"
    draft.write_text(_draft(), encoding="utf-8")
    url = "https://aniccaai.com/blog/capafy-slide-maker-2026-10-04"
    result = module.publish(
        draft_path=draft, slug="capafy-slide-maker-2026-10-04", cta_url=CTA_URL,
        landing_root=landing, remote="origin", branch="main", base_url="https://aniccaai.com",
        date="2026-10-04", retries=1,
        fetch=lambda u: f"<h1>Slide Maker turns any outline into a deck</h1> ... {CTA_URL}",
    )
    assert result["status"] == "published"
    log = subprocess.run(["git", "log", "--oneline", "main"], cwd=remote, check=True,
                         text=True, capture_output=True).stdout
    assert "other writer" in log
    assert "publish free article capafy-slide-maker-2026-10-04" in log


@pytest.fixture
def concurrent_publication(tmp_path):
    module = load()
    git = module._load_self_owned_module()._git
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    landing = tmp_path / "landing"
    _init_repo(landing)
    git(landing, "remote", "add", "origin", str(remote))
    git(landing, "push", "origin", "main")
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(remote), str(other)], check=True)
    git(other, "config", "user.email", "other@example.com")
    git(other, "config", "user.name", "Other Writer")
    draft = tmp_path / "article-en.md"
    draft.write_text(_draft(), encoding="utf-8")
    relative = "apps/landing/data/research/concurrent-article.json"

    def advance(path="OTHER.md", text="other writer\n"):
        target = other / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        git(other, "add", "--", path)
        git(other, "commit", "-m", f"other writer: {path}")
        git(other, "push", "origin", "main")

    def publish():
        return module.publish(
            draft_path=draft, slug="concurrent-article", cta_url=CTA_URL,
            landing_root=landing, remote="origin", branch="main",
            base_url="https://aniccaai.com", date="2026-10-23", retries=1,
            fetch=lambda url: f"<h1>Slide Maker turns any outline into a deck</h1> {CTA_URL}",
        )

    return module, git, remote, landing, relative, advance, publish


@pytest.mark.parametrize("resume", [False, True])
def test_publish_recovers_remote_advance_after_sync(concurrent_publication, monkeypatch, resume):
    module, git, remote, landing, relative, advance, publish = concurrent_publication
    if resume:
        article = module.build_free_article(
            _draft(), slug="concurrent-article", date="2026-10-23", cta_url=CTA_URL,
        )
        module.write_free_article(landing, article)
        git(landing, "add", "--", relative)
        git(landing, "commit", "-m", "interrupted article commit")
    pushes = []

    def raced_git(root, *args):
        if root == landing and args[0] == "push":
            pushes.append(args)
            if len(pushes) == 1:
                advance()
        return git(root, *args)

    monkeypatch.setattr(module._load_self_owned_module(), "_git", raced_git)
    result = publish()
    assert result["status"] == "published"
    assert len(pushes) == 2
    assert result["commit"] == git(remote, "rev-parse", "main") == git(landing, "rev-parse", "HEAD")
    assert json.loads(git(remote, "show", f"main:{relative}"))["markdown"] == _draft().strip()
    assert git(remote, "show", "main:OTHER.md") == "other writer"
    # The rebase preserves both writers and never duplicates the article commit.
    assert len(git(remote, "log", "--format=%H", "main", "--", relative).splitlines()) == 1


@pytest.mark.parametrize("error", ["remote: Permission denied", "fatal: Could not resolve host"])
def test_publish_does_not_retry_non_rejection_errors(concurrent_publication, monkeypatch, error):
    module, git, remote, landing, relative, advance, publish = concurrent_publication
    soa = module._load_self_owned_module()
    after_push = []

    def refused_git(root, *args):
        if root == landing and (after_push or args[0] == "push"):
            after_push.append(args)
        if root == landing and args[0] == "push":
            raise soa.SelfOwnedInvariant(error)
        return git(root, *args)

    monkeypatch.setattr(soa, "_git", refused_git)
    with pytest.raises(soa.SelfOwnedInvariant, match=error):
        publish()
    assert len(after_push) == 1
    assert (landing / relative).exists()
    assert git(landing, "status", "--porcelain") == ""


def test_publish_stops_after_second_remote_rejection(concurrent_publication, monkeypatch):
    module, git, remote, landing, relative, advance, publish = concurrent_publication
    pushes = []

    def always_raced_git(root, *args):
        if root == landing and args[0] == "push":
            pushes.append(args)
            advance(path=f"OTHER-{len(pushes)}.md")
        return git(root, *args)

    monkeypatch.setattr(module._load_self_owned_module(), "_git", always_raced_git)
    with pytest.raises(module._load_self_owned_module().SelfOwnedInvariant, match=r"\[rejected\]"):
        publish()
    assert len(pushes) == 2
    assert git(remote, "show", "main:OTHER-1.md") == "other writer"
    assert git(remote, "show", "main:OTHER-2.md") == "other writer"
    assert (landing / relative).exists()


def test_publish_preserves_conflicting_rebase_for_owner_recovery(concurrent_publication, monkeypatch):
    module, git, remote, landing, relative, advance, publish = concurrent_publication
    commands = []

    def conflict_git(root, *args):
        if root == landing:
            commands.append(args)
            if args[0] == "push":
                advance(path=relative, text='{"other": "immutable article"}\n')
        return git(root, *args)

    monkeypatch.setattr(module._load_self_owned_module(), "_git", conflict_git)
    with pytest.raises(module._load_self_owned_module().SelfOwnedInvariant):
        publish()
    assert sum(args[0] == "push" for args in commands) == 1
    assert json.loads(git(remote, "show", f"main:{relative}")) == {"other": "immutable article"}
    assert git(landing, "show", f"ORIG_HEAD:{relative}")
    assert git(landing, "diff", "--name-only", "--diff-filter=U") == relative
    assert (landing / ".git/rebase-merge").is_dir()
    assert not any(args[0] in {"reset", "clean"} or "--abort" in args or "--force" in args for args in commands)


def test_push_recovery_does_not_abort_preexisting_rebase(concurrent_publication, monkeypatch):
    module, git, remote, landing, relative, advance, publish = concurrent_publication
    soa = module._load_self_owned_module()
    (landing / "OTHER.md").write_text("local conflicting text\n", encoding="utf-8")
    git(landing, "add", "OTHER.md")
    git(landing, "commit", "-m", "local writer")
    advance(text="remote conflicting text\n")
    with pytest.raises(soa.SelfOwnedInvariant):
        git(landing, "pull", "--rebase", "origin", "main")
    rebase = landing / ".git/rebase-merge"
    original_head = git(landing, "rev-parse", "HEAD")
    original_state = {p.name: p.read_bytes() for p in rebase.iterdir() if p.is_file()}
    advance(path="AFTER-REBASE.md")
    with pytest.raises(soa.SelfOwnedInvariant):
        module._push_with_rebase_retry(landing, remote="origin", branch="main")
    assert git(landing, "rev-parse", "HEAD") == original_head
    assert {p.name: p.read_bytes() for p in rebase.iterdir() if p.is_file()} == original_state
    assert git(landing, "diff", "--name-only", "--diff-filter=U") == "OTHER.md"


# D7 (SSOT 2026-10-15): one real output image per article when the run directory has one.
IMG = "https://uploads.postiz.com/abc123.png"


def test_with_image_inserts_after_the_first_paragraph_once():
    m = load()
    md = "# Title\n\nFirst paragraph.\n\n## Section\n\nMore."
    out = m.with_image(md, IMG, "Three Hook Lab hooks for one video")
    assert out == ("# Title\n\nFirst paragraph.\n\n![Three Hook Lab hooks for one video](" + IMG + ")\n\n"
                   "## Section\n\nMore.")
    assert m.with_image(out, IMG, "x") == out


def test_with_image_ignores_non_https_urls():
    m = load()
    md = "# Title\n\nFirst."
    assert m.with_image(md, "javascript:alert(1)", "x") == md


def test_load_draft_applies_image_file_next_to_the_draft(tmp_path):
    m = load()
    draft = tmp_path / "article-en.md"
    draft.write_text("# Title\n\nFirst.\n\nSecond.", encoding="utf-8")
    assert m.load_draft(draft) == "# Title\n\nFirst.\n\nSecond."
    (tmp_path / "article-image.url").write_text(IMG + "\n", encoding="utf-8")
    assert f"]({IMG})" in m.load_draft(draft)


def test_build_free_article_requires_every_query_word_in_the_title() -> None:
    module = load()
    ok = module.build_free_article(_draft(title="Free TikTok Hook Generator: 50 hooks"), slug="tiktok-hook-generator-free",
                                   date="2026-10-17", cta_url=CTA_URL, title_must_contain="tiktok hook generator free")
    assert ok["title"] == "Free TikTok Hook Generator: 50 hooks"
    with pytest.raises(ValueError, match="search query"):
        module.build_free_article(_draft(title="Your video needs a better first three seconds"),
                                  slug="tiktok-hook-generator-free", date="2026-10-17", cta_url=CTA_URL,
                                  title_must_contain="tiktok hook generator free")


@pytest.mark.parametrize("title", [
    "Ganchos para vídeos curtos: 12 exemplos",
    "Ganchos para vi\u0301deos curtos: 12 exemplos",
])
def test_ascii_query_accepts_accented_title_without_changing_public_text(title: str) -> None:
    article = load().build_free_article(
        _draft(title=title), slug="ganchos-para-videos-curtos", date="2026-10-21",
        cta_url=CTA_URL, title_must_contain="ganchos para videos curtos",
    )
    assert article["title"] == title
    assert f"# {title}" in article["markdown"]


@pytest.mark.parametrize(("title", "query"), [
    ("Ganchos para vídeos longos", "ganchos para videos curtos"),
    ("パターンの紹介", "ハターン"),
    ("ķ", "K"),
])
def test_keyword_check_still_rejects_missing_words_and_distinct_unicode(title: str, query: str) -> None:
    with pytest.raises(ValueError, match="search query"):
        load().build_free_article(
            _draft(title=title), slug="keyword-check", date="2026-10-21",
            cta_url=CTA_URL, title_must_contain=query,
        )


def test_publish_pings_indexnow_after_the_live_readback(tmp_path: Path) -> None:
    module = load()
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    landing = tmp_path / "landing"
    _init_repo(landing)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=landing, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=landing, check=True)
    draft = tmp_path / "article-en.md"
    draft.write_text(_draft(), encoding="utf-8")
    pings = []
    result = module.publish(
        draft_path=draft, slug="slide-deck-maker", cta_url=CTA_URL, landing_root=landing, remote="origin",
        branch="main", base_url="https://aniccaai.com", date="2026-10-17", retries=1,
        fetch=lambda url: f"<h1>Slide Maker turns any outline into a deck</h1> {CTA_URL}",
        indexnow_key="k123", indexnow=lambda url, key: pings.append((url, key)) or 200)
    assert pings == [("https://aniccaai.com/blog/slide-deck-maker", "k123")]
    assert result["indexnow"] == 200
