#!/usr/bin/env python3
"""Read Coconala request pages for unresolved legacy intents and record 募集終了.

Read-only: it opens https://coconala.com/requests/<id> in the leased registered
browser (run under ``with-browser.sh coconala:kosuke``) and never clicks. A request
whose official page reads 募集期限 募集終了 can no longer receive an application,
so a fence that only guards against a duplicate application to it is moot.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import coconala_application_effect_reconcile as adapter  # noqa: E402

_REQUEST_ID = re.compile(r"[0-9]{4,10}")


def request_closed(body_text: str) -> bool | None:
    """True for 募集終了, False for an open request, None when the page is unrecognised."""
    text = re.sub(r"\s+", " ", body_text or "")
    match = re.search(r"募集期限 (\S+)", text)
    if match is None:
        return None
    return match.group(1) == "募集終了"


def unresolved_request_ids(intent_root: Path) -> list[str]:
    applied = adapter._roster_ids(adapter._latest_roster())
    ids = []
    for path in sorted(intent_root.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rid = str(value.get("request_id") or path.stem)
        if (value.get("state") in adapter.SETTLED_STATES or value.get("effect_phase") == "pre_effect"
                or rid in applied or not _REQUEST_ID.fullmatch(rid)):
            continue
        ids.append(rid)
    return ids


def _atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intent-root", type=Path, default=Path.home() / "gig" / "application-intents")
    parser.add_argument("--result", type=Path, default=adapter.CLOSED_READBACK)
    args = parser.parse_args(argv)
    endpoint = os.environ.get("CLOAK_CDP_BASE_URL")
    if not endpoint:
        print(json.dumps({"ok": False, "reason": "browser_lease_required"}))
        return 2
    from playwright.sync_api import sync_playwright

    requests: dict[str, dict] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(endpoint)
        page = browser.contexts[0].new_page()
        try:
            for rid in unresolved_request_ids(args.intent_root):
                url = f"https://coconala.com/requests/{rid}"
                response = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                page.wait_for_timeout(1_500)
                status = response.status if response is not None else None
                gone = status == 404 and page.url == url  # the request itself no longer exists
                closed = True if gone else (request_closed(page.inner_text("body")) if status == 200 else None)
                requests[rid] = {"closed": closed, "gone": gone, "http_status": status,
                                 "url": url, "final_url": page.url,
                                 "observed_at": datetime.now(timezone.utc).isoformat()}
        finally:
            page.close()
    _atomic_write(args.result, {"source": "code_owned_cdp_readback", "requests": requests})
    summary = {"ok": True, "checked": len(requests),
               "closed": sum(row["closed"] is True for row in requests.values()),
               "open": sum(row["closed"] is False for row in requests.values()),
               "unrecognised": sum(row["closed"] is None for row in requests.values())}
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
