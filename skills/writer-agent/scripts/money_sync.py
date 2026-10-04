#!/usr/bin/env python3
"""Synchronize verified Writer publication and measurement evidence into money.sqlite3.

The legacy JSONL files mix public metrics, account dashboard totals, and explicit
unknowns.  This importer deliberately creates metric observations only.  It never
turns a dashboard number into received revenue: a money event requires its own
external transaction receipt through :mod:`money_ledger`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from money_ledger import MoneyInvariant, MoneyLedger  # noqa: E402


def _rows(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            yield row


def _receipt(row: dict[str, Any]) -> str:
    encoded = json.dumps(
        row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _artifact_id(row: dict[str, Any]) -> str | None:
    run_id = row.get("run_id")
    platform = row.get("platform")
    lang = row.get("lang") or row.get("language")
    if not all(isinstance(value, str) and value.strip() for value in (run_id, platform, lang)):
        return None
    return f"{run_id}__{platform}__{lang}"


def _live_artifact(row: dict[str, Any]) -> bool:
    return (
        row.get("state") == "live"
        and row.get("published") is True
        and row.get("reality_gate") == "PASS"
        and row.get("verified") is True
        and isinstance(row.get("live_url"), str)
        and isinstance(row.get("published_at"), str)
        and isinstance(row.get("artifact_sha256"), str)
    )


def _unit(metric: str, row: dict[str, Any]) -> str:
    explicit = row.get("unit")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if metric in {"price", "sales_revenue"}:
        return "JPY" if row.get("platform") == "note" else "unknown_currency"
    if metric in {"revenue", "mrr"}:
        return "USD" if row.get("platform") == "substack" else "unknown_currency"
    if metric.startswith("is_") or metric in {"published", "paywall_active"}:
        return "boolean"
    return "count"


def _numeric(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    return None


def _metric_status(row: dict[str, Any], value: Any) -> str:
    status = str(row.get("status") or "").lower()
    if status == "test":
        return "test"
    if status == "unknown" or value is None:
        return "unknown"
    if status in {"verified", "scorable"} or row.get("ok") is True:
        return "verified"
    # A numeric value fetched by the funnel/own-metrics collector is a direct
    # observation even though those older rows predate an explicit status field.
    return "verified"


def _observed_at(row: dict[str, Any]) -> str | None:
    value = row.get("measured_at") or row.get("ts")
    return value if isinstance(value, str) and value.strip() else None


def _source_url(row: dict[str, Any]) -> str | None:
    value = row.get("source_url") or row.get("live_url") or row.get("url")
    return value if isinstance(value, str) and value.startswith("https://") else None


def _reason(row: dict[str, Any], metric: str) -> str:
    specific = row.get(f"{metric}_reason")
    generic = row.get("reason")
    value = specific if isinstance(specific, str) and specific.strip() else generic
    if isinstance(value, str) and value.strip():
        return " ".join(value.split())
    return f"source returned no numeric {metric} value"


def _sync_artifacts(
    ledger: MoneyLedger, article_rows: list[dict[str, Any]]
) -> tuple[dict[str, int], dict[str, str]]:
    report = {"seen": len(article_rows), "eligible": 0, "inserted": 0, "rejected": 0}
    by_url: dict[str, str] = {}
    for row in article_rows:
        if not _live_artifact(row):
            continue
        report["eligible"] += 1
        key = _artifact_id(row)
        if key is None:
            report["rejected"] += 1
            continue
        try:
            result = ledger.register_artifact(
                artifact_id=key,
                run_id=str(row["run_id"]),
                platform=str(row["platform"]),
                lang=str(row.get("lang") or row.get("language")),
                live_url=str(row["live_url"]),
                published_at=str(row["published_at"]),
                artifact_sha256=str(row["artifact_sha256"]),
            )
        except MoneyInvariant:
            report["rejected"] += 1
            continue
        report["inserted"] += int(result["inserted"])
        by_url[str(row["live_url"])] = key
    return report, by_url


def _record_metric(
    ledger: MoneyLedger,
    *,
    row: dict[str, Any],
    metric: str,
    value: Any,
    artifact_id: str | None,
    scope: str,
) -> bool:
    numeric = _numeric(value)
    status = _metric_status(row, value)
    if status != "unknown" and numeric is None:
        return False
    observed_at = _observed_at(row)
    source_url = _source_url(row)
    if not observed_at or not source_url:
        return False
    result = ledger.record_metric(
        artifact_id=artifact_id,
        scope=scope,
        metric=metric,
        value=None if status == "unknown" else numeric,
        unit=_unit(metric, row),
        status=status,
        reason=_reason(row, metric) if status == "unknown" else None,
        observed_at=observed_at,
        source_url=source_url,
        receipt_sha256=_receipt(row),
    )
    return bool(result["inserted"])


def _sync_sales(
    ledger: MoneyLedger, rows: Iterable[dict[str, Any]], by_url: dict[str, str]
) -> dict[str, int]:
    report = {"rows": 0, "inserted": 0, "rejected": 0, "unmatched_artifact_rows": 0}
    for row in rows:
        report["rows"] += 1
        metric = row.get("metric")
        if not isinstance(metric, str) or not metric.strip():
            report["rejected"] += 1
            continue
        scope = str(row.get("scope") or "account")
        artifact_id = row.get("artifact_id") if scope == "artifact" else None
        if scope == "artifact" and not artifact_id:
            artifact_id = by_url.get(str(_source_url(row) or ""))
        if scope == "artifact" and not artifact_id:
            report["unmatched_artifact_rows"] += 1
            continue
        try:
            report["inserted"] += int(
                _record_metric(
                    ledger,
                    row=row,
                    metric=metric,
                    value=row.get("value"),
                    artifact_id=str(artifact_id) if artifact_id else None,
                    scope=scope,
                )
            )
        except MoneyInvariant:
            report["rejected"] += 1
    return report


def _sync_nested_metrics(
    ledger: MoneyLedger,
    rows: Iterable[dict[str, Any]],
    by_url: dict[str, str],
) -> dict[str, int]:
    report = {"rows": 0, "inserted": 0, "rejected": 0, "unmatched_artifact_rows": 0}
    for row in rows:
        report["rows"] += 1
        artifact_id = by_url.get(str(_source_url(row) or ""))
        if not artifact_id:
            report["unmatched_artifact_rows"] += 1
            continue
        measured = row.get("measured") if isinstance(row.get("measured"), dict) else row.get("metric")
        if not isinstance(measured, dict):
            report["rejected"] += 1
            continue
        metric_row = {**row}
        for key, value in measured.items():
            if key.endswith("_reason") or key.startswith("raw_") or key == "error":
                continue
            if not (value is None or isinstance(value, (bool, int, float))):
                continue
            if isinstance(measured.get(f"{key}_reason"), str):
                metric_row[f"{key}_reason"] = measured[f"{key}_reason"]
            try:
                report["inserted"] += int(
                    _record_metric(
                        ledger,
                        row=metric_row,
                        metric=key,
                        value=value,
                        artifact_id=artifact_id,
                        scope="artifact",
                    )
                )
            except MoneyInvariant:
                report["rejected"] += 1
    return report


def _merge_metric_reports(*reports: dict[str, int]) -> dict[str, int]:
    keys = {key for report in reports for key in report}
    return {key: sum(report.get(key, 0) for report in reports) for key in sorted(keys)}


def _sync_publication_offers(
    ledger: MoneyLedger, state_dir: Path, by_url: dict[str, str]
) -> dict[str, int]:
    report = {"seen": 0, "inserted": 0, "rejected": 0}
    for path in sorted((state_dir / "runs").glob("*/gates/publication-state.json")):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for pair_name in ("note/ja", "substack/ja", "substack/en"):
            pair = state.get("pairs", {}).get(pair_name, {})
            if pair.get("status") != "live" or not isinstance(pair.get("receipt"), dict):
                continue
            report["seen"] += 1
            receipt = pair["receipt"]
            evidence = receipt.get("evidence") if isinstance(receipt.get("evidence"), dict) else {}
            live_url = receipt.get("live_url")
            artifact_id = by_url.get(str(live_url or ""))
            common_valid = (
                state.get("run_id") == path.parents[1].name
                and artifact_id is not None
                and evidence.get("verified") is True
                and evidence.get("monetization_verified") is True
                and evidence.get("public_id") == pair.get("target")
                and isinstance(receipt.get("recorded_at"), str)
            )
            price = evidence.get("price")
            if pair_name == "note/ja":
                valid = (
                    common_valid
                    and isinstance(price, (int, float))
                    and not isinstance(price, bool)
                    and price > 0
                )
                metrics = (("price", price, "JPY"), ("paywall_active", 1, "boolean"))
            else:
                valid = (
                    common_valid
                    and evidence.get("audience") == "only_paid"
                    and evidence.get("free_preview_verified") is True
                    and evidence.get("paywall_count") == 1
                )
                metrics = (("paid_post_active", 1, "boolean"),)
            if not valid:
                report["rejected"] += 1
                continue
            for metric, value, unit in metrics:
                metric_receipt = {
                    "receipt": receipt, "metric": metric, "artifact_id": artifact_id
                }
                result = ledger.record_metric(
                    artifact_id=artifact_id,
                    scope="artifact",
                    metric=metric,
                    value=value,
                    unit=unit,
                    status="verified",
                    reason=None,
                    observed_at=receipt["recorded_at"],
                    source_url=live_url,
                    receipt_sha256=_receipt(metric_receipt),
                )
                report["inserted"] += int(result["inserted"])
    return report


def _sync_product_funnel(
    ledger: MoneyLedger, rows: Iterable[dict[str, Any]]
) -> dict[str, int]:
    values = sorted(rows, key=lambda row: str(row.get("occurred_at") or ""))
    report = {"rows": len(values), "inserted": 0, "rejected": 0}
    for row in values:
        try:
            result = ledger.record_product_event(
                event_id=row.get("event_id"),
                event_type=row.get("event_type"),
                product_id=row.get("product_id"),
                run_id=row.get("run_id"),
                artifact_id=row.get("artifact_id"),
                variant_id=row.get("variant_id"),
                click_id=row.get("click_id"),
                target_id=row.get("target_id"),
                occurred_at=row.get("occurred_at"),
                source_url=row.get("source_url"),
                receipt_sha256=row.get("receipt_sha256"),
                amount=row.get("amount"),
                currency=row.get("currency"),
                external_receipt_id=row.get("external_receipt_id"),
                counterparty=row.get("counterparty"),
                test=row.get("test"),
            )
        except (KeyError, MoneyInvariant, TypeError):
            report["rejected"] += 1
            continue
        report["inserted"] += int(result["inserted"])
    return report


def _sync_subscriptions(
    ledger: MoneyLedger, rows: Iterable[dict[str, Any]], by_url: dict[str, str]
) -> dict[str, int]:
    values = sorted(rows, key=lambda row: str(row.get("observed_at") or ""))
    report = {"rows": len(values), "inserted": 0, "rejected": 0}
    for row in values:
        platform = row.get("platform")
        stream = {
            "substack": "substack_subscription",
            "self-owned": "self_owned_subscription",
        }.get(platform)
        artifact_id = by_url.get(str(row.get("acquisition_url") or ""))
        try:
            if stream is None:
                raise MoneyInvariant("unsupported subscription platform")
            result = ledger.record_subscription(
                acquisition_artifact_id=artifact_id,
                stream=stream,
                amount=row.get("amount"),
                currency=row.get("currency"),
                interval=row.get("interval"),
                status=row.get("status"),
                external_contract_id=row.get("external_contract_id"),
                source_url=row.get("source_url"),
                test=row.get("test"),
                started_at=row.get("started_at"),
                ended_at=row.get("ended_at"),
                observed_at=row.get("observed_at"),
            )
        except (MoneyInvariant, TypeError):
            report["rejected"] += 1
            continue
        report["inserted"] += int(result["inserted"])
    return report


def _stripe_receipt_valid(row: dict[str, Any]) -> bool:
    receipt = row.get("receipt_sha256")
    if not isinstance(receipt, str) or len(receipt) != 64:
        return False
    immutable = {
        key: value
        for key, value in row.items()
        if key not in {"observed_at", "receipt_sha256"}
    }
    return hashlib.sha256(
        json.dumps(
            immutable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest() == receipt


def _sync_stripe_receipts(
    ledger: MoneyLedger, rows: Iterable[dict[str, Any]]
) -> dict[str, int]:
    order = {
        "checkout_observation": 0,
        "money": 1,
        "subscription": 2,
        "fee": 3,
        "refund": 4,
        "payout": 5,
    }
    values = sorted(
        rows,
        key=lambda row: (
            order.get(str(row.get("receipt_type")), 99),
            str(row.get("occurred_at") or row.get("started_at") or ""),
            str(row.get("external_receipt_id") or row.get("stripe_id") or ""),
        ),
    )
    report = {"rows": len(values), "inserted": 0, "observations": 0, "rejected": 0}
    for row in values:
        receipt_type = row.get("receipt_type")
        if not _stripe_receipt_valid(row):
            report["rejected"] += 1
            continue
        if receipt_type == "checkout_observation":
            report["observations"] += 1
            continue
        try:
            if receipt_type in {"money", "refund"}:
                result = ledger.record_money_event(
                    artifact_id=row.get("artifact_id"),
                    scope="artifact",
                    stream=row.get("stream"),
                    revenue_class=row.get("revenue_class"),
                    kind=row.get("kind"),
                    amount=row.get("amount"),
                    currency=row.get("currency"),
                    status=row.get("status"),
                    counterparty=row.get("counterparty"),
                    external_receipt_id=row.get("external_receipt_id"),
                    source_url=row.get("source_url"),
                    test=row.get("test"),
                    occurred_at=row.get("occurred_at"),
                    settled_at=row.get("settled_at"),
                    external_contract_id=row.get("external_contract_id"),
                )
            elif receipt_type == "subscription":
                result = ledger.record_subscription(
                    acquisition_artifact_id=row.get("artifact_id"),
                    stream=row.get("stream"),
                    amount=row.get("amount"),
                    currency=row.get("currency"),
                    interval=row.get("interval"),
                    status=row.get("status"),
                    external_contract_id=row.get("external_contract_id"),
                    source_url=row.get("source_url"),
                    test=row.get("test"),
                    started_at=row.get("started_at"),
                    ended_at=row.get("ended_at"),
                    observed_at=row.get("observed_at"),
                )
            elif receipt_type == "fee":
                with ledger._connect() as connection:
                    event = connection.execute(
                        "SELECT event_id FROM money_events WHERE external_receipt_id=?",
                        (row.get("money_external_receipt_id"),),
                    ).fetchone()
                if event is None:
                    raise MoneyInvariant("Stripe fee has no durable money event")
                result = ledger.record_fee(
                    event_id=str(event["event_id"]),
                    fee_kind=row.get("fee_kind"),
                    amount=row.get("amount"),
                    currency=row.get("currency"),
                    status=row.get("status"),
                    external_receipt_id=row.get("external_receipt_id"),
                    source_url=row.get("source_url"),
                    observed_at=row.get("observed_at"),
                    occurred_at=row.get("occurred_at"),
                    settled_at=row.get("settled_at"),
                )
            elif receipt_type == "payout":
                result = ledger.record_payout(
                    stream=row.get("stream"),
                    status=row.get("status"),
                    gross_amount=row.get("gross_amount"),
                    fee_amount=row.get("fee_amount"),
                    net_amount=row.get("net_amount"),
                    currency=row.get("currency"),
                    external_receipt_id=row.get("external_receipt_id"),
                    source_url=row.get("source_url"),
                    test=row.get("test"),
                    occurred_at=row.get("occurred_at"),
                )
            else:
                raise MoneyInvariant("unsupported Stripe receipt type")
        except (MoneyInvariant, TypeError, KeyError):
            report["rejected"] += 1
            continue
        report["inserted"] += int(result["inserted"])
    return report


def _time(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


def _generation_wall_seconds(path: Path, run_id: str) -> tuple[float, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    attempts = payload.get("attempts")
    if payload.get("run_id") != run_id or not isinstance(attempts, list) or not attempts:
        raise ValueError("generation receipt does not match the artifact run")
    if payload.get("status") == "invoking":
        raise ValueError("generation receipt is unfinished")
    seconds = 0.0
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise ValueError("generation attempt is malformed")
        started = _time(attempt.get("started_at"))
        finished = _time(attempt.get("finished_at"))
        duration = (finished - started).total_seconds()
        if duration < 0:
            raise ValueError("generation attempt ends before it starts")
        seconds += duration
    return seconds, hashlib.sha256(path.read_bytes()).hexdigest()


def _sync_learning_metrics(
    ledger: MoneyLedger,
    state_dir: Path,
    *,
    observed_at: str,
) -> dict[str, int]:
    """Project canary inputs from canonical receipts without inventing outcomes.

    The zero values below mean zero *verified receipts in this ledger*, not an
    assertion that an external platform had no unobserved activity.  Views are
    supplied separately by the authenticated first-party note stats collector.
    """

    report = {"eligible": 0, "inserted": 0, "rejected": 0}
    observed = _time(observed_at)
    with ledger._connect() as connection:
        artifacts = list(
            connection.execute(
                "SELECT artifact_id,run_id,platform,live_url,published_at "
                "FROM money_artifacts WHERE platform='note'"
            )
        )
    for artifact in artifacts:
        try:
            published = _time(artifact["published_at"])
        except ValueError:
            report["rejected"] += 1
            continue
        # The matched-canary contract compares only the first 24 hours.  Do not
        # keep manufacturing later snapshots that its reader will ignore.
        if observed < published or observed > published + timedelta(hours=24):
            continue
        generation_path = (
            state_dir / "runs" / str(artifact["run_id"]) / "gates/generation-state.json"
        )
        try:
            wall_seconds, generation_sha256 = _generation_wall_seconds(
                generation_path, str(artifact["run_id"])
            )
        except (OSError, json.JSONDecodeError, ValueError):
            report["rejected"] += 1
            continue
        with ledger._connect() as connection:
            offer = connection.execute(
                "SELECT metric,value,unit,status,observation_id FROM metric_observations "
                "WHERE artifact_id=? AND metric IN ('price','paywall_active') "
                "AND datetime(observed_at)<=datetime(?) "
                "ORDER BY datetime(observed_at) DESC",
                (artifact["artifact_id"], observed_at),
            ).fetchall()
            latest_offer = {}
            for row in offer:
                latest_offer.setdefault(str(row["metric"]), row)
            price = latest_offer.get("price")
            paywall = latest_offer.get("paywall_active")
            if (
                price is None
                or price["status"] != "verified"
                or not isinstance(price["value"], (int, float))
                or not isinstance(price["unit"], str)
                or paywall is None
                or paywall["status"] != "verified"
                or paywall["value"] != 1
            ):
                report["rejected"] += 1
                continue
            currency = str(price["unit"])
            visits = list(
                connection.execute(
                    "SELECT e.event_id,e.occurred_at,e.receipt_sha256 FROM product_funnel_events e "
                    "JOIN product_lineages l ON l.click_id=e.click_id "
                    "WHERE l.artifact_id=? AND e.event_type='visit' "
                    "AND datetime(e.occurred_at)<=datetime(?) ORDER BY e.event_id",
                    (artifact["artifact_id"], observed_at),
                )
            )
            events = list(
                connection.execute(
                    "SELECT event_id,kind,amount,currency,status,external_receipt_id,occurred_at "
                    "FROM money_events WHERE artifact_id=? AND test=0 "
                    "AND datetime(occurred_at)<=datetime(?) ORDER BY event_id",
                    (artifact["artifact_id"], observed_at),
                )
            )
            fees = list(
                connection.execute(
                    "SELECT f.fee_id,f.amount,f.currency,f.status,f.external_receipt_id,f.observed_at "
                    "FROM money_fees f JOIN money_events e ON e.event_id=f.event_id "
                    "WHERE e.artifact_id=? AND e.test=0 "
                    "AND datetime(f.observed_at)<=datetime(?) ORDER BY f.fee_id",
                    (artifact["artifact_id"], observed_at),
                )
            )
        received = [
            row for row in events
            if row["status"] == "verified_received"
            and row["kind"] != "refund"
            and row["currency"] == currency
        ]
        refunded = [
            row for row in events
            if row["status"] == "refunded"
            and row["kind"] == "refund"
            and row["currency"] == currency
        ]
        verified_fees = [
            row for row in fees
            if row["status"] == "verified" and row["currency"] == currency
        ]
        gross = sum(float(row["amount"]) for row in received)
        refunds = sum(float(row["amount"]) for row in refunded)
        fee_total = sum(float(row["amount"]) for row in verified_fees)
        values = {
            "qualified_cta_clicks": (len(visits), "count"),
            "purchases": (len(received), "count"),
            "refunds": (refunds, currency),
            "net_received": (max(0.0, gross - refunds - fee_total), currency),
            "compute_cost": (wall_seconds, "wall_seconds"),
        }
        evidence = {
            "schema_version": 1,
            "artifact_id": artifact["artifact_id"],
            "observed_at": observed_at,
            "offer_observations": sorted(
                [price["observation_id"], paywall["observation_id"]]
            ),
            "generation_state_sha256": generation_sha256,
            "visit_receipts": [dict(row) for row in visits],
            "money_receipts": [dict(row) for row in events],
            "fee_receipts": [dict(row) for row in fees],
        }
        report["eligible"] += 1
        for metric, (value, unit) in values.items():
            metric_evidence = {**evidence, "metric": metric, "value": value, "unit": unit}
            try:
                result = ledger.record_metric(
                    artifact_id=str(artifact["artifact_id"]),
                    scope="artifact",
                    metric=metric,
                    value=value,
                    unit=unit,
                    status="verified",
                    reason=None,
                    observed_at=observed_at,
                    source_url=str(artifact["live_url"]),
                    receipt_sha256=_receipt(metric_evidence),
                )
            except MoneyInvariant:
                report["rejected"] += 1
                continue
            report["inserted"] += int(result["inserted"])
    return report


def sync_state(
    *, state_dir: Path, db_path: Path, observed_at: str | None = None
) -> dict[str, Any]:
    state_dir = Path(state_dir)
    if observed_at is None:
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        observed_at = now.isoformat().replace("+00:00", "Z")
    else:
        observed_at = _time(observed_at).isoformat().replace("+00:00", "Z")
    ledger = MoneyLedger(db_path)
    article_rows = list(_rows(state_dir / "articles.jsonl"))
    artifacts, by_url = _sync_artifacts(ledger, article_rows)
    offer_receipts = _sync_publication_offers(ledger, state_dir, by_url)
    product_funnel = _sync_product_funnel(
        ledger, _rows(state_dir / "product-funnel.jsonl")
    )
    subscriptions = _sync_subscriptions(
        ledger, _rows(state_dir / "subscription-receipts.jsonl"), by_url
    )
    stripe_receipts = _sync_stripe_receipts(
        ledger, _rows(state_dir / "writer-stripe-receipts.jsonl")
    )
    metrics = _merge_metric_reports(
        _sync_sales(ledger, _rows(state_dir / "sales-ledger.jsonl"), by_url),
        _sync_nested_metrics(ledger, _rows(state_dir / "funnel.jsonl"), by_url),
        _sync_nested_metrics(ledger, _rows(state_dir / "own-metrics.jsonl"), by_url),
    )
    with ledger._connect() as connection:
        view_anchors = [
            str(row["observed_at"])
            for row in connection.execute(
                "SELECT DISTINCT m.observed_at FROM metric_observations m "
                "JOIN money_artifacts a ON a.artifact_id=m.artifact_id "
                "WHERE m.scope='artifact' AND m.metric='views' AND m.status='verified' "
                "AND a.platform='note' "
                "AND datetime(m.observed_at)>=datetime(a.published_at) "
                "AND datetime(m.observed_at)<=datetime(a.published_at,'+24 hours') "
                "ORDER BY datetime(observed_at)"
            )
            if str(row["observed_at"]) != observed_at
        ]
    learning_metrics = _merge_metric_reports(
        *(
            _sync_learning_metrics(ledger, state_dir, observed_at=anchor)
            for anchor in [*view_anchors, observed_at]
        )
    )
    return {
        "database": str(db_path),
        "artifacts": artifacts,
        "metrics": metrics,
        "learning_metrics": learning_metrics,
        "offer_receipts": offer_receipts,
        "product_funnel": product_funnel,
        "subscriptions": subscriptions,
        "stripe_receipts": stripe_receipts,
        "summary": ledger.summary(start="1970-01-01T00:00:00Z", end="2100-01-01T00:00:00Z"),
        "money_import_rule": (
            "dashboard totals are observations only; received revenue requires a separate "
            "external transaction receipt"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_state = SCRIPT_DIR.parent / "state"
    parser.add_argument("--state-dir", type=Path, default=default_state)
    parser.add_argument("--db", type=Path)
    args = parser.parse_args(argv)
    db_path = args.db or args.state_dir / "money.sqlite3"
    report = sync_state(state_dir=args.state_dir, db_path=db_path)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
