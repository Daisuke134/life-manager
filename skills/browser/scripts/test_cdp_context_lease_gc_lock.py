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
import contextlib
import threading
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
        heartbeat = module.heartbeat("gig-task", token="a" * 32, generation=1)
        assert heartbeat == {"ok": False, "reason": "context_cleanup_pending"}
        return [{}]

    monkeypatch.setattr(module, "_calls", dispose_then_race)
    result = module.gc(idle_min=45)

    assert "gig-task" in result["reaped"]
    assert "gig-task" not in module._leases()


def test_gc_claim_prevents_acquire_from_returning_context_being_disposed(monkeypatch, tmp_path):
    module = load_module()
    leases_file = tmp_path / "leases.json"
    monkeypatch.setenv("CLOAK_CONTEXT_LEASES_FILE", str(leases_file))
    _write_leases(leases_file, {"gig-task": {
        "context_id": "old-context", "target_id": "old-target",
        "ws": "ws://old-target", "ts": 0, "pid": 99999999,
        "token": "a" * 32, "generation": 1,
    }})
    dispose_started = threading.Event()
    allow_dispose = threading.Event()

    async def dispose_then_create(pairs, timeout=None):
        method = pairs[0][0]
        if method == "Target.disposeBrowserContext":
            dispose_started.set()
            assert allow_dispose.wait(2)
            return [{}]
        if method == "Target.createBrowserContext":
            return [{"browserContextId": "new-context"}]
        if method == "Target.createTarget":
            return [{"targetId": "new-target"}]
        return [{} for _pair in pairs]

    monkeypatch.setattr(module, "_calls", dispose_then_create)
    monkeypatch.setattr(module, "_seed_material", lambda *_args: ([], {}, None))
    gc_thread = threading.Thread(target=lambda: module.gc(idle_min=45))
    gc_thread.start()
    assert dispose_started.wait(2)
    assert module._leases()["gig-task"]["cleanup_pending"] is True

    acquired = {}
    acquire_thread = threading.Thread(
        target=lambda: acquired.update(module.acquire("gig-task", no_seed=True))
    )
    acquire_thread.start()
    time.sleep(0.05)
    assert acquire_thread.is_alive()
    allow_dispose.set()
    gc_thread.join(2)
    acquire_thread.join(2)

    assert acquired["context_id"] == "new-context"
    assert acquired["context_id"] != "old-context"


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


def test_gc_returns_immediately_when_another_reaper_owns_singleflight(monkeypatch):
    module = load_module()

    @contextlib.contextmanager
    def busy():
        yield False

    monkeypatch.setattr(module, "_gc_singleflight", busy)
    monkeypatch.setattr(module, "_gc_owned", lambda _idle: (_ for _ in ()).throw(
        AssertionError("busy gc must not inspect or mutate the ledger")
    ))

    result = module.gc(idle_min=45)

    assert result["ok"] is True
    assert result["skipped"] == "gc_already_running"


def test_acquire_reaps_only_one_stale_row_at_capacity(monkeypatch, tmp_path):
    module = load_module()
    leases_file = tmp_path / "leases.json"
    monkeypatch.setenv("CLOAK_CONTEXT_LEASES_FILE", str(leases_file))
    monkeypatch.setenv("CLOAK_BROWSER_MAX_CONTEXTS", "2")
    _write_leases(leases_file, {
        "dead-a": {"context_id": "c1", "target_id": "t1", "ts": 0, "pid": -1},
        "dead-b": {"context_id": "c2", "target_id": "t2", "ts": 0, "pid": -1},
    })
    calls = []

    def fake_gc(idle_min=45, max_reaps=None, priority_task=None):
        calls.append((idle_min, max_reaps, priority_task))
        leases = module._leases()
        leases.pop("dead-a")
        module._save(leases)
        return {"ok": True, "reaped": ["dead-a"]}

    monkeypatch.setattr(module, "gc", fake_gc)

    module._recover_capacity_if_needed("new-task")

    assert calls == [(45, 8, "new-task")]
    assert list(module._leases()) == ["dead-b"]


def test_existing_task_reuse_never_waits_for_capacity_gc(monkeypatch, tmp_path):
    module = load_module()
    leases_file = tmp_path / "leases.json"
    monkeypatch.setenv("CLOAK_CONTEXT_LEASES_FILE", str(leases_file))
    monkeypatch.setenv("CLOAK_BROWSER_MAX_CONTEXTS", "1")
    _write_leases(leases_file, {
        "same-task": {"context_id": "c1", "target_id": "t1", "ts": 0, "pid": 1},
    })
    monkeypatch.setattr(module, "gc", lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("reuse does not need a new slot")
    ))

    module._recover_capacity_if_needed("same-task", wait_seconds=0)


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
