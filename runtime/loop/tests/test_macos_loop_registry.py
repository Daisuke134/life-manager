import json
import copy
import os
import re
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from runtime.loop.macos_loop_registry import (
    CONTROL_PLANE_SAFETY_LOOPS,
    loop_json_schema,
    render_job_models,
    render_loop_json_schema,
    validate_registry,
)
from runtime.loop.lm_loop import doctor_report, status_rows


ROOT = Path(__file__).resolve().parents[3]


def entry(label="ai.anicca.example"):
    return {
        "label": label,
        "domain": "system",
        "entrypoint": "bin/example.sh",
        "cadence": {"run_at_load": True},
        "effect_class": "none",
        "state_root": "~/.local/state/life-manager/example",
        "log_root": "~/.local/state/life-manager/example/logs",
        "cleanup": {"max_runs": 10, "max_age_days": 7},
        "provider_route": "deterministic",
    }


def browser_entry(label: str, profile: str, port: int):
    value = entry(label)
    value["browser_owner"] = {"profile": profile, "cdp_port": port}
    return value


class MacosLoopRegistryTest(unittest.TestCase):
    def test_queued_release_reconcile_is_an_explicit_boolean(self):
        row = entry()
        row.update({
            "resource_class": "deterministic",
            "admission_class": "revenue",
            "priority": "revenue",
            "reconcile_queued_release": True,
        })
        self.assertTrue(validate_registry({
            "schema_version": 2, "loops": {"example": row},
        })["loops"]["example"]["reconcile_queued_release"])

        for invalid_value in (None, 1, "true"):
            invalid = dict(row)
            invalid["reconcile_queued_release"] = invalid_value
            with self.subTest(value=invalid_value), self.assertRaisesRegex(
                ValueError, "invalid reconcile_queued_release",
            ):
                validate_registry({"schema_version": 2, "loops": {"example": invalid}})

        missing_contract = entry()
        missing_contract["reconcile_queued_release"] = True
        with self.assertRaisesRegex(ValueError, "requires admission contract"):
            validate_registry({
                "schema_version": 2, "loops": {"example": missing_contract},
            })

    def test_x_repost_opts_into_queued_release_reconcile(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["x-repost"]
        self.assertEqual(row.get("resource_class"), "agent")
        self.assertEqual(row.get("admission_class"), "borrow")
        self.assertEqual(row.get("priority"), "revenue")
        self.assertIs(row.get("reconcile_queued_release"), True)

    def test_queued_wake_coalescing_requires_reserved_wake_coalescing(self):
        row = entry()
        row["coalesce_queued_wakes"] = True
        with self.assertRaises(ValueError):
            validate_registry({"schema_version": 2, "loops": {"example": row}})
        row["coalesce_reserved_wakes"] = True
        self.assertEqual(validate_registry({
            "schema_version": 2, "loops": {"example": row},
        })["loops"]["example"]["coalesce_queued_wakes"], True)

    def test_paper_and_shadow_are_retired_after_recurring_live_cutover(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        self.assertNotIn("alpaca-investment", registry["loops"])
        self.assertNotIn("alpaca-investment-shadow", registry["loops"])
        self.assertIn("alpaca-investment-paper", registry["loops"])
        self.assertIn("alpaca-investment-live", registry["loops"])
        self.assertIn("ai.anicca.alpaca-investment", registry["retired_labels"])
        self.assertIn("ai.anicca.alpaca-investment-shadow", registry["retired_labels"])

    def test_investment_live_declares_existing_admission_and_coalescing_contract(self):
        row = json.loads((ROOT / "config/loop-registry.json").read_text())["loops"][
            "alpaca-investment-live"
        ]
        self.assertEqual(row["resource_class"], "agent")
        self.assertEqual(row["admission_class"], "revenue")
        self.assertEqual(row["priority"], "revenue")
        self.assertTrue(row["coalesce_reserved_wakes"])
        self.assertTrue(row["coalesce_queued_wakes"])
        self.assertTrue(row["reconcile_queued_release"])

    def test_fundraiser_declares_existing_admission_and_coalescing_contract(self):
        row = json.loads((ROOT / "config/loop-registry.json").read_text())["loops"][
            "fundraiser"
        ]
        self.assertEqual(row["cadence"], {"start_interval_seconds": 3600})
        self.assertEqual(row["resource_class"], "agent")
        self.assertEqual(row["admission_class"], "revenue")
        self.assertEqual(row["priority"], "revenue")
        self.assertEqual(row["admission_effect_scope"], "occurrence")
        self.assertTrue(row["coalesce_reserved_wakes"])
        self.assertTrue(row["coalesce_queued_wakes"])

    def test_ebook_postiz_reconcilers_use_owner_identity_dir(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        identity_dir = "~/.local/state/life-manager/ebook/effect-identities"
        for loop_id in (
            "ebook-en-tiktok-daily",
            "ebook-ja-instagram-daily",
            "ebook-ja-tiktok-daily",
        ):
            with self.subTest(loop_id=loop_id):
                argv = registry["loops"][loop_id]["effect_reconcile"]["argv"]
                self.assertIn("--identity-dir", argv)
                index = argv.index("--identity-dir")
                self.assertEqual(argv[index + 1], identity_dir)

    def test_writer_jobs_declare_existing_admission_and_coalescing_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        for loop_id in (
            "writer-claim-loop",
            "writer-craft-train",
            "writer-money-sync",
            "writer-opportunity-discovery",
            "writer-opportunity-response",
            "writer-report",
            "writer-sales-measure",
        ):
            with self.subTest(loop_id=loop_id):
                row = registry["loops"][loop_id]
                self.assertEqual(row.get("resource_class"), "agent")
                self.assertEqual(row.get("admission_class"), "borrow")
                self.assertEqual(row.get("priority"), "support")
                self.assertTrue(row.get("coalesce_reserved_wakes"))
                self.assertTrue(row.get("coalesce_queued_wakes"))

    def test_job_search_daily_and_inbox_declare_admission_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        for loop_id in ("job-search-daily", "job-search-inbox"):
            with self.subTest(loop_id=loop_id):
                row = registry["loops"][loop_id]
                self.assertEqual(row.get("provider_route"), "shared-agent-runner")
                if loop_id == "job-search-daily":
                    self.assertEqual(row.get("resource_class"), "agent")
                    self.assertEqual(row.get("admission_class"), "revenue")
                    self.assertEqual(row.get("priority"), "revenue")
                    self.assertTrue(row.get("reconcile_queued_release"))
                else:
                    self.assertEqual(row.get("resource_class"), "agent")
                    self.assertEqual(row.get("admission_class"), "borrow")
                    self.assertEqual(row.get("priority"), "support")
                self.assertTrue(row.get("coalesce_reserved_wakes"))
                self.assertTrue(row.get("coalesce_queued_wakes"))

    def test_x402_acquisition_controller_declares_effect_free_rebind_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["x402-acquisition-controller"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("admission_class"), "borrow")
        self.assertEqual(row.get("priority"), "support")
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))

    def test_x402_experiment_franklin1_declares_effect_free_rebind_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["x402-experiment-franklin1"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("admission_class"), "borrow")
        self.assertEqual(row.get("priority"), "support")
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))

    def test_x402_inflow_watch_declares_effect_free_rebind_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["x402-inflow-watch"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("admission_class"), "borrow")
        self.assertEqual(row.get("priority"), "support")
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))

    def test_x402_inflow_watch_claude_p_declares_agent_rebind_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["x402-inflow-watch-claude-p"]
        self.assertEqual(row.get("resource_class"), "agent")
        self.assertEqual(row.get("admission_class"), "borrow")
        self.assertEqual(row.get("priority"), "support")
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))

    def test_x402_inflow_watch_franklin1_declares_effect_free_rebind_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["x402-inflow-watch-franklin1"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("admission_class"), "borrow")
        self.assertEqual(row.get("priority"), "support")
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))

    def test_x402_inflow_watch_franklin2_declares_effect_free_rebind_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["x402-inflow-watch-franklin2"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("admission_class"), "borrow")
        self.assertEqual(row.get("priority"), "support")
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))

    def test_x402_sale_observer_declares_effect_free_rebind_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["x402-sale-observer"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("admission_class"), "borrow")
        self.assertEqual(row.get("priority"), "support")
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))

    def test_citizen_refill_declares_effect_free_rebind_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["citizen-refill"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("admission_class"), "borrow")
        self.assertEqual(row.get("priority"), "support")
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))

    def test_life_manager_x402_ledger_declares_effect_free_rebind_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["life-manager-x402-ledger"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("admission_class"), "borrow")
        self.assertEqual(row.get("priority"), "support")
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))

    def test_life_manager_taskmarket_ledger_declares_effect_free_rebind_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["life-manager-taskmarket-ledger"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("admission_class"), "borrow")
        self.assertEqual(row.get("priority"), "support")
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))

    def test_life_manager_ugig_invoice_observer_declares_effect_free_rebind_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["life-manager-ugig-invoice-observer"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("admission_class"), "borrow")
        self.assertEqual(row.get("priority"), "support")
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))

    def test_life_manager_cfo_hourly_declares_effect_rebind_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["life-manager-cfo-hourly"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("admission_class"), "revenue")
        self.assertEqual(row.get("priority"), "revenue")
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))
        self.assertEqual(
            row["effect_reconcile"]["argv"][0],
            "skills/cfo/effect_reconcile.py",
        )
        self.assertEqual(row["effect_reconcile"]["occurrence_flag"], "--occurrence-id")
        self.assertEqual(row["effect_reconcile"]["resolve_flag"], "--resolve")

    def test_life_manager_financial_report_declares_effect_rebind_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["life-manager-financial-report"]
        self.assertEqual(row.get("effect_class"), "none")
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("admission_class"), "borrow")
        self.assertEqual(row.get("priority"), "support")
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))

    def test_life_manager_payout_declares_effect_rebind_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["life-manager-payout"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("admission_class"), "borrow")
        self.assertEqual(row.get("priority"), "support")
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))

    def test_job_search_health_declares_effect_rebind_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["job-search-health"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("admission_class"), "borrow")
        self.assertEqual(row.get("priority"), "support")
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))

    def test_job_search_learning_declares_effect_rebind_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["job-search-learning"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("admission_class"), "borrow")
        self.assertEqual(row.get("priority"), "support")
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))

    def test_citizen_refill_launchd_uses_managed_runtime_node_without_path(self):
        launcher = ROOT / "bin/citizen-refill-launchd"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            empty_bin = root / "empty-bin"
            empty_bin.mkdir()
            (empty_bin / "dirname").symlink_to("/usr/bin/dirname")
            fake_node = root / "managed-node"
            fake_node.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$@\" > \"$FAKE_NODE_ARGS\"\n"
                "exit 0\n"
            )
            fake_node.chmod(0o700)
            args_path = root / "node-args"
            env = os.environ.copy()
            env.update({
                "PATH": str(empty_bin),
                "LIFE_MANAGER_NODE": "",
                "LIFE_MANAGER_RUNTIME_NODE": str(fake_node),
                "LIFE_MANAGER_STATE_HOME": str(root / "state"),
                "LIFE_MANAGER_ENV_FILE": str(root / "missing-env"),
                "FAKE_NODE_ARGS": str(args_path),
            })
            result = subprocess.run(
                [str(launcher)],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                args_path.read_text().splitlines(),
                [str(ROOT / "bin/citizen-refill"), "--live"],
            )

    def test_recovery_supervisor_uses_managed_runtime_node_without_path(self):
        launcher = ROOT / "bin/lm-recovery-supervise"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            empty_bin = root / "empty-bin"
            empty_bin.mkdir()
            (empty_bin / "bash").symlink_to("/bin/bash")
            (empty_bin / "dirname").symlink_to("/usr/bin/dirname")
            fake_node = root / "managed-node"
            fake_node.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$@\" > \"$FAKE_NODE_ARGS\"\n"
                "exit 0\n"
            )
            fake_node.chmod(0o700)
            args_path = root / "node-args"
            queue_path = root / "recovery-intents.jsonl"
            env = os.environ.copy()
            env.update({
                "PATH": str(empty_bin),
                "LIFE_MANAGER_RUNTIME_NODE": str(fake_node),
                "FAKE_NODE_ARGS": str(args_path),
            })
            result = subprocess.run(
                [str(launcher), "--queue", str(queue_path)],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            node_args = args_path.read_text().splitlines()
            node_args[0] = str(Path(node_args[0]).resolve())
            self.assertEqual(
                node_args,
                [str((ROOT / "runtime/loop/recovery-supervisor-cli.mjs").resolve()),
                 "--queue", str(queue_path)],
            )

    def test_migrated_system_loops_keep_runtime_metadata_out_of_openclaw(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        for loop_id in {
            "browser-state-backup",
            "cadence-deadline-check",
            "claude-projects-backup",
            "earning-health-allslots",
            "session-vault",
            "verify-loops-audit",
        }:
            with self.subTest(loop_id=loop_id):
                row = registry["loops"][loop_id]
                root = f"~/.local/state/life-manager/{loop_id}"
                self.assertEqual(row["state_root"], root)
                self.assertEqual(row["log_root"], f"{root}/logs")

    def test_citizens_diff_monitor_is_retired_after_lifecycle_receipt_cutover(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        self.assertNotIn("citizens-diff-monitor", registry["loops"])
        self.assertIn("ai.anicca.citizens-diff-monitor", registry["retired_labels"])

    def test_unused_peer_api_and_legacy_watchdog_are_retired(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        self.assertNotIn("watchdog", registry["loops"])
        self.assertIn("ai.anicca.watchdog", registry["retired_labels"])
        self.assertIn("com.anicca.peer-api", registry["retired_labels"])

    def test_obsolete_phone_and_bridge_runtimes_are_retired(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        for loop_id, label in (
            ("pipecat-phone", "ai.anicca.pipecat-phone"),
            ("phone-conversation", "ai.anicca.phone-conversation"),
            ("phone-tunnel", "ai.anicca.phone-tunnel"),
            ("phone-tunnel-watcher", "ai.anicca.phone-tunnel-watcher"),
            ("slack-bridge", "ai.anicca.slack-bridge"),
        ):
            with self.subTest(loop_id=loop_id):
                self.assertNotIn(loop_id, registry["loops"])
                self.assertIn(label, registry["retired_labels"])

    def test_unloaded_stale_external_artifacts_are_retired(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        for label in (
            "ai.anicca.clawrouter",
            "ai.anicca.fleet-daily",
            "ai.anicca.freelancer-bid-watch",
            "ai.anicca.freelancer-revenue-application",
            "ai.anicca.freelancer-revenue-work-sync",
            "ai.anicca.x402-monitor",
            "ai.anicca.x402-tunnel",
            "ai.anicca.job-search-observability",
            "ai.anicca.job-search-camofox",
            "ai.anicca.probe-rollback-1782857566-85245-proactive",
            "ai.anicca.provision-browser.tiktok.anicca",
        ):
            with self.subTest(label=label):
                self.assertNotIn(label, registry["external_labels"])
                self.assertIn(label, registry["retired_labels"])

    def test_life_manager_owned_loops_do_not_write_runtime_metadata_to_openclaw(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        loop_ids = {
            "life-manager-daily",
            "life-manager-dev",
            "life-manager-selfbuild",
            "life-manager-taskmarket-ledger",
            "life-manager-ugig-invoice-observer",
            "lm-recording-store",
        }
        for loop_id in loop_ids:
            with self.subTest(loop_id=loop_id):
                row = registry["loops"][loop_id]
                self.assertTrue(row["state_root"].startswith("~/.local/state/life-manager/"))
                self.assertTrue(row["log_root"].startswith("~/.local/state/life-manager/"))
                self.assertNotIn("openclaw", row["state_root"] + row["log_root"])

    def test_all_x402_skill_jobs_share_the_canonical_runtime_state(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        state_root = "~/.local/state/life-manager/x402-sell"
        matched = 0
        for loop_id, row in registry["loops"].items():
            if not row["entrypoint"].startswith("skills/earn/x402-sell/"):
                continue
            matched += 1
            with self.subTest(loop_id=loop_id):
                self.assertEqual(row["state_root"], state_root)
                self.assertEqual(row["log_root"], f"{state_root}/logs")
        self.assertGreater(matched, 10)

    def test_life_manager_video_and_dev_jobs_share_the_receipt_backed_exec_adapter(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        for loop_id in {
            "life-manager-dev",
            "life-manager-selfbuild",
            "life-manager-taskmarket-ledger",
            "life-manager-ugig-invoice-observer",
            "lm-recording-store",
        }:
            with self.subTest(loop_id=loop_id):
                row = registry["loops"][loop_id]
                self.assertEqual(row["adapter"], "exec")
                self.assertEqual(row["command"], [])

    def test_boot_panic_evidence_runs_once_when_the_aqua_session_loads(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        self.assertEqual(registry["loops"]["boot-panic-evidence"], {
            "cadence": {"run_at_load": True},
            "cleanup": {"max_age_days": 30, "max_runs": 20},
            "domain": "system",
            "effect_class": "none",
            "entrypoint": "runtime/host/boot_panic_collector.py",
            "label": "ai.anicca.boot-panic-evidence",
            "log_root": "~/.local/state/life-manager/boot-panic-evidence/logs",
            "provider_route": "deterministic",
            "state_root": "~/.local/state/life-manager/boot-panic-evidence",
            "system_role": "control",
        })

    def test_money_printer_symphony_is_retired_after_cloud_cutover(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        self.assertNotIn("money-printer-symphony", registry["loops"])
        self.assertIn("ai.anicca.life-manager-money-printer-symphony", registry["retired_labels"])

    def test_money_printer_symphony_bridge_is_retired_after_cloud_cutover(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        self.assertNotIn("money-printer-symphony-bridge", registry["loops"])
        self.assertIn("ai.anicca.life-manager-money-printer-symphony-bridge", registry["retired_labels"])

    def test_legacy_telegram_bot_is_retired_after_gateway_cutover(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        self.assertNotIn("telegram-bot", registry["loops"])
        self.assertIn("ai.anicca.telegram-bot", registry["retired_labels"])

    def test_unused_job_search_browser_is_retired_after_shared_owner_readback(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        self.assertNotIn("job-search-browser", registry["loops"])
        self.assertIn("ai.anicca.job-search-browser", registry["retired_labels"])

    def test_release_reconciler_is_an_independent_system_owner(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["life-manager-release-reconciler"]
        self.assertEqual(row, {
            "cadence": {"start_interval_seconds": 60},
            "cleanup": {"max_age_days": 14, "max_runs": 100},
            "domain": "system",
            "effect_class": "none",
            "entrypoint": "bin/reconcile-agent-runner-release.sh",
            "label": "ai.anicca.life-manager-release-reconciler",
            "log_root": "~/.local/state/life-manager/release-reconciler/logs",
            "provider_route": "deterministic",
            "state_root": "~/.local/state/life-manager/release-reconciler",
            "system_role": "control",
        })
        self.assertEqual(validate_registry(registry), registry)

    def test_release_reconciler_updates_only_loaded_idle_fleet_owners(self):
        script = (ROOT / "bin/reconcile-agent-runner-release.sh").read_text()
        self.assertIn("':(exclude)docs/**'", script)
        self.assertIn("':(exclude)skills/earn/gig/TODO.md'", script)
        self.assertIn(
            "reconcile shared-agent-runner --loaded-idle-only",
            script,
        )
        self.assertIn(
            "reconcile shared-agent-runner --loaded-idle-only --max-owners 4",
            script,
        )
        self.assertIn(
            "reconcile deterministic --loaded-idle-only",
            script,
        )
        self.assertIn(
            "reconcile deterministic --loaded-idle-only --max-owners 4",
            script,
        )
        self.assertIn("admission-v2-enable", script)
        self.assertIn("lm-recovery-supervise", script)
        self.assertIn("LIFE_MANAGER_RECOVERY_INTENTS_PATH", script)
        self.assertIn("LIFE_MANAGER_RECONCILE_TIMEOUT_SECONDS", script)
        self.assertIn("timeout_runner", script)
        self.assertNotIn("--include-running", script)
        self.assertNotIn("--loop-id", script)

    def test_registry_rejects_missing_and_secret_fields(self):
        missing = {"schema_version": 2, "loops": {"example": entry()}}
        del missing["loops"]["example"]["cleanup"]
        with self.assertRaisesRegex(ValueError, "cleanup"):
            validate_registry(missing)

        secret = {"schema_version": 2, "loops": {"example": entry()}}
        secret["loops"]["example"]["auth_token"] = "not-a-real-secret"
        with self.assertRaisesRegex(ValueError, "secret-like"):
            validate_registry(secret)

    def test_registry_accepts_only_the_explicit_queue_priorities(self):
        value = entry()
        value["priority"] = "revenue"
        self.assertEqual(
            validate_registry({"schema_version": 2, "loops": {"example": value}})["loops"]["example"]["priority"],
            "revenue",
        )
        invalid = entry()
        invalid["priority"] = "urgent"
        with self.assertRaisesRegex(ValueError, "invalid priority"):
            validate_registry({"schema_version": 2, "loops": {"example": invalid}})

    def test_registry_accepts_only_typed_system_roles(self):
        for role in ("platform", "control", "shared"):
            value = entry()
            value["system_role"] = role
            with self.subTest(role=role):
                self.assertEqual(
                    validate_registry({"schema_version": 2, "loops": {"example": value}})
                    ["loops"]["example"]["system_role"],
                    role,
                )
        invalid = entry()
        invalid["system_role"] = "product"
        with self.assertRaisesRegex(ValueError, "invalid system_role"):
            validate_registry({"schema_version": 2, "loops": {"example": invalid}})

    def test_registry_accepts_explicit_admission_effect_scope(self):
        value = entry()
        value["entrypoint"] = "skills/earn/crowdworks/scripts/paid-owner"
        value["admission_effect_scope"] = "occurrence"
        self.assertEqual(
            validate_registry({"schema_version": 2, "loops": {"example": value}})
            ["loops"]["example"]["admission_effect_scope"],
            "occurrence",
        )
        for invalid_value in ("client", 1, True):
            invalid = entry()
            invalid["admission_effect_scope"] = invalid_value
            with self.subTest(value=invalid_value), self.assertRaisesRegex(
                ValueError, "invalid admission_effect_scope",
            ):
                validate_registry({"schema_version": 2, "loops": {"example": invalid}})
        unproven = entry()
        unproven["admission_effect_scope"] = "occurrence"
        with self.assertRaisesRegex(ValueError, "not proven for entrypoint"):
            validate_registry({"schema_version": 2, "loops": {"example": unproven}})

    def test_shared_marketing_and_connector_owners_declare_runtime_class_and_priority(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        mobile_ids = [
            loop_id for loop_id, row in registry["loops"].items()
            if row["entrypoint"] == "apps/life-manager/scripts/mobile-app"
        ]
        assert len(mobile_ids) == 18  # 17 existing mobile owners plus the EN2 TikTok owner
        for loop_id in mobile_ids:
            with self.subTest(loop_id=loop_id):
                row = registry["loops"][loop_id]
                self.assertEqual(row.get("resource_class"), "agent")
                self.assertEqual(row.get("admission_class"), "revenue")
                self.assertEqual(row.get("priority"), "revenue")
        connector = registry["loops"]["life-manager-connector-native"]
        self.assertEqual(connector.get("resource_class"), "browser")
        self.assertEqual(connector.get("admission_class"), "revenue")
        self.assertEqual(connector.get("priority"), "revenue")
        # Revenue readers run on revenue capacity: as borrow owners they never got a
        # slot once revenue owners filled the host (2026-09-27, SSOT P-5).
        for loop_id in ("life-manager-instagram-metrics", "life-manager-tiktok-metrics",
                        "capafy-outcome-monitor", "marketing-metrics", "marketing-owner-events"):
            with self.subTest(loop_id=loop_id):
                row = registry["loops"][loop_id]
                self.assertEqual(row.get("resource_class"), "deterministic")
                self.assertEqual(row.get("admission_class"), "revenue")
                self.assertEqual(row.get("priority"), "revenue")
        daily = registry["loops"]["life-manager-daily"]
        self.assertEqual(daily.get("admission_class"), "revenue")
        self.assertEqual(daily.get("priority"), "revenue")
        capafy_healthcheck = registry["loops"]["capafy-loop-healthcheck"]
        self.assertEqual(capafy_healthcheck.get("resource_class"), "deterministic")
        self.assertEqual(capafy_healthcheck.get("admission_class"), "revenue")
        self.assertEqual(capafy_healthcheck.get("priority"), "revenue")

    def test_marketplace_item_lanes_declare_occurrence_scoped_admission(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        for loop_id in (
            "crowdworks-revenue-application", "crowdworks-revenue-paid",
            "crowdworks-revenue-reply", "lancers-revenue-application",
            "lancers-revenue-negotiate", "lancers-revenue-paid",
        ):
            with self.subTest(loop_id=loop_id):
                self.assertEqual(
                    registry["loops"][loop_id].get("admission_effect_scope"),
                    "occurrence",
                )
        for loop_id in (
            "crowdworks-revenue-report", "lancers-revenue-storefront",
            "lancers-revenue-telegram-report",
        ):
            with self.subTest(loop_id=loop_id):
                self.assertIsNone(registry["loops"][loop_id].get("admission_effect_scope"))

    def test_lancers_report_declares_observed_deterministic_borrow_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["lancers-revenue-telegram-report"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("admission_class"), "borrow")
        self.assertEqual(row.get("priority"), "support")
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))

    def test_crowdworks_report_declares_deterministic_revenue_contract(self):
        # Borrow never ran once revenue owners filled the host (11/11 wakes
        # capacity_busy on 2026-09-26, 46 reports undelivered to the owner).
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["crowdworks-revenue-report"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("admission_class"), "revenue")
        self.assertEqual(row.get("priority"), "revenue")
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))

    def test_affiliate_loop_opts_into_queued_release_reconcile(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        self.assertIs(
            registry["loops"]["affiliate-loop"].get("reconcile_queued_release"),
            True,
        )

    def test_x402_money_observers_declare_existing_admission_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        for loop_id in ("sol-funding", "x402-settlement-recorder"):
            with self.subTest(loop_id=loop_id):
                row = registry["loops"][loop_id]
                self.assertEqual(row.get("resource_class"), "deterministic")
                self.assertEqual(row.get("admission_class"), "borrow")
                self.assertEqual(row.get("priority"), "support")
                self.assertTrue(row.get("coalesce_queued_wakes"))
                self.assertTrue(row.get("coalesce_reserved_wakes"))
                self.assertTrue(row.get("reconcile_queued_release"))

    def test_honne_ja_is_the_only_mobile_queued_release_canary(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        mobile = json.loads(
            (ROOT / "apps/life-manager/config/mobile-app-loops.json").read_text()
        )
        opted_in = {
            loop_id
            for loop_id in mobile["loops"]
            if registry["loops"][loop_id].get("reconcile_queued_release") is True
        }
        self.assertEqual(opted_in, {"life-manager-honne-ja"})

    def test_writer_publication_owners_use_revenue_admission(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        for loop_id in ("article-daily", "article-resume"):
            with self.subTest(loop_id=loop_id):
                row = registry["loops"][loop_id]
                self.assertEqual(row.get("effect_class"), "publish")
                self.assertEqual(row.get("resource_class"), "agent")
                self.assertEqual(row.get("admission_class"), "revenue")
                self.assertEqual(row.get("priority"), "critical_paid")
                self.assertTrue(row.get("coalesce_queued_wakes"))
                self.assertTrue(row.get("coalesce_reserved_wakes"))

    def test_connector_runtime_timeout_bounds_provider_hang_to_one_wake_budget(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        connector = registry["loops"]["life-manager-connector-native"]
        self.assertEqual(connector.get("runtime_timeout_seconds"), 720)
        self.assertGreater(connector["runtime_timeout_seconds"], 600)

    def test_command_and_adapter_are_validated_as_one_contract(self):
        value = entry()
        value.update({"adapter": "python", "command": ["dashboard"]})
        self.assertEqual(
            validate_registry({"schema_version": 2, "loops": {"example": value}})["loops"]["example"],
            value,
        )
        executable = entry()
        executable.update({"adapter": "exec", "command": ["sources", "wake"]})
        self.assertEqual(
            validate_registry({"schema_version": 2, "loops": {"example": executable}})["loops"]["example"],
            executable,
        )
        no_arguments = entry()
        no_arguments.update({"adapter": "python", "command": []})
        self.assertEqual(
            validate_registry({"schema_version": 2, "loops": {"example": no_arguments}})["loops"]["example"],
            no_arguments,
        )
        for adapter, command in ((None, ["dashboard"]), ("python", None),
                                 ("shell", ["dashboard"]),
                                 ("python", [""])):
            invalid = entry()
            if adapter is not None:
                invalid["adapter"] = adapter
            if command is not None:
                invalid["command"] = command
            with self.subTest(adapter=adapter, command=command), self.assertRaises(ValueError):
                validate_registry({"schema_version": 2, "loops": {"example": invalid}})
        explicit_null = entry()
        explicit_null.update({"adapter": None, "command": None})
        with self.assertRaises(ValueError):
            validate_registry({"schema_version": 2, "loops": {"example": explicit_null}})

    def test_runtime_timeout_is_positive_and_scheduled_only(self):
        value = entry()
        value["runtime_timeout_seconds"] = 10800
        self.assertEqual(
            validate_registry({"schema_version": 2, "loops": {"example": value}})["loops"]["example"],
            value,
        )
        for timeout in (None, 0, -1, True, 1.5, "10800"):
            invalid = entry()
            invalid["runtime_timeout_seconds"] = timeout
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                validate_registry({"schema_version": 2, "loops": {"example": invalid}})
        continuous = entry()
        continuous["cadence"] = {"keep_alive": True}
        continuous["runtime_timeout_seconds"] = 10800
        with self.assertRaises(ValueError):
            validate_registry({"schema_version": 2, "loops": {"example": continuous}})

        self.assertEqual(loop_json_schema()["allOf"], [{
            "not": {
                "required": ["runtime_timeout_seconds"],
                "properties": {"cadence": {"required": ["keep_alive"]}},
            },
        }])

    def test_marketing_dashboard_uses_direct_python_adapter(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["marketing-dashboard"]
        self.assertEqual(row["adapter"], "python")
        self.assertEqual(row["command"], ["dashboard"])
        self.assertEqual(
            row["entrypoint"],
            "skills/earn/marketing-engine/report/scheduled_runner.py",
        )

    def test_marketing_mine_daily_uses_direct_python_adapter(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["marketing-mine-daily"]
        self.assertEqual(row["adapter"], "python")
        self.assertEqual(row["command"], ["mine"])
        self.assertEqual(
            row["entrypoint"],
            "skills/earn/marketing-engine/report/scheduled_runner.py",
        )

    def test_affiliate_source_refresh_uses_direct_exec_adapter(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["affiliate-source-refresh"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], ["sources", "wake"])
        self.assertEqual(row["entrypoint"], "skills/affiliate/affiliate")
        self.assertEqual(row["runtime_timeout_seconds"], 10800)
        self.assertEqual(row["resource_class"], "deterministic")
        self.assertEqual(row["admission_class"], "borrow")
        self.assertEqual(row["priority"], "support")

    def test_affiliate_loop_uses_direct_exec_adapter(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["affiliate-loop"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], ["loop", "wake"])
        self.assertEqual(row["entrypoint"], "skills/affiliate/affiliate")
        self.assertEqual(row["resource_class"], "deterministic")
        self.assertEqual(row["admission_class"], "revenue")
        self.assertEqual(row["priority"], "revenue")

    def test_affiliate_browser_uses_repo_managed_runtime_python(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["affiliate-browser"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(row["entrypoint"], "skills/affiliate/scripts/local-browser")

    def test_affiliate_impact_browser_uses_repo_managed_runtime_python(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["affiliate-impact-browser"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(row["entrypoint"], "skills/affiliate/scripts/local-browser")

    def test_affiliate_x_browser_uses_repo_managed_runtime_python(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["affiliate-x-browser"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(row["entrypoint"], "skills/affiliate/scripts/local-browser")

    def test_daily_driver_uses_shared_owned_browser_adapter(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["life-manager-daily-driver"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(row["entrypoint"], "skills/browser/owned-persistent-context")
        self.assertEqual(row["browser_owner"], {
            "cdp_port": 9222,
            "profile": "~/.cloak/profiles/daily-driver",
        })

    def test_affiliate_composition_uses_direct_exec_adapter(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["affiliate-composition"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], ["compose", "wake"])
        self.assertEqual(row["entrypoint"], "skills/affiliate/affiliate")
        self.assertEqual(row["resource_class"], "deterministic")
        self.assertEqual(row["admission_class"], "borrow")
        self.assertEqual(row["priority"], "support")

    def test_crowdworks_application_uses_repo_managed_runtime_python(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["crowdworks-revenue-application"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(
            row["entrypoint"],
            "skills/earn/crowdworks/scripts/application-owner",
        )

    def test_crowdworks_report_uses_repo_managed_runtime_python(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["crowdworks-revenue-report"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(
            row["entrypoint"],
            "skills/earn/crowdworks/scripts/report-owner",
        )

    def test_lancers_application_uses_repo_managed_runtime_python(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["lancers-revenue-application"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(
            row["entrypoint"],
            "skills/earn/lancers/scripts/application-owner",
        )

    def test_lancers_work_sync_uses_repo_managed_runtime_python(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["lancers-revenue-work-sync"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(
            row["entrypoint"],
            "skills/earn/lancers/scripts/work-sync-owner",
        )
        self.assertEqual(row["resource_class"], "deterministic")

    def test_lancers_negotiate_uses_repo_managed_runtime_python(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["lancers-revenue-negotiate"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(
            row["entrypoint"],
            "skills/earn/lancers/scripts/negotiate-owner",
        )

    def test_lancers_paid_uses_repo_managed_runtime_python(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["lancers-revenue-paid"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(
            row["entrypoint"],
            "skills/earn/lancers/scripts/paid-owner",
        )

    def test_lancers_paid_coalesces_queued_and_reserved_wakes(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["lancers-revenue-paid"]
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("coalesce_reserved_wakes"))

    def test_crowdworks_paid_coalesces_queued_and_reserved_wakes(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["crowdworks-revenue-paid"]
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("coalesce_reserved_wakes"))

    def test_mercor_paid_coalesces_queued_and_reserved_wakes(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["mercor-revenue-paid"]
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("coalesce_reserved_wakes"))

    def test_lancers_storefront_uses_repo_managed_runtime_python(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["lancers-revenue-storefront"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(
            row["entrypoint"],
            "skills/earn/lancers/scripts/storefront-owner",
        )

    def test_lancers_telegram_report_uses_repo_managed_runtime_python(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["lancers-revenue-telegram-report"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(
            row["entrypoint"],
            "skills/earn/lancers/scripts/telegram-report-owner",
        )

    def test_lancers_finite_revenue_lanes_have_bounded_runtime(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        finite_lanes = (
            "lancers-revenue-application",
            "lancers-revenue-paid",
            "lancers-revenue-negotiate",
            "lancers-revenue-storefront",
            "lancers-revenue-work-sync",
            "lancers-revenue-telegram-report",
        )
        for loop_id in finite_lanes:
            with self.subTest(loop_id=loop_id):
                expected = 600 if loop_id == "lancers-revenue-application" else 300
                self.assertEqual(registry["loops"][loop_id]["runtime_timeout_seconds"], expected)
        self.assertNotIn(
            "runtime_timeout_seconds",
            registry["loops"]["lancers-revenue-browser"],
        )

    def test_marketing_metrics_daily_uses_direct_python_adapter(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["marketing-metrics-daily"]
        self.assertEqual(row["adapter"], "python")
        self.assertEqual(row["command"], ["metrics"])
        self.assertEqual(
            row["entrypoint"],
            "skills/earn/marketing-engine/report/scheduled_runner.py",
        )

    def test_marketing_metrics_uses_repo_owned_exec_adapter(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["marketing-metrics"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(
            row["entrypoint"],
            "marketing/engine/bin/marketing-metrics-owner",
        )

    def test_marketing_owner_events_uses_repo_managed_runtime_python(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["marketing-owner-events"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(
            row["entrypoint"],
            "skills/earn/marketing-engine/report/events-owner",
        )

    def test_marketing_weekly_review_uses_repo_owned_exec_adapter(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["marketing-weekly-review"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(
            row["entrypoint"],
            "skills/earn/marketing-engine/intel/weekly-review-owner",
        )
        self.assertEqual(row["effect_class"], "message")
        self.assertEqual(row["resource_class"], "agent")
        self.assertEqual(row["admission_class"], "borrow")
        self.assertEqual(row["priority"], "support")

    def test_hf_gig_paid_direct_uses_repo_owned_exec_adapter(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["hf-gig-paid-direct"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(row["entrypoint"], "skills/earn/gig/scripts/paid-direct-owner")

    def test_hf_gig_paid_direct_coalesces_queued_and_reserved_wakes(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["hf-gig-paid-direct"]
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("coalesce_reserved_wakes"))

    def test_hf_gig_evidence_gc_declares_observed_deterministic_borrow_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["hf-gig-apply-evidence-gc"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("admission_class"), "borrow")
        self.assertEqual(row.get("priority"), "support")
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))

    def test_hf_gig_daily_report_declares_observed_deterministic_borrow_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["hf-gig-daily-report"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("admission_class"), "borrow")
        self.assertEqual(row.get("priority"), "support")
        self.assertTrue(row.get("coalesce_queued_wakes"))
        self.assertTrue(row.get("coalesce_reserved_wakes"))
        self.assertTrue(row.get("reconcile_queued_release"))

    def test_crowdworks_browser_declares_browser_resource_class(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["crowdworks-revenue-browser"]
        self.assertEqual(row.get("resource_class"), "browser")
        self.assertEqual(row["browser_owner"], {
            "cdp_port": 9228,
            "profile": "~/.local/state/anicca/crowdworks/browser-profile",
        })

    def test_lancers_browser_declares_browser_resource_class(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["lancers-revenue-browser"]
        self.assertEqual(row.get("resource_class"), "browser")
        self.assertEqual(row["browser_owner"], {
            "cdp_port": 9227,
            "profile": "~/.local/state/anicca/lancers/browser-profile",
        })

    def test_line_creators_browser_declares_browser_resource_class(self):
        # Sibling of lancers-revenue-browser (2026-10-06): line-sticker-factory-hourly
        # had no keep_alive owner for identity line-creators:dais and stalled at
        # stage=submit for 15 hourly wakes with "CDP endpoint unavailable". This is
        # the missing *-browser owner every other revenue site already has.
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["line-creators-browser"]
        self.assertEqual(row.get("resource_class"), "browser")
        self.assertEqual(row["cadence"], {"keep_alive": True})
        self.assertEqual(row["entrypoint"], "skills/earn/line-sticker/scripts/browser-owner")
        self.assertEqual(row["browser_owner"], {
            "cdp_port": 9231,
            "profile": "~/.cloak/profiles/line-creators",
        })

    def test_line_sticker_factory_browser_target_owner_is_not_self_referential(self):
        # Regression for the self-reference bug: browser_target_owner pointed at
        # line-sticker-factory-hourly itself instead of a real browser owner, so no
        # process ever held identity line-creators:dais.
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["line-sticker-factory-hourly"]
        self.assertEqual(row["browser_identity"], "line-creators:dais")
        self.assertEqual(row["browser_target_owner"], "line-creators-browser")
        self.assertNotEqual(row["browser_target_owner"], "line-sticker-factory-hourly")
        self.assertEqual(
            registry["loops"][row["browser_target_owner"]]["resource_class"], "browser",
        )

    def test_hf_gig_browser_declares_browser_resource_class(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["hf-gig-browser"]
        self.assertEqual(row.get("resource_class"), "browser")
        self.assertEqual(row["browser_owner"], {
            "cdp_port": 9223,
            "profile": "~/.cloak/profiles/gig-daily-driver",
        })

    def test_affiliate_browser_declares_browser_resource_class(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["affiliate-browser"]
        self.assertEqual(row.get("resource_class"), "browser")
        self.assertEqual(row["browser_owner"], {
            "cdp_port": 9324,
            "profile": "~/.cloak/profiles/affiliate/en",
        })

    def test_affiliate_impact_browser_declares_browser_resource_class(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["affiliate-impact-browser"]
        self.assertEqual(row.get("resource_class"), "browser")
        self.assertEqual(row["browser_owner"], {
            "cdp_port": 9327,
            "profile": "~/.cloak/profiles/affiliate/impact-en",
        })

    def test_affiliate_x_browser_declares_browser_resource_class(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["affiliate-x-browser"]
        self.assertEqual(row.get("resource_class"), "browser")
        self.assertEqual(row["browser_owner"], {
            "cdp_port": 9326,
            "profile": "~/.cloak/profiles/affiliate/x-en",
        })

    def test_agent_economy_loop_declares_agent_resource_class(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["agent-economy-loop"]
        self.assertEqual(row.get("resource_class"), "agent")
        self.assertEqual(row.get("provider_route"), "shared-agent-runner")

    def test_x402_claude_p_declares_agent_resource_class(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["x402-claude-p"]
        self.assertEqual(row.get("resource_class"), "agent")
        self.assertEqual(row.get("provider_route"), "shared-agent-runner")

    def test_x402_franklin1_declares_deterministic_resource_class(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["x402-franklin1"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("provider_route"), "deterministic")

    def test_x402_franklin2_declares_deterministic_resource_class(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["x402-franklin2"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("provider_route"), "deterministic")

    def test_x402_research_serve_declares_deterministic_resource_class(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["x402-research-serve"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("provider_route"), "deterministic")

    def test_the402_provider_declares_deterministic_resource_class(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["the402-provider"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("provider_route"), "deterministic")

    def test_the402_worker_declares_deterministic_resource_class(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["the402-worker"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("provider_route"), "deterministic")

    def test_x402_seller_declares_deterministic_resource_class(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["x402-seller-8404"]
        self.assertEqual(row.get("resource_class"), "deterministic")
        self.assertEqual(row.get("provider_route"), "deterministic")

    def test_writer_claim_loop_uses_repo_owned_exec_adapter(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["writer-claim-loop"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(
            row["entrypoint"],
            "skills/writer-agent/scripts/claim-loop-owner",
        )

    def test_writer_money_sync_uses_repo_owned_exec_adapter(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["writer-money-sync"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(
            row["entrypoint"],
            "skills/writer-agent/scripts/money-sync-owner",
        )

    def test_writer_craft_train_runs_training_before_notification(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["writer-craft-train"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(row["runtime_timeout_seconds"], 25200)
        self.assertEqual(
            row["entrypoint"],
            "skills/writer-agent/scripts/craft-train-owner",
        )
        owner = (ROOT / row["entrypoint"]).read_text()
        self.assertIn("set -uo pipefail", owner)
        self.assertNotIn("set -e", owner)
        self.assertLess(owner.index('craft-train.sh'), owner.index('craft-train-notify.sh'))

    def test_writer_opportunity_discovery_uses_repo_owned_exec_adapter(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["writer-opportunity-discovery"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(
            row["entrypoint"],
            "skills/writer-agent/scripts/opportunity-discovery-owner",
        )

    def test_writer_opportunity_response_uses_repo_owned_exec_adapter(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["writer-opportunity-response"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(
            row["entrypoint"],
            "skills/writer-agent/scripts/opportunity-response-owner",
        )

    def test_writer_report_uses_repo_owned_exec_adapter(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["writer-report"]
        self.assertEqual(row["adapter"], "exec")
        self.assertEqual(row["command"], [])
        self.assertEqual(
            row["entrypoint"],
            "skills/writer-agent/scripts/writer-report-owner",
        )

    def test_marketing_score_daily_uses_direct_python_adapter(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["marketing-score-daily"]
        self.assertEqual(row["adapter"], "python")
        self.assertEqual(row["command"], ["score"])
        self.assertEqual(
            row["entrypoint"],
            "skills/earn/marketing-engine/report/scheduled_runner.py",
        )

    def test_marketing_owner_reports_are_retired_after_financial_manager_consolidation(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        self.assertNotIn("marketing-daily-report", registry["loops"])
        self.assertNotIn("marketing-owner-daily", registry["loops"])
        self.assertNotIn("marketing-owner-weekly", registry["loops"])
        self.assertIn("ai.anicca.marketing-daily-report", registry["retired_labels"])
        self.assertIn("ai.anicca.marketing-owner-daily", registry["retired_labels"])
        self.assertIn("ai.anicca.marketing-owner-weekly", registry["retired_labels"])

    def test_legacy_marketing_helpers_are_retired_not_external_owners(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        for label in (
            "ai.anicca.marketing-account-audit",
            "ai.anicca.marketing-post-metrics",
            "ai.anicca.marketing-post-notify",
        ):
            with self.subTest(label=label):
                self.assertNotIn(label, registry["external_labels"])
                self.assertIn(label, registry["retired_labels"])

    def test_self_improve_evolve_uses_direct_python_adapter(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["self-improve-evolve"]
        self.assertEqual(row["adapter"], "python")
        self.assertEqual(row["command"], ["self-improve"])
        self.assertEqual(
            row["entrypoint"],
            "skills/earn/marketing-engine/report/scheduled_runner.py",
        )
        self.assertEqual(
            row["state_root"], "~/.local/state/life-manager/self-improve-evolve",
        )
        self.assertEqual(
            row["log_root"], "~/.local/state/life-manager/self-improve-evolve/logs",
        )

    def test_obsolete_scheduled_clip_loop_is_retired(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        self.assertNotIn("clip-loop", registry["loops"])
        self.assertIn("ai.anicca.clip-loop", registry["retired_labels"])

    def test_warmup_flip_uses_canonical_life_manager_state(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        row = registry["loops"]["warmup-flip-daily"]
        self.assertEqual(row["state_root"], "~/.local/state/life-manager/warmup-flip-daily")
        self.assertEqual(row["log_root"], "~/.local/state/life-manager/warmup-flip-daily/logs")

    def test_external_labels_are_explicit_and_cannot_overlap_managed(self):
        value = {"schema_version": 2, "loops": {"example": entry()},
                 "external_labels": ["ai.anicca.tsbridge"]}
        self.assertEqual(validate_registry(value), value)
        value["external_labels"] = ["ai.anicca.example"]
        with self.assertRaisesRegex(ValueError, "overlap"):
            validate_registry(value)

    def test_upwork_provision_browser_is_owned_by_the_external_browser_registry(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        label = "ai.anicca.provision-browser.upwork.dais"
        expected_entrypoints = {row["entrypoint"] for row in registry["loops"].values()}
        report = doctor_report(
            registry,
            installed_labels={label},
            loaded_labels={label},
            existing_entrypoints=expected_entrypoints,
        )
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["unmanaged_labels"], [])

    def test_retired_labels_accept_safe_non_managed_namespaces(self):
        value = {"schema_version": 2, "loops": {"example": entry()},
                 "retired_labels": ["com.anicca.peer-api", "local.phone-cleanup"]}
        self.assertEqual(validate_registry(value), value)
        for invalid in ("bad label", "../bad", "/bad", ""):
            value["retired_labels"] = [invalid]
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "valid launchd"):
                validate_registry(value)

    def test_browser_owner_contract_accepts_unique_profile_and_port(self):
        value = {
            "schema_version": 2,
            "loops": {
                "first": browser_entry("ai.anicca.first", "~/.cloak/profiles/first", 9222),
                "second": browser_entry("ai.anicca.second", "~/.cloak/profiles/second", 9223),
            },
        }
        self.assertEqual(validate_registry(value), value)

    def test_browser_owner_contract_rejects_duplicate_profile_or_port(self):
        duplicate_profile = {
            "schema_version": 2,
            "loops": {
                "first": browser_entry("ai.anicca.first", "~/.cloak/profiles/shared", 9222),
                "second": browser_entry("ai.anicca.second", "~/.cloak/profiles/shared", 9223),
            },
        }
        with self.assertRaisesRegex(ValueError, "duplicate browser profile"):
            validate_registry(duplicate_profile)
        duplicate_port = copy.deepcopy(duplicate_profile)
        duplicate_port["loops"]["second"]["browser_owner"] = {
            "profile": "~/.cloak/profiles/second", "cdp_port": 9222,
        }
        with self.assertRaisesRegex(ValueError, "duplicate browser CDP port"):
            validate_registry(duplicate_port)

    def test_browser_identity_is_a_registry_join_without_claiming_a_profile_or_port(self):
        value = {"schema_version": 2, "loops": {"example": entry()}}
        value["loops"]["example"]["browser_identity"] = "interactive:dais"
        value["loops"]["example"]["browser_target_owner"] = "connector-native"
        self.assertEqual(validate_registry(value), value)
        schema = loop_json_schema()
        self.assertEqual(schema["properties"]["browser_identity"]["pattern"],
                         "^[a-z0-9][a-z0-9:_-]{1,127}$")
        self.assertEqual(schema["properties"]["browser_target_owner"]["pattern"],
                         "^[a-z0-9][a-z0-9:_-]{1,127}$")
        for field in ("browser_identity", "browser_target_owner"):
            for invalid in (None, "Interactive:Dais", "../dais", ""):
                value["loops"]["example"][field] = invalid
                with self.subTest(field=field, invalid=invalid), self.assertRaisesRegex(
                    ValueError, f"invalid {field}",
                ):
                    validate_registry(value)
            value["loops"]["example"][field] = (
                "interactive:dais" if field == "browser_identity" else "connector-native"
            )

    def test_browser_identity_join_requires_both_sides(self):
        for field in ("browser_identity", "browser_target_owner"):
            value = {"schema_version": 2, "loops": {"example": entry()}}
            value["loops"]["example"][field] = (
                "interactive:dais" if field == "browser_identity" else "connector-native"
            )
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError, "browser identity join requires both fields",
            ):
                validate_registry(value)

    def test_coconala_action_lanes_declare_the_gig_browser_join(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        for loop_id in (
            "hf-gig-apply-direct", "hf-gig-apply-reconcile", "hf-gig-storefront-direct",
            "hf-gig-paid-direct", "hf-gig-reply-detector",
        ):
            with self.subTest(loop_id=loop_id):
                row = registry["loops"][loop_id]
                self.assertEqual(row["browser_identity"], "coconala:kosuke")
                self.assertEqual(row["browser_target_owner"], "hf-gig-browser")
        self.assertEqual(registry["loops"]["hf-gig-reply-detector"]["effect_class"], "message")

    def test_lancers_and_crowdworks_browser_action_lanes_declare_provider_identity_join(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        expected = {
            **{
                loop_id: ("lancers:dais", "lancers-revenue-browser")
                for loop_id in (
                    "lancers-revenue-application", "lancers-revenue-storefront",
                    "lancers-revenue-negotiate", "lancers-revenue-paid",
                    "lancers-revenue-work-sync",
                )
            },
            **{
                loop_id: ("crowdworks:dais", "crowdworks-revenue-browser")
                for loop_id in (
                    "crowdworks-revenue-application", "crowdworks-revenue-reply",
                    "crowdworks-revenue-paid",
                )
            },
        }
        expected.update({
            "mercor-revenue-application": ("mercor:dais", "mercor-revenue-browser"),
            "mercor-revenue-reply": ("mercor:dais", "mercor-revenue-browser"),
        })
        for loop_id, (identity, owner) in expected.items():
            with self.subTest(loop_id=loop_id):
                row = registry["loops"][loop_id]
                self.assertEqual(row["browser_identity"], identity)
                self.assertEqual(row["browser_target_owner"], owner)
        for loop_id in (
            "lancers-revenue-telegram-report", "crowdworks-revenue-report",
        ):
            with self.subTest(loop_id=loop_id):
                self.assertNotIn("browser_identity", registry["loops"][loop_id])
                self.assertNotIn("browser_target_owner", registry["loops"][loop_id])

    def test_render_is_byte_stable_for_loop_insertion_order(self):
        left = {"schema_version": 2, "loops": {"b": entry("ai.anicca.b"), "a": entry("ai.anicca.a")}}
        right = {"schema_version": 2, "loops": {"a": entry("ai.anicca.a"), "b": entry("ai.anicca.b")}}
        self.assertEqual(render_job_models(left), render_job_models(right))

    def test_registry_covers_every_active_owned_inventory_label(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        inventory = json.loads((ROOT / "docs/evidence/runtime/2026-08-28-macos-loop-control-plane-inventory.json").read_text())
        validate_registry(registry)
        expected = {
            row["label"] for row in inventory["labels"]
            if row["installed"] and row["owner"] == "life-manager"
            and row["launchd_state"].startswith("loaded")
        }
        expected -= set(registry.get("retired_labels", []))
        expected -= set(registry.get("external_labels", []))
        self.assertTrue(expected.issubset({row["label"] for row in registry["loops"].values()}))
        self.assertEqual(registry["loops"]["pm-live-trade"]["effect_class"], "trade")
        self.assertEqual(registry["loops"]["life-manager-payout"]["effect_class"], "money")
        self.assertEqual(registry["loops"]["life-manager-honne-ja"]["effect_class"], "publish")
        self.assertEqual(registry["loops"]["agentmail-replier"]["domain"], "earn")
        self.assertIn("ai.anicca.phone-conversation", registry["retired_labels"])
        self.assertEqual(registry["loops"]["x-repost"]["label"], "ai.anicca.x-repost-pass")
        self.assertEqual(registry["loops"]["x-tweeter"]["label"], "ai.anicca.x-tweeter-pass")
        self.assertEqual(registry["loops"]["x-tweeter"]["cadence"],
                         {"calendar_interval": {"Minute": 15}})

    def test_shared_compute_proxy_owns_legacy_clawrouter_callers(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        self.assertEqual(registry["loops"]["compute-proxy"], {
            "adapter": "exec",
            "cadence": {"keep_alive": True},
            "cleanup": {"max_age_days": 14, "max_runs": 100},
            "command": ["--proxy-only"],
            "domain": "system",
            "effect_class": "none",
            "entrypoint": "runtime/compute-proxy/start-local.sh",
            "label": "ai.anicca.compute-proxy",
            "log_root": "~/.anicca/logs",
            "provider_route": "deterministic",
            "state_root": "~/.anicca",
            "system_role": "platform",
        })
        callers = (
            "skills/earn/x402-sell/the402-worker-daemon.mjs",
            "skills/earn/polymarket-trade/run.sh",
            "skills/earn/polymarket-trade/decision_loop.py",
            "skills/report/daily-nl-report.mjs",
            "skills/earn/self-improve/config.yaml",
        )
        for relative in callers:
            with self.subTest(relative=relative):
                source = (ROOT / relative).read_text()
                self.assertNotIn("127.0.0.1:8402", source)
                self.assertIn("127.0.0.1:18402", source)

    def test_non_coconala_marketplace_loops_use_the_exec_adapter_shell(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        loop_ids = {
            "crowdworks-revenue-application", "crowdworks-revenue-paid",
            "crowdworks-revenue-report", "gig-outcome-watch",
            "lancers-revenue-application", "lancers-revenue-browser",
            "lancers-revenue-negotiate", "lancers-revenue-paid",
            "lancers-revenue-storefront", "lancers-revenue-telegram-report",
            "lancers-revenue-work-sync", "mercor-revenue-application",
            "mercor-revenue-paid", "life-manager-taskmarket-ledger",
            "life-manager-ugig-invoice-observer",
        }
        for loop_id in loop_ids:
            with self.subTest(loop_id=loop_id):
                self.assertEqual(registry["loops"][loop_id]["adapter"], "exec")
                self.assertIsInstance(registry["loops"][loop_id]["command"], list)
        self.assertEqual(
            registry["loops"]["lancers-revenue-browser"]["entrypoint"],
            "skills/earn/lancers/scripts/browser-owner",
        )
        self.assertFalse((ROOT / "runtime/legacy/lancers-revenue-browser/run.sh").exists())
        self.assertFalse((ROOT / "apps/lancers-revenue/scripts/install-local.sh").exists())
        self.assertFalse((ROOT / "apps/lancers-revenue/launchd/ai.anicca.lancers-revenue-browser.plist").exists())

    def test_production_render_matches_byte_stable_fixture(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        expected = (ROOT / "runtime/loop/tests/fixtures/macos-loop-jobs.json").read_bytes()
        self.assertEqual(render_job_models(registry), expected)

    def test_finite_effect_free_control_wakes_declare_coalescing_contract(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        missing = {}
        for loop_id, row in registry["loops"].items():
            interval = row.get("cadence", {}).get("start_interval_seconds")
            if (
                loop_id in CONTROL_PLANE_SAFETY_LOOPS
                or row.get("effect_class") != "none"
                or row.get("system_role") not in {"control", "shared"}
                or type(interval) is not int
                or not 1 <= interval <= 900
            ):
                continue
            absent = [
                field for field in (
                    "coalesce_queued_wakes",
                    "coalesce_reserved_wakes",
                    "reconcile_queued_release",
                ) if row.get(field) is not True
            ]
            if absent:
                missing[loop_id] = absent
        self.assertEqual(missing, {})

    def test_loop_json_schema_is_generated_from_the_registry_contract(self):
        schema_path = ROOT / "runtime/loop/loop.schema.json"
        self.assertEqual(schema_path.read_bytes(), render_loop_json_schema())
        schema = json.loads(schema_path.read_text())
        self.assertEqual(schema["required"], ["loop_id", *sorted(entry())])
        self.assertEqual(schema["properties"]["domain"]["enum"], [
            "earn", "financial", "growth", "mental", "physical", "system",
        ])
        self.assertEqual(schema["properties"]["effect_class"]["enum"], [
            "account_mutation", "application", "message", "money", "none", "publish", "trade",
        ])
        self.assertEqual(schema["properties"]["admission_effect_scope"]["enum"], [
            "occurrence", "owner",
        ])
        self.assertEqual(schema["properties"]["adapter"]["enum"], ["exec", "python"])
        self.assertEqual(schema["properties"]["resource_class"]["enum"], [
            "agent", "browser", "deterministic",
        ])
        self.assertEqual(schema["properties"]["command"]["items"], {
            "type": "string", "minLength": 1,
        })
        self.assertFalse(schema["additionalProperties"])

    def test_registry_and_loop_schema_share_boundary_constraints(self):
        schema = json.loads(render_loop_json_schema())
        self.assertEqual(
            schema["properties"]["entrypoint"]["pattern"],
            r"^(?!/)(?!(?:\./)*\.?$)(?!.*(?:^|/)\.\.(?:/|$)).+$",
        )
        self.assertEqual(
            schema["properties"]["browser_owner"]["properties"]["profile"]["pattern"],
            r"^~/(?!\.\.(?:/|$))(?!.*\/\.\.(?:/|$)).+",
        )
        browser_pattern = schema["properties"]["browser_owner"]["properties"]["profile"]["pattern"]
        self.assertIsNotNone(re.fullmatch(browser_pattern, "~/.cloak/profiles/example"))
        self.assertIsNone(re.fullmatch(browser_pattern, "~/../shared"))
        self.assertIsNone(re.fullmatch(browser_pattern, "~/.cloak/../shared"))
        invalid = []
        for entrypoint in ("./", "bin/../other.sh"):
            value = entry()
            value["entrypoint"] = entrypoint
            invalid.append(value)
        for field in ("state_root", "log_root"):
            value = entry()
            value[field] = "~/"
            invalid.append(value)
        value = entry()
        value["cadence"] = {"start_interval_seconds": True}
        invalid.append(value)
        value = entry()
        value["cleanup"]["max_runs"] = True
        invalid.append(value)
        value = entry()
        value["browser_owner"] = None
        invalid.append(value)
        value = browser_entry("ai.anicca.example", "~/.cloak/../shared", 9222)
        invalid.append(value)
        value = browser_entry("ai.anicca.example", "~/../shared", 9222)
        invalid.append(value)
        for row in invalid:
            with self.subTest(row=row), self.assertRaises(ValueError):
                validate_registry({"schema_version": 2, "loops": {"example": row}})

    def test_loop_entrypoints_do_not_select_auth_or_codex_home(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        forbidden = re.compile(
            r"CODEX_HOME|(?<![-\w])auth\.json|AGENT_RUNNER_PROVIDER"
        )
        violations = []
        for loop_id, entry in registry["loops"].items():
            path = ROOT / entry["entrypoint"]
            if path.is_file() and forbidden.search(path.read_text(errors="replace")):
                violations.append((loop_id, entry["entrypoint"]))
        self.assertEqual(violations, [])

    def test_active_entrypoints_do_not_depend_on_other_worktrees(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        forbidden = re.compile(r"/" + r"Users/[^/]+/.*(?:\.worktrees|/Projects/|/profitable-claude)")
        violations = []
        for loop_id, entry in registry["loops"].items():
            path = ROOT / entry["entrypoint"]
            if path.is_file() and forbidden.search(path.read_text(errors="replace")):
                violations.append((loop_id, entry["entrypoint"]))
        self.assertEqual(violations, [])

    def test_render_500_loops_and_status_under_five_seconds(self):
        base = entry()
        loops = {}
        for index in range(500):
            loop_id = f"scale-{index:03d}"
            row = copy.deepcopy(base)
            row["label"] = f"ai.anicca.{loop_id}"
            row["state_root"] = f"~/.local/state/life-manager/{loop_id}"
            row["log_root"] = f"~/.local/state/life-manager/{loop_id}/logs"
            loops[loop_id] = row
        registry = {"schema_version": 2, "loops": loops}

        started = time.perf_counter()
        rendered = render_job_models(registry)
        render_seconds = time.perf_counter() - started
        started = time.perf_counter()
        rows = status_rows(
            registry, loaded={}, disabled={}, events={}, installed_releases={})
        status_seconds = time.perf_counter() - started

        self.assertEqual((len(rendered.splitlines()), len(rows)), (1, 500))
        self.assertLess(render_seconds, 5)
        self.assertLess(status_seconds, 5)


class RetirementGuardRegistryTests(unittest.TestCase):
    def test_guarded_retirement_registry_is_valid(self):
        value = {"schema_version": 2, "loops": {"example": entry()},
                 "retired_labels": ["ai.anicca.legacy"], "guarded_retired_labels": {
                     "ai.anicca.orphan": {"expected_arguments_sha256": "a" * 64,
                                          "missing_entrypoint": "~/loops/releases/old/entry.py"}}}
        self.assertEqual(validate_registry(value), value)

    def test_invalid_guard_metadata_is_rejected(self):
        for bad in (None, [], {"not-retired": {}}, {"ai.anicca.orphan": {}},
                    {"ai.anicca.orphan": {"expected_arguments_sha256": "bad", "missing_entrypoint": "/missing.py"}},
                    {"ai.anicca.orphan": {"expected_arguments_sha256": "a" * 64, "missing_entrypoint": "relative.py"}},
                    {"ai.anicca.orphan": {"expected_arguments_sha256": "a" * 64, "missing_entrypoint": "/missing.py", "skip": True}}):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ValueError, "guarded_retired_labels"):
                    validate_registry({"schema_version": 2, "loops": {"example": entry()},
                                       "retired_labels": ["ai.anicca.orphan"], "guarded_retired_labels": bad})


class MobileAppEffectReconcileTests(unittest.TestCase):
    def test_mobile_app_publish_loops_declare_the_postiz_effect_reconcile(self):
        """Mobile publish owners must reconcile effects through their own Postiz route."""
        registry = json.loads(
            (ROOT / "config/loop-registry.json").read_text(encoding="utf-8")
        )
        missing = []
        for loop_id, row in registry["loops"].items():
            if (
                row.get("entrypoint") != "apps/life-manager/scripts/mobile-app"
                or row.get("effect_class") != "publish"
            ):
                continue
            reconcile = row.get("effect_reconcile") or {}
            argv = reconcile.get("argv") or []
            valid = (
                argv[:3] == [
                    "apps/life-manager/scripts/mobile-postiz-provider-reconcile.py",
                    "--auto-owner",
                    loop_id,
                ]
                and reconcile.get("occurrence_flag") == "--occurrence-id"
                and reconcile.get("resolve_flag") == "--resolve"
            )
            if not valid:
                missing.append(loop_id)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
