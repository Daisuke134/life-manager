#!/usr/bin/env python3
"""Close surplus tabs owned by one loop on the daily-driver.

Each 応募 opens a Coconala tab and nothing closes it. Fifteen-plus live tabs starved the machine
(free pages ~62MB, load average past 21) and Chromium died, which blinds the whole gig loop.
Keeping one owned Coconala tab alive preserves the loop's working page. Foreign and unregistered
tabs are never touched.

Deterministic bookkeeping only — which page to visit stays the agent's call.

    python3 cdp_tab_gc.py --owner gig-pass
    python3 cdp_tab_gc.py --owner gig-pass --keep 2
"""
import argparse
import json
import os
import sys
import urllib.request

import target_ownership


def _cdp_base():
    return os.environ.get("CLOAK_CDP_BASE_URL", "http://localhost:9222").rstrip("/")


def _get(path):
    return json.loads(urllib.request.urlopen(f"{_cdp_base()}{path}", timeout=8).read())


def select_doomed_target_ids(tabs, owner, keep_coconala=1):
    owned_ids = target_ownership.targets_for_owner(owner)
    pages = [
        tab
        for tab in tabs
        if tab.get("type") == "page" and tab.get("id") in owned_ids
    ]
    coconala = [
        tab for tab in pages if "coconala.com" in (tab.get("url") or "")
    ]
    blanks = [
        tab
        for tab in pages
        if (tab.get("url") or "").startswith(("chrome://newtab", "about:blank"))
    ]
    doomed = coconala[keep_coconala:] + blanks
    seen = set()
    return [
        tab["id"]
        for tab in doomed
        if tab.get("id") and not (tab["id"] in seen or seen.add(tab["id"]))
    ]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", default=os.environ.get("CLOAK_BROWSER_OWNER"))
    parser.add_argument("--keep", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        owner = target_ownership.require_owner(args.owner)
    except ValueError as error:
        print(json.dumps({"ok": False, "reason": str(error)}))
        return 2

    try:
        tabs = _get("/json/list")
    except Exception as e:
        print(json.dumps({"ok": False, "reason": f"cdp_unreachable: {e}"}))
        return 0  # never crash the pass — the browser guard handles a dead browser

    stale_pruned = target_ownership.prune_missing_targets(
        tab.get("id") for tab in tabs if tab.get("id")
    )
    owned_ids = target_ownership.targets_for_owner(owner)
    owned_pages = [
        tab
        for tab in tabs
        if tab.get("type") == "page" and tab.get("id") in owned_ids
    ]
    doomed_ids = select_doomed_target_ids(tabs, owner, max(0, args.keep))

    closed = 0
    for target_id in doomed_ids:
        try:
            urllib.request.urlopen(
                f"{_cdp_base()}/json/close/{target_id}", timeout=8
            ).read()
            target_ownership.release_target(target_id, owner)
            closed += 1
        except Exception:
            pass

    print(json.dumps({
        "ok": True,
        "owner": owner,
        "owned_pages_before": len(owned_pages),
        "closed": closed,
        "owned_pages_after": len(owned_pages) - closed,
        "stale_pruned": stale_pruned,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
