#!/usr/bin/env python3
"""select_article_product.py — deterministic per-run CTA product pick for article-daily.sh.

The article loop used to send every reader to exactly one product (anicca). Capafy's own
best-selling skills get a steady share too now, so Capafy sales become one more attributable
outcome of the same daily article, not a separate campaign.

Deterministic from run_id alone (no state file, no lock, safe under the loop's existing
mkdir-based concurrency guard): the run's JST calendar date decides anicca vs capafy-skills
with strict every-other-day alternation, and the same date also round-robins which Capafy
skill gets the run so all six get roughly equal exposure over time. The production run_id
from article-daily.sh's `date -u '+%Y%m%d-%H%M%S'` is a UTC timestamp, so it is converted to
JST before taking the date -- a 06:00 JST run stamps a UTC clock still on the previous
calendar day, and using that raw UTC date would silently break the every-other-day cadence.
A run_id without an embedded date (tests, ad hoc runs) still gets a stable pick via a
byte-sum fallback -- deterministic, not current-time-based, so the same run_id always
reproduces the same pick.

  select_article_product.py --run-id daily-2026-09-28 --config config/products.json
  select_article_product.py --run-id 20260930-010000 --config config/products.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

JST = dt.timezone(dt.timedelta(hours=9))
RUN_ID_UTC_TIMESTAMP = re.compile(r"(\d{8})-(\d{6})")
RUN_ID_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def day_index(run_id: str) -> int:
    match = RUN_ID_UTC_TIMESTAMP.search(run_id)
    if match:
        utc_dt = dt.datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S").replace(
            tzinfo=dt.timezone.utc
        )
        return utc_dt.astimezone(JST).date().toordinal()
    match = RUN_ID_DATE.search(run_id)
    if match:
        return dt.date.fromisoformat(match.group(1)).toordinal()
    return sum(run_id.encode("utf-8"))


def select(config: dict, run_id: str) -> dict:
    products = config["products"]
    idx = day_index(run_id)
    if idx % 2 == 0:
        anicca = products["anicca"]
        return {
            "product_id": "anicca",
            "landing_url": anicca["landing_url"],
            "capafy_skill": None,
            "buyer_problem": None,
            "ct": "",
        }
    skills = products["capafy-skills"]["skills"]
    slugs = sorted(skills)
    # idx only ever lands on every-other value here (the anicca branch above takes the rest), so
    # indexing slugs by idx directly would cycle mod len(slugs) through the same fixed-parity
    # subset forever and half the skills would never be picked. idx // 2 advances by exactly 1
    # per Capafy-selected run, which visits every slug in turn.
    slug = slugs[(idx // 2) % len(slugs)]
    skill = skills[slug]
    return {
        "product_id": "capafy-skills",
        "landing_url": f"https://capafy.ai/agent/{skill['agent_id']}",
        "capafy_skill": slug,
        "buyer_problem": skill.get("buyer_problem", ""),
        "ct": f"article-{slug}",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    print(json.dumps(select(config, args.run_id), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
