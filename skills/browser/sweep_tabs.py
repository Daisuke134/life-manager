#!/usr/bin/env python3
"""Close leaked tabs when a browser lease is released (stdlib only, best-effort).

Owner loops open pages and never close them: the lancers owner grew one tab per run
(6 tabs, 1.5 GB in 6 h on 2026-10-18) and 17 always-on browsers pushed swap to 8-10 GB,
which deferred revenue loops. browser-guard.sh release calls this while the releasing
holder still owns the lease. Small tab counts are left alone; the first http(s) tab
(usually the logged-in page) always survives.
Usage: sweep_tabs.py PORT
"""
import json
import sys
import urllib.request

MAX_TABS = 3


def tabs_to_close(targets, max_tabs=MAX_TABS):
    pages = [t for t in targets if t.get("type") == "page"]
    if len(pages) <= max_tabs:
        return []
    keep = next((p for p in pages if str(p.get("url", "")).startswith("http")), pages[0])
    return [p["id"] for p in pages if p is not keep]


def main(port):
    base = f"http://127.0.0.1:{int(port)}/json"
    targets = json.load(urllib.request.urlopen(f"{base}/list", timeout=3))
    closed = tabs_to_close(targets)
    for target_id in closed:
        urllib.request.urlopen(f"{base}/close/{target_id}", timeout=3).read()
    print(json.dumps({"closed": len(closed)}))


if __name__ == "__main__":
    try:
        main(sys.argv[1])
    except Exception as error:  # noqa: BLE001 -- never block a lease release
        print(json.dumps({"closed": 0, "error": type(error).__name__}))
