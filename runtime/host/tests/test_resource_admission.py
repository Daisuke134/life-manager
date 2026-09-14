import os

from runtime.host import resource_admission as admission


def isolated(tmp_path, monkeypatch, total="1"):
    monkeypatch.setenv("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", str(tmp_path))
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_FINITE_RUNS", total)


def test_slot_releases_for_next_owner(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    first, reason = admission.try_acquire("deterministic", "first")
    assert first is not None and reason == "acquired"
    second, reason = admission.try_acquire("deterministic", "second")
    assert second is None and reason == "capacity_busy"
    admission.release(first)
    second, reason = admission.try_acquire("deterministic", "second")
    assert second is not None and reason == "acquired"
    admission.release(second)


def test_agent_limit_does_not_block_deterministic_class(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total="2")
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_AGENT_RUNS", "1")
    agent, _ = admission.try_acquire("agent", "agent-one")
    blocked, reason = admission.try_acquire("agent", "agent-two")
    other, _ = admission.try_acquire("deterministic", "deterministic-one")
    assert agent and blocked is None and reason == "capacity_busy" and other
    admission.release(agent); admission.release(other)


def test_live_waiters_are_fifo_and_dead_ticket_does_not_block(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total="2")
    started = admission.process_start(os.getpid())
    old = tmp_path / "tickets/deterministic-00000000000000000001-old.json"
    admission.atomic_json(old, {"pid": os.getpid(), "process_start": started})
    newer, reason = admission.try_acquire("deterministic", "new")
    assert newer is None and reason == "fifo_wait"
    admission.atomic_json(old, {"pid": 999_999_999, "process_start": "dead"})
    newer, reason = admission.try_acquire("deterministic", "new")
    assert newer is not None and reason == "acquired"
    admission.release(newer)


def test_stale_owner_is_reclaimed(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    stale = tmp_path / "owners/stale.json"
    admission.atomic_json(stale, {"pid": 999_999_999, "process_start": "dead"})
    claim, reason = admission.try_acquire("deterministic", "next")
    assert claim is not None and reason == "acquired" and not stale.exists()
    admission.release(claim)


def test_cancel_after_claim_releases_slot(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    calls = iter((False, True))
    try:
        admission.acquire("deterministic", "cancelled", lambda: next(calls))
    except InterruptedError:
        pass
    else:
        raise AssertionError("cancelled admission returned a claim")
    claim, reason = admission.try_acquire("deterministic", "next")
    assert claim is not None and reason == "acquired"
    admission.release(claim)
