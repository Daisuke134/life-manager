#!/usr/bin/env python3
"""Pick the next Hook Lab SEO keyword whose aniccaai.com page does not exist yet.

The 16 keyword-targeted pages (2026-10-16/17) became Hook Lab's top traffic source
(Google AI Overview), while the dated capafy-hook-lab-<slot> articles drew ~1 view a
week. capafy-distribute-daily asks this for a keyword on Hook Lab slots and writes
that page instead. Prints the keyword JSON, or nothing when the list is exhausted.
Usage: pick_seo_keyword.py KEYWORDS_JSON RESEARCH_DIR
"""
import json
import sys
from pathlib import Path


def pick(keywords, research_dir):
    research_dir = Path(research_dir)
    return next((k for k in keywords if not (research_dir / f"{k['slug']}.json").exists()), None)


if __name__ == "__main__":
    hit = pick(json.loads(Path(sys.argv[1]).read_text()), sys.argv[2])
    if hit:
        print(json.dumps(hit, ensure_ascii=False))
