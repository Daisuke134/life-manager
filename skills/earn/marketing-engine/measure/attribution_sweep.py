#!/usr/bin/env python3
"""Daily exact-identity attribution snapshots for the marketing owner."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
ENGINE_ROOT = HERE.parent
REPO_ROOT = HERE.parents[3]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import experiment_attribution as attribution  # noqa: E402


REPORT_SCHEMA_VERSION = 1
MINIMUM_MATURITY = dt.timedelta(hours=24)
REQUIRED_IDENTITY_FIELDS = (
    "publish_key",
    "experiment_id",
    "creative_id",
    "creative_sha256",
    "product_id",
    "account_id",
    "integration_id",
    "platform",
    "hook_id",
    "renderer_id",
    "attribution_token",
    "scheduled_at",
    "postiz_post_id",
    "native_post_id",
    "native_post_url",
)
EXCLUSION_REASONS = (
    "not_published",
    "legacy_uninstrumented",
    "identity_unresolved",
    "identity_ambiguous",
    "metadata_incomplete",
    "native_receipt_missing",
    "published_at_missing",
    "identity_mismatch",
    "duplicate_postiz_id",
    "duplicate_publish_key",
    "duplicate_native_receipt",
    "not_mature_yet",
)
ClickQuery = Callable[[dict[str, Any], str], dict[str, Any]]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return attribution._read_jsonl(Path(path))


def _immutable_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    fields = (
        "publish_key",
        "experiment_id",
        "creative_id",
        "creative_sha256",
        "product_id",
        "account_id",
        "integration_id",
        "platform",
        "hook_id",
        "renderer_id",
        "attribution_token",
        "scheduled_at",
        "native_post_id",
        "native_post_url",
    )
    return tuple(row.get(field) for field in fields)


def _duplicate_rows(rows: list[tuple[int, dict[str, Any]]]) -> dict[int, str]:
    groups: dict[str, dict[Any, list[int]]] = {
        "postiz_post_id": defaultdict(list),
        "publish_key": defaultdict(list),
    }
    native: dict[tuple[Any, Any, Any], list[int]] = defaultdict(list)
    by_index = {index: row for index, row in rows}
    for index, row in rows:
        for field in groups:
            value = row.get(field)
            if value:
                groups[field][value].append(index)
        if row.get("native_post_id"):
            native[(row.get("platform"), row.get("integration_id"),
                    row["native_post_id"])].append(index)

    excluded: dict[int, str] = {}
    for value, indices in groups["postiz_post_id"].items():
        if len(indices) > 1:
            signatures = {_immutable_signature(by_index[index]) for index in indices}
            reason = "duplicate_postiz_id" if len(signatures) == 1 else "identity_mismatch"
            for index in indices:
                excluded.setdefault(index, reason)
    for value, indices in groups["publish_key"].items():
        if len(indices) > 1:
            signatures = {_immutable_signature(by_index[index]) for index in indices}
            reason = "duplicate_publish_key" if len(signatures) == 1 else "identity_mismatch"
            for index in indices:
                excluded.setdefault(index, reason)
    for receipt, indices in native.items():
        if len(indices) > 1:
            for index in indices:
                excluded.setdefault(index, "duplicate_native_receipt")
    return excluded


def _intent_context(identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "marketing.publication-intent.v2",
        "publish_key": identity["publish_key"],
        "experiment_id": identity["experiment_id"],
        "creative_id": identity["creative_id"],
        "asset_sha256": identity["creative_sha256"],
        "product_id": identity["product_id"],
        "account_id": identity["account_id"],
        "integration_id": identity["integration_id"],
        "platform": identity["platform"],
        "hook_id": identity["hook_id"],
        "renderer_id": identity["renderer_id"],
        "attribution_token": identity["attribution_token"],
        "scheduled_at": identity["scheduled_at"],
        "postiz_post_id": identity["postiz_post_id"],
        "native_post_id": identity["native_post_id"],
        "native_post_url": identity["native_post_url"],
    }


def _query_click_for_publication(intent: dict[str, Any], observed_at: str) -> dict[str, Any]:
    return attribution.query_click_receipts(
        supabase_url=os.environ.get("SUPABASE_URL", ""),
        service_role_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        product_id=intent["product_id"],
        campaign_token=intent["attribution_token"],
        observed_at=observed_at,
    )


def run_sweep(
    *,
    identity_path: Path,
    post_metrics_path: Path,
    business_path: Path,
    attribution_path: Path,
    report_path: Path,
    observed_at: str,
    query_click: ClickQuery | None = None,
) -> dict[str, Any]:
    """Write one mature, exact-identity attribution snapshot per publication/day."""

    observed = attribution.parse_time(observed_at)
    identity_rows = _read_jsonl(identity_path)
    post_metric_rows = _read_jsonl(post_metrics_path)
    business_rows = _read_jsonl(business_path)
    prior_snapshots = _read_jsonl(attribution_path)
    observed_day = observed.date()
    query_click = query_click or _query_click_for_publication

    duplicate_exclusions = _duplicate_rows([
        (index, row) for index, row in enumerate(identity_rows)
        if row.get("postiz_state") == "PUBLISHED"
    ])

    already_by_day: dict[tuple[str, dt.date], dict[str, Any]] = {}
    for snapshot in prior_snapshots:
        publish_key = snapshot.get("publish_key")
        timestamp = snapshot.get("observed_at")
        if not publish_key or not timestamp:
            continue
        key = (str(publish_key), attribution.parse_time(str(timestamp)).date())
        if key in already_by_day:
            raise ValueError("duplicate daily attribution snapshot")
        already_by_day[key] = snapshot

    excluded = Counter()
    structurally_valid: list[tuple[int, dict[str, Any], dt.datetime]] = []
    for index, row in enumerate(identity_rows):
        if row.get("postiz_state") != "PUBLISHED":
            excluded["not_published"] += 1
            continue
        duplicate_reason = duplicate_exclusions.get(index)
        if duplicate_reason:
            excluded[duplicate_reason] += 1
            continue
        if (not row.get("publish_key") or not row.get("experiment_id")
                or row.get("experiment_id_null_reason") == "legacy_uninstrumented"):
            excluded["legacy_uninstrumented"] += 1
            continue
        if row.get("identity_status") == "ambiguous":
            excluded["identity_ambiguous"] += 1
            continue
        if row.get("identity_status") != "resolved":
            excluded["identity_unresolved"] += 1
            continue
        if not row.get("native_post_id") or not row.get("native_post_url"):
            excluded["native_receipt_missing"] += 1
            continue
        if any(not isinstance(row.get(field), str) or not row[field]
               for field in REQUIRED_IDENTITY_FIELDS):
            excluded["metadata_incomplete"] += 1
            continue
        published_at = row.get("publish_date")
        if not isinstance(published_at, str) or not published_at:
            excluded["published_at_missing"] += 1
            continue
        try:
            published = attribution.parse_time(published_at)
        except ValueError:
            excluded["identity_mismatch"] += 1
            continue
        try:
            attribution.validate_publication_identity(_intent_context(row), row)
        except ValueError:
            excluded["identity_mismatch"] += 1
            continue
        structurally_valid.append((index, row, published))

    eligible: list[tuple[dict[str, Any], dt.datetime]] = []
    for index, row, published in structurally_valid:
        if observed - published < MINIMUM_MATURITY:
            excluded["not_mature_yet"] += 1
            continue
        eligible.append((row, published))

    unknown_metric_counts: Counter[str] = Counter()
    snapshots_written = 0
    snapshots_already_present = 0
    business_date = observed.date().isoformat()
    for identity, _published in eligible:
        daily_key = (identity["publish_key"], observed_day)
        existing = already_by_day.get(daily_key)
        if existing is not None:
            snapshots_already_present += 1
            unknown_metric_counts.update(
                row["metric_name"] for row in existing.get("results", [])
                if row.get("attribution_class") == "unknown"
            )
            continue

        intent = _intent_context(identity)
        post_metric = attribution.select_latest_post_metric(
            post_metric_rows, identity, observed_at
        )
        business_snapshot = attribution.select_business_snapshot(
            business_rows, intent["product_id"], business_date
        )
        click_query = query_click(intent, observed_at)
        snapshot = attribution.build_snapshot(
            intent=intent,
            identity=identity,
            post_metric=post_metric,
            click_query=click_query,
            business_snapshot=business_snapshot,
            observed_at=observed_at,
        )
        appended = attribution.append_snapshot(attribution_path, snapshot)
        if appended:
            snapshots_written += 1
            already_by_day[daily_key] = snapshot
        else:
            snapshots_already_present += 1
        unknown_metric_counts.update(
            row["metric_name"] for row in snapshot["results"]
            if row["attribution_class"] == "unknown"
        )

    eligible_count = len(eligible)
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "observed_at": observed_at,
        "status": "pass" if eligible_count else "attention",
        "eligible_publications": eligible_count,
        "snapshots_written": snapshots_written,
        "snapshots_already_present": snapshots_already_present,
        "excluded": {
            reason: excluded.get(reason, 0) for reason in EXCLUSION_REASONS
        },
        "unknown_metric_counts": dict(sorted(unknown_metric_counts.items())),
    }
    attribution._write_json(Path(report_path), report)
    return report


def _observed_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--post-metrics", type=Path, required=True)
    parser.add_argument("--business", type=Path, required=True)
    parser.add_argument("--attribution", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--observed-at", default=None)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    observed_at = args.observed_at or _observed_now()

    try:
        attribution.load_repo_env(args.repo_root)
        report = run_sweep(
            identity_path=args.identity,
            post_metrics_path=args.post_metrics,
            business_path=args.business,
            attribution_path=args.attribution,
            report_path=args.report,
            observed_at=observed_at,
        )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "observed_at": observed_at,
            "status": "failed",
            "error_class": type(exc).__name__,
            "next_action": "inspect_exact_identity_or_source_ledger",
        }
        attribution._write_json(args.report, report)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 1

    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 3 if report["status"] == "attention" else 0


if __name__ == "__main__":
    raise SystemExit(main())
