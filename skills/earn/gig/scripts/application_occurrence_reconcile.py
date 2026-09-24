#!/usr/bin/env python3
"""Reconcile one Coconala application fence without retrying the submission.

This command owns only the recovery boundary for an already fenced application.  It
opens a separate leased browser context, reads Coconala's official applied history,
and closes the admission occurrence only when the exact request ID is present.  A
403, partial history, missing ID, or any other inconclusive result leaves the fence
untouched.  The command never opens an application form and never clicks submit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[3]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import application_parent as parent
from runtime.host import resource_admission


OWNER_ID = "hf-gig-apply-direct"
_REQUEST_ID = re.compile(r"(?:[0-9]+|[0-7][0-9A-HJKMNP-TV-Z]{25})\Z")
_OCCURRENCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


class ReconcileContractError(ValueError):
    """The provider evidence cannot safely prove the exact fenced effect."""


def _atomic_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_intent(intent_root: Path, request_id: str) -> dict[str, object]:
    if not _REQUEST_ID.fullmatch(request_id):
        raise ReconcileContractError("request_id_invalid")
    path = Path(intent_root) / f"{request_id}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReconcileContractError("intent_unreadable") from error
    if not isinstance(value, dict):
        raise ReconcileContractError("intent_invalid")
    if value.get("state") != "prepared" or value.get("effect_phase") != "irreversible_attempt_started":
        raise ReconcileContractError("intent_not_effect_started")
    if str(value.get("request_id") or "") != request_id:
        raise ReconcileContractError("intent_request_id_mismatch")
    if not isinstance(value.get("cas"), str) or not value["cas"].strip():
        raise ReconcileContractError("intent_cas_missing")
    return value


def build_provider_proof(
    *,
    owner_id: str,
    occurrence_id: str,
    request_id: str,
    readback: Mapping[str, object],
    evidence_path: Path,
) -> dict[str, object]:
    """Bind a positive official readback to the exact owner/occurrence/request."""
    if not isinstance(readback, Mapping):
        raise ReconcileContractError("official_readback_invalid")
    if readback.get("source") != "code_owned_cdp_readback":
        raise ReconcileContractError("official_readback_source_invalid")
    if readback.get("observed") is not True or readback.get("not_found") is not False:
        raise ReconcileContractError("official_readback_not_verified")
    if readback.get("access_denied") is True:
        raise ReconcileContractError("official_readback_access_denied")
    ids = readback.get("request_ids")
    if not isinstance(ids, list) or request_id not in {str(value) for value in ids}:
        raise ReconcileContractError("exact_id_not_observed")
    pages_walked = readback.get("pages_walked")
    if isinstance(pages_walked, bool) or not isinstance(pages_walked, int) or pages_walked < 1:
        raise ReconcileContractError("official_readback_pages_missing")
    urls = readback.get("urls")
    if not isinstance(urls, list) or not urls or not all(isinstance(url, str) and url for url in urls):
        raise ReconcileContractError("official_readback_urls_missing")
    return {
        "verified": True,
        "proof_type": "provider_official_readback_exact_id",
        "owner_id": owner_id,
        "occurrence_id": occurrence_id,
        "request_id": request_id,
        "provider": "coconala",
        "provider_receipt_id": (
            "https://coconala.com/mypage/job_matching/applied/offers"
            f"#request-{request_id}"
        ),
        "evidence_ref": str(Path(evidence_path).resolve()),
        "official_readback": dict(readback),
    }


def reconcile_occurrence(
    *,
    owner_id: str,
    occurrence_id: str,
    request_id: str,
    intent_root: Path,
    evidence_path: Path,
    readback: Callable[[], Mapping[str, object]],
    resolver: Callable[..., bool] = resource_admission.resolve_unknown_occurrence,
) -> dict[str, object]:
    """Read, prove, and atomically resolve one effect-unknown occurrence."""
    if owner_id != OWNER_ID:
        raise ReconcileContractError("owner_not_allowlisted")
    if not _OCCURRENCE_ID.fullmatch(occurrence_id):
        raise ReconcileContractError("occurrence_id_invalid")
    try:
        intent = _load_intent(Path(intent_root), request_id)
    except ReconcileContractError as error:
        return {
            "status": "unresolved",
            "reason": str(error),
            "retryable": False,
            "request_id": request_id,
            "occurrence_id": occurrence_id,
            "effect": 0,
            "readback": 0,
        }
    try:
        raw_readback = readback()
    except Exception as error:
        detail = str(error)[:240]
        reason = detail if re.fullmatch(r"official_readback_[a-z_]+", detail) else "official_readback_failed"
        return {
            "status": "unresolved",
            "reason": reason,
            "error_class": type(error).__name__,
            "error_detail": detail,
            "retryable": True,
            "next_action": "obtain a fresh official Coconala readback; keep the effect fence closed",
            "request_id": request_id,
            "occurrence_id": occurrence_id,
            "effect": 0,
            "readback": 0,
        }
    try:
        proof = build_provider_proof(
            owner_id=owner_id,
            occurrence_id=occurrence_id,
            request_id=request_id,
            readback=raw_readback,
            evidence_path=evidence_path,
        )
    except ReconcileContractError as error:
        return {
            "status": "unresolved",
            "reason": str(error),
            "retryable": True,
            "request_id": request_id,
            "occurrence_id": occurrence_id,
            "effect": 0,
            "readback": 0,
        }
    try:
        closed = resolver(
            owner_id,
            occurrence_id,
            official_readback=lambda: proof,
            expected_state="claimed",
        )
    except Exception as error:
        return {
            "status": "unresolved",
            "reason": "admission_resolver_failed",
            "error_class": type(error).__name__,
            "error_detail": str(error)[:240],
            "retryable": True,
            "next_action": "inspect the admission boundary before any retry",
            "request_id": request_id,
            "occurrence_id": occurrence_id,
            "effect": 0,
            "readback": 1,
        }
    if closed is not True:
        return {
            "status": "unresolved",
            "reason": "occurrence_not_current_or_already_closed",
            "retryable": False,
            "request_id": request_id,
            "occurrence_id": occurrence_id,
            "effect": 1,
            "readback": 1,
        }
    return {
        "status": "resolved",
        "reason": "exact_provider_readback_confirmed",
        "retryable": False,
        "request_id": request_id,
        "occurrence_id": occurrence_id,
        "intent_cas": str(intent["cas"]),
        "provider_receipt_id": proof["provider_receipt_id"],
        "evidence_ref": proof["evidence_ref"],
        "effect": 1,
        "readback": 1,
    }


def _default_evidence_dir(occurrence_id: str) -> Path:
    digest = hashlib.sha256(occurrence_id.encode("utf-8")).hexdigest()[:16]
    return Path.home() / "gig" / "apply-direct" / "evidence" / f"occurrence-reconcile-{digest}"


def select_single_target(
    *,
    unknown_occurrences: list[str],
    uncertain_request_ids: list[str],
) -> tuple[str, str] | None:
    """Select a target only when the durable occurrence-to-intent mapping is 1:1."""
    occurrences = sorted({str(value) for value in unknown_occurrences if _OCCURRENCE_ID.fullmatch(str(value))})
    requests = sorted({str(value) for value in uncertain_request_ids if _REQUEST_ID.fullmatch(str(value))})
    if len(occurrences) != 1 or len(requests) != 1:
        return None
    return occurrences[0], requests[0]


def discover_single_target(*, owner_id: str, intent_root: Path) -> tuple[str, str] | None:
    """Read admission state and intent state without changing either store."""
    if owner_id != OWNER_ID:
        raise ReconcileContractError("owner_not_allowlisted")
    _root, _owners, _tickets, database = resource_admission._durable_paths()
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=5)
    except (OSError, sqlite3.Error) as error:
        raise ReconcileContractError("admission_database_unreadable") from error
    try:
        rows = connection.execute(
            """SELECT occurrence_id FROM occurrences
               WHERE owner_id=? AND state='claimed' AND effect_unknown=1""",
            (owner_id,),
        ).fetchall()
    except sqlite3.Error as error:
        raise ReconcileContractError("admission_occurrences_unreadable") from error
    finally:
        connection.close()
    uncertain: list[str] = []
    for path in sorted(Path(intent_root).glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            isinstance(value, dict)
            and value.get("state") == "prepared"
            and value.get("effect_phase") == "irreversible_attempt_started"
            and _REQUEST_ID.fullmatch(str(value.get("request_id") or ""))
        ):
            uncertain.append(str(value["request_id"]))
    return select_single_target(
        unknown_occurrences=[str(row[0]) for row in rows],
        uncertain_request_ids=uncertain,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--occurrence-id")
    parser.add_argument("--request-id")
    parser.add_argument(
        "--discover",
        action="store_true",
        help="select exactly one unknown occurrence and one effect-started intent; otherwise do nothing",
    )
    parser.add_argument("--owner-id", default=OWNER_ID)
    parser.add_argument("--intent-root", type=Path, default=Path.home() / "gig" / "application-intents")
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--lease-script", type=Path, default=SCRIPT_DIR.parents[2] / "browser" / "scripts" / "cdp_context_lease.py")
    parser.add_argument("--lease-task")
    parser.add_argument("--max-pages", type=int, default=1000)
    args = parser.parse_args(argv)
    if args.max_pages < 1:
        parser.error("--max-pages must be positive")
    if args.discover and (args.occurrence_id or args.request_id):
        parser.error("--discover cannot be combined with explicit target arguments")
    if not args.discover and (not args.occurrence_id or not args.request_id):
        parser.error("explicit mode requires --occurrence-id and --request-id")
    if args.discover:
        try:
            target = discover_single_target(owner_id=args.owner_id, intent_root=args.intent_root)
        except ReconcileContractError as error:
            result = {
                "status": "unresolved",
                "reason": str(error),
                "retryable": True,
                "effect": 0,
                "readback": 0,
                "next_action": "read admission and intent stores again; do not release or retry",
            }
            result_path = args.result or Path.home() / "gig" / "apply-direct" / "evidence" / "occurrence-reconcile-scan.json"
            _atomic_json(result_path, result)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            return 0
        if target is None:
            result = {
                "status": "nothing_to_reconcile",
                "reason": "one_to_one_occurrence_intent_mapping_not_present",
                "retryable": False,
                "effect": 0,
                "readback": 0,
                "next_action": "wait for a new exact occurrence-to-intent mapping",
            }
            result_path = args.result or Path.home() / "gig" / "apply-direct" / "evidence" / "occurrence-reconcile-scan.json"
            _atomic_json(result_path, result)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            return 0
        args.occurrence_id, args.request_id = target
    evidence_dir = args.evidence_dir or _default_evidence_dir(args.occurrence_id)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"official-readback-{args.request_id}.json"
    result_path = args.result or evidence_dir / "reconcile-result.json"
    task_suffix = hashlib.sha256(args.occurrence_id.encode("utf-8")).hexdigest()[:16]
    lease_task = args.lease_task or f"gig-apply-reconcile-{task_suffix}"

    try:
        # Validate the durable fence before opening a browser context.
        _load_intent(args.intent_root, args.request_id)
        with parent.LeaseHandle(lease_script=args.lease_script, task=lease_task) as lease:
            effects = parent.CdpParentEffects(
                ws_url=lease.ws_url,
                evidence_dir=evidence_dir,
                ledger_path=Path.home() / "gig" / "applied.jsonl",
                pass_id=f"occurrence-reconcile-{task_suffix}",
            )
            effects.ws_recycler = lease.recycle

            def official_readback() -> Mapping[str, object]:
                effects._official_readback(
                    {args.request_id},
                    evidence_path,
                    max_pages=args.max_pages,
                    allow_truncated=False,
                )
                value = json.loads(evidence_path.read_text(encoding="utf-8"))
                if not isinstance(value, dict):
                    raise ReconcileContractError("official_readback_artifact_invalid")
                return value

            result = reconcile_occurrence(
                owner_id=args.owner_id,
                occurrence_id=args.occurrence_id,
                request_id=args.request_id,
                intent_root=args.intent_root,
                evidence_path=evidence_path,
                readback=official_readback,
            )
    except ReconcileContractError as error:
        result = {
            "status": "unresolved",
            "reason": str(error),
            "retryable": False,
            "request_id": args.request_id,
            "occurrence_id": args.occurrence_id,
            "effect": 0,
            "readback": 0,
        }
    except Exception as error:
        result = {
            "status": "unresolved",
            "reason": "reconciler_runtime_failed",
            "error_class": type(error).__name__,
            "error_detail": str(error)[:240],
            "retryable": True,
            "next_action": "inspect the structured error and retry only with a new observation",
            "request_id": args.request_id,
            "occurrence_id": args.occurrence_id,
            "effect": 0,
            "readback": 0,
        }
    _atomic_json(result_path, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
