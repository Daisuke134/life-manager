#!/usr/bin/env python3
"""capafy_market_sweep.py (C6 #1) — refresh a dated sweep of successful Capafy sellers via the
read-only POST /agent/agents/search (~50 queries) and compute price bands, so the daily
decision step (capafy_daily_decision.py) can compare OUR prices against the market instead of
guessing.

Baked-in fact #2 (docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md): "Copy
successful people first" — price/model/product decisions start from top sellers, not our own
listings or failures. This is the refresh half of that rule; capafy_daily_decision.py is the
compare-and-act half. Never a WRITE call: /agent/agents/search only reads the marketplace.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("LIFE_MANAGER_REPO", Path(__file__).resolve().parents[3]))
CAPAFY_HTTP = str(REPO_ROOT / "skills/capafy-autopublish/vendor/capafy-user/scripts/capafy_http.py")
STATE_HOME = Path(os.environ.get("LIFE_MANAGER_STATE_HOME", Path.home() / ".local/state/life-manager")).expanduser()
PYTHON = os.environ.get("CAPAFY_PYTHON", "/opt/homebrew/bin/python3")

# ponytail: a fixed keyword list covering our own catalog's job families plus adjacent
# high-volume Capafy niches, so ~50 search calls sample a broad slice of the marketplace
# without maintaining a second, harder-to-keep-in-sync "category taxonomy" file.
DEFAULT_QUERIES = [
    "hook lab", "tiktok script", "youtube script", "reels hook", "shorts hook", "podcast hook",
    "newsletter hook", "ad hook", "video script", "marketing strategist", "slide maker",
    "presentation deck", "pitch deck", "board update", "experiment readout", "sales deck",
    "sales objection", "customer escalation", "customer renewal", "customer support",
    "incident postmortem", "incident update", "risk register", "security exception",
    "vendor evaluation", "rfp response", "decision record", "launch readiness",
    "delivery commitment", "privacy notice", "sustainability disclosure", "talent review",
    "user interview", "research findings", "academic humanizer", "japanese humanizer",
    "ai humanizer", "dissertation editor", "scholarship essay", "grant proposal",
    "peer review response", "portfolio tracker", "stock tracker", "football analysis",
    "sports analysis", "finance summary", "budget planner", "crypto tracker",
    "resume writer", "cover letter", "seo content writer", "social media caption",
]


def _num(v):
    try:
        if isinstance(v, bool):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _fetch_query(query, page_size=30, timeout=30):
    body = json.dumps({"query": query, "page": 1, "pageSize": page_size})
    result = subprocess.run(
        [PYTHON, CAPAFY_HTTP, "POST", "/agent/agents/search", "--json", body],
        capture_output=True, text=True, timeout=timeout,
    )
    try:
        payload = json.loads(result.stdout)
    except (ValueError, TypeError):
        return []
    lst = (((payload or {}).get("data") or {}).get("list")) or []
    return lst if isinstance(lst, list) else []


def dedupe_agents(batches):
    """Flatten search-result batches into one list, unique by agentId (last write wins)."""
    by_id: dict[str, dict] = {}
    for batch in batches:
        for agent in batch:
            if not isinstance(agent, dict):
                continue
            agent_id = str(agent.get("agentId") or "").strip()
            if agent_id:
                by_id[agent_id] = agent
    return list(by_id.values())


def _cycle_prices(agent):
    """{cycleType: price} for subscription billings, or {"download": price} for a
    download one-time fee. Skips rows with no price set yet (a revenue-leak listing,
    not a market price to copy)."""
    out = {}
    for billing in agent.get("billings") or []:
        if not isinstance(billing, dict):
            continue
        mode = billing.get("billingMode")
        if mode == "subscription":
            cycle = billing.get("cycleType")
            price = _num(billing.get("cyclePrice"))
            if cycle and price:
                out[cycle] = price
        elif mode == "download":
            price = _num(billing.get("oneTimeFee"))
            if price:
                out["download"] = price
    return out


def aggregate_price_bands(agents):
    """Price band (p25/median/p75) per pricing cycle, restricted to agents whose
    salesVolume is at/above the overall median AND positive -- i.e. the "successful
    sellers" baked-in fact #2 says to copy, not every listing including the many
    with 0 sales."""
    sales = sorted(_num(a.get("salesVolume")) or 0.0 for a in agents)
    threshold = statistics.median(sales) if sales else 0.0
    successful = [a for a in agents
                  if (_num(a.get("salesVolume")) or 0.0) >= threshold
                  and (_num(a.get("salesVolume")) or 0.0) > 0]
    by_cycle: dict[str, list] = {}
    for agent in successful:
        for cycle, price in _cycle_prices(agent).items():
            by_cycle.setdefault(cycle, []).append(price)
    bands = {}
    for cycle, prices in by_cycle.items():
        prices = sorted(prices)
        n = len(prices)
        bands[cycle] = {
            "sample_size": n,
            "p25": prices[n // 4],
            "median": statistics.median(prices),
            "p75": prices[min(n - 1, (n * 3) // 4)],
        }
    return {"successful_seller_count": len(successful), "total_agents": len(agents), "bands": bands}


def top_uncovered_categories(agents, covered_tokens, limit=3, min_sales=50):
    """Rank tags among successful sellers (salesVolume >= min_sales) whose tag text does
    NOT substring-match any of our own catalog titles/tags (covered_tokens), so C6#2(d)
    can name a concrete next-category opportunity instead of guessing."""
    covered = {token.lower() for token in covered_tokens if token}
    scores: dict[str, dict] = {}
    for agent in agents:
        sales = _num(agent.get("salesVolume")) or 0.0
        if sales < min_sales:
            continue
        tags = [t.strip().lower() for t in str(agent.get("tags") or "").split(",") if t.strip()]
        if not tags:
            continue
        if any(any(tag in token or token in tag for token in covered) for tag in tags):
            continue
        key = tags[0]
        entry = scores.setdefault(key, {"tag": key, "total_sales": 0.0, "example_title": agent.get("title"),
                                         "example_sales": sales})
        entry["total_sales"] += sales
        if sales > entry["example_sales"]:
            entry["example_sales"] = sales
            entry["example_title"] = agent.get("title")
    ranked = sorted(scores.values(), key=lambda row: row["total_sales"], reverse=True)
    return ranked[:limit]


def main():
    queries_file = os.environ.get("CAPAFY_MARKET_SWEEP_QUERIES")
    queries = DEFAULT_QUERIES
    if queries_file and Path(queries_file).is_file():
        queries = [line.strip() for line in Path(queries_file).read_text().splitlines() if line.strip()]
    batches = []
    errors = 0
    for query in queries:
        try:
            batches.append(_fetch_query(query))
        except Exception as e:  # network / server-broken — never crash the daily loop
            errors += 1
            print(f"[capafy_market_sweep] query {query!r} failed: {e}", file=sys.stderr)
    agents = dedupe_agents(batches)
    observed_at = dt.datetime.now(dt.timezone.utc)
    dated_path = STATE_HOME / "state" / f"capafy-market-agents-{observed_at:%Y%m%d}.json"
    dated_path.parent.mkdir(parents=True, exist_ok=True)
    dated_path.write_text(json.dumps(agents, ensure_ascii=False), encoding="utf-8")
    bands = aggregate_price_bands(agents)
    bands_out = {
        "schema_version": 1,
        "kind": "capafy_market_price_bands",
        "observed_at": observed_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "queries": len(queries),
        "query_errors": errors,
        "raw_agents_path": str(dated_path),
        **bands,
    }
    bands_path = STATE_HOME / "state" / "capafy-market-price-bands-latest.json"
    bands_path.write_text(json.dumps(bands_out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(bands_out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
