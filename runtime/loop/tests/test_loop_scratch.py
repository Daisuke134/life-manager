"""Per-run scratch is isolated without pre-admission recursive cleanup."""

import tempfile
import unittest
import os
from unittest import mock
from pathlib import Path

from runtime.loop.loop_cleanup import remove_owned_tree
from runtime.loop.lm_loop_run import reset_loop_scratch


class LoopScratchTest(unittest.TestCase):
    def test_creates_isolated_run_without_touching_leftovers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            stale = state / "loop-tmp/capafy-ig-marketing-daily/old/npm-cache"
            stale.mkdir(parents=True)
            (stale / "blob.bin").write_bytes(b"x" * 1024)
            scratch, parent_fd, run_fd = reset_loop_scratch(
                state, "capafy-ig-marketing-daily", "run-2")
            self.assertEqual(
                scratch, state.resolve() / "loop-tmp/capafy-ig-marketing-daily/run-2")
            self.assertEqual(
                sorted(item.name for item in scratch.iterdir()),
                [".owner.json", ".terminal-unrecorded"])
            self.assertEqual(scratch.stat().st_mode & 0o777, 0o700)
            self.assertTrue((stale / "blob.bin").is_file())
            os.close(run_fd)
            os.close(parent_fd)

    def test_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            for run_id in ["/tmp/outside", "../outside", "..", "a/b"]:
                with self.subTest(run_id=run_id), self.assertRaisesRegex(
                        ValueError, "unsafe run id"):
                    reset_loop_scratch(state, "job", run_id)

    def test_rejects_reused_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            _, parent_fd, run_fd = reset_loop_scratch(state, "job", "same-run")
            try:
                with self.assertRaises(FileExistsError):
                    reset_loop_scratch(state, "job", "same-run")
            finally:
                os.close(run_fd)
                os.close(parent_fd)

    def test_rejects_symlinked_loop_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            state, outside = base / "state", base / "outside"
            outside.mkdir()
            loop_tmp = state / "loop-tmp"
            loop_tmp.mkdir(parents=True)
            (loop_tmp / "job").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "unsafe loop scratch root"):
                reset_loop_scratch(state, "job", "safe-run")
            self.assertFalse((outside / "safe-run").exists())

    def test_fails_closed_when_process_identity_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch(
                "runtime.loop.lm_loop_run.process_start", return_value=None):
            state = Path(directory) / "state"
            with self.assertRaisesRegex(RuntimeError, "identity unavailable"):
                reset_loop_scratch(state, "job", "safe-run")
            self.assertFalse((state / "loop-tmp/job/safe-run").exists())

    def test_cleanup_uses_creation_time_parent_after_ancestor_swap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            state = base / "state"
            scratch, parent_fd, run_fd = reset_loop_scratch(state, "job", "safe-run")
            loop_dir = scratch.parent
            original = loop_dir.with_name("job-original")
            loop_dir.rename(original)
            outside = base / "outside"
            outside_run = outside / "safe-run"
            outside_run.mkdir(parents=True)
            sentinel = outside_run / "sentinel"
            sentinel.write_text("keep")
            loop_dir.symlink_to(outside, target_is_directory=True)
            try:
                self.assertTrue(remove_owned_tree(parent_fd, run_fd, "safe-run"))
            finally:
                os.close(run_fd)
                os.close(parent_fd)
            self.assertFalse((original / "safe-run").exists())
            self.assertTrue(sentinel.is_file())

    def test_cleanup_preserves_replacement_with_same_run_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            scratch, parent_fd, run_fd = reset_loop_scratch(
                state, "job", "safe-run")
            moved = scratch.with_name("original-run")
            scratch.rename(moved)
            scratch.mkdir()
            sentinel = scratch / "sentinel"
            sentinel.write_text("keep")
            try:
                self.assertFalse(remove_owned_tree(parent_fd, run_fd, "safe-run"))
            finally:
                os.close(run_fd)
                os.close(parent_fd)
            preserved = next(scratch.parent.glob("safe-run.gc-trash.*"))
            self.assertTrue((preserved / "sentinel").is_file())
            self.assertTrue(moved.is_dir())

    def test_creation_rejects_loop_tmp_swapped_before_open(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            state = base / "state"
            outside = base / "outside"
            outside.mkdir()
            original_open = os.open
            swapped = False

            def swap_then_open(path, flags, *args, **kwargs):
                nonlocal swapped
                if path == "loop-tmp" and kwargs.get("dir_fd") is not None and not swapped:
                    swapped = True
                    loop_tmp = state / "loop-tmp"
                    loop_tmp.rename(state / "loop-tmp-original")
                    loop_tmp.symlink_to(outside, target_is_directory=True)
                return original_open(path, flags, *args, **kwargs)

            with mock.patch("runtime.loop.lm_loop_run.os.open",
                            side_effect=swap_then_open), self.assertRaises(OSError):
                reset_loop_scratch(state, "job", "safe-run")
            self.assertFalse((outside / "job/safe-run").exists())

    def test_creation_fails_closed_if_protection_marker_cannot_persist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            original_open = os.open

            def fail_marker(path, flags, *args, **kwargs):
                if path == ".terminal-unrecorded":
                    raise OSError("marker unavailable")
                return original_open(path, flags, *args, **kwargs)

            with mock.patch("runtime.loop.lm_loop_run.os.open", side_effect=fail_marker), \
                    self.assertRaisesRegex(OSError, "marker unavailable"):
                reset_loop_scratch(state, "job", "safe-run")
            self.assertFalse((state / "loop-tmp/job/safe-run").exists())

    def test_creation_rejects_run_replaced_before_first_open(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            original_open = os.open
            swapped = False

            def swap_then_open(path, flags, *args, **kwargs):
                nonlocal swapped
                if path == "safe-run" and kwargs.get("dir_fd") is not None and not swapped:
                    swapped = True
                    run = state / "loop-tmp/job/safe-run"
                    run.rename(run.with_name("created-run"))
                    run.mkdir()
                    (run / "sentinel").write_text("keep")
                return original_open(path, flags, *args, **kwargs)

            with mock.patch("runtime.loop.lm_loop_run.os.open",
                            side_effect=swap_then_open), self.assertRaisesRegex(
                                RuntimeError, "inode changed"):
                reset_loop_scratch(state, "job", "safe-run")
            self.assertTrue((state / "loop-tmp/job/safe-run/sentinel").is_file())
            self.assertTrue((state / "loop-tmp/job/created-run").is_dir())


if __name__ == "__main__":
    unittest.main()
