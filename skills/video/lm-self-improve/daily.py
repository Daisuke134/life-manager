#!/usr/bin/env python3
"""One honest daily measurement/decision row for the Life Manager marketing loop."""

from __future__ import annotations

import argparse
from datetime import date as Date, timedelta
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Mapping
from zoneinfo import ZoneInfo
from datetime import datetime


class SelfImproveError(RuntimeError):
    pass


def _lm_video_state_root() -> Path:
    """Portable lm-video state root: LM_DATA_DIR when set (absolute only,
    mirroring resolveDataRoot in apps/life-manager/lib/runtime-paths.js and
    default_video_root in skills/video/daily-lm-video/generate.py), else
    <home>/.local/state/life-manager."""
    override = os.environ.get("LM_DATA_DIR", "").strip()
    if override:
        if not Path(override).is_absolute():
            raise SystemExit("LM_DATA_DIR must be an absolute path")
        data_root = Path(override)
    else:
        data_root = Path.home() / ".local/state/life-manager"
    return data_root / "state" / "lm-video"


def _read_jsonl(path: Path) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    rows = []
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SelfImproveError(f"invalid JSONL: {path.name}") from exc
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _valid_url(platform: str, value) -> bool:
    if not isinstance(value, str):
        return False
    if platform == "instagram":
        return bool(re.fullmatch(r"https://www\.instagram\.com/(?:reel|p)/[A-Za-z0-9_-]+/?", value))
    if platform == "tiktok":
        return bool(re.fullmatch(r"https://www\.tiktok\.com/@[^/]+/video/[0-9]+/?", value))
    return False


def select_latest_pair(rows: list[dict]) -> list[dict]:
    contracts: dict[tuple, dict[str, dict]] = {}
    order: list[tuple] = []
    for row in rows:
        platform = row.get("platform")
        key = (row.get("creative_id"), row.get("video_sha256"), row.get("caption_sha256"))
        if (
            platform in {"instagram", "tiktok"}
            and row.get("status") == "published"
            and all(isinstance(value, str) and value for value in key)
            and _valid_url(platform, row.get("public_url"))
        ):
            if key not in contracts:
                contracts[key] = {}
                order.append(key)
            contracts[key][platform] = row
    for key in reversed(order):
        if set(contracts[key]) == {"instagram", "tiktok"}:
            return [contracts[key]["instagram"], contracts[key]["tiktok"]]
    raise SelfImproveError("no exact Instagram/TikTok distribution pair")


def select_latest_contract(rows: list[dict], platforms: tuple[str, ...]) -> list[dict]:
    """Select the newest exact distribution contract for the requested scope."""
    if platforms == ("instagram", "tiktok"):
        return select_latest_pair(rows)
    if platforms != ("tiktok",):
        raise SelfImproveError("unsupported distribution scope")
    for row in reversed(rows):
        if (
            row.get("platform") == "tiktok"
            and row.get("status") == "published"
            and isinstance(row.get("creative_id"), str)
            and isinstance(row.get("video_sha256"), str)
            and isinstance(row.get("caption_sha256"), str)
            and _valid_url("tiktok", row.get("public_url"))
        ):
            return [row]
    raise SelfImproveError("no exact TikTok distribution contract")


def _metric(platform: str, url: str, value: Mapping) -> dict:
    views = value.get("views")
    if isinstance(views, bool) or not isinstance(views, int) or views < 0:
        raise SelfImproveError(f"{platform} views must be a real nonnegative integer")
    result = {
        "platform": platform,
        "url": url,
        "views": views,
        "likes": value.get("likes") if isinstance(value.get("likes"), int) else None,
        "comments": value.get("comments") if isinstance(value.get("comments"), int) else None,
        "watch_time": None,
        "completion_rate": None,
        "clicks": None,
        "signups": None,
        "source_limitation": (
            "public/provider readback exposes views/likes/comments; watch-time, completion, "
            "click, and signup attribution are unavailable and remain null"
        ),
    }
    return result


def _bank(path: Path) -> list[dict]:
    rows = _read_jsonl(path)
    required = {"id", "pain", "moment", "punchline"}
    if not rows or any(not required.issubset(row) for row in rows):
        raise SelfImproveError("creative bank contract is invalid")
    return rows


def _next_creative(bank: list[dict], creative_id: str) -> dict:
    indexes = [index for index, row in enumerate(bank) if row.get("id") == creative_id]
    if len(indexes) != 1:
        raise SelfImproveError("creative id must match one bank row")
    return bank[(indexes[0] + 1) % len(bank)]


def unavailable_metric_result(
    *, date: str, distribution_rows: list[dict], bank_path: Path,
    platforms: tuple[str, ...], reason: str,
) -> dict:
    """Return an explicit pending measurement without claiming growth."""
    Date.fromisoformat(date)
    contract = select_latest_contract(distribution_rows, platforms)
    bank = _bank(bank_path)
    next_row = _next_creative(bank, contract[0]["creative_id"])
    return {
        "date": date,
        "status": "unavailable",
        "day_index": 0,
        "streak_dates": [],
        "metric_complete": False,
        "creative_id": contract[0]["creative_id"],
        "video_sha256": contract[0]["video_sha256"],
        "caption_sha256": contract[0]["caption_sha256"],
        "platforms": [],
        "unavailable_metrics": ["views", "likes", "comments", "clicks", "completion_rate", "signups", "watch_time"],
        "next_creative_id": next_row["id"],
        "next_change_reason": f"{reason}; no growth claim; keep the published contract and retry readback later",
    }


def _consecutive_dates(rows: list[dict], current: str) -> list[str]:
    current_date = Date.fromisoformat(current)
    prior = {row.get("date") for row in rows if row.get("metric_complete") is True}
    streak = [current]
    cursor = current_date - timedelta(days=1)
    while cursor.isoformat() in prior:
        streak.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    return list(reversed(streak))


def record_day(
    *,
    date: str,
    distribution_rows: list[dict],
    metrics: Mapping[str, Mapping],
    bank_path: Path,
    ledger_path: Path,
    platforms: tuple[str, ...] = ("instagram", "tiktok"),
) -> dict:
    Date.fromisoformat(date)
    existing = _read_jsonl(ledger_path)
    same_day = [row for row in existing if row.get("date") == date]
    if same_day:
        return same_day[-1]

    pair = select_latest_contract(distribution_rows, platforms)
    contract = pair[0]
    if any(
        row.get(field) != contract.get(field)
        for row in pair[1:]
        for field in ("creative_id", "video_sha256", "caption_sha256")
    ):
        raise SelfImproveError("platform distribution hashes do not match")
    by_platform = {row["platform"]: row for row in pair}
    platform_metrics = [
        _metric(platform, by_platform[platform]["public_url"], metrics.get(platform, {}))
        for platform in platforms
    ]

    bank = _bank(bank_path)
    next_row = _next_creative(bank, contract["creative_id"])
    previous = [row for row in existing if row.get("metric_complete") is True]
    current_views = sum(item["views"] for item in platform_metrics)
    if previous:
        previous_views = sum(item.get("views", 0) for item in previous[-1].get("platforms", []))
        direction = "preserve the stronger structure" if current_views > previous_views else "change the hook and scene"
        comparison = f"combined views {current_views} vs prior {previous_views}; {direction}"
    else:
        comparison = f"baseline combined views {current_views}; establish the first measured reference"
    reason = (
        f"{comparison}. Next {next_row['id']} changes hook={next_row['pain']}, "
        f"scene={next_row['moment']}, punchline={next_row['punchline']}."
    )

    streak_dates = _consecutive_dates(existing, date)
    row = {
        "date": date,
        "status": "done" if len(streak_dates) >= 7 else "started",
        "day_index": len(streak_dates),
        "streak_dates": streak_dates[-7:],
        "metric_complete": True,
        "creative_id": contract["creative_id"],
        "video_sha256": contract["video_sha256"],
        "caption_sha256": contract["caption_sha256"],
        "platforms": platform_metrics,
        "unavailable_metrics": ["clicks", "completion_rate", "signups", "watch_time"],
        "next_creative_id": next_row["id"],
        "next_change_reason": reason,
    }
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.chmod(ledger_path, 0o600)
    return row


def collect_tiktok(url: str, runner=subprocess.run) -> dict:
    proc = runner(
        ["yt-dlp", "--dump-json", "--skip-download", url],
        text=True,
        capture_output=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise SelfImproveError("TikTok public metric readback failed")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SelfImproveError("TikTok metric JSON is invalid") from exc
    return {
        "views": data.get("view_count"),
        "likes": data.get("like_count"),
        "comments": data.get("comment_count"),
    }


def collect_instagram(url: str, settings_path: Path, client_factory=None) -> dict:
    code_match = re.search(r"/(?:reel|p)/([A-Za-z0-9_-]+)/?", url)
    if not code_match or not settings_path.is_file():
        raise SelfImproveError("Instagram metric session or code is unavailable")
    if client_factory is None:
        from instagrapi import Client
        client_factory = Client
    client = client_factory()
    client.load_settings(str(settings_path))
    media_pk = client.media_pk_from_code(code_match.group(1))
    media = client.media_info(media_pk)
    data = media.model_dump() if hasattr(media, "model_dump") else media.dict()
    views = data.get("play_count")
    if views is None:
        views = data.get("view_count")
    return {
        "views": views,
        "likes": data.get("like_count"),
        "comments": data.get("comment_count"),
    }


def main() -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat())
    parser.add_argument(
        "--distribution-ledger",
        type=Path,
        default=_lm_video_state_root() / "distribution.jsonl",
    )
    parser.add_argument(
        "--self-improve-ledger",
        type=Path,
        default=_lm_video_state_root() / "self-improve.jsonl",
    )
    parser.add_argument(
        "--bank",
        type=Path,
        default=here.parent / "daily-lm-video" / "creative-bank.jsonl",
    )
    parser.add_argument("--instagram-handle", default="anicca.affirms2")
    parser.add_argument("--platform", choices=("tiktok", "both"), default="tiktok")
    args = parser.parse_args()

    distribution_rows = _read_jsonl(args.distribution_ledger)
    platforms = ("tiktok",) if args.platform == "tiktok" else ("instagram", "tiktok")
    pair = select_latest_contract(distribution_rows, platforms)
    urls = {row["platform"]: row["public_url"] for row in pair}
    try:
        metrics = {"tiktok": collect_tiktok(urls["tiktok"])}
    except SelfImproveError as exc:
        if args.platform != "tiktok" or "TikTok public metric readback failed" not in str(exc):
            raise
        print(json.dumps(unavailable_metric_result(
            date=args.date, distribution_rows=distribution_rows,
            bank_path=args.bank, platforms=platforms, reason=str(exc),
        ), ensure_ascii=False, separators=(",", ":")))
        return 0
    if args.platform == "both":
        metrics["instagram"] = collect_instagram(
            urls["instagram"],
            Path(f"~/.cloak/instagrapi-{args.instagram_handle}.json").expanduser(),
        )
    row = record_day(
        date=args.date,
        distribution_rows=pair,
        metrics=metrics,
        bank_path=args.bank,
        ledger_path=args.self_improve_ledger,
        platforms=platforms,
    )
    print(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SelfImproveError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, separators=(",", ":")))
        raise SystemExit(1)
