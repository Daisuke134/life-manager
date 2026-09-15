import unittest
import importlib.util
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]


def load_route_lookup():
    path = ROOT / "skills/anicca-life-manager/scripts/route_lookup.py"
    spec = importlib.util.spec_from_file_location("route_lookup_test", path)
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
        route = load_route_lookup()
        completed = mock.Mock(returncode=0, stdout="ok", stderr="")
        with mock.patch.object(route.subprocess, "run", return_value=completed) as run:
            self.assertEqual(route._run_ab(["snapshot"]), "ok")
        self.assertEqual(run.call_args.args[0][:3], [
            route.AGENT_BROWSER, "--session", "life-manager-lateness-route",
        ])

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

        self.assertEqual(calls[-1], (["close"], 20))


if __name__ == "__main__":
    unittest.main()
