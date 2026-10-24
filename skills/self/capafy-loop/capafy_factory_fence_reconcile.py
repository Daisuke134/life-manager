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
still-fenced predecessor) had an effect. If the version is unchanged, its
``updated_at`` must be verifiably before ``queued_at`` to prove no effect;
missing, malformed, or newer timestamps stay inconclusive. When no snapshot
exists (e.g. runs before this feature shipped), numeric epoch seconds or
milliseconds and ISO timestamps inside
``[queued_at, queued_at + MAX_RUN_SECONDS]`` can prove an effect; missing or
out-of-window timestamps stay inconclusive.

Decision:
  - effected: a hit (new/updated agent) proves the effect happened -> read
    ``publish-remote-status`` for that agent's ``platform_status`` and close
    via ``resolve_unknown_occurrence`` with receipt
    ``capafy:agent/<id>/version/<vid>:platform_status=<n>``.
  - no-effect: a complete publish-list readback shows every unchanged agent
    has a verifiable timestamp before ``queued_at`` and enough time has passed
    (> MAX_RUN_SECONDS + a processing buffer) -> write an evidence JSON file
    and close via ``resolve_pre_effect_occurrence``.
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
import math
import os
import re
import sqlite3
import stat
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
FINISH_RECEIPT_KINDS = {
    "capafy_retry_existing_finish": {
        "action": "retry_existing", "key": "retry",
        "terminal": "SUBMITTED — {agent_id} finished CP2/CP3 after prepare",
    },
    "capafy_resume_draft_finish": {
        "action": "resume_draft", "key": "resume",
        "terminal": "RESUMED — {agent_id} finished CP2/CP3 deterministically",
    },
}
# Capafy's own API is a synchronous read (not an eventually-consistent listing
# like Instagram's), so this buffer only covers clock skew and admission-layer
# release latency, not provider propagation delay.
POST_PROCESSING_DELAY_SECONDS = 120
NO_EFFECT_MIN_AGE_SECONDS = MAX_RUN_SECONDS + POST_PROCESSING_DELAY_SECONDS
# Waiting MAX_RUN_SECONDS only guarantees the run is no longer in flight. When the run's own
# process is provably gone, an hour of waiting adds nothing: 2026-10-08 a PREPARE_FAILED run
# (no agent spend) fenced the factory for an hour, twice in one day.
FINISHED_RUN_MIN_AGE_SECONDS = 60


class InconclusiveReadback(Exception):
    """The official listing cannot safely prove either effect or no-effect."""


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
CAPAFY_DRAINER_EVIDENCE_ROOT = Path(
    "~/.local/state/life-manager/state/agent-runner-evidence/capafy-drainer"
).expanduser()
CAPAFY_DAILY_LOOP_LOG = Path(
    "~/.local/state/life-manager/state/capafy-autopublish/daily_loop.log"
).expanduser()
RUNTIME_EVENT_LOG = Path("~/.local/state/life-manager/events.jsonl").expanduser()
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
        return {
            "ok": True,
            "platform_status": status,
            "agent_version_id": str(version_id),
            "audit_status": latest.get("audit_status"),
            "is_confirmed_skills": latest.get("is_confirmed_skills"),
            "is_confirmed_config_keys": latest.get("is_confirmed_config_keys"),
            "package_uploaded": latest.get("package_uploaded"),
            "agent_type": latest.get("agent_type"),
        }
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


def _read_user_file(path: Path, *, private: bool = False) -> bytes | None:
    try:
        info = path.stat(follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or info.st_mode & 0o022
                or (private and info.st_mode & 0o077)):
            return None
        return path.read_bytes()
    except OSError:
        return None


def _parse_daily_loop_timestamp(value: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S").astimezone(dt.timezone.utc)
    except (OverflowError, ValueError):
        return None


def read_occurrence_bound_cp3_receipt(
    occurrence_id: str, queued_at: dt.datetime, window_end: dt.datetime, *,
    evidence_root: Path | None = None, publisher_log: Path | None = None,
    event_log: Path | None = None,
) -> dict[str, Any] | None:
    """Read an exact parent event, child summary and successful CP3 block."""
    evidence_root = evidence_root or CAPAFY_DRAINER_EVIDENCE_ROOT
    publisher_log = publisher_log or CAPAFY_DAILY_LOOP_LOG
    event_log = event_log or RUNTIME_EVENT_LOG
    if not occurrence_id.startswith(f"{OWNER_ID}:"):
        return None
    try:
        events = [(json.loads(line), line) for line in
                  _read_user_file(event_log).decode("utf-8").splitlines()
                  if occurrence_id in line]
        root_info = evidence_root.stat(follow_symlinks=False)
        if not stat.S_ISDIR(root_info.st_mode) or evidence_root.is_symlink():
            return None
    except (AttributeError, OSError, UnicodeDecodeError, ValueError):
        return None
    parent_run_id = occurrence_id.rsplit(":", 1)[-1]
    bound_events = [(row, line) for row, line in events
                    if isinstance(row, dict) and row.get("owner_id") == OWNER_ID
                    and row.get("job_id") == OWNER_ID and row.get("run_id") == parent_run_id
                    and row.get("occurrence_id") == occurrence_id
                    and row.get("effect_class") == "publish"]
    starts = [(row, line) for row, line in bound_events
              if row.get("phase") == "execute" and row.get("status") == "running"
              and row.get("effect_status") == "started"]
    terminals = [(row, line) for row, line in bound_events
                 if row.get("phase") == "report" and row.get("status") == "pass"
                 and row.get("effect_status") == "unknown"
                 and type(row.get("exit_code")) is int and row["exit_code"] == 0]
    if len(starts) != 1 or len(terminals) != 1:
        return None
    start, start_line = starts[0]
    terminal, terminal_line = terminals[0]
    parent_release = start.get("release_sha")
    start_at = _parse_updated_at(start.get("timestamp"))
    terminal_at = _parse_updated_at(terminal.get("timestamp"))
    if (not isinstance(parent_release, str) or not re.fullmatch(r"[0-9a-f]{40}", parent_release)
            or terminal.get("release_sha") != parent_release or start_at is None or terminal_at is None
            or start_at < queued_at - dt.timedelta(seconds=5)
            or start_at > window_end
            or terminal_at < start_at or terminal_at > window_end):
        return None

    candidates = []
    for run_dir in evidence_root.iterdir():
        epoch = run_dir.name.partition("-")[0]
        if (run_dir.is_symlink() or not run_dir.is_dir() or not epoch.isdigit()
                or not int(queued_at.timestamp()) - 120 <= int(epoch) <= int(window_end.timestamp()) + 1):
            continue
        summary_path = run_dir / "summary.json"
        summary_raw = _read_user_file(summary_path, private=True)
        if summary_raw is None:
            continue
        try:
            summary = json.loads(summary_raw)
        except (UnicodeDecodeError, ValueError):
            continue
        if isinstance(summary, dict) and summary.get("parent_lifecycle_occurrence_id") == occurrence_id:
            candidates.append((summary_path, summary, summary_raw))
    # Multiple child runs for one parent are ambiguous; do not choose one.
    if len(candidates) != 1:
        return None
    summary_path, summary, summary_raw = candidates[0]
    started_at = _parse_updated_at(summary.get("started_at"))
    finished_at = _parse_updated_at(summary.get("finished_at"))
    release_sha = summary.get("release_sha")
    child_run_id = summary.get("run_id")
    if (summary.get("owner_id") != OWNER_ID
            or summary.get("loop") != "capafy"
            or summary.get("task_label") != "capafy-drainer"
            or summary.get("task_class") != "application-lane-agent"
            or summary.get("status") != "success"
            or summary.get("parent_lifecycle_run_id") != parent_run_id
            or not isinstance(child_run_id, str) or not child_run_id
            or not isinstance(release_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", release_sha)
            or release_sha != parent_release
            or started_at is None or finished_at is None
            or started_at < queued_at or finished_at < started_at
            or finished_at > terminal_at or finished_at > window_end):
        return None

    try:
        lines = _read_user_file(publisher_log).decode("utf-8").splitlines()
    except (AttributeError, OSError, UnicodeDecodeError):
        return None
    summary_rows = []
    for index, line in enumerate(lines):
        if not line.startswith("{"):
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("run_id") == child_run_id:
            summary_rows.append((index, row))
    if len(summary_rows) != 1:
        return None

    summary_index, logged_summary = summary_rows[0]
    bound_summary_fields = (
        "owner_id", "loop", "run_id", "occurrence_id", "parent_lifecycle_run_id",
        "parent_lifecycle_occurrence_id", "release_sha", "started_at", "finished_at",
        "task_label", "task_class", "status",
    )
    if any(logged_summary.get(key) != summary.get(key) for key in bound_summary_fields):
        return None

    start_index = next((index for index in range(summary_index - 1, -1, -1)
                        if lines[index].startswith("=== ") and lines[index].endswith(" daily_loop start ===")), None)
    if start_index is None:
        return None
    if any(" daily_loop done rc=" in line for line in lines[start_index + 1:summary_index]):
        return None
    end_index = next((index for index in range(summary_index + 1, len(lines))
                      if lines[index].startswith("=== ") and " daily_loop done rc=" in lines[index]), None)
    if end_index is None:
        return None
    start_stamp = lines[start_index][4:-len(" daily_loop start ===")]
    end_stamp = lines[end_index][4:].split(" daily_loop done rc=", 1)[0]
    if start_stamp != end_stamp or any(line.startswith("=== ") and line.endswith(" daily_loop start ===")
                                       for line in lines[summary_index + 1:end_index]):
        return None
    publisher_started_at = _parse_daily_loop_timestamp(start_stamp)
    if (publisher_started_at is None or publisher_started_at < start_at
            or publisher_started_at > started_at):
        return None
    block = lines[start_index:end_index + 1]
    agent_ids = [line[9:] for line in block if line.startswith("AGENT_ID=")]
    version_ids = [line[17:] for line in block if line.startswith("AGENT_VERSION_ID=")]
    attempts = [(index, re.fullmatch(r"CP3 submit attempt (\d+)", line))
                for index, line in enumerate(block) if line.startswith("CP3 submit attempt ")]
    if (len(agent_ids) != 1 or not re.fullmatch(r"\d+", agent_ids[0])
            or len(version_ids) != 1 or not version_ids[0]
            or len(attempts) != 1 or attempts[0][1] is None or attempts[0][1].group(1) != "1"):
        return None
    agent_id, version_id = agent_ids[0], version_ids[0]
    verify_pattern = re.compile(
        r"platform_status=(\d+)\s+skills=(\d+)\s+cfg=(\d+)\s+package_uploaded=(\d+)\s+audit=(\d+)(?:\s|$)"
    )
    verifications = [(index, verify_pattern.search(line))
                     for index, line in enumerate(block) if verify_pattern.search(line)]
    ledger_positions = [index for index, line in enumerate(block)
                        if line == f"ledger appended {agent_id}"]
    final_verify = (
        len(verifications) == 1
        and all(value == "1" for value in verifications[0][1].groups())
        and verifications[0][0] > attempts[0][0]
        and len(ledger_positions) == 1
        and verifications[0][0] < ledger_positions[0]
    )
    ledger_appended = len(ledger_positions) == 1
    published = any(
        f"PUBLISHED + VERIFIED: agent_id={agent_id} " in line
        and "status=1 under review" in line for line in block
    )
    success_terminal = ("daily_loop done rc=0" in lines[end_index]
                        and f"SUBMITTED — {agent_id} finished CP2/CP3 after prepare" in lines[end_index])
    if not (final_verify and ledger_appended and published and success_terminal):
        return None

    block_raw = ("\n".join(block) + "\n").encode("utf-8")
    return {
        "occurrence_id": occurrence_id,
        "parent_release_sha": parent_release,
        "parent_terminal_at": terminal_at.isoformat(timespec="seconds"),
        "parent_event_sha256": hashlib.sha256(
            (start_line + "\n" + terminal_line + "\n").encode("utf-8")
        ).hexdigest(),
        "child_run_id": child_run_id,
        "release_sha": release_sha,
        "child_started_at": started_at.isoformat(timespec="seconds"),
        "child_finished_at": finished_at.isoformat(timespec="seconds"),
        "agent_id": agent_id,
        "agent_version_id": version_id,
        "child_summary_sha256": hashlib.sha256(summary_raw).hexdigest(),
        "publisher_log_block_sha256": hashlib.sha256(block_raw).hexdigest(),
        "summary_ref": str(summary_path),
    }


def _parse_updated_at(value: Any) -> dt.datetime | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        try:
            timestamp = value / 1000 if abs(value) >= 100_000_000_000 else value
            return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


TERMINAL_LEDGER = Path(
    "~/.local/state/life-manager/state/capafy-daily-terminals.jsonl"
).expanduser()
RUN_WINDOW_START_SKEW_SECONDS = 15


def read_occurrence_bound_run_window(
    occurrence_id: str, snapshot: dict[str, Any] | None, *,
    ledger_path: Path = TERMINAL_LEDGER,
) -> tuple[dt.datetime, dt.datetime] | None:
    """Return this run's own [start, terminal] window, or None unless it is unambiguous.

    The pre-dispatch snapshot is keyed by occurrence and captured when the wrapper starts; the
    wrapper writes its own execution id (UTC start + pid) and terminal record to the ledger.
    Exactly one execution starting within a few seconds of the snapshot, with a terminal record,
    binds the window to this occurrence.
    """
    if snapshot is None or not snapshot.get("ok"):
        return None
    start = _parse_updated_at(snapshot.get("captured_at"))
    if start is None:
        return None
    try:
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    terminals: dict[str, dt.datetime] = {}
    starts: dict[str, dt.datetime] = {}
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        execution = row.get("execution_id")
        if not isinstance(execution, str) or "-" not in execution:
            continue
        try:
            started = dt.datetime.strptime(
                execution.split("-", 1)[0], "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
        if abs((started - start).total_seconds()) > RUN_WINDOW_START_SKEW_SECONDS:
            continue
        starts[execution] = started
        if row.get("phase") == "terminal":
            observed = _parse_updated_at(row.get("observed_at"))
            if observed is not None:
                terminals[execution] = observed
    if len(starts) != 1:
        return None
    execution = next(iter(starts))
    end = terminals.get(execution)
    if end is None or end < start:
        return None
    return start, end


def find_in_place_update(
    agents: list[dict[str, Any]], snapshot: dict[str, Any], queued_at: dt.datetime,
    window: tuple[dt.datetime, dt.datetime],
) -> dict[str, Any] | None:
    """The single same-version Agent updated since queued_at, if it falls inside the run window."""
    run_start, run_end = window
    prior_versions = snapshot.get("latest_versions") or {}
    updated = []
    for agent in agents:
        agent_id = str(agent.get("agent_id") or "")
        if not agent_id:
            continue
        moment = _parse_updated_at(agent.get("updated_at"))
        if moment is None or moment < queued_at:
            continue
        updated.append((agent_id, agent, moment))
    if len(updated) != 1:
        return None
    agent_id, agent, moment = updated[0]
    current = str(agent.get("latest_agent_version_id") or "")
    if (prior_versions.get(agent_id) != current or not current
            or not run_start <= moment <= run_end):
        return None
    return {"agent_id": agent_id, "agent_version_id": current,
            "updated_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "run_start": run_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "run_end": run_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "receipt_kind": "agent_pass_in_place_update"}


def find_hit(agents: list[dict[str, Any]], snapshot: dict[str, Any] | None,
             queued_at: dt.datetime, window_end: dt.datetime) -> dict[str, Any] | None:
    """Return a proven effect; raise when the listing cannot prove no-effect."""
    if snapshot is not None and snapshot.get("ok"):
        prior_versions = snapshot.get("latest_versions") or {}
        unchanged = []
        for agent in agents:
            agent_id = agent.get("agent_id")
            if not agent_id:
                continue
            prior = prior_versions.get(str(agent_id))
            current = agent.get("latest_agent_version_id")
            if prior is None or prior != current:
                return agent
            unchanged.append(agent)
        for agent in unchanged:
            updated_at = _parse_updated_at(agent.get("updated_at"))
            if updated_at is None:
                raise InconclusiveReadback("same_version_updated_at_missing_or_malformed")
            if updated_at >= queued_at:
                raise InconclusiveReadback("same_version_updated_after_queued_at")
        if not _snapshot_matches_agent_set(snapshot, agents):
            raise InconclusiveReadback("snapshot_agent_set_mismatch")
        return None
    possible_hit = None
    ambiguous_timestamp = False
    for agent in agents:
        updated_at = _parse_updated_at(agent.get("updated_at"))
        if updated_at is None or updated_at > window_end:
            ambiguous_timestamp = True
        elif queued_at <= updated_at <= window_end:
            possible_hit = possible_hit or agent
    if possible_hit is not None:
        return possible_hit
    if ambiguous_timestamp:
        raise InconclusiveReadback("updated_at_missing_or_outside_occurrence_window")
    return None


def _snapshot_matches_agent_set(snapshot: dict[str, Any], agents: list[dict[str, Any]]) -> bool:
    prior_versions = snapshot.get("latest_versions")
    snapshot_count = snapshot.get("agent_count")
    if not isinstance(prior_versions, dict) or type(snapshot_count) is not int:
        return False
    snapshot_ids = list(prior_versions)
    current_ids = []
    for row in agents:
        if not isinstance(row, Mapping):
            return False
        agent_id = str(row.get("agent_id") or "").strip()
        if not agent_id:
            return False
        current_ids.append(agent_id)
    return (
        all(isinstance(agent_id, str) and agent_id for agent_id in snapshot_ids)
        and len(current_ids) == snapshot_count == len(snapshot_ids)
        and len(set(current_ids)) == len(current_ids)
        and set(current_ids) == set(snapshot_ids)
    )


def read_occurrence_bound_partial_effect_receipt(
    occurrence_id: str,
    queued_at: dt.datetime,
    window_end: dt.datetime,
    snapshot: dict[str, Any] | None,
    agents: list[dict[str, Any]],
    *,
    evidence_root: Path | None = None,
    publisher_log: Path | None = None,
    event_log: Path | None = None,
) -> dict[str, Any] | None:
    """Bind one same-version retry_existing draft update to its failed parent run."""
    evidence_root = evidence_root or CAPAFY_DRAINER_EVIDENCE_ROOT
    publisher_log = publisher_log or CAPAFY_DAILY_LOOP_LOG
    event_log = event_log or RUNTIME_EVENT_LOG
    if not occurrence_id.startswith(f"{OWNER_ID}:"):
        return None
    if (not isinstance(snapshot, dict) or snapshot.get("ok") is not True
            or snapshot.get("owner_id") != OWNER_ID
            or snapshot.get("occurrence_id") != occurrence_id):
        return None
    prior_versions = snapshot.get("latest_versions")
    if not isinstance(prior_versions, dict):
        return None
    snapshot_at = _parse_updated_at(snapshot.get("captured_at"))
    if (snapshot_at is None or snapshot_at < queued_at - dt.timedelta(seconds=5)
            or not _snapshot_matches_agent_set(snapshot, agents)):
        return None

    event_raw = _read_user_file(event_log)
    if event_raw is None:
        return None
    try:
        event_rows = [(json.loads(line), line) for line in event_raw.decode("utf-8").splitlines()
                      if occurrence_id in line]
        root_info = evidence_root.stat(follow_symlinks=False)
        if not stat.S_ISDIR(root_info.st_mode) or evidence_root.is_symlink():
            return None
    except (OSError, UnicodeDecodeError, ValueError):
        return None

    parent_run_id = occurrence_id.rsplit(":", 1)[-1]
    parent_events = [(row, line) for row, line in event_rows
                     if isinstance(row, dict) and row.get("owner_id") == OWNER_ID
                     and row.get("job_id") == OWNER_ID and row.get("run_id") == parent_run_id
                     and row.get("occurrence_id") == occurrence_id
                     and row.get("effect_class") == "publish"]
    starts = [(row, line) for row, line in parent_events
              if row.get("phase") == "execute" and row.get("status") == "running"
              and row.get("effect_status") == "started"]
    terminals = [(row, line) for row, line in parent_events
                 if row.get("phase") == "report" and row.get("status") == "fail"
                 and row.get("effect_status") == "unknown"
                 and row.get("error_class") == "entrypoint_exit_1"
                 and type(row.get("exit_code")) is int and row["exit_code"] == 1]
    if len(starts) != 1 or len(terminals) != 1:
        return None
    start, start_line = starts[0]
    terminal, terminal_line = terminals[0]
    parent_release = start.get("release_sha")
    start_at = _parse_updated_at(start.get("timestamp"))
    terminal_at = _parse_updated_at(terminal.get("timestamp"))
    if (not isinstance(parent_release, str) or not re.fullmatch(r"[0-9a-f]{40}", parent_release)
            or terminal.get("release_sha") != parent_release or start_at is None or terminal_at is None
            or start_at < queued_at - dt.timedelta(seconds=5)
            or start_at > window_end
            or terminal_at < start_at or terminal_at > window_end):
        return None

    child_candidates = []
    for run_dir in evidence_root.iterdir():
        epoch = run_dir.name.partition("-")[0]
        if (run_dir.is_symlink() or not run_dir.is_dir() or not epoch.isdigit()
                or not int(queued_at.timestamp()) - 120 <= int(epoch) <= int(window_end.timestamp()) + 1):
            continue
        summary_path = run_dir / "summary.json"
        summary_raw = _read_user_file(summary_path, private=True)
        if summary_raw is None:
            continue
        try:
            summary = json.loads(summary_raw)
        except (UnicodeDecodeError, ValueError):
            continue
        if (isinstance(summary, dict)
                and summary.get("parent_lifecycle_occurrence_id") == occurrence_id):
            child_candidates.append((run_dir, summary_path, summary, summary_raw))
    if len(child_candidates) != 1:
        return None

    run_dir, summary_path, summary, summary_raw = child_candidates[0]
    child_run_id = summary.get("run_id")
    child_started = _parse_updated_at(summary.get("started_at"))
    child_finished = _parse_updated_at(summary.get("finished_at"))
    child_release = summary.get("release_sha")
    if (summary.get("owner_id") != OWNER_ID or summary.get("loop") != "capafy"
            or summary.get("task_label") != "capafy-drainer"
            or summary.get("task_class") != "application-lane-agent"
            or summary.get("status") != "success"
            or summary.get("parent_lifecycle_run_id") != parent_run_id
            or not isinstance(child_run_id, str) or not child_run_id
            or child_release != parent_release
            or child_started is None or child_finished is None
            or child_started < start_at or child_finished < child_started
            or snapshot_at > child_started
            or child_finished > terminal_at or child_finished > window_end):
        return None

    result_path = Path(str(summary.get("result_path") or ""))
    if (result_path.parent != run_dir or result_path.is_symlink()
            or result_path.name != "attempt-01.result.json"):
        return None
    # agent_runner writes attempt results 0644; owner, nlink and no-write checks still apply.
    result_raw = _read_user_file(result_path)
    if result_raw is None:
        return None
    try:
        child_result = json.loads(result_raw)
    except (UnicodeDecodeError, ValueError):
        return None
    result_evidence = child_result.get("evidence") if isinstance(child_result, dict) else None
    if (child_result.get("status") != "ok" or not isinstance(result_evidence, list)
            or not all(isinstance(item, str) for item in result_evidence)):
        return None
    stopped = [re.fullmatch(
        r"STOPPED: agent ([0-9]+) remains platform_status=0; cannot claim publication\.", item
    ) for item in result_evidence]
    stopped = [match for match in stopped if match is not None]
    if (len(stopped) != 1
            or not any("CP1 saved" in item and "PRICES_MATCH 3" in item for item in result_evidence)
            or not any("is_confirmed_skills=true" in item
                       and "is_confirmed_config_keys=true"
                       and "package_uploaded=true" in item for item in result_evidence)
            or not any("CP3 did not produce official under-review readback" in item
                       and "no ledger/commit was made" in item for item in result_evidence)):
        return None
    agent_id = stopped[0].group(1)

    try:
        log_lines = _read_user_file(publisher_log).decode("utf-8").splitlines()
    except (AttributeError, OSError, UnicodeDecodeError):
        return None
    summary_rows = []
    for index, line in enumerate(log_lines):
        if not line.startswith("{"):
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("run_id") == child_run_id:
            summary_rows.append((index, row))
    if len(summary_rows) != 1:
        return None
    summary_index, logged_summary = summary_rows[0]
    bound_fields = (
        "owner_id", "loop", "run_id", "occurrence_id", "parent_lifecycle_run_id",
        "parent_lifecycle_occurrence_id", "release_sha", "started_at", "finished_at",
        "task_label", "task_class", "status",
    )
    if any(logged_summary.get(key) != summary.get(key) for key in bound_fields):
        return None
    start_index = next((index for index in range(summary_index - 1, -1, -1)
                        if log_lines[index].startswith("=== ")
                        and log_lines[index].endswith(" daily_loop start ===")), None)
    if start_index is None:
        return None
    end_index = next((index for index in range(summary_index + 1, len(log_lines))
                      if log_lines[index].startswith("===")
                      and " daily_loop done rc=" in log_lines[index]), None)
    if end_index is None:
        return None
    start_stamp = log_lines[start_index][4:-len(" daily_loop start ===")]
    end_stamp = log_lines[end_index][4:].split(" daily_loop done rc=", 1)[0]
    if (start_stamp != end_stamp
            or any(line.startswith("===") and line.endswith(" daily_loop start ===")
                   for line in log_lines[summary_index + 1:end_index])):
        return None
    publisher_started = _parse_daily_loop_timestamp(start_stamp)
    if publisher_started is None or publisher_started < start_at or publisher_started > child_started:
        return None
    block = log_lines[start_index:end_index + 1]
    if ("daily_loop done rc=1" not in log_lines[end_index]
            or "BLOCKED" not in log_lines[end_index]
            or "post-verdict=PUBLISHABLE" not in log_lines[end_index]
            or "marker NOT touched" not in log_lines[end_index]
            or any("CP3 submit attempt" in line or "ledger appended " in line
                   or "PUBLISHED + VERIFIED:" in line for line in block)):
        return None
    inventory_rows = []
    for line in block:
        if " inventory verdict=" not in line or " :: " not in line:
            continue
        try:
            inventory_rows.append(json.loads(line.split(" :: ", 1)[1]))
        except ValueError:
            continue
    if len(inventory_rows) != 1:
        return None
    inventory = inventory_rows[0]
    item = inventory.get("item") if isinstance(inventory, dict) else None
    if (inventory.get("action") != "retry_existing"
            or inventory.get("action_key") != f"retry:{agent_id}"
            or not isinstance(item, dict) or str(item.get("agent_id")) != agent_id):
        return None

    prior_versions = snapshot.get("latest_versions") or {}
    prior_version = prior_versions.get(agent_id)
    if not isinstance(prior_version, str) or not prior_version:
        return None
    matches = [row for row in agents if str(row.get("agent_id")) == agent_id]
    if len(matches) != 1 or str(matches[0].get("latest_agent_version_id") or "") != prior_version:
        return None
    updated_at = _parse_updated_at(matches[0].get("updated_at"))
    if (updated_at is None or updated_at < max(queued_at, start_at)
            or updated_at > min(window_end, child_finished, terminal_at)):
        return None
    same_version_updates = []
    for row in agents:
        row_id = str(row.get("agent_id") or "")
        if prior_versions.get(row_id) != row.get("latest_agent_version_id"):
            return None
        row_updated = _parse_updated_at(row.get("updated_at"))
        if row_updated is None:
            return None
        # A change after the window belongs to a later actor; it cannot undo this effect.
        if queued_at <= row_updated <= window_end:
            same_version_updates.append(row_id)
    if same_version_updates != [agent_id]:
        return None

    return {
        "receipt_kind": "partial_effect",
        "agent_id": agent_id,
        "agent_version_id": prior_version,
        "updated_at": updated_at.isoformat(timespec="seconds"),
        "parent_release_sha": parent_release,
        "parent_event_sha256": hashlib.sha256(
            (start_line + "\n" + terminal_line + "\n").encode("utf-8")
        ).hexdigest(),
        "parent_terminal_at": terminal_at.isoformat(timespec="seconds"),
        "child_run_id": child_run_id,
        "child_started_at": child_started.isoformat(timespec="seconds"),
        "child_finished_at": child_finished.isoformat(timespec="seconds"),
        "child_summary_sha256": hashlib.sha256(summary_raw).hexdigest(),
        "child_result_sha256": hashlib.sha256(result_raw).hexdigest(),
        "publisher_log_block_sha256": hashlib.sha256(
            ("\n".join(block) + "\n").encode("utf-8")
        ).hexdigest(),
        "summary_ref": str(summary_path),
        "result_ref": str(result_path),
    }


def read_occurrence_bound_deterministic_retry_finish_receipt(
    occurrence_id: str,
    queued_at: dt.datetime,
    window_end: dt.datetime,
    snapshot: dict[str, Any] | None,
    agents: list[dict[str, Any]],
    *,
    publisher_log: Path | None = None,
    event_log: Path | None = None,
) -> dict[str, Any] | None:
    """Bind a deterministic same-version CP3 finish to its parent lifecycle run."""
    publisher_log = publisher_log or CAPAFY_DAILY_LOOP_LOG
    event_log = event_log or RUNTIME_EVENT_LOG
    if (not occurrence_id.startswith(f"{OWNER_ID}:")
            or not isinstance(snapshot, dict) or snapshot.get("ok") is not True
            or snapshot.get("owner_id") != OWNER_ID
            or snapshot.get("occurrence_id") != occurrence_id
            or not isinstance(snapshot.get("latest_versions"), dict)):
        return None
    snapshot_at = _parse_updated_at(snapshot.get("captured_at"))
    if (snapshot_at is None or snapshot_at < queued_at - dt.timedelta(seconds=5)
            or not _snapshot_matches_agent_set(snapshot, agents)):
        return None

    event_raw = _read_user_file(event_log)
    log_raw = _read_user_file(publisher_log)
    if event_raw is None or log_raw is None:
        return None
    try:
        event_rows = [(json.loads(line), line) for line in event_raw.decode("utf-8").splitlines()
                      if occurrence_id in line]
        log_lines = log_raw.decode("utf-8").splitlines()
    except (UnicodeDecodeError, ValueError):
        return None
    parent_run_id = occurrence_id.rsplit(":", 1)[-1]
    parent_events = [(row, line) for row, line in event_rows
                     if isinstance(row, dict) and row.get("owner_id") == OWNER_ID
                     and row.get("job_id") == OWNER_ID and row.get("run_id") == parent_run_id
                     and row.get("occurrence_id") == occurrence_id
                     and row.get("effect_class") == "publish"]
    starts = [(row, line) for row, line in parent_events
              if row.get("phase") == "execute" and row.get("status") == "running"
              and row.get("effect_status") == "started"]
    terminals = [(row, line) for row, line in parent_events
                 if row.get("phase") == "report" and row.get("status") == "pass"
                 and row.get("effect_status") == "unknown"
                 and type(row.get("exit_code")) is int and row["exit_code"] == 0]
    if len(starts) != 1 or len(terminals) != 1:
        return None
    start, start_line = starts[0]
    terminal, terminal_line = terminals[0]
    release_sha = start.get("release_sha")
    start_at = _parse_updated_at(start.get("timestamp"))
    terminal_at = _parse_updated_at(terminal.get("timestamp"))
    if (not isinstance(release_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", release_sha)
            or terminal.get("release_sha") != release_sha or start_at is None or terminal_at is None
            or start_at < queued_at - dt.timedelta(seconds=5)
            or start_at > window_end
            or terminal_at < start_at or terminal_at > window_end):
        return None

    bound_receipts = []
    for index, line in enumerate(log_lines):
        prefix = "CAPAFY_RETRY_FINISH_RECEIPT="
        if not line.startswith(prefix):
            continue
        try:
            payload = json.loads(line[len(prefix):])
        except ValueError:
            continue
        if (isinstance(payload, dict) and payload.get("owner_id") == OWNER_ID
                and payload.get("run_id") == parent_run_id
                and payload.get("occurrence_id") == occurrence_id):
            bound_receipts.append((index, line, payload))
    if len(bound_receipts) != 1:
        return None
    receipt_index, receipt_line, receipt = bound_receipts[0]
    agent_id = receipt.get("agent_id")
    version_id = receipt.get("agent_version_id")
    checked_at = _parse_updated_at(receipt.get("verified_at"))
    expected_receipt_id = f"capafy:agent/{agent_id}/version/{version_id}:platform_status=1"
    # retry_existing and resume_draft both finish an existing draft through publish_finish.sh.
    kind = FINISH_RECEIPT_KINDS.get(receipt.get("event"))
    if (kind is None
            or receipt.get("release_sha") != release_sha
            or not isinstance(agent_id, str) or not re.fullmatch(r"[0-9]+", agent_id)
            or not isinstance(version_id, str) or not version_id
            or receipt.get("action_key") != f"{kind['key']}:{agent_id}"
            or type(receipt.get("cp3_attempt")) is not int or receipt["cp3_attempt"] != 1
            or type(receipt.get("platform_status")) is not int or receipt["platform_status"] != 1
            or receipt.get("is_confirmed_skills") is not True
            or receipt.get("is_confirmed_config_keys") is not True
            or receipt.get("package_uploaded") is not True
            or receipt.get("provider_receipt_id") != expected_receipt_id
            or checked_at is None or checked_at < start_at or checked_at > terminal_at):
        return None

    start_index = next((index for index in range(receipt_index - 1, -1, -1)
                        if log_lines[index].startswith("=== ")
                        and log_lines[index].endswith(" daily_loop start ===")), None)
    end_index = next((index for index in range(receipt_index + 1, len(log_lines))
                      if log_lines[index].startswith("===")
                      and " daily_loop done rc=" in log_lines[index]), None)
    if start_index is None or end_index is None:
        return None
    start_stamp = log_lines[start_index][4:-len(" daily_loop start ===")]
    end_stamp = log_lines[end_index][4:].split(" daily_loop done rc=", 1)[0]
    if start_stamp != end_stamp:
        return None
    publisher_started = _parse_daily_loop_timestamp(start_stamp)
    if publisher_started is None or publisher_started < start_at or publisher_started > checked_at:
        return None
    block = log_lines[start_index:end_index + 1]
    if ("daily_loop done rc=0" not in log_lines[end_index]
            or kind["terminal"].format(agent_id=agent_id) not in log_lines[end_index]):
        return None
    if [line[9:] for line in block if line.startswith("AGENT_ID=")] != [agent_id]:
        return None
    if [line[17:] for line in block if line.startswith("AGENT_VERSION_ID=")] != [version_id]:
        return None
    attempts = [re.fullmatch(r"CP3 submit attempt (\d+)", line) for line in block
                if line.startswith("CP3 submit attempt ")]
    if len(attempts) != 1 or attempts[0] is None or attempts[0].group(1) != "1":
        return None
    verify_pattern = re.compile(
        r"platform_status=(\d+)\s+skills=(\d+)\s+cfg=(\d+)\s+package_uploaded=(\d+)\s+audit=(\d+)(?:\s|$)"
    )
    verifications = [verify_pattern.search(line) for line in block]
    verifications = [match for match in verifications if match is not None]
    ledger_positions = [i for i, line in enumerate(block) if line == f"ledger appended {agent_id}"]
    if (len(verifications) != 1 or any(value != "1" for value in verifications[0].groups())
            or len(ledger_positions) != 1):
        return None
    if not any(f"PUBLISHED + VERIFIED: agent_id={agent_id} " in line
               and "status=1 under review" in line for line in block):
        return None
    if not any("inventory verdict=" in line and " :: " in line
               and (lambda row: isinstance(row, dict)
                    and row.get("action") == kind["action"]
                    and row.get("action_key") == f"{kind['key']}:{agent_id}")(json.loads(line.split(" :: ", 1)[1]))
               for line in block if line.startswith(tuple(str(i) for i in range(10)))):
        return None

    prior_versions = snapshot.get("latest_versions") or {}
    if prior_versions.get(agent_id) != version_id:
        return None
    matches = [row for row in agents if str(row.get("agent_id")) == agent_id]
    if len(matches) != 1 or str(matches[0].get("latest_agent_version_id") or "") != version_id:
        return None
    updated_at = _parse_updated_at(matches[0].get("updated_at"))
    if updated_at is None or updated_at < start_at or updated_at > terminal_at:
        return None
    same_version_updates = []
    for row in agents:
        row_id = str(row.get("agent_id") or "")
        if prior_versions.get(row_id) != row.get("latest_agent_version_id"):
            return None
        row_updated = _parse_updated_at(row.get("updated_at"))
        if row_updated is None:
            return None
        # A change after the window belongs to a later actor; it cannot undo this effect.
        if queued_at <= row_updated <= window_end:
            same_version_updates.append(row_id)
    if same_version_updates != [agent_id]:
        return None
    return {
        "receipt_kind": "deterministic_retry_finish",
        "owner_id": OWNER_ID, "occurrence_id": occurrence_id,
        "parent_run_id": parent_run_id, "parent_release_sha": release_sha,
        "parent_terminal_at": terminal_at.isoformat(timespec="seconds"),
        "parent_event_sha256": hashlib.sha256(
            (start_line + "\n" + terminal_line + "\n").encode("utf-8")
        ).hexdigest(),
        "agent_id": agent_id, "agent_version_id": version_id,
        "updated_at": updated_at.isoformat(timespec="seconds"),
        "verified_at": checked_at.isoformat(timespec="seconds"),
        "receipt_line_sha256": hashlib.sha256(receipt_line.encode("utf-8")).hexdigest(),
        "publisher_log_block_sha256": hashlib.sha256(
            ("\n".join(block) + "\n").encode("utf-8")
        ).hexdigest(),
    }


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
    run_window_fn: Callable[[str, dict[str, Any] | None], tuple[dt.datetime, dt.datetime] | None] | None = None,
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
    bound_receipt = None
    same_version_update = None
    same_version_remote_status = None
    try:
        hit = find_hit(agents, snapshot, queued_at, window_end)
    except InconclusiveReadback as exc:
        if str(exc) == "same_version_updated_after_queued_at" and state == "released":
            age_seconds = (now - queued_at).total_seconds()
            finished = (run_finished_fn or run_finished)(occurrence_id, queued_at) \
                if age_seconds > FINISHED_RUN_MIN_AGE_SECONDS else False
            if finished and snapshot is not None and snapshot.get("ok"):
                bound_receipt = read_occurrence_bound_cp3_receipt(occurrence_id, queued_at, window_end)
                if bound_receipt is not None:
                    agent_id = bound_receipt["agent_id"]
                    version_id = bound_receipt["agent_version_id"]
                    prior = (snapshot.get("latest_versions") or {}).get(agent_id)
                    matches = [row for row in agents if str(row.get("agent_id")) == agent_id]
                    if (prior == version_id and len(matches) == 1
                            and str(matches[0].get("latest_agent_version_id")) == version_id):
                        hit = matches[0]
                    else:
                        bound_receipt = None
        if bound_receipt is None and str(exc) == "same_version_updated_after_queued_at":
            age_seconds = (now - queued_at).total_seconds()
            finished = (run_finished_fn or run_finished)(occurrence_id, queued_at) \
                if age_seconds > FINISHED_RUN_MIN_AGE_SECONDS else False
            deterministic_receipt = (
                read_occurrence_bound_deterministic_retry_finish_receipt(
                    occurrence_id, queued_at, window_end, snapshot, agents,
                ) if finished else None
            )
            if deterministic_receipt is not None:
                candidate_id = deterministic_receipt["agent_id"]
                matches = [row for row in agents
                           if str(row.get("agent_id")) == candidate_id
                           and str(row.get("latest_agent_version_id") or "")
                           == deterministic_receipt["agent_version_id"]]
                if len(matches) != 1:
                    deterministic_receipt = None
                else:
                    remote = read_remote_status_fn(candidate_id)
                    flags_confirmed = all(
                        remote.get(field) is True
                        or (type(remote.get(field)) is int and remote.get(field) == 1)
                        for field in (
                            "is_confirmed_skills",
                            "is_confirmed_config_keys",
                            "package_uploaded",
                        )
                    )
                    if (remote.get("ok") is not True
                            or remote.get("agent_version_id")
                            != deterministic_receipt["agent_version_id"]
                            or type(remote.get("platform_status")) is not int
                            or remote.get("platform_status") != 1
                            or remote.get("agent_type") != "run_online"
                            or not flags_confirmed):
                        return {
                            "owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                            "verified": False,
                            "reason": "deterministic_retry_official_status_mismatch",
                            "error_class": "ambiguous_provider_readback",
                            "admission_state": state,
                        }
                    hit = matches[0]
                    same_version_remote_status = remote
                    same_version_update = deterministic_receipt
        if (bound_receipt is None and same_version_update is None
                and str(exc) == "same_version_updated_after_queued_at"):
            age_seconds = (now - queued_at).total_seconds()
            finished = (run_finished_fn or run_finished)(occurrence_id, queued_at) \
                if age_seconds > FINISHED_RUN_MIN_AGE_SECONDS else False
            if finished:
                same_version_update = read_occurrence_bound_partial_effect_receipt(
                    occurrence_id, queued_at, window_end, snapshot, agents,
                )
            if same_version_update is not None:
                candidate_id = same_version_update["agent_id"]
                matches = [row for row in agents
                           if str(row.get("agent_id")) == candidate_id
                           and str(row.get("latest_agent_version_id") or "")
                           == same_version_update["agent_version_id"]]
                if len(matches) != 1:
                    same_version_update = None
                else:
                    remote = read_remote_status_fn(candidate_id)
                    flags_confirmed = all(
                        remote.get(field) is True
                        or (type(remote.get(field)) is int and remote.get(field) == 1)
                        for field in (
                            "is_confirmed_skills",
                            "is_confirmed_config_keys",
                            "package_uploaded",
                        )
                    )
                    if (remote.get("ok") is True
                            and remote.get("agent_version_id")
                            == same_version_update["agent_version_id"]
                            and type(remote.get("platform_status")) is int
                            and remote.get("platform_status") == 0
                            and remote.get("agent_type") == "run_online"
                            and flags_confirmed):
                        hit = matches[0]
                        same_version_remote_status = remote
                    else:
                        return {
                            "owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                            "verified": False, "reason": "partial_effect_remote_status_mismatch",
                            "error_class": "ambiguous_provider_readback",
                            "admission_state": state,
                        }
        if (bound_receipt is None and same_version_update is None
                and str(exc) == "same_version_updated_after_queued_at"
                and snapshot is not None and snapshot.get("ok")):
            window = (run_window_fn or read_occurrence_bound_run_window)(occurrence_id, snapshot)
            candidate = (find_in_place_update(agents, snapshot, queued_at, window)
                         if window is not None else None)
            if candidate is not None:
                remote = read_remote_status_fn(candidate["agent_id"])
                if (remote.get("ok") is True
                        and str(remote.get("agent_version_id")) == candidate["agent_version_id"]
                        and type(remote.get("platform_status")) is int
                        and remote.get("platform_status") >= 0):
                    hit = next(row for row in agents
                               if str(row.get("agent_id")) == candidate["agent_id"])
                    same_version_remote_status = remote
                    same_version_update = candidate
                else:
                    return {
                        "owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                        "verified": False, "reason": "agent_pass_remote_status_mismatch",
                        "error_class": "ambiguous_provider_readback",
                        "admission_state": state,
                    }
        if bound_receipt is None and same_version_update is None:
            return {
                "owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": False,
                "reason": str(exc), "error_class": "ambiguous_provider_readback",
                "admission_state": state,
            }

    if hit is not None:
        agent_id = str(hit["agent_id"])
        remote_status = same_version_remote_status or read_remote_status_fn(agent_id)
        if not remote_status.get("ok"):
            return {
                "owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": False,
                "reason": str(remote_status.get("reason") or "remote_status_read_failed"),
                "error_class": "remote_status_read_failed", "admission_state": state,
            }
        version_id = remote_status["agent_version_id"]
        platform_status = remote_status["platform_status"]
        evidence_ref = None
        if bound_receipt is not None:
            if (str(version_id) != bound_receipt["agent_version_id"]
                    or type(platform_status) is not int or platform_status <= 0):
                return {
                    "owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": False,
                    "reason": "occurrence_bound_remote_status_mismatch",
                    "error_class": "ambiguous_provider_readback", "admission_state": state,
                }
            evidence = {
                "owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                "checked_at": now.isoformat(timespec="seconds"),
                "source": "occurrence-bound Capafy drainer summary and CP3 log plus official readback",
                "child_run_id": bound_receipt["child_run_id"],
                "child_release_sha": bound_receipt["release_sha"],
                "parent_release_sha": bound_receipt["parent_release_sha"],
                "parent_event_sha256": bound_receipt["parent_event_sha256"],
                "parent_terminal_at": bound_receipt["parent_terminal_at"],
                "child_summary_ref": bound_receipt["summary_ref"],
                "child_summary_sha256": bound_receipt["child_summary_sha256"],
                "publisher_log_block_sha256": bound_receipt["publisher_log_block_sha256"],
                "agent_id": agent_id, "agent_version_id": version_id,
                "platform_status": platform_status,
                "publish_list_sha256": publish_list.get("sha256"), "verdict": "effected",
            }
            evidence_ref = str(_append_evidence(evidence_dir, occurrence_id, evidence))
        elif (same_version_update is not None
              and same_version_update.get("receipt_kind") == "deterministic_retry_finish"):
            evidence = {
                "owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                "checked_at": now.isoformat(timespec="seconds"),
                "source": "occurrence-bound deterministic retry_existing receipt plus official status",
                "parent_run_id": same_version_update["parent_run_id"],
                "parent_release_sha": same_version_update["parent_release_sha"],
                "parent_event_sha256": same_version_update["parent_event_sha256"],
                "parent_terminal_at": same_version_update["parent_terminal_at"],
                "receipt_line_sha256": same_version_update["receipt_line_sha256"],
                "publisher_log_block_sha256": same_version_update["publisher_log_block_sha256"],
                "agent_id": agent_id, "agent_version_id": str(version_id),
                "updated_at": same_version_update["updated_at"],
                "verified_at": same_version_update["verified_at"],
                "platform_status": platform_status,
                "audit_status": remote_status.get("audit_status"),
                "is_confirmed_skills": remote_status.get("is_confirmed_skills"),
                "is_confirmed_config_keys": remote_status.get("is_confirmed_config_keys"),
                "package_uploaded": remote_status.get("package_uploaded"),
                "publish_list_sha256": publish_list.get("sha256"),
                "verdict": "deterministic_retry_finish_confirmed",
            }
            evidence_ref = str(_append_evidence(evidence_dir, occurrence_id, evidence))
        elif (same_version_update is not None
              and same_version_update.get("receipt_kind") == "agent_pass_in_place_update"):
            evidence = {
                "owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                "checked_at": now.isoformat(timespec="seconds"),
                "source": "wrapper terminal ledger run window plus official publish-list and publish-remote-status",
                "queued_at": queued_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "run_start": same_version_update["run_start"],
                "run_end": same_version_update["run_end"],
                "agent_id": agent_id, "agent_version_id": str(version_id),
                "updated_at": same_version_update["updated_at"],
                "platform_status": platform_status,
                "audit_status": remote_status.get("audit_status"),
                "is_confirmed_skills": remote_status.get("is_confirmed_skills"),
                "is_confirmed_config_keys": remote_status.get("is_confirmed_config_keys"),
                "publish_list_sha256": publish_list.get("sha256"),
                "verdict": "agent_pass_in_place_update",
            }
            evidence_ref = str(_append_evidence(evidence_dir, occurrence_id, evidence))
        elif same_version_update is not None:
            evidence = {
                "owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                "checked_at": now.isoformat(timespec="seconds"),
                "source": "occurrence-bound retry_existing child result plus official publish-list and publish-remote-status",
                "queued_at": queued_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "window_end": window_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "parent_release_sha": same_version_update["parent_release_sha"],
                "parent_event_sha256": same_version_update["parent_event_sha256"],
                "parent_terminal_at": same_version_update["parent_terminal_at"],
                "child_run_id": same_version_update["child_run_id"],
                "child_started_at": same_version_update["child_started_at"],
                "child_finished_at": same_version_update["child_finished_at"],
                "child_summary_sha256": same_version_update["child_summary_sha256"],
                "child_result_sha256": same_version_update["child_result_sha256"],
                "publisher_log_block_sha256": same_version_update["publisher_log_block_sha256"],
                "agent_id": agent_id, "agent_version_id": str(version_id),
                "updated_at": same_version_update["updated_at"],
                "platform_status": platform_status,
                "audit_status": remote_status.get("audit_status"),
                "is_confirmed_skills": remote_status.get("is_confirmed_skills"),
                "is_confirmed_config_keys": remote_status.get("is_confirmed_config_keys"),
                "package_uploaded": remote_status.get("package_uploaded"),
                "publish_list_sha256": publish_list.get("sha256"),
                "verdict": "partial_effect_confirmed",
            }
            evidence_ref = str(_append_evidence(evidence_dir, occurrence_id, evidence))
        receipt = f"capafy:agent/{agent_id}/version/{version_id}:platform_status={platform_status}"
        if (same_version_update is not None
                and same_version_update.get("receipt_kind") == "partial_effect"):
            receipt += ":package_uploaded=1"
        proof = {
            "owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": True,
            "effected": True, "provider_receipt_id": receipt,
            "proof_kind": ("occurrence_bound_capafy_cp3_and_remote_status"
                           if bound_receipt is not None else
                           "occurrence_bound_capafy_deterministic_retry_finish"
                           if (same_version_update is not None
                               and same_version_update.get("receipt_kind") == "deterministic_retry_finish") else
                           "occurrence_bound_capafy_agent_pass_in_place_update"
                           if (same_version_update is not None
                               and same_version_update.get("receipt_kind") == "agent_pass_in_place_update") else
                           "occurrence_bound_capafy_partial_package_upload"
                           if same_version_update is not None else
                           "official_capafy_publish_list_and_remote_status"),
            "checked_at": now.isoformat(timespec="seconds"),
        }
        if bound_receipt is not None:
            proof.update({
                "official_readback_ref": receipt, "child_run_id": bound_receipt["child_run_id"],
                "parent_release_sha": bound_receipt["parent_release_sha"],
                "agent_id": agent_id, "agent_version_id": version_id,
                "platform_status": platform_status, "evidence_ref": evidence_ref,
            })
        elif (same_version_update is not None
              and same_version_update.get("receipt_kind") == "deterministic_retry_finish"):
            proof.update({
                "official_readback_ref": receipt, "run_id": same_version_update["parent_run_id"],
                "parent_release_sha": same_version_update["parent_release_sha"],
                "receipt_line_sha256": same_version_update["receipt_line_sha256"],
                "agent_id": agent_id, "agent_version_id": version_id,
                "platform_status": platform_status, "evidence_ref": evidence_ref,
            })
        elif (same_version_update is not None
              and same_version_update.get("receipt_kind") == "agent_pass_in_place_update"):
            proof.update({
                "official_readback_ref": receipt, "agent_id": agent_id,
                "agent_version_id": version_id, "platform_status": platform_status,
                "updated_at": same_version_update["updated_at"], "evidence_ref": evidence_ref,
            })
        elif same_version_update is not None:
            proof.update({
                "official_readback_ref": receipt, "agent_id": agent_id,
                "agent_version_id": version_id, "platform_status": platform_status,
                "package_uploaded": remote_status.get("package_uploaded"),
                "updated_at": same_version_update["updated_at"],
                "evidence_ref": evidence_ref,
            })
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
