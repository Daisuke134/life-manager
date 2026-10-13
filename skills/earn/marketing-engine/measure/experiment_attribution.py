#!/usr/bin/env python3
"""Truthful experiment attribution joins over canonical Marketing Engine ledgers."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any
import urllib.parse
import urllib.request

from attribution import publication_campaign_token


SCHEMA_VERSION = "marketing.experiment-attribution.v1"
REQUIRED_METRICS = (
    "impressions", "views", "qualified_clicks", "first_time_downloads",
    "installs", "trials", "paid_orders", "refunds", "gross_revenue",
    "net_revenue",
)
ATTRIBUTION_CLASSES = {"deterministic", "apple_aggregate", "modeled", "unknown"}
STATUSES = {"observed", "not_mature", "unavailable", "unknown"}
SOCIAL_METRICS = {"impressions", "views"}
REVENUE_METRICS = {"gross_revenue", "net_revenue"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def parse_time(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("timestamp invalid") from exc
    require(parsed.tzinfo is not None, "timestamp timezone required")
    return parsed.astimezone(dt.timezone.utc)


def stable_id(prefix: str, values: list[str]) -> str:
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode()
    return f"{prefix}.{hashlib.sha256(payload).hexdigest()[:24]}"


def empty_result(metric_name: str, unit: str, window_start: str, window_end: str,
                 source: str, *, status: str = "unknown",
                 reason: str = "evidence_insufficient",
                 evidence_refs: list[str] | None = None) -> dict[str, Any]:
    return {
        "metric_name": metric_name,
        "status": status,
        "value": None,
        "unit": unit,
        "source": source,
        "attribution_class": "unknown",
        "confidence": 0.0,
        "window_start": window_start,
        "window_end": window_end,
        "evidence_refs": evidence_refs or ["publication_identity"],
        "null_reason": reason,
        "model": None,
    }


def observed_result(metric_name: str, value: float, unit: str, source: str,
                    attribution_class: str, confidence: float,
                    window_start: str, window_end: str,
                    evidence_refs: list[str]) -> dict[str, Any]:
    result = empty_result(metric_name, unit, window_start, window_end, source,
                          evidence_refs=evidence_refs)
    result.update({"status": "observed", "value": value,
                   "attribution_class": attribution_class,
                   "confidence": confidence, "null_reason": None})
    return result


def validate_result(result: dict[str, Any]) -> None:
    required = {"metric_name", "status", "value", "unit", "source",
                "attribution_class", "confidence", "window_start", "window_end",
                "evidence_refs", "null_reason", "model"}
    require(set(result) == required, "result fields invalid")
    require(result["metric_name"] in REQUIRED_METRICS, "metric name invalid")
    require(result["status"] in STATUSES, "metric status invalid")
    require(result["attribution_class"] in ATTRIBUTION_CLASSES,
            "attribution class invalid")
    require(isinstance(result["unit"], str) and result["unit"], "metric unit required")
    require(isinstance(result["source"], str) and result["source"], "metric source required")
    require(isinstance(result["confidence"], (int, float)) and
            0 <= result["confidence"] <= 1, "confidence invalid")
    require(isinstance(result["evidence_refs"], list) and result["evidence_refs"] and
            all(isinstance(item, str) and item for item in result["evidence_refs"]),
            "metric evidence required")
    require(parse_time(result["window_start"]) <= parse_time(result["window_end"]),
            "metric window invalid")
    if result["value"] is None:
        require(result["status"] != "observed", "observed metric requires value")
        require(isinstance(result["null_reason"], str) and result["null_reason"],
                "null metric requires reason")
    else:
        require(isinstance(result["value"], (int, float)) and result["value"] >= 0,
                "metric value invalid")
        require(result["status"] == "observed" and result["null_reason"] is None,
                "metric value must be observed")
        require(result["attribution_class"] != "unknown",
                "observed metric attribution cannot be unknown")
    if result["attribution_class"] == "modeled":
        model = result.get("model")
        require(isinstance(model, dict) and
                all(key in model for key in ("method", "baseline", "sample_size", "interval")) and
                isinstance(model["interval"], list) and len(model["interval"]) == 2,
                "modeled evidence incomplete")
    else:
        require(result["model"] is None, "model allowed only for modeled attribution")


def validate_snapshot(snapshot: dict[str, Any]) -> None:
    required = {"schema_version", "attribution_id", "observed_at", "publish_key",
                "experiment_id", "creative_id", "product_id", "account_id",
                "hook_id", "renderer_id", "attribution_token", "postiz_post_id",
                "native_post_id", "native_post_url", "published_at", "results"}
    require(set(snapshot) == required, "snapshot fields invalid")
    require(snapshot["schema_version"] == SCHEMA_VERSION, "snapshot schema invalid")
    for field in required - {"results", "schema_version"}:
        require(isinstance(snapshot[field], str) and snapshot[field], f"{field} required")
    parse_time(snapshot["observed_at"])
    parse_time(snapshot["published_at"])
    expected_id = stable_id("attribution", [snapshot["publish_key"], snapshot["observed_at"]])
    require(snapshot["attribution_id"] == expected_id, "attribution id mismatch")
    require(isinstance(snapshot["results"], list), "results required")
    require([row["metric_name"] for row in snapshot["results"]] == list(REQUIRED_METRICS),
            "complete ordered metric set required")
    for result in snapshot["results"]:
        validate_result(result)


def _age_hours(start: str, end: str) -> float:
    return (parse_time(end) - parse_time(start)).total_seconds() / 3600


def _base_results(published_at: str, observed_at: str) -> dict[str, dict[str, Any]]:
    social_status = "not_mature" if _age_hours(published_at, observed_at) < 6 else "unavailable"
    social_reason = "social_checkpoint_not_mature" if social_status == "not_mature" else "social_metric_not_collected"
    business_status = "not_mature" if _age_hours(published_at, observed_at) < 24 else "unavailable"
    business_reason = "business_window_not_mature" if business_status == "not_mature" else "business_outcome_not_collected"
    rows: dict[str, dict[str, Any]] = {}
    for metric in REQUIRED_METRICS:
        unit = "minor_currency_units" if metric in REVENUE_METRICS else "count"
        if metric in SOCIAL_METRICS:
            rows[metric] = empty_result(metric, unit, published_at, observed_at,
                                        "native_platform", status=social_status,
                                        reason=social_reason)
        elif metric == "qualified_clicks":
            rows[metric] = empty_result(metric, unit, published_at, observed_at,
                                        "marketing_click_receipts", status="unavailable",
                                        reason="click_receipts_not_queried")
        else:
            rows[metric] = empty_result(metric, unit, published_at, observed_at,
                                        "business_outcomes", status=business_status,
                                        reason=business_reason)
    return rows


def _join_social(rows: dict[str, dict[str, Any]], identity: dict, post_metric: dict | None,
                 published_at: str, observed_at: str) -> None:
    if post_metric is None:
        return
    require(post_metric.get("native_post_id") == identity.get("native_post_id"),
            "native identity mismatch")
    require(post_metric.get("experiment_id") == identity.get("experiment_id"),
            "experiment identity mismatch")
    evidence = [f"post_metrics:{identity['native_post_id']}"]
    if post_metric.get("raw_evidence_hash"):
        evidence.append(f"sha256:{post_metric['raw_evidence_hash']}")
    for metric in SOCIAL_METRICS:
        value = post_metric.get(metric)
        if value is not None and post_metric.get("checkpoint_status") == "observed":
            rows[metric] = observed_result(metric, value, "count", "native_platform",
                                           "deterministic", 1.0, published_at,
                                           observed_at, evidence)
        else:
            reason = (post_metric.get("metric_null_reasons") or {}).get(metric)
            reason = reason or post_metric.get("error") or "metric_unobserved"
            status = "not_mature" if reason == "checkpoint_not_mature" else "unavailable"
            rows[metric] = empty_result(metric, "count", published_at, observed_at,
                                        "native_platform", status=status, reason=reason,
                                        evidence_refs=evidence)


def _join_click(rows: dict[str, dict[str, Any]], intent: dict, click_query: dict | None,
                published_at: str, observed_at: str) -> None:
    if click_query is None:
        return
    evidence = list(click_query.get("evidence_refs") or ["marketing_click_receipts"])
    if click_query.get("status") == "available":
        require(click_query.get("product_id") == intent.get("product_id") and
                click_query.get("campaign_token") == intent.get("attribution_token"),
                "click scope mismatch")
        count = click_query.get("count")
        require(isinstance(count, int) and count >= 0, "click count invalid")
        if intent.get("product_id") == "hook-lab":
            receipt_ids = click_query.get("receipt_ids")
            require(isinstance(receipt_ids, list) and len(receipt_ids) == count and
                    all(isinstance(receipt_id, str) and receipt_id for receipt_id in receipt_ids) and
                    len(set(receipt_ids)) == len(receipt_ids),
                    "click receipt IDs invalid")
            evidence.extend(f"marketing_click_receipt:{receipt_id}"
                            for receipt_id in receipt_ids)
        rows["qualified_clicks"] = observed_result(
            "qualified_clicks", count, "count", "marketing_click_receipts",
            "deterministic", 1.0, published_at, observed_at, evidence)
    else:
        reason = click_query.get("reason") or "click_query_unavailable"
        rows["qualified_clicks"] = empty_result(
            "qualified_clicks", "count", published_at, observed_at,
            "marketing_click_receipts", status="unavailable", reason=reason,
            evidence_refs=evidence)


def _join_business(rows: dict[str, dict[str, Any]], intent: dict,
                   business: dict | None, published_at: str, observed_at: str) -> None:
    if business is None:
        return
    require(business.get("product_id") == intent.get("product_id"),
            "business product mismatch")
    sources = business.get("sources") or {}
    token = intent["attribution_token"]
    asc = sources.get("app_store_connect") or {}
    asc_campaign = ((asc.get("data") or {}).get("campaigns") or {}).get(token)
    if asc.get("status") == "available" and asc_campaign:
        evidence = [asc_campaign.get("evidence_ref") or "app_store_connect_campaign"]
        for metric in ("first_time_downloads", "installs"):
            if asc_campaign.get(metric) is not None:
                rows[metric] = observed_result(metric, asc_campaign[metric], "count",
                                               "app_store_connect", "apple_aggregate",
                                               0.9, published_at, observed_at, evidence)
    stripe = sources.get("stripe") or {}
    stripe_data = stripe.get("data") or {}
    stripe_campaign = (stripe_data.get("campaigns") or {}).get(token)
    if stripe.get("status") == "available" and stripe_campaign:
        evidence = [stripe_campaign.get("evidence_ref") or "stripe_campaign"]
        currency = str(stripe_campaign.get("currency") or "unknown").lower()
        mapping = {"paid_orders": "paid_orders", "refunds": "refunds",
                   "gross_revenue": "gross_revenue", "net_revenue": "net_revenue"}
        for metric, key in mapping.items():
            if stripe_campaign.get(key) is not None:
                unit = f"{currency}_minor" if metric in REVENUE_METRICS else "count"
                rows[metric] = observed_result(metric, stripe_campaign[key], unit,
                                               "stripe", "deterministic", 1.0,
                                               published_at, observed_at, evidence)
    elif stripe.get("status") == "available":
        evidence = [stripe_data.get("evidence_ref") or "stripe_product_snapshot"]
        for metric in ("paid_orders", "refunds", "gross_revenue", "net_revenue"):
            unit = "minor_currency_units" if metric in REVENUE_METRICS else "count"
            rows[metric] = empty_result(
                metric, unit, published_at, observed_at, "stripe", status="unknown",
                reason="product_aggregate_not_publication_attributed",
                evidence_refs=evidence)


def build_snapshot(*, intent: dict, identity: dict, post_metric: dict | None,
                   click_query: dict | None, business_snapshot: dict | None,
                   observed_at: str) -> dict[str, Any]:
    if intent.get("product_id") == "hook-lab":
        require(intent.get("attribution_token") == publication_campaign_token(intent),
                "Hook Lab publication token mismatch")
    published_at = identity.get("publish_date") or intent.get("scheduled_at")
    require(identity.get("identity_status") == "resolved", "native identity unresolved")
    require(identity.get("experiment_id") == intent.get("experiment_id"),
            "experiment identity mismatch")
    require(identity.get("native_post_id") and identity.get("native_post_url"),
            "native identity incomplete")
    require(parse_time(published_at) <= parse_time(observed_at), "observation predates publication")
    rows = _base_results(published_at, observed_at)
    _join_social(rows, identity, post_metric, published_at, observed_at)
    _join_click(rows, intent, click_query, published_at, observed_at)
    _join_business(rows, intent, business_snapshot, published_at, observed_at)
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "attribution_id": stable_id("attribution", [intent["publish_key"], observed_at]),
        "observed_at": observed_at,
        "publish_key": intent["publish_key"],
        "experiment_id": intent["experiment_id"],
        "creative_id": intent["creative_id"],
        "product_id": intent["product_id"],
        "account_id": intent["account_id"],
        "hook_id": intent["hook_id"],
        "renderer_id": intent["renderer_id"],
        "attribution_token": intent["attribution_token"],
        "postiz_post_id": identity["postiz_post_id"],
        "native_post_id": identity["native_post_id"],
        "native_post_url": identity["native_post_url"],
        "published_at": published_at,
        "results": [rows[name] for name in REQUIRED_METRICS],
    }
    validate_snapshot(snapshot)
    return snapshot


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def append_snapshot(path: Path, snapshot: dict[str, Any]) -> bool:
    validate_snapshot(snapshot)
    path = Path(path)
    rows = _read_jsonl(path)
    matches = [row for row in rows if row.get("attribution_id") == snapshot["attribution_id"]]
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if matches:
        existing = json.dumps(matches[0], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        require(existing == encoded, "conflicting attribution replay")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text("".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in rows + [snapshot]
    ), encoding="utf-8")
    os.replace(temp, path)
    return True


def select_identity(rows: list[dict[str, Any]], intent: dict[str, Any],
                    postiz_post_id: str) -> dict[str, Any]:
    matches = [row for row in rows
               if row.get("experiment_id") == intent.get("experiment_id")
               and row.get("postiz_post_id") == postiz_post_id
               and row.get("identity_status") == "resolved"]
    require(len(matches) == 1, "exactly one publication identity required")
    return matches[0]


def select_latest_post_metric(rows: list[dict[str, Any]], identity: dict[str, Any],
                              observed_at: str) -> dict[str, Any] | None:
    cutoff = parse_time(observed_at)
    matches = [row for row in rows
               if row.get("experiment_id") == identity.get("experiment_id")
               and row.get("native_post_id") == identity.get("native_post_id")
               and row.get("observed_at")
               and parse_time(row["observed_at"]) <= cutoff]
    return max(matches, key=lambda row: parse_time(row["observed_at"])) if matches else None


def select_business_snapshot(rows: list[dict[str, Any]], product_id: str,
                             business_date: str) -> dict[str, Any] | None:
    matches = [row for row in rows if row.get("product_id") == product_id
               and row.get("business_date") == business_date]
    require(len(matches) <= 1, "ambiguous business snapshot")
    return matches[0] if matches else None


def _default_fetch(url: str, headers: dict[str, str]):
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=20) as response:
        response_headers = {key.lower(): value for key, value in response.headers.items()}
        return response.status, response_headers, json.loads(response.read())


def query_click_receipts(*, supabase_url: str, service_role_key: str,
                         product_id: str, campaign_token: str, observed_at: str,
                         fetch=None) -> dict[str, Any]:
    """Read exact click count without touching the redirect itself."""
    parse_time(observed_at)
    base_evidence = ["supabase:marketing_click_receipts"]
    if not supabase_url or not service_role_key:
        return {"status": "unavailable", "reason": "missing_supabase_credential",
                "observed_at": observed_at, "evidence_refs": base_evidence}
    query = urllib.parse.urlencode({
        "select": "receipt_id,campaign_token,product_id,clicked_at",
        "campaign_token": f"eq.{campaign_token}",
        "product_id": f"eq.{product_id}", "order": "clicked_at.asc",
    }, safe=".,")
    url = f"{supabase_url.rstrip('/')}/rest/v1/marketing_click_receipts?{query}"
    headers = {"apikey": service_role_key,
               "Authorization": f"Bearer {service_role_key}",
               "Accept": "application/json", "Prefer": "count=exact"}
    try:
        status, response_headers, body = (fetch or _default_fetch)(url, headers)
    except Exception as exc:
        return {"status": "unavailable", "reason": f"query_{type(exc).__name__}",
                "observed_at": observed_at, "evidence_refs": base_evidence}
    if status != 200 or not isinstance(body, list):
        return {"status": "unavailable", "reason": f"http_{status}",
                "observed_at": observed_at, "evidence_refs": base_evidence}
    content_range = response_headers.get("content-range") or response_headers.get("Content-Range")
    if not content_range or "/" not in content_range or content_range.rsplit("/", 1)[1] == "*":
        return {"status": "unavailable", "reason": "exact_count_header_missing",
                "observed_at": observed_at, "evidence_refs": base_evidence}
    try:
        count = int(content_range.rsplit("/", 1)[1])
    except ValueError:
        return {"status": "unavailable", "reason": "exact_count_invalid",
                "observed_at": observed_at, "evidence_refs": base_evidence}
    if count != len(body):
        return {"status": "unavailable", "reason": "receipt_rows_incomplete",
                "observed_at": observed_at, "evidence_refs": base_evidence}
    receipt_ids = [row.get("receipt_id") for row in body]
    if (any(not isinstance(receipt_id, str) or not receipt_id for receipt_id in receipt_ids)
            or len(set(receipt_ids)) != len(receipt_ids)):
        return {"status": "unavailable", "reason": "receipt_ids_invalid",
                "observed_at": observed_at, "evidence_refs": base_evidence}
    require(all(row.get("campaign_token") == campaign_token and
                row.get("product_id") == product_id for row in body),
            "click scope mismatch")
    return {"status": "available", "product_id": product_id,
            "campaign_token": campaign_token, "count": count,
            "observed_at": observed_at, "content_range": content_range,
            "receipt_ids": receipt_ids,
            "evidence_refs": base_evidence}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")
    os.replace(temp, path)


def _load_intent(db_path: Path, publish_key: str) -> tuple[dict[str, Any], str]:
    with sqlite3.connect(db_path) as db:
        row = db.execute("SELECT payload_json,provider_post_id FROM intents WHERE publish_key=?",
                         (publish_key,)).fetchone()
    require(row is not None, "publication intent not found")
    require(row[1], "provider post receipt missing")
    return json.loads(row[0]), row[1]


def load_repo_env(repo_root: Path) -> None:
    path = Path(repo_root) / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def run_attribution(*, db_path: Path, publish_key: str, identity_path: Path,
                    post_metrics_path: Path, business_path: Path,
                    business_date: str, observed_at: str, ledger_path: Path,
                    evidence_path: Path, repo_root: Path) -> dict[str, Any]:
    intent, postiz_post_id = _load_intent(db_path, publish_key)
    identity = select_identity(_read_jsonl(identity_path), intent, postiz_post_id)
    post_metric = select_latest_post_metric(_read_jsonl(post_metrics_path), identity, observed_at)
    business = select_business_snapshot(_read_jsonl(business_path), intent["product_id"],
                                        business_date)
    load_repo_env(repo_root)
    click_query = query_click_receipts(
        supabase_url=os.environ.get("SUPABASE_URL", ""),
        service_role_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        product_id=intent["product_id"], campaign_token=intent["attribution_token"],
        observed_at=observed_at)
    click_evidence = Path(evidence_path).with_name("click-receipts.json")
    _write_json(click_evidence, click_query)
    click_query["evidence_refs"] = [str(click_evidence)]
    snapshot = build_snapshot(intent=intent, identity=identity, post_metric=post_metric,
                              click_query=click_query, business_snapshot=business,
                              observed_at=observed_at)
    appended = append_snapshot(ledger_path, snapshot)
    evidence = {
        "schema_version": 1, "gate": 13, "status": "verified",
        "observed_at": observed_at, "attribution_id": snapshot["attribution_id"],
        "publish_key": publish_key, "snapshot_appended": appended,
        "click_query": click_query,
        "result_summary": [
            {key: row[key] for key in ("metric_name", "status", "value", "unit",
                                       "attribution_class", "confidence", "null_reason")}
            for row in snapshot["results"]
        ],
        "source_paths": {"identity": str(identity_path),
                         "post_metrics": str(post_metrics_path),
                         "business": str(business_path), "ledger": str(ledger_path)},
    }
    _write_json(evidence_path, evidence)
    return evidence
