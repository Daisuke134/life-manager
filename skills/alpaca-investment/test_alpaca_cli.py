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
        with patch.object(alpaca_cli, "_context", return_value={}), patch.object(
            alpaca_cli, "_run", side_effect=common
        ), patch.object(alpaca_cli, "read_etf_daily_bars", return_value=etf) as daily:
            value = alpaca_cli.read_allocator_snapshot(
                credentials_path=Path("credentials"), cli_path=Path("alpaca"),
                risk_day_path=Path("risk-day.json"), include_etf_bars=True,
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


class PaperCostReadbackTests(unittest.TestCase):
    def test_read_paper_stock_costs_returns_official_fee_by_client_order(self):
        orders = [
            {"id": "order-entry", "client_order_id": "lm-ai-" + "a" * 24,
             "status": "filled", "symbol": "QQQ", "side": "buy",
             "filled_qty": "0.025", "filled_avg_price": "400"},
            {"id": "order-exit", "client_order_id": "lm-ai-" + "b" * 24,
             "status": "filled", "symbol": "QQQ", "side": "sell",
             "filled_qty": "0.025", "filled_avg_price": "410"},
        ]
        fills = [
            {"id": "fill-entry", "order_id": "order-entry", "activity_type": "FILL",
             "symbol": "QQQ", "side": "buy", "qty": "0.025", "price": "400"},
            {"id": "fill-exit", "order_id": "order-exit", "activity_type": "FILL",
             "symbol": "QQQ", "side": "sell", "qty": "0.025", "price": "410"},
        ]
        fees = [{"id": "fee-entry", "order_id": "order-entry", "activity_type": "CFEE",
                 "qty": "-0.01", "price": "1"}]
        with patch.dict(alpaca_cli.os.environ, {"LIFE_MANAGER_INVESTMENT_MODE": "paper"}), \
                patch.object(alpaca_cli, "_context", return_value={}), patch.object(
                    alpaca_cli, "_run", side_effect=[orders, fills, fees]
                ):
            result = alpaca_cli.read_paper_stock_costs(
                credentials_path=Path("credentials"), cli_path=Path("alpaca"),
                client_order_ids=["lm-ai-" + "a" * 24, "lm-ai-" + "b" * 24],
            )

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["fees_by_client_order_id"], {
            "lm-ai-" + "a" * 24: "0.01",
            "lm-ai-" + "b" * 24: "0.00",
        })
        self.assertEqual(result["source_receipt_ids"], [
            "alpaca-order:order-entry", "alpaca-order:order-exit",
            "alpaca-fill:fill-entry", "alpaca-fill:fill-exit", "alpaca-fee:fee-entry",
        ])


if __name__ == "__main__":
    unittest.main()
