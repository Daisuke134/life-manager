#!/usr/bin/env python3
"""Safely reconcile Coconala application fences through the registered browser.

The generic fence loop has no browser identity in its environment.  This adapter
therefore performs exact occurrence-to-request-set discovery first, without
opening a browser. Only fully bound requests for one occurrence start a readback, and that
readback is run through ``with-browser.sh coconala:kosuke`` so it cannot share the
identity with another loop.  It never opens an application form or clicks submit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[3]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import application_occurrence_reconcile as reconciler  # noqa: E402
from runtime.host import resource_admission  # noqa: E402


OWNER_ID = "hf-gig-apply-direct"
BROWSER_IDENTITY = "coconala:kosuke"
WITH_BROWSER = REPO_ROOT / "skills" / "browser" / "with-browser.sh"
RECONCILER = SCRIPT_DIR / "application_occurrence_reconcile.py"


def _scan_result_path(result: Path | None) -> Path:
    return result or Path.home() / "gig" / "apply-direct" / "evidence" / "occurrence-reconcile-scan.json"


def _write_scan_result(result_path: Path, result: Mapping[str, object]) -> None:
    reconciler._atomic_json(result_path, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def build_browser_command(
    *,
    occurrence_id: str,
    runtime_run_id: str,
    request_ids: Sequence[str],
    owner_id: str,
    intent_root: Path,
    evidence_dir: Path | None = None,
    result: Path | None = None,
    max_pages: int = 1000,
) -> list[str]:
    """Build the only command that may open a Coconala browser for reconciliation."""
    command = [
        "bash",
        str(WITH_BROWSER),
        BROWSER_IDENTITY,
        "--",
        sys.executable,
        str(RECONCILER),
        "--owner-id",
        owner_id,
        "--occurrence-id",
        occurrence_id,
        "--runtime-run-id",
        runtime_run_id,
        "--intent-root",
        str(intent_root),
        "--max-pages",
        str(max_pages),
    ]
    for request_id in request_ids:
        command.extend(["--request-id", request_id])
    if evidence_dir is not None:
        command.extend(["--evidence-dir", str(evidence_dir)])
    if result is not None:
        command.extend(["--result", str(result)])
    return command


def run_browser_reconcile(
    command: Sequence[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> int:
    """Run one identity-leased readback without waiting behind a live owner."""
    environment = os.environ.copy()
    # A fence wake must defer when the production paid loop owns the identity; it
    # must never queue behind it long enough to overlap a later wake.
    environment["BROWSER_WAIT_SECONDS"] = "0"
    # Reconciliation is readback-only.  Do not provision or mutate a browser as a
    # side effect of discovering that the registered identity is unavailable.
    # ``with-browser.sh`` uses ``${VAR:-default}``; a blank value would therefore
    # re-enable its provisioning helper.  A non-executable sentinel disables it.
    environment["AI_ENSURE_PROVISION_BROWSER"] = "/dev/null"
    completed = (runner or subprocess.run)(command, cwd=REPO_ROOT, env=environment, check=False)
    return int(completed.returncode)


SETTLED_STATES = frozenset({"confirmed", "retired_absent"})


EVIDENCE_DIR = Path.home() / "gig" / "apply-direct" / "evidence"
CLOSED_READBACK = EVIDENCE_DIR / "request-closed-readback.json"


def _latest_roster() -> Path:
    found = sorted(EVIDENCE_DIR.glob("coconala-applied-history-*.json"))
    return found[-1] if found else EVIDENCE_DIR / "coconala-applied-history-missing.json"


def _roster_ids(path: Path) -> set[str]:
    """Requests the official applied-history readback lists (an application exists)."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        value = value.get("official_readback", value)
        if (value.get("source") != "code_owned_cdp_readback" or value.get("observed") is not True
                or value.get("truncated") is not False):
            return set()
        return {str(item) for item in value.get("request_ids") or []}
    except (OSError, ValueError, AttributeError):
        return set()


def _closed_ids(path: Path) -> set[str]:
    """Requests whose official page read back as 募集終了: no further application is possible."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("source") != "code_owned_cdp_readback":
            return set()
        return {str(rid) for rid, row in (value.get("requests") or {}).items()
                if isinstance(row, dict) and row.get("closed") is True
                and (row.get("http_status") == 200
                     or (row.get("gone") is True and row.get("http_status") == 404))}
    except (OSError, ValueError, AttributeError):
        return set()


def _settled_scan(intent_root: Path, *, roster_path: Path | None = None,
                  closed_path: Path | None = None) -> dict[str, object]:
    """Count intents that may hold an application effect that could still be duplicated.

    Settled: confirmed/retired_absent (provider readback), an explicit pre_effect
    phase, a request listed in the official applied history, or a request whose
    official page reads 募集終了 (a duplicate application is impossible).
    Legacy, state-less and unreadable intents are otherwise unresolved.
    """
    applied = _roster_ids(roster_path or _latest_roster())
    closed = _closed_ids(closed_path or CLOSED_READBACK)
    digest = hashlib.sha256()
    scanned = unresolved = 0
    for path in sorted(intent_root.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("intent is not an object")
            if not {"state", "request_id", "effect_phase"} & value.keys():
                continue  # store metadata (wedge-quarantine, scan cursors), not an intent
            state, phase = value.get("state"), value.get("effect_phase")
            request_id = str(value.get("request_id") or path.stem)
        except (OSError, ValueError, AttributeError):
            state, phase, request_id = "unreadable", "unreadable", None
        scanned += 1
        settled = (state in SETTLED_STATES or phase == "pre_effect"
                   or (request_id is not None and (request_id in applied or request_id in closed)))
        if not settled:
            unresolved += 1
        digest.update(f"{path.name}\0{state}\0{phase}\0{settled}\n".encode("utf-8"))
    return {"scanned_intents": scanned, "unresolved_irreversible": unresolved,
            "evidence_ref": f"gig-intents://sha256/{digest.hexdigest()}"}


def _fenced_occurrences(owner_id: str) -> list[str]:
    _root, _owners, _tickets, database = resource_admission._durable_paths()
    import sqlite3
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=30) as connection:
        rows = connection.execute(
            "SELECT occurrence_id FROM occurrences WHERE owner_id=? AND effect_unknown=1"
            " AND state IN ('claimed','released') ORDER BY sequence", (owner_id,)).fetchall()
    return [row[0] for row in rows]


def _resolve_settled(owner_id, occurrence_id, *, settled_proof):
    return resource_admission.resolve_settled_write_ahead_occurrence(
        owner_id, occurrence_id, settled_proof=settled_proof)


def _close_settled_fences(owner_id: str, intent_root: Path) -> tuple[dict[str, object], list[dict]]:
    scan = _settled_scan(intent_root)
    if scan["scanned_intents"] == 0 or scan["unresolved_irreversible"] != 0:
        return scan, []
    closed = []
    for occurrence_id in _fenced_occurrences(owner_id):
        checked: dict[str, object] = {}
        def proof(occurrence_id=occurrence_id, checked=checked):
            checked.update(_settled_scan(intent_root))
            return {"owner_id": owner_id, "occurrence_id": occurrence_id, "verified": True,
                    "proof_type": "write_ahead_store_settled.v1", **checked}
        if _resolve_settled(owner_id, occurrence_id, settled_proof=proof):
            closed.append({"owner_id": owner_id, "occurrence_id": occurrence_id, "verified": True,
                           "proof_type": "write_ahead_store_settled.v1",
                           "evidence_ref": checked.get("evidence_ref", scan["evidence_ref"])})
    return scan, closed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-id", default=OWNER_ID)
    parser.add_argument("--intent-root", type=Path, default=Path.home() / "gig" / "application-intents")
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--max-pages", type=int, default=1000)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    if args.owner_id != OWNER_ID:
        _write_scan_result(
            _scan_result_path(args.result),
            {
                "status": "unresolved",
                "reason": "owner_not_allowlisted",
                "retryable": False,
                "effect": 0,
                "readback": 0,
            },
        )
        return 0
    if args.max_pages < 1:
        _parser().error("--max-pages must be positive")

    try:
        target = reconciler.discover_single_target(
            owner_id=args.owner_id,
            intent_root=args.intent_root,
        )
    except reconciler.ReconcileContractError as error:
        _write_scan_result(
            _scan_result_path(args.result),
            {
                "status": "unresolved",
                "reason": str(error),
                "retryable": True,
                "effect": 0,
                "readback": 0,
                "next_action": "read admission and intent stores again; do not release or retry",
            },
        )
        return 0

    if target is None:
        scan, closed = _close_settled_fences(args.owner_id, args.intent_root)
        if closed:
            _write_scan_result(_scan_result_path(args.result), {
                "status": "reconciled", "reason": "write_ahead_store_settled",
                "retryable": False, "effect": 0, "readback": 1, **scan,
                "closed_occurrences": [item["occurrence_id"] for item in closed],
            })
            for item in closed:
                print(json.dumps(item, sort_keys=True, separators=(",", ":")))
            return 0
        _write_scan_result(
            _scan_result_path(args.result),
            {
                "status": "nothing_to_reconcile",
                "reason": "exact_occurrence_request_set_not_present",
                "retryable": False,
                "effect": 0,
                "readback": 0,
                "next_action": "wait for exact run/occurrence-bound intents; do not replay",
                **scan,
            },
        )
        return 0

    occurrence_id, runtime_run_id, request_ids = target
    command = build_browser_command(
        occurrence_id=occurrence_id,
        runtime_run_id=runtime_run_id,
        request_ids=request_ids,
        owner_id=args.owner_id,
        intent_root=args.intent_root,
        evidence_dir=args.evidence_dir,
        result=args.result,
        max_pages=args.max_pages,
    )
    return run_browser_reconcile(command, runner=runner)


if __name__ == "__main__":
    raise SystemExit(main())
