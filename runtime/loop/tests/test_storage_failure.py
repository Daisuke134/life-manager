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
