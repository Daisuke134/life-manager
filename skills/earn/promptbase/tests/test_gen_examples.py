import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import gen_examples  # noqa: E402


class GenExamplesRunnerTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
