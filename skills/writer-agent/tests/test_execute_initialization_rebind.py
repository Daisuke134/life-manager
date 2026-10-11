from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "execute-initialization-pair.py"
SPEC = importlib.util.spec_from_file_location("execute_initialization_rebind", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ExecuteInitializationRebindTest(unittest.TestCase):
    def test_missing_old_release_script_rebinds_to_current_writer_release(self) -> None:
        with TemporaryDirectory() as tmp:
            releases = Path(tmp) / "loops" / "releases"
            release = releases / "20260918T000000-deadbeef"
            writer_root = release / "skills" / "writer-agent"
            script = writer_root / "scripts" / "run.sh"
            script.parent.mkdir(parents=True)
            script.write_text("#!/bin/sh\n", encoding="utf-8")
            script.chmod(0o555)
            old = "/old/loops/releases/20260917T221451-98fa0346/skills/writer-agent/scripts/run.sh"

            old_root = os.environ.get("ARTICLE_ROOT")
            os.environ["ARTICLE_ROOT"] = str(writer_root)
            try:
                rebound, changed = MODULE.rebind_missing_writer_argv(["bash", old, "--channel", "note"])
            finally:
                if old_root is None:
                    os.environ.pop("ARTICLE_ROOT", None)
                else:
                    os.environ["ARTICLE_ROOT"] = old_root

            self.assertTrue(changed)
            self.assertEqual(rebound[0], "bash")
            self.assertEqual(rebound[1], str(script.resolve()))
            self.assertEqual(rebound[2:], ["--channel", "note"])

    def test_unknown_missing_script_is_not_rebound(self) -> None:
        with TemporaryDirectory() as tmp:
            writer_root = Path(tmp) / "loops" / "releases" / "20260918T000000-deadbeef" / "skills" / "writer-agent"
            (writer_root / "scripts").mkdir(parents=True)
            old_root = os.environ.get("ARTICLE_ROOT")
            os.environ["ARTICLE_ROOT"] = str(writer_root)
            try:
                argv, changed = MODULE.rebind_missing_writer_argv(["bash", "/old/custom-publisher.sh"])
            finally:
                if old_root is None:
                    os.environ.pop("ARTICLE_ROOT", None)
                else:
                    os.environ["ARTICLE_ROOT"] = old_root

            self.assertFalse(changed)
            self.assertEqual(argv, ["bash", "/old/custom-publisher.sh"])


class MissingDispatchManifestTest(unittest.TestCase):
    """A killed STEP 5 leaves publication-state but no staging row (2026-10-12)."""

    def _run(self, manifest: str | None, child_exit: int | None = None) -> "subprocess.CompletedProcess[str]":
        import json
        import subprocess
        import sys

        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "runs" / "20261011-134916"
            gates = run_dir / "gates"
            gates.mkdir(parents=True)
            state = gates / "publication-state.json"
            state.write_text('{"publication_contract":"active-four","pairs":{}}', encoding="utf-8")
            if child_exit is not None:
                manifest = json.dumps({
                    "platform": "note", "lang": "ja",
                    "argv": [sys.executable, "-c", f"raise SystemExit({child_exit})"],
                    "env": {"ARTICLE_RUN_DIR": str(run_dir), "ARTICLE_PUBLICATION_STATE": str(state),
                            "ARTICLE_LEDGER": str(Path(tmp) / "articles.jsonl")},
                }) + "\n"
            if manifest is not None:
                (gates / "platform-dispatch.jsonl").write_text(manifest, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCRIPT), "--pair", "note/ja", "--run-dir", str(run_dir),
                 "--state", str(state), "--ledger", str(Path(tmp) / "articles.jsonl")],
                capture_output=True, text=True, check=False,
            )

    def test_missing_manifest_is_a_typed_needs_staging_outcome(self) -> None:
        result = self._run(None)
        self.assertEqual(result.returncode, MODULE.NEEDS_STAGING_EXIT, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("dispatch-row-missing", result.stdout + result.stderr)

    def test_manifest_without_pair_row_is_a_typed_needs_staging_outcome(self) -> None:
        result = self._run('{"platform":"substack","lang":"ja","argv":["true"],"env":{}}\n')
        self.assertEqual(result.returncode, MODULE.NEEDS_STAGING_EXIT, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_duplicate_pair_rows_stay_fail_closed(self) -> None:
        row = '{"platform":"note","lang":"ja","argv":["true"],"env":{}}\n'
        result = self._run(row + row)
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected one note/ja manifest row, got 2", result.stderr)

    def test_staging_child_exit_three_never_reads_as_needs_staging(self) -> None:
        result = self._run(None, child_exit=MODULE.NEEDS_STAGING_EXIT)
        self.assertEqual(result.returncode, 1, result.stderr)
