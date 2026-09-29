"""Runtime bookkeeping retries are wired to the reserve boundary."""

from __future__ import annotations

import errno
import json
from pathlib import Path
from unittest import mock

from runtime.loop import lm_loop_run, runtime_event
from runtime.loop.lm_loop_run import _append_recovery_intent, _atomic_json
from runtime.loop.runtime_event import append_runtime_event
from runtime.loop.runtime_reserve import RUNTIME_RESERVE_BYTES, runtime_reserve_valid


EVENT = {
    "version": 1, "event_id": "a" * 24, "timestamp": "2026-08-28T00:00:00+00:00",
    "loop_id": "example", "domain": "earn", "run_id": "run-1", "phase": "report",
    "status": "pass", "release_sha": "b" * 40, "provider": "openai",
    "profile_alias": "acct2", "effect_class": "application",
    "effect_status": "unknown", "blocker": None,
    "evidence_refs": ["agent-runner://example/run-1/summary.json"],
}


def _seed(path: Path) -> None:
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\0" * RUNTIME_RESERVE_BYTES)
    path.chmod(0o600)


def test_runtime_event_retries_a_short_append_after_enospc(tmp_path: Path, monkeypatch) -> None:
    reserve = tmp_path / "reserve" / ".runtime-reserve"
    _seed(reserve)
    monkeypatch.setenv("LIFE_MANAGER_RUNTIME_RESERVE_PATH", str(reserve))
    events = tmp_path / "events.jsonl"
    real_write = runtime_event.os.write
    failures = 0

    def fail_once(fd: int, data: bytes) -> int:
        nonlocal failures
        if failures == 0:
            failures += 1
            raise OSError(errno.ENOSPC, "events full")
        return real_write(fd, data)

    with mock.patch.object(runtime_event.os, "write", side_effect=fail_once):
        append_runtime_event(events, EVENT)
    assert failures == 1
    assert json.loads(events.read_text(encoding="utf-8")) == EVENT
    assert runtime_reserve_valid(reserve)


def test_recovery_intent_retries_a_short_append_after_enospc(tmp_path: Path, monkeypatch) -> None:
    reserve = tmp_path / "reserve" / ".runtime-reserve"
    _seed(reserve)
    monkeypatch.setenv("LIFE_MANAGER_RUNTIME_RESERVE_PATH", str(reserve))
    queue = tmp_path / "recovery" / "intents.jsonl"
    intent = {"intent_id": "intent-1", "loop_id": "job", "retryable": True}
    real_write = lm_loop_run.os.write
    failures = 0

    def fail_once(fd: int, data: bytes) -> int:
        nonlocal failures
        if failures == 0:
            failures += 1
            raise OSError(errno.ENOSPC, "recovery full")
        return real_write(fd, data)

    with mock.patch.object(lm_loop_run.os, "write", side_effect=fail_once):
        _append_recovery_intent(queue, intent)
    assert failures == 1
    assert json.loads(queue.read_text(encoding="utf-8")) == intent
    assert runtime_reserve_valid(reserve)


def test_atomic_json_retries_replace_after_enospc(tmp_path: Path, monkeypatch) -> None:
    reserve = tmp_path / "reserve" / ".runtime-reserve"
    _seed(reserve)
    monkeypatch.setenv("LIFE_MANAGER_RUNTIME_RESERVE_PATH", str(reserve))
    target = tmp_path / "receipt.json"
    real_replace = lm_loop_run.os.replace
    failures = 0

    def fail_once(source, destination, *args, **kwargs):
        nonlocal failures
        if failures == 0:
            failures += 1
            raise OSError(errno.ENOSPC, "receipt full")
        return real_replace(source, destination, *args, **kwargs)

    with mock.patch.object(lm_loop_run.os, "replace", side_effect=fail_once):
        _atomic_json(target, {"status": "pass"})
    assert failures == 1
    assert json.loads(target.read_text(encoding="utf-8")) == {"status": "pass"}
    assert runtime_reserve_valid(reserve)
