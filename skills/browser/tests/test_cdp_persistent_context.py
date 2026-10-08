import builtins
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "cdp_persistent_context.py"
ENSURE = Path(__file__).parents[1] / "ensure_provision_browser.sh"
SPEC = importlib.util.spec_from_file_location("cdp_persistent_context", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

GUARD_RELATIVE = Path(
    "gig/releases/life-manager/current/runtime/host/disk_admission.py"
)
STUB = """\
import json
import os
import sys
from pathlib import Path

capture = Path(os.environ["STUB_CAPTURE"])
keys = (
    "BROWSER_DISK_HEADROOM_KIB", "LIFE_MANAGER_DISK_HEADROOM_KIB",
    "HOME", "LIFE_MANAGER_HOST_STATE_DIR",
    "LIFE_MANAGER_PRODUCER_STATE_DIR",
    "LIFE_MANAGER_IGNORE_DISK_WRITERS_STOP", "GIG_DISK_HEADROOM_KIB",
    "GIG_HOST_STATE_DIR", "GIG_STATE_DIR", "GIG_IGNORE_DISK_PRESSURE_BLOCK",
    "GIG_IGNORE_DISK_WRITERS_STOP",
    "DISK_CONTROL_STATE_DIR", "OPENCLAW_STATE_DIR", "LIFE_MANAGER_HOST_STATE_DIR",
)
host_state = Path(os.environ["LIFE_MANAGER_HOST_STATE_DIR"])
stop_file = host_state / "disk-writers.stop"
try:
    stop_value = json.loads(stop_file.read_text(encoding="utf-8"))
except (OSError, ValueError):
    stop_value = None
cleanup_recovery = (
    isinstance(stop_value, dict)
    and stop_value.get("owner_id") == "host-disk-recovery"
    and stop_value.get("reason") == "disk_headroom_low"
    and stop_value.get("required_bytes") == 2 * 1024**3
    and stop_value.get("next_action") == "restore_capacity_and_install_shared_disk_gate"
)
reason = "disk_writers_stop" if stop_file.is_file() and not cleanup_recovery else None
record = {"argv": sys.argv, "isolated": sys.flags.isolated,
          "env": {key: os.environ[key] for key in keys if key in os.environ}}
capture.write_text(json.dumps(record), encoding="utf-8")
if reason:
    receipt = Path(os.environ["LIFE_MANAGER_PRODUCER_STATE_DIR"]) / "state/disk-headroom.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({"status": "failed", "failed": 1, "effect": 0,
                                   "readback": 0, "reason": reason,
                                   "required_bytes": 0}),
                       encoding="utf-8")
raise SystemExit(1 if reason else 0)
"""


class CdpPersistentContextPreflightTests(unittest.TestCase):
    def test_browser_has_a_finite_renderer_process_limit(self) -> None:
        self.assertIn(
            'f"--renderer-process-limit={renderer_limit}"',
            SCRIPT.read_text(encoding="utf-8"),
        )

    def test_persistent_context_disables_code_sign_clone(self) -> None:
        self.assertIn(
            '"--disable-features=MacAppCodeSignClone"',
            SCRIPT.read_text(encoding="utf-8"),
        )

    def install_guard(self, home: Path) -> Path:
        guard = home / GUARD_RELATIVE
        guard.parent.mkdir(parents=True)
        guard.write_text(STUB, encoding="utf-8")
        guard.chmod(0o644)
        return guard

    def reject_browser_import(self):
        real_import = builtins.__import__

        def reject(name, *args, **kwargs):
            if name == "cloakbrowser":
                raise AssertionError("cloakbrowser imported before disk preflight")
            return real_import(name, *args, **kwargs)

        return reject

    def test_child_env_is_canonical_and_isolated_from_hostile_pythonpath(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            guard = self.install_guard(home)
            capture = root / "capture.json"
            hostile = root / "hostile"
            hostile.mkdir()
            marker = hostile / "sitecustomize-ran"
            (hostile / "sitecustomize.py").write_text(
                f"from pathlib import Path\nPath({str(marker)!r}).write_text('hostile')\n",
                encoding="utf-8",
            )
            environment = {
                "HOME": "/hostile/home",
                "PYTHONPATH": str(hostile),
                "GIG_DISK_HEADROOM_KIB": "0",
                "GIG_HOST_STATE_DIR": "/hostile/host-state",
                "GIG_STATE_DIR": "/hostile/lane-state",
                "GIG_IGNORE_DISK_WRITERS_STOP": "true",
                "DISK_CONTROL_STATE_DIR": "/hostile/control",
                "OPENCLAW_STATE_DIR": "/hostile/openclaw",
                "LIFE_MANAGER_HOST_STATE_DIR": "/hostile/life-manager",
                "STUB_CAPTURE": str(capture),
            }
            with patch.dict(os.environ, environment, clear=False):
                self.assertTrue(MODULE._disk_preflight(home, guard))
            record = json.loads(capture.read_text(encoding="utf-8"))
            self.assertEqual(record["argv"], [str(guard), "/usr/bin/true"])
            self.assertEqual(record["isolated"], 1)
            self.assertFalse(marker.exists())
            child_env = record["env"]
            self.assertEqual(child_env["HOME"], str(home))
            self.assertEqual(child_env["LIFE_MANAGER_HOST_STATE_DIR"],
                             str(home / ".local/state/life-manager/state"))
            self.assertEqual(child_env["LIFE_MANAGER_PRODUCER_STATE_DIR"],
                             str(home / ".local/state/life-manager/browser-provision"))
            for key in (
                "GIG_IGNORE_DISK_WRITERS_STOP",
                "DISK_CONTROL_STATE_DIR", "OPENCLAW_STATE_DIR",
                "LIFE_MANAGER_DISK_HEADROOM_KIB", "GIG_DISK_HEADROOM_KIB",
                "BROWSER_DISK_HEADROOM_KIB", "GIG_HOST_STATE_DIR", "GIG_STATE_DIR",
                "GIG_IGNORE_DISK_PRESSURE_BLOCK",
            ):
                self.assertNotIn(key, child_env)

    def test_pressure_and_cleanup_recovery_are_advisory_but_operator_stop_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            host_state = home / ".local/state/life-manager/state"
            host_state.mkdir(parents=True)
            guard = self.install_guard(home)
            capture = root / "capture.json"
            (host_state / "disk-pressure.block").write_text("blocked\n", encoding="utf-8")
            with patch.dict(os.environ, {"STUB_CAPTURE": str(capture)}, clear=False):
                self.assertTrue(MODULE._disk_preflight(home, guard))
            stop_file = host_state / "disk-writers.stop"
            stop_file.write_text(json.dumps({
                "owner_id": "host-disk-recovery",
                "reason": "disk_headroom_low",
                "required_bytes": 2 * 1024**3,
                "next_action": "restore_capacity_and_install_shared_disk_gate",
            }) + "\n", encoding="utf-8")
            stop_file.chmod(0o600)
            with patch.dict(os.environ, {"STUB_CAPTURE": str(capture)}, clear=False):
                self.assertTrue(MODULE._disk_preflight(home, guard))
            stop_file.write_text("owner=operator\n", encoding="utf-8")
            with patch.dict(os.environ, {"STUB_CAPTURE": str(capture)}, clear=False):
                self.assertFalse(MODULE._disk_preflight(home, guard))
            receipt = json.loads(
                (home / ".local/state/life-manager/browser-provision/state/disk-headroom.json").read_text()
            )
            self.assertEqual(receipt["reason"], "disk_writers_stop")
            self.assertEqual(receipt["effect"], 0)
            self.assertEqual(receipt["required_bytes"], 0)

    def test_legacy_browser_headroom_setting_is_not_forwarded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            guard = self.install_guard(home)
            capture = root / "capture.json"
            with patch.dict(os.environ, {
                "BROWSER_DISK_HEADROOM_KIB": "not-a-number", "STUB_CAPTURE": str(capture)
            }, clear=False):
                self.assertTrue(MODULE._disk_preflight(home, guard))
            record = json.loads(capture.read_text(encoding="utf-8"))
            self.assertNotIn("LIFE_MANAGER_DISK_HEADROOM_KIB", record["env"])

    def test_with_browser_starts_unreachable_identity_and_owns_one_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            guard = root / "guard.sh"
            ensure = root / "ensure.sh"
            calls = root / "calls"
            guard.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"guard:$1:$2:${{AI_BROWSER_HOLDER_PID:-}}:${{AI_BROWSER_HOLDER_START:-}}\" >> {calls!s}\n"
                "case \"$1\" in\n"
                "  acquire) exit 10 ;;\n"
                "  release) exit 0 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            ensure.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"ensure:$1:${{AI_BROWSER_HOLDER_PID:-}}:${{AI_BROWSER_HOLDER_START:-}}\" >> {calls!s}\n"
                "printf '%s\\n' http://127.0.0.1:54321\n",
                encoding="utf-8",
            )
            guard.chmod(0o755)
            ensure.chmod(0o755)
            target_owners = root / "home/.cloak/vault/target-owners" / (
                hashlib.sha256(b"buyma:test").hexdigest() + ".json"
            )
            completed = subprocess.run(
                ["bash", str(ENSURE.with_name("with-browser.sh")), "buyma:test", "--",
                 "sh", "-c", 'test "$CDP" = http://127.0.0.1:54321 && '
                 'test "$CLOAK_CDP_BASE_URL" = http://127.0.0.1:54321 && '
                 'test "$CDP_DAILY_DRIVER_PORT" = 54321 && '
                 'test "$GIG_CDP_HEALTH_URL" = http://127.0.0.1:54321/json/version && '
                 'test "$SESSION_VAULT_PORT" = 54321 && '
                 'test "$CLOAK_TARGET_OWNERS_FILE" = "$EXPECTED_TARGET_OWNERS"'],
                env={**os.environ, "AI_BROWSER_GUARD": str(guard),
                     "AI_ENSURE_PROVISION_BROWSER": str(ensure),
                     "BROWSER_WAIT_SECONDS": "1", "HOME": str(root / "home"),
                     "CLOAK_CDP_BASE_URL": "http://127.0.0.1:9223",
                     "CDP_DAILY_DRIVER_PORT": "9223",
                     "GIG_CDP_HEALTH_URL": "http://127.0.0.1:9223/json/version",
                     "CLOAK_TARGET_OWNERS_FILE": str(root / "outer-loop-targets.json"),
                     "EXPECTED_TARGET_OWNERS": str(target_owners)},
                capture_output=True, text=True, check=False, timeout=15,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            records = calls.read_text(encoding="utf-8").splitlines()
            self.assertRegex(records[0], r"^guard:acquire:buyma:test:\d+:[0-9a-f]{32}$")
            holder_pid, holder_start = records[0].rsplit(":", 2)[1:]
            self.assertEqual(records[1], f"ensure:buyma:test:{holder_pid}:{holder_start}")
            self.assertEqual(records[2], f"guard:release:buyma:test:{holder_pid}:{holder_start}")

    def test_with_browser_falls_back_to_shared_owner_for_protected_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            guard = root / "guard.sh"
            provision = root / "provision.sh"
            shared = root / "shared.sh"
            calls = root / "calls"
            state = root / "state"
            guard.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"guard:$1:$2\" >> {calls!s}\n"
                f"if [ \"$1\" = acquire ] && [ ! -f {state!s} ]; then touch {state!s}; exit 10; fi\n"
                "if [ \"$1\" = acquire ]; then printf '%s\\n' http://127.0.0.1:54322; exit 0; fi\n",
                encoding="utf-8",
            )
            provision.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' provision >> {calls!s}\n"
                "exit 1\n",
                encoding="utf-8",
            )
            shared.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' shared >> {calls!s}\n"
                "exit 0\n",
                encoding="utf-8",
            )
            for script in (guard, provision, shared):
                script.chmod(0o755)
            completed = subprocess.run(
                ["bash", str(ENSURE.with_name("with-browser.sh")), "coconala:kosuke", "--",
                 "sh", "-c", 'test "$CDP" = http://127.0.0.1:54322'],
                env={
                    **os.environ,
                    "HOME": str(root / "home"),
                    "AI_BROWSER_GUARD": str(guard),
                    "AI_ENSURE_PROVISION_BROWSER": str(provision),
                    "AI_ENSURE_BROWSER": str(shared),
                    "CLOAK_BROWSER_LAUNCHD_LABEL": "ai.anicca.hf-gig-browser",
                    "BROWSER_WAIT_SECONDS": "1",
                },
                capture_output=True, text=True, check=False, timeout=15,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(calls.read_text(encoding="utf-8").splitlines(), [
                "guard:acquire:coconala:kosuke",
                "provision",
                "shared",
                "guard:acquire:coconala:kosuke",
                "guard:release:coconala:kosuke",
            ])

    def test_port_zero_preflight_only_reaches_guard_without_cloak_import(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            guard = self.install_guard(home)
            capture = root / "capture.json"
            with (
                patch.dict(os.environ, {"HOME": "/hostile/home", "STUB_CAPTURE": str(capture)}, clear=False),
                patch.object(MODULE, "_canonical_home", return_value=home),
                patch.object(MODULE, "_GUARD", guard),
                patch("builtins.__import__", side_effect=self.reject_browser_import()),
            ):
                self.assertEqual(
                    MODULE.main(["--profile", str(root / "profile"), "--port", "0", "--preflight-only"]),
                    0,
                )
            self.assertTrue(capture.exists())

    def test_shell_preflight_precedes_profile_and_launch_side_effects(self) -> None:
        text = ENSURE.read_text(encoding="utf-8")
        launch = text.split("launch() {", 1)[1].split("\n}", 1)[0]
        preflight = launch.index('--port 0 --preflight-only')
        for effect in (
            'mkdir -p "$profile"',
            "clear_stale_singletons",
            '"$LAUNCHCTL_SAFE" remove "$LABEL"',
            "sleep 1",
            '"$LAUNCHCTL_SAFE" submit',
        ):
            self.assertLess(preflight, launch.index(effect))
        self.assertIn('"$CLOAK_PY" "$KEEPALIVE" --profile "$profile" --port 0 --preflight-only', launch)

    def test_launcher_uses_guarded_launchctl_control_plane(self) -> None:
        text = ENSURE.read_text(encoding="utf-8")
        self.assertIn('LAUNCHCTL_SAFE="${LIFE_MANAGER_LAUNCHCTL_SAFE:-', text)
        self.assertNotIn('\n  launchctl remove ', text)
        self.assertNotIn('\n  if ! launchctl submit ', text)

    def test_launcher_stops_when_launchctl_preflight_rejects_remove(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            profile = home / ".cloak/profiles/test"
            registry = root / "browsers.toml"
            registry.write_text(
                f'[[identity]]\nid = "test:browser"\nprofile = "{profile}"\n',
                encoding="utf-8",
            )
            calls = root / "launchctl.calls"
            guard_calls = root / "guard.calls"
            launchctl_safe = root / "launchctl-safe"
            launchctl_safe.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$1\" >> {calls}\n"
                '[ "$1" = remove ] && exit 75\n'
                "exit 0\n",
                encoding="utf-8",
            )
            guard = root / "browser-guard.sh"
            guard.write_text(
                f"#!/bin/sh\nprintf '%s\\n' \"$1\" >> {guard_calls}\n"
                '[ "$1" = status ] && printf \'%s\\n\' '
                "'{\"identities\":[{\"reachable\":false}]}'\n",
                encoding="utf-8",
            )
            runtime = root / "python"
            runtime.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            for executable in (launchctl_safe, guard, runtime):
                executable.chmod(0o755)
            completed = subprocess.run(
                ["bash", str(ENSURE), "test:browser"],
                env={**os.environ, "HOME": str(home), "AI_BROWSER_GUARD": str(guard),
                     "AI_BROWSER_REGISTRY": str(registry), "CLOAK_PYTHON": str(runtime),
                     "LIFE_MANAGER_LAUNCHCTL_SAFE": str(launchctl_safe)},
                capture_output=True, text=True, check=False, timeout=15,
            )
            self.assertEqual(completed.returncode, 75, completed.stderr)
            self.assertEqual(calls.read_text(encoding="utf-8").splitlines(), ["remove"])
            self.assertEqual(guard_calls.read_text(encoding="utf-8").splitlines(), ["status"])

            calls.unlink()
            guard_calls.unlink()
            launchctl_safe.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$1\" >> {calls}\n"
                '[ "$1" = submit ] && exit 75\n'
                "exit 0\n",
                encoding="utf-8",
            )
            launchctl_safe.chmod(0o755)
            completed = subprocess.run(
                ["bash", str(ENSURE), "test:browser"],
                env={**os.environ, "HOME": str(home), "AI_BROWSER_GUARD": str(guard),
                     "AI_BROWSER_REGISTRY": str(registry), "CLOAK_PYTHON": str(runtime),
                     "LIFE_MANAGER_LAUNCHCTL_SAFE": str(launchctl_safe)},
                capture_output=True, text=True, check=False, timeout=15,
            )
            self.assertEqual(completed.returncode, 75, completed.stderr)
            self.assertEqual(calls.read_text(encoding="utf-8").splitlines(), ["remove", "submit"])
            self.assertEqual(guard_calls.read_text(encoding="utf-8").splitlines(), ["status"])

    def test_missing_symlink_or_unreadable_guard_has_no_cloak_import(self) -> None:
        for kind in ("missing", "symlink", "unreadable"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                home = root / "home"
                home.mkdir()
                guard = home / GUARD_RELATIVE
                if kind == "symlink":
                    target = root / "guard-target.py"
                    target.write_text(STUB, encoding="utf-8")
                    guard.parent.mkdir(parents=True)
                    guard.symlink_to(target)
                elif kind == "unreadable":
                    self.install_guard(home).chmod(0)
                with (patch.dict(os.environ, {"HOME": "/hostile/home"}, clear=False),
                      patch.object(MODULE, "_canonical_home", return_value=home),
                      patch.object(MODULE, "_GUARD", guard),
                      patch("builtins.__import__", side_effect=self.reject_browser_import())):
                    self.assertEqual(MODULE.main(["--profile", str(root / "profile"), "--port", "9333"]), 1)

    def test_invalid_port_has_no_cloak_import_or_effect(self) -> None:
        for port in ("-1", "65536", "not-an-int"):
            with self.subTest(port=port), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with (patch.object(MODULE, "_disk_preflight", return_value=True),
                      patch("builtins.__import__", side_effect=self.reject_browser_import())):
                    self.assertEqual(MODULE.main(["--profile", str(root / "profile"), "--port", port]), 1)
                self.assertFalse((root / "profile").exists())

if __name__ == "__main__":
    unittest.main()


class LiveProfileOwnerTests(unittest.TestCase):
    def _profile(self, root: Path, target: str) -> Path:
        profile = root / "daily-driver"
        profile.mkdir()
        os.symlink(target, profile / "SingletonLock")
        return profile

    def test_live_chromium_on_same_profile_is_the_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            profile = self._profile(Path(directory), "host-4242")
            command = f"Chromium --user-data-dir={os.path.realpath(profile)} --x"
            with (patch.object(MODULE.os, "kill", return_value=None),
                  patch.object(MODULE, "_command_line", return_value=command)):
                self.assertEqual(MODULE._live_profile_owner(str(profile)), 4242)

    def test_dead_or_unrelated_pid_or_missing_lock_is_not_an_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            profile = self._profile(Path(directory), "host-4242")
            with patch.object(MODULE.os, "kill", side_effect=ProcessLookupError):
                self.assertIsNone(MODULE._live_profile_owner(str(profile)))
            with (patch.object(MODULE.os, "kill", return_value=None),
                  patch.object(MODULE, "_command_line", return_value="Chromium --user-data-dir=/other")):
                self.assertIsNone(MODULE._live_profile_owner(str(profile)))
            self.assertIsNone(MODULE._live_profile_owner(str(Path(directory) / "missing")))

    def test_adopts_live_owner_instead_of_launching_and_exits_nonzero_when_it_dies(self) -> None:
        alive = iter([True, True, False])
        with (patch.object(MODULE, "_disk_preflight", return_value=True),
              patch.object(MODULE, "_live_profile_owner", return_value=4242),
              patch.object(MODULE, "_pid_alive", side_effect=lambda _pid: next(alive)),
              patch.object(MODULE.time, "sleep"),
              patch.dict("sys.modules", {"cloakbrowser": None})):
            self.assertEqual(MODULE.main(["--profile", "/p", "--port", "9222"]), 1)
