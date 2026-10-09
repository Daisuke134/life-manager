import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WATCHER = ROOT / "bin/reconcile-agent-handoff-watch.sh"


class ReconcilerHandoffWatcherTest(unittest.TestCase):
    def test_watcher_delegates_to_current_release_in_handoff_only_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            release = Path(directory) / "release"
            bin_dir = release / "bin"
            bin_dir.mkdir(parents=True)
            log = Path(directory) / "delegation.json"
            launchctl_log = Path(directory) / "launchctl.log"
            runner = bin_dir / "reconcile-agent-runner-release.sh"
            runner.write_text(
                "#!/bin/sh\n"
                "printf '%s|%s|%s|%s' \"$LIFE_MANAGER_RELEASE_ROOT\" "
                "\"$LIFE_MANAGER_RECONCILER_HANDOFF_ONLY\" \"$LIFE_MANAGER_LOOP_ID\" "
                "\"${LIFE_MANAGER_RECONCILER_FORCE_HANDOFF:-0}\" "
                "> \"$WATCHER_TEST_LOG\"\n",
                encoding="utf-8",
            )
            runner.chmod(runner.stat().st_mode | stat.S_IEXEC)
            launchctl_safe = bin_dir / "launchctl-safe"
            launchctl_safe.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$WATCHER_LAUNCHCTL_LOG\"\n"
                "case \"$1:$2\" in\n"
                "  preflight:*) exit 0 ;;\n"
                "  print:*)\n"
                "    case \"$2\" in\n"
                "      */ai.anicca.life-manager-release-reconciler-self-handoff)\n"
                "        case \"${FAKE_HELPER_STATE:-absent}\" in\n"
                "          running) printf 'state = running\\npid = %s\\n' \"$FAKE_HELPER_PID\" ;;\n"
                "          waiting) printf 'state = waiting\\n' ;;\n"
                "          absent) echo 'Could not find service' >&2; exit 113 ;;\n"
                "          *) printf 'state = %s\\n' \"$FAKE_HELPER_STATE\" ;;\n"
                "        esac\n"
                "        exit 0\n"
                "        ;;\n"
                "      */ai.anicca.life-manager-release-reconciler)\n"
                "        case \"${FAKE_OLD_STATE:-absent}\" in\n"
                "          absent) echo 'Could not find service' >&2; exit 113 ;;\n"
                "          *) printf 'state = %s\\n' \"$FAKE_OLD_STATE\" ;;\n"
                "        esac\n"
                "        ;;\n"
                "    esac\n"
                "    ;;\n"
                "  bootout:*) exit 0 ;;\n"
                "esac\n"
                "exit 64\n",
                encoding="utf-8",
            )
            launchctl_safe.chmod(launchctl_safe.stat().st_mode | stat.S_IEXEC)

            result = subprocess.run(
                ["/bin/bash", str(WATCHER)],
                env={
                    **os.environ,
                    "LIFE_MANAGER_RELEASE_ROOT": str(release),
                    "LIFE_MANAGER_LOOP_ID": "aa-release-reconciler-handoff",
                    "WATCHER_TEST_LOG": str(log),
                    "WATCHER_LAUNCHCTL_LOG": str(launchctl_log),
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                log.read_text(encoding="utf-8"),
                f"{release}|1|aa-release-reconciler-handoff|1",
            )
            self.assertEqual(launchctl_log.read_text(encoding="utf-8").splitlines(), [
                f"print gui/{os.getuid()}/ai.anicca.life-manager-release-reconciler-self-handoff",
                f"print gui/{os.getuid()}/ai.anicca.life-manager-release-reconciler",
            ])

    def test_watcher_leaves_an_active_handoff_helper_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            release = Path(directory) / "release"
            bin_dir = release / "bin"
            bin_dir.mkdir(parents=True)
            delegation = Path(directory) / "delegation.json"
            launchctl_log = Path(directory) / "launchctl.log"
            runner = bin_dir / "reconcile-agent-runner-release.sh"
            runner.write_text("#!/bin/sh\ntouch \"$WATCHER_TEST_LOG\"\n")
            runner.chmod(runner.stat().st_mode | stat.S_IEXEC)
            launchctl_safe = bin_dir / "launchctl-safe"
            launchctl_safe.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$WATCHER_LAUNCHCTL_LOG\"\n"
                "if [ \"$1\" = print ]; then printf 'state = running\\npid = %s\\n' \"$FAKE_HELPER_PID\"; exit 0; fi\n"
                "exit 64\n"
            )
            launchctl_safe.chmod(launchctl_safe.stat().st_mode | stat.S_IEXEC)
            result = subprocess.run(
                ["/bin/bash", str(WATCHER)],
                env={
                    **os.environ,
                    "LIFE_MANAGER_RELEASE_ROOT": str(release),
                    "WATCHER_TEST_LOG": str(delegation),
                    "WATCHER_LAUNCHCTL_LOG": str(launchctl_log),
                    "FAKE_HELPER_PID": str(os.getpid()),
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(delegation.exists())
            self.assertEqual(launchctl_log.read_text(encoding="utf-8").splitlines(), [
                f"print gui/{os.getuid()}/ai.anicca.life-manager-release-reconciler-self-handoff",
            ])

    def test_watcher_unloads_stale_helper_and_retries_against_old_service_state(self):
        with tempfile.TemporaryDirectory() as directory:
            release = Path(directory) / "release"
            bin_dir = release / "bin"
            bin_dir.mkdir(parents=True)
            delegation = Path(directory) / "delegation.json"
            launchctl_log = Path(directory) / "launchctl.log"
            runner = bin_dir / "reconcile-agent-runner-release.sh"
            runner.write_text(
                "#!/bin/sh\n"
                "printf '%s|%s' \"${LIFE_MANAGER_RECONCILER_HANDOFF_ONLY:-0}\" "
                "\"${LIFE_MANAGER_RECONCILER_FORCE_HANDOFF:-0}\" > \"$WATCHER_TEST_LOG\"\n"
            )
            runner.chmod(runner.stat().st_mode | stat.S_IEXEC)
            launchctl_safe = bin_dir / "launchctl-safe"
            launchctl_safe.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$WATCHER_LAUNCHCTL_LOG\"\n"
                "case \"$1\" in\n"
                "  print)\n"
                "    case \"$2\" in\n"
                "      */ai.anicca.life-manager-release-reconciler-self-handoff) printf 'state = waiting\\n' ;;\n"
                "      */ai.anicca.life-manager-release-reconciler) echo 'Could not find service' >&2; exit 113 ;;\n"
                "    esac\n"
                "    exit 0\n"
                "    ;;\n"
                "  bootout) exit 0 ;;\n"
                "esac\n"
                "exit 64\n"
            )
            launchctl_safe.chmod(launchctl_safe.stat().st_mode | stat.S_IEXEC)
            result = subprocess.run(
                ["/bin/bash", str(WATCHER)],
                env={
                    **os.environ,
                    "LIFE_MANAGER_RELEASE_ROOT": str(release),
                    "WATCHER_TEST_LOG": str(delegation),
                    "WATCHER_LAUNCHCTL_LOG": str(launchctl_log),
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                result.returncode, 0,
                f"{result.stderr}\n{launchctl_log.read_text(encoding='utf-8')}\n{launchctl_safe.read_text(encoding='utf-8')}",
            )
            self.assertEqual(delegation.read_text(encoding="utf-8"), "1|1")
            self.assertEqual(launchctl_log.read_text(encoding="utf-8").splitlines(), [
                f"print gui/{os.getuid()}/ai.anicca.life-manager-release-reconciler-self-handoff",
                f"bootout gui/{os.getuid()}/ai.anicca.life-manager-release-reconciler-self-handoff",
                f"print gui/{os.getuid()}/ai.anicca.life-manager-release-reconciler",
            ])

    def test_watcher_unloads_helper_in_launchd_not_running_state(self):
        with tempfile.TemporaryDirectory() as directory:
            release = Path(directory) / "release"
            bin_dir = release / "bin"
            bin_dir.mkdir(parents=True)
            delegation = Path(directory) / "delegation.json"
            launchctl_log = Path(directory) / "launchctl.log"
            runner = bin_dir / "reconcile-agent-runner-release.sh"
            runner.write_text(
                "#!/bin/sh\n"
                "printf '%s|%s' \"${LIFE_MANAGER_RECONCILER_HANDOFF_ONLY:-0}\" "
                "\"${LIFE_MANAGER_RECONCILER_FORCE_HANDOFF:-0}\" > \"$WATCHER_TEST_LOG\"\n"
            )
            runner.chmod(runner.stat().st_mode | stat.S_IEXEC)
            launchctl_safe = bin_dir / "launchctl-safe"
            launchctl_safe.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$WATCHER_LAUNCHCTL_LOG\"\n"
                "case \"$1:$2\" in\n"
                "  print:*)\n"
                "    case \"$2\" in\n"
                "      */ai.anicca.life-manager-release-reconciler-self-handoff) "
                "printf 'state = not running\\n' ;;\n"
                "      */ai.anicca.life-manager-release-reconciler) "
                "printf 'state = running\\n' ;;\n"
                "    esac\n"
                "    exit 0\n"
                "    ;;\n"
                "  bootout:*) exit 0 ;;\n"
                "esac\n"
                "exit 64\n"
            )
            launchctl_safe.chmod(launchctl_safe.stat().st_mode | stat.S_IEXEC)

            result = subprocess.run(
                ["/bin/bash", str(WATCHER)],
                env={
                    **os.environ,
                    "LIFE_MANAGER_RELEASE_ROOT": str(release),
                    "WATCHER_TEST_LOG": str(delegation),
                    "WATCHER_LAUNCHCTL_LOG": str(launchctl_log),
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(delegation.read_text(encoding="utf-8"), "1|0")
            self.assertEqual(launchctl_log.read_text(encoding="utf-8").splitlines(), [
                f"print gui/{os.getuid()}/ai.anicca.life-manager-release-reconciler-self-handoff",
                f"bootout gui/{os.getuid()}/ai.anicca.life-manager-release-reconciler-self-handoff",
                f"print gui/{os.getuid()}/ai.anicca.life-manager-release-reconciler",
            ])


if __name__ == "__main__":
    unittest.main()
