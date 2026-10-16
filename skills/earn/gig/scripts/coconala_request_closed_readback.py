#!/usr/bin/env python3
"""Read Coconala request pages for unresolved legacy intents and record 募集終了.

Read-only: it opens https://coconala.com/requests/<id> in the leased registered
browser (run under ``with-browser.sh coconala:kosuke``). Its only click is the
applicant list's もっと見る expander; it never touches an application form. A request
whose official page reads 募集期限 募集終了 can no longer receive an application,
so a fence that only guards against a duplicate application to it is moot. The
recorded applicant roster lets the adapter prove a post-marker attempt left none.
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
_RETAINER_ID = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}")  # ULID retainer (継続) requests


def request_closed(body_text: str) -> bool | None:
    """True for 募集終了, False for an open request, None when the page is unrecognised."""
    text = re.sub(r"\s+", " ", body_text or "")
    match = re.search(r"募集期限 (\S+)", text)
    if match is not None:
        return match.group(1) == "募集終了"
    # Retainer (継続) pages show the state where the apply button would be.
    if re.search(r"(^| )募集終了 ブックマーク( |$)", text):
        return True
    if re.search(r"(^| )応募する ブックマーク( |$)", text):
        return False
    return None


def unresolved_request_ids(intent_root: Path) -> list[str]:
    """Requests of intents not settled without a closed-page readback."""
    applied = adapter._roster_ids(adapter._latest_roster())
    ids = []
    for _path, value in adapter._store_intents(intent_root):
        if value is None or adapter._intent_settled(value, applied, set()):
            continue
        if _REQUEST_ID.fullmatch(value["request_id"]) or _RETAINER_ID.fullmatch(value["request_id"]):
            ids.append(value["request_id"])
    return ids


# Applicant user IDs listed under 応募者一覧 and the 応募人数/契約人数 counters.
_ROSTER_JS = r"""() => {
  const head = [...document.querySelectorAll('*')].find(e => e.children.length === 0
    && (e.innerText || '').trim() === '応募者一覧');
  let section = head || null;
  for (let i = 0; section && i < 6 && !section.querySelector('a[href*="/users/"]'); i++)
    section = section.parentElement;
  const hrefs = section ? [...section.querySelectorAll('a[href*="/users/"]')].map(a => a.getAttribute('href')) : [];
  const ids = [...new Set(hrefs.map(h => (h.match(/\/users\/(\d+)/) || [])[1]).filter(Boolean))];
  const m = document.body.innerText.replace(/\s+/g, ' ').match(/応募人数 (\d+) 契約人数 (\d+)/);
  return {applicant_ids: ids, applicants_count: m ? +m[1] : null, contracted_count: m ? +m[2] : null};
}"""


def read_roster(page) -> dict:
    """Expand 応募者一覧 until every counted applicant is listed (or no expander remains)."""
    roster = page.evaluate(_ROSTER_JS)
    for _ in range(30):
        more = page.get_by_text("もっと見る", exact=True)
        if roster["applicants_count"] is None or len(roster["applicant_ids"]) >= roster["applicants_count"] \
                or more.count() != 1:
            break
        more.first.click()
        page.wait_for_timeout(1_200)
        roster = page.evaluate(_ROSTER_JS)
    return roster


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
                url = (f"https://coconala.com/job_matching/outsources/{rid}" if _RETAINER_ID.fullmatch(rid)
                       else f"https://coconala.com/requests/{rid}")
                response = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                page.wait_for_timeout(1_500)
                status = response.status if response is not None else None
                exact = page.url == url  # a redirect is never evidence about this request
                gone = exact and status == 404
                closed = True if gone else (
                    request_closed(page.inner_text("body")) if exact and status == 200 else None)
                roster = read_roster(page) if exact and status == 200 and closed is False else {}
                requests[rid] = {"closed": closed, "gone": gone, "http_status": status,
                                 "url": url, "final_url": page.url, **roster,
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
