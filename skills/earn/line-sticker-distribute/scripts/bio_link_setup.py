#!/usr/bin/env python3
"""bio_link_setup.py -- add the LINE STORE creator/author page URL to the IG bio, ONCE.

SSOT L17 gap #4: top LINE sticker creators' accounts carry a durable link in the account
bio (store/author page or an Instagram handle), not a link on every post -- see
docs/superpowers/specs/2026-08-28-line-sticker-loop-design.md "Social formats copied from
top creators". Dais 2026-10-07: a brand-new account carries no outbound link for its first
days; from account.bio_link_from onward (config-driven, not hardcoded) it is allowed. Reuses
~/.claude/skills/ig-account-create/scripts/setup_profile.py (--website only, already proven
2026-06-29) rather than re-implementing the DOM flow -- same "copy a sibling loop" rule as
browser_reel_publish.py reusing ig-reels-poster.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[3]
sys.path.insert(0, str(SCRIPT_DIR))

import browser_reel_publish as reel  # noqa: E402
import date_gate  # noqa: E402
import line_sticker_distribute as distribute  # noqa: E402
import line_sticker_distribute_ledger as ledger  # noqa: E402

SETUP_PROFILE_PY = Path("~/.claude/skills/ig-account-create/scripts/setup_profile.py").expanduser()
PYB = "/opt/homebrew/bin/python3"
DEFAULT_STATE_ROOT = Path("~/.local/state/life-manager/line-sticker-distribute").expanduser()


def bio_link_due(account: dict, now: datetime, ledger_path: Path) -> tuple[bool, str | None]:
    bio_link_from = account.get("bio_link_from")
    author_url = account.get("author_url")
    if not isinstance(bio_link_from, str) or not bio_link_from or not isinstance(author_url, str) or not author_url:
        return False, None
    if not date_gate.is_on_or_after(now, account["timezone"], bio_link_from):
        return False, None
    key = f"{account['lane_id']}-bio-link"
    if ledger.already_attempted(ledger_path, key):
        return False, key
    return True, key


def run_bio_link(account: dict, *, state_root: Path, now: datetime, dry_run: bool) -> dict:
    ledger_path = state_root / "engagement-ledger.json"  # one small shared one-off/day ledger
    due, key = bio_link_due(account, now, ledger_path)
    if not due:
        return {"state": "not_due" if key is None else "already_set"}

    author_url = account["author_url"]
    handle = account["handle"]
    if dry_run:
        return {"state": "dry_run", "account": account["lane_id"], "author_url": author_url}

    creds_path = Path(f"~/.cloak/ig-{handle}.json").expanduser()
    if not creds_path.is_file():
        raise RuntimeError(f"no stored IG credentials for {handle} at {creds_path}")
    creds = json.loads(creds_path.read_text(encoding="utf-8"))

    endpoint = reel._lease(account["browser_identity"])
    match = re.fullmatch(r"https?://([^:/]+):(\d+)", endpoint)
    if not match:
        raise RuntimeError(f"unexpected browser lease endpoint: {endpoint}")
    cdp_host, cdp_port = match.group(1), match.group(2)
    tid = None
    try:
        tid = reel._cdp(["new", "https://www.instagram.com/"], cdp_host=cdp_host, cdp_port=cdp_port)
        reel._cdp(["focus", tid], cdp_host=cdp_host, cdp_port=cdp_port)
        reel._ensure_logged_in(tid, cdp_host=cdp_host, cdp_port=cdp_port, creds=creds)
        env = {**os.environ, "CDP_HOST": cdp_host, "CDP_PORT": cdp_port}
        done = subprocess.run(
            [PYB, str(SETUP_PROFILE_PY), "--tid", tid, "--website", author_url, "--username", handle],
            capture_output=True, text=True, timeout=60, env=env,
        )
        output = done.stdout.strip()
        ok = done.returncode == 0 and "website set (POST-WARMUP)" in output
    finally:
        if tid:
            reel._cdp(["close", tid], cdp_host=cdp_host, cdp_port=cdp_port)
        reel._release(account["browser_identity"])

    ledger.record(ledger_path, key, {
        "status": "ok" if ok else "error", "attempted_at": now.isoformat(), "author_url": author_url,
    })
    if not ok:
        raise RuntimeError(f"bio_link_setup_failed: {output[-500:]}")
    return {"state": "set", "account": account["lane_id"], "author_url": author_url}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts-config", default=str(distribute.DEFAULT_ACCOUNTS_CONFIG))
    parser.add_argument("--state-root", default=str(DEFAULT_STATE_ROOT))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--now", default=None)
    args = parser.parse_args(argv)

    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
    accounts = distribute.load_accounts(Path(args.accounts_config).expanduser())
    state_root = Path(args.state_root).expanduser()
    results = []
    for account in accounts:
        if account.get("transport") != "browser_reel":
            continue
        results.append(run_bio_link(account, state_root=state_root, now=now, dry_run=args.dry_run))
    print(json.dumps({"results": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
