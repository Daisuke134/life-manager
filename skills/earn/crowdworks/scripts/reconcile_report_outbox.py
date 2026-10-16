#!/usr/bin/env python3
"""Close one crowdworks-revenue-report effect_unknown fence from its Telegram outbox receipt.

The report owner's only effect is ``delivery.deliver_pending`` on
``telegram-outbox.sqlite3`` (telegram_report.py).  ``claim_next`` stamps
``claimed_at`` right before each send and ``mark_delivered`` stores the
``message_id`` Telegram returned, so the outbox is the provider receipt store
(same contract as skills/cfo/effect_reconcile.py).

Proof, all required:
* the admission occurrence is still ``effect_unknown=1``;
* the journal holds the claim run's execute start and report terminal;
* the occurrence's own wake message (event key ``crowdworks:wake:<occurrence>:``,
  written by ``enqueue_wake_summary``) is ``delivered`` with a provider id and
  was claimed inside that run;
* every other row claimed inside the run is also ``delivered`` with an id, so
  no send of this occurrence remains uncertain.

Anything else keeps the fence.  Nothing is sent or retried.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime
import gzip
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from runtime.host.resource_admission import (  # noqa: E402
    resolve_unknown_occurrence, state_root as admission_state_root)

OWNER = "crowdworks-revenue-report"
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
SLACK = 60  # host clock skew between journal and outbox stamps


def _epoch(value: Any) -> float | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.timestamp() if parsed.tzinfo is not None else None


def _events(state_root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in [state_root / "events.jsonl", *sorted(state_root.glob("events-*.jsonl.gz"))]:
        try:
            with (gzip.open if path.suffix == ".gz" else open)(path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        value = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(value, dict) and value.get("loop_id") == OWNER:
                        rows.append(value)
        except OSError:
            continue
    return rows


def _occurrence_state(database: Path, occurrence: str) -> str:
    with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=0.5)) as db:
        row = db.execute("SELECT owner_id,state,effect_unknown FROM occurrences WHERE occurrence_id=?",
                         (occurrence,)).fetchone()
    if not row or row[0] != OWNER or row[1] not in {"claimed", "released"} or row[2] != 1:
        raise RuntimeError("occurrence_not_effect_unknown")
    return row[1]


def _run_window(rows: list[dict[str, Any]], occurrence: str) -> tuple[float, float, str]:
    suffix = occurrence[len(OWNER) + 1:]
    claim_ref = f"lm-occurrence://{OWNER}/{suffix}/claim"
    claim_runs = {r.get("run_id") for r in rows if claim_ref in (r.get("evidence_refs") or [])}
    if len(claim_runs) > 1:
        raise RuntimeError("claimed_by_multiple_runs")
    run = claim_runs.pop() if claim_runs else suffix
    run_rows = [r for r in rows if r.get("run_id") == run]
    if any(r.get("occurrence_id") not in (None, occurrence) for r in run_rows):
        raise RuntimeError("claim_occurrence_mismatch")
    starts = [_epoch(r.get("timestamp")) for r in run_rows
              if r.get("phase") == "execute" and r.get("status") == "running"]
    ends = [r for r in run_rows if r.get("phase") == "report"]
    if len(starts) != 1 or len(ends) != 1 or starts[0] is None or _epoch(ends[0].get("timestamp")) is None:
        raise RuntimeError("claim_run_unavailable")
    return starts[0], _epoch(ends[0]["timestamp"]), str(ends[0].get("release_sha") or "")


def find_proof(state_root: Path, occurrence: str, admission_db: Path) -> dict[str, Any]:
    if not SAFE_ID.fullmatch(occurrence) or not occurrence.startswith(f"{OWNER}:"):
        raise RuntimeError("invalid_occurrence")
    state = _occurrence_state(admission_db, occurrence)
    start, end, release = _run_window(_events(state_root), occurrence)
    with closing(sqlite3.connect(f"file:{state_root / 'telegram-outbox.sqlite3'}?mode=ro",
                                 uri=True, timeout=0.5)) as db:
        outbox = db.execute("SELECT event_key,status,provider_message_id,claimed_at "
                            "FROM telegram_outbox WHERE claimed_at IS NOT NULL").fetchall()
    in_run = [row for row in outbox
              if (stamp := _epoch(row[3])) is not None and start - SLACK <= stamp <= end + SLACK]
    if any(status != "delivered" or not provider_id for _, status, provider_id, _ in in_run):
        raise RuntimeError("outbox_window_not_settled")
    bound = [row for row in in_run if row[0].startswith(f"crowdworks:wake:{occurrence}:")]
    if len(bound) != 1:
        raise RuntimeError("bound_receipt_unavailable")
    event_key, _, provider_id, claimed_at = bound[0]
    return {"owner_id": OWNER, "occurrence_id": occurrence, "verified": True,
            "proof_type": "telegram_outbox_delivered_receipt",
            "provider_receipt_id": f"telegram:{provider_id}",
            "evidence_ref": f"telegram-outbox://{OWNER}/{event_key}",
            "claimed_at": claimed_at, "window": [start, end], "release_sha": release or None,
            "window_receipts": sorted(str(row[2]) for row in in_run),
            "occurrence_state": state}


def reconcile(*, state_root: Path, occurrence: str, admission_db: Path, resolve: bool = False,
              resolver: Callable[..., bool] = resolve_unknown_occurrence) -> dict[str, Any]:
    proof = find_proof(state_root, occurrence, admission_db)
    resolved = bool(resolve and resolver(OWNER, occurrence, official_readback=lambda: proof,
                                         expected_state=proof["occurrence_state"]))
    return {**proof, "resolved": resolved}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--admission-db", type=Path, default=None)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    state_root = args.state_root.expanduser().resolve()
    database = (args.admission_db or admission_state_root() / "admission-v2.sqlite3").expanduser()
    try:
        result = reconcile(state_root=state_root, occurrence=args.occurrence,
                           admission_db=database, resolve=args.resolve)
    except (RuntimeError, OSError, sqlite3.Error) as error:
        print(json.dumps({"owner_id": OWNER, "occurrence_id": args.occurrence, "verified": False,
                          "effect_status": "unknown", "error_class": str(error) or type(error).__name__,
                          "next_action": "obtain_occurrence_bound_readback", "resolved": False},
                         sort_keys=True))
        return 75
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not args.resolve or result["resolved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
