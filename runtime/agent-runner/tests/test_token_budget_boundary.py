import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent_runner import rollout_budget_tokens_for  # noqa: E402
from token_budget import TokenBudgetLedger  # noqa: E402


class TokenBudgetBoundaryTest(unittest.TestCase):
    def test_promptbase_example_route_always_enforces_its_small_rollout_cap(self):
        self.assertEqual(
            rollout_budget_tokens_for("promptbase-example-agent", 8192, False, None),
            8192,
        )
        self.assertIsNone(
            rollout_budget_tokens_for("high-value-agent", 65536, False, None)
        )

    def test_pass_budget_overrides_task_default_when_budget_is_enabled(self):
        self.assertEqual(
            rollout_budget_tokens_for("promptbase-example-agent", 8192, True, 4096),
            4096,
        )

    def test_pass_budget_can_operate_without_daily_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger=TokenBudgetLedger(Path(directory)/"budget.jsonl")
            values=[]
            for event in ("a","b"):
                values.append(ledger.reserve(event_id=event,loop="affiliate",scope_id=event,
                    daily_scope="affiliate",day="2026-08-28",reservation_tokens=100,
                    pass_limit=100,daily_limit=None))
                ledger.settle(event_id=event,actual_tokens=100,measurement="provider_reported")
            self.assertEqual([x["status"] for x in values],["allowed","allowed"])


if __name__ == "__main__": unittest.main()
