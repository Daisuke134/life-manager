"""Daily, read-only cross-venue net-P&L report with durable delivery evidence."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
import json
from pathlib import Path
from typing import Any, Callable, Mapping

import telegram_outbox
from cross_venue_allocator import build_candidates, rank
from net_pnl import aggregate as aggregate_net
from portfolio_receipts import VenueSnapshot
from rolling_measurement import rolling_30d


_MONEY = Decimal("0.01")
_DEFAULT_CAPS = {
    "cash_reserve_usd": "100",
    "max_allocation_usd": "100",
    "current_cap_usd": "100",
    "max_drawdown_fraction": "0.20",
    "min_round_trips": 30,
}


def _money(value: Any) -> str:
    if value is None or value == "unknown":
        return "不明"
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return "不明"
    if not amount.is_finite():
        return "不明"
    amount = amount.quantize(_MONEY, rounding=ROUND_HALF_EVEN)
    return f"-${abs(amount):,.2f}" if amount < 0 else f"${amount:,.2f}"


def _read_value(value: Any) -> VenueSnapshot | dict[str, str]:
    if isinstance(value, VenueSnapshot):
        return value
    if isinstance(value, Mapping) and value.get("status") == "unknown":
        return {"status": "unknown", "reason": str(value.get("reason") or "source_unknown")}
    if isinstance(value, Mapping) and isinstance(value.get("snapshot"), Mapping):
        value = value["snapshot"]
    try:
        return VenueSnapshot.from_mapping(value)
    except (TypeError, ValueError) as error:
        return {"status": "unknown", "reason": str(error)}


def _unknown_label(row: Mapping[str, Any]) -> str:
    venue = str(row.get("venue") or "unknown")
    return f"{venue}: 不明 ({row.get('reason') or 'source_unknown'})"


def render_daily_pnl(aggregate: Mapping[str, Any], allocation: Mapping[str, Any], day: str) -> str:
    lines = [
        f"[Investment Loop][Cross Venue P&L] {day}",
        f"measurement: {aggregate.get('measurement_status') or '不明'}",
        f"gross P&L: {_money(aggregate.get('gross_pnl_usd'))}",
        f"取引手数料: {_money(aggregate.get('trading_fees_usd'))}",
        f"funding/borrow: {_money(aggregate.get('funding_or_borrow_usd'))}",
        f"slippage: {_money(aggregate.get('slippage_usd'))}",
        f"gas: {_money(aggregate.get('gas_usd'))}",
        f"model cost: {_money(aggregate.get('model_cost_usd'))}",
        f"owner cash flow: {_money(aggregate.get('owner_cash_flow_usd'))}",
        f"net P&L: {_money(aggregate.get('net_pnl_usd'))}",
        f"rolling period end: {aggregate.get('rolling_period_end') or '不明'}",
        f"rolling 30d net P&L: {_money(aggregate.get('rolling_30d_net_pnl_usd'))}",
        f"target gap ($10k/month): {_money(aggregate.get('target_gap_usd'))}",
        "",
        "venues:",
    ]
    venue_rows = aggregate.get("venue_rows")
    if isinstance(venue_rows, list) and venue_rows:
        for row in sorted((item for item in venue_rows if isinstance(item, Mapping)), key=lambda item: str(item.get("venue") or "")):
            lines.append(
                f"- {row.get('venue') or 'unknown'}: gross {_money(row.get('gross_pnl_usd'))}, "
                f"net {_money(row.get('net_pnl_usd'))}, receipts {len(row.get('source_receipt_ids') or [])}"
            )
    else:
        lines.append("- 不明")
    for row in sorted((item for item in aggregate.get("unknown_venues", []) if isinstance(item, Mapping)), key=lambda item: str(item.get("venue") or "")):
        lines.append(f"- {_unknown_label(row)}")
    lines.extend((
        "",
        f"allocation: {allocation.get('action') or '不明'}",
        f"allocation amount: {_money(allocation.get('allocation_usd'))}",
        f"capital expansion: {'allowed' if allocation.get('capital_expansion_allowed') is True else 'not allowed'}",
        f"allocation reason: {allocation.get('reason') or '不明'}",
    ))
    return "\n".join(lines)


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{path.stat().st_ino if path.exists() else 'new'}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def _provider_message_id(response: Any) -> str | None:
    if isinstance(response, str) and response:
        return response
    if isinstance(response, Mapping):
        value = response.get("message_id", response.get("provider_message_id"))
        if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value):
            return str(value)
    return None


def _base_receipt(day: str, aggregate: Mapping[str, Any], allocation: Mapping[str, Any], unknown: list[dict[str, str]], event_key: str) -> dict[str, Any]:
    return {
        "day": day,
        "event_key": event_key,
        "aggregate": dict(aggregate),
        "allocation": dict(allocation),
        "unknown_venues": unknown,
    }


def load_daily_receipts(state_dir: str | Path, end_day: str) -> list[dict[str, Any]]:
    """Read persisted daily receipts for one rolling window without writing state."""
    try:
        parsed_end = date.fromisoformat(end_day)
    except (TypeError, ValueError) as error:
        raise ValueError("daily_receipt_day_invalid") from error
    if parsed_end.isoformat() != end_day:
        raise ValueError("daily_receipt_day_invalid")

    state = Path(state_dir)
    rows: list[dict[str, Any]] = []
    for offset in range(29, -1, -1):
        day = (parsed_end - timedelta(days=offset)).isoformat()
        path = state / f"cross-venue-{day}.json"
        if not path.exists():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            rows.append({"day": day, "_load_error": "daily_receipt_file_invalid"})
            continue
        if not isinstance(value, Mapping) or value.get("day") != day:
            rows.append({"day": day, "_load_error": "daily_receipt_file_invalid"})
            continue
        rows.append(dict(value))
    return rows


def wake(
    readers: Mapping[str, Callable[[], Any]],
    state_dir: str | Path,
    today: str,
    send: Callable[[str], Any],
) -> dict[str, Any]:
    state = Path(state_dir)
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    state.chmod(0o700)
    receipt_path = state / f"cross-venue-{today}.json"
    if receipt_path.exists():
        try:
            return json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"status": "delivery_uncertain", "reason": "aggregate_receipt_invalid", "day": today}

    known: list[VenueSnapshot] = []
    unknown: list[dict[str, str]] = []
    for venue in sorted(key for key in readers if not key.startswith("__")):
        reader = readers[venue]
        try:
            value = reader() if callable(reader) else reader
            normalized = _read_value(value)
        except Exception as error:  # provider boundary: preserve class, not secret text
            normalized = {"status": "unknown", "reason": type(error).__name__}
        if isinstance(normalized, VenueSnapshot):
            known.append(normalized)
        else:
            unknown.append({"venue": venue, "reason": normalized.get("reason", "source_unknown")})

    now = datetime.now(timezone.utc).replace(microsecond=0)
    now_text = now.isoformat().replace("+00:00", "Z")
    owner_flow = readers.get("__owner_cash_flow_usd__", "unknown")
    if known:
        aggregate = aggregate_net(f"{today}T00:00:00Z", now_text, known, owner_flow)
    else:
        aggregate = {
            "measurement_status": "unknown",
            "reason": "source_missing",
            "owner_cash_flow_usd": owner_flow if owner_flow is not None else "unknown",
            "venue_rows": [],
        }
    aggregate = dict(aggregate)
    if unknown:
        aggregate["unknown_venues"] = unknown
        aggregate["measurement_status"] = "partial" if aggregate.get("measurement_status") == "measured" else "unknown"
    daily_receipts = readers.get("__daily_receipts__")
    auto_persisted_window = daily_receipts is None and "__rolling_30d_net_pnl_usd__" not in readers
    rolling_end_day = today
    if auto_persisted_window:
        rolling_end_day = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
        daily_receipts = load_daily_receipts(state, rolling_end_day)
    if daily_receipts is not None:
        try:
            daily_receipts = daily_receipts() if callable(daily_receipts) else daily_receipts
            rolling_result = rolling_30d(daily_receipts, rolling_end_day)
        except Exception as error:  # receipt boundary: preserve class, not provider text
            rolling_result = {
                "measurement_status": "unknown",
                "reason": type(error).__name__,
                "net_pnl_usd": None,
                "owner_cash_flow_usd": None,
                "target_gap_usd": None,
            }
        aggregate["rolling_measurement_status"] = rolling_result.get("measurement_status")
        aggregate["rolling_reason"] = rolling_result.get("reason")
        aggregate["rolling_period_end"] = rolling_result.get("period_end")
        aggregate["rolling_30d_net_pnl_usd"] = rolling_result.get("net_pnl_usd")
        aggregate["rolling_owner_cash_flow_usd"] = rolling_result.get("owner_cash_flow_usd")
        aggregate["target_gap_usd"] = rolling_result.get("target_gap_usd")
    else:
        # Kept for callers that already provide a separately verified rolling
        # receipt. The daily-receipt path above is the canonical producer.
        rolling = readers.get("__rolling_30d_net_pnl_usd__")
        aggregate["rolling_measurement_status"] = "provided" if rolling is not None else "unknown"
        aggregate["rolling_reason"] = "provided_input" if rolling is not None else "daily_receipts_missing"
        aggregate["rolling_period_end"] = today if rolling is not None else None
        aggregate["rolling_30d_net_pnl_usd"] = rolling
        aggregate["target_gap_usd"] = None
        if rolling is not None:
            try:
                aggregate["target_gap_usd"] = max(Decimal("0"), Decimal("10000") - Decimal(str(rolling)))
            except (InvalidOperation, TypeError, ValueError):
                aggregate["target_gap_usd"] = None

    caps = readers.get("__caps__", _DEFAULT_CAPS)
    if not isinstance(caps, Mapping):
        caps = _DEFAULT_CAPS
    available = readers.get("__available_capital_usd__", aggregate.get("free_cash_usd", "0"))
    candidates = build_candidates(known, aggregate, dict(caps))
    allocation = rank(candidates, available, dict(caps))
    message = render_daily_pnl(aggregate, allocation, today)
    database = state / "telegram-outbox.sqlite3"
    event_key = f"cross-venue-daily:{today}"
    receipt = _base_receipt(today, aggregate, allocation, unknown, event_key)
    try:
        inserted = telegram_outbox.enqueue(database, event_key, message, now_text)
    except Exception as error:
        receipt.update(status="delivery_uncertain", reason=type(error).__name__)
        _atomic_json(receipt_path, receipt)
        return receipt
    if not inserted:
        item = next((row for row in telegram_outbox.list_items(database) if row.event_key == event_key), None)
        if item and item.status == "delivered" and item.provider_message_id:
            receipt.update(status="delivered", provider_message_id=item.provider_message_id)
        else:
            receipt.update(status="delivery_uncertain", reason="outbox_delivery_unconfirmed")
        _atomic_json(receipt_path, receipt)
        return receipt

    claimed = telegram_outbox.claim_next(database)
    if claimed is None or claimed.event_key != event_key:
        receipt.update(status="delivery_uncertain", reason="outbox_claim_failed")
        _atomic_json(receipt_path, receipt)
        return receipt
    try:
        response = send(message)
        provider_id = _provider_message_id(response)
        if provider_id is None:
            raise ValueError("provider_message_id_missing")
        delivered_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        telegram_outbox.mark_delivered(database, event_key, provider_id, delivered_at, claimed_at=claimed.claimed_at)
        receipt.update(status="delivered", provider_message_id=provider_id, delivered_at=delivered_at)
    except Exception as error:
        try:
            telegram_outbox.mark_delivery_uncertain(database, event_key, type(error).__name__, claimed_at=claimed.claimed_at)
        except Exception:
            pass
        receipt.update(status="delivery_uncertain", reason=type(error).__name__)
    _atomic_json(receipt_path, receipt)
    return receipt
