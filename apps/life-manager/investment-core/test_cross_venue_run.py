import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from cross_venue_run import build_readers, main, parse_snapshot_spec, read_manifest, run_once


NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def snapshot(venue="alpaca"):
    return {
        "venue": venue,
        "observed_at": NOW,
        "equity_usd": "1000",
        "free_cash_usd": "500",
        "gross_pnl_usd": "10",
        "trading_fees_usd": "1",
        "funding_or_borrow_usd": "0.5",
        "slippage_usd": "0.25",
        "gas_usd": "0.1",
        "model_cost_usd": "0.15",
        "source_receipt_ids": [f"{venue}-receipt"],
        "risk": {"drawdown_fraction": "0.01", "round_trips": 30,
                 "capital_at_risk_usd": "100"},
        "measurement_status": "measured",
    }


class CrossVenueRunTests(unittest.TestCase):
    def test_missing_manifest_is_explicitly_unknown_and_has_no_capital(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = read_manifest(Path(directory) / "inputs.json")

        self.assertEqual(manifest["status"], "missing")
        self.assertEqual(manifest["snapshot_specs"], [])
        self.assertEqual(manifest["available_capital_usd"], "0")

    def test_manifest_loads_snapshot_and_owner_flow_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inputs.json"
            path.write_text(json.dumps({
                "snapshot_specs": ["alpaca=/tmp/alpaca.json"],
                "alpaca_state_dir": "/tmp/alpaca-state",
                "owner_cash_flow_path": "/tmp/owner-flow.json",
                "available_capital_usd": "100",
            }), encoding="utf-8")

            manifest = read_manifest(path)

        self.assertEqual(manifest["status"], "configured")
        self.assertEqual(manifest["snapshot_specs"], ["alpaca=/tmp/alpaca.json"])
        self.assertEqual(manifest["alpaca_state_dir"], "/tmp/alpaca-state")
        self.assertEqual(manifest["owner_cash_flow_path"], "/tmp/owner-flow.json")
        self.assertEqual(manifest["available_capital_usd"], "100")

    def test_run_once_can_read_alpaca_owner_state_without_snapshot_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            alpaca_state = root / "alpaca-state"
            alpaca_state.mkdir()
            (alpaca_state / "performance-latest.json").write_text(json.dumps({
                "measurement_status": "measured",
                "observed_at": NOW,
                "gross_strategy_pnl_usd": "10",
                "fees_usd": "1",
                "funding_or_borrow_usd": "0.5",
                "slippage_usd": "0.25",
                "gas_usd": "0.1",
                "model_cost_usd": "0.15",
                "completed_round_trips": 30,
                "observed_endpoint_drawdown_usd": "1",
                "gross_exposure_usd": "100",
                "source_receipt_ids": ["alpaca-state-receipt"],
            }), encoding="utf-8")
            (alpaca_state / "observation-latest.json").write_text(json.dumps({
                "account": {"equity": "1000", "cash": "500"},
            }), encoding="utf-8")
            (alpaca_state / "risk-latest.json").write_text(json.dumps({
                "drawdown_fraction": "0.01",
            }), encoding="utf-8")
            owner_flow_path = root / "owner-flow.json"
            owner_flow_path.write_text(
                json.dumps({"owner_cash_flow_usd": "0", "source_receipt_ids": ["flow-1"]}),
                encoding="utf-8",
            )

            receipt = run_once(
                snapshot_specs=[],
                alpaca_state_dir=alpaca_state,
                state_dir=root / "state",
                today="2026-09-29",
                owner_cash_flow_path=owner_flow_path,
                available_capital_usd="0",
                send=lambda message: {"message_id": "m-state"},
            )

        self.assertEqual(receipt["status"], "delivered")
        self.assertEqual(receipt["provider_message_id"], "m-state")
        self.assertEqual(receipt["aggregate"]["net_pnl_usd"], "8.00")
        self.assertEqual(
            [row["venue"] for row in receipt["aggregate"]["unknown_venues"]],
            ["hyperliquid", "solana"],
        )

    def test_parse_snapshot_spec_rejects_missing_venue_or_path(self):
        with self.assertRaisesRegex(ValueError, "snapshot_spec_invalid"):
            parse_snapshot_spec("/tmp/snapshot.json")
        with self.assertRaisesRegex(ValueError, "snapshot_spec_invalid"):
            parse_snapshot_spec("alpaca=")

    def test_build_readers_keeps_unconfigured_standard_venues_unknown(self):
        readers = build_readers([])

        self.assertEqual(
            readers["hyperliquid"](),
            {"status": "unknown", "reason": "snapshot_file_missing"},
        )
        self.assertEqual(
            readers["solana"](),
            {"status": "unknown", "reason": "snapshot_file_missing"},
        )

    def test_reader_rejects_snapshot_with_missing_cost_before_aggregation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "alpaca.json"
            incomplete = snapshot()
            del incomplete["model_cost_usd"]
            path.write_text(json.dumps(incomplete), encoding="utf-8")

            result = build_readers([f"alpaca={path}"])["alpaca"]()

            self.assertEqual(result, {"status": "unknown", "reason": "cost_unknown"})

    def test_run_once_loads_snapshot_and_persists_delivered_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot_path = root / "alpaca.json"
            snapshot_path.write_text(json.dumps(snapshot()), encoding="utf-8")
            owner_flow_path = root / "owner-flow.json"
            owner_flow_path.write_text(
                json.dumps({"owner_cash_flow_usd": "0", "source_receipt_ids": ["flow-1"]}),
                encoding="utf-8",
            )
            calls = []

            receipt = run_once(
                snapshot_specs=[f"alpaca={snapshot_path}"],
                state_dir=root / "state",
                today="2026-09-28",
                owner_cash_flow_path=owner_flow_path,
                available_capital_usd="0",
                send=lambda message: calls.append(message) or {"message_id": "m-1"},
            )

            self.assertEqual(receipt["status"], "delivered")
            self.assertEqual(receipt["provider_message_id"], "m-1")
            self.assertEqual(len(calls), 1)
            self.assertEqual(receipt["aggregate"]["measurement_status"], "partial")
            self.assertEqual(receipt["aggregate"]["net_pnl_usd"], "8.00")
            self.assertEqual(
                json.loads((root / "state" / "cross-venue-2026-09-28.json").read_text())[
                    "provider_message_id"
                ],
                "m-1",
            )

    def test_main_is_a_finite_cli_and_accepts_injected_sender(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            output = StringIO()
            with redirect_stdout(output):
                status = main(
                    ["--state-dir", str(root / "state"), "--today", "2026-09-28"],
                    send=lambda message: calls.append(message) or {"message_id": "m-2"},
                )

            self.assertEqual(status, 0)
            self.assertEqual(len(calls), 1)
            result = json.loads(output.getvalue())
            self.assertEqual(result["provider_message_id"], "m-2")
            self.assertEqual(result["input_manifest_status"], "missing")


if __name__ == "__main__":
    unittest.main()
