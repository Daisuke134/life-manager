import os
import json
import shutil
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path

from runtime.loop.loop_cleanup import _release_immutable_store_probe


class CutLoopReleasePressureTest(unittest.TestCase):
    def test_full_release_capacity_defers_before_export(self):
        source = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            repo = home / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
            for key, value in (("user.email", "test@example.invalid"), ("user.name", "Test")):
                subprocess.run(["git", "config", key, value], cwd=repo, check=True)
            for relative in ("bin/cut-loop-release.sh", "runtime/host/disk_admission.py"):
                target = repo / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / relative, target)
            cleanup = repo / "runtime/loop/central_cleanup.py"
            cleanup.parent.mkdir(parents=True)
            cleanup.write_text("import os,pathlib\npathlib.Path(os.environ[\"LOOPS_ROOT\"]).parent.joinpath(\"cleanup-ran\").write_text(\"1\")\n")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=repo, check=True)
            probe = home / "capacity-probe"
            probe.mkdir()
            (probe / "sitecustomize.py").write_text(
                "import shutil,types\nshutil.disk_usage=lambda p: types.SimpleNamespace(free=0)\n")
            for paths in ("", "\t "):
                with self.subTest(paths=paths):
                    result, loops = self.run_cut(repo, home, paths, LOOPS_ACTIVATE_CURRENT="0", PYTHONPATH=str(probe))
                    self.assertEqual(result.returncode, 75, result.stderr)
                    self.assertEqual(json.loads(result.stdout.strip())["reason"], "disk_headroom_low")
                    self.assertTrue((home / "cleanup-ran").is_file())
                    self.assertEqual(list((loops / "releases").iterdir()), [])
                    self.assertFalse((loops / ".release-cut.lock").exists())

    def test_unchanged_complete_release_uses_measured_budget(self):
        source = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            repo = home / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
            for key, value in (("user.email", "test@example.invalid"), ("user.name", "Test")):
                subprocess.run(["git", "config", key, value], cwd=repo, check=True)
            for relative in ("bin/cut-loop-release.sh", "runtime/host/disk_admission.py"):
                target = repo / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / relative, target)
            cleanup = repo / "runtime/loop/central_cleanup.py"
            cleanup.parent.mkdir(parents=True)
            cleanup.write_text("raise SystemExit(0)\n")
            (repo / "package.json").write_text("{}\n")
            (repo / "package-lock.json").write_text("{}\n")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=repo, check=True)
            probe = home / "capacity-probe"
            probe.mkdir()
            (probe / "sitecustomize.py").write_text("import shutil,types\nshutil.disk_usage=lambda p: types.SimpleNamespace(free=1024**3)\n")
            loops = home / "loops"
            donor = loops / "releases/donor"
            subprocess.run(["git", "clone", "--local", str(repo), str(donor)], check=True, capture_output=True)
            shutil.rmtree(donor / ".git")
            import hashlib, platform
            header = "\0".join(("command","npm-ci --omit=dev --ignore-scripts","os",platform.system(),"arch",platform.machine(),"node","v-test","npm","test")) + "\0"
            key_data = header.encode()
            for label in ("package-json","package-lock"):
                key_data += label.encode() + b"\0" + (hashlib.sha256(b"{}\n").hexdigest() + "  -\n").encode()
            key = hashlib.sha256(key_data).hexdigest()
            bundle = loops / "dependency-bundles" / ("npm-" + key)
            (bundle / "node_modules").mkdir(parents=True)
            (bundle / "node_modules/.package-lock.json").write_text("{}\n")
            (bundle / ".complete").write_text(key + "\n")
            (donor / "node_modules").symlink_to(bundle / "node_modules")
            subprocess.run(["chmod","-R","a-w",str(bundle)],check=True)
            descriptor = {"sha": subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True).strip(), "release_paths":"ALL", "provenance":"ancestor-of-origin-main", "runtime_python":str(Path(sys.executable).resolve()), "runtime_python_cache_tag":sys.implementation.cache_tag}
            (donor / "RELEASE.json").write_text(json.dumps(descriptor))
            subprocess.run(["chmod","-R","a-w",str(donor)],check=True)
            (loops / "current").symlink_to(donor)
            result, _ = self.run_cut(repo, home, "", LOOPS_ACTIVATE_CURRENT="0", PYTHONPATH=str(probe), NPM_NODE_VERSION="v-test", NPM_VERSION="test", LOOPS_RUNTIME_PYTHON=sys.executable)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual((donor / "RELEASE.json").read_text(), json.dumps(descriptor))
            self.assertEqual((loops / "current").resolve(), donor.resolve())
            (repo / "payload.txt").write_text("new source\n")
            subprocess.run(["git","add","."],cwd=repo,check=True)
            subprocess.run(["git","commit","-m","source change"],cwd=repo,check=True,capture_output=True)
            subprocess.run(["git","update-ref","refs/remotes/origin/main","HEAD"],cwd=repo,check=True)
            bundle.chmod(0o755)
            (bundle / ".complete").unlink()
            result, _ = self.run_cut(repo, home, "", LOOPS_ACTIVATE_CURRENT="0", PYTHONPATH=str(probe), NPM_NODE_VERSION="v-test", NPM_VERSION="test", LOOPS_RUNTIME_PYTHON=sys.executable)
            self.assertEqual(result.returncode,75,result.stderr + result.stdout)
            self.assertEqual(len(list((loops / "releases").iterdir())),2)
            (bundle / ".complete").write_text(key + "\n")
            (bundle / ".complete").chmod(0o444)
            bundle.chmod(0o555)
            # Only one clone temporary exists at a time; the full export is never copied twice.
            for index in range(5):
                (repo / f"serial-{index}.bin").write_bytes(b"x" * (4 * 1024**2))
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "serial source fixture"], cwd=repo,
                           check=True, capture_output=True)
            subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=repo, check=True)
            (probe / "sitecustomize.py").write_text(
                "import shutil,types\nshutil.disk_usage=lambda p: types.SimpleNamespace(free=96*1024**2)\n")
            result, _ = self.run_cut(repo, home, "", LOOPS_ACTIVATE_CURRENT="0", PYTHONPATH=str(probe),
                NPM_NODE_VERSION="v-test", NPM_VERSION="test", LOOPS_RUNTIME_PYTHON=sys.executable)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            newest = next(p for p in (loops / "releases").iterdir()
                          if (p / "serial-4.bin").is_file())
            self.assertEqual((newest / "serial-4.bin").stat().st_size, 4 * 1024**2)
            self.assertLess(json.loads((newest / "RELEASE.json").read_text())["capacity_required_bytes"],
                            96 * 1024**2)
            # Dependency changes require the ordinary budget before extraction.
            (repo / "package.json").write_text("{}")
            (repo / "package-lock.json").write_text("{}")
            subprocess.run(["git","add","."],cwd=repo,check=True)
            subprocess.run(["git","commit","-m","dependency change"],cwd=repo,check=True,capture_output=True)
            subprocess.run(["git","update-ref","refs/remotes/origin/main","HEAD"],cwd=repo,check=True)
            result, _ = self.run_cut(repo, home, "", LOOPS_ACTIVATE_CURRENT="0", PYTHONPATH=str(probe), NPM_NODE_VERSION="v-test", NPM_VERSION="test", LOOPS_RUNTIME_PYTHON=sys.executable)
            self.assertEqual(result.returncode,75,result.stderr + result.stdout)
            self.assertEqual(len(list((loops / "releases").iterdir())),3)

    def run_cut(self, repo: Path, home: Path, paths: str, **extra_env: str):
        pressure = home / ".local" / "state" / "life-manager" / "state" / "disk-pressure.block"
        pressure.parent.mkdir(parents=True, exist_ok=True)
        pressure.write_text('{"tier":"PRESSURE"}\n', encoding="utf-8")
        loops = home / "loops"
        result = subprocess.run(
            ["bash", str(repo / "bin/cut-loop-release.sh"), "HEAD"],
            cwd=repo,
            env={
                **os.environ,
                "HOME": str(home),
                "LOOPS_ROOT": str(loops),
                "LIFE_MANAGER_RESOURCE_ADMISSION_ROOT": str(home / "admission"),
                "LIFE_MANAGER_DISK_PRESSURE_FILE": str(pressure),
                "LIFE_MANAGER_SOURCE_REPO": str(repo),
                "LOOPS_RELEASE_PATHS": paths,
                "NPM_BIN": "",
                **extra_env,
            },
            capture_output=True,
            text=True,
            check=False,
        )
        return result, loops

    def test_pressure_marker_does_not_block_sparse_release(self) -> None:
        repo = Path(__file__).resolve().parents[3]

        with tempfile.TemporaryDirectory() as raw_home:
            home = Path(raw_home)
            trace = home / "git.trace"
            result, loops = self.run_cut(
                repo, home, "runtime/loop/runtime_event.py", LOOPS_ACTIVATE_CURRENT="0", GIT_TRACE=str(trace),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotRegex(trace.read_text(), r"run_command:.*(?:maintenance run|gc).*--auto")
            releases = list((loops / "releases").iterdir())
            self.assertEqual(len(releases), 1)
            self.assertTrue((releases[0] / "RELEASE.json").is_file())

    def test_legacy_archive_size_limit_does_not_block_sparse_release(self) -> None:
        repo = Path(__file__).resolve().parents[3]

        with tempfile.TemporaryDirectory() as raw_home:
            home = Path(raw_home)
            result, loops = self.run_cut(
                repo, home, "runtime/loop/runtime_event.py", LOOPS_ACTIVATE_CURRENT="0",
                LOOPS_PRESSURE_MAX_ARCHIVE_BYTES="1",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            release, = (loops / "releases").iterdir()
            self.assertTrue((release / "runtime/loop/runtime_event.py").is_file())
            self.assertTrue((release / "RELEASE.json").is_file())

    def test_complete_release_reuses_verified_ancestor(self) -> None:
        self._check_complete_release_reuse(clone_failure=False)

    def test_native_clone_failure_keeps_committed_export(self) -> None:
        self._check_complete_release_reuse(clone_failure=True)

    def _check_complete_release_reuse(self, *, clone_failure):
        with tempfile.TemporaryDirectory() as raw_home:
            home = Path(raw_home)
            repo = home / "repo"
            origin = home / "origin.git"
            repo.mkdir()
            subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "release-test@example.invalid"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Release Test"], cwd=repo, check=True)
            subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=repo, check=True)
            (repo / "bin").mkdir()
            shutil.copy2(Path(__file__).resolve().parents[3] / "bin/cut-loop-release.sh",
                         repo / "bin/cut-loop-release.sh")
            attributes = Path(__file__).resolve().parents[3] / ".gitattributes"
            if attributes.is_file():
                shutil.copy2(attributes, repo / ".gitattributes")
            memory = repo / "memory" / "owner.md"
            memory.parent.mkdir()
            memory.write_text("persistent owner memory\n", encoding="utf-8")
            cleanup = repo / "runtime/loop/central_cleanup.py"
            cleanup.parent.mkdir(parents=True)
            cleanup.write_text("raise SystemExit(0)\n", encoding="utf-8")
            shutil.copy2(Path(__file__).resolve().parents[3] / "runtime/loop/loop_cleanup.py",
                         cleanup.with_name("loop_cleanup.py"))
            guard = repo / "runtime/host/disk_admission.py"
            guard.parent.mkdir(parents=True)
            shutil.copy2(Path(__file__).resolve().parents[3] / "runtime/host/disk_admission.py", guard)
            (repo / "old.txt").write_text("old\n", encoding="utf-8")
            (repo / "same.py").write_text("print('same')\n")
            (repo / "changed.py").write_text("print('old')\n")
            (repo / "package.json").write_text('{"name":"release-test","version":"1.0.0"}\n', encoding="utf-8")
            package_lock = '{"name":"release-test","version":"1.0.0","lockfileVersion":3,"packages":{}}\n'
            (repo / "package-lock.json").write_text(package_lock, encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "old"], cwd=repo, check=True, capture_output=True)
            old_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            subprocess.run(["git", "push", "-u", "origin", "main"], cwd=repo, check=True, capture_output=True)

            loops = home / "loops"
            donor = loops / "releases/donor"
            donor.mkdir(parents=True)
            (donor / "old.txt").write_text("old\n", encoding="utf-8")
            shutil.copy2(repo / "same.py", donor / "same.py")
            shutil.copy2(repo / "changed.py", donor / "changed.py")
            dependency = donor / "node_modules/runtime-marker"
            dependency.parent.mkdir()
            dependency.write_text("preserved\n", encoding="utf-8")
            (donor / "node_modules/.package-lock.json").write_text(package_lock, encoding="utf-8")
            shutil.copy2(repo / "package.json", donor / "package.json")
            shutil.copy2(repo / "package-lock.json", donor / "package-lock.json")
            (donor / "RELEASE.json").write_text(json.dumps({
                "sha": old_sha, "release_paths": "ALL",
            }) + "\n", encoding="utf-8")
            (donor / "untracked-diagnostic.log").write_text("legacy diagnostics must not propagate\n", encoding="utf-8")
            donor_memory = donor / "memory" / "owner.md"
            donor_memory.parent.mkdir()
            donor_memory.write_text("existing owner memory\n", encoding="utf-8")
            subprocess.run(["chmod", "-R", "a-w", str(donor)], check=True)
            (loops / "current").symlink_to(donor)

            (repo / "old.txt").unlink()
            (repo / "new.txt").write_text("new\n", encoding="utf-8")
            (repo / "changed.py").write_text("print('new')\n")
            (repo / "same.py").chmod(0o755)
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "new"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=repo, check=True, capture_output=True)
            probe = home / "capacity-probe"
            probe.mkdir()
            (probe / "sitecustomize.py").write_text(
                "import shutil,types\nshutil.disk_usage=lambda p: types.SimpleNamespace(free=16*1024**3)\n")
            if clone_failure:
                with (probe / "sitecustomize.py").open("a") as handle:
                    handle.write("import ctypes\noriginal_cdll=ctypes.CDLL\n"
                                 "def cdll(*a,**kw):\n"
                                 " lib=original_cdll(*a,**kw)\n"
                                 " lib.clonefile=lambda *args: -1\n"
                                 " return lib\nctypes.CDLL=cdll\n")
            result, _ = self.run_cut(
                repo, home, "", LOOPS_ACTIVATE_CURRENT="0", LOOPS_KEEP_RELEASES="2",
                PYTHONPATH=str(probe),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            if sys.platform == "darwin":
                if clone_failure:
                    self.assertIn("source clones: 0", result.stdout)
                else:
                    self.assertRegex(result.stdout, r"source clones: [1-9][0-9]*")
            releases = [candidate for candidate in (loops / "releases").iterdir()
                        if candidate != donor]
            self.assertEqual(len(releases), 1)
            release = releases[0]
            self.assertEqual((release / "same.py").read_text(), "print('same')\n")
            self.assertEqual((release / "same.py").stat().st_mode & 0o777, 0o555)
            self.assertNotEqual((release / "same.py").stat().st_ino,
                                (donor / "same.py").stat().st_ino)
            self.assertEqual((release / "changed.py").read_text(), "print('new')\n")
            self.assertEqual((donor / "changed.py").read_text(), "print('old')\n")
            self.assertFalse((release / "memory").exists(), "source archive copied owner memory")
            self.assertEqual(memory.read_text(), "persistent owner memory\n")
            self.assertEqual(donor_memory.read_text(), "existing owner memory\n")
            self.assertIsNone(_release_immutable_store_probe(release))
            self.assertFalse((release / "untracked-diagnostic.log").exists())
            self.assertEqual((donor / "untracked-diagnostic.log").read_text(), "legacy diagnostics must not propagate\n")
            self.assertFalse((release / "old.txt").exists())
            self.assertEqual((release / "new.txt").read_text(), "new\n")
            self.assertEqual((release / "node_modules/runtime-marker").read_text(), "preserved\n")
            self.assertEqual(
                (release / "node_modules/runtime-marker").stat().st_ino,
                (donor / "node_modules/runtime-marker").stat().st_ino,
            )
            self.assertEqual((donor / "old.txt").read_text(), "old\n")
            self.assertEqual((donor / "node_modules/runtime-marker").stat().st_mode & 0o222, 0)
            self.assertFalse((release / "node_modules/node_modules").exists())
            self.assertEqual(json.loads((release / "RELEASE.json").read_text())["release_paths"], "ALL")

    def test_sparse_release_keeps_required_bin_closure_with_tabs(self) -> None:
        repo = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as raw_home:
            result, loops = self.run_cut(
                repo, Path(raw_home), "bin\truntime/loop/runtime_event.py",
                LOOPS_ACTIVATE_CURRENT="0",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            release, = (loops / "releases").iterdir()
            self.assertTrue((release / "bin/lm-loop-run").is_file())
            self.assertTrue((release / "skills/_shared/browser-state-backup.sh").is_file())

if __name__ == "__main__":
    unittest.main()
