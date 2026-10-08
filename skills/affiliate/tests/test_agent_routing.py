from __future__ import annotations

import json
import hashlib
import importlib.util
import tempfile
import unittest
import sys
from argparse import Namespace
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG = REPO_ROOT / "runtime" / "agent-runner" / "config.json"
RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "agent_runner.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("affiliate_agent_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_vendor_runner_module():
    vendor = REPO_ROOT / "runtime" / "agent-runner"
    sys.path.insert(0, str(vendor))
    spec = importlib.util.spec_from_file_location(
        "affiliate_vendor_agent_runner", vendor / "agent_runner.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AffiliateAgentRoutingTests(unittest.TestCase):
    def test_pass_budget_can_run_without_a_daily_cap(self) -> None:
        runner = load_vendor_runner_module()
        with tempfile.TemporaryDirectory() as temporary:
            ledger = runner.TokenBudgetLedger(Path(temporary) / "budget.jsonl")
            first = ledger.reserve(
                event_id="one", loop="affiliate", scope_id="run-one",
                daily_scope="affiliate", day="2026-08-24",
                reservation_tokens=100, pass_limit=100, daily_limit=None,
            )
            ledger.settle(event_id="one", actual_tokens=100, measurement="provider_reported")
            second = ledger.reserve(
                event_id="two", loop="affiliate", scope_id="run-two",
                daily_scope="affiliate", day="2026-08-24",
                reservation_tokens=100, pass_limit=100, daily_limit=None,
            )
        self.assertEqual(first["status"], "allowed")
        self.assertIsNone(first["daily_limit_tokens"])
        self.assertEqual(second["status"], "allowed")

    def test_budgeted_codex_command_enforces_native_rollout_ceiling(self) -> None:
        runner = load_vendor_runner_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = runner.command_for(
                "codex", "/usr/bin/codex", {},
                {"model": "gpt-5.6-terra", "effort": "high"},
                Namespace(task_class="marketing-agent", workdir=root, image=[]),
                "bounded task", {"type": "object"}, root / "result.json", 60,
                None, rollout_budget_tokens=8192,
            )
        expected = (
            "features.rollout_budget={enabled=true,limit_tokens=8192,"
            "reminder_at_remaining_tokens=[],sampling_token_weight=1.0,"
            "prefill_token_weight=1.0}"
        )
        self.assertIn(expected, command)

    def test_native_rollout_exhaustion_is_typed_budget_failure(self) -> None:
        runner = load_vendor_runner_module()
        self.assertEqual(
            runner.classify_provider_error(
                1, False,
                '{"type":"turn.failed","error":{"message":"shared rollout token budget exhausted"}}',
                "", "",
            ),
            "native_rollout_budget_exhausted",
        )

    def test_strategy_and_repair_routes_are_explicit_and_single_candidate(self) -> None:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        strategy = config["task_classes"]["affiliate-marketing-agent"]
        repair = config["task_classes"]["affiliate-escalation-agent"]

        self.assertEqual(strategy["route"], "affiliate-sol-medium-strategy")
        self.assertTrue(strategy["requires_explicit_escalation"])
        self.assertEqual(
            strategy["candidates"],
            [{"provider": "codex", "model": "gpt-6.1-sol", "effort": "medium", "profile_alias": "acct2"}],
        )
        self.assertEqual(repair["route"], "affiliate-sol-high-one-use-repair")
        self.assertTrue(repair["requires_explicit_escalation"])
        self.assertEqual(
            repair["candidates"],
            [{"provider": "codex", "model": "gpt-6.1-sol", "effort": "high", "profile_alias": "acct2"}],
        )

    def test_evidence_seal_binds_result_and_source_set_and_detects_tampering(self) -> None:
        runner = load_runner_module()
        source_set_sha256 = "a" * 64
        with tempfile.TemporaryDirectory() as temporary:
            evidence_dir = Path(temporary) / "evidence"
            evidence_dir.mkdir(mode=0o700)
            result_path = evidence_dir / "attempt-01.result.json"
            result_path.write_text('{"title":"verified"}\n', encoding="utf-8")
            (evidence_dir / "summary.json").write_text(
                json.dumps({"attempt_count": 1, "result_path": str(result_path)}) + "\n",
                encoding="utf-8",
            )
            (evidence_dir / "attempts.jsonl").write_text('{"attempt":1}\n', encoding="utf-8")

            runner.seal_evidence(evidence_dir, 0, source_set_sha256)
            seal = runner.verify_evidence_seal(evidence_dir, source_set_sha256)

            self.assertEqual(seal["source_set_sha256"], source_set_sha256)
            self.assertEqual(
                seal["result_sha256"], hashlib.sha256(result_path.read_bytes()).hexdigest()
            )
            with self.assertRaises(runner.EvidenceError):
                runner.verify_evidence_seal(evidence_dir, "b" * 64)
            result_path.write_text('{"title":"tampered"}\n', encoding="utf-8")
            with self.assertRaises(runner.EvidenceError):
                runner.verify_evidence_seal(evidence_dir, source_set_sha256)


if __name__ == "__main__":
    unittest.main()
