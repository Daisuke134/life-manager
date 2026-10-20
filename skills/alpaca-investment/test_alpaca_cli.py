from __future__ import annotations

from datetime import date, timedelta
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import alpaca_cli


SYMBOLS = ("SPY", "QQQ", "IWM", "DIA", "EFA", "EEM", "TLT", "GLD")
START = date(2026, 1, 1)
COMPLETED_SESSIONS = [START + timedelta(days=index) for index in range(127)]
CURRENT_SESSION = COMPLETED_SESSIONS[-1] + timedelta(days=1)
CLOCK = {"timestamp": f"{CURRENT_SESSION.isoformat()}T15:00:00Z", "is_open": True}


def _bar(session: date, close: str) -> dict[str, str]:
    return {
        "t": f"{session.isoformat()}T15:00:00Z",
        "o": close,
        "c": close,
    }


def _response(*, add_current: bool = True, add_future: bool = False,
              duplicate: bool = False) -> list[dict[str, object]]:
    result = []
    for symbol in SYMBOLS:
        bars = [_bar(session, str(100 + index)) for index, session in enumerate(COMPLETED_SESSIONS)]
        if add_current:
            bars.append(_bar(CURRENT_SESSION, "999"))
        if add_future:
            bars.append(_bar(CURRENT_SESSION + timedelta(days=1), "1000"))
        if duplicate:
            bars[-1] = {**bars[-1], "t": bars[-2]["t"]}
        result.append({"symbol": symbol, "bars": bars})
    return result


class CryptoValidationHistoryTests(unittest.TestCase):
    def _read(self, *, mutate=None):
        from datetime import datetime, timezone
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rows = [{"t": (start + timedelta(minutes=5 * i)).isoformat(),
                 "o": "100", "h": "102", "l": "99", "c": "101"} for i in range(13)]
        payload = {"next_page_token": None, "bars": {"BTC/USDC": rows,
                   "USDC/USD": [{"t": r["t"], "c": "0.99"} for r in rows]}}
        if mutate:
            mutate(payload)
        with patch.object(alpaca_cli, "_context", return_value={}) as context, patch.object(
            alpaca_cli, "_run", return_value=payload) as run:
            result = alpaca_cli.read_crypto_validation_history(
                credentials_path=Path("credentials"), cli_path=Path("alpaca"),
                start=start, end=start + timedelta(hours=1), observed_at="2026-01-02T00:00:00Z")
        return result, context, run

    def test_completed_nonoverlapping_btc_and_fx_with_paper_context(self):
        result, context, run = self._read()
        self.assertEqual(len(result["crypto_history"]), 12)
        self.assertEqual(len(result["quote_conversions"]), 12)
        self.assertEqual(result["quote_conversions"][0]["rate"], "0.99")
        self.assertEqual(context.call_args.kwargs["mode"], "paper")
        self.assertIn("BTC/USDC,USDC/USD", run.call_args.args[1])
        self.assertIn("next_page_token", run.call_args.args[1][-1])
        self.assertTrue(result["source_receipt_ids"])

    def test_history_follows_page_token_before_validating_complete_window(self):
        from datetime import datetime, timezone
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        btc = [{"t": (start + timedelta(minutes=5 * i)).isoformat(),
                "o": "100", "h": "102", "l": "99", "c": "101"}
               for i in range(13)]
        fx = [{"t": row["t"], "c": "0.99"} for row in btc]
        pages = [
            {"next_page_token": "opaque-token-2", "bars": {
                "BTC/USDC": btc[:6]}},
            {"next_page_token": None, "bars": {
                "BTC/USDC": btc[6:], "USDC/USD": fx}},
        ]
        with patch.object(alpaca_cli, "_context", return_value={}) as context, patch.object(
            alpaca_cli, "_run", side_effect=pages,
        ) as run:
            result = alpaca_cli.read_crypto_validation_history(
                credentials_path=Path("credentials"), cli_path=Path("alpaca"),
                start=start, end=start + timedelta(hours=1),
                observed_at="2026-01-02T00:00:00Z")

        self.assertEqual(context.call_args.kwargs["mode"], "paper")
        self.assertEqual(run.call_count, 2)
        second_args = run.call_args_list[1].args[1]
        self.assertEqual(second_args[second_args.index("--page-token") + 1],
                         "opaque-token-2")
        self.assertEqual(len(result["crypto_history"]), 12)
        self.assertEqual(len(result["quote_conversions"]), 12)

    def test_history_fails_closed_when_page_limit_leaves_more_data(self):
        from datetime import datetime, timezone
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        pages = []
        for index in range(alpaca_cli.MAX_CRYPTO_VALIDATION_HISTORY_PAGES):
            row = {"t": (start + timedelta(minutes=5 * index)).isoformat(),
                   "o": "100", "h": "102", "l": "99", "c": "101"}
            pages.append({"next_page_token": f"opaque-token-{index + 1}",
                          "bars": {"BTC/USDC": [row]}})
        with patch.object(alpaca_cli, "_context", return_value={}), patch.object(
            alpaca_cli, "_run", side_effect=pages,
        ) as run:
            with self.assertRaisesRegex(
                    ValueError,
                    "^alpaca_crypto_validation_history_invalid:pagination_incomplete$") as raised:
                alpaca_cli.read_crypto_validation_history(
                    credentials_path=Path("credentials"), cli_path=Path("alpaca"),
                    start=start, end=start + timedelta(hours=1),
                    observed_at="2026-01-02T00:00:00Z")

        self.assertEqual(run.call_count, alpaca_cli.MAX_CRYPTO_VALIDATION_HISTORY_PAGES)
        self.assertEqual(raised.exception.details, {
            "page_number": alpaca_cli.MAX_CRYPTO_VALIDATION_HISTORY_PAGES,
            "received_count": alpaca_cli.MAX_CRYPTO_VALIDATION_HISTORY_PAGES,
        })

    def test_history_fails_closed_when_page_has_no_bars_and_more_data(self):
        from datetime import datetime, timezone
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        btc = [{"t": (start + timedelta(minutes=5 * i)).isoformat(),
                "o": "100", "h": "102", "l": "99", "c": "101"}
               for i in range(13)]
        fx = [{"t": row["t"], "c": "0.99"} for row in btc]
        pages = [
            {"next_page_token": "opaque-token-2", "bars": {"BTC/USDC": []}},
            {"next_page_token": None, "bars": {"BTC/USDC": btc,
                                                "USDC/USD": fx}},
        ]
        with patch.object(alpaca_cli, "_context", return_value={}), patch.object(
            alpaca_cli, "_run", side_effect=pages,
        ) as run:
            with self.assertRaisesRegex(
                    ValueError,
                    "^alpaca_crypto_validation_history_invalid:pagination_incomplete$") as raised:
                alpaca_cli.read_crypto_validation_history(
                    credentials_path=Path("credentials"), cli_path=Path("alpaca"),
                    start=start, end=start + timedelta(hours=1),
                    observed_at="2026-01-02T00:00:00Z")

        self.assertEqual(run.call_count, 1)
        self.assertEqual(raised.exception.details, {
            "page_number": 1, "received_count": 0,
        })

    def test_history_rejects_pagination_missing_duplicate_future_and_bad_prices(self):
        mutations = [
            ("pagination_incomplete", lambda p: p.update(next_page_token="more")),
            ("symbol_set_invalid", lambda p: p.pop("bars")),
            ("btc_bar_count_mismatch", lambda p: p["bars"]["BTC/USDC"].pop(2)),
            ("bar_timestamp_not_increasing", lambda p: p["bars"]["BTC/USDC"][0].update(
                t=p["bars"]["BTC/USDC"][1]["t"])),
            ("bar_price_invalid", lambda p: p["bars"]["BTC/USDC"][0].update(c="NaN")),
            ("bar_price_invalid", lambda p: p["bars"]["BTC/USDC"][0].update(h="0")),
            ("bar_timestamp_outside_window", lambda p: p["bars"]["BTC/USDC"][-1].update(
                t="2026-01-03T00:00:00Z")),
            ("bar_price_invalid", lambda p: p["bars"]["USDC/USD"][0].update(c="0")),
        ]
        for reason, mutate in mutations:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(
                        ValueError,
                        f"^alpaca_crypto_validation_history_invalid:{reason}$"):
                    self._read(mutate=mutate)

    def test_btc_bar_count_failure_reports_only_safe_counts(self):
        with self.assertRaises(ValueError) as raised:
            self._read(mutate=lambda p: p["bars"]["BTC/USDC"].pop(2))
        self.assertEqual(getattr(raised.exception, "reason_code", None),
                         "btc_bar_count_mismatch")
        self.assertEqual(getattr(raised.exception, "details", None), {
            "symbol": "BTC/USDC", "expected_count": 12, "actual_count": 11,
        })

    def test_missing_fx_is_not_replaced_by_one(self):
        result, _, _ = self._read(mutate=lambda p: p["bars"].pop("USDC/USD"))
        self.assertEqual(result["quote_conversions"], [])


class EtfDailyBarsTests(unittest.TestCase):
    def test_multi_bars_has_bounded_large_response_budget_only_for_that_operation(self):
        payload = json.dumps({"payload": "x" * alpaca_cli.MAX_OUTPUT_BYTES}).encode("utf-8")
        completed = type("Completed", (), {"returncode": 0, "stdout": payload})()
        with patch.object(alpaca_cli.subprocess, "run", return_value=completed):
            self.assertIn("payload", alpaca_cli._run(Path("alpaca"), ["data", "multi-bars"], {}))
            with self.assertRaisesRegex(ValueError, "^alpaca_cli_output_too_large$"):
                alpaca_cli._run(Path("alpaca"), ["account", "get"], {})

    def _read(self, response):
        with patch.object(alpaca_cli, "_context", return_value={}), patch.object(
            alpaca_cli, "_run", return_value=response
        ) as run:
            value = alpaca_cli.read_etf_daily_bars(
                credentials_path=Path("credentials"),
                cli_path=Path("alpaca"),
                clock=CLOCK,
            )
        return value, run

    def test_multi_bars_uses_iex_split_adjusted_completed_daily_boundary(self):
        value, run = self._read(_response())

        self.assertEqual(tuple(value["daily_bars"]), SYMBOLS)
        self.assertEqual(value["completed_through_session"], COMPLETED_SESSIONS[-1].isoformat())
        self.assertEqual(len(value["daily_bars"]["SPY"]), 127)
        self.assertNotIn(CURRENT_SESSION.isoformat(), {
            row["t"][:10] for row in value["daily_bars"]["SPY"]
        })
        self.assertEqual(len(value["source_receipt_ids"]), 1)
        args = run.call_args.args[1]
        self.assertEqual(args[:3], ["data", "multi-bars", "--symbols"])
        self.assertIn("SPY,QQQ,IWM,DIA,EFA,EEM,TLT,GLD", args)
        self.assertIn("--timeframe", args)
        self.assertIn("1Day", args)
        self.assertIn("--adjustment", args)
        self.assertIn("split", args)
        self.assertIn("--feed", args)
        self.assertIn("iex", args)

    def test_future_bar_is_rejected_instead_of_silently_filtered(self):
        with patch.object(alpaca_cli, "_context", return_value={}), patch.object(
            alpaca_cli, "_run", return_value=_response(add_future=True)
        ):
            with self.assertRaisesRegex(ValueError, "^alpaca_etf_daily_bars_invalid$"):
                alpaca_cli.read_etf_daily_bars(
                    credentials_path=Path("credentials"),
                    cli_path=Path("alpaca"),
                    clock=CLOCK,
                )

    def test_duplicate_bar_is_rejected(self):
        with patch.object(alpaca_cli, "_context", return_value={}), patch.object(
            alpaca_cli, "_run", return_value=_response(duplicate=True)
        ):
            with self.assertRaisesRegex(ValueError, "^alpaca_etf_daily_bars_invalid$"):
                alpaca_cli.read_etf_daily_bars(
                    credentials_path=Path("credentials"),
                    cli_path=Path("alpaca"),
                    clock=CLOCK,
                )

    def test_missing_symbol_is_rejected(self):
        response = _response()
        response.pop()
        with patch.object(alpaca_cli, "_context", return_value={}), patch.object(
            alpaca_cli, "_run", return_value=response
        ):
            with self.assertRaisesRegex(ValueError, "^alpaca_etf_daily_bars_invalid$"):
                alpaca_cli.read_etf_daily_bars(
                    credentials_path=Path("credentials"),
                    cli_path=Path("alpaca"),
                    clock=CLOCK,
                )

    def test_allocator_snapshot_can_include_the_daily_bar_boundary(self):
        account = {"cash": "100", "equity": "100", "last_equity": "100"}
        common = [
            account, CLOCK,
            [], [], [], [{"symbol": "USDCUSD", "market_value": "0", "unrealized_pl": "0"}],
            0, {"price": "100", "timestamp": CLOCK["timestamp"]}, [],
            {"tradable": False, "status": "inactive"},
            {"bid": "99", "ask": "100", "quote_at": CLOCK["timestamp"]}, [],
        ]
        etf = {
            "daily_bars": {
                symbol: [_bar(session, "100") for session in COMPLETED_SESSIONS]
                for symbol in SYMBOLS
            },
            "completed_through_session": COMPLETED_SESSIONS[-1].isoformat(),
            "source_receipt_ids": ["source"],
        }
        with tempfile.TemporaryDirectory() as directory, patch.object(
            alpaca_cli, "_context", return_value={},
        ), patch.object(
            alpaca_cli, "_run", side_effect=common
        ), patch.object(alpaca_cli, "read_etf_daily_bars", return_value=etf) as daily:
            value = alpaca_cli.read_allocator_snapshot(
                credentials_path=Path("credentials"), cli_path=Path("alpaca"),
                risk_day_path=Path(directory) / "risk-day.json", include_etf_bars=True,
            )

        self.assertEqual(value["completed_through_session"], COMPLETED_SESSIONS[-1].isoformat())
        self.assertEqual(value["daily_bars"]["QQQ"][0]["c"], "100")
        daily.assert_called_once()

    def test_paper_allocator_skips_unsupported_wallet_transfers_endpoint(self):
        account = {"cash": "100", "equity": "100", "last_equity": "100"}
        responses = [
            account, CLOCK,
            [],  # cash activities
            [],  # trade activities
            [{"symbol": "USDCUSD", "market_value": "0", "unrealized_pl": "0"}],
            0, {"price": "100", "timestamp": CLOCK["timestamp"]}, [],
            {"tradable": False, "status": "inactive"},
            {"bid": "99", "ask": "100", "quote_at": CLOCK["timestamp"]}, [],
        ]
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            alpaca_cli.os.environ, {"LIFE_MANAGER_INVESTMENT_MODE": "paper"},
        ), patch.object(alpaca_cli, "_context", return_value={}), patch.object(
            alpaca_cli, "_run", side_effect=responses,
        ) as run:
            value = alpaca_cli.read_allocator_snapshot(
                credentials_path=Path("credentials"), cli_path=Path("alpaca"),
                risk_day_path=Path(directory) / "risk-day.json",
            )

        self.assertEqual(value["risk"]["cash_flow_ny_day_usd"], "0")
        self.assertFalse(any(call.args[1][:2] == ["api", "GET"]
                             for call in run.call_args_list))


class EtfDailyHistoryTests(unittest.TestCase):
    def _trim(self, response, end):
        return [
            {
                **row,
                "bars": [bar for bar in row["bars"] if bar["t"][:10] <= end.isoformat()],
            }
            for row in response
        ]

    def _read(self, response, *, start=START, end=COMPLETED_SESSIONS[60]):
        response = self._trim(response, end)
        with patch.object(alpaca_cli, "_context", return_value={}) as context, patch.object(
            alpaca_cli, "_run", side_effect=[CLOCK, response]
        ) as run:
            value = alpaca_cli.read_etf_daily_history(
                credentials_path=Path("credentials"),
                cli_path=Path("alpaca"),
                start=start,
                end=end,
            )
        return value, context, run

    def test_history_uses_paper_context_and_returns_the_requested_completed_window(self):
        value, context, run = self._read(_response())

        context.assert_called_once_with(Path("credentials"), Path("alpaca"), mode="paper")
        self.assertEqual(len(value["daily_bars"]["SPY"]), 61)
        self.assertEqual(value["completed_through_session"], COMPLETED_SESSIONS[60].isoformat())
        self.assertEqual(value["observed_at"], CLOCK["timestamp"])
        self.assertEqual(run.call_count, 2)
        operations = [call.args[1][:2] for call in run.call_args_list]
        self.assertEqual(operations, [["clock", "get"], ["data", "multi-bars"]])
        bars_args = run.call_args_list[1].args[1]
        self.assertIn("--start", bars_args)
        self.assertIn(START.isoformat(), bars_args)
        self.assertIn("--end", bars_args)
        self.assertIn(COMPLETED_SESSIONS[60].isoformat(), bars_args)

    def test_history_rejects_range_larger_than_ninety_calendar_days(self):
        with patch.object(alpaca_cli, "_context", return_value={}), patch.object(
            alpaca_cli, "_run", return_value=CLOCK
        ):
            with self.assertRaisesRegex(ValueError, "^alpaca_etf_daily_bars_invalid$"):
                alpaca_cli.read_etf_daily_history(
                    credentials_path=Path("credentials"), cli_path=Path("alpaca"),
                    start=date(2025, 1, 1), end=date(2025, 4, 2),
                )

    def test_history_rejects_future_end_without_fetching_bars(self):
        with patch.object(alpaca_cli, "_context", return_value={}), patch.object(
            alpaca_cli, "_run", return_value=CLOCK
        ) as run:
            with self.assertRaisesRegex(ValueError, "^alpaca_etf_daily_bars_invalid$"):
                alpaca_cli.read_etf_daily_history(
                    credentials_path=Path("credentials"), cli_path=Path("alpaca"),
                    start=CURRENT_SESSION - timedelta(days=10),
                    end=CURRENT_SESSION + timedelta(days=1),
                )

        self.assertEqual(run.call_count, 1)

    def test_history_rejects_missing_symbol(self):
        response = self._trim(_response(), COMPLETED_SESSIONS[60])
        response.pop()
        with patch.object(alpaca_cli, "_context", return_value={}), patch.object(
            alpaca_cli, "_run", side_effect=[CLOCK, response]
        ):
            with self.assertRaisesRegex(ValueError, "^alpaca_etf_daily_bars_invalid$"):
                alpaca_cli.read_etf_daily_history(
                    credentials_path=Path("credentials"), cli_path=Path("alpaca"),
                    start=START, end=COMPLETED_SESSIONS[60],
                )


class PaperEtfCostEvidenceTests(unittest.TestCase):
    observed_at = "2026-09-30T14:00:00Z"
    period_start = "2026-09-29T14:30:00Z"
    orders = [
        {"id": "buy-order", "symbol": "QQQ", "side": "buy",
         "filled_qty": "0.025", "filled_avg_price": "400"},
        {"id": "sell-order", "symbol": "QQQ", "side": "sell",
         "filled_qty": "0.025", "filled_avg_price": "410"},
    ]
    fills = [
        {"id": "fill-buy", "activity_type": "FILL", "order_id": "buy-order",
         "symbol": "QQQ", "side": "buy", "qty": "0.025", "price": "400",
         "transaction_time": "2026-09-29T14:31:05Z"},
        {"id": "fill-sell", "activity_type": "FILL", "order_id": "sell-order",
         "symbol": "QQQ", "side": "sell", "qty": "0.025", "price": "410",
         "transaction_time": "2026-09-29T14:31:10Z"},
    ]
    def _read(self, *, fills=None, missing_quote=False, observed_at=None,
              quote_next_page_token=None, calls=None):
        fills = self.fills if fills is None else fills
        observed_at = self.observed_at if observed_at is None else observed_at

        def run(_cli, args, _env):
            if calls is not None:
                calls.append(args)
            if args[:2] == ["clock", "get"]:
                return {"timestamp": observed_at}
            if args[:2] == ["account", "activity"] and "FILL" in args:
                return fills
            if args[:2] == ["data", "quotes"]:
                if missing_quote:
                    return {"quotes": [], "next_page_token": quote_next_page_token}
                end = args[args.index("--end") + 1]
                if "14:31:05" in end:
                    rows = [{"t": "2026-09-29T14:31:05Z", "bp": "399.99", "ap": "400.01"}]
                else:
                    rows = [{"t": "2026-09-29T14:31:10Z", "bp": "409.99", "ap": "410.01"}]
                return {"quotes": rows, "next_page_token": quote_next_page_token}
            raise AssertionError(f"unexpected Alpaca CLI operation: {args[:2]}")

        with patch.object(alpaca_cli, "_context", return_value={}) as context, patch.object(
            alpaca_cli, "_run", side_effect=run
        ) as cli_run:
            value = alpaca_cli.read_paper_etf_cost_evidence(
                credentials_path=Path("credentials"), cli_path=Path("alpaca"),
                orders=self.orders, period_start=self.period_start,
            )
        return value, context, cli_run

    def test_paper_readback_joins_exact_fills_and_quotes(self):
        value, context, cli_run = self._read()

        context.assert_called_once_with(Path("credentials"), Path("alpaca"), mode="paper")
        self.assertEqual(value["broker_costs_status"], "partial")
        self.assertEqual(value["provider"], "alpaca")
        self.assertEqual(value["broker_gross_pnl_usd"], "0.250")
        self.assertIsNone(value["broker_fees_usd"])
        self.assertEqual(value["broker_slippage_usd"], "0")
        self.assertEqual(set(value["order_ids"]), {"buy-order", "sell-order"})
        self.assertEqual(set(value["source_receipt_ids"]), {
            "fill-buy", "fill-sell",
            "alpaca-quote:fill-buy:2026-09-29T14:31:05Z",
            "alpaca-quote:fill-sell:2026-09-29T14:31:10Z",
        })
        self.assertIn("sip", cli_run.call_args_list[2].args[1])
        self.assertIn("next_page_token", cli_run.call_args_list[2].args[1][-1])

    def test_execution_readback_ignores_other_account_orders(self):
        foreign = {
            "id": "foreign-fill", "activity_type": "FILL", "order_id": "other-order",
            "symbol": "QQQ", "side": "buy", "qty": "1", "price": "400",
            "transaction_time": "2026-09-29T14:32:00Z",
        }
        value, _context, _run = self._read(fills=[*self.fills, foreign])
        self.assertNotIn("foreign-fill", value["source_receipt_ids"])
        self.assertEqual(value["broker_gross_pnl_usd"], "0.250")

    def test_execution_activity_scan_starts_at_the_owner_period(self):
        calls = []
        self._read(calls=calls)
        fill_call = next(
            args for args in calls
            if args[:2] == ["account", "activity"] and "FILL" in args
        )
        self.assertEqual(
            fill_call[fill_call.index("--after") + 1],
            "2026-09-29T14:30:00Z",
        )

    def test_missing_historical_quote_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "^paper_cost_quote_invalid$"):
            self._read(missing_quote=True)

    def test_truncated_historical_quote_page_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "^paper_cost_quote_pages_incomplete$"):
            self._read(quote_next_page_token="more-quotes")

    def test_paper_fee_gap_does_not_prevent_execution_slippage_readback(self):
        calls = []
        try:
            value, _context, _run = self._read(calls=calls)
        except ValueError as error:
            self.fail(f"paper fee gap blocked execution readback: {error}")

        self.assertEqual(value["broker_costs_status"], "partial")
        self.assertEqual(value["broker_slippage_status"], "complete")
        self.assertEqual(value["broker_fees_status"], "not_simulated")
        self.assertIsNone(value["broker_fees_usd"])
        self.assertEqual(value["broker_slippage_usd"], "0")
        self.assertFalse(any("FEE" in args for args in calls))

    def test_execution_readback_does_not_wait_for_unsimulated_fee_settlement(self):
        value, _context, _run = self._read(observed_at="2026-09-29T20:00:00Z")
        self.assertEqual(value["broker_slippage_status"], "complete")
        self.assertIsNone(value["broker_fees_usd"])

if __name__ == "__main__":
    unittest.main()
