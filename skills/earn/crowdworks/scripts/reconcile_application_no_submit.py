#!/usr/bin/env python3
"""Reconcile Application fences from exact CrowdWorks proposal readback.

The run that claimed an occurrence bounds its window. A verified receipt bound
to that occurrence resolves only when a fresh proposal-page readback confirms
the same ID and its full minute is inside the claim window. Without that proof,
the existing no-submit rules keep the fence for any bound receipt, pending
transaction, in-window proposal, or incomplete/unordered inventory.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any
from urllib.parse import urljoin, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from runtime.host.resource_admission import (resolve_pre_effect_occurrence,
                                             resolve_unknown_occurrence,
                                             state_root as resource_admission_state_root)
from reconcile_reply_no_send import (ADMISSION_DB, JST, MINUTE, SAFE_ID, SLACK,
                                     ProviderBrowserBusy, _json, _events, _overlaps,
                                     _provider_lease, _window)

OWNER = "crowdworks-revenue-application"
SENDER = "Kaito｜AI自動化"
SENDER_ID = "7145638"


def _minute(value: str) -> float | None:
    match = MINUTE.fullmatch(value or "")
    return datetime(*map(int, match.groups()), tzinfo=JST).timestamp() if match else None


def evaluate(state_root: Path, occurrences: list[str],
             proposals: list[tuple[int, str] | dict[str, Any]] | None
             ) -> dict[str, tuple[dict[str, Any] | None, str]]:
    rows = _events(state_root, OWNER)
    receipts = [json.loads(line) for line in
                (state_root / "application-receipts.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()]
    pending = (_json(state_root / "application-transaction.json") or {}).get("pending")
    timeline, ordered = _timeline(proposals)
    result = {}
    for occurrence in occurrences:
        result[occurrence] = _prove(occurrence, rows, receipts, pending, timeline, ordered)
    return result


def _timeline(proposals):
    if proposals is None:
        return None, False
    timeline = []
    try:
        for proposal in proposals:
            if isinstance(proposal, dict):
                pid = proposal.get("proposal_id")
                timestamp = proposal.get("first_message_timestamp")
                readback = proposal
            else:
                pid, timestamp = proposal
                readback = None
            if type(pid) is not int or pid < 1:
                return None, False
            timeline.append((pid, _minute(timestamp), readback))
    except (TypeError, ValueError):
        return None, False
    timeline.sort(key=lambda row: row[0], reverse=True)
    ordered = all(a[1] is not None and b[1] is not None and a[1] >= b[1]
                  for a, b in zip(timeline, timeline[1:]))
    ordered = ordered and all(minute is not None for _, minute, _ in timeline)
    return timeline, ordered


def _proposal_evidence(readback, proposal_id):
    if not isinstance(readback, dict) or readback.get("proposal_id") != proposal_id:
        return None
    proposal_url = readback.get("proposal_url")
    parsed_url = urlsplit(proposal_url if isinstance(proposal_url, str) else "")
    proposal_path = re.fullmatch(r"/proposals/(\d+)/?", parsed_url.path)
    seller = readback.get("seller_identity")
    profile_url = seller.get("profile_url") if isinstance(seller, dict) else None
    profile = urlsplit(profile_url if isinstance(profile_url, str) else "")
    timestamp = readback.get("first_message_timestamp")
    minute = _minute(timestamp) if isinstance(timestamp, str) else None
    observed_at = readback.get("observed_at")
    try:
        observed = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if (parsed_url.scheme != "https" or parsed_url.hostname != "crowdworks.jp"
            or proposal_path is None or int(proposal_path.group(1)) != proposal_id
            or not isinstance(seller, dict) or seller.get("display_name") != SENDER
            or profile.scheme != "https" or profile.hostname != "crowdworks.jp"
            or profile.path.rstrip("/") != f"/public/employees/{SENDER_ID}"
            or minute is None or observed.tzinfo is None
            or readback.get("first_message_minute") != datetime.fromtimestamp(
                minute, JST).isoformat(timespec="minutes")):
        return None
    return {
        "proposal_url": proposal_url,
        "seller_identity": {"display_name": SENDER, "profile_url": profile_url},
        "first_message_timestamp": timestamp,
        "first_message_minute": readback["first_message_minute"],
        "observed_at": observed.isoformat(),
    }


def _prove(occurrence, rows, receipts, pending, timeline, ordered):
    if not SAFE_ID.fullmatch(occurrence) or not occurrence.startswith(f"{OWNER}:"):
        return None, "invalid_occurrence"
    run_id = occurrence[len(OWNER) + 1:]
    window, reason = _window(rows, run_id, None, owner=OWNER)
    if window is None:
        return None, reason
    bound = [r for r in receipts if isinstance(r, dict)
             and r.get("occurrence_id") == occurrence]
    if pending:
        return None, "application_transaction_pending"
    if timeline is None:
        return None, "proposal_readback_incomplete"
    if not ordered:
        return None, "proposal_order_unverified"
    if bound:
        if (len(bound) != 1
                or bound[0].get("record_type") != "application_receipt"
                or bound[0].get("platform") != "crowdworks"
                or bound[0].get("status") != "verified"
                or not str(bound[0].get("application_external_id", "")).isdigit()):
            return None, "application_receipt_bound"
        proposal_id = int(bound[0]["application_external_id"])
        match = next((row for row in timeline if row[0] == proposal_id), None)
        if match is None:
            return None, "application_receipt_proposal_missing"
        _, minute, readback = match
        if minute < window[0] or minute + 60 > window[1]:
            return None, "application_receipt_window_mismatch"
        evidence = _proposal_evidence(readback, proposal_id)
        if evidence is None:
            return None, "application_receipt_readback_incomplete"
        return {
            "owner_id": OWNER, "occurrence_id": occurrence, "verified": True,
            "proof_type": "official_effect", "provider_receipt_id": f"proposal:{proposal_id}",
            "evidence_ref": f"lm-crowdworks-application-readback://{OWNER}/{run_id}/{proposal_id}",
            "application_external_id": str(proposal_id), "window": list(window), **evidence,
        }, "ok"
    if not timeline or timeline[-1][1] + 60 >= window[0] - SLACK:
        return None, "proposal_readback_incomplete"
    for pid, minute, _ in timeline:
        if _overlaps(minute, window):
            return None, f"proposal_in_window:{pid}"
    before = next(pid for pid, minute, _ in timeline if minute + 60 < window[0] - SLACK)
    before_row = next(row for row in timeline if row[0] == before)
    digest = hashlib.sha256(json.dumps({"window": window, "latest_before": before},
                                       sort_keys=True).encode()).hexdigest()[:16]
    proof = {
        "owner_id": OWNER, "occurrence_id": occurrence, "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": f"lm-crowdworks-application-readback://{OWNER}/{run_id}/{digest}",
        "window": list(window), "latest_proposal_before_window": before,
    }
    if evidence := _proposal_evidence(before_row[2], before):
        proof.update(evidence)
    return proof, "ok"


def recorded_proposals(state_root: Path) -> set[int]:
    """Proposal ids our own receipts recorded; the provider list can drop some."""
    ids = set()
    for line in (state_root / "application-receipts.jsonl").read_text(encoding="utf-8").splitlines():
        value = json.loads(line) if line.strip() else {}
        if str(value.get("application_external_id", "")).isdigit():
            ids.add(int(value["application_external_id"]))
    return ids


def read_proposals_with_lease(
    state_root: Path, oldest_needed: float, recorded: set[int]
) -> tuple[list[dict[str, Any]] | None, str]:
    """Read proposal pages without queueing behind an active revenue owner."""
    try:
        with _provider_lease(state_root):
            import reply_adapter
            adapter, _ = reply_adapter.build(["--state-path", str(state_root / "reply/state.json")])
            try:
                adapter._open()
                return read_proposals(adapter.page, oldest_needed, recorded), "ok"
            except Exception:
                return None, "proposal_readback_incomplete"
            finally:
                adapter.close()
    except ProviderBrowserBusy:
        return None, "provider_browser_busy"


def read_proposals(page: Any, oldest_needed: float,
                   recorded: set[int] = frozenset()) -> list[dict[str, Any]] | None:
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
        actual_url = urlsplit(page.url)
        displayed = re.fullmatch(r"/proposals/(\d+)/?", actual_url.path)
        if (actual_url.scheme != "https" or actual_url.hostname != "crowdworks.jp"
                or displayed is None or int(displayed.group(1)) != pid):
            return None
        first = page.locator('div[class*="_messageItem_"]').first
        sender_link = first.locator('a[class*="_senderName_"]').first
        sender = (sender_link.text_content() or "").strip()
        profile_url = urljoin("https://crowdworks.jp", sender_link.get_attribute("href") or "")
        profile = urlsplit(profile_url)
        timestamp = first.locator("time").first.get_attribute("datetime") or ""
        minute = _minute(timestamp)
        if (sender != SENDER or profile.scheme != "https"
                or profile.hostname != "crowdworks.jp"
                or profile.path.rstrip("/") != f"/public/employees/{SENDER_ID}"
                or minute is None):
            return None
        result.append({
            "proposal_id": pid, "proposal_url": page.url,
            "seller_identity": {"display_name": sender, "profile_url": profile_url},
            "first_message_timestamp": timestamp,
            "first_message_minute": datetime.fromtimestamp(minute, JST).isoformat(timespec="minutes"),
            "observed_at": datetime.now(timezone.utc).isoformat(),
        })
        if minute < oldest_needed:
            break
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--admission-db", type=Path, default=ADMISSION_DB)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    state_root = args.state_root.expanduser().resolve()
    admission_db = args.admission_db.expanduser().resolve()
    resolver_db = (resource_admission_state_root() / "admission-v2.sqlite3").resolve()
    if args.resolve and admission_db != resolver_db:
        print(json.dumps({"owner_id": OWNER, "checked": 0, "resolved": [],
                          "fenced": {}, "error": "admission_database_mismatch"},
                         ensure_ascii=False, sort_keys=True))
        return 75
    with sqlite3.connect(f"file:{admission_db}?mode=ro", uri=True) as db:
        occurrences = [r[0] for r in db.execute(
            "SELECT occurrence_id FROM occurrences WHERE owner_id=? AND state='claimed' "
            "AND effect_unknown=1 ORDER BY queued_at", (OWNER,))]
    rows = _events(state_root, OWNER)
    starts = [w[0] for o in occurrences
              if (w := _window(rows, o[len(OWNER) + 1:], None, owner=OWNER)[0])]
    proposals = None
    readback_reason = "proposal_readback_incomplete"
    if starts:
        proposals, readback_reason = read_proposals_with_lease(
            state_root, min(starts) - 3600, recorded_proposals(state_root))
    if readback_reason == "provider_browser_busy":
        report = {
            "owner_id": OWNER,
            "checked": len(occurrences),
            "resolved": [],
            "fenced": {occurrence: "provider_browser_busy" for occurrence in occurrences},
            "next_action": "retry_after_provider_browser",
        }
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 75
    report = {"owner_id": OWNER, "checked": len(occurrences), "resolved": [], "fenced": {}}
    for occurrence, (proof, reason) in evaluate(state_root, occurrences, proposals).items():
        if proof is None:
            report["fenced"][occurrence] = reason
        elif not args.resolve:
            report["resolved"].append({"occurrence_id": occurrence, "dry_run": True,
                                       "evidence_ref": proof["evidence_ref"]})
        elif proof["proof_type"] == "official_effect":
            receipt = state_root / "reconciliation" / (
                f"application-effect-{occurrence[len(OWNER) + 1:]}.json")
            receipt.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            receipt.write_text(json.dumps({"schema_version": 1, "receipt_type":
                                           "CROWDWORKS_APPLICATION_RECEIPT_READBACK", **proof},
                                          sort_keys=True) + "\n", encoding="utf-8")
            receipt.chmod(0o600)
            if resolve_unknown_occurrence(OWNER, occurrence,
                                          official_readback=lambda p=proof: p,
                                          expected_state="claimed"):
                report["resolved"].append({"occurrence_id": occurrence,
                                           "evidence_ref": proof["evidence_ref"]})
            else:
                report["fenced"][occurrence] = "close_rejected"
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
