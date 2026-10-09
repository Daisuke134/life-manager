import errno
import pytest
from runtime.host.storage_failure import classify_storage_failure
from runtime.loop.runtime_event import build_runtime_event, validate_runtime_event

BINDING = dict(owner_id="example", run_id="run-1", occurrence_id="example:run-1", release_sha="a"*40)

@pytest.mark.parametrize("number", [errno.ENOSPC, errno.EDQUOT])
@pytest.mark.parametrize("started", [False, True, None])
def test_storage_errno_preserves_effect_boundary(number, started):
    failure = classify_storage_failure(OSError(number, "not persisted"), "scratch_allocation", BINDING, started)
    assert failure["effect_started"] is started
    assert failure["retryable"] is (started is False)
    assert failure["error_class"] == ("storage_write_failed_pre_effect" if started is False else "storage_write_failed_effect_unknown")
    event = build_runtime_event(loop_id="example", domain="earn", run_id="run-1", release_sha="a"*40,
        provider="codex", profile_alias=None, effect_class="publish", succeeded=False, blocker="storage_write_failed",
        storage_failure=failure["storage_failure"])
    assert validate_runtime_event(event)["storage_failure"]["errno"] == number

def test_non_storage_error_is_not_capacity_failure():
    assert classify_storage_failure(OSError(errno.EACCES, "denied"), "write", BINDING, False) is None
    assert classify_storage_failure(ValueError("ENOSPC in text"), "write", BINDING, False) is None

def test_invalid_effect_proof_rejected():
    with pytest.raises(ValueError):
        classify_storage_failure(OSError(errno.ENOSPC, "full"), "write", BINDING, 0)

def test_recovery_requires_fresh_committed_cleanup_and_real_write(tmp_path):
    import json
    from datetime import datetime, timezone, timedelta
    from runtime.host.storage_failure import storage_recovery_ready
    now = datetime.now(timezone.utc)
    failure = classify_storage_failure(OSError(errno.ENOSPC, "full"), "scratch_allocation", BINDING, False)
    event = {**BINDING, "timestamp": (now-timedelta(seconds=30)).isoformat(),
             "storage_failure": failure["storage_failure"]}
    state = tmp_path / "state"; state.mkdir()
    events = state / "events.jsonl"; events.write_text(json.dumps(event)+"\n"); events.chmod(0o600)
    host = tmp_path / "host"; host.mkdir()
    receipt = host / "last-receipt.json"
    receipt.write_text(json.dumps({"identity":{"owner_id":"life-manager-disk-cleanup", "release_sha":"a"*40},
        "ok":True, "observed_at": now.isoformat(), "errors":0, "protected_deletions":0,
        "capacity_recovery":{"goal":"unmet"}})); receipt.chmod(0o600)
    assert storage_recovery_ready(state, host, BINDING, failure["storage_failure"], now=now) is True
    assert not list(state.glob(".lm-storage-write-probe-*"))
    receipt.write_text('{}')
    assert storage_recovery_ready(state, host, BINDING, failure["storage_failure"], now=now) is False
