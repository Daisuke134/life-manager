#!/usr/bin/env python3
"""Close one capafy-loop-daily effect_unknown admission fence.

capafy-loop-daily (the Capafy skill factory) is a deterministic owner: every
run that touches Capafy and then exits non-zero gets fenced by the host
admission layer (``resource_admission.release_and_reserve_resource`` sets
``effect_unknown`` whenever ``effect_class != "none"`` and the child exited
non-zero). Nothing previously closed those fences automatically -- three
happened on 2026-09-27 and stayed fenced until a human ran
``resolve_pre_effect_occurrence``/``resolve_unknown_occurrence`` by hand using
a ``packager.py publish-list`` readback.

Official readback: the same read-only Capafy seller API calls
``inventory_status.py`` already trusts --
``skills/capafy-autopublish/vendor/capafy-publisher/packager.py publish-list``
(all agents + latest_agent_version_id + updated_at) and ``publish-remote-status
--agent-id <id>`` (the exact ``platform_status`` for a receipt). Never a
mutating call.

Precision: ``capafy-loop-daily.sh`` writes a durable pre-dispatch snapshot
(``record_snapshot``) at the very start of every run, before any Capafy
mutation, capturing each known agent's ``latest_agent_version_id``. The
reconciler diffs the live publish-list against that snapshot: any agent
whose id is new or whose latest version changed proves this run (or a
still-fenced predecessor) had an effect. When no snapshot exists (e.g. runs
before this feature shipped), it falls back to an ``updated_at`` window
check against ``[queued_at, queued_at + MAX_RUN_SECONDS]``, the same
approach ``capafy_ig_fence_reconcile.py`` uses for Instagram.

Decision:
  - effected: a hit (new/updated agent) proves the effect happened -> read
    ``publish-remote-status`` for that agent's ``platform_status`` and close
    via ``resolve_unknown_occurrence`` with receipt
    ``capafy:agent/<id>/version/<vid>:platform_status=<n>``.
  - no-effect: a complete publish-list readback shows nothing changed and
    enough time has passed (> MAX_RUN_SECONDS + a processing buffer) -> write
    an evidence JSON file and close via ``resolve_pre_effect_occurrence``.
  - inconclusive (read failure, remote-status read failure, or not enough
    time passed yet): stays fenced; the result records ``reason`` and
    ``error_class`` for the next wake to retry.

Usage:
    python3 capafy_factory_fence_reconcile.py --occurrence capafy-loop-daily:<run_id> [--resolve]
    python3 capafy_factory_fence_reconcile.py --occurrence capafy-loop-daily:<run_id> --record-snapshot
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OWNER_ID = "capafy-loop-daily"
# Matches the registry's default runtime_timeout_seconds (config/loop-registry.json
# has no runtime_timeout_seconds override for capafy-loop-daily; lm_loop_run.py
# falls back to 3600) -- the actual wall-clock bound the admission layer enforces,
# regardless of what the in-run prompt claims about "no wall-clock limit".
MAX_RUN_SECONDS = 3600
# Capafy's own API is a synchronous read (not an eventually-consistent listing
# like Instagram's), so this buffer only covers clock skew and admission-layer
# release latency, not provider propagation delay.
POST_PROCESSING_DELAY_SECONDS = 120
NO_EFFECT_MIN_AGE_SECONDS = MAX_RUN_SECONDS + POST_PROCESSING_DELAY_SECONDS
# Waiting MAX_RUN_SECONDS only guarantees the run is no longer in flight. When the run's own
# process is provably gone, an hour of waiting adds nothing: 2026-10-08 a PREPARE_FAILED run
# (no agent spend) fenced the factory for an hour, twice in one day.
FINISHED_RUN_MIN_AGE_SECONDS = 60


def run_finished(occurrence_id: str, queued_at: dt.datetime, *, process_start_fn=None) -> bool:
    """True only when the runner pid encoded as the occurrence suffix is gone or was reused.

    Unparseable ids and any doubt return False (keep waiting): never guess a run is over.
    """
    import re
    match = re.search(r"-(\d+)$", occurrence_id)
    if not match:
        return False
    if process_start_fn is None:
        from runtime.host.resource_admission import process_start as process_start_fn
    try:
        started = process_start_fn(int(match.group(1)))
    except Exception:  # noqa: BLE001
        return False
    if started is None:
        return True
    try:
        began = dt.datetime.strptime(" ".join(str(started).split()), "%a %b %d %H:%M:%S %Y").astimezone()
    except ValueError:
        return False
    return began > queued_at + dt.timedelta(seconds=30)  # a newer process owns that pid now

PUBLISHER_DIR = REPO_ROOT / "skills/capafy-autopublish/vendor/capafy-publisher"
SNAPSHOT_DIR = Path(
    "~/.local/state/life-manager/state/capafy-loop-daily-snapshots"
).expanduser()
EVIDENCE_DIR = Path(
    "~/.local/state/life-manager/reconciliation/evidence"
).expanduser()


def _safe_occurrence(occurrence_id: str) -> str:
    return occurrence_id.replace(":", "_").replace("/", "_")


def fenced_row(owner_id: str, occurrence_id: str) -> tuple[str, dt.datetime]:
    """Read (state, queued_at) of the fenced row without mutating the ledger."""
    from runtime.host import resource_admission

    database = resource_admission.state_root() / "admission-v2.sqlite3"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        row = connection.execute(
            """SELECT state, queued_at FROM occurrences
                 WHERE owner_id=? AND occurrence_id=? AND effect_unknown=1""",
            (owner_id, occurrence_id),
        ).fetchone()
    if row is None or row[1] is None:
        raise ValueError("occurrence is not an effect_unknown row")
    queued = dt.datetime.fromtimestamp(float(row[1]), dt.timezone.utc)
    return str(row[0]), queued


def read_publish_list(*, publisher_dir: Path = PUBLISHER_DIR,
                       timeout: float = 90) -> dict[str, Any]:
    """Read-only ``packager.py publish-list``. Never mutates platform state."""
    try:
        result = subprocess.run(
            [sys.executable, "packager.py", "publish-list"],
            cwd=publisher_dir, capture_output=True, text=True, timeout=timeout, check=False,
        )
        if result.returncode != 0:
            return {"ok": False, "reason": f"publish_list_exit_{result.returncode}"}
        payload = json.loads(result.stdout, strict=False)
        agents_raw = payload.get("agents") if isinstance(payload, dict) else None
        if not isinstance(agents_raw, list):
            return {"ok": False, "reason": "publish_list_missing_agents"}
        agents: list[dict[str, Any]] = []
        for row in agents_raw:
            if not isinstance(row, Mapping):
                return {"ok": False, "reason": "publish_list_row_not_object"}
            agents.append({
                "agent_id": row.get("agent_id"),
                "updated_at": row.get("updated_at"),
                "latest_agent_version_id": row.get("latest_agent_version_id"),
            })
        return {
            "ok": True, "agents": agents,
            "sha256": hashlib.sha256(result.stdout.encode("utf-8")).hexdigest(),
        }
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return {"ok": False, "reason": f"publish_list_failed:{type(exc).__name__}"}


def read_remote_status(agent_id: str, *, publisher_dir: Path = PUBLISHER_DIR,
                        timeout: float = 30) -> dict[str, Any]:
    """Read-only ``packager.py publish-remote-status --agent-id <id>``."""
    try:
        result = subprocess.run(
            [sys.executable, "packager.py", "publish-remote-status", "--agent-id", str(agent_id)],
            cwd=publisher_dir, capture_output=True, text=True, timeout=timeout, check=False,
        )
        if result.returncode != 0:
            return {"ok": False, "reason": f"remote_status_exit_{result.returncode}"}
        payload = json.loads(result.stdout, strict=False)
        latest = payload.get("latest_version") if isinstance(payload, dict) else None
        if not isinstance(latest, Mapping):
            return {"ok": False, "reason": "remote_status_missing_latest_version"}
        status = latest.get("platform_status")
        version_id = latest.get("agent_version_id")
        if isinstance(status, bool) or not isinstance(status, int):
            return {"ok": False, "reason": "remote_status_invalid_platform_status"}
        if not version_id:
            return {"ok": False, "reason": "remote_status_missing_agent_version_id"}
        return {"ok": True, "platform_status": status, "agent_version_id": str(version_id)}
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return {"ok": False, "reason": f"remote_status_failed:{type(exc).__name__}"}


def snapshot_path(occurrence_id: str, *, snapshot_dir: Path = SNAPSHOT_DIR) -> Path:
    return snapshot_dir / f"{_safe_occurrence(occurrence_id)}.json"


def _atomic_write_json(path: Path, value: dict[str, Any], *, mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True)
    os.replace(tmp, path)


def record_snapshot(occurrence_id: str, *,
                     read_publish_list_fn: Callable[[], dict[str, Any]] = read_publish_list,
                     snapshot_dir: Path = SNAPSHOT_DIR,
                     now: dt.datetime | None = None) -> dict[str, Any]:
    """Durably record every known agent's latest version before this run can mutate Capafy.

    Best-effort by design: called at the very top of capafy-loop-daily.sh, before
    any Capafy-mutating step. A failure here never blocks the run -- the
    reconciler falls back to the updated_at-window check when no usable
    snapshot exists.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    publish_list = read_publish_list_fn()
    if not publish_list.get("ok"):
        snapshot = {
            "schema_version": 1, "owner_id": OWNER_ID, "occurrence_id": occurrence_id,
            "ok": False, "reason": str(publish_list.get("reason") or "publish_list_read_failed"),
            "captured_at": now.isoformat(timespec="seconds"),
        }
    else:
        agents = publish_list.get("agents") or []
        latest_versions = {
            str(agent["agent_id"]): agent.get("latest_agent_version_id")
            for agent in agents if agent.get("agent_id")
        }
        snapshot = {
            "schema_version": 1, "owner_id": OWNER_ID, "occurrence_id": occurrence_id,
            "ok": True, "agent_count": len(agents), "latest_versions": latest_versions,
            "captured_at": now.isoformat(timespec="seconds"),
        }
    try:
        _atomic_write_json(snapshot_path(occurrence_id, snapshot_dir=snapshot_dir), snapshot)
    except OSError as exc:
        snapshot = {**snapshot, "ok": False, "reason": f"snapshot_write_failed:{type(exc).__name__}"}
    return snapshot


def load_snapshot(occurrence_id: str, *,
                   snapshot_dir: Path = SNAPSHOT_DIR) -> dict[str, Any] | None:
    path = snapshot_path(occurrence_id, snapshot_dir=snapshot_dir)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _parse_updated_at(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def find_hit(agents: list[dict[str, Any]], snapshot: dict[str, Any] | None,
             queued_at: dt.datetime, window_end: dt.datetime) -> dict[str, Any] | None:
    """Return the first agent proving a Capafy effect happened, or None."""
    if snapshot is not None and snapshot.get("ok"):
        prior_versions = snapshot.get("latest_versions") or {}
        for agent in agents:
            agent_id = agent.get("agent_id")
            if not agent_id:
                continue
            prior = prior_versions.get(str(agent_id))
            current = agent.get("latest_agent_version_id")
            if prior is None or prior != current:
                return agent
        return None
    for agent in agents:
        updated_at = _parse_updated_at(agent.get("updated_at"))
        if updated_at is not None and queued_at <= updated_at <= window_end:
            return agent
    return None


def _append_evidence(evidence_dir: Path, occurrence_id: str, payload: dict[str, Any]) -> Path:
    path = evidence_dir / f"{OWNER_ID}-{_safe_occurrence(occurrence_id)}.json"
    _atomic_write_json(path, payload)
    return path


def reconcile(
    occurrence_id: str, *,
    fenced_row_fn: Callable[[str, str], tuple[str, dt.datetime]] = fenced_row,
    load_snapshot_fn: Callable[[str], dict[str, Any] | None] = load_snapshot,
    read_publish_list_fn: Callable[[], dict[str, Any]] = read_publish_list,
    read_remote_status_fn: Callable[[str], dict[str, Any]] = read_remote_status,
    resolve_unknown_fn: Callable[..., bool] | None = None,
    resolve_pre_effect_fn: Callable[..., bool] | None = None,
    evidence_dir: Path = EVIDENCE_DIR,
    now: dt.datetime | None = None,
    run_finished_fn: Callable[[str, dt.datetime], bool] | None = None,
    resolve: bool = False,
) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    state, queued_at = fenced_row_fn(OWNER_ID, occurrence_id)
    window_end = queued_at + dt.timedelta(seconds=MAX_RUN_SECONDS)

    publish_list = read_publish_list_fn()
    if not publish_list.get("ok"):
        return {
            "owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": False,
            "reason": str(publish_list.get("reason") or "publish_list_read_failed"),
            "error_class": "provider_read_failed", "admission_state": state,
        }

    snapshot = load_snapshot_fn(occurrence_id)
    agents = publish_list.get("agents") or []
    hit = find_hit(agents, snapshot, queued_at, window_end)

    if hit is not None:
        agent_id = str(hit["agent_id"])
        remote_status = read_remote_status_fn(agent_id)
        if not remote_status.get("ok"):
            return {
                "owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": False,
                "reason": str(remote_status.get("reason") or "remote_status_read_failed"),
                "error_class": "remote_status_read_failed", "admission_state": state,
            }
        version_id = remote_status["agent_version_id"]
        platform_status = remote_status["platform_status"]
        receipt = f"capafy:agent/{agent_id}/version/{version_id}:platform_status={platform_status}"
        proof = {
            "owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": True,
            "effected": True, "provider_receipt_id": receipt,
            "proof_kind": "official_capafy_publish_list_and_remote_status",
            "checked_at": now.isoformat(timespec="seconds"),
        }
        result: dict[str, Any] = {**proof, "admission_state": state}
        if not resolve:
            return result
        resolve_fn = resolve_unknown_fn
        if resolve_fn is None:
            from runtime.host.resource_admission import resolve_unknown_occurrence
            resolve_fn = resolve_unknown_occurrence
        result["closed"] = resolve_fn(
            OWNER_ID, occurrence_id, official_readback=lambda: proof, expected_state=state,
        )
        return result

    age_seconds = (now - queued_at).total_seconds()
    finished = (run_finished_fn or run_finished)(occurrence_id, queued_at) \
        if age_seconds > FINISHED_RUN_MIN_AGE_SECONDS else False
    if age_seconds <= NO_EFFECT_MIN_AGE_SECONDS and not finished:
        return {
            "owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": False,
            "reason": f"too_recent:{int(age_seconds)}s<={NO_EFFECT_MIN_AGE_SECONDS}s",
            "admission_state": state,
        }

    evidence_payload = {
        "owner_id": OWNER_ID, "occurrence_id": occurrence_id,
        "checked_at": now.isoformat(timespec="seconds"),
        "source": "packager.py publish-list (official Capafy seller API)",
        "publish_list_sha256": publish_list.get("sha256"),
        "agent_count": len(agents),
        "snapshot_used": bool(snapshot is not None and snapshot.get("ok")),
        "queued_at": queued_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_end": window_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verdict": "no_effect",
    }
    evidence_path = _append_evidence(evidence_dir, occurrence_id, evidence_payload)
    proof = {
        "owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": True,
        "effected": False, "proof_type": "pre_effect", "evidence_ref": str(evidence_path),
        "checked_at": now.isoformat(timespec="seconds"),
    }
    result = {**proof, "admission_state": state}
    if not resolve:
        return result
    resolve_fn = resolve_pre_effect_fn
    if resolve_fn is None:
        from runtime.host.resource_admission import resolve_pre_effect_occurrence
        resolve_fn = resolve_pre_effect_occurrence
    result["closed"] = resolve_fn(
        OWNER_ID, occurrence_id, pre_effect_readback=lambda: proof, expected_state=state,
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true")
    parser.add_argument("--record-snapshot", action="store_true",
                        help="Write the pre-dispatch snapshot for this occurrence and exit "
                             "(called at run start, never for reconciliation).")
    args = parser.parse_args(argv)
    if args.record_snapshot:
        snapshot = record_snapshot(args.occurrence)
        print(json.dumps(snapshot, sort_keys=True, default=str))
        return 0 if snapshot.get("ok") else 1
    try:
        result = reconcile(args.occurrence, resolve=args.resolve)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({
            "owner_id": OWNER_ID, "occurrence_id": args.occurrence, "verified": False,
            "error": f"{type(exc).__name__}:{exc}",
        }, sort_keys=True))
        print("CAPAFY_FACTORY_FENCE_RECONCILE=FAIL", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, default=str))
    if not result.get("verified"):
        print("CAPAFY_FACTORY_FENCE_RECONCILE=HELD")
        return 1
    if not args.resolve:
        print("CAPAFY_FACTORY_FENCE_RECONCILE=PROOF_READY")
        return 0
    if not result.get("closed"):
        print("CAPAFY_FACTORY_FENCE_RECONCILE=FAIL reason=admission_refused_close", file=sys.stderr)
        return 1
    print("CAPAFY_FACTORY_FENCE_RECONCILE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
