import plistlib
import json
import hashlib
import errno
import io
import os
import plistlib
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from unittest import mock


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
    @classmethod
    def setUpClass(cls):
        fixture = tempfile.TemporaryDirectory()
        cls.addClassCleanup(fixture.cleanup)
        cls.source_repo = Path(fixture.name) / "source.git"
        # Keep real export/fetch/provenance checks local and pinned to the PR tree.
        subprocess.run(
            ["git", "clone", "--bare", "--shared", "--single-branch", str(ROOT), str(cls.source_repo)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(cls.source_repo), "update-ref", "refs/remotes/origin/main", "HEAD"],
            check=True, capture_output=True,
        )
        cls.probe_root = Path(fixture.name) / "probes"
        cls.probe_root.mkdir()
        (cls.probe_root / "sitecustomize.py").write_text("import release_gc_probe\n")
        (cls.probe_root / "release_gc_probe.py").write_text(
            "import os,subprocess\n"
            "original_run=subprocess.run\n"
            "def run(command,*args,**kwargs):\n"
            "    if isinstance(command,(list,tuple)) and os.path.basename(str(command[0])) in ('ps','lsof'):\n"
            "        return subprocess.CompletedProcess(command,0,'','')\n"
            "    if isinstance(command,(list,tuple)) and os.path.basename(str(command[0])) == 'plutil':\n"
            "        raise AssertionError('unexpected native plist fixture probe')\n"
            "    return original_run(command,*args,**kwargs)\n"
            "subprocess.run=run\n"
        )

    def setUp(self):
        fixture = tempfile.TemporaryDirectory()
        self.addCleanup(fixture.cleanup)
        home = Path(fixture.name)
        agents = home / "agents"
        agents.mkdir()
        (agents / "com.example.unrelated.plist").write_bytes(plistlib.dumps({"Label": "com.example.unrelated", "ProgramArguments": ["/usr/bin/true"]}))
        protected = home / "protected-releases.json"
        protected.write_text("[]")
        self.enterContext(mock.patch.dict(os.environ, {
            "HOME": str(home), "LIFE_MANAGER_SOURCE_REPO": str(self.source_repo),
            "LIFE_MANAGER_LAUNCH_AGENTS_DIR": str(agents),
            "LIFE_MANAGER_PROTECTED_RELEASES": str(protected),
            "PYTHONPATH": str(self.probe_root),
        }))

    def test_matching_locked_dependencies_rejects_reclaimed_donor(self):
        source = (ROOT / "bin/cut-loop-release.sh").read_text()
        start = source.index("matching_locked_dependencies() {")
        function = source[start:source.index("\nlink_locked_dependencies()", start)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            donor = root / "releases/donor"
            target.mkdir()
            donor.mkdir(parents=True)
            for filename in ("package.json", "package-lock.json"):
                (target / filename).write_text("{}\n")
                (donor / filename).write_text("{}\n")
            bundle_root = root / "bundles"
            bundle_key = "a" * 64
            bundle = bundle_root / ("npm-" + bundle_key)
            (bundle / "node_modules").mkdir(parents=True)
            (bundle / "node_modules/.package-lock.json").write_text("{}\n")
            (bundle / ".complete").write_text(bundle_key + "\n")
            bundle.chmod(0o555)
            (donor / "node_modules").symlink_to(bundle / "node_modules")
            descriptor = json.dumps({"sha": "a" * 40, "release_paths": "ALL"}).encode()
            (donor / "RELEASE.json").write_bytes(descriptor)
            marker = donor / "RECLAIMED-RELEASE.json"
            for kind in ("absent", "descriptor", "dangling", "probe_error"):
                with self.subTest(kind=kind):
                    if kind == "descriptor":
                        marker.write_bytes(descriptor)
                    elif kind == "dangling":
                        marker.symlink_to(donor / "missing-descriptor")
                    elif kind == "probe_error":
                        donor.chmod(0)
                    try:
                        result = subprocess.run(
                            ["bash"], input=function + '\nmatching_locked_dependencies "$DEST"\n',
                            env={**os.environ, "SCRIPT_ROOT": str(ROOT),
                                 "DEST": str(target), "RELEASES": str(root / "releases"),
                                 "DEPENDENCY_BUNDLES": str(bundle_root),
                                 "RUNTIME_PYTHON": sys.executable},
                            capture_output=True, text=True, check=False,
                        )
                    finally:
                        donor.chmod(0o755)
                        bundle.chmod(0o755)
                        marker.unlink(missing_ok=True)
                    if kind == "absent":
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout.strip(), str((donor / "node_modules").resolve()))
                    else:
                        self.assertEqual(result.returncode, 1, result.stderr)
                        self.assertEqual(result.stdout, "")
                    self.assertEqual((donor / "RELEASE.json").read_bytes(), descriptor)

    def test_script_only_change_reuses_bundle_without_installing_dependencies(self):
        import hashlib
        import platform
        import sys
        source = (ROOT / "bin/cut-loop-release.sh").read_text()
        start = source.index("matching_locked_dependencies() {")
        function = source[start:source.index('\nmkdir -p "$DEPENDENCY_BUNDLES"', start)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target, donor = root / "target", root / "releases/donor"
            target.mkdir(); donor.mkdir(parents=True)
            package = {"name": "fixture", "version": "1.0.0", "scripts": {"test": "old"}}
            old = json.dumps(package).encode()
            lock = b'{"lockfileVersion":3}\n'
            (donor / "package.json").write_bytes(old)
            (donor / "package-lock.json").write_bytes(lock)
            header = "\0".join(("command", "npm-ci --omit=dev --ignore-scripts", "os", platform.system(),
                                  "arch", platform.machine(), "node", "previous-node", "npm", "previous-npm")) + "\0"
            data = header.encode()
            for label, payload in (("package-json", old), ("package-lock", lock)):
                data += label.encode() + b"\0" + (hashlib.sha256(payload).hexdigest() + "  -\n").encode()
            key = hashlib.sha256(data).hexdigest()
            bundles = root / "bundles"
            bundle = bundles / ("npm-" + key)
            current_header = header.replace("previous-node", "node").replace("previous-npm", "npm")
            current_data = current_header.encode()
            for label, payload in (("package-json", old), ("package-lock", lock)):
                current_data += label.encode() + b"\0" + (hashlib.sha256(payload).hexdigest() + "  -\n").encode()
            current_key = hashlib.sha256(current_data).hexdigest()
            current_bundle = bundles / ("npm-" + current_key)
            (bundle / "node_modules").mkdir(parents=True)
            (bundle / "node_modules/.package-lock.json").write_bytes(lock)
            (bundle / "node_modules/retained.txt").write_text("known dependency")
            (bundle / ".complete").write_text(key + "\n")
            bundle.chmod(0o555)
            (donor / "node_modules").symlink_to(bundle / "node_modules")
            (donor / "RELEASE.json").write_text(json.dumps({"sha": "a" * 40, "release_paths": "ALL"}))
            package["scripts"]["test"] = "new"
            cases = (("script_only", package, lock, 0),
                     ("deps_changed", {**package, "dependencies": {"new": "1"}}, lock, 1),
                     ("lock_changed", package, lock + b" ", 1))
            try:
                for name, candidate, candidate_lock, expected in cases:
                    with self.subTest(name=name):
                        (target / "package.json").write_text(json.dumps(candidate))
                        (target / "package-lock.json").write_bytes(candidate_lock)
                        result = subprocess.run(["bash"], input=function + '\nlink_locked_dependencies "$DEST"\n',
                            env={**os.environ, "SCRIPT_ROOT": str(ROOT), "DEST": str(target), "CURRENT": str(donor),
                                 "RELEASES": str(donor.parent),
                                 "DEPENDENCY_BUNDLES": str(bundles), "RUNTIME_PYTHON": sys.executable,
                                 "NPM_NODE_VERSION": "node", "NPM_VERSION": "npm", "NPM_BIN": "/usr/bin/false",
                                 "RELEASE_REQUIRED_BYTES": str(2 * 1024**3 + 64 * 1024**2)},
                            capture_output=True, text=True)
                        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                        if expected == 0:
                            self.assertEqual((target / "node_modules").resolve(),
                                             (current_bundle / "node_modules").resolve())
                            self.assertEqual((bundle / "node_modules/retained.txt").stat().st_ino,
                                             (current_bundle / "node_modules/retained.txt").stat().st_ino)
                            (target / "node_modules").unlink()
                        else:
                            self.assertFalse((target / "node_modules").exists())
                        self.assertEqual((target / "package.json").read_text(), json.dumps(candidate))
                if current_bundle.exists():
                    self.assertEqual({path.name for path in bundles.iterdir()},
                                     {bundle.name, current_bundle.name})
                self.assertEqual((bundle / "node_modules/retained.txt").read_text(), "known dependency")
            finally:
                for path in sorted(bundles.rglob("*"), reverse=True):
                    if not path.is_symlink():
                        path.chmod(path.stat().st_mode | 0o200)
                for path in bundles.iterdir():
                    if path.is_dir() and not path.is_symlink():
                        path.chmod(path.stat().st_mode | 0o200)

    def _pushed_branch_fixture(self, root):
        repo, origin = root / "repo", root / "origin.git"
        repo.mkdir()
        subprocess.run(["git", "init", "--bare", str(origin)], check=True,
                       capture_output=True)
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True,
                       capture_output=True)
        for key, value in (("user.email", "release-test@example.invalid"),
                           ("user.name", "Release Test")):
            subprocess.run(["git", "config", key, value], cwd=repo, check=True)
        subprocess.run(["git", "remote", "add", "origin", str(origin)],
                       cwd=repo, check=True)
        (repo / "payload.txt").write_text("main\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "main"], cwd=repo, check=True,
                       capture_output=True)
        main_sha = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                           cwd=repo, text=True).strip()
        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=repo,
                       check=True, capture_output=True)
        subprocess.run(["git", "switch", "-c", "candidate"], cwd=repo,
                       check=True, capture_output=True)
        (repo / "payload.txt").write_text("candidate\n")
        subprocess.run(["git", "commit", "-am", "candidate"], cwd=repo,
                       check=True, capture_output=True)
        candidate_sha = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                                cwd=repo, text=True).strip()
        subprocess.run(["git", "push", "-u", "origin", "candidate"], cwd=repo,
                       check=True, capture_output=True)
        return repo, main_sha, candidate_sha

    def _cut_sparse(self, root, repo, sha, *, activate, paths="payload.txt"):
        capacity_probe = root / "capacity-probe"
        capacity_probe.mkdir(exist_ok=True)
        (capacity_probe / "sitecustomize.py").write_text(
            "import release_gc_probe\nimport shutil,types\nshutil.disk_usage=lambda p: types.SimpleNamespace(free=16*1024**3)\n"
        )
        return subprocess.run(
            ["/bin/bash", str(ROOT / "bin/cut-loop-release.sh"), sha],
            cwd=repo,
            env={**os.environ, "LIFE_MANAGER_SOURCE_REPO": str(repo),
                 "PYTHONPATH": str(capacity_probe) + os.pathsep + str(self.probe_root),
                 "LOOPS_ROOT": str(root / "loops"), "LOOPS_RELEASE_PATHS": paths,
                 "LOOPS_ACTIVATE_CURRENT": "1" if activate else "0",
                 "LIFE_MANAGER_RESOURCE_ADMISSION_ROOT": str(root / "admission"),
                 "LIFE_MANAGER_DISK_PRESSURE_FILE": str(root / "no-pressure"),
                 "NPM_BIN": ""},
            capture_output=True, text=True, check=False,
        )

    def test_pushed_unmerged_release_cannot_activate_current(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, _main_sha, candidate_sha = self._pushed_branch_fixture(root)
            result = self._cut_sparse(root, repo, candidate_sha, activate=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("origin/main", result.stderr)
            self.assertFalse((root / "loops/current").exists())

    def test_sparse_main_release_cannot_activate_global_current(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, main_sha, _candidate_sha = self._pushed_branch_fixture(root)
            result = self._cut_sparse(root, repo, main_sha, activate=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("complete release", result.stderr)
            self.assertFalse((root / "loops/current").exists())

    def test_main_release_recovers_current_from_unmerged_branch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, main_sha, candidate_sha = self._pushed_branch_fixture(root)
            candidate = self._cut_sparse(root, repo, candidate_sha, activate=False)
            self.assertEqual(candidate.returncode, 0, candidate.stderr)
            release = next((root / "loops/releases").iterdir())
            (root / "loops/current").symlink_to(release)
            recovered = self._cut_sparse(root, repo, main_sha, activate=True, paths="")
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            self.assertEqual(json.loads((root / "loops/current/RELEASE.json").read_text())["sha"],
                             main_sha)

    def test_release_builds_immutable_bytecode_for_its_runtime_python(self):
        with tempfile.TemporaryDirectory() as directory:
            loops = Path(directory) / "loops"
            result = subprocess.run(
                ["/bin/bash", str(ROOT / "bin/cut-loop-release.sh"), "origin/main"],
                cwd=ROOT,
                env={
                    **os.environ,
                    "LOOPS_ROOT": str(loops),
                    "LOOPS_RELEASE_PATHS": "runtime/loop",
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
            checkout_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
            ).strip()
            self.assertEqual(manifest["sha"], checkout_sha)
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
            (agents / "com.example.unrelated.plist").write_bytes(plistlib.dumps({"Label": "com.example.unrelated", "ProgramArguments": ["/usr/bin/true"]}))
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
                    "LIFE_MANAGER_RESOURCE_ADMISSION_ROOT": str(root / "admission"),
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

    def test_taskmarket_sparse_release_builds_its_cli_dependency_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            loops = root / "loops"
            npm = root / "npm"
            npm.write_text(
                "#!/bin/sh\n"
                "mkdir -p node_modules/.bin\n"
                "printf '{}\\n' > node_modules/.package-lock.json\n"
                "printf '#!/bin/sh\\nexit 0\\n' > node_modules/.bin/taskmarket\n"
                "chmod +x node_modules/.bin/taskmarket\n"
            )
            npm.chmod(0o755)

            result = subprocess.run(
                ["/bin/bash", str(ROOT / "bin/cut-loop-release.sh"), "origin/main"],
                cwd=ROOT,
                env={
                    **os.environ,
                    "LOOPS_ROOT": str(loops),
                    "LOOPS_RELEASE_PATHS": "skills/earn/taskmarket",
                    "LOOPS_ACTIVATE_CURRENT": "0",
                    "LIFE_MANAGER_DISK_PRESSURE_FILE": str(root / "no-pressure"),
                    "LIFE_MANAGER_RESOURCE_ADMISSION_ROOT": str(root / "admission"),
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
            modules = release / "skills/earn/taskmarket/node_modules"
            cli = modules / ".bin/taskmarket"
            self.assertTrue(modules.is_symlink())
            self.assertTrue(cli.is_file())
            self.assertTrue(os.access(cli, os.X_OK))

    def test_release_cannot_move_current_to_an_older_main_ancestor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, older_sha, _candidate_sha = self._pushed_branch_fixture(root)
            subprocess.run(["git", "switch", "main"], cwd=repo, check=True,
                           capture_output=True)
            (repo / "payload.txt").write_text("newer main\n")
            subprocess.run(["git", "commit", "-am", "newer main"], cwd=repo,
                           check=True, capture_output=True)
            current_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            subprocess.run(["git", "push", "origin", "main"], cwd=repo,
                           check=True, capture_output=True)
            loops = root / "loops"
            current_release = loops / "releases" / "current-release"
            current_release.mkdir(parents=True)
            (current_release / "RELEASE.json").write_text(
                json.dumps({"sha": current_sha, "release_paths": "ALL"}) + "\n"
            )
            current = loops / "current"
            current.symlink_to(current_release)
            result = self._cut_sparse(root, repo, older_sha, activate=True, paths="")

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("current backwards", result.stderr)
            self.assertEqual(current.resolve(), current_release.resolve())

    def test_release_reuses_one_content_addressed_dependency_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            loops = root / "loops"
            calls = root / "npm.calls"
            clock_calls = root / "release-clock.calls"
            clock_env = root / "release-clock.bash"
            clock_env.write_text(
                "date() {\n"
                '  if [ "$*" = "+%Y%m%dT%H%M%S" ]; then\n'
                f'    if [ ! -e "{clock_calls}.first" ]; then\n'
                f'      : > "{clock_calls}.first"\n'
                '      timestamp="20261023T032742"\n'
                '    else\n'
                '      timestamp="20261023T032743"\n'
                '    fi\n'
                f'    printf "%s\\n" "$timestamp" >> "{clock_calls}"\n'
                '    printf "%s\\n" "$timestamp"\n'
                '  else\n'
                '    command /bin/date "$@"\n'
                '  fi\n'
                '}\n'
            )
            npm = root / "npm"
            npm.write_text(
                f'#!/bin/sh\nprintf "%s\\n" "$PWD" >> "{calls}"\n'
                'mkdir -p node_modules\nprintf "{}\\n" > node_modules/.package-lock.json\n'
                'printf "sealed\\n" > node_modules/bundle-marker\n'
            )
            npm.chmod(0o755)
            agents = root / "agents"
            agents.mkdir()
            (agents / "com.example.unrelated.plist").write_bytes(plistlib.dumps({"Label": "com.example.unrelated", "ProgramArguments": ["/usr/bin/true"]}))

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
                "BASH_ENV": str(clock_env),
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
            self.assertEqual(
                clock_calls.read_text().splitlines(),
                ["20261023T032742", "20261023T032743"],
            )
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
                env={**os.environ, "LOOPS_ROOT": str(loops), "LOOPS_KEEP_RELEASES": "2", "LOOPS_RELEASE_PATHS": "package.json package-lock.json runtime/compute-proxy runtime/agentmail apps/life-manager skills/earn/x402-sell services/x402-endpoint", "LOOPS_ACTIVATE_CURRENT": "0", "LIFE_MANAGER_DISK_PRESSURE_FILE": str(root / "no-pressure"), "LIFE_MANAGER_RESOURCE_ADMISSION_ROOT": str(root / "admission"), "NPM_BIN": str(npm), "NPM_VERSION": "test", "NPM_NODE_VERSION": "test"},
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
            referenced = bundles / ("npm-" + "a" * 64)
            orphan = bundles / ("npm-" + "b" * 64)
            for bundle in (referenced, orphan):
                (bundle / "node_modules").mkdir(parents=True)
                (bundle / ".complete").write_text(bundle.name[4:] + "\n")
                (bundle / "package.json").write_text("{}\n")
                (bundle / "package-lock.json").write_text("{}\n")
                (bundle / "node_modules/.package-lock.json").write_text("{}\n")
                for path in bundle.rglob("*"):
                    path.chmod(0o555 if path.is_dir() else 0o444)
                bundle.chmod(0o555)
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
            bundle_key = hashlib.sha256(b"old toolchain bundle").hexdigest()
            source_bundle = loops / "dependency-bundles" / ("npm-" + bundle_key)
            modules = source_bundle / "node_modules"
            modules.mkdir(parents=True)
            (source_bundle / ".complete").write_text(bundle_key + "\n")
            (modules / ".package-lock.json").write_text("{}\n")
            marker = modules / "marker"
            marker.write_text("sealed\n")
            source_bundle.chmod(0o555)
            donor = loops / "releases/donor"
            donor.mkdir(parents=True)
            release_ref = "origin/main"
            for name in ("package.json", "package-lock.json"):
                source_bytes = subprocess.check_output(
                    ["git", "show", f"{release_ref}:{name}"], cwd=self.source_repo
                )
                (donor / name).write_bytes(source_bytes)
            (donor / "node_modules").symlink_to(modules)
            (donor / "RELEASE.json").write_text(
                '{"sha":"%s","release_paths":"ALL"}\n' % ("a" * 40)
            )
            npm = root / "npm"
            npm.write_text("#!/bin/sh\nexit 99\n")
            npm.chmod(0o755)

            try:
                result = subprocess.run(
                    ["/bin/bash", str(ROOT / "bin/cut-loop-release.sh"), release_ref],
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
            finally:
                source_bundle.chmod(0o755)

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
            (agents / "com.example.unrelated.plist").write_bytes(plistlib.dumps({"Label": "com.example.unrelated", "ProgramArguments": ["/usr/bin/true"]}))
            result = subprocess.run(
                ["/bin/bash", str(ROOT / "bin/cut-loop-release.sh"), "origin/main"],
                cwd=ROOT,
                env={
                    **os.environ,
                    "LOOPS_ROOT": str(root / "loops"),
                    "LOOPS_KEEP_RELEASES": "1",
                    "LOOPS_RELEASE_PATHS": "package.json package-lock.json runtime/compute-proxy runtime/agentmail apps/life-manager skills/earn/x402-sell services/x402-endpoint",
                    "LOOPS_ACTIVATE_CURRENT": "0",
                    "LIFE_MANAGER_LAUNCH_AGENTS_DIR": str(agents),
                    "LIFE_MANAGER_DISK_PRESSURE_FILE": str(root / "no-pressure"),
                    "LIFE_MANAGER_RESOURCE_ADMISSION_ROOT": str(root / "admission"),
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

    def test_reconciler_bounds_origin_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            loops = root / "loops"
            release = loops / "releases" / "current-release"
            (release / "bin").mkdir(parents=True)
            (loops / "current").symlink_to(release)
            (release / "RELEASE.json").write_text(
                '{"sha":"%s","release_paths":"ALL"}\n' % ("a" * 40)
            )
            reconcile_calls = root / "reconcile.calls"
            lm_loop = release / "bin" / "lm-loop"
            lm_loop.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$*\" >> {reconcile_calls}\n"
            )
            lm_loop.chmod(0o755)
            fake_git = fake_bin / "git"
            fetch_args = root / "fetch.args"
            fake_git.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$*\" > {fetch_args}\n"
                "sleep 10\n"
            )
            fake_git.chmod(0o755)

            result = subprocess.run(
                ["/bin/bash", str(ROOT / "bin/reconcile-agent-runner-release.sh")],
                cwd=ROOT,
                env={
                    **os.environ,
                    "HOME": str(root),
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "LIFE_MANAGER_SOURCE_REPO": str(root),
                    "LOOPS_ROOT": str(loops),
                    "LIFE_MANAGER_RELEASE_FETCH_TIMEOUT_SECONDS": "1",
                },
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )

            self.assertEqual(result.returncode, 124, result.stderr)
            self.assertIn("--no-tags", fetch_args.read_text())
            self.assertIn("--no-auto-maintenance", fetch_args.read_text())
            self.assertIn(
                "--negotiation-tip=refs/remotes/origin/main", fetch_args.read_text()
            )
            self.assertFalse(
                reconcile_calls.exists(),
                "a pre-fetch release must never be applied after current can move",
            )

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
                f"mkdir -p {new_release / 'bin'} {new_release / 'config'}\n"
                f"printf '%s\\n' '{{\"sha\":\"{captured_sha}\",\"release_paths\":\"ALL\"}}' > {new_release / 'RELEASE.json'}\n"
                f"printf '%s\\n' '{{\"loops\":{{\"loop-a\":{{}}}}}}' > {new_release / 'config' / 'loop-registry.json'}\n"
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
                    "HOME": str(root),
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "LIFE_MANAGER_SOURCE_REPO": str(root),
                    "LOOPS_ROOT": str(loops),
                    "LIFE_MANAGER_RELEASE_CUT_MIN_INTERVAL_SECONDS": "0",
                    "LIFE_MANAGER_RESOURCE_ADMISSION_ROOT": str(root / "admission"),
                    "LIFE_MANAGER_RECOVERY_INTENTS_PATH": str(root / "recovery-intents.jsonl"),
                    "LIFE_MANAGER_RELEASE_RECONCILER_STATE_ROOT": str(root / "reconciler-state"),
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(cutter_arg.read_text().strip(), captured_sha)
            self.assertEqual((root / "origin.sha").read_text().strip(), "c" * 40)
            reconciles = calls.read_text().splitlines()
            self.assertEqual(len(reconciles), 4)
            self.assertTrue(
                all(line.startswith(f"{new_release.resolve()}|") for line in reconciles),
                reconciles,
            )
            self.assertEqual(
                [line.split("|", 1)[1] for line in reconciles],
                [
                    "reconcile shared-agent-runner --loaded-idle-only --max-owners 4",
                    "reconcile deterministic --loaded-idle-only --max-owners 4",
                    "admission-v2-enable",
                    "apply --loaded-idle-only",
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
            (release / "config").mkdir()
            current = loops / "current"
            current.symlink_to(release)
            current_sha = "b" * 40
            main_sha = "a" * 40
            (release / "RELEASE.json").write_text(
                '{"sha":"%s","release_paths":"ALL"}\n' % current_sha
            )
            (release / "config" / "loop-registry.json").write_text(
                '{"loops":{"loop-a":{}}}\n'
            )
            cutter_called = root / "cutter.called"
            calls = root / "lm-loop.calls"
            admission_root = root / "admission"
            admission_root.mkdir()
            (admission_root / "protocol.json").write_text('{"version":2}\n')
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
                    "HOME": str(root),
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "LIFE_MANAGER_SOURCE_REPO": str(root),
                    "LOOPS_ROOT": str(loops),
                    "LIFE_MANAGER_RESOURCE_ADMISSION_ROOT": str(admission_root),
                    "LIFE_MANAGER_RECOVERY_INTENTS_PATH": str(root / "recovery-intents.jsonl"),
                    "LIFE_MANAGER_RELEASE_RECONCILER_STATE_ROOT": str(root / "reconciler-state"),
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(cutter_called.exists())
            self.assertEqual(len(calls.read_text().splitlines()), 3)


class CentralReleaseBundleGCTest(unittest.TestCase):
    def setUp(self):
        from runtime.loop import central_cleanup
        self.cleanup = central_cleanup
        fixture = tempfile.TemporaryDirectory()
        self.addCleanup(fixture.cleanup)
        self.root = Path(fixture.name)
        self.addCleanup(self._restore_directories)
        self.loops = self.root / "loops"
        self.releases = self.loops / "releases"
        self.agents = self.root / "agents"
        self.source_repo = self.root / "source"
        for path in (self.releases, self.agents, self.source_repo):
            path.mkdir(parents=True)
        (self.agents / "com.example.unrelated.plist").write_bytes(plistlib.dumps({"Label": "com.example.unrelated", "ProgramArguments": ["/usr/bin/true"]}))
        self.protected = self.root / "protected-releases.json"
        self.protected.write_text("[]")
        self.enterContext(mock.patch.dict(os.environ, {
            "HOME": str(self.root), "LOOPS_ROOT": str(self.loops),
            "LIFE_MANAGER_LAUNCH_AGENTS_DIR": str(self.agents),
            "LIFE_MANAGER_PROTECTED_RELEASES": str(self.protected),
            "LIFE_MANAGER_SOURCE_REPO": str(self.source_repo),
        }))
        self.ps_stdout = self.lsof_stdout = self.lsof_stderr = ""
        self.ps_code = self.lsof_code = 0
        self.native_plist = None
        self.commands = []

    def _restore_directories(self):
        for current, directories, _files in os.walk(self.root, followlinks=False):
            Path(current).chmod(0o755)
            for name in directories:
                path = Path(current) / name
                if not path.is_symlink():
                    path.chmod(0o755)

    def _seal(self, root):
        for path in root.rglob("*"):
            if not path.is_symlink():
                path.chmod(0o555 if path.is_dir() else 0o444)
        root.chmod(0o555)

    def _bundle(self, key="a" * 64, *, protected_path=None):
        bundle = self.loops / "dependency-bundles" / ("npm-" + key)
        modules = bundle / "node_modules"
        modules.mkdir(parents=True)
        (bundle / "package.json").write_text('{"name":"fixture"}\n')
        for path in (bundle / "package-lock.json", modules / ".package-lock.json"):
            path.write_text('{"lockfileVersion":3}\n')
        (bundle / ".complete").write_text(key + "\n")
        (modules / "fixture.js").write_text("sealed dependency\n")
        if protected_path:
            path = bundle / protected_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("protected fixture\n")
        self._seal(bundle)
        return bundle

    def _release(self, bundle):
        release = self.releases / "20260101T000000-aaaaaaaa"
        (release / "bin").mkdir(parents=True)
        (release / "bin/run.py").write_text("pass\n")
        (release / "RELEASE.json").write_text(json.dumps({"sha": "a" * 40}))
        (release / "node_modules").symlink_to(bundle / "node_modules")
        self._seal(release)
        return release

    def _probe(self, command, **kwargs):
        command = list(map(str, command))
        self.commands.append(command)
        tool = Path(command[0]).name
        if tool == "ps":
            code, stdout, stderr = self.ps_code, self.ps_stdout, ""
        elif tool == "lsof":
            code, stdout, stderr = self.lsof_code, self.lsof_stdout, self.lsof_stderr
        elif tool == "git" and command[1:3] == ["-C", str(self.source_repo)]:
            code, stdout, stderr = 0, "", ""
        elif command == ["/usr/bin/plutil", "-convert", "json", "-o", "-",
                         str(self.agents / "ai.anicca.fixture.plist")]:
            code = 1 if self.native_plist is None else 0
            stdout = "" if self.native_plist is None else json.dumps(self.native_plist)
            stderr = ""
        else:
            raise AssertionError(f"unexpected fixture subprocess: {command!r}")
        if code and kwargs.get("check"):
            raise subprocess.CalledProcessError(code, command, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(command, code, stdout, stderr)

    def _gc(self, keep=0):
        output = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"LIFE_MANAGER_RELEASE_KEEP": str(keep)}),
            mock.patch.object(sys, "argv", ["central_cleanup.py", "--release-gc-only"]),
            mock.patch.object(subprocess, "run", side_effect=self._probe),
            mock.patch.object(subprocess, "Popen", side_effect=AssertionError("host subprocess forbidden")),
            mock.patch.object(subprocess, "check_output", side_effect=AssertionError("host subprocess forbidden")),
            redirect_stdout(output),
        ):
            code = self.cleanup.main()
        return code, json.loads(output.getvalue())

    def test_release_gc_gives_slow_release_link_censuses_a_fresh_bounded_window(self):
        bundle = self._bundle()
        release = self._release(bundle)
        clock = [0.0]
        calls = 0

        def slow_reference_snapshot(*args, **kwargs):
            nonlocal calls
            calls += 1
            deadline = args[4]
            remaining = deadline - clock[0]
            if remaining < 20:
                raise subprocess.TimeoutExpired("release dependency links", remaining)
            clock[0] += 20
            return set(), [str(bundle)]

        with mock.patch.object(self.cleanup.time, "monotonic", side_effect=lambda: clock[0]), \
             mock.patch.object(self.cleanup, "_bundle_references", side_effect=slow_reference_snapshot):
            code, result = self._gc(keep=1)

        self.assertEqual(code, 0, result)
        self.assertEqual(calls, 2)
        self.assertTrue(release.exists())
        self.assertTrue(bundle.exists())
        self.assertEqual(result["dependency_bundles"]["preserved"], 1)
        self.assertEqual(result["errors"], 0)

    def test_bundle_reference_open_file_probe_uses_bounded_census_budget(self):
        bundle = self._bundle()
        self._release(bundle)
        timeouts = []
        probe = self._probe

        def record_probe(command, **kwargs):
            if Path(command[0]).name == "lsof":
                timeouts.append(kwargs.get("timeout"))
            return probe(command, **kwargs)

        with mock.patch.object(self, "_probe", side_effect=record_probe):
            code, result = self._gc(keep=1)

        self.assertEqual(code, 0, result)
        self.assertTrue(timeouts)
        self.assertEqual(timeouts[0], 15)
        self.assertLessEqual(timeouts[0], 30)

    def test_release_gc_only_preserves_open_bundle_with_minimal_host_path(self):
        bundle = self._bundle()
        self.lsof_stdout = f"p12345\nf7\nn{bundle}/node_modules/fixture.js\n"
        probe = self._probe

        def minimal_path_probe(command, **kwargs):
            if command[0] == "lsof":
                raise FileNotFoundError(2, "No such file or directory", "lsof")
            return probe(command, **kwargs)

        with mock.patch.dict(os.environ, {"PATH": "/bin:/usr/bin"}), \
             mock.patch.object(self, "_probe", side_effect=minimal_path_probe):
            code, result = self._gc()

        self.assertEqual(code, 0, result)
        self.assertEqual(result["errors"], 0)
        self.assertTrue(bundle.exists())
        self.assertEqual(result["dependency_bundles"]["removed"], 0)

    def test_release_gc_only_reclaims_readonly_bundle_without_current_and_replays_zero(self):
        bundle = self._bundle()
        release = self._release(bundle)
        code, result = self._gc()
        self.assertFalse(release.exists())
        self.assertFalse(bundle.exists(), "release-gc-only left its unreferenced readonly bundle")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["removed_releases"], 1)
        self.assertGreater(result["reclaimed_bytes"], 0)
        self.assertFalse(any(Path(command[0]).name == "git" for command in self.commands))
        code, replay = self._gc()
        self.assertEqual(code, 0, replay)
        self.assertEqual(replay["removed_releases"], 0)
        self.assertEqual(replay["reclaimed_bytes"], 0)

    def test_release_gc_only_empty_roots_need_no_reference_probe(self):
        self.ps_code = self.lsof_code = 1
        code, result = self._gc()
        self.assertEqual(code, 0, result)
        self.assertEqual(result["reclaimed_bytes"], 0)
        self.assertEqual(self.commands, [])

    def test_release_gc_only_rejects_empty_agents_without_releases(self):
        bundle = self._bundle()
        for path in self.agents.iterdir():
            path.unlink()
        code, result = self._gc()
        self.assertTrue(bundle.exists(), "empty launchd inventory allowed bundle removal")
        self.assertEqual(code, 1, result)
        self.assertEqual(result["dependency_bundles"]["status"], "reference_or_lock_unavailable")

    def test_release_gc_only_rejects_missing_agents_without_releases(self):
        bundle = self._bundle()
        for path in self.agents.iterdir():
            path.unlink()
        self.agents.rmdir()
        code, result = self._gc()
        self.assertTrue(bundle.exists(), "missing launchd inventory allowed bundle removal")
        self.assertEqual(code, 1, result)
        self.assertEqual(result["dependency_bundles"]["status"], "reference_or_lock_unavailable")

    def test_release_gc_only_preserves_current_bundle(self):
        bundle = self._bundle()
        release = self._release(bundle)
        (self.loops / "current").symlink_to(release)
        self._gc()
        self.assertTrue(release.exists())
        self.assertEqual((bundle / "node_modules/fixture.js").read_text(), "sealed dependency\n")

    def test_release_gc_only_preserves_pinned_bundle(self):
        bundle = self._bundle()
        release = self._release(bundle)
        self.protected.write_text(json.dumps([str(release)]))
        self._gc()
        self.assertTrue(release.exists())
        self.assertTrue(bundle.exists())

    def test_release_gc_only_preserves_bundle_linked_by_retained_release(self):
        bundle = self._bundle()
        release = self._release(bundle)
        self._gc(keep=1)
        self.assertTrue(release.exists())
        self.assertTrue(bundle.exists())

    def test_release_gc_only_preserves_bundle_named_by_plist(self):
        bundle = self._bundle()
        (self.agents / "ai.anicca.fixture.plist").write_bytes(plistlib.dumps({
            "ProgramArguments": [str(bundle / "node_modules/fixture.js")],
        }))
        self._gc()
        self.assertTrue(bundle.exists())

    def test_release_gc_only_preserves_bundle_named_by_plist_directory_or_environment(self):
        for index, key in enumerate(("WorkingDirectory", "EnvironmentVariables"), 1):
            bundle = self._bundle(f"{index:064x}")
            alias = self.root / f"dependency alias {index}"
            alias.symlink_to(bundle)
            fields = {key: str(alias / "node_modules") if key == "WorkingDirectory"
                      else {"NODE_PATH": str(alias / "node_modules")}}
            with self.subTest(fields=tuple(fields)):
                (self.agents / "ai.anicca.fixture.plist").write_bytes(plistlib.dumps(fields))
                self._gc()
                self.assertTrue(bundle.exists())

    def test_release_gc_only_preserves_bundle_named_by_process(self):
        bundle = self._bundle()
        self.ps_stdout = f"999999 node {bundle}/node_modules/fixture.js\n"
        self._gc()
        self.assertTrue(bundle.exists())

    def test_release_gc_only_preserves_quoted_process_alias_with_spaces(self):
        bundle = self._bundle()
        alias = self.root / "dependency alias"
        alias.symlink_to(bundle)
        self.ps_stdout = f"node --require '{alias}/node_modules/fixture.js' worker.js\n"
        self._gc()
        self.assertTrue(bundle.exists())

    def test_release_gc_only_preserves_unquoted_process_alias_with_spaces(self):
        bundle = self._bundle()
        alias = self.root / "dependency alias"
        alias.symlink_to(bundle)
        self.ps_stdout = f"node --require {alias}/node_modules/fixture.js worker.js\n"
        self._gc()
        self.assertTrue(bundle.exists())

    def test_release_gc_only_preserves_process_alias_with_equals_in_its_path(self):
        for index, template in enumerate(("--require '{}'", "--require {}", "--require='{}'"), 1):
            with self.subTest(argument_form=index):
                bundle = self._bundle(f"{index:064x}")
                alias = self.root / f"dependency=alias {index} with spaces"
                alias.symlink_to(bundle)
                argument = template.format(alias / "node_modules/fixture.js")
                self.ps_stdout = f"node {argument} worker.js\n"
                self._gc()
                self.assertTrue(bundle.exists())

    def test_release_gc_only_preserves_bundle_when_process_quotes_are_unknown(self):
        bundle = self._bundle()
        alias = self.root / "dependency alias"
        alias.symlink_to(bundle)
        self.ps_stdout = f"node --require '{alias}/node_modules/fixture.js\n"
        self._gc()
        self.assertTrue(bundle.exists())

    def test_release_gc_only_reclaims_bundle_with_unrelated_quoted_process(self):
        bundle = self._bundle()
        unrelated = self.root / "unrelated dependency"
        unrelated.mkdir()
        (unrelated / "fixture.js").write_text("unrelated fixture\n")
        self.ps_stdout = f"node --require '{unrelated}/fixture.js' worker.js\n"
        self._gc()
        self.assertFalse(bundle.exists())

    def test_release_gc_only_reclaims_bundle_with_unrelated_process_apostrophe(self):
        bundle = self._bundle()
        unrelated = self.root / "unrelated fixture.js"
        unrelated.write_text("unrelated fixture\n")
        self.ps_stdout = f"node --message don't --require {unrelated} worker.js\n"
        self._gc()
        self.assertFalse(bundle.exists())

    def test_release_gc_only_preserves_bundle_when_process_alias_resolution_is_unknown(self):
        bundle = self._bundle()
        alias = self.root / "dependency alias"
        alias.symlink_to(bundle)
        self.ps_stdout = f"node --require '{alias}/node_modules/fixture.js' worker.js\n"
        resolve = Path.resolve
        def unavailable_alias(path, *args, **kwargs):
            if os.fspath(path).startswith(str(alias)):
                raise PermissionError(errno.EACCES, "fixture alias probe unavailable")
            return resolve(path, *args, **kwargs)
        with mock.patch.object(Path, "resolve", unavailable_alias):
            _code, result = self._gc()
        self.assertTrue(bundle.exists())
        self.assertGreater(result["errors"], 0)

    def test_release_gc_gives_reference_scan_a_fresh_budget_after_lock_wait(self):
        bundle = self._bundle()
        self._release(bundle)
        clock = [0.0]
        probe = self._probe

        def process_probe(command, **kwargs):
            if Path(command[0]).name == "ps":
                clock[0] += 2
            return probe(command, **kwargs)

        @contextmanager
        def delayed_lock(_current, _deadline):
            clock[0] = 14
            yield

        with mock.patch.object(self.cleanup.time, "monotonic", side_effect=lambda: clock[0]), \
             mock.patch.object(self.cleanup, "_source_reclaim_lock", delayed_lock), \
             mock.patch.object(self, "_probe", side_effect=process_probe):
            code, result = self._gc()

        self.assertEqual(code, 0, result)
        self.assertFalse(bundle.exists(), "lock wait must not consume the reference census budget")

    def test_release_gc_waits_for_a_90_second_admission_lock_owner(self):
        import fcntl

        bundle = self._bundle()
        self._release(bundle)
        admission_lock = os.open(self.loops / ".admission-protocol.lock",
                                 os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(admission_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        clock = [0.0]
        released = [False]

        def advance(seconds):
            clock[0] += seconds
            if clock[0] >= 90 and not released[0]:
                fcntl.flock(admission_lock, fcntl.LOCK_UN)
                released[0] = True

        try:
            with mock.patch.object(self.cleanup.time, "monotonic", side_effect=lambda: clock[0]), \
                 mock.patch.object(self.cleanup.time, "sleep", side_effect=advance):
                code, result = self._gc()
        finally:
            if not released[0]:
                fcntl.flock(admission_lock, fcntl.LOCK_UN)
            os.close(admission_lock)

        self.assertEqual(code, 0, result)
        self.assertTrue(released[0])
        self.assertFalse(bundle.exists(), "release GC must resume after its admission-lock owner exits")

    def test_release_gc_gives_bundle_scan_a_fresh_budget_after_release_scan(self):
        bundle = self._bundle()
        self._release(bundle)
        clock = [0.0]
        ps_calls = [0]
        lsof_calls = [0]
        probe = self._probe

        def slow_release_scan(command, **kwargs):
            tool = Path(command[0]).name
            if tool == "ps":
                ps_calls[0] += 1
                result = probe(command, **kwargs)
                if ps_calls[0] == 1:
                    clock[0] += 14
                return result
            if tool == "lsof":
                lsof_calls[0] += 1
                if lsof_calls[0] == 2 and kwargs.get("timeout", 0) < 2:
                    raise subprocess.TimeoutExpired(command, kwargs["timeout"])
            return probe(command, **kwargs)

        output = io.StringIO()
        with mock.patch.object(self.cleanup.time, "monotonic", side_effect=lambda: clock[0]), \
             mock.patch.object(subprocess, "run", side_effect=slow_release_scan), \
             mock.patch.object(subprocess, "Popen", side_effect=AssertionError("host subprocess forbidden")), \
             mock.patch.object(subprocess, "check_output", side_effect=AssertionError("host subprocess forbidden")), \
             mock.patch.dict(os.environ, {"LIFE_MANAGER_RELEASE_KEEP": "0"}), \
             mock.patch.object(sys, "argv", ["central_cleanup.py", "--release-gc-only"]), \
             redirect_stdout(output):
            code = self.cleanup.main()
        result = json.loads(output.getvalue())

        self.assertEqual(code, 0, result)
        self.assertFalse(bundle.exists(), "bundle scan must receive its own bounded reference budget")

    def test_release_gc_only_reclaims_bundle_with_long_multiline_process_inventory(self):
        bundle = self._bundle()
        executable = self.root / "unrelated-process"
        executable.write_text("unrelated fixture\n")
        self.ps_stdout = "\n".join(f"{executable} --payload {'x' * 300}" for _ in range(40))
        resolve = Path.resolve
        def bounded_resolve(path, *args, **kwargs):
            if "\n" in os.fspath(path):
                raise OSError(errno.ENAMETOOLONG, "fixture path exceeds native path bound")
            return resolve(path, *args, **kwargs)
        with mock.patch.object(Path, "resolve", bounded_resolve):
            code, result = self._gc()
        self.assertEqual(code, 0, result)
        self.assertFalse(bundle.exists())

    def test_release_gc_only_deduplicates_alias_resolution_within_snapshot_budget(self):
        bundle = self._bundle()
        unrelated = self.root / "unrelated"
        unrelated.mkdir()
        alias = self.root / "repeated alias"
        alias.symlink_to(unrelated)
        for index in range(12):
            (self.agents / f"ai.anicca.repeated-{index}.plist").write_bytes(plistlib.dumps({
                "ProgramArguments": [str(alias), str(alias)],
            }))
        self.ps_stdout = f"node --require='{alias}' worker.js\n" * 12
        clock = [0.0]
        resolve = Path.resolve
        def costly_alias(path, *args, **kwargs):
            if os.fspath(path) == str(alias):
                clock[0] += 4
            return resolve(path, *args, **kwargs)
        with mock.patch.object(Path, "resolve", costly_alias), \
             mock.patch.object(self.cleanup.time, "monotonic", side_effect=lambda: clock[0]):
            code, result = self._gc()
        self.assertFalse(bundle.exists(), "duplicate resolution exhausted the unchanged reference budget")
        self.assertEqual(code, 0, result)
        self.assertLess(clock[0], 15)
        self.assertEqual(sum(Path(command[0]).name == "lsof" for command in self.commands), 3)

    def test_release_gc_only_rechecks_same_alias_in_final_reference_snapshot(self):
        bundle = self._bundle()
        unrelated = self.root / "unrelated"
        unrelated.mkdir()
        (unrelated / "fixture.js").write_text("unrelated fixture\n")
        alias = self.root / "changing alias"
        alias.symlink_to(unrelated)
        self.ps_stdout = f"node --require '{alias}/fixture.js' worker.js\n"
        collect = self.cleanup._bundle_references
        snapshots = [0]
        def references(*args, **kwargs):
            snapshots[0] += 1
            if snapshots[0] == 3:
                alias.unlink()
                alias.symlink_to(bundle / "node_modules")
            return collect(*args, **kwargs)
        with mock.patch.object(self.cleanup, "_bundle_references", side_effect=references):
            _code, result = self._gc()
        self.assertEqual(snapshots[0], 3)
        self.assertTrue(bundle.exists())
        self.assertEqual(result["dependency_bundles"]["removed"], 0)
        self.assertEqual(stat.S_IMODE(bundle.stat().st_mode), 0o555)

    def test_release_gc_only_walks_regular_files_within_reference_budget(self):
        bundle = self._bundle()
        release = self._release(bundle)
        release.chmod(0o755)
        nested = release / "ordinary" / "nested"
        nested.mkdir(parents=True)
        for index in range(40):
            (nested / f"source-{index}.py").write_text("pass\n")
        self._seal(release)
        clock = [0.0]
        lstat = os.lstat

        def costly_metadata(path, *args, **kwargs):
            if Path(path).parent == nested:
                clock[0] += .5
            return lstat(path, *args, **kwargs)

        with mock.patch.object(os, "lstat", costly_metadata), \
             mock.patch.object(self.cleanup.time, "monotonic", side_effect=lambda: clock[0]):
            code, result = self._gc(keep=1)
        self.assertEqual(code, 0, result)
        self.assertTrue(release.exists() and bundle.exists())
        self.assertLess(clock[0], 15)

    def test_release_gc_only_preserves_deep_file_and_directory_links_without_following_them(self):
        primary = self._bundle()
        file_bundle = self._bundle("b" * 64)
        directory_bundle = self._bundle("c" * 64)
        release = self._release(primary)
        release.chmod(0o755)
        nested = release / "deep" / "nested"
        nested.mkdir(parents=True)
        (nested / "file-link").symlink_to(file_bundle / "node_modules/fixture.js")
        (nested / "directory-link").symlink_to(directory_bundle / "node_modules")
        (nested / "cycle").symlink_to(release)
        self._seal(release)
        scandir = os.scandir

        def no_link_descent(path):
            if any(Path(path).is_relative_to(bundle) for bundle in (primary, file_bundle, directory_bundle)) or Path(path).is_symlink():
                raise AssertionError("reference walk followed a dependency or cyclic link")
            return scandir(path)

        with mock.patch.object(os, "scandir", side_effect=no_link_descent):
            code, result = self._gc(keep=1)
        self.assertEqual(code, 0, result)
        for bundle in (primary, file_bundle, directory_bundle):
            self.assertTrue((bundle / "node_modules/fixture.js").is_file())

    def test_release_gc_only_preserves_everything_when_tree_inventory_fails_or_expires(self):
        bundle = self._bundle()
        release = self._release(bundle)
        release.chmod(0o755)
        nested = release / "nested"
        nested.mkdir()
        for name in ("first.py", "second.py"):
            (nested / name).write_text("pass\n")
        self._seal(release)
        scandir = os.scandir

        for failure in ("open", "iteration", "deadline"):
            with self.subTest(failure=failure):
                clock = [0.0]

                @contextmanager
                def interrupted_scan(path):
                    if Path(path) == nested and failure == "open":
                        raise PermissionError("fixture inventory unavailable")
                    with scandir(path) as entries:
                        def interrupted_entries():
                            yield next(entries)
                            if failure == "iteration":
                                raise PermissionError("fixture inventory interrupted")
                            clock[0] = 31
                            yield from entries
                        yield interrupted_entries() if Path(path) == nested else entries

                with mock.patch.object(os, "scandir", side_effect=interrupted_scan), \
                     mock.patch.object(self.cleanup.time, "monotonic", side_effect=lambda: clock[0]):
                    code, result = self._gc(keep=0)
                self.assertEqual(code, 1, result)
                self.assertGreater(result["errors"], 0)
                self.assertEqual(result["removed_releases"], 0)
                self.assertEqual(result["reclaimed_bytes"], 0)
                self.assertTrue(release.exists() and bundle.exists())

    def test_release_gc_only_preserves_everything_when_last_empty_directory_expires(self):
        bundle = self._bundle()
        release = self._release(bundle)
        empty = release / "bin"
        empty.chmod(0o755)
        (empty / "run.py").unlink()
        empty.chmod(0o555)
        clock = [0.0]
        scandir = os.scandir

        @contextmanager
        def delayed_empty_scan(path):
            with scandir(path) as entries:
                yield entries
            if not isinstance(path, int) and Path(path) == empty:
                clock[0] = 31

        with mock.patch.object(os, "scandir", side_effect=delayed_empty_scan), \
             mock.patch.object(self.cleanup.time, "monotonic", side_effect=lambda: clock[0]):
            code, result = self._gc(keep=0)
        self.assertEqual(code, 1, result)
        self.assertEqual(result["removed_releases"], 0)
        self.assertEqual(result["reclaimed_bytes"], 0)
        self.assertTrue(release.exists() and bundle.exists())

    def test_release_gc_only_preserves_fd_opened_before_final_reference_snapshot(self):
        bundle = self._bundle()
        collect = self.cleanup._bundle_references
        snapshots = [0]
        def references(*args, **kwargs):
            snapshots[0] += 1
            if snapshots[0] == 3:
                self.lsof_stdout = f"p{os.getpid()}\nf999999\nn{bundle}/node_modules/fixture.js\n"
            return collect(*args, **kwargs)
        with mock.patch.object(self.cleanup, "_bundle_references", side_effect=references):
            _code, result = self._gc()
        self.assertEqual(sum(Path(command[0]).name == "lsof" for command in self.commands), 3)
        self.assertTrue(bundle.exists())
        self.assertEqual(result["dependency_bundles"]["removed"], 0)
        self.assertEqual(stat.S_IMODE(bundle.stat().st_mode), 0o555)

    def test_release_gc_only_preserves_all_artifacts_when_reference_snapshot_expires(self):
        bundle = self._bundle()
        release = self._release(bundle)
        referenced = self._bundle("b" * 64)
        alias = self.root / "held alias"
        alias.symlink_to(referenced / "node_modules")
        unrelated = self.root / "unrelated"
        unrelated.write_text("unrelated fixture\n")
        alias_path = str(alias / "fixture.js")
        self.ps_stdout = f"node --require '{alias_path}' {unrelated}\n"
        resolve = Path.resolve
        def expired_path(path, *args, **kwargs):
            if os.fspath(path) in {alias_path, str(unrelated)}:
                raise subprocess.TimeoutExpired("reference path resolution", 0)
            return resolve(path, *args, **kwargs)
        with mock.patch.object(Path, "resolve", expired_path):
            code, result = self._gc(keep=1)
        self.assertTrue(release.exists())
        self.assertTrue(bundle.exists())
        self.assertTrue(referenced.exists())
        self.assertEqual(code, 1, result)
        self.assertFalse(result["ok"])
        self.assertEqual(result["removed_releases"], 0)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["deferred"], 1)
        self.assertEqual(result["dependency_bundles"]["status"], "deferred")
        self.assertEqual(result["source_reclaim"]["status"], "deferred")
        self.assertEqual(result["dependency_bundles"]["diagnostic"], {
            "phase": "reference_path_resolution", "timeout_seconds": 0,
            "retryable": True, "next_action": "retry_next_scheduled_run",
        })

    def test_release_gc_only_timeout_diagnostic_omits_untrusted_command(self):
        bundle = self._bundle()
        self._release(bundle)
        failure = subprocess.TimeoutExpired(["/private/secret/token", "argument"], float("inf"))
        with mock.patch.object(self.cleanup, "_bundle_references", side_effect=failure):
            _code, result = self._gc()

        self.assertEqual(result["dependency_bundles"]["diagnostic"], {
            "phase": "reference_subprocess", "retryable": True,
            "next_action": "retry_next_scheduled_run",
        })
        self.assertNotIn("/private/secret/token", json.dumps(result))

    def test_release_gc_only_preserves_unowned_fd_even_in_its_own_process(self):
        bundle = self._bundle()
        self.lsof_stdout = f"p{os.getpid()}\nf999999\nn{bundle}/node_modules/fixture.js\n"
        self._gc()
        self.assertTrue(bundle.exists())

    def test_release_gc_only_preserves_protected_bundle_stores(self):
        paths = ("nested/memory/owner.md", "nested/state/events.jsonl", ".lm-protected")
        bundles = [self._bundle(f"{index:064x}", protected_path=path)
                   for index, path in enumerate(paths, 1)]
        self._gc()
        for bundle, path in zip(bundles, paths):
            self.assertEqual((bundle / path).read_text(), "protected fixture\n")

    def test_release_gc_only_reclaims_regular_dependency_source_names(self):
        bundle = self._bundle(protected_path="node_modules/sessions/credentials/wallet.js")
        memory_file = self._bundle("b" * 64, protected_path="node_modules/memory")
        self._gc()
        self.assertFalse(bundle.exists())
        self.assertFalse(memory_file.exists())

    def test_release_gc_only_preserves_state_directory_symlink(self):
        bundle = self._bundle(protected_path="node_modules/journal/events.jsonl")
        modules = bundle / "node_modules"
        modules.chmod(0o755)
        (modules / "state").symlink_to("journal", target_is_directory=True)
        modules.chmod(0o555)
        self._gc()
        self.assertTrue(bundle.exists())

    def test_release_gc_only_never_chmods_hardlinked_files(self):
        bundle = self._bundle()
        outside = self.root / "external-hardlink"
        os.link(bundle / "node_modules/fixture.js", outside)
        self._gc()
        self.assertFalse(bundle.exists())
        self.assertEqual(outside.read_text(), "sealed dependency\n")
        self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o444)

    def test_release_gc_only_preserves_bundle_when_fd_inventory_is_unknown(self):
        bundle = self._bundle()
        release = self._release(bundle)
        for code, stderr in ((1, ""), (0, "coverage gap")):
            with self.subTest(code=code, stderr=stderr):
                self.lsof_code, self.lsof_stderr = code, stderr
                self._gc()
                self.assertTrue(bundle.exists())
                self.assertTrue(release.exists())

    def test_release_gc_only_preserves_bundle_when_process_inventory_is_unknown(self):
        bundle = self._bundle()
        self.ps_code = 1
        self._gc()
        self.assertTrue(bundle.exists())

    def test_release_gc_only_preserves_bundle_when_plist_fallback_fails(self):
        bundle = self._bundle()
        (self.agents / "ai.anicca.fixture.plist").write_text("<plist><dict>malformed")
        self._gc()
        self.assertTrue(bundle.exists())

    def test_release_gc_only_accepts_native_plist_fallback_before_bundle_reclaim(self):
        bundle = self._bundle()
        (self.agents / "ai.anicca.fixture.plist").write_text("<plist><dict>malformed")
        unrelated = self.root / "unrelated-fixture"
        unrelated.write_text("unrelated executable fixture\n")
        self.native_plist = {"ProgramArguments": [str(unrelated)]}
        self._gc()
        self.assertFalse(bundle.exists(), "valid native plist fallback must permit safe bundle reclaim")

    def test_release_gc_only_preserves_bundle_when_pins_are_unknown(self):
        bundle = self._bundle()
        self.protected.write_text("{")
        self._gc()
        self.assertTrue(bundle.exists())

    def test_release_gc_only_preserves_bundle_for_dangling_current(self):
        bundle = self._bundle()
        (self.loops / "current").symlink_to(self.releases / "missing")
        self._gc()
        self.assertTrue(bundle.exists())

    def test_release_gc_only_preserves_bundle_with_other_cut_lock_owner(self):
        bundle = self._bundle()
        release = self._release(bundle)
        lock = self.loops / ".release-cut.lock"
        lock.mkdir()
        (lock / "pid").write_text(str(os.getpid()) + "\n")
        inode = lock.stat().st_ino
        self._gc()
        self.assertTrue(bundle.exists())
        self.assertTrue(release.exists())
        self.assertEqual(lock.stat().st_ino, inode)
        self.assertEqual((lock / "pid").read_text(), str(os.getpid()) + "\n")

    def test_release_gc_only_borrows_exact_parent_cut_lock_without_removing_it(self):
        bundle = self._bundle()
        lock = self.loops / ".release-cut.lock"
        lock.mkdir()
        (lock / "pid").write_text(str(os.getppid()) + "\n")
        inode = lock.stat().st_ino
        self._gc()
        self.assertFalse(bundle.exists())
        self.assertEqual(lock.stat().st_ino, inode)
        self.assertEqual((lock / "pid").read_text(), str(os.getppid()) + "\n")

    def test_release_gc_only_preserves_foreign_uid_and_changed_bundle_inode(self):
        bundle = self._bundle()
        expected = bundle.stat()
        fstat = os.fstat
        for field, value in ((4, os.getuid() + 1), (1, expected.st_ino + 1)):
            with self.subTest(field=field):
                def changed_info(descriptor):
                    info = fstat(descriptor)
                    if (info.st_dev, info.st_ino) == (expected.st_dev, expected.st_ino):
                        values = list(info)
                        values[field] = value
                        return os.stat_result(values)
                    return info
                with mock.patch.object(os, "fstat", side_effect=changed_info):
                    self._gc()
                self.assertEqual(bundle.stat().st_ino, expected.st_ino)
                self.assertEqual(stat.S_IMODE(bundle.stat().st_mode), 0o555)

    def test_release_gc_only_preserves_incomplete_or_writable_bundle(self):
        incomplete = self._bundle("b" * 64)
        incomplete.chmod(0o755)
        (incomplete / ".complete").unlink()
        incomplete.chmod(0o555)
        writable = self._bundle("c" * 64)
        writable.chmod(0o755)
        writable_leaf = self._bundle("d" * 64)
        (writable_leaf / "node_modules/fixture.js").chmod(0o644)
        wrong_marker = self._bundle("e" * 64)
        marker = wrong_marker / ".complete"
        marker.chmod(0o644)
        marker.write_text("f" * 64 + "\n")
        marker.chmod(0o444)
        self._gc()
        self.assertTrue(incomplete.exists())
        self.assertTrue(writable.exists())
        self.assertTrue(writable_leaf.exists())
        self.assertTrue(wrong_marker.exists())


if __name__ == "__main__":
    unittest.main()
