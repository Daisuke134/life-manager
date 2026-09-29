import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "select_publish_agent.py"
TITLE = "Customer Renewal Evidence Brief"
SUFFIX = " (LM generated — please review and edit before saving)"


def _run(extra):
    # Five occupants; review_rejected rows never trigger a network detail read.
    agents = [{"agent_id": "4973250899", "name": TITLE + SUFFIX, "agent_status": "draft"}]
    agents += [{"agent_id": str(1000 + i), "name": f"Other {i}", "agent_status": "review_rejected"} for i in range(4)]
    return subprocess.run([sys.executable, str(SCRIPT), "--title", TITLE, "--require-free-slot", *extra],
                          input=json.dumps({"agents": agents}), capture_output=True, text=True)


def test_reusing_the_fifth_occupant_draft_needs_no_free_slot():
    result = _run(["--reuse-agent-id", "4973250899"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "4973250899"


def test_a_new_agent_still_needs_a_free_slot():
    result = _run([])
    assert result.returncode != 0
    assert "CAP_FULL" in result.stderr + result.stdout
