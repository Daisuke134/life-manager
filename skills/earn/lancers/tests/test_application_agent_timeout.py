from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "application_loop.py"


def _module():
    spec = importlib.util.spec_from_file_location("lancers_application_timeout_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_safety_verifier_uses_a_shorter_parent_timeout_than_planner():
    module = _module()

    assert module._agent_timeout_seconds(module.SAFETY_TASK_CLASS) == 150
    assert module._agent_timeout_seconds(module.PLANNER_TASK_CLASS) == module.PLANNER_TIMEOUT_SECONDS

