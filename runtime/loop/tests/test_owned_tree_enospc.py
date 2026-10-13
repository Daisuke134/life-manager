import errno
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from runtime.loop import loop_cleanup
from runtime.loop import central_cleanup


class OwnedTreeEnospcTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.run = self.parent / "closed-run"
        (self.run / "nested").mkdir(parents=True)
        (self.run / "nested/payload").write_text("regenerable")
        (self.run / ".owner.json").write_text('{"effect_class":"none"}')
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        self.parent_fd = os.open(self.parent, flags)
        self.run_fd = os.open(self.run, flags)
        self.addCleanup(os.close, self.parent_fd)
        self.addCleanup(os.close, self.run_fd)

    def remove(self):
        try:
            return loop_cleanup.remove_owned_tree(
                self.parent_fd, self.run_fd, self.run.name)
        except OSError as error:
            if error.errno == errno.ENOSPC:
                self.fail("ENOSPC during rename blocks confirmed-owned scratch cleanup")
            raise

    def test_full_filesystem_reclaims_opened_tree_without_following_symlink(self):
        outside = self.parent / "outside"
        outside.mkdir()
        (outside / "keep").write_text("authoritative")
        (self.run / "link").symlink_to(outside, target_is_directory=True)
        with mock.patch.object(loop_cleanup.os, "replace",
                               side_effect=OSError(errno.ENOSPC, "full")):
            self.assertEqual(self.remove(), "contents_reclaimed")
        self.assertEqual({p.name for p in self.run.iterdir()}, {".owner.json"})
        self.assertEqual((outside / "keep").read_text(), "authoritative")
        self.assertTrue(self.remove())
        self.assertFalse(self.run.exists())

    def test_replacement_before_fallback_preserves_both_trees(self):
        detached = self.parent / "detached"

        def replace(*_args, **_kwargs):
            os.rename(self.run, detached)
            self.run.mkdir()
            (self.run / "keep").write_text("different owner")
            raise OSError(errno.ENOSPC, "full")

        with mock.patch.object(loop_cleanup.os, "replace", side_effect=replace):
            self.assertFalse(self.remove())
        self.assertEqual((self.run / "keep").read_text(), "different owner")
        self.assertEqual((detached / "nested/payload").read_text(), "regenerable")

    def test_replacement_during_clear_never_removes_different_owner(self):
        original_clear = loop_cleanup._clear_owned_directory
        detached = self.parent / "detached"

        def clear(fd, **kwargs):
            result = original_clear(fd, **kwargs)
            if os.fstat(fd).st_ino == os.fstat(self.run_fd).st_ino:
                os.rename(self.run, detached)
                self.run.mkdir()
                (self.run / "keep").write_text("different owner")
            return result

        with mock.patch.object(loop_cleanup.os, "replace",
                               side_effect=OSError(errno.ENOSPC, "full")), \
                mock.patch.object(loop_cleanup, "_clear_owned_directory", side_effect=clear):
            self.assertFalse(self.remove())
        self.assertEqual((self.run / "keep").read_text(), "different owner")
        self.assertTrue(detached.is_dir())

    def test_other_rename_errors_preserve_the_tree(self):
        with mock.patch.object(loop_cleanup.os, "replace",
                               side_effect=OSError(errno.EACCES, "denied")):
            with self.assertRaises(PermissionError):
                self.remove()
        self.assertEqual((self.run / "nested/payload").read_text(), "regenerable")

    def test_replacement_after_last_stat_keeps_different_empty_directory(self):
        original_stat = os.stat
        detached = self.parent / "detached"
        replaced = False

        def stat(path, *args, **kwargs):
            nonlocal replaced
            result = original_stat(path, *args, **kwargs)
            if path == self.run.name and kwargs.get("dir_fd") == self.parent_fd and not replaced:
                replaced = True
                os.rename(self.run, detached)
                self.run.mkdir()
            return result

        with mock.patch.object(loop_cleanup.os, "replace",
                               side_effect=OSError(errno.ENOSPC, "full")), \
                mock.patch.object(loop_cleanup.os, "stat", side_effect=stat):
            self.remove()
        self.assertTrue(self.run.is_dir(), "a different owner directory was removed")

    def test_central_sweep_reports_partial_reclaim_then_finishes_and_replays_zero(self):
        root = self.parent / "state-root"
        run = root / "loop-tmp/job/run"
        run.mkdir(parents=True)
        (run / ".owner.json").write_text(json.dumps({
            "pid": 11, "process_start": "closed-start", "effect_class": "none"}))
        (run / "payload").write_text("regenerable")
        (root / "events.jsonl").write_text(json.dumps({
            "loop_id": "job", "run_id": "run", "effect_class": "none",
            "effect_status": "not_applicable", "occurrence_id": "job:run",
            "release_sha": "a" * 40}) + "\n")

        def sweep():
            return central_cleanup.scratch_gc(
                {root}, starts={}, snapshot_started_ns=time.time_ns() + 1,
                no_effect_loop_ids={"job"})

        with mock.patch.object(loop_cleanup.os, "replace",
                               side_effect=OSError(errno.ENOSPC, "full")):
            first = sweep()
        self.assertEqual((first["contents_reclaimed"], first["removed"],
                          first["preserved"], first["errors"]), (1, 0, 1, 0))
        self.assertEqual({p.name for p in run.iterdir()}, {".owner.json"})
        second = sweep()
        self.assertEqual((second["removed"], second["errors"]), (1, 0))
        self.assertFalse(run.exists())
        self.assertTrue((root / "events.jsonl").exists())
        self.assertEqual(sweep()["removed"], 0)


if __name__ == "__main__":
    unittest.main()
