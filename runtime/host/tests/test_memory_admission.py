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
        for name, value in (("swap_used_mb", 0.0), ("swapin_pages_per_second", 0.0)):
            patcher = patch.object(MODULE, name, return_value=value)
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

    def test_parse_swapins(self):
        self.assertEqual(MODULE.parse_swapins(
            "Mach Virtual Memory Statistics: (page size of 16384 bytes)\nSwapins:  50370264.\nSwapouts: 61234567.\n"),
            50370264)
        self.assertIsNone(MODULE.parse_swapins("unexpected"))

    def test_high_swap_total_alone_does_not_defer(self):
        # 2026-10-24 14:1x JST: swap sat at 17.1/18.4 GB with 28-31% free and swap-ins at 159-880 pages/s,
        # and the absolute-size gate deferred writer-claim-loop, article-daily, mercor and fundraiser for 10 h.
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "memory.json"
            with (
                patch.dict(os.environ, {"LIFE_MANAGER_MEMORY_RECEIPT": str(receipt)}, clear=True),
                patch.object(MODULE, "memory_free_percent", return_value=29),
                patch.object(MODULE, "swap_used_mb", return_value=17298.0),
                patch.object(MODULE, "swapin_pages_per_second", return_value=880.0),
                patch.object(MODULE.os, "execvpe", side_effect=SystemExit) as execute,
            ):
                with self.assertRaises(SystemExit):
                    MODULE.main(["/usr/bin/true"])
            self.assertEqual(execute.call_args.args[0], "/usr/bin/true")
            self.assertEqual(json.loads(receipt.read_text())["reason"], "memory_headroom_ok")

    def test_fast_swap_ins_defer_even_when_free_percent_looks_healthy(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "memory.json"
            with (
                patch.dict(os.environ, {"LIFE_MANAGER_MEMORY_RECEIPT": str(receipt)}, clear=True),
                patch.object(MODULE, "memory_free_percent", return_value=30),
                patch.object(MODULE, "swapin_pages_per_second", return_value=2500.0),
                patch.object(MODULE.os, "execvpe") as execute,
            ):
                self.assertEqual(MODULE.main(["/usr/bin/true"]), 75)
            execute.assert_not_called()
            row = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(row["reason"], "swap_pressure_high")
            self.assertEqual(row["swapin_pages_per_second"], 2500.0)
            self.assertEqual(row["max_swapin_pages_per_second"], 2000)

    def test_unmeasurable_swap_in_rate_defers(self):
        # no vm_stat reading proves nothing, so the gate stays closed
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "memory.json"
            with (
                patch.dict(os.environ, {"LIFE_MANAGER_MEMORY_RECEIPT": str(receipt)}, clear=True),
                patch.object(MODULE, "memory_free_percent", return_value=30),
                patch.object(MODULE, "swapin_pages_per_second", return_value=None),
                patch.object(MODULE.os, "execvpe") as execute,
            ):
                self.assertEqual(MODULE.main(["/usr/bin/true"]), 75)
            execute.assert_not_called()
            self.assertEqual(json.loads(receipt.read_text())["reason"], "swap_rate_unavailable")

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


def _module():
    import runtime.host.memory_admission as module
    return module


def test_swapin_rate_needs_five_minutes_of_history(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFE_MANAGER_SWAP_SAMPLES", str(tmp_path / "swap.json"))
    m = _module()
    assert m.swapin_rate(1_000_000, now=1000.0) is None
    assert m.swapin_rate(1_100_000, now=1000.0 + 299) is None
    assert m.swapin_rate(1_301_000, now=1000.0 + 301) == 1000.0


def test_swapin_rate_forgets_samples_older_than_the_window(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFE_MANAGER_SWAP_SAMPLES", str(tmp_path / "swap.json"))
    m = _module()
    m.swapin_rate(0, now=3000.0)
    # the 20-minute-old sample is outside the 15-minute window, so no rate is proven
    assert m.swapin_rate(9_000_000, now=3000.0 + 1200) is None


def test_swapin_rate_is_none_when_history_cannot_be_written(tmp_path, monkeypatch):
    blocked = tmp_path / "file"
    blocked.write_text("x")
    monkeypatch.setenv("LIFE_MANAGER_SWAP_SAMPLES", str(blocked / "swap.json"))
    assert _module().swapin_rate(1_000_000, now=4000.0) is None


def test_missing_history_falls_back_to_a_live_probe(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFE_MANAGER_SWAP_SAMPLES", str(tmp_path / "swap.json"))
    m = _module()
    readings = iter([1_000_000, 1_006_000])
    monkeypatch.setattr(m, "swapins", lambda: next(readings))
    monkeypatch.setattr(m.time, "sleep", lambda seconds: None)
    assert m.swapin_pages_per_second() == 3000.0


def test_probe_without_vm_stat_is_unmeasured(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFE_MANAGER_SWAP_SAMPLES", str(tmp_path / "swap.json"))
    m = _module()
    monkeypatch.setattr(m, "swapins", lambda: None)
    assert m.swapin_pages_per_second() is None
