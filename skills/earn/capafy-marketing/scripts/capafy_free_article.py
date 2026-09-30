#!/usr/bin/env python3
"""capafy_free_article.py — publish ONE fully free (no paywall, no preview/
paid split) English article to aniccaai.com for the Capafy distribute loop.

Dais decision 2026-09-29: dev.to and Zenn are no longer used by this loop;
its free article now goes to our own site instead. The Writer's self-owned
publisher (skills/writer-agent/scripts/self_owned_article.py) always splits
an article into a public preview + a paid section
(SelfOwnedInvariant("no useful paid-section boundary...")) and writes into
apps/landing/private/writer-articles/<slug>.json behind a generated
require() registry -- that whole contract exists to protect the PAID body
and must not change for this always-free loop. aniccaai.com's blog page
already renders a second, fully public article source with no split at all:
apps/landing/data/research/<slug>.json. apps/landing/app/blog/[slug]/page.tsx
`loadPost()` checks the private paid store first, then falls back to this
directory verbatim (no access_model/paid_sha256/run_id/artifact_id/lang
fields at all, so `WriterUnlock` never renders); apps/landing/lib/
blog-posts.ts reads the same directory for the public post list. This
module writes exactly that: one plain JSON file, no registry, no
preview/paid split, full body public.

Reuses self_owned_article.py's PURE git/text helpers (`_git`, `_title`,
`_frontmatter_title`, `_without_frontmatter`) instead of re-implementing
them. Never calls its `build_contract`/`stage_contracts`/
`SelfOwnedPublicationStore` (the paid pipeline), so the Writer's paid
contract behaviour is untouched by this loop.

  capafy_free_article.py publish --draft-file article-en.md --slug SLUG \\
      --cta-url URL --landing-root DIR --remote origin --branch main \\
      --base-url https://aniccaai.com [--date 2026-09-29] \\
      [--retries 60] [--retry-interval-seconds 15]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

WRITER_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "writer-agent" / "scripts"

RESEARCH_RELATIVE = Path("apps/landing/data/research")
_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,99}")


def _load_self_owned_module():
    sys.path.insert(0, str(WRITER_SCRIPTS_DIR))
    import self_owned_article  # noqa: PLC0415

    return self_owned_article


def build_free_article(markdown_text: str, *, slug: str, date: str, cta_url: str) -> dict:
    """Pure: parse the draft, require the Capafy CTA link, return the exact
    plain public JSON body this loop writes to data/research/<slug>.json.
    """
    if _SLUG_RE.fullmatch(slug) is None:
        raise ValueError("slug is invalid")
    soa = _load_self_owned_module()
    source = soa._without_frontmatter(markdown_text)  # noqa: SLF001
    if cta_url not in source:
        raise ValueError("draft is missing the required Capafy CTA link")
    title = soa._title(source, soa._frontmatter_title(markdown_text))  # noqa: SLF001
    return {
        "slug": slug,
        "title": title,
        "date": date,
        "project": "capafy-distribute",
        "n_papers_cited": 0,
        "word_count": len(source.split()),
        "markdown": source,
    }


def _target_path(landing_root: Path, slug: str) -> Path:
    return landing_root / RESEARCH_RELATIVE / f"{slug}.json"


def write_free_article(landing_root: Path, article: dict) -> dict:
    """Write the plain public JSON if absent; refuse a slug collision with
    different bytes. A worktree left dirty by a prior partial run is only
    tolerated when the sole dirty path is this exact target file (retrying
    an interrupted publish, not an unrelated change).
    """
    soa = _load_self_owned_module()
    root = Path(landing_root).resolve()
    if soa._git(root, "rev-parse", "--show-toplevel") != str(root):  # noqa: SLF001
        raise ValueError("landing root is not the exact git worktree")
    target = _target_path(root, article["slug"])
    relative = target.relative_to(root)
    status = soa._git(root, "status", "--porcelain", "--untracked-files=all")  # noqa: SLF001
    dirty = {line[3:] for line in status.splitlines() if len(line) >= 4}
    if dirty - {str(relative)}:
        raise ValueError("landing worktree is dirty")
    if target.exists():
        current = _safe_read_json(target)
        if current != article:
            raise ValueError("slug conflict with different immutable bytes")
        return {"status": "already-present", "relative_path": str(relative)}
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(article, ensure_ascii=False, indent=2) + "\n"
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    temporary.write_text(encoded, encoding="utf-8")
    os.replace(temporary, target)
    return {"status": "staged", "relative_path": str(relative)}


def _safe_read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def commit_and_push(landing_root: Path, relative_path: str, *, message: str, remote: str, branch: str) -> dict:
    soa = _load_self_owned_module()
    root = Path(landing_root).resolve()
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts or path.parent != RESEARCH_RELATIVE or path.suffix != ".json":
        raise ValueError("publication target is outside the exact directory")
    dirty = {
        line[3:]
        for line in soa._git(root, "status", "--porcelain", "--untracked-files=all").splitlines()  # noqa: SLF001
        if len(line) >= 4
    }
    if dirty != {str(path)}:
        raise ValueError("unrelated landing change appeared before commit")
    soa._git(root, "add", "--", str(path))  # noqa: SLF001
    cached = set(soa._git(root, "diff", "--cached", "--name-only").splitlines())  # noqa: SLF001
    if cached != {str(path)}:
        raise ValueError("git index contains a non-publication target")
    soa._git(root, "commit", "-m", message)  # noqa: SLF001
    commit = soa._git(root, "rev-parse", "HEAD")  # noqa: SLF001
    soa._git(root, "push", remote, f"HEAD:refs/heads/{branch}")  # noqa: SLF001
    return {"commit": commit, "pushed": True}


def verify_live(markup: str, *, title: str, cta_url: str) -> None:
    if title not in markup:
        raise ValueError("public page is missing the article title")
    if cta_url not in markup:
        raise ValueError("public page is missing the required Capafy CTA link")


def _default_fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Capafy-Distribute/1.0"})
    with urllib.request.urlopen(request, timeout=8) as response:  # noqa: S310
        return response.read().decode("utf-8")


def publish(
    *, draft_path: Path, slug: str, cta_url: str, landing_root: Path, remote: str, branch: str,
    base_url: str, date: str | None = None, retries: int = 60, retry_interval_seconds: float = 15.0,
    fetch=None,
) -> dict:
    markdown_text = Path(draft_path).read_text(encoding="utf-8")
    date = date or dt.datetime.now(dt.timezone.utc).date().isoformat()
    article = build_free_article(markdown_text, slug=slug, date=date, cta_url=cta_url)
    write_result = write_free_article(landing_root, article)
    soa = _load_self_owned_module()
    root = Path(landing_root).resolve()
    if write_result["status"] == "staged":
        commit_result = commit_and_push(
            landing_root, write_result["relative_path"],
            message=f"feat(capafy-distribute): publish free article {slug}",
            remote=remote, branch=branch,
        )
    else:
        # Already committed by a prior (possibly interrupted) attempt. A push
        # with nothing new is a harmless no-op, so re-running it is safe.
        soa._git(root, "push", remote, f"HEAD:refs/heads/{branch}")  # noqa: SLF001
        commit_result = {"commit": soa._git(root, "rev-parse", "HEAD"), "pushed": True}  # noqa: SLF001

    live_url = f"{base_url.rstrip('/')}/blog/{slug}"
    fetch = fetch or _default_fetch
    last_error = "no attempt made"
    for attempt in range(max(1, retries)):
        try:
            markup = fetch(live_url)
            verify_live(markup, title=article["title"], cta_url=cta_url)
            return {
                "status": "published",
                "slug": slug,
                "url": live_url,
                "title": article["title"],
                "cta_url": cta_url,
                "commit": commit_result["commit"],
            }
        except Exception as error:  # deploy propagation is retried within this run
            last_error = f"{type(error).__name__}: {error}"
            if attempt + 1 < retries:
                time.sleep(retry_interval_seconds)
    raise SystemExit(f"public readback never confirmed the free article: {last_error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    publish_p = sub.add_parser("publish")
    publish_p.add_argument("--draft-file", required=True, type=Path)
    publish_p.add_argument("--slug", required=True)
    publish_p.add_argument("--cta-url", required=True)
    publish_p.add_argument("--landing-root", required=True, type=Path)
    publish_p.add_argument("--remote", required=True)
    publish_p.add_argument("--branch", required=True)
    publish_p.add_argument("--base-url", required=True)
    publish_p.add_argument("--date", default=None)
    publish_p.add_argument("--retries", type=int, default=60)  # GitHub Actions deploy takes ~5 min; 15 s polls cover 15 min
    publish_p.add_argument("--retry-interval-seconds", type=float, default=15.0)
    args = parser.parse_args(argv)

    result = publish(
        draft_path=args.draft_file,
        slug=args.slug,
        cta_url=args.cta_url,
        landing_root=args.landing_root,
        remote=args.remote,
        branch=args.branch,
        base_url=args.base_url,
        date=args.date,
        retries=args.retries,
        retry_interval_seconds=args.retry_interval_seconds,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
