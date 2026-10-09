import os
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class CutLoopReleasePressureTest(unittest.TestCase):
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
            cleanup = repo / "runtime/loop/central_cleanup.py"
            cleanup.parent.mkdir(parents=True)
            cleanup.write_text("raise SystemExit(0)\n", encoding="utf-8")
            (repo / "old.txt").write_text("old\n", encoding="utf-8")
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
            subprocess.run(["chmod", "-R", "a-w", str(donor)], check=True)
            (loops / "current").symlink_to(donor)

            (repo / "old.txt").unlink()
            (repo / "new.txt").write_text("new\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "new"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=repo, check=True, capture_output=True)
            result, _ = self.run_cut(
                repo, home, "", LOOPS_ACTIVATE_CURRENT="0", LOOPS_KEEP_RELEASES="2",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            releases = [candidate for candidate in (loops / "releases").iterdir()
                        if candidate != donor]
            self.assertEqual(len(releases), 1)
            release = releases[0]
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
