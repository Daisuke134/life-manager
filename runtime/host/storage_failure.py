"""Classify actual storage syscalls; text and free-space samples are not proof."""
import errno
import re


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
