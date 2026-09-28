from __future__ import annotations

import fcntl
import importlib.util
import pathlib
import sys
import tempfile
import unittest


MODULE_PATH = pathlib.Path(__file__).with_name("truth_pipeline.py")
SPEC = importlib.util.spec_from_file_location("truth_pipeline", MODULE_PATH)
assert SPEC and SPEC.loader
truth_pipeline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = truth_pipeline
SPEC.loader.exec_module(truth_pipeline)


class TruthPipelineTest(unittest.TestCase):
    def test_commands_are_serialized_reconcile_collect_report_without_paid_tools(self):
        root = pathlib.Path("/repo")
        home = pathlib.Path("/home/owner")
        commands = truth_pipeline.build_commands(root, home, python="/python")
        rendered = [" ".join(command) for command in commands]
        self.assertIn("publication_ledger.py", rendered[0])
        self.assertIn("--quality-gate-exit-code 3", rendered[0])
        self.assertIn("native_metrics.py", rendered[1])
        self.assertEqual(
            [command[command.index("--kind") + 1] for command in commands[2:]],
            ["action", "checkpoint", "incident", "experiment", "product_daily", "portfolio_weekly"],
        )
        self.assertNotIn("apify", " ".join(rendered).lower())

    def test_commands_put_all_mutable_outputs_under_explicit_state_root(self):
        root = pathlib.Path("/read-only-release")
        home = pathlib.Path("/home/owner")
        state_root = pathlib.Path("/writable/marketing-owner-events")

        commands = truth_pipeline.build_commands(
            root, home, state_root=state_root, python="/python"
        )

        rendered = "\n".join(" ".join(command) for command in commands)
        self.assertEqual(
            commands[0][commands[0].index("--output") + 1],
            str(state_root / "state/publication-identity.jsonl"),
        )
        self.assertIn(str(state_root / "evidence/metrics/publication-reconcile-latest.json"), rendered)
        self.assertEqual(
            commands[1][commands[1].index("--ledger") + 1],
            str(state_root / "state/publication-identity.jsonl"),
        )
        self.assertEqual(
            commands[1][commands[1].index("--state") + 1],
            str(state_root / "state/post-metrics.jsonl"),
        )
        self.assertEqual(
            commands[1][commands[1].index("--raw-evidence") + 1],
            str(state_root / "evidence/metrics/provider-responses.jsonl"),
        )
        self.assertIn(str(state_root / "evidence/metrics/native-metrics-latest.json"), rendered)
        self.assertEqual(
            [command[command.index("--state-root") + 1] for command in commands[2:6]],
            [str(state_root / "state")] * 4,
        )
        metrics_state = home / ".local/state/life-manager/marketing-metrics-daily/state"
        self.assertEqual(
            [command[command.index("--state-root") + 1] for command in commands[6:]],
            [str(metrics_state)] * 2,
        )
        self.assertNotIn("/read-only-release/skills/earn/marketing-engine/state", rendered)
        self.assertNotIn("/read-only-release/skills/earn/marketing-engine/evidence", rendered)

    def test_nonblocking_lock_prevents_overlapping_external_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = pathlib.Path(tmp) / "truth.lock"
            lock_path.touch()
            calls = []
            with lock_path.open("r+") as held:
                fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = truth_pipeline.run_pipeline(
                    [["one"], ["two"]],
                    lock_path=lock_path,
                    run_command=lambda command: calls.append(command) or 0,
                )
        self.assertEqual(result["status"], "locked")
        self.assertEqual(calls, [])

    def test_failure_does_not_suppress_health_reporting(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []

            def runner(command: list[str]) -> int:
                calls.append(command[0])
                return 1 if command[0] == "collect" else 0

            result = truth_pipeline.run_pipeline(
                [["reconcile"], ["collect"], ["report"]],
                lock_path=pathlib.Path(tmp) / "truth.lock",
                run_command=runner,
            )
        self.assertEqual(calls, ["reconcile", "collect", "report"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed_stages"], ["collect"])

    def test_reconcile_quality_gate_is_attention_not_pipeline_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = truth_pipeline.run_pipeline(
                [["publication_ledger.py"], ["native_metrics.py"]],
                lock_path=pathlib.Path(tmp) / "truth.lock",
                run_command=lambda command: 3 if "publication_ledger.py" in command else 0,
            )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["failed_stages"], [])
        self.assertEqual(result["attention_stages"], ["reconcile"])
        self.assertEqual(
            result["stages"],
            [
                {"stage": "reconcile", "returncode": 3, "result": "attention"},
                {"stage": "collect", "returncode": 0, "result": "pass"},
            ],
        )

    def test_reconcile_runtime_error_remains_pipeline_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = truth_pipeline.run_pipeline(
                [["publication_ledger.py"]],
                lock_path=pathlib.Path(tmp) / "truth.lock",
                run_command=lambda _command: 1,
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed_stages"], ["reconcile"])
        self.assertEqual(result["attention_stages"], [])


if __name__ == "__main__":
    unittest.main()
