#!/usr/bin/env python3
"""Close host-admission effect_unknown fences via each owner's own readback script.

This is the generic T5-G-2/T5-G-3 reconciler (see
``docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md``). It reads
the exact live fences from ``_admission_effect_unknown_occurrences`` and, for
every owner that declares ``effect_reconcile`` in ``config/loop-registry.json``,
runs that owner's existing official-readback script -- the same script a human
previously ran by hand. A script call proves either "no effect" or "effect
with a receipt" through the owner's own provider readback before closing
anything; nothing here retries or replays an effect. A non-zero exit, a
timeout, or a script that still reports the occurrence fenced simply leaves
that occurrence fenced for the next wake.

Owners with current fences but no ``effect_reconcile`` entry are reported in
``needs_readback_adapter`` (T5-G-4): a human/dev-loop task, not this loop,
must add their adapter.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime
import sqlite3
import sys
from pathlib import Path
from typing import Callable, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.loop.lm_loop import _admission_effect_unknown_occurrences  # noqa: E402
from runtime.loop.runtime_event import rotate_jsonl_locked  # noqa: E402
from runtime.loop.macos_loop_registry import validate_registry  # noqa: E402

DEFAULT_REGISTRY = ROOT / "config/loop-registry.json"
CALL_TIMEOUT_SECONDS = 60
MAX_CALLS_PER_WAKE = 20
# Stays under the loop's runtime_timeout_seconds (1200): a call whose own timeout would
# overrun this budget is deferred to the next wake instead of being killed mid-proof.
WAKE_BUDGET_SECONDS = 1000
WAKE_PERIOD_SECONDS = 600  # lm-fence-reconciler cadence (config/loop-registry.json)
STDOUT_TAIL_LIMIT = 2048
EVENT_TAIL_LIMIT = 4 * 1024 * 1024
DEFAULT_LOG = Path(
    "~/.local/state/life-manager/lm-fence-reconciler/reconcile-calls.jsonl"
).expanduser()
CALL_LOG_TAIL_BYTES = 4 * 1024 * 1024
# Every reader (here, lm_loop._last_adapter_calls, central_cleanup.closed_reconcile_occurrences)
# reads at most the last 4 MiB, so rotation carries that tail forward. Archives hold closure
# proofs, so they are compressed (~30x) and never pruned.
CALL_LOG_MAX_BYTES = 32 * 1024 * 1024
# SH2a: the health observer's latest snapshot names revenue lanes in revenue_outage.
DEFAULT_HEALTH_LATEST = Path(
    "~/.local/state/life-manager/health-observer/latest.json"
).expanduser()


HEALTH_MAX_AGE_SECONDS = 30 * 60


def revenue_outage_owners(path: Path | None, now: float | None = None) -> frozenset[str]:
    """Jobs whose ``facets.revenue.status`` is ``blocked`` in the latest health snapshot.

    An unreadable or stale (> 30 min) snapshot yields no extra priority."""
    if path is None:
        return frozenset()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        generated = datetime.fromisoformat(document["generated_at"].replace("Z", "+00:00"))
        age = (time.time() if now is None else now) - generated.timestamp()
        jobs = document.get("jobs") or []
    except (OSError, ValueError, AttributeError, KeyError, TypeError):
        return frozenset()
    if not -60 <= age <= HEALTH_MAX_AGE_SECONDS:  # small clock skew tolerated
        return frozenset()
    return frozenset(
        job["job_id"] for job in jobs
        if isinstance(job, dict) and isinstance(job.get("job_id"), str)
        and ((job.get("facets") or {}).get("revenue") or {}).get("status") == "blocked"
    )


def _failure_fields(stdout_tail: str) -> dict:
    """The last error_class/reason an adapter printed as JSON, so a repeated failure is visible."""
    fields: dict = {}
    for record in _json_output_records(stdout_tail):
        for key in ("error_class", "reason"):
            if isinstance(record.get(key), str):
                fields[key] = record[key][:240]
    return fields


def run_call(argv: list[str], timeout: float = CALL_TIMEOUT_SECONDS) -> tuple[int, str]:
    """Run one owner reconcile script; never raises, always (exit_code, stdout_tail)."""
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False,
        )
        return result.returncode, (result.stdout or "")[-STDOUT_TAIL_LIMIT:]
    except subprocess.TimeoutExpired:
        return 124, "reconcile_call_timed_out"
    except OSError as error:
        return 127, f"reconcile_call_start_failed:{type(error).__name__}"


def _runtime_release_shas(owner_id: str, occurrences: set[str],
                          loops: Mapping[str, object]) -> dict[str, str | None]:
    """Bind reconciled occurrence proofs to one unambiguous runtime event release."""
    result = {occurrence: None for occurrence in occurrences}
    row = loops.get(owner_id)
    state_root = row.get("state_root") if isinstance(row, Mapping) else None
    if not isinstance(state_root, str) or not state_root:
        return result
    path = Path(state_root).expanduser() / "events.jsonl"
    try:
        size = path.stat().st_size
        offset = max(0, size - EVENT_TAIL_LIMIT)
        with path.open("rb") as handle:
            handle.seek(offset)
            payload = handle.read(EVENT_TAIL_LIMIT)
    except OSError:
        return result
    lines = payload.splitlines()
    if offset and lines:
        lines = lines[1:]
    observed: dict[str, set[str | None]] = {occurrence: set() for occurrence in occurrences}
    for line in lines:
        try:
            event = json.loads(line)
        except (UnicodeError, json.JSONDecodeError):
            return result
        if not isinstance(event, dict) or event.get("loop_id") != owner_id:
            continue
        occurrence = event.get("occurrence_id")
        if occurrence not in observed:
            continue
        release_sha = event.get("release_sha")
        if not isinstance(release_sha, str) or re.fullmatch(r"[a-f0-9]{40}", release_sha) is None:
            observed[occurrence].add(None)
        else:
            observed[occurrence].add(release_sha)
    for occurrence, values in observed.items():
        if len(values) == 1 and None not in values:
            result[occurrence] = next(iter(values))
    return result


def _lost_terminal_unknown_occurrences(
        loops: Mapping[str, object], active: Mapping[str, tuple[str, ...]],
        log_path: Path | None) -> dict[str, tuple[str, ...]]:
    """Find exact unknown terminal events whose admission fence was already lost.

    These are readback candidates only. A registered owner adapter must still prove the
    occurrence through its official provider readback before an idempotent close is logged.
    """
    candidates: dict[str, set[str]] = {}
    for owner_id, value in loops.items():
        if not isinstance(owner_id, str) or not isinstance(value, Mapping):
            continue
        cfg = value.get("effect_reconcile")
        state_root = value.get("state_root")
        if (not isinstance(cfg, Mapping) or not cfg.get("argv")
                or not isinstance(state_root, str) or not state_root):
            continue
        event_path = Path(state_root).expanduser() / "events.jsonl"
        try:
            size = event_path.stat().st_size
            offset = max(0, size - EVENT_TAIL_LIMIT)
            with event_path.open("rb") as handle:
                handle.seek(offset)
                payload = handle.read(EVENT_TAIL_LIMIT)
        except OSError:
            continue
        lines = payload.splitlines()
        if offset and lines:
            lines = lines[1:]
        for line in lines:
            try:
                event = json.loads(line)
            except (UnicodeError, json.JSONDecodeError):
                continue
            if not isinstance(event, dict):
                continue
            occurrence = event.get("occurrence_id")
            release_sha = event.get("release_sha")
            if (event.get("loop_id") != owner_id or event.get("owner_id") != owner_id
                    or event.get("phase") != "report"
                    or event.get("status") not in {"blocked", "fail"}
                    or event.get("effect_status") != "unknown"
                    or not isinstance(event.get("effect_class"), str)
                    or not event.get("effect_class") or event.get("effect_class") == "none"
                    or not isinstance(occurrence, str)
                    or not occurrence.startswith(f"{owner_id}:")
                    or not isinstance(release_sha, str)
                    or re.fullmatch(r"[a-f0-9]{40}", release_sha) is None
                    or occurrence in active.get(owner_id, ())):
                continue
            candidates.setdefault(owner_id, set()).add(occurrence)
    if not candidates:
        return {}

    release_shas = {
        owner: _runtime_release_shas(owner, occurrences, loops)
        for owner, occurrences in candidates.items()
    }
    closed = set()
    if log_path is not None:
        from runtime.loop.central_cleanup import closed_reconcile_occurrences
        closed = closed_reconcile_occurrences(log_path)

    pending: dict[str, set[str]] = {}
    for owner, occurrences in candidates.items():
        for occurrence in occurrences:
            sha = release_shas[owner].get(occurrence)
            if (sha is None or (owner, occurrence, sha) in closed):
                continue
            pending.setdefault(owner, set()).add(occurrence)
    if not pending:
        return {}

    from runtime.host import resource_admission
    database = resource_admission.state_root() / "admission-v2.sqlite3"
    if not database.is_file():
        return {}
    released: dict[str, list[str]] = {}
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=0.5) as connection:
        for owner, occurrences in pending.items():
            ordered = sorted(occurrences)
            for start in range(0, len(ordered), 500):
                batch = ordered[start:start + 500]
                placeholders = ",".join("?" for _ in batch)
                rows = connection.execute(
                    f"""SELECT occurrence_id FROM occurrences
                          WHERE owner_id=? AND state='released' AND effect_unknown=0
                            AND occurrence_id IN ({placeholders})""",
                    (owner, *batch),
                ).fetchall()
                if rows:
                    released.setdefault(owner, []).extend(row[0] for row in rows)
    return {owner: tuple(sorted(set(occurrences)))
            for owner, occurrences in released.items()}


def _json_output_records(stdout_tail: str) -> list[dict]:
    records = []
    for line in stdout_tail.splitlines():
        try:
            value = json.loads(line)
        except (TypeError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            records.append(value)
        elif isinstance(value, list):
            records.extend(item for item in value if isinstance(item, dict))
    return records


def _closure_proof(stdout_tail: str, *, owner_id: str, occurrence_id: str,
                   release_sha: str | None) -> dict | None:
    if not isinstance(release_sha, str) or re.fullmatch(r"[a-f0-9]{40}", release_sha) is None:
        return None
    matching = [record for record in _json_output_records(stdout_tail)
                if record.get("owner_id") == owner_id
                and record.get("occurrence_id") == occurrence_id]
    if len(matching) != 1:
        return None
    proof = matching[0]
    if proof.get("verified") is not True:
        return None
    proof_release = proof.get("release_sha")
    if proof_release is not None and proof_release != release_sha:
        return None
    receipt_ref = proof.get("provider_receipt_id") or proof.get("evidence_ref")
    if not isinstance(receipt_ref, str) or not receipt_ref.strip():
        return None
    return {
        "proof_type": "effect_reconcile_closure.v1",
        "owner_id": owner_id,
        "occurrence_id": occurrence_id,
        "release_sha": release_sha,
        "verified": True,
        "receipt_ref": receipt_ref,
    }


def build_argv(reconcile_cfg: Mapping[str, object], root: Path,
                occurrence: str | None) -> list[str]:
    """Turn one registry ``effect_reconcile`` row plus a target into a real argv.

    ``argv[0]`` is always a repository-relative script path (validated by
    ``macos_loop_registry``), never marked executable, so it is always invoked
    through the current Python interpreter.
    """
    fixed = list(reconcile_cfg.get("argv") or [])
    if not fixed:
        raise ValueError("effect_reconcile.argv is empty")
    argv = [sys.executable, str(root / fixed[0]), *fixed[1:]]
    occurrence_flag = reconcile_cfg.get("occurrence_flag")
    if occurrence_flag is not None:
        if occurrence is None:
            raise ValueError("occurrence_flag is set but no occurrence target was given")
        argv += [occurrence_flag, occurrence]
    resolve_flag = reconcile_cfg.get("resolve_flag")
    if resolve_flag is not None:
        argv.append(resolve_flag)
    return argv


def plan_targets(
    fenced: Mapping[str, tuple[str, ...]],
    loops: Mapping[str, Mapping[str, object]],
) -> tuple[dict[str, list[str | None]], list[str]]:
    """Split current fences into (per-owner call targets, owners lacking an adapter).

    An owner whose script has no ``occurrence_flag`` (it self-enumerates every
    fenced occurrence from its own admission read, e.g.
    ``reconcile_application_no_submit.py``) gets one ``None`` target: one call
    covers every currently fenced occurrence for that owner.
    """
    targets: dict[str, list[str | None]] = {}
    needs_adapter: list[str] = []
    for owner_id in sorted(fenced):
        row = loops.get(owner_id) or {}
        reconcile_cfg = row.get("effect_reconcile") if isinstance(row, Mapping) else None
        if not isinstance(reconcile_cfg, Mapping) or not reconcile_cfg.get("argv"):
            needs_adapter.append(owner_id)
            continue
        if reconcile_cfg.get("occurrence_flag") is None:
            targets[owner_id] = [None]
        else:
            targets[owner_id] = list(fenced[owner_id])
    return targets, needs_adapter


def round_robin(
    targets: Mapping[str, list[str | None]], cap: int, *,
    priority_owners: set[str] | frozenset[str] = frozenset(), start: int = 0,
    outage_owners: set[str] | frozenset[str] = frozenset(),
) -> list[tuple[str, str | None]]:
    """Interleave owners fairly, serving explicit safety priorities first.

    ``start`` rotates the non-priority owners so a fixed alphabetical order cannot starve the
    owners at the back when ``cap`` is smaller than the number of owners (2026-10-09: 41 owners,
    20 calls per wake, Anicca/Honne sat at positions 18+ and 16 of them were never called).
    """
    # Order: financial (safety) -> revenue_outage (SH2a) -> rotating rest.
    priority = sorted(owner for owner in targets if owner in priority_owners)
    priority += sorted(owner for owner in targets
                       if owner in outage_owners and owner not in priority_owners)
    rest = sorted(owner for owner in targets
                  if owner not in priority_owners and owner not in outage_owners)
    if rest:
        offset = start % len(rest)
        rest = rest[offset:] + rest[:offset]
    owners = priority + rest
    queues = {owner: list(values) for owner, values in targets.items()}
    calls: list[tuple[str, str | None]] = []
    while len(calls) < cap and any(queues.values()):
        for owner in owners:
            if len(calls) >= cap:
                break
            if queues[owner]:
                calls.append((owner, queues[owner].pop(0)))
    return calls


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    rotate_jsonl_locked(descriptor, path, CALL_LOG_MAX_BYTES,
                        keep_tail_bytes=CALL_LOG_TAIL_BYTES)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _recent_call_rows(path: Path | None) -> dict[tuple[str, str], dict]:
    """Read only the recent call window; historical proof rows stay untouched."""
    if path is None:
        return {}
    try:
        with path.open("rb") as handle:
            size = os.fstat(handle.fileno()).st_size
            offset = max(0, size - CALL_LOG_TAIL_BYTES)
            handle.seek(offset)
            lines = handle.read(CALL_LOG_TAIL_BYTES).splitlines()
    except OSError:
        return {}
    if offset and lines:
        lines = lines[1:]
    latest: dict[tuple[str, str], dict] = {}
    for line in lines:
        try:
            row = json.loads(line)
        except (UnicodeError, json.JSONDecodeError):
            continue
        if (isinstance(row, dict) and isinstance(row.get("owner_id"), str)
                and isinstance(row.get("occurrence_id"), str)):
            latest[(row["owner_id"], row["occurrence_id"])] = row
    return latest


def _occurrence_digest(occurrences: set[str] | tuple[str, ...]) -> str:
    payload = "\n".join(sorted(occurrences)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _owner_batch_summary(owner_id: str, checked: set[str], still_fenced: set[str],
                         exit_code: int, *, result_kind: str = "batch_checked") -> dict:
    return {
        "owner_id": owner_id,
        "occurrence_id": f"{owner_id}:*",
        "owner_batch_summary": True,
        "checked_occurrence_count": len(checked),
        "checked_occurrences_sha256": _occurrence_digest(checked),
        "still_fenced_count": len(still_fenced),
        "still_fenced_occurrences_sha256": _occurrence_digest(still_fenced),
        "exit_code": exit_code,
        "closed": False,
        "result_kind": result_kind,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _batch_summary_changed(previous: dict | None, current: dict) -> bool:
    if not isinstance(previous, dict) or previous.get("owner_batch_summary") is not True:
        return True
    keys = (
        "checked_occurrence_count", "checked_occurrences_sha256", "still_fenced_count",
        "still_fenced_occurrences_sha256", "exit_code", "result_kind",
    )
    return any(previous.get(key) != current.get(key) for key in keys)


LOCK_RETRIES = 4
LOCK_RETRY_SECONDS = 2.0


def _read_with_retry(read_fenced: Callable[[], dict[str, tuple[str, ...]]],
                     sleep: Callable[[float], None]) -> dict[str, tuple[str, ...]]:
    """Read the fences, waiting out a transient ``database is locked`` (2026-10-09: it ended
    the whole wake after a handful of calls).  Any other error, or a lock that outlasts the
    retries, propagates."""
    for attempt in range(LOCK_RETRIES + 1):
        try:
            return read_fenced()
        except sqlite3.OperationalError as error:
            if "locked" not in str(error).lower() or attempt == LOCK_RETRIES:
                raise
            sleep(LOCK_RETRY_SECONDS)
    raise AssertionError("unreachable")


def _rotate_occurrences_from_log(targets: dict[str, list[str | None]], log_path: Path | None) -> None:
    """Advance within each owner using the existing call ledger, without new state."""
    if log_path is None:
        return
    last = {}
    try:
        with log_path.open("rb") as handle:
            offset = max(0, os.fstat(handle.fileno()).st_size - 256 * 1024)
            handle.seek(offset)
            lines = handle.read(256 * 1024).splitlines()
        for line in lines[1:] if offset else lines:
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(row, dict):
                continue
            owner = row.get("owner_id")
            occurrence = (row.get("last_occurrence_id") if row.get("owner_cursor") is True
                          else row.get("occurrence_id"))
            if isinstance(owner, str) and isinstance(occurrence, str):
                last[owner] = occurrence
    except OSError:
        return
    for owner, values in targets.items():
        previous = last.get(owner)
        if previous is not None and previous in values:
            index = values.index(previous) + 1
            targets[owner] = values[index:] + values[:index]


def reconcile(
    *,
    registry: Mapping[str, object],
    root: Path,
    cap: int = MAX_CALLS_PER_WAKE,
    budget_seconds: float = WAKE_BUDGET_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    run_call: Callable[..., tuple[int, str]] = run_call,
    read_fenced: Callable[[], dict[str, tuple[str, ...]]] = _admission_effect_unknown_occurrences,
    log_path: Path | None = DEFAULT_LOG,
    wake_epoch: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
    health_latest: Path | None = None,
) -> dict:
    """Run one bounded reconciliation pass and return the summary dict."""
    loops = registry.get("loops", {}) if isinstance(registry, Mapping) else {}
    fenced = _read_with_retry(read_fenced, sleep)
    lost_fence_scan_locked = False
    try:
        lost_fences = _read_with_retry(
            lambda: _lost_terminal_unknown_occurrences(loops, fenced, log_path), sleep)
    except sqlite3.OperationalError as error:
        if "locked" not in str(error).lower():
            raise
        # This supplemental scan finds released-only candidates. Its failure must not
        # suppress adapter readbacks for active fences already read above; keep those
        # candidates unknown and retry their discovery on a later natural wake.
        lost_fences = {}
        lost_fence_scan_locked = True
    for owner_id, occurrences in lost_fences.items():
        fenced[owner_id] = tuple(sorted(set(fenced.get(owner_id, ())) | set(occurrences)))
    checked = sum(len(occurrences) for occurrences in fenced.values())
    targets, needs_adapter = plan_targets(fenced, loops)
    _rotate_occurrences_from_log(targets, log_path)
    financial = frozenset(
        owner_id for owner_id in targets
        if isinstance(loops.get(owner_id), Mapping)
        and loops[owner_id].get("domain") == "financial"
        and isinstance(loops[owner_id].get("effect_reconcile"), Mapping)
    )
    outage = revenue_outage_owners(health_latest) & set(targets)
    # The rotation comes from the wall clock (one step of ``cap`` owners per wake): no state file.
    wake = time.time() if wake_epoch is None else wake_epoch
    start = int(wake // WAKE_PERIOD_SECONDS) * cap
    calls = round_robin(targets, cap, priority_owners=financial, start=start,
                        outage_owners=outage)
    target_owners = {owner_id for owner_id, _ in calls}
    event_release_shas = {
        owner_id: _runtime_release_shas(owner_id, set(fenced.get(owner_id, ())), loops)
        for owner_id in target_owners
    }
    closed = 0
    deferred = 0
    locked = lost_fence_scan_locked
    records: list[dict] = []
    recent_call_rows = _recent_call_rows(log_path)
    started = clock()
    for owner_id, occurrence in calls:
        reconcile_cfg = loops[owner_id]["effect_reconcile"]
        timeout = reconcile_cfg.get("timeout_seconds") or CALL_TIMEOUT_SECONDS
        if clock() - started + timeout > budget_seconds:
            deferred += 1
            continue
        argv = build_argv(reconcile_cfg, root, occurrence)
        exit_code, tail = run_call(argv, timeout=timeout)
        try:
            after = _read_with_retry(read_fenced, sleep)
        except sqlite3.OperationalError:
            # Keep what already ran in the log and end the wake cleanly; the next wake resumes.
            locked = True
            if occurrence is None:
                before = set(fenced.get(owner_id, ()))
                record = _owner_batch_summary(
                    owner_id, before, before, exit_code,
                    result_kind="post_call_admission_read_locked",
                )
                if _batch_summary_changed(
                        recent_call_rows.get((owner_id, record["occurrence_id"])), record):
                    records.append(record)
            else:
                records.append({
                    "owner_id": owner_id, "occurrence_id": occurrence,
                    "exit_code": exit_code, "closed": False, "stdout_tail": tail,
                })
            break
        still_open = set(after.get(owner_id, ()))
        if occurrence is None:
            before = sorted(set(fenced.get(owner_id, ())))
            still_fenced = set(before) & still_open
            for occ in before:
                if occ not in still_open:
                    closed += 1
                    record = {
                        "owner_id": owner_id, "occurrence_id": occ,
                        "exit_code": exit_code, "closed": True, "stdout_tail": tail,
                    }
                    records.append(record)
                    if exit_code == 0:
                        proof = _closure_proof(
                            tail, owner_id=owner_id, occurrence_id=occ,
                            release_sha=event_release_shas.get(owner_id, {}).get(occ),
                        )
                        if proof is not None:
                            record["release_sha"] = proof["release_sha"]
                            record["closure_proof"] = proof
            if still_fenced:
                record = _owner_batch_summary(
                    owner_id, set(before), still_fenced, exit_code,
                )
                previous = recent_call_rows.get((owner_id, record["occurrence_id"]))
                if owner_id in outage:
                    record.update(_failure_fields(tail))
                    records.append(record)
                elif _batch_summary_changed(previous, record):
                    records.append(record)
        else:
            proof = _closure_proof(
                tail, owner_id=owner_id, occurrence_id=occurrence,
                release_sha=event_release_shas.get(owner_id, {}).get(occurrence),
            ) if exit_code == 0 else None
            lost = occurrence in lost_fences.get(owner_id, ())
            occ_closed = occurrence not in still_open
            if lost:
                occ_closed = occ_closed and proof is not None
            if occ_closed:
                closed += 1
            record = {
                "owner_id": owner_id, "occurrence_id": occurrence,
                "exit_code": exit_code, "closed": occ_closed, "stdout_tail": tail,
            }
            if not occ_closed:
                record.update(_failure_fields(tail))
            previous = recent_call_rows.get((owner_id, occurrence))
            if (not lost or occ_closed or owner_id in outage or previous is None or previous.get("closed")
                    or previous.get("exit_code") != exit_code):
                records.append(record)
            elif len(targets.get(owner_id, ())) > 1:
                cursor = {
                    "owner_id": owner_id, "occurrence_id": f"{owner_id}:*",
                    "owner_cursor": True, "last_occurrence_id": occurrence,
                    "closed": False,
                }
                previous_cursor = recent_call_rows.get((owner_id, cursor["occurrence_id"]), {})
                if previous_cursor.get("last_occurrence_id") != occurrence:
                    records.append(cursor)
            if occ_closed and proof is not None:
                record["release_sha"] = proof["release_sha"]
                record["closure_proof"] = proof
    if log_path is not None:
        _append_jsonl(log_path, records)
    summary = {
        "checked": checked,
        "closed": closed,
        "still_fenced": checked - closed,
        "deferred_calls": deferred,
        "needs_readback_adapter": needs_adapter,
    }
    if locked:
        summary["status"] = "partial_database_locked"
    if lost_fence_scan_locked:
        summary["lost_fence_scan_locked"] = True
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--max-calls", type=int, default=MAX_CALLS_PER_WAKE)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    args = parser.parse_args(argv)
    if args.max_calls < 1:
        parser.error("--max-calls must be positive")
    try:
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
        validate_registry(registry)
    except (OSError, ValueError) as error:
        print(json.dumps(
            {"error": "registry_unreadable_or_invalid", "detail": str(error)[:240]},
            sort_keys=True,
        ), file=sys.stderr)
        return 1
    summary = reconcile(
        registry=registry, root=args.root.resolve(), cap=args.max_calls,
        log_path=args.log.expanduser(), health_latest=DEFAULT_HEALTH_LATEST,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
