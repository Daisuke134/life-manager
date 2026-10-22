#!/usr/bin/env python3
"""Close one warmup-flip-daily effect_unknown admission fence.

warmup_flip.py has two effects, both journaled: it rewrites postiz-integrations.json through
warmup-flip-transaction.json, and it delivers the graduation notice through pending-telegram.txt,
removed only after the sender succeeds. When the run leaves neither file behind and the state file
parses, every effect the run started is either complete or was never begun, and the state file
(the effect's own store) is the readback. A leftover journal or pending notice stays fenced: the
next run recovers it, and only then can the fence close.

Usage: warmup_fence_reconcile.py --occurrence warmup-flip-daily:<run_id> [--resolve]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OWNER_ID = "warmup-flip-daily"
MIN_AGE_SECONDS = 300
STATE_ROOT = Path.home() / ".local/state/life-manager/warmup-flip-daily"


def fenced_row(owner_id: str, occurrence_id: str) -> tuple[str, dt.datetime]:
    from runtime.host import resource_admission

    database = resource_admission.state_root() / "admission-v2.sqlite3"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        row = connection.execute(
            "SELECT state, queued_at FROM occurrences WHERE owner_id=? AND occurrence_id=? AND effect_unknown=1",
            (owner_id, occurrence_id),
        ).fetchone()
    if row is None or row[1] is None:
        raise ValueError("occurrence is not an effect_unknown row")
    return str(row[0]), dt.datetime.fromtimestamp(float(row[1]), dt.timezone.utc)


def build_proof(occurrence_id: str, queued_at: dt.datetime, *, now: dt.datetime,
                state_root: Path) -> dict[str, Any]:
    proof: dict[str, Any] = {"owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                             "verified": False, "queued_at": queued_at.isoformat()}
    age = (now - queued_at).total_seconds()
    if age <= MIN_AGE_SECONDS:
        proof["reason"] = f"too_recent:{int(age)}s<={MIN_AGE_SECONDS}s"
        return proof
    for leftover in ("warmup-flip-transaction.json", "pending-telegram.txt"):
        if (state_root / leftover).exists():
            proof["reason"] = f"unrecovered:{leftover}"
            return proof
    state_file = state_root / "state" / "postiz-integrations.json"
    try:
        body = state_file.read_bytes()
        json.loads(body)
    except (OSError, ValueError) as exc:
        proof["reason"] = f"state_unreadable:{type(exc).__name__}"
        return proof
    proof.update(verified=True, proof_type="state_readback",
                 provider_receipt_id=f"warmup-flip-state:{hashlib.sha256(body).hexdigest()}",
                 proof_kind="journal_and_pending_absent_state_parses",
                 checked_at=now.isoformat(timespec="seconds"))
    return proof


def reconcile(occurrence_id: str, *, resolve: bool = False) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    state, queued_at = fenced_row(OWNER_ID, occurrence_id)
    proof = build_proof(occurrence_id, queued_at, now=now, state_root=STATE_ROOT)
    result = {**proof, "admission_state": state}
    if not proof.get("verified") or not resolve:
        return result
    from runtime.host.resource_admission import resolve_unknown_occurrence

    result["closed"] = resolve_unknown_occurrence(OWNER_ID, occurrence_id,
                                                  official_readback=lambda: proof, expected_state=state)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = reconcile(args.occurrence, resolve=args.resolve)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"owner_id": OWNER_ID, "occurrence_id": args.occurrence,
                          "verified": False, "error": f"{type(exc).__name__}:{exc}"}))
        print("WARMUP_FLIP_FENCE_RECONCILE=FAIL", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, default=str, ensure_ascii=False))
    if not result.get("verified"):
        print("WARMUP_FLIP_FENCE_RECONCILE=HELD")
        return 1
    if not args.resolve:
        print("WARMUP_FLIP_FENCE_RECONCILE=PROOF_READY")
        return 0
    if not result.get("closed"):
        print("WARMUP_FLIP_FENCE_RECONCILE=FAIL reason=admission_refused_close", file=sys.stderr)
        return 1
    print("WARMUP_FLIP_FENCE_RECONCILE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
