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
_UNSET = object()


class MergeWhenGreenTests(unittest.TestCase):
    def run_guard(self, workflow, checks="pass", workflow_exit=0, rollup=_UNSET, view_exit=0):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / "gh"
            if rollup is _UNSET:
                fixture_checks = {
                    "pass": {"__typename": "CheckRun", "status": "COMPLETED",
                             "conclusion": "SUCCESS"},
                    "pending": {"__typename": "CheckRun", "status": "IN_PROGRESS",
                                "conclusion": ""},
                    "fail": {"__typename": "CheckRun", "status": "COMPLETED",
                             "conclusion": "FAILURE"},
                    "cancel": {"__typename": "CheckRun", "status": "COMPLETED",
                               "conclusion": "CANCELLED"},
                }
                rollup = [fixture_checks[item] for item in checks.splitlines() if item]
            fake.write_text(f"#!{sys.executable}\n" + '''
import json, os, pathlib, subprocess, sys
args = sys.argv[1:]
if args[:2] == ["pr", "view"]:
    if int(os.environ["FIXTURE_VIEW_EXIT"]):
        sys.exit(int(os.environ["FIXTURE_VIEW_EXIT"]))
    if args[args.index("--json") + 1] != "headRefOid,statusCheckRollup":
        sys.exit(97)
    query = args[args.index("--jq") + 1]
    payload = {"headRefOid": os.environ["FIXTURE_HEAD"],
               "statusCheckRollup": json.loads(os.environ["FIXTURE_ROLLUP"])}
    # Execute the production filter itself; never pre-classify fixtures here.
    result = subprocess.run(["jq", "-r", query], input=json.dumps(payload),
                            capture_output=True, text=True)
    if result.returncode:
        sys.stderr.write(result.stderr)
        sys.exit(result.returncode)
    sys.stdout.write(result.stdout)
elif args[:2] == ["run", "list"]:
    assert args[args.index("--commit") + 1] == os.environ["FIXTURE_HEAD"]
    assert args[args.index("--workflow") + 1] == "sec-scan.yml"
    assert args[args.index("--event") + 1] == "pull_request"
    print(os.environ["FIXTURE_WORKFLOW"])
    sys.exit(int(os.environ["FIXTURE_WORKFLOW_EXIT"]))
elif args[:2] == ["pr", "merge"]:
    pathlib.Path(os.environ["FIXTURE_MERGE"]).write_text(json.dumps(args))
elif args[:2] == ["pr", "checks"]:
    sys.exit(98)
else:
    sys.exit(99)
''')
            fake.chmod(0o755)
            receipt = root / "merge.json"
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"],
                       MERGE_WHEN_GREEN_TRIES="1", MERGE_WHEN_GREEN_POLL="0",
                       FIXTURE_HEAD=HEAD, FIXTURE_WORKFLOW=workflow,
                       FIXTURE_WORKFLOW_EXIT=str(workflow_exit), FIXTURE_CHECKS=checks,
                       FIXTURE_ROLLUP=json.dumps(rollup), FIXTURE_VIEW_EXIT=str(view_exit),
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

    def test_status_rollup_failure_is_not_hidden_by_green_fixture(self):
        rollup = [{"__typename": "CheckRun", "status": "COMPLETED",
                   "conclusion": "FAILURE"}]
        result, merged = self.run_guard(f"{HEAD} completed success", "pass", rollup=rollup)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIsNone(merged)

    def test_empty_and_null_rollups_never_merge(self):
        for rollup in ([], None):
            with self.subTest(rollup=rollup):
                result, merged = self.run_guard(f"{HEAD} completed success", rollup=rollup)
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIsNone(merged)

    def test_neutral_skipped_and_success_status_context_are_green(self):
        rollup = [
            {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "NEUTRAL"},
            {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SKIPPED"},
            {"__typename": "StatusContext", "state": "SUCCESS"},
        ]
        result, merged = self.run_guard(f"{HEAD} completed success", rollup=rollup)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNotNone(merged)

    def test_unknown_rollup_type_and_pr_read_error_never_merge(self):
        result, merged = self.run_guard(
            f"{HEAD} completed success", rollup=[{"__typename": "Unknown"}])
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIsNone(merged)

        result, merged = self.run_guard(f"{HEAD} completed success", view_exit=1)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIsNone(merged)


if __name__ == "__main__":
    unittest.main()
