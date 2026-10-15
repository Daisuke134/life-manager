#!/usr/bin/env python3
"""Close one Mercor effect_unknown fence only from occurrence-bound readback.

The window is the run whose terminal claims the occurrence: a report event
whose ``occurrence_id`` is the occurrence or that carries
``lm-occurrence://<owner>/<run>/claim``.  Journals written before terminals
recorded that binding fall back to the occurrence's own wake start with an
open end, so every run that could have claimed it is covered.

* application: Mercor mails "Application Submitted - <title> on Mercor" within
  0-2 s of every submission (4/4 matched to official ``appliedAt``).  Zero such
  mails in the window, read from the application Gmail account, proves no
  submission.
* reply: the only provider effect is ``gog gmail send``.  Zero sent mails in
  the window proves no reply.
* paid: ``paid-owner`` execs the paid kernel only after
  ``mercor_paid_snapshot`` rewrites ``paid-official-snapshot.json`` (releases
  before that gate did not).  A snapshot older than the window start, written
  by an earlier run on the claim run's own release, with no kernel run marker,
  proves the kernel never started.

Existing pre-effect markers still close first.  Any hit, incomplete search,
ambiguous claim or missing input keeps the fence; nothing is retried.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from typing import Any, Callable

SHARED = Path(__file__).resolve().parents[3] / "_shared/marketplace-core/scripts"
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from runtime.host.resource_admission import resolve_pre_effect_occurrence  # noqa: E402
from reconcile_paid_no_effect import find_paid_no_effect_proof, run_marker_path  # noqa: E402
from reconcile_pre_effect_hint import find_pre_effect_proof  # noqa: E402

APP = "mercor-revenue-application"
REPLY = "mercor-revenue-reply"
PAID = "mercor-revenue-paid"
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
SLACK = 60  # host/provider clock skew
TAIL = 600  # measured Mercor confirmation lag is 0-2 s
QUERIES = {
    APP: 'from:mercor.com subject:"Application Submitted"',
    REPLY: "in:sent",
}
GOG = "/opt/homebrew/bin/gog"
PROFILE = Path("~/.config/anicca/job-search/profile.json").expanduser()


def _epoch(value: Any) -> float | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.timestamp() if parsed.tzinfo is not None else None


def _events(state_root: Path, owner: str) -> list[dict[str, Any]]:
    rows = []
    for path in [state_root / "events.jsonl", *sorted(state_root.glob("events-*.jsonl.gz"))]:
        try:
            with (gzip.open if path.suffix == ".gz" else open)(path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        value = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(value, dict) and value.get("loop_id") == owner:
                        rows.append(value)
        except OSError:
            continue
    return rows


def claim_window(rows: list[dict[str, Any]], owner: str, occurrence: str
                 ) -> tuple[tuple[float, float | None, dict[str, Any]] | None, str]:
    run_id = occurrence[len(owner) + 1:]
    claim_ref = f"lm-occurrence://{owner}/{run_id}/claim"
    bound = [r for r in rows if r.get("phase") == "report"
             and (r.get("occurrence_id") == occurrence
                  or claim_ref in (r.get("evidence_refs") or []))]
    if len(bound) > 1:
        return None, "claim_run_ambiguous"
    if bound:
        executor, terminal = bound[0].get("run_id"), bound[0]
        end = _epoch(terminal.get("timestamp"))
    else:
        own = [r for r in rows if r.get("run_id") == run_id]
        if not own or any("occurrence_id" in r for r in own):
            return None, "claim_run_unavailable"
        executor, terminal, end = run_id, {}, None
    starts = [_epoch(r.get("timestamp")) for r in rows if r.get("run_id") == executor
              and r.get("phase") == "execute" and r.get("status") == "running"]
    if (len(starts) != 1 or starts[0] is None or (bound and end is None)
            or (end is not None and end < starts[0])):
        return None, "claim_run_unavailable"
    return (starts[0], end, terminal), "ok"


def _account() -> str:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    account = ((profile.get("candidate") or {}).get("application_email")
               or profile.get("application_email") or profile.get("email"))
    if not isinstance(account, str) or not account.strip():
        raise RuntimeError("mercor_gmail_account_unavailable")
    return account.strip()


def gmail_search(query: str) -> dict[str, Any] | None:
    """Same read-only gog call the Reply snapshot already uses."""
    argv = [GOG, "gmail", "messages", "search", query, "--max", "100",
            "--account", _account(), "--json", "--no-input"]
    for attempt in range(2):
        if attempt:
            time.sleep(1)
        try:
            done = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=30)
        except subprocess.TimeoutExpired:
            continue
        if done.returncode == 0:
            try:
                value = json.loads(done.stdout)
            except ValueError:
                return None
            return value if isinstance(value, dict) else None
    return None


def _paid_proof(state_root: Path, occurrence: str, start: float, release: Any,
                rows: list[dict[str, Any]]) -> tuple[dict | None, str]:
    canonical = run_marker_path(state_root, occurrence)
    for marker in (canonical, state_root / "shared-paid" / "runs" / canonical.name):
        if marker.exists() or marker.is_symlink():
            return None, "paid_run_marker_present"
    path = state_root / "paid-official-snapshot.json"
    try:
        info = path.lstat()
        observed = _epoch(json.loads(path.read_text(encoding="utf-8")).get("observed_at"))
    except (OSError, ValueError, AttributeError):
        return None, "paid_snapshot_unavailable"
    if not stat.S_ISREG(info.st_mode) or observed is None:
        return None, "paid_snapshot_unavailable"
    if info.st_mtime >= start or observed >= start:
        return None, "paid_snapshot_refreshed_in_window"
    # Releases before the snapshot gate exec the kernel directly.  Accept only
    # when an earlier run on the claim run's own release wrote this snapshot.
    spans: dict[str, list[float | None]] = {}
    for row in rows:
        if row.get("release_sha") == release and row.get("phase") in {"execute", "report"}:
            spans.setdefault(row.get("run_id"), [None, None])[
                row["phase"] == "report"] = _epoch(row.get("timestamp"))
    writer = next((run for run, (begin, end) in spans.items()
                   if begin is not None and end is not None
                   and begin <= observed <= info.st_mtime <= end), None)
    if not isinstance(release, str) or not re.fullmatch(r"[0-9a-f]{40}", release) or writer is None:
        return None, "paid_snapshot_writer_unproven"
    return {"proof_type": "pre_effect",
            "evidence_ref": f"lm-mercor-paid-snapshot://{PAID}/{int(observed)}",
            "snapshot_observed_at": observed, "snapshot_writer_run_id": writer}, "ok"


def find_proof(state_root: Path, owner: str, occurrence: str, *,
               search: Callable[[str], dict[str, Any] | None] = gmail_search
               ) -> tuple[dict[str, Any] | None, str]:
    if (owner not in {APP, REPLY, PAID} or not SAFE_ID.fullmatch(occurrence)
            or not occurrence.startswith(f"{owner}:")):
        return None, "invalid_occurrence"
    local = (find_paid_no_effect_proof if owner == PAID else find_pre_effect_proof)(
        state_root, owner, occurrence)
    if local is not None:
        return local, "ok"
    rows = _events(state_root, owner)
    window, reason = claim_window(rows, owner, occurrence)
    if window is None:
        return None, reason
    start, end, terminal = window
    if owner == PAID:
        proof, reason = _paid_proof(state_root, occurrence, start,
                                    terminal.get("release_sha"), rows)
        if proof is None:
            return None, reason
    else:
        query = f"{QUERIES[owner]} after:{math.floor(start) - SLACK}"
        if end is not None:
            query += f" before:{math.ceil(end) + TAIL}"
        result = search(query)
        if (not isinstance(result, dict) or result.get("messages") != []
                or result.get("nextPageToken")):
            return None, "official_readback_not_absent"
        digest = hashlib.sha256(query.encode()).hexdigest()[:16]
        proof = {"proof_type": "pre_effect", "evidence_ref": f"gmail-search://{owner}/{digest}",
                 "query": query, "message_count": 0}
    return {"owner_id": owner, "occurrence_id": occurrence, "verified": True,
            "window": [start, end], "release_sha": terminal.get("release_sha"),
            "claim_run_id": terminal.get("run_id"), **proof}, "ok"


def reconcile(*, state_root: Path, owner: str, occurrence: str, resolve: bool = False,
              search: Callable[[str], dict[str, Any] | None] = gmail_search,
              resolver: Callable[..., bool] = resolve_pre_effect_occurrence) -> dict[str, Any]:
    proof, reason = find_proof(state_root, owner, occurrence, search=search)
    if proof is None:
        raise RuntimeError(reason)
    resolved = False
    if resolve:
        # Same two-step as reconcile_paid_no_effect: an already released exact
        # occurrence is an idempotent success for the same proof.
        resolved = any(resolver(owner, occurrence, pre_effect_readback=lambda: proof,
                                expected_state=state)
                       for state in ("claimed", "released"))
    return {**proof, "resolved": resolved}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    state_root = args.state_root.expanduser().resolve()
    try:
        result = reconcile(state_root=state_root, owner=args.owner,
                           occurrence=args.occurrence, resolve=args.resolve)
    except (RuntimeError, OSError, ValueError) as error:
        print(json.dumps({
            "version": 1, "owner_id": args.owner, "occurrence_id": args.occurrence,
            "phase": "reconcile", "command": "mercor_reconcile_fence_readback",
            "state_root": str(state_root), "exit_code": 75, "effect": "unknown",
            "effect_status": "unknown", "provider_receipt_id": None,
            "official_readback_ref": None, "evidence_refs": [],
            "error_class": str(error) or type(error).__name__, "retryable": False,
            "next_action": "obtain_occurrence_bound_readback", "resolved": False,
        }, ensure_ascii=False, sort_keys=True))
        return 75
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not args.resolve or result["resolved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
