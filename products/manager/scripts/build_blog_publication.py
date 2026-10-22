#!/usr/bin/env python3
"""Add reviewed Manager manuscripts to the existing canonical blog package.

This is an offline content builder, not a publisher. The existing integrity-
checking installer, Next build and Netlify release continue to own publication.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import quote, unquote, urlsplit


REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path("products/manager/publication/articles-2026-10-22.json")
PACKAGE_PATH = Path("docs/research/manager/publication/2026-10-19")
RECEIPT_PATH = Path("products/manager/docs/verification/BLOG_PUBLICATION_PACKAGE_20261022.json")
SOURCE_ROOT = Path("products/manager/docs")
SLUG = re.compile(r"manager-[a-z0-9]+(?:-[a-z0-9]+)*-(?:en|ja)")
LINK = re.compile(r"(!?)\[([^\]\n]*)\]\(([^)\n]+)\)")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventory_digest(value):
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8"))


def source_file(root, value, suffix=".md"):
    path = PurePosixPath(value)
    if (path.is_absolute() or ".." in path.parts or "\\" in value
            or not value.startswith(SOURCE_ROOT.as_posix() + "/") or path.suffix != suffix):
        raise ValueError("Source path is outside Manager documentation: " + value)
    resolved = (root / value).resolve()
    if not resolved.is_relative_to((root / SOURCE_ROOT).resolve()):
        raise ValueError("Source path resolves outside Manager documentation: " + value)
    return resolved


def additive_media(root, config, original, frozen):
    """Append explicitly reviewed PNGs without replacing the frozen archive."""
    items = config.get("media", [])
    if not isinstance(items, list):
        raise ValueError("Media inventory must be a list")
    additions, copies, sources = [], {}, set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"source", "source_sha256"}:
            raise ValueError("Invalid additive media entry")
        source, expected = item["source"], item["source_sha256"]
        if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise ValueError("Invalid media source hash")
        path = source_file(root, source, ".png")
        raw = path.read_bytes()
        if digest(raw) != expected:
            raise ValueError("Media source hash mismatch: " + source)
        if (len(raw) < 24 or not raw.startswith(b"\x89PNG\r\n\x1a\n")
                or raw[12:16] != b"IHDR" or not int.from_bytes(raw[16:20], "big")
                or not int.from_bytes(raw[20:24], "big")):
            raise ValueError("Additive media must contain a PNG image: " + source)
        package_path = "media/" + expected + ".png"
        if source in sources or package_path in copies:
            raise ValueError("Duplicate additive media source or content")
        sources.add(source)
        copies[package_path] = raw
        additions.append({"source": source, "package_path": package_path,
                          "sha256": expected, "bytes": len(raw),
                          "public_url": "https://aniccaai.com/blog/manager/" + package_path})
    by_path = {item["package_path"]: item for item in additions}
    seen_paths, legacy = set(), []
    for item in original["media"]:
        path = item["package_path"]
        if path in seen_paths:
            raise ValueError("Duplicate media path in existing package")
        seen_paths.add(path)
        if path in by_path:
            if item != by_path[path]:
                raise ValueError("Media collision or unauthorized replacement: " + path)
        else:
            legacy.append(item)
    if (len(legacy) != frozen["media_count"]
            or inventory_digest(legacy) != frozen["media_sha256"]):
        raise ValueError("Legacy media inventory changed; existing bytes must be preserved")
    return copy.deepcopy(legacy) + additions, copies, additions


def public_markdown(markdown, source, root, revision, known_media):
    """Strip metadata and resolve source-relative citations; never fetch a URL."""
    if markdown.startswith("---\n"):
        end = markdown.find("\n---\n", 4)
        if end < 0:
            raise ValueError("Unterminated article frontmatter")
        markdown = markdown[end + 5:].lstrip("\n")

    def link(match):
        image, label, target = match.groups()
        if image and target not in known_media:
            raise ValueError("Unregistered image: " + target)
        parsed = urlsplit(target)
        if any(ch.isspace() for ch in target) or any(ch in target for ch in ('\\', '<', '>', '"', "'")):
            raise ValueError("Unsafe link: " + target)
        if parsed.scheme:
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError("Unsafe link: " + target)
        elif target.startswith("#"):
            pass
        elif target.startswith("/") or parsed.netloc or parsed.query:
            raise ValueError("Unsafe link: " + target)
        else:
            resolved = (source.parent / unquote(parsed.path)).resolve()
            if not resolved.is_relative_to((root / "products/manager").resolve()):
                raise ValueError("Relative link escapes Manager: " + target)
            if not resolved.exists():
                raise ValueError("Missing relative link: " + target)
            kind = "tree" if resolved.is_dir() else "blob"
            target = (f"https://github.com/Daisuke134/life-manager/{kind}/{revision}/"
                      + quote(resolved.relative_to(root).as_posix(), safe="/"))
            if parsed.fragment:
                target += "#" + parsed.fragment
        return f"{image}[{label}]({target})"

    return LINK.sub(link, markdown)


def build_publication(root, config, original):
    root = Path(root).resolve()
    if config.get("schema_version") != 1 or not re.fullmatch(r"[a-f0-9]{40}", config.get("source_commit", "")):
        raise ValueError("Invalid source inventory version or immutable commit")
    seen_slugs, seen_sources = set(), set()
    for item in config["articles"]:
        slug = item["slug"]
        if not SLUG.fullmatch(slug):
            raise ValueError("Invalid article slug: " + slug)
        lang = item.get("lang", "en")
        if lang not in ("en", "ja") or not slug.endswith("-" + lang):
            raise ValueError("Article language and slug must agree: " + slug)
        revision = item.get("source_commit", config["source_commit"])
        if not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise ValueError("Invalid per-article immutable commit: " + slug)
        if slug in seen_slugs:
            raise ValueError("Duplicate article slug: " + slug)
        if item["source_sha256"] in seen_sources:
            raise ValueError("Duplicate manuscript: " + item["source"])
        source_file(root, item["source"])
        seen_slugs.add(slug)
        seen_sources.add(item["source_sha256"])

    legacy = [a for a in original["articles"] if a["slug"] not in seen_slugs]
    frozen = config["legacy"]
    if len(legacy) != frozen["article_count"] or inventory_digest(legacy) != frozen["articles_sha256"]:
        raise ValueError("Legacy article inventory changed; review against the deployed package")
    media, copies, media_records = additive_media(root, config, original, frozen)
    known_media = {m["public_url"] for m in media}
    additions, records = [], []
    for item in config["articles"]:
        path = source_file(root, item["source"])
        raw = path.read_bytes()
        if digest(raw) != item["source_sha256"]:
            raise ValueError("Source hash mismatch: " + item["source"])
        revision = item.get("source_commit", config["source_commit"])
        lang = item.get("lang", "en")
        markdown = public_markdown(raw.decode("utf-8"), path, root, revision, known_media)
        title = next((line[2:] for line in markdown.splitlines() if line.startswith("# ")), None)
        if title != item["title"]:
            raise ValueError("Article title does not match source: " + item["slug"])
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item["date"]):
            raise ValueError("Invalid article date")
        if type(item["n_papers_cited"]) is not int or item["n_papers_cited"] < 0:
            raise ValueError("Invalid citation count")
        package_path = lang + "/" + item["slug"] + ".md"
        article = {key: item[key] for key in ("slug", "title", "date", "description", "series_order", "n_papers_cited")}
        article.update({"lang": lang, "project": "Manager", "package_path": package_path,
                        "source": item["source"], "source_sha256": item["source_sha256"],
                        "source_commit": revision, "sha256": digest(markdown.encode("utf-8")),
                        "word_count": len(markdown.split()), "markdown": markdown,
                        "canonical_url": "https://aniccaai.com/blog/" + item["slug"]})
        additions.append(article)
        copies[package_path] = markdown.encode("utf-8")
        records.append({key: article[key] for key in ("slug", "source", "source_sha256", "source_commit",
                        "package_path", "sha256", "canonical_url", "word_count")})

    package = copy.deepcopy(original)
    package["articles"] = copy.deepcopy(legacy) + additions
    package["media"] = media
    package["additive_publication"] = {
        "inventory": CONFIG_PATH.as_posix(), "source_commit": config["source_commit"],
        "legacy_articles": len(legacy), "additional_articles": len(additions),
        "publication_verified": False,
        "scope": "Source package only; live publication requires canonical release receipt and article readback.",
    }
    english = sum(a["lang"] == "en" for a in additions)
    japanese = sum(a["lang"] == "ja" for a in additions)
    languages = (f"{english} English and {japanese} Japanese articles" if japanese
                 else f"{english} further English articles")
    inventory_note = (f"The legacy archive contains {sum(a.get('lang') == 'ja' for a in legacy)} Japanese "
                      f"and {sum(a.get('lang') == 'en' for a in legacy)} English articles; "
                      f"the additive inventory has {languages}.")
    package["publication_constraints"] = [
        re.sub(r"The (?:admitted|legacy) archive contains \d+ Japanese and \d+ English articles"
               r"(?:; the additive inventory has [^.]+)?\.", inventory_note, text)
        for text in package.get("publication_constraints", [])
    ]
    receipt = {
        "schema": "manager.blog-publication-package.v1", "source_commit": config["source_commit"],
        "legacy_article_count": len(legacy), "article_count": len(package["articles"]),
        "media_count": len(package["media"]), "publication_verified": False,
        "existing_installer": "apps/landing/manager-blog/scripts/install.mjs",
        "transformations": ["Remove YAML frontmatter from two EBA manuscripts.",
                            "Resolve source-relative citations to existing files at the immutable source commit.",
                            "Preserve all prose, existing absolute links and registered media."],
        "articles": records,
    }
    source_commits = sorted({a["source_commit"] for a in additions})
    if source_commits != [config["source_commit"]]:
        package["additive_publication"]["source_commits"] = source_commits
        receipt["source_commits"] = source_commits
    if media_records:
        receipt["media"] = media_records
    return package, copies, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify generated bytes without modifying files")
    args = parser.parse_args()
    config = json.loads((REPO / CONFIG_PATH).read_text(encoding="utf-8"))
    original = json.loads((REPO / PACKAGE_PATH / "manifest.json").read_text(encoding="utf-8"))
    package, copies, receipt = build_publication(REPO, config, original)
    outputs = {PACKAGE_PATH / key: value for key, value in copies.items()}
    for path, value in ((PACKAGE_PATH / "manifest.json", package), (RECEIPT_PATH, receipt)):
        outputs[path] = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    for relative, expected in outputs.items():
        path = REPO / relative
        if args.check:
            if not path.is_file() or path.read_bytes() != expected:
                raise SystemExit("Generated publication differs: " + relative.as_posix())
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(expected)
    print(f"{'Checked' if args.check else 'Prepared'} {len(package['articles'])} articles, "
          f"{len(package['media'])} media; publication remains unverified")


if __name__ == "__main__":
    main()
