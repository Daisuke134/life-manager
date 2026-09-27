import json
import os
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "bin/reconcile-agent-runner-release.sh"

FAKE_LM_LOOP = """#!/bin/sh
set -eu
echo "$@" >> "$FAKE_LM_LOOP_CALLS_LOG"
if [ "$1" = "reconcile" ]; then
  exit 0
fi
if [ "$1" = "apply" ]; then
  case "${FAKE_APPLY_MODE:-ok}" in
    ok)
      echo '[{"ok":true,"label":"a","release_sha":"x","changed":true},{"ok":true,"label":"b","release_sha":"x","changed":false,"skipped":"effect-unknown-fence"}]'
      exit 0
      ;;
    orphan_holds_stdout)
      sleep 60 &
      echo '[{"ok":true,"label":"a","release_sha":"x","changed":true}]'
      exit 0
      ;;
    already_owned)
      echo '{"ok": false, "error": "production apply is already owned"}'
      exit 1
      ;;
    fail)
      echo '{"ok": false, "error": "boom"}'
      exit 1
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

    def _make_release(self, root, sha, *, release_paths="ALL"):
        release_dir = root / "loops" / "releases" / f"rel-{sha}"
        (release_dir / "bin").mkdir(parents=True)
        (release_dir / "RELEASE.json").write_text(
            json.dumps({"sha": sha, "release_paths": release_paths}))
        lm_loop = release_dir / "bin" / "lm-loop"
        lm_loop.write_text(FAKE_LM_LOOP)
        lm_loop.chmod(lm_loop.stat().st_mode | stat.S_IEXEC)
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


if __name__ == "__main__":
    unittest.main()
