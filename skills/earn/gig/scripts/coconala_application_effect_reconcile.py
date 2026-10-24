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
GIG_VAULT = Path.home() / ".cloak/vault/gig-daily-driver/auth-state.json"


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
    # The fence reconciler has no Coconala session env; without it the leased context
    # is seeded from the personal vault and the readback lands on /login (2026-10-25).
    environment.setdefault("CLOAK_SESSION_VAULT_FILE", str(GIG_VAULT))
    completed = (runner or subprocess.run)(command, cwd=REPO_ROOT, env=environment, check=False)
    return int(completed.returncode)


SETTLED_STATES = frozenset({"confirmed", "retired_absent"})


APPLY_ROOT = Path.home() / "gig" / "apply-direct"
EVIDENCE_DIR = APPLY_ROOT / "evidence"
LEDGER_PATH = Path.home() / "gig" / "applied.jsonl"
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


_COMMIT_TASK = re.compile(r"gig-apply-direct-((gig-apply-direct-[0-9]+-[0-9]+)-commit-([0-9]+))")


def _commit_task(value: dict) -> re.Match | None:
    """(worker pass id, commit pass id, request id) of the commit pass that wrote the intent."""
    match = _COMMIT_TASK.fullmatch(str((value.get("lease_fence") or {}).get("task") or ""))
    return match if match is not None and match.group(3) == value["request_id"] else None


def _identity_account(value: dict, apply_root: Path) -> str | None:
    """Account captured before the marker by the same commit pass that wrote the intent."""
    rid = value["request_id"]
    match = _commit_task(value)
    if match is None:
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


# A clicked application can take a while to appear on the request's applicant roster; an
# absence read sooner than this after the irreversible marker proves nothing.
ROSTER_SAFETY_LAG_SECONDS = 30 * 60


def _roster_verdict(value: dict, row: object, apply_root: Path, *,
                    after: float, lag: float = 0) -> str | None:
    """"present"/"absent" for our account on the request's own official applicant roster.

    The account is the one the same commit pass captured before the marker. Present needs
    the exact page read after ``after``; absent also needs the whole list (count matches,
    nothing left to expand, nobody contracted) read at least ``lag`` seconds after it.
    Anything else is None: keep the fence.
    """
    account = _identity_account(value, apply_root)
    if account is None or not isinstance(row, dict):
        return None
    url = f"https://coconala.com/requests/{value['request_id']}"
    ids = row.get("applicant_ids")
    try:
        observed = datetime.fromisoformat(str(row.get("observed_at"))).timestamp()
    except (ValueError, TypeError):
        return None
    if (observed <= after or row.get("http_status") != 200
            or row.get("url") != url or row.get("final_url") != url
            or not isinstance(ids, list) or not all(isinstance(item, str) for item in ids)
            or account in (row.get("requester_ids") or [])):
        return None
    if account in ids:
        return "present"
    complete = (type(row.get("applicants_count")) is int
                and row["applicants_count"] == len(set(ids)) == len(ids)
                and row.get("contracted_count") == 0 and row.get("expander_remaining") is False)
    return "absent" if complete and observed >= after + lag else None


def _roster_proves_no_dispatch(value: dict, intent_root: Path, apply_root: Path, rows: dict) -> bool:
    """Post-marker retire without a click, plus the official roster lacking our account.

    The request page lists every applicant; a complete list (count matches, nobody
    contracted) read after the retire that excludes the account captured before the
    marker proves this attempt left no application.
    """
    archive = _pre_dispatch_abort_archive(value, intent_root)
    try:
        retired_at = archive.stat().st_mtime if archive else None
    except OSError:
        return False
    return retired_at is not None and _roster_verdict(
        value, rows.get(value["request_id"]), apply_root, after=retired_at) == "absent"


def _roster_settles_attempt(value: dict, intent_root: Path, apply_root: Path, rows: dict) -> str | None:
    """Verdict for a still-prepared post-marker intent, read after its marker + safety lag."""
    try:
        marker = (Path(intent_root) / f"{value['request_id']}.json").stat().st_mtime
    except OSError:
        return None
    return _roster_verdict(value, rows.get(value["request_id"]), apply_root,
                           after=marker, lag=ROSTER_SAFETY_LAG_SECONDS)


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
    A post-marker ``prepared`` intent settles only through ``no_dispatch`` too: its own
    applicant roster is complete without our account after the safety lag.
    """
    request_id = str(value.get("request_id") or "")
    if request_id and (request_id in applied or request_id in closed):
        return True
    if value.get("state") == "confirmed" or fence.is_pre_effect(value):
        return True
    if value.get("state") == "prepared" and value.get("effect_phase") == fence.IRREVERSIBLE_ATTEMPT_STARTED:
        return no_dispatch(value)
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
        if value.get("state") == "prepared":
            # "present" is a landed, unconfirmed application with no ledger row: it must
            # stay unresolved here, or the store proof would close owner fences as effect 0.
            return _roster_settles_attempt(value, intent_root, apply_root or APPLY_ROOT, rows) == "absent"
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


def _released_fenced_occurrences(owner_id: str) -> list[str]:
    _root, _owners, _tickets, database = resource_admission._durable_paths()
    import sqlite3
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=30) as connection:
        rows = connection.execute(
            "SELECT occurrence_id FROM occurrences WHERE owner_id=? AND effect_unknown=1"
            " AND state='released' ORDER BY queued_at", (owner_id,)).fetchall()
    return [row[0] for row in rows]


def _owner_has_claimed_occurrence(owner_id: str) -> bool:
    _root, _owners, _tickets, database = resource_admission._durable_paths()
    import sqlite3
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=30) as connection:
        return connection.execute(
            "SELECT EXISTS(SELECT 1 FROM occurrences WHERE owner_id=? AND state='claimed')",
            (owner_id,)).fetchone()[0] == 1


def _run_started_unix(run_id: object) -> float | None:
    """lm-loop run ids start with the wake time in hex nanoseconds."""
    try:
        return int(str(run_id).rsplit(":", 1)[-1].split("-", 1)[0], 16) / 1e9
    except ValueError:
        return None


def _scoped_settled_scan(intent_root: Path, occurrence_id: str, since: float) -> dict[str, object]:
    """Settle only the intents this occurrence's own runs could have written.

    Every attempt writes an intent bound to its ``runtime_occurrence_id`` before the
    irreversible marker. Any intent its runs wrote is therefore newer than ``since``
    (by run id or, unbound/unreadable, by file mtime). Such an intent counts unless it
    is bound to another occurrence (that occurrence's fence owns it) or is this
    occurrence's own intent with a provider-settled state.
    """
    applied, closed = _roster_ids(_latest_roster()), _closed_ids(CLOSED_READBACK)
    rows = _closed_rows(CLOSED_READBACK)

    def no_dispatch(value: dict) -> bool:
        if value.get("state") == "prepared":
            return _roster_settles_attempt(value, intent_root, APPLY_ROOT, rows) == "absent"
        return _roster_proves_no_dispatch(value, intent_root, APPLY_ROOT, rows)

    digest = hashlib.sha256()
    scanned = unresolved = own = 0
    for path, value in _store_intents(intent_root):
        bound = value.get("runtime_occurrence_id") if value else None
        # A claimer may predate the occurrence it claims, so its own intents count at any age.
        if bound != occurrence_id:
            started = _run_started_unix(value.get("runtime_run_id")) if value else None
            if (started if started is not None else path.stat().st_mtime) < since:
                continue
        else:
            own += 1
        scanned += 1
        # An unbound intent may be this occurrence's own, so it must be settled by the same rule
        # the store-wide proof uses (confirmed, pre-effect, or retired before the marker).
        settled = value is not None and (
            (bool(bound) and bound != occurrence_id)
            or _intent_settled(value, applied, closed, no_dispatch))
        if not settled:
            unresolved += 1
        digest.update(f"{path.name}\0{bound}\0{settled}\n".encode("utf-8"))
    return {"scanned_intents": scanned, "unresolved_irreversible": unresolved,
            "occurrence_bound_intents": own, "scope_since_unix": since,
            "evidence_ref": f"gig-intents://sha256/{digest.hexdigest()}"}


def _resolve_settled(owner_id, occurrence_id, *, settled_proof, expected_state="claimed"):
    return resource_admission.resolve_settled_write_ahead_occurrence(
        owner_id, occurrence_id, settled_proof=settled_proof, expected_state=expected_state)


def _needs_roster_readback(intent_root: Path) -> bool:
    """Read the official roster only for post-marker intents a roster can settle: retired
    before any click, or still prepared with the account captured before the marker."""
    return any(value is not None
               and value.get("effect_phase") == fence.IRREVERSIBLE_ATTEMPT_STARTED
               and ((value.get("state") == "retired_absent"
                     and _pre_dispatch_abort_archive(value, intent_root) is not None)
                    or (value.get("state") == "prepared"
                        and _identity_account(value, APPLY_ROOT) is not None))
               for _path, value in _store_intents(intent_root))


def _close_settled_fences(owner_id: str, intent_root: Path, runner=None) -> tuple[dict[str, object], list[dict]]:
    scan = _settled_scan(intent_root)
    if scan["scanned_intents"] and scan["unresolved_irreversible"]:
        # The per-occurrence proof needs no browser; serve it before the roster readback.
        scoped = _close_scoped_fences(owner_id, intent_root)
        if scoped:
            return scan, scoped
    if scan["unresolved_irreversible"] and _needs_roster_readback(intent_root):
        exit_code = run_browser_reconcile(["bash", str(WITH_BROWSER), BROWSER_IDENTITY, "--",
                                           sys.executable, str(CLOSED_READBACK_SCRIPT)], runner=runner)
        scan = {**_settled_scan(intent_root), "roster_readback_exit_code": exit_code}
    if scan["scanned_intents"] == 0 or scan["unresolved_irreversible"] != 0:
        return scan, _close_scoped_fences(owner_id, intent_root)
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


def _close_scoped_fences(owner_id: str, intent_root: Path) -> list[dict]:
    """Close each fenced occurrence whose own possible intents are all run-bound and settled.

    Claimed fences go first: the admission resolver refuses a claimed close while any owner
    process is live, so a stale claim left by a finished run (2026-10-23
    18e109c520f9ace8-50348: exit 0, no intent) is the only kind it releases.
    """
    closed = []

    def close(occurrence_id: str, state: str) -> None:
        since = _run_started_unix(occurrence_id)
        if since is None:
            return
        precheck = _scoped_settled_scan(intent_root, occurrence_id, since)
        if precheck["scanned_intents"] == 0 or precheck["unresolved_irreversible"] != 0:
            return
        checked: dict[str, object] = {}

        def proof():
            checked.update(_scoped_settled_scan(intent_root, occurrence_id, since))
            return {"owner_id": owner_id, "occurrence_id": occurrence_id, "verified": True,
                    "proof_type": "write_ahead_store_settled.v1", **checked}
        if _resolve_settled(owner_id, occurrence_id, settled_proof=proof, expected_state=state):
            closed.append({"owner_id": owner_id, "occurrence_id": occurrence_id, "verified": True,
                           "proof_type": "write_ahead_store_settled.v1",
                           "scope_since_unix": since,
                           "evidence_ref": checked.get("evidence_ref", precheck["evidence_ref"])})

    for occurrence_id in _fenced_occurrences(owner_id):
        close(occurrence_id, "claimed")
    if _owner_has_claimed_occurrence(owner_id):
        # A live claim may be writing intents right now (intents use per-request locks, not
        # the admission control lock); released fences rely on this idle check.
        return closed
    for occurrence_id in _released_fenced_occurrences(owner_id):
        close(occurrence_id, "released")
    return closed


def _close_closed_batch(owner_id: str, occurrence_id: str, runtime_run_id: str,
                        request_ids: Sequence[str], intent_root: Path, *,
                        runner=None, resolver=None) -> dict[str, object] | None:
    """Close the exact occurrence when every bound, unconfirmed request's own official page,
    read after its marker, is 募集終了/gone: no further application to it is possible.

    Per-request pages instead of the full applied-history walk, which Coconala answers
    with 403 after a few pages (hf-gig-apply-direct:18dea9ef6158f5b0-37135). A request that
    is still open counts only when its complete roster, read after its marker + safety lag,
    lacks our account; such a closed + absent batch closes through its own per-request proof
    (hf-gig-apply-direct:18df80f03ec86a98-74517). None means "not proven" and the caller
    falls back to the roster batch, then the history walk.
    """
    try:
        bound = reconciler._require_complete_request_set(
            intent_root, occurrence_id=occurrence_id, runtime_run_id=runtime_run_id,
            request_ids=list(request_ids))
    except reconciler.ReconcileContractError:
        return None
    unconfirmed = sorted((value for value in bound if value.get("state") != "confirmed"),
                         key=lambda value: str(value["request_id"]))
    pending = [str(value["request_id"]) for value in unconfirmed]
    if not pending:
        return None
    path = reconciler._default_evidence_dir(occurrence_id) / "request-closed-readback.json"
    command = ["bash", str(WITH_BROWSER), BROWSER_IDENTITY, "--", sys.executable,
               str(CLOSED_READBACK_SCRIPT), "--intent-root", str(intent_root), "--result", str(path)]
    for request_id in pending:
        command.extend(["--request-id", request_id])
    if run_browser_reconcile(command, runner=runner) != 0:
        return None
    rows, closed = _closed_rows(path), _closed_ids(path)
    urls, kinds = [], {}
    for value, request_id in zip(unconfirmed, pending):
        row, url = rows.get(request_id) or {}, f"https://coconala.com/requests/{request_id}"
        try:
            after_marker = (datetime.fromisoformat(str(row.get("observed_at"))).timestamp()
                            > (Path(intent_root) / f"{request_id}.json").stat().st_mtime)
        except (OSError, ValueError, TypeError):
            return None
        if request_id in closed and row.get("url") == url and row.get("final_url") == url and after_marker:
            kinds[request_id] = "closed"
        elif _roster_settles_attempt(value, intent_root, APPLY_ROOT, rows) == "absent":
            kinds[request_id] = "roster_absent"
        else:
            return None
        urls.append(url)
    if "roster_absent" in kinds.values():
        # All-absent stays with _close_roster_batch's historical no-dispatch sibling.
        if "closed" not in kinds.values():
            return None
        return _close_closed_or_absent_batch(owner_id, occurrence_id, runtime_run_id,
                                             unconfirmed, kinds, intent_root, path)
    # The earlier click may still have applied, so the effect stays "unknown", never 0.
    proof = {"owner_id": owner_id, "occurrence_id": occurrence_id, "runtime_run_id": runtime_run_id,
             "request_ids": pending, "verified": True, "provider": "coconala",
             "proof_type": resource_admission.REQUEST_CLOSED_PROOF_TYPE,
             "effect": "unknown", "reason": "duplicate_impossible_request_closed",
             "provider_receipt_id": ",".join(urls), "evidence_ref": str(path.resolve())}
    closed_now = (resolver or resource_admission.resolve_request_closed_occurrence)(
        owner_id, occurrence_id, closed_proof=lambda: proof, expected_state="claimed")
    return {"status": "reconciled" if closed_now is True else "unresolved",
            "reason": "duplicate_impossible_request_closed" if closed_now is True
            else "occurrence_not_current_or_already_closed",
            "retryable": False, "effect": "unknown", "readback": 1, "occurrence_id": occurrence_id,
            "request_ids": pending, "provider_receipt_id": proof["provider_receipt_id"],
            "evidence_ref": proof["evidence_ref"]}


def _retire_absent_intents(store, absent: Sequence[dict], evidence_ref: str) -> dict | None:
    """Retire each roster-absent prepared intent under its lock + CAS once its fence is closed."""
    try:
        for value in absent:
            rid = value["request_id"]
            with store.locked(rid):
                current = store._read_locked(rid)
                if current is None:
                    raise fence.IntentFenceError("intent_missing_after_resolution")
                if current["state"] == fence.PREPARED and current["cas"] == value["cas"]:
                    store.retire_prepared_locked(
                        rid, expected_cas=value["cas"],
                        reason="official_roster_account_absent_no_dispatch_confirmed:" + evidence_ref)
                elif current["state"] != fence.RETIRED_ABSENT:
                    raise fence.IntentFenceError("intent_state_changed_after_resolution")
    except Exception as error:
        return {"status": "unresolved", "reason": "intent_retire_failed",
                "error_class": type(error).__name__, "error_detail": str(error)[:240],
                "next_action": "inspect the durable intent archive; the provider fence is closed"}
    return None


def _close_closed_or_absent_batch(owner_id: str, occurrence_id: str, runtime_run_id: str,
                                  unconfirmed: Sequence[dict], kinds: Mapping[str, str],
                                  intent_root: Path, path: Path) -> dict[str, object]:
    """Close the exact occurrence when each unconfirmed request is closed or roster-absent.

    A closed request may still hold our application, so the effect stays "unknown".
    Absent intents are retired like the historical sibling; closed ones stay prepared.
    """
    evidence_ref = str(path.resolve())
    requests = {}
    for value in unconfirmed:
        rid = str(value["request_id"])
        requests[rid] = {"kind": kinds[rid], "official_url": f"https://coconala.com/requests/{rid}"}
        if kinds[rid] == "roster_absent":
            requests[rid]["account_id"] = _identity_account(value, APPLY_ROOT)
    ids = sorted(requests)
    proof = {"owner_id": owner_id, "occurrence_id": occurrence_id, "runtime_run_id": runtime_run_id,
             "request_ids": ids, "verified": True, "provider": "coconala",
             "proof_type": resource_admission.REQUEST_CLOSED_OR_ROSTER_ABSENT_PROOF_TYPE,
             "effect": "unknown", "reason": "duplicate_impossible_request_closed_or_roster_absent",
             "provider_receipt_id": ",".join(requests[rid]["official_url"] for rid in ids),
             "evidence_ref": evidence_ref, "requests": requests}
    base = {"retryable": False, "effect": "unknown", "readback": 1, "occurrence_id": occurrence_id,
            "request_ids": ids, "closed_request_ids": [rid for rid in ids if kinds[rid] == "closed"],
            "no_dispatch_request_ids": [rid for rid in ids if kinds[rid] == "roster_absent"],
            "requests": requests, "provider_receipt_id": proof["provider_receipt_id"],
            "evidence_ref": evidence_ref}
    closed_now = resource_admission.resolve_request_closed_or_roster_absent_occurrence(
        owner_id, occurrence_id, mixed_proof=lambda: proof, expected_state="claimed")
    if closed_now is not True:
        return {**base, "status": "unresolved", "reason": "occurrence_not_current_or_already_closed"}
    failure = _retire_absent_intents(
        fence.IntentStore(intent_root),
        [value for value in unconfirmed if kinds[str(value["request_id"])] == "roster_absent"],
        evidence_ref)
    if failure is not None:
        return {**base, **failure}
    return {**base, "status": "reconciled", "reason": "duplicate_impossible_request_closed_or_roster_absent"}


def _applied_detail(value: dict, apply_root: Path) -> dict | None:
    """The request detail the commit pass judged, bound to the intent by its snapshot hash.

    The worker hashes a sub-snapshot of its pass snapshot under its own lease fence; only the
    pass snapshot that recomputes the intent's exact ``snapshot_sha256`` is accepted.
    """
    match = _commit_task(value)
    if match is None:
        return None
    parent = reconciler.parent
    for path in sorted((apply_root / match.group(2)).glob("*/application-snapshot.json")):
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            details = [row for row in snapshot.get("request_details") or []
                       if isinstance(row, dict) and str(row.get("request_id")) == value["request_id"]]
            if len(details) == 1 and parent._planner_subsnapshot(
                    {**snapshot, "lease_fence": value["lease_fence"]}, details
            )["snapshot_sha256"] == value.get("snapshot_sha256"):
                return details[0]
        except Exception:
            continue
    return None


def _append_applied_ledger(value: dict, detail: dict, readback_path: Path) -> None:
    """The parent's own idempotent ledger writer, fed the exact detail the pass judged."""
    parent = reconciler.parent
    effects = parent.CdpParentEffects(
        ws_url="ws://roster-reconcile/devtools/page/none", evidence_dir=readback_path.parent,
        ledger_path=LEDGER_PATH, pass_id=_commit_task(value).group(1))
    effects._fresh_details[value["request_id"]] = detail
    effects._readback_paths[value["request_id"]] = readback_path
    effects.canonical_ledger_append(parent._application_row_from_intent(detail, value))


def _close_roster_batch(owner_id: str, occurrence_id: str, runtime_run_id: str,
                        request_ids: Sequence[str], intent_root: Path) -> dict[str, object] | None:
    """Close the exact occurrence from each prepared request's official applicant roster.

    Reads the per-request readback ``_close_closed_batch`` just wrote (no second browser).
    Our account listed: the click applied, so write the ledger row, confirm the intent and
    close through the provider-confirmed resolver. Complete without it and read after the
    marker + safety lag: no application, so close this occurrence with the account-bound
    no-dispatch proof and retire the intent, as the historical sibling does. Anything else is
    None and the fence stays; in such a mixed batch the listed requests are still ledgered and
    confirmed, so a later wake sees only the unproven ones. A closed + absent batch is closed
    by ``_close_closed_batch``, which owns this wake's exit-0 readback.
    """
    try:
        bound = reconciler._require_complete_request_set(
            intent_root, occurrence_id=occurrence_id, runtime_run_id=runtime_run_id,
            request_ids=list(request_ids))
    except reconciler.ReconcileContractError:
        return None
    pending = [value for value in bound if value.get("state") != "confirmed"]
    if not pending:
        return None
    path = reconciler._default_evidence_dir(occurrence_id) / "request-closed-readback.json"
    rows = _closed_rows(path)
    verdicts = {str(value["request_id"]): _roster_settles_attempt(value, intent_root, APPLY_ROOT, rows)
                for value in pending}
    present = [value for value in pending if verdicts[str(value["request_id"])] == "present"]
    absent = [value for value in pending if verdicts[str(value["request_id"])] == "absent"]
    accounts = {_identity_account(value, APPLY_ROOT) for value in absent}
    if len(accounts) > 1:
        return None
    evidence_ref = str(path.resolve())
    base = {"retryable": False, "occurrence_id": occurrence_id, "request_ids": sorted(verdicts),
            "applied_request_ids": sorted(str(value["request_id"]) for value in present),
            "no_dispatch_request_ids": sorted(str(value["request_id"]) for value in absent),
            "effect": len(bound) - len(absent), "readback": 1, "evidence_ref": evidence_ref}
    details = {str(value["request_id"]): _applied_detail(value, APPLY_ROOT) for value in present}
    if None in details.values():
        return {**base, "status": "unresolved", "reason": "ledger_detail_unavailable",
                "next_action": "restore the commit pass snapshot; keep the fence closed"}
    store = fence.IntentStore(intent_root)
    try:
        for value in present:
            # Ledger first, as the parent does: CONFIRMED must never exist without its row.
            _append_applied_ledger(value, details[str(value["request_id"])], path)
            store.confirm(value["request_id"], expected_cas=value["cas"])
    except Exception as error:
        return {**base, "status": "unresolved", "reason": "intent_confirmation_failed",
                "retryable": True, "error_class": type(error).__name__,
                "error_detail": str(error)[:240]}
    if None in verdicts.values():
        # Mixed batch: landed applications are confirmed and ledgered above, so the next
        # wake's pending set holds only the unproven requests. This occurrence stays fenced.
        return None
    if absent:
        account = next(iter(accounts))
        proof = {"verified": True, "proof_type": "historical_account_bound_no_dispatch",
                 "owner_id": owner_id, "occurrence_id": occurrence_id,
                 "runtime_run_id": runtime_run_id, "provider": "coconala",
                 "request_ids": base["no_dispatch_request_ids"],
                 "applied_request_ids": base["applied_request_ids"],
                 "historical_account_id": account,
                 "historical_profile_url": f"https://coconala.com/users/{account}",
                 "evidence_ref": evidence_ref,
                 "target_roster": {str(value["request_id"]): {
                     "official_url": f"https://coconala.com/requests/{value['request_id']}",
                     "applicants_count": rows[str(value["request_id"])]["applicants_count"],
                     "contracted_count": 0, "historical_account_absent": True}
                     for value in absent}}
        closed_now = resource_admission.resolve_historical_no_dispatch_occurrence(
            owner_id, occurrence_id, no_dispatch_proof=lambda: proof, expected_state="claimed")
        if closed_now is not True:
            return {**base, "status": "unresolved", "reason": "occurrence_not_current_or_already_closed"}
        failure = _retire_absent_intents(store, absent, evidence_ref)
        if failure is not None:
            return {**base, **failure}
        return {**base, "status": "reconciled", "reason": "official_roster_account_absent",
                "historical_account_id": account}
    urls = [f"https://coconala.com/requests/{value['request_id']}" for value in present]
    proof = {"owner_id": owner_id, "occurrence_id": occurrence_id,
             "runtime_run_id": runtime_run_id, "request_ids": base["applied_request_ids"],
             "verified": True, "provider": "coconala",
             "proof_type": "provider_official_readback_exact_request_batch",
             "source": "official_request_applicant_roster",
             "provider_receipt_id": ",".join(urls), "evidence_ref": evidence_ref}
    closed_now = resource_admission.resolve_unknown_occurrence(
        owner_id, occurrence_id, official_readback=lambda: proof, expected_state="claimed")
    return {**base, "provider_receipt_id": proof["provider_receipt_id"],
            "status": "reconciled" if closed_now is True else "unresolved",
            "reason": "official_roster_account_present" if closed_now is True
            else "occurrence_not_current_or_already_closed"}


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
    closed_batch = _close_closed_batch(args.owner_id, occurrence_id, runtime_run_id,
                                       request_ids, args.intent_root, runner=runner)
    if closed_batch is not None:
        _write_scan_result(_scan_result_path(args.result), closed_batch)
        return 0
    roster_batch = _close_roster_batch(args.owner_id, occurrence_id, runtime_run_id,
                                       request_ids, args.intent_root)
    if roster_batch is not None:
        _write_scan_result(_scan_result_path(args.result), roster_batch)
        return 0
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
