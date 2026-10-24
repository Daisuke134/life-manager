#!/usr/bin/env python3
"""Hourly funnel diagnosis and improvement ledger for the Capafy distribution loop.

Deterministic, no LLM, read-only on Capafy: it reads the hourly reconcile, finds the narrowest funnel
stage, scores the previous logged change against the same metric, and appends one ledger row. Choosing
and shipping the next change stays with the reviewed PR path; this file only makes the loop remember
what it tried and whether it worked.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

RECONCILE = Path(os.environ.get(
    "CAPAFY_RECONCILE", "~/.local/state/life-manager/state/capafy-hourly-reconcile.json")).expanduser()
LEDGER = Path(os.environ.get(
    "CAPAFY_IMPROVEMENT_LEDGER", "~/.local/state/life-manager/state/capafy-improvement-ledger.jsonl")).expanduser()
MIN_VIEWS_FOR_PAID_SIGNAL = 200  # below this the views->paid rate is noise, do not blame that stage


def _rate(num, den):
    return None if not den else num / den


def funnel(reconcile: dict) -> dict:
    ts = reconcile["traffic_sources"]
    impressions = sum(r["exposure_count"] for r in ts["impressions"]["account"]["last_7d"]["by_source"])
    totals = ts["last_7d"]["totals"]
    views, trials, paid = totals["views"], totals["trial_orders"], totals["paid_orders"]
    return {
        "observed_at": reconcile.get("observed_at"),
        "impressions": impressions, "views": views, "trials": trials, "paid": paid,
        "view_rate": _rate(views, impressions), "trial_rate": _rate(trials, views),
        "paid_rate": _rate(paid, views),
    }


OUTSIDE_SHARE_FLOOR = 0.20  # below this our own distribution is too small to learn from; grow reach first


def channels(reconcile: dict) -> dict:
    """7d views/trials/paid split into the marketplace's own surfaces (internal) and everything we drive."""
    split = {"internal": {"views": 0, "trials": 0, "paid": 0}, "outside": {"views": 0, "trials": 0, "paid": 0}}
    ts = reconcile["traffic_sources"]
    # The account-level split is complete. by_agent covers only the ~60 of 79 agents queried this hour
    # (utc_hour_round_robin), so summing it swings with the omitted set (internal read 294 vs ~1,239).
    rows = (ts.get("last_7d") or {}).get("by_source")
    if not rows:
        rows = [row for agent in ts.get("by_agent", {}).values()
                for row in (agent.get("last_7d") or {}).get("by_source", [])]
    for row in rows:
        bucket = split["internal" if row["source_type"] == "internal" else "outside"]
        bucket["views"] += row["views"]
        bucket["trials"] += row["trial_orders"]
        bucket["paid"] += row["paid_orders"]
    total = split["internal"]["views"] + split["outside"]["views"]
    split["outside_view_share"] = _rate(split["outside"]["views"], total)
    return split


def lever(split: dict) -> str | None:
    """Which channel the next change should target."""
    share = split["outside_view_share"]
    if share is None:
        return None
    return "outside_reach" if share < OUTSIDE_SHARE_FLOOR else "internal_conversion"


def weakest_stage(f: dict) -> str | None:
    """The stage with the lowest conversion, judged against a 'healthy' marketplace benchmark."""
    if not f["impressions"] or f["view_rate"] is None:
        return None
    if f["views"] < MIN_VIEWS_FOR_PAID_SIGNAL:
        return "impressions_to_views"
    # Marketplace benchmark: ~10% of impressions open a page, ~1% of views pay. Pick the stage furthest
    # below its benchmark, as a ratio, so a tiny absolute rate late in the funnel is not always "weakest".
    gaps = {
        "impressions_to_views": f["view_rate"] / 0.10,
        "views_to_paid": (f["paid_rate"] or 0.0) / 0.01,
    }
    return min(gaps, key=gaps.get)


def evaluate_previous(previous: dict | None, current: dict) -> dict | None:
    if previous is None:
        return None
    now = current.get(previous["metric"])
    if now is None:
        verdict = "inconclusive"
    else:
        verdict = "kept" if now > previous["baseline"] else "revert_candidate"
    return {"action": previous.get("action"), "metric": previous["metric"],
            "baseline": previous["baseline"], "now": now, "verdict": verdict}


def _last_row(path: Path) -> dict | None:
    try:
        lines = [l for l in path.read_text().splitlines() if l.strip()]
        return json.loads(lines[-1]) if lines else None
    except (OSError, ValueError):
        return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--action", help="record the change shipped this cycle (text)")
    parser.add_argument("--metric", default="view_rate", help="metric the change should move")
    args = parser.parse_args(argv)
    f = funnel(json.loads(RECONCILE.read_text()))
    stage = weakest_stage(f)
    previous = _last_row(LEDGER)
    prior = None
    if previous and previous.get("action"):
        prior = evaluate_previous({"metric": previous["metric"], "baseline": previous["baseline"],
                                   "action": previous["action"]}, f)
    row = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "funnel": f,
           "weakest_stage": stage, "previous_verdict": prior}
    split = channels(json.loads(RECONCILE.read_text()))
    row.update(channels=split, lever=lever(split))
    if args.action:
        row.update(action=args.action, metric=args.metric, baseline=f.get(args.metric))
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
