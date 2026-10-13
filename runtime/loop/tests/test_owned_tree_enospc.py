import errno
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from runtime.loop import loop_cleanup


class OwnedTreeEnospcTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.run = self.parent / "closed-run"
        (self.run / "nested").mkdir(parents=True)
        (self.run / "nested/payload").write_text("regenerable")
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
            self.assertTrue(self.remove())
        self.assertFalse(self.run.exists())
        self.assertEqual((outside / "keep").read_text(), "authoritative")

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

        def clear(fd):
            result = original_clear(fd)
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


if __name__ == "__main__":
    unittest.main()
