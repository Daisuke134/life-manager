from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest import TestCase, mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "bounded-exec.py"
SPEC = importlib.util.spec_from_file_location("bounded_exec", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
bounded_exec = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bounded_exec)


class BoundedExecDescendantTests(TestCase):
    def test_descendant_snapshot_walks_recursive_children(self) -> None:
        ps = """\
  101     1 Mon Sep 19 12:00:00 2026 /bin/runner
  202   101 Mon Sep 19 12:00:01 2026 /bin/direct-child
  303   202 Mon Sep 19 12:00:02 2026 /bin/detached-grandchild
  404   999 Mon Sep 19 12:00:03 2026 /bin/unrelated
"""
        with mock.patch.object(
            bounded_exec, "_process_table", return_value={
                101: (1, "Mon Sep 19 12:00:00 2026"),
                202: (101, "Mon Sep 19 12:00:01 2026"),
                303: (202, "Mon Sep 19 12:00:02 2026"),
                404: (999, "Mon Sep 19 12:00:03 2026"),
            }
        ):
            self.assertEqual(
                bounded_exec._descendant_identities(101),
                {
                    202: "Mon Sep 19 12:00:01 2026",
                    303: "Mon Sep 19 12:00:02 2026",
                },
            )

    def test_termination_signals_owned_descendants_before_cleanup(self) -> None:
        process = SimpleNamespace(pid=101, poll=lambda: None, wait=mock.Mock())
        descendants = {
            202: "Mon Sep 19 12:00:01 2026",
            303: "Mon Sep 19 12:00:02 2026",
        }
        with (
            mock.patch.object(bounded_exec, "_descendant_identities", return_value=descendants),
            mock.patch.object(bounded_exec, "_group_exists", side_effect=[True, False, False]),
            mock.patch.object(bounded_exec, "_signal_owned", return_value=True) as signal_owned,
            mock.patch.object(bounded_exec.os, "killpg") as killpg,
            mock.patch.object(bounded_exec.time, "sleep"),
        ):
            bounded_exec._terminate_group(process)

        killpg.assert_any_call(101, bounded_exec.signal.SIGTERM)
        self.assertEqual(
            signal_owned.call_args_list[:2],
            [
                mock.call(202, descendants[202], bounded_exec.signal.SIGTERM),
                mock.call(303, descendants[303], bounded_exec.signal.SIGTERM),
            ],
        )
        self.assertEqual(
            signal_owned.call_args_list[2:],
            [
                mock.call(202, descendants[202], bounded_exec.signal.SIGKILL),
                mock.call(303, descendants[303], bounded_exec.signal.SIGKILL),
            ],
        )
        process.wait.assert_called_once_with()

    def test_timeout_terminates_detached_grandchild(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pid_file = root / "child.pid"
            helper = root / "spawn-detached.py"
            helper.write_text(
                "import os, pathlib, sys, time\n"
                "pid = os.fork()\n"
                "if pid == 0:\n"
                "    os.setsid()\n"
                "    pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))\n"
                "    time.sleep(30)\n"
                "    os._exit(0)\n"
                "time.sleep(30)\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(MODULE_PATH), "0.2", sys.executable,
                 str(helper), str(pid_file)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 124, result.stderr)
            child_pid = int(pid_file.read_text(encoding="utf-8"))
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                try:
                    os.kill(child_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.05)
            else:
                subprocess.run(["kill", "-KILL", str(child_pid)], check=False)
                self.fail("detached grandchild survived bounded timeout")
