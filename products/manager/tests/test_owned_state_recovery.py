"""Backups are consistent snapshots; restored state is read-only quarantined."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from manager_core.state_recovery import (
    StateRecoveryError,
    create_backup,
    restore_backup,
    verify_backup,
)
from manager_core.owned_cycle import CycleStore, run_owned_cycle
from test_candidate_verification import NOW


class OwnedStateRecoveryTests(unittest.TestCase):
    @staticmethod
    def prepare_fixture(root):
        from test_digital_cycle_acceptance import CycleAcceptanceTests
        return CycleAcceptanceTests().prepare(root)

    def test_backup_is_integrity_checked_and_restore_is_quarantined(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, store, host, git = self.prepare_fixture(root / "fixture")
            store.due(config, NOW)
            backup = root / "backup-001"

            receipt = create_backup(store.root, backup, source_root=Path(__file__).resolve().parents[1])
            self.assertEqual(receipt["status"], "VERIFIED_SNAPSHOT_ONLY")
            manifest = verify_backup(backup)
            self.assertEqual(manifest["database_file"], "cycle.sqlite")

            restored = root / "restored-state"
            restore_backup(backup, restored, source_root=Path(__file__).resolve().parents[1])
            self.assertTrue((restored / "RESTORE_RECONCILIATION_REQUIRED.json").is_file())
            restored_bytes = (restored / "cycle.sqlite").read_bytes()
            restored_store = CycleStore(restored)
            result = run_owned_cycle(config, restored_store, host=host, now=NOW)
            self.assertEqual(result["status"], "RESTORE_RECONCILIATION_REQUIRED")
            self.assertFalse(result["deployed"])
            from manager_core import owned_cycle
            from manager_core.digital_handoff import prepare_owned_change
            packet = prepare_owned_change(host.context, host.assessment, host.scope, NOW).packet
            direct = owned_cycle.dispatch_owned_once(restored_store, host, packet, NOW)
            self.assertEqual(direct["status"], "RESTORE_RECONCILIATION_REQUIRED")
            self.assertEqual(direct["writes"], 0)
            self.assertEqual((restored / "cycle.sqlite").read_bytes(), restored_bytes)
            self.assertEqual(git.git("rev-list", "--count", "HEAD"), "1")

    def test_backup_refuses_live_owner_and_rejects_modified_snapshot(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, store, host, git = self.prepare_fixture(root / "fixture")
            backup = root / "backup-001"
            with store.owner_lock():
                with self.assertRaises(StateRecoveryError):
                    create_backup(store.root, backup, source_root=Path(__file__).resolve().parents[1])

            create_backup(store.root, backup, source_root=Path(__file__).resolve().parents[1])
            database = backup / "cycle.sqlite"
            database.write_bytes(database.read_bytes() + b"corruption")
            with self.assertRaises(StateRecoveryError):
                verify_backup(backup)

    def test_backup_and_restore_paths_must_be_private_and_non_overwriting(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, store, host, git = self.prepare_fixture(root / "fixture")
            manager_root = Path(__file__).resolve().parents[1]
            with self.assertRaises(StateRecoveryError):
                create_backup(manager_root, root / "bad-backup", source_root=manager_root)
            backup = root / "backup-001"
            create_backup(store.root, backup, source_root=manager_root)
            with self.assertRaises(StateRecoveryError):
                restore_backup(backup, store.root, source_root=manager_root)
            nonempty = root / "nonempty"
            nonempty.mkdir()
            (nonempty / "keep.txt").write_text("keep")
            with self.assertRaises(StateRecoveryError):
                restore_backup(backup, nonempty, source_root=manager_root)
            self.assertEqual((nonempty / "keep.txt").read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
