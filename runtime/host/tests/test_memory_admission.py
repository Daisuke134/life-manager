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
    def setUp(self):
        # Host swap is a real signal on the developer Mac; pin it unless a test sets its own.
        patcher = patch.object(MODULE, "swap_used_mb", return_value=0.0)
        patcher.start()
        self.addCleanup(patcher.stop)

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
                patch.object(MODULE, "swap_used_mb", return_value=0.0),
                patch.object(MODULE.os, "execvpe") as execute,
            ):
                self.assertEqual(MODULE.main(["/usr/bin/true"]), 75)
            execute.assert_not_called()
            row = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(row["reason"], "memory_headroom_low")
            self.assertEqual(row["free_percent"], 9)
            self.assertEqual(row["effect"], 0)

    def test_parse_swap_used_mb(self):
        self.assertEqual(MODULE.parse_swap_used_mb(
            "vm.swapusage: total = 17152.00M  used = 16625.94M  free = 526.06M  (encrypted)\n"), 16625.94)
        self.assertIsNone(MODULE.parse_swap_used_mb("unexpected"))

    def test_swap_pressure_defers_even_when_free_percent_looks_healthy(self):
        # 2026-10-23 21:30 JST: memory_pressure -Q read 29-31% free while swap sat at 15.7-18.1 GB
        # on a 16 GB Mac mini, ate the boot volume to 300 MiB, and 84 lm_loop_run wakes piled up.
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "memory.json"
            with (
                patch.dict(os.environ, {
                    "LIFE_MANAGER_MEMORY_RECEIPT": str(receipt),
                    "LIFE_MANAGER_MIN_MEMORY_FREE_PERCENT": "15",
                    "LIFE_MANAGER_MAX_SWAP_PERCENT_OF_RAM": "75",
                }, clear=True),
                patch.object(MODULE, "memory_free_percent", return_value=30),
                patch.object(MODULE, "swap_used_mb", return_value=15700.0),
                patch.object(MODULE, "physical_memory_mb", return_value=16384.0),
                patch.object(MODULE.os, "execvpe") as execute,
            ):
                self.assertEqual(MODULE.main(["/usr/bin/true"]), 75)
            execute.assert_not_called()
            row = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(row["reason"], "swap_pressure_high")
            self.assertEqual(row["swap_used_mb"], 15700.0)
            self.assertEqual(row["swap_limit_mb"], 12288.0)

    def test_healthy_headroom_executes_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "memory.json"
            with (
                patch.dict(os.environ, {
                    "LIFE_MANAGER_MEMORY_RECEIPT": str(receipt),
                    "LIFE_MANAGER_MIN_MEMORY_FREE_PERCENT": "15",
                }, clear=True),
                patch.object(MODULE, "memory_free_percent", return_value=43),
                patch.object(MODULE, "swap_used_mb", return_value=0.0),
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


def _plateau_module():
    import runtime.host.memory_admission as module
    return module


def test_swap_plateau_needs_five_minutes_of_history_before_it_can_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFE_MANAGER_SWAP_SAMPLES", str(tmp_path / "swap.json"))
    m = _plateau_module()
    assert m.swap_plateau(15300.0, now=1000.0) is False
    assert m.swap_plateau(15300.0, now=1000.0 + 299) is False
    assert m.swap_plateau(15350.0, now=1000.0 + 301) is True


def test_swap_plateau_is_false_while_swap_keeps_growing(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFE_MANAGER_SWAP_SAMPLES", str(tmp_path / "swap.json"))
    m = _plateau_module()
    m.swap_plateau(14000.0, now=2000.0)
    assert m.swap_plateau(14600.0, now=2000.0 + 400) is False


def test_swap_plateau_forgets_samples_older_than_the_window(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFE_MANAGER_SWAP_SAMPLES", str(tmp_path / "swap.json"))
    m = _plateau_module()
    m.swap_plateau(10000.0, now=3000.0)
    # the 10000 MB sample is 20 minutes old, so it no longer proves a rise; only one fresh sample remains
    assert m.swap_plateau(15300.0, now=3000.0 + 1200) is False


def test_swap_plateau_fails_closed_when_history_cannot_be_written(tmp_path, monkeypatch):
    blocked = tmp_path / "file"
    blocked.write_text("x")
    monkeypatch.setenv("LIFE_MANAGER_SWAP_SAMPLES", str(blocked / "swap.json"))
    m = _plateau_module()
    assert m.swap_plateau(15300.0, now=4000.0) is False
