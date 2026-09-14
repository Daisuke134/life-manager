import os
import fcntl
import json
import time
from unittest.mock import patch

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


def test_one_shot_busy_attempt_does_not_leave_a_ticket(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    first, _ = admission.try_acquire("deterministic", "first")
    blocked, reason = admission.try_acquire(
        "deterministic", "second", retain_ticket=False)
    assert blocked is None and reason == "capacity_busy"
    assert not list((tmp_path / "tickets").glob("*.json"))
    admission.release(first)


def test_one_shot_control_lock_contention_returns_immediately(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    tmp_path.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(tmp_path / "control.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        started = time.monotonic()
        with patch.object(admission, "process_starts",
                          side_effect=AssertionError("probe ran while lock busy")):
            claim, reason = admission.try_acquire(
                "agent", "one-shot", retain_ticket=False)
        assert claim is None and reason == "control_busy"
        assert time.monotonic() - started < 0.5
    finally:
        os.close(descriptor)


def test_process_snapshot_runs_once_outside_control_lock(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    observed = []

    def snapshot():
        descriptor = os.open(tmp_path / "control.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            observed.append("outside")
        finally:
            os.close(descriptor)
        return {os.getpid(): admission.process_start(os.getpid())}

    with patch.object(admission, "process_starts", side_effect=snapshot) as probe:
        claim, reason = admission.try_acquire("deterministic", "one-shot")
    assert claim is not None and reason == "acquired"
    assert observed == ["outside"] and probe.call_count == 1
    admission.release(claim)


def test_snapshot_avoids_per_record_identity_processes(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total="2")
    started = admission.process_start(os.getpid())
    for index in range(100):
        admission.atomic_json(
            tmp_path / f"tickets/agent-{index:020d}-live-{index}.json",
            {"pid": os.getpid(), "process_start": started},
        )
    with patch.object(admission, "process_starts",
                      return_value={os.getpid(): started}) as snapshot:
        with patch.object(admission, "process_start",
                          side_effect=AssertionError("per-record probe")):
            claim, reason = admission.try_acquire("agent", "new")
    assert claim is None and reason == "fifo_wait"
    assert snapshot.call_count == 1


def test_failed_snapshot_never_falls_back_to_per_record_processes(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total="2")
    started = admission.process_start(os.getpid())
    for index in range(25):
        admission.atomic_json(
            tmp_path / f"tickets/agent-{index:020d}-live-{index}.json",
            {"pid": os.getpid(), "process_start": started},
        )
    with patch.object(admission, "process_starts", return_value=None):
        with patch.object(admission, "process_start", return_value=started) as probe:
            claim, reason = admission.try_acquire("agent", "new")
    assert claim is None and reason == "fifo_wait"
    assert probe.call_count == 1


def test_row_created_during_snapshot_is_kept_live(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    owner = tmp_path / "owners/new-owner.json"
    actual_start = admission.process_start(os.getpid())

    def stale_snapshot():
        admission.atomic_json(
            owner,
            {"pid": os.getpid(), "process_start": actual_start,
             "owner_id": "new-owner", "resource_class": "deterministic"},
        )
        return {os.getpid(): "stale snapshot identity"}

    with patch.object(admission, "process_starts", side_effect=stale_snapshot):
        claim, reason = admission.try_acquire("deterministic", "next")
    assert claim is None and reason == "capacity_busy"
    assert owner.exists()


def test_one_shot_never_overwrites_or_removes_live_fifo_ticket(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total="2")
    ticket = tmp_path / "tickets/agent-00000000000000000001-existing.json"
    original = {"version": 1, "pid": os.getpid(),
                "process_start": admission.process_start(os.getpid()),
                "owner_id": "same-owner"}
    admission.atomic_json(ticket, original)
    claim, reason = admission.try_acquire(
        "agent", "same-owner", retain_ticket=False)
    assert claim is None and reason == "fifo_wait"
    assert json.loads(ticket.read_text()) == original


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


def test_unavailable_identity_probe_keeps_existing_pid_live(tmp_path):
    owner = tmp_path / "owner.json"
    admission.atomic_json(owner, {"pid": os.getpid(), "process_start": "expected"})
    with patch.object(admission, "process_start", return_value=None):
        assert admission._live(owner) is True


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
