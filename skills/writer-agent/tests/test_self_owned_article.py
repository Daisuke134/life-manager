"""self_owned_article.py had zero test coverage before this file, even though
it is the module that commits and pushes directly to the aniccaai.com landing
repo's main branch. These tests prove the pieces that run before any git
side effect: the preview/paid split, the base-run safety gate, the immutable
git staging transaction, and the public-readback verification that guards
against leaking the paid body.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def soa():
    return load("self_owned_article_under_test", "skills/writer-agent/scripts/self_owned_article.py")


def _markdown(paragraphs_before_boundary: int = 20, title: str = "A useful title") -> str:
    body = "\n\n".join(f"Filler sentence number {i} with enough visible characters to count toward the preview minimum threshold." for i in range(paragraphs_before_boundary))
    return f"# {title}\n\n{body}\n\n## Paid section\n\nThe paid body content goes here, unlocked after purchase.\n"


def test_build_contract_splits_preview_and_paid():
    module = soa()
    contract = module.build_contract(run_id="20260928-132912", lang="ja", markdown=_markdown())
    assert contract["title"] == "A useful title"
    assert contract["slug"] == "a-useful-title"
    assert "## Paid section" not in contract["preview_markdown"]
    assert "paid body content" in contract["paid_markdown"]
    assert contract["preview_sha256"] == module.sha256_text(contract["preview_markdown"])
    assert contract["paid_sha256"] == module.sha256_text(contract["paid_markdown"])


def test_build_contract_requires_h1_title():
    module = soa()
    body = "\n\n".join(f"Filler sentence number {i} with enough visible characters to count toward the preview minimum threshold." for i in range(20))
    markdown = f"no title here\n\n{body}\n\n## Paid section\n\npaid body\n"
    with pytest.raises(module.SelfOwnedInvariant, match="H1"):
        module.build_contract(run_id="20260928-132912", lang="ja", markdown=markdown)


def test_build_contract_requires_a_paid_boundary():
    module = soa()
    with pytest.raises(module.SelfOwnedInvariant, match="boundary"):
        module.build_contract(run_id="20260928-132912", lang="ja", markdown="# Title only\n\nshort body, no second heading")


_SELF_OWNED_CTA = (
    "https://aniccaai.com/lm?product_id=anicca&run_id=20260928-132912"
    "&artifact_id=article-ja&variant_id=role-map&click_id=20260928-132912-article-ja"
)
_CAPAFY_CTA = (
    "https://capafy.ai/agent/9563867391?product_id=capafy-skills"
    "&run_id=20260928-132912&artifact_id=article-ja&variant_id=hook-variant-1"
    "&click_id=20260928-132912-article-ja&ct=article-marketing-strategist"
)


def test_build_contract_never_buries_the_self_owned_cta_in_the_paid_section():
    """Regression: run 20260928-132912's real article-ja.md had its CTA link
    in a paragraph right before the last H2 ("## 出典" / Sources). The
    naive first-H2-past-threshold boundary landed BEFORE that paragraph, so
    the CTA ended up in paid_markdown -- which the site never renders for a
    free reader -- and the live page had zero conversion links.
    """
    module = soa()
    body = "\n\n".join(
        f"Filler sentence number {i} with enough visible characters to count toward the preview minimum threshold."
        for i in range(20)
    )
    markdown = (
        f"# A useful title\n\n{body}\n\n"
        f"## Where to start\n\nSee [the workspace]({_SELF_OWNED_CTA}) to continue.\n\n"
        "## Sources\n\n- one citation\n"
    )
    contract = module.build_contract(run_id="20260928-132912", lang="ja", markdown=markdown)
    assert _SELF_OWNED_CTA in contract["preview_markdown"]
    assert _SELF_OWNED_CTA not in contract["paid_markdown"]


def test_build_contract_never_buries_a_capafy_cta_in_the_paid_section():
    module = soa()
    body = "\n\n".join(
        f"Filler sentence number {i} with enough visible characters to count toward the preview minimum threshold."
        for i in range(20)
    )
    markdown = (
        f"# A useful title\n\n{body}\n\n"
        f"## Where to start\n\nSee [the agent]({_CAPAFY_CTA}) to continue.\n\n"
        "## Sources\n\n- one citation\n"
    )
    contract = module.build_contract(run_id="20260928-132912", lang="ja", markdown=markdown)
    assert _CAPAFY_CTA in contract["preview_markdown"]
    assert _CAPAFY_CTA not in contract["paid_markdown"]


def test_build_contract_refuses_to_split_a_cta_with_no_boundary_after_it():
    """If the CTA is the very last thing in the article (no heading after
    it), there is no safe boundary that both hides something and keeps the
    CTA visible. Fail closed rather than silently dropping the CTA.
    """
    module = soa()
    body = "\n\n".join(
        f"Filler sentence number {i} with enough visible characters to count toward the preview minimum threshold."
        for i in range(20)
    )
    markdown = f"# A useful title\n\n{body}\n\nSee [the workspace]({_SELF_OWNED_CTA}) to continue.\n"
    with pytest.raises(module.SelfOwnedInvariant, match="boundary"):
        module.build_contract(run_id="20260928-132912", lang="ja", markdown=markdown)


def test_contracts_from_publication_state_requires_safety_allow(tmp_path):
    module = soa()
    run_dir = tmp_path / "20260928-132912"
    run_dir.mkdir()
    (run_dir / "article-ja.md").write_text(_markdown(), encoding="utf-8")
    (run_dir / "article-en.md").write_text(_markdown(), encoding="utf-8")
    state_path = tmp_path / "publication-state.json"
    state = {
        "run_id": "20260928-132912",
        "run_dir": str(run_dir),
        "topic_id": "topic-1",
        "safety_status": "REVIEW",
        "self_owned_base_url": "https://aniccaai.com",
        "drafts": {
            "ja": {"path": str(run_dir / "article-ja.md"), "sha256": module.sha256_text((run_dir / "article-ja.md").read_text())},
            "en": {"path": str(run_dir / "article-en.md"), "sha256": module.sha256_text((run_dir / "article-en.md").read_text())},
        },
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    store = module.SelfOwnedPublicationStore(tmp_path / "adjunct.json", tmp_path / "ledger.jsonl")
    contracts = module.contracts_from_publication_state(state_path)
    with pytest.raises(module.SelfOwnedInvariant, match="not safe and complete"):
        store.prepare(state_path, contracts, base_url="https://aniccaai.com")


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "writer@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Writer Test"], cwd=path, check=True)
    (path / "README.md").write_text("landing repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


def test_managed_landing_checkout_is_bounded_without_removing_primary_data(tmp_path, monkeypatch):
    module = soa()
    state = tmp_path / "writer"
    landing = state / "checkouts/self-owned-landing"
    monkeypatch.setenv("WRITER_STATE_DIR", str(state))
    _init_repo(landing)
    files = {"apps/landing/private/writer-articles/old.json": "{}",
             "apps/other/build-input.txt": "regenerable code",
             ".cursor/copied-code.bin": "unused code",
             "nested/memory/kept.md": "retained memory",
             "skills/earn/state/earn-ledger.jsonl": "retained ledger",
             "other/credentials.json": "retained account settings",
             "docs/receipt.json": "retained receipt"}
    for name, value in files.items():
        p = landing / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value)
    subprocess.run(["git", "add", "."], cwd=landing, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=landing, check=True)
    head = module._git(landing, "rev-parse", "HEAD")
    assert module.bound_landing_checkout(landing) is True
    assert not (landing / "apps/other/build-input.txt").exists()
    assert not (landing / ".cursor/copied-code.bin").exists()
    for name in files:
        if name not in {"apps/other/build-input.txt", ".cursor/copied-code.bin"}:
            assert (landing / name).read_text() == files[name]
    assert module._git(landing, "rev-parse", "HEAD") == head
    assert module._git(landing, "status", "--porcelain") == ""
    assert module.bound_landing_checkout(landing) is True


@pytest.mark.parametrize("kind", ("dirty", "untracked", "ignored"))
def test_managed_landing_checkout_refuses_unknown_work_before_sparsifying(tmp_path, monkeypatch, kind):
    module = soa()
    state = tmp_path / "writer"
    landing = state / "checkouts/self-owned-landing"
    monkeypatch.setenv("WRITER_STATE_DIR", str(state))
    _init_repo(landing)
    if kind == "dirty":
        (landing / "README.md").write_text("active work")
    else:
        if kind == "ignored":
            (landing / ".git/info/exclude").write_text("active.bin\n")
        (landing / "active.bin").write_text("unknown work")
    assert module.bound_landing_checkout(landing) is False
    assert not (landing / ".git/info/sparse-checkout").exists()
    assert (landing / ("README.md" if kind == "dirty" else "active.bin")).read_text() in {"active work", "unknown work"}


def test_stage_and_commit_contracts_writes_immutable_files(tmp_path):
    module = soa()
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    landing = tmp_path / "landing"
    _init_repo(landing)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=landing, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=landing, check=True)

    contract = module.build_contract(run_id="20260928-132912", lang="ja", markdown=_markdown())
    staged = module.stage_contracts(landing, [contract])
    assert {item["status"] for item in staged} == {"staged"}

    article_path = landing / "apps/landing/private/writer-articles" / f"{contract['slug']}.json"
    assert json.loads(article_path.read_text(encoding="utf-8")) == contract
    registry = (landing / module.REGISTRY_RELATIVE).read_text(encoding="utf-8")
    assert f"'{contract['slug']}'" in registry

    result = module.commit_contract(
        landing,
        [str(article_path.relative_to(landing)), str(module.REGISTRY_RELATIVE)],
        message="feat(writer): publish self-owned 20260928-132912",
        remote="origin",
        branch="main",
    )
    assert result["pushed"] is True
    pushed_files = subprocess.run(
        ["git", "show", "--name-only", "--format=", f"{result['commit']}"],
        cwd=remote, check=True, text=True, capture_output=True,
    ).stdout.split()
    assert f"apps/landing/private/writer-articles/{contract['slug']}.json" in pushed_files

    # Re-staging the identical, now-committed contract over a clean worktree is a no-op.
    restaged = module.stage_contracts(landing, [contract])
    assert {item["status"] for item in restaged} == {"already-present"}


def test_commit_contract_survives_a_pre_existing_modified_registry(tmp_path):
    """Regression: live run 20260928-132912 hit `SelfOwnedInvariant("unrelated
    landing change appeared before commit")` even though nothing unrelated had
    changed. Root cause: _git() ran a whole-output .strip() on `git status
    --porcelain`, which silently ate the leading space off the FIRST line
    when it happened to be a tracked, modified-not-staged file (" M path"),
    truncating that one path by a character and breaking the exact dirty-set
    comparison. This only reproduces once the registry file is already
    tracked (a second real run, not the very first), so the earlier
    from-scratch staging test never exercised it.
    """
    module = soa()
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    landing = tmp_path / "landing"
    _init_repo(landing)

    # Seed one already-published article + a committed, tracked registry --
    # the exact shape of a landing repo after its first self-owned publish.
    existing = module.build_contract(run_id="20260101-000000", lang="ja", markdown=_markdown(title="Existing"))
    module.stage_contracts(landing, [existing])
    subprocess.run(["git", "add", "-A"], cwd=landing, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed existing article"], cwd=landing, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=landing, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=landing, check=True)

    ja = module.build_contract(run_id="20260928-132912", lang="ja", markdown=_markdown(title="JA today"))
    en = module.build_contract(run_id="20260928-132912", lang="en", markdown=_markdown(title="EN today"))
    module.stage_contracts(landing, [ja, en])

    # Sanity: the registry is now a MODIFIED tracked file (leading-space
    # porcelain line), which is exactly the shape that triggered the bug.
    status_lines = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=landing, check=True, text=True, capture_output=True,
    ).stdout.splitlines()
    assert any(line.startswith(" M ") for line in status_lines)

    result = module.commit_contract(
        landing,
        [
            f"apps/landing/private/writer-articles/{ja['slug']}.json",
            f"apps/landing/private/writer-articles/{en['slug']}.json",
            str(module.REGISTRY_RELATIVE),
        ],
        message="feat(writer): publish self-owned 20260928-132912",
        remote="origin",
        branch="main",
    )
    assert result["pushed"] is True


def test_stage_contracts_refuses_a_dirty_worktree(tmp_path):
    module = soa()
    landing = tmp_path / "landing"
    _init_repo(landing)
    (landing / "uncommitted.txt").write_text("oops\n", encoding="utf-8")
    contract = module.build_contract(run_id="20260928-132912", lang="ja", markdown=_markdown())
    with pytest.raises(module.SelfOwnedInvariant, match="dirty"):
        module.stage_contracts(landing, [contract])


def test_verify_public_readback_matches_contract():
    module = soa()
    contract = module.build_contract(run_id="20260928-132912", lang="ja", markdown=_markdown())
    live_url = f"https://aniccaai.com/blog/{contract['slug']}"
    markup = module.public_receipt_markup(contract)
    receipt = module.verify_public_readback(
        contract, live_url, markup, base_url="https://aniccaai.com", observed_at="2026-09-28T13:00:00Z",
    )
    assert receipt["live_url"] == live_url
    assert receipt["public_id"] == contract["slug"]


def test_verify_public_readback_honors_a_base_url_path_prefix():
    module = soa()
    contract = module.build_contract(run_id="20260928-132912", lang="ja", markdown=_markdown())
    live_url = f"https://aniccaai.com/lm/blog/{contract['slug']}"
    markup = module.public_receipt_markup(contract)
    receipt = module.verify_public_readback(
        contract, live_url, markup, base_url="https://aniccaai.com/lm", observed_at="2026-09-28T13:00:00Z",
    )
    assert receipt["live_url"] == live_url


def test_verify_public_readback_rejects_wrong_host():
    module = soa()
    contract = module.build_contract(run_id="20260928-132912", lang="ja", markdown=_markdown())
    markup = module.public_receipt_markup(contract)
    with pytest.raises(module.SelfOwnedInvariant, match="does not match"):
        module.verify_public_readback(
            contract, f"https://evil.example/blog/{contract['slug']}", markup,
            base_url="https://aniccaai.com", observed_at="2026-09-28T13:00:00Z",
        )


def test_verify_public_readback_rejects_leaked_paid_body():
    module = soa()
    contract = module.build_contract(run_id="20260928-132912", lang="ja", markdown=_markdown())
    live_url = f"https://aniccaai.com/blog/{contract['slug']}"
    leaking_markup = module.public_receipt_markup(contract) + contract["paid_markdown"]
    with pytest.raises(module.SelfOwnedInvariant, match="leaked"):
        module.verify_public_readback(
            contract, live_url, leaking_markup, base_url="https://aniccaai.com", observed_at="2026-09-28T13:00:00Z",
        )


def test_resume_publication_end_to_end_pushes_and_records_ledger(tmp_path):
    """The exact tick article-resume-pending.sh's self-owned adjunct runs: stage
    -> commit -> push -> fetch the live page -> verify -> record the ledger row.
    """
    module = soa()
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    landing = tmp_path / "landing"
    _init_repo(landing)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=landing, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=landing, check=True)

    run_dir = tmp_path / "runs" / "20260928-132912"
    run_dir.mkdir(parents=True)
    ja_md = _markdown(title="A useful title JA")
    en_md = _markdown(title="A useful title EN")
    (run_dir / "article-ja.md").write_text(ja_md, encoding="utf-8")
    (run_dir / "article-en.md").write_text(en_md, encoding="utf-8")
    publication_state_path = run_dir / "publication-state.json"
    publication_state_path.write_text(json.dumps({
        "run_id": "20260928-132912",
        "run_dir": str(run_dir),
        "topic_id": "topic-1",
        "safety_status": "ALLOW",
        "self_owned_base_url": "https://aniccaai.com",
        "drafts": {
            "ja": {"path": str(run_dir / "article-ja.md"), "sha256": module.sha256_text(ja_md)},
            "en": {"path": str(run_dir / "article-en.md"), "sha256": module.sha256_text(en_md)},
        },
    }), encoding="utf-8")
    ledger_path = tmp_path / "articles.jsonl"

    published_markup: dict[str, str] = {}

    def fake_fetch(url: str) -> str:
        return published_markup[url]

    result = module.resume_publication(
        publication_state_path=publication_state_path,
        ledger_path=ledger_path,
        landing_root=landing,
        remote="origin",
        branch="main",
        base_url="https://aniccaai.com",
        fetch_markup=fake_fetch,
    )
    # First tick: pushed to git, but the live fetch has nothing published yet.
    assert result["status"] == "pending"
    assert len(result["waiting"]) == 2
    pushed = subprocess.run(
        ["git", "log", "--oneline", "main"], cwd=remote, check=True, text=True, capture_output=True,
    ).stdout
    assert "self-owned 20260928-132912" in pushed

    # Simulate the site having deployed: build the exact markup the real page
    # would serve for each staged slug, keyed by the URL resume_publication fetches.
    articles_dir = landing / "apps/landing/private/writer-articles"
    for lang in ("ja", "en"):
        slug = next(
            json.loads(p.read_text(encoding="utf-8"))["slug"]
            for p in articles_dir.glob("*.json")
            if json.loads(p.read_text(encoding="utf-8")).get("lang") == lang
        )
        contract = json.loads((articles_dir / f"{slug}.json").read_text(encoding="utf-8"))
        published_markup[f"https://aniccaai.com/blog/{slug}"] = module.public_receipt_markup(contract)

    result = module.resume_publication(
        publication_state_path=publication_state_path,
        ledger_path=ledger_path,
        landing_root=landing,
        remote="origin",
        branch="main",
        base_url="https://aniccaai.com",
        fetch_markup=fake_fetch,
    )
    assert result["status"] == "complete"
    ledger_rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert {row["lang"] for row in ledger_rows} == {"ja", "en"}
    assert all(row["platform"] == "self-owned" and row["published"] is True for row in ledger_rows)
    assert all(row["live_url"].startswith("https://aniccaai.com/blog/") for row in ledger_rows)

    # A third tick is idempotent: already complete, no further git or network side effect.
    result = module.resume_publication(
        publication_state_path=publication_state_path,
        ledger_path=ledger_path,
        landing_root=landing,
        remote="origin",
        branch="main",
        base_url="https://aniccaai.com",
        fetch_markup=fake_fetch,
    )
    assert result["status"] == "complete"


def test_article_resume_pending_wires_the_self_owned_adjunct():
    """article-daily.sh's per-run publication resume loop lives in
    article-resume-pending.sh; this pins the call so the self-owned worker
    cannot be silently dropped from it again.
    """
    worker = ROOT.joinpath("skills/writer-agent/scripts/article-resume-pending.sh").read_text(
        encoding="utf-8"
    )
    block = worker.split("# The self-owned paid publication is an adjunct to active-four.", 1)[1]
    assert 'python3 "$ARTICLE_ROOT/scripts/self_owned_article.py" resume' in block
    assert '--landing-root "$ARTICLE_SELF_OWNED_LANDING_ROOT"' in block
    assert '--remote "$ARTICLE_SELF_OWNED_REMOTE"' in block
    assert '--branch "$ARTICLE_SELF_OWNED_BRANCH"' in block
    assert '--base-url "$ARTICLE_SELF_OWNED_BASE_URL"' in block


def test_build_contract_uses_frontmatter_title_when_h1_is_missing():
    # run 20260929-010128: the EN draft carried its title only in frontmatter.
    module = soa()
    body = "\n\n".join(f"Filler sentence number {i} with enough visible characters to count toward the preview minimum threshold." for i in range(20))
    markdown = f'---\ntitle: "A viral X post is not a funnel"\n---\n\n{body}\n\n## Paid section\n\npaid body\n'
    contract = module.build_contract(run_id="20260929-010128", lang="en", markdown=markdown)
    assert contract["title"] == "A viral X post is not a funnel"
