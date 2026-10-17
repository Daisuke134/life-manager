#!/usr/bin/env python3
"""select_capafy_distribute_skill.py — deterministic daily pick for the Capafy
distribute (free-article) loop.

Selects profitable buyer-visible Capafy sellers from the configured skills,
ranked by last-30-day profit (falling back to net revenue when profit is
unmeasured). Hook Lab takes half the slots while other eligible sellers share
the rest; without Hook Lab, the highest-ranked seller takes half.

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


def _is_online_earner(products_cfg: dict, analytics: dict | None, slug: str) -> bool:
    agent_id = str(products_cfg["products"]["capafy-skills"]["skills"][slug]["agent_id"])
    for row in (analytics or {}).get("per_skill_rows") or []:
        if str(row.get("agent_id")) == agent_id:
            profit = _decimal_or_none(row.get("profit_30d_actual_usd"))
            if profit is None:
                profit = _decimal_or_none(row.get("profit_30d_usd"))
            # The seller list keeps the buyer-visible version flag while a next version is draft.
            has_online_version = row.get("has_online_version")
            buyer_visible = (
                has_online_version is True
                if has_online_version is not None
                else row.get("status") in ("online", "under_review")
            )
            return (buyer_visible
                    and profit is not None and profit > 0)
    return False


def _is_buyer_visible(products_cfg: dict, analytics: dict | None, slug: str) -> bool:
    agent_id = str(products_cfg["products"]["capafy-skills"]["skills"][slug]["agent_id"])
    for row in (analytics or {}).get("per_skill_rows") or []:
        if str(row.get("agent_id")) == agent_id:
            flag = row.get("has_online_version")
            return flag is True if flag is not None else row.get("status") in ("online", "under_review")
    return False


def select_for_date(
    products_cfg: dict,
    analytics: dict | None,
    date: dt.date,
    channel: str = "capafy-distribute",
    slot: int = 0,
) -> dict:
    ranked = rank_skills(products_cfg, analytics)
    # Other marketplaces' live listings (PromptBase, P4) join the rotation after
    # the Capafy ranking; they carry their own landing_url and no agent_id.
    extra = products_cfg["products"].get("promptbase", {}).get("listings", {})
    # Promote only online skills that made money in 30 days (2026-10-04: equal
    # rotation gave 0-order and losing agents as many articles as the sellers).
    # With no earner at all, keep the full rotation so the loop still publishes.
    earners = [slug for slug in ranked if _is_online_earner(products_cfg, analytics, slug)]
    # Rule 10: the top seller keeps half the slots while buyer-visible, even in a short
    # loss window (2026-10-16: Hook Lab at -2.43 got 0 of 48 slots after its price restore).
    if earners and "hook-lab" in ranked and "hook-lab" not in earners and _is_buyer_visible(products_cfg, analytics, "hook-lab"):
        earners = ["hook-lab"] + earners
    ranked = earners if earners else ranked + sorted(extra)
    # Keep Hook Lab in half the slots regardless of short-window profit ranking.
    if len(earners) > 1:
        first = "hook-lab" if "hook-lab" in earners else earners[0]
        ranked = [slug for other in earners if other != first for slug in (first, other)]
    if not ranked:
        raise ValueError("no capafy-skills or listings configured to rotate")
    # One slot per wake (48 half-hour slots/day); each slot promotes the next skill in the ranking.
    slug = ranked[(date.toordinal() * 8 + slot) % len(ranked)]
    skill = extra.get(slug) or products_cfg["products"]["capafy-skills"]["skills"][slug]
    return {
        "date": date.isoformat(),
        "channel": channel,
        "capafy_skill": slug,
        "agent_id": skill.get("agent_id", ""),
        "landing_url": skill.get("landing_url") or f"https://capafy.ai/agent/{skill['agent_id']}",
        "buyer_problem": skill.get("buyer_problem", ""),
        "seo_seed": skill.get("seo_seed", ""),
        "ct": f"{channel}-{slug}",
        "rank": (earners or ranked).index(slug) + 1 if slug in (earners or ranked) else ranked.index(slug) + 1,
        "ranked_slugs": ranked,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="JST calendar date YYYY-MM-DD; defaults to today JST")
    parser.add_argument("--products", required=True)
    parser.add_argument("--analytics", help="capafy-skill-analytics.json path (optional)")
    parser.add_argument("--channel", default="capafy-distribute")
    parser.add_argument("--slot", type=int, default=0, help="JST half-hour slot 0-47")
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
