#!/usr/bin/env python3
"""Durable write-ahead envelope for Affiliate external effects."""

import fcntl
import hashlib
import json
import os
import tempfile
import time
import uuid
from pathlib import Path


class JobStateError(Exception):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def reject_secrets(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if any(word in str(key).lower() for word in ("password", "secret", "token", "credential")):
                raise JobStateError("job journal refuses secret-bearing fields")
            reject_secrets(item)
    elif isinstance(value, list):
        for item in value:
            reject_secrets(item)


def atomic_json(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(canonical(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def append(path, value):
    with path.open("a", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        stream.write(canonical(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def target_index_path(jobs, kind, target):
    target_key = hashlib.sha256(f"{kind}\0{target}".encode()).hexdigest()
    return jobs / f"target-{target_key}.json"


def empty_target_row(kind, target):
    return {
        "schema_version": 1,
        "receipt_type": "AFFILIATE_EXTERNAL_TARGET_INDEX",
        "kind": kind,
        "target": target,
        "state": "NO_UNRESOLVED_LEGACY",
    }


def validate_target_row(row, kind, target):
    if row.get("receipt_type") == "AFFILIATE_EXTERNAL_TARGET_INDEX":
        if row == empty_target_row(kind, target):
            return None
        raise JobStateError("target job index is invalid or does not match request")
    sequence = row.get("sequence")
    hashes = (row.get("job_id"), row.get("job_key"), row.get("action_fingerprint"))
    if (
        row.get("schema_version") != 1
        or row.get("receipt_type") != "AFFILIATE_EXTERNAL_JOB"
        or row.get("kind") != kind
        or row.get("target") != target
        or row.get("state") not in {"EFFECT_STARTED", "VERIFIED"}
        or not isinstance(sequence, int)
        or sequence < 1
        or any(
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in hashes
        )
    ):
        raise JobStateError("target job index is invalid or does not match request")
    expected_job_key = hashlib.sha256(
        f"{kind}\0{target}\0{row['action_fingerprint']}".encode()
    ).hexdigest()
    expected_job_id = hashlib.sha256(
        f"{expected_job_key}\0{sequence}".encode()
    ).hexdigest()
    if row["job_key"] != expected_job_key or row["job_id"] != expected_job_id:
        raise JobStateError("target job index is invalid or does not match request")
    return row


def legacy_target_row(jobs, kind, target, index_path, cache_empty=True):
    """Migrate one legacy unresolved target without changing its identity."""
    unresolved = []
    for path in jobs.glob("key-*.json"):
        try:
            row = json.loads(path.read_text())
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise JobStateError("legacy job index is invalid") from error
        if row.get("state") == "EFFECT_STARTED" and row.get("kind") == kind and row.get("target") == target:
            unresolved.append(validate_target_row(row, kind, target))
    if len(unresolved) > 1:
        raise JobStateError("multiple unresolved effects require quarantine")
    if unresolved:
        atomic_json(index_path, unresolved[0])
        return unresolved[0]
    if cache_empty:
        atomic_json(index_path, empty_target_row(kind, target))
    return None


def target_row(jobs, kind, target, cache_empty=True):
    """Resolve one effect by durable target index, with one-time legacy migration."""
    index_path = target_index_path(jobs, kind, target)
    if not index_path.is_file():
        return legacy_target_row(jobs, kind, target, index_path, cache_empty)
    try:
        row = json.loads(index_path.read_text())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise JobStateError("target job index is invalid") from error
    return validate_target_row(row, kind, target)


def write_job_indexes(jobs, row):
    target_path = target_index_path(jobs, row["kind"], row["target"])
    if row["state"] == "EFFECT_STARTED":
        # The target fence is authoritative. Persist it before secondary
        # lookup indexes so a crash can delay recovery but cannot allow a
        # second action fingerprint for the same external target.
        atomic_json(target_path, row)
    atomic_json(jobs / f"{row['job_id']}.json", row)
    atomic_json(jobs / f"key-{row['job_key']}.json", row)
    if row["state"] != "EFFECT_STARTED":
        atomic_json(target_path, row)


def start_effect(state, kind, target, action, last_verified, cooldown_seconds):
    reject_secrets(action)
    reject_secrets(last_verified)
    state = state.expanduser()
    jobs = state / "jobs"
    jobs.mkdir(mode=0o700, parents=True, exist_ok=True)
    action_fingerprint = hashlib.sha256(canonical(action).encode()).hexdigest()
    job_key = hashlib.sha256(f"{kind}\0{target}\0{action_fingerprint}".encode()).hexdigest()
    lock_path = jobs / ".lock"
    with lock_path.open("a+") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        active = target_row(jobs, kind, target, cache_empty=False)
        if active and active.get("state") == "EFFECT_STARTED":
            raise JobStateError("unresolved external effect requires reconciliation")
        index_path = jobs / f"key-{job_key}.json"
        previous = json.loads(index_path.read_text()) if index_path.is_file() else None
        if previous and previous.get("state") == "EFFECT_STARTED":
            raise JobStateError("unresolved external effect requires reconciliation")
        sequence = int(previous.get("sequence", 0)) + 1 if previous else 1
        job_id = hashlib.sha256(f"{job_key}\0{sequence}".encode()).hexdigest()
        now = int(time.time())
        row = {
            "schema_version": 1,
            "receipt_type": "AFFILIATE_EXTERNAL_JOB",
            "run_id": str(uuid.uuid4()),
            "job_id": job_id,
            "job_key": job_key,
            "kind": kind,
            "target": target,
            "state": "EFFECT_STARTED",
            "attempt": 1,
            "sequence": sequence,
            "action_fingerprint": action_fingerprint,
            "cooldown": {"seconds": int(cooldown_seconds), "until": None},
            "last_verified_external_object": last_verified,
            "updated_at": now,
        }
        write_job_indexes(jobs, row)
        append(state / "job-events.jsonl", row)
        return row


def verify_effect(state, job_id, external_object):
    reject_secrets(external_object)
    state = state.expanduser()
    jobs = state / "jobs"
    path = jobs / f"{job_id}.json"
    lock_path = jobs / ".lock"
    with lock_path.open("a+") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        row = json.loads(path.read_text())
        if row.get("state") != "EFFECT_STARTED":
            raise JobStateError("job is not awaiting external verification")
        row.update(
            state="VERIFIED",
            last_verified_external_object=external_object,
            updated_at=int(time.time()),
        )
        indexed = target_row(jobs, row["kind"], row["target"])
        if indexed and indexed.get("state") == "EFFECT_STARTED" and indexed.get("job_id") != job_id:
            raise JobStateError("target index points to another unresolved effect")
        write_job_indexes(jobs, row)
        append(state / "job-events.jsonl", row)
        return row


def resume_effect(state, kind, target):
    """Resume exactly one unresolved effect without changing its identity."""
    state = state.expanduser()
    jobs = state / "jobs"
    if not jobs.is_dir():
        return None
    lock_path = jobs / ".lock"
    with lock_path.open("a+") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        row = target_row(jobs, kind, target)
        if not row or row.get("state") != "EFFECT_STARTED":
            return None
        row.update(attempt=int(row["attempt"]) + 1, resumed=True, updated_at=int(time.time()))
        write_job_indexes(jobs, row)
        append(state / "job-events.jsonl", row)
        return row


def unresolved_effect(state, kind, target):
    """Read exactly one unresolved effect without changing attempts or timestamps."""
    state = state.expanduser()
    jobs = state / "jobs"
    if not jobs.is_dir():
        return None
    lock_path = jobs / ".lock"
    with lock_path.open("a+") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        row = target_row(jobs, kind, target)
        return row if row and row.get("state") == "EFFECT_STARTED" else None


def reconcile_effect(state, kind, target, external_object):
    """Complete the one unresolved target after a fresh semantic readback."""
    reject_secrets(external_object)
    state = state.expanduser()
    jobs = state / "jobs"
    if not jobs.is_dir():
        return None
    lock_path = jobs / ".lock"
    with lock_path.open("a+") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        row = target_row(jobs, kind, target)
        if not row or row.get("state") != "EFFECT_STARTED":
            return None
        row.update(
            state="VERIFIED",
            attempt=int(row["attempt"]) + 1,
            resumed=True,
            last_verified_external_object=external_object,
            updated_at=int(time.time()),
        )
        write_job_indexes(jobs, row)
        append(state / "job-events.jsonl", row)
        return row
