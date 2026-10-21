#!/usr/bin/env python3
"""Executable contract tests for the Writer's sole model process boundary."""

from __future__ import annotations

import os
import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "runtime" / "model-runner.sh"


class ModelRunnerContractTests(unittest.TestCase):
    def make_environment(self, sandbox: Path, fake_codex: Path) -> dict[str, str]:
        environment = os.environ.copy()
        environment.pop("ARTICLE_MODEL_REASONING_EFFORT", None)
        environment.pop("ARTICLE_PROVIDER_COOLDOWN_SECONDS", None)
        environment.update(
            {
                "ARTICLE_PROVIDER": "codex",
                "ARTICLE_CODEX_BIN": str(fake_codex),
                "ARTICLE_MODEL_ROOT": str(sandbox / "model-root"),
                "ARTICLE_MODEL_STATE_ROOT": str(sandbox / "state"),
                "ARTICLE_PROVIDER_HEALTH": str(sandbox / "provider-health.json"),
                "ARTICLE_MODEL_LOG": str(sandbox / "model.log"),
            }
        )
        return environment

    def test_codex_cooldown_does_not_fallback_to_claude(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sandbox = Path(temporary)
            codex_calls = sandbox / "codex-calls.txt"
            claude_calls = sandbox / "claude-calls.txt"
            fake_codex = sandbox / "codex"
            fake_claude = sandbox / "claude"
            fake_codex.write_text(
                "#!/usr/bin/env bash\nprintf 'CODEX\n' >>\"$CODEX_CALLS\"\ncat >/dev/null\n",
                encoding="utf-8",
            )
            fake_claude.write_text(
                "#!/usr/bin/env bash\nprintf 'CLAUDE\n' >>\"$CLAUDE_CALLS\"\ncat >/dev/null\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            fake_claude.chmod(0o755)
            prompt = sandbox / "prompt.txt"
            prompt.write_text("do not invoke while cooling down", encoding="utf-8")
            health = sandbox / "provider-health.json"
            health.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "entries": {
                            "codex:agent": {
                                "status": "retryable",
                                "unhealthy_until": int(time.time()) + 600,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            environment = self.make_environment(sandbox, fake_codex)
            environment.update(
                {
                    "ARTICLE_RUN_ID": "codex-cooldown-contract",
                    "ARTICLE_CLAUDE_BIN": str(fake_claude),
                    "CODEX_CALLS": str(codex_calls),
                    "CLAUDE_CALLS": str(claude_calls),
                }
            )

            result = subprocess.run(
                [str(RUNNER), "agent", "--prompt-file", str(prompt)],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 75, result.stderr)
            self.assertFalse(codex_calls.exists())
            self.assertFalse(claude_calls.exists())

    def test_provider_defaults_to_codex(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sandbox = Path(temporary)
            calls = sandbox / "codex-calls.txt"
            fake_codex = sandbox / "codex"
            fake_codex.write_text(
                "#!/usr/bin/env bash\nprintf 'CODEX\\n' >>\"$CODEX_CALLS\"\n"
                "cat >/dev/null\nprintf 'CODEX-OUTPUT\\n'\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            prompt = sandbox / "prompt.txt"
            prompt.write_text("use the default provider", encoding="utf-8")
            environment = self.make_environment(sandbox, fake_codex)
            environment.pop("ARTICLE_PROVIDER")
            environment.update({
                "ARTICLE_RUN_ID": "codex-default-provider-contract",
                "CODEX_CALLS": str(calls),
            })

            result = subprocess.run(
                [str(RUNNER), "agent", "--prompt-file", str(prompt)],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(calls.read_text(encoding="utf-8"), "CODEX\n")

    def test_non_codex_provider_is_rejected_before_any_model_process(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sandbox = Path(temporary)
            claude_calls = sandbox / "claude-calls.txt"
            fake_codex = sandbox / "codex"
            fake_claude = sandbox / "claude"
            fake_codex.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            fake_claude.write_text(
                "#!/usr/bin/env bash\nprintf 'CLAUDE\\n' >>\"$CLAUDE_CALLS\"\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            fake_claude.chmod(0o755)
            prompt = sandbox / "prompt.txt"
            prompt.write_text("must fail closed", encoding="utf-8")
            environment = self.make_environment(sandbox, fake_codex)
            environment.update({
                "ARTICLE_PROVIDER": "claude",
                "ARTICLE_CLAUDE_BIN": str(fake_claude),
                "ARTICLE_RUN_ID": "codex-only-reject-contract",
                "CLAUDE_CALLS": str(claude_calls),
            })

            result = subprocess.run(
                [str(RUNNER), "agent", "--prompt-file", str(prompt)],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 64, result.stderr)
            self.assertFalse(claude_calls.exists())

    def test_retryable_default_cooldown_is_five_minutes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sandbox = Path(temporary)
            fake_codex = sandbox / "codex"
            fake_codex.write_text(
                "#!/usr/bin/env bash\ncat >/dev/null\nexit 124\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            prompt = sandbox / "prompt.txt"
            prompt.write_text("timeout", encoding="utf-8")
            environment = self.make_environment(sandbox, fake_codex)
            environment["ARTICLE_RUN_ID"] = "codex-default-cooldown-contract"
            before = int(time.time())

            result = subprocess.run(
                [str(RUNNER), "agent", "--prompt-file", str(prompt)],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 75, result.stderr)
            entry = json.loads(
                (sandbox / "provider-health.json").read_text(encoding="utf-8")
            )["entries"]["codex:agent"]
            remaining = int(entry["unhealthy_until"]) - int(time.time())
            self.assertGreaterEqual(remaining, 295)
            self.assertLessEqual(int(entry["unhealthy_until"]) - before, 305)

    def test_codex_defaults_to_terra_medium_and_preserves_prompt_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sandbox = Path(temporary)
            args_path = sandbox / "args.txt"
            stdin_path = sandbox / "stdin.txt"
            fake_codex = sandbox / "codex"
            fake_codex.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$@\" >\"$CAPTURE_ARGS\"\n"
                "cat >\"$CAPTURE_STDIN\"\n"
                "printf '%s\\n' TERRAMEDIUM\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            prompt = sandbox / "prompt.txt"
            prompt.write_text("Return exactly TERRAMEDIUM", encoding="utf-8")

            environment = self.make_environment(sandbox, fake_codex)
            environment.update(
                {
                    "ARTICLE_RUN_ID": "terra-medium-contract",
                    "CAPTURE_ARGS": str(args_path),
                    "CAPTURE_STDIN": str(stdin_path),
                }
            )

            result = subprocess.run(
                [str(RUNNER), "judge", "--prompt-file", str(prompt)],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            args = args_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(args[args.index("--model") + 1], "gpt-5.6-terra")
            self.assertIn('model_reasoning_effort="medium"', args)
            self.assertEqual(
                stdin_path.read_text(encoding="utf-8"), "Return exactly TERRAMEDIUM"
            )

    def test_valid_sol_receipt_runs_sol_once_and_replay_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sandbox = Path(temporary)
            args_path = sandbox / "args.txt"
            calls_path = sandbox / "calls.txt"
            fake_codex = sandbox / "codex"
            fake_codex.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$@\" >\"$CAPTURE_ARGS\"\n"
                "printf 'CALL\\n' >>\"$CAPTURE_CALLS\"\n"
                "cat >/dev/null\n"
                "printf '%s\\n' SOLAUDIT\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            prompt = sandbox / "prompt.txt"
            prompt.write_text("Return exactly SOLAUDIT", encoding="utf-8")
            receipt = sandbox / "sol-trigger.json"
            receipt.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "trigger": "quality_sample",
                        "run_id": "sol-contract",
                        "artifact_id": "article-ja",
                        "article_sha256": "a" * 64,
                        "requested_reasoning_effort": "medium",
                    }
                ),
                encoding="utf-8",
            )
            environment = self.make_environment(sandbox, fake_codex)
            environment.update(
                {
                    "ARTICLE_RUN_ID": "sol-contract",
                    "ARTICLE_MODEL_ROLE": "sol-audit",
                    "ARTICLE_SOL_TRIGGER_RECEIPT": str(receipt),
                    "CAPTURE_ARGS": str(args_path),
                    "CAPTURE_CALLS": str(calls_path),
                }
            )

            first = subprocess.run(
                [str(RUNNER), "judge", "--prompt-file", str(prompt)],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            args = args_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(args[args.index("--model") + 1], "gpt-5.6-sol")
            self.assertIn('model_reasoning_effort="medium"', args)
            self.assertTrue(Path(str(receipt) + ".claim/receipt.sha256").is_file())

            replay = subprocess.run(
                [str(RUNNER), "judge", "--prompt-file", str(prompt)],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(replay.returncode, 78, replay.stderr)
            self.assertEqual(calls_path.read_text(encoding="utf-8"), "CALL\n")

    def _capture(
        self, sandbox: Path, mode: str, *, session: bool = False,
    ) -> list[str]:
        args_path = sandbox / f"args-{mode}-{session}.txt"
        fake_codex = sandbox / f"codex-{mode}-{session}"
        fake_codex.write_text(
            "#!/usr/bin/env bash\n"
            'printf "%s\\n" "$@" >"$CAPTURE_ARGS"\n'
            "cat >/dev/null\n"
            "printf 'done\\n'\n",
            encoding="utf-8",
        )
        fake_codex.chmod(0o755)
        prompt = sandbox / "prompt.txt"
        prompt.write_text("p", encoding="utf-8")
        image = sandbox / "image.png"
        image.write_bytes(b"img")
        schema = sandbox / "schema.json"
        schema.write_text("{}", encoding="utf-8")

        environment = self.make_environment(sandbox, fake_codex)
        environment.update({
            "ARTICLE_RUN_ID": "caller-contract",
            "CAPTURE_ARGS": str(args_path),
        })
        if session:
            environment.update({
                "ARTICLE_CODEX_EVENTS_FILE": str(sandbox / "events.jsonl"),
                "ARTICLE_CODEX_LAST_MESSAGE_FILE": str(sandbox / "last.txt"),
                "ARTICLE_CODEX_OUTPUT_SCHEMA": str(schema),
            })
        else:
            for key in (
                "ARTICLE_CODEX_EVENTS_FILE", "ARTICLE_CODEX_LAST_MESSAGE_FILE",
                "ARTICLE_CODEX_OUTPUT_SCHEMA",
            ):
                environment.pop(key, None)
        command = [str(RUNNER), mode, "--prompt-file", str(prompt)]
        if mode == "vision":
            command += ["--image", str(image)]
        result = subprocess.run(
            command, env=environment, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return args_path.read_text(encoding="utf-8").splitlines()

    def test_existing_caller_command_lines_are_unchanged_by_the_repair_mode(
        self,
    ) -> None:
        """Adding a write-capable mode must not move the daily writing, judge,
        or vision paths by a single argv token. Verified against the pre-change
        script on 2026-08-07; frozen here so it cannot drift later."""
        with tempfile.TemporaryDirectory() as temporary:
            sandbox = Path(temporary)
            model = ["--model", "gpt-5.6-terra", "-c", 'model_reasoning_effort="medium"']

            self.assertEqual(
                self._capture(sandbox, "agent"),
                ["exec", "--ephemeral", *model, "--sandbox", "danger-full-access",
                 "-C", str(sandbox / "model-root"), "--ignore-user-config", "--ignore-rules",
                 "--add-dir", os.environ["HOME"], "-"],
            )
            self.assertEqual(
                self._capture(sandbox, "judge"),
                ["exec", "--ephemeral", *model, "--sandbox", "read-only",
                 "-C", str(sandbox / "model-root"),
                 "--ignore-user-config", "--ignore-rules", "-"],
            )
            self.assertEqual(
                self._capture(sandbox, "vision"),
                ["exec", "--ephemeral", *model, "--sandbox", "read-only",
                 "-C", str(sandbox / "model-root"),
                 "--ignore-user-config", "--ignore-rules",
                 "--image", str(sandbox / "image.png"), "-"],
            )
            self.assertEqual(
                self._capture(sandbox, "judge", session=True),
                ["exec", *model, "--sandbox", "read-only",
                 "-C", str(sandbox / "model-root"),
                 "--ignore-user-config", "--ignore-rules",
                 "--json", "-o", str(sandbox / "last.txt"),
                 "--output-schema", str(sandbox / "schema.json"), "-"],
            )

    def test_agent_mode_still_has_no_event_stream_so_repair_needs_its_own_mode(
        self,
    ) -> None:
        """The C1 session surface stays off for `agent`; repair remains separate."""
        with tempfile.TemporaryDirectory() as temporary:
            sandbox = Path(temporary)
            args = self._capture(sandbox, "agent", session=True)
            self.assertNotIn("--json", args)
            self.assertIn("--ephemeral", args)

    def test_agent_workspace_mode_is_confined_to_its_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sandbox = Path(temporary)
            workspace = sandbox / "run"
            workspace.mkdir()
            args_path = sandbox / "args.txt"
            fake_codex = sandbox / "codex"
            fake_codex.write_text(
                "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" >\"$CAPTURE_ARGS\"\n"
                "cat >/dev/null\nprintf 'DONE\\n'\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            prompt = sandbox / "prompt.txt"
            prompt.write_text("draft only", encoding="utf-8")
            environment = self.make_environment(sandbox, fake_codex)
            environment.update({
                "ARTICLE_RUN_ID": "isolated-agent-contract",
                "ARTICLE_RUN_DIR": str(workspace),
                "CAPTURE_ARGS": str(args_path),
            })

            result = subprocess.run(
                [str(RUNNER), "agent-workspace", "--prompt-file", str(prompt)],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            args = args_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(args[args.index("--sandbox") + 1], "workspace-write")
            self.assertEqual(args[args.index("-C") + 1], str(workspace))
            self.assertIn("sandbox_workspace_write.exclude_slash_tmp=true", args)
            self.assertIn("sandbox_workspace_write.exclude_tmpdir_env_var=true", args)
            self.assertIn("sandbox_workspace_write.network_access=false", args)
            self.assertNotIn("--add-dir", args)
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", args)

    def test_sol_rejects_missing_invalid_or_wrong_run_receipt(self) -> None:
        cases = (
            (None, "missing"),
            ({"schema_version": 1, "trigger": "anything"}, "invalid"),
            (
                {
                    "schema_version": 1,
                    "trigger": "legal",
                    "run_id": "other-run",
                    "artifact_id": "article-ja",
                    "article_sha256": "b" * 64,
                    "requested_reasoning_effort": "medium",
                },
                "wrong-run",
            ),
        )
        for payload, label in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                sandbox = Path(temporary)
                calls_path = sandbox / "calls.txt"
                fake_codex = sandbox / "codex"
                fake_codex.write_text(
                    "#!/usr/bin/env bash\nprintf 'CALL\\n' >>\"$CAPTURE_CALLS\"\ncat >/dev/null\n",
                    encoding="utf-8",
                )
                fake_codex.chmod(0o755)
                prompt = sandbox / "prompt.txt"
                prompt.write_text("do not run", encoding="utf-8")
                environment = self.make_environment(sandbox, fake_codex)
                environment.update(
                    {
                        "ARTICLE_RUN_ID": "sol-contract",
                        "ARTICLE_MODEL_ROLE": "sol-audit",
                        "CAPTURE_CALLS": str(calls_path),
                    }
                )
                if payload is not None:
                    receipt = sandbox / "receipt.json"
                    receipt.write_text(json.dumps(payload), encoding="utf-8")
                    environment["ARTICLE_SOL_TRIGGER_RECEIPT"] = str(receipt)
                result = subprocess.run(
                    [str(RUNNER), "judge", "--prompt-file", str(prompt)],
                    env=environment,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 64, result.stderr)
                self.assertFalse(calls_path.exists())


if __name__ == "__main__":
    unittest.main()
