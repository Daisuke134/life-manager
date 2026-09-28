"""X23: the capafy loop must be routed to a task class that can fit its work.

Measured 2026-07-27 against the live capafy prompt (read-only dry run, sonnet,
tools on): 21 turns / 229s wall. A real publish pass -- which drives the Capafy
CP1/CP2/CP3 browser UI -- is strictly longer. capafy-loop-daily.sh was wired to
`tool-agent`, whose timeout is 180s, so every pass was killed mid-flight: on
2026-07-24..27 attempt-01 (codex) hit rc=124 four days running with ~195KB of
real progress already on stdout. This is the same failure the agent-runner
config already documents for the browser lanes, which is why `browser-lane-agent`
(900s) was split out of `tool-agent` -- capafy is simply an unmigrated consumer.

Also pins the fail-closed prompt guard in run_agent.sh: a caller that pipes in an
empty or trivial prompt must be rejected before the runner (and therefore before
a paid provider) is invoked. run_agent.sh appends a ~180-char FINAL CONTRACT to
whatever it is given, so an empty caller prompt would otherwise look substantial
to the runner's own guard.
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ENGINE = Path(__file__).resolve().parent
RUN_AGENT = ENGINE / "run_agent.sh"
CAPAFY = ENGINE.parents[1] / "self" / "capafy-loop" / "capafy-loop-daily.sh"
CAPAFY_MARKETING = ENGINE.parents[1] / "earn" / "capafy-marketing" / "capafy-ig-marketing-daily.sh"
CAPAFY_DRAINER = ENGINE.parents[1] / "capafy-autopublish" / "scripts" / "daily_loop.sh"
CAPAFY_CP1 = ENGINE.parents[1] / "capafy-autopublish" / "CP1_AGENTIC.md"
CONFIG = ENGINE.parents[2] / "runtime" / "agent-runner" / "config.json"

MIN_TIMEOUT_SECONDS = 900
CAPAFY_EVIDENCE_MIN_FREE_BYTES = 64 * 1024 * 1024


def task_class_of(script: Path) -> str:
    text = script.read_text(encoding="utf-8")
    marker = "--task-class "
    index = text.index(marker) + len(marker)
    return text[index:].split()[0]


class CapafyLoopWiringTest(unittest.TestCase):
    def test_capafy_uses_its_measured_evidence_floor_for_every_agent_run(self):
        text = CAPAFY.read_text(encoding="utf-8")
        invocations = [
            line.strip() for line in text.splitlines()
            if '"$RUN_AGENT"' in line
        ]
        self.assertEqual(len(invocations), 2)
        expected = (
            f"AGENT_RUNNER_EVIDENCE_MIN_FREE_BYTES="
            f"{CAPAFY_EVIDENCE_MIN_FREE_BYTES} \"$RUN_AGENT\""
        )
        self.assertTrue(
            all(expected in invocation for invocation in invocations),
            "both Capafy agent paths must override only the generic 512 MiB "
            "evidence reserve with the measured Capafy-specific 64 MiB floor",
        )

    def test_capafy_marketing_uses_the_same_measured_evidence_floor(self):
        text = CAPAFY_MARKETING.read_text(encoding="utf-8")
        self.assertIn(
            f"AGENT_RUNNER_EVIDENCE_MIN_FREE_BYTES="
            f"{CAPAFY_EVIDENCE_MIN_FREE_BYTES} \"$RUN_AGENT\"",
            text,
        )

    def test_capafy_uses_a_task_class_that_can_fit_a_measured_pass(self):
        task_class = task_class_of(CAPAFY)
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        classes = config["task_classes"]
        self.assertIn(task_class, classes)
        timeout = int(classes[task_class].get(
            "timeout_seconds", config["timeout_seconds"]))
        self.assertGreaterEqual(
            timeout, MIN_TIMEOUT_SECONDS,
            f"capafy is wired to {task_class} ({timeout}s); a measured read-only "
            f"pass already takes 229s and a publish pass is longer",
        )

    def test_capafy_prompt_does_not_promise_a_budget_the_runner_will_not_honour(self):
        text = CAPAFY.read_text(encoding="utf-8")
        task_class = task_class_of(CAPAFY)
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        timeout = int(config["task_classes"][task_class].get(
            "timeout_seconds", config["timeout_seconds"]))
        if "NO wall-clock limit" in text:
            self.assertGreaterEqual(
                timeout, MIN_TIMEOUT_SECONDS,
                "prompt tells the model it has no wall-clock limit while the "
                "runner will SIGKILL it -- the model cannot plan against that",
            )

    def test_capafy_drained_prompt_rejects_stale_log_misattribution(self):
        text = CAPAFY.read_text(encoding="utf-8")
        self.assertIn("INITIAL WRAPPER INVENTORY VERDICT: $VERDICT", text)
        self.assertIn("Historical log lines before this execution are not current failures", text)
        self.assertIn("If the INITIAL action is DRAINED and a review slot is free, develop and submit exactly one new Skill.", text)

    def test_capafy_drainer_prompt_binds_authoritative_inventory_action(self):
        text = CAPAFY_DRAINER.read_text(encoding="utf-8")
        self.assertIn("AUTHORITATIVE INVENTORY ACTION:", text)
        self.assertIn("Do not select or substitute another item", text)
        self.assertIn("$(printf '%s' \"$INV\" | tail -1)", text)

    def test_capafy_drainer_uses_a_browser_task_class_that_fits_cp1(self):
        task_class = task_class_of(CAPAFY_DRAINER)
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        timeout = int(config["task_classes"][task_class].get(
            "timeout_seconds", config["timeout_seconds"]))
        self.assertGreaterEqual(timeout, MIN_TIMEOUT_SECONDS)

    def test_capafy_cp1_guide_covers_current_silent_save_blockers(self):
        text = CAPAFY_CP1.read_text(encoding="utf-8")
        # Live card 2026-09-28 (#6068): no welcomeMessage / third-party fields on CP1.
        for blocker in ("test input", "DPA"):
            self.assertIn(blocker, text)

    def test_run_agent_accepts_every_task_class_its_consumers_declare(self):
        # run_agent.sh keeps its own task-class whitelist, so a consumer can be
        # retargeted to a class the runner supports and still die at rc=2 on the
        # wrapper. Caught exactly that way while migrating capafy off tool-agent.
        proc = self._run_agent_with(
            "Run one bounded fixture pass and return the contract JSON only.\n",
            task_class=task_class_of(CAPAFY),
        )
        self.assertNotIn("invalid or missing --task-class", proc.stderr)

    def test_run_agent_accepts_the_capafy_drainer_browser_class(self):
        # capafy-autopublish uses this longer browser class for the actual
        # CP1/CP2/CP3 drainer.  Keep the wrapper whitelist from silently
        # rejecting a valid configured class before any live work begins.
        proc = self._run_agent_with(
            "Run one bounded Capafy browser publish fixture and return JSON only.\n",
            task_class="application-lane-agent",
        )
        self.assertNotIn("invalid or missing --task-class", proc.stderr)

    def _run_agent_with(self, prompt_text, task_class="tool-agent"):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = os.environ.copy()
            # Point the runner at a path that does not exist: if the guard works
            # we exit before ever needing it, so this also proves ordering.
            env["AGENT_RUNNER_BIN"] = str(root / "never-invoked-runner.py")
            proc = subprocess.run(
                ["bash", str(RUN_AGENT), "--task-class", task_class,
                 "--evidence-dir", str(root / "evidence"),
                 "--task-label", "x23", "--loop", "x23"],
                input=prompt_text, text=True, capture_output=True, env=env,
            )
            return proc

    def test_run_agent_rejects_an_empty_caller_prompt(self):
        proc = self._run_agent_with("")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("prompt", proc.stderr.lower())
        self.assertNotIn("runner not found", proc.stderr)

    def test_run_agent_rejects_a_trivial_caller_prompt(self):
        proc = self._run_agent_with("hi\n")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("prompt", proc.stderr.lower())
        self.assertNotIn("runner not found", proc.stderr)

    def test_run_agent_accepts_a_real_caller_prompt(self):
        proc = self._run_agent_with(
            "Run the bounded capafy pass and return the contract JSON only.\n")
        # Guard must pass this through; it then fails on the missing runner,
        # which proves the prompt guard was not what stopped it.
        self.assertIn("runner not found", proc.stderr)


if __name__ == "__main__":
    unittest.main()
