"""Read-only checks of the real browser dependency paths; never run cleanup."""

from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1]))
from disk_cleanup import EXACT_CACHE_ROOTS, HostDiskGovernor  # noqa: E402


class BrowserInstallationProtectionTests(unittest.TestCase):
    def test_camoufox_sdk_installation_is_protected(self) -> None:
        root = Path.home() / "Library/Caches/camoufox"
        governor = HostDiskGovernor()

        self.assertTrue(governor._protected(root))
        self.assertTrue(governor._protected(root / "version.json"))
        self.assertNotIn("camoufox-sdk-cache", EXACT_CACHE_ROOTS)

    def test_pinned_camofox_installation_is_protected(self) -> None:
        fetch = Path(__file__).resolve().parents[3] / "camofox-browser/fetch.sh"
        commit = re.search(r'^COMMIT="([0-9a-f]{40})"$', fetch.read_text(), re.M)
        self.assertIsNotNone(commit)
        root = Path.home() / ".cache/life-manager/camofox-browser"
        governor = HostDiskGovernor()

        self.assertTrue(governor._protected(root))
        self.assertTrue(governor._protected(root / commit.group(1) / "archive.tar.gz"))
        self.assertNotIn("camofox-browser-cache", EXACT_CACHE_ROOTS)

    def test_other_exact_runtime_cache_is_unchanged(self) -> None:
        relative = EXACT_CACHE_ROOTS["codex-runtime-cache"]
        self.assertEqual(relative, ".cache/codex-runtimes")
        self.assertFalse(HostDiskGovernor()._protected(Path.home() / relative))


if __name__ == "__main__":
    unittest.main()
