from __future__ import annotations

import hashlib
import importlib.util
import json
import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "skills" / "affiliate" / "scripts" / "machine_capability_inventory.py"
RUNNER_GATE = REPO_ROOT / "skills" / "affiliate" / "scripts" / "agent_runner.py"


class MachineCapabilityInventoryTests(unittest.TestCase):
    def require_script(self) -> Path:
        self.assertTrue(
            SCRIPT.is_file(),
            f"feature missing: expected machine capability inventory at {SCRIPT}",
        )
        return SCRIPT

    def run_inventory(
        self,
        script: Path,
        request: Path,
        receipt: Path,
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["python3", str(script), "--request", str(request), "--receipt", str(receipt)],
            text=True,
            capture_output=True,
            check=False,
        )

    def write_json(self, path: Path, value: object) -> None:
        path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")

    def sha256(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def load_module(self, script: Path) -> Any:
        spec = importlib.util.spec_from_file_location(script.stem, script)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_inventory_is_deterministic_for_macos_app(self) -> None:
        script = self.require_script()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "Example.app"
            app_binary = app / "Contents" / "MacOS" / "Example"
            app_binary.parent.mkdir(parents=True)
            app_binary.write_bytes(b"app executable\n")
            app_binary.chmod(0o755)
            info = app / "Contents" / "Info.plist"
            with info.open("wb") as stream:
                plistlib.dump(
                    {
                        "CFBundleIdentifier": "com.example.affiliate",
                        "CFBundleShortVersionString": "2.4.1",
                    },
                    stream,
                )

            request = root / "request.json"
            receipt = root / "state" / "machine-capability.json"
            self.write_json(
                request,
                {
                    "capabilities": [{
                        "name": "example-app",
                        "kind": "macos_app",
                        "path": str(app),
                        "executable": "Example",
                    }]
                },
            )

            first = self.run_inventory(script, request, receipt)
            self.assertEqual(first.returncode, 0, first.stderr)
            first_bytes = receipt.read_bytes()
            payload = json.loads(first_bytes)
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["status"], "READY")
            self.assertEqual(payload["platform"], "macOS")
            self.assertTrue(payload["architecture"])
            self.assertEqual(
                payload["request_sha256"], self.sha256(request)
            )
            self.assertEqual(
                [entry["name"] for entry in payload["capabilities"]],
                ["example-app"],
            )

            records = {entry["name"]: entry for entry in payload["capabilities"]}
            self.assertEqual(records["example-app"]["kind"], "macos_app")
            self.assertEqual(records["example-app"]["canonical_path"], str(app.resolve()))
            self.assertEqual(records["example-app"]["version"], "2.4.1")
            self.assertEqual(records["example-app"]["size_bytes"], app_binary.stat().st_size)
            self.assertEqual(records["example-app"]["sha256"], self.sha256(app_binary))

            second = self.run_inventory(script, request, receipt)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(receipt.read_bytes(), first_bytes)
            self.assertEqual(list(receipt.parent.glob(".*")), [])

            module = self.load_module(script)
            unsupported_request = root / "unsupported-request.json"
            unsupported_receipt = root / "unsupported-receipt.json"
            self.write_json(
                unsupported_request,
                {"capabilities": [{
                    "name": "example-app",
                    "kind": "macos_app",
                    "path": str(app),
                    "executable": "Example",
                }]},
            )
            with mock.patch.object(module.platform, "system", return_value="Linux"), mock.patch.object(
                module.sys,
                "argv",
                ["machine_capability_inventory.py", "--request", str(unsupported_request), "--receipt", str(unsupported_receipt)],
            ):
                with self.assertRaises(module.InventoryError):
                    module.main()
            self.assertFalse(unsupported_receipt.exists())

    def test_codex_cli_receipt_pins_path_version_and_hash_before_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "codex"
            executable.write_text(
                "#!/bin/sh\n"
                "if [ -z \"${CODEX_HOME:-}\" ]; then printf 'temporary HOME warning\\n' >&2; fi\n"
                "printf 'codex-cli 9.8.7\\n'\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)
            request = root / "request.json"
            receipt = root / "machine-capability.json"
            self.write_json(request, {"capabilities": [{
                "name": "codex-cli",
                "kind": "codex_cli",
                "path": str(executable),
            }]})

            result = self.run_inventory(self.require_script(), request, receipt)
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads(receipt.read_text(encoding="utf-8"))["capabilities"][0]
            self.assertEqual(record["canonical_path"], str(executable.resolve()))
            self.assertEqual(record["version"], "9.8.7")
            self.assertEqual(record["sha256"], self.sha256(executable))

            gate = self.load_module(RUNNER_GATE)
            self.assertEqual(gate.verify_codex_pin(receipt), executable.resolve())
            evidence = root / "evidence"
            model_receipt = gate.write_model_call_pin(receipt, evidence)
            model_record = json.loads(model_receipt.read_text(encoding="utf-8"))
            self.assertEqual(model_record["canonical_path"], str(executable.resolve()))
            self.assertEqual(model_record["version"], "9.8.7")
            self.assertEqual(model_record["sha256"], self.sha256(executable))
            self.assertEqual(model_receipt.stat().st_mode & 0o777, 0o600)
            executable.write_text("#!/bin/sh\nprintf 'codex-cli 9.8.8\\n'\n", encoding="utf-8")
            executable.chmod(0o755)
            with self.assertRaises(gate.PinError):
                gate.verify_codex_pin(receipt)

    def test_stale_codex_pin_refreshes_from_secure_sibling_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            old = root / "codex-old"
            new = root / "codex-new"
            stable = root / "codex"
            old.write_text("#!/bin/sh\nprintf 'codex-cli 9.8.7\\n'\n", encoding="utf-8")
            new.write_text("#!/bin/sh\nprintf 'codex-cli 9.8.8\\n'\n", encoding="utf-8")
            old.chmod(0o755)
            new.chmod(0o755)
            stable.symlink_to(old)
            request = root / "codex-request.json"
            receipt = root / "codex-capability.json"
            self.write_json(request, {"capabilities": [{
                "name": "codex-cli",
                "kind": "codex_cli",
                "path": str(stable),
            }]})
            request.chmod(0o600)
            first = self.run_inventory(self.require_script(), request, receipt)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(
                json.loads(receipt.read_text())["capabilities"][0]["version"],
                "9.8.7",
            )

            stable.unlink()
            old.unlink()
            stable.symlink_to(new)

            gate = self.load_module(RUNNER_GATE)
            self.assertEqual(gate.verify_codex_pin(receipt), new.resolve())
            refreshed = json.loads(receipt.read_text())
            self.assertEqual(refreshed["capabilities"][0]["version"], "9.8.8")
            self.assertEqual(refreshed["capabilities"][0]["sha256"], self.sha256(new))
            self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)

    def test_stale_codex_pin_does_not_refresh_from_insecure_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            executable = root / "codex"
            executable.write_text(
                "#!/bin/sh\nprintf 'codex-cli 9.8.7\\n'\n", encoding="utf-8"
            )
            executable.chmod(0o755)
            request = root / "codex-request.json"
            receipt = root / "codex-capability.json"
            self.write_json(request, {"capabilities": [{
                "name": "codex-cli",
                "kind": "codex_cli",
                "path": str(executable),
            }]})
            request.chmod(0o600)
            first = self.run_inventory(self.require_script(), request, receipt)
            self.assertEqual(first.returncode, 0, first.stderr)
            original = receipt.read_bytes()
            executable.unlink()
            request.chmod(0o644)

            gate = self.load_module(RUNNER_GATE)
            with self.assertRaises(gate.PinError):
                gate.verify_codex_pin(receipt)
            self.assertEqual(receipt.read_bytes(), original)

    def test_codex_pin_does_not_refresh_an_in_place_binary_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            executable = root / "codex"
            executable.write_text(
                "#!/bin/sh\nprintf 'codex-cli 9.8.7\\n'\n", encoding="utf-8"
            )
            executable.chmod(0o755)
            request = root / "codex-request.json"
            receipt = root / "codex-capability.json"
            self.write_json(request, {"capabilities": [{
                "name": "codex-cli",
                "kind": "codex_cli",
                "path": str(executable),
            }]})
            request.chmod(0o600)
            first = self.run_inventory(self.require_script(), request, receipt)
            self.assertEqual(first.returncode, 0, first.stderr)
            original = receipt.read_bytes()
            executable.write_text(
                "#!/bin/sh\nprintf 'codex-cli 9.8.8\\n'\n", encoding="utf-8"
            )
            executable.chmod(0o755)

            gate = self.load_module(RUNNER_GATE)
            with self.assertRaises(gate.PinError):
                gate.verify_codex_pin(receipt)
            self.assertEqual(receipt.read_bytes(), original)

    def test_stale_codex_pin_does_not_refresh_a_changed_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            old = root / "codex-old"
            new = root / "codex-new"
            old.write_text("#!/bin/sh\nprintf 'codex-cli 9.8.7\\n'\n", encoding="utf-8")
            new.write_text("#!/bin/sh\nprintf 'codex-cli 9.8.8\\n'\n", encoding="utf-8")
            old.chmod(0o755)
            new.chmod(0o755)
            request = root / "codex-request.json"
            receipt = root / "codex-capability.json"
            self.write_json(request, {"capabilities": [{
                "name": "codex-cli", "kind": "codex_cli", "path": str(old),
            }]})
            request.chmod(0o600)
            first = self.run_inventory(self.require_script(), request, receipt)
            self.assertEqual(first.returncode, 0, first.stderr)
            original = receipt.read_bytes()
            old.unlink()
            self.write_json(request, {"capabilities": [{
                "name": "codex-cli", "kind": "codex_cli", "path": str(new),
            }]})
            request.chmod(0o600)

            gate = self.load_module(RUNNER_GATE)
            with self.assertRaises(gate.PinError):
                gate.verify_codex_pin(receipt)
            self.assertEqual(receipt.read_bytes(), original)

    def test_runner_environment_is_allowlisted_and_uses_isolated_home(self) -> None:
        gate = self.load_module(RUNNER_GATE)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            owner_home = root / "owner"
            executable = root / "release" / "codex"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"codex")
            source = {
                "HOME": str(owner_home),
                "PATH": "/untrusted/bin:/usr/bin",
                "LIFE_MANAGER_STATE_HOME": str(root / "state"),
                "AGENT_RUNNER_CONFIG": str(root / "runner.json"),
                "AFFILIATE_CODEX_CAPABILITY_RECEIPT": str(root / "pin.json"),
                "ANICCA_BUDGET_SCOPE_ID": "affiliate-campaign",
                "ANICCA_PASS_TOKEN_BUDGET": "49152",
                "DATABASE_URL": "AUTHORITY_SECRET_SENTINEL",
                "AWS_SECRET_ACCESS_KEY": "AUTHORITY_SECRET_SENTINEL",
                "OPENAI_API_KEY": "AUTHORITY_SECRET_SENTINEL",
                "BROWSER_CDP_URL": "http://127.0.0.1:9324",
            }

            child = gate.allowlisted_environment(source, executable)

            self.assertEqual(child["HOME"], str(owner_home.resolve()))
            self.assertNotIn("CODEX_HOME", child)
            self.assertNotIn("AFFILIATE_CODEX_AUTH_FILE", child)
            self.assertEqual(child["ANICCA_BUDGET_SCOPE_ID"], "affiliate-campaign")
            self.assertEqual(child["PATH"], f"{executable.parent}:/usr/bin:/bin:/usr/sbin:/sbin")
            self.assertEqual(
                child["AGENT_RUNNER_CONFIG"],
                str(REPO_ROOT / "runtime" / "agent-runner" / "config.json"),
            )
            for forbidden in (
                "DATABASE_URL", "AWS_SECRET_ACCESS_KEY", "OPENAI_API_KEY", "BROWSER_CDP_URL"
            ):
                self.assertNotIn(forbidden, child)
            self.assertNotIn("AUTHORITY_SECRET_SENTINEL", json.dumps(child, sort_keys=True))

    def test_runner_evidence_requires_private_atomic_seal(self) -> None:
        gate = self.load_module(RUNNER_GATE)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "evidence"
            evidence.mkdir(mode=0o755)
            (evidence / "summary.json").write_text(
                '{"status":"success","attempt_count":1}\n', encoding="utf-8"
            )
            (evidence / "attempts.jsonl").write_text('{"attempt":1}\n', encoding="utf-8")
            (evidence / "attempt-01.stdout.log").write_text("raw\n", encoding="utf-8")
            for path in evidence.iterdir():
                path.chmod(0o644)

            seal_path = gate.seal_evidence(evidence, 0)
            seal = json.loads(seal_path.read_text(encoding="utf-8"))
            self.assertEqual(seal["status"], "SEALED")
            self.assertEqual(seal["runner_exit_code"], 0)
            self.assertEqual(evidence.stat().st_mode & 0o777, 0o700)
            self.assertTrue(all(path.stat().st_mode & 0o777 == 0o600 for path in evidence.iterdir()))
            self.assertEqual(gate.verify_evidence_seal(evidence), seal)
            (evidence / "summary.json").write_text('{"status":"tampered"}\n', encoding="utf-8")
            with self.assertRaises(gate.EvidenceError):
                gate.verify_evidence_seal(evidence)

            incomplete = root / "incomplete"
            incomplete.mkdir()
            (incomplete / "attempts.jsonl").write_text('{"attempt":1}\n{"broken"', encoding="utf-8")
            with self.assertRaises(gate.EvidenceError):
                gate.seal_evidence(incomplete, 1)
            self.assertFalse((incomplete / "evidence-seal.json").exists())

    def test_rejects_missing_duplicate_and_secret_inputs_without_receipt(self) -> None:
        script = self.require_script()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "tool"
            executable.write_bytes(b"tool\n")
            executable.chmod(0o755)
            base: Dict[str, Any] = {
                "name": "tool",
                "kind": "executable",
                "path": str(executable),
            }
            bad_app = root / "External.app"
            bad_binary = root / "outside" / "External"
            bad_binary.parent.mkdir()
            bad_binary.write_bytes(b"outside\n")
            bad_binary.chmod(0o755)
            (bad_app / "Contents").mkdir(parents=True)
            (bad_app / "Contents" / "Info.plist").write_bytes(
                plistlib.dumps({"CFBundleVersion": "1.0"})
            )
            (bad_app / "Contents" / "MacOS").symlink_to(
                bad_binary.parent, target_is_directory=True
            )
            secret_app = root / "Version.app"
            secret_binary = secret_app / "Contents" / "MacOS" / "Version"
            secret_binary.parent.mkdir(parents=True)
            secret_binary.write_bytes(b"version\n")
            secret_binary.chmod(0o755)
            (secret_app / "Contents" / "Info.plist").write_bytes(
                plistlib.dumps({"CFBundleVersion": "sk_live_123456789"})
            )
            cases = {
                "generic_executable": {"capabilities": [dict(base)]},
                "missing": {
                    "capabilities": [dict(base, path=str(root / "missing"))]
                },
                "duplicate": {"capabilities": [dict(base), dict(base)]},
                "secret": {
                    "capabilities": [dict(base, token="AUTHORITY_SECRET_SENTINEL")]
                },
                "unknown_entry": {
                    "capabilities": [dict(base, unexpected="reject-me")]
                },
                "unknown_top_level": {
                    "capabilities": [dict(base)],
                    "extra": "reject-me",
                },
                "empty": {"capabilities": []},
                "fake_version": {
                    "capabilities": [dict(base, version="9.9.9")]
                },
                "external_macos": {
                    "capabilities": [{
                        "name": "external-app",
                        "kind": "macos_app",
                        "path": str(bad_app),
                        "executable": "External",
                    }]
                },
                "secret_version": {
                    "capabilities": [{
                        "name": "version-app",
                        "kind": "macos_app",
                        "path": str(secret_app),
                        "executable": "Version",
                    }]
                },
            }
            for name, request_value in cases.items():
                with self.subTest(case=name):
                    request = root / (name + "-request.json")
                    receipt = root / (name + "-receipt.json")
                    self.write_json(request, request_value)
                    result = self.run_inventory(script, request, receipt)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(receipt.exists())
                    self.assertNotIn("AUTHORITY_SECRET_SENTINEL", result.stdout)
                    self.assertNotIn("AUTHORITY_SECRET_SENTINEL", result.stderr)

            module = self.load_module(script)

            def valid_app(name: str) -> tuple[Path, Path, Path]:
                app = root / (name + ".app")
                binary = app / "Contents" / "MacOS" / name
                binary.parent.mkdir(parents=True)
                binary.write_bytes(b"valid app\n")
                binary.chmod(0o755)
                info = app / "Contents" / "Info.plist"
                info.write_bytes(plistlib.dumps({"CFBundleVersion": "1.0"}))
                return app, app / "Contents" / "MacOS", info

            swap_app, swap_macos, _ = valid_app("Swap")
            swap_outside = root / "swap-outside"
            swap_outside.mkdir()
            (swap_outside / "Swap").write_bytes(b"outside\n")
            (swap_outside / "Swap").chmod(0o755)
            original_bundle_version = module.bundle_version

            def swap_macos_after_validation(info_fd: int) -> tuple[str, Any]:
                swap_macos.rename(root / "Swap-MacOS")
                swap_macos.symlink_to(swap_outside, target_is_directory=True)
                return original_bundle_version(info_fd)

            with mock.patch.object(
                module, "bundle_version", side_effect=swap_macos_after_validation
            ):
                with self.assertRaises(module.InventoryError):
                    module.inspect({
                        "name": "swap-app",
                        "kind": "macos_app",
                        "path": str(swap_app),
                        "executable": "Swap",
                    })

            info_app, _, info_path = valid_app("InfoSwap")

            def swap_info_after_validation(info_fd: int) -> tuple[str, Any]:
                info_path.rename(root / "InfoSwap-original.plist")
                info_path.write_bytes(
                    plistlib.dumps({"CFBundleShortVersionString": "secret-version"})
                )
                return original_bundle_version(info_fd)

            with mock.patch.object(module, "bundle_version", side_effect=swap_info_after_validation):
                with self.assertRaises(module.InventoryError):
                    module.inspect({
                        "name": "info-swap-app",
                        "kind": "macos_app",
                        "path": str(info_app),
                        "executable": "InfoSwap",
                    })

    def test_stat_mutation_during_hash_fails_closed(self) -> None:
        script = self.require_script()
        module = self.load_module(script)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "Mutable.app"
            target = app / "Contents" / "MacOS" / "Mutable"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"stable content\n")
            target.chmod(0o755)
            (app / "Contents" / "Info.plist").write_bytes(
                plistlib.dumps({"CFBundleVersion": "1.0"})
            )
            original_stream = module.stream_sha256

            def mutate_then_hash(fd: int) -> str:
                target.chmod(0o700)
                return original_stream(fd)

            with mock.patch.object(module, "stream_sha256", side_effect=mutate_then_hash):
                with self.assertRaises(module.InventoryError):
                    module.inspect({
                        "name": "mutable-app",
                        "kind": "macos_app",
                        "path": str(app),
                        "executable": "Mutable",
                    })


if __name__ == "__main__":
    unittest.main()
