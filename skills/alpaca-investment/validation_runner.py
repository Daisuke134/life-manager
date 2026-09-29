"""Run the bounded, paper-only ETF validation and refresh selected strategy state."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any
from zoneinfo import ZoneInfo


_ROOT = Path(__file__).resolve().parents[2]
_CORE = _ROOT / "apps" / "life-manager" / "investment-core"
if str(_CORE) not in sys.path:
    sys.path.append(str(_CORE))

from alpaca_cli import read_etf_daily_history  # noqa: E402
from etf_momentum import (  # noqa: E402
    ETF_MOMENTUM_UNIVERSE,
    build_validation_report,
    screen_grid,
    simulate,
    strategy_card,
)
from provision_selection import provision_selection  # noqa: E402
from strategy_cards import is_valid_release_sha  # noqa: E402


HISTORY_CALENDAR_DAYS = 2190
CHUNK_CALENDAR_DAYS = 90
REPORT_TTL_DAYS = 7
LOOKBACKS = (84, 126, 168)
HOLD_DAYS = (15, 21, 30)
NOTIONAL_USD = Decimal("10")


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("validation_observed_at_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("validation_observed_at_invalid") from error
    if parsed.tzinfo is None:
        raise ValueError("validation_observed_at_invalid")
    return parsed


def _utc_timestamp(value: Any) -> str:
    return _parse_timestamp(value).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _chunk_ranges(start: date, end: date) -> list[tuple[date, date]]:
    if (not isinstance(start, date) or isinstance(start, datetime)
            or not isinstance(end, date) or isinstance(end, datetime)
            or end < start):
        raise ValueError("validation_date_range_invalid")
    result: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=CHUNK_CALENDAR_DAYS - 1), end)
        result.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return result


def _session(value: Any) -> str:
    return _parse_timestamp(value).date().isoformat()


def _merge_history(chunks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if isinstance(chunks, (str, bytes)) or not isinstance(chunks, Sequence) or not chunks:
        raise ValueError("validation_history_invalid")
    by_symbol: dict[str, dict[str, dict[str, str]]] = {
        symbol: {} for symbol in ETF_MOMENTUM_UNIVERSE
    }
    source_receipt_ids: list[str] = []
    observed_at: list[datetime] = []
    completed_sessions: list[str] = []
    try:
        for chunk in chunks:
            if not isinstance(chunk, Mapping):
                raise ValueError
            daily_bars = chunk.get("daily_bars")
            if not isinstance(daily_bars, Mapping) or set(daily_bars) != set(ETF_MOMENTUM_UNIVERSE):
                raise ValueError
            receipts = chunk.get("source_receipt_ids")
            if not isinstance(receipts, Sequence) or isinstance(receipts, (str, bytes)):
                raise ValueError
            for receipt in receipts:
                if not isinstance(receipt, str) or not receipt.strip():
                    raise ValueError
                if receipt not in source_receipt_ids:
                    source_receipt_ids.append(receipt)
            observed_at.append(_parse_timestamp(chunk.get("observed_at")))
            completed = chunk.get("completed_through_session")
            if not isinstance(completed, str) or date.fromisoformat(completed) is None:
                raise ValueError
            completed_sessions.append(completed)
            for symbol in ETF_MOMENTUM_UNIVERSE:
                rows = daily_bars[symbol]
                if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
                    raise ValueError
                for row in rows:
                    if not isinstance(row, Mapping):
                        raise ValueError
                    session = _session(row.get("t"))
                    normalized = {
                        "t": str(row["t"]),
                        "o": str(Decimal(str(row["o"]))),
                        "c": str(Decimal(str(row["c"]))),
                    }
                    if Decimal(normalized["o"]) <= 0 or Decimal(normalized["c"]) <= 0:
                        raise ValueError
                    previous = by_symbol[symbol].get(session)
                    if previous is not None and previous != normalized:
                        raise ValueError
                    by_symbol[symbol][session] = normalized
    except (KeyError, TypeError, ValueError):
        raise ValueError("validation_history_invalid") from None
    if not source_receipt_ids or not observed_at or not completed_sessions:
        raise ValueError("validation_history_invalid")
    if any(not by_symbol[symbol] for symbol in ETF_MOMENTUM_UNIVERSE):
        raise ValueError("validation_history_invalid")
    return {
        "daily_bars": {
            symbol: [by_symbol[symbol][session] for session in sorted(by_symbol[symbol])]
            for symbol in ETF_MOMENTUM_UNIVERSE
        },
        "source_receipt_ids": source_receipt_ids,
        "observed_at": max(observed_at).astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "completed_through_session": max(completed_sessions),
    }


def _history_digest(bars_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]]) -> str:
    canonical = json.dumps(
        {symbol: list(bars_by_symbol[symbol]) for symbol in ETF_MOMENTUM_UNIVERSE},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_report_from_history(
    bars_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    source_receipt_ids: Sequence[str],
    release_sha: str,
    observed_at: str,
    completed_through_session: str,
) -> dict[str, Any]:
    """Evaluate the fixed ETF card and add a seven-day freshness boundary."""
    if not is_valid_release_sha(release_sha):
        raise ValueError("release_sha_invalid")
    card = strategy_card()
    costs = card.to_mapping()["cost_model"]
    result = simulate(
        bars_by_symbol,
        universe=ETF_MOMENTUM_UNIVERSE,
        lookback_days=126,
        hold_days=21,
        notional_usd=NOTIONAL_USD,
        entry_fee_bps=Decimal(str(costs["entry_fee_bps"])),
        exit_fee_bps=Decimal(str(costs["exit_fee_bps"])),
        entry_slippage_bps=Decimal(str(costs["entry_slippage_bps"])),
        exit_slippage_bps=Decimal(str(costs["exit_slippage_bps"])),
    )
    grid = screen_grid(
        bars_by_symbol,
        universe=ETF_MOMENTUM_UNIVERSE,
        lookbacks=LOOKBACKS,
        hold_days=HOLD_DAYS,
        notional_usd=NOTIONAL_USD,
        entry_fee_bps=Decimal(str(costs["entry_fee_bps"])),
        exit_fee_bps=Decimal(str(costs["exit_fee_bps"])),
        entry_slippage_bps=Decimal(str(costs["entry_slippage_bps"])),
        exit_slippage_bps=Decimal(str(costs["exit_slippage_bps"])),
    )
    normalized_observed_at = _utc_timestamp(observed_at)
    report_id = (
        f"{card.strategy_id}-{completed_through_session}-"
        f"{_history_digest(bars_by_symbol)[:12]}"
    )
    report = build_validation_report(
        card,
        result,
        grid,
        release_sha=release_sha,
        report_id=report_id,
        evidence_ids=list(source_receipt_ids),
        observed_at=normalized_observed_at,
    )
    report["expires_at"] = (
        _parse_timestamp(normalized_observed_at) + timedelta(days=REPORT_TTL_DAYS)
    ).isoformat().replace("+00:00", "Z")
    report["completed_through_session"] = completed_through_session
    return report


def _atomic_write(path: Path, payload: bytes) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("validation_report_path_invalid")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if descriptor != -1:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def write_reports(path: str | Path, report: Mapping[str, Any]) -> None:
    destination = Path(path).expanduser()
    encoded = json.dumps(
        {"reports": [dict(report)]}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    _atomic_write(destination, (encoded + "\n").encode("utf-8"))


def _default_credentials_path() -> Path:
    value = (os.environ.get("ALPACA_INVESTMENT_PAPER_CREDENTIALS_FILE")
             or os.environ.get("ANICCA_CREDENTIALS_FILE"))
    return Path(value).expanduser() if value else Path("~/.local/share/anicca/credentials.json").expanduser()


def _default_cli_path() -> Path:
    return Path(os.environ.get("ALPACA_CLI", "~/.local/bin/alpaca")).expanduser()


def _release_sha(value: str | None) -> str:
    resolved = value or os.environ.get("LIFE_MANAGER_RELEASE_SHA")
    if not is_valid_release_sha(resolved):
        raise ValueError("release_sha_invalid")
    return resolved


def run_once(
    *,
    reports_path: str | Path,
    selection_path: str | Path,
    credentials_path: Path | None = None,
    cli_path: Path | None = None,
    release_sha: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any]:
    """Fetch, evaluate, persist, and provision one read-only validation cycle."""
    resolved_release = _release_sha(release_sha)
    resolved_end = end_date or datetime.now(ZoneInfo("America/New_York")).date()
    resolved_start = start_date or (resolved_end - timedelta(days=HISTORY_CALENDAR_DAYS))
    ranges = _chunk_ranges(resolved_start, resolved_end)
    history = [
        read_etf_daily_history(
            credentials_path=credentials_path or _default_credentials_path(),
            cli_path=cli_path or _default_cli_path(),
            start=start,
            end=end,
        )
        for start, end in ranges
    ]
    merged = _merge_history(history)
    report = build_report_from_history(
        merged["daily_bars"],
        source_receipt_ids=merged["source_receipt_ids"],
        release_sha=resolved_release,
        observed_at=merged["observed_at"],
        completed_through_session=merged["completed_through_session"],
    )
    write_reports(reports_path, report)
    selection = provision_selection(
        selection_path,
        reports_path,
        runtime_release_sha=resolved_release,
        refresh=True,
    )
    return {
        "status": "ok",
        "report_id": report["report_id"],
        "report_decision": report["decision"],
        "selection_status": selection["status"],
        "chunks": len(ranges),
        "completed_through_session": merged["completed_through_session"],
    }


def _date_arg(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-path", required=True)
    parser.add_argument("--selection-path", required=True)
    parser.add_argument("--credentials-path", type=Path)
    parser.add_argument("--cli-path", type=Path)
    parser.add_argument("--release-sha")
    parser.add_argument("--start-date", type=_date_arg)
    parser.add_argument("--end-date", type=_date_arg)
    args = parser.parse_args(argv)
    try:
        result = run_once(
            reports_path=args.reports_path,
            selection_path=args.selection_path,
            credentials_path=args.credentials_path,
            cli_path=args.cli_path,
            release_sha=args.release_sha,
            start_date=args.start_date,
            end_date=args.end_date,
        )
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CHUNK_CALENDAR_DAYS", "ETF_MOMENTUM_UNIVERSE", "HISTORY_CALENDAR_DAYS",
    "build_report_from_history", "main", "run_once", "write_reports", "_chunk_ranges",
]
