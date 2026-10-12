"""Read-only contracts for paths verified in Codex's installed startup source."""

import ast
import inspect
from pathlib import Path
import textwrap
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

    def test_reclaimed_preview_keeps_the_eight_entry_overflow_boundary(self) -> None:
        # Inspect the real sweep source without discovery, deletion, mocks, or
        # fabricated candidates. The existing package-cache test now has exactly
        # eight roots; independently retain the overflow accounting contract.
        source = ast.parse(textwrap.dedent(inspect.getsource(HostDiskGovernor.sweep)))
        preview_guards = [
            node for node in ast.walk(source)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and '"reclaimed_candidates"' in ast.unparse(node.test).replace("'", '"')
        ]
        self.assertEqual(len(preview_guards), 1)
        guard = preview_guards[0]
        self.assertEqual(
            ast.dump(guard.test),
            ast.dump(ast.parse('len(result["reclaimed_candidates"]) < 8', mode="eval").body),
        )
        self.assertEqual(len(guard.body), 1)
        self.assertIsInstance(guard.body[0], ast.Expr)
        append = guard.body[0].value
        self.assertIsInstance(append, ast.Call)
        self.assertEqual(
            ast.dump(append.func),
            ast.dump(ast.parse('result["reclaimed_candidates"].append', mode="eval").body),
        )
        self.assertEqual(
            [ast.dump(node) for node in guard.orelse],
            [ast.dump(node) for node in ast.parse(
                'result["reclaimed_candidates_omitted"] += 1'
            ).body],
        )

    def test_pip_download_cache_policy_is_unchanged(self) -> None:
        relative = EXACT_CACHE_ROOTS["pip-cache"]
        self.assertEqual(relative, "Library/Caches/pip")
        self.assertFalse(HostDiskGovernor()._protected(Path.home() / relative))


if __name__ == "__main__":
    unittest.main()
