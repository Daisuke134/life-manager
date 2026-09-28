#!/usr/bin/env python3
"""Pick the next Capafy catalog skill to ship to PromptBase.

Pure selection logic, no network/browser: given (1) skills/capafy/catalog/*/
LISTING.md titles, (2) the authoritative Capafy `publish-list` agents (a
title matches when it equals a catalog dir's LISTING.md "## Title"), and (3)
the PromptBase ledger, choose the highest-priority slug that is:

  - online on Capafy (its title has agent_status == "online" on the server,
    the authoritative source -- never a local guess), AND
  - not already shipped or pending on PromptBase (ledger.already_listed
    returns None: no row yet, or the last row is a retryable terminal status
    such as "rejected" or "captcha_challenge_deferred").

Preference order: LISTING.md's "Demand rank: N" (lower first, reusing
skills/capafy-autopublish's own inventory_status.py ranking rather than a
second implementation), with the "reels-hook-lab" slug given first priority
whenever it is itself a candidate (the winner-family slug this loop's spec
names explicitly), then alphabetically by slug.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills/capafy-autopublish/scripts"))
import inventory_status  # noqa: E402  (reuse listing_title / listing_demand_rank)

sys.path.insert(0, str(HERE))
import ledger as ledger_mod  # noqa: E402

PREFERRED_FIRST_SLUG = "reels-hook-lab"


def catalog_titles(catalog_dir: Path) -> dict:
    """slug -> title for every catalog dir with a parseable LISTING.md title."""
    out: dict = {}
    if not catalog_dir.is_dir():
        return out
    for entry in sorted(catalog_dir.iterdir()):
        if not entry.is_dir():
            continue
        listing = entry / "LISTING.md"
        if not listing.is_file():
            continue
        title = inventory_status.listing_title(str(listing))
        if title:
            out[entry.name] = title
    return out


def online_titles(capafy_agents: list) -> set:
    return {
        (agent.get("name") or "").strip()
        for agent in capafy_agents
        if isinstance(agent, dict) and agent.get("agent_status") == "online"
    } - {""}


def select_next(catalog_dir: Path, capafy_agents: list, ledger_path: Path) -> dict:
    titles = catalog_titles(catalog_dir)
    if not titles:
        return {"slug": None, "reason": "no_catalog_items_found"}

    online = online_titles(capafy_agents)
    candidates = []
    for slug, title in titles.items():
        if title not in online:
            continue
        if ledger_mod.already_listed(slug, ledger_path) is not None:
            continue
        rank = inventory_status.listing_demand_rank(str(catalog_dir / slug / "LISTING.md"))
        priority = 0 if slug == PREFERRED_FIRST_SLUG else 1
        candidates.append((priority, rank, slug, title))

    if not candidates:
        return {"slug": None, "reason": "no_online_unshipped_catalog_item"}

    candidates.sort(key=lambda c: (c[0], c[1], c[2]))
    _, rank, slug, title = candidates[0]
    return {"slug": slug, "title": title, "demand_rank": rank}


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-dir", required=True, type=Path)
    parser.add_argument("--ledger-path", required=True, type=Path)
    parser.add_argument(
        "--capafy-list-file", required=True, type=Path,
        help="JSON file: 'packager.py publish-list' stdout ({'agents': [...]})",
    )
    args = parser.parse_args()
    payload = json.loads(args.capafy_list_file.read_text(encoding="utf-8"))
    agents = payload.get("agents") if isinstance(payload, dict) else None
    if not isinstance(agents, list):
        print(json.dumps({"slug": None, "reason": "capafy_list_missing_agents"}))
        return 1
    result = select_next(args.catalog_dir, agents, args.ledger_path)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
