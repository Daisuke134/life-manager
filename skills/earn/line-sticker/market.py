#!/usr/bin/env python3
"""Daily LINE STORE top-seller sweep so the sticker factory always copies current winners
(AGENTS.md #2: every decision starts from what the top sellers on the platform do).

Deterministic HTTP GET against the public showcase pages -- no login, no browser. Reads the
top_creators (all + animated) and new_creators rankings, dedups to ~40 products in rank order,
and fetches each product page for price/sticker-count/description/format (parsed from the
page's own schema.org JSON-LD and its sticker-preview ``data-preview`` type field -- both
public and stable, no guessing). For the top ``CLASSIFY_LIMIT`` items only, the main thumbnail
is handed to the model (``runtime/agent-runner/agent_runner.py``) to classify whether the
stickers carry text, the theme, art style and covered phrases -- that judgment belongs to the
model, not a hardcoded rule. Writes one compact snapshot to ``market.json`` (no images kept)
so ``line_sticker_planner.py`` can require a concrete ``copy_target`` from it.

Self-gates to once per day like ``sales_readback.py``; every other hourly wake is a no-op.

    market.py
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import line_sticker_planner as planner_mod  # noqa: E402 (reuse its agent_runner plumbing)

STATE_ROOT_DEFAULT = Path(os.environ.get("LIFE_MANAGER_STATE_HOME", str(Path.home() / ".local/state/life-manager"))) / "line-sticker"
JST = datetime.timezone(datetime.timedelta(hours=9))
SHOWCASE_URLS = (
    "https://store.line.me/stickershop/showcase/top_creators/ja",
    "https://store.line.me/stickershop/showcase/top_creators/ja?category=2000",
    "https://store.line.me/stickershop/showcase/new_creators/ja",
)
PRODUCT_LIST_LIMIT = 40
CLASSIFY_LIMIT = 15
USER_AGENT = "Mozilla/5.0 (compatible; life-manager-market-sweep/1.0)"

PRODUCT_HREF_RE = re.compile(r'href="/stickershop/product/(\d+)/ja"')
LDJSON_RE = re.compile(r'<script type="application/ld\+json">([\s\S]*?)</script>')
STICKER_LIST_RE = re.compile(r'FnStickerList[\s\S]*?</ul>')
STICKER_LI_RE = re.compile(r'<li class="mdCMN09Li.*?</li>', re.S)
STICKER_TYPE_RE = re.compile(r'&quot;type&quot;\s*:\s*&quot;(\w+)&quot;')


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _fetch(url: str) -> str | None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError):
        return None


def parse_showcase_product_ids(html: str) -> list[str]:
    """Product ids in rank order as they appear on a showcase page, deduped."""
    return list(dict.fromkeys(PRODUCT_HREF_RE.findall(html)))


def parse_product_page(html: str) -> dict:
    """Public, stable fields from a product page: schema.org JSON-LD (title, description,
    price, author) plus the sticker-preview list's own ``data-preview`` type field (format,
    sticker_count). A field the page did not render stays None, never a guessed value."""
    ld_match = LDJSON_RE.search(html)
    ld = json.loads(ld_match.group(1)) if ld_match else {}
    offers = ld.get("offers") or {}
    seller = offers.get("seller") or {}
    seller_url = seller.get("url")
    list_match = STICKER_LIST_RE.search(html)
    items = STICKER_LI_RE.findall(list_match.group(0)) if list_match else []
    types = [m.group(1) for li in items for m in [STICKER_TYPE_RE.search(li)] if m]
    if "animation" in types:
        fmt = "animated"
    elif "popup" in types:
        fmt = "popup"
    elif types:
        fmt = "static"
    else:
        fmt = "unknown"
    price_raw = offers.get("price")
    return {
        "title": ld.get("name"),
        "description": ld.get("description"),
        "price_jpy": int(price_raw) if price_raw is not None else None,
        "author": seller.get("name"),
        "author_url": seller_url,
        "sticker_count": len(items) or None,
        "format": fmt,
    }


def parse_author_set_count(html: str) -> int:
    """Distinct products linked from an author's page (first page only -- a lower bound on
    their series size, which is all the planner needs to judge "this author has many sets")."""
    return len(set(PRODUCT_HREF_RE.findall(html)))


def sweep_product_ids(fetch=_fetch, limit: int = PRODUCT_LIST_LIMIT) -> list[str]:
    ids: list[str] = []
    for url in SHOWCASE_URLS:
        html = fetch(url)
        if html:
            ids.extend(parse_showcase_product_ids(html))
    return list(dict.fromkeys(ids))[:limit]


def build_items(product_ids: list[str], fetch=_fetch) -> list[dict]:
    items = []
    author_set_counts: dict[str, int] = {}
    for product_id in product_ids:
        html = fetch(f"https://store.line.me/stickershop/product/{product_id}/ja")
        if not html:
            continue
        detail = parse_product_page(html)
        author_url = detail.pop("author_url")
        author_sets = None
        if author_url:
            if author_url not in author_set_counts:
                author_html = fetch(f"https://store.line.me{author_url}" if author_url.startswith("/") else author_url)
                author_set_counts[author_url] = parse_author_set_count(author_html) if author_html else None
            author_sets = author_set_counts[author_url]
        items.append({
            "product_id": product_id,
            "product_url": f"https://store.line.me/stickershop/product/{product_id}/ja",
            "author_sets": author_sets,
            "text_or_no_text": None,
            "theme": None,
            "art_style": None,
            "phrases": None,
            **detail,
        })
    return items


def classify_top_items(items: list[dict], set_dir: Path, limit: int = CLASSIFY_LIMIT, fetch_bytes=None) -> None:
    """Hands the top ``limit`` items' main thumbnail to the model to judge text/no-text,
    theme, art style and covered phrases -- a taxonomic judgment, not a hardcoded rule."""
    fetch_bytes = fetch_bytes or (lambda url: urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=20).read())
    targets = items[:limit]
    image_paths = []
    with tempfile.TemporaryDirectory(prefix=".market-", dir=set_dir) as tmp:
        tmp_dir = Path(tmp)
        for item in targets:
            image_url = f"https://stickershop.line-scdn.net/stickershop/v1/product/{item['product_id']}/LINEStorePC/main.png"
            try:
                data = fetch_bytes(image_url)
            except (urllib.error.URLError, TimeoutError, OSError):
                continue
            path = tmp_dir / f"{item['product_id']}.png"
            path.write_bytes(data)
            image_paths.append((item["product_id"], path))
        if not image_paths:
            return
        prompt = f"""添付の各画像は、LINE STOREの人気スタンプの代表サムネイル。画像の順番と
product_idの対応: {json.dumps([pid for pid, _ in image_paths], ensure_ascii=False)}

各商品について判定する:
- text_or_no_text: 画像内に文字（セリフ・吹き出しの文章など）が描かれているか。"text" か "no_text"。
- theme: 一言でテーマ（例: 敬語・仕事、季節イベント、毎日のリアクション）。
- art_style: 一言で画風（例: 丸くてシンプルな線画、ちぎり絵風、水彩タッチ）。
- phrases: 画像から読み取れる、またはテーマから推測される短いフレーズ/意図のリスト（3〜6個）。

product_idごとに1件、配列で返す。JSON Schemaに厳密に従ったJSONだけを返す。"""
        evidence_dir = tmp_dir / "evidence"
        result = planner_mod._run_agent(
            prompt=prompt, schema=HERE / "schemas" / "market_classification.schema.json",
            evidence_dir=evidence_dir, task_label=f"line-sticker-market-classify-{set_dir.name}",
            images=[path for _, path in image_paths],
        )
    by_id = {row["product_id"]: row for row in result.get("items", [])}
    for item in targets:
        row = by_id.get(item["product_id"])
        if row:
            item.update({k: row[k] for k in ("text_or_no_text", "theme", "art_style", "phrases")})


def should_run_today(market_file: Path) -> bool:
    if not market_file.exists():
        return True
    try:
        observed = datetime.datetime.fromisoformat(json.loads(market_file.read_text())["observed_at"])
    except (json.JSONDecodeError, KeyError, ValueError):
        return True
    return observed.astimezone(JST).date() != now_utc().astimezone(JST).date()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, default=STATE_ROOT_DEFAULT)
    parser.add_argument("--skip-classify", action="store_true", help="for tests/dry-runs")
    args = parser.parse_args()
    state_root = args.state_root
    market_file = state_root / "market.json"

    if not should_run_today(market_file):
        print(json.dumps({"status": "skipped_already_today"}))
        return

    product_ids = sweep_product_ids()
    if not product_ids:
        print(json.dumps({"status": "fetch_failed"}))
        return
    items = build_items(product_ids)
    state_root.mkdir(parents=True, exist_ok=True)
    if not args.skip_classify and items:
        classify_top_items(items, state_root)
    row = {
        "observed_at": now_utc().isoformat(),
        "source_urls": list(SHOWCASE_URLS),
        "items": items,
    }
    tmp = market_file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(row, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    tmp.replace(market_file)
    print(json.dumps({"status": "ok", "items": len(items)}))


if __name__ == "__main__":
    main()
