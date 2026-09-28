import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from cross_venue_reporter import load_daily_receipts, render_daily_pnl, wake
from telegram_outbox import list_items
from venue_snapshot import VenueSnapshot


NOW = datetime.now(timezone.utc).replace(microsecond=0)
TODAY = NOW.date().isoformat()


def snapshot(venue="alpaca", receipt_id=None):
    return VenueSnapshot.from_mapping({
        "venue": venue,
        "observed_at": (NOW - timedelta(seconds=30)).isoformat().replace("+00:00", "Z"),
        "equity_usd": "1000",
        "free_cash_usd": "500",
        "gross_pnl_usd": "10",
        "trading_fees_usd": "1",
        "funding_or_borrow_usd": "0.5",
        "slippage_usd": "0.25",
        "gas_usd": "0.1",
        "model_cost_usd": "0.15",
        "source_receipt_ids": [receipt_id or f"{venue}-receipt"],
        "risk": {"drawdown_fraction": "0.01", "round_trips": 30, "capital_at_risk_usd": "100"},
        "measurement_status": "measured",
    })


class CrossVenueReporterTests(unittest.TestCase):
    def test_render_includes_all_costs_and_unknown_markers_in_venue_order(self):
        message = render_daily_pnl(
            {
                "measurement_status": "partial",
                "gross_pnl_usd": "10.00",
                "trading_fees_usd": "1.00",
                "funding_or_borrow_usd": "0.50",
                "slippage_usd": "0.25",
                "gas_usd": "0.10",
                "model_cost_usd": None,
                "net_pnl_usd": None,
                "rolling_30d_net_pnl_usd": None,
                "target_gap_usd": None,
                "unknown_venues": [{"venue": "hyperliquid", "reason": "cost_unknown"}],
                "venue_rows": [
                    {"venue": "zeta", "net_pnl_usd": "2.00"},
                    {"venue": "alpaca", "net_pnl_usd": "1.00"},
                ],
            },
            {"action": "hold", "allocation_usd": "0.00"},
            TODAY,
        )

        self.assertIn("取引手数料: $1.00", message)
        self.assertIn("funding/borrow: $0.50", message)
        self.assertIn("slippage: $0.25", message)
        self.assertIn("gas: $0.10", message)
        self.assertIn("model cost: 不明", message)
        self.assertIn("rolling 30d net P&L: 不明", message)
        self.assertLess(message.index("alpaca"), message.index("zeta"))
        self.assertIn("hyperliquid: 不明 (cost_unknown)", message)

    def test_wake_persists_provider_message_id_and_replays_same_day_without_send(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            calls = []
            readers = {
                "alpaca": lambda: snapshot(),
                "hyperliquid": lambda: {"status": "unknown", "reason": "cost_unknown"},
                "__caps__": {
                    "cash_reserve_usd": "100",
                    "max_allocation_usd": "100",
                    "current_cap_usd": "100",
                    "max_drawdown_fraction": "0.20",
                    "min_round_trips": 30,
                },
                "__available_capital_usd__": "500",
                "__owner_cash_flow_usd__": "0",
            }

            def send(message):
                calls.append(message)
                return {"message_id": "telegram-123"}

            first = wake(readers, state, TODAY, send)
            second = wake(readers, state, TODAY, send)
            items = list_items(state / "telegram-outbox.sqlite3")

            self.assertEqual(first["status"], "delivered")
            self.assertEqual(first["provider_message_id"], "telegram-123")
            self.assertEqual(second["provider_message_id"], "telegram-123")
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].status, "delivered")
            self.assertEqual(first["aggregate"]["measurement_status"], "partial")
            self.assertEqual(first["unknown_venues"][0]["reason"], "cost_unknown")

    def test_delivery_uncertain_is_persisted_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            calls = []
            readers = {"alpaca": lambda: snapshot()}

            def send(_message):
                calls.append(True)
                raise RuntimeError("provider unavailable")

            first = wake(readers, state, TODAY, send)
            second = wake(readers, state, TODAY, send)

            self.assertEqual(first["status"], "delivery_uncertain")
            self.assertEqual(second["status"], "delivery_uncertain")
            self.assertEqual(len(calls), 1)

    def test_wake_derives_rolling_target_gap_from_daily_receipts(self):
        today = "2026-09-28"
        end = date.fromisoformat(today)
        daily_receipts = []
        for offset in range(29, -1, -1):
            day = (end - timedelta(days=offset)).isoformat()
            daily_receipts.append({
                "day": day,
                "status": "delivered",
                "aggregate": {
                    "measurement_status": "measured",
                    "net_pnl_usd": "1.00",
                    "owner_cash_flow_usd": "50.00",
                    "source_receipt_ids": [f"daily-{offset}"],
                },
            })

        with tempfile.TemporaryDirectory() as directory:
            receipt = wake(
                {"alpaca": lambda: snapshot(), "__daily_receipts__": daily_receipts},
                Path(directory),
                today,
                lambda _message: {"message_id": "telegram-rolling"},
            )

        self.assertEqual(receipt["aggregate"]["rolling_measurement_status"], "measured")
        self.assertEqual(receipt["aggregate"]["rolling_30d_net_pnl_usd"], "30.00")
        self.assertEqual(receipt["aggregate"]["target_gap_usd"], "9970.00")
        self.assertEqual(receipt["aggregate"]["rolling_owner_cash_flow_usd"], "1500.00")

    def test_load_daily_receipts_reads_only_the_requested_window(self):
        today = "2026-09-28"
        end = date.fromisoformat(today)
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            expected_days = []
            for offset in range(29, -1, -1):
                day = (end - timedelta(days=offset)).isoformat()
                expected_days.append(day)
                (state / f"cross-venue-{day}.json").write_text(
                    json.dumps({"day": day, "status": "delivered"}), encoding="utf-8"
                )
            outside = (end - timedelta(days=30)).isoformat()
            (state / f"cross-venue-{outside}.json").write_text(
                json.dumps({"day": outside, "status": "delivered"}), encoding="utf-8"
            )

            rows = load_daily_receipts(state, today)

        self.assertEqual([row["day"] for row in rows], expected_days)
        self.assertEqual(len(rows), 30)

    def test_load_daily_receipts_marks_malformed_file_without_treating_it_as_missing(self):
        today = "2026-09-28"
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            day = "2026-09-01"
            (state / f"cross-venue-{day}.json").write_text("{not-json", encoding="utf-8")

            rows = load_daily_receipts(state, today)

        malformed = next(row for row in rows if row["day"] == day)
        self.assertEqual(malformed["_load_error"], "daily_receipt_file_invalid")

    def test_wake_replays_last_completed_persisted_window_when_daily_reader_is_not_injected(self):
        today = "2026-09-28"
        end = date.fromisoformat(today)
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            completed_end = end - timedelta(days=1)
            for offset in range(29, -1, -1):
                day = (completed_end - timedelta(days=offset)).isoformat()
                (state / f"cross-venue-{day}.json").write_text(
                    json.dumps({
                        "day": day,
                        "status": "delivered",
                        "aggregate": {
                            "measurement_status": "measured",
                            "net_pnl_usd": "1.00",
                            "owner_cash_flow_usd": "0.00",
                            "source_receipt_ids": [f"persisted-{offset}"],
                        },
                    }), encoding="utf-8"
                )

            receipt = wake(
                {"alpaca": lambda: snapshot()},
                state,
                today,
                lambda _message: {"message_id": "telegram-persisted"},
            )

        self.assertEqual(receipt["aggregate"]["rolling_measurement_status"], "measured")
        self.assertEqual(receipt["aggregate"]["rolling_reason"], "rolling_measurement_complete")
        self.assertEqual(receipt["aggregate"]["rolling_period_end"], "2026-09-27")
        self.assertEqual(receipt["aggregate"]["rolling_30d_net_pnl_usd"], "30.00")


if __name__ == "__main__":
    unittest.main()
