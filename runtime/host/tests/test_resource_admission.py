import os
import fcntl
import hashlib
import json
import multiprocessing
import time
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from runtime.host import resource_admission as admission


def isolated(tmp_path, monkeypatch, total="1"):
    monkeypatch.setenv("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", str(tmp_path))
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_FINITE_RUNS", total)
    # Unit tests below exercise raw slot semantics unless a floor is explicit.
    monkeypatch.setenv("LIFE_MANAGER_HOST_MIN_REVENUE_RUNS", "0")


def durable_rows(root, table):
    with sqlite3.connect(root / "admission-v2.sqlite3") as connection:
        columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
        return [dict(zip(columns, row)) for row in connection.execute(f"SELECT * FROM {table}")]


def enqueue_after_barrier(root, index, barrier, results):
    os.environ["LIFE_MANAGER_RESOURCE_ADMISSION_ROOT"] = str(root)
    os.environ["LIFE_MANAGER_HOST_MAX_FINITE_RUNS"] = "3"
    os.environ["LIFE_MANAGER_HOST_MAX_AGENT_RUNS"] = "1"
    os.environ["LIFE_MANAGER_HOST_MAX_DETERMINISTIC_RUNS"] = "2"
    barrier.wait(timeout=10)
    ticket, reason = admission.enqueue_durable("agent", f"loop-{index:03d}")
    results.put((ticket is not None, reason))


def hold_control_lock(path, ready):
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        ready.set()
        time.sleep(2)
    finally:
        os.close(descriptor)


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


def test_durable_protocol_defaults_v1_and_activates_only_when_idle(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    assert admission.durable_protocol_version() == 1
    claim, reason = admission.try_acquire("agent", "legacy", retain_ticket=False)
    assert claim is not None and reason == "acquired"

    with pytest.raises(RuntimeError, match="legacy admission is not idle"):
        admission.activate_durable_v2()

    admission.release(claim)
    admission.activate_durable_v2()
    assert admission.durable_protocol_version() == 2


def test_preflighted_v2_activation_preserves_live_v1_owner(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    claim, reason = admission.try_acquire(
        "agent", "legacy-live", retain_ticket=False)
    assert claim is not None and reason == "acquired"

    admission.activate_durable_v2(allow_live_owners=True)

    assert admission.durable_protocol_version() == 2
    assert claim.exists()
    admission.release(claim)


def test_durable_protocol_activation_is_replay_safe_after_queue_starts(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    admission.activate_durable_v2()
    admission.enqueue_durable("agent", "queued")

    admission.activate_durable_v2()

    assert admission.durable_protocol_version() == 2
    assert [row["owner_id"] for row in durable_rows(tmp_path, "queue")] == ["queued"]


def test_durable_protocol_activation_removes_malformed_legacy_ticket(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    ticket = tmp_path / "tickets/agent-broken.json"
    ticket.parent.mkdir(parents=True)
    ticket.write_text("{")

    admission.activate_durable_v2()

    assert admission.durable_protocol_version() == 2
    assert not ticket.exists()


def test_durable_protocol_activation_preserves_unknown_future_ticket(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    ticket = tmp_path / "tickets/agent-future.json"
    admission.atomic_json(ticket, {
        "version": 3, "owner_id": "future", "resource_class": "agent",
    })

    with pytest.raises(RuntimeError, match="legacy admission is not idle"):
        admission.activate_durable_v2()

    assert ticket.exists()
    assert admission.durable_protocol_version() == 1


def test_v2_reservation_blocks_compatibility_v1_claim(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    admission.activate_durable_v2()
    admission.enqueue_durable("agent", "v2-first")
    instant = time.time()
    assert admission.reserve_available(
        now=instant, lease_seconds=30,
    ) == ["v2-first"]

    legacy, reason = admission.try_acquire(
        "agent", "v1-later", retain_ticket=False,
    )

    assert legacy is None and reason == "capacity_busy"
    claim, reason = admission.claim_durable("agent", "v2-first", now=instant + 1)
    assert claim is not None and reason == "acquired"


def test_v1_claim_refuses_protocol_flip_inside_control_lock(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    admission.activate_durable_v2()

    claim, reason = admission.try_acquire(
        "agent", "late-v1", retain_ticket=False, required_protocol=1,
    )

    assert claim is None and reason == "protocol_changed"
    assert not list((tmp_path / "owners").glob("*.json"))


def test_reserved_v2_claim_refuses_unexpected_legacy_capacity_overlap(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    admission.activate_durable_v2()
    admission.enqueue_durable("agent", "v2-first")
    instant = time.time()
    assert admission.reserve_available(
        now=instant, lease_seconds=30,
    ) == ["v2-first"]
    admission.atomic_json(tmp_path / "owners/legacy.json", {
        "version": 1,
        "pid": os.getpid(),
        "process_start": admission.process_start(os.getpid()),
        "owner_id": "unexpected-legacy",
        "resource_class": "agent",
    })

    claim, reason = admission.claim_durable(
        "agent", "v2-first", now=instant + 1,
    )

    assert claim is None and reason == "capacity_busy"


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


def test_durable_waiter_survives_process_lifetime_and_is_reserved_fifo(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    first, _ = admission.try_acquire("agent", "first", retain_ticket=False)
    ticket, reason = admission.enqueue_durable("agent", "second")
    assert ticket is not None and reason == "capacity_busy"
    assert durable_rows(tmp_path, "queue") == [{
        "sequence": 1, "owner_id": "second", "resource_class": "agent",
    }]

    reserved = admission.release_and_reserve(first, now=100, lease_seconds=30)
    assert reserved == ["second"]
    reservation = durable_rows(tmp_path, "reservations")[0]
    assert reservation["sequence"] == 1 and reservation["lease_until"] == 130

    third, reason = admission.enqueue_durable("agent", "third", now=101)
    assert third is not None and reason == "capacity_busy"
    claim, reason = admission.claim_durable("agent", "second", now=102)
    assert claim is not None and reason == "acquired"
    assert durable_rows(tmp_path, "reservations") == []


def test_expired_reservation_returns_to_original_fifo_position(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    first, _ = admission.try_acquire("agent", "first", retain_ticket=False)
    admission.enqueue_durable("agent", "second")
    admission.enqueue_durable("agent", "third")
    admission.release_and_reserve(first, now=100, lease_seconds=10)

    claim, reason = admission.claim_durable("agent", "third", now=111)
    assert claim is None and reason == "fifo_wait"
    claim, reason = admission.claim_durable("agent", "second", now=111)
    assert claim is not None and reason == "acquired"


def test_post_claim_deferral_requeues_original_sequence(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    ticket, reason = admission.enqueue_durable("deterministic", "first")
    assert ticket is not None and reason == "ready"
    claim, reason = admission.claim_durable("deterministic", "first")
    assert claim is not None and reason == "acquired"
    admission.release_and_reserve(claim, requeue=True)
    assert durable_rows(tmp_path, "queue")[0]["sequence"] == 1


def test_post_claim_requeue_commits_before_claim_is_removed(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    admission.enqueue_durable("deterministic", "first")
    claim, reason = admission.claim_durable("deterministic", "first")
    assert claim is not None and reason == "acquired"
    observed = []
    original_unlink = Path.unlink

    def observe_committed_queue(path, *args, **kwargs):
        if path == claim:
            observed.extend(durable_rows(tmp_path, "queue"))
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", observe_committed_queue)
    admission.release_and_reserve(claim, requeue=True, reserve=False)

    assert observed == [{
        "sequence": 1, "owner_id": "first", "resource_class": "deterministic",
    }]


def test_release_already_reclaimed_claim_is_idempotent(tmp_path, monkeypatch):
    """A stale-owner sweep may win the race with the original finally block."""
    isolated(tmp_path, monkeypatch)
    admission.enqueue_durable("deterministic", "first")
    claim, reason = admission.claim_durable("deterministic", "first")
    assert claim is not None and reason == "acquired"
    claim.unlink()

    assert admission.release_and_reserve(claim, reserve=False) == []


def test_legacy_agent_waiter_does_not_starve_deterministic_queue(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total="2")
    started = admission.process_start(os.getpid())
    admission.atomic_json(tmp_path / "tickets" / "agent-00000000000000000001-old.json", {
        "version": 1, "pid": os.getpid(), "process_start": started,
        "owner_id": "old-agent",
    })
    ticket, reason = admission.enqueue_durable("deterministic", "new-deterministic")
    assert ticket is not None and reason == "ready"


def test_memory_defer_releases_only_its_reservation(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total="2")
    first, _ = admission.try_acquire("agent", "first", retain_ticket=False)
    admission.enqueue_durable("agent", "second")
    admission.enqueue_durable("deterministic", "other")
    reserved = admission.release_and_reserve(first, now=100, lease_seconds=30)
    assert set(reserved) == {"second", "other"}

    assert admission.defer_durable("second") is True
    rows = durable_rows(tmp_path, "reservations")
    assert [row["owner_id"] for row in rows] == ["other"]
    ticket, reason = admission.enqueue_durable("agent", "second", now=101)
    assert ticket is not None and reason == "ready"


def test_stale_owner_recovery_reserves_sleeping_fifo_head(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    admission.atomic_json(tmp_path / "owners" / "stale.json", {
        "version": 1, "pid": 999_999_999, "process_start": "dead",
        "owner_id": "stale", "resource_class": "agent",
    })
    admission.enqueue_durable("agent", "sleeping-head")
    admission.enqueue_durable("agent", "later-wake")
    assert admission.reserve_available(now=100, lease_seconds=30) == ["sleeping-head"]


def test_revenue_waiter_gets_released_slot_before_older_borrow_waiter(
        tmp_path, monkeypatch):
    """Maintenance may borrow idle capacity but cannot starve funded client work."""
    isolated(tmp_path, monkeypatch)
    admission.activate_durable_v2()
    admission.enqueue_durable("agent", "running-maintenance", admission_class="borrow")
    running, reason = admission.claim_durable(
        "agent", "running-maintenance", admission_class="borrow")
    assert running is not None and reason == "acquired"

    admission.enqueue_durable("agent", "older-maintenance", admission_class="borrow")
    admission.enqueue_durable("agent", "coconala-paid", admission_class="revenue")

    assert admission.release_and_reserve(
        running, now=100, lease_seconds=30) == ["coconala-paid"]


def test_aged_revenue_waiter_advances_during_continuous_paid_arrivals(
        tmp_path, monkeypatch):
    """Aged acquisition work receives service despite newer critical work."""
    isolated(tmp_path, monkeypatch, total="1")
    admission.activate_durable_v2()
    running, reason = admission.try_acquire(
        "agent", "paid-running", retain_ticket=False,
        admission_class="revenue")
    assert running is not None and reason == "acquired"

    admission.enqueue_durable(
        "agent", "connector-aged", admission_class="revenue",
        priority="revenue", now=0)
    for index in range(5):
        ticket, reason = admission.enqueue_durable(
            "agent", f"paid-new-{index}", admission_class="revenue",
            priority="critical_paid", now=1801 + index)
        assert ticket is not None and reason in {"capacity_busy", "fifo_wait"}

    reserved = admission.release_and_reserve(
        running, now=1801, lease_seconds=30)

    assert reserved == ["connector-aged"]


def test_explicit_occurrence_survives_owner_busy_and_reaches_terminal(
        tmp_path, monkeypatch):
    """A scheduled wake is durable even when the owner is already running."""
    isolated(tmp_path, monkeypatch, total="1")
    admission.activate_durable_v2()
    running, reason = admission.try_acquire(
        "agent", "connector-running", retain_ticket=False,
        admission_class="revenue")
    assert running is not None and reason == "acquired"

    ticket, reason = admission.enqueue_durable(
        "agent", "connector-running", admission_class="revenue",
        priority="revenue", occurrence_id="connector-wake-0001", now=100)
    assert ticket is not None and reason == "owner_busy"

    with sqlite3.connect(tmp_path / "admission-v2.sqlite3") as connection:
        occurrence = connection.execute(
            "SELECT occurrence_id,owner_id,state FROM occurrences"
        ).fetchone()
    assert occurrence == ("connector-wake-0001", "connector-running", "queued")

    admission.release(running)
    assert admission.reserve_available(now=101, lease_seconds=30) == [
        "connector-running"
    ]
    claim, reason = admission.claim_durable(
        "agent", "connector-running", admission_class="revenue", now=102)
    assert claim is not None and reason == "acquired"
    assert json.loads(claim.read_text())["occurrence_id"] == "connector-wake-0001"
    admission.release_and_reserve(claim, reserve=False)

    with sqlite3.connect(tmp_path / "admission-v2.sqlite3") as connection:
        assert connection.execute(
            "SELECT state FROM occurrences WHERE occurrence_id=?",
            ("connector-wake-0001",),
        ).fetchone() == ("released",)


def test_multiple_occurrences_drain_one_owner_queue_without_loss(
        tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total="1")
    admission.activate_durable_v2()
    running, reason = admission.try_acquire(
        "agent", "mobile-running", retain_ticket=False,
        admission_class="revenue")
    assert running is not None and reason == "acquired"
    for occurrence_id in ("mobile-wake-0001", "mobile-wake-0002"):
        ticket, reason = admission.enqueue_durable(
            "agent", "mobile-running", admission_class="revenue",
            priority="revenue", occurrence_id=occurrence_id, now=100)
        assert ticket is not None and reason == "owner_busy"

    admission.release(running)
    assert admission.reserve_available(now=101, lease_seconds=30) == [
        "mobile-running"
    ]
    first, reason = admission.claim_durable(
        "agent", "mobile-running", admission_class="revenue", now=102)
    assert first is not None and reason == "acquired"
    assert json.loads(first.read_text())["occurrence_id"] == "mobile-wake-0001"
    assert admission.release_and_reserve(first, now=103, lease_seconds=30) == [
        "mobile-running"
    ]

    second, reason = admission.claim_durable(
        "agent", "mobile-running", admission_class="revenue", now=104)
    assert second is not None and reason == "acquired"
    assert json.loads(second.read_text())["occurrence_id"] == "mobile-wake-0002"
    admission.release_and_reserve(second, reserve=False)

    with sqlite3.connect(tmp_path / "admission-v2.sqlite3") as connection:
        states = connection.execute(
            "SELECT occurrence_id,state FROM occurrences ORDER BY occurrence_id"
        ).fetchall()
    assert states == [
        ("mobile-wake-0001", "released"),
        ("mobile-wake-0002", "released"),
    ]


def test_revenue_priority_applies_across_resource_classes(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_AGENT_RUNS", "1")
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_DETERMINISTIC_RUNS", "1")
    admission.activate_durable_v2()
    admission.enqueue_durable("agent", "older-agent-maintenance")
    admission.enqueue_durable(
        "deterministic", "crowdworks-paid", admission_class="revenue")

    assert admission.reserve_available(now=100, lease_seconds=30) == [
        "crowdworks-paid"
    ]


def test_revenue_workers_share_host_capacity_beyond_borrow_agent_limit(
        tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total="3")
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_AGENT_RUNS", "1")
    admission.activate_durable_v2()

    claims = []
    for owner_id in ("coconala-apply", "coconala-reply", "coconala-paid"):
        ticket, _ = admission.enqueue_durable(
            "agent", owner_id, admission_class="revenue")
        assert ticket is not None
        claim, reason = admission.claim_durable(
            "agent", owner_id, admission_class="revenue")
        assert claim is not None and reason == "acquired"
        claims.append(claim)

    for claim in claims:
        admission.release_and_reserve(claim, reserve=False)


def test_default_host_capacity_allows_five_revenue_workers(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", str(tmp_path))
    monkeypatch.delenv("LIFE_MANAGER_HOST_MAX_FINITE_RUNS", raising=False)
    monkeypatch.delenv("LIFE_MANAGER_HOST_MAX_REVENUE_RUNS", raising=False)
    monkeypatch.delenv("LIFE_MANAGER_HOST_MIN_REVENUE_RUNS", raising=False)
    claims = []

    for index in range(5):
        claim, reason = admission.try_acquire(
            "agent", f"revenue-{index}", retain_ticket=False,
            admission_class="revenue",
        )
        assert claim is not None and reason == "acquired"
        claims.append(claim)

    blocked, reason = admission.try_acquire(
        "agent", "revenue-six", retain_ticket=False,
        admission_class="revenue",
    )
    assert blocked is None and reason == "capacity_busy"
    for claim in claims:
        admission.release(claim)


def test_revenue_floor_keeps_borrowers_from_consuming_reserved_headroom(
        tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total="5")
    monkeypatch.setenv("LIFE_MANAGER_HOST_MIN_REVENUE_RUNS", "4")
    admission.activate_durable_v2()

    borrow, reason = admission.try_acquire(
        "agent", "maintenance-one", retain_ticket=False,
        admission_class="borrow")
    assert borrow is not None and reason == "acquired"
    blocked_borrow, reason = admission.try_acquire(
        "deterministic", "maintenance-two", retain_ticket=False,
        admission_class="borrow")
    assert blocked_borrow is None and reason == "capacity_busy"

    revenue_claims = []
    for index in range(4):
        claim, reason = admission.try_acquire(
            "agent", f"revenue-reserved-{index}", retain_ticket=False,
            admission_class="revenue")
        assert claim is not None and reason == "acquired"
        revenue_claims.append(claim)
    extra, reason = admission.try_acquire(
        "agent", "revenue-over-hard-ceiling", retain_ticket=False,
        admission_class="revenue")
    assert extra is None and reason == "capacity_busy"

    for claim in [borrow, *revenue_claims]:
        admission.release(claim)


def test_revenue_floor_defers_while_legacy_owner_is_live(
        tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total="5")
    monkeypatch.setenv("LIFE_MANAGER_HOST_MIN_REVENUE_RUNS", "4")
    admission.activate_durable_v2()
    admission.atomic_json(tmp_path / "owners" / "legacy.json", {
        "version": 2, "pid": os.getpid(),
        "process_start": admission.process_start(os.getpid()),
        "owner_id": "legacy-owner", "resource_class": "agent",
        "admission_class": "borrow",
    })

    claim, reason = admission.try_acquire(
        "agent", "revenue-during-migration", retain_ticket=False,
        admission_class="revenue")
    assert claim is None and reason == "capacity_busy"

    (tmp_path / "owners" / "legacy.json").unlink()
    claim, reason = admission.try_acquire(
        "agent", "revenue-after-migration", retain_ticket=False,
        admission_class="revenue")
    assert claim is not None and reason == "acquired"
    admission.release(claim)


def test_revenue_floor_does_not_block_on_legacy_revenue_owner(
        tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total="5")
    monkeypatch.setenv("LIFE_MANAGER_HOST_MIN_REVENUE_RUNS", "4")
    admission.activate_durable_v2()
    admission.atomic_json(tmp_path / "owners" / "legacy-revenue.json", {
        "version": 2, "pid": os.getpid(),
        "process_start": admission.process_start(os.getpid()),
        "owner_id": "legacy-revenue", "resource_class": "agent",
        "admission_class": "revenue",
    })

    claim, reason = admission.try_acquire(
        "agent", "revenue-alongside-legacy", retain_ticket=False,
        admission_class="revenue")
    assert claim is not None and reason == "acquired"
    admission.release(claim)


def test_revenue_floor_treats_legacy_reservation_as_migration_block(
        tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total="5")
    monkeypatch.setenv("LIFE_MANAGER_HOST_MIN_REVENUE_RUNS", "4")
    admission.activate_durable_v2()
    with sqlite3.connect(tmp_path / "admission-v2.sqlite3") as connection:
        lease_until = time.time() + 3600
        connection.execute(
            "INSERT INTO priorities(owner_id,admission_class) VALUES(?,?)",
            ("legacy-reservation", "borrow"),
        )
        connection.execute(
            "INSERT INTO reservations(owner_id,resource_class,sequence,lease_until) "
            "VALUES(?,?,?,?)",
            ("legacy-reservation", "agent", 1, lease_until),
        )

    claim, reason = admission.try_acquire(
        "agent", "revenue-after-legacy-reservation", retain_ticket=False,
        admission_class="revenue")
    assert claim is None and reason == "capacity_busy"


def test_existing_priorities_schema_migrates_policy_column(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    database = tmp_path / "admission-v2.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript("""
            CREATE TABLE priorities (
                owner_id TEXT PRIMARY KEY,
                admission_class TEXT NOT NULL
            );
        """)
    connection = admission._database(database)
    try:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(priorities)")
        }
    finally:
        connection.close()
    assert "admission_policy" in columns


def test_reserved_revenue_rechecks_legacy_owner_before_claim(
        tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total="5")
    monkeypatch.setenv("LIFE_MANAGER_HOST_MIN_REVENUE_RUNS", "4")
    admission.activate_durable_v2()
    admission.enqueue_durable(
        "agent", "revenue-reservation", admission_class="revenue")
    assert admission.reserve_available(now=100, lease_seconds=30) == [
        "revenue-reservation"
    ]
    admission.atomic_json(tmp_path / "owners" / "legacy.json", {
        "version": 2, "pid": os.getpid(),
        "process_start": admission.process_start(os.getpid()),
        "owner_id": "legacy-owner", "resource_class": "agent",
        "admission_class": "borrow",
    })

    claim, reason = admission.claim_durable(
        "agent", "revenue-reservation", admission_class="revenue", now=101)
    assert claim is None and reason == "capacity_busy"

    (tmp_path / "owners" / "legacy.json").unlink()
    claim, reason = admission.claim_durable(
        "agent", "revenue-reservation", admission_class="revenue", now=102)
    assert claim is not None and reason == "acquired"
    admission.release(claim)


def test_durable_reservation_fills_revenue_floor_around_one_borrower(
        tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total="5")
    monkeypatch.setenv("LIFE_MANAGER_HOST_MIN_REVENUE_RUNS", "4")
    admission.activate_durable_v2()

    admission.enqueue_durable("agent", "maintenance-one", admission_class="borrow")
    borrow, reason = admission.claim_durable(
        "agent", "maintenance-one", admission_class="borrow")
    assert borrow is not None and reason == "acquired"
    for index in range(4):
        ticket, reason = admission.enqueue_durable(
            "agent", f"revenue-floor-{index}", admission_class="revenue")
        assert ticket is not None and reason in {"ready", "capacity_busy", "fifo_wait"}

    assert admission.reserve_available(now=100, lease_seconds=30) == [
        "revenue-floor-0", "revenue-floor-1", "revenue-floor-2", "revenue-floor-3"
    ]
    admission.release(borrow)
    for index in range(4):
        claim, reason = admission.claim_durable(
            "agent", f"revenue-floor-{index}", admission_class="revenue", now=101)
        assert claim is not None and reason == "acquired"
        admission.release(claim)


def test_legacy_revenue_uses_host_capacity_beyond_borrow_agent_limit(
        tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total="3")
    monkeypatch.setenv("LIFE_MANAGER_HOST_MAX_AGENT_RUNS", "1")

    claims = []
    for owner_id in ("coconala-apply", "coconala-reply", "coconala-paid"):
        claim, reason = admission.try_acquire(
            "agent", owner_id, retain_ticket=False,
            admission_class="revenue")
        assert claim is not None and reason == "acquired"
        claims.append(claim)

    for claim in claims:
        admission.release(claim)


def test_crashed_revenue_claim_keeps_priority_when_requeued(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    admission.activate_durable_v2()
    admission.enqueue_durable("agent", "older-maintenance")
    admission.enqueue_durable(
        "agent", "coconala-paid", admission_class="revenue")
    claim, reason = admission.claim_durable(
        "agent", "coconala-paid", admission_class="revenue")
    assert claim is not None and reason == "acquired"
    row = json.loads(claim.read_text())
    admission.atomic_json(claim, {
        **row, "pid": 999_999_999, "process_start": "dead",
    })

    assert admission.reserve_available(now=100, lease_seconds=30) == [
        "coconala-paid"
    ]


def test_stale_pre_handoff_claim_returns_to_original_fifo_position(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    admission.enqueue_durable("agent", "first")
    claim, reason = admission.claim_durable("agent", "first")
    assert claim is not None and reason == "acquired"
    row = json.loads(claim.read_text())
    admission.atomic_json(claim, {
        **row, "pid": 999_999_999, "process_start": "dead", "phase": "claimed",
    })

    admission.enqueue_durable("agent", "second")

    assert durable_rows(tmp_path, "queue") == [
        {"sequence": 1, "owner_id": "first", "resource_class": "agent"},
        {"sequence": 2, "owner_id": "second", "resource_class": "agent"},
    ]


def test_same_owner_resume_recovers_pre_handoff_sequence_before_new_insert(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    admission.enqueue_durable("agent", "first")
    claim, reason = admission.claim_durable("agent", "first")
    assert claim is not None and reason == "acquired"
    admission.enqueue_durable("agent", "second")
    row = json.loads(claim.read_text())
    admission.atomic_json(claim, {
        **row, "pid": 999_999_999, "process_start": "dead", "phase": "claimed",
    })

    ticket, reason = admission.enqueue_durable("agent", "first")

    assert ticket is not None and reason == "ready"
    assert durable_rows(tmp_path, "queue") == [
        {"sequence": 1, "owner_id": "first", "resource_class": "agent"},
        {"sequence": 2, "owner_id": "second", "resource_class": "agent"},
    ]


def test_transfer_claim_tracks_child_while_controller_can_release(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    admission.enqueue_durable("agent", "first")
    claim, reason = admission.claim_durable("agent", "first")
    assert claim is not None and reason == "acquired"
    controller_start = admission.process_start(os.getpid())

    def process_identity(pid):
        return "child-start" if pid == 4242 else controller_start

    with patch.object(admission, "process_start", side_effect=process_identity):
        admission.transfer_durable(claim, 4242)
        row = json.loads(claim.read_text())
        assert row["pid"] == 4242
        assert row["process_start"] == "child-start"
        assert row["controller_pid"] == os.getpid()
        assert row["controller_process_start"] == controller_start
        assert row["phase"] == "running"
        admission.release_and_reserve(claim, reserve=False)

    assert not claim.exists()


def test_transfer_lock_contention_fails_closed_without_waiting(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    admission.enqueue_durable("agent", "first")
    claim, reason = admission.claim_durable("agent", "first")
    assert claim is not None and reason == "acquired"
    controller_start = admission.process_start(os.getpid())

    def process_identity(pid):
        return "child-start" if pid == 4242 else controller_start

    with patch.object(admission, "process_start", side_effect=process_identity), \
         patch.object(admission, "_acquire_bounded", return_value=False):
        with pytest.raises(RuntimeError, match="control_busy"):
            admission.transfer_durable(claim, 4242)

    assert json.loads(claim.read_text())["phase"] == "claimed"
    admission.release_and_reserve(claim, reserve=False)


def test_release_lock_contention_fails_closed_without_waiting(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    admission.enqueue_durable("agent", "first")
    claim, reason = admission.claim_durable("agent", "first")
    assert claim is not None and reason == "acquired"

    with patch.object(admission, "_acquire_bounded", return_value=False):
        with pytest.raises(RuntimeError, match="control_busy"):
            admission.release_and_reserve(claim, reserve=False)

    assert claim.exists()
    admission.release_and_reserve(claim, reserve=False)


def test_transfer_control_lock_contention_is_time_bounded(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    admission.enqueue_durable("agent", "first")
    claim, reason = admission.claim_durable("agent", "first")
    assert claim is not None and reason == "acquired"
    controller_start = admission.process_start(os.getpid())
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    holder = context.Process(target=hold_control_lock,
                             args=(str(tmp_path / "control.lock"), ready))
    holder.start()
    try:
        assert ready.wait(timeout=10)

        def process_identity(pid):
            return "child-start" if pid == 4242 else controller_start

        started = time.monotonic()
        with patch.object(admission, "process_start", side_effect=process_identity):
            with pytest.raises(RuntimeError, match="control_busy"):
                admission.transfer_durable(claim, 4242)
        assert time.monotonic() - started < 1.5
    finally:
        holder.terminate()
        holder.join(timeout=5)
    admission.release_and_reserve(claim, reserve=False)


def test_release_control_lock_contention_is_time_bounded(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    admission.enqueue_durable("agent", "first")
    claim, reason = admission.claim_durable("agent", "first")
    assert claim is not None and reason == "acquired"
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    holder = context.Process(target=hold_control_lock,
                             args=(str(tmp_path / "control.lock"), ready))
    holder.start()
    try:
        assert ready.wait(timeout=10)
        started = time.monotonic()
        with pytest.raises(RuntimeError, match="control_busy"):
            admission.release_and_reserve(claim, reserve=False)
        assert time.monotonic() - started < 1.5
    finally:
        holder.terminate()
        holder.join(timeout=5)
    admission.release_and_reserve(claim, reserve=False)


def test_cancel_retired_owner_removes_queue_and_reservation(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    admission.enqueue_durable("agent", "retired")
    admission.reserve_available(now=100, lease_seconds=30)
    assert admission.cancel_durable("retired") is True
    assert durable_rows(tmp_path, "queue") == []
    assert durable_rows(tmp_path, "reservations") == []


def test_five_hundred_durable_waiters_remain_bounded(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    started = time.monotonic()
    for index in range(500):
        assert admission.enqueue_durable("agent", f"loop-{index:03d}")[0] is not None
    assert len(durable_rows(tmp_path, "queue")) == 500
    assert time.monotonic() - started < 15


def test_simultaneous_durable_waiters_all_persist(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total="3")
    admission.activate_durable_v2()
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(40)
    results = context.Queue()
    processes = [
        context.Process(target=enqueue_after_barrier, args=(
            tmp_path, index, barrier, results,
        ))
        for index in range(39)
    ]
    try:
        for process in processes:
            process.start()
        barrier.wait(timeout=10)
        for process in processes:
            process.join(timeout=10)
        outcomes = [results.get(timeout=2) for _ in processes]
        assert all(process.exitcode == 0 for process in processes)
        assert all(persisted for persisted, _ in outcomes)
        assert len(durable_rows(tmp_path, "queue")) == 39
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
