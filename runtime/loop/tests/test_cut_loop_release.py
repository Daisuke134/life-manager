import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEPENDENCY_ROOTS = (
    Path("."),
    Path("runtime/compute-proxy"),
    Path("runtime/agentmail"),
    Path("apps/life-manager"),
    Path("skills/earn/x402-sell"),
    Path("services/x402-endpoint"),
)


class CutLoopReleaseTest(unittest.TestCase):
    def test_release_builds_immutable_bytecode_for_its_runtime_python(self):
        with tempfile.TemporaryDirectory() as directory:
            loops = Path(directory) / "loops"
            result = subprocess.run(
                ["/bin/bash", str(ROOT / "bin/cut-loop-release.sh"), "origin/main"],
                cwd=ROOT,
                env={
                    **os.environ,
                    "LOOPS_ROOT": str(loops),
                    "LOOPS_RELEASE_PATHS": "runtime",
                    "LOOPS_ACTIVATE_CURRENT": "0",
                    "LIFE_MANAGER_DISK_PRESSURE_FILE": str(Path(directory) / "no-pressure"),
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            release = next((loops / "releases").iterdir())
            manifest = json.loads((release / "RELEASE.json").read_text())
            runtime_python = Path(manifest["runtime_python"])
            tag = manifest["runtime_python_cache_tag"]
            caches = list(release.glob(f"runtime/**/__pycache__/*.{tag}.pyc"))
            self.assertTrue(caches)
            self.assertEqual(int.from_bytes(caches[0].read_bytes()[4:8], "little"), 3)
            self.assertFalse(release.stat().st_mode & 0o200)
            self.assertTrue(runtime_python.is_absolute() and os.access(runtime_python, os.X_OK))
            actual_tag = subprocess.check_output(
                [str(runtime_python), "-c", "import sys; print(sys.implementation.cache_tag)"],
                text=True,
            ).strip()
            self.assertEqual(tag, actual_tag)

    def test_connector_sparse_release_includes_shared_browser_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            loops = root / "loops"
            agents = root / "agents"
            agents.mkdir()
            npm = root / "npm"
            npm.write_text("#!/bin/sh\nmkdir -p node_modules\nprintf '{}\\n' > node_modules/.package-lock.json\n")
            npm.chmod(0o755)

            result = subprocess.run(
                ["/bin/bash", str(ROOT / "bin/cut-loop-release.sh"), "origin/main"],
                cwd=ROOT,
                env={
                    **os.environ,
                    "LOOPS_ROOT": str(loops),
                    "LOOPS_RELEASE_PATHS": "bin config runtime/loop runtime/agent-runner skills/_shared skills/connector apps/life-manager",
                    "LOOPS_ACTIVATE_CURRENT": "0",
                    "LIFE_MANAGER_LAUNCH_AGENTS_DIR": str(agents),
                    "LIFE_MANAGER_DISK_PRESSURE_FILE": str(root / "no-pressure"),
                    "NPM_BIN": str(npm),
                    "NPM_VERSION": "test",
                    "NPM_NODE_VERSION": "test",
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            release = next((loops / "releases").iterdir())
            self.assertTrue((release / "runtime/browser/target-lease.cjs").is_file())

    def test_release_can_be_built_without_changing_current(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            loops = root / "loops"
            previous = loops / "releases" / "previous"
            previous.mkdir(parents=True)
            (previous / "RELEASE.json").write_text('{"sha":"old"}\n')
            current = loops / "current"
            current.symlink_to(previous)
            npm = root / "npm"
            npm.write_text("#!/bin/sh\nmkdir -p node_modules\nprintf '{}\\n' > node_modules/.package-lock.json\n")
            npm.chmod(0o755)

            result = subprocess.run(
                ["/bin/bash", str(ROOT / "bin/cut-loop-release.sh"), "origin/main"],
                cwd=ROOT,
                env={
                    **os.environ,
                    "LOOPS_ROOT": str(loops),
                    "LOOPS_RELEASE_PATHS": "runtime/loop",
                    "LOOPS_ACTIVATE_CURRENT": "0",
                    "LIFE_MANAGER_DISK_PRESSURE_FILE": str(root / "no-pressure"),
                    "NPM_BIN": str(npm),
                    "NPM_VERSION": "test",
                    "NPM_NODE_VERSION": "test",
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(current.resolve(), previous.resolve())
            releases = [p for p in (loops / "releases").iterdir() if p != previous]
            self.assertEqual(len(releases), 1)
            self.assertTrue((releases[0] / "RELEASE.json").is_file())
            self.assertIn("current unchanged", result.stdout)

    def test_release_reuses_one_content_addressed_dependency_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            loops = root / "loops"
            calls = root / "npm.calls"
            npm = root / "npm"
            npm.write_text(
                f'#!/bin/sh\nprintf "%s\\n" "$PWD" >> "{calls}"\n'
                'mkdir -p node_modules\nprintf "{}\\n" > node_modules/.package-lock.json\n'
                'printf "sealed\\n" > node_modules/bundle-marker\n'
            )
            npm.chmod(0o755)
            agents = root / "agents"
            agents.mkdir()

            env = {
                **os.environ,
                "LOOPS_ROOT": str(loops),
                "LOOPS_KEEP_RELEASES": "2",
                "LOOPS_RELEASE_PATHS": "package.json package-lock.json runtime/compute-proxy runtime/agentmail apps/life-manager skills/earn/x402-sell services/x402-endpoint",
                "LOOPS_ACTIVATE_CURRENT": "0",
                "LIFE_MANAGER_LAUNCH_AGENTS_DIR": str(agents),
                "LIFE_MANAGER_DISK_PRESSURE_FILE": str(root / "no-pressure"),
                "NPM_BIN": str(npm),
                "NPM_VERSION": "test",
                "NPM_NODE_VERSION": "test",
            }
            first = subprocess.run(
                ["/bin/bash", str(ROOT / "bin/cut-loop-release.sh"), "origin/main"],
                cwd=ROOT, env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            first_release = next((loops / "releases").iterdir())
            first_targets = {
                relative: (first_release / relative / "node_modules").resolve()
                for relative in DEPENDENCY_ROOTS
            }
            npm.write_text("#!/bin/sh\nexit 99\n")

            result = subprocess.run(
                ["/bin/bash", str(ROOT / "bin/cut-loop-release.sh"), "origin/main"],
                cwd=ROOT, env=env, capture_output=True, text=True, check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            releases = sorted((loops / "releases").iterdir())
            self.assertEqual(len(releases), 2)
            release = releases[-1]
            self.assertEqual(len(calls.read_text().splitlines()), len(DEPENDENCY_ROOTS))
            for relative in DEPENDENCY_ROOTS:
                modules = release / relative / "node_modules"
                self.assertTrue(modules.is_symlink())
                self.assertEqual(modules.resolve(), first_targets[relative])
                self.assertEqual(
                    (modules / "bundle-marker").read_text(), "sealed\n"
                )

    def test_release_ignores_an_empty_matching_dependency_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            loops = root / "loops"
            donor = loops / "releases" / "donor"
            for relative in DEPENDENCY_ROOTS:
                package = donor / relative
                package.mkdir(parents=True, exist_ok=True)
                (package / "package-lock.json").write_bytes(
                    (ROOT / relative / "package-lock.json").read_bytes()
                )
                (package / "node_modules").mkdir()
            (donor / "RELEASE.json").write_text('{"sha":"%s"}\n' % ("a" * 40))
            (loops / "current").symlink_to(donor)
            calls = root / "npm.calls"
            npm = root / "npm"
            npm.write_text(f'#!/bin/sh\nprintf "%s\n" "$PWD" >> "{calls}"\nmkdir -p node_modules\nprintf "{{}}\\n" > node_modules/.package-lock.json\n')
            npm.chmod(0o755)

            result = subprocess.run(
                ["/bin/bash", str(ROOT / "bin/cut-loop-release.sh"), "origin/main"],
                cwd=ROOT,
                env={**os.environ, "LOOPS_ROOT": str(loops), "LOOPS_KEEP_RELEASES": "2", "LOOPS_RELEASE_PATHS": "package.json package-lock.json runtime/compute-proxy runtime/agentmail apps/life-manager skills/earn/x402-sell services/x402-endpoint", "LIFE_MANAGER_DISK_PRESSURE_FILE": str(root / "no-pressure"), "NPM_BIN": str(npm), "NPM_VERSION": "test", "NPM_NODE_VERSION": "test"},
                capture_output=True, text=True, check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(calls.read_text().splitlines()), len(DEPENDENCY_ROOTS))

    def test_release_prunes_only_unreferenced_dependency_bundles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            loops = root / "loops"
            releases = loops / "releases"
            retained = releases / "retained"
            retained.mkdir(parents=True)
            bundles = loops / "dependency-bundles"
            referenced = bundles / "npm-referenced"
            orphan = bundles / "npm-orphan"
            for bundle in (referenced, orphan):
                (bundle / "node_modules").mkdir(parents=True)
                (bundle / ".complete").write_text("key\n")
            (retained / "node_modules").symlink_to(referenced / "node_modules")
            (retained / "RELEASE.json").write_text(
                '{"sha":"%s","release_paths":"runtime/loop"}\n' % ("a" * 40)
            )

            result = subprocess.run(
                ["/bin/bash", str(ROOT / "bin/cut-loop-release.sh"), "origin/main"],
                cwd=ROOT,
                env={
                    **os.environ,
                    "LOOPS_ROOT": str(loops),
                    "LOOPS_KEEP_RELEASES": "2",
                    "LOOPS_RELEASE_PATHS": "runtime/loop",
                    "LOOPS_ACTIVATE_CURRENT": "0",
                    "LIFE_MANAGER_DISK_PRESSURE_FILE": str(root / "no-pressure"),
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(referenced.is_dir())
            self.assertFalse(orphan.exists())

    def test_matching_symlinked_donor_creates_a_self_contained_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            loops = root / "loops"
            source_bundle = loops / "dependency-bundles/npm-old"
            modules = source_bundle / "node_modules"
            modules.mkdir(parents=True)
            (source_bundle / ".complete").write_text("old\n")
            (modules / ".package-lock.json").write_text("{}\n")
            marker = modules / "marker"
            marker.write_text("sealed\n")
            donor = loops / "releases/donor"
            donor.mkdir(parents=True)
            for name in ("package.json", "package-lock.json"):
                (donor / name).write_bytes((ROOT / name).read_bytes())
            (donor / "node_modules").symlink_to(modules)
            (donor / "RELEASE.json").write_text(
                '{"sha":"%s","release_paths":"ALL"}\n' % ("a" * 40)
            )
            npm = root / "npm"
            npm.write_text("#!/bin/sh\nexit 99\n")
            npm.chmod(0o755)

            result = subprocess.run(
                ["/bin/bash", str(ROOT / "bin/cut-loop-release.sh"), "origin/main"],
                cwd=ROOT,
                env={
                    **os.environ,
                    "LOOPS_ROOT": str(loops),
                    "LOOPS_KEEP_RELEASES": "2",
                    "LOOPS_RELEASE_PATHS": "package.json package-lock.json",
                    "LOOPS_ACTIVATE_CURRENT": "0",
                    "LIFE_MANAGER_DISK_PRESSURE_FILE": str(root / "no-pressure"),
                    "NPM_BIN": str(npm),
                    "NPM_VERSION": "new",
                    "NPM_NODE_VERSION": "new",
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            release = next(p for p in (loops / "releases").iterdir() if p != donor)
            target = (release / "node_modules").resolve()
            self.assertNotEqual(target, modules.resolve())
            self.assertFalse(target.is_symlink())
            self.assertEqual((target / "marker").stat().st_ino, marker.stat().st_ino)

    def test_release_builds_locked_root_and_agentmail_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = root / "npm.calls"
            npm = root / "npm"
            npm.write_text(
                f'#!/bin/sh\nprintf "%s|%s\\n" "$PWD" "$*" >> "{calls}"\n'
                'mkdir -p node_modules\nprintf "{}\\n" > node_modules/.package-lock.json\n')
            npm.chmod(0o755)
            agents = root / "agents"
            agents.mkdir()
            result = subprocess.run(
                ["/bin/bash", str(ROOT / "bin/cut-loop-release.sh"), "origin/main"],
                cwd=ROOT,
                env={
                    **os.environ,
                    "LOOPS_ROOT": str(root / "loops"),
                    "LOOPS_KEEP_RELEASES": "1",
                    "LOOPS_RELEASE_PATHS": "package.json package-lock.json runtime/compute-proxy runtime/agentmail apps/life-manager skills/earn/x402-sell services/x402-endpoint",
                    "LIFE_MANAGER_LAUNCH_AGENTS_DIR": str(agents),
                    "LIFE_MANAGER_DISK_PRESSURE_FILE": str(root / "no-pressure"),
                    "NPM_BIN": str(npm),
                    "NPM_VERSION": "test",
                    "NPM_NODE_VERSION": "test",
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            recorded = calls.read_text().splitlines()
            self.assertEqual(len(recorded), len(DEPENDENCY_ROOTS))
            self.assertTrue(all(
                line.endswith("|ci --omit=dev --ignore-scripts") for line in recorded
            ))
            bundles = list((root / "loops/dependency-bundles").glob("npm-*"))
            self.assertEqual(len(bundles), len(DEPENDENCY_ROOTS))
            release = next((root / "loops/releases").iterdir())
            self.assertTrue(all(
                (release / relative / "node_modules").is_symlink()
                for relative in DEPENDENCY_ROOTS
            ))

    def test_reconciler_pins_captured_main_sha_when_origin_moves_during_cut(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            loops = root / "loops"
            old_release = loops / "releases" / "old"
            new_release = loops / "releases" / "new"
            old_release.mkdir(parents=True)
            new_release.mkdir(parents=True)
            current = loops / "current"
            current.symlink_to(old_release)
            captured_sha = "a" * 40
            (old_release / "RELEASE.json").write_text(
                '{"sha":"%s","release_paths":"ALL"}\n' % ("b" * 40)
            )
            (root / "origin.sha").write_text(captured_sha)
            cutter_arg = root / "cutter.arg"
            calls = root / "lm-loop.calls"
            fake_git = fake_bin / "git"
            fake_git.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = -C ] && [ \"$3\" = fetch ]; then exit 0; fi\n"
                "if [ \"$1\" = -C ] && [ \"$3\" = rev-parse ]; then\n"
                f"  cat {cutter_arg.parent / 'origin.sha'}\n"
                "  exit 0\n"
                "fi\n"
                "if [ \"$1\" = -C ] && [ \"$3\" = merge-base ]; then exit 0; fi\n"
                "if [ \"$1\" = -C ] && [ \"$3\" = diff ]; then exit 1; fi\n"
                "exit 1\n"
            )
            fake_git.chmod(0o755)
            cutter = old_release / "bin" / "cut-loop-release.sh"
            cutter.parent.mkdir()
            cutter.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$1\" > {cutter_arg}\n"
                f"printf '%s\\n' \"{'c' * 40}\" > {root / 'origin.sha'}\n"
                f"mkdir -p {new_release / 'bin'}\n"
                f"printf '%s\\n' '{{\"sha\":\"{captured_sha}\",\"release_paths\":\"ALL\"}}' > {new_release / 'RELEASE.json'}\n"
                f"printf '%s\\n' '#!/bin/sh' 'printf \"%s|%s\\\\n\" \"$LIFE_MANAGER_RELEASE_ROOT\" \"$*\" >> {calls}' 'exit 0' > {new_release / 'bin' / 'lm-loop'}\n"
                f"chmod +x {new_release / 'bin' / 'lm-loop'}\n"
                f"ln -sfn {new_release} {current}\n"
            )
            cutter.chmod(0o755)
            result = subprocess.run(
                ["/bin/bash", str(ROOT / "bin/reconcile-agent-runner-release.sh")],
                cwd=ROOT,
                env={
                    **os.environ,
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "LIFE_MANAGER_SOURCE_REPO": str(root),
                    "LOOPS_ROOT": str(loops),
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(cutter_arg.read_text().strip(), captured_sha)
            self.assertEqual((root / "origin.sha").read_text().strip(), "c" * 40)
            reconciles = calls.read_text().splitlines()
            self.assertEqual(len(reconciles), 2)
            self.assertTrue(
                all(line.startswith(f"{new_release.resolve()}|") for line in reconciles),
                reconciles,
            )
            self.assertEqual(
                [line.split("|", 1)[1] for line in reconciles],
                [
                    "reconcile shared-agent-runner --loaded-idle-only",
                    "reconcile deterministic --loaded-idle-only",
                ],
            )

    def test_reconciler_reuses_complete_release_for_docs_only_main(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            loops = root / "loops"
            release = loops / "releases" / "current-release"
            release.mkdir(parents=True)
            current = loops / "current"
            current.symlink_to(release)
            current_sha = "b" * 40
            main_sha = "a" * 40
            (release / "RELEASE.json").write_text(
                '{"sha":"%s","release_paths":"ALL"}\n' % current_sha
            )
            cutter_called = root / "cutter.called"
            calls = root / "lm-loop.calls"
            fake_git = fake_bin / "git"
            fake_git.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = -C ] && [ \"$3\" = fetch ]; then exit 0; fi\n"
                f"if [ \"$1\" = -C ] && [ \"$3\" = rev-parse ]; then printf '%s\\n' {main_sha}; exit 0; fi\n"
                "if [ \"$1\" = -C ] && [ \"$3\" = merge-base ]; then exit 0; fi\n"
                "if [ \"$1\" = -C ] && [ \"$3\" = diff ]; then exit 0; fi\n"
                "exit 1\n"
            )
            fake_git.chmod(0o755)
            cutter = release / "bin" / "cut-loop-release.sh"
            cutter.parent.mkdir()
            cutter.write_text(f"#!/bin/sh\ntouch {cutter_called}\nexit 99\n")
            cutter.chmod(0o755)
            lm_loop = release / "bin" / "lm-loop"
            lm_loop.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$*\" >> {calls}\n"
            )
            lm_loop.chmod(0o755)

            result = subprocess.run(
                ["/bin/bash", str(ROOT / "bin/reconcile-agent-runner-release.sh")],
                cwd=ROOT,
                env={
                    **os.environ,
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "LIFE_MANAGER_SOURCE_REPO": str(root),
                    "LOOPS_ROOT": str(loops),
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(cutter_called.exists())
            self.assertEqual(len(calls.read_text().splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
