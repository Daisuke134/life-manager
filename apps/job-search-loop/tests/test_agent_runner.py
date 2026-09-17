import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from job_search_loop.agent_runner import (
    AgentRunner,
    ContractError,
    PassAlreadyRunning,
    TASK_CLASSES,
)


class AgentRunnerTests(unittest.TestCase):
    def test_default_runner_is_the_canonical_life_manager_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = AgentRunner(evidence_root=Path(directory) / "evidence")
            repo_root = Path(__file__).resolve().parents[3]
            self.assertEqual(
                runner.runner_path,
                repo_root / "runtime" / "agent-runner" / "agent_runner.py",
            )

    def test_task_routes_are_pinned(self):
        self.assertEqual(TASK_CLASSES["tailor"], "composition-agent")
        self.assertEqual(TASK_CLASSES["inbox"], "composition-agent")
        self.assertEqual(TASK_CLASSES["submit"], "browser-lane-agent")
        self.assertEqual(TASK_CLASSES["improve"], "high-value-agent")

    def test_mercor_pass_supplies_required_escalation_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = AgentRunner(
                runner_path=Path("/opt/agent_runner.py"),
                evidence_root=root / "evidence",
            )
            completed = type(
                "Completed",
                (),
                {
                    "returncode": 0,
                    "stdout": json.dumps(
                        {
                            "status": "success",
                            "result_path": str(root / "result.json"),
                        }
                    ),
                    "stderr": "",
                },
            )()
            (root / "result.json").write_text('{"answer":"ok"}', encoding="utf-8")
            schema = root / "schema.json"
            schema.write_text('{"type":"object","required":["answer"]}', encoding="utf-8")
            process = type("Process", (), {
                "pid": 4242,
                "returncode": completed.returncode,
                "communicate": lambda self, **kwargs: (completed.stdout, completed.stderr),
                "wait": lambda self, **kwargs: self.returncode,
                "poll": lambda self: self.returncode,
            })()
            with patch("subprocess.Popen", return_value=process) as call:
                runner.run(
                    task="mercor_pass",
                    prompt="Grounded task",
                    schema_path=schema,
                    workdir=root,
                    run_id="mercor-pass",
                )
            argv = call.call_args.args[0]
            self.assertIn("--escalation-reason", argv)
            self.assertIn("Mercor application", argv[argv.index("--escalation-reason") + 1])

    def test_composition_prompt_uses_stdin_and_retains_private_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = AgentRunner(
                runner_path=Path("/opt/agent_runner.py"),
                evidence_root=root / "evidence",
            )
            completed = type(
                "Completed",
                (),
                {
                    "returncode": 0,
                    "stdout": json.dumps(
                        {
                            "status": "success",
                            "result_path": str(root / "result.json"),
                        }
                    ),
                    "stderr": "",
                },
            )()
            (root / "result.json").write_text('{"answer":"ok"}', encoding="utf-8")
            schema = root / "schema.json"
            schema.write_text(
                '{"type":"object","required":["answer"]}', encoding="utf-8"
            )
            process = type("Process", (), {
                "pid": 4242,
                "returncode": completed.returncode,
                "received_input": None,
                "communicate": lambda self, **kwargs: (setattr(self, "received_input", kwargs.get("input")) or (completed.stdout, completed.stderr)),
                "wait": lambda self, **kwargs: self.returncode,
                "poll": lambda self: self.returncode,
            })()
            with patch("subprocess.Popen", return_value=process) as call:
                result = runner.run(
                    task="tailor",
                    prompt="Grounded task",
                    schema_path=schema,
                    workdir=root,
                    run_id="one",
                )
            argv = call.call_args.args[0]
            self.assertIn("--prompt-stdin", argv)
            self.assertNotIn("--prompt-file", argv)
            self.assertEqual(process.received_input, "Grounded task")
            self.assertNotIn("Grounded task", argv)
            prompt_path = root / "evidence" / "one" / "prompt.md"
            self.assertEqual(prompt_path.read_text(encoding="utf-8"), "Grounded task")
            self.assertEqual(prompt_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(result["answer"], "ok")

    def test_missing_required_result_field_fails_closed(self):
        with self.assertRaises(ContractError):
            AgentRunner.validate({"other": True}, {"required": ["answer"]})

    def test_identified_busy_runner_is_not_a_contract_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = AgentRunner(
                runner_path=Path("/opt/agent_runner.py"),
                evidence_root=root / "evidence",
            )
            schema = root / "schema.json"
            schema.write_text('{"type":"object"}', encoding="utf-8")
            completed = type("Completed", (), {
                "returncode": 75,
                "stdout": "",
                "stderr": "LIFE_MANAGER_PROVIDER_LEASE_BUSY\nprovider lease busy\n",
            })()
            process = type("Process", (), {
                "pid": 4242,
                "returncode": completed.returncode,
                "communicate": lambda self, **kwargs: (completed.stdout, completed.stderr),
                "wait": lambda self, **kwargs: self.returncode,
                "poll": lambda self: self.returncode,
            })()
            with patch("subprocess.Popen", return_value=process):
                with self.assertRaises(PassAlreadyRunning):
                    runner.run(
                        task="mercor_pass", prompt="Grounded task",
                        schema_path=schema, workdir=root, run_id="busy",
                    )

    def test_unidentified_rc75_remains_a_contract_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = AgentRunner(
                runner_path=Path("/opt/agent_runner.py"),
                evidence_root=root / "evidence",
            )
            schema = root / "schema.json"
            schema.write_text('{"type":"object"}', encoding="utf-8")
            completed = type("Completed", (), {
                "returncode": 75, "stdout": "", "stderr": "budget blocked\n",
            })()
            process = type("Process", (), {
                "pid": 4242,
                "returncode": completed.returncode,
                "communicate": lambda self, **kwargs: (completed.stdout, completed.stderr),
                "wait": lambda self, **kwargs: self.returncode,
                "poll": lambda self: self.returncode,
            })()
            with patch("subprocess.Popen", return_value=process):
                with self.assertRaises(ContractError):
                    runner.run(
                        task="mercor_pass", prompt="Grounded task",
                        schema_path=schema, workdir=root, run_id="budget-blocked",
                    )

    def test_timeout_terminates_the_runner_process_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = AgentRunner(
                runner_path=Path("/opt/agent_runner.py"),
                evidence_root=root / "evidence",
            )
            schema = root / "schema.json"
            schema.write_text('{"type":"object"}', encoding="utf-8")

            class HangingProcess:
                pid = 4242
                returncode = None

                def communicate(self, *, input=None, timeout=None):
                    raise subprocess.TimeoutExpired(["agent-runner"], timeout)

                def wait(self, timeout=None):
                    self.returncode = -signal.SIGTERM
                    return self.returncode

                def poll(self):
                    return self.returncode

            process = HangingProcess()
            with patch("subprocess.Popen", return_value=process) as popen, patch(
                "job_search_loop.agent_runner.os.killpg"
            ) as killpg:
                with self.assertRaisesRegex(ContractError, "timed out"):
                    runner.run(
                        task="mercor_pass", prompt="Grounded task",
                        schema_path=schema, workdir=root, run_id="timeout",
                    )
            killpg.assert_called_once_with(4242, signal.SIGTERM)
            self.assertTrue(popen.call_args.kwargs["start_new_session"])

    def test_timeout_reaps_a_real_runner_descendant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child_pid_path = root / "child.pid"
            runner_script = root / "runner.py"
            runner_script.write_text(
                "import os, subprocess, sys, time\n"
                "from pathlib import Path\n"
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
                "Path(os.environ['CHILD_PID_FILE']).write_text(str(child.pid))\n"
                "time.sleep(30)\n",
                encoding="utf-8",
            )
            schema = root / "schema.json"
            schema.write_text('{"type":"object"}', encoding="utf-8")
            runner = AgentRunner(
                runner_path=runner_script,
                evidence_root=root / "evidence",
            )
            with patch.dict(os.environ, {"CHILD_PID_FILE": str(child_pid_path)}), patch(
                "job_search_loop.agent_runner.AGENT_RUNNER_TIMEOUT_SECONDS", 1
            ):
                with self.assertRaisesRegex(ContractError, "timed out"):
                    runner.run(
                        task="mercor_pass", prompt="Grounded task",
                        schema_path=schema, workdir=root, run_id="real-timeout",
                    )
            child_pid = int(child_pid_path.read_text(encoding="utf-8"))
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                probe = subprocess.run(
                    ["/bin/ps", "-p", str(child_pid), "-o", "pid="],
                    check=False, capture_output=True, text=True,
                )
                if not probe.stdout.strip():
                    break
                time.sleep(0.05)
            else:
                self.fail(f"runner descendant {child_pid} survived timeout cleanup")


if __name__ == "__main__":
    unittest.main()
