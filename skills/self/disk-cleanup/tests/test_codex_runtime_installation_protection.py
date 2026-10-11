"""Read-only contracts for paths verified in Codex's installed startup source."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1]))
from disk_cleanup import EXACT_CACHE_ROOTS, HostDiskGovernor  # noqa: E402


class CodexRuntimeInstallationProtectionTests(unittest.TestCase):
    def test_runtime_installation_root_is_protected(self) -> None:
        root = Path.home() / ".cache/codex-runtimes"
        self.assertTrue(HostDiskGovernor()._protected(root))

    def test_primary_runtime_executables_and_metadata_are_protected(self) -> None:
        root = Path.home() / ".cache/codex-runtimes/codex-primary-runtime"
        governor = HostDiskGovernor()
        # Actual primary-runtime layout and app-tools Node launcher paths.
        for relative in (
            "runtime.json",
            "dependencies/node/bin/node",
            "dependencies/python/bin/python3",
        ):
            with self.subTest(relative=relative):
                self.assertTrue(governor._protected(root / relative))

    def test_runtime_installation_is_not_an_exact_cache_candidate(self) -> None:
        self.assertNotIn("codex-runtime-cache", EXACT_CACHE_ROOTS)
        self.assertNotIn(".cache/codex-runtimes", EXACT_CACHE_ROOTS.values())

    def test_pip_download_cache_policy_is_unchanged(self) -> None:
        relative = EXACT_CACHE_ROOTS["pip-cache"]
        self.assertEqual(relative, "Library/Caches/pip")
        self.assertFalse(HostDiskGovernor()._protected(Path.home() / relative))


if __name__ == "__main__":
    unittest.main()
