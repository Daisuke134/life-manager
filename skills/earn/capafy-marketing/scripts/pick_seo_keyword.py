#!/usr/bin/env python3
"""Pick the next Hook Lab SEO keyword whose aniccaai.com page does not exist yet.

capafy-distribute-daily asks this for a keyword on Hook Lab slots and writes
that page instead. Traffic-source classification and measured outcomes live in
the canonical SSOT; creating a page does not establish external search acquisition.
Prints the keyword JSON, or nothing when the list is exhausted.
Usage: pick_seo_keyword.py KEYWORDS_JSON RESEARCH_DIR
"""
import json
import sys
from pathlib import Path


def listing_example(listing_path):
    """The seller's published '## ... Example' section, quoted on keyword pages above the CTA
    so a searcher sees real input/output before the Capafy click (2026-10-18: 0% view->paid)."""
    try:
        text = Path(listing_path).read_text(encoding="utf-8")
    except OSError:
        return ""
    lines, out, inside = text.splitlines(), [], False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = "example" in line.lower()
            continue
        if inside:
            out.append(line)
    return "\n".join(out).strip()


def pick(keywords, research_dir):
    research_dir = Path(research_dir)
    return next((k for k in keywords if not (research_dir / f"{k['slug']}.json").exists()), None)


if __name__ == "__main__":
    if sys.argv[1] == "--example":
        print(listing_example(sys.argv[2]))
        raise SystemExit(0)
    hit = pick(json.loads(Path(sys.argv[1]).read_text()), sys.argv[2])
    if hit:
        print(json.dumps(hit, ensure_ascii=False))
