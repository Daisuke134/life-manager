import pytest


@pytest.fixture(autouse=True)
def _no_swap_pressure(monkeypatch, tmp_path_factory):
    """Host swap is a real signal on the developer Mac; keep every admission test deterministic,
    in-process (patched probe) and in the lm_loop_run subprocesses some tests spawn (env)."""
    monkeypatch.setattr("runtime.host.memory_admission.swapin_pages_per_second", lambda: 0.0)
    monkeypatch.setenv("LIFE_MANAGER_SWAPIN_GATE", "off")  # subprocesses have no swap-in history
    monkeypatch.setenv("LIFE_MANAGER_SWAP_SAMPLES", str(tmp_path_factory.mktemp("swap") / "swap.json"))
    # Release GC tests must not append receipts to the real host's release-gc.jsonl.
    monkeypatch.setenv("LIFE_MANAGER_RELEASE_GC_LOG", str(tmp_path_factory.mktemp("gc") / "release-gc.jsonl"))
