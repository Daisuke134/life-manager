import json
from datetime import datetime
import os
import plistlib
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "bin/reconcile-agent-runner-release.sh"

# The reconciler now applies one registry loop id at a time (LIFE_MANAGER_APPLY_TARGET) instead
# of one fleet-wide `apply --all`, so the fake must answer per target rather than emit one fixed
# fleet-wide response. `target=$FAKE_TARGET_ECHO` is appended to the calls log line so tests can
# tell which owner each call was for.
FAKE_LM_LOOP = """#!/bin/sh
set -eu
target="${LIFE_MANAGER_APPLY_TARGET:-}"
echo "$@ target=$target" >> "$FAKE_LM_LOOP_CALLS_LOG"
if [ "$1" = "reconcile" ]; then
  exit 0
fi
if [ "$1" = "apply" ]; then
  case "${FAKE_APPLY_MODE:-ok}" in
    ok)
      echo "[{\\"ok\\":true,\\"label\\":\\"$target\\",\\"release_sha\\":\\"x\\",\\"changed\\":true}]"
      exit 0
      ;;
    retire_bad)
      if [ "$target" = "${FAKE_RETIRE_TARGET:-}" ]; then
        echo "$FAKE_RETIRE_RESPONSE"
      else
        echo "[{\\"ok\\":true,\\"changed\\":true}]"
      fi
      exit 0
      ;;
    retire_guarded)
      if [ "$target" = "${FAKE_RETIRE_TARGET:-}" ]; then
        echo "[{\\"ok\\":true,\\"label\\":\\"$target\\",\\"retired\\":true,\\"was_loaded\\":${FAKE_RETIRE_LOADED:-true},\\"removed_plist\\":false}]"
      else
        echo "[{\\"ok\\":true,\\"changed\\":true}]"
      fi
      exit 0
      ;;
    orphan_holds_stdout)
      sleep 60 &
      echo "[{\\"ok\\":true,\\"label\\":\\"$target\\",\\"release_sha\\":\\"x\\",\\"changed\\":true}]"
      exit 0
      ;;
    already_owned)
      echo '{"ok": false, "error": "production apply is already owned"}'
      exit 1
      ;;
    effect_unknown)
      if [ "$target" = "${FAKE_EFFECT_UNKNOWN_TARGET:-}" ]; then
        echo '{"ok": false, "error": "admission rebind refused: effect_unknown"}'
        exit 1
      fi
      printf '[{"ok":true,"label":"%s","release_sha":"x","changed":true}]' "$target"
      exit 0
      ;;
    effect_unknown_lookalike)
      if [ "$target" = "${FAKE_EFFECT_UNKNOWN_TARGET:-}" ]; then
        echo '{"ok": false, "error": "observer failed while checking effect_unknown hint"}'
        exit 1
      fi
      printf '[{"ok":true,"label":"%s","release_sha":"x","changed":true}]' "$target"
      exit 0
      ;;
    effect_unknown_compound)
      echo '{"ok": false, "error": "admission rebind refused: effect_unknown", "details": "bootstrap code 5 Input/output error"}'
      exit 1
      ;;
    fail)
      echo '{"ok": false, "error": "boom"}'
      exit 1
      ;;
    hang_one)
      if [ "$target" = "${FAKE_HANG_LOOP_ID:-}" ]; then
        sleep 60
        exit 0
      fi
      echo "[{\\"ok\\":true,\\"label\\":\\"$target\\",\\"release_sha\\":\\"x\\",\\"changed\\":true}]"
      exit 0
      ;;
    slow_first)
      if [ "$target" = "${FAKE_SLOW_LOOP_ID:-}" ]; then
        sleep 2.2
      fi
      echo "[{\\"ok\\":true,\\"label\\":\\"$target\\",\\"release_sha\\":\\"x\\",\\"changed\\":true}]"
      exit 0
      ;;
  esac
fi
exit 0
"""


class ReconcileAgentRunnerReleaseFleetApplyTest(unittest.TestCase):
    """The release-reconciler cuts+activates a new `current` every 60s but, until now, never ran
    the fleet-wide `lm-loop apply --all` that actually repoints loaded launchd owners onto it --
    measured 2026-09-27: 53/172 loaded owners were current, 81 sat on a 10h-old release, until a
    human ran `apply --all` by hand. These tests prove the reconciler now runs that apply exactly
    once per newly activated release sha, never for a candidate/non-activated release, never while
    the promotion hold is active, and never retries a failed attempt on the very next tick.
    """

    def _make_repo(self, root):
        repo, origin = root / "repo", root / "origin.git"
        subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
        subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
        for key, value in (("user.email", "fleet-apply-test@example.invalid"),
                           ("user.name", "Fleet Apply Test")):
            subprocess.run(["git", "config", key, value], cwd=repo, check=True)
        subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=repo, check=True)
        (repo / "payload.txt").write_text("v1\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "v1"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=repo, check=True,
                       capture_output=True)
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        return repo, sha

    def _make_release(self, root, sha, *, release_paths="ALL", loop_ids=("loop-a",),
                       labels=None, entry_overrides=None,
                       with_investment_provisioner=False,
                       with_investment_selection_provisioner=False,
                       with_reviewed_validation_reports=False):
        release_dir = root / "loops" / "releases" / f"rel-{sha}"
        (release_dir / "bin").mkdir(parents=True)
        (release_dir / "config").mkdir(parents=True)
        (release_dir / "RELEASE.json").write_text(
            json.dumps({"sha": sha, "release_paths": release_paths}))
        labels = labels or {}
        entry_overrides = entry_overrides or {}
        loops = {}
        for loop_id in loop_ids:
            entry = {"label": labels[loop_id]} if loop_id in labels else {}
            entry.update(entry_overrides.get(loop_id, {}))
            loops[loop_id] = entry
        (release_dir / "config" / "loop-registry.json").write_text(json.dumps({
            "loops": loops,
            "retired_labels": [],
        }))
        lm_loop = release_dir / "bin" / "lm-loop"
        lm_loop.write_text(FAKE_LM_LOOP)
        lm_loop.chmod(lm_loop.stat().st_mode | stat.S_IEXEC)
        if with_investment_provisioner:
            provisioner = release_dir / "apps/life-manager/investment-core/provision_manifest.py"
            provisioner.parent.mkdir(parents=True)
            provisioner.write_text(
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "if os.environ.get('FAKE_PROVISION_FAIL') == '1':\n"
                "    raise SystemExit(1)\n"
                "Path(os.environ['FAKE_PROVISION_MARKER']).write_text("
                "json.dumps({'argv': sys.argv[1:]})\n"
                ")\n",
                encoding="utf-8",
            )
        if with_investment_selection_provisioner:
            provisioner = release_dir / "apps/life-manager/investment-core/provision_selection.py"
            provisioner.parent.mkdir(parents=True, exist_ok=True)
            provisioner.write_text(
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "if os.environ.get('FAKE_SELECTION_PROVISION_FAIL') == '1':\n"
                "    raise SystemExit(1)\n"
                "marker = Path(os.environ['FAKE_SELECTION_PROVISION_MARKER'])\n"
                "calls = json.loads(marker.read_text()) if marker.exists() else []\n"
                "calls.append({'argv': sys.argv[1:]})\n"
                "marker.write_text(json.dumps(calls))\n",
                encoding="utf-8",
            )
            if with_reviewed_validation_reports:
                (release_dir / "apps/life-manager/investment-core/reviewed-validation-reports.json").write_text(
                    "{\"reports\": []}\n", encoding="utf-8",
                )
        if release_paths != "ALL":
            # `$CURRENT/bin/cut-loop-release.sh` is preferred over the source repo's; stub it as a
            # no-op so a sparse/candidate `current` (which forces `current_complete=0`) doesn't
            # actually get replaced -- the reconciler re-reads `current` after "cutting" and must
            # hit its own "release is not the full pushed-main build" refusal on this same
            # still-sparse release, never reaching fleet apply.
            noop_cutter = release_dir / "bin" / "cut-loop-release.sh"
            noop_cutter.write_text("#!/bin/sh\nexit 0\n")
            noop_cutter.chmod(noop_cutter.stat().st_mode | stat.S_IEXEC)
        return release_dir

    def _activate(self, root, release_dir):
        current = root / "loops" / "current"
        current.unlink(missing_ok=True)
        current.symlink_to(release_dir)

    def _base_env(self, root, repo, *, calls_log, apply_mode="ok"):
        admission_root = root / "admission"
        (admission_root).mkdir(parents=True, exist_ok=True)
        (admission_root / "protocol.json").write_text("{}")
        return {
            **os.environ,
            "SOURCE_REPO": str(repo),
            "LIFE_MANAGER_SOURCE_REPO": str(repo),
            "LOOPS_ROOT": str(root / "loops"),
            "LIFE_MANAGER_RESOURCE_ADMISSION_ROOT": str(admission_root),
            "LIFE_MANAGER_RECOVERY_INTENTS_PATH": str(root / "no-intents.jsonl"),
            "LIFE_MANAGER_RELEASE_RECONCILER_STATE_ROOT": str(root / "reconciler-state"),
            "LIFE_MANAGER_RELEASE_FETCH_TIMEOUT_SECONDS": "30",
            "LIFE_MANAGER_RECONCILE_TIMEOUT_SECONDS": "30",
            "LIFE_MANAGER_FLEET_APPLY_TIMEOUT_SECONDS": "10",
            "LIFE_MANAGER_FLEET_APPLY_PER_OWNER_TIMEOUT_SECONDS": "2",
            "LIFE_MANAGER_FLEET_APPLY_BACKOFF_SECONDS": "100000",
            "LIFE_MANAGER_FLEET_APPLY_MIN_INTERVAL_SECONDS": "1800",
            "FAKE_LM_LOOP_CALLS_LOG": str(calls_log),
            "FAKE_APPLY_MODE": apply_mode,
        }

    def _advance_repo(self, repo):
        marker = f"v-{os.urandom(4).hex()}\n"
        (repo / "payload.txt").write_text(marker)
        subprocess.run(["git", "commit", "-am", marker.strip()], cwd=repo, check=True,
                       capture_output=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=repo, check=True, capture_output=True)
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()

    def _backdate_last_ok(self, root, seconds_ago):
        state_path = root / "reconciler-state" / "fleet-apply-state.json"
        state = json.loads(state_path.read_text())
        state["last_ok_epoch"] = state["last_ok_epoch"] - seconds_ago
        state_path.write_text(json.dumps(state))

    def _run(self, env):
        return subprocess.run(["/bin/bash", str(SCRIPT)], env=env,
                              capture_output=True, text=True, check=False)

    def _apply_call_count(self, calls_log):
        if not calls_log.exists():
            return 0
        return sum(1 for line in calls_log.read_text().splitlines() if line.startswith("apply "))

    def _state(self, root):
        state_path = root / "reconciler-state" / "fleet-apply-state.json"
        return json.loads(state_path.read_text()) if state_path.exists() else None

    def test_new_release_triggers_apply_once_then_skips_next_tick(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            release_dir = self._make_release(root, sha)
            self._activate(root, release_dir)
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log)

            first = self._run(env)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(self._apply_call_count(calls_log), 1)
            state = self._state(root)
            self.assertEqual(state["sha"], sha)
            self.assertEqual(state["status"], "ok")
            self.assertEqual(state["changed"], 1)

            second = self._run(env)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(self._apply_call_count(calls_log), 1,
                             "same release on the next tick must not re-apply")

    def test_release_handoff_runs_investment_manifest_provisioner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            release_dir = self._make_release(
                root, sha, with_investment_provisioner=True,
            )
            self._activate(root, release_dir)
            calls_log = root / "calls.log"
            marker = root / "provision.json"
            env = self._base_env(root, repo, calls_log=calls_log)
            env["FAKE_PROVISION_MARKER"] = str(marker)
            env["LIFE_MANAGER_INVESTMENT_MANIFEST_PATH"] = str(
                root / "state/inputs.json"
            )

            result = self._run(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(marker.read_text(encoding="utf-8"))["argv"],
                [
                    "--path", str(root / "state/inputs.json"),
                    "--alpaca-state-dir",
                    "~/.local/state/life-manager/alpaca-investment-live",
                    "--available-capital-usd", "0",
                ],
            )

    def test_failed_investment_manifest_provisioning_stops_owner_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            release_dir = self._make_release(
                root, sha, with_investment_provisioner=True,
            )
            self._activate(root, release_dir)
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log)
            env["FAKE_PROVISION_MARKER"] = str(root / "provision.json")
            env["FAKE_PROVISION_FAIL"] = "1"

            result = self._run(env)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self._apply_call_count(calls_log), 0)

    def test_release_handoff_runs_investment_selection_provisioner_when_reports_configured(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            release_dir = self._make_release(
                root, sha, with_investment_selection_provisioner=True,
            )
            self._activate(root, release_dir)
            calls_log = root / "calls.log"
            marker = root / "selection-provision.json"
            env = self._base_env(root, repo, calls_log=calls_log)
            env["FAKE_SELECTION_PROVISION_MARKER"] = str(marker)
            env["LIFE_MANAGER_INVESTMENT_VALIDATION_REPORTS_PATH"] = str(
                root / "state/validation-reports.json"
            )
            env["LIFE_MANAGER_INVESTMENT_SELECTION_PATH"] = str(
                root / "state/selected-strategy.json"
            )
            env["LIFE_MANAGER_INVESTMENT_PAPER_SELECTION_PATH"] = str(
                root / "state/paper-selected-strategy.json"
            )

            result = self._run(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(marker.read_text(encoding="utf-8")),
                [
                    {"argv": [
                        "--path", str(root / "state/selected-strategy.json"),
                        "--reports", str(root / "state/validation-reports.json"),
                        "--release-sha", sha,
                    ]},
                    {"argv": [
                        "--path", str(root / "state/paper-selected-strategy.json"),
                        "--reports", str(root / "state/validation-reports.json"),
                        "--release-sha", sha,
                    ]},
                ],
            )

    def test_failed_investment_selection_provisioning_stops_owner_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            release_dir = self._make_release(
                root, sha, with_investment_selection_provisioner=True,
            )
            self._activate(root, release_dir)
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log)
            env["FAKE_SELECTION_PROVISION_MARKER"] = str(root / "selection-provision.json")
            env["FAKE_SELECTION_PROVISION_FAIL"] = "1"
            env["LIFE_MANAGER_INVESTMENT_VALIDATION_REPORTS_PATH"] = str(
                root / "state/validation-reports.json"
            )

            result = self._run(env)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self._apply_call_count(calls_log), 0)

    def test_release_handoff_uses_release_reviewed_reports_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            release_dir = self._make_release(
                root, sha, with_investment_selection_provisioner=True,
                with_reviewed_validation_reports=True,
            )
            self._activate(root, release_dir)
            calls_log = root / "calls.log"
            marker = root / "selection-provision.json"
            env = self._base_env(root, repo, calls_log=calls_log)
            env["FAKE_SELECTION_PROVISION_MARKER"] = str(marker)

            result = self._run(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(marker.read_text(encoding="utf-8")),
                [
                    {"argv": [
                        "--path", str(Path.home() / ".local/state/life-manager/alpaca-investment-live/selected-strategy.json"),
                        "--reports", str((release_dir / "apps/life-manager/investment-core/reviewed-validation-reports.json").resolve()),
                        "--release-sha", sha,
                    ]},
                    {"argv": [
                        "--path", str(Path.home() / ".local/state/life-manager/alpaca-investment-paper/selected-strategy.json"),
                        "--reports", str((release_dir / "apps/life-manager/investment-core/reviewed-validation-reports.json").resolve()),
                        "--release-sha", sha,
                    ]},
                ],
            )

    def test_descendant_holding_stdout_does_not_stall_the_apply(self):
        # A process started during apply that keeps stdout open made the first
        # automatic run wait until the 1200s timeout.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            release_dir = self._make_release(root, sha)
            self._activate(root, release_dir)
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log,
                                 apply_mode="orphan_holds_stdout")
            started = time.monotonic()
            result = self._run(env)
            self.assertLess(time.monotonic() - started, 20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self._state(root)["status"], "ok")
            self.assertEqual(self._state(root)["changed"], 1)

    def test_promotion_hold_prevents_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            release_dir = self._make_release(root, sha)
            self._activate(root, release_dir)
            (root / "loops").mkdir(exist_ok=True)
            hold_path = root / "loops" / ".promotion-hold"
            import datetime
            hold_path.write_text(json.dumps({
                "sha": "a" * 40, "owner_id": "test-owner", "pr": 1,
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "expires_at": (datetime.datetime.now(datetime.timezone.utc)
                               + datetime.timedelta(hours=1)).isoformat(),
            }))
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log)

            result = self._run(env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("promotion hold active", result.stderr)
            self.assertEqual(self._apply_call_count(calls_log), 0)
            self.assertIsNone(self._state(root))

    def test_non_activated_candidate_release_is_never_applied(self):
        # A sparse/non-activated candidate (LOOPS_ACTIVATE_CURRENT=0, #5916 self-heal canary path)
        # never becomes `current` on its own; simulate the failure mode directly by pointing
        # `current` at a release with release_paths != "ALL" while it matches origin/main's sha,
        # which is exactly what the reconciler's own "refuse incomplete release" guard exists for.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            candidate = self._make_release(root, sha, release_paths="payload.txt")
            self._activate(root, candidate)
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log)

            result = self._run(env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("release is not the full pushed-main build", result.stderr)
            self.assertEqual(self._apply_call_count(calls_log), 0)
            self.assertIsNone(self._state(root))

    def test_apply_failure_is_recorded_and_not_retried_next_tick(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            release_dir = self._make_release(root, sha)
            self._activate(root, release_dir)
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log, apply_mode="fail")

            first = self._run(env)
            self.assertNotEqual(first.returncode, 0)
            self.assertEqual(self._apply_call_count(calls_log), 1)
            state = self._state(root)
            self.assertEqual(state["status"], "error")
            self.assertGreater(state["next_retry_epoch"], 0)

            second = self._run(env)
            self.assertEqual(self._apply_call_count(calls_log), 1,
                             "a failed apply must not retry on the very next tick")

    def test_effect_unknown_fence_refusal_skips_owner_and_continues_fleet_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            release_dir = self._make_release(
                root, sha, loop_ids=("loop-a", "loop-b"),
            )
            self._activate(root, release_dir)
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log,
                                 apply_mode="effect_unknown")
            env["FAKE_EFFECT_UNKNOWN_TARGET"] = "loop-a"

            result = self._run(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            state = self._state(root)
            self.assertEqual(state["status"], "ok")
            self.assertEqual(state["changed"], 1)
            self.assertEqual(state["skipped"], 1)
            self.assertEqual(state["errors"], 0)
            self.assertEqual(
                [line for line in calls_log.read_text().splitlines()
                 if line.startswith("apply ")],
                ["apply target=loop-a", "apply target=loop-b"],
            )
            owner_rows = self._owners_log(root)
            fenced_owner = next(row for row in owner_rows if row["loop_id"] == "loop-a")
            self.assertEqual(fenced_owner["rc"], 1)
            self.assertEqual(fenced_owner["skipped"], 1)
            self.assertEqual(fenced_owner["reason"], "effect-unknown-fence")

    def test_effect_unknown_word_in_other_error_does_not_become_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            release_dir = self._make_release(
                root, sha, loop_ids=("loop-a", "loop-b"),
            )
            self._activate(root, release_dir)
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log,
                                 apply_mode="effect_unknown_lookalike")
            env["FAKE_EFFECT_UNKNOWN_TARGET"] = "loop-a"

            result = self._run(env)

            self.assertNotEqual(result.returncode, 0)
            state = self._state(root)
            self.assertEqual(state["status"], "error")
            self.assertEqual(state["skipped"], 0)
            self.assertEqual(state["errors"], 1)

    def test_compound_effect_unknown_refusal_remains_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            release_dir = self._make_release(root, sha)
            self._activate(root, release_dir)
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log,
                                 apply_mode="effect_unknown_compound")

            result = self._run(env)

            self.assertNotEqual(result.returncode, 0)
            state = self._state(root)
            self.assertEqual(state["status"], "error")
            self.assertEqual(state["skipped"], 0)
            self.assertEqual(state["errors"], 1)

    def test_already_owned_is_treated_as_skip_and_retried_next_tick(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            release_dir = self._make_release(root, sha)
            self._activate(root, release_dir)
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log, apply_mode="already_owned")

            first = self._run(env)
            self.assertEqual(self._apply_call_count(calls_log), 1)
            state = self._state(root)
            self.assertEqual(state["status"], "skip")
            self.assertEqual(state["next_retry_epoch"], 0)

            second = self._run(env)
            self.assertEqual(self._apply_call_count(calls_log), 2,
                             "lock contention is not a failure and must retry next tick")

    def test_second_new_release_within_min_interval_is_not_applied(self):
        # Releases are cut on every merge -- roughly every 20 minutes on a busy night -- and each
        # apply re-bootstraps ~150 idle launchd owners, which loads the host (measured cause of
        # the Mac mini's WindowServer kernel panics under load). A second release activated soon
        # after a successful apply must be coalesced, not applied immediately.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha1 = self._make_repo(root)
            release1 = self._make_release(root, sha1)
            self._activate(root, release1)
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log)

            first = self._run(env)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(self._apply_call_count(calls_log), 1)

            sha2 = self._advance_repo(repo)
            release2 = self._make_release(root, sha2)
            self._activate(root, release2)

            second = self._run(env)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(self._apply_call_count(calls_log), 1,
                             "a release within the min interval since the last success "
                             "must be coalesced, not applied")
            state = self._state(root)
            self.assertEqual(state["sha"], sha1, "state must still reflect the last applied sha")

    def test_after_min_interval_elapses_applies_once_to_latest_sha(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha1 = self._make_repo(root)
            release1 = self._make_release(root, sha1)
            self._activate(root, release1)
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log)

            first = self._run(env)
            self.assertEqual(self._apply_call_count(calls_log), 1)

            # An intermediate release (sha2) is cut and activated inside the min interval and is
            # never observed applying by itself -- it is superseded by sha3 before the interval
            # elapses, which is exactly the coalescing this feature exists for.
            sha2 = self._advance_repo(repo)
            release2 = self._make_release(root, sha2)
            self._activate(root, release2)
            unattended_tick = self._run(env)
            self.assertEqual(self._apply_call_count(calls_log), 1,
                             "sha2 must be coalesced while still inside the min interval")

            sha3 = self._advance_repo(repo)
            release3 = self._make_release(root, sha3)
            self._activate(root, release3)

            # Simulate the min interval having elapsed since the last successful apply.
            self._backdate_last_ok(root, seconds_ago=3600)

            final = self._run(env)
            self.assertEqual(final.returncode, 0, final.stderr)
            self.assertEqual(self._apply_call_count(calls_log), 2,
                             "exactly one apply once the interval elapses")
            state = self._state(root)
            self.assertEqual(state["sha"], sha3,
                             "must apply only the current release, never the coalesced sha2")

    def _owners_log(self, root):
        path = root / "reconciler-state" / "fleet-apply-owners.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def test_one_hung_owner_times_out_others_still_applied_own_id_skipped(self):
        # Applying one `--all` process for the whole fleet means one stuck owner hangs everything
        # for the full budget. Per-owner apply must bound the hung owner to its own timeout, still
        # apply every other owner, record the hung owner in the per-owner log, and mark the whole
        # cycle "partial" rather than silently "ok". The reconciler's own loop id must never be
        # applied to itself.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            release_dir = self._make_release(
                root, sha, loop_ids=("own-id", "loop-a", "loop-hang", "loop-b"))
            self._activate(root, release_dir)
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log, apply_mode="hang_one")
            env["LIFE_MANAGER_LOOP_ID"] = "own-id"
            env["FAKE_HANG_LOOP_ID"] = "loop-hang"
            env["LIFE_MANAGER_FLEET_APPLY_PER_OWNER_TIMEOUT_SECONDS"] = "2"

            started = time.monotonic()
            result = self._run(env)
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 30, "a hung owner must not stall the other owners")
            self.assertNotEqual(result.returncode, 0)

            calls_text = calls_log.read_text()
            self.assertNotIn("target=own-id", calls_text,
                             "the reconciler must never apply itself")
            self.assertIn("target=loop-a", calls_text)
            self.assertIn("target=loop-hang", calls_text)
            self.assertIn("target=loop-b", calls_text,
                          "owners after the hung one must still be applied")

            state = self._state(root)
            self.assertEqual(state["status"], "partial")
            self.assertEqual(state["changed"], 2, "loop-a and loop-b both applied cleanly")
            self.assertGreater(state["next_retry_epoch"], 0)

            owners = {row["loop_id"]: row for row in self._owners_log(root)}
            self.assertIn("loop-hang", owners)
            self.assertNotEqual(owners["loop-hang"]["rc"], 0)
            self.assertEqual(owners["loop-a"]["changed"], 1)
            self.assertEqual(owners["loop-b"]["changed"], 1)
            self.assertNotIn("own-id", owners)

    def _write_plist(self, agents_dir, label, release_sha):
        agents_dir.mkdir(parents=True, exist_ok=True)
        path = agents_dir / f"{label}.plist"
        with path.open("wb") as handle:
            plistlib.dump({
                "Label": label,
                "EnvironmentVariables": {"LIFE_MANAGER_RELEASE_SHA": release_sha},
            }, handle)
        return path

    def test_owner_with_current_release_sha_in_plist_is_skipped_without_apply(self):
        # An owner whose loaded LaunchAgent plist already carries the target release sha needs no
        # apply at all -- per-owner apply costs 5-15s even as a no-op. Skip it cheaply and record it
        # as skipped reason "current" instead of spawning `lm-loop apply`.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            release_dir = self._make_release(
                root, sha, loop_ids=("loop-a", "loop-b"),
                labels={"loop-a": "ai.anicca.loop-a", "loop-b": "ai.anicca.loop-b"})
            self._activate(root, release_dir)
            agents_dir = root / "launch-agents"
            self._write_plist(agents_dir, "ai.anicca.loop-a", sha)
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log)
            env["LIFE_MANAGER_LAUNCH_AGENTS_DIR"] = str(agents_dir)

            result = self._run(env)
            self.assertEqual(result.returncode, 0, result.stderr)

            calls_text = calls_log.read_text() if calls_log.exists() else ""
            self.assertNotIn("target=loop-a", calls_text,
                              "an owner already on the target sha must never be applied")
            self.assertIn("target=loop-b", calls_text)

            owners = {row["loop_id"]: row for row in self._owners_log(root)}
            self.assertEqual(owners["loop-a"]["reason"], "current")
            self.assertEqual(owners["loop-a"]["skipped"], 1)
            self.assertNotIn("reason", owners.get("loop-b", {}))

            state = self._state(root)
            self.assertEqual(state["status"], "ok")
            self.assertEqual(state["changed"], 1)

    def test_owner_that_errored_previous_attempt_for_same_sha_is_ordered_last(self):
        # Every attempt restarts from the top of the (alphabetically sorted) registry, so an owner
        # that keeps failing near the front can starve every owner after it. Owners that errored or
        # timed out on a previous attempt for this exact sha must be tried last instead.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            # Alphabetically "aaa-timeout" sorts before "zzz-clean"; without reordering it would be
            # applied first.
            release_dir = self._make_release(root, sha, loop_ids=("aaa-timeout", "zzz-clean"))
            self._activate(root, release_dir)
            state_root = root / "reconciler-state"
            state_root.mkdir(parents=True, exist_ok=True)
            owners_log_path = state_root / "fleet-apply-owners.jsonl"
            owners_log_path.write_text(json.dumps({
                "sha": sha, "loop_id": "aaa-timeout", "rc": 124, "seconds": 120,
                "changed": 0, "skipped": 0,
            }, sort_keys=True) + "\n")
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log)

            result = self._run(env)
            self.assertEqual(result.returncode, 0, result.stderr)

            calls_text = calls_log.read_text()
            self.assertLess(
                calls_text.index("target=zzz-clean"), calls_text.index("target=aaa-timeout"),
                "the owner that errored/timed out last attempt for this sha must be tried last")

    def test_owner_that_succeeded_after_previous_error_for_different_sha_is_not_deprioritized(self):
        # A failure recorded against a *different* sha must not push an owner to the back for this
        # sha's run.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            release_dir = self._make_release(root, sha, loop_ids=("aaa-owner", "zzz-owner"))
            self._activate(root, release_dir)
            state_root = root / "reconciler-state"
            state_root.mkdir(parents=True, exist_ok=True)
            owners_log_path = state_root / "fleet-apply-owners.jsonl"
            owners_log_path.write_text(json.dumps({
                "sha": "f" * 40, "loop_id": "aaa-owner", "rc": 124, "seconds": 120,
                "changed": 0, "skipped": 0,
            }, sort_keys=True) + "\n")
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log)

            result = self._run(env)
            self.assertEqual(result.returncode, 0, result.stderr)

            calls_text = calls_log.read_text()
            self.assertLess(
                calls_text.index("target=aaa-owner"), calls_text.index("target=zzz-owner"),
                "a prior failure for an unrelated sha must not reorder this run")

    def test_earn_revenue_owners_are_applied_before_growth_owners(self):
        """Revenue contract owners must not starve behind slow growth publishers."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            release_dir = self._make_release(
                root,
                sha,
                loop_ids=("aaa-growth", "zzz-contract"),
                entry_overrides={
                    "aaa-growth": {
                        "domain": "growth", "admission_class": "revenue",
                        "priority": "revenue",
                    },
                    "zzz-contract": {
                        "domain": "earn", "admission_class": "revenue",
                        "priority": "revenue",
                    },
                },
            )
            self._activate(root, release_dir)
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log)

            result = self._run(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            calls_text = calls_log.read_text()
            self.assertLess(
                calls_text.index("target=zzz-contract"),
                calls_text.index("target=aaa-growth"),
                "earn/revenue owners must run before growth owners",
            )

    def test_owner_is_not_started_when_remaining_budget_is_less_than_per_owner_timeout(self):
        """A bounded fleet budget must not be overrun by starting another full owner timeout."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            release_dir = self._make_release(
                root,
                sha,
                loop_ids=("first-earn", "second-earn"),
                entry_overrides={
                    "first-earn": {"domain": "earn", "priority": "revenue"},
                    "second-earn": {"domain": "earn", "priority": "revenue"},
                },
            )
            self._activate(root, release_dir)
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log, apply_mode="slow_first")
            env["FAKE_SLOW_LOOP_ID"] = "first-earn"
            env["LIFE_MANAGER_FLEET_APPLY_TIMEOUT_SECONDS"] = "4"
            env["LIFE_MANAGER_FLEET_APPLY_PER_OWNER_TIMEOUT_SECONDS"] = "3"

            result = self._run(env)

            calls_text = calls_log.read_text()
            self.assertIn("target=first-earn", calls_text)
            self.assertNotIn(
                "target=second-earn",
                calls_text,
                "the next owner must wait for a later retry when less than one full owner timeout remains",
            )
            self.assertNotEqual(result.returncode, 0)
            state = self._state(root)
            self.assertEqual(state["status"], "partial")
            self.assertIn("budget exceeded", state["message"])

    def test_partial_apply_honors_backoff_before_same_release_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, sha = self._make_repo(root)
            release_dir = self._make_release(
                root,
                sha,
                loop_ids=("first-earn", "second-earn"),
                entry_overrides={
                    "first-earn": {"domain": "earn", "priority": "revenue"},
                    "second-earn": {"domain": "earn", "priority": "revenue"},
                },
            )
            self._activate(root, release_dir)
            calls_log = root / "calls.log"
            env = self._base_env(root, repo, calls_log=calls_log, apply_mode="slow_first")
            env["FAKE_SLOW_LOOP_ID"] = "first-earn"
            env["LIFE_MANAGER_FLEET_APPLY_TIMEOUT_SECONDS"] = "4"
            env["LIFE_MANAGER_FLEET_APPLY_PER_OWNER_TIMEOUT_SECONDS"] = "3"

            first = self._run(env)
            self.assertNotEqual(first.returncode, 0)
            self.assertEqual(self._apply_call_count(calls_log), 1)
            first_state = self._state(root)
            self.assertEqual(first_state["status"], "partial")
            self.assertGreater(first_state["next_retry_epoch"], time.time())

            second = self._run(env)
            self.assertEqual(
                self._apply_call_count(calls_log),
                1,
                "a partial result with a future retry time must not start another fleet apply",
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(self._state(root)["status"], "partial")


    def test_guarded_retirement_runs_before_loops_and_counts_change_or_replay(self):
        for was_loaded in (True, False):
            with self.subTest(was_loaded=was_loaded), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                repo, sha = self._make_repo(root)
                release = self._make_release(root, sha)
                registry_path = release / "config/loop-registry.json"
                registry = json.loads(registry_path.read_text())
                label = "ai.anicca.orphan"
                registry["guarded_retired_labels"] = {label: {"expected_arguments_sha256": "a" * 64, "missing_entrypoint": "/missing.py"}}
                registry_path.write_text(json.dumps(registry))
                self._activate(root, release)
                calls = root / "calls.log"
                env = self._base_env(root, repo, calls_log=calls)
                env.update({"FAKE_APPLY_MODE": "retire_guarded", "FAKE_RETIRE_TARGET": label, "FAKE_RETIRE_LOADED": str(was_loaded).lower()})
                first = self._run(env)
                self.assertEqual(first.returncode, 0, first.stderr)
                applies = [line for line in calls.read_text().splitlines() if line.startswith("apply ")]
                self.assertEqual(applies, [f"apply target={label}", "apply target=loop-a"])
                self.assertEqual(self._state(root)["changed"], 2 if was_loaded else 1)
                self.assertEqual(self._state(root)["skipped"], 0 if was_loaded else 1)
                second = self._run(env)
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertEqual(self._apply_call_count(calls), 2)


    def test_guarded_exit_zero_requires_exact_retirement_readback(self):
        invalid = ['[]', 'not-json', '[{"ok":true,"label":"other","retired":true,"was_loaded":false,"removed_plist":false}]', '[{"ok":true,"label":"ai.anicca.orphan","retired":true,"was_loaded":0,"removed_plist":false}]']
        for payload in invalid:
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                repo, sha = self._make_repo(root)
                release = self._make_release(root, sha)
                p = release / 'config/loop-registry.json'
                registry = json.loads(p.read_text())
                label = 'ai.anicca.orphan'
                registry['guarded_retired_labels'] = {label: {}}
                p.write_text(json.dumps(registry))
                self._activate(root, release)
                calls = root / 'calls.log'
                env = self._base_env(root, repo, calls_log=calls)
                env.update({'FAKE_APPLY_MODE':'retire_bad', 'FAKE_RETIRE_TARGET':label, 'FAKE_RETIRE_RESPONSE':payload})
                result = self._run(env)
                self.assertNotEqual(result.returncode, 0)
                state = self._state(root)
                self.assertEqual(state['status'], 'error')
                self.assertEqual(state['errors'], 1)
                self.assertEqual(state['changed'], 1)
                self.assertIn('apply target=loop-a', calls.read_text())


    def test_retirement_ignores_generic_changed_and_skipped_fields(self):
        for was_loaded in (False, True):
            with self.subTest(was_loaded=was_loaded), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                repo, sha = self._make_repo(root)
                release = self._make_release(root, sha)
                p = release/'config/loop-registry.json'
                registry = json.loads(p.read_text())
                label = 'ai.anicca.orphan'
                registry['guarded_retired_labels'] = {label: {}}
                p.write_text(json.dumps(registry))
                self._activate(root, release)
                env = self._base_env(root, repo, calls_log=root/'calls.log')
                payload = [{'ok':True, 'label':label, 'retired':True, 'was_loaded':was_loaded,
                            'removed_plist':False, 'changed':not was_loaded, 'skipped':was_loaded}]
                env.update({'FAKE_APPLY_MODE':'retire_bad','FAKE_RETIRE_TARGET':label,'FAKE_RETIRE_RESPONSE':json.dumps(payload)})
                result = self._run(env)
                self.assertEqual(result.returncode, 0, result.stderr)
                state = self._state(root)
                self.assertEqual(state['changed'], 2 if was_loaded else 1)
                self.assertEqual(state['skipped'], 0 if was_loaded else 1)


    def test_owner_rows_preserve_native_run_and_claimed_occurrence_context(self):
        for native in (True, False):
            with self.subTest(native=native), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                repo, sha = self._make_repo(root)
                release = self._make_release(root, sha, loop_ids=('loop-a','loop-b'),
                                             labels={'loop-a':'ai.anicca.loop-a','loop-b':'ai.anicca.loop-b'})
                self._activate(root, release)
                agents = root/'agents'
                self._write_plist(agents, 'ai.anicca.loop-a', sha)
                env = self._base_env(root, repo, calls_log=root/'calls.log')
                env['LIFE_MANAGER_LAUNCH_AGENTS_DIR'] = str(agents)
                env.pop('LIFE_MANAGER_RUN_ID', None)
                env.pop('LIFE_MANAGER_OCCURRENCE_ID', None)
                if native:
                    env.update({'LIFE_MANAGER_RUN_ID':'native-wake-1', 'LIFE_MANAGER_OCCURRENCE_ID':'life-manager-release-reconciler:queued-older-claim'})
                result = self._run(env)
                self.assertEqual(result.returncode, 0, result.stderr)
                rows = self._owners_log(root)
                self.assertEqual(len(rows), 2)
                for row in rows:
                    self.assertIn('run_id', row)
                    self.assertEqual(row['run_id'], 'native-wake-1' if native else None)
                    self.assertEqual(row['occurrence_id'], 'life-manager-release-reconciler:queued-older-claim' if native else None)
                    self.assertEqual(row['owner_id'], 'life-manager-release-reconciler')
                    self.assertIsNotNone(datetime.fromisoformat(row['timestamp']).utcoffset())
                self.assertEqual({row['loop_id'] for row in rows}, {'loop-a','loop-b'})


if __name__ == "__main__":
    unittest.main()
