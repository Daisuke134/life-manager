#!/usr/bin/env python3
"""Cross-check ten native posts without treating unavailable fields as matches."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Iterable

import native_metrics
from tiktok_public_metrics import collect_tiktok_public_metrics


DEFAULT_REPORT = (
    native_metrics.ENGINE_ROOT
    / "evidence"
    / "metrics"
    / "2026-08-01-gate4-ten-post-verification.json"
)


def compare_fields(
    primary: dict[str, int | None],
    independent: dict[str, int | None],
    fields: Iterable[str],
) -> dict[str, Any]:
    comparable: list[str] = []
    excluded: dict[str, str] = {}
    mismatches: list[dict[str, Any]] = []
    for field in fields:
        left = primary.get(field)
        right = independent.get(field)
        if left is None or right is None:
            excluded[field] = "field_unavailable_in_one_source"
            continue
        comparable.append(field)
        if left != right:
            mismatches.append(
                {"field": field, "primary": left, "independent": right}
            )
    return {
        "comparable_fields": comparable,
        "excluded_fields": excluded,
        "mismatches": mismatches,
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    identity_matches = sum(bool(record.get("identity_match")) for record in records)
    posts_with_comparable_field = sum(
        bool(record.get("comparison", {}).get("comparable_fields"))
        for record in records
    )
    mismatches = [
        {"native_post_id": record.get("native_post_id"), **mismatch}
        for record in records
        for mismatch in record.get("comparison", {}).get("mismatches", [])
    ]
    return {
        "posts_checked": len(records),
        "identity_matches": identity_matches,
        "posts_with_comparable_field": posts_with_comparable_field,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "passes_gate": (
            len(records) == 10
            and identity_matches == 10
            and posts_with_comparable_field == 10
            and not mismatches
        ),
    }


def shortcode(url: str) -> str | None:
    parts = [part for part in urllib.parse.urlparse(url).path.split("/") if part]
    if len(parts) >= 2 and parts[0] in {"p", "reel"}:
        return parts[1]
    return None


def apify_instagram(
    rows: list[dict[str, Any]], token: str
) -> dict[str, dict[str, Any]]:
    payload = {
        "directUrls": [row["native_post_url"] for row in rows],
        "resultsType": "posts",
        "resultsLimit": len(rows),
    }
    query = urllib.parse.urlencode({"token": token, "timeout": 600})
    items = native_metrics.http_json(
        "https://api.apify.com/v2/acts/apify~instagram-scraper/"
        f"run-sync-get-dataset-items?{query}",
        {"Content-Type": "application/json"},
        data=json.dumps(payload).encode(),
        method="POST",
        timeout=650,
    )
    return {
        code: item
        for item in items
        if (code := shortcode(str(item.get("url") or "")))
    }


async def _tiktok_visible_async(
    rows: list[dict[str, Any]], cdp_url: str
) -> dict[str, dict[str, Any]]:
    from playwright.async_api import async_playwright

    output: dict[str, dict[str, Any]] = {}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(cdp_url)
        context = await browser.new_context()
        try:
            page = await context.new_page()
            for row in rows:
                native_id = str(row["native_post_id"])
                await page.goto(
                    row["native_post_url"],
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                await page.wait_for_timeout(4_000)
                result = await page.evaluate(
                    """() => {
                      const text = (name) => {
                        const el = document.querySelector(`[data-e2e="${name}-count"]`);
                        return el ? el.textContent.trim() : null;
                      };
                      const aria = (name) => {
                        const el = document.querySelector(`[data-e2e="${name}-icon"]`);
                        return el ? el.getAttribute("aria-label") : null;
                      };
                      return {
                        url: location.href,
                        likes: text("like"),
                        comments: text("comment"),
                        saves: text("favorite"),
                        shares: text("share"),
                        share_aria: aria("share")
                      };
                    }"""
                )

                def number(value: Any) -> int | None:
                    if value is None:
                        return None
                    match = re.search(r"[0-9][0-9,]*", str(value))
                    return int(match.group(0).replace(",", "")) if match else None

                shares = number(result.get("shares"))
                if shares is None:
                    shares = number(result.get("share_aria"))
                output[native_id] = {
                    "url": result.get("url"),
                    "metrics": {
                        "likes": number(result.get("likes")),
                        "comments": number(result.get("comments")),
                        "saves": number(result.get("saves")),
                        "shares": shares,
                    },
                }
        finally:
            await context.close()
            await browser.close()
    return output


def tiktok_visible(
    rows: list[dict[str, Any]], cdp_url: str
) -> dict[str, dict[str, Any]]:
    return asyncio.run(_tiktok_visible_async(rows, cdp_url))


def youtube_public(row: dict[str, Any]) -> dict[str, Any]:
    result = subprocess.run(
        [
            "yt-dlp",
            "--skip-download",
            "--dump-single-json",
            "--no-warnings",
            row["native_post_url"],
        ],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    if result.returncode:
        return {
            "id": None,
            "metrics": {},
            "error": f"yt-dlp exit {result.returncode}: {result.stderr[:160]}",
        }
    item = json.loads(result.stdout)
    return {
        "id": item.get("id"),
        "metrics": {
            "views": item.get("view_count"),
            "likes": item.get("like_count"),
            "comments": item.get("comment_count"),
        },
        "error": None,
    }


def verify(
    ledger_rows: list[dict[str, Any]],
    *,
    postiz: native_metrics.PostizClient,
    apify_token: str,
    cdp_url: str,
) -> dict[str, Any]:
    resolved = [
        row
        for row in ledger_rows
        if row.get("postiz_state") == "PUBLISHED"
        and row.get("identity_status") == "resolved"
    ]
    instagram_candidates = [
        row for row in resolved if row.get("platform") == "instagram-standalone"
    ][:8]
    tiktok_rows = [
        row for row in resolved if row.get("platform") == "tiktok"
    ][:3]
    youtube_rows = [
        row for row in resolved if row.get("platform") == "youtube"
    ][:3]
    records: list[dict[str, Any]] = []

    public_instagram = apify_instagram(instagram_candidates, apify_token)
    for row in instagram_candidates:
        code = shortcode(row["native_post_url"])
        item = public_instagram.get(code or "")
        if not item:
            continue
        primary, _ = native_metrics.normalize_postiz_analytics(
            "instagram", postiz.analytics(row["postiz_post_id"])
        )
        independent, _ = native_metrics.normalize_public_instagram(item)
        comparison = compare_fields(
            primary, independent, ("views", "likes", "comments")
        )
        if not comparison["comparable_fields"]:
            continue
        records.append(
            {
                "platform": "instagram",
                "postiz_id": row["postiz_post_id"],
                "native_post_id": row["native_post_id"],
                "native_url": row["native_post_url"],
                "identity_match": code == shortcode(str(item.get("url") or "")),
                "primary_source": "postiz_instagram_graph_api",
                "independent_source": "apify_instagram_public_post",
                "primary_metrics": primary,
                "independent_metrics": independent,
                "comparison": comparison,
            }
        )
        if sum(record["platform"] == "instagram" for record in records) == 4:
            break

    tiktok_primary = collect_tiktok_public_metrics(tiktok_rows, cdp_url=cdp_url)
    tiktok_independent = tiktok_visible(tiktok_rows, cdp_url)
    for row in tiktok_rows:
        native_id = str(row["native_post_id"])
        primary_item = tiktok_primary.get(native_id)
        independent_item = tiktok_independent.get(native_id, {})
        primary, _ = native_metrics.normalize_public_tiktok(
            primary_item.get("stats") if primary_item else None
        )
        independent = independent_item.get("metrics") or {}
        records.append(
            {
                "platform": "tiktok",
                "postiz_id": row["postiz_post_id"],
                "native_post_id": native_id,
                "native_url": row["native_post_url"],
                "identity_match": (
                    bool(primary_item)
                    and f"/video/{native_id}"
                    in str(independent_item.get("url") or "")
                ),
                "primary_source": "cloakbrowser_tiktok_native_public_api",
                "independent_source": "tiktok_visible_detail_dom",
                "primary_metrics": primary,
                "independent_metrics": independent,
                "comparison": compare_fields(
                    primary, independent, ("likes", "comments", "shares", "saves")
                ),
            }
        )

    for row in youtube_rows:
        primary, _ = native_metrics.normalize_postiz_analytics(
            "youtube", postiz.analytics(row["postiz_post_id"])
        )
        public = youtube_public(row)
        records.append(
            {
                "platform": "youtube",
                "postiz_id": row["postiz_post_id"],
                "native_post_id": row["native_post_id"],
                "native_url": row["native_post_url"],
                "identity_match": public.get("id") == row["native_post_id"],
                "primary_source": "postiz_youtube_data_api",
                "independent_source": "yt_dlp_public_metadata",
                "primary_metrics": primary,
                "independent_metrics": public.get("metrics") or {},
                "independent_error": public.get("error"),
                "comparison": compare_fields(
                    primary,
                    public.get("metrics") or {},
                    ("views", "likes", "comments"),
                ),
            }
        )

    observed_at = native_metrics.utc_text(dt.datetime.now(dt.timezone.utc))
    return {
        "schema_version": 1,
        "observed_at": observed_at,
        "rounding_rule": "exact integers; unavailable fields excluded with reason",
        "platform_counts": {
            platform: sum(record["platform"] == platform for record in records)
            for platform in ("instagram", "tiktok", "youtube")
        },
        "records": records,
        "summary": summarize(records),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=native_metrics.DEFAULT_LEDGER)
    parser.add_argument("--env", type=Path, default=native_metrics.DEFAULT_ENV)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--cdp-url",
        default="http://localhost:9222",
    )
    args = parser.parse_args()
    env = native_metrics.load_env(args.env)
    if not env.get("APIFY_API_TOKEN"):
        print("ERROR APIFY_API_TOKEN missing", file=sys.stderr)
        return 1
    report = verify(
        native_metrics.read_jsonl(args.ledger),
        postiz=native_metrics.PostizClient(env.get("POSTIZ_API_KEY", "")),
        apify_token=env["APIFY_API_TOKEN"],
        cdp_url=args.cdp_url,
    )
    native_metrics.write_json(args.report, report)
    print(json.dumps({**report["summary"], "report": str(args.report)}, sort_keys=True))
    return 0 if report["summary"]["passes_gate"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
