"""Context provisioning must not hold the shared lease-ledger lock."""
import fcntl
import importlib.util
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
    monkeypatch.setenv("CLOAK_CONTEXT_LEASES_FILE", str(leases_file))

    async def create_while_proving_lock_is_free(pairs, timeout=None):
        with open(str(leases_file) + ".lock", "a+") as handle:
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
