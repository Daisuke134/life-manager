#!/usr/bin/env python3
"""Close Application fences only when official CrowdWorks readback shows no proposal.

An Application run's only provider effect is submitting a proposal. The run
that claimed the occurrence (``lm-occurrence://<owner>/<run>/claim``) bounds
the window. CrowdWorks' proposal list plus every receipted proposal id cover
the proposals we sent (the pending marker is written before the submit click,
so an unreceipted submission stays pending); each proposal page opens
with our proposal message, whose minute is the submission time. Proposal ids
are issued in time order, so reading newest first until one predates the window
covers it. A proposal minute in the window, a receipt bound to the occurrence,
a pending transaction, or an incomplete/unordered readback keeps the fence.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from runtime.host.resource_admission import resolve_pre_effect_occurrence
from reconcile_reply_no_send import (ADMISSION_DB, JST, MINUTE, SAFE_ID, SLACK, _json,
                                     _events, _overlaps, _provider_lease, _window)

OWNER = "crowdworks-revenue-application"
SENDER = "Kaito｜AI自動化"


def _minute(value: str) -> float | None:
    match = MINUTE.fullmatch(value or "")
    return datetime(*map(int, match.groups()), tzinfo=JST).timestamp() if match else None


def evaluate(state_root: Path, occurrences: list[str],
             proposals: list[tuple[int, str]] | None
             ) -> dict[str, tuple[dict[str, Any] | None, str]]:
    rows = _events(state_root, OWNER)
    receipts = [json.loads(line) for line in
                (state_root / "application-receipts.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()]
    pending = (_json(state_root / "application-transaction.json") or {}).get("pending")
    timeline = None if proposals is None else [(pid, _minute(m)) for pid, m in
                                               sorted(proposals, reverse=True)]
    ordered = timeline is not None and all(
        a[1] is not None and b[1] is not None and a[1] >= b[1]
        for a, b in zip(timeline, timeline[1:])) and all(t is not None for _, t in timeline)
    result = {}
    for occurrence in occurrences:
        result[occurrence] = _prove(occurrence, rows, receipts, pending, timeline, ordered)
    return result


def _prove(occurrence, rows, receipts, pending, timeline, ordered):
    if not SAFE_ID.fullmatch(occurrence) or not occurrence.startswith(f"{OWNER}:"):
        return None, "invalid_occurrence"
    run_id = occurrence[len(OWNER) + 1:]
    window, reason = _window(rows, run_id, None, owner=OWNER)
    if window is None:
        return None, reason
    if any(r.get("occurrence_id") == occurrence for r in receipts):
        return None, "application_receipt_bound"
    if pending:
        return None, "application_transaction_pending"
    if timeline is None:
        return None, "proposal_readback_incomplete"
    if not ordered:
        return None, "proposal_order_unverified"
    if not timeline or timeline[-1][1] + 60 >= window[0] - SLACK:
        return None, "proposal_readback_incomplete"
    for pid, minute in timeline:
        if _overlaps(minute, window):
            return None, f"proposal_in_window:{pid}"
    before = next(pid for pid, minute in timeline if minute + 60 < window[0] - SLACK)
    digest = hashlib.sha256(json.dumps({"window": window, "latest_before": before},
                                       sort_keys=True).encode()).hexdigest()[:16]
    return {
        "owner_id": OWNER, "occurrence_id": occurrence, "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": f"lm-crowdworks-application-readback://{OWNER}/{run_id}/{digest}",
        "window": list(window), "latest_proposal_before_window": before,
    }, "ok"


def recorded_proposals(state_root: Path) -> set[int]:
    """Proposal ids our own receipts recorded; the provider list can drop some."""
    ids = set()
    for line in (state_root / "application-receipts.jsonl").read_text(encoding="utf-8").splitlines():
        value = json.loads(line) if line.strip() else {}
        if str(value.get("application_external_id", "")).isdigit():
            ids.add(int(value["application_external_id"]))
    return ids


def read_proposals(page: Any, oldest_needed: float,
                   recorded: set[int] = frozenset()) -> list[tuple[int, str]] | None:
    """Newest-first proposals with their first-message minute, or None if unreadable.

    CrowdWorks' list omits some proposals (5 of 224 receipted ones were absent on
    2026-09-26), so every receipted id is read as well. A submission that never
    got a receipt still holds application-transaction pending, which _prove checks.
    """
    ids: set[int] = set(recorded)
    for number in range(1, 51):
        page.goto(f"https://crowdworks.jp/e/proposals?page={number}",
                  wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(1500)
        hrefs = page.eval_on_selector_all("a[href]", "as => as.map(a => a.href)")
        found = {int(m) for m in re.findall(r"/proposals/(\d+)$", "\n".join(hrefs), re.M)}
        if not found:
            break
        ids |= found
    else:
        return None
    result = []
    for pid in sorted(ids, reverse=True):
        page.goto(f"https://crowdworks.jp/proposals/{pid}", wait_until="domcontentloaded",
                  timeout=30_000)
        page.wait_for_timeout(1200)
        first = page.locator('div[class*="_messageItem_"]').first
        sender = first.locator('a[class*="_senderName_"]').first.text_content() or ""
        minute = first.locator("time").first.get_attribute("datetime") or ""
        if sender.strip() != SENDER or _minute(minute) is None:
            return None
        result.append((pid, minute))
        if _minute(minute) < oldest_needed:
            break
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--admission-db", type=Path, default=ADMISSION_DB)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    state_root = args.state_root.expanduser().resolve()
    with sqlite3.connect(f"file:{args.admission_db.expanduser()}?mode=ro", uri=True) as db:
        occurrences = [r[0] for r in db.execute(
            "SELECT occurrence_id FROM occurrences WHERE owner_id=? AND state='claimed' "
            "AND effect_unknown=1 ORDER BY queued_at", (OWNER,))]
    rows = _events(state_root, OWNER)
    starts = [w[0] for o in occurrences
              if (w := _window(rows, o[len(OWNER) + 1:], None, owner=OWNER)[0])]
    proposals = None
    if starts:
        with _provider_lease(state_root):
            import reply_adapter
            adapter, _ = reply_adapter.build(["--state-path", str(state_root / "reply/state.json")])
            try:
                adapter._open()
                proposals = read_proposals(adapter.page, min(starts) - 3600,
                                           recorded_proposals(state_root))
            except Exception:
                proposals = None
            finally:
                adapter.close()
    report = {"owner_id": OWNER, "checked": len(occurrences), "resolved": [], "fenced": {}}
    for occurrence, (proof, reason) in evaluate(state_root, occurrences, proposals).items():
        if proof is None:
            report["fenced"][occurrence] = reason
        elif not args.resolve:
            report["resolved"].append({"occurrence_id": occurrence, "dry_run": True,
                                       "evidence_ref": proof["evidence_ref"]})
        else:
            receipt = state_root / "reconciliation" / (
                f"application-no-submit-{occurrence[len(OWNER) + 1:]}.json")
            receipt.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            receipt.write_text(json.dumps({"schema_version": 1, "receipt_type":
                                           "CROWDWORKS_APPLICATION_NO_SUBMIT_READBACK", **proof},
                                          sort_keys=True) + "\n", encoding="utf-8")
            receipt.chmod(0o600)
            if resolve_pre_effect_occurrence(OWNER, occurrence,
                                             pre_effect_readback=lambda p=proof: p,
                                             expected_state="claimed"):
                report["resolved"].append({"occurrence_id": occurrence,
                                           "evidence_ref": proof["evidence_ref"]})
            else:
                report["fenced"][occurrence] = "close_rejected"
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
