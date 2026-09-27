#!/usr/bin/env python3
"""Join Capafy business state under one run_id and deliver it at most once."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[4]
OUTBOX_MODULES = REPO_ROOT / "skills/_shared/marketplace-core/scripts"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(OUTBOX_MODULES))
from telegram_outbox import enqueue, claim_next, list_items, mark_delivered, mark_delivery_uncertain  # noqa: E402
from skills._shared.telegram import TelegramClient, TelegramDeliveryUnknown, TelegramError  # noqa: E402


STATE_HOME = Path(os.environ.get("LIFE_MANAGER_STATE_HOME", Path.home() / ".local/state/life-manager")).expanduser()
CAPAFY_STATE = STATE_HOME / "state"
DEFAULT_OUTBOX = STATE_HOME / "state/capafy-telegram-outbox.sqlite"
DEFAULT_RECEIPTS = STATE_HOME / "state/capafy-company-receipts"


class DeliveryUncertain(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _semantic_payload(sources: dict) -> dict:
    inventory = sources.get("inventory") or {}
    candidate = sources.get("candidate") or {}
    marketing = sources.get("marketing") or {}
    outcome = marketing.get("outcome") if isinstance(marketing, dict) else {}
    outcome = outcome if isinstance(outcome, dict) else {}
    money_source = sources.get("money") or {}
    growth = sources.get("growth") or {}
    skill_analytics = sources.get("skill_analytics")
    product_metrics = sources.get("product_metrics")
    return {
        "skill": {
            "candidate_id": candidate.get("candidate_id"),
            "name": candidate.get("title"),
            "agent_id": candidate.get("agent_id"),
            "version": candidate.get("version"),
            "remote_status": candidate.get("platform_state"),
            "content_sha256": candidate.get("content_sha256"),
        },
        "slots": copy.deepcopy(inventory.get("counts") or {}),
        "distribution": [
            {
                "platform": "instagram",
                "skill_agent_id": outcome.get("agent_id"),
                "skill_name": outcome.get("title"),
                "native_url": outcome.get("reel_url"),
                "creative_sha256": outcome.get("media_sha256"),
                "owner_session_verified": outcome.get("owner_session_verified"),
                "status": marketing.get("status", "unknown"),
            }
        ],
        "money": copy.deepcopy(money_source.get("money") or {}),
        "money_status": copy.deepcopy(money_source.get("money_status") or {}),
        "orders": money_source.get("orders"),
        "growth_signal": {
            "signal": growth.get("signal") or "unknown",
            "company_orders": growth.get("company_orders"),
            "winner_agent_id": ((growth.get("winner") or {}).get("agent_id") or (growth.get("winner") or {}).get("agentId")) if isinstance(growth.get("winner"), dict) else None,
            "attribution_status": growth.get("attribution_status"),
        },
        "skill_analytics": copy.deepcopy(skill_analytics) if isinstance(skill_analytics, dict) else {
            "status": "unavailable", "reason": "not_provided",
        },
        "product_metrics": copy.deepcopy(product_metrics) if isinstance(product_metrics, dict) else {},
    }


def build_receipt(sources: dict, observed_at: str) -> dict:
    semantic = _semantic_payload(sources)
    digest = hashlib.sha256(_canonical(semantic)).hexdigest()
    receipt = {
        "schema_version": 1,
        "kind": "capafy_company_receipt",
        "run_id": f"capafy-{digest[:24]}",
        "state_sha256": f"sha256:{digest}",
        "observed_at": observed_at,
        **semantic,
        "telegram": {"status": "pending", "message_id": None},
    }
    if not isinstance(receipt["slots"].get("occupied"), int):
        raise ValueError("slot occupancy is not readable")
    if not isinstance(receipt["skill"].get("candidate_id"), str):
        raise ValueError("candidate identity is missing")
    if "settled_mrr_usd" not in receipt["money"]:
        raise ValueError("settled_mrr_usd must remain explicit")
    return receipt


def _render_skill_analytics_line(section: dict | None) -> str:
    section = section or {}
    if section.get("status") != "fresh":
        reason = section.get("reason") or "no_data"
        return f"Skills(30d/7d): unavailable ({reason})"
    top = section.get("top_skills") or []
    top_text = ", ".join(f"{item.get('name')}=${item.get('earnings_usd')}" for item in top) or "none"
    subscription = section.get("subscription_signal") or {}
    if subscription.get("status") == "unavailable":
        sub_text = f"unavailable ({subscription.get('reason')})"
    else:
        sub_text = f"${subscription.get('amount_usd')} ({subscription.get('label')})"
    return (
        f"Skills: net30d=${section.get('last_30d_net_usd')} orders30d={section.get('last_30d_orders')} "
        f"gross7d=${section.get('last_7d_gross_usd')} top5=[{top_text}] "
        f"zero-sales={section.get('zero_sales_count')}/{section.get('total_skills')} "
        f"sub={sub_text}"
    )


def _render_product_metrics_line(sections: dict | None) -> str:
    sections = sections or {}
    parts = []
    for product_id in ("anicca-ios", "honne-ai"):
        section = sections.get(product_id) or {}
        if section.get("status") != "fresh":
            reason = section.get("reason") or "no_data"
            parts.append(f"{product_id}=unavailable ({reason})")
        else:
            parts.append(
                f"{product_id}@{section.get('business_date')}(MRR=${section.get('mrr')} "
                f"actives={section.get('actives')} trials={section.get('new_trials')})"
            )
    return "Apps: " + " ".join(parts)


def render_message(receipt: dict) -> str:
    skill = receipt["skill"]
    slots = receipt["slots"]
    money = receipt["money"]
    distribution = receipt["distribution"][0]
    growth = receipt.get("growth_signal") or {}
    post = distribution.get("native_url") or "none"
    mrr = money.get("settled_mrr_usd")
    mrr_text = "unknown" if mrr is None else f"${mrr}"
    return (
        f"Codex::: Capafy company receipt {receipt['run_id']}\n"
        f"Candidate: {skill.get('name')} ({skill.get('candidate_id')}) status={skill.get('remote_status')}\n"
        f"Slots: occupied={slots.get('occupied')} free={slots.get('free')} retry={slots.get('retry')} listed={slots.get('listed')}\n"
        f"Latest Reel: {post}\n"
        f"Money: orders={receipt.get('orders')} gross=${money.get('gross_usd')} pending=${money.get('pending_usd')} realized=${money.get('realized_usd')} refunds=${money.get('refunds_usd')} settled MRR={mrr_text}\n"
        f"Growth signal: {growth.get('signal')} (winner_agent_id={growth.get('winner_agent_id') or 'none'}; attribution={growth.get('attribution_status') or 'none'})\n"
        f"{_render_skill_analytics_line(receipt.get('skill_analytics'))}\n"
        f"{_render_product_metrics_line(receipt.get('product_metrics'))}"
    )


def _atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def deliver_receipt(
    receipt: dict,
    outbox_database: Path,
    receipts_directory: Path,
    sender: Callable[[str], str],
) -> dict:
    run_id = receipt["run_id"]
    receipt_path = receipts_directory / f"{run_id}.json"
    message = render_message(receipt)
    inserted = enqueue(outbox_database, run_id, message, receipt["observed_at"])
    if not inserted:
        if receipt_path.exists():
            return json.loads(receipt_path.read_text())
        outbox_item = next((item for item in list_items(outbox_database) if item.event_key == run_id), None)
        if outbox_item is not None:
            recovered = copy.deepcopy(receipt)
            if outbox_item.status == "delivered" and outbox_item.provider_message_id:
                recovered["telegram"] = {"status": "delivered", "message_id": outbox_item.provider_message_id}
                _atomic_write(receipt_path, recovered)
            else:
                recovered["telegram"] = {"status": "delivery_uncertain", "message_id": None}
            return recovered
        return receipt
    claimed = claim_next(outbox_database)
    if claimed is None or claimed.event_key != run_id:
        raise RuntimeError("outbox claim did not return the enqueued run")
    delivered = copy.deepcopy(receipt)
    try:
        message_id = str(sender(message))
        if not message_id or "\x00" in message_id:
            raise DeliveryUncertain("message_id_missing")
    except DeliveryUncertain as exc:
        mark_delivery_uncertain(outbox_database, run_id, str(exc) or "delivery_uncertain")
        delivered["telegram"] = {"status": "delivery_uncertain", "message_id": None}
        _atomic_write(receipt_path, delivered)
        return delivered
    delivered_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    mark_delivered(outbox_database, run_id, message_id, delivered_at)
    delivered["telegram"] = {"status": "delivered", "message_id": message_id}
    _atomic_write(receipt_path, delivered)
    return delivered


def _find_message_id(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("messageId", "message_id"):
            candidate = value.get(key)
            if isinstance(candidate, (str, int)) and str(candidate):
                return str(candidate)
        for child in value.values():
            found = _find_message_id(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_message_id(child)
            if found:
                return found
    return None


def _telegram_sender(message: str) -> str:
    """Send one receipt through the shared direct Telegram Bot API client."""
    target = (os.environ.get("CAPAFY_TELEGRAM_TARGET") or os.environ.get("TELEGRAM_ALERT_CHAT_ID")
              or os.environ.get("LM_TELEGRAM_ALERT_CHAT_ID"))
    if not target:
        raise DeliveryUncertain("telegram_target_missing")
    try:
        env_file = STATE_HOME / ".env"
        client_environment = dict(os.environ)
        client_environment["TELEGRAM_CHAT_ID"] = target
        telegram = TelegramClient.from_env(
            environ=client_environment,
            env_file=env_file,
        )
        response = telegram.send_text(message, chat_id=target)
    except TelegramDeliveryUnknown as exc:
        raise DeliveryUncertain("sender_delivery_unknown") from exc
    except TelegramError as exc:
        suffix = f"_{exc.error_code}" if exc.error_code is not None else ""
        raise DeliveryUncertain(f"sender_provider_error{suffix}") from exc

    if not isinstance(response, dict):
        raise DeliveryUncertain("message_id_missing")
    message_ids = response.get("message_ids")
    if not isinstance(message_ids, list):
        raise DeliveryUncertain("message_id_missing")
    for candidate in message_ids:
        if isinstance(candidate, bool) or not isinstance(candidate, (str, int)):
            continue
        message_id = str(candidate).strip()
        if message_id and "\x00" not in message_id:
            return message_id
    raise DeliveryUncertain("message_id_missing")


def _load(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"source is not an object: {path}")
    return value


def _marketing_from_ledger(path: Path) -> dict:
    if not path.is_file():
        return {"status": "unknown_no_native_ig_ledger", "outcome": {}}
    latest = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (isinstance(row, dict) and row.get("platform") in {"ig", "instagram"}
                and str(row.get("reel_url") or "").startswith("https://www.instagram.com/")):
            latest = row
    if latest is None:
        return {"status": "unknown_no_native_reel", "outcome": {}}
    artifact_hash = latest.get("artifact_sha256")
    return {"status": "native_ledger_observed", "outcome": {
        "agent_id": latest.get("agent_id"),
        "title": latest.get("listing_name"),
        "reel_url": latest.get("reel_url"),
        "media_sha256": ("sha256:" + artifact_hash if isinstance(artifact_hash, str)
                         and len(artifact_hash) == 64 else None),
        "owner_session_verified": None,
    }}


def _short_skill_name(name: str | None) -> str | None:
    """Shorten 'Hook Lab — Win the First 3 Seconds' to 'Hook Lab' for a compact report line."""
    if not isinstance(name, str) or not name.strip():
        return name
    return name.split(" — ", 1)[0].strip()


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _subscription_signal(data: dict) -> dict:
    """Prefer last-30d gross (subscription_proxy.last_30d_net_usd is a gross figure despite its
    name, kept for backward compatibility); fall back to since-launch web-console gross for
    subscription SKUs when the 30d window itself is a real, legitimate zero, clearly labeled as
    not-MRR and not-last-30d. Only report unavailable when neither source has a real number."""
    proxy = data.get("subscription_proxy") or {}
    gross_30d = _decimal_or_none(proxy.get("last_30d_net_usd"))
    if gross_30d is not None and gross_30d != 0:
        return {"amount_usd": proxy.get("last_30d_net_usd"), "label": "last30d gross, proxy not MRR"}

    subscription_gross = Decimal("0")
    saw_subscription_sku = False
    for row in data.get("per_skill_rows") or []:
        skus = row.get("since_launch_skus") or []
        if not any(str((sku or {}).get("skuType") or "").startswith("subscription_") for sku in skus):
            continue
        saw_subscription_sku = True
        gross = _decimal_or_none(row.get("since_launch_gross_usd"))
        if gross is not None:
            subscription_gross += gross
    if saw_subscription_sku and subscription_gross > 0:
        return {
            "amount_usd": f"{subscription_gross:.2f}",
            "label": "since-launch web-console gross, proxy not MRR, not last-30d",
        }
    return {"status": "unavailable", "reason": "settlement lag"}


def _skill_analytics_section(path: Path, name_by_agent_id: dict[str, str] | None = None) -> dict:
    """Compact, product-metrics view of capafy-skill-analytics.json for the Telegram report."""
    if not path.is_file():
        return {"status": "unavailable", "reason": "missing_capafy_skill_analytics"}
    try:
        data = _load(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {"status": "unavailable", "reason": "malformed_capafy_skill_analytics"}
    account_totals = data.get("account_totals") or {}
    account_status = account_totals.get("_status")
    per_skill_status = data.get("per_skill_rows_status")
    if account_status != "fresh" or per_skill_status != "fresh":
        return {
            "status": "unavailable",
            "reason": f"stale_capafy_skill_analytics(account={account_status},per_skill={per_skill_status})",
        }
    last_30d = account_totals.get("last_30d") or {}
    last_7d = account_totals.get("last_7d") or {}
    rankings = data.get("rankings") or {}
    name_by_agent_id = name_by_agent_id or {}
    per_skill_name_by_id = {
        row.get("agent_id"): row.get("name")
        for row in (data.get("per_skill_rows") or [])
        if row.get("agent_id") and row.get("name")
    }
    top_skills = []
    for row in (rankings.get("top_by_earnings") or [])[:5]:
        agent_id = row.get("agent_id")
        resolved_name = per_skill_name_by_id.get(agent_id) or name_by_agent_id.get(agent_id) or agent_id
        top_skills.append({"name": _short_skill_name(resolved_name), "earnings_usd": row.get("creator_earnings_usd")})
    return {
        "status": "fresh",
        "last_30d_net_usd": last_30d.get("net_usd"),
        "last_30d_orders": last_30d.get("orders"),
        "last_7d_gross_usd": last_7d.get("gross_usd"),
        "top_skills": top_skills,
        "zero_sales_count": len(rankings.get("zero_sales") or []),
        "total_skills": len(data.get("per_skill_rows") or []),
        "subscription_signal": _subscription_signal(data),
    }


def _chart_latest_value(charts: dict, chart_name: str) -> Any:
    latest = ((charts or {}).get(chart_name) or {}).get("latest_complete") or {}
    for point in latest.values():
        if isinstance(point, dict) and "value" in point:
            return point.get("value")
    return None


def _latest_revenuecat_row(path: Path, product_id: str) -> dict | None:
    matches: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or row.get("product_id") != product_id:
            continue
        revenuecat = ((row.get("sources") or {}).get("revenuecat")) or {}
        if isinstance(revenuecat, dict) and revenuecat.get("status") == "available":
            matches.append(row)
    if not matches:
        return None
    return max(matches, key=lambda row: str(row.get("business_date") or ""))


def _product_metrics_section(path: Path, product_id: str) -> dict:
    if not path.is_file():
        return {"status": "unavailable", "reason": "missing_business_outcomes"}
    try:
        row = _latest_revenuecat_row(path, product_id)
    except OSError:
        return {"status": "unavailable", "reason": "business_outcomes_read_failed"}
    if row is None:
        return {"status": "unavailable", "reason": "no_revenuecat_row"}
    charts = (((row.get("sources") or {}).get("revenuecat") or {}).get("data") or {}).get("charts") or {}
    return {
        "status": "fresh",
        "business_date": row.get("business_date"),
        "mrr": _chart_latest_value(charts, "mrr"),
        "actives": _chart_latest_value(charts, "actives"),
        "new_trials": _chart_latest_value(charts, "trials_new"),
    }


def _live_sources() -> dict:
    inventory_result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "skills/capafy-autopublish/scripts/inventory_status.py")],
        capture_output=True,
        text=True,
        timeout=120,
    )
    inventory = json.loads(inventory_result.stdout.splitlines()[-1])
    backlog = _load(STATE_HOME / "state/capafy-candidate-backlog.json")
    candidates = [item for item in backlog.get("items", []) if item.get("state") in {"ready", "submitted", "listed"}]
    if not candidates:
        raise ValueError("candidate backlog has no receipt candidate")
    candidate = sorted(candidates, key=lambda item: item["candidate_id"])[0]
    marketing_path = CAPAFY_STATE / "capafy-marketing-terminal.json"
    marketing = (_load(marketing_path) if marketing_path.is_file() else
                 _marketing_from_ledger(CAPAFY_STATE / "capafy-marketing-ig-ledger.jsonl"))
    outcome = marketing.get("outcome") or {}
    media_path = Path(str(outcome.get("media_path") or ""))
    if media_path.is_file():
        outcome["media_sha256"] = "sha256:" + hashlib.sha256(media_path.read_bytes()).hexdigest()
    money = _load(STATE_HOME / "state/capafy-hourly-reconcile.json")
    growth_path = STATE_HOME / "state/capafy-sales-ranking.json"
    growth = _load(growth_path) if growth_path.is_file() else {"signal": "unknown"}
    name_by_agent_id = {
        agent.get("agent_id"): agent.get("name")
        for agent in (inventory.get("agents") or [])
        if isinstance(agent, dict) and agent.get("agent_id") and agent.get("name")
    }
    skill_analytics = _skill_analytics_section(CAPAFY_STATE / "capafy-skill-analytics.json", name_by_agent_id)
    business_outcomes_path = STATE_HOME / "marketing-metrics-daily/state/business-outcomes.jsonl"
    product_metrics = {
        product_id: _product_metrics_section(business_outcomes_path, product_id)
        for product_id in ("anicca-ios", "honne-ai")
    }
    return {
        "inventory": inventory, "candidate": candidate, "marketing": marketing, "money": money, "growth": growth,
        "skill_analytics": skill_analytics, "product_metrics": product_metrics,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deliver", nargs="?")
    parser.add_argument("--outbox", type=Path, default=DEFAULT_OUTBOX)
    parser.add_argument("--receipts", type=Path, default=DEFAULT_RECEIPTS)
    parser.add_argument("--observed-at")
    args = parser.parse_args(argv)
    observed_at = args.observed_at or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    receipt = build_receipt(_live_sources(), observed_at)
    delivered = deliver_receipt(receipt, args.outbox, args.receipts, _telegram_sender)
    print(json.dumps(delivered, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0 if delivered["telegram"]["status"] == "delivered" else 1


if __name__ == "__main__":
    raise SystemExit(main())
