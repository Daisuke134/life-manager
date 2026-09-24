import json
import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.loop.lm_loop_apply import build_apply_plan, install_one


SHA = "a" * 40


class RecoveryCanaryRollbackTest(unittest.TestCase):
    def test_real_installer_restores_connector_snapshot_without_touching_sibling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bin").mkdir()
            for name in ("lm-loop-run", "connector-canary", "sibling-canary"):
                executable = root / "bin" / name
                executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                executable.chmod(0o755)
            (root / "RELEASE.json").write_text(
                json.dumps({"sha": SHA}), encoding="utf-8",
            )
            for dependency in ("playwright-core", "jsqr"):
                package = root / "apps/life-manager/node_modules" / dependency / "package.json"
                package.parent.mkdir(parents=True)
                package.write_text("{}\n", encoding="utf-8")

            def row(label, entrypoint, state_name):
                state = f"~/.local/state/life-manager/recovery-canary/{state_name}"
                return {
                    "label": label,
                    "domain": "system",
                    "entrypoint": entrypoint,
                    "cadence": {"start_interval_seconds": 300},
                    "effect_class": "none",
                    "state_root": state,
                    "log_root": f"{state}/logs",
                    "cleanup": {"max_runs": 10, "max_age_days": 7},
                    "provider_route": "deterministic",
                }

            target_id = "life-manager-connector-native"
            sibling_id = "affiliate-composition"
            registry = {
                "schema_version": 2,
                "loops": {
                    target_id: row(
                        "ai.anicca.life-manager-connector-native",
                        "bin/connector-canary", "connector",
                    ),
                    sibling_id: row(
                        "ai.anicca.affiliate-composition",
                        "bin/sibling-canary", "sibling",
                    ),
                },
            }
            (root / "config").mkdir()
            (root / "config/loop-registry.json").write_text(
                json.dumps(registry), encoding="utf-8",
            )
            plan = {item["loop_id"]: item for item in build_apply_plan(registry, root, SHA)}

            agents = root / "agents"
            agents.mkdir()
            target = agents / "ai.anicca.life-manager-connector-native.plist"
            sibling = agents / "ai.anicca.affiliate-composition.plist"
            old_target_args = ["/test-owned/old/lm-loop-run", target_id, "/test-owned/old"]
            old_target = plistlib.dumps({
                "Label": registry["loops"][target_id]["label"],
                "ProgramArguments": old_target_args,
            })
            old_sibling = plistlib.dumps({
                "Label": registry["loops"][sibling_id]["label"],
                "ProgramArguments": [
                    "/test-owned/sibling/lm-loop-run", sibling_id, "/test-owned/sibling",
                ],
            })
            target.write_bytes(old_target)
            sibling.write_bytes(old_sibling)

            def launchctl(args):
                if args[0] == "print":
                    loaded = old_target_args if target.read_bytes() == old_target else ["/wrong/canary"]
                    return 0, "arguments = {\n" + "\n".join(loaded) + "\n}\n"
                return 0, ""

            with patch("runtime.loop.lm_loop_apply._ensure_runtime_roots"), \
                    self.assertRaisesRegex(RuntimeError, "restored previous job"):
                install_one(plan[target_id], target, launchctl,
                            attempts=1, sleeper=lambda _seconds: None)

            self.assertEqual(target.read_bytes(), old_target)
            self.assertEqual(sibling.read_bytes(), old_sibling)


if __name__ == "__main__":
    unittest.main()
