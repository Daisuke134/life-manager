"""Classify actual storage syscalls; text and free-space samples are not proof."""
import errno
import re
import json
import os
import stat
import tempfile
from pathlib import Path
from datetime import datetime, timezone


def classify_storage_failure(error, phase, binding, effect_started):
    if not isinstance(error, OSError) or error.errno not in {errno.ENOSPC, errno.EDQUOT}:
        return None
    if effect_started is not None and type(effect_started) is not bool:
        raise ValueError("invalid storage effect boundary")
    if not isinstance(phase, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", phase):
        raise ValueError("invalid storage operation")
    for key in ("owner_id", "run_id", "occurrence_id"):
        if not isinstance(binding.get(key), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", binding[key]):
            raise ValueError("invalid storage identity")
    if not re.fullmatch(r"[a-f0-9]{40}", binding.get("release_sha", "")):
        raise ValueError("invalid storage release")
    proof = f'lm-storage://{binding["owner_id"]}/{binding["run_id"]}/{phase}'
    return {**binding, "phase": phase,
        "error_class": "storage_write_failed_pre_effect" if effect_started is False else "storage_write_failed_effect_unknown",
        "retryable": effect_started is False,
        "next_action": "retry_after_cleanup" if effect_started is False else "official_readback_required",
        "effect_started": effect_started, "evidence_refs": [proof],
        "storage_failure": {"errno": error.errno, "operation": phase,
            "effect_started": effect_started, "proof_ref": proof}}


def validate_storage_failure(value):
    if not isinstance(value, dict) or set(value) != {"errno", "operation", "effect_started", "proof_ref"}:
        raise ValueError("invalid storage failure shape")
    if type(value["errno"]) is not int or value["errno"] not in {errno.ENOSPC, errno.EDQUOT}:
        raise ValueError("invalid storage errno")
    if value["effect_started"] is not None and type(value["effect_started"]) is not bool:
        raise ValueError("invalid storage effect boundary")
    if not isinstance(value["operation"], str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value["operation"]):
        raise ValueError("invalid storage operation")
    if not isinstance(value["proof_ref"], str) or not re.fullmatch(r"lm-storage://[A-Za-z0-9._:-]+/[A-Za-z0-9._:-]+/[a-z0-9_]+", value["proof_ref"]):
        raise ValueError("invalid storage proof")
    return value


def _private_read(path, limit, tail=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_nlink != 1):
            raise ValueError("unsafe storage readback")
        if info.st_size > limit:
            if not tail: raise ValueError("oversized storage receipt")
            stream.seek(-limit, os.SEEK_END)
        return stream.read(limit)


def storage_recovery_ready(state_root, host_root, binding, failure, *, now=None):
    """Fresh official local readback plus the actual affected-volume syscall."""
    probe = None
    try:
        validate_storage_failure(failure)
        if failure["effect_started"] is not False or failure["operation"] != "scratch_allocation": return False
        if failure["proof_ref"] != f'lm-storage://{binding["owner_id"]}/{binding["run_id"]}/scratch_allocation': return False
        state = Path(state_root).expanduser(); host = Path(host_root).expanduser()
        if not state.is_absolute() or not host.is_absolute(): return False
        if any(p.is_symlink() for root in (state, host) for p in [root, *root.parents]): return False
        receipt = json.loads(_private_read(host / "last-receipt.json", 65536))
        identity = receipt.get("identity") or {}
        if (identity.get("owner_id") != "life-manager-disk-cleanup"
                or identity.get("release_sha") != binding["release_sha"]
                or receipt.get("ok") is not True or receipt.get("errors") != 0
                or receipt.get("protected_deletions") != 0): return False
        observed = datetime.fromisoformat(receipt["observed_at"].replace("Z", "+00:00"))
        clock = now or datetime.now(timezone.utc)
        if observed.tzinfo is None or not 0 <= (clock-observed).total_seconds() <= 600: return False
        matched = False
        for line in _private_read(state / "events.jsonl", 262144, tail=True).splitlines():
            try: event = json.loads(line)
            except ValueError: continue
            if (all(event.get(k) == v for k, v in binding.items())
                    and event.get("storage_failure") == failure):
                failed_at = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
                matched = failed_at.tzinfo is not None and failed_at <= observed
        if not matched: return False
        fd, probe = tempfile.mkstemp(prefix=".lm-storage-write-probe-", dir=state)
        with os.fdopen(fd, "wb") as stream:
            stream.write(b"\0"*4096); stream.flush(); os.fsync(stream.fileno())
        return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False
    finally:
        if probe:
            try: os.unlink(probe)
            except OSError: pass


if __name__ == "__main__":
    import sys
    request = json.loads(sys.argv[1])
    print(json.dumps({"ready": storage_recovery_ready(request["state_root"], request["host_root"],
        request["binding"], request["storage_failure"])}))
