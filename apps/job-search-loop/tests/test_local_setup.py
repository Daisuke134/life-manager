import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]


class LocalSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.config = self.root / "config"
        self.state = self.root / "state"
        self.data = self.root / "data"
        self.codex_home = self.root / "codex-home"
        self.bin = self.root / "bin"
        self.bin.mkdir(parents=True)
        self.codex_home.mkdir()
        self.codex_auth = self.codex_home / "auth.json"
        self.codex_auth.write_text('{"test":"credential"}\n', encoding="utf-8")
        self.codex_auth.chmod(0o600)
        self.profile = self.root / "source-profile.json"
        self.resume = self.root / "resume.pdf"
        self.resume.write_bytes(b"%PDF-1.4\nportable resume\n")
        self.profile.write_text(
            json.dumps(
                {
                    "version": 1,
                    "candidate": {"name": "Portable Candidate"},
                    "materials": {
                        "resumes": {"engineering": str(self.resume)}
                    },
                    "facts": [
                        {
                            "id": "verified-experience",
                            "claim": "Built verified AI systems.",
                            "evidence": "User-supplied private source",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def _write_executable(self, name: str, body: str) -> Path:
        path = self.bin / name
        path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        path.chmod(0o700)
        return path

    def _env(self) -> dict[str, str]:
        return {
            **os.environ,
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.config),
            "XDG_STATE_HOME": str(self.state),
            "XDG_DATA_HOME": str(self.data),
            "CODEX_HOME": str(self.codex_home),
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "PYTHONPATH": str(APP_ROOT),
        }

    def _run(self, *extra: str, env: dict[str, str] | None = None):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "job_search_loop.local_setup",
                "--profile",
                str(self.profile),
                *extra,
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env or self._env(),
        )

    def test_auto_selects_authenticated_codex_and_creates_private_install(self):
        self._write_executable(
            "codex",
            'test "$1" = "login" && test "$2" = "status" && '
            'printf "Logged in using ChatGPT\\n"',
        )

        result = self._run("--provider", "auto", "--scheduler", "none")

        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        profile = self.config / "anicca" / "job-search" / "profile.json"
        install = self.config / "anicca" / "job-search" / "install.json"
        auth_alias = self.config / "anicca" / "job-search" / "codex-auth.json"
        self.assertEqual(receipt["provider"], "codex")
        self.assertEqual(receipt["scheduler"], "none")
        self.assertEqual(receipt["profile_path"], str(profile))
        self.assertEqual(profile.stat().st_mode & 0o777, 0o600)
        self.assertEqual(install.stat().st_mode & 0o777, 0o600)
        self.assertEqual(profile.parent.stat().st_mode & 0o777, 0o700)
        self.assertTrue(auth_alias.is_symlink())
        self.assertEqual(auth_alias.resolve(strict=True), self.codex_auth.resolve())
        self.assertEqual(
            (self.state / "anicca" / "job-search").stat().st_mode & 0o777,
            0o700,
        )
        self.assertEqual(
            (self.data / "anicca" / "job-search").stat().st_mode & 0o777,
            0o700,
        )
        manifest = self.data / "anicca/job-search/materials/manifest.v1.json"
        self.assertEqual(manifest.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(manifest.read_text())["resumes"], {
            "engineering": "resumes/engineering.pdf",
            "japanese": "resumes/japanese.pdf",
            "technical_business": "resumes/technical_business.pdf",
        })
        encoded = install.read_text(encoding="utf-8")
        self.assertNotIn("Logged in using ChatGPT", encoded)
        self.assertNotIn("token", encoded.lower())
        self.assertNotIn("/Users/anicca", encoded)

    def test_auto_does_not_fall_through_to_authenticated_claude(self):
        self._write_executable("codex", "exit 1")
        self._write_executable(
            "claude",
            'test "$1" = "auth" && test "$2" = "status" && '
            "printf '%s\\n' '{\"loggedIn\":true,\"authMethod\":\"oauth_token\"}'",
        )

        result = self._run("--provider", "auto", "--scheduler", "none")

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("claude-direct", result.stdout)
        self.assertFalse(
            (self.config / "anicca" / "job-search" / "profile.json").exists()
        )

    def test_explicit_provider_fails_closed_when_auth_is_missing(self):
        self._write_executable("codex", "exit 1")

        result = self._run("--provider", "codex", "--scheduler", "none")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("authenticated provider", result.stderr)
        self.assertFalse(
            (self.config / "anicca" / "job-search" / "profile.json").exists()
        )

    def test_relative_xdg_override_fails_closed(self):
        env = self._env()
        env["XDG_CONFIG_HOME"] = "relative-config"

        result = self._run("--provider", "auto", "--scheduler", "none", env=env)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absolute", result.stderr)

    def test_existing_profile_is_preserved_without_explicit_replace(self):
        self._write_executable(
            "codex",
            'test "$1" = "login" && test "$2" = "status"',
        )
        first = self._run("--provider", "codex", "--scheduler", "none")
        self.assertEqual(first.returncode, 0, first.stderr)
        installed = self.config / "anicca" / "job-search" / "profile.json"
        before = installed.read_bytes()
        self.profile.write_text(
            self.profile.read_text(encoding="utf-8").replace(
                "Portable Candidate", "Replacement Candidate"
            ),
            encoding="utf-8",
        )

        second = self._run("--provider", "codex", "--scheduler", "none")

        self.assertNotEqual(second.returncode, 0)
        self.assertIn("already exists", second.stderr)
        self.assertEqual(installed.read_bytes(), before)

        replaced = self._run(
            "--provider",
            "codex",
            "--scheduler",
            "none",
            "--replace-profile",
        )
        self.assertEqual(replaced.returncode, 0, replaced.stderr)
        self.assertIn("Replacement Candidate", installed.read_text(encoding="utf-8"))

    def test_runtime_paths_use_only_the_canonical_router(self):
        self._write_executable(
            "codex",
            'test "$1" = "login" && test "$2" = "status"',
        )
        setup = self._run("--provider", "codex", "--scheduler", "none")
        self.assertEqual(setup.returncode, 0, setup.stderr)

        result = subprocess.run(
            [
                "/bin/zsh",
                "-c",
                (
                    f'source "{APP_ROOT / "scripts" / "runtime-paths.sh"}"; '
                    'printf "%s|%s" "${AGENT_RUNNER_PROVIDER-unset}" "$AGENT_RUNNER_CONFIG"'
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=self._env(),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            f"unset|{APP_ROOT.parents[1] / 'runtime' / 'agent-runner' / 'config.json'}",
        )

    def test_install_local_none_is_a_clean_home_end_to_end(self):
        self._write_executable(
            "codex",
            'test "$1" = "login" && test "$2" = "status"',
        )

        result = subprocess.run(
            [
                "/bin/zsh",
                str(APP_ROOT / "scripts" / "install-local.sh"),
                "--profile",
                str(self.profile),
                "--provider",
                "auto",
                "--scheduler",
                "none",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=self._env(),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt["provider"], "codex")
        self.assertEqual(receipt["scheduler"], "none")
        self.assertTrue(Path(receipt["profile_path"]).is_file())
        self.assertFalse((self.home / "Library" / "LaunchAgents").exists())
        self.assertFalse((self.config / "systemd" / "user").exists())

    def test_installer_preserves_profile_when_source_is_active_destination(self):
        self._write_executable(
            "codex",
            'test "$1" = "login" && test "$2" = "status"',
        )
        active = self.config / "anicca" / "job-search" / "profile.json"
        active.parent.mkdir(parents=True)
        active.write_bytes(self.profile.read_bytes())
        active.chmod(0o600)
        before = active.read_bytes()

        result = subprocess.run(
            [
                "/bin/zsh",
                str(APP_ROOT / "scripts" / "install-local.sh"),
                "--profile",
                str(active),
                "--provider",
                "codex",
                "--scheduler",
                "none",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=self._env(),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(active.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
