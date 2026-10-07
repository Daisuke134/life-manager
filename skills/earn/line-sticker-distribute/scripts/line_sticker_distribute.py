#!/usr/bin/env python3
"""line_sticker_distribute.py -- the LINE sticker sell loop's one-wake pass.

For each configured dedicated sticker account (config/line-sticker-distribute-
accounts.json), checks whether this wake is at or after that account's next
due cadence_jst slot and whether that slot has not already posted (per-slot
ledger fence). Picks the first due+unposted account, renders one short
vertical video from an on-sale sticker set's clips, composes a caption
(hook via agent_runner, everything else deterministic), and publishes it
through one of two transports selected per account ("transport" field,
default "postiz"):
  - "postiz": the shared skills/video/lm-distribution/postiz_video.py
    client (create -> poll -> PUBLISHED readback, official receipt).
  - "browser_reel": browser_reel_publish.py drives
    ~/.agents/skills/ig-reels-poster directly over CloakBrowser for an
    account whose Postiz channel slot is unavailable (workspace channel
    limit, 2026-10-07) -- readback is the Reel URL post_reel.py confirms on
    the profile.
An empty accounts list is a no-op, not an error -- Dais adds a dedicated
target here once one exists; see AGENTS.md rule 9 and the 2026-10-07 course
correction: NEVER a shared Anicca/Honne/eBook brand integration.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[3]
sys.path.insert(0, str(SCRIPT_DIR))

import browser_reel_publish  # noqa: E402
import caption_compose  # noqa: E402
import due_slot  # noqa: E402
import line_sticker_distribute_ledger as ledger  # noqa: E402
import pick_set  # noqa: E402
import render_video  # noqa: E402

POSTIZ_VIDEO = REPO_ROOT / "skills/video/lm-distribution/postiz_video.py"
DEFAULT_ACCOUNTS_CONFIG = REPO_ROOT / "config/line-sticker-distribute-accounts.json"
DEFAULT_LINE_STICKER_STATE_ROOT = Path("~/.local/state/life-manager/line-sticker").expanduser()
DEFAULT_STATE_ROOT = Path("~/.local/state/life-manager/line-sticker-distribute").expanduser()
CLIP_COUNT = 4


def load_accounts(config_path: Path) -> list[dict]:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"accounts config is unreadable: {exc}") from None
    accounts = config.get("accounts")
    if not isinstance(accounts, list):
        raise RuntimeError("accounts config must have an 'accounts' array")
    timezone_name = config.get("timezone", "Asia/Tokyo")
    for account in accounts:
        if not isinstance(account, dict) or not all(
            isinstance(account.get(field), str) and account[field] for field in ("lane_id", "platform")
        ):
            raise RuntimeError("each account needs lane_id, platform")
        transport = account.setdefault("transport", "postiz")
        if transport == "postiz":
            if not isinstance(account.get("integration_id"), str) or not account["integration_id"]:
                raise RuntimeError(f"account {account['lane_id']} (postiz) needs integration_id")
        elif transport == "browser_reel":
            if not all(
                isinstance(account.get(field), str) and account[field]
                for field in ("handle", "browser_identity")
            ):
                raise RuntimeError(f"account {account['lane_id']} (browser_reel) needs handle, browser_identity")
        else:
            raise RuntimeError(f"account {account['lane_id']} has an unknown transport: {transport}")
        if not isinstance(account.get("cadence_jst"), list) or not account["cadence_jst"]:
            raise RuntimeError(f"account {account.get('lane_id')} needs a non-empty cadence_jst")
        account.setdefault("timezone", timezone_name)
        account.setdefault("link_in_caption", True)
    return accounts


def find_due_account(accounts: list[dict], ledger_path: Path, now: datetime) -> tuple[dict, str, str] | None:
    """First (account, slot_at, key) whose slot is due now and not yet posted."""
    for account in accounts:
        slot_at = due_slot.due_slot_iso(now, account["timezone"], account["cadence_jst"])
        if slot_at is None:
            continue
        key = f"{account['lane_id']}-{slot_at}"
        if ledger.is_published(ledger_path, key):
            continue
        return account, slot_at, key
    return None


def run_pass(
    *,
    accounts_config: Path,
    line_sticker_state_root: Path,
    state_root: Path,
    now: datetime,
    dry_run: bool,
    caption_hook_override: str | None,
) -> dict:
    accounts = load_accounts(accounts_config)
    if not accounts:
        return {"state": "no_targets_configured"}

    ledger_path = state_root / "ledger.json"
    due = find_due_account(accounts, ledger_path, now)
    if due is None:
        return {"state": "no_due_slot"}
    account, slot_at, key = due

    chosen = pick_set.choose_set(
        pick_set.load_on_sale_sets(line_sticker_state_root), seed_key=key,
    )
    if chosen is None:
        entry = {"status": "blocked", "reason": "no_sets_on_sale", "slot_at": slot_at}
        ledger.record(ledger_path, key, entry)
        return {"state": "blocked", "reason": "no_sets_on_sale", "account": account["lane_id"]}
    clip_order = pick_set.choose_clip_order(chosen["clip_ids"], key, CLIP_COUNT)

    run_dir = state_root / "runs" / key.replace(":", "-")
    run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    video_path = run_dir / "video.mp4"
    render_video.render(
        [Path(chosen["clips_dir"]) / f"{clip_id}.mp4" for clip_id in clip_order],
        chosen["title_ja"], chosen["store_url"], video_path,
    )

    seed_index = pick_set.deterministic_index(key, 6)
    caption_result = caption_compose.build_caption(
        hook=caption_hook_override or caption_compose.call_agent_runner(
            title_ja=chosen["title_ja"],
            use_cases=caption_compose.use_cases_for(clip_order),
            task_label=f"line-sticker-distribute-{account['lane_id']}",
            state_root=state_root,
        ),
        title_ja=chosen["title_ja"],
        use_cases=caption_compose.use_cases_for(clip_order),
        store_url=chosen["store_url"],
        hashtags=caption_compose.pick_hashtags(chosen["character_name"], seed_index),
        include_link=account["link_in_caption"],
    )
    caption_path = run_dir / "caption.txt"
    caption_path.write_text(caption_result, encoding="utf-8")

    if dry_run:
        entry = {
            "status": "dry_run", "slot_at": slot_at, "set_id": chosen["set_id"],
            "clip_order": clip_order, "caption": caption_result,
            "video_size_bytes": video_path.stat().st_size,
        }
        ledger.record(ledger_path, key, entry)
        return {
            "state": "dry_run", "account": account["lane_id"], "slot_at": slot_at,
            "set_id": chosen["set_id"], "store_url": chosen["store_url"],
            "clip_order": clip_order, "caption": caption_result,
            "video_path": str(video_path), "video_size_bytes": video_path.stat().st_size,
        }

    title = chosen["title_ja"][:100]
    transport = account["transport"]
    if transport == "postiz":
        api_key = os.environ.get("POSTIZ_API_KEY") or os.environ.get("LM_POSTIZ_API_KEY", "")
        if not api_key:
            raise RuntimeError("POSTIZ_API_KEY is unavailable")
        done = subprocess.run(
            [sys.executable, str(POSTIZ_VIDEO), "--video", str(video_path),
             "--caption-file", str(caption_path), "--integration", account["integration_id"],
             "--title", title, "--platform", account["platform"]],
            env={**os.environ, "POSTIZ_API_KEY": api_key},
            capture_output=True, text=True, timeout=400,
        )
        try:
            receipt = json.loads(done.stdout.strip().splitlines()[-1]) if done.stdout.strip() else {}
        except (ValueError, IndexError):
            receipt = {}
        error_detail = receipt.get("error") or done.stderr[-500:]
        published = (
            done.returncode == 0 and receipt.get("reconciled") is True and receipt.get("state") == "PUBLISHED"
        )
        post_url = receipt.get("post_url")
    elif transport == "browser_reel":
        receipt = browser_reel_publish.publish(
            video=video_path, caption_file=caption_path, handle=account["handle"],
            browser_identity=account["browser_identity"], live=True,
        )
        error_detail = receipt.get("error")
        published = receipt.get("outcome") == "published" and bool(receipt.get("post_url"))
        post_url = receipt.get("post_url")
    else:
        raise RuntimeError(f"unknown transport: {transport}")
    video_path.unlink(missing_ok=True)  # disk is near-full; keep only the caption + receipt

    if published:
        ledger.record(ledger_path, key, {
            "status": "published", "slot_at": slot_at, "set_id": chosen["set_id"],
            "post_id": receipt.get("post_id"), "post_url": post_url,
        })
        return {"state": "published", "account": account["lane_id"], **receipt}

    ledger.record(ledger_path, key, {
        "status": "failed", "slot_at": slot_at, "set_id": chosen["set_id"], "reason": error_detail,
    })
    raise RuntimeError(f"{transport} publish did not reconcile: {receipt}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts-config", default=str(DEFAULT_ACCOUNTS_CONFIG))
    parser.add_argument("--line-sticker-state-root", default=str(DEFAULT_LINE_STICKER_STATE_ROOT))
    parser.add_argument("--state-root", default=str(DEFAULT_STATE_ROOT))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--caption-hook", default=None, help="skip agent_runner (tests/evidence)")
    parser.add_argument("--now", default=None, help="ISO 8601 UTC instant override (tests)")
    args = parser.parse_args(argv)

    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
    result = run_pass(
        accounts_config=Path(args.accounts_config).expanduser(),
        line_sticker_state_root=Path(args.line_sticker_state_root).expanduser(),
        state_root=Path(args.state_root).expanduser(),
        now=now,
        dry_run=args.dry_run,
        caption_hook_override=args.caption_hook,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
