import importlib.util
import json
import os
import sqlite3
from pathlib import Path


def test_bootout_guard_preserves_registered_waiter_and_claim(tmp_path, monkeypatch):
    assert importlib.util.find_spec("runtime.loop.launchctl_pending_guard") is not None
    from runtime.loop.launchctl_pending_guard import check_service

    root = tmp_path / "admission"
    root.mkdir()
    monkeypatch.setenv("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", str(root))
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"loops": {
        "probe": {"label": "ai.anicca.probe"},
        "other": {"label": "ai.anicca.other"},
    }}))
    database = root / "admission-v2.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE queue (owner_id TEXT)")
        connection.execute("CREATE TABLE occurrences (owner_id TEXT, state TEXT, effect_unknown INTEGER)")
        connection.execute("INSERT INTO queue VALUES ('probe')")
        connection.execute("INSERT INTO occurrences VALUES ('probe', 'queued', 0)")

    service = f"gui/{os.getuid()}/ai.anicca.probe"
    assert check_service(registry, service) == 75
    assert check_service(registry, f"gui/{os.getuid()}/ai.anicca.other") == 0
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM queue")
        connection.execute("UPDATE occurrences SET state='claimed'")
    assert check_service(registry, service) == 75
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE occurrences SET state='released'")
    assert check_service(registry, service) == 0
    database.write_text("corrupt sqlite")
    assert check_service(registry, service) == 1
