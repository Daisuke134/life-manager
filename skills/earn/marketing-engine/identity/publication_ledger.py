#!/usr/bin/env python3
"""Build a truthful Postiz-to-native publication identity ledger."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import tempfile
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

from product_binding import bind_product_ids, load_account_bindings, load_product_ids


POSTIZ = "https://api.postiz.com/public/v1"
MEASURE_DIR = Path(__file__).resolve().parents[1] / "measure"


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    except ValueError:
        return None


def normalize_text(value: str | None) -> str:
    return "".join((value or "").split()).casefold()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_env(path: Path) -> dict[str, str]:
    env = dict(os.environ)
    if not path.is_file():
        return env
    for line in path.read_text(errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env.setdefault(key.strip(), value.strip().strip("\"'"))
    return env


def http_json(url: str, headers: dict[str, str], data: bytes | None = None) -> Any:
    method = "POST" if data is not None else "GET"
    request = urllib.request.Request(url, headers=headers, data=data, method=method)
    with urllib.request.urlopen(request, timeout=650 if data is not None else 90) as response:
        return json.load(response)


def fetch_postiz_posts(api_key: str, start: dt.datetime, end: dt.datetime) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({
        "startDate": start.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "endDate": end.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "limit": 500,
    })
    body = http_json(f"{POSTIZ}/posts?{query}", {"Authorization": api_key})
    return body if isinstance(body, list) else list(body.get("posts") or [])


def tiktok_handle(post: dict[str, Any]) -> str | None:
    url = str(post.get("releaseURL") or "")
    if "@" not in url:
        return None
    return url.rstrip("/").rsplit("@", 1)[-1].split("/", 1)[0] or None


def fetch_tiktok_public_profiles(
    handles: list[str], *, cdp_url: str
) -> list[dict[str, Any]]:
    if str(MEASURE_DIR) not in sys.path:
        sys.path.insert(0, str(MEASURE_DIR))
    from tiktok_public_metrics import collect_tiktok_public_profiles

    return collect_tiktok_public_profiles(handles, cdp_url=cdp_url)


def candidate_handle(item: dict[str, Any]) -> str | None:
    author = item.get("authorMeta") or {}
    return author.get("name") if isinstance(author, dict) else None


def candidate_time(item: dict[str, Any]) -> dt.datetime | None:
    parsed = parse_time(item.get("createTimeISO"))
    if parsed:
        return parsed
    epoch = item.get("createTime")
    if isinstance(epoch, (int, float)):
        return dt.datetime.fromtimestamp(epoch, dt.timezone.utc)
    return None


def resolve_tiktok(post: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    handle = tiktok_handle(post)
    published_at = parse_time(post.get("publishDate"))
    content = normalize_text(post.get("content"))
    account_items = [item for item in items if candidate_handle(item) == handle]
    exact = [item for item in account_items if content and normalize_text(item.get("text")) == content]
    near = []
    if published_at:
        near = [
            item for item in account_items
            if candidate_time(item) is not None
            and abs((candidate_time(item) - published_at).total_seconds()) <= 900
        ]
    near_ids = {str(item.get("id") or "") for item in near}
    exact_near = [
        item for item in exact if str(item.get("id") or "") in near_ids
    ]
    if len(exact_near) == 1:
        item = exact_near[0]
        native_id = str(item.get("id") or "") or None
        native_url = item.get("webVideoUrl")
        if native_id and native_url:
            return {
                "identity_status": "resolved",
                "native_post_id": native_id,
                "native_post_url": native_url,
                "resolution_method": "platform_profile_full_caption_time_exact",
                "resolution_confidence": "deterministic",
                "candidate_count": 1,
            }
    return {
        "identity_status": "ambiguous" if exact or near else "unresolved",
        "native_post_id": None,
        "native_post_url": None,
        "resolution_method": None,
        "resolution_confidence": "unknown",
        "candidate_count": len(exact_near) or max(len(exact), len(near)),
    }


def direct_identity(post: dict[str, Any]) -> dict[str, Any]:
    release_id = post.get("releaseId")
    release_url = post.get("releaseURL")
    if release_id and release_id != "missing" and release_url:
        return {
            "identity_status": "resolved",
            "native_post_id": str(release_id),
            "native_post_url": str(release_url),
            "resolution_method": "postiz_provider_native_receipt",
            "resolution_confidence": "deterministic",
            "candidate_count": 1,
        }
    return {
        "identity_status": "unresolved",
        "native_post_id": None,
        "native_post_url": None,
        "resolution_method": None,
        "resolution_confidence": "unknown",
        "candidate_count": 0,
    }


def make_row(post: dict[str, Any], tiktok_items: list[dict[str, Any]], observed_at: str) -> dict[str, Any]:
    integration = post.get("integration") or {}
    platform = integration.get("providerIdentifier") if isinstance(integration, dict) else None
    state = post.get("state")
    if state == "ERROR":
        identity = {
            "identity_status": "error",
            "native_post_id": None,
            "native_post_url": None,
            "resolution_method": None,
            "resolution_confidence": "unknown",
            "candidate_count": 0,
        }
    elif state == "PUBLISHED" and platform == "tiktok" and "/video/" not in str(post.get("releaseURL") or ""):
        identity = resolve_tiktok(post, tiktok_items)
    elif state == "PUBLISHED":
        identity = direct_identity(post)
    else:
        identity = {
            "identity_status": "not_published",
            "native_post_id": None,
            "native_post_url": None,
            "resolution_method": None,
            "resolution_confidence": "unknown",
            "candidate_count": 0,
        }
    content = str(post.get("content") or "")
    return {
        "schema_version": 1,
        "observed_at": observed_at,
        "postiz_post_id": post.get("id"),
        "postiz_group_id": post.get("group"),
        "postiz_state": state,
        "postiz_release_id": post.get("releaseId"),
        "postiz_release_url": post.get("releaseURL"),
        "publish_date": post.get("publishDate"),
        "creation_method": post.get("creationMethod"),
        "integration_id": integration.get("id") if isinstance(integration, dict) else None,
        "account_name": integration.get("name") if isinstance(integration, dict) else None,
        "platform": platform,
        "content_sha256": sha256_text(content),
        "experiment_id": None,
        "experiment_id_null_reason": "legacy_uninstrumented",
        "creative_sha256": None,
        "creative_sha256_null_reason": "legacy_postiz_list_omits_asset_identity",
        "provenance": ["postiz_public_api"] + (
            ["public_tiktok_profile_snapshot"] if platform == "tiktok" and tiktok_items else []
        ),
        **identity,
    }


def validate_rows(rows: list[dict[str, Any]]) -> None:
    postiz_ids: set[str] = set()
    native_keys: set[tuple[str, str, str]] = set()
    for row in rows:
        identifier = row.get("postiz_post_id")
        if not identifier or identifier in postiz_ids:
            raise ValueError(f"missing or duplicate Postiz ID: {identifier}")
        postiz_ids.add(identifier)
        if row.get("identity_status") == "resolved":
            if not row.get("native_post_id") or not row.get("native_post_url"):
                raise ValueError(f"resolved row lacks native receipt: {identifier}")
            key = (str(row.get("platform")), str(row.get("integration_id")), str(row["native_post_id"]))
            if key in native_keys:
                raise ValueError(f"duplicate native identity: {key}")
            native_keys.add(key)
        elif row.get("native_post_id") is not None or row.get("native_post_url") is not None:
            raise ValueError(f"unresolved row contains native identity: {identifier}")
        if row.get("creative_sha256") is None and not row.get("creative_sha256_null_reason"):
            raise ValueError(f"missing creative null reason: {identifier}")


def merge_rows(existing: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {str(row["postiz_post_id"]): row for row in existing}
    identity_fields = (
        "identity_status",
        "native_post_id",
        "native_post_url",
        "resolution_method",
        "resolution_confidence",
        "candidate_count",
    )
    for row in current:
        key = str(row["postiz_post_id"])
        previous = merged.get(key)
        if (
            previous is not None
            and previous.get("identity_status") == "resolved"
            and row.get("postiz_state") == "PUBLISHED"
            and row.get("identity_status") != "resolved"
        ):
            row = dict(row)
            for field in identity_fields:
                row[field] = previous.get(field)
            row["provenance"] = list(
                dict.fromkeys(
                    [*(previous.get("provenance") or []), *(row.get("provenance") or [])]
                )
            )
        merged[key] = row
    rows = sorted(merged.values(), key=lambda row: (str(row.get("publish_date") or ""), str(row["postiz_post_id"])))
    validate_rows(rows)
    return rows


def bind_merged_rows(
    rows: list[dict[str, Any]], *, product_registry: Path, account_registry: Path
) -> tuple[list[dict[str, Any]], dict]:
    """Bind every merged publication row using the account manifest registry."""

    products = load_product_ids(product_registry)
    bindings = load_account_bindings(account_registry, products)
    return bind_product_ids(rows, bindings)


def reconciliation_report(rows: list[dict[str, Any]], start: dt.datetime, end: dt.datetime, observed_at: str) -> dict[str, Any]:
    window_ids = {
        row["postiz_post_id"] for row in rows
        if (published := parse_time(row.get("publish_date"))) is not None and start <= published <= end
    }
    window = [row for row in rows if row["postiz_post_id"] in window_ids]
    published = [row for row in window if row.get("postiz_state") == "PUBLISHED"]
    resolved = [row for row in published if row.get("identity_status") == "resolved"]
    denominator = len(published)
    return {
        "schema_version": 1,
        "observed_at": observed_at,
        "window_start": iso(start),
        "window_end": iso(end),
        "total_rows": len(window),
        "published_denominator": denominator,
        "published_resolved": len(resolved),
        "published_resolution_rate": round(len(resolved) / denominator, 6) if denominator else None,
        "passes_95_percent_gate": bool(denominator and len(resolved) / denominator >= 0.95),
        "state_counts": dict(Counter(str(row.get("postiz_state")) for row in window)),
        "platform_state_counts": {
            f"{platform}|{state}": count
            for (platform, state), count in sorted(Counter((str(row.get("platform")), str(row.get("postiz_state"))) for row in window).items())
        },
        "identity_status_counts": dict(Counter(str(row.get("identity_status")) for row in window)),
        "ambiguous_postiz_ids": [row["postiz_post_id"] for row in published if row.get("identity_status") == "ambiguous"],
        "error_postiz_ids": [row["postiz_post_id"] for row in window if row.get("postiz_state") == "ERROR"],
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[1]
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--days", type=int, default=3)
    result.add_argument("--env-file", type=Path, default=Path.home() / "anicca/.env")
    result.add_argument("--posts-fixture", type=Path)
    result.add_argument("--tiktok-snapshot", type=Path)
    result.add_argument(
        "--cdp-url",
        default=os.environ.get("CLOAK_CDP_BASE_URL", "http://localhost:9222"),
    )
    result.add_argument("--output", type=Path, default=root / "state/publication-identity.jsonl")
    result.add_argument("--report", type=Path, required=True)
    result.add_argument("--account-registry", type=Path, default=root / "registry/accounts")
    result.add_argument("--product-registry", type=Path, default=root / "registry/products")
    result.add_argument("--bind-existing-only", action="store_true")
    result.add_argument(
        "--quality-gate-exit-code",
        type=int,
        choices=(1, 3),
        default=1,
        help="exit code used when evidence is written but the 95%% quality gate misses",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.days <= 0:
        raise SystemExit("--days must be positive")
    end = utc_now()
    start = end - dt.timedelta(days=args.days)

    if args.bind_existing_only:
        observed_at = iso(end)
        rows, binding_report = bind_merged_rows(
            read_jsonl(args.output),
            product_registry=args.product_registry,
            account_registry=args.account_registry,
        )
        validate_rows(rows)
        report = reconciliation_report(rows, start, end, observed_at)
        report["binding"] = binding_report
        atomic_write(
            args.output,
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        )
        atomic_write(args.report, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        print(
            json.dumps(
                {
                    "status": "written",
                    "output": str(args.output),
                    "report": str(args.report),
                    **report,
                },
                ensure_ascii=False,
            )
        )
        return 0 if report["passes_95_percent_gate"] else args.quality_gate_exit_code

    env = load_env(args.env_file)
    if args.posts_fixture:
        value = json.loads(args.posts_fixture.read_text())
        posts = value if isinstance(value, list) else value.get("posts", [])
    else:
        if not env.get("POSTIZ_API_KEY"):
            raise SystemExit("POSTIZ_API_KEY missing from Marketing Engine environment")
        posts = fetch_postiz_posts(env["POSTIZ_API_KEY"], start, end)
    if args.tiktok_snapshot:
        tiktok_items = json.loads(args.tiktok_snapshot.read_text())
    else:
        handles = sorted(
            {
                handle
                for post in posts
                if post.get("state") == "PUBLISHED"
                and (post.get("integration") or {}).get("providerIdentifier") == "tiktok"
                and "/video/" not in str(post.get("releaseURL") or "")
                and (handle := tiktok_handle(post))
            }
        )
        try:
            tiktok_items = (
                fetch_tiktok_public_profiles(handles, cdp_url=args.cdp_url)
                if handles
                else []
            )
        except Exception as exc:
            print(
                f"WARNING free TikTok public identity unavailable: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            tiktok_items = []
    observed_at = iso(end)
    current = [make_row(post, tiktok_items, observed_at) for post in posts]
    rows = merge_rows(read_jsonl(args.output), current)
    rows, binding_report = bind_merged_rows(
        rows,
        product_registry=args.product_registry,
        account_registry=args.account_registry,
    )
    validate_rows(rows)
    report = reconciliation_report(rows, start, end, observed_at)
    report["binding"] = binding_report
    atomic_write(args.output, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows))
    atomic_write(args.report, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "written", "output": str(args.output), "report": str(args.report), **report}, ensure_ascii=False))
    return 0 if report["passes_95_percent_gate"] else args.quality_gate_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
