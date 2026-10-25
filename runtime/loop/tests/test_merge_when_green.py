from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[3] / "bin/merge-when-green"
HEAD = "a" * 40


class MergeWhenGreenTests(unittest.TestCase):
    def run_guard(self, workflow, checks="pass", workflow_exit=0):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / "gh"
            fake.write_text(f"#!{sys.executable}\n" + '''
import json, os, pathlib, sys
args = sys.argv[1:]
if args[:2] == ["pr", "view"]:
    query = args[args.index("--json") + 1]
    if query == "headRefOid,statusCheckRollup":
        checks = os.environ["FIXTURE_CHECKS"].splitlines()
        if not checks:
            state = "none"
        elif any(check not in {"pass", "pending"} for check in checks):
            state = "fail"
        elif "pending" in checks:
            state = "pending"
        else:
            state = "green"
        print(os.environ["FIXTURE_HEAD"] + "\\t" + state)
    else:
        print(os.environ["FIXTURE_HEAD"])
elif args[:2] == ["run", "list"]:
    assert args[args.index("--commit") + 1] == os.environ["FIXTURE_HEAD"]
    assert args[args.index("--workflow") + 1] == "sec-scan.yml"
    assert args[args.index("--event") + 1] == "pull_request"
    print(os.environ["FIXTURE_WORKFLOW"])
    sys.exit(int(os.environ["FIXTURE_WORKFLOW_EXIT"]))
elif args[:2] == ["pr", "merge"]:
    pathlib.Path(os.environ["FIXTURE_MERGE"]).write_text(json.dumps(args))
else:
    sys.exit(99)
''')
            fake.chmod(0o755)
            receipt = root / "merge.json"
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"],
                       MERGE_WHEN_GREEN_TRIES="1", MERGE_WHEN_GREEN_POLL="0",
                       FIXTURE_HEAD=HEAD, FIXTURE_WORKFLOW=workflow,
                       FIXTURE_WORKFLOW_EXIT=str(workflow_exit), FIXTURE_CHECKS=checks,
                       FIXTURE_MERGE=str(receipt))
            result = subprocess.run(["bash", str(SCRIPT), "123", "--admin", "--merge"],
                                    cwd=root, env=env, capture_output=True, text=True, timeout=5)
            merged = json.loads(receipt.read_text()) if receipt.exists() else None
            return result, merged

    def test_unregistered_or_unfinished_workflow_never_merges_coderabbit_only(self):
        for state in ["", f"{HEAD} queued ", f"{HEAD} in_progress "]:
            with self.subTest(state=state):
                result, merged = self.run_guard(state)
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIsNone(merged)

    def test_wrong_head_and_failed_workflow_read_never_merge(self):
        for state, code in [("b" * 40 + " completed success", 0),
                            (f"{HEAD} completed success", 1)]:
            with self.subTest(state=state, code=code):
                result, merged = self.run_guard(state, workflow_exit=code)
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIsNone(merged)

    def test_failed_or_cancelled_workflow_never_merges(self):
        for conclusion in ["failure", "cancelled", "timed_out", "neutral", "skipped"]:
            with self.subTest(conclusion=conclusion):
                result, merged = self.run_guard(f"{HEAD} completed {conclusion}")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIsNone(merged)

    def test_existing_check_pending_failure_and_cancel_protection_remains(self):
        for checks, code in [("pass\npending", 3), ("pass\nfail", 2), ("pass\ncancel", 2)]:
            with self.subTest(checks=checks):
                result, merged = self.run_guard(f"{HEAD} completed success", checks)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertIsNone(merged)

    def test_exact_head_workflow_and_all_checks_success_merge_the_pinned_head(self):
        result, merged = self.run_guard(f"{HEAD} completed success", "pass\npass")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(merged, ["pr", "merge", "123", "--admin", "--merge",
                                  "--match-head-commit", HEAD])


if __name__ == "__main__":
    unittest.main()
