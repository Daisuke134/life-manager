import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class SolFundingContractTests(unittest.TestCase):
    def test_registry_owns_one_finite_portable_sol_funding_wake(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["sol-funding"]
        self.assertEqual(row["label"], "ai.anicca.sol-funding")
        self.assertEqual(row["entrypoint"], "skills/earn/sol-funding-owner")
        self.assertEqual(row["cadence"], {"start_interval_seconds": 60})
        self.assertEqual(row["effect_class"], "money")
        self.assertEqual(row["state_root"], "~/.local/state/life-manager/sol-funding")
        self.assertIn("com.anicca.sol-funding", registry["retired_labels"])
        self.assertFalse((ROOT / "skills/earn/com.anicca.sol-funding.plist").exists())
        self.assertFalse((ROOT / "skills/earn/sol-funding-daemon.sh").exists())

    def test_owner_loads_private_env_and_uses_managed_python(self):
        owner = ROOT / "skills/earn/sol-funding-owner"
        self.assertTrue(os.access(owner, os.X_OK))
        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / ".env"
            fake_python = Path(temporary) / "python"
            env_file.write_text(
                "ANICCA_SOLANA_KEY=sentinel-key\n"
                "SWAP_RECIPIENT=0x1111111111111111111111111111111111111111\n"
            )
            fake_python.write_text("#!/bin/sh\nenv\n")
            fake_python.chmod(0o700)
            result = subprocess.run(
                [str(owner)],
                env={
                    **os.environ,
                    "LIFE_MANAGER_REPO": str(ROOT),
                    "LIFE_MANAGER_ENV_FILE": str(env_file),
                    "LIFE_MANAGER_PYTHON": str(fake_python),
                },
                check=True,
                capture_output=True,
                text=True,
            )
        self.assertIn("ANICCA_SOLANA_KEY=sentinel-key", result.stdout)
        self.assertIn(
            "SWAP_RECIPIENT=0x1111111111111111111111111111111111111111",
            result.stdout,
        )

    def test_runtime_locks_solders_and_source_has_no_user_recipient_default(self):
        requirements = (ROOT / "requirements-runtime.txt").read_text().splitlines()
        self.assertIn("solders==0.27.1", requirements)
        source = (ROOT / "skills/earn/sol-to-usdc.py").read_text()
        self.assertIn('os.environ.get("SWAP_RECIPIENT")', source)
        self.assertNotIn('os.environ.get("SWAP_RECIPIENT",', source)

    def test_future_result_identity_binds_the_host_occurrence_without_claiming_confirmation(self):
        source = (ROOT / "skills/earn/sol-to-usdc.py").read_text()
        self.assertIn("LIFE_MANAGER_OCCURRENCE_ID", source)
        self.assertIn('"occurrence_id"', source)
        self.assertIn('"provider_receipt_id"', source)
        self.assertIn('"official_readback_ref"', source)
        self.assertIn('effect_status="submitted"', source)
        self.assertIn("append_future_receipt", source)
        self.assertIn("sol-funding-receipts.jsonl", source)
        self.assertIn("relay_check_endpoint", source)
        self.assertIn("destination_tx_hash", source)

    def test_unconfigured_wake_emits_secret_free_occurrence_bound_no_effect_result(self):
        result = subprocess.run(
            ["python3", str(ROOT / "skills/earn/sol-to-usdc.py")],
            env={
                **os.environ,
                "LIFE_MANAGER_OCCURRENCE_ID": "sol-funding:fixture-1",
                "SWAP_SOLANA_KEY": "",
                "ANICCA_SOLANA_KEY": "",
                "SWAP_RECIPIENT": "",
            },
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(payload, {
            "effect_status": "not_started",
            "kind": "sol_funding_result",
            "occurrence_id": "sol-funding:fixture-1",
            "official_readback_ref": None,
            "provider_receipt_id": None,
            "schema_version": 1,
            "status": "not_configured",
        })


if __name__ == "__main__":
    unittest.main()
