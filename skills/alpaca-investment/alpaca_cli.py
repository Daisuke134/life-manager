"""Pinned, paper-only Alpaca CLI observation boundary."""

from __future__ import annotations

import json
import hashlib
import os
import re
import stat
import subprocess
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from risk_day import reconcile as reconcile_risk_day

from risk_policy import parse_instant
from etf_ownership import ETF_STRATEGY_ID, ETF_SYMBOLS, investment_owner_id
from crypto_ownership_proof import validate_crypto_activity_page_chunk, crypto_fx_quote_request, crypto_fx_quote_proof, _digest, _fx_instant


CLI_VERSION = "0.0.14"
PAPER_ENDPOINT = "https://paper-api.alpaca.markets/v2"
LIVE_ENDPOINT = "https://api.alpaca.markets/v2"
ETF_DAILY_SYMBOLS = ("SPY", "QQQ", "IWM", "DIA", "EFA", "EEM", "TLT", "GLD")
ETF_DAILY_LOOKBACK_SESSIONS = 127
ETF_HISTORY_MAX_CALENDAR_DAYS = 90
MAX_CREDENTIAL_BYTES = 1_048_576
MAX_OUTPUT_BYTES = 64 * 1024
MAX_MULTI_BARS_OUTPUT_BYTES = 512 * 1024
MAX_CRYPTO_VALIDATION_HISTORY_PAGES = 10
CLI_OPERATIONS = frozenset({
    "account_activity", "account_get", "api_GET", "asset_get", "clock_get", "data_crypto",
    "data_latest-quotes", "data_latest-trade", "data_multi-bars", "data_option", "data_quotes", "order_list",
    "order_submit", "position_list",
})
SAFE_ERROR_CODES = frozenset({
    "crypto_fx_quote_invalid", "crypto_fx_quote_missing", "crypto_fx_quote_stale",
    "owned_position_changed_before_submit", "entry_policy_changed_before_submit",
    "entry_position_changed_before_submit", "owned_close_proof_invalid",
    "owned_close_receipt_missing", "owned_close_receipt_conflict",
    "owned_closed_identity_invalid", "owned_no_fill_proof_invalid",
    "owned_entry_account_invalid", "owned_entry_account_pending",
    "owned_entry_receipt_missing", "owned_entry_receipt_conflict",
    "crypto_activity_period_invalid", "crypto_activity_invalid", "crypto_activity_limit_exceeded", "crypto_activity_account_invalid",
    "owned_crypto_fills_pending", "owned_crypto_fills_invalid",
    "owned_sell_proof_invalid", "owned_sell_receipt_missing", "owned_sell_receipt_conflict", "owned_sell_account_pending",
    "owned_no_fill_receipt_missing", "owned_no_fill_receipt_conflict",
    "alpaca_allocator_risk_invalid", "alpaca_allocator_shape_invalid",
    "alpaca_crypto_history_invalid",
    "alpaca_etf_daily_bars_invalid",
    "alpaca_cli_json_invalid", "alpaca_cli_output_too_large", "alpaca_cli_unavailable",
    "alpaca_cli_version_unpinned", "alpaca_credential_record_invalid",
    "alpaca_live_credentials_unavailable", "alpaca_paper_credentials_unavailable",
    "alpaca_shadow_credentials_unavailable", "credential_document_invalid",
    "credential_file_too_large", "credential_path_invalid", "credential_permissions_invalid",
    "investment_mode_invalid",
})

CRYPTO_VALIDATION_REASON_CODES = frozenset({
    "response_shape_invalid", "pagination_incomplete", "symbol_set_invalid",
    "symbol_bars_invalid", "bar_count_exceeded", "bar_timestamp_invalid",
    "bar_timestamp_outside_window", "bar_timestamp_unaligned",
    "bar_timestamp_not_increasing", "bar_price_invalid", "bar_ohlc_invalid",
    "btc_bar_count_mismatch", "btc_timestamp_gap", "malformed_payload",
})


class CryptoValidationHistoryError(ValueError):
    """Safe reason code and non-sensitive counts for one validation input failure."""

    def __init__(self, reason_code: str, **details: Any):
        self.reason_code = (reason_code if reason_code in CRYPTO_VALIDATION_REASON_CODES
                            else "malformed_payload")
        allowed_details = {
            "symbol", "expected_count", "actual_count", "row_index",
            "page_number", "received_count",
        }
        self.details = {
            key: value for key, value in details.items()
            if key in allowed_details and type(value) in {str, int}
        }
        super().__init__(f"alpaca_crypto_validation_history_invalid:{self.reason_code}")


def _selected_mode(mode: str | None = None) -> str:
    value = mode if mode is not None else os.environ.get("LIFE_MANAGER_INVESTMENT_MODE")
    if value not in {"paper", "shadow", "live"}:
        raise ValueError("investment_mode_invalid")
    return value


def _credentials(path: Path, mode: str | None = None) -> dict[str, str]:
    mode = _selected_mode(mode)
    parent, info = path.parent, path.lstat()
    if path.is_symlink() or parent.is_symlink():
        raise ValueError("credential_path_invalid")
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("credential_path_invalid")
    if stat.S_IMODE(info.st_mode) != 0o600 or stat.S_IMODE(parent.stat().st_mode) != 0o700:
        raise ValueError("credential_permissions_invalid")
    if info.st_size > MAX_CREDENTIAL_BYTES:
        raise ValueError("credential_file_too_large")
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("credential_document_invalid")
    rows = [row for row in document.get("credentials", [])
            if isinstance(row, dict) and row.get("service") == "app.alpaca.markets"]
    if len(rows) != 1:
        raise ValueError("alpaca_credential_record_invalid")
    row = rows[0]
    endpoint_key = "paper_endpoint" if mode == "paper" else "live_endpoint"
    endpoint = PAPER_ENDPOINT if mode == "paper" else LIVE_ENDPOINT
    if row.get(endpoint_key) != endpoint:
        raise ValueError(f"alpaca_{mode}_credentials_unavailable")
    fields = ("api_key", "api_secret") if mode == "paper" else ("live_api_key", "live_api_secret")
    values = {"api_key": row.get(fields[0]), "api_secret": row.get(fields[1])}
    if any(not isinstance(value, str) or not value or len(value) > 8192
           for value in values.values()):
        raise ValueError(f"alpaca_{mode}_credentials_unavailable")
    return values  # type: ignore[return-value]


def _context(credentials_path: Path, cli_path: Path, mode: str | None = None) -> dict[str, str]:
    mode = _selected_mode(mode)
    if not cli_path.is_file() or not os.access(cli_path, os.X_OK):
        raise ValueError("alpaca_cli_unavailable")
    private = _credentials(credentials_path, mode)
    env = {
        **os.environ,
        "ALPACA_API_KEY": private["api_key"],
        "ALPACA_SECRET_KEY": private["api_secret"],
        "ALPACA_LIVE_TRADE": "false" if mode == "paper" else "true",
    }
    version = subprocess.run(
        [str(cli_path), "version"], env=env, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=10, check=False,
    )
    if version.returncode != 0 or version.stdout.strip() != CLI_VERSION:
        raise ValueError("alpaca_cli_version_unpinned")
    return env


def _run(cli: Path, args: list[str], env: dict[str, str]) -> Any:
    operation = "_".join(args[:2])
    if operation not in CLI_OPERATIONS:
        operation = "unknown"
    try:
        result = subprocess.run(
            [str(cli), *args], env=env, stdin=subprocess.DEVNULL,
            capture_output=True, timeout=30, check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError(f"alpaca_cli_timeout:{operation}") from error
    if result.returncode != 0:
        raise ValueError(f"alpaca_cli_failed:{operation}")
    bounded_btc_bars = args[:5] == ["data", "crypto", "bars", "--symbols", "BTC/USDC"]
    output_limit = (MAX_MULTI_BARS_OUTPUT_BYTES if operation == "data_multi-bars" or bounded_btc_bars
                    else MAX_OUTPUT_BYTES)
    if len(result.stdout) > output_limit:
        raise ValueError("alpaca_cli_output_too_large")
    try:
        return json.loads(result.stdout.decode("utf-8").strip())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("alpaca_cli_json_invalid") from error


def _read_activity_pages(cli_path: Path, env: dict[str, str], *, kind: str | None,
                         after: str, until: str, query: str, error_prefix: str,
                         max_pages: int = 10, page_token: str | None = None,
                         page_sink: list | None = None) -> list[dict[str, Any]]:
    """Read a fixed window to an observed short page, never infer missing pages."""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _page in range(max_pages):
        args = ["account", "activity", "list", *(["--activity-types", kind] if kind is not None else []),
                "--after", after, "--until", until, "--page-size", "100",
                "--direction", "asc", "--quiet", "--jq", query]
        if page_token is not None:
            args.extend(["--page-token", page_token])
        page = _run(cli_path, args, env)
        if not isinstance(page, list) or len(page) > 100:
            raise ValueError(f"{error_prefix}_activity_invalid")
        for row in page:
            if (not isinstance(row, dict) or (row.get("activity_type") != kind if kind is not None else
                    not isinstance(row.get("activity_type"),str) or not row["activity_type"].strip())
                    or not isinstance(row.get("id"), str) or not row["id"].strip()
                    or row["id"] in seen):
                raise ValueError(f"{error_prefix}_activity_invalid")
            seen.add(row["id"])
        result.extend(page)
        if page_sink is not None: page_sink.append(page)
        if len(page) < 100:
            return result
        page_token = page[-1]["id"]
    raise ValueError(f"{error_prefix}_activity_limit_exceeded")


def _capture_crypto_flow_evidence(*, cli_path: Path, env: dict[str, str], mode: str,
                                 native_trading_account_id: str | None, clock: dict | None,
                                 after: str, until: str, page_token: str | None = None) -> dict[str, Any]:
    frame={'mode':mode,'paper':mode=='paper','native_trading_account_id':native_trading_account_id,
        'clock':clock,'wallet_transfers':None,
        'wallet_status':'unsupported_on_paper' if mode=='paper' else 'unknown',
        'activity_request':{'after':after,'until':until,'direction':'asc','page_size':100},
        'activity_pages':[],'activity_pagination':'unknown','next_page_token':None,
        'capture_status':'pending','fee_completeness_status':'unknown','net_pnl_usd':None}
    if page_token is not None:
        frame['activity_request']['page_token']=page_token
    def capture_error(prefix,error):
        code=str(error)
        safe=(code in SAFE_ERROR_CODES or code.startswith('crypto_flow_') or
            (code.partition(':')[0] in {'alpaca_cli_timeout','alpaca_cli_failed'} and code.partition(':')[2] in CLI_OPERATIONS))
        frame[prefix+'_error_class']=type(error).__name__
        frame[prefix+'_error_code']=code if safe else type(error).__name__
    if not isinstance(native_trading_account_id,str) or not native_trading_account_id.strip():
        capture_error('capture',ValueError('crypto_flow_account_invalid'))
    else:
        if mode!='paper':
            try:
                frame['wallet_transfers']=_run(cli_path,
                    ['api','GET','/v2/wallets/transfers','--quiet','--jq','.'],env)
                if (not isinstance(frame['wallet_transfers'],list) or
                        any(not isinstance(row,dict) for row in frame['wallet_transfers'])):
                    raise ValueError('crypto_flow_wallet_invalid')
                frame['wallet_status']='observed'
            except Exception as error:
                frame['wallet_status']='failed';capture_error('wallet',error)
        try:
            _read_activity_pages(cli_path,env,kind=None,after=after,until=until,query='.',
                error_prefix='crypto_flow',max_pages=4,page_token=page_token,page_sink=frame['activity_pages'])
            frame['activity_pagination']='exhausted'
        except Exception as error:
            pages=frame['activity_pages']
            frame.update(activity_pagination='partial' if pages else 'unknown',
                next_page_token=pages[-1][-1]['id'] if pages and len(pages[-1])==100 else None)
            capture_error('capture',error)
    failed=any(key in frame for key in ('capture_error_code','wallet_error_code'))
    frame['capture_status']=('partial' if frame['activity_pages'] or frame['wallet_status']=='observed' else 'failed') if failed else 'captured'
    return json.loads(json.dumps(frame))


def read_crypto_flow_evidence(*, credentials_path: Path, cli_path: Path, mode: str,
                              period_start: str, period_end: str, native_trading_account_id: str,
                              page_token: str | None = None) -> dict[str, Any]:
    """Retain bounded raw flows for one exact account/window, without fee authority."""
    if mode not in ('paper','live'):
        raise ValueError('investment_mode_invalid')
    if (not isinstance(native_trading_account_id,str) or not native_trading_account_id.strip()
            or (page_token is not None and (not isinstance(page_token,str) or not page_token.strip()
                                           or len(page_token)>8192))):
        raise ValueError('crypto_flow_context_invalid')
    try:
        start,end=_fx_instant(period_start),_fx_instant(period_end)
        if start>end or end-start>90*86400:raise ValueError
    except (ValueError,TypeError,AttributeError,ArithmeticError) as error:
        raise ValueError('crypto_flow_period_invalid') from error
    env=_context(credentials_path,cli_path,mode=mode)
    account=_run(cli_path,['account','get','--quiet','--jq','{id}'],env)
    if not isinstance(account,dict) or account.get('id')!=native_trading_account_id:
        raise ValueError('crypto_flow_account_invalid')
    return _capture_crypto_flow_evidence(cli_path=cli_path,env=env,mode=mode,
        native_trading_account_id=account['id'],clock=None,after=period_start,until=period_end,
        page_token=page_token)


def read_crypto_activity_evidence(*, credentials_path: Path, cli_path: Path,
                                  mode: str, period_start: str, period_end: str) -> dict[str, Any]:
    """Capture raw activity evidence; exhaustion does not prove fee settlement.

    CFEE can be posted later without an order_id. Retain all account activities
    in the window; ownership and fee attribution belong to the proof consumer.
    """
    if mode not in {"paper", "live"}:
        raise ValueError("investment_mode_invalid")
    try:
        start, end = parse_instant(period_start), parse_instant(period_end)
        if start > end or end - start > timedelta(days=90):
            raise ValueError
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("crypto_activity_period_invalid") from error
    # Activities are filtered by creation time. Include the entire start day
    # and retain each provider timestamp/date rather than relabeling it a fill.
    after = start.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    after_text = after.isoformat().replace("+00:00", "Z")
    until = end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    env = _context(credentials_path, cli_path, mode=mode)
    account = _run(cli_path, ["account", "get", "--quiet", "--jq", "{id}"], env)
    if not isinstance(account, dict) or not isinstance(account.get("id"), str) or not account["id"].strip():
        raise ValueError("crypto_activity_account_invalid")
    fills, fees = [_read_activity_pages(cli_path, env, kind=kind, after=after_text,
        until=until, query=".", error_prefix="crypto", max_pages=4) for kind in ("FILL", "CFEE")]
    if len({row["id"] for row in [*fills, *fees]}) != len(fills) + len(fees):
        raise ValueError("crypto_activity_invalid")
    snapshot = {"schema_version": 1, "mode": mode, "paper": mode == "paper", "native_trading_account_id": account["id"],
        "requested_period_start": period_start, "requested_period_end": period_end,
        "request": {"after": after_text, "until": until, "direction": "asc", "page_size": 100},
        "pagination": "exhausted", "fills": fills, "fees": fees,
        "fee_attribution_status": "unknown", "fee_settlement_status": "unknown",
        "net_realized_pnl_usd": None}
    # Content address of this local snapshot, not a provider-issued receipt ID.
    snapshot["source_receipt_id"] = "alpaca-crypto-activities:" + _digest_rows([snapshot])
    return snapshot


def read_crypto_activity_page_chunk(*, credentials_path: Path, cli_path: Path, mode: str,
                                    period_start: str, period_end: str, activity_type: str,
                                    page_token: str | None = None) -> dict[str, Any]:
    if (mode not in {'paper','live'} or activity_type not in {'FILL','CFEE'}
            or (page_token is not None and (not isinstance(page_token,str) or not page_token.strip()))):
        raise ValueError('crypto_activity_page_context_invalid')
    try:
        start,end=parse_instant(period_start),parse_instant(period_end)
        if start>end or end-start>timedelta(days=90): raise ValueError
    except (ValueError,TypeError,AttributeError) as error:
        raise ValueError('crypto_activity_period_invalid') from error
    after=start.astimezone(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).isoformat().replace('+00:00','Z')
    until=end.astimezone(timezone.utc).isoformat().replace('+00:00','Z');pages=[]
    env=_context(credentials_path,cli_path,mode=mode)
    account=_run(cli_path,['account','get','--quiet','--jq','{id}'],env)
    if not isinstance(account,dict) or not isinstance(account.get('id'),str) or not account['id'].strip():
        raise ValueError('crypto_activity_account_invalid')
    try:
        _read_activity_pages(cli_path,env,kind=activity_type,after=after,until=until,query='.',
            error_prefix='crypto',max_pages=4,page_token=page_token,page_sink=pages)
    except ValueError as error:
        if str(error)!='crypto_activity_limit_exceeded' or len(pages)!=4 or any(len(p)!=100 for p in pages): raise
    next_token=pages[-1][-1]['id'] if len(pages[-1])==100 else None
    body={'schema_version':1,'kind':'crypto_activity_page_chunk','mode':mode,'paper':mode=='paper','native_trading_account_id':account['id'],
        'requested_period_start':period_start,'requested_period_end':period_end,
        'request':{'after':after,'until':until,'direction':'asc','page_size':100,
                   'activity_type':activity_type,'page_token':page_token},'pages':pages,
        'pagination':'partial' if next_token is not None else 'exhausted','next_page_token':next_token}
    body['source_receipt_id']='alpaca-crypto-activity-chunk:'+_digest_rows([body])
    validate_crypto_activity_page_chunk(body,mode=mode)
    return body


def read_paper_etf_cost_evidence(
    *, credentials_path: Path, cli_path: Path,
    orders: list[Mapping[str, Any]], period_start: str,
) -> dict[str, Any]:
    """Measure paper execution slippage; regulatory fees are not simulated."""
    if (not isinstance(orders, list) or len(orders) != 2
            or not isinstance(period_start, str)):
        raise ValueError("paper_cost_orders_invalid")
    expected: dict[str, dict[str, Any]] = {}
    try:
        for raw in orders:
            if not isinstance(raw, Mapping):
                raise ValueError
            order_id = raw.get("id")
            symbol = raw.get("symbol")
            side = raw.get("side")
            qty = Decimal(str(raw.get("filled_qty")))
            price = Decimal(str(raw.get("filled_avg_price")))
            if (not isinstance(order_id, str) or not order_id
                    or order_id in expected or symbol not in ETF_SYMBOLS
                    or side not in {"buy", "sell"} or not qty.is_finite() or qty <= 0
                    or not price.is_finite() or price <= 0):
                raise ValueError
            expected[order_id] = {
                "symbol": symbol, "side": side, "filled_qty": qty,
                "filled_avg_price": price,
            }
        if ({row["side"] for row in expected.values()} != {"buy", "sell"}
                or len({row["symbol"] for row in expected.values()}) != 1
                or len({row["filled_qty"] for row in expected.values()}) != 1):
            raise ValueError
        start = parse_instant(period_start)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("paper_cost_orders_invalid") from error

    env = _context(credentials_path, cli_path, mode="paper")
    clock = _run(cli_path, ["clock", "get", "--quiet", "--jq", "{timestamp}"], env)
    try:
        if not isinstance(clock, Mapping):
            raise ValueError
        observed = parse_instant(clock["timestamp"])
        if start > observed:
            raise ValueError
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("paper_cost_period_invalid") from error
    after = start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    until = observed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def activities(kind: str, query: str) -> list[dict[str, Any]]:
        return _read_activity_pages(cli_path, env, kind=kind, after=after,
                                    until=until, query=query, error_prefix="paper_cost")

    all_fills = activities(
        "FILL", "[.[]|{id,activity_type,order_id,symbol,side,qty,price,transaction_time}]",
    )
    fills_by_order: dict[str, list[dict[str, Any]]] = {order_id: [] for order_id in expected}
    seen_fill_ids: set[str] = set()
    try:
        for row in all_fills:
            row_id, order_id = row.get("id"), row.get("order_id")
            symbol, side = row.get("symbol"), row.get("side")
            qty, price = Decimal(str(row.get("qty"))), Decimal(str(row.get("price")))
            filled_at = parse_instant(row.get("transaction_time"))
            if (row.get("activity_type") != "FILL" or not isinstance(row_id, str)
                    or not row_id or row_id in seen_fill_ids
                    or not isinstance(order_id, str) or not order_id
                    or not isinstance(symbol, str) or not symbol
                    or side not in {"buy", "sell"} or not qty.is_finite() or qty <= 0
                    or not price.is_finite() or price <= 0
                    or filled_at < start or filled_at > observed):
                raise ValueError
            seen_fill_ids.add(row_id)
            if order_id in expected:
                if filled_at < start:
                    raise ValueError
                order = expected[order_id]
                if symbol != order["symbol"] or side != order["side"]:
                    raise ValueError
                fills_by_order[order_id].append({
                    "id": row_id, "activity_type": "FILL", "order_id": order_id,
                    "symbol": symbol, "side": side, "qty": str(qty),
                    "price": str(price), "transaction_time": row["transaction_time"],
                })
        for order_id, order in expected.items():
            fills = fills_by_order[order_id]
            qty = sum((Decimal(row["qty"]) for row in fills), Decimal("0"))
            notional = sum((Decimal(row["qty"]) * Decimal(row["price"])
                            for row in fills), Decimal("0"))
            if (not fills or qty != order["filled_qty"]
                    or abs(notional / qty - order["filled_avg_price"]) > Decimal("0.000001")):
                raise ValueError
    except (InvalidOperation, KeyError, TypeError, ValueError) as error:
        raise ValueError("paper_cost_fill_mismatch") from error

    quotes_by_fill_id: dict[str, dict[str, str]] = {}
    try:
        for fills in fills_by_order.values():
            for row in fills:
                filled_at = parse_instant(row["transaction_time"])
                start_quote = filled_at - timedelta(seconds=2)
                # Use the consolidated feed; an IEX-only quote is not a market-wide execution reference.
                quotes = _run(cli_path, [
                    "data", "quotes", "--symbol", row["symbol"],
                    "--start", start_quote.isoformat().replace("+00:00", "Z"),
                    "--end", filled_at.isoformat().replace("+00:00", "Z"),
                    "--feed", "sip", "--limit", "1000", "--sort", "asc",
                    "--quiet", "--jq",
                    "{quotes: (.quotes|map({t,bp,ap})), next_page_token}",
                ], env)
                if not isinstance(quotes, Mapping):
                    raise ValueError
                if "next_page_token" not in quotes:
                    raise ValueError
                if quotes.get("next_page_token") not in (None, ""):
                    raise ValueError("paper_cost_quote_pages_incomplete")
                quote_rows = quotes.get("quotes")
                if not isinstance(quote_rows, list) or not quote_rows:
                    raise ValueError
                prior_quotes = [
                    (parse_instant(item.get("t")), item) for item in quote_rows
                    if parse_instant(item.get("t")) <= filled_at
                ]
                if not prior_quotes:
                    raise ValueError
                quote_at, nearest = max(prior_quotes, key=lambda pair: pair[0])
                bid, ask = Decimal(str(nearest.get("bp"))), Decimal(str(nearest.get("ap")))
                if ((filled_at - quote_at).total_seconds() > 1
                        or not bid.is_finite() or not ask.is_finite()
                        or bid <= 0 or ask < bid):
                    raise ValueError
                quotes_by_fill_id[row["id"]] = {
                    "t": nearest["t"], "bp": str(bid), "ap": str(ask),
                }
    except (InvalidOperation, KeyError, TypeError, ValueError) as error:
        if str(error) == "paper_cost_quote_pages_incomplete":
            raise
        raise ValueError("paper_cost_quote_invalid") from error

    target_fills = [row for rows in fills_by_order.values() for row in rows]
    buy_notional = sum((Decimal(row["qty"]) * Decimal(row["price"])
                        for row in target_fills if row["side"] == "buy"), Decimal("0"))
    sell_notional = sum((Decimal(row["qty"]) * Decimal(row["price"])
                         for row in target_fills if row["side"] == "sell"), Decimal("0"))
    slippage = Decimal("0")
    for row in target_fills:
        quote = quotes_by_fill_id[row["id"]]
        midpoint = (Decimal(quote["bp"]) + Decimal(quote["ap"])) / 2
        quantity, price = Decimal(row["qty"]), Decimal(row["price"])
        slippage += ((price - midpoint) if row["side"] == "buy" else (midpoint - price)) * quantity
    source_ids = [*[row["id"] for rows in fills_by_order.values() for row in rows],
                  *[f"alpaca-quote:{fill_id}:{row['t']}"
                    for fill_id, row in quotes_by_fill_id.items()]]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("paper_cost_receipt_duplicate")
    return {
        "broker_fees_usd": None,
        "broker_fees_status": "not_simulated",
        "broker_gross_pnl_usd": str(sell_notional - buy_notional),
        "broker_slippage_usd": format(slippage.normalize(), "f"),
        "broker_slippage_status": "complete",
        "broker_costs_status": "partial",
        "broker_costs_reason": "paper_regulatory_fees_not_simulated",
        "observed_at": clock["timestamp"],
        "order_ids": sorted(expected),
        "period_start": start.isoformat().replace("+00:00", "Z"),
        "provider": "alpaca",
        "provider_readback": {
            "fills": target_fills,
            "quotes_by_fill_id": quotes_by_fill_id,
        },
        "source_receipt_ids": source_ids,
    }


def observe(*, credentials_path: Path, cli_path: Path, symbol: str = "SPY") -> dict[str, Any]:
    if symbol != "SPY":
        raise ValueError("unsupported_observation_symbol")
    mode = _selected_mode()
    env = _context(credentials_path, cli_path, mode)

    account = _run(cli_path, [
        "account", "get", "--quiet", "--jq",
        "{id:.id,status:.status,cash:.cash,equity:.equity,last_equity:.last_equity,options_level:.options_trading_level}",
    ], env)
    clock = _run(cli_path, [
        "clock", "get", "--quiet", "--jq",
        "{is_open:.is_open,observed_at:.timestamp,next_open:.next_open,next_close:.next_close}",
    ], env)
    positions = _run(cli_path, [
        "position", "list", "--quiet", "--jq",
        "[.[]|{symbol,qty,side,avg_entry_price,current_price,market_value,unrealized_pl}]",
    ], env)
    orders = _run(cli_path, [
        "order", "list", "--quiet", "--status", "all", "--limit", "500", "--jq", "length",
    ], env)
    activities = _run(cli_path, [
        "account", "activity", "list", "--quiet", "--jq", "length",
    ], env)
    trade = _run(cli_path, [
        "data", "latest-trade", "--symbol", symbol, "--quiet", "--jq",
        "{symbol:.symbol,price:.trade.p,timestamp:.trade.t}",
    ], env)
    options = _run(cli_path, [
        "data", "option", "chain", "--underlying-symbol", symbol, "--limit", "100", "--quiet", "--jq",
        "(.snapshots|length)",
    ], env)
    if not isinstance(account, dict) or not isinstance(clock, dict):
        raise ValueError("alpaca_cli_shape_invalid")
    if not isinstance(positions, list) or not isinstance(orders, int):
        raise ValueError("alpaca_cli_shape_invalid")
    if not isinstance(activities, int) or not isinstance(trade, dict) or not isinstance(options, int):
        raise ValueError("alpaca_cli_shape_invalid")
    return {
        "account": account,
        "activities_count": activities,
        "cli_version": CLI_VERSION,
        "clock": clock,
        "observed_symbol": symbol,
        "open_and_closed_orders_count": orders,
        "option_contracts_count": options,
        "mode": mode,
        "paper": mode == "paper",
        "positions": positions,
        "trade": trade,
    }


def find_order_by_client_id(
    *, credentials_path: Path, cli_path: Path, client_order_id: str,
) -> dict[str, Any] | None:
    if not re.fullmatch(r"lm-ai-[0-9a-f]{24}", client_order_id):
        raise ValueError("client_order_id_invalid")
    env = _context(credentials_path, cli_path)
    query = (
        f"first(.[]|select(.client_order_id=={json.dumps(client_order_id)})) // "
        "{found:false}|if .found==false then . else "
        "{found:true,id:.id,client_order_id:.client_order_id,status:.status,"
        "symbol:.symbol,side:.side,type:.type,time_in_force:.time_in_force,"
        "notional:.notional,qty:.qty,filled_qty:.filled_qty,"
        "filled_avg_price:.filled_avg_price,submitted_at:.submitted_at,filled_at:.filled_at} end"
    )
    result = _run(cli_path, [
        "order", "list", "--quiet", "--status", "all", "--limit", "500", "--jq", query,
    ], env)
    if result == {"found": False}:
        return None
    if not isinstance(result, dict) or result.get("found") is not True:
        raise ValueError("alpaca_order_readback_invalid")
    return result


def read_campaign_snapshot(
    *, credentials_path: Path, cli_path: Path, symbols: tuple[str, str],
) -> dict[str, Any]:
    mode = _selected_mode()
    env = _context(credentials_path, cli_path, mode)
    account = _run(cli_path, [
        "account", "get", "--quiet", "--jq",
        "{cash:.cash,equity:.equity,last_equity:.last_equity}",
    ], env)
    positions = _run(cli_path, [
        "position", "list", "--quiet", "--jq",
        "[.[]|{symbol,qty,side,avg_entry_price,current_price,market_value,unrealized_pl}]",
    ], env)
    fills = _run(cli_path, [
        "account", "activity", "list", "--activity-types", "FILL", "--page-size", "100",
        "--direction", "asc", "--quiet", "--jq",
        "[.[]|{order_id,symbol,side:(if .side==\"sell_short\" then \"sell\" else .side end),qty,price,transaction_time}]",
    ], env)
    clock = _run(cli_path, [
        "clock", "get", "--quiet", "--jq", "{is_open:.is_open,observed_at:.timestamp}",
    ], env)
    option_query = (
        ".snapshots|to_entries|map({symbol:.key,bid:.value.latestQuote.bp,"
        "ask:.value.latestQuote.ap,quote_at:.value.latestQuote.t})"
    )
    options = _run(cli_path, [
        "data", "option", "snapshot", "--symbols", ",".join(symbols),
        "--limit", "2", "--quiet", "--jq", option_query,
    ], env)
    if not isinstance(account, dict) or not isinstance(clock, dict):
        raise ValueError("alpaca_campaign_shape_invalid")
    if not isinstance(positions, list) or not isinstance(fills, list) or not isinstance(options, list):
        raise ValueError("alpaca_campaign_shape_invalid")
    return {
        "account": account,
        "clock": clock,
        "fills": [fill for fill in fills if fill.get("symbol") in symbols],
        "options": options,
        "mode": mode,
        "paper": mode == "paper",
        "positions": [position for position in positions if position.get("symbol") in symbols],
        "unexpected_positions": [position.get("symbol") for position in positions
                                 if position.get("symbol") not in symbols],
    }


def _normalize_etf_daily_bars(
    rows: Any,
    clock: Mapping[str, Any],
    *,
    start_session: date | None = None,
    end_session: date | None = None,
    max_sessions: int | None = ETF_DAILY_LOOKBACK_SESSIONS,
    minimum_sessions: int = ETF_DAILY_LOOKBACK_SESSIONS,
) -> dict[str, Any]:
    if not isinstance(rows, list) or not isinstance(clock, Mapping):
        raise ValueError("alpaca_etf_daily_bars_invalid")
    is_open = clock.get("is_open")
    if not isinstance(is_open, bool):
        raise ValueError("alpaca_etf_daily_bars_invalid")
    try:
        observed = parse_instant(clock["timestamp"])
        current_session = observed.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("alpaca_etf_daily_bars_invalid") from error

    by_symbol: dict[str, dict[str, dict[str, str]]] = {}
    try:
        for item in rows:
            if not isinstance(item, dict):
                raise ValueError
            symbol = item.get("symbol")
            if symbol not in ETF_DAILY_SYMBOLS or symbol in by_symbol:
                raise ValueError
            raw_bars = item.get("bars")
            if not isinstance(raw_bars, list) or not raw_bars:
                raise ValueError
            normalized: dict[str, dict[str, str]] = {}
            previous_session: str | None = None
            for raw in raw_bars:
                if not isinstance(raw, dict):
                    raise ValueError
                timestamp = parse_instant(raw["t"])
                session = timestamp.astimezone(ZoneInfo("America/New_York")).date().isoformat()
                session_date = date.fromisoformat(session)
                if ((start_session is not None and session_date < start_session)
                        or (end_session is not None and session_date > end_session)):
                    raise ValueError
                if session > current_session:
                    raise ValueError
                if is_open and session == current_session:
                    continue
                opening = Decimal(str(raw["o"]))
                closing = Decimal(str(raw["c"]))
                if (not opening.is_finite() or not closing.is_finite()
                        or opening <= 0 or closing <= 0):
                    raise ValueError
                if previous_session is not None:
                    if session == previous_session or session < previous_session:
                        raise ValueError
                normalized[session] = {
                    "t": str(raw["t"]), "o": str(opening), "c": str(closing),
                }
                previous_session = session
            if not normalized:
                raise ValueError
            by_symbol[symbol] = normalized
        if set(by_symbol) != set(ETF_DAILY_SYMBOLS):
            raise ValueError
        common_sessions = set.intersection(*(set(rows_by_session) for rows_by_session in by_symbol.values()))
        if len(common_sessions) < minimum_sessions:
            raise ValueError
        selected_sessions = sorted(common_sessions)
        if max_sessions is not None:
            selected_sessions = selected_sessions[-max_sessions:]
        aligned = {
            symbol: [by_symbol[symbol][session] for session in selected_sessions]
            for symbol in ETF_DAILY_SYMBOLS
        }
        completed = selected_sessions[-1]
        canonical = json.dumps(
            {"symbols": ETF_DAILY_SYMBOLS, "completed_through_session": completed,
             "daily_bars": aligned}, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        source_hash = hashlib.sha256(canonical).hexdigest()
    except (InvalidOperation, KeyError, TypeError, ValueError) as error:
        raise ValueError("alpaca_etf_daily_bars_invalid") from error
    return {
        "daily_bars": aligned,
        "completed_through_session": completed,
        "observed_at": clock["timestamp"],
        "source_receipt_ids": [
            f"alpaca://stock-bars/iex/split/{completed}/{source_hash}"
        ],
    }


def read_etf_daily_bars(
    *, credentials_path: Path, cli_path: Path, clock: Mapping[str, Any],
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Read a bounded, split-adjusted IEX daily ETF window without an effect."""
    try:
        observed = parse_instant(clock["timestamp"])
        current_session = observed.astimezone(ZoneInfo("America/New_York")).date()
        start = current_session - timedelta(days=260)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("alpaca_etf_daily_bars_invalid") from error
    context = env if env is not None else _context(credentials_path, cli_path)
    rows = _run(cli_path, [
        "data", "multi-bars", "--symbols", ",".join(ETF_DAILY_SYMBOLS),
        "--start", start.isoformat(), "--end", current_session.isoformat(),
        "--timeframe", "1Day", "--adjustment", "split", "--feed", "iex",
        "--limit", "2000", "--sort", "asc", "--quiet", "--jq",
        ".bars|to_entries|map({symbol:.key,bars:(.value|map({t,o,c}))})",
    ], context)
    return _normalize_etf_daily_bars(rows, clock)


def read_etf_daily_history(
    *, credentials_path: Path, cli_path: Path, start: date, end: date,
) -> dict[str, Any]:
    """Read one bounded, paper-only, split-adjusted IEX daily ETF history chunk."""
    if (not isinstance(start, date) or isinstance(start, datetime)
            or not isinstance(end, date) or isinstance(end, datetime)
            or end < start
            or (end - start).days > ETF_HISTORY_MAX_CALENDAR_DAYS):
        raise ValueError("alpaca_etf_daily_bars_invalid")
    context = _context(credentials_path, cli_path, mode="paper")
    clock = _run(cli_path, [
        "clock", "get", "--quiet", "--jq", "{is_open:.is_open,timestamp:.timestamp}",
    ], context)
    if not isinstance(clock, Mapping):
        raise ValueError("alpaca_etf_daily_bars_invalid")
    try:
        observed = parse_instant(clock["timestamp"])
        current_session = observed.astimezone(ZoneInfo("America/New_York")).date()
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("alpaca_etf_daily_bars_invalid") from error
    if end > current_session:
        raise ValueError("alpaca_etf_daily_bars_invalid")
    rows = _run(cli_path, [
        "data", "multi-bars", "--symbols", ",".join(ETF_DAILY_SYMBOLS),
        "--start", start.isoformat(), "--end", end.isoformat(),
        "--timeframe", "1Day", "--adjustment", "split", "--feed", "iex",
        "--limit", "2000", "--sort", "asc", "--quiet", "--jq",
        ".bars|to_entries|map({symbol:.key,bars:(.value|map({t,o,c}))})",
    ], context)
    return _normalize_etf_daily_bars(
        rows,
        clock,
        start_session=start,
        end_session=end,
        max_sessions=None,
        minimum_sessions=1,
    )


def read_allocator_snapshot(
    *, credentials_path: Path, cli_path: Path, risk_day_path: Path,
    include_etf_bars: bool = False, flow_sink: list | None = None,
) -> dict[str, Any]:
    """Read candidate inputs, optionally retaining raw pre-trade flow observations."""
    env = _context(credentials_path, cli_path)
    account = _run(cli_path, [
        "account", "get", "--quiet", "--jq",
        "{id:.id,cash:.cash,equity:.equity,last_equity:.last_equity}",
    ], env)
    clock = _run(cli_path, [
        "clock", "get", "--quiet", "--jq", "{is_open:.is_open,timestamp:.timestamp}",
    ], env)
    if not isinstance(account, dict) or not isinstance(clock, dict):
        raise ValueError("alpaca_allocator_shape_invalid")
    try:
        observed = parse_instant(clock["timestamp"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("alpaca_allocator_risk_invalid") from error
    ny_day = observed.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    ny_zone = ZoneInfo("America/New_York")
    day_start = datetime.combine(observed.astimezone(ny_zone).date(), time.min, ny_zone)
    day_end = day_start + timedelta(days=1)
    cash_activities = _run(cli_path, [
        "account", "activity", "list", "--activity-types", "CSD,CSW",
        "--after", day_start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "--until", day_end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "--direction", "asc", "--quiet", "--jq",
        "[.[]|{activity_type,date,net_amount}]",
    ], env)
    if os.environ.get("LIFE_MANAGER_INVESTMENT_MODE") == "paper":
        # The paper trading host exposes no wallet-transfer resource (it
        # returns 404). Paper cash movements are already represented by the
        # account CSD/CSW activities read above; keep the risk-day input empty
        # instead of failing every paper wake on an unsupported read-only API.
        crypto_transfers = []
    else:
        crypto_transfers = _run(cli_path, [
            "api", "GET", "/v2/wallets/transfers", "--quiet", "--jq",
            "[.[]|{id,asset,usd_value,direction,status}]",
        ], env)
    trade_activities = _run(cli_path, [
        "account", "activity", "list", "--activity-types", "FILL",
        "--after", day_start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "--until", day_end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "--direction", "asc", "--quiet", "--jq", "[.[]|.id]",
    ], env)
    positions = _run(cli_path, ["position", "list", "--quiet", "--jq",
        "[.[]|{symbol,market_value,unrealized_pl}]"], env)
    orders = _run(cli_path, [
        "order", "list", "--quiet", "--status", "open", "--limit", "500", "--jq", "length",
    ], env)
    spy = _run(cli_path, [
        "data", "latest-trade", "--symbol", "SPY", "--quiet", "--jq",
        "{price:.trade.p,timestamp:.trade.t}",
    ], env)
    crypto = _run(cli_path, [
        "data", "crypto", "latest-quotes", "--symbols", "BTC/USDC,ETH/USDC", "--quiet", "--jq",
        ".quotes|to_entries|map({symbol:.key,bid:.value.bp,ask:.value.ap,quote_at:.value.t})",
    ], env)
    qqq_asset = _run(cli_path, [
        "asset", "get", "--symbol-or-asset-id", "QQQ", "--quiet", "--jq",
        "{symbol,tradable,status,overnight_tradable,overnight_halted,fractionable}",
    ], env)
    qqq_quote = _run(cli_path, [
        "data", "latest-quotes", "--symbols", "QQQ", "--quiet", "--jq",
        ".quotes.QQQ|{bid:.bp,ask:.ap,quote_at:.t}",
    ], env)
    price = float(spy["price"])
    option_query = (
        ".snapshots|to_entries|map({symbol:.key,bid:.value.latestQuote.bp,"
        "ask:.value.latestQuote.ap,quote_at:.value.latestQuote.t})"
    )
    options = _run(cli_path, [
        "data", "option", "chain", "--underlying-symbol", "SPY",
        "--expiration-date-gte", str(date.today() + timedelta(days=7)),
        "--expiration-date-lte", str(date.today() + timedelta(days=45)),
        "--strike-price-gte", f"{price * .97:.2f}",
        "--strike-price-lte", f"{price * 1.03:.2f}",
        "--type", "call", "--limit", "100", "--quiet", "--jq", option_query,
    ], env)
    if (not isinstance(positions, list) or isinstance(orders, bool)
            or not isinstance(orders, int) or orders < 0):
        raise ValueError("alpaca_allocator_shape_invalid")
    if (not isinstance(cash_activities, list) or not isinstance(crypto_transfers, list)
            or not isinstance(trade_activities, list)
            or not isinstance(crypto, list) or not isinstance(options, list)):
        raise ValueError("alpaca_allocator_shape_invalid")
    try:
        equity = Decimal(str(account["equity"]))
        funding_positions = [row for row in positions if row.get("symbol") == "USDCUSD"]
        risk_positions = [row for row in positions if row.get("symbol") != "USDCUSD"]
        allocated = sum((abs(Decimal(str(row["market_value"]))) for row in risk_positions), Decimal("0"))
        available_cash = Decimal(str(account["cash"])) + sum(
            (Decimal(str(row["market_value"])) for row in funding_positions), Decimal("0"))
        unrealized = sum((Decimal(str(row["unrealized_pl"])) for row in positions), Decimal("0"))
        if any(not isinstance(row, dict) or row.get("activity_type") not in {"CSD", "CSW"}
               for row in cash_activities):
            raise ValueError
        cash_flow = sum((Decimal(str(row["net_amount"])) for row in cash_activities), Decimal("0"))
        values = (equity, allocated, available_cash, unrealized, cash_flow)
        if any(not value.is_finite() for value in values):
            raise ValueError
        daily = reconcile_risk_day(risk_day_path, observed_at=observed, equity=equity,
                                   bank_cash_flow=cash_flow, transfers=crypto_transfers,
                                   trade_activity_ids=trade_activities,
                                   official_unrealized=unrealized)
        risk = {"allocated_capital_usd": str(allocated), **daily,
                "unrealized_pnl_usd": str(unrealized),
                "observed_at": clock["timestamp"],
                "ny_day": ny_day}
    except (KeyError, InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("alpaca_allocator_risk_invalid") from error
    result = {"account": account, "available_cash_usd": str(available_cash),
            "clock": clock, "crypto": crypto,
            "open_orders": orders, "option_quotes": options, "positions": len(risk_positions), "risk": risk,
            "qqq_asset": qqq_asset, "qqq_quote": qqq_quote, "spy": spy}
    if include_etf_bars:
        result.update(read_etf_daily_bars(
            credentials_path=credentials_path, cli_path=cli_path,
            clock=clock, env=env,
        ))
    if flow_sink is not None:
        after=day_start.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
        flow_sink.append(_capture_crypto_flow_evidence(cli_path=cli_path,env=env,mode=_selected_mode(),
            native_trading_account_id=account.get('id'),clock=clock,after=after,until=clock['timestamp']))
    return result


def read_crypto_history(*, credentials_path: Path, cli_path: Path,
                        observed_at: str, history_bars: int | None = None) -> dict[str, list[dict[str, Any]]]:
    """Keep legacy history unchanged; v2 requires exactly 800 completed BTC bars."""
    observed = parse_instant(observed_at)
    if history_bars is not None and (type(history_bars) is not int or history_bars != 800):
        raise ValueError("alpaca_crypto_history_invalid")
    window_end = (observed.replace(second=0, microsecond=0) - timedelta(minutes=observed.minute % 5)
                  if history_bars is not None else observed)
    window = timedelta(minutes=5 * history_bars) if history_bars is not None else timedelta(hours=8)
    window_start = window_end - window
    max_bars = window // timedelta(minutes=5) + 1
    start = window_start.isoformat().replace("+00:00", "Z")
    end = window_end.isoformat().replace("+00:00", "Z")
    env = _context(credentials_path, cli_path)
    projection = ".bars|to_entries|map({symbol:.key,bars:(.value|map({t,o,h,l,c}))})"
    if history_bars is not None:
        projection = "{next_page_token,rows:(" + projection + ")}"
    rows = _run(cli_path, ["data", "crypto", "bars", "--symbols",
        "BTC/USDC" if history_bars is not None else "BTC/USDC,ETH/USDC", "--start", start, "--end", end,
        "--timeframe", "5Min", "--limit", "1000", "--sort", "asc", "--quiet", "--jq", projection], env)
    if history_bars is not None:
        if not isinstance(rows, dict) or "next_page_token" not in rows or rows["next_page_token"] is not None:
            raise ValueError("alpaca_crypto_history_invalid")
        rows = rows.get("rows")
    if not isinstance(rows, list):
        raise ValueError("alpaca_crypto_history_invalid")
    result: dict[str, list[dict[str, Any]]] = {}
    try:
        for row in rows:
            symbol, bars = row["symbol"], row["bars"]
            # Bound the inclusive provider response before dropping a forming bar.
            if symbol not in ({"BTC/USDC"} if history_bars is not None else {"BTC/USDC", "ETH/USDC"}) or symbol in result \
                    or not isinstance(bars, list) or len(bars) > max_bars:
                raise ValueError
            normalized = []
            previous_timestamp = None
            for bar in bars:
                timestamp = parse_instant(bar["t"])
                values = [Decimal(str(bar[key])) for key in ("o", "h", "l", "c")]
                if (timestamp < window_start or timestamp > window_end
                        or (previous_timestamp is not None
                            and (timestamp <= previous_timestamp
                                 or (timestamp - previous_timestamp).total_seconds() % 300 != 0))
                        or any(not value.is_finite() or value <= 0 for value in values)
                        or values[1] < max(values[0], values[2], values[3])
                        or values[2] > min(values[0], values[1], values[3])):
                    raise ValueError
                previous_timestamp = timestamp
                if (history_bars is not None and timestamp == window_end) or observed - timestamp < timedelta(minutes=5):
                    continue
                normalized.append({"t": bar["t"], "o": str(values[0]), "h": str(values[1]),
                                   "l": str(values[2]), "c": str(values[3])})
            result[symbol] = normalized
        btc = result.get("BTC/USDC")
        if history_bars is not None and (not btc or len(btc) != history_bars or any(
                parse_instant(row["t"]) != window_start + timedelta(minutes=5 * index)
                for index, row in enumerate(btc))):
            raise ValueError
        if not btc or len(btc) < 6 or observed - parse_instant(btc[-1]["t"]) > timedelta(minutes=15):
            raise ValueError
    except (InvalidOperation, KeyError, TypeError, ValueError) as error:
        raise ValueError("alpaca_crypto_history_invalid") from error
    return result


def read_crypto_validation_history(
    *, credentials_path: Path, cli_path: Path, start: datetime, end: datetime,
    observed_at: str,
) -> dict[str, Any]:
    """Read bounded paper-context BTC bars and exact-time USD valuation bars."""
    observed = parse_instant(observed_at)
    if (not isinstance(start, datetime) or not isinstance(end, datetime)
            or start.tzinfo is None or end.tzinfo is None
            or not timedelta(0) < end - start <= timedelta(hours=6)
            or end > observed or any(moment.timestamp() % 300 for moment in (start, end))):
        raise ValueError("alpaca_crypto_validation_range_invalid")
    start_text = start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    end_text = end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    context = _context(credentials_path, cli_path, mode="paper")
    locations = {"BTC/USDC": "us", "USDC/USD": "us-1"}
    source_evidence: dict[str, str] = {}
    count = int((end - start).total_seconds() // 300)
    try:
        rows_by_symbol: dict[str, list[dict[str, str]]] = {}
        for symbol, location in locations.items():
            raw_rows: list[dict[str, Any]] = []
            seen_page_tokens: set[str] = set()
            page_token = None
            for page_number in range(1, MAX_CRYPTO_VALIDATION_HISTORY_PAGES + 1):
                projection = ("{t,o,h,l,c}" if symbol == "BTC/USDC" else "{t,c}")
                args = ["data", "crypto", "bars", "--symbols", symbol,
                    "--start", start_text, "--end", end_text, "--timeframe", "5Min",
                    "--limit", "1000", "--sort", "asc", "--loc", location,
                    "--quiet", "--jq",
                    "{next_page_token,bars:(.bars|with_entries(.value|=map(" + projection + ")))}"]
                if page_token is not None:
                    args.extend(["--page-token", page_token])
                payload = _run(cli_path, args, context)
                if not isinstance(payload, dict) or "next_page_token" not in payload:
                    raise CryptoValidationHistoryError("response_shape_invalid")
                next_page_token = payload["next_page_token"]
                if next_page_token == "":  # Alpaca may emit an empty-string end marker.
                    next_page_token = None
                elif next_page_token is not None and (
                        not isinstance(next_page_token, str) or not next_page_token.strip()
                        or len(next_page_token) > 8192 or next_page_token in seen_page_tokens):
                    raise CryptoValidationHistoryError(
                        "pagination_incomplete", page_number=page_number,
                        received_count=len(raw_rows),
                    )
                page_rows_by_symbol = payload.get("bars")
                if (not isinstance(page_rows_by_symbol, dict)
                        or set(page_rows_by_symbol) - {symbol}):
                    raise CryptoValidationHistoryError("symbol_set_invalid")
                page_rows = page_rows_by_symbol.get(symbol, [])
                if not isinstance(page_rows, list):
                    raise CryptoValidationHistoryError("symbol_bars_invalid", symbol=symbol)
                raw_rows.extend(page_rows)
                if next_page_token is None:
                    break
                if not page_rows:
                    raise CryptoValidationHistoryError(
                        "pagination_incomplete", page_number=page_number,
                        received_count=len(raw_rows),
                    )
                seen_page_tokens.add(next_page_token)
                if page_number == MAX_CRYPTO_VALIDATION_HISTORY_PAGES:
                    raise CryptoValidationHistoryError(
                        "pagination_incomplete", page_number=page_number,
                        received_count=len(raw_rows),
                    )
                page_token = next_page_token
            else:
                raise CryptoValidationHistoryError(
                    "pagination_incomplete", page_number=MAX_CRYPTO_VALIDATION_HISTORY_PAGES,
                    received_count=len(raw_rows),
                )

            if len(raw_rows) > count + 1:
                raise CryptoValidationHistoryError(
                    "bar_count_exceeded", symbol=symbol,
                    expected_count=count + 1, actual_count=len(raw_rows),
                )
            normalized = []
            previous = None
            for row_index, row in enumerate(raw_rows):
                try:
                    timestamp = parse_instant(row["t"])
                except (KeyError, TypeError, ValueError, OverflowError) as error:
                    raise CryptoValidationHistoryError(
                        "bar_timestamp_invalid", symbol=symbol, row_index=row_index,
                    ) from error
                if timestamp < start or timestamp > end:
                    raise CryptoValidationHistoryError(
                        "bar_timestamp_outside_window", symbol=symbol, row_index=row_index,
                    )
                if timestamp.timestamp() % 300:
                    raise CryptoValidationHistoryError(
                        "bar_timestamp_unaligned", symbol=symbol, row_index=row_index,
                    )
                if previous is not None and timestamp <= previous:
                    raise CryptoValidationHistoryError(
                        "bar_timestamp_not_increasing", symbol=symbol, row_index=row_index,
                    )
                keys = ("o", "h", "l", "c") if symbol == "BTC/USDC" else ("c",)
                try:
                    prices = {key: Decimal(str(row[key])) for key in keys}
                except (InvalidOperation, KeyError, TypeError, ValueError) as error:
                    raise CryptoValidationHistoryError(
                        "bar_price_invalid", symbol=symbol, row_index=row_index,
                    ) from error
                if any(not price.is_finite() or price <= 0 for price in prices.values()):
                    raise CryptoValidationHistoryError(
                        "bar_price_invalid", symbol=symbol, row_index=row_index,
                    )
                if (symbol == "BTC/USDC"
                        and (prices["h"] < max(prices.values())
                             or prices["l"] > min(prices.values()))):
                    raise CryptoValidationHistoryError(
                        "bar_ohlc_invalid", symbol=symbol, row_index=row_index,
                    )
                previous = timestamp
                if timestamp == end:
                    continue  # Exclusive end makes adjacent history chunks disjoint.
                normalized.append({"t": timestamp.astimezone(timezone.utc).isoformat(),
                                   **{key: str(price) for key, price in prices.items()}})
            rows_by_symbol[symbol] = normalized
            digest = hashlib.sha256(json.dumps({
                "location": location, "symbol": symbol, "start": start_text,
                "end": end_text, "bars": normalized,
            }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            source_evidence[symbol] = (
                f"alpaca://crypto-bars/{location}/5Min/{symbol}/{start_text}/{end_text}/{digest}"
            )

        btc = rows_by_symbol["BTC/USDC"]
    except CryptoValidationHistoryError:
        raise
    except (InvalidOperation, KeyError, OverflowError, TypeError, ValueError) as error:
        raise CryptoValidationHistoryError("malformed_payload") from error
    fx_timestamps = {row["t"] for row in rows_by_symbol["USDC/USD"]}
    matched_fx = sum(row["t"] in fx_timestamps for row in btc)
    coverage = {
        "expected_btc_slots": count,
        "observed_btc_bars": len(btc),
        "unobserved_btc_slots": count - len(btc),
        "fx_matched_btc_bars": matched_fx,
        "btc_bars_without_exact_fx": len(btc) - matched_fx,
        "synthetic_bars": 0,
        "btc_location": locations["BTC/USDC"],
        "fx_location": locations["USDC/USD"],
    }
    return {"crypto_history": btc, "quote_conversions": [
        {"timestamp": row["t"], "currency": "USDC", "rate": row["c"],
         "evidence_ref": source_evidence["USDC/USD"]}
        for row in rows_by_symbol.get("USDC/USD", [])],
        "source_receipt_ids": list(source_evidence.values()),
        "market_data_coverage": coverage, "observed_at": observed_at}


def read_crypto_fx_evidence(*,credentials_path: Path,cli_path: Path,mode: str,asof_at: str,observed_at: str) -> dict[str,Any]:
    request=crypto_fx_quote_request(mode=mode,asof_at=asof_at,observed_at=observed_at)
    env=_context(credentials_path,cli_path,mode=mode)
    response=_run(cli_path,['data','crypto','quotes','--symbols','USDC/USD',
        '--start',request['start'],'--end',request['end'],'--sort','desc','--limit','1','--quiet','--jq',
        '{next_page_token,quotes:(.quotes|with_entries(.value|=map({t,bp,ap})))}'],env)
    body={'schema_version':1,'kind':'crypto_fx_asof_quote','mode':mode,'paper':mode=='paper',
        'symbol':'USDC/USD','base_currency':'USDC','quote_currency':'USD','asof_at':asof_at,
        'observed_at':observed_at,'request':request,'response':response}
    body['source_receipt_id']='alpaca-crypto-fx-quote:'+_digest(body)
    crypto_fx_quote_proof(body,mode=mode,asof_at=asof_at)
    return body


def read_live_performance_snapshot(
    *, credentials_path: Path, cli_path: Path, period_start: str,
    buy_client_order_id: str, sell_client_order_id: str,
) -> dict[str, Any]:
    """Rebuild the one completed live round trip from official broker records."""
    if (buy_client_order_id == sell_client_order_id
            or any(not re.fullmatch(r"lm-ai-[0-9a-f]{24}", value)
                   for value in (buy_client_order_id, sell_client_order_id))):
        raise ValueError("live_performance_order_ids_invalid")
    start = parse_instant(period_start)
    env = _context(credentials_path, cli_path, "live")
    clients = json.dumps([buy_client_order_id, sell_client_order_id])
    account = _run(cli_path, ["account", "get", "--quiet", "--jq", "{cash,equity}"], env)
    clock = _run(cli_path, ["clock", "get", "--quiet", "--jq", "{timestamp}"], env)
    positions = _run(cli_path, ["position", "list", "--quiet", "--jq",
        "[.[]|{symbol,qty,market_value,unrealized_pl,current_price}]"], env)
    transfers = _run(cli_path, ["api", "GET", "/v2/wallets/transfers", "--quiet", "--jq",
        "[.[]|{id,asset,amount,usd_value,direction,status,created_at}]"], env)
    orders = _run(cli_path, ["order", "list", "--quiet", "--status", "all", "--limit", "500",
        "--jq", f"[.[]|select(.client_order_id as $id|{clients}|index($id))|"
        "{id,client_order_id,status,symbol,side,filled_qty}]"], env)
    order_ids = json.dumps([row.get("id") for row in orders]) if isinstance(orders, list) else "[]"
    fills = _run(cli_path, ["account", "activity", "list", "--activity-types", "FILL",
        "--page-size", "100", "--direction", "asc", "--quiet", "--jq",
        f"[.[]|select(.order_id as $id|{order_ids}|index($id))|"
        "{id,activity_type,order_id,symbol,side,qty,price,transaction_time}]"], env)
    fees = _run(cli_path, ["account", "activity", "list", "--activity-types", "CFEE",
        "--page-size", "100", "--direction", "asc", "--quiet", "--jq",
        f"[.[]|select(.order_id as $id|{order_ids}|index($id))|"
        "{id,activity_type,order_id,symbol,qty,price,date}]"], env)

    def quotes(begin: datetime, end: datetime) -> list[dict[str, Any]]:
        value = _run(cli_path, ["data", "crypto", "quotes", "--symbols", "BTC/USDC",
            "--start", begin.isoformat().replace("+00:00", "Z"),
            "--end", end.isoformat().replace("+00:00", "Z"), "--limit", "1000",
            "--sort", "asc", "--quiet", "--jq",
            '.quotes["BTC/USDC"]|map({t,bp,ap})'], env)
        if not isinstance(value, list) or not value:
            raise ValueError("live_performance_quote_missing")
        return value

    try:
        if (not isinstance(account, dict) or not isinstance(clock, dict)
                or not isinstance(positions, list) or not isinstance(transfers, list)
                or not isinstance(orders, list) or not isinstance(fills, list)
                or not isinstance(fees, list) or len(orders) != 2 or len(fills) != 2
                or len(fees) != 2 or len(positions) != 1):
            raise ValueError
        by_client = {row["client_order_id"]: row for row in orders}
        buy_order, sell_order = by_client[buy_client_order_id], by_client[sell_client_order_id]
        if (buy_order.get("side") != "buy" or sell_order.get("side") != "sell"
                or any(row.get("status") != "filled" or row.get("symbol") not in
                       {"BTC/USDC", "BTCUSDC"} for row in orders)):
            raise ValueError
        by_order = {row["order_id"]: row for row in fills}
        buy_fill, sell_fill = by_order[buy_order["id"]], by_order[sell_order["id"]]
        expected_order_ids = {buy_order["id"], sell_order["id"]}
        if (set(by_order) != expected_order_ids or buy_fill.get("side") != "buy"
                or sell_fill.get("side") != "sell"
                or any(row.get("activity_type") != "FILL" for row in fills)
                or {row.get("order_id") for row in fees} != expected_order_ids
                or any(row.get("activity_type") != "CFEE" for row in fees)):
            raise ValueError
        complete = [row for row in transfers if row.get("asset") == "USDC"
                    and row.get("direction") == "INCOMING" and row.get("status") == "COMPLETE"]
        if len(complete) != 1 or positions[0].get("symbol") != "USDCUSD":
            raise ValueError
        transfer, position = complete[0], positions[0]
        observed = parse_instant(clock["timestamp"])
        if start > observed or parse_instant(transfer["created_at"]) > start:
            raise ValueError
        buy_time, sell_time = (parse_instant(row["transaction_time"])
                               for row in (buy_fill, sell_fill))
        if not start <= buy_time < sell_time <= observed:
            raise ValueError
        start_quotes = quotes(start, start + timedelta(seconds=30))
        fill_quotes = [quotes(moment - timedelta(seconds=2), moment + timedelta(seconds=2))
                       for moment in (buy_time, sell_time)]
        latest = _run(cli_path, ["data", "crypto", "latest-quotes", "--symbols", "BTC/USDC",
            "--quiet", "--jq", '.quotes["BTC/USDC"]|{t,bp,ap}'], env)
        clock = _run(cli_path, ["clock", "get", "--quiet", "--jq", "{timestamp}"], env)
        observed = parse_instant(clock["timestamp"])
        latest_age = observed - parse_instant(latest["t"]) if isinstance(latest, dict) else None
        if latest_age is None or not timedelta(0) <= latest_age <= timedelta(minutes=15):
            raise ValueError

        def number(value: Any) -> Decimal:
            result = Decimal(str(value))
            if not result.is_finite():
                raise ValueError
            return result

        def nearest(rows: list[dict[str, Any]], moment: datetime) -> dict[str, Any]:
            row = min(rows, key=lambda item: abs((parse_instant(item["t"]) - moment).total_seconds()))
            bid, ask = number(row["bp"]), number(row["ap"])
            if (abs((parse_instant(row["t"]) - moment).total_seconds()) > 1
                    or bid <= 0 or ask < bid):
                raise ValueError
            return row

        buy_ref, sell_ref = nearest(fill_quotes[0], buy_time), nearest(fill_quotes[1], sell_time)
        buy_qty, sell_qty = number(buy_fill["qty"]), number(sell_fill["qty"])
        buy_price, sell_price = number(buy_fill["price"]), number(sell_fill["price"])
        if (buy_qty <= 0 or sell_qty <= 0 or buy_price <= 0 or sell_price <= 0
                or buy_qty != number(buy_order["filled_qty"])
                or sell_qty != number(sell_order["filled_qty"])
                or any(number(row["qty"]) >= 0 or number(row["price"]) <= 0 for row in fees)):
            raise ValueError
        slippage = max(Decimal("0"), buy_price - number(buy_ref["ap"])) * buy_qty
        slippage += max(Decimal("0"), number(sell_ref["bp"]) - sell_price) * sell_qty
        fee_total = sum((abs(number(row["qty"])) * number(row["price"]) for row in fees), Decimal("0"))
        transfer_amount, transfer_usd = number(transfer["amount"]), number(transfer["usd_value"])
        position_qty, position_value = number(position["qty"]), number(position["market_value"])
        unrealised = number(position["unrealized_pl"])
        ending_nav = number(account["cash"]) + position_value
        # The provider's marked ending NAV is authoritative. Valuing the
        # position-quantity delta at the current mark and adding unrealized
        # P&L double-counts the mark when the residual USDC position moves.
        realised_usd = (ending_nav - transfer_usd) - unrealised
        if (transfer_amount <= 0 or transfer_usd <= 0
                or abs(number(account["equity"]) - ending_nav) > Decimal("0.01")
                or abs((realised_usd + unrealised) - (ending_nav - transfer_usd)) > Decimal("0.01")):
            raise ValueError
        start_quote = start_quotes[0]
        start_quote_time = parse_instant(start_quote["t"])
        if not start <= start_quote_time <= start + timedelta(seconds=30):
            raise ValueError

        def midpoint(row: dict[str, Any]) -> Decimal:
            bid, ask = number(row["bp"]), number(row["ap"])
            if bid <= 0 or ask < bid:
                raise ValueError
            return (bid + ask) / 2

        benchmark_start, benchmark_end = midpoint(start_quote), midpoint(latest)
        source_ids = [transfer["id"], buy_order["id"], sell_order["id"],
                      *(row["id"] for row in fills), *(row["id"] for row in fees),
                      f"BTC/USDC@{start_quote['t']}", f"BTC/USDC@{latest['t']}"]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError
    except (InvalidOperation, KeyError, TypeError, ValueError) as error:
        raise ValueError("live_performance_receipts_invalid") from error
    return {
        "benchmark_end_price_usd": str(benchmark_end),
        "benchmark_start_price_usd": str(benchmark_start),
        "completed_round_trips": 1,
        "ending_nav_usd": str(ending_nav),
        "fees_usd": str(fee_total),
        "gross_exposure_usd": str(buy_qty * buy_price),
        "observed_at": clock["timestamp"],
        "owner_cash_flow_usd": str(transfer_usd),
        "period_start": period_start,
        "realized_pnl_usd": str(realised_usd),
        "schema_version": 1,
        "slippage_usd": str(slippage),
        "source_receipt_ids": source_ids,
        "starting_nav_usd": "0",
        "unrealized_pnl_usd": str(unrealised),
    }


def submit_order(
    *, credentials_path: Path, cli_path: Path, client_order_id: str,
    order: dict[str, Any], mode: str | None = None,
    owner_id: str | None = None, strategy_id: str | None = None,
) -> dict[str, Any]:
    """Submit gated orders with one bounded BTC transport and explicit mode context."""
    if not re.fullmatch(r"lm-ai-[0-9a-f]{24}", client_order_id):
        raise ValueError("client_order_id_invalid")
    mode = _selected_mode(mode)
    if mode == "shadow":
        raise ValueError("investment_mode_effect_forbidden")
    if mode == "live" or order.get("asset_class") == "crypto":
        shape_error = "unsupported_live_order_shape" if mode == "live" else "unsupported_order_shape"
        if mode == "live" and order.get("asset_class") == "us_equity":
            raise ValueError("live_etf_rejected")
        expected = {"asset_class", "side", "symbol", "time_in_force", "type"}
        if order.get("symbol") != "BTC/USDC" or order.get("asset_class") != "crypto" \
                or order.get("type") != "market" or order.get("time_in_force") != "gtc":
            raise ValueError(shape_error)
        if order.get("side") == "buy":
            expected.add("notional_usd")
            try:
                amount = Decimal(str(order.get("notional_usd")))
                valid = amount.is_finite() and Decimal("0") < amount <= Decimal("10")
            except InvalidOperation:
                valid = False
            if set(order) != expected or not valid:
                raise ValueError(shape_error)
            args = ["order", "submit", "--quiet", "--symbol", "BTC/USDC",
                    "--notional", str(order["notional_usd"]), "--side", "buy", "--type", "market",
                    "--time-in-force", "gtc", "--client-order-id", client_order_id]
        elif order.get("side") == "sell":
            expected.add("qty")
            try:
                qty = Decimal(str(order.get("qty")))
                valid = qty.is_finite() and qty > 0 and qty.as_tuple().exponent >= -9
            except InvalidOperation:
                valid = False
            if set(order) != expected or not valid:
                raise ValueError(shape_error)
            args = ["order", "submit", "--quiet", "--symbol", "BTC/USDC", "--qty", str(order["qty"]),
                    "--side", "sell", "--type", "market", "--time-in-force", "gtc",
                    "--client-order-id", client_order_id]
        else:
            raise ValueError(shape_error)
        env = _context(credentials_path, cli_path, mode)
        result = _run(cli_path, [*args, "--jq",
            "{client_order_id,status,submitted_at,symbol,notional,qty,side,type,time_in_force}"], env)
        if not isinstance(result, dict) or result.get("client_order_id") != client_order_id:
            raise ValueError("alpaca_submit_readback_invalid")
        return result
    if order.get("asset_class") == "us_equity":
        if owner_id != investment_owner_id() or strategy_id != ETF_STRATEGY_ID:
            raise ValueError("etf_order_identity_invalid")
        common = {"asset_class", "side", "symbol", "time_in_force", "type"}
        if (order.get("symbol") not in ETF_SYMBOLS or order.get("type") != "market"
                or order.get("time_in_force") != "day"):
            raise ValueError("etf_order_shape_invalid")
        if order.get("side") == "buy":
            expected = common | {"notional_usd"}
            try:
                notional = Decimal(str(order.get("notional_usd")))
                valid_shape = notional.is_finite() and notional == Decimal("10.00")
            except InvalidOperation:
                valid_shape = False
            if set(order) != expected or not valid_shape:
                raise ValueError("etf_order_shape_invalid")
            args = ["order", "submit", "--quiet", "--symbol", order["symbol"],
                    "--notional", order["notional_usd"], "--side", "buy", "--type", "market",
                    "--time-in-force", "day", "--client-order-id", client_order_id]
        elif order.get("side") == "sell":
            expected = common | {"qty"}
            try:
                qty = Decimal(str(order.get("qty")))
                valid_shape = qty.is_finite() and qty > 0 and qty.as_tuple().exponent >= -9
            except InvalidOperation:
                valid_shape = False
            if set(order) != expected or not valid_shape:
                raise ValueError("etf_order_shape_invalid")
            args = ["order", "submit", "--quiet", "--symbol", order["symbol"],
                    "--qty", order["qty"], "--side", "sell", "--type", "market",
                    "--time-in-force", "day", "--client-order-id", client_order_id]
        else:
            raise ValueError("etf_order_shape_invalid")
    elif order.get("asset_class") in {"option_spread", "option_spread_close"}:
        closing = order["asset_class"] == "option_spread_close"
        legs = json.dumps([
            {"symbol": order["long_symbol"], "ratio_qty": "1",
             "position_intent": "sell_to_close" if closing else "buy_to_open"},
            {"symbol": order["short_symbol"], "ratio_qty": "1",
             "position_intent": "buy_to_close" if closing else "sell_to_open"},
        ], separators=(",", ":"))
        args = ["order", "submit", "--quiet", "--order-class", "mleg", "--qty", "1",
                "--type", "limit", "--limit-price", order["limit_price"],
                "--time-in-force", "day", "--legs", legs,
                "--client-order-id", client_order_id]
    else:
        raise ValueError("unsupported_order_shape")
    env = _context(credentials_path, cli_path, mode)
    result = _run(cli_path, [*args, "--jq",
        "{id,client_order_id,status,submitted_at,symbol,notional,qty,filled_qty,"
        "filled_avg_price,side,type,time_in_force}"], env)
    if not isinstance(result, dict) or result.get("client_order_id") != client_order_id:
        raise ValueError("alpaca_submit_readback_invalid")
    if order.get("asset_class") == "us_equity":
        common_valid = (
            result.get("symbol") in ETF_SYMBOLS
            and result.get("symbol") == order.get("symbol")
            and result.get("side") == order.get("side")
            and result.get("type") == "market"
            and result.get("time_in_force") == "day"
            and isinstance(result.get("id"), str)
            and bool(result["id"])
        )
        if order.get("side") == "buy":
            try:
                acknowledged_notional = Decimal(str(result.get("notional")))
            except InvalidOperation:
                acknowledged_notional = Decimal("0")
            common_valid = common_valid and acknowledged_notional == Decimal("10.00")
        else:
            try:
                acknowledged_qty = Decimal(str(result.get("qty")))
                requested_qty = Decimal(str(order.get("qty")))
            except InvalidOperation:
                acknowledged_qty = requested_qty = Decimal("0")
            common_valid = common_valid and acknowledged_qty == requested_qty
        if not common_valid:
            raise ValueError("alpaca_submit_readback_invalid")
    return result


def submit_live_canary(*, credentials_path: Path, cli_path: Path,
                       client_order_id: str, order: dict[str, Any]) -> dict[str, Any]:
    """Submit the single frozen L09 live canary; no scheduled loop calls this function."""
    expected = {"asset_class": "crypto", "notional_usd": "2.00", "side": "buy",
                "symbol": "BTC/USDC", "time_in_force": "gtc", "type": "market"}
    if order != expected or not re.fullmatch(r"lm-ai-[0-9a-f]{24}", client_order_id):
        raise ValueError("live_canary_shape_invalid")
    if _selected_mode() != "live":
        raise ValueError("investment_mode_effect_forbidden")
    env = _context(credentials_path, cli_path, "live")
    result = _run(cli_path, [
        "order", "submit", "--quiet", "--symbol", "BTC/USDC", "--notional", "2.00",
        "--side", "buy", "--type", "market", "--time-in-force", "gtc",
        "--client-order-id", client_order_id, "--jq",
        "{id,client_order_id,status,submitted_at,symbol,notional,side,type,time_in_force}",
    ], env)
    if (not isinstance(result, dict) or result.get("client_order_id") != client_order_id
            or result.get("symbol") not in {"BTC/USDC", "BTCUSDC"}
            or result.get("notional") != "2"
            or result.get("side") != "buy" or result.get("type") != "market"
            or result.get("time_in_force") != "gtc"):
        raise ValueError("live_canary_ack_invalid")
    return result


def read_live_canary(*, credentials_path: Path, cli_path: Path,
                     client_order_id: str) -> dict[str, Any]:
    """Verify the frozen canary from official order, FILL, and position records."""
    env = _context(credentials_path, cli_path, "live")
    query = (
        f"first(.[]|select(.client_order_id=={json.dumps(client_order_id)})) // "
        "{found:false}|if .found==false then . else "
        "{found:true,id,client_order_id,status,filled_qty,filled_avg_price,symbol,side,notional,type,time_in_force} end"
    )
    order = _run(cli_path, [
        "order", "list", "--quiet", "--status", "all", "--limit", "500", "--jq", query,
    ], env)
    if order == {"found": False}:
        return {"status": "absent", "verified": False}
    if not isinstance(order, dict) or order.get("found") is not True:
        raise ValueError("live_canary_order_invalid")
    if (order.get("client_order_id") != client_order_id
            or order.get("symbol") not in {"BTC/USDC", "BTCUSDC"}
            or order.get("side") != "buy" or order.get("notional") != "2"
            or order.get("type") != "market" or order.get("time_in_force") != "gtc"):
        raise ValueError("live_canary_order_mismatch")
    status = order.get("status")
    try:
        filled_qty = Decimal(str(order.get("filled_qty") or "0"))
    except InvalidOperation as error:
        raise ValueError("live_canary_order_invalid") from error
    if status in {"canceled", "expired", "rejected"} and filled_qty == 0:
        return {"status": "terminal_failure", "verified": False, "order": order}
    if status in {"canceled", "expired", "rejected"}:
        return {"status": "partial_terminal", "verified": False, "order": order}
    if status != "filled":
        return {"status": "pending", "verified": False, "order": order}
    fills = _run(cli_path, [
        "account", "activity", "list", "--activity-types", "FILL", "--order-id", str(order["id"]),
        "--page-size", "100",
        "--direction", "desc", "--quiet", "--jq",
        f"[.[]|select(.order_id=={json.dumps(order.get('id'))})|"
        "{order_id,symbol,side,qty,price,transaction_time}]",
    ], env)
    positions = _run(cli_path, [
        "position", "list", "--quiet", "--jq",
        "[.[]|select(.symbol==\"BTCUSD\" or .symbol==\"BTCUSDC\" or .symbol==\"BTC/USDC\")|"
        "{symbol,qty,market_value,unrealized_pl}]",
    ], env)
    try:
        if not isinstance(fills, list) or not fills or not isinstance(positions, list) \
                or len(positions) != 1:
            raise ValueError
        fill_total = sum((Decimal(str(fill["qty"])) for fill in fills), Decimal("0"))
        position_qty = Decimal(str(positions[0]["qty"]))
        if (any(fill.get("order_id") != order["id"] or fill.get("side") != "buy"
                or fill.get("symbol") not in {"BTC/USDC", "BTCUSDC"} for fill in fills)
                or fill_total != filled_qty
                or position_qty > filled_qty or position_qty < filled_qty * Decimal("0.99")
                or filled_qty <= 0):
            raise ValueError
    except (InvalidOperation, KeyError, TypeError, ValueError) as error:
        raise ValueError("live_canary_fill_mismatch") from error
    return {"status": "verified", "verified": True, "order": order,
            "fills": fills, "position": positions[0]}


def read_live_close_snapshot(*, credentials_path: Path, cli_path: Path) -> dict[str, Any]:
    """Read the narrow official state needed to close the L09 BTC holding."""
    env = _context(credentials_path, cli_path, "live")
    account = _run(cli_path, ["account", "get", "--quiet", "--jq",
        "{status,trading_blocked,transfers_blocked,account_blocked,crypto_status}"], env)
    orders = _run(cli_path, ["order", "list", "--quiet", "--status", "open", "--limit", "500",
        "--jq", "[.[]|{id,client_order_id,status,symbol,side}]"], env)
    positions = _run(cli_path, ["position", "list", "--quiet", "--jq",
        "[.[]|{symbol,qty,market_value,unrealized_pl}]"], env)
    asset = _run(cli_path, ["asset", "get", "--symbol-or-asset-id", "BTC/USDC", "--quiet", "--jq",
        "{symbol,status,tradable}"], env)
    quote = _run(cli_path, ["data", "crypto", "latest-quotes", "--symbols", "BTC/USDC",
        "--quiet", "--jq", ".quotes[\"BTC/USDC\"]|{bp,ap,t}"], env)
    fees = _run(cli_path, ["account", "activity", "list", "--activity-types", "CFEE",
        "--direction", "asc", "--quiet", "--jq",
        "[.[]|{activity_type,order_id,symbol,qty,price,date}]"], env)
    bank_flows = _run(cli_path, ["account", "activity", "list", "--activity-types", "CSD,CSW",
        "--direction", "asc", "--quiet", "--jq",
        "[.[]|{activity_type,id,date,net_amount}]"], env)
    transfers = _run(cli_path, ["api", "GET", "/v2/wallets/transfers", "--quiet", "--jq",
        "[.[]|{id,asset,usd_value,direction,status}]"], env)
    if not isinstance(account, dict) or not isinstance(orders, list) \
            or not isinstance(positions, list) or not isinstance(asset, dict) \
            or not isinstance(quote, dict) or not isinstance(fees, list) \
            or not isinstance(bank_flows, list) or not isinstance(transfers, list):
        raise ValueError("live_close_snapshot_invalid")
    return {"account": account, "open_orders": orders, "positions": positions,
            "asset": asset, "quote": quote, "fees": fees,
            "external_flow_fingerprint": _digest_rows([*bank_flows, *transfers])}


def _digest_rows(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def submit_live_close(*, credentials_path: Path, cli_path: Path, client_order_id: str,
                      frozen_qty: str, order: dict[str, Any]) -> dict[str, Any]:
    """Submit only the frozen full-size BTC/USDC close; scheduled code never calls this."""
    expected = {"asset_class": "crypto", "qty": frozen_qty, "side": "sell",
                "symbol": "BTC/USDC", "time_in_force": "gtc", "type": "market"}
    try:
        valid_qty = Decimal(frozen_qty) > 0 and Decimal(frozen_qty).as_tuple().exponent >= -9
    except InvalidOperation:
        valid_qty = False
    if order != expected or not valid_qty \
            or not re.fullmatch(r"lm-ai-[0-9a-f]{24}", client_order_id):
        raise ValueError("live_close_shape_invalid")
    if _selected_mode() != "live":
        raise ValueError("investment_mode_effect_forbidden")
    env = _context(credentials_path, cli_path, "live")
    result = _run(cli_path, ["order", "submit", "--quiet", "--symbol", "BTC/USDC",
        "--qty", frozen_qty, "--side", "sell", "--type", "market", "--time-in-force", "gtc",
        "--client-order-id", client_order_id, "--jq",
        "{id,client_order_id,status,submitted_at,symbol,qty,side,type,time_in_force}"], env)
    if (not isinstance(result, dict) or result.get("client_order_id") != client_order_id
            or result.get("symbol") not in {"BTC/USDC", "BTCUSDC"}
            or Decimal(str(result.get("qty"))) != Decimal(frozen_qty)
            or result.get("side") != "sell" or result.get("type") != "market"
            or result.get("time_in_force") != "gtc"):
        raise ValueError("live_close_ack_invalid")
    return result


def read_live_close(*, credentials_path: Path, cli_path: Path, client_order_id: str,
                    frozen_qty: str, pre_usdc_qty: str, buy_gross_cost_usdc: str,
                    external_flow_fingerprint: str) -> dict[str, Any]:
    """Verify one close from its official order, all FILLs, and post-close positions."""
    env = _context(credentials_path, cli_path, "live")
    query = (f"first(.[]|select(.client_order_id=={json.dumps(client_order_id)})) // "
             "{found:false}|if .found==false then . else "
             "{found:true,id,client_order_id,status,filled_qty,symbol,side,qty,type,time_in_force} end")
    order = _run(cli_path, ["order", "list", "--quiet", "--status", "all", "--limit", "500",
                            "--jq", query], env)
    if order == {"found": False}:
        return {"status": "absent", "verified": False}
    try:
        expected_qty = Decimal(frozen_qty)
        filled_qty = Decimal(str(order.get("filled_qty") or "0"))
        if (order.get("found") is not True or order.get("client_order_id") != client_order_id
                or order.get("symbol") not in {"BTC/USDC", "BTCUSDC"}
                or order.get("side") != "sell" or Decimal(str(order.get("qty"))) != expected_qty
                or order.get("type") != "market" or order.get("time_in_force") != "gtc"):
            raise ValueError
    except (AttributeError, InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("live_close_order_mismatch") from error
    if order.get("status") in {"canceled", "expired", "rejected"} and filled_qty == 0:
        return {"status": "terminal_failure", "verified": False, "order": order}
    if order.get("status") in {"canceled", "expired", "rejected"}:
        return {"status": "partial_terminal", "verified": False, "order": order}
    if order.get("status") != "filled":
        return {"status": "pending", "verified": False, "order": order}
    fills = _run(cli_path, ["account", "activity", "list", "--activity-types", "FILL",
        "--order-id", str(order["id"]), "--page-size", "100", "--direction", "desc", "--quiet",
        "--jq", f"[.[]|select(.order_id=={json.dumps(order['id'])})|"
        "{order_id,symbol,side,qty,price,transaction_time}]"], env)
    positions = _run(cli_path, ["position", "list", "--quiet", "--jq",
        "[.[]|{symbol,qty,market_value}]"], env)
    open_orders = _run(cli_path, ["order", "list", "--quiet", "--status", "open", "--limit", "500",
        "--jq", "length"], env)
    fees = _run(cli_path, ["account", "activity", "list", "--activity-types", "CFEE",
        "--direction", "asc", "--quiet", "--jq",
        f"[.[]|select(.order_id=={json.dumps(order['id'])})|"
        "{activity_type,order_id,symbol,qty,price,date}]"], env)
    bank_flows = _run(cli_path, ["account", "activity", "list", "--activity-types", "CSD,CSW",
        "--direction", "asc", "--quiet", "--jq",
        "[.[]|{activity_type,id,date,net_amount}]"], env)
    transfers = _run(cli_path, ["api", "GET", "/v2/wallets/transfers", "--quiet", "--jq",
        "[.[]|{id,asset,usd_value,direction,status}]"], env)
    try:
        fill_total = sum((Decimal(str(fill["qty"])) for fill in fills), Decimal("0"))
        btc = [row for row in positions if row.get("symbol") in {"BTCUSD", "BTCUSDC", "BTC/USDC"}]
        usdc = [row for row in positions if row.get("symbol") == "USDCUSD"]
        post_usdc = Decimal(str(usdc[0]["qty"]))
        if (not fills or any(fill.get("order_id") != order["id"] or fill.get("side") != "sell"
                or fill.get("symbol") not in {"BTC/USDC", "BTCUSDC"} for fill in fills)
                or fill_total != filled_qty or filled_qty != expected_qty or btc or len(usdc) != 1
                or len(positions) != 1 or post_usdc <= Decimal(pre_usdc_qty) or open_orders != 0
                or _digest_rows([*bank_flows, *transfers]) != external_flow_fingerprint):
            raise ValueError
        gross = sum((Decimal(str(fill["qty"])) * Decimal(str(fill["price"])) for fill in fills),
                    Decimal("0"))
        usdc_delta = post_usdc - Decimal(pre_usdc_qty)
    except (InvalidOperation, KeyError, TypeError, ValueError) as error:
        raise ValueError("live_close_fill_mismatch") from error
    preliminary = {"order": order, "fills": fills, "post_usdc_qty": str(post_usdc),
                   "gross_proceeds_usdc": str(gross), "official_usdc_delta": str(usdc_delta)}
    if not fees:
        return {"status": "fee_pending", "verified": False, **preliminary}
    try:
        if len(fees) != 1 or fees[0].get("symbol") != "USDCUSD" \
                or fees[0].get("order_id") != order["id"]:
            raise ValueError
        sell_fee = -Decimal(str(fees[0]["qty"]))
        discrepancy = gross - usdc_delta
        if (sell_fee < 0 or sell_fee > gross * Decimal("0.01")
                or abs(discrepancy - sell_fee) > Decimal("0.00001")):
            raise ValueError
        realised = usdc_delta - Decimal(buy_gross_cost_usdc)
    except (InvalidOperation, KeyError, TypeError, ValueError) as error:
        raise ValueError("live_close_fee_mismatch") from error
    return {"status": "verified", "verified": True, **preliminary,
            "post_usdc_qty": str(post_usdc), "gross_proceeds_usdc": str(gross),
            "sell_fee_usdc": str(sell_fee), "realised_net_pnl_usdc": str(realised),
            "fee_activity": fees[0]}
