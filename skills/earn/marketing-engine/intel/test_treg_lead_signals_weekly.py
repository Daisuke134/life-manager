import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


INTEL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(INTEL_DIR))
sys.path.insert(0, str(INTEL_DIR.parent / "gates"))

import treg_lead_signals_weekly as monitor  # noqa: E402
from product_router import load_registry  # noqa: E402


class ProductProfileRegistryTests(unittest.TestCase):
    def test_four_apps_are_formal_unique_research_products_without_social_accounts(self):
        expected = {
            "dhamma-quotes": (
                "https://apps.apple.com/us/app/daily-dhamma/id6757726663?uo=4",
                "People seeking authentic Dhammapada teachings and mindfulness reminders throughout the day.",
            ),
            "sleep-reset": (
                "https://apps.apple.com/us/app/for-better-sleep-sleep-reset/id6762143790?uo=4",
                "People recovering from a disrupted sleep schedule who want a personalized bedtime plan and guided breathwork.",
            ),
            "studio-cherie": (
                "https://apps.apple.com/us/app/studio-cherie/id6766485903?uo=4",
                "Adults who want personal styling and outfit suggestions based on the clothes in their own wardrobe.",
            ),
            "thankful": (
                "https://apps.apple.com/us/app/thankful-gratitude-journal/id6759514159?uo=4",
                "People building a daily gratitude journaling practice.",
            ),
        }
        engine = INTEL_DIR.parent
        registry = load_registry(engine)
        profiles = monitor.load_product_profiles(
            engine / "registry" / "products",
            INTEL_DIR / "lead-signals-products-extra.json",
        )

        self.assertLessEqual(set(expected), set(registry.products))
        for product_id, (url, audience) in expected.items():
            with self.subTest(product_id=product_id):
                product = registry.products[product_id]
                self.assertEqual(product["type"], "ios_app")
                self.assertEqual(product["live_status"], "app_store_live")
                self.assertEqual(product["destination_url"], url)
                self.assertIn(audience, product["audiences"])
                matches = [row for row in profiles if row["product_id"] == product_id]
                self.assertEqual(len(matches), 1)
                self.assertEqual(matches[0]["listing_url"], url)
                self.assertIn(audience, matches[0]["buyer_profile"])
                self.assertFalse(any(row["product_id"] == product_id
                                     for row in registry.accounts.values()))


class SignalBaselineTests(unittest.TestCase):
    def test_unmarked_header_only_csv_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            state_root = Path(temporary)
            signals_path = state_root / "signals.csv"
            signals_path.write_text(",".join(monitor.CSV_FIELDS) + "\n", encoding="utf-8")
            signals_path.chmod(0o600)

            with self.assertRaisesRegex(monitor.MonitorError, "signals_csv_baseline"):
                monitor._read_signals(signals_path)

    def test_hash_bound_empty_baseline_is_valid_and_csv_mutation_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            signals_path = Path(temporary) / "signals.csv"
            monitor._write_signals(signals_path, [], {})

            self.assertEqual(monitor._read_signals(signals_path), [])

            with signals_path.open("a", encoding="utf-8") as stream:
                stream.write("\n")
            signals_path.chmod(0o600)
            with self.assertRaisesRegex(monitor.MonitorError, "signals_csv_baseline"):
                monitor._read_signals(signals_path)


class TregGateReceiptTests(unittest.TestCase):
    def test_weekly_owner_passes_the_authorized_restricted_route_reason(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence_dir = Path(temporary)
            result = subprocess.CompletedProcess([], 0, "{}", "")
            with patch.object(monitor.subprocess, "run", return_value=result) as run_agent:
                monitor._default_agent_runner(
                    "bounded public-signal prompt",
                    evidence_dir / "schema.json",
                    evidence_dir,
                    "treg-monitor:explicit-escalation-test",
                )

        command = run_agent.call_args.args[0]
        self.assertIn("--escalation-reason", command)
        index = command.index("--escalation-reason")
        self.assertEqual(command[index + 1], monitor.TREG_ESCALATION_REASON)

    def test_gate_ledger_must_match_captured_mcp_receipts(self):
        validator = getattr(monitor, "_validate_gate_ledger", None)
        self.assertTrue(callable(validator), "parent has no local-gate receipt validator")
        if not callable(validator):
            return

        occurrence_id = "treg-monitor:test-occurrence"
        call = {
            "occurrence_id": occurrence_id,
            "endpoint_id": "x.search",
            "reserved_micro": 3_000,
            "status": "settled",
            "created_at": "2026-10-10T00:00:00Z",
            "call_id": "treg-call-1",
            "charged_micro": 2_500,
        }
        ledger = {
            "schema_version": 1,
            "occurrence_id": occurrence_id,
            "quotes": {"x.search": {"quote_micro": 2_000, "unsafe": False}},
            "calls": [call],
            "route_count": 1,
            "reserved_micro": 3_000,
            "charged_micro": 2_500,
            "unresolved_micro": 0,
            "halted": False,
            "halt_reason": None,
            "blocked_attempt_count": 0,
            "blocked_attempts": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            ledger_path = Path(temporary) / "treg-budget-occurrence.json"
            monitor._atomic_json(ledger_path, ledger)
            receipt = {"endpoint_id": "x.search", "call_id": "treg-call-1", "charged_micro": 2_500}
            validator(ledger_path, occurrence_id, [receipt])

            with self.assertRaisesRegex(monitor.MonitorError, "treg_gate_receipt"):
                validator(ledger_path, occurrence_id, [{**receipt, "call_id": "other-call"}])


if __name__ == "__main__":
    unittest.main()
