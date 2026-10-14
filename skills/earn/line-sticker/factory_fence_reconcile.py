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

  - No hit: local absence is not proof that LINE saw no effect; keep the occurrence fenced until an
    exact official no-effect readback is available.
  - Every hit an item with a product_id that readback has seen on Creators Market: a finished
    submission (review_requested, official status) or one stopped mid-flight that LINE lists as 編集中
    (submit resumes from the recorded item): close as effected, citing those.
  - Any other hit stays fenced: only the item's own status readback can say.

Usage:
    python3 factory_fence_reconcile.py --occurrence line-sticker-factory-hourly:<run_id> [--resolve]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OWNER_ID = "line-sticker-factory-hourly"
STATE_ROOT = Path.home() / ".local/state/life-manager/line-sticker"
MID_SUBMISSION_STATES = frozenset({"metadata_saved", "images_uploaded", "tagged"})
FACTORY_TIME_FIELDS = ("created_at", "review_requested_at")
# Statuses only the readback loop writes, read off the item's own Creators Market page.
OFFICIAL_STATUSES = frozenset({"審査待ち", "審査中", "承認", "販売中", "リジェクト", "販売停止"})
# An item created but not yet sent to review; submit resumes from it (creators-item.json sub-state).
DRAFT_STATUS = "編集中"


def _has_terminal_unknown_event(state_root: Path, occurrence_id: str) -> bool:
    path = state_root / "events.jsonl"
    try:
        size = path.stat().st_size
        offset = max(0, size - 4 * 1024 * 1024)
        with path.open("rb") as handle:
            handle.seek(offset)
            payload = handle.read(4 * 1024 * 1024)
    except OSError:
        return False
    lines = payload.splitlines()
    if offset and lines:
        lines = lines[1:]
    releases = set()
    for line in lines:
        try:
            event = json.loads(line)
        except (UnicodeError, json.JSONDecodeError):
            continue
        if (not isinstance(event, dict)
                or event.get("loop_id") != OWNER_ID
                or event.get("owner_id") != OWNER_ID
                or event.get("occurrence_id") != occurrence_id
                or event.get("phase") != "report"
                or event.get("status") not in {"blocked", "failed"}
                or event.get("effect_status") != "unknown"
                or not isinstance(event.get("effect_class"), str)
                or event.get("effect_class") == "none"):
            continue
        release_sha = event.get("release_sha")
        if isinstance(release_sha, str) and re.fullmatch(r"[a-f0-9]{40}", release_sha):
            releases.add(release_sha)
        else:
            return False
    return len(releases) == 1


def fenced_row(owner_id: str, occurrence_id: str) -> tuple[str, dt.datetime]:
    from runtime.host import resource_admission

    database = resource_admission.state_root() / "admission-v2.sqlite3"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        row = connection.execute(
            """SELECT state, queued_at, effect_unknown FROM occurrences
                 WHERE owner_id=? AND occurrence_id=?""",
            (owner_id, occurrence_id),
        ).fetchone()
    if row is None or row[1] is None:
        raise ValueError("occurrence is not an effect_unknown row")
    if row[2] != 1 and not (
            str(row[0]) == "released" and row[2] == 0
            and _has_terminal_unknown_event(STATE_ROOT, occurrence_id)):
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
    """'<product_id>:<status>' when the run's effect is an item Creators Market itself shows
    (readback's state_observed): a finished submission, or one stopped mid-flight that LINE lists as
    編集中 (submit resumes from the recorded item, so nothing is created twice). None when unread,
    unreadable or without a product_id."""
    try:
        item = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not (isinstance(item, dict) and item.get("product_id")):
        return None
    finished = item.get("state") == "review_requested" and item.get("state_observed") in OFFICIAL_STATUSES
    resumable = item.get("state") in MID_SUBMISSION_STATES and item.get("state_observed") == DRAFT_STATUS
    if finished or resumable:
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
    proof.update(reason="official_line_no_effect_readback_required",
                 elapsed_seconds=max(0, int(age)))
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
