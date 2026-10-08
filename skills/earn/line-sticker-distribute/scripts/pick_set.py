#!/usr/bin/env python3
"""pick_set.py -- choose a 販売中 (on-sale) LINE sticker set and clip order.

Reads ~/.local/state/life-manager/line-sticker/set-*/creators-item.json (the
line-sticker build loop's own durable state; see
skills/earn/line-sticker/SKILL.md) and skips any set that is not
state_observed == "販売中" -- a set still in review or rejected has no store
page to sell. Rotates which on-sale set and which clip order is picked by a
deterministic index derived from the caller's slot key, so consecutive posts
are not identical (anti-spam) without needing any model call for bookkeeping.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ON_SALE = "販売中"


def load_on_sale_sets(line_sticker_state_root: Path) -> list[dict]:
    sets = []
    for item_file in sorted(line_sticker_state_root.glob("set-*/creators-item.json")):
        try:
            item = json.loads(item_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(item, dict) or item.get("state_observed") != ON_SALE:
            continue
        set_dir = item_file.parent
        clips_dir = set_dir / "clips"
        listing_file = set_dir / "listing.json"
        if not clips_dir.is_dir() or not listing_file.is_file():
            continue
        try:
            listing = json.loads(listing_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        clip_ids = sorted(p.stem for p in clips_dir.glob("*.mp4"))
        if not clip_ids:
            continue
        # The only trustworthy link is the one Creators Market itself shows as 購入用URL
        # (https://line.me/S/sticker/<store id>). The store's product id differs from the item id,
        # so a URL built from the item id is a 404 (all promotion pointed at one until 2026-10-09).
        store_url = item.get("purchase_url")
        if not isinstance(store_url, str) or not store_url.startswith("https://line.me/S/sticker/"):
            continue
        sets.append({
            "set_id": set_dir.name,
            "set_dir": str(set_dir),
            "clips_dir": str(clips_dir),
            "clip_ids": clip_ids,
            "title_ja": item.get("title_ja") or listing.get("title", {}).get("ja", ""),
            "character_name": listing.get("character_name", ""),
            "store_url": store_url,
            "purchase_url": store_url,
        })
    return sets


def deterministic_index(seed_key: str, modulus: int) -> int:
    if modulus <= 0:
        return 0
    digest = hashlib.sha256(seed_key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % modulus


def choose_clip_order(clip_ids: list[str], seed_key: str, count: int) -> list[str]:
    count = min(count, len(clip_ids))
    ordered = list(clip_ids)
    # Deterministic shuffle (Fisher-Yates driven by a seeded counter) so the
    # same seed_key always yields the same order, but different slots differ.
    for i in range(len(ordered) - 1, 0, -1):
        j = deterministic_index(f"{seed_key}:{i}", i + 1)
        ordered[i], ordered[j] = ordered[j], ordered[i]
    return ordered[:count]


def choose_set(sets: list[dict], seed_key: str) -> dict | None:
    if not sets:
        return None
    index = deterministic_index(seed_key, len(sets))
    return sets[index]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", required=True, help="line-sticker build loop state root")
    parser.add_argument("--seed-key", required=True, help="e.g. lane_id + slot_at, for deterministic rotation")
    parser.add_argument("--clip-count", type=int, default=4)
    args = parser.parse_args(argv)

    sets = load_on_sale_sets(Path(args.state_root).expanduser())
    chosen = choose_set(sets, args.seed_key)
    if chosen is None:
        print(json.dumps({"state": "no_sets_on_sale"}))
        return 1
    clip_order = choose_clip_order(chosen["clip_ids"], args.seed_key, args.clip_count)
    print(json.dumps({
        "state": "selected",
        **chosen,
        "clip_order": clip_order,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
