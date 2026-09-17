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
