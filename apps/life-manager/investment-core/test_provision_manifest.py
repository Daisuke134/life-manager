import json
import stat
import tempfile
import unittest
from pathlib import Path

from provision_manifest import ManifestProvisionError, provision_manifest


class ProvisionManifestTests(unittest.TestCase):
    def test_absent_manifest_is_created_with_zero_capital_and_alpaca_reader(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "investment" / "inputs.json"

            result = provision_manifest(
                path,
                "~/.local/state/life-manager/alpaca-investment-live",
            )

            self.assertEqual(result["status"], "created")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {
                "alpaca_state_dir": "~/.local/state/life-manager/alpaca-investment-live",
                "available_capital_usd": "0",
                "snapshot_specs": [],
            })
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)

    def test_existing_valid_manifest_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inputs.json"
            original = {
                "snapshot_specs": ["alpaca=/tmp/snapshot.json"],
                "owner_cash_flow_path": "/tmp/owner-flow.json",
                "available_capital_usd": "0",
            }
            path.write_text(json.dumps(original), encoding="utf-8")

            result = provision_manifest(
                path,
                "~/.local/state/life-manager/alpaca-investment-live",
            )

            self.assertEqual(result["status"], "existing")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), original)

    def test_existing_invalid_manifest_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inputs.json"
            path.write_text('{"snapshot_specs":["broken"]}', encoding="utf-8")
            before = path.read_bytes()

            with self.assertRaisesRegex(ManifestProvisionError, "existing_manifest_invalid"):
                provision_manifest(
                    path,
                    "~/.local/state/life-manager/alpaca-investment-live",
                )

            self.assertEqual(path.read_bytes(), before)

    def test_nonzero_capital_is_rejected_by_safe_provisioner(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ManifestProvisionError, "capital_must_be_zero"):
                provision_manifest(
                    Path(directory) / "inputs.json",
                    "~/.local/state/life-manager/alpaca-investment-live",
                    available_capital_usd="100",
                )


if __name__ == "__main__":
    unittest.main()
