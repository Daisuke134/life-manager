import pytest


@pytest.fixture(autouse=True)
def _no_swap_pressure(monkeypatch, tmp_path_factory):
    """Host swap is a real signal on the developer Mac; keep every admission test deterministic,
    in-process (patched probe) and in the lm_loop_run subprocesses some tests spawn (env)."""
    monkeypatch.setattr("runtime.loop.lm_loop_run.swap_used_mb", lambda: 0.0, raising=False)
    monkeypatch.setenv("LIFE_MANAGER_MAX_SWAP_PERCENT_OF_RAM", "1000")
    # the plateau history must not read the developer Mac's real samples
    monkeypatch.setenv("LIFE_MANAGER_SWAP_SAMPLES", str(tmp_path_factory.mktemp("swap") / "swap.json"))
