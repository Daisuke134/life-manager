import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "memory_admission.py"
SPEC = importlib.util.spec_from_file_location("memory_admission", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class MemoryAdmissionTests(unittest.TestCase):
    def test_host_pressure_record_contains_only_bounded_redacted_metrics(self):
        record = MODULE.build_host_pressure_record(
            observed_at="2026-09-15T06:00:00Z",
            resource_class="browser",
            memory_free_percent=43,
            swap_used_bytes=1024,
            load_1m=1.25,
            active_finite_wakes=2,
            active_browser_sessions=1,
            browser_processes=4,
            browser_debug_endpoints=1,
        )
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["record_type"], "host_pressure")
        self.assertEqual(record["redaction"], "metrics_only")
        self.assertEqual(record["active_browser_sessions"], 1)
        self.assertNotIn("pid", json.dumps(record))
        self.assertNotIn("url", json.dumps(record))
        self.assertNotIn("Users/", json.dumps(record))

        with self.assertRaises(ValueError):
            MODULE.build_host_pressure_record(
                observed_at="2026-09-15T06:00:00Z",
                resource_class="browser",
                memory_free_percent=101,
                swap_used_bytes=0,
                load_1m=0,
                active_finite_wakes=0,
                active_browser_sessions=0,
                browser_processes=0,
                browser_debug_endpoints=0,
            )

    def test_parse_memory_pressure_percentage(self):
        self.assertEqual(
            MODULE.parse_free_percent(
                "System-wide memory free percentage: 43%\n"
            ),
            43,
        )
        self.assertIsNone(MODULE.parse_free_percent("unexpected"))

    def test_low_headroom_defers_without_executing_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "memory.json"
            with (
                patch.dict(os.environ, {
                    "LIFE_MANAGER_MEMORY_RECEIPT": str(receipt),
                    "LIFE_MANAGER_MIN_MEMORY_FREE_PERCENT": "15",
                }, clear=True),
                patch.object(MODULE, "memory_free_percent", return_value=9),
                patch.object(MODULE.os, "execvpe") as execute,
            ):
                self.assertEqual(MODULE.main(["/usr/bin/true"]), 75)
            execute.assert_not_called()
            row = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(row["reason"], "memory_headroom_low")
            self.assertEqual(row["free_percent"], 9)
            self.assertEqual(row["effect"], 0)

    def test_healthy_headroom_executes_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "memory.json"
            with (
                patch.dict(os.environ, {
                    "LIFE_MANAGER_MEMORY_RECEIPT": str(receipt),
                    "LIFE_MANAGER_MIN_MEMORY_FREE_PERCENT": "15",
                }, clear=True),
                patch.object(MODULE, "memory_free_percent", return_value=43),
                patch.object(MODULE.os, "execvpe", side_effect=SystemExit) as execute,
            ):
                with self.assertRaises(SystemExit):
                    MODULE.main(["/usr/bin/true"])
            self.assertEqual(execute.call_args.args[0], "/usr/bin/true")
            row = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(row["status"], "pass")
            self.assertEqual(row["free_percent"], 43)
            self.assertEqual(row["reason"], "memory_headroom_ok")

    def test_unavailable_measurement_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "memory.json"
            with (
                patch.dict(os.environ, {
                    "LIFE_MANAGER_MEMORY_RECEIPT": str(receipt),
                }, clear=True),
                patch.object(MODULE, "memory_free_percent", return_value=None),
            ):
                self.assertEqual(MODULE.main(["/usr/bin/true"]), 75)
            row = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(row["reason"], "memory_headroom_unavailable")

    def test_wait_mode_defers_in_process_until_headroom_recovers(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "memory.json"
            with (
                patch.dict(os.environ, {
                    "LIFE_MANAGER_MEMORY_RECEIPT": str(receipt),
                }, clear=True),
                patch.object(MODULE, "memory_free_percent", side_effect=[9, 43]),
                patch.object(MODULE.time, "sleep") as sleep,
                patch.object(MODULE.os, "execvpe", side_effect=SystemExit) as execute,
            ):
                with self.assertRaises(SystemExit):
                    MODULE.main(["--wait-seconds", "30", "--", "/usr/bin/true"])
            sleep.assert_called_once_with(30)
            self.assertEqual(execute.call_args.args[0], "/usr/bin/true")
            self.assertEqual(json.loads(receipt.read_text())["status"], "pass")

    def test_cpu_load_is_not_a_fleet_wide_admission_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "memory.json"
            with (
                patch.dict(os.environ, {"LIFE_MANAGER_MEMORY_RECEIPT": str(receipt)}, clear=True),
                patch.object(MODULE, "memory_free_percent", return_value=43),
                patch.object(MODULE.os, "getloadavg", side_effect=AssertionError(
                    "memory admission must not reject fleet work from host load")),
                patch.object(MODULE.os, "execvpe", side_effect=SystemExit) as execute,
            ):
                with self.assertRaises(SystemExit):
                    MODULE.main(["/usr/bin/true"])
            self.assertEqual(execute.call_args.args[0], "/usr/bin/true")
            row = json.loads(receipt.read_text())
            self.assertEqual(row["reason"], "memory_headroom_ok")


if __name__ == "__main__":
    unittest.main()
