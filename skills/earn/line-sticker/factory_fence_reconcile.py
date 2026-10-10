#!/usr/bin/env python3
"""Close one line-sticker-factory-hourly effect_unknown admission fence.

Same decision shape as distribute_fence_reconcile.py / capafy_ig_fence_reconcile.py: one proof per
occurrence, never a guess. The factory's only external effect is writing to LINE Creators Market (create the item, upload
images, set tags, request review). ``factory._submit`` records those steps in the set's own
``creators-item.json``, so the proof reads the fields only the factory writes, never file mtimes
(the readback loop rewrites every set's creators-item.json, which would hold the fence forever):

  - ``created_at`` / ``review_requested_at`` at or after the occurrence's ``queued_at`` (ISO8601,
    ``Z`` or naive = UTC): the run created the item or requested review.
  - ``state`` in metadata_saved / images_uploaded / tagged: submission is mid-flight; uploads and
    tagging leave no timestamp, only the state moves, so the run may have touched LINE.
  - An unreadable creators-item.json cannot be excluded and counts as a hit.
  - ``state_observed`` / ``purchase_url`` / ``store_public`` / ``last_auto_resubmit_at`` are written
    by readback and are never evidence.

  - No hit and enough time has passed: close as no-effect.
  - Every hit a finished submission (state review_requested, a product_id) that readback has seen on
    Creators Market (state_observed is an official status): close as effected, citing those.
  - Any other hit stays fenced: only the item's own status readback can say.

Usage:
    python3 factory_fence_reconcile.py --occurrence line-sticker-factory-hourly:<run_id> [--resolve]
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

OWNER_ID = "line-sticker-factory-hourly"
# A wake can run for up to the loop's runtime (5400 s); the file check is local and exact, so only
# a short settle time is needed for a late writer to finish.
MAX_RUN_SECONDS = 5400
NO_EFFECT_MIN_AGE_SECONDS = 300
STATE_ROOT = Path.home() / ".local/state/life-manager/line-sticker"
MID_SUBMISSION_STATES = frozenset({"metadata_saved", "images_uploaded", "tagged"})
FACTORY_TIME_FIELDS = ("created_at", "review_requested_at")
# Statuses only the readback loop writes, read off the item's own Creators Market page.
OFFICIAL_STATUSES = frozenset({"審査待ち", "審査中", "承認", "販売中", "リジェクト", "販売停止"})


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


def _at_or_after(value: Any, since: dt.datetime) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return True  # an unparseable factory timestamp cannot be excluded
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return stamp >= since


def touched_since(state_root: Path, since: dt.datetime) -> list[str]:
    hits = []
    for set_dir in sorted(state_root.glob("set-*")):
        path = set_dir / "creators-item.json"
        if not path.exists():
            continue
        label = f"{set_dir.name}/{path.name}"
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(item, dict):
                raise ValueError("item is not an object")
        except (OSError, ValueError):
            hits.append(label)
            continue
        if item.get("state") in MID_SUBMISSION_STATES or any(
                _at_or_after(item.get(field), since) for field in FACTORY_TIME_FIELDS):
            hits.append(label)
    return hits


def confirmed_submission(path: Path) -> str | None:
    """'<product_id>:<status>' when the run's effect is a finished submission that Creators Market
    itself shows (readback's state_observed); None when it is mid-flight, unread or unreadable."""
    try:
        item = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (isinstance(item, dict) and item.get("state") == "review_requested" and item.get("product_id")
            and item.get("state_observed") in OFFICIAL_STATUSES):
        return f"{item['product_id']}:{item['state_observed']}"
    return None


def build_proof(occurrence_id: str, queued_at: dt.datetime, *, now: dt.datetime,
                state_root: Path) -> dict[str, Any]:
    proof: dict[str, Any] = {"owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                             "verified": False, "queued_at": queued_at.isoformat()}
    hits = touched_since(state_root, queued_at)
    if hits:
        confirmed = [confirmed_submission(state_root / label) for label in hits]
        if all(confirmed):  # the effect happened, finished, and LINE shows it: close as effected
            proof.update(verified=True, effected=True,
                         provider_receipt_id="creators-market-readback:" + ",".join(confirmed),
                         proof_kind="factory_submission_confirmed_by_creators_readback",
                         checked_at=now.isoformat(timespec="seconds"))
            return proof
        proof["reason"] = "state_touched_after_run_start:" + ",".join(hits)
        return proof
    age = (now - queued_at).total_seconds()
    if age <= NO_EFFECT_MIN_AGE_SECONDS:
        proof["reason"] = f"too_recent:{int(age)}s<={NO_EFFECT_MIN_AGE_SECONDS}s"
        return proof
    proof.update(verified=True, effected=False,
                 provider_receipt_id=f"line-sticker-state-untouched-since:{queued_at.isoformat()}",
                 proof_kind="factory_state_files_unmodified_since_run_start",
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
        print("LINE_STICKER_FACTORY_FENCE_RECONCILE=FAIL", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, default=str, ensure_ascii=False))
    if not result.get("verified"):
        print("LINE_STICKER_FACTORY_FENCE_RECONCILE=HELD")
        return 1
    if not args.resolve:
        print("LINE_STICKER_FACTORY_FENCE_RECONCILE=PROOF_READY")
        return 0
    if not result.get("closed"):
        print("LINE_STICKER_FACTORY_FENCE_RECONCILE=FAIL reason=admission_refused_close", file=sys.stderr)
        return 1
    print("LINE_STICKER_FACTORY_FENCE_RECONCILE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
