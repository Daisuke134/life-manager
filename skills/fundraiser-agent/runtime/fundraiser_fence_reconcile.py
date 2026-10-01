#!/usr/bin/env python3
"""Close one fundraiser effect_unknown admission fence.

fundraiser's real external effect (a submitted program application) only
starts after run.sh has cleared its disk and browser-lease preflight gates,
created the run's evidence directory, and handed the runtime prompt to the
agent runner (see skills/fundraiser-agent/runtime/run.sh). The most common
fence -- observed live 2026-09-27 for occurrence
fundraiser:18d93c1c4f16c148-65964 -- is the entrypoint dying at one of those
preflight gates (exit 75, ``failure_layer":"entrypoint"``,
``effect_identity_status":"not_written"`` in events.jsonl) before any
evidence directory, and therefore before any browser action, ever existed.

Decision (mirrors capafy_ig_fence_reconcile.py's rule: only positive proof
closes a fence, never a guess):
  - The occurrence's own durable admission-layer event already says the
    entrypoint aborted before writing an effect identity, AND no evidence
    directory (the durable pre-dispatch marker: run.sh creates
    ``evidence/<run_id>/`` right before invoking the agent) was created
    anywhere in the account's plausible run window: proof of no dispatch,
    close via ``resolve_pre_effect_occurrence``.
  - An evidence directory *does* exist in that window with a
    ``submitted_verified`` row in application-receipts.jsonl for it: proof an
    application really was submitted, close via ``resolve_unknown_occurrence``
    with that receipt (completion_png/telegram_photo_message_id) as the
    provider receipt.
  - Anything else (an evidence directory exists but its outcome cannot be
    read back cleanly, or the admission-layer event does not show the
    entrypoint-preflight signature) is inconclusive: stays fenced.

Usage:
    python3 fundraiser_fence_reconcile.py --occurrence fundraiser:<run_id> [--resolve]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import stat
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OWNER_ID = "fundraiser"
STATE_ROOT = Path("~/.local/state/life-manager/fundraiser").expanduser()
EVENTS_PATH = STATE_ROOT / "events.jsonl"
EVIDENCE_ROOT = STATE_ROOT / "evidence"
RECEIPTS_PATH = STATE_ROOT / "application-receipts.jsonl"
MARKERS_ROOT = STATE_ROOT / "effect-markers"
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
MARKER_PHASES = frozenset({"pre_effect", "effect_attempted", "human_required", "post_effect_verified"})
# run.sh: RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$" and EVIDENCE_DIR="evidence/$RUN_ID".
EVIDENCE_DIR_NAME = re.compile(r"^(\d{8}T\d{6}Z)-\d+$")
# Preflight gates in run.sh exit either 2 (hard/misconfigured) or 75
# (deferred/no-mutation, per AGENTS.md's launchctl-safe convention); only 75 is
# ever a legitimate pre-effect signature because 2 can also fire deep inside a
# canonical-context or deck preflight that already ran after the evidence
# directory existed. Being conservative here costs nothing but a held fence.
PRE_EFFECT_EXIT_CODES = {75}
# Generous ceiling for the whole preflight sequence (disk check, browser lease
# acquire/recovery retries, node/context checks) between the "running" event
# and the "fail" event -- measured live at 32s; this leaves ample margin
# without accepting an evidence directory from an unrelated later run.
PREFLIGHT_WINDOW_SECONDS = 180


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    with path.open(encoding="utf-8") as source:
        for line in source:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


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


def _occurrence_events(occurrence_id: str, events_path: Path) -> list[dict[str, Any]]:
    return [row for row in _read_jsonl(events_path) if row.get("occurrence_id") == occurrence_id]


def _marker_path(markers_root: Path, owner_id: str, occurrence_id: str) -> Path | None:
    if (owner_id != OWNER_ID or not SAFE_ID.fullmatch(occurrence_id)
            or not occurrence_id.startswith(f"{owner_id}:")):
        return None
    run_id = occurrence_id[len(owner_id) + 1:]
    if not SAFE_ID.fullmatch(run_id):
        return None
    return markers_root / f"{run_id}.json"


def _read_marker(path: Path | None, owner_id: str, occurrence_id: str) -> dict[str, Any] | None:
    if path is None:
        return None
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            return None
        with os.fdopen(descriptor, "r", encoding="utf-8") as source:
            descriptor = -1
            marker = json.load(source)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if (
        not isinstance(marker, dict)
        or marker.get("schema_version") != 1
        or marker.get("owner_id") != owner_id
        or marker.get("occurrence_id") != occurrence_id
        or marker.get("phase") not in MARKER_PHASES
        or marker.get("effect") not in {0, 1}
    ):
        return None
    return marker


def _evidence_dir_timestamps(evidence_root: Path) -> list[dt.datetime]:
    if not evidence_root.is_dir():
        return []
    timestamps = []
    for child in evidence_root.iterdir():
        if not child.is_dir():
            continue
        match = EVIDENCE_DIR_NAME.match(child.name)
        if not match:
            continue
        try:
            timestamps.append(dt.datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(
                tzinfo=dt.timezone.utc,
            ))
        except ValueError:
            continue
    return timestamps


def pre_effect_proof(
    owner_id: str, occurrence_id: str, *,
    events_path: Path = EVENTS_PATH,
    evidence_root: Path = EVIDENCE_ROOT,
    markers_root: Path = MARKERS_ROOT,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Build a resolve_pre_effect_occurrence-shaped proof, or an unverified one."""
    marker = _read_marker(_marker_path(markers_root, owner_id, occurrence_id), owner_id, occurrence_id)
    if marker is not None:
        phase = marker["phase"]
        if phase == "pre_effect" and marker["effect"] == 0:
            run_id = occurrence_id[len(owner_id) + 1:]
            return {
                "owner_id": owner_id,
                "occurrence_id": occurrence_id,
                "verified": True,
                "proof_type": "pre_effect",
                "classification": "pre_effect",
                "evidence_ref": f"lm-fundraiser-marker://{owner_id}/{run_id}/effect-marker.json",
                "checked_at": (now or dt.datetime.now(dt.timezone.utc)).isoformat(timespec="seconds"),
            }
        if phase == "human_required":
            return {
                "owner_id": owner_id,
                "occurrence_id": occurrence_id,
                "verified": False,
                "classification": "human_required",
                "reason": "human_required",
            }
        return {
            "owner_id": owner_id,
            "occurrence_id": occurrence_id,
            "verified": False,
            "classification": "post_effect",
            "reason": "post_effect_readback_required",
        }
    events = _occurrence_events(occurrence_id, events_path)
    started = next((row for row in events if row.get("status") == "running"), None)
    failed = next((
        row for row in events
        if row.get("status") == "fail"
        and row.get("failure_layer") == "entrypoint"
        and row.get("effect_identity_status") == "not_written"
        and row.get("exit_code") in PRE_EFFECT_EXIT_CODES
    ), None)
    unverified = {
        "owner_id": owner_id, "occurrence_id": occurrence_id,
        "verified": False, "classification": "unknown",
    }
    if started is None or failed is None:
        return {**unverified, "reason": "no_entrypoint_preflight_signature"}
    try:
        start_ts = dt.datetime.fromisoformat(str(started["timestamp"]).replace("Z", "+00:00"))
        fail_ts = dt.datetime.fromisoformat(str(failed["timestamp"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return {**unverified, "reason": "event_timestamps_unavailable"}
    window_start = start_ts - dt.timedelta(seconds=5)
    window_end = fail_ts + dt.timedelta(seconds=PREFLIGHT_WINDOW_SECONDS)
    in_window = [ts for ts in _evidence_dir_timestamps(evidence_root) if window_start <= ts <= window_end]
    if in_window:
        return {**unverified, "reason": "evidence_directory_exists_in_window"}
    return {
        "owner_id": owner_id,
        "occurrence_id": occurrence_id,
        "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": f"events.jsonl:{occurrence_id}@{failed['timestamp']}:no_evidence_dir_in_window",
        "checked_at": (now or dt.datetime.now(dt.timezone.utc)).isoformat(timespec="seconds"),
    }


def reconcile(
    occurrence_id: str, *,
    events_path: Path = EVENTS_PATH,
    evidence_root: Path = EVIDENCE_ROOT,
    markers_root: Path = MARKERS_ROOT,
    fenced_row_fn: Callable[[str, str], tuple[str, dt.datetime]] = fenced_row,
    resolve_fn: Callable[..., bool] | None = None,
    now: dt.datetime | None = None,
    resolve: bool = False,
) -> dict[str, Any]:
    state, _queued_at = fenced_row_fn(OWNER_ID, occurrence_id)
    proof = pre_effect_proof(
        OWNER_ID, occurrence_id, events_path=events_path, evidence_root=evidence_root,
        markers_root=markers_root, now=now,
    )
    result: dict[str, Any] = {**proof, "admission_state": state}
    if not proof.get("verified") or not resolve:
        return result
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
    parser.add_argument("--events-path", type=Path, default=EVENTS_PATH)
    parser.add_argument("--evidence-root", type=Path, default=EVIDENCE_ROOT)
    parser.add_argument("--markers-root", type=Path, default=MARKERS_ROOT)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = reconcile(
            args.occurrence, events_path=args.events_path, evidence_root=args.evidence_root,
            markers_root=args.markers_root, resolve=args.resolve,
        )
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({
            "owner_id": OWNER_ID, "occurrence_id": args.occurrence, "verified": False,
            "error": f"{type(exc).__name__}:{exc}",
        }, sort_keys=True))
        print("FUNDRAISER_FENCE_RECONCILE=FAIL", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, default=str))
    if not result.get("verified"):
        print("FUNDRAISER_FENCE_RECONCILE=HELD")
        return 1
    if not args.resolve:
        print("FUNDRAISER_FENCE_RECONCILE=PROOF_READY")
        return 0
    if not result.get("closed"):
        print("FUNDRAISER_FENCE_RECONCILE=FAIL reason=admission_refused_close", file=sys.stderr)
        return 1
    print("FUNDRAISER_FENCE_RECONCILE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
