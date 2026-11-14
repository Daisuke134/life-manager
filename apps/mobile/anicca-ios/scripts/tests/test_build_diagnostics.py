"""Execute the workflow's build shell with a fake compiler, never an Apple build."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest


APP = Path(__file__).resolve().parents[2]
WORKFLOW = APP.parents[2] / ".github/workflows/anicca-ios-build.yml"


class BuildDiagnosticsTests(unittest.TestCase):
    def run_build_step(self, compiler_exit):
        source = WORKFLOW.read_text()
        match = re.search(
            r"      - name: Build app \(unsigned\)\n        run: \|\n(.*?)(?=\n      - |\Z)",
            source, re.S,
        )
        self.assertIsNotNone(match)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        compiler = root / "xcodebuild"
        compiler.write_text(textwrap.dedent("""\
            #!/bin/bash
            if [ "$COMPILER_EXIT" != 0 ]; then
              echo 'Fixture.swift:1: error: early stdout diagnostic'
              echo 'Fixture.swift:2: error: early stderr diagnostic' >&2
            fi
            for number in {1..120}; do echo "compile progress $number"; done
            if [ "$COMPILER_EXIT" = 0 ]; then
              echo '** BUILD SUCCEEDED **'
            else
              echo '** BUILD FAILED **'
            fi
            exit "$COMPILER_EXIT"
            """))
        compiler.chmod(0o755)
        env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"],
                   RUNNER_TEMP=str(root), COMPILER_EXIT=str(compiler_exit))
        result = subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", textwrap.dedent(match.group(1))],
            cwd=root, env=env, capture_output=True, text=True, check=False,
        )
        return result, root / "build-output.log"

    def run_unit_test_step(self, compiler_exit):
        source = WORKFLOW.read_text()
        match = re.search(
            r"      - name: Run unit tests \(unsigned\)\n.*?        run: \|\n(.*?)(?=\n      - |\Z)",
            source, re.S,
        )
        self.assertIsNotNone(match)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        tools = root / "bin"
        tools.mkdir()
        simulator = tools / "xcrun"
        simulator.write_text("#!/bin/bash\necho 'iPhone 16 (A1B2C3D4-E5F6-7890-ABCD-EF1234567890) (Shutdown)'\n")
        simulator.chmod(0o755)
        compiler = tools / "xcodebuild"
        compiler.write_text(textwrap.dedent("""\
            #!/bin/bash
            if [ "$COMPILER_EXIT" != 0 ]; then
              echo 'Tests.swift:1: error: early stdout diagnostic'
              echo 'Tests.swift:2: error: early stderr diagnostic' >&2
            fi
            echo 'Test Case SomeTests.testBehavior failed (0.1 seconds)'
            if [ "$COMPILER_EXIT" = 0 ]; then
              echo '** TEST SUCCEEDED **'
            else
              echo '** TEST FAILED **'
            fi
            exit "$COMPILER_EXIT"
            """))
        compiler.chmod(0o755)
        env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"],
                   RUNNER_TEMP=str(root), COMPILER_EXIT=str(compiler_exit))
        result = subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", textwrap.dedent(match.group(1))],
            cwd=root, env=env, capture_output=True, text=True, check=False,
        )
        return result, root / "test-output.log"

    def test_failure_preserves_early_diagnostics_full_log_and_exit_status(self):
        result, log = self.run_build_step(65)
        self.assertEqual(result.returncode, 65, result.stderr)
        self.assertIn("early stdout diagnostic", result.stdout)
        self.assertIn("early stderr diagnostic", result.stdout)
        self.assertIn("** BUILD FAILED **", result.stdout)
        self.assertTrue(log.is_file(), "The build must retain the unabridged compiler log")
        content = log.read_text()
        for line in ("early stdout diagnostic", "early stderr diagnostic",
                     "compile progress 1\n", "compile progress 120\n"):
            self.assertIn(line, content)

    def test_success_stays_successful_when_no_errors_match_grep(self):
        result, log = self.run_build_step(0)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("** BUILD SUCCEEDED **", result.stdout)
        self.assertTrue(log.is_file())
        self.assertIn("compile progress 1\n", log.read_text())

    def test_unit_test_failure_preserves_diagnostics_full_log_and_exit_status(self):
        result, log = self.run_unit_test_step(65)
        self.assertEqual(result.returncode, 65, result.stderr)
        self.assertIn("early stdout diagnostic", result.stdout)
        self.assertIn("early stderr diagnostic", result.stdout)
        self.assertIn("** TEST FAILED **", result.stdout)
        self.assertTrue(log.is_file(), "The unit test must retain the unabridged xcodebuild log")
        content = log.read_text()
        self.assertIn("early stdout diagnostic", content)
        self.assertIn("early stderr diagnostic", content)
        self.assertIn("** TEST FAILED **", content)

    def test_unit_test_success_preserves_log_and_zero_exit_status(self):
        result, log = self.run_unit_test_step(0)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("** TEST SUCCEEDED **", result.stdout)
        self.assertTrue(log.is_file())
        self.assertIn("Test Case SomeTests.testBehavior failed", log.read_text())

    def test_failure_artifact_upload_runs_after_tests_and_contains_both_logs(self):
        source = WORKFLOW.read_text()
        upload = source.index("- name: Preserve full build and unit test logs on failure")
        unit_tests = source.index("- name: Run unit tests (unsigned)")
        self.assertGreater(upload, unit_tests)
        step = source[upload:]
        self.assertIn("if: failure()", step)
        self.assertIn("${{ runner.temp }}/build-output.log", step)
        self.assertIn("${{ runner.temp }}/test-output.log", step)


class NativeModelCoverageTests(unittest.TestCase):
    @staticmethod
    def undefined_quote_provider_members(source, provider_source):
        """Check direct model references only; this does not typecheck Swift."""
        declared = set(re.findall(
            r"\bstatic\s+(?:let|var|func)\s+([A-Za-z_]\w*)", provider_source
        ))
        referenced = set(re.findall(r"\bQuoteProvider\.([A-Za-z_]\w*)", source))
        return referenced - declared

    def test_ci_native_tests_exercise_synthetic_user_and_manager_bench_case(self):
        app_source = APP / "aniccaios/Models"
        tests = APP / "aniccaiosTests"
        synthetic_model = app_source / "SyntheticUser.swift"
        manager_model = app_source / "ManagerBenchCase.swift"
        synthetic_tests = (tests / "SyntheticUserTests.swift").read_text()
        manager_tests = (tests / "ManagerBenchCaseTests.swift").read_text()
        project = (APP / "aniccaios.xcodeproj/project.pbxproj").read_text()

        self.assertTrue(synthetic_model.is_file())
        self.assertTrue(manager_model.is_file())
        self.assertIn("PBXFileSystemSynchronizedRootGroup", project)
        self.assertIn("path = aniccaios;", project)
        self.assertIn("path = aniccaiosTests;", project)
        self.assertIn("8471AE7D2EB783E1002CECAA /* aniccaios */", project)
        self.assertIn("E44CE0012F14A00100000001 /* SyntheticUserTests.swift */", project)
        self.assertIn("E54CE0012F14A00100000001 /* ManagerBenchCaseTests.swift */", project)
        self.assertIn("E44CE0022F14A00100000002 /* SyntheticUserTests.swift in Sources */", project)
        self.assertIn("E54CE0022F14A00100000002 /* ManagerBenchCaseTests.swift in Sources */", project)
        self.assertIn("@testable import aniccaios", synthetic_tests)
        self.assertIn("@testable import aniccaios", manager_tests)
        self.assertRegex(synthetic_tests, r"SyntheticUser\(profile:")
        self.assertIn("LegacySignals(", synthetic_tests)
        self.assertIn("DecisionPointStore(", manager_tests)
        self.assertRegex(manager_tests, r"ManagerBenchCase\.encoder\.encode")

    def test_new_models_only_reference_declared_quote_provider_members(self):
        provider = (APP / "aniccaios/Services/QuoteProvider.swift").read_text()
        models = {
            name: (APP / f"aniccaios/Models/{name}.swift").read_text()
            for name in ("SyntheticUser", "ManagerBenchCase")
        }

        for name, source in models.items():
            self.assertEqual(self.undefined_quote_provider_members(source, provider), set(), name)

        mutated = models["SyntheticUser"].replace(
            "QuoteProvider.goalCategories", "QuoteProvider.dualCategories", 1
        )
        self.assertEqual(
            self.undefined_quote_provider_members(mutated, provider), {"dualCategories"}
        )


class PaywallNativeBuildTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("swiftc"), "Swift compiler not installed")
    def test_production_paywall_helper_compiles_and_passes_existing_truth_table(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = str(Path(directory) / "paywall-selection-tests")
            compiled = subprocess.run([
                "swiftc", "-swift-version", "5",
                str(APP / "aniccaios/Onboarding/PaywallPackageSelection.swift"),
                str(APP / "scripts/tests/PaywallPackageSelectionTests.swift"),
                "-o", executable,
            ], capture_output=True, text=True, check=False)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            tested = subprocess.run([executable], capture_output=True, text=True, check=False)
            self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)
            self.assertIn("native selection regressions passed", tested.stdout)


if __name__ == "__main__":
    unittest.main()
