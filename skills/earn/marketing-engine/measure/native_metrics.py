#!/usr/bin/env python3
"""Truthful native-post metric checkpoints for the Marketing Engine.

The publication identity ledger is the only identity input. This collector never
matches captions, parses publish tokens, or substitutes a current number for a
historical checkpoint that was missed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable


POSTIZ = "https://api.postiz.com/public/v1"
COLLECTOR_VERSION = "native-metrics-v2"
CHECKPOINTS = (
    {"target_age_hours": 6, "max_lateness_hours": 3},
    {"target_age_hours": 24, "max_lateness_hours": 3},
    {"target_age_hours": 72, "max_lateness_hours": 6},
    {"target_age_hours": 168, "max_lateness_hours": 24},
)
METRIC_FIELDS = (
    "views",
    "reach",
    "impressions",
    "likes",
    "comments",
    "shares",
    "saves",
)
LABEL_TO_FIELD = {
    "views": "views",
    "reach": "reach",
    "impressions": "impressions",
    "likes": "likes",
    "comments": "comments",
    "shares": "shares",
    "saves": "saves",
}
NUMERIC_TIKTOK_ID = re.compile(r"^[0-9]{10,30}$")

ENGINE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ENGINE_ROOT / "state" / "publication-identity.jsonl"
DEFAULT_STATE = ENGINE_ROOT / "state" / "post-metrics.jsonl"
DEFAULT_RAW_EVIDENCE = ENGINE_ROOT / "evidence" / "metrics" / "provider-responses.jsonl"
DEFAULT_ENV = Path.home() / "anicca" / ".env"


def parse_time(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def utc_text(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def evidence_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    materialized = list(rows)
    if not materialized:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in materialized:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return len(materialized)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_env(path: Path = DEFAULT_ENV) -> dict[str, str]:
    values = dict(os.environ)
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values.setdefault(key.strip(), value.strip())
    return values


def metric_platform(platform: str) -> str:
    return "instagram" if platform == "instagram-standalone" else platform


def publication_id(row: dict[str, Any]) -> str:
    return f"postiz:{row['postiz_post_id']}"


def eligible_publications(
    rows: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    eligible: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for row in rows:
        state = row.get("postiz_state")
        identity = row.get("identity_status")
        if state == "ERROR" or identity == "error":
            counts["excluded_error"] += 1
        elif state != "PUBLISHED":
            counts["excluded_not_published"] += 1
        elif identity == "ambiguous":
            counts["excluded_ambiguous"] += 1
        elif identity != "resolved":
            counts["excluded_unresolved"] += 1
        elif not row.get("native_post_id") or not row.get("native_post_url"):
            counts["excluded_missing_native_identity"] += 1
        else:
            eligible.append(row)
            counts["eligible"] += 1
    for key in (
        "eligible",
        "excluded_error",
        "excluded_not_published",
        "excluded_ambiguous",
        "excluded_unresolved",
        "excluded_missing_native_identity",
    ):
        counts.setdefault(key, 0)
    return eligible, dict(counts)


def plan_checkpoints(
    publication_row: dict[str, Any],
    existing_rows: Iterable[dict[str, Any]],
    observed_at: str,
) -> list[dict[str, Any]]:
    published = parse_time(publication_row["publish_date"])
    observed = parse_time(observed_at)
    age_hours = (observed - published).total_seconds() / 3600
    if age_hours < 0:
        return []
    pid = publication_id(publication_row)
    latest_by_checkpoint: dict[tuple[object, object], dict[str, Any]] = {}
    for row in existing_rows:
        latest_by_checkpoint[
            (row.get("publication_id"), row.get("target_age_hours"))
        ] = row
    plans: list[dict[str, Any]] = []
    for checkpoint in CHECKPOINTS:
        target = checkpoint["target_age_hours"]
        if age_hours < target:
            continue
        previous = latest_by_checkpoint.get((pid, target))
        if previous is not None and previous.get("checkpoint_status") != "missed":
            continue
        lateness = age_hours - target
        missed = lateness > checkpoint["max_lateness_hours"]
        plans.append(
            {
                "publication_id": pid,
                "target_age_hours": target,
                "observed_age_hours": round(age_hours, 4),
                "lateness_hours": round(lateness, 4),
                "max_lateness_hours": checkpoint["max_lateness_hours"],
                "checkpoint_status": "due",
                "checkpoint_sla_status": "missed" if missed else "in_window",
                "corrects_snapshot_id": (
                    previous.get("snapshot_id") if previous is not None else None
                ),
                "error": "checkpoint_missed" if missed else None,
            }
        )
    return plans


def _empty_metrics(reason: str) -> tuple[dict[str, None], dict[str, str]]:
    return (
        {field: None for field in METRIC_FIELDS},
        {field: reason for field in METRIC_FIELDS},
    )


def _integer(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value).strip().replace(",", "")
    if re.fullmatch(r"-?[0-9]+", text):
        return int(text)
    return None


def normalize_postiz_analytics(
    platform: str, payload: list[dict[str, Any]]
) -> tuple[dict[str, int | None], dict[str, str | None]]:
    del platform  # Supported labels have the same contract across these providers.
    if not payload:
        return _empty_metrics("provider_empty_response")
    values: dict[str, int | None] = {field: None for field in METRIC_FIELDS}
    reasons: dict[str, str | None] = {
        field: "provider_field_missing" for field in METRIC_FIELDS
    }
    for item in payload:
        field = LABEL_TO_FIELD.get(str(item.get("label") or "").strip().lower())
        if not field:
            continue
        points = item.get("data")
        raw = points[-1].get("total") if isinstance(points, list) and points else None
        number = _integer(raw)
        if number is None:
            reasons[field] = "provider_value_invalid"
        else:
            values[field] = number
            reasons[field] = None
    return values, reasons


def normalize_public_instagram(
    item: dict[str, Any],
) -> tuple[dict[str, int | None], dict[str, str | None]]:
    values: dict[str, int | None] = {field: None for field in METRIC_FIELDS}
    reasons: dict[str, str | None] = {
        field: "public_field_unavailable" for field in METRIC_FIELDS
    }
    if "videoPlayCount" in item:
        values["views"] = _integer(item.get("videoPlayCount"))
    elif "videoViewCount" in item:
        values["views"] = _integer(item.get("videoViewCount"))
    for source, target in (
        ("likesCount", "likes"),
        ("commentsCount", "comments"),
    ):
        if source in item:
            values[target] = _integer(item.get(source))
    for field in METRIC_FIELDS:
        if values[field] is not None:
            reasons[field] = None
    return values, reasons


def normalize_public_tiktok(
    stats: dict[str, Any] | None,
) -> tuple[dict[str, int | None], dict[str, str | None]]:
    if stats is None:
        return _empty_metrics("native_item_not_visible")
    values: dict[str, int | None] = {field: None for field in METRIC_FIELDS}
    reasons: dict[str, str | None] = {
        field: "public_field_unavailable" for field in METRIC_FIELDS
    }
    for source, target in (
        ("playCount", "views"),
        ("diggCount", "likes"),
        ("commentCount", "comments"),
        ("shareCount", "shares"),
        ("collectCount", "saves"),
    ):
        if source in stats:
            values[target] = _integer(stats.get(source))
    for field in METRIC_FIELDS:
        if values[field] is not None:
            reasons[field] = None
    return values, reasons


def _row_base(
    publication_row: dict[str, Any],
    plan: dict[str, Any],
    observed_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "snapshot_id": hashlib.sha256(
            (
                f"{publication_id(publication_row)}:{plan['target_age_hours']}"
                + (f":correction:{observed_at}" if plan.get("corrects_snapshot_id") else "")
            ).encode()
        ).hexdigest(),
        "publication_id": publication_id(publication_row),
        "experiment_id": publication_row.get("experiment_id"),
        "experiment_id_null_reason": (
            None
            if publication_row.get("experiment_id")
            else "legacy_uninstrumented"
        ),
        "creative_id": publication_row.get("creative_sha256"),
        "creative_id_null_reason": (
            None
            if publication_row.get("creative_sha256")
            else "legacy_publication_asset_identity_absent"
        ),
        "product_id": publication_row.get("product_id"),
        "product_id_null_reason": (
            None
            if publication_row.get("product_id")
            else "legacy_publication_manifest_absent"
        ),
        "platform": metric_platform(str(publication_row.get("platform") or "")),
        "provider_identifier": publication_row.get("platform"),
        "account_name": publication_row.get("account_name"),
        "integration_id": publication_row.get("integration_id"),
        "postiz_id": publication_row.get("postiz_post_id"),
        "postiz_release_id": publication_row.get("postiz_release_id"),
        "native_post_id": publication_row.get("native_post_id"),
        "native_url": publication_row.get("native_post_url"),
        "published_at": publication_row.get("publish_date"),
        "observed_at": observed_at,
        "target_age_hours": plan["target_age_hours"],
        "observed_age_hours": plan["observed_age_hours"],
        "lateness_hours": plan["lateness_hours"],
        "checkpoint_sla_status": plan.get(
            "checkpoint_sla_status",
            "missed" if plan.get("checkpoint_status") == "missed" else "in_window",
        ),
        "corrects_snapshot_id": plan.get("corrects_snapshot_id"),
        "collector_version": COLLECTOR_VERSION,
    }


def make_missed_row(
    publication_row: dict[str, Any],
    plan: dict[str, Any],
    observed_at: str,
) -> dict[str, Any]:
    values, reasons = _empty_metrics("checkpoint_missed")
    return {
        **_row_base(publication_row, plan, observed_at),
        **values,
        "metric_null_reasons": reasons,
        "checkpoint_status": "missed",
        "source": None,
        "raw_evidence_hash": None,
        "error": "checkpoint_missed",
    }


def make_metric_row(
    publication_row: dict[str, Any],
    plan: dict[str, Any],
    values: dict[str, int | None],
    reasons: dict[str, str | None],
    *,
    observed_at: str,
    source: str,
    raw_response: Any,
    error: str | None = None,
) -> dict[str, Any]:
    missing_reason = next(
        (reason for reason in reasons.values() if reason), None
    )
    if error:
        status = "error"
    elif all(values.get(field) is None for field in METRIC_FIELDS):
        status = "unavailable"
        error = missing_reason or "provider_fields_unavailable"
    else:
        status = "measured"
    return {
        **_row_base(publication_row, plan, observed_at),
        **{field: values.get(field) for field in METRIC_FIELDS},
        "metric_null_reasons": {
            field: reasons.get(field) for field in METRIC_FIELDS
        },
        "checkpoint_status": status,
        "source": source,
        "raw_evidence_hash": evidence_hash(raw_response),
        "error": error,
    }


def validate_metric_rows(rows: Iterable[dict[str, Any]]) -> None:
    seen: dict[tuple[str, int], dict[str, Any]] = {}
    for index, row in enumerate(rows, start=1):
        key = (row.get("publication_id"), row.get("target_age_hours"))
        previous = seen.get(key)
        if previous is not None and row.get("corrects_snapshot_id") != previous.get("snapshot_id"):
            raise ValueError(f"unlinked duplicate metric checkpoint at row {index}: {key}")
        seen[key] = row
        if not key[0] or key[1] not in {6, 24, 72, 168}:
            raise ValueError(f"invalid metric checkpoint at row {index}")
        for field in METRIC_FIELDS:
            value = row.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(f"invalid {field} at row {index}")
            if value is None and not row.get("metric_null_reasons", {}).get(field):
                raise ValueError(f"missing null reason for {field} at row {index}")
        if row.get("checkpoint_status") == "missed" and any(
            row.get(field) is not None for field in METRIC_FIELDS
        ):
            raise ValueError(f"missed checkpoint contains metrics at row {index}")


def plan_tiktok_release_repairs(
    rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    planned: list[dict[str, Any]] = []
    native_seen: set[tuple[str, str]] = set()
    for row in rows:
        if (
            row.get("platform") != "tiktok"
            or row.get("postiz_state") != "PUBLISHED"
            or row.get("identity_status") != "resolved"
        ):
            continue
        native_id = str(row.get("native_post_id") or "")
        native_url = str(row.get("native_post_url") or "")
        integration_id = str(row.get("integration_id") or "")
        old_id = str(row.get("postiz_release_id") or "")
        expected_path = f"/video/{native_id}"
        unique_key = (integration_id, native_id)
        if (
            not NUMERIC_TIKTOK_ID.fullmatch(native_id)
            or expected_path not in native_url
            or not integration_id
            or unique_key in native_seen
        ):
            continue
        native_seen.add(unique_key)
        if old_id == native_id:
            continue
        planned.append(
            {
                "postiz_post_id": row["postiz_post_id"],
                "integration_id": integration_id,
                "native_url": native_url,
                "old_release_id": old_id,
                "new_release_id": native_id,
                "validation": "resolved_numeric_id_url_and_integration_unique",
            }
        )
    return planned


def execute_tiktok_release_repair(
    repair: dict[str, Any],
    *,
    update_release_id: Callable[[str, str], None],
    fetch_analytics: Callable[[str], list[dict[str, Any]]],
) -> dict[str, Any]:
    postiz_id = repair["postiz_post_id"]
    old_id = repair["old_release_id"]
    new_id = repair["new_release_id"]
    try:
        update_release_id(postiz_id, new_id)
        payload = fetch_analytics(postiz_id)
        if not payload:
            update_release_id(postiz_id, old_id)
            return {
                **repair,
                "status": "rolled_back",
                "error": "analytics_verification_empty",
                "analytics_evidence_hash": evidence_hash(payload),
            }
        values, _ = normalize_postiz_analytics("tiktok", payload)
        if values["views"] is None:
            update_release_id(postiz_id, old_id)
            return {
                **repair,
                "status": "rolled_back",
                "error": "analytics_verification_missing_views",
                "analytics_evidence_hash": evidence_hash(payload),
            }
        return {
            **repair,
            "status": "verified",
            "error": None,
            "analytics_evidence_hash": evidence_hash(payload),
            "verified_metrics": {
                field: values[field]
                for field in ("views", "likes", "comments", "shares")
            },
        }
    except Exception as exc:
        rollback_error = None
        try:
            update_release_id(postiz_id, old_id)
        except Exception as rollback_exc:  # Preserve both failures.
            rollback_error = f"{type(rollback_exc).__name__}: {rollback_exc}"
        return {
            **repair,
            "status": "rollback_failed" if rollback_error else "rolled_back",
            "error": f"{type(exc).__name__}: {exc}",
            "rollback_error": rollback_error,
        }


def http_json(
    url: str,
    headers: dict[str, str],
    *,
    data: bytes | None = None,
    method: str | None = None,
    timeout: int = 90,
) -> Any:
    request = urllib.request.Request(
        url,
        headers=headers,
        data=data,
        method=method or ("POST" if data is not None else "GET"),
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        return json.loads(body) if body else None


class PostizClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("POSTIZ_API_KEY missing")
        self._headers = {"Authorization": api_key}

    def analytics(self, postiz_id: str, days: int = 7) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"date": days})
        value = http_json(
            f"{POSTIZ}/analytics/post/{urllib.parse.quote(postiz_id)}?{query}",
            self._headers,
        )
        return value if isinstance(value, list) else []


def source_for(platform: str) -> str:
    return {
        "instagram": "postiz_instagram_graph_api",
        "tiktok": "postiz_tiktok_per_post_api",
        "youtube": "postiz_youtube_data_api",
    }.get(platform, "postiz_provider_analytics")


def collect_metrics(
    ledger_rows: list[dict[str, Any]],
    existing_rows: list[dict[str, Any]],
    *,
    observed_at: str,
    fetch_analytics: Callable[[str], list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    eligible, counts = eligible_publications(ledger_rows)
    new_rows: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []
    for publication_row in eligible:
        for plan in plan_checkpoints(publication_row, existing_rows + new_rows, observed_at):
            platform = metric_platform(publication_row["platform"])
            source = source_for(platform)
            try:
                payload = fetch_analytics(publication_row["postiz_post_id"])
                values, reasons = normalize_postiz_analytics(platform, payload)
                row = make_metric_row(
                    publication_row,
                    plan,
                    values,
                    reasons,
                    observed_at=observed_at,
                    source=source,
                    raw_response=payload,
                )
                raw_rows.append(
                    {
                        "schema_version": 1,
                        "publication_id": publication_id(publication_row),
                        "target_age_hours": plan["target_age_hours"],
                        "observed_at": observed_at,
                        "source": source,
                        "raw_evidence_hash": evidence_hash(payload),
                        "response": payload,
                    }
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                values, reasons = _empty_metrics("provider_request_failed")
                raw_error = {"error": error}
                row = make_metric_row(
                    publication_row,
                    plan,
                    values,
                    reasons,
                    observed_at=observed_at,
                    source=source,
                    raw_response=raw_error,
                    error=error,
                )
                raw_rows.append(
                    {
                        "schema_version": 1,
                        "publication_id": publication_id(publication_row),
                        "target_age_hours": plan["target_age_hours"],
                        "observed_at": observed_at,
                        "source": source,
                        "raw_evidence_hash": evidence_hash(raw_error),
                        "response": raw_error,
                    }
                )
            new_rows.append(row)
    validate_metric_rows(existing_rows + new_rows)
    status_counts = Counter(row["checkpoint_status"] for row in new_rows)
    report = {
        "schema_version": 1,
        "observed_at": observed_at,
        "collector_version": COLLECTOR_VERSION,
        "ledger_rows": len(ledger_rows),
        **counts,
        "new_rows": len(new_rows),
        "new_status_counts": dict(sorted(status_counts.items())),
    }
    return new_rows, raw_rows, report


def command_plan(args: argparse.Namespace) -> int:
    ledger_rows = read_jsonl(args.ledger)
    existing_rows = read_jsonl(args.state)
    now = args.now or utc_text(dt.datetime.now(dt.timezone.utc))
    eligible, counts = eligible_publications(ledger_rows)
    plans = [
        plan
        for row in eligible
        for plan in plan_checkpoints(row, existing_rows, now)
    ]
    print(
        json.dumps(
            {
                "observed_at": now,
                "ledger_rows": len(ledger_rows),
                **counts,
                "due": sum(p["checkpoint_status"] == "due" for p in plans),
                "missed": sum(p["checkpoint_status"] == "missed" for p in plans),
            },
            sort_keys=True,
        )
    )
    return 0


def command_collect(args: argparse.Namespace) -> int:
    env = load_env(args.env)
    client = PostizClient(env.get("POSTIZ_API_KEY", ""))
    ledger_rows = read_jsonl(args.ledger)
    existing_rows = read_jsonl(args.state)
    observed_at = args.now or utc_text(dt.datetime.now(dt.timezone.utc))
    new_rows, raw_rows, report = collect_metrics(
        ledger_rows,
        existing_rows,
        observed_at=observed_at,
        fetch_analytics=client.analytics,
    )
    append_jsonl(args.raw_evidence, raw_rows)
    append_jsonl(args.state, new_rows)
    if args.report:
        write_json(args.report, report)
    print(json.dumps({**report, "state": str(args.state)}, sort_keys=True))
    return 0 if not report["new_status_counts"].get("error") else 1


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    ap.add_argument("--state", type=Path, default=DEFAULT_STATE)
    ap.add_argument("--env", type=Path, default=DEFAULT_ENV)
    sub = ap.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan")
    plan.add_argument("--now")
    plan.set_defaults(function=command_plan)

    collect = sub.add_parser("collect")
    collect.add_argument("--now")
    collect.add_argument("--raw-evidence", type=Path, default=DEFAULT_RAW_EVIDENCE)
    collect.add_argument("--report", type=Path)
    collect.set_defaults(function=command_collect)
    return ap


def main() -> int:
    args = parser().parse_args()
    try:
        return args.function(args)
    except (ValueError, OSError, urllib.error.URLError) as exc:
        print(f"ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
