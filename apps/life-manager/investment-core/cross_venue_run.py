"""Finite, read-only cross-venue wake entry point.

The owner runtime supplies canonical venue snapshot files.  This module only
loads those files, wires them into the existing idempotent reporter, and
delivers the resulting report.  It never loads credentials or calls a venue
execution API.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from cross_venue_reporter import render_daily_pnl, wake


DEFAULT_STATE_DIR = Path("~/.local/state/life-manager/investment-cross-venue")
STANDARD_VENUES = ("alpaca", "hyperliquid", "solana")
_VENUE_RE = re.compile(r"[A-Za-z0-9_-]+\Z")


def parse_snapshot_spec(value: str) -> tuple[str, Path]:
    """Parse the owner-configured ``venue=/path/to/snapshot.json`` contract."""
    if not isinstance(value, str):
        raise ValueError("snapshot_spec_invalid")
    venue, separator, raw_path = value.partition("=")
    if (not separator or not venue or not raw_path or venue.startswith("__")
            or _VENUE_RE.fullmatch(venue) is None):
        raise ValueError("snapshot_spec_invalid")
    return venue, Path(raw_path).expanduser()


def _unknown(reason: str) -> dict[str, str]:
    return {"status": "unknown", "reason": reason}


def _load_json_mapping(path: Path) -> Mapping[str, Any] | None:
    try:
        if not path.is_file():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _snapshot_reader(venue: str, path: Path) -> Callable[[], Mapping[str, Any]]:
    def read() -> Mapping[str, Any]:
        value = _load_json_mapping(path)
        if value is None:
            return _unknown("snapshot_file_missing" if not path.is_file()
                            else "snapshot_file_invalid")
        payload = value.get("snapshot") if isinstance(value.get("snapshot"), Mapping) else value
        if payload.get("status") == "unknown":
            reason = payload.get("reason")
            return _unknown(reason if isinstance(reason, str) and reason else "source_unknown")
        if payload.get("venue") != venue:
            return _unknown("snapshot_venue_mismatch")
        return value

    return read


def build_readers(snapshot_specs: Iterable[str]) -> dict[str, Callable[[], Mapping[str, Any]]]:
    """Build stable readers, keeping missing standard venues explicitly unknown."""
    readers: dict[str, Callable[[], Mapping[str, Any]]] = {
        venue: (lambda venue=venue: _unknown("snapshot_file_missing"))
        for venue in STANDARD_VENUES
    }
    seen: set[str] = set()
    for raw_spec in snapshot_specs:
        venue, path = parse_snapshot_spec(raw_spec)
        if venue in seen:
            raise ValueError("snapshot_spec_duplicate")
        seen.add(venue)
        readers[venue] = _snapshot_reader(venue, path)
    return readers


def _read_owner_cash_flow(path: Path | None) -> str:
    if path is None:
        return "unknown"
    value = _load_json_mapping(path)
    if value is None:
        return "unknown"
    amount = value.get("owner_cash_flow_usd")
    source_ids = value.get("source_receipt_ids")
    if (isinstance(amount, bool) or amount is None or not isinstance(source_ids, list)
            or not source_ids or any(not isinstance(item, str) or not item for item in source_ids)):
        return "unknown"
    try:
        parsed = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        return "unknown"
    return str(parsed) if parsed.is_finite() else "unknown"


def _valid_available_capital(value: Any) -> str:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return "0"
    if not parsed.is_finite() or parsed < 0:
        return "0"
    return str(parsed)


def run_once(
    *,
    snapshot_specs: Iterable[str],
    state_dir: str | Path,
    today: str,
    owner_cash_flow_path: str | Path | None,
    available_capital_usd: Any,
    send: Callable[[str], Any],
) -> dict[str, Any]:
    """Run one finite measurement/report wake with no venue side effect."""
    owner_path = Path(owner_cash_flow_path).expanduser() if owner_cash_flow_path else None
    readers: dict[str, Callable[[], Any]] = build_readers(snapshot_specs)
    readers["__owner_cash_flow_usd__"] = _read_owner_cash_flow(owner_path)
    readers["__available_capital_usd__"] = _valid_available_capital(available_capital_usd)
    return wake(readers, Path(state_dir).expanduser(), today, send)


def _telegram_send(message: str) -> Any:
    from reporter import _telegram_client

    client, target = _telegram_client()
    return client.send_text(message, chat_id=target)


def _parser() -> argparse.ArgumentParser:
    default_state = os.environ.get("INVESTMENT_CROSS_VENUE_STATE_DIR", str(DEFAULT_STATE_DIR))
    default_capital = os.environ.get("INVESTMENT_AVAILABLE_CAPITAL_USD", "0")
    default_owner_flow = os.environ.get("INVESTMENT_OWNER_CASH_FLOW_FILE")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", default=default_state)
    parser.add_argument("--today", default=None, help="UTC date; defaults to today")
    parser.add_argument("--snapshot", dest="snapshot_specs", action="append", default=[],
                        metavar="VENUE=PATH")
    parser.add_argument("--owner-cash-flow-file", default=default_owner_flow)
    parser.add_argument("--available-capital-usd", default=default_capital)
    return parser


def main(argv: list[str] | None = None, *, send: Callable[[str], Any] | None = None) -> int:
    args = _parser().parse_args(argv)
    today = args.today or datetime.now(timezone.utc).date().isoformat()
    date.fromisoformat(today)
    receipt = run_once(
        snapshot_specs=args.snapshot_specs,
        state_dir=args.state_dir,
        today=today,
        owner_cash_flow_path=args.owner_cash_flow_file,
        available_capital_usd=args.available_capital_usd,
        send=send or _telegram_send,
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt.get("status") == "delivered" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_STATE_DIR",
    "STANDARD_VENUES",
    "build_readers",
    "main",
    "parse_snapshot_spec",
    "render_daily_pnl",
    "run_once",
    "wake",
]
