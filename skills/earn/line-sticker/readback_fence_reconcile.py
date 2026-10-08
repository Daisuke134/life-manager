#!/usr/bin/env python3
"""Close one line-sticker-readback-hourly effect_unknown admission fence.

Same shape as factory_fence_reconcile.py. The readback loop only reads Creators Market and the
store (status, sales, features, market sweep) and writes local ledgers; its single external write is
the automatic re-request of a rejected item (``line_sticker_resubmit``), and that stamps
``last_auto_resubmit_at`` into the item's ``creators-item.json`` as it succeeds.

  - No item carries a ``last_auto_resubmit_at`` at or after the occurrence's ``queued_at``, and
    enough time has passed: the run wrote nothing to LINE, close as no-effect.
  - An item stamped after the run started stays fenced: only that item's own status readback can
    say whether the re-request went through.

Usage:
    python3 readback_fence_reconcile.py --occurrence line-sticker-readback-hourly:<run_id> [--resolve]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OWNER_ID = "line-sticker-readback-hourly"
NO_EFFECT_MIN_AGE_SECONDS = 300
STATE_ROOT = Path.home() / ".local/state/life-manager/line-sticker"


def fenced_row(owner_id: str, occurrence_id: str) -> tuple[str, dt.datetime]:
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
    return str(row[0]), dt.datetime.fromtimestamp(float(row[1]), dt.timezone.utc)


def resubmitted_since(state_root: Path, since: dt.datetime) -> list[str]:
    hits = []
    for item_file in sorted(state_root.glob("set-*/creators-item.json")):
        try:
            stamp = json.loads(item_file.read_text()).get("last_auto_resubmit_at")
            when = dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00")) if stamp else None
        except (OSError, ValueError):
            hits.append(f"{item_file.parent.name}:unreadable")  # cannot rule it out
            continue
        if when is not None and when >= since:
            hits.append(item_file.parent.name)
    return hits


def build_proof(occurrence_id: str, queued_at: dt.datetime, *, now: dt.datetime,
                state_root: Path) -> dict[str, Any]:
    proof: dict[str, Any] = {"owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                             "verified": False, "queued_at": queued_at.isoformat()}
    hits = resubmitted_since(state_root, queued_at)
    if hits:
        proof["reason"] = "auto_resubmit_after_run_start:" + ",".join(hits)
        return proof
    age = (now - queued_at).total_seconds()
    if age <= NO_EFFECT_MIN_AGE_SECONDS:
        proof["reason"] = f"too_recent:{int(age)}s<={NO_EFFECT_MIN_AGE_SECONDS}s"
        return proof
    proof.update(verified=True, effected=False,
                 provider_receipt_id=f"line-sticker-no-auto-resubmit-since:{queued_at.isoformat()}",
                 proof_kind="no_item_auto_resubmit_stamp_since_run_start",
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
        print("LINE_STICKER_READBACK_FENCE_RECONCILE=FAIL", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, default=str, ensure_ascii=False))
    if not result.get("verified"):
        print("LINE_STICKER_READBACK_FENCE_RECONCILE=HELD")
        return 1
    if not args.resolve:
        print("LINE_STICKER_READBACK_FENCE_RECONCILE=PROOF_READY")
        return 0
    if not result.get("closed"):
        print("LINE_STICKER_READBACK_FENCE_RECONCILE=FAIL reason=admission_refused_close", file=sys.stderr)
        return 1
    print("LINE_STICKER_READBACK_FENCE_RECONCILE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
