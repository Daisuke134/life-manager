"""Durable, owner-bound paper ETF position and receipt state."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


ETF_OWNER_ID = "alpaca-investment-live"
ETF_PAPER_OWNER_ID = "alpaca-investment-paper"
ETF_OWNER_IDS = frozenset({ETF_OWNER_ID, ETF_PAPER_OWNER_ID})
ETF_STRATEGY_ID = "alpaca-etf-126d-momentum-v1"
ETF_SYMBOLS = frozenset({"SPY", "QQQ", "IWM", "DIA", "EFA", "EEM", "TLT", "GLD"})
CLIENT_ORDER_ID = re.compile(r"lm-ai-[0-9a-f]{24}")


def investment_owner_id() -> str:
    """Return the configured ETF owner, allowing only declared owner lanes."""
    owner_id = os.environ.get("LIFE_MANAGER_INVESTMENT_OWNER_ID", ETF_OWNER_ID)
    if owner_id not in ETF_OWNER_IDS:
        raise ValueError("etf_owner_invalid")
    return owner_id


def _number(value: Any, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("etf_number_invalid")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("etf_number_invalid") from error
    if not number.is_finite() or (positive and number <= 0):
        raise ValueError("etf_number_invalid")
    return number


def _session(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("etf_decision_session_invalid")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ValueError("etf_decision_session_invalid") from error


def _load(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("etf_position_state_invalid") from error
    if not isinstance(value, dict):
        raise ValueError("etf_position_state_invalid")
    return value


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _identity(value: Mapping[str, Any], owner_id: str, strategy_id: str) -> None:
    if value.get("owner_id") != owner_id or value.get("strategy_id") != strategy_id:
        raise ValueError("etf_position_not_owned")


def _read_open(value: Mapping[str, Any]) -> dict[str, Any]:
    status = value.get("status")
    if status not in {"open", "closed"}:
        raise ValueError("etf_position_state_invalid")
    try:
        symbol = value["symbol"]
        decision_session = _session(value["decision_session"])
        client_order_id = value["client_order_id"]
        provider_order_id = value["provider_order_id"]
        if symbol not in ETF_SYMBOLS or not isinstance(client_order_id, str) \
                or not CLIENT_ORDER_ID.fullmatch(client_order_id) \
                or not isinstance(provider_order_id, str) or not provider_order_id:
            raise ValueError
        qty = _number(value["position_qty"], positive=True)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("etf_position_state_invalid") from error
    if status == "open":
        return {
            "owner_id": value["owner_id"],
            "strategy_id": value["strategy_id"],
            "symbol": symbol,
            "qty": str(qty),
            "entry_session": decision_session,
        }
    return {}


def read_state(
    path: Path,
    *,
    owner_id: str = ETF_OWNER_ID,
    strategy_id: str = ETF_STRATEGY_ID,
) -> dict[str, Any]:
    """Read ETF state without adopting a foreign owner or strategy."""
    value = _load(path)
    if value is None:
        return {"position": None, "last_decision_session": None}
    _identity(value, owner_id, strategy_id)
    position = _read_open(value)
    return {
        "position": position or None,
        "last_decision_session": _session(value["decision_session"]),
    }


def _provider_order(
    order: Mapping[str, Any],
    *,
    client_order_id: str,
) -> tuple[str, Decimal, Decimal]:
    if (order.get("client_order_id") != client_order_id
            or order.get("status") != "filled"
            or order.get("symbol") not in ETF_SYMBOLS
            or order.get("side") != "buy"
            or order.get("type") != "market"
            or order.get("time_in_force") != "day"):
        raise ValueError("etf_fill_missing")
    provider_order_id = order.get("id")
    if not isinstance(provider_order_id, str) or not provider_order_id:
        raise ValueError("etf_provider_receipt_invalid")
    try:
        notional = _number(order.get("notional"))
        qty = _number(order.get("filled_qty"), positive=True)
        price = _number(order.get("filled_avg_price"), positive=True)
    except ValueError as error:
        raise ValueError("etf_fill_missing") from error
    if notional != Decimal("10.00"):
        raise ValueError("etf_order_shape_invalid")
    return provider_order_id, qty, price


def _account_position(
    readback: Mapping[str, Any],
    *,
    symbol: str,
    expected_qty: Decimal,
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    account = readback.get("account")
    positions = readback.get("positions")
    if not isinstance(account, Mapping) or not isinstance(positions, list):
        raise ValueError("etf_account_readback_invalid")
    try:
        cash = _number(account["cash"])
        equity = _number(account["equity"])
    except (KeyError, ValueError) as error:
        raise ValueError("etf_account_readback_invalid") from error
    matching = [row for row in positions if isinstance(row, Mapping) and row.get("symbol") == symbol]
    if len(matching) != 1:
        raise ValueError("etf_account_readback_invalid")
    try:
        held_qty = _number(matching[0]["qty"], positive=True)
    except (KeyError, ValueError) as error:
        raise ValueError("etf_account_readback_invalid") from error
    if held_qty != expected_qty:
        raise ValueError("etf_account_readback_invalid")
    observed_at = readback.get("clock", {}).get("observed_at") \
        if isinstance(readback.get("clock"), Mapping) else None
    if not isinstance(observed_at, str) or not observed_at:
        raise ValueError("etf_account_readback_invalid")
    return {
        "cash": str(cash),
        "equity": str(equity),
        "observed_at": observed_at,
    }, matching[0]


def record_filled(
    path: Path,
    *,
    owner_id: str,
    strategy_id: str,
    decision_session: str,
    client_order_id: str,
    order: Mapping[str, Any],
    account_readback: Mapping[str, Any],
    source_receipt_ids: Sequence[str],
) -> dict[str, Any]:
    """Persist one filled paper entry, or return the same identity on replay."""
    if owner_id != investment_owner_id() or strategy_id != ETF_STRATEGY_ID:
        raise ValueError("etf_position_not_owned")
    if not CLIENT_ORDER_ID.fullmatch(client_order_id):
        raise ValueError("client_order_id_invalid")
    decision_session = _session(decision_session)
    if isinstance(source_receipt_ids, (str, bytes)) \
            or not isinstance(source_receipt_ids, Sequence) \
            or not source_receipt_ids \
            or any(not isinstance(value, str) or not value for value in source_receipt_ids):
        raise ValueError("etf_source_receipts_invalid")
    if not isinstance(order, Mapping):
        raise ValueError("etf_provider_receipt_invalid")
    provider_order_id, qty, price = _provider_order(order, client_order_id=client_order_id)
    account, _position = _account_position(
        account_readback, symbol=str(order["symbol"]), expected_qty=qty,
    )
    existing = _load(path)
    if existing is not None:
        _identity(existing, owner_id, strategy_id)
        _read_open(existing)
        same_identity = (
            existing.get("status") == "open"
            and existing.get("client_order_id") == client_order_id
            and existing.get("provider_order_id") == provider_order_id
            and existing.get("symbol") == order["symbol"]
            and existing.get("position_qty") == str(qty)
        )
        if same_identity:
            return {**existing, "replay_zero": True}
        if existing.get("status") == "open":
            raise ValueError("etf_position_ownership_conflict")
    payload = {
        "schema_version": 1,
        "status": "open",
        "owner_id": owner_id,
        "strategy_id": strategy_id,
        "symbol": str(order["symbol"]),
        "decision_session": decision_session,
        "client_order_id": client_order_id,
        "entry_client_order_id": client_order_id,
        "provider_order_id": provider_order_id,
        "position_qty": str(qty),
        "filled_avg_price": str(price),
        "notional_usd": "10.00",
        "account_cash_usd": account["cash"],
        "account_equity_usd": account["equity"],
        "account_readback_at": account["observed_at"],
        "source_receipt_ids": list(source_receipt_ids),
    }
    _atomic_json(path, payload)
    return {**payload, "replay_zero": False}


__all__ = [
    "ETF_OWNER_ID", "ETF_PAPER_OWNER_ID", "ETF_OWNER_IDS", "ETF_STRATEGY_ID",
    "ETF_SYMBOLS", "investment_owner_id", "read_state", "record_filled",
]
