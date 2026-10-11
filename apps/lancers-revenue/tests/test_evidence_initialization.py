import errno
import io
import json
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from test_application_loop_hol import _load_deployed_loop, _opportunity


class EvidenceInitializationTests(unittest.TestCase):
    def test_enospc_during_initialization_stops_before_discovery_or_effects(self):
        for stage in ("reset", "run_mkdir", "run_chmod"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                loop = _load_deployed_loop()
                root = Path(directory) / "evidence"
                root.mkdir()
                sentinel = root / "prior-receipt.json"
                sentinel.write_text("preserve")
                callbacks = {name: Mock(side_effect=AssertionError(name)) for name in
                             ("discoverer", "planner", "safety_verifier", "submitter")}
                private_error = OSError(errno.ENOSPC, "private diagnostic must not escape")
                original_mkdir, original_chmod = Path.mkdir, loop.os.chmod

                def mkdir(path, *args, **kwargs):
                    if path.parent == root and path.name.startswith("run-"):
                        raise private_error
                    return original_mkdir(path, *args, **kwargs)

                def chmod(path, *args, **kwargs):
                    if Path(path).parent == root and Path(path).name.startswith("run-"):
                        raise private_error
                    return original_chmod(path, *args, **kwargs)

                output = io.StringIO()
                with ExitStack() as stack:
                    if stage == "reset":
                        stack.enter_context(patch.object(loop, "_reset", side_effect=private_error))
                    elif stage == "run_mkdir":
                        stack.enter_context(patch.object(Path, "mkdir", new=mkdir))
                    else:
                        stack.enter_context(patch.object(loop.os, "chmod", new=chmod))
                    result = loop.run_loop(
                        state_path=Path(directory) / "application.json",
                        evidence_root=root, output_stream=output, **callbacks,
                    )
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"], "evidence_initialization_failed")
                self.assertFalse(result["submitted"])
                self.assertEqual(json.loads(output.getvalue()), result)
                self.assertNotIn("private diagnostic", output.getvalue())
                for callback in callbacks.values():
                    callback.assert_not_called()
                # Keep the old planner-error retention behavior: no new cleanup on failure.
                self.assertTrue(root.exists())
                if stage == "reset":
                    self.assertEqual(sentinel.read_text(), "preserve")
                elif stage == "run_chmod":
                    self.assertEqual(len(list(root.glob("run-*"))), 1)

    def test_actual_planner_failure_keeps_its_existing_classification(self):
        loop = _load_deployed_loop()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "evidence"
            planner = Mock(side_effect=RuntimeError("model unavailable"))
            submitter = Mock(side_effect=AssertionError("must not submit"))
            result = loop.run_loop(
                state_path=Path(directory) / "application.json", evidence_root=root,
                discoverer=lambda **kwargs: {"ok": True, "opportunities": [_opportunity("6000001")]},
                planner=planner, submitter=submitter,
                clock=lambda: datetime(2026, 8, 13, tzinfo=timezone.utc),
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "planner_runner_failed")
            planner.assert_called_once()
            submitter.assert_not_called()
            self.assertTrue(root.exists())

    def test_successful_initialization_reaches_no_work_result(self):
        loop = _load_deployed_loop()
        with tempfile.TemporaryDirectory() as directory:
            planner = Mock(side_effect=AssertionError("no opportunities"))
            result = loop.run_loop(
                state_path=Path(directory) / "application.json",
                evidence_root=Path(directory) / "evidence",
                discoverer=lambda **kwargs: {"ok": True, "opportunities": []},
                planner=planner,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["reason"], "no_eligible_project")
            planner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
