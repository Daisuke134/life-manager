#!/usr/bin/env python3
"""Reconcile one legacy Paid inventory failure from an exact time-bound proof."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from runtime.host.resource_admission import resolve_pre_effect_occurrence


OWNER = "crowdworks-revenue-paid"


def _read_events(path: Path) -> list[dict[str, Any]]:
    rows = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            value = json.loads(line)
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _time(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def find_legacy_proof(events_path: Path, latest_path: Path, owner: str,
                      occurrence: str) -> dict[str, Any] | None:
    if owner != OWNER or not occurrence.startswith(f"{OWNER}:"):
        return None
    suffix = occurrence[len(OWNER) + 1:]
    rows = _read_events(events_path)
    terminal = None
    for row in rows:
        if row.get("loop_id") != owner:
            continue
        refs = row.get("evidence_refs")
        if not isinstance(refs, list):
            continue
        if (row.get("phase") == "report" and row.get("status") == "fail"
                and row.get("blocker") == "entrypoint_exit_1"
                and f"lm-occurrence://{owner}/{suffix}/claim" in refs):
            terminal = row
    if terminal is None:
        return None
    start = next((row for row in rows
                  if row.get("loop_id") == owner
                  and row.get("run_id") == terminal.get("run_id")
                  and row.get("phase") == "execute"
                  and row.get("status") == "running"), None)
    if start is None:
        return None
    start_at = _time(start.get("timestamp"))
    terminal_at = _time(terminal.get("timestamp"))
    if start_at is None or terminal_at is None:
        return None
    try:
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        modified = latest_path.stat().st_mtime
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(latest, Mapping):
        return None
    if not (start_at <= modified <= terminal_at):
        return None
    if (latest.get("status") != "failed"
            or latest.get("failed_step") != "provider_inventory"
            or latest.get("effect") != 0
            or latest.get("observed") != 0
            or latest.get("readback") != 0
            or latest.get("items") != []):
        return None
    return {
        "owner_id": owner,
        "occurrence_id": occurrence,
        "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": f"lm-event://{owner}/{terminal['run_id']}/{terminal['event_id']}",
        "provider_result_ref": "crowdworks://paid-latest/provider-inventory-failed",
    }


def reconcile(*, events_path: Path, latest_path: Path, owner: str,
              occurrence: str, resolve: bool = False) -> dict[str, Any]:
    proof = find_legacy_proof(events_path, latest_path, owner, occurrence)
    if proof is None:
        raise RuntimeError("exact_legacy_paid_inventory_proof_unavailable")
    resolved = False
    if resolve:
        resolved = resolve_pre_effect_occurrence(
            owner, occurrence, pre_effect_readback=lambda: proof,
            expected_state="claimed",
        )
    return {**proof, "resolved": resolved}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--latest", required=True, type=Path)
    parser.add_argument("--owner", default=OWNER, choices=(OWNER,))
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    result = reconcile(events_path=args.events.expanduser().resolve(),
                       latest_path=args.latest.expanduser().resolve(),
                       owner=args.owner, occurrence=args.occurrence,
                       resolve=args.resolve)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not args.resolve or result["resolved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
