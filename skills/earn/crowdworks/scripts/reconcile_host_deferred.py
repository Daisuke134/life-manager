#!/usr/bin/env python3
"""Reconcile a CrowdWorks fence only from an exact pre-child host-deferred event."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from runtime.host.resource_admission import resolve_pre_effect_occurrence


OWNERS = frozenset({
    "crowdworks-revenue-application",
    "crowdworks-revenue-reply",
    "crowdworks-revenue-paid",
})
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
# These are emitted before `_run_entrypoint` can start.  In particular,
# `resource_admission_interrupted` is deliberately excluded: the runtime can
# write that receipt after a child has already started and was interrupted.
PRE_CHILD_REASONS = frozenset({
    "resource_capacity_busy",
    "resource_fifo_wait",
    # Durable admission returns this before creating a claim when the owner
    # already has an unresolved effect.  A claim/effect reference below still
    # wins and keeps the occurrence fenced.
    "resource_effect_unknown",
})


def _events(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        handle = path.open(encoding="utf-8")
    except OSError:
        return rows
    with handle:
        for line in handle:
            try:
                value = json.loads(line)
            except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def find_host_deferred_proof(events_path: Path, owner: str,
                             occurrence: str) -> dict[str, Any] | None:
    """Return proof only for one exact run that never reached a child."""
    if owner not in OWNERS or not SAFE_ID.fullmatch(occurrence):
        return None
    prefix = f"{owner}:"
    if not occurrence.startswith(prefix):
        return None
    run_id = occurrence[len(prefix):]
    rows = [row for row in _events(events_path)
            if row.get("loop_id") == owner and row.get("run_id") == run_id]
    starts = [row for row in rows
              if row.get("phase") == "execute"
              and row.get("status") == "running"
              and row.get("effect_status") == "started"]
    terminals = [row for row in rows
                 if row.get("phase") == "report" and row.get("status") == "blocked"]
    if len(starts) != 1 or len(terminals) != 1:
        return None
    terminal = terminals[0]
    blocker = terminal.get("blocker")
    reason = blocker.split(":", 1)[1] if isinstance(blocker, str) and ":" in blocker else ""
    if (terminal.get("effect_status") != "unknown"
            or not isinstance(blocker, str)
            or not blocker.startswith("host_admission_deferred:")
            or reason not in PRE_CHILD_REASONS
            or any(isinstance(ref, str)
                   and ref.startswith(("lm-effect://", "lm-occurrence://"))
                   for row in rows for ref in row.get("evidence_refs", []))):
        return None
    summary_ref = f"lm-loop://{owner}/{run_id}/summary.json"
    if summary_ref not in terminal.get("evidence_refs", []):
        return None
    return {
        "owner_id": owner,
        "occurrence_id": occurrence,
        "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": f"lm-event://{owner}/{run_id}/{terminal['event_id']}",
        "blocker": blocker,
    }


def reconcile(*, state_root: Path, owner: str, occurrence: str,
              resolve: bool = False) -> dict[str, Any]:
    events_path = state_root / "events.jsonl"
    proof = find_host_deferred_proof(events_path, owner, occurrence)
    if proof is None:
        raise RuntimeError("exact_host_deferred_proof_unavailable")
    resolved = False
    if resolve:
        resolved = resolve_pre_effect_occurrence(
            owner, occurrence, pre_effect_readback=lambda: proof,
            expected_state="claimed",
        )
    return {**proof, "resolved": resolved}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--owner", required=True, choices=sorted(OWNERS))
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true",
                        help="release the exact claimed occurrence after proof")
    args = parser.parse_args(argv)
    result = reconcile(state_root=args.state_root.expanduser().resolve(),
                       owner=args.owner, occurrence=args.occurrence,
                       resolve=args.resolve)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not args.resolve or result["resolved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
