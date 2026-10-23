import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ManagedJobHunterFixture:
    def __init__(self, root):
        root = root.resolve()
        self.root = root
        self.home = root / "owner"
        self.tools = self.home / "bin"
        self.tools.mkdir(parents=True)
        self.repo = root / "repo"
        self.scripts = self.repo / "apps/job-search-loop/scripts"
        self.scripts.mkdir(parents=True)
        for name in ("install-oss.sh", "install-launchd.sh", "runtime-paths.sh"):
            shutil.copy2(ROOT / "apps/job-search-loop/scripts" / name, self.scripts / name)
        shutil.copytree(ROOT / "apps/job-search-loop/launchd", self.scripts.parent / "launchd")
        for relative in ("apps/life-manager/config/product-loop-catalog.json", "config/loop-registry.json",
                         "runtime/host/local_profile.py"):
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        self.calls = root / "calls.jsonl"
        self.release = root / "loops/releases/20261023T000000-aaaaaaaa"
        self.release.mkdir(parents=True)
        self.python = self.executable("python", f'''#!{sys.executable}
import json, os, subprocess, sys
from pathlib import Path
args=sys.argv[1:]
if args[:2] == ["-m", "job_search_loop.connector_preflight"]:
 Path(args[args.index("--output")+1]).parent.mkdir(parents=True,exist_ok=True)
 Path(args[args.index("--output")+1]).write_text(json.dumps({{"telegram":{{"status":"not_configured"}}}}))
 raise SystemExit(0)
if args and args[0] == "-c" and "check_platform_available" in args[1]:
 raise SystemExit(0)
raise SystemExit(subprocess.call([{sys.executable!r}, *args]))
''')
        for name, body in {
            "uname": 'if [ "$1" = -s ]; then echo Darwin; else echo arm64; fi',
            "codex": "exit 0", "plutil": "exit 0",
            "curl": 'printf \'curl %s\\n\' "$*" >> "$FIXTURE_BROWSER_CALLS"',
            "gog": "printf '%s\\n' '{\"accounts\":[{\"email\":\"owner@example.invalid\",\"services\":[\"gmail\"]}]}'",
            "jq": "echo owner@example.invalid",
            "df": "echo 'Filesystem 1024-blocks Used Available Capacity Mounted'; echo 'fixture 9000000 1 8999999 1% /'",
            "launchctl": 'printf \'legacy %s\\n\' "$*" >> "$FIXTURE_BROWSER_CALLS"',
        }.items():
            self.executable(name, "#!/bin/sh\n" + body + "\n")
        (self.scripts / "private-env.sh").write_text('job_search_load_private_env() { export GOG_KEYRING_PASSWORD="fixture-only"; return 0; }\n')
        (self.scripts / "install-local.sh").write_text("#!/bin/sh\nexit 0\n")
        (self.scripts / "install-local.sh").chmod(0o700)
        browser = self.home / ".cloakbrowser/chromium-fixture/Chromium.app/Contents/MacOS/Chromium"
        browser.parent.mkdir(parents=True)
        browser.touch(mode=0o700)
        config = self.home / ".config/life-manager"
        config.mkdir(parents=True)
        self.host = config / "host.json"
        self.host.write_text(json.dumps({
            "schema_version": 1, "owner_home": str(self.home), "tenant_id": "local-fixture",
            "source_checkout": str(self.repo),
            "runtime": {"python": str(self.python), "node": sys.executable},
            "agent_runner_config": str(config / "agent-runner.json"),
            "browser_registry": str(config / "browsers.toml"),
            "environment_file": str(self.home / ".local/state/life-manager/.env"),
        }))
        self.host.chmod(0o600)
        (config / "browsers.toml").write_text('[[identity]]\nid="interactive:owner"\nowner="life-manager-daily-driver"\nprofile="' + str(self.home / ".cloak/profiles/daily-driver") + '"\ndeclared_port=9555\n')
        private = self.home / ".config/anicca/job-search"
        private.mkdir(parents=True)
        (private / "profile.json").write_text("{}")
        self.install_config = private / "install.json"
        self.install_config.write_text("{}")
        (private / "telegram.env").touch()
        (self.release / "RELEASE.json").write_text(json.dumps({
            "sha": "a" * 40, "provenance": "ancestor-of-origin-main", "release_paths": "ALL",
            "runtime_python": str(self.python),
        }))
        (self.repo / "runtime/loop").mkdir(parents=True)
        (self.repo / "runtime/loop/local_install.py").write_text('''import json, os
from pathlib import Path
def record(value):
 with Path(os.environ["FIXTURE_CALLS"]).open("a") as handle: handle.write(json.dumps(value)+"\\n")
def cut_release(root, environment):
 record({"action":"cut", "environment":environment})
 return Path(os.environ["FIXTURE_RELEASE"])
def validate_release(release, profile):
 return json.loads((release/"RELEASE.json").read_text())
def apply_targets(release, owners, environment):
 record({"action":"apply", "owners":owners, "release":str(release), "environment":environment})
 return [{"ok":True,"label":"ai.anicca."+owner, **({"skipped":"running"} if os.environ.get("FIXTURE_WAITING") else {})} for owner in owners]
''')
        bin_dir = self.repo / "bin"
        bin_dir.mkdir()
        (bin_dir / "launchctl-safe").write_text("#!/bin/sh\nexit 0\n")
        (bin_dir / "launchctl-safe").chmod(0o700)
        (bin_dir / "lm-loop").write_text(f'''#!{sys.executable}
import json,os,sys
from pathlib import Path
owner=sys.argv[-1]
with Path(os.environ["FIXTURE_CALLS"]).open("a") as handle: handle.write(json.dumps({{"action":sys.argv[1],"owner":owner}})+"\\n")
print(json.dumps([{{"label":"ai.anicca."+owner,"return_code":0}}]))
''')
        (bin_dir / "lm-loop").chmod(0o700)
        self.env = {**os.environ, "HOME": str(self.home), "PATH": f"{self.tools}:/usr/bin:/bin",
                    "JOB_SEARCH_PYTHON": str(self.python), "JOB_SEARCH_PLUTIL": str(self.tools / "plutil"),
                    "JOB_SEARCH_LAUNCHCTL": str(self.tools / "launchctl"), "JOB_SEARCH_JQ": str(self.tools / "jq"),
                    "FIXTURE_CALLS": str(self.calls), "FIXTURE_RELEASE": str(self.release),
                    "FIXTURE_BROWSER_CALLS": str(root / "browser-calls"), "JOB_SEARCH_OSS_SKIP_PREP": "1"}
        for key in ("LIFE_MANAGER_HOST_PROFILE", "AGENT_RUNNER_CONFIG", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
            self.env.pop(key, None)

    def executable(self, name, content):
        path = self.tools / name
        path.write_text(content)
        path.chmod(0o700)
        return path

    def run(self, script, *arguments):
        return subprocess.run([shutil.which("zsh"), str(self.scripts / script), *arguments],
                              cwd=self.repo, env=self.env, capture_output=True, text=True, timeout=15)

    def events(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []


class JobHunterMacTest(unittest.TestCase):
    def test_direct_finished_reuses_a_prepared_venv_after_the_environment_is_lost(self):
        for relative in (".local/share/anicca/job-search/venv/bin/python",
                         ".local/share/life-manager/venv/bin/python"):
            with self.subTest(venv=relative), tempfile.TemporaryDirectory() as directory:
                fixture = ManagedJobHunterFixture(Path(directory))
                base = fixture.executable("python3", fixture.python.read_text().replace(
                    '"check_platform_available" in args[1]:\n raise SystemExit(0)',
                    '"check_platform_available" in args[1]:\n raise SystemExit(1)',
                ))
                prepared = fixture.home / relative
                prepared.parent.mkdir(parents=True)
                shutil.copy2(fixture.python, prepared)
                fixture.env.pop("JOB_SEARCH_PYTHON")

                result = fixture.run("install-oss.sh", "finished")

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout.splitlines()[-1])["status"], "ready")
                self.assertNotEqual(base, prepared)

    def test_direct_finished_preserves_an_explicit_python_override(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = ManagedJobHunterFixture(Path(directory))
            explicit = fixture.executable("explicit-python", fixture.python.read_text().replace(
                '"check_platform_available" in args[1]:\n raise SystemExit(0)',
                '"check_platform_available" in args[1]:\n raise SystemExit(1)',
            ))
            prepared = fixture.home / ".local/share/anicca/job-search/venv/bin/python"
            prepared.parent.mkdir(parents=True)
            shutil.copy2(fixture.python, prepared)
            fixture.env["JOB_SEARCH_PYTHON"] = str(explicit)

            result = fixture.run("install-oss.sh", "finished")

            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["missing"], ["machine_preflight"])
            self.assertEqual(fixture.events(), [])

    def test_host_install_keeps_managed_jobs_on_the_common_immutable_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = ManagedJobHunterFixture(Path(directory))
            result = fixture.run("install-launchd.sh")
            self.assertEqual(result.returncode, 0, result.stderr)
            applied = [row for row in fixture.events() if row["action"] == "apply"]
            self.assertEqual(len(applied), 1)
            self.assertEqual(set(applied[0]["owners"]), {"job-search-daily", "job-search-inbox", "job-search-learning", "job-search-health"})
            self.assertEqual(applied[0]["release"], str(fixture.release))
            self.assertEqual(applied[0]["environment"]["AGENT_RUNNER_CONFIG"], str(fixture.home / ".config/life-manager/agent-runner.json"))
            self.assertFalse((fixture.home / "Library/LaunchAgents").exists())

    def test_host_start_uses_the_shared_daily_driver(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = ManagedJobHunterFixture(Path(directory))
            result = fixture.run("install-oss.sh", "start")
            self.assertEqual(result.returncode, 0, result.stderr)
            applied = [row for row in fixture.events() if row["action"] == "apply"]
            self.assertEqual(applied[0]["owners"], ["life-manager-daily-driver"])
            self.assertFalse((fixture.home / "Library/LaunchAgents/ai.anicca.job-search-browser.plist").exists())

    def test_partial_host_activation_does_not_mark_oss_setup_activated(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = ManagedJobHunterFixture(Path(directory))
            fixture.env["FIXTURE_WAITING"] = "1"
            result = fixture.run("install-oss.sh", "finished")
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertNotEqual(json.loads(fixture.install_config.read_text()).get("oss_onboarding", {}).get("state"), "activated")
            self.assertEqual([row["action"] for row in fixture.events()], ["cut", "apply"])

    def test_host_stop_targets_catalog_jobs_and_preserves_the_shared_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = ManagedJobHunterFixture(Path(directory))
            result = fixture.run("install-oss.sh", "stop")
            self.assertEqual(result.returncode, 0, result.stderr)
            stopped = {row["owner"] for row in fixture.events() if row["action"] == "stop"}
            self.assertEqual(stopped, {"job-search-daily", "job-search-inbox", "job-search-learning", "job-search-health"})
            self.assertTrue(fixture.install_config.is_file())

    def test_missing_explicit_host_profile_fails_before_any_legacy_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = ManagedJobHunterFixture(Path(directory))
            fixture.env["LIFE_MANAGER_HOST_PROFILE"] = str(fixture.home / "missing.json")
            result = fixture.run("install-launchd.sh", "--browser-only")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(fixture.events(), [])
            self.assertFalse((fixture.home / "Library/LaunchAgents").exists())

    def test_explicit_host_profile_is_preserved_in_the_managed_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = ManagedJobHunterFixture(Path(directory))
            selected = fixture.home / "selected-host.json"
            fixture.host.rename(selected)
            fixture.env["LIFE_MANAGER_HOST_PROFILE"] = str(selected)
            result = fixture.run("install-launchd.sh")
            self.assertEqual(result.returncode, 0, result.stderr)
            applied = next(row for row in fixture.events() if row["action"] == "apply")
            self.assertEqual(applied["environment"]["LIFE_MANAGER_HOST_PROFILE"], str(selected))

    def test_mercor_browser_keeps_its_existing_scoped_installer_without_recursion(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = ManagedJobHunterFixture(Path(directory))
            fixture.env["LIFE_MANAGER_HOST_PROFILE"] = str(fixture.host)
            result = fixture.run("install-launchd.sh", "--mercor-browser-only")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(fixture.events(), [])
            self.assertEqual([path.name for path in (fixture.home / "Library/LaunchAgents").iterdir()],
                             ["ai.anicca.job-search-mercor-browser.plist"])

    def test_auto_resume_does_not_restart_setup_after_partial_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = ManagedJobHunterFixture(Path(directory))
            fixture.env["FIXTURE_WAITING"] = "1"
            result = fixture.run("install-oss.sh")
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual([row["action"] for row in fixture.events()], ["cut", "apply"])
            self.assertNotEqual(json.loads(fixture.install_config.read_text()).get("oss_onboarding", {}).get("state"), "activated")

    def test_preflight_accepts_both_supported_mac_architectures(self):
        for cpu, system, expected in (("arm64", "Darwin", 0), ("x86_64", "Darwin", 0),
                                      ("ppc", "Darwin", 2), ("x86_64", "Linux", 2)):
            with self.subTest(cpu=cpu, system=system), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary)
                tools = home / "bin"
                tools.mkdir()
                for name, text in {
                    "uname": f'if [ "$1" = -s ]; then echo {system}; else echo {cpu}; fi',
                    "codex": "exit 0", "python": "exit 0",
                    "df": "echo 'Filesystem 1024-blocks Used Available Capacity Mounted'; echo 'fixture 9000000 1 8999999 1% /'",
                }.items():
                    path = tools / name
                    path.write_text("#!/bin/sh\n" + text + "\n")
                    path.chmod(0o755)
                browser = home / ".cloakbrowser/chromium-fixture/Chromium.app/Contents/MacOS/Chromium"
                browser.parent.mkdir(parents=True)
                browser.touch()
                browser.chmod(0o755)
                result = subprocess.run([shutil.which("zsh"), str(ROOT / "apps/job-search-loop/scripts/install-oss.sh"), "preflight"],
                    env={**os.environ, "HOME": str(home), "PATH": f"{tools}:{os.environ['PATH']}",
                         "JOB_SEARCH_PYTHON": str(tools / "python")}, capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "ready" if expected == 0 else "blocked")

    def test_host_agent_configuration_survives_runtime_paths(self):
        result = subprocess.run([shutil.which("zsh"), "-c",
            'source "$1/apps/job-search-loop/scripts/runtime-paths.sh"; printf "%s" "$AGENT_RUNNER_CONFIG"',
            "fixture", str(ROOT)], env={**os.environ, "AGENT_RUNNER_CONFIG": "/own/agent-runner.json"},
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "/own/agent-runner.json")


if __name__ == "__main__":
    unittest.main()
