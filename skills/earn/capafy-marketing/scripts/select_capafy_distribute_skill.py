#!/usr/bin/env python3
"""select_capafy_distribute_skill.py — deterministic daily pick for the Capafy
distribute (free-article) loop.

Rotates through Capafy's own best-selling skills (from
skills/writer-agent/config/products.json's "capafy-skills" list), ranked by
last-30-day profit (falls back to net revenue when profit is unmeasured), one
per JST calendar date. Every skill gets picked in turn as the ranking's order
changes over time, so the article always points at whichever skill made the
most money most recently rather than a fixed favorite.

  select_capafy_distribute_skill.py --date 2026-09-29 \
      --products skills/writer-agent/config/products.json \
      --analytics ~/.local/state/life-manager/state/capafy-skill-analytics.json

ct scheme: "<channel>-<skill-slug>" (default channel "capafy-distribute"), a
distinct token from the main Writer loop's own "article-<slug>" ct so Capafy's
traffic-sources dashboard (sourceType="ct") shows this loop's visits/sales as
their own row -- see skills/writer-agent/config/products.json "tracking".
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

JST = dt.timezone(dt.timedelta(hours=9))


def _decimal_or_none(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def rank_skills(products_cfg: dict, analytics: dict | None) -> list[dict]:
    """Return capafy-skills entries sorted best-first by 30d profit/revenue.

    Skills absent from the analytics rows (never synced yet) sort last, in a
    stable slug order, so a fresh install still rotates through every skill
    instead of crashing or picking nothing.
    """
    skills = products_cfg["products"]["capafy-skills"]["skills"]
    rows_by_agent: dict[str, dict] = {}
    if analytics:
        for row in analytics.get("per_skill_rows") or []:
            agent_id = row.get("agent_id")
            if agent_id:
                rows_by_agent[str(agent_id)] = row

    def score(slug: str) -> float:
        agent_id = str(skills[slug]["agent_id"])
        row = rows_by_agent.get(agent_id)
        if not row:
            return float("-inf")
        profit = _decimal_or_none(row.get("profit_30d_actual_usd"))
        if profit is None:
            profit = _decimal_or_none(row.get("profit_30d_usd"))
        if profit is not None:
            return profit
        revenue = _decimal_or_none(row.get("net_revenue_30d_usd"))
        return revenue if revenue is not None else float("-inf")

    slugs = sorted(skills)
    return sorted(slugs, key=lambda slug: (-score(slug), slug))


def select_for_date(
    products_cfg: dict,
    analytics: dict | None,
    date: dt.date,
    channel: str = "capafy-distribute",
    slot: int = 0,
) -> dict:
    ranked = rank_skills(products_cfg, analytics)
    if not ranked:
        raise ValueError("no capafy-skills configured to rotate")
    # 8 three-hour slots per day; each slot promotes the next skill in the ranking.
    slug = ranked[(date.toordinal() * 8 + slot) % len(ranked)]
    skill = products_cfg["products"]["capafy-skills"]["skills"][slug]
    return {
        "date": date.isoformat(),
        "channel": channel,
        "capafy_skill": slug,
        "agent_id": skill["agent_id"],
        "landing_url": f"https://capafy.ai/agent/{skill['agent_id']}",
        "buyer_problem": skill.get("buyer_problem", ""),
        "seo_seed": skill.get("seo_seed", ""),
        "ct": f"{channel}-{slug}",
        "rank": ranked.index(slug) + 1,
        "ranked_slugs": ranked,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="JST calendar date YYYY-MM-DD; defaults to today JST")
    parser.add_argument("--products", required=True)
    parser.add_argument("--analytics", help="capafy-skill-analytics.json path (optional)")
    parser.add_argument("--channel", default="capafy-distribute")
    parser.add_argument("--slot", type=int, default=0, help="3-hour JST slot 0-7")
    args = parser.parse_args(argv)

    products_cfg = json.loads(Path(args.products).read_text(encoding="utf-8"))
    analytics = None
    if args.analytics and Path(args.analytics).exists():
        analytics = json.loads(Path(args.analytics).read_text(encoding="utf-8"))

    date = (
        dt.date.fromisoformat(args.date)
        if args.date
        else dt.datetime.now(tz=JST).date()
    )
    result = select_for_date(products_cfg, analytics, date, channel=args.channel, slot=args.slot)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
