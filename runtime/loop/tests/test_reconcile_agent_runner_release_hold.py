import datetime
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "bin/reconcile-agent-runner-release.sh"


def _iso(delta_seconds):
    return (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(seconds=delta_seconds)).isoformat().replace("+00:00", "Z")


class ReconcileAgentRunnerReleaseHoldTest(unittest.TestCase):
    """Blocker 2 (independent review): the release-reconciler cuts+activates whatever is on
    origin/main every 60s, independent of the unattended merge guard's own promotion. A bound
    recovery PR's canary/health/rollback decision is meaningless if this reconciler fleet-activates
    the same merged commit before that decision lands. The guard freezes it with a promotion-hold
    file; these tests prove the reconciler actually honours that file before it touches `current`.
    """

    def _run(self, env_overrides):
        return subprocess.run(
            ["/bin/bash", str(SCRIPT)],
            env={
                "PATH": "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin",
                "HOME": env_overrides.get("HOME", "/nonexistent"),
                **env_overrides,
            },
            capture_output=True, text=True, check=False,
        )

    def test_a_non_expired_hold_skips_the_cycle_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            loops_root = Path(directory) / "loops"
            loops_root.mkdir()
            hold_path = loops_root / ".promotion-hold"
            hold_path.write_text(json.dumps({
                "sha": "a" * 40, "owner_id": "test-owner", "pr": 1234,
                "created_at": _iso(-60), "expires_at": _iso(3600),
            }))
            # SOURCE_REPO is deliberately not a real git repo: a live hold must short-circuit
            # BEFORE the script ever touches git, so this must never be reached.
            result = self._run({
                "LOOPS_ROOT": str(loops_root),
                "SOURCE_REPO": str(Path(directory) / "does-not-exist"),
                "LIFE_MANAGER_SOURCE_REPO": str(Path(directory) / "does-not-exist"),
            })
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("promotion hold active", result.stderr)
            self.assertIn("skipping cut/advance of current", result.stderr)

    def test_b_an_expired_hold_is_logged_and_ignored_so_reconciliation_proceeds(self):
        with tempfile.TemporaryDirectory() as directory:
            loops_root = Path(directory) / "loops"
            loops_root.mkdir()
            hold_path = loops_root / ".promotion-hold"
            hold_path.write_text(json.dumps({
                "sha": "a" * 40, "owner_id": "test-owner", "pr": 1234,
                "created_at": _iso(-7200), "expires_at": _iso(-60),
            }))
            missing_repo = Path(directory) / "does-not-exist"
            result = self._run({
                "LOOPS_ROOT": str(loops_root),
                "SOURCE_REPO": str(missing_repo),
                "LIFE_MANAGER_SOURCE_REPO": str(missing_repo),
            })
            # The expired hold must not short-circuit: the script proceeds into `git fetch` against
            # a repo that does not exist and fails loudly there, never at "exit 0" for the hold.
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("expired or unreadable", result.stderr)
            self.assertNotIn("skipping cut/advance of current", result.stderr)

    def test_c_a_missing_hold_file_is_silent_and_reconciliation_proceeds(self):
        with tempfile.TemporaryDirectory() as directory:
            loops_root = Path(directory) / "loops"
            loops_root.mkdir()
            missing_repo = Path(directory) / "does-not-exist"
            result = self._run({
                "LOOPS_ROOT": str(loops_root),
                "SOURCE_REPO": str(missing_repo),
                "LIFE_MANAGER_SOURCE_REPO": str(missing_repo),
            })
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("promotion hold", result.stderr)

    def test_d_hold_path_is_injectable_via_env(self):
        with tempfile.TemporaryDirectory() as directory:
            loops_root = Path(directory) / "loops"
            loops_root.mkdir()
            custom_hold = Path(directory) / "custom-hold.json"
            custom_hold.write_text(json.dumps({
                "sha": "a" * 40, "owner_id": "test-owner", "pr": 1234,
                "created_at": _iso(-60), "expires_at": _iso(3600),
            }))
            missing_repo = Path(directory) / "does-not-exist"
            result = self._run({
                "LOOPS_ROOT": str(loops_root),
                "SOURCE_REPO": str(missing_repo),
                "LIFE_MANAGER_SOURCE_REPO": str(missing_repo),
                "LIFE_MANAGER_PROMOTION_HOLD_PATH": str(custom_hold),
            })
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(custom_hold), result.stderr)


if __name__ == "__main__":
    unittest.main()
