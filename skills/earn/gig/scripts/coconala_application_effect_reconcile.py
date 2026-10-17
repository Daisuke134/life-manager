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
import re
import subprocess
from datetime import datetime
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
import application_effect_fence as fence  # noqa: E402
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


APPLY_ROOT = Path.home() / "gig" / "apply-direct"
EVIDENCE_DIR = APPLY_ROOT / "evidence"
CLOSED_READBACK = EVIDENCE_DIR / "request-closed-readback.json"
CLOSED_READBACK_SCRIPT = SCRIPT_DIR / "coconala_request_closed_readback.py"
# application_parent raises application_応募する_button_missing before it dispatches any
# mouse event, and only that error retires an intent after the irreversible marker.
PRE_DISPATCH_ABORT = "pre_submit_effect_not_started:click_submit_control:"


def _latest_roster() -> Path:
    found = sorted(EVIDENCE_DIR.glob("coconala-applied-history-*.json"), key=lambda path: path.stat().st_mtime)
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


def _closed_rows(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("source") != "code_owned_cdp_readback":
            return {}
        return {str(rid): row for rid, row in (value.get("requests") or {}).items() if isinstance(row, dict)}
    except (OSError, ValueError, AttributeError):
        return {}


def _identity_account(value: dict, apply_root: Path) -> str | None:
    """Account captured before the marker by the same commit pass that wrote the intent."""
    rid = value["request_id"]
    task = str((value.get("lease_fence") or {}).get("task") or "")
    match = re.fullmatch(r"gig-apply-direct-((gig-apply-direct-[0-9]+-[0-9]+)-commit-([0-9]+))", task)
    if match is None or match.group(3) != rid:
        return None
    found = list((apply_root / match.group(2)).glob(
        f"*/commit-workers/{rid}/gig-{match.group(1)}-B2-{rid}-identity.json"))
    try:
        identity = json.loads(found[0].read_text(encoding="utf-8")) if len(found) == 1 else {}
    except (OSError, ValueError):
        return None
    account = str(identity.get("account_id") or "")
    if (identity.get("source") != "code_owned_cdp_authenticated_identity"
            or identity.get("request_id") != rid or not account.isdigit()):
        return None
    return account


def _pre_dispatch_abort_archive(value: dict, intent_root: Path) -> Path | None:
    cas = str(value.get("cas") or "")
    path = (intent_root / "recovery-history" / value["request_id"]
            / f"{hashlib.sha256(cas.encode('utf-8')).hexdigest()}.json")
    try:
        archive = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    archived = archive.get("intent") if isinstance(archive, dict) else None
    if (archive.get("event") != "prepared_reconciled_absent"
            or not str(archive.get("reason") or "").startswith(PRE_DISPATCH_ABORT)
            or not isinstance(archived, dict) or not cas or archived.get("cas") != cas
            or archived.get("runtime_occurrence_id") != value.get("runtime_occurrence_id")):
        return None
    return path


def _roster_proves_no_dispatch(value: dict, intent_root: Path, apply_root: Path, rows: dict) -> bool:
    """Post-marker retire without a click, plus the official roster lacking our account.

    The request page lists every applicant; a complete list (count matches, nobody
    contracted) read after the retire that excludes the account captured before the
    marker proves this attempt left no application.
    """
    archive = _pre_dispatch_abort_archive(value, intent_root)
    account = _identity_account(value, apply_root) if archive else None
    row = rows.get(value["request_id"])
    if account is None or not isinstance(row, dict):
        return False
    url = f"https://coconala.com/requests/{value['request_id']}"
    ids = row.get("applicant_ids")
    try:
        after_retire = datetime.fromisoformat(str(row.get("observed_at"))).timestamp() > archive.stat().st_mtime
    except (OSError, ValueError, TypeError):
        return False
    return (after_retire and row.get("http_status") == 200
            and row.get("url") == url and row.get("final_url") == url
            and isinstance(ids, list) and all(isinstance(item, str) for item in ids)
            and type(row.get("applicants_count")) is int and row["applicants_count"] == len(set(ids)) == len(ids)
            and row.get("contracted_count") == 0 and row.get("expander_remaining") is False
            and account not in ids and account not in (row.get("requester_ids") or []))


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


STORE_METADATA = frozenset({"wedge-quarantine.json", "full-history-scan-state.json"})


def _intent_settled(value: dict, applied: set[str], closed: set[str],
                    no_dispatch: Callable[[dict], bool] = lambda _value: False) -> bool:
    """Whether an intent can no longer hide a duplicable application.

    Provider-confirmed, a versioned pre_effect intent, a request listed in the
    official applied history, or a request whose own official page is 募集終了 /
    gone. retired_absent counts only when no irreversible attempt started: the
    screenshot-based retire path is not a provider readback; after the marker it
    also needs ``no_dispatch`` (pre-dispatch abort plus the official applicant roster).
    """
    request_id = str(value.get("request_id") or "")
    if request_id and (request_id in applied or request_id in closed):
        return True
    if value.get("state") == "confirmed" or fence.is_pre_effect(value):
        return True
    if value.get("state") != "retired_absent":
        return False
    return value.get("effect_phase") != fence.IRREVERSIBLE_ATTEMPT_STARTED or no_dispatch(value)


def _store_intents(intent_root: Path):
    """Yield (path, intent-or-None); None means unreadable or not an intent object."""
    for path in sorted(intent_root.glob("*.json")):
        if path.name in STORE_METADATA:
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            value = None
        if not isinstance(value, dict) or not value.get("state"):
            value = None
        else:
            value = {**value, "request_id": str(value.get("request_id") or path.stem)}
        yield path, value


def _settled_scan(intent_root: Path, *, roster_path: Path | None = None,
                  closed_path: Path | None = None, apply_root: Path | None = None) -> dict[str, object]:
    """Count store entries that may still hide a duplicable application (fail closed)."""
    applied = _roster_ids(roster_path or _latest_roster())
    closed_path = closed_path or CLOSED_READBACK
    closed = _closed_ids(closed_path)
    rows = _closed_rows(closed_path)

    def no_dispatch(value: dict) -> bool:
        return _roster_proves_no_dispatch(value, intent_root, apply_root or APPLY_ROOT, rows)

    digest = hashlib.sha256()
    scanned = unresolved = 0
    for path, value in _store_intents(intent_root):
        scanned += 1
        settled = value is not None and _intent_settled(value, applied, closed, no_dispatch)
        if not settled:
            unresolved += 1
        state = value.get("state") if value else "unreadable"
        phase = value.get("effect_phase") if value else "unreadable"
        digest.update(f"{path.name}\0{state}\0{phase}\0{settled}\n".encode("utf-8"))
    return {"scanned_intents": scanned, "unresolved_irreversible": unresolved,
            "evidence_ref": f"gig-intents://sha256/{digest.hexdigest()}"}


def _fenced_occurrences(owner_id: str) -> list[str]:
    _root, _owners, _tickets, database = resource_admission._durable_paths()
    import sqlite3
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=30) as connection:
        rows = connection.execute(
            "SELECT occurrence_id FROM occurrences WHERE owner_id=? AND effect_unknown=1"
            " AND state='claimed' ORDER BY queued_at", (owner_id,)).fetchall()
    return [row[0] for row in rows]


def _resolve_settled(owner_id, occurrence_id, *, settled_proof):
    return resource_admission.resolve_settled_write_ahead_occurrence(
        owner_id, occurrence_id, settled_proof=settled_proof)


def _needs_roster_readback(intent_root: Path) -> bool:
    """Read the official roster only for post-marker intents retired before any click."""
    return any(value is not None and value.get("state") == "retired_absent"
               and value.get("effect_phase") == fence.IRREVERSIBLE_ATTEMPT_STARTED
               and _pre_dispatch_abort_archive(value, intent_root) is not None
               for _path, value in _store_intents(intent_root))


def _close_settled_fences(owner_id: str, intent_root: Path, runner=None) -> tuple[dict[str, object], list[dict]]:
    scan = _settled_scan(intent_root)
    if scan["unresolved_irreversible"] and _needs_roster_readback(intent_root):
        exit_code = run_browser_reconcile(["bash", str(WITH_BROWSER), BROWSER_IDENTITY, "--",
                                           sys.executable, str(CLOSED_READBACK_SCRIPT)], runner=runner)
        scan = {**_settled_scan(intent_root), "roster_readback_exit_code": exit_code}
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
        scan, closed = _close_settled_fences(args.owner_id, args.intent_root, runner)
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
