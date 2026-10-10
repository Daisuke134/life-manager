#!/usr/bin/env python3
"""Pure helpers of threads_publish (no browser): reading post codes and spotting the new one."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import threads_publish  # noqa: E402


class PostCodes(unittest.TestCase):
    def test_codes_are_read_only_from_the_handles_own_posts(self) -> None:
        html = ('<a href="/@stardust_doubutsu/post/AbC_1-x">' '<a href="/@someone_else/post/ZZZ">'
                '<a href="/@stardust_doubutsu/post/AbC_1-x/media">')
        self.assertEqual(threads_publish.post_codes(html, "stardust_doubutsu"), {"AbC_1-x"})

    def test_the_new_post_is_the_code_that_was_not_there_before(self) -> None:
        self.assertEqual(threads_publish.new_post_code({"A", "B"}, {"A", "B", "C"}), "C")

    def test_no_new_post_or_an_ambiguous_one_is_none(self) -> None:
        self.assertIsNone(threads_publish.new_post_code({"A"}, {"A"}))
        self.assertIsNone(threads_publish.new_post_code({"A"}, {"A", "B", "C"}))


if __name__ == "__main__":
    unittest.main()
