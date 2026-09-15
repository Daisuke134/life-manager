import importlib.util
from pathlib import Path
import sys

import pytest


MODULE = Path(__file__).parents[1] / "agent_runner.py"
sys.path.insert(0, str(MODULE.parent))
SPEC = importlib.util.spec_from_file_location("life_manager_agent_runner_escalation", MODULE)
agent_runner = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(agent_runner)


def test_non_escalation_task_ignores_stale_reason_without_granting_authority():
    reason, warning = agent_runner.normalize_escalation_request(
        {"requires_explicit_escalation": False},
        "stale caller metadata",
    )
    assert reason is None
    assert warning == "extraneous_escalation_reason_ignored"


def test_explicit_escalation_still_requires_and_retains_a_reason():
    with pytest.raises(ValueError, match="explicit escalation reason"):
        agent_runner.normalize_escalation_request(
            {"requires_explicit_escalation": True}, None,
        )
    reason, warning = agent_runner.normalize_escalation_request(
        {"requires_explicit_escalation": True}, "bounded repair",
    )
    assert reason == "bounded repair"
    assert warning is None
