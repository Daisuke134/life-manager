import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "application_parent.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("application_parent_hint_test", SCRIPT)
parent = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(parent)


def test_enter_effect_boundary_clears_exact_private_hint(tmp_path, monkeypatch):
    hint = tmp_path / "entrypoint-result.json"
    hint.write_text(json.dumps({"status": "pre_effect_failure", "effect": 0}) + "\n")
    hint.chmod(0o600)
    monkeypatch.setenv("LIFE_MANAGER_RESULT_HINT_PATH", str(hint))

    parent._enter_effect_boundary()

    assert not hint.exists()


@pytest.mark.parametrize("value", [
    {"status": "pre_effect_failure", "effect": 1},
    {"status": "unknown", "effect": 0},
])
def test_enter_effect_boundary_rejects_untrusted_hint(tmp_path, monkeypatch, value):
    hint = tmp_path / "entrypoint-result.json"
    hint.write_text(json.dumps(value) + "\n")
    hint.chmod(0o600)
    monkeypatch.setenv("LIFE_MANAGER_RESULT_HINT_PATH", str(hint))

    with pytest.raises(parent.ParentContractError, match="pre_effect_hint_invalid"):
        parent._enter_effect_boundary()


def test_enter_effect_boundary_is_noop_outside_managed_runtime(monkeypatch):
    monkeypatch.delenv("LIFE_MANAGER_RESULT_HINT_PATH", raising=False)
    parent._enter_effect_boundary()


def test_enter_effect_boundary_is_idempotent_after_first_submit(tmp_path, monkeypatch):
    hint = tmp_path / "entrypoint-result.json"
    monkeypatch.setenv("LIFE_MANAGER_RESULT_HINT_PATH", str(hint))
    parent._enter_effect_boundary()
