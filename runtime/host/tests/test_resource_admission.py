import os
import fcntl
import hashlib
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


def test_unknown_future_ticket_is_preserved_and_ignored(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    digest = hashlib.sha256(b"next").hexdigest()
    future = tmp_path / f"tickets/deterministic-00000000000000000001-{digest}.json"
    admission.atomic_json(future, {
        "version": 2, "owner_id": "future", "sequence": 1,
    })
    claim, reason = admission.try_acquire(
        "deterministic", "next", retain_ticket=False)
    assert claim and reason == "acquired" and future.exists()
    admission.release(claim)

    claim, reason = admission.try_acquire("deterministic", "next")
    assert claim and reason == "acquired" and future.exists()
    admission.release(claim)


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


def test_admission_does_not_enumerate_the_process_table(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    with patch.object(
        admission, "process_starts", side_effect=AssertionError("fleet ps probe")
    ):
        claim, reason = admission.try_acquire("deterministic", "one-shot")
    assert claim is not None and reason == "acquired"
    admission.release(claim)


def test_darwin_process_identity_is_native_and_stable():
    if admission.sys.platform != "darwin":
        return
    expected = admission.subprocess.check_output(
        ["/bin/ps", "-p", str(os.getpid()), "-o", "lstart="], text=True
    ).strip()
    with patch.object(admission.subprocess, "run",
                      side_effect=AssertionError("ps subprocess")):
        first = admission.process_start(os.getpid())
        second = admission.process_start(os.getpid())
    assert first and first == second == expected


def test_native_identity_cache_avoids_per_record_probes(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total="2")
    started = admission.process_start(os.getpid())
    for index in range(100):
        admission.atomic_json(
            tmp_path / f"tickets/agent-{index:020d}-live-{index}.json",
            {"pid": os.getpid(), "process_start": started},
        )
    with patch.object(admission, "process_starts",
                      side_effect=AssertionError("fleet ps probe")):
        with patch.object(admission, "process_start", return_value=started) as probe:
            claim, reason = admission.try_acquire("agent", "new")
    assert claim is None and reason == "fifo_wait"
    assert probe.call_count == 1


def test_native_identity_probe_is_cached_by_pid(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total="2")
    started = admission.process_start(os.getpid())
    for index in range(25):
        admission.atomic_json(
            tmp_path / f"tickets/agent-{index:020d}-live-{index}.json",
            {"pid": os.getpid(), "process_start": started},
        )
    with patch.object(admission, "process_starts",
                      side_effect=AssertionError("fleet ps probe")):
        with patch.object(admission, "process_start", return_value=started) as probe:
            claim, reason = admission.try_acquire("agent", "new")
    assert claim is None and reason == "fifo_wait"
    assert probe.call_count == 1


def test_row_created_during_native_self_probe_is_kept_live(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    owner = tmp_path / "owners/new-owner.json"
    actual_start = admission.process_start(os.getpid())

    def self_probe(_pid):
        admission.atomic_json(
            owner,
            {"pid": os.getpid(), "process_start": actual_start,
             "owner_id": "new-owner", "resource_class": "deterministic"},
        )
        return actual_start

    with patch.object(admission, "process_start", side_effect=self_probe):
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
