#!/usr/bin/env python3
"""Close one line-sticker-distribute effect_unknown admission fence.

Same decision shape as capafy_ig_fence_reconcile.py (one no-effect proof per occurrence, never a
guess). This loop's only external effect is a Reel on the sticker account, posted by the browser
(ig-reels-poster over CloakBrowser), and every published Reel's URL is written to ledger.json. The
official readback is therefore the account's own Reels listing, read through the same browser
identity the poster uses:
  - The listing is complete (as many Reel codes as the profile's post count) and every Reel on it
    is already in the ledger, and enough time has passed: the fenced run posted nothing, so close
    as no-effect, citing the listing as the receipt.
  - Any Reel missing from the ledger may be this run's post: stays fenced (closing would let the
    slot post again).
  - Any readback failure, an incomplete listing, or too recent: stays fenced.

Usage:
    python3 distribute_fence_reconcile.py --occurrence line-sticker-distribute:<run_id> [--resolve]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OWNER_ID = "line-sticker-distribute"
# caption (<= 90 s) + render + browser upload/share readback; the poster gives up well inside this.
MAX_RUN_SECONDS = 3600
NO_EFFECT_MIN_AGE_SECONDS = MAX_RUN_SECONDS + 900
STATE_ROOT = Path.home() / ".local/state/life-manager/line-sticker-distribute"
ACCOUNTS = REPO_ROOT / "config/line-sticker-distribute-accounts.json"
GUARD = REPO_ROOT / "skills/browser/browser-guard.sh"
CODE_RE = re.compile(r"/reel/([A-Za-z0-9_-]+)")
POST_COUNT_RE = re.compile(r"投稿\s*([\d,]+)\s*件|([\d,]+)\s*件の投稿|([\d,]+)\s*posts")


def fenced_row(owner_id: str, occurrence_id: str) -> tuple[str, dt.datetime]:
    """Read (state, queued_at) of the fenced row without mutating the ledger."""
    from runtime.host import resource_admission

    database = resource_admission.state_root() / "admission-v2.sqlite3"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        row = connection.execute(
            """SELECT state, queued_at FROM occurrences
                 WHERE owner_id=? AND occurrence_id=? AND effect_unknown=1""",
            (owner_id, occurrence_id),
        ).fetchone()
    if row is None or row[1] is None:
        raise ValueError("occurrence is not an effect_unknown row")
    return str(row[0]), dt.datetime.fromtimestamp(float(row[1]), dt.timezone.utc)


def ledger_codes(rows: dict) -> set[str]:
    return {m.group(1) for row in rows.values() if isinstance(row, dict)
            for m in [CODE_RE.search(str(row.get("post_url") or ""))] if m}


def read_reels(handle: str, identity: str, known: set[str] = frozenset()) -> dict[str, Any]:
    acquired = subprocess.run(["bash", str(GUARD), "acquire", identity], capture_output=True, text=True)
    if acquired.returncode != 0:
        return {"ok": False, "reason": "browser_unavailable"}
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(acquired.stdout.strip().splitlines()[-1])
            page = browser.contexts[0].new_page()
            try:
                page.goto(f"https://www.instagram.com/{handle}/", timeout=60000)
                page.wait_for_timeout(5000)
                match = POST_COUNT_RE.search(page.inner_text("body"))
                page.goto(f"https://www.instagram.com/{handle}/reels/", timeout=60000)
                page.wait_for_timeout(5000)
                codes = set(re.findall(rf"/{re.escape(handle)}/reel/([A-Za-z0-9_-]+)", page.content()))
                taken_at = {}
                for code in sorted(codes - set(known)):  # date only the Reels the ledger cannot explain
                    page.goto(f"https://www.instagram.com/{handle}/reel/{code}/", timeout=60000)
                    page.wait_for_timeout(3000)
                    stamp = page.locator("time[datetime]").first
                    taken_at[code] = stamp.get_attribute("datetime") if stamp.count() else None
            finally:
                page.close()
    except Exception as exc:  # noqa: BLE001 -- any failure is inconclusive
        return {"ok": False, "reason": f"instagram_readback_failed:{type(exc).__name__}"}
    finally:
        subprocess.run(["bash", str(GUARD), "release", identity], capture_output=True)
    if not match:
        return {"ok": False, "reason": "post_count_unreadable"}
    count = int(next(g for g in match.groups() if g).replace(",", ""))
    return {"ok": True, "codes": codes, "post_count": count, "taken_at": taken_at}


def build_proof(occurrence_id: str, queued_at: dt.datetime, *, now: dt.datetime,
                reels: dict[str, Any], ledger_codes: set[str]) -> dict[str, Any]:
    proof: dict[str, Any] = {"owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                             "verified": False, "queued_at": queued_at.isoformat()}
    if not reels.get("ok"):
        proof["reason"] = reels.get("reason")
        return proof
    def before_run(code: str) -> bool:
        stamp = (reels.get("taken_at") or {}).get(code)
        try:
            return dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00")) < queued_at
        except ValueError:
            return False  # undated: cannot rule out this run

    # A Reel older than the run cannot be its effect (e.g. posts made before the ledger existed).
    unledgered = sorted(c for c in reels["codes"] - ledger_codes if not before_run(c))
    if unledgered:
        proof["reason"] = "unledgered_reel:" + ",".join(unledgered)
        return proof
    if len(reels["codes"]) < reels["post_count"]:
        proof["reason"] = f"incomplete_listing:{len(reels['codes'])}<{reels['post_count']}"
        return proof
    age = (now - queued_at).total_seconds()
    if age <= NO_EFFECT_MIN_AGE_SECONDS:
        proof["reason"] = f"too_recent:{int(age)}s<={NO_EFFECT_MIN_AGE_SECONDS}s"
        return proof
    proof.update(verified=True, effected=False,
                 provider_receipt_id=f"instagram-reels-listing-all-ledgered:{len(reels['codes'])}:{now.isoformat(timespec='seconds')}",
                 proof_kind="official_instagram_reels_listing_vs_ledger",
                 checked_at=now.isoformat(timespec="seconds"))
    return proof


def reconcile(occurrence_id: str, *, resolve: bool = False) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    state, queued_at = fenced_row(OWNER_ID, occurrence_id)
    account = next(a for a in json.loads(ACCOUNTS.read_text())["accounts"] if a.get("transport") == "browser_reel")
    ledger_path = STATE_ROOT / "ledger.json"
    rows = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    proof = build_proof(occurrence_id, queued_at, now=now,
                        reels=read_reels(account["handle"], account["browser_identity"], ledger_codes(rows)),
                        ledger_codes=ledger_codes(rows))
    result = {**proof, "admission_state": state}
    if not proof.get("verified") or not resolve:
        return result
    from runtime.host.resource_admission import resolve_unknown_occurrence

    result["closed"] = resolve_unknown_occurrence(OWNER_ID, occurrence_id,
                                                  official_readback=lambda: proof, expected_state=state)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = reconcile(args.occurrence, resolve=args.resolve)
    except (OSError, ValueError, sqlite3.Error, StopIteration) as exc:
        print(json.dumps({"owner_id": OWNER_ID, "occurrence_id": args.occurrence,
                          "verified": False, "error": f"{type(exc).__name__}:{exc}"}))
        print("LINE_STICKER_DISTRIBUTE_FENCE_RECONCILE=FAIL", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, default=str, ensure_ascii=False))
    if not result.get("verified"):
        print("LINE_STICKER_DISTRIBUTE_FENCE_RECONCILE=HELD")
        return 1
    if not args.resolve:
        print("LINE_STICKER_DISTRIBUTE_FENCE_RECONCILE=PROOF_READY")
        return 0
    if not result.get("closed"):
        print("LINE_STICKER_DISTRIBUTE_FENCE_RECONCILE=FAIL reason=admission_refused_close", file=sys.stderr)
        return 1
    print("LINE_STICKER_DISTRIBUTE_FENCE_RECONCILE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
