"""Provisioning expiry must free abandoned admission rows before a new acquire."""
from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path


def load_module():
    path = Path(__file__).resolve().parent / "cdp_context_lease.py"
    spec = importlib.util.spec_from_file_location("cdp_context_lease_provisioning_deadline", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_acquire_reclaims_expired_live_provisioning_row_before_create(monkeypatch, tmp_path):
    module = load_module()
    leases_file = tmp_path / "leases.json"
    monkeypatch.setenv("CLOAK_CONTEXT_LEASES_FILE", str(leases_file))
    leases_file.write_text(json.dumps({
        "task": {
            "provisioning": True,
            "provisioning_started_at": time.time() - 300,
            "provisioning_deadline": time.time() - 1,
            "context_id": "old-context",
            "target_id": "old-target",
            "token": "a" * 32,
            "generation": 1,
            "pid": os.getpid(),
            "ts": int(time.time()),
        },
    }), encoding="utf-8")
    calls = []

    async def calls_for_reclaim_and_create(pairs, timeout=None):
        calls.append(pairs[0][0])
        output = []
        for method, _params in pairs:
            if method == "Target.disposeBrowserContext":
                output.append({})
            elif method == "Target.createBrowserContext":
                output.append({"browserContextId": "new-context"})
            elif method == "Target.createTarget":
                output.append({"targetId": "new-target"})
        return output

    monkeypatch.setattr(module, "_calls", calls_for_reclaim_and_create)
    result = module.acquire("task", no_seed=True)

    assert result["context_id"] == "new-context"
    assert calls[0] == "Target.disposeBrowserContext"
    assert calls[-2:] == ["Target.createBrowserContext", "Target.createTarget"]
    assert "provisioning" not in json.loads(leases_file.read_text())["task"]


def test_new_reservation_exposes_deadline_while_provisioning(monkeypatch, tmp_path):
    module = load_module()
    leases_file = tmp_path / "leases.json"
    monkeypatch.setenv("CLOAK_CONTEXT_LEASES_FILE", str(leases_file))
    observed = {}

    async def create_and_inspect(pairs, timeout=None):
        if pairs == [("Target.createBrowserContext", {})]:
            observed.update(module._leases()["task"])
            return [{"browserContextId": "context"}]
        return [{}, {"targetId": "target"}]

    monkeypatch.setattr(module, "_calls", create_and_inspect)
    module.acquire("task", no_seed=True)

    assert observed["provisioning_deadline"] > observed["provisioning_started_at"]
    assert module._provisioning_expired(
        observed, observed["provisioning_deadline"] - 1
    ) is False
    assert module._provisioning_expired(
        observed, observed["provisioning_deadline"]
    ) is True


def test_requested_stale_task_is_prioritized_over_batch_limit(monkeypatch, tmp_path):
    module = load_module()
    leases_file = tmp_path / "leases.json"
    monkeypatch.setenv("CLOAK_CONTEXT_LEASES_FILE", str(leases_file))
    leases = {
        f"stale-{index}": {
            "context_id": f"old-context-{index}",
            "target_id": f"old-target-{index}",
            "token": "a" * 32,
            "generation": 1,
            "pid": -1,
            "ts": 0,
        }
        for index in range(9)
    }
    leases["requested"] = {
        "provisioning": True,
        "provisioning_deadline": 0,
        "context_id": "requested-old-context",
        "target_id": "requested-old-target",
        "token": "r" * 32,
        "generation": 1,
        "pid": -1,
        "ts": 0,
    }
    leases_file.write_text(json.dumps(leases), encoding="utf-8")
    calls = []

    async def dispose_then_create(pairs, timeout=None):
        output = []
        for method, params in pairs:
            calls.append((method, params))
            if method == "Target.disposeBrowserContext":
                output.append({})
            elif method == "Target.createBrowserContext":
                output.append({"browserContextId": "fresh-context"})
            elif method == "Target.createTarget":
                output.append({"targetId": "fresh-target"})
        return output

    monkeypatch.setattr(module, "_calls", dispose_then_create)
    result = module.acquire("requested", no_seed=True)

    assert result["context_id"] == "fresh-context"
    assert calls[0] == (
        "Target.disposeBrowserContext",
        {"browserContextId": "requested-old-context"},
    )


def test_unexpired_live_provisioning_is_not_reclaimed(monkeypatch, tmp_path):
    module = load_module()
    leases_file = tmp_path / "leases.json"
    monkeypatch.setenv("CLOAK_CONTEXT_LEASES_FILE", str(leases_file))
    row = {
        "provisioning": True,
        "provisioning_started_at": time.time(),
        "provisioning_deadline": time.time() + 300,
        "context_id": "context",
        "target_id": "target",
        "token": "a" * 32,
        "generation": 1,
        "pid": os.getpid(),
        "ts": int(time.time()),
    }
    leases_file.write_text(json.dumps({"task": row}), encoding="utf-8")
    monkeypatch.setattr(module, "gc", lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("live provisioning must not trigger GC")
    ))

    try:
        module.acquire("task", no_seed=True)
    except RuntimeError as error:
        assert str(error) == "lease_busy"
    else:
        raise AssertionError("live provisioning was reclaimed")
    assert module._leases()["task"]["context_id"] == "context"
