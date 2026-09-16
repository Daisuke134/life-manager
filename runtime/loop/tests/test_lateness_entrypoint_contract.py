import unittest
import importlib.util
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]


def load_route_lookup():
    path = ROOT / "skills/anicca-life-manager/scripts/route_lookup.py"
    spec = importlib.util.spec_from_file_location("route_lookup_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_lateness_check():
    path = ROOT / "skills/anicca-life-manager/scripts/lateness_check.py"
    spec = importlib.util.spec_from_file_location("lateness_check_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LatenessEntrypointContractTest(unittest.TestCase):
    def test_state_and_logs_live_outside_immutable_release(self):
        source = (ROOT / "skills/anicca-life-manager/scripts/run.sh").read_text()
        self.assertIn('LOG="$STATE_ROOT/logs/run.log"', source)
        self.assertIn("unset ANICCA_HOME OPENCLAW_ENV_FILE", source)
        self.assertEqual(source.count("unset ANICCA_HOME OPENCLAW_ENV_FILE"), 2)
        self.assertNotIn("migrate-legacy-lateness-state.py", source)
        self.assertIn('PYTHON_BIN="${LIFE_MANAGER_PYTHON:-python3}"', source)
        self.assertIn('"$LIFE_MANAGER_REPO/runtime/run-with-timeout.py"', source)
        self.assertNotIn("/opt/homebrew", source)
        self.assertNotIn("TIMEOUT_BIN", source)
        self.assertIn("LATENESS_STATUS=$?", source)
        self.assertIn('exit "$LATENESS_STATUS"', source)
        self.assertNotIn('LOG="$SKILL/state/run.log"', source)
        self.assertNotIn("openclaw cron", source.lower())

        checker = (ROOT / "skills/anicca-life-manager/scripts/lateness_check.py").read_text()
        self.assertIn('LOOP_STATE_DIR = LIFE_MANAGER_STATE_ROOT / "state"', checker)
        for name in (
            "heartbeat_log.jsonl",
            "nudge_sent.json",
            "active_call_loop.json",
            "renraku_sent.json",
        ):
            self.assertIn(f'LOOP_STATE_DIR / "{name}"', checker)
        self.assertNotIn('parent.parent / "state"', checker)

        for relative in (
            "arrival.py",
            "gcal_departures.py",
            "route_lookup.py",
            "renraku.py",
        ):
            helper = (ROOT / "skills/anicca-life-manager/scripts" / relative).read_text()
            self.assertNotIn("/opt/homebrew/bin", helper, relative)

    def test_route_lookup_uses_owned_agent_browser_session(self):
        with mock.patch.dict(os.environ, {"LIFE_MANAGER_AGENT_BROWSER_SESSION": "shared-session"}):
            route = load_route_lookup()
            another_run = load_route_lookup()
        completed = mock.Mock(returncode=0, stdout="ok", stderr="")
        with mock.patch.object(route.subprocess, "run", return_value=completed) as run:
            self.assertEqual(route._run_ab(["snapshot"]), "ok")
        self.assertEqual(run.call_args.args[0][:3], [route.AGENT_BROWSER, "--session", route.AGENT_BROWSER_SESSION])
        self.assertTrue(route.AGENT_BROWSER_SESSION.startswith("life-manager-lateness-route-"))
        self.assertNotEqual(route.AGENT_BROWSER_SESSION, another_run.AGENT_BROWSER_SESSION)

    def test_lateness_parent_uses_group_timeout_with_browser_close_grace(self):
        checker = load_lateness_check()
        completed = mock.Mock(returncode=124, stdout="", stderr="")
        with mock.patch.object(checker.subprocess, "run", return_value=completed) as run:
            self.assertIs(checker.run_route_lookup("35.0,139.0", "Tokyo"), completed)
        command = run.call_args.args[0]
        self.assertEqual(command[:5], [
            sys.executable, str(ROOT / "runtime/run-with-timeout.py"),
            "--grace-seconds", "10", "45",
        ])
        self.assertEqual(command[5:7], [
            sys.executable, str(ROOT / "skills/anicca-life-manager/scripts/route_lookup.py"),
        ])
        self.assertNotIn("timeout", run.call_args.kwargs)

    def test_route_lookup_closes_owned_session_after_failure(self):
        route = load_route_lookup()
        calls = []

        def invoke(args, timeout=30):
            calls.append((args, timeout))
            if args[0] == "snapshot":
                raise RuntimeError("snapshot failed")
            return ""

        with (mock.patch.object(route, "_run_ab", side_effect=invoke),
              mock.patch.object(route.time, "sleep")):
            with self.assertRaisesRegex(RuntimeError, "snapshot failed"):
                route.fetch_transit_route("35.0,139.0", "destination")

        self.assertEqual(calls[-1], (["close"], 8))

    def test_route_lookup_closes_its_session_when_timeout_sends_term(self):
        route = load_route_lookup()
        calls = []

        def invoke(args, timeout=30):
            calls.append(args[0])
            if args[0] == "snapshot":
                route._terminate_route(15, None)
            return ""

        with (mock.patch.object(route, "_run_ab", side_effect=invoke),
              mock.patch.object(route.time, "sleep")):
            with self.assertRaises(SystemExit):
                route.fetch_transit_route("35.0,139.0", "destination")
        self.assertEqual(calls, ["open", "snapshot", "close"])

    def test_route_lookup_sigterm_closes_only_its_process_named_session(self):
        with tempfile.TemporaryDirectory(prefix="lateness-browser-term-") as directory:
            root = Path(directory)
            trace = root / "trace"
            browser = root / "fake-browser"
            browser.write_text(
                "#!/bin/sh\n"
                'printf "%s\\n" "$*" >> "$TRACE"\n'
                "exit 0\n",
            )
            browser.chmod(0o700)
            env = {**os.environ, "LIFE_MANAGER_AGENT_BROWSER": str(browser), "TRACE": str(trace)}
            env.pop("LIFE_MANAGER_AGENT_BROWSER_SESSION", None)
            process = subprocess.Popen(
                [sys.executable, str(ROOT / "skills/anicca-life-manager/scripts/route_lookup.py"),
                 "--origin", "35.0,139.0", "--destination", "Tokyo"],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            try:
                deadline = time.monotonic() + 5
                while not trace.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(trace.exists(), "browser open was not reached")
                process.send_signal(signal.SIGTERM)
                process.communicate(timeout=5)
                self.assertEqual(process.returncode, 143)
                calls = trace.read_text().splitlines()
                self.assertEqual(len(calls), 2)
                self.assertIn(" open ", f" {calls[0]} ")
                self.assertTrue(calls[1].endswith(" close"))
                self.assertEqual(calls[0].split(" ")[1], calls[1].split(" ")[1])
                self.assertTrue(calls[0].split(" ")[1].startswith("life-manager-lateness-route-"))
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
