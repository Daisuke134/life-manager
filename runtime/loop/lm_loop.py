#!/usr/bin/env python3
"""Read-only lm-loop commands. Lifecycle mutation is added in later slices."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import fcntl
import gzip
import json
import os
import plistlib
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from runtime.loop.macos_launchd_inventory import extract_release, parse_disabled, parse_loaded
from runtime.loop.macos_loop_registry import (
    CONTROL_PLANE_SAFETY_LOOPS, admission_effect_scope, validate_registry,
)
from runtime.loop.lm_loop_apply import (
    _plist,
    _loaded_arguments,
    _preserve_operational_attributes,
    apply_registry,
    install_one,
)
from runtime.loop.lm_loop_lifecycle import lifecycle, lifecycle_one
from runtime.loop.runtime_event import (
    DIAGNOSTIC_FIELDS, append_runtime_event, build_install_event, validate_runtime_event,
)
from runtime.host.resource_admission import (
    ADMISSION_POLICY, activate_durable_v2, durable_protocol_version, owner_deploy_lock,
    cancel_effect_free_queued_owner, clear_no_effect_unknown, rebind_queued_owner, resume_durable,
    resolve_pre_effect_occurrence, suspend_durable,
    state_root as admission_root,
)


ROOT = Path(__file__).resolve().parents[2]
PRE_EFFECT_ADMISSION_BLOCKERS = frozenset({
    "host_admission_deferred:resource_capacity_busy",
    "host_admission_deferred:resource_fifo_wait",
})
SAFE_OCCURRENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
MAX_PRE_EFFECT_ARCHIVES = 4
MAX_HARNESS_FAILURE_BYTES = 16 * 1024 * 1024


def _event_epoch(value: object) -> float:
    if not isinstance(value, str):
        raise ValueError("runtime event timestamp missing")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def _private_runtime_rows(path: Path, *, max_rows: int = 50_000) -> list[dict]:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError("runtime event journal is not private")
        rows = []
        with os.fdopen(descriptor, "rb") as raw:
            descriptor = -1
            stream = (
                gzip.GzipFile(fileobj=raw, mode="rb")
                if path.name.endswith(".jsonl.gz") else raw
            )
            try:
                for line in stream:
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError("runtime event row invalid")
                    rows.append(validate_runtime_event(value))
                    if len(rows) > max_rows:
                        raise ValueError("runtime event journal too large")
            finally:
                if stream is not raw:
                    stream.close()
        return rows
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _private_jsonl_rows(path: Path, *, max_rows: int = 50_000,
                        max_bytes: int = MAX_HARNESS_FAILURE_BYTES) -> list[dict]:
    """Read one private JSONL side channel without following links or trusting its mode.

    Harness failures are diagnostic input, not runtime events, so they cannot use
    ``_private_runtime_rows``'s strict event validator.  They still need the same
    ownership, regular-file, link-count and 0600 checks before status consumes them.
    """
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return []
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_size > max_bytes):
            return []
        with os.fdopen(descriptor, "rb") as raw:
            descriptor = -1
            rows = []
            for line in raw:
                try:
                    value = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(value, dict):
                    rows.append(value)
                    if len(rows) > max_rows:
                        return []
            return rows
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _harness_failure_paths(state_root: str) -> list[Path]:
    root = Path(os.path.expanduser(state_root))
    return [
        root / "instance" / "state" / "harness-failures.jsonl",
        root / "state" / "harness-failures.jsonl",
        root / "harness-failures.jsonl",
    ]


def _ledger_paths(state_root: str) -> list[Path]:
    root = Path(os.path.expanduser(state_root))
    return [
        root / "instance" / "state" / "ledger.jsonl",
        root / "state" / "ledger.jsonl",
        root / "ledger.jsonl",
    ]


def _latest_harness_failure(state_root: str, loop_id: str,
                            event: dict | None) -> dict | None:
    """Project the latest same-run harness failure for a continuous owner.

    A running process is not sufficient evidence of health.  This projection is
    deliberately read-only and owner/run/release bound.  A later clean ledger
    wake marks the failure inactive while retaining it as diagnostic history.
    """
    if not isinstance(event, dict) or event.get("status") != "running":
        return None
    run_id = event.get("run_id")
    release_sha = event.get("release_sha")
    if not isinstance(run_id, str) or not isinstance(release_sha, str):
        return None
    failures: list[dict] = []
    for path in _harness_failure_paths(state_root):
        for row in _private_jsonl_rows(path):
            intent = row.get("recovery_intent")
            if not isinstance(intent, dict):
                continue
            if (intent.get("loop_id") != loop_id or intent.get("run_id") != run_id
                    or intent.get("release_sha") != release_sha):
                continue
            if not isinstance(row.get("ts"), (int, float)):
                continue
            failures.append(row)
    if not failures:
        return None
    failure = max(failures, key=lambda row: row["ts"])
    intent = failure.get("recovery_intent") or {}
    layer = str(failure.get("layer") or "unknown")
    detail = str(failure.get("detail") or "")
    lowered = detail.lower()
    if layer == "brain_transport" and ("429" in lowered or "rate" in lowered):
        error_class = "provider_rate_limit"
    elif layer == "tool_logic" and "enoent" in lowered:
        error_class = "tool_missing"
    else:
        error_class = layer
    clean_after = False
    for path in _ledger_paths(state_root):
        for row in _private_jsonl_rows(path):
            if (isinstance(row.get("ts"), (int, float))
                    and row["ts"] > failure["ts"]
                    and row.get("kind") in {"wake", "narrate"}):
                clean_after = True
                break
        if clean_after:
            break
    evidence_refs = intent.get("evidence_refs")
    if not isinstance(evidence_refs, list):
        evidence_refs = []
    return {
        "active": not clean_after,
        "kind": failure.get("kind"),
        "layer": layer,
        "error_class": error_class,
        "detail": detail[:4000],
        "wake_id": failure.get("wake_id"),
        "run_id": run_id,
        "release_sha": release_sha,
        "retryable": intent.get("retryable") is True,
        "next_action": intent.get("action") or "reconcile_owner",
        "blocker": f"harness_failure:{error_class}",
        "evidence_refs": [ref for ref in evidence_refs if isinstance(ref, str)][:32],
        "ts": failure["ts"],
    }


def _atomic_private_json(path: Path, value: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _pre_effect_admission_proof(loop_id: str, entry: dict) -> tuple[str, str, dict] | None:
    """Prove one exact old fence stopped in host admission before entrypoint."""
    database = admission_root() / "admission-v2.sqlite3"
    with sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True) as connection:
        rows = connection.execute(
            """SELECT occurrence_id,state FROM occurrences
                 WHERE owner_id=? AND effect_unknown=1
                 ORDER BY queued_at,occurrence_id""",
            (loop_id,),
        ).fetchall()
    if len(rows) != 1:
        return None
    occurrence_id, expected_state = rows[0]
    prefix = f"{loop_id}:"
    if (expected_state not in {"claimed", "released"}
            or not isinstance(occurrence_id, str)
            or not SAFE_OCCURRENCE.fullmatch(occurrence_id)
            or not occurrence_id.startswith(prefix)):
        return None
    run_id = occurrence_id[len(prefix):]
    state_root = entry.get("state_root")
    if not isinstance(state_root, str) or not state_root:
        return None
    try:
        root = Path(os.path.expanduser(state_root))
        journals = [root / "events.jsonl", *sorted(
            root.glob("events-*.jsonl.gz"), reverse=True,
        )[:MAX_PRE_EFFECT_ARCHIVES]]
        runtime_rows = [
            row for journal in journals for row in _private_runtime_rows(journal)
        ]
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return None
    exact = [row for row in runtime_rows
             if row.get("loop_id") == loop_id and row.get("run_id") == run_id]
    starts = [row for row in exact
              if row.get("phase") == "execute" and row.get("status") == "running"
              and row.get("effect_status") == "started"]
    terminals = [row for row in exact
                 if row.get("phase") == "report" and row.get("status") == "blocked"]
    if len(exact) != 2 or len(starts) != 1 or len(terminals) != 1:
        return None
    start, terminal = starts[0], terminals[0]
    summary_ref = f"lm-loop://{loop_id}/{run_id}/summary.json"
    evidence_refs = terminal.get("evidence_refs", [])
    if (terminal.get("blocker") not in PRE_EFFECT_ADMISSION_BLOCKERS
            or terminal.get("effect_status") != "unknown"
            or summary_ref not in start.get("evidence_refs", [])
            or summary_ref not in evidence_refs
            or any(isinstance(ref, str) and ref.startswith("lm-effect://")
                   for ref in evidence_refs)):
        return None
    try:
        if _event_epoch(start.get("timestamp")) > _event_epoch(terminal.get("timestamp")):
            return None
    except ValueError:
        return None
    proof = {
        "owner_id": loop_id,
        "occurrence_id": occurrence_id,
        "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": f"lm-event://{loop_id}/{run_id}/{terminal['event_id']}",
        "blocker": terminal["blocker"],
    }
    return occurrence_id, expected_state, proof


def _resolve_pre_effect_admission_unknown(loop_id: str, entry: dict) -> bool:
    proof_row = _pre_effect_admission_proof(loop_id, entry)
    if proof_row is None:
        return False
    occurrence_id, expected_state, proof = proof_row
    state_root = Path(os.path.expanduser(entry["state_root"]))
    run_id = occurrence_id[len(loop_id) + 1:]
    receipt_path = state_root / "reconciliation" / f"pre-effect-{run_id}.json"
    receipt = {
        "schema_version": 1,
        "receipt_type": "HOST_PRE_EFFECT_RECONCILIATION",
        "resolution": "PROOF_READY",
        **proof,
    }
    _atomic_private_json(receipt_path, receipt)
    resolved = resolve_pre_effect_occurrence(
        loop_id, occurrence_id, pre_effect_readback=lambda: proof,
        expected_state=expected_state,
    )
    if resolved:
        _atomic_private_json(receipt_path, {**receipt, "resolution": "RESOLVED"})
    return resolved


def _product_loop_job_map(catalog_path: Path | None = None) -> dict[str, str]:
    path = catalog_path or ROOT / "apps/life-manager/config/product-loop-catalog.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    loops = value.get("loops") if isinstance(value, dict) else None
    if not isinstance(loops, list):
        return {}
    result: dict[str, str] = {}
    duplicates: set[str] = set()
    for loop in loops:
        if (not isinstance(loop, dict) or not isinstance(loop.get("id"), str)
                or not isinstance(loop.get("job_ids"), list)):
            continue
        for job_id in loop["job_ids"]:
            if not isinstance(job_id, str):
                continue
            if job_id in result:
                duplicates.add(job_id)
            else:
                result[job_id] = loop["id"]
    for job_id in duplicates:
        result.pop(job_id, None)
    return result


def _pending_admission_owners() -> set[str]:
    database = admission_root() / "admission-v2.sqlite3"
    try:
        database.stat()
    except FileNotFoundError:
        return set()
    with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True, timeout=1) as connection:
        return {owner_id for (owner_id,) in connection.execute(
            """SELECT owner_id FROM occurrences WHERE state='claimed'
               UNION
               SELECT o.owner_id FROM occurrences o
                 JOIN queue q ON q.owner_id=o.owner_id
               WHERE o.state='queued' AND o.effect_unknown=0""")}


def _entry_effect_scope(entry: dict) -> str:
    return admission_effect_scope(entry)


def _pending_admission_policy_mismatches(registry: dict) -> set[str]:
    """Return effect-free queued owners whose durable policy differs from registry."""
    expected_by_owner = {}
    for owner_id, entry in registry.get("loops", {}).items():
        expected = (
            entry.get("resource_class"), entry.get("admission_class"),
            entry.get("priority"), ADMISSION_POLICY, _entry_effect_scope(entry),
        )
        if all(isinstance(value, str) and value for value in expected[:3]):
            expected_by_owner[owner_id] = expected
    if not expected_by_owner:
        return set()
    database = admission_root() / "admission-v2.sqlite3"
    try:
        database.stat()
    except FileNotFoundError:
        return set()
    with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True, timeout=1) as connection:
        rows = connection.execute(
            """SELECT q.owner_id,q.resource_class,p.admission_class,p.base_priority,
                      p.admission_policy,p.effect_scope,p.effect_unknown,
                      EXISTS (
                          SELECT 1 FROM occurrences claimed
                          WHERE claimed.owner_id=q.owner_id
                            AND claimed.state='claimed'
                            AND claimed.effect_unknown=0
                      ),
                      EXISTS (
                          SELECT 1 FROM occurrences uncertain
                          WHERE uncertain.owner_id=q.owner_id
                            AND uncertain.effect_unknown=1
                      )
               FROM queue q JOIN priorities p ON p.owner_id=q.owner_id
               WHERE EXISTS (
                   SELECT 1 FROM occurrences o
                   WHERE o.owner_id=q.owner_id
                     AND o.state='queued' AND o.effect_unknown=0
               )"""
        ).fetchall()
    mismatches = set()
    for (owner_id, resource_class, admission_class, priority, policy, effect_scope,
         priority_effect_unknown, claimed, occurrence_effect_unknown) in rows:
        expected = expected_by_owner.get(owner_id)
        if expected is None:
            continue
        expected_resource, *_rest, expected_effect_scope = expected
        if resource_class != expected_resource:
            continue
        if (priority_effect_unknown or claimed
                or (expected_effect_scope == "owner" and occurrence_effect_unknown)):
            continue
        if (resource_class, admission_class, priority, policy, effect_scope) != expected:
            mismatches.add(owner_id)
    return mismatches


def _admission_effect_unknown_owners() -> set[str]:
    """Read current effect fences so status does not trust a stale terminal event."""
    database = admission_root() / "admission-v2.sqlite3"
    try:
        database.stat()
    except FileNotFoundError:
        return set()
    try:
        with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True, timeout=1) as connection:
            return {
                owner_id for (owner_id,) in connection.execute(
                    "SELECT DISTINCT owner_id FROM occurrences WHERE effect_unknown=1"
                )
            }
    except sqlite3.Error:
        return set()


@contextmanager
def _admission_rebind_guard(
    loop_id: str,
    enabled: bool,
    *,
    entry: dict | None = None,
    item: dict | None = None,
    release_sha: str | None = None,
    launchctl_safe: Path | None = None,
    replace_reserved_policy_drift: bool = False,
    allow_reserved_release_rebind: bool = False,
):
    if not enabled:
        yield None
        return
    with owner_deploy_lock(loop_id) as acquired:
        if not acquired:
            raise RuntimeError("owner deploy busy")
        pending = loop_id in _pending_admission_owners()
        if not pending:
            yield None
            return
        loaded_idle_verified = False
        if item is not None and release_sha and launchctl_safe:
            skipped = _skip_if_not_loaded_idle(item, release_sha, launchctl_safe)
            if skipped is not None and skipped.get("skipped") != "unloaded":
                yield skipped
                return
            loaded_idle_verified = skipped is None
        if loop_id in CONTROL_PLANE_SAFETY_LOOPS:
            if entry is None or entry.get("effect_class") != "none":
                raise RuntimeError("control-plane safety loop must be effect-free")
            result = cancel_effect_free_queued_owner(loop_id)
            if result in {"cancelled", "not_queued"}:
                yield None
                return
            yield "pending"
            return
        admission_class = entry.get("admission_class") if entry else None
        resource_class = entry.get("resource_class") if entry else None
        priority = entry.get("priority") if entry else None
        if not all(isinstance(value, str) and value for value in (
                admission_class, resource_class, priority)):
            # Legacy registry rows retain the old pending-admission skip contract.
            yield "pending"
            return
        rebind_kwargs = {
            "resource_class": resource_class,
            "admission_class": admission_class,
            "priority": priority,
        }
        if replace_reserved_policy_drift:
            rebind_kwargs["replace_reserved_policy_drift"] = True
        if _entry_effect_scope(entry) == "occurrence":
            rebind_kwargs["effect_scope"] = "occurrence"
        result = rebind_queued_owner(loop_id, **rebind_kwargs)
        if (result == "effect_unknown" and loaded_idle_verified
                and entry.get("effect_class") == "none"):
            clear_no_effect_unknown(loop_id)
            result = rebind_queued_owner(loop_id, **rebind_kwargs)
        elif (result == "effect_unknown" and loaded_idle_verified
              and _resolve_pre_effect_admission_unknown(loop_id, entry)):
            result = rebind_queued_owner(loop_id, **rebind_kwargs)
        if result == "reserved":
            if allow_reserved_release_rebind and loaded_idle_verified:
                # The reservation names only this owner and its preserved FIFO
                # occurrence. Repointing an idle owner lets the dispatcher start
                # that same reservation from the current immutable release.
                yield None
                return
            # Keep the old release paired with its reserved admission policy.
            # The next reconciler pass can rebind after the lease expires.
            yield "pending"
            return
        if result == "not_queued":
            # A drained queue row has no policy to migrate.
            if loaded_idle_verified and entry.get("effect_class") == "none":
                clear_no_effect_unknown(loop_id)
            yield None
            return
        if result not in {"rebound", "unchanged"}:
            raise RuntimeError(f"admission rebind refused: {result}")
        yield None


def _next_eligible(cadence: dict) -> str:
    key, value = next(iter(cadence.items()))
    if key == "start_interval_seconds":
        return f"interval:{value}s"
    if key == "calendar_interval":
        return "calendar:" + json.dumps(value, sort_keys=True, separators=(",", ":"))
    return key.replace("_", "-")


def status_rows(registry: dict, *, loaded: dict, disabled: dict, events: dict,
                installed_releases: dict,
                admission_effect_unknown: set[str] | None = None,
                product_by_job: dict[str, str] | None = None) -> list[dict]:
    validate_registry(registry)
    product_by_job = _product_loop_job_map() if product_by_job is None else product_by_job
    rows = []
    for loop_id in sorted(registry["loops"]):
        entry = registry["loops"][loop_id]
        label = entry["label"]
        runtime = loaded.get(label)
        if disabled.get(label):
            launchd_state = "disabled"
        elif runtime:
            launchd_state = "loaded-running" if runtime.get("pid") else "loaded-idle"
        else:
            launchd_state = "unloaded"
        event = events.get(loop_id) or {}
        current_effect_unknown = (
            None if admission_effect_unknown is None
            else loop_id in admission_effect_unknown
        )
        stale_event = None
        blocker = event.get("blocker")
        if (
            admission_effect_unknown is not None
            and current_effect_unknown is False
            and blocker == "host_admission_deferred:resource_effect_unknown"
        ):
            stale_event = "resource_effect_unknown_resolved"
            blocker = None
        missing_diagnostic_fields = sorted(DIAGNOSTIC_FIELDS - set(event))
        catalog_product_loop_id = product_by_job.get(loop_id)
        event_product_loop_id = event.get("product_loop_id")
        diagnostic_error = None
        if event.get("job_id") is not None and event.get("job_id") != loop_id:
            diagnostic_error = "event_job_identity_mismatch"
        elif (catalog_product_loop_id is not None and event_product_loop_id is not None
              and event_product_loop_id != catalog_product_loop_id):
            diagnostic_error = "event_product_identity_mismatch"
        diagnostic_complete = not missing_diagnostic_fields and diagnostic_error is None
        latest_harness_failure = _latest_harness_failure(entry["state_root"], loop_id, event)
        active_harness_failure = (
            latest_harness_failure if latest_harness_failure
            and latest_harness_failure.get("active") is True else None
        )
        last_terminal_result = event.get("status")
        failure_layer = event.get("failure_layer")
        error_class = event.get("error_class")
        retryable = event.get("retryable")
        next_action = event.get("next_action")
        if active_harness_failure is not None:
            # Keep launchd/process identity separate from health: a continuous
            # process can be alive while its latest wake is failing.
            last_terminal_result = "fail"
            failure_layer = "runtime"
            error_class = active_harness_failure["error_class"]
            retryable = active_harness_failure["retryable"]
            next_action = active_harness_failure["next_action"]
            blocker = active_harness_failure["blocker"]
        rows.append({
            "classification": "managed",
            "owner": "life-manager",
            "desired_mode": "continuous" if "keep_alive" in entry["cadence"] else "scheduled",
            "loop_id": loop_id,
            "label": label,
            "domain": entry["domain"],
            "launchd_state": launchd_state,
            "pid": runtime.get("pid") if runtime else None,
            "last_exit": runtime.get("last_exit") if runtime else None,
            "installed_release_sha": installed_releases.get(label),
            "provider_route": entry["provider_route"],
            "provider": event.get("provider"),
            "profile_alias": event.get("profile_alias"),
            "event_id": event.get("event_id"),
            "product_loop_id": catalog_product_loop_id or event_product_loop_id,
            "job_id": loop_id,
            "owner_id": event.get("owner_id"),
            "run_id": event.get("run_id"),
            "wake_id": event.get("wake_id"),
            "occurrence_id": event.get("occurrence_id"),
            "phase": event.get("phase"),
            "loaded_argv_sha256": event.get("loaded_argv_sha256"),
            "loaded_env_sha256": event.get("loaded_env_sha256"),
            "exit_code": event.get("exit_code"),
            "failure_layer": failure_layer,
            "error_class": error_class,
            "retryable": retryable,
            "next_action": next_action,
            "provider_receipt_id": event.get("provider_receipt_id"),
            "official_readback_ref": event.get("official_readback_ref"),
            "evidence_refs": event.get("evidence_refs"),
            "diagnostic_complete": diagnostic_complete,
            "diagnostic_missing_fields": missing_diagnostic_fields,
            "diagnostic_error": diagnostic_error,
            "last_pass": event.get("timestamp"),
            "last_terminal_result": last_terminal_result,
            "effect_class": entry["effect_class"],
            "effect_status": event.get("effect_status", "unknown"),
            "event_release_sha": event.get("release_sha"),
            "next_eligible_run": _next_eligible(entry["cadence"]),
            "blocker": blocker,
            "admission_effect_unknown": current_effect_unknown,
            "stale_event": stale_event,
            "latest_harness_failure": latest_harness_failure,
        })
    return rows


def resolver_rows(registry: dict, *, loaded: dict, disabled: dict, events: dict,
                    installed_releases: dict, installed_labels: set[str],
                    admission_effect_unknown: set[str] | None = None) -> list[dict]:
    rows = status_rows(
        registry,
        loaded=loaded,
        disabled=disabled,
        events=events,
        installed_releases=installed_releases,
        admission_effect_unknown=admission_effect_unknown,
    )
    managed = {entry["label"] for entry in registry["loops"].values()}
    external = set(registry.get("external_labels", []))
    retired = set(registry.get("retired_labels", []))
    labels = external | retired | installed_labels | {
        label for label in loaded if label.startswith("ai.anicca.")
    }
    for label in sorted(labels - managed):
        runtime = loaded.get(label)
        classification = (
            "retired" if label in retired else
            "external" if label in external else
            "unmanaged"
        )
        if disabled.get(label):
            launchd_state = "disabled"
        elif runtime:
            launchd_state = "loaded-running" if runtime.get("pid") else "loaded-idle"
        else:
            launchd_state = "unloaded"
        present = bool(runtime or label in installed_labels)
        rows.append({
            "classification": classification,
            "owner": "external" if classification == "external" else (
                "retired" if classification == "retired" else "unknown"),
            "desired_mode": classification,
            "loop_id": label,
            "label": label,
            "domain": None,
            "launchd_state": launchd_state,
            "pid": runtime.get("pid") if runtime else None,
            "last_exit": runtime.get("last_exit") if runtime else None,
            "installed_release_sha": installed_releases.get(label),
            "provider_route": None,
            "provider": None,
            "profile_alias": None,
            "event_id": None,
            "product_loop_id": None,
            "job_id": label,
            "owner_id": None,
            "run_id": None,
            "wake_id": None,
            "occurrence_id": None,
            "phase": None,
            "loaded_argv_sha256": None,
            "loaded_env_sha256": None,
            "exit_code": None,
            "failure_layer": None,
            "error_class": None,
            "retryable": None,
            "next_action": None,
            "provider_receipt_id": None,
            "official_readback_ref": None,
            "evidence_refs": None,
            "diagnostic_complete": False,
            "diagnostic_missing_fields": sorted(DIAGNOSTIC_FIELDS),
            "diagnostic_error": None,
            "last_pass": None,
            "last_terminal_result": None,
            "effect_class": "unknown",
            "effect_status": "unknown",
            "event_release_sha": None,
            "next_eligible_run": None,
            "blocker": (
                "retired_still_present" if classification == "retired" and present else
                "unmanaged_label" if classification == "unmanaged" else None),
        })
    return sorted(rows, key=lambda row: row["label"])


def doctor_report(registry: dict, *, installed_labels: set[str], loaded_labels: set[str],
                  existing_entrypoints: set[str]) -> dict:
    validate_registry(registry)
    retired = set(registry.get("retired_labels", []))
    managed = ({entry["label"] for entry in registry["loops"].values()}
               | set(registry.get("external_labels", [])) | retired)
    unmanaged = sorted((installed_labels | loaded_labels) - managed)
    missing = sorted(
        f"{loop_id}:{entry['entrypoint']}"
        for loop_id, entry in registry["loops"].items()
        if entry["entrypoint"] not in existing_entrypoints
    )
    return {
        "ok": not unmanaged and not missing and not ((installed_labels | loaded_labels) & retired),
        "registry_entries": len(registry["loops"]),
        "unmanaged_labels": unmanaged,
        "missing_entrypoints": missing,
        "retired_installed_labels": sorted((installed_labels | loaded_labels) & retired),
    }


def _launchctl(*args: str) -> str:
    with tempfile.TemporaryFile(mode="w+") as stdout, tempfile.TemporaryFile(mode="w+") as stderr:
        result = subprocess.run(
            ["launchctl", *args], stdout=stdout, stderr=stderr, text=True, timeout=15)
        stdout.seek(0)
        stderr.seek(0)
        output, error = stdout.read(), stderr.read()
    if result.returncode:
        raise RuntimeError(error.strip() or "launchctl failed")
    return output


def _last_event(state_root: str, loop_id: str | None = None,
                cache: dict[Path, dict[str | None, dict]] | None = None,
                running_pid: str | None = None) -> dict | None:
    path = Path(os.path.expanduser(state_root)) / "events.jsonl"
    if running_pid is None and cache is not None and path in cache:
        cached = cache[path]
        # A targeted scan stores only the requested loop.  The ``None`` key
        # is populated only by a complete scan, so it is the signal that a
        # missing loop id is a cached miss rather than an unscanned one.
        if loop_id in cached or None in cached:
            return cached.get(loop_id)
    reports: dict[str | None, dict] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in reversed(lines):
        try:
            value = json.loads(line)
            validate_runtime_event(value)
        except (json.JSONDecodeError, ValueError):
            continue
        pid_bound_running = (
            running_pid is not None
            and value.get("phase") == "execute"
            and value.get("status") == "running"
            and value.get("job_id") is not None
            and str(value.get("run_id", "")).endswith(f"-{running_pid}")
        )
        if value.get("phase") != "report" and not pid_bound_running:
            continue
        if loop_id is not None and value.get("loop_id") == loop_id:
            if cache is not None:
                cache.setdefault(path, {})[loop_id] = value
            return value
        reports.setdefault(None, value)
        reports.setdefault(value.get("loop_id"), value)
    if cache is not None:
        cache[path] = reports
    return reports.get(loop_id)


def _release_from_plist(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            plist = plistlib.load(handle)
    except Exception:
        return None
    release_sha = str((plist.get("EnvironmentVariables") or {}).get(
        "LIFE_MANAGER_RELEASE_SHA") or "")
    if re.fullmatch(r"[0-9a-f]{40}", release_sha):
        return release_sha
    args = list(map(str, plist.get("ProgramArguments") or []))
    release = extract_release(" ".join(args))
    if release:
        return release
    for arg in args:
        candidate = Path(os.path.expanduser(arg))
        try:
            if candidate.exists():
                release = extract_release(str(candidate.resolve()))
        except OSError:
            continue
        if release:
            return release
    return None


def _state_root_from_plist(path: Path, fallback: str) -> str:
    try:
        with path.open("rb") as handle:
            plist = plistlib.load(handle)
        value = (plist.get("EnvironmentVariables") or {}).get("LIFE_MANAGER_STATE_ROOT")
        if isinstance(value, str) and Path(value).is_absolute():
            return value
    except Exception:
        pass
    return os.path.expanduser(fallback)


def collect_live(registry: dict, *, full_inventory: bool = True
                 ) -> tuple[dict, dict, dict, set[str], set[str]]:
    loaded = parse_loaded(_launchctl("list"))
    disabled = parse_disabled(_launchctl("print-disabled", f"gui/{os.getuid()}"))
    plist_dir = Path.home() / "Library/LaunchAgents"
    installed_paths = (list(plist_dir.glob("ai.anicca.*.plist")) if full_inventory else [
        plist_dir / f"{entry['label']}.plist" for entry in registry["loops"].values()
        if (plist_dir / f"{entry['label']}.plist").is_file()
    ])
    installed = {path.stem for path in installed_paths}
    releases, events = {}, {}
    for path in installed_paths:
        releases[path.stem] = _release_from_plist(path)
    event_cache: dict[Path, dict[str | None, dict]] = {}
    for loop_id, entry in registry["loops"].items():
        label = entry["label"]
        plist_path = plist_dir / f"{label}.plist"
        releases[label] = _release_from_plist(plist_path)
        event = _last_event(
            _state_root_from_plist(plist_path, entry["state_root"]), loop_id, event_cache,
            running_pid=(loaded.get(label) or {}).get("pid")
            if entry.get("cadence", {}).get("keep_alive") is True else None,
        )
        if event:
            events[loop_id] = event
    return loaded, disabled, events, releases, installed


def _select(rows: list[dict], target: str) -> list[dict]:
    if target == "all":
        return rows
    selected = [row for row in rows if row["loop_id"] == target]
    if not selected:
        raise ValueError(f"unknown loop id: {target}")
    return selected


def _loaded_sha_is_ancestor(installed_sha: str, current_sha: str) -> bool:
    source = Path(os.environ.get(
        "LIFE_MANAGER_SOURCE_REPO", "~/Projects/life-manager-main")).expanduser()
    try:
        result = subprocess.run(
            ["git", "-C", str(source), "merge-base", "--is-ancestor",
             installed_sha, current_sha],
            capture_output=True, check=False, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _recoverable_env_snapshot_sha(plist_path: Path, loop_id: str, entry: dict,
                                  release_root: Path, current_sha: str) -> str | None:
    """Read the old SHA only after the shared apply path accepts this owner's JSON."""
    try:
        old_bytes = plist_path.read_bytes()
        env = json.loads(old_bytes)
        rendered = _plist(loop_id, entry, release_root, current_sha)
        _preserve_operational_attributes(rendered, old_bytes)
    except (OSError, ValueError, RuntimeError, KeyError, plistlib.InvalidFileException):
        return None
    sha = env.get("LIFE_MANAGER_RELEASE_SHA")
    return sha if isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha) else None


def _bounded_reconcile_candidates(registry: dict, route: str,
                                  current_sha: str, max_owners: int,
                                  skipped_non_ancestor: list[str] | None = None) -> set[str]:
    """Inspect the finite registry so an ineligible prefix cannot hide later owners."""
    agents_dir = Path(os.environ.get(
        "LIFE_MANAGER_LAUNCH_AGENTS_DIR", "~/Library/LaunchAgents")).expanduser()
    candidates: list[str] = []
    automatic = os.environ.get("LIFE_MANAGER_LOOP_ID") == "life-manager-release-reconciler"
    ancestry: dict[str, bool] = {}
    for loop_id, entry in sorted(registry["loops"].items()):
        if entry.get("provider_route") != route:
            continue
        plist_path = agents_dir / f"{entry['label']}.plist"
        installed_sha = _release_from_plist(plist_path)
        if installed_sha and installed_sha != current_sha:
            if automatic:
                if installed_sha not in ancestry:
                    ancestry[installed_sha] = _loaded_sha_is_ancestor(
                        installed_sha, current_sha)
                if not ancestry[installed_sha]:
                    if skipped_non_ancestor is not None:
                        skipped_non_ancestor.append(loop_id)
                    continue
            candidates.append(loop_id)
    return set(candidates)


def snapshot(registry: dict, target: str) -> list[dict]:
    if target != "all" and target in registry["loops"]:
        selected_registry = {**registry, "loops": {target: registry["loops"][target]}}
        loaded, disabled, events, releases, _ = collect_live(
            selected_registry, full_inventory=False)
        return status_rows(
            selected_registry, loaded=loaded, disabled=disabled, events=events,
            installed_releases=releases,
            admission_effect_unknown=_admission_effect_unknown_owners())
    loaded, disabled, events, releases, installed = collect_live(registry)
    rows = resolver_rows(
        registry, loaded=loaded, disabled=disabled, events=events,
        installed_releases=releases, installed_labels=installed,
        admission_effect_unknown=_admission_effect_unknown_owners())
    return _select(rows, target)


def _safe_launchctl(executable: Path, args: list[str]) -> tuple[int, str]:
    with tempfile.TemporaryFile(mode="w+") as output:
        result = subprocess.run(
            [str(executable), *args], stdout=output, stderr=output, text=True, timeout=30)
        output.seek(0)
        return result.returncode, output.read()


def targeted_snapshot(registry: dict, targets: set[str],
                      launchctl_safe: Path) -> list[dict]:
    """Read only explicitly requested services; never list the whole fleet."""
    disabled = parse_disabled(_launchctl("print-disabled", f"gui/{os.getuid()}"))
    plist_dir = Path.home() / "Library/LaunchAgents"
    rows = []
    for loop_id in sorted(targets):
        entry = registry["loops"][loop_id]
        label = entry["label"]
        rc, detail = _safe_launchctl(
            launchctl_safe, ["print", f"gui/{os.getuid()}/{label}"])
        absent = rc != 0 and bool(re.search(
            r"(?i)(?:could not find service|service not found|\babsent\b)", detail))
        if rc != 0 and not absent:
            raise RuntimeError(f"{label}: targeted launchd readback failed: {detail.strip()}")
        loaded = {}
        if rc == 0:
            pid = re.search(r"\bpid\s*=\s*([1-9][0-9]*)\b", detail)
            last_exit = re.search(r"\blast exit code\s*=\s*(-?[0-9]+)\b", detail)
            loaded[label] = {
                "pid": pid.group(1) if pid else None,
                "last_exit": last_exit.group(1) if last_exit else None,
            }
        plist_path = plist_dir / f"{label}.plist"
        event = _last_event(
            _state_root_from_plist(plist_path, entry["state_root"]), loop_id,
            running_pid=(loaded.get(label) or {}).get("pid")
            if entry.get("cadence", {}).get("keep_alive") is True else None,
        )
        selected_registry = {**registry, "loops": {loop_id: entry}}
        rows.extend(status_rows(
            selected_registry,
            loaded=loaded,
            disabled={label: disabled.get(label, False)},
            events={loop_id: event} if event else {},
            installed_releases={label: _release_from_plist(plist_path)},
            admission_effect_unknown=_admission_effect_unknown_owners(),
        ))
    return rows


@contextmanager
def _apply_lock(current: Path, lock_path: Path | None):
    lock_path = Path(lock_path or current.parent / ".apply.lock").expanduser()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.fchmod(lock_fd, 0o600)
        with os.fdopen(lock_fd, "a+") as owner_lock:
            lock_fd = -1
            try:
                fcntl.flock(owner_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("production apply is already owned") from exc
            yield
    finally:
        if lock_fd >= 0:
            os.close(lock_fd)


def _label_apply_lock_path(current: Path, label: str,
                           lock_path: Path | None = None) -> Path:
    base = Path(lock_path).expanduser() if lock_path else current.parent / ".apply-locks"
    return (base / f"{label}.lock" if lock_path is None else
            base.with_name(f"{base.name}.{label}.lock"))


@contextmanager
def _protocol_transition_lock(current: Path, *, exclusive: bool):
    path = current.parent / ".admission-protocol.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield
    finally:
        os.close(descriptor)


def _protocol_v1() -> int:
    return 1


def _service_is_running(detail: str) -> bool:
    return bool(re.search(r"\bstate\s*=\s*running\b|\bpid\s*=\s*[1-9][0-9]*\b",
                          detail))


def _skip_if_not_loaded_idle(item: dict, release_sha: str,
                             launchctl_safe: Path) -> dict | None:
    rc, printed = _safe_launchctl(
        launchctl_safe, ["print", f"gui/{os.getuid()}/{item['label']}"])
    if rc != 0:
        return {"ok": True, "label": item["label"], "loaded": False,
                "loaded_arguments": [], "release_sha": release_sha,
                "changed": False, "skipped": "unloaded"}
    if not _service_is_running(printed):
        return None
    return {"ok": True, "label": item["label"], "loaded": True,
            "loaded_arguments": _loaded_arguments(printed),
            "release_sha": release_sha, "changed": False,
            "skipped": "loaded-running"}


def _retire_labels(registry: dict, agents_dir: Path, launchctl_safe: Path,
                   current: Path, lock_path: Path | None,
                   labels: list[str] | None = None) -> list[dict]:
    results = []
    domain = f"gui/{os.getuid()}"
    selected = labels if labels is not None else registry.get("retired_labels", [])
    for label in sorted(selected):
        with _apply_lock(current, _label_apply_lock_path(current, label, lock_path)):
            service = f"{domain}/{label}"
            present_rc, present_detail = _safe_launchctl(launchctl_safe, ["print", service])
            absent = present_rc != 0 and bool(re.search(
                r"(?i)(?:could not find service|service not found|\babsent\b)", present_detail))
            if present_rc != 0 and not absent:
                raise RuntimeError(
                    f"{label}: retirement presence readback failed: {present_detail.strip()}")
            if present_rc == 0:
                bootout_rc, detail = _safe_launchctl(launchctl_safe, ["bootout", service])
                if bootout_rc != 0:
                    raise RuntimeError(f"{label}: retirement bootout failed: {detail.strip()}")
                for attempt in range(50):
                    verify_rc, verify_detail = _safe_launchctl(
                        launchctl_safe, ["print", service])
                    if verify_rc != 0:
                        if not re.search(
                                r"(?i)(?:could not find service|service not found|\babsent\b)",
                                verify_detail):
                            raise RuntimeError(
                                f"{label}: retirement absence readback failed: "
                                f"{verify_detail.strip()}")
                        break
                    if attempt == 49:
                        raise RuntimeError(f"{label}: retirement readback still loaded")
                    time.sleep(0.1)
            plist = agents_dir / f"{label}.plist"
            removed = plist.is_file()
            if removed:
                plist.unlink()
            results.append({"ok": True, "label": label, "retired": True,
                            "was_loaded": present_rc == 0,
                            "removed_plist": removed})
    return results


def _supports_durable_admission_v2(release_root: Path) -> bool:
    try:
        value = json.loads(
            (release_root / "config/runtime-capabilities.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return isinstance(value, dict) and value.get("resource_admission") == 2


def _loaded_v2_release(arguments: list[str], loop_id: str) -> bool:
    if len(arguments) != 3 or arguments[1] != loop_id:
        return False
    try:
        loaded_root = Path(arguments[2]).resolve(strict=True)
    except OSError:
        return False
    return (
        arguments[0] == str(loaded_root / "bin/lm-loop-run")
        and arguments[2] == str(loaded_root)
        and _supports_durable_admission_v2(loaded_root)
    )


def activate_current(current: Path, release_root: Path,
                     lock_path: Path | None = None, *,
                     protocol_reader: Callable[[], int] = _protocol_v1) -> None:
    current = Path(current).expanduser()
    release_root = Path(release_root).expanduser()
    with _protocol_transition_lock(current, exclusive=True):
        with _apply_lock(current, lock_path):
            release_root = release_root.resolve(strict=True)
            if not release_root.is_dir():
                raise ValueError("release root is not a directory")
            if (protocol_reader() == 2
                    and not _supports_durable_admission_v2(release_root)):
                raise RuntimeError("target release does not support durable admission v2")
            current.parent.mkdir(parents=True, exist_ok=True)
            swap = current.with_name(current.name + ".swap")
            swap.unlink(missing_ok=True)
            swap.symlink_to(release_root)
            try:
                os.replace(swap, current)
            finally:
                swap.unlink(missing_ok=True)


def activate_durable_admission_live(
        registry: dict, release_root: Path, launchctl_safe: Path, *,
        current: Path | None = None,
        agents_dir: Path | None = None) -> dict[str, object]:
    """Enable v2 only when every finite owner uses a v2-capable release."""
    validate_registry(registry)
    release_root = release_root.resolve(strict=True)
    if not _supports_durable_admission_v2(release_root):
        raise RuntimeError("release does not support durable admission v2")
    current = Path(current or "~/loops/current").expanduser()
    agents_dir = Path(agents_dir or "~/Library/LaunchAgents").expanduser()
    with _protocol_transition_lock(current, exclusive=True):
        with _apply_lock(current, None):
            preflight_rc, detail = _safe_launchctl(launchctl_safe, ["preflight"])
            if preflight_rc:
                raise RuntimeError(f"launchctl-safe preflight failed: {detail.strip()}")
            verified = 0
            for loop_id, entry in sorted(registry["loops"].items()):
                if entry.get("cadence", {}).get("keep_alive"):
                    continue
                rc, printed = _safe_launchctl(
                    launchctl_safe, ["print", f"gui/{os.getuid()}/{entry['label']}"])
                if rc != 0:
                    absent = bool(re.search(
                        r"(?i)(?:could not find service|service not found|\babsent\b)",
                        printed))
                    if not absent:
                        raise RuntimeError(
                            f"{loop_id}: loaded argv readback failed: {printed.strip()}")
                    plist_path = agents_dir / f"{entry['label']}.plist"
                    try:
                        with plist_path.open("rb") as handle:
                            plist = plistlib.load(handle)
                        arguments = list(map(str, plist.get("ProgramArguments") or []))
                    except (OSError, ValueError, plistlib.InvalidFileException):
                        arguments = []
                    if not _loaded_v2_release(arguments, loop_id):
                        raise RuntimeError(f"{loop_id}: installed plist is not v2-capable")
                    verified += 1
                    continue
                if not _loaded_v2_release(_loaded_arguments(printed), loop_id):
                    raise RuntimeError(f"{loop_id}: loaded argv is not v2-capable")
                verified += 1
            activate_durable_v2(allow_live_owners=True)
    return {"ok": True, "protocol": 2, "verified_finite_labels": verified}


def apply_live(release_root: Path, agents_dir: Path, launchctl_safe: Path,
               target: str | None = None, *, current: Path | None = None,
               lock_path: Path | None = None,
               preserve_unloaded: bool = False,
               skip_busy: bool = False,
               preserve_pending_admission: bool = False,
               replace_reserved_policy_drift: bool = False,
               allow_reserved_release_rebind: bool = False,
               reload_running: bool = False,
               require_current: bool = False,
               protocol_reader: Callable[[], int] = _protocol_v1,
               event_writer=append_runtime_event,
               _protocol_guarded: bool = False) -> list[dict]:
    current = Path(current or "~/loops/current").expanduser()
    if not _protocol_guarded:
        with _protocol_transition_lock(current, exclusive=False):
            return apply_live(
                release_root, agents_dir, launchctl_safe, target,
                current=current, lock_path=lock_path,
                preserve_unloaded=preserve_unloaded, skip_busy=skip_busy,
                preserve_pending_admission=preserve_pending_admission,
                replace_reserved_policy_drift=replace_reserved_policy_drift,
                allow_reserved_release_rebind=allow_reserved_release_rebind,
                reload_running=reload_running, require_current=require_current,
                protocol_reader=protocol_reader,
                event_writer=event_writer, _protocol_guarded=True,
            )
    release_root = release_root.resolve()
    if require_current and current.resolve(strict=True) != release_root:
        raise RuntimeError("release is no longer current")
    if (protocol_reader() == 2
            and not _supports_durable_admission_v2(release_root)):
        raise RuntimeError("target release does not support durable admission v2")
    registry = json.loads((release_root / "config/loop-registry.json").read_text())
    manifest = json.loads((release_root / "RELEASE.json").read_text())
    release_sha = manifest.get("sha")
    retired_target = target if target in set(registry.get("retired_labels", [])) else None
    plan = ([] if retired_target else
            apply_registry(registry, release_root, release_sha, lambda item: item, target=target))
    preflight_rc, detail = _safe_launchctl(launchctl_safe, ["preflight"])
    if preflight_rc:
        raise RuntimeError(f"launchctl-safe preflight failed: {detail.strip()}")
    results = (
        _retire_labels(registry, agents_dir, launchctl_safe, current, lock_path)
        if target is None else
        _retire_labels(
            registry, agents_dir, launchctl_safe, current, lock_path,
            labels=[retired_target],
        ) if retired_target else []
    )
    for item in plan:
        item_lock = (None if reload_running else
                     _label_apply_lock_path(current, item["label"], lock_path))
        try:
            with _apply_lock(current, item_lock), _admission_rebind_guard(
                    item["loop_id"], True,
                    entry=registry["loops"][item["loop_id"]],
                    item=item, release_sha=release_sha,
                    launchctl_safe=launchctl_safe,
                    replace_reserved_policy_drift=replace_reserved_policy_drift,
                    allow_reserved_release_rebind=allow_reserved_release_rebind,
            ) as pending_admission:
                if isinstance(pending_admission, dict):
                    results.append(pending_admission)
                    continue
                if pending_admission == "pending":
                    results.append({"ok": True, "label": item["label"],
                                    "release_sha": release_sha, "changed": False,
                                    "skipped": "pending-admission"})
                    continue
                # Old runners take this label lock before admission; the running
                # readback closes their first-upgrade gap before the new owner lock.
                if skip_busy or preserve_pending_admission:
                    skipped = _skip_if_not_loaded_idle(
                        item, release_sha, launchctl_safe)
                    if skipped is not None:
                        results.append(skipped)
                        continue
                target_path = agents_dir / f"{item['label']}.plist"
                result = None
                existing_bytes = target_path.read_bytes() if target_path.is_file() else None
                writer_loop_ids = {
                    "article-audit-7day", "article-daily", "article-healthcheck",
                    "article-learn-whitelist", "article-repair-candidate", "article-resume",
                    "article-self-improve",
                    "article-zenn-retry", "writer-claim-loop", "writer-craft-train",
                    "writer-money-sync", "writer-opportunity-discovery",
                    "writer-opportunity-response", "writer-report", "writer-sales-measure",
                }
                writer_retired_environment_keys = (
                    (
                        "ARTICLE_DAILY_LOG", "ARTICLE_MODEL_LOG", "GIG_LOG_DIR",
                        # These executable/provider overrides came from the retired
                        # gig Writer plist. Keep them out of the shared runner so a
                        # stale Claude binary cannot bypass the immutable release.
                        "ARTICLE_CLAUDE_BIN", "ARTICLE_CODEX_BIN",
                        "ARTICLE_CODEX_PROVIDER_API_KEY", "ARTICLE_MODEL_RUNNER",
                    )
                    if item["loop_id"] in writer_loop_ids else ()
                )
                retired_environment_keys = {
                    "affiliate-loop": ("AFFILIATE_LANDING_ROOT",),
                    "life-manager-cfo-hourly": ("LIFE_MANAGER_APP_DIR", "CFO_STATE_DIR"),
                    "life-manager-selfbuild": ("LM_SELFBUILD_REPO",),
                    "agentmail-webhook": (
                        "AGENTMAIL_QUEUE_PATH", "AGENTMAIL_DB_PATH",
                        "AGENTMAIL_ADAPTER_STATE_DIR", "AGENTMAIL_SEMANTIC_STATE_DIR",
                    ),
                    "agentmail-replier": (
                        "AGENTMAIL_QUEUE_PATH", "AGENTMAIL_DB_PATH",
                        "AGENTMAIL_ADAPTER_STATE_DIR", "AGENTMAIL_SEMANTIC_STATE_DIR",
                    ),
                    "agentmail-nudge": (
                        "AGENTMAIL_QUEUE_PATH", "AGENTMAIL_DB_PATH",
                        "AGENTMAIL_ADAPTER_STATE_DIR", "AGENTMAIL_SEMANTIC_STATE_DIR",
                    ),
                    "agent-economy-loop": (
                        "ANICCA_ECONOMY_CREATE_EVM_WALLET",
                        "ANICCA_RELEASE_ID",
                        "ANICCA_RELEASE_SHA",
                        "CEO_EFFECTIVE_CRON_DIR",
                    ),
                    "franklin-loop": (
                        "ANICCA_STATE_DIR", "FRANKLIN_PROXY_PORT", "OPENCLAW_ENV_FILE",
                    ),
                    "franklin2-loop": (
                        "ANICCA_STATE_DIR", "FRANKLIN_PROXY_PORT", "OPENCLAW_ENV_FILE",
                    ),
                    # These two lanes' plists were installed while they were still rendered
                    # from skills/earn/gig/config/launchd-jobs.json's legacy manifest, which
                    # explicitly set GIG_DISK_HEADROOM_KIB="0" for them (see gig_disk_guard.py's
                    # module comment). Now that they are lm-loop registry loops, _plist() never
                    # sets this key, so _preserve_operational_attributes carries that "0" forward
                    # forever unless it is named here. Dropping it lets the safe code default
                    # (524288 KiB) take over. hf-gig-storefront-direct is deliberately excluded:
                    # its frozen value was already 524288, so retiring it has no effect and only
                    # widens the blast radius of this change.
                    "hf-gig-apply-direct": ("GIG_DISK_HEADROOM_KIB",),
                    "hf-gig-reply-detector": ("GIG_DISK_HEADROOM_KIB",),
                    "pm-decision-loop": (
                        "ANICCA_HOME", "PM_TRADE_AGENT_HOME", "PKVAR",
                        "ANICCA_EVM_PRIVATE_KEY", "BASE_CHAIN_WALLET_KEY", "BLOCKRUN_WALLET_KEY",
                        "POLYGON_WALLET_PRIVATE_KEY",
                    ),
                    "pm-live-trade": (
                        "ANICCA_HOME", "PM_TRADE_AGENT_HOME", "PKVAR",
                        "ANICCA_EVM_PRIVATE_KEY", "BASE_CHAIN_WALLET_KEY", "BLOCKRUN_WALLET_KEY",
                        "POLYGON_WALLET_PRIVATE_KEY",
                    ),
                    "realtime-guide": (
                        "ANICCA_HOME", "OPENCLAW_ENV_FILE", "REALTIME_GUIDE_STATE_DIR",
                    ),
                    # The reconciler's source checkout is derived from the current
                    # release runner's default. Preserve only the immutable release
                    # and state identity; an old checkout path can disappear and
                    # otherwise turns every reconcile wake into exit 128.
                    "life-manager-release-reconciler": ("LIFE_MANAGER_SOURCE_REPO",),
                    "lateness-heartbeat": (
                        "ANICCA_HOME", "OPENCLAW_ENV_FILE",
                    ),
                }.get(item["loop_id"], writer_retired_environment_keys)
                retired_operational_keys = (
                    ("WorkingDirectory",)
                    if item["loop_id"] in {"life-manager-cfo-hourly", "realtime-guide"} else ()
                )
                desired_bytes = _preserve_operational_attributes(
                    item["plist_bytes"], existing_bytes,
                    retired_environment_keys=retired_environment_keys,
                    retired_operational_keys=retired_operational_keys)
                if existing_bytes is not None and existing_bytes == desired_bytes:
                    rc, printed = _safe_launchctl(
                        launchctl_safe, ["print", f"gui/{os.getuid()}/{item['label']}"])
                    loaded = _loaded_arguments(printed) if rc == 0 else []
                    if loaded == item["expected_arguments"]:
                        result = {"ok": True, "label": item["label"],
                                  "loaded_arguments": loaded, "release_sha": release_sha,
                                  "changed": False}
                if result is None:
                    result = install_one(
                        item, target_path, lambda args: _safe_launchctl(launchctl_safe, args),
                        preserve_unloaded=preserve_unloaded,
                        retired_environment_keys=retired_environment_keys,
                        retired_operational_keys=retired_operational_keys)
                    result["changed"] = True
                entry = registry["loops"][item["loop_id"]]
                event = build_install_event(
                    loop_id=item["loop_id"], domain=entry["domain"], release_sha=release_sha,
                    provider=entry["provider_route"], effect_class=entry["effect_class"])
                installed_plist = plistlib.loads(item["plist_bytes"])
                installed_state = installed_plist["EnvironmentVariables"]["LIFE_MANAGER_STATE_ROOT"]
                event_writer(Path(installed_state) / "events.jsonl", event)
                result["install_event_id"] = event["event_id"]
                results.append(result)
        except RuntimeError as exc:
            if not (skip_busy and str(exc) == "production apply is already owned"):
                raise
            skipped = _skip_if_not_loaded_idle(item, release_sha, launchctl_safe)
            if skipped is None:
                raise
            results.append(skipped)
    return results


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    commands = {
        "admission-v2-enable", "apply", "doctor", "reconcile",
        "start", "stop", "restart", "status", "watch",
    }
    if not args or args[0] not in commands:
        print("usage: lm-loop admission-v2-enable|apply [--all]|doctor|reconcile <provider-route> [--loaded-idle-only] [--max-owners N] [--loop-id <loop-id>]...|start|stop|restart <loop-id|all>|status|watch [<loop-id|all>]", file=sys.stderr)
        return 2
    command = args[0]
    if command == "apply":
        if args[1:] not in ([], ["--all"]):
            print(json.dumps({"ok": False, "error": "apply accepts only --all"}))
            return 2
        target = os.environ.get("LIFE_MANAGER_APPLY_TARGET")
        if not target and args[1:] != ["--all"]:
            print(json.dumps({
                "ok": False,
                "error": "apply requires LIFE_MANAGER_APPLY_TARGET; use --all only for an intentional fleet-wide reload",
            }, sort_keys=True))
            return 2
        if target and args[1:] == ["--all"]:
            print(json.dumps({"ok": False, "error": "--all conflicts with LIFE_MANAGER_APPLY_TARGET"}))
            return 2
        release_root = Path(os.environ.get("LIFE_MANAGER_RELEASE_ROOT", "~/loops/current")).expanduser()
        agents_dir = Path(os.environ.get(
            "LIFE_MANAGER_LAUNCH_AGENTS_DIR", "~/Library/LaunchAgents")).expanduser()
        launchctl_safe = Path(os.environ.get(
            "LIFE_MANAGER_LAUNCHCTL_SAFE", str(release_root / "bin/launchctl-safe"))).expanduser()
        try:
            results = apply_live(
                release_root, agents_dir, launchctl_safe,
                target=target, protocol_reader=durable_protocol_version)
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
            return 1
        print(json.dumps(results, indent=2, sort_keys=True))
        return 0
    if command == "admission-v2-enable":
        if len(args) != 1:
            print(json.dumps({"ok": False, "error": "admission-v2-enable accepts no arguments"}))
            return 2
        release_root = Path(os.environ.get(
            "LIFE_MANAGER_RELEASE_ROOT", "~/loops/current")).expanduser().resolve(strict=True)
        launchctl_safe = Path(os.environ.get(
            "LIFE_MANAGER_LAUNCHCTL_SAFE", str(release_root / "bin/launchctl-safe")
        )).expanduser()
        try:
            release_registry = validate_registry(json.loads(
                (release_root / "config/loop-registry.json").read_text(encoding="utf-8")
            ))
            result = activate_durable_admission_live(
                release_registry, release_root, launchctl_safe,
            )
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    registry = validate_registry(json.loads((ROOT / "config/loop-registry.json").read_text()))
    if command == "reconcile":
        positionals, loop_ids, loaded_idle_only, include_running = [], [], False, False
        max_owners = None
        reconcile_args = args[1:]
        index = 0
        while index < len(reconcile_args):
            value = reconcile_args[index]
            if value == "--loaded-idle-only":
                loaded_idle_only = True
            elif value == "--include-running":
                include_running = True
            elif value == "--max-owners":
                if index + 1 >= len(reconcile_args) or reconcile_args[index + 1].startswith("--"):
                    print(json.dumps({"ok": False, "error": "--max-owners requires a value"}))
                    return 2
                try:
                    max_owners = int(reconcile_args[index + 1])
                except ValueError:
                    print(json.dumps({"ok": False, "error": "--max-owners must be a positive integer"}))
                    return 2
                if not 1 <= max_owners <= 64:
                    print(json.dumps({"ok": False, "error": "--max-owners must be between 1 and 64"}))
                    return 2
                index += 1
            elif value == "--loop-id":
                if index + 1 >= len(reconcile_args) or reconcile_args[index + 1].startswith("--"):
                    print(json.dumps({"ok": False, "error": "--loop-id requires a value"}))
                    return 2
                loop_ids.append(reconcile_args[index + 1])
                index += 1
            elif value.startswith("--loop-id="):
                loop_id = value.split("=", 1)[1]
                if not loop_id:
                    print(json.dumps({"ok": False, "error": "--loop-id requires a value"}))
                    return 2
                loop_ids.append(loop_id)
            elif value.startswith("--"):
                print(json.dumps({"ok": False, "error": f"unknown reconcile option: {value}"}))
                return 2
            else:
                positionals.append(value)
            index += 1
        if len(positionals) != 1:
            print(json.dumps({"ok": False, "error": "reconcile requires <provider-route>"}))
            return 2
        route = positionals[0]
        requested_ids = set(loop_ids)
        automatic_release_reconciler = (
            os.environ.get("LIFE_MANAGER_LOOP_ID") == "life-manager-release-reconciler")
        auto_disk_cleanup = automatic_release_reconciler and route == "deterministic"
        effective_requested_ids = requested_ids | (
            {"life-manager-disk-cleanup"} if auto_disk_cleanup else set())
        if include_running and not requested_ids:
            print(json.dumps({"ok": False,
                              "error": "--include-running requires --loop-id"}))
            return 2
        if include_running and loaded_idle_only:
            print(json.dumps({"ok": False,
                              "error": "--include-running conflicts with --loaded-idle-only"}))
            return 2
        for loop_id in loop_ids:
            entry = registry["loops"].get(loop_id)
            if not isinstance(entry, dict):
                print(json.dumps({"ok": False, "error": f"unknown loop id: {loop_id}"}))
                return 2
            if entry["provider_route"] != route:
                print(json.dumps({"ok": False,
                                  "error": f"loop id {loop_id} is not on provider route {route}"}))
                return 2
        release_root = Path(os.environ.get("LIFE_MANAGER_RELEASE_ROOT", ROOT)).expanduser().resolve(strict=True)
        current_sha = json.loads((release_root / "RELEASE.json").read_text()).get("sha")
        skipped_non_ancestor: list[str] = []
        if automatic_release_reconciler and not requested_ids:
            targets = set()
        elif requested_ids:
            targets = set(effective_requested_ids)
        elif max_owners is not None:
            targets = _bounded_reconcile_candidates(
                registry, route, current_sha, max_owners, skipped_non_ancestor)
            if auto_disk_cleanup:
                targets.add("life-manager-disk-cleanup")
        else:
            targets = set()
        if automatic_release_reconciler and not requested_ids:
            rows = snapshot(registry, "all")
        elif requested_ids or max_owners is not None:
            rows = targeted_snapshot(
                registry, targets, release_root / "bin/launchctl-safe")
        else:
            rows = snapshot(registry, "all")
        explicitly_reloadable = {
            loop_id for loop_id in effective_requested_ids
            if registry["loops"][loop_id].get("cadence", {}).get("keep_alive") is True
        }
        agents_dir = Path(os.environ.get(
            "LIFE_MANAGER_LAUNCH_AGENTS_DIR", "~/Library/LaunchAgents")).expanduser()
        snapshot_shas = {}
        for row in rows:
            if (row.get("provider_route") == route
                    and row.get("installed_release_sha") is None
                    and row.get("launchd_state") == "loaded-idle"):
                loop_id = row["loop_id"]
                entry = registry["loops"][loop_id]
                sha = _recoverable_env_snapshot_sha(
                    agents_dir / f"{entry['label']}.plist", loop_id, entry,
                    release_root, current_sha)
                if sha:
                    snapshot_shas[loop_id] = sha

        def effective_installed_sha(row: dict) -> str | None:
            return row.get("installed_release_sha") or snapshot_shas.get(row["loop_id"])

        eligible_states = ({"loaded-idle", "loaded-running"} if include_running else
                           {"loaded-idle", "loaded-running"} if explicitly_reloadable else
                           {"loaded-idle"} if loaded_idle_only else
                           {"loaded-idle", "unloaded"})
        ancestry_cache: dict[str, bool] = {}
        try:
            pending_owners = _pending_admission_owners()
            pending_policy_mismatches = (
                _pending_admission_policy_mismatches(registry)
                if automatic_release_reconciler else set()
            )
            pending_release_rebinds = (
                {
                    loop_id for loop_id in pending_owners
                    if registry["loops"].get(loop_id, {}).get(
                        "reconcile_queued_release"
                    ) is True
                }
                if automatic_release_reconciler else set()
            )
        except (OSError, sqlite3.Error) as exc:
            print(json.dumps({"ok": False, "error": f"admission queue read failed: {type(exc).__name__}"}))
            return 1
        if automatic_release_reconciler:
            for row in rows:
                if row.get("provider_route") != route:
                    continue
                installed_sha = effective_installed_sha(row)
                if installed_sha and installed_sha != current_sha:
                    if installed_sha not in ancestry_cache:
                        ancestry_cache[installed_sha] = _loaded_sha_is_ancestor(
                            installed_sha, current_sha)
                    if not ancestry_cache[installed_sha]:
                        skipped_non_ancestor.append(row["loop_id"])
        eligible = [row for row in rows if (
            row["classification"] == "managed"
            and row["loop_id"] != os.environ.get("LIFE_MANAGER_LOOP_ID")
            and row["provider_route"] == route
            and (row["loop_id"] not in pending_owners
                 or row["loop_id"] in requested_ids
                 or row["loop_id"] in pending_policy_mismatches
                 or row["loop_id"] in pending_release_rebinds)
            and (not requested_ids or row["loop_id"] in effective_requested_ids)
            and row["launchd_state"] in eligible_states
            and (row["launchd_state"] != "loaded-running"
                 or include_running
                 or row["loop_id"] in explicitly_reloadable)
            and effective_installed_sha(row)
            and effective_installed_sha(row) != current_sha
            and (not automatic_release_reconciler
                 or ancestry_cache.get(effective_installed_sha(row), False))
            and (not automatic_release_reconciler
                 or row["loop_id"] in explicitly_reloadable
                 or row.get("event_release_sha") == effective_installed_sha(row))
        )]
        if max_owners is not None:
            extra = [row for row in eligible if auto_disk_cleanup
                     and row["loop_id"] == "life-manager-disk-cleanup"]
            eligible = [row for row in eligible if row not in extra][:max_owners] + extra
        skipped_non_ancestor = sorted(set(skipped_non_ancestor))
        skipped_pending = sorted({row["loop_id"] for row in rows if (
            row["provider_route"] == route
            and row["loop_id"] in pending_owners
            and row["loop_id"] not in requested_ids
            and row["loop_id"] not in pending_policy_mismatches
            and row["loop_id"] not in pending_release_rebinds)})
        applied, failed = [], []
        for row in eligible:
            try:
                results = apply_live(
                    release_root, Path("~/Library/LaunchAgents").expanduser(),
                    release_root / "bin/launchctl-safe",
                    target=row["loop_id"],
                    preserve_unloaded=row["launchd_state"] == "unloaded",
                    skip_busy=(loaded_idle_only and
                               row["loop_id"] not in explicitly_reloadable),
                    preserve_pending_admission=(row["launchd_state"] == "loaded-idle"),
                    replace_reserved_policy_drift=(
                        row["loop_id"] in pending_policy_mismatches
                    ),
                    allow_reserved_release_rebind=(
                        row["loop_id"] in pending_release_rebinds
                    ),
                    require_current=True,
                    reload_running=row["launchd_state"] == "loaded-running",
                    protocol_reader=durable_protocol_version)
                for result in results:
                    if result.get("skipped") == "pending-admission":
                        skipped_pending.append(row["loop_id"])
                    else:
                        applied.append(result)
            except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
                failed.append({"loop_id": row["loop_id"], "error": str(exc)})
        print(json.dumps({
            "ok": not failed, "route": route, "release_sha": current_sha,
            "skipped_non_ancestor": skipped_non_ancestor,
            "skipped_pending": sorted(set(skipped_pending)),
            "eligible": len(eligible), "applied": applied, "failed": failed,
            "skipped_running": [row["loop_id"] for row in rows if (
                row["classification"] == "managed"
                and row["provider_route"] == route
                and row["launchd_state"] == "loaded-running"
                and row["installed_release_sha"] != current_sha)],
        }, indent=2, sort_keys=True))
        return 1 if failed else 0
    if command in {"start", "stop", "restart"}:
        if len(args) != 2:
            print(json.dumps({"ok": False, "error": f"{command} requires <loop-id|all>"}))
            return 2
        target = args[1]
        if target != "all" and target not in registry["loops"]:
            print(json.dumps({"ok": False, "error": f"unknown loop id: {target}"}))
            return 2
        agents_dir = Path(os.environ.get(
            "LIFE_MANAGER_LAUNCH_AGENTS_DIR", "~/Library/LaunchAgents")).expanduser()
        launchctl_safe = Path(os.environ.get(
            "LIFE_MANAGER_LAUNCHCTL_SAFE", str(ROOT / "bin/launchctl-safe"))).expanduser()
        preflight_rc, detail = _safe_launchctl(launchctl_safe, ["preflight"])
        if preflight_rc:
            print(json.dumps({"ok": False, "error": detail.strip()}, sort_keys=True))
            return 1
        results = lifecycle(
            registry, command, target,
            lambda action, loop_id, entry: lifecycle_one(
                action, loop_id, entry, agents_dir,
                lambda launch_args: _safe_launchctl(launchctl_safe, launch_args),
                admission=lambda admission_action: (
                    suspend_durable(loop_id)
                    if admission_action == "suspend"
                    else resume_durable(loop_id)),
            ))
        print(json.dumps(results, indent=2, sort_keys=True))
        return 1 if any(row["return_code"] for row in results) else 0
    target = args[1] if len(args) > 1 else "all"
    if command == "doctor":
        loaded, _, _, _, installed = collect_live(registry)
        existing = {entry["entrypoint"] for entry in registry["loops"].values()
                    if (ROOT / entry["entrypoint"]).is_file()}
        report = doctor_report(registry, installed_labels=installed,
                               loaded_labels=set(loaded), existing_entrypoints=existing)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["ok"] else 1
    while True:
        print(json.dumps(snapshot(registry, target), indent=2, sort_keys=True), flush=True)
        if command == "status" or os.environ.get("LM_LOOP_WATCH_ONCE") == "1":
            return 0
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
