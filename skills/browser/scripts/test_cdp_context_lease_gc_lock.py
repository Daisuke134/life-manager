"""gc() must never clobber a live lease write with its own stale snapshot.

Root cause (spec Sec-EO, docs/loop-engineering/26-gig-loop-asis-tobe-plan.md): gc() used
to read the whole ledger unlocked, run slow real-CDP dispose calls, then unconditionally
`_save(leases)` -- overwriting the shared leases.json with its stale start-of-call
snapshot. Any heartbeat()/acquire() write that landed during gc's dispose loop got
silently erased, and the victim's next heartbeat returned lease_not_found. Measured 149
occurrences / 6 days in production.

The fix: read candidates under the ledger lock, dispose outside it (so slow CDP calls
never block other callers), then re-open the lock per row and only pop it if the ledger
still shows the *same* lease (matching context_id/target_id) and it is *still* stale.
These tests pin the three outcomes that matter.
"""
from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path


def load_module():
    path = Path(__file__).resolve().parent / "cdp_context_lease.py"
    spec = importlib.util.spec_from_file_location("cdp_context_lease_gc_lock", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_leases(leases_file, leases):
    leases_file.write_text(json.dumps(leases), encoding="utf-8")


def test_gc_does_not_clobber_a_concurrent_heartbeat_write(monkeypatch, tmp_path):
    module = load_module()
    leases_file = tmp_path / "leases.json"
    monkeypatch.setenv("CLOAK_CONTEXT_LEASES_FILE", str(leases_file))
    stale_ts = int(time.time()) - 3600
    _write_leases(leases_file, {
        "gig-task": {
            "context_id": "c1", "target_id": "t1",
            "ws": "ws://127.0.0.1:9222/devtools/page/t1",
            "ts": stale_ts, "token": "a" * 32, "generation": 1,
        }
    })

    async def dispose_then_race(pairs, timeout=None):
        # gc holds the lock only for the read and the per-row finalize; dispose (this
        # call) happens outside it. A concurrent heartbeat lands right here.
        module.heartbeat("gig-task", token="a" * 32, generation=1)
        return [{}]

    monkeypatch.setattr(module, "_calls", dispose_then_race)
    result = module.gc(idle_min=45)

    assert "gig-task" not in result["reaped"]
    saved = json.loads(leases_file.read_text(encoding="utf-8"))
    assert saved["gig-task"]["context_id"] == "c1"


def test_gc_removes_a_row_that_is_still_stale(monkeypatch, tmp_path):
    module = load_module()
    leases_file = tmp_path / "leases.json"
    monkeypatch.setenv("CLOAK_CONTEXT_LEASES_FILE", str(leases_file))
    stale_ts = int(time.time()) - 3600
    _write_leases(leases_file, {
        "gig-task": {
            "context_id": "c1", "target_id": "t1",
            "ws": "ws://127.0.0.1:9222/devtools/page/t1",
            "ts": stale_ts, "token": "a" * 32, "generation": 1,
        }
    })

    async def dispose_ok(pairs, timeout=None):
        return [{}]

    monkeypatch.setattr(module, "_calls", dispose_ok)
    result = module.gc(idle_min=45)

    assert result["reaped"] == ["gig-task"]
    assert json.loads(leases_file.read_text(encoding="utf-8")) == {}


def test_gc_does_not_remove_a_row_reacquired_with_a_new_identity(monkeypatch, tmp_path):
    module = load_module()
    leases_file = tmp_path / "leases.json"
    monkeypatch.setenv("CLOAK_CONTEXT_LEASES_FILE", str(leases_file))
    stale_ts = int(time.time()) - 3600
    _write_leases(leases_file, {
        "gig-task": {
            "context_id": "old-context", "target_id": "old-target",
            "ws": "ws://127.0.0.1:9222/devtools/page/old-target",
            "ts": stale_ts, "token": "a" * 32, "generation": 1,
        }
    })

    async def dispose_then_reacquire(pairs, timeout=None):
        # The old context really did get disposed here -- then the same task id won a
        # brand new lease (different context_id/target_id) before gc's finalize step.
        # Keep its ts old too, so this pins that gc checks identity, not just staleness.
        leases = module._leases()
        leases["gig-task"] = {
            "context_id": "new-context", "target_id": "new-target",
            "ws": "ws://127.0.0.1:9222/devtools/page/new-target",
            "ts": stale_ts, "token": "b" * 32, "generation": 1,
        }
        module._save(leases)
        return [{}]

    monkeypatch.setattr(module, "_calls", dispose_then_reacquire)
    result = module.gc(idle_min=45)

    assert "gig-task" not in result["reaped"]
    saved = json.loads(leases_file.read_text(encoding="utf-8"))
    assert saved["gig-task"]["context_id"] == "new-context"


def test_gc_does_not_remove_a_new_provisioning_reservation(monkeypatch, tmp_path):
    module = load_module()
    leases_file = tmp_path / "leases.json"
    monkeypatch.setenv("CLOAK_CONTEXT_LEASES_FILE", str(leases_file))
    stale_ts = int(time.time()) - 3600
    _write_leases(leases_file, {
        "gig-task": {
            "provisioning": True, "context_id": None, "target_id": None,
            "ts": stale_ts, "token": "a" * 32, "generation": 1, "pid": None,
        }
    })

    async def dispose_then_rereserve(_pairs, timeout=None):
        leases = module._leases()
        leases["gig-task"] = {
            "provisioning": True, "context_id": None, "target_id": None,
            "ts": stale_ts, "token": "b" * 32, "generation": 1, "pid": None,
        }
        module._save(leases)
        return [{}]

    monkeypatch.setattr(module, "_calls", dispose_then_rereserve)

    result = module.gc(idle_min=0)

    assert "gig-task" not in result["reaped"]
    assert module._leases()["gig-task"]["token"] == "b" * 32


def test_heartbeat_lease_not_found_reason_carries_ledger_mtime(monkeypatch, tmp_path):
    # The reason string is the only channel that reaches real logs: LeaseHandle raises
    # lease_command_failed:{reason} and discards stderr. Pin that the diagnostic rides it.
    module = load_module()
    leases_file = tmp_path / "leases.json"
    monkeypatch.setenv("CLOAK_CONTEXT_LEASES_FILE", str(leases_file))
    _write_leases(leases_file, {})

    result = module.heartbeat("gig-task", token="a" * 32, generation=1)

    assert result["ok"] is False
    assert result["reason"].startswith("lease_not_found")
    assert "ledger_mtime=" in result["reason"]
