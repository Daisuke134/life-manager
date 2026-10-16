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

  - No hit: local absence is not proof that LINE saw no effect (``_create_item`` saves on LINE
    before the factory writes creators-item.json). The official readback is the account's own
    Creators Market item list (``api/v2/sticker``, every status incl. 編集中), read through the
    same browser identity the submitter uses. The list is complete (as many ids as its
    ``totalEntries``), every item missing from the sets' creators-item.json is older than the
    newest item recorded before the run (item ids only grow), and the run's time cap has passed:
    the run created nothing, close as no-effect citing the list. Any newer unrecorded item, an
    incomplete list or a readback failure stays fenced.
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
import os
import re
import sqlite3
import subprocess
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
# The registry's runtime_timeout_seconds for line-sticker-factory-hourly, plus slack.
NO_EFFECT_MIN_AGE_SECONDS = 5400 + 900
GUARD = REPO_ROOT / "skills/browser/browser-guard.sh"
IDENTITY = "line-creators:dais"  # the submitter's identity (line_sticker_submit.IDENTITY)
CREATOR_BASE = "https://creator.line.me/my/cCX4POFknN2lhLJE"
MAX_LIST_PAGES = 50


def _terminal_events(state_root: Path) -> list[dict]:
    path = state_root / "events.jsonl"
    try:
        size = path.stat().st_size
        offset = max(0, size - 4 * 1024 * 1024)
        with path.open("rb") as handle:
            handle.seek(offset)
            payload = handle.read(4 * 1024 * 1024)
    except OSError:
        return []
    lines = payload.splitlines()
    if offset and lines:
        lines = lines[1:]
    events = []
    for line in lines:
        try:
            event = json.loads(line)
        except (UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(event, dict) and event.get("phase") == "report":
            events.append(event)
    return events


def _terminal_unknown_release_sha(state_root: Path, occurrence_id: str,
                                  owner_id: str = OWNER_ID) -> str | None:
    releases = set()
    for event in _terminal_events(state_root):
        if (event.get("loop_id") != owner_id
                or event.get("owner_id") != owner_id
                or event.get("occurrence_id") != occurrence_id
                or event.get("phase") != "report"
                or event.get("status") not in {"blocked", "fail"}
                or event.get("effect_status") != "unknown"
                or not isinstance(event.get("effect_class"), str)
                or event.get("effect_class") == "none"):
            continue
        release_sha = event.get("release_sha")
        if isinstance(release_sha, str) and re.fullmatch(r"[a-f0-9]{40}", release_sha):
            releases.add(release_sha)
        else:
            return None
    return next(iter(releases)) if len(releases) == 1 else None


def run_ended_at(state_root: Path, occurrence_id: str) -> dt.datetime | None:
    """The run's exact terminal report time. lm_loop_run writes it only after the entrypoint's whole
    process group has exited, so nothing this run did can carry a later factory timestamp."""
    stamps = {event.get("timestamp") for event in _terminal_events(state_root)
              if event.get("owner_id") == OWNER_ID and event.get("occurrence_id") == occurrence_id}
    if len(stamps) != 1:
        return None
    try:
        ended = dt.datetime.fromisoformat(str(next(iter(stamps))).replace("Z", "+00:00"))
    except ValueError:
        return None
    return ended if ended.tzinfo is not None else None


def fenced_row(owner_id: str, occurrence_id: str) -> tuple[str, dt.datetime, bool]:
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
    lost = str(row[0]) == "released" and row[2] == 0
    if row[2] != 1 and not (lost and _terminal_unknown_release_sha(STATE_ROOT, occurrence_id)):
        raise ValueError("occurrence is not an effect_unknown row")
    return str(row[0]), dt.datetime.fromtimestamp(float(row[1]), dt.timezone.utc), lost


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


def touched_since(state_root: Path, since: dt.datetime, until: dt.datetime | None = None) -> list[str]:
    """Sets the run may have touched. ``until`` (the run's terminal report) excludes items later
    runs created: without it every newer set counted against every older fence."""
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
        if until is None:
            touched = any(_at_or_after(item.get(field), since) for field in FACTORY_TIME_FIELDS)
        else:
            # Upload/tag leave no timestamp and one item spans several runs, so any item alive during
            # the run (created by its end, review not requested before its start) may be its effect.
            created, requested = item.get("created_at"), item.get("review_requested_at")
            touched = (isinstance(created, str) and bool(created)
                       and not _at_or_after(created, until + dt.timedelta(microseconds=1))
                       and (not requested or _at_or_after(requested, since)))
        if item.get("state") in MID_SUBMISSION_STATES or touched:
            hits.append(label)
    return hits


def confirmed_submission(path: Path, *, expected_binding: tuple[str, str, str] | None = None) -> str | None:
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
    if expected_binding is not None and tuple(
            item.get(key) for key in ("owner_id", "occurrence_id", "release_sha")) != expected_binding:
        return None
    finished = item.get("state") == "review_requested" and item.get("state_observed") in OFFICIAL_STATUSES
    resumable = item.get("state") in MID_SUBMISSION_STATES and item.get("state_observed") == DRAFT_STATUS
    if finished or resumable:
        return f"{item['product_id']}:{item['state_observed']}"
    return None


def collect_listing(get_page) -> dict[str, Any]:
    """Every page of the official item list -> {"ok", "ids", "total"}; any malformed page fails."""
    ids: list[str] = []
    total = None
    try:
        page_number, max_page = 1, 1
        while page_number <= max_page:
            payload = get_page(page_number)
            pager = payload["pager"]
            max_page, total = int(pager["maxPage"]), int(pager["totalEntries"])
            if max_page > MAX_LIST_PAGES:
                return {"ok": False, "reason": "creators_listing_too_many_pages"}
            ids.extend(str(int(item["id"])) for item in payload["items"])
            page_number += 1
    except (KeyError, TypeError, ValueError):
        return {"ok": False, "reason": "creators_listing_malformed"}
    return {"ok": True, "ids": ids, "total": total}


def read_creators_items() -> dict[str, Any]:
    # The guard matches the lease to this pid on release; without it release is an unconditional rm.
    env = {**os.environ, "AI_BROWSER_HOLDER_PID": str(os.getpid())}
    acquired = subprocess.run(["bash", str(GUARD), "acquire", IDENTITY], capture_output=True, text=True, env=env)
    if acquired.returncode != 0:
        return {"ok": False, "reason": "browser_unavailable"}
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(acquired.stdout.strip().splitlines()[-1])
            request = browser.contexts[0].request

            def get_page(number: int) -> Any:
                response = request.get(f"{CREATOR_BASE}/api/v2/sticker?page={number}", timeout=60000,
                                       max_redirects=0)
                if response.status != 200:
                    raise ValueError(f"status_{response.status}")
                return response.json()

            return collect_listing(get_page)
    except Exception as exc:  # noqa: BLE001 -- any failure is inconclusive
        return {"ok": False, "reason": f"creators_readback_failed:{type(exc).__name__}"}
    finally:
        subprocess.run(["bash", str(GUARD), "release", IDENTITY], capture_output=True, env=env)


def _recorded_items(state_root: Path) -> list[dict[str, Any]]:
    items = []
    for path in sorted(state_root.glob("set-*/creators-item.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # an unreadable item is already a touched_since hit
        if isinstance(item, dict) and str(item.get("product_id") or "").isdigit():
            items.append(item)
    return items


def no_effect_proof(proof: dict[str, Any], queued_at: dt.datetime, *, now: dt.datetime,
                    state_root: Path, creators: dict[str, Any]) -> dict[str, Any]:
    if not creators.get("ok"):
        proof["reason"] = creators.get("reason")
        return proof
    ids = creators["ids"]
    if len(set(ids)) != len(ids) or len(ids) < creators["total"]:
        proof["reason"] = f"incomplete_creators_listing:{len(set(ids))}<{creators['total']}"
        return proof
    recorded = _recorded_items(state_root)
    known = {str(item["product_id"]) for item in recorded}
    before_run = [int(item["product_id"]) for item in recorded
                  if isinstance(item.get("created_at"), str) and not _at_or_after(item["created_at"], queued_at)]
    baseline = max(before_run, default=None)
    unrecorded = sorted(i for i in ids if i not in known and (baseline is None or int(i) > baseline))
    if unrecorded:  # may be the item this run created before it could record it
        proof["reason"] = "unrecorded_creators_item:" + ",".join(unrecorded)
        return proof
    age = (now - queued_at).total_seconds()
    if age <= NO_EFFECT_MIN_AGE_SECONDS:
        proof["reason"] = f"too_recent:{int(age)}s<={NO_EFFECT_MIN_AGE_SECONDS}s"
        return proof
    proof.update(verified=True, effected=False,
                 provider_receipt_id=(f"creators-market-item-list:{len(ids)}:{max(map(int, ids), default=0)}:"
                                      f"{now.isoformat(timespec='seconds')}"),
                 proof_kind="official_creators_item_list_vs_recorded_items",
                 checked_at=now.isoformat(timespec="seconds"))
    return proof


def build_proof(occurrence_id: str, queued_at: dt.datetime, *, now: dt.datetime,
                state_root: Path, expected_binding: tuple[str, str, str] | None = None,
                creators: dict[str, Any] | None = None, until: dt.datetime | None = None) -> dict[str, Any]:
    proof: dict[str, Any] = {"owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                             "verified": False, "queued_at": queued_at.isoformat()}
    hits = touched_since(state_root, queued_at, until)
    if hits:
        confirmed = [confirmed_submission(state_root / label, expected_binding=expected_binding)
                     for label in hits]
        if all(confirmed):  # the effect happened, finished, and LINE shows it: close as effected
            proof.update(verified=True, effected=True,
                         provider_receipt_id="creators-market-readback:" + ",".join(confirmed),
                         proof_kind="factory_submission_confirmed_by_creators_readback",
                         checked_at=now.isoformat(timespec="seconds"))
            return proof
        reason = ("exact_occurrence_receipt_binding_required" if expected_binding is not None
                  else "state_touched_after_run_start")
        proof["reason"] = reason + ":" + ",".join(hits)
        return proof
    if creators is not None:
        return no_effect_proof(proof, queued_at, now=now, state_root=state_root, creators=creators)
    age = (now - queued_at).total_seconds()
    proof.update(reason="official_line_no_effect_readback_required",
                 elapsed_seconds=max(0, int(age)))
    return proof


def reconcile(occurrence_id: str, *, resolve: bool = False) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    state, queued_at, lost = fenced_row(OWNER_ID, occurrence_id)
    binding = None
    if lost:
        release_sha = _terminal_unknown_release_sha(STATE_ROOT, occurrence_id)
        if release_sha is None:
            raise ValueError("exact terminal unknown release is unavailable")
        binding = (OWNER_ID, occurrence_id, release_sha)
    until = run_ended_at(STATE_ROOT, occurrence_id)
    creators = None if touched_since(STATE_ROOT, queued_at, until) else read_creators_items()
    proof = build_proof(occurrence_id, queued_at, now=now, state_root=STATE_ROOT,
                        expected_binding=binding, creators=creators, until=until)
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
