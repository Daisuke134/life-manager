#!/usr/bin/env python3
"""Read ElevenLabs PartnerStack overview metrics into a durable local receipt."""

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from websocket import WebSocketException, create_connection

from local_loop import append_unique
from provider_cli import atomic_write, cdp_call, read_json
from program_registry import refresh_partnerstack_team_access


class RevenueError(Exception):
    pass


def failure_type(error):
    """Reduce provider failures to actionable types without logging private text."""
    message = str(error)
    if isinstance(error, WebSocketException):
        return "BROWSER_TRANSPORT"
    if isinstance(error, RevenueError):
        if "authentication is required" in message:
            return "AUTH_REQUIRED"
        if "metrics did not become ready" in message:
            return "METRICS_NOT_READY"
        if "expected one provider tab" in message:
            return "TAB_INVARIANT"
        return "PROVIDER_SCHEMA_ERROR"
    if isinstance(error, OSError):
        return "RUNTIME_IO"
    return "CONTRACT"


LABELS = {
    "clicks": ("クリック数", "Clicks"),
    "signups": ("登録数", "Signups"),
    "paid_signups": ("有料会員登録", "Paid signups"),
    "conversion_rate": ("コンバージョン率", "Conversion rate"),
    "revenue_minor": ("収益", "Revenue"),
    "pending_minor": ("支払い待ちのコミッション", "Commissions pending payment"),
    "paid_minor": ("支払い済みコミッション", "Commissions paid"),
    "earnings_per_click_minor": ("クリックあたりの収益", "Earnings per click"),
}

COMMISSION_FIELDS = {
    "created_at": ("作成日", "Created at"),
    "partnership": ("パートナーシップ", "Partnership"),
    "team_member": ("チームメンバー", "Team member"),
    "offer_name": ("オファー名", "Offer name"),
    "status": ("コミッションステータス", "Commission status"),
    "customer_name": ("顧客名", "Customer name"),
    "customer_email": ("顧客のメールアドレス", "Customer email"),
    "customer_key": ("顧客キー", "Customer key"),
    "customer_location": ("お客様の所在地", "Customer location"),
    "product_key": ("プロダクトキー", "Product key"),
    "action": ("アクション", "Action"),
    "sub_id_1": ("サブID 1", "Sub ID 1"),
    "sub_id_2": ("サブID 2", "Sub ID 2"),
    "sub_id_3": ("サブID 3", "Sub ID 3"),
    "shared_id": ("共有ID", "Shared ID"),
    "clicked_at": ("日付をクリック", "Click date"),
    "click_location": ("場所をクリック", "Click location"),
    "link": ("リンク", "Link"),
    "referrer_page": ("リファラーページ", "Referrer page"),
    "landing_page": ("ランディングページ", "Landing page"),
    "commission_amount": ("コミッション", "Commission"),
    "reward_key": ("コミッション・キー", "Commission key"),
    "target_type": ("ターゲット・タイプ", "Target type"),
}

KNOWN_PLAN_BY_PLACEMENT = {
    "elevenlabs-plans-for-solo-creators": "elevenlabs-en",
    "elevenlabs-en-1": "elevenlabs-en",
    "elevenagents-for-customer-support": "elevenagents-en",
    "elevenagents-en-1": "elevenagents-en",
    "elevenlabs-text-to-speech-api-for-developers": "elevenlabs-tts-api-en",
}

KNOWN_PLACEMENT_BY_SLUG = {
    "elevenlabs-plans-for-solo-creators": "elevenlabs-en-1",
    "elevenagents-for-customer-support": "elevenagents-en-1",
}

COMMISSION_STATUS = {
    "pending": "pending",
    "hold": "pending",
    "approved": "approved",
    "scheduled": "approved",
    "declined": "reversed",
    "reversed": "reversed",
    "paid": "paid",
}

PAYOUT_FIELDS = {
    "earned_at": ("獲得済み", "Earned"),
    "program": ("プログラム", "Program"),
    "source": ("ソース", "Source"),
    "status": ("コミッションステータス", "Commission status"),
    "available_at": ("利用可能予定日", "Available on"),
    "amount": ("金額", "Amount"),
}

TAX_REQUIRED_MARKERS = (
    "納税登録が必要", "出金するための税金情報を記入する",
    "tax information is required", "complete your tax information",
)
PROVIDER_SELECTION_MARKERS = (
    "口座振替、PayPal、Stripeからお選びください",
    "choose from direct deposit, PayPal, or Stripe",
    "connect provider",
)


def payout_readiness(text):
    folded = text.casefold()
    tax_required = any(marker.casefold() in folded for marker in TAX_REQUIRED_MARKERS)
    provider_selection = any(
        marker.casefold() in folded for marker in PROVIDER_SELECTION_MARKERS
    )
    if tax_required:
        state = "PAYOUT_BLOCKED_BY_TAX_SETUP"
    elif provider_selection:
        state = "PAYMENT_PROVIDER_SELECTION_REQUIRED"
    else:
        state = "UNKNOWN"
    return {
        "payout_readiness": state,
        "tax_information_state": "REQUIRED" if tax_required else "UNKNOWN",
        "payment_provider_state": "SELECTION_REQUIRED" if provider_selection else "UNKNOWN",
    }


def parse_value(key, value):
    compact = value.strip().replace(",", "")
    if key.endswith("_minor"):
        match = re.fullmatch(r"\$([0-9]+(?:\.[0-9]{2})?)", compact)
        if not match:
            raise RevenueError("invalid USD dashboard value")
        return int(round(float(match.group(1)) * 100))
    if key == "conversion_rate":
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?%", compact):
            raise RevenueError("invalid conversion rate")
        return compact
    if not re.fullmatch(r"[0-9]+", compact):
        raise RevenueError("invalid integer dashboard value")
    return int(compact)


def parse_cards(cards):
    metrics = {}
    for key, aliases in LABELS.items():
        values = [cards[alias] for alias in aliases if alias in cards]
        if len(values) != 1:
            raise RevenueError("dashboard metric is missing or ambiguous")
        metrics[key] = parse_value(key, values[0])
    metrics.update(approved_minor=None, reversed_minor=None)
    return metrics


def extract_cards(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cards = {}
    for key, aliases in LABELS.items():
        candidates = []
        for alias in aliases:
            for index, line in enumerate(lines[:-1]):
                if line != alias:
                    continue
                try:
                    parse_value(key, lines[index + 1])
                except RevenueError:
                    continue
                candidates.append((alias, lines[index + 1]))
        if len(candidates) != 1:
            raise RevenueError("dashboard metric is missing or ambiguous")
        cards[candidates[0][0]] = candidates[0][1]
    return cards


def build_receipt(metrics, previous, observed_at):
    baseline = previous.get("baseline_metrics") or previous.get("metrics") or metrics
    delta = {}
    for key, value in metrics.items():
        base = baseline.get(key)
        delta[key] = value - base if isinstance(value, int) and isinstance(base, int) else None
    return {
        "schema_version": 1,
        "receipt_type": "PARTNERSTACK_OVERVIEW",
        "provider": "elevenlabs",
        "currency": "USD",
        "window": "last_30_days",
        "metrics": metrics,
        "metrics_sha256": hashlib.sha256(json.dumps(metrics, sort_keys=True).encode()).hexdigest(),
        "baseline_metrics": baseline,
        "baseline_observed_at": previous.get("baseline_observed_at") or previous.get("observed_at") or observed_at,
        "delta_from_baseline": delta,
        "attribution_state": "BASELINE_ONLY" if not previous else "DELTA_OBSERVABLE",
        "observed_at": observed_at,
    }


def present_fields(text, schema):
    found = []
    for key, aliases in schema.items():
        if not any(alias in text for alias in aliases):
            raise RevenueError("provider report schema is incomplete")
        found.append(key)
    return found


OPTIONAL_IDENTIFIER_KEYS = {
    "provider_settlement_id": (
        "settlement_id", "settlement_key", "settlementId",
    ),
    "provider_payout_id": (
        "payout_id", "payout_key", "payoutId", "payment_id", "withdrawal_id",
    ),
}


def _optional_identifier(row, keys):
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _currency_code(value):
    if not isinstance(value, str) or not value.strip():
        return None
    code = value.strip().upper()
    return code if re.fullmatch(r"[A-Z]{3}", code) else None


def normalize_commission_row(row, currency="USD"):
    key = row.get("reward_key")
    provider_status = row.get("reward_status")
    if not isinstance(key, str) or not key or provider_status not in COMMISSION_STATUS:
        raise RevenueError("commission identity or status is invalid")
    row_currency_value = next(
        (row.get(name) for name in ("currency", "currency_code", "currency_iso")
         if row.get(name) not in (None, "")),
        currency,
    )
    row_currency = _currency_code(row_currency_value)
    if row_currency is None:
        raise RevenueError("commission currency is invalid")
    try:
        minor_decimal = Decimal(str(row["commission_amount"])) * 100
    except (KeyError, InvalidOperation, ValueError):
        raise RevenueError("commission amount is invalid") from None
    if minor_decimal != minor_decimal.to_integral_value() or minor_decimal < 0:
        raise RevenueError("commission amount is invalid")
    gross_minor = int(minor_decimal)
    status = COMMISSION_STATUS[provider_status]
    reversal_minor = gross_minor if status == "reversed" else 0
    normalized = {
        "provider_transaction_id": key,
        "provider_status": provider_status,
        "status": status,
        "currency": row_currency,
        "gross_commission_minor": gross_minor,
        "reversal_minor": reversal_minor,
        "net_commission_minor": gross_minor - reversal_minor,
        "created_at": row.get("created_at_date"),
        "offer": row.get("reward_description"),
        "target_type": row.get("target_type"),
        "action": row.get("action_external_type"),
        "attribution": {
            "sub_id_1": row.get("sub_id_1"),
            "sub_id_2": row.get("sub_id_2"),
            "sub_id_3": row.get("sub_id_3"),
            "shared_id": row.get("shared_id"),
            "clicked_at": row.get("click_created_at_date"),
            "link_sha256": hash_optional(row.get("link_path")),
            "referrer_sha256": hash_optional(row.get("referral_source")),
            "landing_page_sha256": hash_optional(row.get("link_destination_path")),
        },
    }
    for field, keys in OPTIONAL_IDENTIFIER_KEYS.items():
        normalized[field] = _optional_identifier(row, keys)
    return normalized


def hash_optional(value):
    return hashlib.sha256(value.encode()).hexdigest() if isinstance(value, str) and value else None


def link_fingerprints(value):
    if not isinstance(value, str) or not value:
        return set()
    parsed = urlparse(value)
    values = {value}
    if parsed.scheme == "https" and parsed.hostname:
        values.update({parsed.hostname + parsed.path, parsed.path})
    return {hashlib.sha256(item.encode()).hexdigest() for item in values if item}


def _nonnegative_count(value, label):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RevenueError(f"PartnerStack {label} is invalid")
    return value


def aggregate_link_rows(rows, candidate, secondary_grouping):
    matches = [
        row for row in rows
        if isinstance(row, dict)
        and link_fingerprints(row.get("link_path")).intersection(
            candidate["link_fingerprints"]
        )
    ]
    if not matches:
        return {
            "click_count": 0,
            "unique_click_count": 0,
            "unique_click_count_state": "OBSERVED",
            "link_path_sha256": None,
            "row_count": 0,
            "aggregation_state": "NO_MATCH",
        }
    row_fingerprints = [link_fingerprints(row.get("link_path")) for row in matches]
    common_fingerprints = set.intersection(*row_fingerprints)
    if len(matches) > 1:
        months = [row.get("click_created_at_month") for row in matches]
        if (
            secondary_grouping != "click_created_at_month"
            or not common_fingerprints
            or not all(isinstance(month, str) and month for month in months)
            or len(set(months)) != len(months)
        ):
            raise RevenueError("PartnerStack link attribution is ambiguous")
    click_count = sum(
        _nonnegative_count(row.get("click_count"), "click count") for row in matches
    )
    raw_unique = [row.get("unique_click_count") for row in matches]
    unique_valid = all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
        for value in raw_unique
    )
    unique_count = sum(raw_unique) if unique_valid else None
    return {
        "click_count": click_count,
        "unique_click_count": unique_count,
        "unique_click_count_state": (
            "OBSERVED_MONTH_BUCKET_SUM" if unique_valid and len(matches) > 1
            else "OBSERVED" if unique_valid else "UNKNOWN"
        ),
        "link_path_sha256": hash_optional(matches[0].get("link_path")),
        "row_count": len(matches),
        "aggregation_state": (
            "MONTH_BUCKETS_AGGREGATED" if len(matches) > 1 else "SINGLE_ROW"
        ),
    }


def link_count_delta(current, previous, current_window, previous_window):
    if previous is None:
        return {"baseline": current, "delta": 0, "state": "BASELINE_ESTABLISHED"}
    _nonnegative_count(previous, "previous count")
    if current_window != previous_window:
        return {"baseline": None, "delta": None, "state": "WINDOW_CHANGED"}
    delta = current - previous
    if delta < 0:
        raise RevenueError("PartnerStack click count regressed")
    return {"baseline": previous, "delta": delta, "state": "COMPARABLE"}


def placement_candidates(state):
    candidates = {}
    for path in sorted((state / "program-links").glob("*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        placement_id = row.get("placement")
        if row.get("state") == "VERIFIED" and placement_id:
            candidates[placement_id] = {
                "placement_id": placement_id,
                "public_url": None,
                "provider_link_key": row.get("provider_link_key"),
                "tracking_custom_link_id": row.get("tracking_custom_link_id"),
                "link_fingerprints": row.get("link_fingerprints", []),
            }
    campaigns_by_slug = {}
    for path in sorted((state / "campaign-publications").glob("*.json")):
        try:
            campaign = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (
            campaign.get("state") not in
            {"MATERIALIZED", "OWNED_NOT_LIVE", "OWNED_LIVE", "X_LIVE"}
            or not campaign.get("slug")
            or not campaign.get("placement_id")
        ):
            continue
        campaigns_by_slug[campaign["slug"]] = campaign
        placement_id = campaign.get("placement_id")
        if placement_id in candidates:
            candidates[placement_id]["public_url"] = campaign.get("owned_url")
            candidates[placement_id]["opportunity_decision"] = campaign.get(
                "opportunity_decision"
            )
            candidates[placement_id]["experiment"] = campaign.get("experiment")
            candidates[placement_id]["plan_id"] = campaign.get("plan_id")
    content_root = state / "content"
    publication_root = state / "owned-publications"
    for content_path in sorted(content_root.glob("*.json")) if content_root.is_dir() else []:
        content = json.loads(content_path.read_text(encoding="utf-8"))
        slug = content.get("slug")
        publication_path = publication_root / f"{slug}.json"
        if not slug or not publication_path.is_file():
            continue
        publication = json.loads(publication_path.read_text(encoding="utf-8"))
        links = content.get("readback_links", [])
        if publication.get("state") != "LIVE" or len(links) != 1:
            continue
        parsed = urlparse(links[0])
        if parsed.scheme != "https" or parsed.hostname != "try.elevenlabs.io":
            continue
        campaign = campaigns_by_slug.get(slug, {})
        placement_id = campaign.get("placement_id") or KNOWN_PLACEMENT_BY_SLUG.get(slug, slug)
        prior = candidates.get(placement_id, {})
        dedicated = bool(prior.get("provider_link_key"))
        candidates[placement_id] = {
            "placement_id": placement_id,
            "public_url": publication.get("public_url"),
            "provider_link_key": prior.get("provider_link_key"),
            "tracking_custom_link_id": prior.get("tracking_custom_link_id"),
            "link_fingerprints": sorted(
                set(prior.get("link_fingerprints", []))
                if dedicated else link_fingerprints(links[0])
            ),
            "opportunity_decision": campaign.get("opportunity_decision"),
            "experiment": campaign.get("experiment"),
            "plan_id": campaign.get("plan_id"),
        }
    return list(candidates.values())


def _json_rows(path):
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def build_placement_ledger(state):
    candidates = {row["placement_id"]: row for row in placement_candidates(state)}
    try:
        link_report = json.loads((
            state / "provider-reports" / "partnerstack-links" / "latest.json"
        ).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        link_report = {}
    link_rows = {
        row.get("placement_id"): row for row in link_report.get("placements", [])
        if isinstance(row, dict) and row.get("placement_id")
    }
    try:
        dev_metrics = json.loads((
            state / "distribution-metrics" / "devto.json"
        ).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dev_metrics = {}
    dev_rows = {
        row.get("placement_id"): row for row in dev_metrics.get("articles", [])
        if isinstance(row, dict) and row.get("placement_id")
    }
    latest_transactions = latest_commission_transitions(state)
    usage_rows = _json_rows(state / "telemetry" / "agent-usage.jsonl")
    rows = []
    for placement_id, candidate in sorted(candidates.items()):
        link = link_rows.get(placement_id, {})
        dev = dev_rows.get(placement_id, {})
        transactions = [
            row for row in latest_transactions.values()
            if (row.get("placement") or {}).get("state") == "MATCHED"
            and (row.get("placement") or {}).get("placement_id") == placement_id
        ]
        approved = {}
        for row in transactions:
            if row.get("status") not in {"approved", "paid"}:
                continue
            currency = row.get("currency") or "UNKNOWN"
            approved[currency] = approved.get(currency, 0) + int(
                row.get("net_commission_minor") or 0
            )
        plan_id = candidate.get("plan_id") or KNOWN_PLAN_BY_PLACEMENT.get(placement_id)
        placement_usage = [
            row for row in usage_rows
            if plan_id and str(row.get("task_label", "")).startswith(f"{plan_id}-")
        ]
        measured_usage = [
            row for row in placement_usage
            if row.get("measurement") == "provider_reported"
            and isinstance((row.get("tokens") or {}).get("total"), int)
        ]
        estimated_costs = [
            float(row["provider_cost_usd"]) for row in placement_usage
            if row.get("cost_basis") == "api_equivalent_estimate"
            and isinstance(row.get("provider_cost_usd"), (int, float))
            and not isinstance(row.get("provider_cost_usd"), bool)
        ]
        actual_costs = [
            float(row["provider_cost_usd"]) for row in placement_usage
            if row.get("cost_basis") == "actual_billed"
            and isinstance(row.get("provider_cost_usd"), (int, float))
            and not isinstance(row.get("provider_cost_usd"), bool)
        ]
        page_views = dev.get("page_views_count")
        per_thousand = (
            {
                currency: round(minor * 1000 / page_views)
                for currency, minor in approved.items()
            }
            if isinstance(page_views, int) and page_views > 0 else None
        )
        rows.append({
            "placement_id": placement_id,
            "plan_id": plan_id,
            "opportunity_decision": candidate.get("opportunity_decision"),
            "experiment": candidate.get("experiment"),
            "public_url": candidate.get("public_url"),
            "provider_link_key": candidate.get("provider_link_key"),
            "exposure": {
                "x_impressions": None,
                "x_impressions_state": "UNKNOWN",
                "owned_page_visits": None,
                "owned_page_visits_state": "UNKNOWN",
                "devto_page_views": dev.get("page_views_count"),
                "devto_reactions": dev.get("public_reactions_count"),
                "devto_comments": dev.get("comments_count"),
                "observed_at": dev_metrics.get("observed_at") if dev else None,
            },
            "provider_clicks": {
                "count": link.get("current_click_count"),
                "delta": link.get("delta_click_count"),
                "unique_count": link.get("current_unique_click_count"),
                "unique_delta": link.get("delta_unique_click_count"),
                "unique_state": link.get("unique_click_count_state", "UNKNOWN"),
                "observed_at": link_report.get("observed_at") if link else None,
            },
            "commission": {
                "transaction_count": len(transactions),
                "status_counts": {
                    status: sum(row.get("status") == status for row in transactions)
                    for status in ("pending", "approved", "paid", "reversed")
                },
                "approved_or_paid_net_minor_by_currency": approved,
            },
            "cost": {
                "actual_cash_state": "UNKNOWN",
                "actual_cash_amount_by_currency": None,
                "model_actual_billed_usd": (
                    round(sum(actual_costs), 8)
                    if placement_usage and len(actual_costs) == len(placement_usage)
                    else None
                ),
                "tool_cash_state": "UNKNOWN",
                "channel_cash_state": "UNKNOWN",
                "model_usage": {
                    "attempt_count": len(placement_usage),
                    "provider_measured_attempt_count": len(measured_usage),
                    "total_tokens": sum(
                        int(row["tokens"]["total"]) for row in measured_usage
                    ),
                    "api_equivalent_estimate_usd": (
                        round(sum(estimated_costs), 8) if estimated_costs else None
                    ),
                    "api_equivalent_is_not_invoice": True,
                },
            },
            "unit_economics": {
                "approved_or_paid_net_per_1000_devto_views_minor_by_currency": per_thousand,
                "exposure_denominator_state": (
                    "OBSERVED" if isinstance(page_views, int) and page_views > 0
                    else "INSUFFICIENT_DENOMINATOR"
                ),
                "actual_net_profit_state": "UNKNOWN_COST",
                "actual_net_profit_minor_by_currency": None,
            },
        })
    core = {
        "schema_version": 1,
        "receipt_type": "AFFILIATE_PLACEMENT_LEDGER",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "placements": rows,
    }
    core["ledger_sha256"] = hashlib.sha256(json.dumps(
        core, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    atomic_write(state / "placement-ledger.json", core)
    return core


ROLLING_NET_THRESHOLD_USD_MINOR = 1_000_000


def parse_timestamp(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def latest_commission_transitions(state):
    latest = {}
    for index, row in enumerate(_json_rows(state / "commission-ledger.jsonl")):
        provider = row.get("provider") or "unknown"
        transaction_id = row.get("provider_transaction_id")
        if not isinstance(transaction_id, str) or not transaction_id:
            continue
        observed = parse_timestamp(row.get("observed_at"))
        key = (observed or datetime.min.replace(tzinfo=timezone.utc), index)
        identity = (provider, transaction_id)
        prior = latest.get(identity)
        if prior is None or key > prior[0]:
            latest[identity] = (key, row)
    # The provider namespace is part of the replay identity. Two admitted
    # programs may legitimately expose the same transaction key; collapsing on
    # the key alone would silently discard one provider's economic row.
    return {identity: value for identity, (_, value) in latest.items()}


def build_rolling_net(state, now=None):
    """Write a fail-closed rolling net receipt from immutable economic inputs.

    Approved and paid are lifecycle states of one transaction, not additive
    revenue. A missing real-bill ledger, incomplete cost-window coverage,
    missing FX, missing placement join, or missing economic time keeps a
    qualifying net result unknown; clicks and model estimates never enter this
    calculation.
    """
    state = Path(state).expanduser()
    window_end = now or datetime.now(timezone.utc)
    if window_end.tzinfo is None:
        window_end = window_end.replace(tzinfo=timezone.utc)
    window_end = window_end.astimezone(timezone.utc)
    window_start = window_end - timedelta(days=30)
    transitions = latest_commission_transitions(state)
    ledger_path = state / "commission-ledger.jsonl"
    source_ledger_sha256 = (
        hashlib.sha256(ledger_path.read_bytes()).hexdigest()
        if ledger_path.is_file() else None
    )
    placement_ledger_path = state / "placement-ledger.json"
    placement_ledger_sha256 = (
        hashlib.sha256(placement_ledger_path.read_bytes()).hexdigest()
        if placement_ledger_path.is_file() else None
    )
    status_counts = {status: 0 for status in ("pending", "approved", "paid", "reversed")}
    approved_net = {}
    reversal_totals = {}
    unknown_time_count = 0
    unknown_fx_currencies = set()
    in_window_rows = 0
    unjoined_economic_rows = 0
    economic_rows = []
    for row in transitions.values():
        status = row.get("status")
        # A reversal can be reported long after the original commission was
        # created. Use the observation time for that lifecycle transition so a
        # rolling window cannot silently miss a late clawback.
        event_time = (
            parse_timestamp(row.get("observed_at")) or parse_timestamp(row.get("created_at"))
            if status == "reversed" else
            parse_timestamp(row.get("created_at")) or parse_timestamp(row.get("observed_at"))
        )
        if event_time is None:
            unknown_time_count += 1
            continue
        if not window_start <= event_time <= window_end:
            continue
        in_window_rows += 1
        if status in status_counts:
            status_counts[status] += 1
        placement = row.get("placement") if isinstance(row.get("placement"), dict) else {}
        placement_id = placement.get("placement_id")
        joined = placement.get("state") == "MATCHED" and isinstance(placement_id, str) and bool(placement_id)
        economic_rows.append({
            "provider": row.get("provider") or "unknown",
            "provider_transaction_id": row.get("provider_transaction_id"),
            "placement_id": placement_id if joined else None,
            "placement_join_state": "MATCHED" if joined else "UNMATCHED",
            "status": status,
            "currency": row.get("currency"),
            "gross_commission_minor": row.get("gross_commission_minor"),
            "reversal_minor": row.get("reversal_minor"),
            "net_commission_minor": row.get("net_commission_minor"),
        })
        currency = row.get("currency") or "UNKNOWN"
        reversal = int(row.get("reversal_minor") or 0)
        if status in {"approved", "paid", "reversed"} and not joined:
            unjoined_economic_rows += 1
            continue
        if reversal:
            reversal_totals[currency] = reversal_totals.get(currency, 0) + reversal
        if status in {"approved", "paid", "reversed"} and currency != "USD":
            unknown_fx_currencies.add(currency)
        if status not in {"approved", "paid"}:
            continue
        net = int(row.get("net_commission_minor") or 0)
        approved_net[currency] = approved_net.get(currency, 0) + net

    cost_rows = _json_rows(state / "cost-ledger.jsonl")
    cost_totals = {}
    invalid_cost_rows = 0
    for row in cost_rows:
        if row.get("cost_basis") != "actual_billed":
            invalid_cost_rows += 1
            continue
        cost_time = parse_timestamp(
            row.get("occurred_at") or row.get("created_at") or row.get("observed_at")
        )
        if cost_time is None:
            invalid_cost_rows += 1
            continue
        if not window_start <= cost_time <= window_end:
            continue
        amount = row.get("amount_minor")
        currency = row.get("currency")
        if not isinstance(amount, int) or amount < 0 or not isinstance(currency, str) or not currency:
            invalid_cost_rows += 1
            continue
        cost_totals[currency] = cost_totals.get(currency, 0) + amount
        if currency != "USD":
            unknown_fx_currencies.add(currency)
    coverage_path = state / "cost-ledger-coverage.json"
    try:
        coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        coverage = {}
    coverage_start = parse_timestamp(coverage.get("window_start"))
    coverage_end = parse_timestamp(coverage.get("window_end"))
    cost_coverage_state = (
        "COMPLETE"
        if coverage.get("coverage_state") == "COMPLETE"
        and coverage_start is not None
        and coverage_end is not None
        and coverage_start <= window_start
        and coverage_end >= window_end
        else "UNKNOWN"
    )
    has_qualifying_money = bool(approved_net or reversal_totals)
    cost_unknown_reasons = []
    if has_qualifying_money and not cost_rows:
        cost_unknown_reasons.append("actual_billed_cost_ledger_missing")
    if has_qualifying_money and invalid_cost_rows:
        cost_unknown_reasons.append("actual_billed_cost_row_invalid")
    if has_qualifying_money and cost_coverage_state != "COMPLETE":
        cost_unknown_reasons.append("actual_billed_cost_coverage_unknown")
    if has_qualifying_money and unjoined_economic_rows:
        cost_unknown_reasons.append("economic_row_unjoined_to_placement")
    cost_state = "KNOWN" if has_qualifying_money and not cost_unknown_reasons else "UNKNOWN"
    if not has_qualifying_money:
        cost_state = "UNKNOWN"
    fx_state = "KNOWN" if not unknown_fx_currencies else "UNKNOWN"
    unknown_reasons = []
    if unknown_time_count:
        unknown_reasons.append("economic_time_missing")
    if unknown_fx_currencies:
        unknown_reasons.append("fx_missing:" + ",".join(sorted(unknown_fx_currencies)))
    unknown_reasons.extend(cost_unknown_reasons)
    if not transitions:
        money_state = "NO_TRANSACTIONS"
    elif not in_window_rows:
        money_state = "NO_TRANSACTIONS_IN_WINDOW"
    elif not has_qualifying_money:
        money_state = "OBSERVED_NON_MONEY_STATES"
    else:
        money_state = "TRANSACTIONS_OBSERVED"
    net_state = "UNKNOWN" if has_qualifying_money and unknown_reasons else (
        "KNOWN" if has_qualifying_money else "NO_APPROVED_OR_PAID_ROWS"
    )
    usd_net_minor = approved_net.get("USD", 0) - cost_totals.get("USD", 0)
    if net_state != "KNOWN" or unknown_fx_currencies or any(currency != "USD" for currency in approved_net):
        usd_net_minor_value = None
    else:
        usd_net_minor_value = usd_net_minor
    threshold_state = (
        "PASS" if usd_net_minor_value is not None and usd_net_minor_value >= ROLLING_NET_THRESHOLD_USD_MINOR
        else "UNKNOWN" if net_state == "UNKNOWN" or unknown_fx_currencies
        else "NOT_REACHED"
    )
    receipt = {
        "schema_version": 1,
        "receipt_type": "AFFILIATE_ROLLING_NET",
        "provider": "portfolio",
        "window": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
            "days": 30,
        },
        "money_state": money_state,
        "source_transition_count": len(transitions),
        "in_window_transition_count": in_window_rows,
        "source_ledger_sha256": source_ledger_sha256,
        "placement_ledger_sha256": placement_ledger_sha256,
        "economic_rows": economic_rows,
        "unjoined_economic_transition_count": unjoined_economic_rows,
        "status_counts": status_counts,
        "approved_or_paid_net_minor_by_currency": approved_net,
        "reversal_minor_by_currency": reversal_totals,
        "known_real_cost_minor_by_currency": cost_totals,
        "cost_state": cost_state,
        "cost_coverage_state": cost_coverage_state,
        "fx_state": fx_state,
        "unknown_reasons": sorted(set(unknown_reasons)),
        "net_state": net_state,
        "approved_or_paid_net_usd": (
            usd_net_minor_value / 100 if usd_net_minor_value is not None else None
        ),
        "threshold_usd": 10_000,
        "threshold_state": threshold_state,
        "observed_at": window_end.isoformat(),
    }
    receipt["receipt_sha256"] = hashlib.sha256(json.dumps(
        receipt, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    atomic_write(state / "rolling-net.json", receipt)
    return receipt


def capture_link_performance(args):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RevenueError("Playwright is unavailable") from error
    rows = None
    report_url = None
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(
            f"http://{args.cdp_host}:{args.cdp_port}"
        )
        pages = [page for context in browser.contexts for page in context.pages]
        if len(pages) != 1:
            raise RevenueError("expected one provider tab")
        page = pages[0]
        try:
            page.goto(
                "https://dash.partnerstack.com/reporting/link_performance",
                wait_until="domcontentloaded", timeout=20_000,
            )
            auth_refresh = refresh_partnerstack_team_access(page)
            if auth_refresh["state"] in {"AUTH_REQUIRED", "TEAM_CONTEXT_MISSING"}:
                raise RevenueError("PartnerStack authentication is required")
            if auth_refresh["state"] != "REFRESHED":
                raise RevenueError("PartnerStack team context refresh failed")
            page.get_by_text(re.compile(r"^(リンク追跡レポート|Link tracking report)$")).first.wait_for(
                timeout=15_000
            )
            page.evaluate(
                """() => [...document.querySelectorAll('button')]
                .find(element => (element.innerText || '').trim() === 'グループ別' ||
                  (element.innerText || '').trim() === 'Group by').click()"""
            )
            page.evaluate(
                """() => [...document.querySelectorAll('button')]
                .find(element => ['ランディングページ','Landing page']
                  .includes((element.innerText || '').trim())).click()"""
            )
            with page.expect_response(
                lambda response: (
                    "/api/v2/stats/click_report/" in response.url
                    and not response.url.split("?", 1)[0].endswith("/summary")
                    and "primary_grouping=link_path" in response.url
                ), timeout=15_000,
            ) as response_info:
                selected = page.evaluate(
                    """() => { const element = [...document.querySelectorAll('*')]
                    .find(node => node.children.length === 0 &&
                      ['リンク','Link'].includes((node.innerText || '').trim()) &&
                      node.getBoundingClientRect().width);
                    if (!element) return false; element.click(); return true; }"""
                )
                if not selected:
                    raise RevenueError("link grouping is unavailable")
            response = response_info.value
            rows = response.json()
            report_url = response.url
        finally:
            page.goto("https://elevenlabs.io/app/home", wait_until="domcontentloaded", timeout=20_000)
    if not isinstance(rows, list):
        raise RevenueError("PartnerStack link report is not a list")
    query = parse_qs(urlparse(report_url).query)
    window = {key: query.get(key, [None])[0] for key in ("start_date", "end_date")}
    secondary_grouping = query.get("secondary_grouping", [None])[0]
    state = args.state.expanduser()
    previous_path = state / "provider-reports" / "partnerstack-links" / "latest.json"
    try:
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    previous_counts = {
        row.get("placement_id"): row.get("current_click_count")
        for row in previous.get("placements", []) if isinstance(row, dict)
        and row.get("placement_id")
    }
    previous_unique_counts = {
        row.get("placement_id"): row.get("current_unique_click_count")
        for row in previous.get("placements", []) if isinstance(row, dict)
        and row.get("placement_id")
    }
    candidates = [
        candidate for candidate in placement_candidates(state)
        if candidate.get("provider_link_key")
    ]
    placements = []
    appended = 0
    latest_transition = None
    for candidate in candidates:
        aggregate = aggregate_link_rows(rows, candidate, secondary_grouping)
        current = aggregate["click_count"]
        click_delta = link_count_delta(
            current, previous_counts.get(candidate["placement_id"]),
            window, previous.get("window"),
        )
        baseline = click_delta["baseline"]
        delta = click_delta["delta"]
        current_unique = aggregate["unique_click_count"]
        baseline_unique = None
        unique_delta = None
        unique_delta_state = "UNKNOWN"
        if current_unique is not None:
            unique_result = link_count_delta(
                current_unique,
                previous_unique_counts.get(candidate["placement_id"]),
                window, previous.get("window"),
            )
            baseline_unique = unique_result["baseline"]
            unique_delta = unique_result["delta"]
            unique_delta_state = unique_result["state"]
        row = {
            "provider_link_key": candidate.get("provider_link_key"),
            "placement_id": candidate["placement_id"],
            "public_url": candidate.get("public_url"),
            "link_path_sha256": aggregate["link_path_sha256"],
            "baseline_click_count": baseline,
            "current_click_count": current,
            "delta_click_count": delta,
            "delta_click_count_state": click_delta["state"],
            "baseline_unique_click_count": baseline_unique,
            "current_unique_click_count": current_unique,
            "delta_unique_click_count": unique_delta,
            "delta_unique_click_count_state": unique_delta_state,
            "unique_click_count_state": aggregate["unique_click_count_state"],
            "provider_row_count": aggregate["row_count"],
            "aggregation_state": aggregate["aggregation_state"],
        }
        placements.append(row)
        if (
            isinstance(delta, int) and delta > 0
            and row["provider_link_key"] and row["link_path_sha256"]
        ):
            identity = {
                "provider": "elevenlabs", "provider_link_key": row["provider_link_key"],
                "link_path_sha256": row["link_path_sha256"],
                "placement_id": row["placement_id"],
                "observed_click_count": current, "window": window,
            }
            transition_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            transition = {
                "schema_version": 1, "receipt_type": "CLICK_TRANSITION",
                "transition_id": transition_id, **identity,
                "delta_click_count": delta, "public_url": row["public_url"],
                "observed_unique_click_count": current_unique,
                "delta_unique_click_count": unique_delta,
                "observed_at": datetime.now(timezone.utc).isoformat(),
            }
            if append_unique(state / "click-ledger.jsonl", transition, ("transition_id",)):
                appended += 1
                latest_transition = transition
    observed_at = datetime.now(timezone.utc).isoformat()
    artifact = {"rows": rows, "report_url": report_url, "observed_at": observed_at}
    artifact_hash = hashlib.sha256(json.dumps(artifact, sort_keys=True).encode()).hexdigest()
    atomic_write(previous_path.parent / f"{artifact_hash}.json", artifact)
    receipt = {
        "schema_version": 1, "receipt_type": "PARTNERSTACK_LINK_PERFORMANCE",
        "provider": "elevenlabs", "window": window, "placements": placements,
        "provider_row_count": len(rows), "rendered_artifact_sha256": artifact_hash,
        "auth_refresh_state": auth_refresh["state"],
        "auth_refresh_http": auth_refresh.get("http"),
        "appended_transitions": appended,
        "latest_transition": latest_transition,
        "observed_at": observed_at,
    }
    atomic_write(previous_path, receipt)
    return receipt


def resolve_attribution(raw_row, candidates):
    ids = {
        value for key in ("sub_id_1", "sub_id_2", "sub_id_3", "shared_id")
        if isinstance((value := raw_row.get(key)), str) and value
    }
    row_links = link_fingerprints(raw_row.get("link_path"))
    matches = []
    for candidate in candidates:
        basis = []
        if candidate["placement_id"] in ids:
            basis.append("SUB_ID")
        if row_links.intersection(candidate["link_fingerprints"]):
            basis.append("LINK_FINGERPRINT")
        if basis:
            matches.append((candidate, basis))
    if len(matches) != 1:
        return {"state": "UNMATCHED" if not matches else "AMBIGUOUS", "placement_id": None, "public_url": None, "match_basis": []}
    candidate, basis = matches[0]
    return {
        "state": "MATCHED",
        "placement_id": candidate["placement_id"],
        "public_url": candidate["public_url"],
        "match_basis": basis,
    }


def build_transition(row, source_hash, observed_at):
    identity = {
        "provider": "elevenlabs",
        "provider_transaction_id": row["provider_transaction_id"],
        "provider_status": row["provider_status"],
        "gross_commission_minor": row["gross_commission_minor"],
        "reversal_minor": row["reversal_minor"],
        "net_commission_minor": row["net_commission_minor"],
        "currency": row["currency"],
        "provider_settlement_id": row.get("provider_settlement_id"),
        "provider_payout_id": row.get("provider_payout_id"),
        # Attribution is part of the replay identity. A provider can expose a
        # reward before its sub-ID/link fingerprint is present; omitting this
        # binding would make the later exact placement match look like a
        # duplicate and permanently strand the economic row as UNMATCHED.
        "attribution": row["attribution"],
        "placement": row["placement"],
    }
    transition_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return {
        "schema_version": 1,
        "receipt_type": "COMMISSION_TRANSITION",
        "transition_id": transition_id,
        **identity,
        "source_artifact_sha256": source_hash,
        "status": row["status"],
        "created_at": row["created_at"],
        "offer": row["offer"],
        "target_type": row["target_type"],
        "action": row["action"],
        "attribution": row["attribution"],
        "placement": row["placement"],
        "observed_at": observed_at,
    }


def navigate_text(ws, request_id, url, ready_markers):
    cdp_call(ws, request_id, "Page.navigate", {"url": url})
    expression = "({url:location.href,text:(document.body&&document.body.innerText)||''})"
    for offset in range(1, 61):
        result = cdp_call(ws, request_id + offset, "Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
        })
        page = result.get("result", {}).get("value", {})
        if any(marker in page.get("text", "") for marker in ready_markers):
            return page
        if "Sign in to PartnerStack" in page.get("text", ""):
            raise RevenueError("PartnerStack authentication is required")
        time.sleep(0.5)
    raise RevenueError("PartnerStack report did not become ready")


def cdp_call_collect(ws, request_id, method, params, events):
    ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
    while True:
        message = json.loads(ws.recv())
        if message.get("method"):
            events.append(message)
        if message.get("id") == request_id:
            if "error" in message:
                raise RevenueError(f"CDP {method} failed")
            return message.get("result", {})


def capture_commission_rows(args):
    pages = [item for item in read_json(f"http://{args.cdp_host}:{args.cdp_port}/json/list") if item.get("type") == "page"]
    if len(pages) != 1:
        raise RevenueError(f"expected one provider tab, found {len(pages)}")
    ws = create_connection(
        f"ws://{args.cdp_host}:{args.cdp_port}/devtools/page/{pages[0]['id']}",
        timeout=20, max_size=None, suppress_origin=True,
    )
    events = []
    try:
        cdp_call_collect(ws, 1, "Network.enable", {}, events)
        cdp_call_collect(ws, 2, "Page.enable", {}, events)
        cdp_call_collect(ws, 3, "Page.navigate", {
            "url": "https://dash.partnerstack.com/reporting/commission_performance",
        }, events)
        request_id = None
        for attempt in range(20):
            time.sleep(0.5)
            cdp_call_collect(ws, 10 + attempt, "Runtime.evaluate", {
                "expression": "document.readyState", "returnByValue": True,
            }, events)
            for event in events:
                if event.get("method") != "Network.responseReceived":
                    continue
                response = event.get("params", {}).get("response", {})
                url = response.get("url", "").split("?", 1)[0]
                if "/api/v2/stats/commission_report/" in url and not url.endswith("/summary"):
                    request_id = event["params"]["requestId"]
            if request_id:
                break
        if not request_id:
            raise RevenueError("PartnerStack commission response was not observed")
        result = cdp_call_collect(ws, 100, "Network.getResponseBody", {"requestId": request_id}, events)
        rows = json.loads(result.get("body", ""))
        if not isinstance(rows, list):
            raise RevenueError("PartnerStack commission response is not a list")
        return rows
    finally:
        try:
            cdp_call_collect(ws, 200, "Page.navigate", {"url": "https://elevenlabs.io/app/home"}, events)
        finally:
            ws.close()


def capture_reports(args):
    pages = [item for item in read_json(f"http://{args.cdp_host}:{args.cdp_port}/json/list") if item.get("type") == "page"]
    if len(pages) != 1:
        raise RevenueError(f"expected one provider tab, found {len(pages)}")
    ws = create_connection(
        f"ws://{args.cdp_host}:{args.cdp_port}/devtools/page/{pages[0]['id']}",
        timeout=20, max_size=None, suppress_origin=True,
    )
    try:
        cdp_call(ws, 1, "Page.enable")
        payout_summary = navigate_text(
            ws, 10, "https://dash.partnerstack.com/payouts",
            ("利用可能資金合計", "Total available funds"),
        )
        commissions = navigate_text(
            ws, 100, "https://dash.partnerstack.com/reporting/commission_performance",
            ("コミッション・レポート", "Commission report"),
        )
        payouts = navigate_text(
            ws, 200, "https://dash.partnerstack.com/payouts/rewards",
            ("コミッションおよび引き出し", "Commissions and withdrawals"),
        )
    finally:
        try:
            cdp_call(ws, 300, "Page.navigate", {"url": "https://elevenlabs.io/app/home"})
        finally:
            ws.close()
    commission_rows = capture_commission_rows(args)
    observed_at = datetime.now(timezone.utc).isoformat()
    normalized_rows = [normalize_commission_row(row) for row in commission_rows]
    artifact = {
        "schema_version": 1,
        "receipt_type": "PARTNERSTACK_RENDERED_REPORT_ARTIFACT",
        "observed_at": observed_at,
        "commission_url": commissions["url"],
        "commission_text": commissions["text"],
        "commission_rows": commission_rows,
        "normalized_commissions": normalized_rows,
        "payout_url": payouts["url"],
        "payout_text": payouts["text"],
        "payout_summary_url": payout_summary["url"],
        "payout_summary_text": payout_summary["text"],
    }
    artifact_hash = hashlib.sha256(json.dumps(artifact, sort_keys=True).encode()).hexdigest()
    state = args.state.expanduser()
    artifact_path = state / "provider-reports" / "partnerstack" / f"{artifact_hash}.json"
    atomic_write(artifact_path, artifact)
    receipt = {
        "schema_version": 1,
        "receipt_type": "PARTNERSTACK_REPORT_CAPTURE",
        "provider": "elevenlabs",
        "currency_display": "USD",
        "commission_fields": present_fields(commissions["text"], COMMISSION_FIELDS),
        "payout_fields": present_fields(payouts["text"], PAYOUT_FIELDS),
        "generic_transaction_id_available": False,
        "provider_transaction_key": "reward_key",
        "attribution_keys": ["sub_id_1", "sub_id_2", "sub_id_3", "shared_id", "click_created_at_date", "link_path"],
        "commission_row_count": len(commission_rows),
        "commission_row_state": "EMPTY" if not commission_rows else "ROWS_PRESENT",
        "normalizer_state": "NO_LIVE_ROWS" if not commission_rows else "NORMALIZED",
        "payout_row_state": "EMPTY" if ("0 to 0" in payouts["text"] or "0件中0" in payouts["text"]) else "ROWS_PRESENT",
        **payout_readiness(payout_summary["text"]),
        "rendered_artifact_sha256": artifact_hash,
        "observed_at": observed_at,
    }
    atomic_write(state / "provider-reports" / "partnerstack" / "latest.json", receipt)
    return receipt


def reconcile(args):
    state = args.state.expanduser()
    latest_path = state / "provider-reports" / "partnerstack" / "latest.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    source_hash = latest["rendered_artifact_sha256"]
    artifact_path = state / "provider-reports" / "partnerstack" / f"{source_hash}.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    if hashlib.sha256(json.dumps(artifact, sort_keys=True).encode()).hexdigest() != source_hash:
        raise RevenueError("provider report artifact hash mismatch")
    raw_rows = artifact.get("commission_rows", [])
    captured_normalized = [normalize_commission_row(row) for row in raw_rows]
    if captured_normalized != artifact.get("normalized_commissions"):
        raise RevenueError("stored commission normalization mismatch")
    candidates = placement_candidates(state)
    normalized = []
    for raw_row, row in zip(raw_rows, captured_normalized):
        normalized.append({**row, "placement": resolve_attribution(raw_row, candidates)})
    appended = 0
    for row in normalized:
        transition = build_transition(row, source_hash, latest["observed_at"])
        appended += int(append_unique(
            state / "commission-ledger.jsonl", transition, ("transition_id",),
        ))
    placement_ledger = build_placement_ledger(state)
    receipt = {
        "schema_version": 1,
        "receipt_type": "COMMISSION_RECONCILIATION",
        "provider": "elevenlabs",
        "source_artifact_sha256": source_hash,
        "source_rows": len(normalized),
        "appended_transitions": appended,
        "replayed_transitions": len(normalized) - appended,
        "money_state": "NO_TRANSACTIONS" if not normalized else "TRANSACTIONS_RECONCILED",
        "placement_ledger_sha256": placement_ledger["ledger_sha256"],
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write(state / "provider-reports" / "partnerstack" / "reconciliation-latest.json", receipt)
    return receipt


def observe(args):
    pages = [item for item in read_json(f"http://{args.cdp_host}:{args.cdp_port}/json/list") if item.get("type") == "page"]
    if len(pages) != 1:
        raise RevenueError(f"expected one provider tab, found {len(pages)}")
    ws = create_connection(
        f"ws://{args.cdp_host}:{args.cdp_port}/devtools/page/{pages[0]['id']}",
        timeout=20, max_size=None, suppress_origin=True,
    )
    cards = None
    try:
        cdp_call(ws, 1, "Page.enable")
        cdp_call(ws, 2, "Page.navigate", {"url": "https://dash.partnerstack.com/elevenlabsinc"})
        expression = "({url:location.href,text:(document.body&&document.body.innerText)||''})"
        for request_id in range(10, 70):
            result = cdp_call(ws, request_id, "Runtime.evaluate", {"expression": expression, "returnByValue": True})
            page = result.get("result", {}).get("value", {})
            try:
                cards = extract_cards(page.get("text", ""))
                break
            except RevenueError:
                pass
            if "Sign in to PartnerStack" in page.get("text", ""):
                raise RevenueError("PartnerStack authentication is required")
            time.sleep(0.5)
    finally:
        try:
            cdp_call(ws, 100, "Page.navigate", {"url": "https://elevenlabs.io/app/home"})
        finally:
            ws.close()
    if cards is None:
        raise RevenueError("PartnerStack metrics did not become ready")
    metrics = parse_cards(cards)
    state = args.state.expanduser()
    previous = {}
    receipt_path = state / "provider-metrics" / "elevenlabs.json"
    if receipt_path.is_file():
        previous = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt = build_receipt(metrics, previous, datetime.now(timezone.utc).isoformat())
    atomic_write(receipt_path, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(prog="affiliate revenue")
    parser.add_argument(
        "command", choices=("observe", "links", "capture", "reconcile", "ledger", "net")
    )
    parser.add_argument("--cdp-host", default="127.0.0.1")
    parser.add_argument("--cdp-port", type=int, default=9324)
    parser.add_argument("--state", type=Path, default=Path("~/.local/state/life-manager/affiliate"))
    args = parser.parse_args()
    if args.command == "observe":
        result = observe(args)
    elif args.command == "links":
        result = capture_link_performance(args)
    elif args.command == "capture":
        result = capture_reports(args)
    elif args.command == "reconcile":
        result = reconcile(args)
    elif args.command == "ledger":
        result = build_placement_ledger(args.state.expanduser())
    else:
        result = build_rolling_net(args.state.expanduser())
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        RevenueError, WebSocketException, OSError, ValueError, KeyError,
        json.JSONDecodeError,
    ) as error:
        print(json.dumps(
            {"failure_type": failure_type(error)},
            sort_keys=True, separators=(",", ":"),
        ), file=sys.stderr)
        raise SystemExit(1)
