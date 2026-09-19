"""Context provisioning must not hold the shared lease-ledger lock."""
import fcntl
import importlib.util
import threading
import time
from pathlib import Path


def load_module():
    path = Path(__file__).resolve().parent / "cdp_context_lease.py"
    spec = importlib.util.spec_from_file_location("cdp_context_lease_acquire_lock", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_acquire_releases_ledger_lock_before_browser_provisioning(monkeypatch, tmp_path):
    module = load_module()
    leases_file = tmp_path / "leases.json"
    vault_file = tmp_path / "vault.json"
    monkeypatch.setenv("CLOAK_CONTEXT_LEASES_FILE", str(leases_file))
    monkeypatch.setenv("CLOAK_SESSION_VAULT_FILE", str(vault_file))
    monkeypatch.setenv("CLOAK_SESSION_VAULT_WRITEBACK_FILE", str(vault_file))

    async def create_while_proving_lock_is_free(pairs, timeout=None):
        for lock_path in (str(leases_file) + ".lock", str(vault_file) + ".lock"):
            with open(lock_path, "a+") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        output = []
        for method, _params in pairs:
            if method == "Target.createBrowserContext":
                output.append({"browserContextId": "context-1"})
            elif method == "Target.createTarget":
                output.append({"targetId": "target-1"})
            else:
                output.append({})
        return output

    monkeypatch.setattr(module, "_calls", create_while_proving_lock_is_free)

    result = module.acquire("client-1", no_seed=True)

    assert result["context_id"] == "context-1"
    assert module._leases()["client-1"].get("provisioning") is None


def test_acquire_records_context_before_cookie_seeding(monkeypatch, tmp_path):
    module = load_module()
    leases_file = tmp_path / "leases.json"
    vault_file = tmp_path / "vault.json"
    vault_file.write_text('{"cookies":[{"name":"session","value":"x","domain":"example.com"}]}')
    monkeypatch.setenv("CLOAK_CONTEXT_LEASES_FILE", str(leases_file))
    monkeypatch.setenv("CLOAK_SESSION_VAULT_FILE", str(vault_file))
    calls = 0

    async def create_then_seed(pairs, timeout=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            return [{"browserContextId": "context-1"}]
        reserved = module._leases()["client-1"]
        assert reserved["provisioning"] is True
        assert reserved["context_id"] == "context-1"
        return [{}, {"targetId": "target-1"}]

    monkeypatch.setattr(module, "_calls", create_then_seed)

    assert module.acquire("client-1")["target_id"] == "target-1"


def test_context_only_acquire_does_not_create_a_seed_target(monkeypatch, tmp_path):
    module = load_module()
    leases_file = tmp_path / "leases.json"
    monkeypatch.setenv("CLOAK_CONTEXT_LEASES_FILE", str(leases_file))
    calls = []

    async def create_context_only(pairs, timeout=None):
        calls.extend(method for method, _params in pairs)
        return [{"browserContextId": "context-only"}]

    monkeypatch.setattr(module, "_calls", create_context_only)

    result = module.acquire("client-1", no_seed=True, create_target=False)

    assert result["context_id"] == "context-only"
    assert result["target_id"] is None
    assert result["ws"] is None
    assert result["context_only"] is True
    assert calls == ["Target.createBrowserContext"]


def test_seed_and_dispose_failure_keeps_cleanup_tombstone(monkeypatch, tmp_path):
    module = load_module()
    leases_file = tmp_path / "leases.json"
    vault_file = tmp_path / "vault.json"
    vault_file.write_text('{"cookies":[{"name":"session","value":"x","domain":"example.com"}]}')
    monkeypatch.setenv("CLOAK_CONTEXT_LEASES_FILE", str(leases_file))
    monkeypatch.setenv("CLOAK_SESSION_VAULT_FILE", str(vault_file))
    calls = 0

    async def fail_seed_and_dispose(pairs, timeout=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            return [{"browserContextId": "context-1"}]
        raise TimeoutError("browser unavailable")

    monkeypatch.setattr(module, "_calls", fail_seed_and_dispose)
    monkeypatch.setattr(module, "_browser_context_exists", lambda _context: True)

    try:
        module.acquire("client-1")
    except TimeoutError:
        pass
    else:
        raise AssertionError("seed failure must escape")

    saved = module._leases()["client-1"]
    assert saved["context_id"] == "context-1"
    assert saved["cleanup_pending"] is True
    assert saved.get("provisioning") is None


def test_release_cannot_dispose_context_after_same_task_reacquires(monkeypatch, tmp_path):
    module = load_module()
    leases_file = tmp_path / "leases.json"
    monkeypatch.setenv("CLOAK_CONTEXT_LEASES_FILE", str(leases_file))
    module._save({"client-1": {
        "token": "old", "generation": 1, "context_id": "context-1",
        "target_id": "target-1", "ws": "ws://target-1", "parked": True,
        "pid": None, "ts": 1,
    }})
    dispose_started = threading.Event()
    allow_dispose = threading.Event()

    async def slow_dispose(pairs, timeout=None):
        method = pairs[0][0]
        if method == "Target.disposeBrowserContext":
            dispose_started.set()
            assert allow_dispose.wait(2)
            return [{}]
        if method == "Target.createBrowserContext":
            return [{"browserContextId": "context-2"}]
        if method == "Target.createTarget":
            return [{"targetId": "target-2"}]
        return [{} for _pair in pairs]

    monkeypatch.setattr(module, "_calls", slow_dispose)
    monkeypatch.setattr(module, "_seed_material", lambda *_args: ([], {}, None))
    monkeypatch.setattr(module, "target_responds", lambda _ws: True)

    release_result = {}
    acquire_result = {}
    release_thread = threading.Thread(
        target=lambda: release_result.update(module.release("client-1", "old", 1))
    )
    release_thread.start()
    assert dispose_started.wait(2)
    acquire_thread = threading.Thread(
        target=lambda: acquire_result.update(module.acquire("client-1", no_seed=True))
    )
    acquire_thread.start()
    time.sleep(0.05)
    assert acquire_thread.is_alive(), "same-task acquire must wait for release disposal"
    allow_dispose.set()
    release_thread.join(2)
    acquire_thread.join(2)

    assert release_result["released"] == "client-1"
    assert acquire_result["context_id"] != "context-1"
