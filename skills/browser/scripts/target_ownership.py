#!/usr/bin/env python3
"""Small, process-safe registry of loop-owned CDP page targets."""
import fcntl
import errno
import json
import os
import re
import stat
import time
from pathlib import Path

_OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _registry_path():
    configured = os.environ.get("CLOAK_TARGET_OWNERS_FILE")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cloak" / "vault" / "target-owners.json"


def require_owner(owner=None):
    value = owner or os.environ.get("CLOAK_BROWSER_OWNER")
    if not value or not _OWNER_RE.fullmatch(value):
        raise ValueError(
            "browser owner is required; pass --owner or set CLOAK_BROWSER_OWNER"
        )
    return value


def _persist_registry(path, data):
    """Persist the tiny ownership ledger even when directory allocation is exhausted.

    The normal path remains replace-on-write.  If only the directory-entry allocation
    fails, reuse the already allocated inode while holding the same flock.  A missing,
    symlinked, or non-regular ledger never takes this fallback; callers then receive the
    typed capacity error and the newly-created CDP target is closed by the helper.
    """
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n"
    temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    try:
        temp.write_text(payload, encoding="utf-8")
        os.replace(temp, path)
        return
    except OSError as error:
        if error.errno != errno.ENOSPC:
            raise
        try:
            info = path.lstat()
        except OSError:
            raise error
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise error
        try:
            with path.open("r+", encoding="utf-8") as handle:
                handle.seek(0)
                handle.write(payload)
                handle.truncate()
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as fallback_error:
            raise OSError(
                errno.ENOSPC,
                "browser_state_capacity: ownership ledger could not be persisted",
                str(path),
            ) from fallback_error
    finally:
        temp.unlink(missing_ok=True)


def _mutate(callback):
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                data = {"version": 1, "targets": {}}
            if not isinstance(data.get("targets"), dict):
                data = {"version": 1, "targets": {}}
            result, changed = callback(data["targets"])
            if changed:
                _persist_registry(path, data)
            return result
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def claim_target(target_id, owner=None, max_targets=1):
    owner = require_owner(owner)
    if not target_id:
        raise ValueError("target_id is required")
    if max_targets is not None and (
        isinstance(max_targets, bool) or not isinstance(max_targets, int) or max_targets < 1
    ):
        raise ValueError("max_targets must be a positive integer")

    def claim(targets):
        existing = targets.get(target_id)
        if existing and existing.get("owner") != owner:
            raise PermissionError(
                f"target {target_id} is already owned by {existing.get('owner')}"
            )
        owned_count = sum(
            isinstance(record, dict) and record.get("owner") == owner
            for current_id, record in targets.items()
            if current_id != target_id
        )
        if max_targets is not None and owned_count >= max_targets:
            raise RuntimeError("browser_tab_limit")
        targets[target_id] = {"owner": owner, "claimed_at": int(time.time())}
        return True, True

    return _mutate(claim)


def owner_for_target(target_id):
    def lookup(targets):
        record = targets.get(target_id)
        return (record.get("owner") if isinstance(record, dict) else None), False

    return _mutate(lookup)


def owns_target(target_id, owner=None):
    return owner_for_target(target_id) == require_owner(owner)


def targets_for_owner(owner=None):
    owner = require_owner(owner)

    def collect(targets):
        return {
            target_id
            for target_id, record in targets.items()
            if isinstance(record, dict) and record.get("owner") == owner
        }, False

    return _mutate(collect)


def release_target(target_id, owner=None):
    owner = require_owner(owner)

    def release(targets):
        record = targets.get(target_id)
        if not isinstance(record, dict) or record.get("owner") != owner:
            return False, False
        del targets[target_id]
        return True, True

    return _mutate(release)


def prune_missing_targets(live_target_ids):
    """Forget registry rows whose CDP targets no longer exist."""
    live_target_ids = set(live_target_ids)

    def prune(targets):
        stale = [target_id for target_id in targets if target_id not in live_target_ids]
        for target_id in stale:
            del targets[target_id]
        return len(stale), bool(stale)

    return _mutate(prune)
