import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "reconcile_ledger.py"


def load_module():
    spec = importlib.util.spec_from_file_location("reconcile_ledger_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_server_agents_accepts_current_flat_snake_case_publish_list(monkeypatch):
    module = load_module()
    payload = {
        "ok": True,
        "agents": [{"agent_id": "8828622062", "name": "Slide Maker", "agent_status": "online"}],
    }
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(payload)),
    )

    assert module.server_agents() == [{
        "agentId": "8828622062", "name": "Slide Maker", "agentStatus": "online",
    }]


def test_server_agents_accepts_legacy_nested_publish_list(monkeypatch):
    module = load_module()
    payload = {
        "ok": True,
        "agents": {"list": [{"agentId": "1", "name": "Legacy", "agentStatus": "online"}]},
    }
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(payload)),
    )

    assert module.server_agents() == [{"agentId": "1", "name": "Legacy", "agentStatus": "online"}]
