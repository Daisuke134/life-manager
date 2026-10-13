import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import gen_examples  # noqa: E402


class GenExamplesRunnerTest(unittest.TestCase):
    def test_requests_json_string_contract_and_unwraps_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = root / "runner"
            schema_record = root / "schema.json"
            runner.write_text(
                "#!/bin/sh\n"
                "cat \"$ARTICLE_CODEX_OUTPUT_SCHEMA\" > \"$SCHEMA_RECORD\"\n"
                "printf '{\"text\":\"plain output\"}'\n",
                encoding="utf-8",
            )
            runner.chmod(runner.stat().st_mode | stat.S_IXUSR)
            old = {
                key: os.environ.get(key)
                for key in ("ARTICLE_MODEL_RUNNER", "SCHEMA_RECORD")
            }
            try:
                os.environ["ARTICLE_MODEL_RUNNER"] = str(runner)
                os.environ["SCHEMA_RECORD"] = str(schema_record)
                result = gen_examples._claude("return a plain example")
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            self.assertEqual(result, "plain output")
            self.assertEqual(
                json.loads(schema_record.read_text(encoding="utf-8")),
                {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
            )

    def test_uses_house_runner_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "catalog"
            (catalog / "evidence").mkdir(parents=True)
            (catalog / "SKILL.md").write_text("Write natural English output.", encoding="utf-8")
            (catalog / "evidence" / "verified-demonstration.md").write_text(
                "## Concrete input\n```text\nfirst\n```\n## Actual output\nfirst output\n",
                encoding="utf-8",
            )
            runner = root / "runner"
            record = root / "record.json"
            runner.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$PWD\" >> \"$RUNNER_RECORD\"\n"
                "printf '%s\\n' \"$1 $2 $3 $4\" >> \"$RUNNER_RECORD\"\n"
                "cat \"$3\" >> \"$RUNNER_RECORD\"\n"
                "if grep -q 'Write 3 NEW' \"$3\"; then printf '[\"input two\",\"input three\",\"input four\"]'; else printf 'output-%s' \"$(basename \"$3\")\"; fi\n",
                encoding="utf-8",
            )
            runner.chmod(runner.stat().st_mode | stat.S_IXUSR)
            old = {k: os.environ.get(k) for k in ("ARTICLE_MODEL_RUNNER", "RUNNER_RECORD")}
            try:
                os.environ["ARTICLE_MODEL_RUNNER"] = str(runner)
                os.environ["RUNNER_RECORD"] = str(record)
                gen_examples.EXAMPLES_DIR = root / "state"
                result = gen_examples.generate(catalog)
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            self.assertEqual(len(result), 4)
            self.assertEqual(Path(record.read_text(encoding="utf-8").splitlines()[0]).resolve(), Path("/tmp").resolve())
            recorded = record.read_text(encoding="utf-8")
            self.assertIn("agent --prompt-file", recorded)
            self.assertIn("## SYSTEM INSTRUCTIONS\nWrite natural English output.", recorded)
            self.assertIn("## BUYER PROMPT\nHere is a skill a buyer uses:", recorded)
            self.assertEqual(result[1]["output"].startswith("output-"), True)

    def test_resumes_completed_examples_after_provider_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "catalog"
            (catalog / "evidence").mkdir(parents=True)
            (catalog / "SKILL.md").write_text("Write natural English output.", encoding="utf-8")
            (catalog / "evidence" / "verified-demonstration.md").write_text(
                "## Concrete input\n```text\nfirst\n```\n## Actual output\nfirst output\n",
                encoding="utf-8",
            )
            runner = root / "runner"
            calls = root / "calls"
            failed_once = root / "failed-once"
            runner.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "calls = Path(os.environ['RUNNER_CALLS'])\n"
                "count = int(calls.read_text()) + 1 if calls.exists() else 1\n"
                "calls.write_text(str(count))\n"
                "prompt = Path(sys.argv[3]).read_text()\n"
                "if 'Write 3 NEW realistic buyer inputs' in prompt:\n"
                "    print(json.dumps(['request two', 'request three', 'request four']))\n"
                "elif count == 3 and not Path(os.environ['FAIL_ONCE']).exists():\n"
                "    Path(os.environ['FAIL_ONCE']).write_text('failed')\n"
                "    print('transient_quota', file=sys.stderr)\n"
                "    raise SystemExit(75)\n"
                "else:\n"
                "    buyer = prompt.rsplit('## BUYER PROMPT\\n', 1)[1].strip()\n"
                "    print(json.dumps({'text': 'output for ' + buyer}))\n",
                encoding="utf-8",
            )
            runner.chmod(runner.stat().st_mode | stat.S_IXUSR)
            saved_env = {
                key: os.environ.get(key)
                for key in ("ARTICLE_MODEL_RUNNER", "RUNNER_CALLS", "FAIL_ONCE")
            }
            original_examples_dir = gen_examples.EXAMPLES_DIR
            state = root / "state"
            try:
                os.environ["ARTICLE_MODEL_RUNNER"] = str(runner)
                os.environ["RUNNER_CALLS"] = str(calls)
                os.environ["FAIL_ONCE"] = str(failed_once)
                gen_examples.EXAMPLES_DIR = state

                with self.assertRaises(subprocess.CalledProcessError):
                    gen_examples.generate(catalog)

                progress = state / "catalog.partial.json"
                self.assertTrue(progress.exists())
                self.assertEqual(len(json.loads(progress.read_text())["examples"]), 2)

                examples = gen_examples.generate(catalog)

                self.assertEqual(int(calls.read_text()), 5)
                self.assertEqual(len(examples), 4)
                self.assertEqual(len({example["output"] for example in examples}), 4)
                self.assertFalse(progress.exists())
                self.assertTrue((state / "catalog.json").exists())
            finally:
                gen_examples.EXAMPLES_DIR = original_examples_dir
                for key, value in saved_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_rejects_cached_examples_without_four_distinct_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            catalog = Path(tmp) / "catalog"
            state.mkdir()
            (catalog / "evidence").mkdir(parents=True)
            (catalog / "SKILL.md").write_text("Write natural English output.", encoding="utf-8")
            (catalog / "evidence" / "verified-demonstration.md").write_text(
                "## Concrete input\n```text\nverified request\n```\n## Actual output\nverified output\n",
                encoding="utf-8",
            )
            target = state / "catalog.json"
            original_examples_dir = gen_examples.EXAMPLES_DIR
            invalid_caches = [
                [{"input": "request", "output": f"output {index}"} for index in range(3)],
                [
                    {"input": "request one", "output": "duplicate"},
                    {"input": "request two", "output": "duplicate"},
                    {"input": "request three", "output": "output three"},
                    {"input": "request four", "output": "output four"},
                ],
                [
                    {"input": "verified request", "output": "verified output"},
                    {"input": "same request", "output": "output one"},
                    {"input": "same request", "output": "output two"},
                    {"input": "same request", "output": "output three"},
                ],
                [
                    {"input": "stale request", "output": "stale output"},
                    {"input": "request two", "output": "output two"},
                    {"input": "request three", "output": "output three"},
                    {"input": "request four", "output": "output four"},
                ],
            ]
            try:
                gen_examples.EXAMPLES_DIR = state
                for examples in invalid_caches:
                    with self.subTest(example_count=len(examples)):
                        target.write_text(json.dumps(examples), encoding="utf-8")
                        with self.assertRaisesRegex(RuntimeError, "examples_cache_invalid"):
                            gen_examples.generate(catalog)
            finally:
                gen_examples.EXAMPLES_DIR = original_examples_dir

    def test_reuses_valid_complete_cache_without_provider_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state"
            catalog = root / "catalog"
            (catalog / "evidence").mkdir(parents=True)
            (catalog / "SKILL.md").write_text("Write natural English output.", encoding="utf-8")
            (catalog / "evidence" / "verified-demonstration.md").write_text(
                "## Concrete input\n```text\nverified request\n```\n## Actual output\nverified output\n",
                encoding="utf-8",
            )
            examples = [
                {"input": "verified request", "output": "verified output"},
                {"input": "request two", "output": "output two"},
                {"input": "request three", "output": "output three"},
                {"input": "request four", "output": "output four"},
            ]
            state.mkdir()
            (state / "catalog.json").write_text(json.dumps(examples), encoding="utf-8")
            original_examples_dir = gen_examples.EXAMPLES_DIR
            original_claude = gen_examples._claude
            try:
                gen_examples.EXAMPLES_DIR = state
                gen_examples._claude = lambda *_args, **_kwargs: self.fail("provider call on valid cache")
                self.assertEqual(gen_examples.generate(catalog), examples)
            finally:
                gen_examples.EXAMPLES_DIR = original_examples_dir
                gen_examples._claude = original_claude

    def test_rejects_bracketed_input_in_progress_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state"
            catalog = root / "catalog"
            (catalog / "evidence").mkdir(parents=True)
            (catalog / "SKILL.md").write_text("Write natural English output.", encoding="utf-8")
            (catalog / "evidence" / "verified-demonstration.md").write_text(
                "## Concrete input\n```text\nverified request\n```\n## Actual output\nverified output\n",
                encoding="utf-8",
            )
            state.mkdir()
            (state / "catalog.partial.json").write_text(
                json.dumps({
                    "schema_version": 1,
                    "inputs": ["request [one]", "request two", "request three"],
                    "examples": [{"input": "verified request", "output": "verified output"}],
                }),
                encoding="utf-8",
            )
            original_examples_dir = gen_examples.EXAMPLES_DIR
            original_claude = gen_examples._claude
            try:
                gen_examples.EXAMPLES_DIR = state
                gen_examples._claude = lambda *_args, **_kwargs: self.fail("provider call on invalid progress")
                with self.assertRaisesRegex(RuntimeError, "examples_progress_invalid"):
                    gen_examples.generate(catalog)
            finally:
                gen_examples.EXAMPLES_DIR = original_examples_dir
                gen_examples._claude = original_claude


if __name__ == "__main__":
    unittest.main()
