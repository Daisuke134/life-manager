import importlib.util
import inspect
import os
from pathlib import Path


SCRIPTS = Path(__file__).parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_application_yields_outer_browser_lease_only_around_model_and_validation():
    parent = (SCRIPTS / "application_parent.py").read_text()
    direct = (SCRIPTS / "application_direct.py").read_text()

    assert "def _invoke_isolated_planner_yielding(" in parent
    assert "decisions, planner_missing_request_ids = _invoke_isolated_planner_yielding(" in parent
    assert "def _validate_parent_result_yielding(" in direct
    assert direct.count("_validate_parent_result_yielding(") == 4


def test_shared_yield_releases_and_reacquires_same_holder(monkeypatch, tmp_path):
    browser_yield = _load("browser_lease_yield")
    guard = tmp_path / "browser-guard.sh"
    guard.write_text("#!/bin/sh\n")
    guard.chmod(0o700)
    monkeypatch.setenv("LIFE_MANAGER_BROWSER_LEASE_HOLDER_PID", "12345")
    monkeypatch.setenv("LIFE_MANAGER_BROWSER_LEASE_IDENTITY", "coconala:kosuke")
    monkeypatch.setenv("LIFE_MANAGER_BROWSER_GUARD", str(guard))
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs["env"].get("AI_BROWSER_HOLDER_PID")))
        return type("Completed", (), {
            "returncode": 0,
            "stdout": "http://127.0.0.1:9223\n",
        })()

    monkeypatch.setattr(browser_yield.subprocess, "run", run)
    with browser_yield.yield_registered_browser_lease():
        assert calls == [([str(guard), "release", "coconala:kosuke"], "12345")]

    assert calls == [
        ([str(guard), "release", "coconala:kosuke"], "12345"),
        ([str(guard), "acquire", "coconala:kosuke"], "12345"),
    ]
    assert os.environ["CDP_DAILY_DRIVER_PORT"] == "9223"


def test_paid_and_application_use_the_shared_yield_helper():
    paid = (SCRIPTS / "paid_direct.py").read_text()
    parent = (SCRIPTS / "application_parent.py").read_text()
    direct = (SCRIPTS / "application_direct.py").read_text()

    for source in (paid, parent, direct):
        assert "from browser_lease_yield import" in source
