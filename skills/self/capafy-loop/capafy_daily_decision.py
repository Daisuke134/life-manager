#!/usr/bin/env python3
"""capafy_daily_decision.py (C6) — the daily analysis closed loop: read per-skill profit,
market price bands, and traffic views, then decide what Life Manager should build/fix next,
without ever writing to Capafy directly.

Four rules (docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md row C6):
  1. losing money (model cost > 30% of net)              -> queue a model-switch UPDATE.json
  2. priced below the successful sellers' band            -> queue a reprice UPDATE.json
     (download/one-time only; CP1 has no subscription-cycle reprice field yet -- C4 note)
  3. zero sales in 30d with real traffic (views)           -> flag a retire/rewrite candidate
  4. best uncovered category among top sellers             -> append a category opportunity

Every queued file is one the factory already reads: UPDATE.json (skills/capafy/catalog/<x>/,
consumed by inventory_status.py's ready_inventory()) or the category-opportunity backlog
(read by the offline-build prompt in capafy-loop-daily.sh). No Capafy API write ever happens
here -- reads are GET /agent/agents and the already-collected analytics/traffic snapshots.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("LIFE_MANAGER_REPO", Path(__file__).resolve().parents[3]))
CAPAFY_HTTP = str(REPO_ROOT / "skills/capafy-autopublish/vendor/capafy-user/scripts/capafy_http.py")
STATE_HOME = Path(os.environ.get("LIFE_MANAGER_STATE_HOME", Path.home() / ".local/state/life-manager")).expanduser()
PYTHON = os.environ.get("CAPAFY_PYTHON", "/opt/homebrew/bin/python3")
CATALOG_DIR = Path(os.environ.get("CAPAFY_CATALOG_DIR") or (REPO_ROOT / "skills/capafy/catalog"))

ANALYTICS_PATH = STATE_HOME / "state/capafy-skill-analytics.json"
HOURLY_RECONCILE_PATH = STATE_HOME / "state/capafy-hourly-reconcile.json"
PRICE_BANDS_PATH = STATE_HOME / "state/capafy-market-price-bands-latest.json"
DECISIONS_DIR = STATE_HOME / "state/capafy-daily-decisions"
OPPORTUNITIES_PATH = STATE_HOME / "state/capafy-candidate-opportunities.json"

LOSING_MONEY_COST_RATIO = 0.30
UNDERPRICE_MARGIN_USD = 1.0
ZERO_SALES_VIEWS_THRESHOLD = 20
TARGET_CHEAP_MODEL_ID = "deepseek/deepseek-v4.1-flash"
CHEAP_MODEL_NAME_TOKEN = "deepseek"
# Same-Agent update leaves an Agent occupying a review slot; never queue a second one
# while the first is still in flight (task requirement: no duplicate UPDATE while pending).
PENDING_SERVER_STATUSES = {"draft", "under_review", "review_rejected", "submitted"}


def _num(value):
    try:
        if isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Read-only Capafy fetch (identical pattern to sales_selector.py's _fetch()).
# ---------------------------------------------------------------------------

def fetch_server_agents():
    result = subprocess.run(
        [PYTHON, CAPAFY_HTTP, "GET", "/agent/agents"],
        capture_output=True, text=True, timeout=60,
    )
    payload = json.loads(result.stdout)
    lst = (((payload or {}).get("data") or {}).get("list")) or []
    return lst if isinstance(lst, list) else []


def index_server_agents(agents):
    return {str(a.get("agentId")): a for a in agents if isinstance(a, dict) and a.get("agentId")}


# ---------------------------------------------------------------------------
# Catalog index: title -> {dir, pricing, has_update}
# ---------------------------------------------------------------------------

def listing_title(text):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "## Title" and i + 1 < len(lines):
            return lines[i + 1].strip()
    return None


def parse_listing_pricing(text):
    """{cycle: price} from the '| cycle | price | cap | trial |' Pricing table."""
    out = {}
    for match in re.finditer(r"^\|\s*(day|week|month|year|download)\s*\|\s*\$?([\d.]+)\s*\|", text, re.M):
        cycle, price = match.group(1), _num(match.group(2))
        if price is not None:
            out[cycle] = price
    return out


def build_catalog_index(catalog_dir=CATALOG_DIR):
    index = {}
    if not Path(catalog_dir).is_dir():
        return index
    for entry in sorted(Path(catalog_dir).iterdir()):
        if not entry.is_dir():
            continue
        listing_path = entry / "LISTING.md"
        if not listing_path.is_file():
            continue
        text = listing_path.read_text(encoding="utf-8")
        title = listing_title(text)
        if not title:
            continue
        index[title] = {
            "dir_name": entry.name,
            "dir_path": str(entry),
            "pricing": parse_listing_pricing(text),
            "has_update": (entry / "UPDATE.json").is_file(),
        }
    return index


# ---------------------------------------------------------------------------
# Traffic views per agent (from the hourly reconcile's traffic_sources.by_agent).
# ---------------------------------------------------------------------------

def views_by_agent(hourly_reconcile):
    out = {}
    by_agent = (((hourly_reconcile or {}).get("traffic_sources") or {}).get("by_agent")) or {}
    for agent_id, windows in by_agent.items():
        totals = (((windows or {}).get("last_30d") or {}).get("totals")) or {}
        views = totals.get("views")
        if isinstance(views, (int, float)) and not isinstance(views, bool):
            out[str(agent_id)] = views
    return out


# ---------------------------------------------------------------------------
# Decision engine (pure, fixture-testable).
# ---------------------------------------------------------------------------

def decide_actions(analytics_rows, server_by_id, catalog_by_title, price_bands, views):
    """One decision dict per skill in analytics_rows. Never mutates input."""
    bands = (price_bands or {}).get("bands") or {}
    decisions = []
    for row in analytics_rows or []:
        agent_id = str(row.get("agent_id") or "")
        name = row.get("name") or ""
        server = server_by_id.get(agent_id)
        catalog = catalog_by_title.get(name)
        pending = bool(server) and server.get("agentStatus") in PENDING_SERVER_STATUSES
        has_update_file = bool(catalog and catalog.get("has_update"))
        blocked = pending or has_update_file
        block_reason = "pending_review" if pending else ("update_already_queued" if has_update_file else None)

        net = _num(row.get("net_revenue_30d_usd"))
        cost = _num(row.get("cost_30d_actual_usd"))
        if cost is None:
            cost = _num(row.get("cost_30d_usd"))
        orders = _num(row.get("stats_30d_orders")) or 0.0
        model = str(row.get("model") or "")
        agent_views = views.get(agent_id)

        decision = {
            "agent_id": agent_id, "name": name, "model": model,
            "net_revenue_30d_usd": net, "cost_30d_actual_usd": cost,
            "stats_30d_orders": orders, "views_30d": agent_views,
            "findings": [],
        }

        # 1. Losing money.
        losing = cost is not None and cost > 0 and (
            (net is not None and net > 0 and cost > LOSING_MONEY_COST_RATIO * net)
            or (net is not None and net <= 0)
        )
        if losing:
            if blocked:
                decision["findings"].append({"rule": "losing_money", "action": "skip", "reason": block_reason})
            elif not catalog:
                decision["findings"].append({"rule": "losing_money", "action": "skip", "reason": "no_catalog_match"})
            elif not server:
                decision["findings"].append({"rule": "losing_money", "action": "skip", "reason": "no_server_match"})
            elif CHEAP_MODEL_NAME_TOKEN in model.lower():
                decision["findings"].append({
                    "rule": "losing_money", "action": "manual_review",
                    "reason": "already_on_cheap_model_needs_price_or_scope_fix",
                })
            else:
                decision["findings"].append({
                    "rule": "losing_money", "action": "queue_update",
                    "update": {
                        "agent_id": agent_id,
                        "from_version_id": str(server.get("latestAgentVersionId") or ""),
                        "target_model_id": TARGET_CHEAP_MODEL_ID,
                        "reason": "daily_decision_losing_money_switch_to_cheap_model",
                    },
                    "catalog_dir": catalog["dir_path"],
                })

        # 2. Underpriced vs. the successful-seller band.
        if catalog:
            pricing = catalog.get("pricing") or {}
            download_price = pricing.get("download")
            download_band = bands.get("download")
            if download_price is not None and download_band and download_price < download_band["p25"] - UNDERPRICE_MARGIN_USD:
                already_has_action = any(f.get("action") == "queue_update" for f in decision["findings"])
                if blocked or already_has_action:
                    decision["findings"].append({
                        "rule": "underpriced", "action": "skip",
                        "reason": block_reason or "losing_money_update_already_queued",
                    })
                elif not server:
                    decision["findings"].append({"rule": "underpriced", "action": "skip", "reason": "no_server_match"})
                else:
                    decision["findings"].append({
                        "rule": "underpriced", "action": "queue_update",
                        "update": {
                            "agent_id": agent_id,
                            "from_version_id": str(server.get("latestAgentVersionId") or ""),
                            "target_one_time_fee": f"{download_band['median']:.2f}",
                            "reason": "daily_decision_reprice_to_successful_seller_band",
                        },
                        "catalog_dir": catalog["dir_path"],
                    })
            for cycle in ("day", "week", "month", "year"):
                price = pricing.get(cycle)
                band = bands.get(cycle)
                if price is not None and band and price < band["p25"] - UNDERPRICE_MARGIN_USD:
                    decision["findings"].append({
                        "rule": "underpriced", "action": "blocked_no_cp1_support",
                        "cycle": cycle, "our_price": price, "band_p25": band["p25"],
                        "reason": "cp1_has_no_subscription_cycle_reprice_field_yet",
                    })

        # 3. Zero sales with real traffic.
        if orders == 0 and isinstance(agent_views, (int, float)) and agent_views >= ZERO_SALES_VIEWS_THRESHOLD:
            decision["findings"].append({
                "rule": "zero_sales_with_views", "action": "retire_or_rewrite_candidate",
                "views_30d": agent_views,
            })

        decisions.append(decision)
    return decisions


def build_telegram_summary(decisions, opportunity, observed_at):
    """One-screen Japanese summary, numbers-first (per SSOT C6: '日次レポートの数字 → 次の行動の記録')."""
    queued = [d for f in [dec["findings"] for dec in decisions] for d in f if d.get("action") == "queue_update"]
    retire = [dec for dec in decisions if any(f.get("action") == "retire_or_rewrite_candidate" for f in dec["findings"])]
    manual = [dec for dec in decisions if any(f.get("action") == "manual_review" for f in dec["findings"])]
    lines = [f"Capafy 日次分析 {observed_at}"]
    lines.append(f"分析対象 {len(decisions)} スキル / 新規キュー {len(queued)} 件"
                 f" / 要手動確認 {len(manual)} 件 / 撤退・書き直し候補 {len(retire)} 件")
    for dec in decisions:
        for finding in dec["findings"]:
            if finding.get("action") == "queue_update":
                update = finding["update"]
                target = update.get("target_model_id") or f"${update.get('target_one_time_fee')}"
                lines.append(f"・{dec['name']}: {finding['rule']} → {target} を queue（{update['reason']}）")
    for dec in retire[:5]:
        lines.append(f"・{dec['name']}: 30日売上0・閲覧{dec['views_30d']} → 書き直し/取り下げ候補")
    if opportunity:
        lines.append(f"次カテゴリ候補: {opportunity['tag']}（売れ筋例 {opportunity['example_title']}"
                      f"・売上台数 {opportunity['example_sales']:.0f}）")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Side effects: queue files, write the dated decision record.
# ---------------------------------------------------------------------------

def queue_update_file(catalog_dir, update):
    path = Path(catalog_dir) / "UPDATE.json"
    if path.exists():
        return False
    path.write_text(json.dumps(update, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def append_opportunity(path, opportunity, observed_at):
    """Dedup by tag; keeps the freshest observation per opportunity."""
    data = _load_json(path, {"schema_version": 1, "items": []})
    if not isinstance(data.get("items"), list):
        data["items"] = []
    if opportunity is None:
        return data
    items = [item for item in data["items"] if item.get("tag") != opportunity["tag"]]
    items.append({**opportunity, "observed_at": observed_at})
    data["items"] = items
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def write_decision_record(decisions, opportunity, observed_at, telegram_summary, path_dir=DECISIONS_DIR):
    record = {
        "schema_version": 1,
        "kind": "capafy_daily_decision",
        "observed_at": observed_at,
        "decisions": decisions,
        "category_opportunity": opportunity,
        "telegram_summary": telegram_summary,
    }
    Path(path_dir).mkdir(parents=True, exist_ok=True)
    out_path = Path(path_dir) / f"{observed_at[:10]}.json"
    out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out_path


def main():
    observed_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    analytics = _load_json(ANALYTICS_PATH, {}) or {}
    analytics_rows = analytics.get("per_skill_rows") or []
    hourly = _load_json(HOURLY_RECONCILE_PATH, {}) or {}
    price_bands = _load_json(PRICE_BANDS_PATH, {}) or {}
    catalog_by_title = build_catalog_index()
    views = views_by_agent(hourly)

    try:
        server_agents = fetch_server_agents()
    except Exception as e:
        print(f"[capafy_daily_decision] server fetch failed: {e}", file=sys.stderr)
        server_agents = []
    server_by_id = index_server_agents(server_agents)

    # (4) best uncovered category, from the latest dated market sweep if present.
    opportunity = None
    market_agents_files = sorted(STATE_HOME.glob("state/capafy-market-agents-*.json"))
    if market_agents_files:
        try:
            from capafy_market_sweep import top_uncovered_categories
        except ImportError:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from capafy_market_sweep import top_uncovered_categories
        market_agents = _load_json(market_agents_files[-1], []) or []
        covered_tokens = list(catalog_by_title.keys())
        for title in catalog_by_title:
            covered_tokens.extend(title.lower().split())
        ranked = top_uncovered_categories(market_agents, covered_tokens)
        opportunity = ranked[0] if ranked else None

    decisions = decide_actions(analytics_rows, server_by_id, catalog_by_title, price_bands, views)

    queued = 0
    for dec in decisions:
        for finding in dec["findings"]:
            if finding.get("action") == "queue_update":
                if queue_update_file(finding["catalog_dir"], finding["update"]):
                    queued += 1

    if opportunity:
        append_opportunity(OPPORTUNITIES_PATH, opportunity, observed_at)

    summary = build_telegram_summary(decisions, opportunity, observed_at)
    record_path = write_decision_record(decisions, opportunity, observed_at, summary)
    print(json.dumps({"ok": True, "decisions": len(decisions), "queued_updates": queued,
                       "record_path": str(record_path), "telegram_summary": summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
