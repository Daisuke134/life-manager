import unittest
from pathlib import Path


DAILY_LOOP = Path(__file__).resolve().parents[1] / "scripts" / "daily_loop.sh"
RUNBOOK = Path(__file__).resolve().parents[1] / "DAILY_LOOP.md"
MONEY_DAILY = Path(__file__).resolve().parents[2] / "self" / "capafy-loop" / "capafy-loop-daily.sh"
LEGACY_CLI = Path(__file__).resolve().parents[2] / "self" / "capafy-loop" / "capafy-loop-cli.sh"


class ProviderAgnosticRunnerTest(unittest.TestCase):
    def test_publish_drainer_uses_shared_runner_instead_of_direct_claude(self):
        text = DAILY_LOOP.read_text(encoding="utf-8")

        self.assertIn("run_agent.sh", text)
        # CP1/CP2/CP3 drives the browser UI and needs the measured long
        # application lane; the 180-second tool lane killed real publishes.
        self.assertIn("--task-class application-lane-agent", text)
        self.assertNotRegex(text, r"\bclaude\s+-p\b")

    def test_rejected_retry_waits_when_all_five_submission_slots_are_full(self):
        text = RUNBOOK.read_text(encoding="utf-8")

        normalized = " ".join(text.split())
        self.assertIn(
            'If occupied is 5, STOP and report "cap full, N listed" for both fresh '
            "and retry work",
            normalized,
        )

    def test_outer_daily_owner_skips_agent_spend_when_cap_is_full(self):
        text = MONEY_DAILY.read_text(encoding="utf-8")

        gate = text.index('if [ "$VERDICT" = "CAP_FULL" ]')
        publishable_branch = text.index(
            'if [ "$VERDICT" = "PUBLISHABLE" ]', gate
        )
        drainer = text.index(
            'bash "$LIFE_MANAGER_RELEASE_ROOT/skills/capafy-autopublish/scripts/daily_loop.sh"',
            publishable_branch,
        )
        # The cap gate precedes both the direct bounded drainer and any
        # provider-backed offline/self-heal runner invocation.
        self.assertLess(gate, publishable_branch)
        self.assertLess(publishable_branch, drainer)
        self.assertIn("agent spend=0; platform write=0", text)

    def test_legacy_cli_converges_on_the_single_launchd_owner(self):
        text = LEGACY_CLI.read_text(encoding="utf-8")

        self.assertIn("bin/launchctl-safe", text)
        self.assertIn("ai.anicca.capafy-loop-daily", text)
        self.assertNotIn("tmux", text)
        self.assertNotIn("CronCreate", text)
        self.assertNotIn("command -v claude", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
