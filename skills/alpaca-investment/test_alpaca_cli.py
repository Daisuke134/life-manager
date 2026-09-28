from __future__ import annotations

from datetime import date, timedelta
import json
import sys
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


if __name__ == "__main__":
    unittest.main()
