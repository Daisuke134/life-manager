#!/usr/bin/env python3
"""seo_keyword_seed.py -- SEO target keyword for a capafy-skills article run.

The daily article loop (article-daily.sh) now sends some runs to a Capafy skill
instead of aniccaai.com (#6110). This script picks the best keyword to target in
that run's title/H2s for the chosen skill's buyer problem, using OpenSEO
(hosted MCP, free-trial credits -- see config/products.json "tracking" for why we
already trust OpenSEO's own numbers).

Cost discipline: one live research_keywords call costs ~43-54 OpenSEO credits.
Each skill's result is cached for 30 days under
~/.local/state/life-manager/writer/seo-keywords/<slug>.json, so each of the six
skills costs at most one call per rotation month, not one call per run. A
network/API/credits failure NEVER fails the article run -- it falls back to
whatever cache exists (even stale), and if there is no cache at all, falls back
to the skill's static seed phrase from products.json with no live metrics.

Usage:
  seo_keyword_seed.py --slug hook-lab --config config/products.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

CACHE_TTL_SECONDS = 30 * 24 * 3600
DEFAULT_CACHE_DIR = Path.home() / ".local/state/life-manager/writer/seo-keywords"
DEFAULT_CREDENTIALS_FILE = Path.home() / ".local/share/anicca/credentials.json"
DEFAULT_PROJECT_ID = "4e3bd4d3-a1ee-4b9b-b76f-6edb01f8bede"
OPENSEO_MCP_URL = "https://app.openseo.so/mcp"
# Cloudflare in front of app.openseo.so blocks the default urllib UA (error 1010
# browser_signature_banned) -- confirmed live 2026-09-28. A plain desktop-browser
# UA is required, not a bot-evasion measure.
OPENSEO_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
# A keyword with KD above this is effectively unrankable regardless of volume
# (e.g. a seed's most generic token, KD 100) -- excluded before sorting by volume.
MAX_KEYWORD_DIFFICULTY = 60
GOOD_INTENTS = {"informational", "commercial"}


def load_credential(credentials_file: Path, service: str) -> dict[str, Any] | None:
    try:
        data = json.loads(credentials_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for entry in data.get("credentials", []):
        if isinstance(entry, dict) and entry.get("service") == service:
            return entry
    return None


def _mcp_call(api_key: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    req = urllib.request.Request(
        OPENSEO_MCP_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json, text/event-stream",
            "User-Agent": OPENSEO_USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_live_rows(api_key: str, project_id: str, seed: str) -> list[dict[str, Any]]:
    """Call OpenSEO research_keywords for one seed. Raises on any failure --
    caller is responsible for catching and falling back."""
    response = _mcp_call(
        api_key,
        "tools/call",
        {
            "name": "research_keywords",
            "arguments": {"projectId": project_id, "seeds": [{"seed": seed}]},
        },
    )
    if "error" in response:
        raise RuntimeError(f"openseo error: {response['error']}")
    result = response["result"]["structuredContent"]["results"][0]
    if not result.get("ok"):
        raise RuntimeError(f"openseo seed failed: {result.get('error')}")
    return result.get("rows", [])


def pick_keywords(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Apply the spec's ranking: informational/commercial intent, keyword
    difficulty low (capped, so a seed's dominant head term with KD=100 never
    wins on volume alone), search volume high. Returns primary + up to 4
    secondaries, or None if nothing qualifies."""
    candidates = [
        row
        for row in rows
        if row.get("intent") in GOOD_INTENTS
        and isinstance(row.get("searchVolume"), (int, float))
        and row["searchVolume"] > 0
        and isinstance(row.get("keywordDifficulty"), (int, float))
        and row["keywordDifficulty"] <= MAX_KEYWORD_DIFFICULTY
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda r: (-r["searchVolume"], r["keywordDifficulty"]))
    primary = candidates[0]
    secondaries = candidates[1:5]
    return {
        "primary": primary["keyword"],
        "secondary": [c["keyword"] for c in secondaries],
        "metrics": {
            "primary": {
                "searchVolume": primary["searchVolume"],
                "keywordDifficulty": primary["keywordDifficulty"],
                "intent": primary["intent"],
            },
        },
    }


def cache_path(cache_dir: Path, slug: str) -> Path:
    return cache_dir / f"{slug}.json"


def load_cache(cache_dir: Path, slug: str) -> dict[str, Any] | None:
    path = cache_path(cache_dir, slug)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def cache_is_fresh(cache: dict[str, Any], now: float) -> bool:
    fetched_at = cache.get("fetched_at")
    return isinstance(fetched_at, (int, float)) and (now - fetched_at) < CACHE_TTL_SECONDS


def write_cache(cache_dir: Path, slug: str, record: dict[str, Any]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache_path(cache_dir, slug).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(cache_path(cache_dir, slug))


def resolve(
    slug: str,
    config: dict[str, Any],
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    credentials_file: Path = DEFAULT_CREDENTIALS_FILE,
    now: float | None = None,
) -> dict[str, Any]:
    now = time.time() if now is None else now
    skills = config["products"]["capafy-skills"]["skills"]
    skill = skills.get(slug)
    if skill is None:
        raise KeyError(f"unknown capafy skill slug: {slug}")
    seed = skill.get("seo_seed") or skill.get("buyer_problem", slug)

    cache = load_cache(cache_dir, slug)
    if cache is not None and cache_is_fresh(cache, now):
        return {**cache, "source": "cache"}

    credential = load_credential(credentials_file, "openseo")
    if credential and credential.get("api_key"):
        try:
            rows = fetch_live_rows(credential["api_key"], DEFAULT_PROJECT_ID, seed)
            picked = pick_keywords(rows)
            if picked is not None:
                record = {
                    "slug": slug,
                    "seed": seed,
                    "fetched_at": now,
                    **picked,
                }
                write_cache(cache_dir, slug, record)
                return {**record, "source": "live"}
        except (urllib.error.URLError, OSError, RuntimeError, KeyError, ValueError, TypeError):
            pass  # fall through to stale cache / static fallback below

    if cache is not None:
        return {**cache, "source": "cache-stale"}

    return {
        "slug": slug,
        "seed": seed,
        "primary": seed,
        "secondary": [],
        "metrics": {},
        "fetched_at": None,
        "source": "static",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--credentials-file", default=str(DEFAULT_CREDENTIALS_FILE))
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    result = resolve(
        args.slug,
        config,
        cache_dir=Path(args.cache_dir).expanduser(),
        credentials_file=Path(args.credentials_file).expanduser(),
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
