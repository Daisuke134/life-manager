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

from alpaca_snapshot import read_alpaca_snapshot
from cross_venue_reporter import render_daily_pnl, wake
from portfolio_receipts import VenueSnapshot


DEFAULT_STATE_DIR = Path("~/.local/state/life-manager/investment-cross-venue")
DEFAULT_MANIFEST_NAME = "inputs.json"
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
        try:
            canonical = VenueSnapshot.from_mapping(payload)
        except (TypeError, ValueError) as error:
            return _unknown(str(error))
        reason = canonical.validation_reason()
        return _unknown(reason) if reason is not None else canonical

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


def read_manifest(path: str | Path | None) -> dict[str, Any]:
    """Read the owner-provided input manifest without treating absence as zero."""
    if path is None:
        return {
            "status": "missing",
            "snapshot_specs": [],
            "alpaca_state_dir": None,
            "owner_cash_flow_path": None,
            "available_capital_usd": "0",
        }
    manifest_path = Path(path).expanduser()
    if not manifest_path.is_file():
        return {
            "status": "missing",
            "snapshot_specs": [],
            "alpaca_state_dir": None,
            "owner_cash_flow_path": None,
            "available_capital_usd": "0",
        }
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "invalid",
            "snapshot_specs": [],
            "alpaca_state_dir": None,
            "owner_cash_flow_path": None,
            "available_capital_usd": "0",
        }
    if not isinstance(value, Mapping):
        status = "invalid"
        return {"status": status, "snapshot_specs": [],
                "alpaca_state_dir": None, "owner_cash_flow_path": None,
                "available_capital_usd": "0"}
    specs = value.get("snapshot_specs", [])
    alpaca_state_dir = value.get("alpaca_state_dir")
    owner_path = value.get("owner_cash_flow_path")
    if (not isinstance(specs, list) or any(not isinstance(item, str) or not item for item in specs)
            or (alpaca_state_dir is not None and not isinstance(alpaca_state_dir, str))
            or (owner_path is not None and not isinstance(owner_path, str))):
        return {"status": "invalid", "snapshot_specs": [],
                "alpaca_state_dir": None, "owner_cash_flow_path": None,
                "available_capital_usd": "0"}
    return {
        "status": "configured",
        "snapshot_specs": specs,
        "alpaca_state_dir": alpaca_state_dir,
        "owner_cash_flow_path": owner_path,
        "available_capital_usd": value.get("available_capital_usd", "0"),
    }


def run_once(
    *,
    snapshot_specs: Iterable[str],
    state_dir: str | Path,
    today: str,
    owner_cash_flow_path: str | Path | None,
    available_capital_usd: Any,
    send: Callable[[str], Any],
    input_manifest_status: str = "configured",
    alpaca_state_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run one finite measurement/report wake with no venue side effect."""
    owner_path = Path(owner_cash_flow_path).expanduser() if owner_cash_flow_path else None
    specs = list(snapshot_specs)
    readers: dict[str, Callable[[], Any]] = build_readers(specs)
    explicit_alpaca = any(
        isinstance(spec, str) and spec.partition("=")[0] == "alpaca"
        for spec in specs
    )
    if alpaca_state_dir and not explicit_alpaca:
        state_path = Path(alpaca_state_dir).expanduser()
        readers["alpaca"] = lambda: read_alpaca_snapshot(state_path)
    readers["__owner_cash_flow_usd__"] = _read_owner_cash_flow(owner_path)
    readers["__available_capital_usd__"] = _valid_available_capital(available_capital_usd)
    readers["__input_manifest_status__"] = input_manifest_status
    return wake(readers, Path(state_dir).expanduser(), today, send)


def _telegram_send(message: str) -> Any:
    from reporter import _telegram_client

    client, target = _telegram_client()
    return client.send_text(message, chat_id=target)


def _parser() -> argparse.ArgumentParser:
    default_state = os.environ.get("INVESTMENT_CROSS_VENUE_STATE_DIR", str(DEFAULT_STATE_DIR))
    default_manifest = os.environ.get(
        "INVESTMENT_CROSS_VENUE_MANIFEST",
        str(Path(default_state).expanduser() / DEFAULT_MANIFEST_NAME),
    )
    default_alpaca_state = os.environ.get("INVESTMENT_ALPACA_STATE_DIR")
    default_capital = os.environ.get("INVESTMENT_AVAILABLE_CAPITAL_USD", "0")
    default_owner_flow = os.environ.get("INVESTMENT_OWNER_CASH_FLOW_FILE")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", default=default_state)
    parser.add_argument("--manifest", default=default_manifest)
    parser.add_argument("--alpaca-state-dir", default=default_alpaca_state)
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
    manifest = read_manifest(args.manifest)
    receipt = run_once(
        snapshot_specs=args.snapshot_specs or manifest["snapshot_specs"],
        alpaca_state_dir=args.alpaca_state_dir or manifest["alpaca_state_dir"],
        state_dir=args.state_dir,
        today=today,
        owner_cash_flow_path=args.owner_cash_flow_file or manifest["owner_cash_flow_path"],
        available_capital_usd=(args.available_capital_usd
                               if args.available_capital_usd != "0"
                               else manifest["available_capital_usd"]),
        send=send or _telegram_send,
        input_manifest_status=manifest["status"],
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt.get("status") == "delivered" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_STATE_DIR",
    "DEFAULT_MANIFEST_NAME",
    "STANDARD_VENUES",
    "build_readers",
    "main",
    "parse_snapshot_spec",
    "read_manifest",
    "render_daily_pnl",
    "run_once",
    "wake",
]
