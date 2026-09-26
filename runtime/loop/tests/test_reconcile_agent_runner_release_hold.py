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

    def test_b_an_expired_hold_with_no_terminal_ledger_row_stays_frozen(self):
        # Medium finding from independent re-review: if the guard crashes mid-promotion, nothing
        # ever clears the hold. Once its TTL passes, "ignoring" it here would fleet-activate the
        # unverified merged commit -- exactly the blocker this hold exists to prevent, just on a
        # delay. An expired hold with no proof of resolution must stay frozen, not proceed.
        with tempfile.TemporaryDirectory() as directory:
            loops_root = Path(directory) / "loops"
            loops_root.mkdir()
            hold_path = loops_root / ".promotion-hold"
            sha = "a" * 40
            hold_path.write_text(json.dumps({
                "sha": sha, "owner_id": "test-owner", "pr": 1234, "pid": 999999999,
                "created_at": _iso(-7200), "expires_at": _iso(-60),
            }))
            missing_repo = Path(directory) / "does-not-exist"
            empty_ledger = Path(directory) / "promotions.jsonl"
            result = self._run({
                "LOOPS_ROOT": str(loops_root),
                "SOURCE_REPO": str(missing_repo),
                "LIFE_MANAGER_SOURCE_REPO": str(missing_repo),
                "LIFE_MANAGER_PROMOTIONS_LEDGER_PATH": str(empty_ledger),
            })
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"promotion_hold_orphaned sha={sha} pr=1234", result.stderr)
            self.assertNotIn("skipping cut/advance of current", result.stderr)

    def test_an_expired_hold_with_a_terminal_ok_row_is_treated_as_released(self):
        with tempfile.TemporaryDirectory() as directory:
            loops_root = Path(directory) / "loops"
            loops_root.mkdir()
            hold_path = loops_root / ".promotion-hold"
            sha = "b" * 40
            hold_path.write_text(json.dumps({
                "sha": sha, "owner_id": "test-owner", "pr": 5555, "pid": 999999999,
                "created_at": _iso(-7200), "expires_at": _iso(-60),
            }))
            ledger_path = Path(directory) / "promotions.jsonl"
            ledger_path.write_text(json.dumps({
                "record_type": "recovery_promotion_terminal", "merged_sha": sha, "pr": 5555,
                "ok": True, "rolled_back": False, "ts": _iso(-30),
            }) + "\n")
            missing_repo = Path(directory) / "does-not-exist"
            result = self._run({
                "LOOPS_ROOT": str(loops_root),
                "SOURCE_REPO": str(missing_repo),
                "LIFE_MANAGER_SOURCE_REPO": str(missing_repo),
                "LIFE_MANAGER_PROMOTIONS_LEDGER_PATH": str(ledger_path),
            })
            # A terminal row means the promotion genuinely finished -- the reconciler proceeds into
            # `git fetch` against a repo that does not exist and fails loudly there, not at the hold.
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("terminal ledger row; treating as released", result.stderr)
            self.assertNotIn("promotion_hold_orphaned", result.stderr)

    def test_an_expired_hold_with_a_terminal_rolled_back_row_is_treated_as_released(self):
        with tempfile.TemporaryDirectory() as directory:
            loops_root = Path(directory) / "loops"
            loops_root.mkdir()
            hold_path = loops_root / ".promotion-hold"
            sha = "c" * 40
            hold_path.write_text(json.dumps({
                "sha": sha, "owner_id": "test-owner", "pr": 7777, "pid": 999999999,
                "created_at": _iso(-7200), "expires_at": _iso(-60),
            }))
            ledger_path = Path(directory) / "promotions.jsonl"
            ledger_path.write_text(json.dumps({
                "record_type": "recovery_promotion_terminal", "merged_sha": sha, "pr": 7777,
                "ok": False, "rolled_back": True, "ts": _iso(-30),
            }) + "\n")
            missing_repo = Path(directory) / "does-not-exist"
            result = self._run({
                "LOOPS_ROOT": str(loops_root),
                "SOURCE_REPO": str(missing_repo),
                "LIFE_MANAGER_SOURCE_REPO": str(missing_repo),
                "LIFE_MANAGER_PROMOTIONS_LEDGER_PATH": str(ledger_path),
            })
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("terminal ledger row; treating as released", result.stderr)

    def test_an_expired_hold_with_only_a_non_terminal_row_for_the_sha_stays_frozen(self):
        with tempfile.TemporaryDirectory() as directory:
            loops_root = Path(directory) / "loops"
            loops_root.mkdir()
            hold_path = loops_root / ".promotion-hold"
            sha = "d" * 40
            hold_path.write_text(json.dumps({
                "sha": sha, "owner_id": "test-owner", "pr": 8888, "pid": 999999999,
                "created_at": _iso(-7200), "expires_at": _iso(-60),
            }))
            ledger_path = Path(directory) / "promotions.jsonl"
            # ok:false and rolled_back:false -- the promotion failed and remediation never landed.
            ledger_path.write_text(json.dumps({
                "record_type": "recovery_promotion_terminal", "merged_sha": sha, "pr": 8888,
                "ok": False, "rolled_back": False, "ts": _iso(-30),
            }) + "\n")
            missing_repo = Path(directory) / "does-not-exist"
            result = self._run({
                "LOOPS_ROOT": str(loops_root),
                "SOURCE_REPO": str(missing_repo),
                "LIFE_MANAGER_SOURCE_REPO": str(missing_repo),
                "LIFE_MANAGER_PROMOTIONS_LEDGER_PATH": str(ledger_path),
            })
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"promotion_hold_orphaned sha={sha} pr=8888", result.stderr)

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
