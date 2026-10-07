#!/usr/bin/env python3
"""engagement_daily.py -- day-3+ capped IG follow/like engagement (SSOT L17 gap #2).

Top LINE sticker creators' accounts engage with their niche, not only broadcast (see
docs/superpowers/specs/2026-08-28-line-sticker-loop-design.md "Social formats copied from
top creators"). ~/.agents/skills/ig-account-warmer already defines this exact layer for a
fresh account: PASSIVE warmup runs every day via code, but ENGAGEMENT (light likes/follows)
is done AGENTICALLY starting day 3+, because judgment ("is this post actually in my niche",
"does this look like a bot account to follow") belongs to the model, not a hardcoded
selector/keyword list (skills/building-agents). This script is the deterministic bookkeeping
half only: the day-3+ gate, the daily idempotency fence, the hard caps, and leasing the
already-authenticated browser -- then it hands the live CDP endpoint to one bounded
browser-lane-agent call (same mechanism skills/earn/gig/scripts/market_form_operator.py uses)
with an explicit cap and an explicit ban-signal stop instruction, and records whatever it
reports back.

One attempt per account per local calendar day, regardless of outcome (mirrors warm.py's own
"one session/day" idempotency) -- see line_sticker_distribute_ledger.already_attempted.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[3]
sys.path.insert(0, str(SCRIPT_DIR))

import browser_reel_publish as reel  # noqa: E402
import date_gate  # noqa: E402
import line_sticker_distribute as distribute  # noqa: E402
import line_sticker_distribute_ledger as ledger  # noqa: E402

AGENT_RUNNER = REPO_ROOT / "runtime/agent-runner/agent_runner.py"
SCHEMA = Path(__file__).resolve().parent.parent / "schemas" / "engagement_result.schema.json"
DEFAULT_STATE_ROOT = Path("~/.local/state/life-manager/line-sticker-distribute").expanduser()
# ig-account-warmer research (shadowphone.io, cited in its SKILL.md): aggressive activity in
# the first 72h risks an 80%+ ban rate. Engagement starts day 3 (i.e. the 3rd local calendar
# day since the account's created_at), same as warm.py's own engagement layer.
WARMUP_MIN_DAYS = 3
DEFAULT_LIKES_CAP = 15
DEFAULT_FOLLOWS_CAP = 5
DEFAULT_NICHE_TERMS = ["LINEスタンプ", "イラスト", "かわいい"]


def engagement_due_today(account: dict, now: datetime, ledger_path: Path) -> tuple[bool, str | None]:
    created_at = account.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        return False, None
    if date_gate.days_since(now, account["timezone"], created_at) < WARMUP_MIN_DAYS:
        return False, None
    today = date_gate.local_date(now, account["timezone"]).isoformat()
    key = f"{account['lane_id']}-{today}"
    if ledger.already_attempted(ledger_path, key):
        return False, key
    return True, key


def engagement_prompt(*, handle: str, cdp_base: str, likes_cap: int, follows_cap: int, niche_terms: list[str]) -> str:
    terms = "、".join(niche_terms)
    return f"""Instagramアカウント @{handle} で、今の認証済みブラウザ（EXACT_CDP_ENDPOINT={cdp_base}）を使い、
このニッチ（{terms}）に実在する投稿/アカウントへの軽いエンゲージメントだけを行う。
上限は絶対に超えない: いいね最大{likes_cap}件、フォロー最大{follows_cap}件（0件でもよい）。
やり方: ハッシュタグ検索または発見タブで{terms}に関する実在の投稿を探し、実際にニッチに合う投稿にだけ
いいねし、実際に関連するアカウントにだけフォローする。ハードコードされたセレクタや固定キーワードのクリックではなく、
スクリーンショット相当の現在のページ内容を見て、その都度どの投稿/アカウントが妥当か自分で判断すること。
停止条件（即座に全処理を中断しstatus=blockedで返す）: 「操作がブロック」「Action Blocked」「challenge」
「本人確認」「アカウントの不審な動き」など、ig-account-warmer skillが定義するban-signalに相当する文言が
画面に表示された場合。スパム的な連続操作、課金、購入、フォロー解除、他人への返信投稿、アカウント設定変更は行わない。
EXACT_CDP_ENDPOINT以外のCDPエンドポイントは使わない。既存の認証済みデフォルトコンテキストのみ使い、新しい
プロフィール/ログイン/復元は行わない。
最後に、実際に行った「いいね」件数と「フォロー」件数、ban-signalを見たかどうかを正確に数えて返すこと
（多く見積もらない）。"""


def run_engagement(
    account: dict, *, state_root: Path, now: datetime, dry_run: bool,
    runner: Path = AGENT_RUNNER, schema: Path = SCHEMA,
) -> dict:
    ledger_path = state_root / "engagement-ledger.json"
    due, key = engagement_due_today(account, now, ledger_path)
    if not due:
        return {"state": "not_due" if key is None else "already_attempted_today"}

    likes_cap = int(account.get("engagement_daily_likes_cap", DEFAULT_LIKES_CAP))
    follows_cap = int(account.get("engagement_daily_follows_cap", DEFAULT_FOLLOWS_CAP))
    niche_terms = account.get("engagement_niche_terms") or DEFAULT_NICHE_TERMS
    handle = account["handle"]

    if dry_run:
        return {
            "state": "dry_run", "account": account["lane_id"], "handle": handle,
            "likes_cap": likes_cap, "follows_cap": follows_cap, "niche_terms": niche_terms,
        }

    creds_path = Path(f"~/.cloak/ig-{handle}.json").expanduser()
    if not creds_path.is_file():
        raise RuntimeError(f"no stored IG credentials for {handle} at {creds_path}")
    creds = json.loads(creds_path.read_text(encoding="utf-8"))

    endpoint = reel._lease(account["browser_identity"])
    import re
    match = re.fullmatch(r"https?://([^:/]+):(\d+)", endpoint)
    if not match:
        raise RuntimeError(f"unexpected browser lease endpoint: {endpoint}")
    cdp_host, cdp_port = match.group(1), match.group(2)
    cdp_base = f"http://{cdp_host}:{cdp_port}"
    tid = None
    try:
        tid = reel._cdp(["new", "https://www.instagram.com/"], cdp_host=cdp_host, cdp_port=cdp_port)
        reel._cdp(["focus", tid], cdp_host=cdp_host, cdp_port=cdp_port)
        reel._ensure_logged_in(tid, cdp_host=cdp_host, cdp_port=cdp_port, creds=creds)

        prompt = engagement_prompt(
            handle=handle, cdp_base=cdp_base, likes_cap=likes_cap, follows_cap=follows_cap,
            niche_terms=niche_terms,
        )
        evidence_root = state_root / "engagement-evidence"
        evidence_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        evidence = evidence_root / f"{time.time_ns()}-{account['lane_id']}"
        environment = os.environ.copy()
        environment.update({"BU_CDP_URL": cdp_base, "BU_NAME": f"line-sticker-engagement-{account['lane_id']}"})
        completed = subprocess.run(
            [sys.executable, str(runner), "--task-class", "browser-lane-agent", "--prompt-stdin",
             "--schema", str(schema), "--evidence-dir", str(evidence),
             "--task-label", f"line-sticker-engagement-{account['lane_id']}", "--loop",
             f"line-sticker-distribute-{account['lane_id']}", "--workdir", str(Path.home()),
             "--timeout-seconds", "600"],
            input=prompt, text=True, capture_output=True, timeout=630, env=environment, check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("line_sticker_engagement_failed")
        summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
        result_path = Path(str(summary.get("result_path") or "")).resolve()
        result_path.relative_to(evidence.resolve())
        result = json.loads(result_path.read_text(encoding="utf-8"))
    finally:
        if tid:
            reel._cdp(["close", tid], cdp_host=cdp_host, cdp_port=cdp_port)
        reel._release(account["browser_identity"])

    ledger.record(ledger_path, key, {
        "status": result.get("status"), "attempted_at": now.isoformat(),
        "likes_done": result.get("likes_done"), "follows_done": result.get("follows_done"),
        "ban_signal_seen": result.get("ban_signal_seen"),
    })
    return {"state": "attempted", "account": account["lane_id"], **result}


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
            continue  # engagement needs a dedicated authenticated browser identity, like posting
        results.append(run_engagement(account, state_root=state_root, now=now, dry_run=args.dry_run))
    print(json.dumps({"results": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
