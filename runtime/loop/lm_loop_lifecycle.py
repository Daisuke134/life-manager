"""Uniform launchd lifecycle operations with collect-all result semantics."""

from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
from typing import Callable

from runtime.loop.macos_loop_registry import validate_registry


_REPAIR_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
_REPAIR_EVENT_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")
_REPAIR_REASONS = {"retry_budget_exhausted", "failure_streak_threshold"}
_REPAIR_FIELDS = {
    "event_key", "job_id", "owner_id", "reason", "recorded_at", "retry_attempt",
    "route", "slot", "state", "schema_version",
}


def _repair_queue_path(queue_path: Path | None) -> Path:
    if queue_path is not None:
        return Path(queue_path).expanduser()
    configured = os.environ.get("LIFE_MANAGER_REPAIR_QUEUE_PATH", "").strip()
    return Path(configured).expanduser() if configured else Path(
        "~/.local/state/life-manager/recovery/repair-queue.jsonl"
    ).expanduser()


def _valid_repair_row(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != _REPAIR_FIELDS:
        return False
    if (value.get("schema_version") != "repair.queue.v1"
            or value.get("state") not in {"queued", "claimed", "repaired", "blocked"}
            or not isinstance(value.get("event_key"), str)
            or not _REPAIR_EVENT_KEY.fullmatch(value["event_key"])
            or not isinstance(value.get("job_id"), str)
            or not _REPAIR_ID.fullmatch(value["job_id"])
            or value.get("owner_id") != value.get("job_id")
            or not isinstance(value.get("reason"), str)
            or value["reason"] not in _REPAIR_REASONS
            or not isinstance(value.get("recorded_at"), str)
            or not isinstance(value.get("retry_attempt"), int)
            or isinstance(value.get("retry_attempt"), bool)
            or value["retry_attempt"] < 0
            or not isinstance(value.get("route"), str)
            or value["route"] not in {"deterministic", "shared-agent-runner"}
            or not isinstance(value.get("slot"), str)
            or not _REPAIR_ID.fullmatch(value["slot"])
    ):
        return False
    try:
        datetime.fromisoformat(value["recorded_at"].replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def enqueue_repair_intent(recovery_path: Path, registry: dict, route: str, *,
                          queue_path: Path | None = None,
                          recorded_at: str | None = None) -> dict:
    """Persist one exhausted recovery intent without restarting or resending it.

    The projection is required to contain exactly one ``escalate_repair`` decision.  The
    resulting queue row is secret-free and idempotent by ``event_key``; a malformed or
    multi-owner projection fails closed before any write.
    """
    try:
        validate_registry(registry)
    except (TypeError, ValueError):
        return {"ok": False, "error": "registry_invalid"}
    if route not in {"deterministic", "shared-agent-runner"}:
        return {"ok": False, "error": "recovery_repair_route_invalid"}
    try:
        value = json.loads(Path(recovery_path).expanduser().read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {"ok": False, "error": "recovery_repair_intent_invalid"}
    if (not isinstance(value, dict)
            or value.get("schema_version") != "recovery.intents.v1"
            or not isinstance(value.get("decisions"), list)):
        return {"ok": False, "error": "recovery_repair_intent_invalid"}
    repairs = [item for item in value["decisions"]
               if isinstance(item, dict) and item.get("action") == "escalate_repair"]
    if len(repairs) != 1:
        return {"ok": False, "error": "recovery_repair_intent_count_invalid"}
    intent = repairs[0]
    event_key = intent.get("event_key")
    owner_id = intent.get("owner_id")
    job_id = intent.get("job_id")
    slot = intent.get("slot")
    reason = intent.get("reason")
    retry_attempt = intent.get("retry_attempt")
    if (not isinstance(event_key, str) or not _REPAIR_EVENT_KEY.fullmatch(event_key)
            or not isinstance(owner_id, str) or not _REPAIR_ID.fullmatch(owner_id)
            or not isinstance(job_id, str) or not _REPAIR_ID.fullmatch(job_id)
            or not isinstance(slot, str) or not _REPAIR_ID.fullmatch(slot)
            or reason not in _REPAIR_REASONS
            or not isinstance(retry_attempt, int) or isinstance(retry_attempt, bool)
            or retry_attempt < 0):
        return {"ok": False, "error": "recovery_repair_intent_invalid"}
    if owner_id != job_id:
        return {"ok": False, "error": "recovery_repair_intent_owner_mismatch"}
    entry = registry.get("loops", {}).get(job_id)
    if not isinstance(entry, dict):
        return {"ok": False, "error": "recovery_repair_intent_job_unknown"}
    expected_owner = entry.get("owner_id") if isinstance(entry.get("owner_id"), str) else job_id
    if expected_owner != owner_id:
        return {"ok": False, "error": "recovery_repair_intent_owner_mismatch"}
    if entry.get("provider_route") != route:
        return {"ok": False, "error": "recovery_repair_intent_route_mismatch"}
    stamp = recorded_at or datetime.now(timezone.utc).isoformat()
    try:
        parsed_stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if parsed_stamp.tzinfo is None:
            raise ValueError("timezone required")
    except (AttributeError, TypeError, ValueError):
        return {"ok": False, "error": "recovery_repair_timestamp_invalid"}
    row = {
        "event_key": event_key,
        "job_id": job_id,
        "owner_id": owner_id,
        "reason": reason,
        "recorded_at": stamp,
        "retry_attempt": retry_attempt,
        "route": route,
        "slot": slot,
        "state": "queued",
        "schema_version": "repair.queue.v1",
    }
    target = _repair_queue_path(queue_path)
    if target.is_symlink() or target.name in {"", ".", ".."}:
        return {"ok": False, "error": "repair_queue_path_invalid"}
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target.parent, 0o700)
    lock_path = target.with_name(f".{target.name}.lock")
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        existing_keys: set[str] = set()
        if target.exists():
            if target.is_symlink() or not target.is_file():
                return {"ok": False, "error": "repair_queue_path_invalid"}
            for line in target.read_text(encoding="utf-8").splitlines():
                try:
                    existing = json.loads(line)
                except (ValueError, json.JSONDecodeError):
                    return {"ok": False, "error": "repair_queue_corrupt"}
                if not _valid_repair_row(existing):
                    return {"ok": False, "error": "repair_queue_corrupt"}
                existing_keys.add(existing["event_key"])
        if event_key in existing_keys:
            return {"ok": True, "queued": False, "queue_path": str(target),
                    "event_key": event_key, "reason": "already_queued"}
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(target, 0o600)
    finally:
        os.close(descriptor)
    return {"ok": True, "queued": True, "queue_path": str(target),
            "event_key": event_key}


def lifecycle_one(action: str, loop_id: str, entry: dict, agents_dir: Path,
                  launchctl: Callable[[list[str]], tuple[int, str]]) -> dict:
    if action not in {"start", "stop", "restart"}:
        raise ValueError(f"invalid lifecycle action: {action}")
    label = entry["label"]
    domain = f"gui/{os.getuid()}"
    service = f"{domain}/{label}"
    plist = agents_dir / f"{label}.plist"
    operations = []

    def run(args: list[str]) -> tuple[int, str]:
        rc, detail = launchctl(args)
        operations.append({"command": args[0], "return_code": rc})
        return rc, detail

    if action == "stop":
        rc, detail = run(["bootout", service])
        return {"loop_id": loop_id, "label": label, "action": action,
                "return_code": rc, "operations": operations, "detail": detail.strip()}

    if not plist.is_file():
        return {"loop_id": loop_id, "label": label, "action": action,
                "return_code": 2, "operations": operations,
                "detail": f"installed plist missing: {plist}"}

    if action == "start":
        print_rc, _ = run(["print", service])
        if print_rc == 0:
            action_rc, detail = run(["kickstart", service])
        else:
            action_rc, detail = run(["bootstrap", domain, str(plist)])
    else:
        run(["bootout", service])
        action_rc, detail = run(["bootstrap", domain, str(plist)])
    readback_rc, readback = run(["print", service])
    rc = action_rc or readback_rc
    return {"loop_id": loop_id, "label": label, "action": action,
            "return_code": rc, "operations": operations,
            "detail": (readback if readback_rc else detail).strip()}


def lifecycle(registry: dict, action: str, target: str,
              execute: Callable[[str, str, dict], dict]) -> list[dict]:
    validate_registry(registry)
    if action not in {"start", "stop", "restart"}:
        raise ValueError(f"invalid lifecycle action: {action}")
    if target == "all":
        loop_ids = sorted(registry["loops"])
    elif target in registry["loops"]:
        loop_ids = [target]
    else:
        raise ValueError(f"unknown loop id: {target}")
    results = []
    for loop_id in loop_ids:
        entry = registry["loops"][loop_id]
        try:
            results.append(execute(action, loop_id, entry))
        except Exception as exc:
            results.append({"loop_id": loop_id, "label": entry["label"],
                            "action": action, "return_code": 1,
                            "operations": [], "detail": str(exc)})
    return results
