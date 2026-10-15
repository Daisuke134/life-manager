#!/usr/bin/env python3
"""Close one Mercor effect_unknown fence only from occurrence-bound readback.

Binding copies the host pre-effect proof (``runtime/loop/lm_loop.py``): the
claim run is the one run whose terminal carries
``lm-occurrence://<owner>/<suffix>/claim``, else the occurrence's own wake.
The window spans every row tagged with the occurrence (nested runners
included) plus every row of the claim run.  Journals written before rows
carried an occurrence keep the suffix run with an open end.  A journal whose
oldest row is newer than the occurrence's ``queued_at`` fails closed.

* application: Mercor mails "Application Submitted - <title> on Mercor" from
  team@mercor.com 0-4 s after every submission (92/92 official ``appliedAt``,
  docs/evidence/job-search-loop/2026-10-15-mercor-fence-readback.json).  Zero
  such mails anywhere in Gmail (spam/trash included) proves no submission.
  The host's pre-spawn hint is not used: it predates the agent's clicks.
  Scope: submissions only; the pass's per-run Telegram report is not covered.
* reply: provider effect is ``gog gmail send``; owner notification goes
  through ``telegram-outbox.sqlite3`` whose ``claimed_at`` is stamped right
  before each send.  Zero mails from the account and zero outbox claims in
  the window prove neither happened.
* paid: ``paid-owner`` execs the paid kernel only after
  ``mercor_paid_snapshot`` rewrites ``paid-official-snapshot.json`` (releases
  before that gate did not).  A snapshot older than the window, written by
  an earlier run on the claim run's own release, with no kernel run marker,
  proves the kernel never started.

Any hit, page token, ambiguous claim or missing input keeps the fence; nothing
is retried and no provider is mutated (gog runs with ``--gmail-no-send``).
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import time
from typing import Any, Callable

SHARED = Path(__file__).resolve().parents[3] / "_shared/marketplace-core/scripts"
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from runtime.host.resource_admission import (  # noqa: E402
    resolve_pre_effect_occurrence, state_root as admission_state_root)
from reconcile_paid_no_effect import find_paid_no_effect_proof, run_marker_path  # noqa: E402
from reconcile_pre_effect_hint import find_pre_effect_proof  # noqa: E402

APP = "mercor-revenue-application"
REPLY = "mercor-revenue-reply"
PAID = "mercor-revenue-paid"
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
SLACK = 60  # host/provider clock skew
TAIL = 600  # measured Mercor confirmation lag is 0-4 s
QUERIES = {
    APP: 'in:anywhere from:mercor.com subject:"Application Submitted"',
    REPLY: "in:anywhere from:me",
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


def _queued_at(occurrence: str) -> float | None:
    database = admission_state_root() / "admission-v2.sqlite3"
    if not database.is_file():
        return None
    with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=0.5)) as db:
        row = db.execute("SELECT queued_at FROM occurrences WHERE occurrence_id=?",
                         (occurrence,)).fetchone()
    return float(row[0]) if row else None


def claim_window(rows: list[dict[str, Any]], owner: str, occurrence: str
                 ) -> tuple[tuple[float, float | None, dict[str, Any]] | None, str]:
    suffix = occurrence[len(owner) + 1:]
    claim_ref = f"lm-occurrence://{owner}/{suffix}/claim"
    tagged = [r for r in rows if r.get("occurrence_id") == occurrence]
    claims = [r for r in rows if claim_ref in (r.get("evidence_refs") or [])]
    if any(r.get("occurrence_id") not in (None, occurrence) for r in claims):
        return None, "claim_occurrence_mismatch"
    claim_runs = {r.get("run_id") for r in claims}
    if len(claim_runs) > 1:
        return None, "claimed_by_multiple_runs"
    claim_run = claim_runs.pop() if claim_runs else suffix
    run_rows = [r for r in rows if r.get("run_id") == claim_run]
    if any(r.get("phase") == "report" and r.get("occurrence_id") not in (None, occurrence)
           for r in run_rows):
        return None, "claimed_by_other_run"
    legacy = not tagged and not claims
    if legacy and any("occurrence_id" in r for r in run_rows):
        return None, "claim_run_unavailable"
    members = {id(r): r for r in [*tagged, *claims, *run_rows]}.values()
    stamps = [_epoch(r.get("timestamp")) for r in members]
    terminals = sorted((r for r in run_rows if r.get("phase") == "report"),
                       key=lambda r: str(r.get("timestamp")))
    if (not terminals or None in stamps
            or not any(r.get("phase") == "execute" and r.get("status") == "running"
                       for r in run_rows)):
        return None, "claim_run_unavailable"
    return (min(stamps), None if legacy else max(stamps), terminals[-1]), "ok"


def _account() -> str:
    """The Mercor login identity: paid snapshot and auth readback match it."""
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    account = ((profile.get("candidate") or {}).get("application_email")
               or profile.get("application_email") or profile.get("email"))
    if not isinstance(account, str) or not account.strip():
        raise RuntimeError("mercor_gmail_account_unavailable")
    return account.strip()


def gmail_search(query: str) -> dict[str, Any] | None:
    """Same read-only gog call the Reply snapshot already uses."""
    argv = [GOG, "gmail", "messages", "search", query, "--max", "100",
            "--account", _account(), "--json", "--no-input", "--gmail-no-send"]
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


def _outbox_claims(state_root: Path, start: float, end: float | None) -> int | None:
    database = state_root / "telegram-outbox.sqlite3"
    if not database.is_file():
        return None
    try:
        with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=0.5)) as db:
            claimed = [_epoch(row[0]) for row in db.execute(
                "SELECT claimed_at FROM telegram_outbox WHERE claimed_at IS NOT NULL")]
    except sqlite3.Error:
        return None
    if None in claimed:
        return None
    upper = math.inf if end is None else end + TAIL
    return sum(1 for value in claimed if start - SLACK <= value <= upper)


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
    # Application-owner never cleared the host hint before its pass, so a
    # leftover hint there proves nothing; Reply and Paid clear theirs.
    local = {REPLY: find_pre_effect_proof, PAID: find_paid_no_effect_proof}.get(owner)
    if local is not None and (proof := local(state_root, owner, occurrence)) is not None:
        return proof, "ok"
    rows = _events(state_root, owner)
    window, reason = claim_window(rows, owner, occurrence)
    if window is None:
        return None, reason
    queued_at = _queued_at(occurrence)
    history = [stamp for r in rows if (stamp := _epoch(r.get("timestamp"))) is not None]
    if queued_at is not None and (not history or min(history) > queued_at):
        # Rotated-out journals could hide a foreign claim (lm_loop.py).
        return None, "history_incomplete"
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
        if owner == REPLY:
            claimed = _outbox_claims(state_root, start, end)
            if claimed != 0:
                return None, "telegram_outbox_not_quiet"
            proof["telegram_outbox_claims_in_window"] = 0
    return {"owner_id": owner, "occurrence_id": occurrence, "verified": True,
            "window": [start, end], "release_sha": terminal.get("release_sha"),
            "claim_run_id": terminal.get("run_id"), "queued_at": queued_at, **proof}, "ok"


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
    except (RuntimeError, OSError, ValueError, sqlite3.Error) as error:
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
