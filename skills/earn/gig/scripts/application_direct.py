#!/usr/bin/env python3
"""Run the direct Coconala Apply boundary on each scheduled wake."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from b2_result_gate import (
    ContractError as CursorContractError,
    _valid_request_id as _valid_b2_request_id,
    next_required_source_cursor,
    next_search_cursor,
)
from b2_search_objective import checkpoint, finish, wake_plan
from application_snapshot import SnapshotContractError, canonical_request_url
from evidence_gc import register_live_evidence_pin
from telegram_outbox import TelegramOutbox, dispatch_one
from apply_telegram_report import ApplyTelegramTransport
from gig_paths import BROWSER_DIR, RUNNER_DIR
from gig_release import pin_release_for_process
from operator_brake import status as shared_operator_brake_status


HERE = Path(__file__).resolve().parent
GIG_ROOT = HERE.parent
DEFAULT_PREP = GIG_ROOT / "passprep.py"
DEFAULT_GATE = HERE / "b2_result_gate.py"
DEFAULT_PARENT = HERE / "application_parent.py"
DEFAULT_POSTING_SOURCE = HERE / "posting_source.py"
DEFAULT_OPERATOR_BRAKE = HERE / "gig_brake.sh"
DEFAULT_RUNNER = RUNNER_DIR / "agent_runner.py"
DEFAULT_TELEGRAM_DATABASE = Path.home() / "gig" / "telegram-outbox.sqlite3"
DEFAULT_TELEGRAM_TARGET = os.environ.get("GIG_REPORT_CHAT", "")
DEFAULT_TELEGRAM_RECEIPT_DIR = Path.home() / "gig" / "telegram-delivery-receipts"
SAME_WAKE_RECONCILE_DELAY_SECONDS = 60
CONFIRMED = frozenset(("confirmed", "recovered_prepared_confirmed", "reconciled_confirmed"))
ALREADY_APPLIED_STATUSES = frozenset(("dedupe_already_applied",))
EFFECT_STATUSES = CONFIRMED | {"confirmed_unverified"}
FAILED_STATUSES = frozenset(("prepared_unconfirmed",))
FAILED_PREFIXES = (
    "submission_runtime_failed", "submission_failed", "readback_inconclusive",
    "pre_submit_aborted", "form_readback_mismatch", "stale_snapshot",
    "quarantined_wedging_form",
)
PENDING_PREFIXES = ("awaiting_", "prepared", "confirmed_unverified", "crash_injected", "cap_reached")
# A CDP call that ran out of time says the browser hiccupped on one listing, not that the listing
# was judged. Classifying it as a plain failure stopped the whole wake from scanning deeper, so one
# slow page cost every listing behind it.
TRANSIENT_REASON_MARKERS = ("_timeout_after_", "cdp_disconnected", "target_closed")
SUBMIT_REQUIRED = "submit_required"
HARD_PROHIBITED = "hard_prohibited"
DUPLICATE_FENCED = "duplicate_fenced"
OFFICIALLY_UNSUBMITTABLE = "officially_unsubmittable"
DIRECT_MAX_APPLICATIONS = 20


def _official_open_scan_prep(prep: dict[str, Any]) -> dict[str, Any]:
    """Keep pass metadata, but retire legacy category/budget filtering for Direct Apply."""
    thresholds = dict(prep.get("apply_skip_thresholds") or {})
    # Dais 2026-08-18: drop all three gates — competition is not a reason to skip and a ¥500 job is
    # worth taking. Budget was already zeroed here. The other two turned out to be dead settings:
    # `passprep.py` defines max_applicants and min_contracted_to_skip, and grepping both this tree
    # and the running release finds no reader for either. Zeroing them is therefore a statement of
    # intent, not a behaviour change — the applications those two were blamed for were never
    # actually filtered by them. Anything that starts reading these later must treat 0 as "no gate".
    thresholds["min_budget_jpy"] = 0
    thresholds["max_applicants"] = 0
    thresholds["min_contracted_to_skip"] = 0
    return {
        **prep,
        # One continuous opportunity shares the existing 20-attempt Apply budget;
        # it is not a separate lane or scheduler.
        "target_apply_per_pass": DIRECT_MAX_APPLICATIONS - 1,
        "target_retainer_apply_per_pass": 1,
        "max_apply_per_pass": DIRECT_MAX_APPLICATIONS,
        "category_order": [],
        "apply_skip_thresholds": thresholds,
        "active_strategy_experiment": None,
    }


def _decision_business_class(decision: dict[str, Any]) -> str | None:
    """Read the new planner class, with legacy vocabulary only for old evidence."""
    value = decision.get("business_class")
    if value in {SUBMIT_REQUIRED, HARD_PROHIBITED, DUPLICATE_FENCED, OFFICIALLY_UNSUBMITTABLE}:
        return value
    # Historical report fixtures may still carry the retired binary field. This adapter
    # does not feed the planner or commit boundary; it only keeps old evidence readable.
    if value is None and decision.get("eligibility") == "eligible":
        return SUBMIT_REQUIRED
    if value is None and decision.get("eligibility") == "ineligible":
        return None
    return None
def _status_rank(status: str) -> int:
    if status in CONFIRMED:
        return 50
    if status in ALREADY_APPLIED_STATUSES:
        return 45
    if status.startswith(FAILED_PREFIXES):
        return 40
    if status in FAILED_STATUSES:
        return 35
    if status.startswith(PENDING_PREFIXES):
        return 20
    if status in {HARD_PROHIBITED, ""}:
        return 10
    return 30


def _merged_phase_summary(
    phases: list[tuple[str, Path, int]], output_dir: Path, *, intent_root: Path | None = None,
) -> dict[str, Any]:
    """Choose one coherent detail/decision/result bundle per request, then reuse summarize."""
    winners: dict[str, tuple[int, dict[str, Any], dict[str, Any], dict[str, Any]]] = {}
    parent_failed = False
    raw_request_ids: set[str] = set()
    already_applied_ids: set[str] = set()
    quarantined_ids: set[str] = set()
    filtered_results: dict[str, dict[str, Any]] = {}
    lifecycle_results: dict[str, dict[str, Any]] = {}
    planner_missing_request_ids: set[str] = set()
    observations_present = bool(phases)
    for phase, evidence_dir, parent_rc in phases:
        details = {
            str(row.get("request_id") or "").strip(): row
            for row in _rows(_load(evidence_dir / "application-snapshot.json"), "request_details")
            if str(row.get("request_id") or "").strip()
        }
        decisions = {
            str(row.get("request_id") or "").strip(): row
            for row in _rows(_load(evidence_dir / "application-decisions.json"), "decisions")
            if str(row.get("request_id") or "").strip()
        }
        parent_commit = _load(evidence_dir / "parent-commit.json")
        planner_missing_request_ids.update(
            _planner_missing_request_ids(parent_commit, set(details))
        )
        results = {}
        for row in _rows(parent_commit, "results"):
            application = row.get("application") if isinstance(row.get("application"), dict) else {}
            request_id = str(row.get("request_id") or application.get("request_id") or "").strip()
            if request_id:
                results[request_id] = row
        for request_id in dict.fromkeys((*details, *decisions, *results)):
            result = results.get(request_id, {})
            candidate = (
                _status_rank(str(result.get("status") or "")),
                details.get(request_id, {}), decisions.get(request_id, {}), result,
            )
            if request_id not in winners or candidate[0] >= winners[request_id][0]:
                winners[request_id] = candidate
        observations = _validated_observations(
            _load(evidence_dir / "application-observations.json")
        )
        if observations is not None:
            phase_raw_request_ids = {
                str(value) for value in observations.get("raw_request_ids", [])
            }
            raw_request_ids.update(phase_raw_request_ids)
            already_applied_ids.update(
                str(value) for value in observations.get("already_applied_ids", [])
            )
            quarantined_ids.update(str(value) for value in observations.get("quarantined_ids", []))
            for row in observations.get("filtered_results", []):
                if isinstance(row, dict) and str(row.get("request_id") or ""):
                    filtered_results[str(row["request_id"])] = row
            for row in observations["lifecycle_results"]:
                request_id = str(row["request_id"])
                previous = lifecycle_results.get(request_id)
                if previous is not None and any(previous.get(key) != row.get(key) for key in ("lifecycle_sha256", "status", "reason_codes")):
                    parent_failed = True
                    if row.get("status") in {"officially_unavailable", "unknown"}:
                        lifecycle_results[request_id] = row
                elif previous is None:
                    lifecycle_results[request_id] = row
            if not set(details).issubset(phase_raw_request_ids):
                raw_request_ids.update(details)
                parent_failed = True
        else:
            # The parent owns this sidecar.  A missing or malformed phase must not
            # silently erase candidates from a multi-turn report.  Preserve the
            # candidates still proven by the canonical snapshot and make the wake
            # non-successful so the loss of filtered reasons remains observable.
            raw_request_ids.update(details)
            parent_failed = True
        parent_failed = parent_failed or parent_rc != 0
    _atomic_json(output_dir / "application-snapshot.json", {
        "request_details": [bundle[1] for bundle in winners.values() if bundle[1]],
    })
    _atomic_json(output_dir / "application-decisions.json", {
        "decisions": [bundle[2] for bundle in winners.values() if bundle[2]],
    })
    _atomic_json(output_dir / "parent-commit.json", {
        "planner_missing_request_ids": sorted(planner_missing_request_ids),
        "results": [bundle[3] for bundle in winners.values() if bundle[3]],
    })
    if observations_present:
        _atomic_json(output_dir / "application-observations.json", {
            "version": 1,
            "raw_request_ids": sorted(raw_request_ids),
            "already_applied_ids": sorted(already_applied_ids),
            "quarantined_ids": sorted(quarantined_ids),
            "filtered_results": list(filtered_results.values()),
            "lifecycle_results": [lifecycle_results[key] for key in sorted(lifecycle_results)],
        })
    return summarize(output_dir, 1 if parent_failed else 0, intent_root=intent_root)


def _default_pass_id() -> str:
    return f"gig-apply-direct-{time.time_ns()}-{os.getpid()}"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _run(command: list[str], env: dict[str, str], stdout_path: Path, stderr_path: Path) -> subprocess.CompletedProcess[str]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8")
    return completed


def _validate_parent_result(
    *, args: argparse.Namespace, run_dir: Path, phase: str, evidence_dir: Path,
    context: Path, pass_id: str, cursor_path: Path | None,
    deferred_cursor_path: Path,
) -> int:
    """Reuse the legacy B2 postcondition before direct advances its cursor."""
    files = [path for path in run_dir.rglob("*") if path.is_file()]
    min_mtime = min((path.stat().st_mtime for path in files), default=time.time())
    readback_files = sorted({
        *run_dir.rglob("parent-B2-applied-readback-*.json"),
        *run_dir.rglob("parent-B2-applied-full-history.json"),
    })
    if readback_files:
        request_ids: set[str] = set()
        absent_ids: set[str] = set()
        urls: set[str] = set()
        observed_at: list[str] = []
        pages_walked = 0
        cards_seen = 0
        has_next_page = False
        valid = True
        for path in readback_files:
            payload = _load(path)
            if not (
                isinstance(payload, dict)
                and payload.get("source") == "code_owned_cdp_readback"
                and payload.get("observed") is True
                and payload.get("not_found") is False
            ):
                valid = False
                continue
            observed_ids = {
                str(value) for value in payload.get("request_ids", [])
                if _valid_b2_request_id(value)
            }
            expected_ids = {
                str(value) for value in payload.get("expected_ids", [])
                if _valid_b2_request_id(value)
            }
            request_ids.update(observed_ids)
            absent_ids.update(expected_ids - observed_ids)
            if isinstance(payload.get("observed_at"), str):
                observed_at.append(payload["observed_at"])
            pages_walked += int(payload.get("pages_walked") or 0)
            cards_seen += int(payload.get("cards_seen") or 0)
            has_next_page = has_next_page or payload.get("has_next_page") is True
            for value in payload.get("urls") or [payload.get("url")]:
                if (isinstance(value, str) and value
                        and urlsplit(value).path.rstrip("/") in {
                            "/mypage/job_matching/applied/offers",
                            "/mypage/job_matching/applied/outsource_applications",
                        }):
                    urls.add(value)
        _atomic_json(run_dir / "code-applied-readback.json", {
            "source": "code_owned_cdp_readback",
            "observed_at": max(observed_at, default=None),
            "pass_id": pass_id,
            "observed": valid,
            "not_found": not valid,
            "request_ids": sorted(request_ids),
            "expected_request_ids": sorted(request_ids | absent_ids),
            "applied_page_absent_request_ids": sorted(absent_ids - request_ids),
            "pages_walked": pages_walked,
            "cards_seen": cards_seen,
            "has_next_page": has_next_page,
            "missing_count": len(absent_ids - request_ids),
            "unresolved_count": 0,
            "urls": sorted(urls),
            "url": sorted(urls)[0] if urls else None,
        })

    gate_path = run_dir / f"b2-gate-result-{phase}.json"
    validate_command = [
        sys.executable, str(args.b2_gate), "validate",
        "--context", str(context),
        "--runner-summary", str(evidence_dir / "summary.json"),
        "--evidence-dir", str(run_dir),
        "--evidence-root", str(args.intent_root.parent),
        "--ledger", str(args.ledger),
        "--min-mtime", str(min_mtime),
        "--pass-id", pass_id,
        "--min-new-inspections", "0",
        "--deferred-coverage-cursor", str(deferred_cursor_path),
    ]
    if cursor_path is not None:
        validate_command.extend(("--cursor-contract", str(cursor_path)))
    gate = _run(
        validate_command, os.environ.copy(), gate_path,
        run_dir / f"b2-gate-result-{phase}.stderr",
    )
    if gate.returncode == 0:
        return 0
    continuation = _run(
        [
            sys.executable, str(args.b2_gate), "continuable",
            "--gate-result", str(gate_path),
            "--ledger", str(args.ledger),
            "--context", str(context),
            "--pass-id", pass_id,
        ],
        os.environ.copy(), run_dir / f"b2-continuation-result-{phase}.json",
        run_dir / f"b2-continuation-result-{phase}.stderr",
    )
    return 0 if continuation.returncode == 0 else 1


def _harvest_postings(
    *, args: argparse.Namespace, env: dict[str, str], run_dir: Path,
    phase: str, evidence_dir: Path,
) -> None:
    _run(
        [
            sys.executable, str(args.posting_source), "harvest",
            "--snapshot", str(evidence_dir / "application-snapshot.json"),
        ],
        env, run_dir / f"posting-harvest-{phase}.json",
        run_dir / f"posting-harvest-{phase}.stderr",
    )


def _last_json(stdout: str) -> dict[str, Any] | None:
    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _operator_brake_status(
    script: Path, *, timeout: float = 5.0,
) -> str:
    """Return free/held, or fail closed when the existing brake is unknowable."""
    return shared_operator_brake_status(script, timeout=timeout)


def _run_parent(
    command: list[str], env: dict[str, str], stdout_path: Path, stderr_path: Path,
) -> subprocess.CompletedProcess[str]:
    """Retry one renderer-wedged parent with the fresh context its lease creates."""
    completed = _run(command, env, stdout_path, stderr_path)
    payload = _last_json(completed.stdout)
    if (
        completed.returncode == 0
        or not isinstance(payload, dict)
        or payload.get("error") != "cdp_browser_wedged_for_every_attempt"
    ):
        return completed
    first_commit = None
    evidence_dir = None
    if "--evidence-dir" in command:
        index = command.index("--evidence-dir") + 1
        if index < len(command):
            evidence_dir = Path(command[index])
            first_commit = _load(evidence_dir / "parent-commit.json")
            if isinstance(first_commit, dict):
                _atomic_json(evidence_dir / "parent-commit.attempt-1.json", first_commit)
    os.replace(stdout_path, stdout_path.with_name(f"{stdout_path.name}.attempt-1"))
    os.replace(stderr_path, stderr_path.with_name(f"{stderr_path.name}.attempt-1"))
    retried = _run(command, env, stdout_path, stderr_path)
    if isinstance(first_commit, dict) and evidence_dir is not None:
        current_commit = _load(evidence_dir / "parent-commit.json")
        if isinstance(current_commit, dict):
            merged = {
                str(row.get("request_id") or ""): row
                for row in _rows(current_commit, "results")
                if str(row.get("request_id") or "")
            }
            for row in _rows(first_commit, "results"):
                request_id = str(row.get("request_id") or "")
                current = merged.get(request_id)
                if request_id and (
                    current is None
                    or _status_rank(str(row.get("status") or ""))
                    > _status_rank(str(current.get("status") or ""))
                ):
                    merged[request_id] = row
            current_commit["results"] = list(merged.values())
            _atomic_json(evidence_dir / "parent-commit.json", current_commit)
    _atomic_json(stdout_path.with_suffix(".recovery.json"), {
        "trigger": "cdp_browser_wedged_for_every_attempt",
        "attempts": 2,
        "first_returncode": completed.returncode,
        "final_returncode": retried.returncode,
    })
    return retried


# One unreachable source must not take the pass down with it. A 403 was already absorbed this
# way; a page whose title matches the not-found pattern was not, so it reached the wrapper as an
# unrecognised parent failure and ended the pass at the report phase -- after the report had
# already been delivered. An exit 1 that means "one source is missing" then looked identical to
# an exit 1 that means "this lane never reported".
_SOURCE_FAILURE_KINDS = ("source_access_denied", "source_not_found")


def _temporary_source_denial(
    completed: subprocess.CompletedProcess[str],
) -> tuple[str, str] | None:
    """Return (source_id, kind) for a single-source failure the pass can survive."""
    payload = _last_json(completed.stderr)
    if not isinstance(payload, dict) or payload.get("error_type") != "ParentContractError":
        return None
    error = str(payload.get("error") or "")
    for kind in _SOURCE_FAILURE_KINDS:
        prefix = f"{kind}:"
        if not error.startswith(prefix):
            continue
        # The message may carry diagnostic detail after the id, so take the first token only.
        source_id = error.removeprefix(prefix).strip().split(" ", 1)[0].strip()
        if source_id:
            return source_id, kind
    return None


def _restart_cursor_after_pagination_end(
    cursor_path: Path, source_id: str, kind: str | None,
) -> bool:
    """Running off the last page is exhaustion, not a missing source.

    The cursor walks `?page=N` forward until the provider stops rendering pages. Page 9 of a
    listing with eight pages answers with `ご指定のページが見つかりませんでした`, which is a real
    404 and not a stale URL -- page 8 loaded normally in the same pass. Treating that as a missing
    source ends the pass, and when the source is the only required one there is no successor to
    move to, so the lane fails every wake with nothing wrong with it.

    Reset to the source's first page instead: for a newest-first firehose, starting over is what
    reading it again means.
    """
    if kind != "source_not_found":
        return False
    try:
        cursor = json.loads(Path(cursor_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(cursor, dict) or str(cursor.get("source_id") or "") != source_id:
        return False
    parts = urlsplit(str(cursor.get("next_url") or ""))
    query = parse_qs(parts.query)
    pages = query.get("page") or []
    if not pages or not str(pages[0]).isdecimal() or int(pages[0]) < 2:
        return False
    query.pop("page", None)
    first_page = urlunsplit((
        parts.scheme, parts.netloc, parts.path,
        urlencode({key: values[0] for key, values in sorted(query.items())}), "",
    ))
    _atomic_json(Path(cursor_path), {
        "source_id": source_id,
        "previous_url": "",
        "next_url": first_page,
        "reason": "restart_after_pagination_end",
        "prior_inspected_request_ids": [],
    })
    return True


def _record_temporary_source_failure(
    run_dir: Path, failures: dict[str, dict[str, Any]], source_id: str, phase: str,
    kind: str = "source_access_denied",
) -> None:
    failures[source_id] = {
        "source_id": source_id,
        "phase": phase,
        "error": kind,
        # A 403 is expected to clear on its own. A page that is not there will not, so it is
        # recorded as persistent rather than retried forever under a "temporary" label.
        "temporary": kind == "source_access_denied",
        "exhausted": False,
    }
    _atomic_json(run_dir / "temporary-source-failures.json", {
        "version": 1,
        "sources": list(failures.values()),
    })


def _rows(payload: Any, key: str) -> list[dict[str, Any]]:
    values = payload.get(key) if isinstance(payload, dict) else payload
    return [row for row in values if isinstance(row, dict)] if isinstance(values, list) else []


def _planner_missing_request_ids(payload: Any, known_ids: set[str]) -> set[str]:
    """Trust parent missing-ID evidence only for this exact fresh snapshot."""
    values = payload.get("planner_missing_request_ids") if isinstance(payload, dict) else None
    if not isinstance(values, list):
        return set()
    return {
        value for value in values
        if isinstance(value, str) and value in known_ids
    }


def _validated_observations(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or payload.get("version") != 1:
        return None
    if "lifecycle_results" not in payload:
        payload = {**payload, "lifecycle_results": []}
    for key in ("raw_request_ids", "already_applied_ids", "quarantined_ids", "filtered_results", "lifecycle_results"):
        if not isinstance(payload.get(key), list):
            return None
    if any(not isinstance(value, str) or not value.strip() for key in (
        "raw_request_ids", "already_applied_ids", "quarantined_ids"
    ) for value in payload[key]):
        return None
    for row in payload["filtered_results"]:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("request_id"), str)
            or not row["request_id"].strip()
            or not isinstance(row.get("title"), str)
            or row.get("status") not in {"cached_ineligible", "closed"}
            or not isinstance(row.get("reason_codes"), list)
            or any(not isinstance(reason, str) for reason in row["reason_codes"])
            or row.get("business_class") not in {None, HARD_PROHIBITED}
        ):
            return None
    lifecycle_ids = set()
    for row in payload["lifecycle_results"]:
        request_id = row.get("request_id") if isinstance(row, dict) else None
        if not isinstance(request_id, str) or not _valid_b2_request_id(request_id) or request_id in lifecycle_ids or not isinstance(row.get("title"), str): return None
        lifecycle_ids.add(request_id)
        if row.get("status") == "unknown" and row.get("reason_codes") in (["lifecycle_observation_invalid"], ["lifecycle_shard_conflict"]) and not any(key in row for key in ("canonical_url", "page_state", "accepting_control", "deadline_state", "deadline_value", "form_state", "lifecycle_sha256")): continue
        fields = ("page_state", "accepting_control", "deadline_state", "deadline_value", "form_state")
        allowed = ({"present", "not_found", "unknown"}, {"present", "absent", "unknown"}, {"future", "expired", "unknown"}, None, {"present", "absent", "unknown"})
        if not isinstance(row.get("observed_at"), str) or any(row.get(key) not in values for key, values in zip(fields, allowed) if values is not None): return None
        if row["deadline_value"] is not None:
            try: deadline = dt.date.fromisoformat(row["deadline_value"])
            except (TypeError, ValueError): return None
            if deadline.isoformat() != row["deadline_value"] or row["deadline_state"] != ("expired" if deadline < dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date() else "future"): return None
        try:
            canonical_url = canonical_request_url(str(row.get("canonical_url") or ""), request_id=request_id)
        except SnapshotContractError:
            return None
        if row.get("canonical_url") != canonical_url or row.get("lifecycle_sha256") != hashlib.sha256(json.dumps({"request_id": request_id, "canonical_url": canonical_url, **{key: row[key] for key in fields}}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(): return None
        expected = {"page_state": "present", "accepting_control": "present", "deadline_state": "future", "form_state": "present"}
        reasons = [f"{key}:{row[key]}" for key, value in expected.items() if row[key] != value]
        status = "open" if not reasons else ("officially_unavailable" if row["page_state"] == "not_found" or not any(row[key] == "unknown" for key in expected) else "unknown")
        if (status == "open" and ("status" in row or "reason_codes" in row)) or (status != "open" and (row.get("status") != status or row.get("reason_codes") != reasons)): return None
    raw_ids = set(payload["raw_request_ids"])
    categorized_ids = (
        set(payload["already_applied_ids"])
        | set(payload["quarantined_ids"])
        | {row["request_id"] for row in payload["filtered_results"]}
        | lifecycle_ids
    )
    if not categorized_ids.issubset(raw_ids):
        return None
    return payload


def _oldest(details: list[dict[str, Any]]) -> str | None:
    values = []
    for row in details:
        for field in ("posted_at", "created_at", "published_at", "observed_at"):
            value = row.get(field)
            if isinstance(value, str) and value.strip():
                values.append(value.strip())
                break
    return min(values) if values else None


def summarize(
    evidence_dir: Path, parent_rc: int, *, require_observations: bool = False,
    intent_root: Path | None = None,
) -> dict[str, Any]:
    snapshot = _load(evidence_dir / "application-snapshot.json")
    details = _rows(snapshot, "request_details")
    detail_by_id = {
        str(row.get("request_id") or "").strip(): row for row in details
        if str(row.get("request_id") or "").strip()
    }
    decisions = _rows(_load(evidence_dir / "application-decisions.json"), "decisions")
    parent_commit = _load(evidence_dir / "parent-commit.json")
    rows = _rows(parent_commit, "results")
    planner_missing_request_ids = _planner_missing_request_ids(
        parent_commit, set(detail_by_id),
    )
    statuses = [str(row.get("status") or "") for row in rows]
    observations = _validated_observations(
        _load(evidence_dir / "application-observations.json")
    )
    observation_rows = _rows(observations, "filtered_results")
    officially_unavailable_ids = sorted(
        (str(row.get("request_id") or "").strip() for row in _rows(observations, "lifecycle_results")
         if row.get("status") == "officially_unavailable"),
        key=lambda request_id: (0, int(request_id)) if request_id.isdigit() else (1, request_id),
    )
    raw_request_ids = {
        str(value) for value in observations.get("raw_request_ids", [])
        if str(value)
    } if isinstance(observations, dict) else set()
    already_applied_ids = {
        str(value) for value in observations.get("already_applied_ids", [])
        if str(value)
    } if isinstance(observations, dict) else set()
    quarantined_ids = {
        str(value) for value in observations.get("quarantined_ids", [])
        if str(value)
    } if isinstance(observations, dict) else set()
    observation_incomplete = bool(
        observations is not None
        and not set(detail_by_id).issubset(raw_request_ids)
    )
    if observation_incomplete:
        raw_request_ids.update(detail_by_id)
    decision_by_id = {str(row.get("request_id") or "").strip(): row for row in decisions}
    duplicate_fenced_ids = set()
    for row in rows:
        application = row.get("application") if isinstance(row.get("application"), dict) else {}
        request_id = str(row.get("request_id") or application.get("request_id") or "").strip()
        decision = decision_by_id.get(request_id)
        if request_id and (
            row.get("business_class") == DUPLICATE_FENCED
            or row.get("status") in ALREADY_APPLIED_STATUSES
            or (
                isinstance(decision, dict)
                and _decision_business_class(decision) == DUPLICATE_FENCED
            )
        ):
            duplicate_fenced_ids.add(request_id)
    actionable = sum(
        _decision_business_class(row) == SUBMIT_REQUIRED
        and str(row.get("request_id") or "").strip() not in duplicate_fenced_ids
        for row in decisions
    )
    effect = sum(status in EFFECT_STATUSES for status in statuses)
    readback = sum(status in CONFIRMED for status in statuses)

    def _is_transient_reason(reason: object) -> bool:
        if isinstance(reason, (list, tuple)):
            return any(_is_transient_reason(item) for item in reason)
        text = str(reason or "")
        return any(marker in text for marker in TRANSIENT_REASON_MARKERS)

    report_results = []
    for row in rows:
        application = row.get("application") if isinstance(row.get("application"), dict) else {}
        request_id = str(row.get("request_id") or application.get("request_id") or "").strip()
        detail = detail_by_id.get(request_id, {})
        decision = decision_by_id.get(request_id, {})
        status = str(row.get("status") or "").strip()
        title = next((value for value in (application.get("title"), row.get("title"), detail.get("title")) if value), "")
        reason = row.get("reason") or row.get("error") or row.get("reason_codes") or decision.get("reason") or decision.get("reason_codes")
        price_jpy = next((value for value in (application.get("price_jpy"), row.get("price_jpy"), decision.get("price_jpy")) if value is not None), None)
        business_class = row.get("business_class") or _decision_business_class(decision)
        outcome = (
            "confirmed" if status in CONFIRMED
            else DUPLICATE_FENCED if business_class == DUPLICATE_FENCED or status in ALREADY_APPLIED_STATUSES
            else HARD_PROHIBITED if business_class == HARD_PROHIBITED or status == HARD_PROHIBITED
            else "prepared" if status == "prepared_unconfirmed"
            else "pending" if status.startswith(PENDING_PREFIXES)
            else "failed_transient" if _is_transient_reason(reason)
            else "failed"
        )
        report_results.append({
            "request_id": request_id,
            "title": title,
            "price_jpy": price_jpy,
            "status": status,
            "business_class": business_class,
            "reason": reason,
            "outcome": outcome,
        })
    committed_ids = {str(row.get("request_id") or "") for row in report_results}
    for row in observation_rows:
        request_id = str(row.get("request_id") or "").strip()
        if not request_id or request_id in committed_ids:
            continue
        status = str(row.get("status") or "").strip()
        cached_business_class = row.get("business_class")
        report_results.append({
            "request_id": request_id,
            "title": str(row.get("title") or ""),
            "price_jpy": None,
            "status": status,
            "business_class": cached_business_class,
            "reason": row.get("reason_codes"),
            "outcome": HARD_PROHIBITED if cached_business_class == HARD_PROHIBITED else "failed",
        })
    committed_ids = {str(row.get("request_id") or "") for row in report_results}
    planner_missing_reported = planner_missing_request_ids - committed_ids
    for request_id in sorted(planner_missing_reported):
        detail = detail_by_id[request_id]
        report_results.append({
            "request_id": request_id,
            "title": str(detail.get("title") or ""),
            "price_jpy": None,
            "status": "planner_missing_request_id",
            "business_class": None,
            "processing_disposition": "failed_transient",
            "effect": 0,
            "reason": "planner_missing_request_id",
            "outcome": "failed_transient",
        })
    failed = 0
    for row in rows:
        application = row.get("application") if isinstance(row.get("application"), dict) else {}
        request_id = str(row.get("request_id") or application.get("request_id") or "").strip()
        status = str(row.get("status") or "")
        if request_id not in duplicate_fenced_ids and (
            status in FAILED_STATUSES or status.startswith(FAILED_PREFIXES)
        ):
            failed += 1
    failed += len(planner_missing_reported)
    already_applied = sum(status in ALREADY_APPLIED_STATUSES for status in statuses)
    pending = sum(status.startswith(PENDING_PREFIXES) and status not in FAILED_STATUSES for status in statuses)
    pending = max(pending, actionable - effect - failed - already_applied)
    if (
        parent_rc != 0
        or (require_observations and (observations is None or observation_incomplete))
    ) and failed == 0:
        failed = 1
    return {
        "observed": len(raw_request_ids) if isinstance(observations, dict) else len(details),
        "judged": len(details),
        "already_applied_filtered": len(already_applied_ids),
        "cached_ineligible_filtered": sum(
            row.get("status") == "cached_ineligible" for row in observation_rows
        ),
        "officially_unavailable_count": len(officially_unavailable_ids),
        "officially_unavailable_ids": officially_unavailable_ids[:8],
        "closed_filtered": sum(row.get("status") == "closed" for row in observation_rows) + len(officially_unavailable_ids),
        "quarantined_filtered": len(quarantined_ids),
        "actionable": actionable,
        "effect": effect,
        "readback": readback,
        "failed": failed,
        "pending": pending,
        "oldest": _oldest(details),
        "report_results": report_results,
    }


def _clip_report(value: object, limit: int = 48, omitted_suffix: str = "…") -> str:
    text = " ".join(str(value or "").split()) or "不明"
    return text if len(text) <= limit else text[:limit - len(omitted_suffix)] + omitted_suffix


def _report_lines(pass_id: str, values: dict[str, Any]) -> list[str]:
    lines = [
        f"observed（観測）: {values['observed']}件",
        f"actionable（応募対象）: {values['actionable']}件",
        f"effect（実行）: {values['effect']}件",
        f"readback（公式確認）: {values['readback']}件",
        f"failed（失敗）: {values['failed']}件",
        f"pending（保留）: {values['pending']}件",
        f"oldest（最古）: {_clip_report(values['oldest'])}",
    ]
    if values.get("source_health"):
        lines.append(f"情報源状態: {_clip_report(values['source_health'], 180)}")
    if values["observed"]:
        lines.append(
            f"公式募集{values['observed']}件を確認（新規判定{values.get('judged', values['observed'])}件、"
            f"既応募{values.get('already_applied_filtered', 0)}件、"
            f"判定cache{values.get('cached_ineligible_filtered', 0)}件、"
            f"募集終了{values.get('closed_filtered', 0)}件、"
            f"安全停止{values.get('quarantined_filtered', 0)}件）。"
        )
    if values["observed"] == 0:
        lines.append("今回の実行では募集を観測できませんでした。")
    if unavailable_count := values.get("officially_unavailable_count", 0):
        unavailable_ids = values.get("officially_unavailable_ids", [])
        remaining = unavailable_count - len(unavailable_ids)
        lines.append(
            f"{OFFICIALLY_UNSUBMITTABLE}: 公式送信不能: {unavailable_count}件（ID: {', '.join(unavailable_ids)}"
            f"{'、他' + str(remaining) + '件' if remaining else ''}）"
        )
    results = values.get("report_results") or []
    outcome_counts = {
        outcome: sum(row.get("outcome") == outcome for row in results if isinstance(row, dict))
        for outcome in ("confirmed", HARD_PROHIBITED, DUPLICATE_FENCED, "failed_transient", "failed", "pending")
    }
    lines.append(
        "判断結果: "
        f"応募＋公式確認{outcome_counts['confirmed']}件 / "
        f"禁止条件{outcome_counts[HARD_PROHIBITED]}件 / "
        f"重複防止{outcome_counts[DUPLICATE_FENCED]}件 / "
        f"再判定待ち{outcome_counts['failed_transient']}件 / "
        f"送信失敗{outcome_counts['failed']}件 / "
        f"確認待ち{outcome_counts['pending']}件"
    )
    lines.append(f"pass_id: {_clip_report(pass_id, 96)}")
    return lines


def _reports(pass_id: str, values: dict[str, Any]) -> list[str]:
    body = _report_lines(pass_id, values)
    prefix = "[ココナラ][応募]"
    header_budget = len(prefix) + len("\npart 999999\n")
    chunks: list[list[str]] = []
    current: list[str] = []
    for line in body:
        candidate = "\n".join(current + [line])
        if current and len(candidate) + header_budget > 3900:
            chunks.append(current)
            current = []
        current.append(line)
    if current:
        chunks.append(current)
    return [
        f"{prefix}\npart {index}\n" + "\n".join(chunk)
        for index, chunk in enumerate(chunks, 1)
    ]


def _report(pass_id: str, values: dict[str, Any]) -> str:
    return _reports(pass_id, values)[0]


def _telegram_pass_key(pass_id: str) -> str:
    raw = str(pass_id)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{_clip_report(raw, 96)}-{digest}"


def _telegram_event_key(pass_id: str, message: str, part_index: int | None = None) -> str:
    body_digest = hashlib.sha256(message.encode("utf-8")).hexdigest()
    part = f":part-{part_index}" if part_index is not None and part_index > 1 else ""
    return f"gig:telegram:apply-direct:v1:{_telegram_pass_key(pass_id)}{part}:body-{body_digest}"


def _send_telegram(
    pass_id: str,
    message: str,
    args: argparse.Namespace,
    *,
    part_index: int | None = None,
) -> dict[str, Any]:
    safe_pass_id = _telegram_pass_key(pass_id)
    event_key = _telegram_event_key(pass_id, message, part_index)
    outbox = TelegramOutbox(args.telegram_database)
    row = outbox.enqueue(
        event_key=event_key,
        kind="apply-direct",
        message=message,
        created_at=int(time.time()),
        suppress_identical_body=False,
    )
    report_id = int(row["report_id"])
    event_key = str(row["event_key"])
    if row["state"] == "sent":
        return {"status": "sent", "message_id": row.get("message_id")}
    if row["state"] == "delivery_unknown":
        return {"status": "delivery_unknown", "message_id": row.get("message_id")}
    result = dispatch_one(
        outbox,
        owner=f"gig-apply-direct:{safe_pass_id}",
        now=lambda: int(time.time()),
        transport=ApplyTelegramTransport(
            target=args.telegram_target,
            receipt_dir=args.telegram_receipt_dir,
        ),
        report_id=report_id,
    )
    current = outbox.enqueue(
        event_key=event_key,
        kind="apply-direct",
        message=message,
        created_at=int(time.time()),
        suppress_identical_body=False,
    )
    if int(current["report_id"]) != report_id or str(current["event_key"]) != event_key:
        raise RuntimeError("Telegram current event changed")
    if current["state"] == "sent":
        return {"status": "sent", "message_id": current.get("message_id")}
    if current["state"] == "delivery_unknown":
        return {"status": "delivery_unknown", "message_id": current.get("message_id")}
    if result["status"] == "queue_empty":
        return {"status": "delivery_unknown", "message_id": None}
    return {"status": "delivery_unknown", "message_id": current.get("message_id")}


_HARD_PROHIBITION_JA = {
    "video_or_animation": "動画・アニメーション制作",
    "physical_or_onsite": "現地または現物での作業",
    "mandatory_human_presence": "本人の出演・通話・面談",
    "explicit_ai_prohibition": "明示的なAI利用禁止",
    "illegal_or_unsafe": "違法または安全でない作業",
    "missing_legal_qualification": "保有していない法定資格",
    "mandatory_attribute_fabrication": "本人属性についての虚偽回答",
}


def _fresh_decision_notifications(
    evidence_dir: Path, values: dict[str, Any],
) -> list[tuple[str, str]]:
    snapshot = _load(evidence_dir / "application-snapshot.json") or {}
    observations = _load(evidence_dir / "application-observations.json") or {}
    details = {str(row.get("request_id") or ""): row for row in _rows(snapshot, "request_details")}
    lifecycle = {str(row.get("request_id") or ""): row for row in _rows(observations, "lifecycle_results")}
    rows = [
        row for row in values.get("report_results", [])
        if isinstance(row, dict) and (
            row.get("status") == HARD_PROHIBITED
            or row.get("outcome") == "failed_transient"
            or (row.get("outcome") == "failed" and str(row.get("status") or "").startswith(
                ("submission_", "pre_submit_aborted", "form_readback_mismatch")
            ))
        )
    ]
    rows.extend({
        "request_id": row.get("request_id"), "title": row.get("title"),
        "status": OFFICIALLY_UNSUBMITTABLE, "outcome": OFFICIALLY_UNSUBMITTABLE,
    } for row in lifecycle.values() if row.get("status") == "officially_unavailable")

    notifications: list[tuple[str, str]] = []
    for row in rows:
        request_id = str(row.get("request_id") or "").strip()
        if not request_id:
            continue
        detail = details.get(request_id, {})
        lifecycle_row = lifecycle.get(request_id, {})
        title = _clip_report(row.get("title") or detail.get("title"), 100)
        outcome = str(row.get("outcome") or "failed")
        event_key = f"gig:telegram:apply-decision:v2:{request_id}:{outcome}"
        reason = row.get("reason") if isinstance(row.get("reason"), list) else []
        if outcome == HARD_PROHIBITED:
            class_name = _HARD_PROHIBITION_JA.get(str(reason[0]) if reason else "", "明示的な対応禁止条件")
            excerpt = _clip_report(reason[1] if len(reason) > 1 else "募集条件", 160)
            heading = "🚫 この案件には応募しませんでした"
            explanation = f"募集文の「{excerpt}」が{class_name}を必須としているためです。"
        elif outcome == OFFICIALLY_UNSUBMITTABLE:
            heading = "⏭️ 公式に応募できない案件をスキップしました"
            explanation = "公式ページで募集受付中の応募フォームを確認できなかったためです。"
        elif outcome == "failed_transient":
            status = str(row.get("status") or "")
            if status.startswith("submission_"):
                heading = "⚠️ この案件への応募確認を完了できませんでした"
                explanation = (
                    f"構造化判断は完了しましたが、送信後の公式確認が「{_clip_report(status, 120)}」"
                    "で止まりました。再送信せず、次回に公式履歴を照合します。"
                )
            else:
                heading = "⚠️ この案件の判断を完了できませんでした"
                explanation = "構造化判断が欠落したため送信せず、次回の再判定へ残しました。"
        else:
            heading = "⚠️ この案件への応募を完了できませんでした"
            explanation = f"送信処理が「{_clip_report(row.get('status'), 120)}」で止まったため、完了とは扱っていません。"
        message = "\n".join((
            "[ココナラ][応募判断]", heading, "", f"案件: {title}", f"依頼ID: {request_id}",
            f"理由: {explanation}", "", "次に自動で行うこと",
            "次の案件の確認を続けます。ユーザーの操作は必要ありません。",
        ))
        notifications.append((event_key, message))
    return notifications


def _decision_notification_exists(outbox: TelegramOutbox, event_key: str) -> bool:
    """Treat an acknowledged or unresolved legacy row as the durable migration fence."""
    if outbox.has_event(event_key):
        return True
    parts = event_key.split(":")
    if len(parts) != 6 or parts[:4] != ["gig", "telegram", "apply-decision", "v2"]:
        raise ValueError("invalid_apply_decision_event_key")
    request_id, outcome = parts[4], parts[5]
    return outbox.has_event_boundary(
        kind="apply-decision",
        prefix=f"gig:telegram:apply-decision:v1:{request_id}:",
        suffix=f":{outcome}",
    )


def _publish_fresh_decision_notifications(
    *, args: argparse.Namespace, pass_id: str, evidence_dir: Path, values: dict[str, Any],
) -> None:
    now = int(time.time())
    try:
        outbox = TelegramOutbox(args.telegram_database)
    except sqlite3.DatabaseError as error:
        _atomic_json(evidence_dir / "application-decision-telegram.json", {
            "version": 1, "enqueued": [], "dispatched": [], "error": type(error).__name__,
        })
        return
    enqueued: list[dict[str, Any]] = []
    for event_key, message in _fresh_decision_notifications(evidence_dir, values):
        if _decision_notification_exists(outbox, event_key):
            continue
        row = outbox.enqueue(
            event_key=event_key, kind="apply-decision", message=message,
            created_at=now, suppress_identical_body=False,
        )
        enqueued.append({"event_key": event_key, "report_id": int(row["report_id"])})
    dispatched: list[dict[str, Any]] = []
    transport = ApplyTelegramTransport(
        target=args.telegram_target,
        receipt_dir=args.telegram_receipt_dir,
    )
    for report_id in outbox.ready_report_ids(kind="apply-decision", now=now):
        try:
            result = dispatch_one(
                outbox,
                owner=f"gig-apply-direct:{_telegram_pass_key(pass_id)}",
                now=lambda: int(time.time()),
                transport=transport,
                report_id=report_id,
            )
        except Exception as error:
            dispatched.append({"report_id": report_id, "status": "failed", "error": type(error).__name__})
            break
        dispatched.append({"report_id": report_id, **result})
        if result["status"] == "delivery_unknown":
            break
    _atomic_json(evidence_dir / "application-decision-telegram.json", {
        "version": 1, "enqueued": enqueued, "dispatched": dispatched,
    })


def _finish(
    output: Path,
    pass_id: str,
    values: dict[str, Any],
    *,
    status: str,
    args: argparse.Namespace,
    error: str | None = None,
) -> int:
    values = dict(values)
    report_results = list(values.get("report_results") or [])
    reported_ids = {str(row.get("request_id") or "") for row in report_results}
    durable_pending = []
    if args.intent_root.is_dir():
        for path in sorted(args.intent_root.glob("*.json")):
            intent = _load(path)
            if (
                not isinstance(intent, dict)
                or intent.get("version") not in {2, 3}
                or intent.get("state") != "prepared"
                or intent.get("effect_phase") != "irreversible_attempt_started"
            ):
                continue
            request_id = str(intent.get("request_id") or "").strip()
            if not request_id or request_id in reported_ids:
                continue
            durable_pending.append({
                "request_id": request_id,
                "title": "",
                "price_jpy": intent.get("price_jpy"),
                "status": "prepared_unconfirmed",
                "business_class": DUPLICATE_FENCED,
                "reason": "durable_intent_requires_official_reconciliation",
                "outcome": "prepared",
            })
    if durable_pending:
        report_results.extend(durable_pending)
        values["report_results"] = report_results
        values["durable_uncertain_count"] = len(durable_pending)
        values["durable_pending_ids"] = [row["request_id"] for row in durable_pending]
    payload: dict[str, Any] = {
        "status": status,
        "pass_id": pass_id,
        **values,
        "business_success": values["effect"] == values["readback"] and values["effect"] > 0 and values["failed"] == 0 and values["pending"] == 0,
    }
    if error:
        payload["error"] = error
    reports = _reports(pass_id, values)
    payload["reports"] = reports
    payload["report"] = reports[0]
    deliveries = []
    transport_errors = []
    for index, report in enumerate(reports, 1):
        try:
            deliveries.append(_send_telegram(
                pass_id, report, args,
                part_index=None if index == 1 else index,
            ))
        except Exception as transport_error:
            deliveries.append({"status": "failed", "message_id": None})
            transport_errors.append(type(transport_error).__name__)
    payload["message_ids"] = [delivery.get("message_id") for delivery in deliveries]
    if len(reports) == 1 and payload["message_ids"][0] is not None:
        payload["message_id"] = payload["message_ids"][0]
    if all(delivery["status"] == "sent" for delivery in deliveries):
        payload["transport"] = "sent"
    elif any(delivery["status"] == "failed" for delivery in deliveries):
        payload["transport"] = "failed"
    else:
        payload["transport"] = "delivery_unknown"
    if transport_errors:
        payload["transport_error"] = transport_errors[0]
    _atomic_json(output, payload)
    # One row per wake, same filename storefront uses. Without this the lane has no heartbeat:
    # skills/self/earning-health-registry.json lists all four gig labels but probes a single ledger,
    # gig/storefront-direct/wakes.jsonl, so storefront's minute-by-minute rows were standing in for
    # apply's health. Measured 2026-08-18: apply ran a two-day-old release and fell from 38
    # applications a day to 1, and the slot stayed green the whole time, because the lane that
    # reports was not the lane that broke.
    try:
        ledger = args.state_dir / "wakes.jsonl"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            handle.flush()
    except OSError as ledger_error:
        # A wake that ran is worth more than a wake that logged; never fail the pass over this.
        print(f"wake_ledger_write_failed: {type(ledger_error).__name__}", file=sys.stderr)
    print("\n\n".join(reports))
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0 if status == "ok" else 1


def _parent_command(
    args: argparse.Namespace,
    *,
    context: Path,
    pass_id: str,
    evidence_dir: Path,
    legacy_path: Path,
    lease_task: str,
    cursor_path: Path | None = None,
    attempt_budget_path: Path | None = None,
) -> list[str]:
    command = [
        sys.executable, str(args.parent), "run",
        "--lease-script", str(args.lease_script), "--lease-task", lease_task,
        "--context", str(context), "--pass-id", pass_id,
        "--evidence-dir", str(evidence_dir), "--intent-root", str(args.intent_root),
        "--ledger", str(args.ledger), "--output", str(legacy_path),
        "--planner-runner", str(args.planner_runner), "--planner-workdir", str(Path.home()),
        "--planner-timeout-seconds", os.environ.get("GIG_APPLY_PLANNER_TIMEOUT_SECONDS", "900"),
        "--heartbeat-seconds", "20", "--planner-cache", str(args.planner_cache),
        "--ineligible-cache", str(args.ineligible_cache),
    ]
    if attempt_budget_path is not None:
        command.extend(("--attempt-budget", str(attempt_budget_path)))
    if cursor_path is not None:
        command.extend(("--cursor-contract", str(cursor_path)))
    if args.all_eligible:
        command.append("--all-eligible")
    return command


def _wake_sentence(cursor: dict[str, Any]) -> str:
    source_id = str(cursor.get("source_id") or "single:new")
    query = parse_qs(urlsplit(str(cursor.get("next_url") or "")).query)
    page = query.get("page", ["1"])[0]
    return f"新着eligible 0のため既存B2 cursor {source_id} page{page}を追加確認し、次pageへcheckpoint"


def _all_sources_exhausted(evidence_dir: Path) -> bool:
    summary = _load(evidence_dir / "summary.json")
    result = _load(Path(str(summary.get("result_path") or ""))) if isinstance(summary, dict) else None
    current = result.get("current_b2") if isinstance(result, dict) else None
    sources = current.get("search_sources") if isinstance(current, dict) else None
    return bool(sources) and all(
        isinstance(row, dict)
        and row.get("has_next") is False
        and row.get("exhausted") is True
        for row in sources
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pass-id", default=os.environ.get("GIG_APPLY_PASS_ID") or _default_pass_id())
    parser.add_argument("--state-dir", type=Path, default=Path(os.environ.get("GIG_APPLY_STATE_DIR", str(Path.home() / "gig" / "apply-direct"))))
    parser.add_argument("--passprep", type=Path, default=DEFAULT_PREP)
    parser.add_argument("--b2-gate", type=Path, default=DEFAULT_GATE)
    parser.add_argument("--parent", type=Path, default=DEFAULT_PARENT)
    parser.add_argument("--posting-source", type=Path, default=DEFAULT_POSTING_SOURCE)
    parser.add_argument("--operator-brake", type=Path, default=DEFAULT_OPERATOR_BRAKE)
    parser.add_argument("--lease-script", type=Path, default=BROWSER_DIR / "scripts" / "cdp_context_lease.py")
    parser.add_argument("--planner-runner", type=Path, default=DEFAULT_RUNNER)
    parser.add_argument("--intent-root", type=Path, default=Path.home() / "gig" / "application-intents")
    parser.add_argument("--ledger", type=Path, default=Path.home() / "gig" / "applied.jsonl")
    parser.add_argument("--planner-cache", type=Path, default=Path.home() / "gig" / "b2-planner-cache.json")
    parser.add_argument("--ineligible-cache", type=Path, default=Path.home() / "gig" / "b2-ineligible-cache.json")
    parser.add_argument(
        "--search-objective-state", type=Path,
        default=Path(os.environ.get("GIG_B2_OBJECTIVE_STATE", str(Path.home() / "gig" / "b2-search-objective.json"))),
    )
    parser.add_argument("--telegram-database", type=Path, default=DEFAULT_TELEGRAM_DATABASE)
    parser.add_argument("--telegram-target", default=DEFAULT_TELEGRAM_TARGET)
    parser.add_argument("--telegram-receipt-dir", type=Path, default=DEFAULT_TELEGRAM_RECEIPT_DIR)
    parser.add_argument(
        "--all-eligible",
        action="store_true",
        help="ask the parent to use the existing 20-application ceiling for this batch",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    args.planner_runner = args.planner_runner.resolve(strict=True)
    pin_release_for_process(args.parent)

    pass_id = str(args.pass_id)
    run_dir = args.state_dir / pass_id
    evidence_dir = run_dir / "evidence"
    prep_path = run_dir / "passprep.json"
    context = run_dir / "b2-context.json"
    legacy_path = run_dir / "legacy-b2.json"
    output = args.output or run_dir / "result.json"
    empty = {"observed": 0, "actionable": 0, "effect": 0, "readback": 0, "failed": 0, "pending": 0, "oldest": None}

    env = os.environ.copy()
    # The runner accepts a budget scope only together with the budgets it scopes --
    # naming one without them is rejected outright. So opt in only once an operator
    # has set the budgets, and otherwise run unmetered, the way this lane always has.
    if env.get("ANICCA_PASS_TOKEN_BUDGET") and env.get("ANICCA_LOOP_DAILY_TOKEN_BUDGET"):
        env.setdefault("ANICCA_BUDGET_SCOPE_ID", pass_id)
        env.setdefault("ANICCA_BUDGET_DAILY_SCOPE", "gig-apply-direct")
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        register_live_evidence_pin(args.state_dir.parent, run_dir, "apply-direct")
    except OSError:
        empty["failed"] = 1
        empty["source_health"] = "実行中evidenceの保護状態を確立できませんでした"
        return _finish(output, pass_id, empty, status="failed", args=args, error="evidence_pin_failed")
    brake_status = _operator_brake_status(args.operator_brake)
    if brake_status == "held":
        empty["source_health"] = "operator brakeが有効なため、応募処理を開始しませんでした"
        return _finish(
            output, pass_id, empty, status="operator_brake", args=args,
            error="operator_brake_held",
        )
    if brake_status == "failed":
        empty["failed"] = 1
        empty["source_health"] = "operator brake状態を確認できないため、安全のため応募処理を開始しませんでした"
        return _finish(
            output, pass_id, empty, status="failed", args=args,
            error="operator_brake_check_failed",
        )
    refresh_cursor_path = run_dir / "b2-refresh-cursor.json"
    coverage_cursor_path = run_dir / "b2-coverage-cursor.json"
    try:
        wake = wake_plan(
            state_path=args.search_objective_state,
            refresh_output_path=refresh_cursor_path,
            coverage_output_path=coverage_cursor_path,
            pass_id=pass_id,
            now=int(time.time()),
        )
    except (OSError, ValueError) as error:
        empty["failed"] = 1
        empty["source_health"] = f"応募情報源を読み取れませんでした（{type(error).__name__}）"
        return _finish(output, pass_id, empty, status="failed", args=args, error="b2_objective_wake_failed")

    if not context.exists():
        prep_payload = _load(prep_path)
        if not isinstance(prep_payload, dict):
            prep = _run(
                [sys.executable, str(args.passprep)], env,
                run_dir / "passprep.stdout", run_dir / "passprep.stderr",
            )
            prep_payload = _last_json(prep.stdout)
            if prep.returncode != 0 or prep_payload is None:
                empty["failed"] = 1
                return _finish(output, pass_id, empty, status="failed", args=args, error="passprep_failed")
            _atomic_json(prep_path, prep_payload)
        temporary_context = run_dir / ".b2-context.json.tmp"
        gate = _run(
            [sys.executable, str(args.b2_gate), "build", "--prep-json",
             json.dumps(
                 _official_open_scan_prep(prep_payload),
                 ensure_ascii=False,
                 separators=(",", ":"),
             ),
             "--applied", str(args.ledger), "--output", str(temporary_context)],
            env, run_dir / "b2-gate.stdout", run_dir / "b2-gate.stderr",
        )
        if gate.returncode != 0 or not temporary_context.is_file() or _load(temporary_context) is None:
            temporary_context.unlink(missing_ok=True)
            empty["failed"] = 1
            return _finish(output, pass_id, empty, status="failed", args=args, error="b2_context_build_failed")
        os.replace(temporary_context, context)
    elif not isinstance(_load(context), dict):
        empty["failed"] = 1
        return _finish(output, pass_id, empty, status="failed", args=args, error="b2_context_invalid")

    phase_specs = (
        [("main", evidence_dir, legacy_path, None, f"gig-apply-direct-{pass_id}")]
        if wake is None else [
            ("refresh", run_dir / "refresh-evidence", run_dir / "refresh-legacy-b2.json",
             refresh_cursor_path, f"gig-apply-direct-{pass_id}"),
            ("coverage", run_dir / "coverage-evidence", run_dir / "coverage-legacy-b2.json",
             coverage_cursor_path, f"gig-apply-direct-{pass_id}-coverage"),
        ]
    )
    attempt_budget_path = run_dir / "submit-attempt-budget.json"
    phases: list[tuple[str, Path, int]] = []
    phase_cursor_paths: dict[str, Path] = {}
    phase_source_denials: dict[str, str] = {}
    phase_source_failure_kinds: dict[str, str] = {}
    temporary_source_failures: dict[str, dict[str, Any]] = {}
    refresh_safe_counts: dict[str, int] | None = None
    refresh_exhausted = False
    for phase, phase_evidence, phase_legacy, cursor, lease_task in phase_specs:
        if cursor is not None:
            phase_cursor_paths[phase] = cursor
        command = _parent_command(
            args, context=context, pass_id=pass_id, evidence_dir=phase_evidence,
            legacy_path=phase_legacy, lease_task=lease_task, cursor_path=cursor,
            attempt_budget_path=attempt_budget_path,
        )
        stem = "parent" if phase == "main" else phase
        completed = _run_parent(command, env, run_dir / f"{stem}.stdout", run_dir / f"{stem}.stderr")
        source_failure = _temporary_source_denial(completed)
        # Bind unconditionally: a later branch reads denied_source_id on every phase, so leaving it
        # assigned only inside the `if` makes an ordinary pass raise UnboundLocalError.
        denied_source_id = source_failure[0] if source_failure is not None else None
        if source_failure is not None:
            failure_kind = source_failure[1]
            phase_source_denials[phase] = denied_source_id
            phase_source_failure_kinds[phase] = failure_kind
            _record_temporary_source_failure(
                run_dir, temporary_source_failures, denied_source_id, phase, failure_kind,
            )
        invocation = "parent.invocation.json" if phase == "main" else f"parent.invocation-{phase}.json"
        _atomic_json(run_dir / invocation, {"argv": command})
        parent_rc = completed.returncode
        if parent_rc == 0:
            parent_rc = _validate_parent_result(
                args=args, run_dir=run_dir, phase=phase, evidence_dir=phase_evidence,
                context=context, pass_id=pass_id, cursor_path=cursor,
                deferred_cursor_path=coverage_cursor_path,
            )
        if parent_rc == 0:
            _harvest_postings(
                args=args, env=env, run_dir=run_dir, phase=phase,
                evidence_dir=phase_evidence,
            )
        phases.append((phase, phase_evidence, parent_rc))
        values = summarize(
            phase_evidence, parent_rc, require_observations=True,
            intent_root=args.intent_root,
        )
        _publish_fresh_decision_notifications(
            args=args, pass_id=pass_id, evidence_dir=phase_evidence, values=values,
        )
        awaiting_exact_readback = any(
            row.get("status") == "awaiting_exact_id_readback"
            for row in values["report_results"]
        )
        if parent_rc == 0 and awaiting_exact_readback:
            # Keep the durable parent as the only click authority. A delayed second
            # parent turn re-enters its existing PREPARED recovery state machine,
            # which requires official absence, saved non-landing evidence and a
            # fresh accepting form before it can create another irreversible attempt.
            # If this wrapper dies during the delay, the next launchd wake resumes
            # from the same durable intent instead of losing or duplicating work.
            time.sleep(SAME_WAKE_RECONCILE_DELAY_SECONDS)
            reconcile_evidence = run_dir / f"{phase}-reconcile-evidence"
            reconcile_legacy = run_dir / f"{phase}-reconcile-legacy-b2.json"
            reconcile_command = _parent_command(
                args, context=context, pass_id=pass_id,
                evidence_dir=reconcile_evidence, legacy_path=reconcile_legacy,
                lease_task=f"{lease_task}-reconcile", cursor_path=cursor,
                attempt_budget_path=attempt_budget_path,
            )
            reconcile = _run_parent(
                reconcile_command, env,
                run_dir / f"{stem}-reconcile.stdout",
                run_dir / f"{stem}-reconcile.stderr",
            )
            _atomic_json(
                run_dir / f"parent.invocation-{phase}-reconcile.json",
                {"argv": reconcile_command},
            )
            reconcile_rc = reconcile.returncode
            if reconcile_rc == 0:
                reconcile_rc = _validate_parent_result(
                    args=args, run_dir=run_dir, phase=f"{phase}-reconcile",
                    evidence_dir=reconcile_evidence, context=context,
                    pass_id=pass_id, cursor_path=cursor,
                    deferred_cursor_path=coverage_cursor_path,
                )
            if reconcile_rc == 0:
                _harvest_postings(
                    args=args, env=env, run_dir=run_dir,
                    phase=f"{phase}-reconcile", evidence_dir=reconcile_evidence,
                )
            phases[-1] = (phase, reconcile_evidence, reconcile_rc)
            phase_evidence = reconcile_evidence
            parent_rc = reconcile_rc
            values = summarize(
                phase_evidence, parent_rc, require_observations=True,
                intent_root=args.intent_root,
            )
            _publish_fresh_decision_notifications(
                args=args, pass_id=pass_id,
                evidence_dir=phase_evidence, values=values,
            )
        if phase == "refresh":
            if denied_source_id is not None:
                try:
                    successor = next_required_source_cursor(
                        context, denied_source_id,
                        skipped_source_ids=set(temporary_source_failures),
                    )
                except CursorContractError:
                    break
                _atomic_json(coverage_cursor_path, successor)
                refresh_safe_counts = {
                    field: 0 for field in ("actionable", "effect", "readback", "failed", "pending")
                }
                continue
            safe_no_effect_outcomes = all(
                row.get("outcome") in {
                    HARD_PROHIBITED, DUPLICATE_FENCED, "failed_transient",
                }
                for row in values["report_results"]
            )
            duplicate_fenced_count = sum(
                row.get("outcome") == DUPLICATE_FENCED
                for row in values["report_results"]
            )
            failed_transient_count = sum(
                row.get("outcome") == "failed_transient"
                for row in values["report_results"]
            )
            refresh_is_empty = (
                parent_rc == values["actionable"] == values["effect"]
                == values["readback"] == values["failed"] == values["pending"] == 0
                and safe_no_effect_outcomes
            )
            refresh_is_duplicate_only = (
                parent_rc == 0
                and values["actionable"] <= duplicate_fenced_count
                and values["effect"] == values["readback"] == 0
                and values["pending"] == 0
                and safe_no_effect_outcomes
                and values["failed"] <= duplicate_fenced_count + failed_transient_count
            )
            if not (refresh_is_empty or refresh_is_duplicate_only):
                break
            if _all_sources_exhausted(phase_evidence):
                refresh_exhausted = True
                break
            coverage_cursor = _load(coverage_cursor_path)
            if not isinstance(coverage_cursor, dict):
                raise ValueError("coverage_cursor_invalid_after_refresh")
            coverage_cursor["prior_inspected_request_ids"] = list(dict.fromkeys(
                request_id
                for row in values["report_results"]
                if _valid_b2_request_id(
                    request_id := str(row.get("request_id") or "").strip()
                )
            ))
            _atomic_json(coverage_cursor_path, coverage_cursor)
            if refresh_is_duplicate_only:
                refresh_safe_counts = {
                    field: values[field]
                    for field in ("actionable", "effect", "readback", "failed", "pending")
                }

    last_phase, last_evidence, last_rc = phases[-1]
    values = (
        _merged_phase_summary(phases, run_dir / "combined-evidence", intent_root=args.intent_root)
        if len(phases) > 1 else summarize(
            last_evidence, last_rc, require_observations=True,
            intent_root=args.intent_root,
        )
    )
    if wake is None:
        values["source_health"] = "深掘りcursorは未接続"
        return _finish(
            output, pass_id, values, status="ok" if last_rc == 0 else "failed", args=args,
            error=None if last_rc == 0 else f"parent_failed_rc_{last_rc}",
        )
    if refresh_exhausted:
        target_payload = _load(context)
        target = target_payload.get("target_applications") if isinstance(target_payload, dict) else 1
        try:
            finish(
                state_path=args.search_objective_state, ledger_path=args.ledger,
                pass_id=pass_id, target=max(1, int(target)), now=int(time.time()),
            )
        except (OSError, ValueError) as error:
            values["source_health"] = f"全探索完了状態を保存できませんでした（{type(error).__name__}）"
            return _finish(output, pass_id, values, status="failed", args=args, error="b2_objective_finish_failed")
        values["source_health"] = "全source探索完了。次wakeは新着から再開"
        return _finish(output, pass_id, values, status="ok", args=args)
    if last_phase == "refresh":
        inconsistent = (
            values["effect"] > values["actionable"]
            or values["readback"] > values["effect"]
        )
        if inconsistent:
            values["failed"] += 1
            values["source_health"] = "新着処理の集計が不整合なため、深掘りと成功判定を停止"
            return _finish(
                output, pass_id, values, status="failed", args=args,
                error="refresh_count_incoherent",
            )
        if last_rc != 0 and phase_source_denials.get("refresh") is not None:
            failed_source = phase_source_denials["refresh"]
            if phase_source_failure_kinds.get("refresh") == "source_not_found":
                values["source_health"] = (
                    f"新着source {failed_source} が見つかりません（公式ページが404扱い）。"
                    "既存intentを保持し、他sourceの処理は継続します"
                )
            else:
                values["source_health"] = (
                    f"新着source {failed_source} は一時access denial。既存intentを保持して次wakeで再試行"
                )
            return _finish(output, pass_id, values, status="ok", args=args)
        if last_rc != 0:
            values["source_health"] = f"新着情報の取得に失敗したため深掘りを停止（終了コード {last_rc}）"
        elif values["failed"]:
            values["source_health"] = f"新着処理で失敗{values['failed']}件を記録したため深掘りを停止"
        else:
            values["source_health"] = f"新着処理に応募対象{values['actionable']}件または確認待ち{values['pending']}件があるため、深掘りを停止"
        return _finish(
            output, pass_id, values, status="ok" if last_rc == 0 else "failed", args=args,
            error=None if last_rc == 0 else f"parent_failed_rc_{last_rc}",
        )
    # One refresh plus one coverage turn keeps the cursor moving without letting
    # full reconciliation block the next wake's fresh discovery for several minutes.
    max_parent_turns = 2
    while True:
        last_phase, last_evidence, last_rc = phases[-1]
        values = _merged_phase_summary(
            phases, run_dir / "combined-evidence", intent_root=args.intent_root,
        )
        continuing_after_source_failure = False
        if last_rc != 0:
            denied_source_id = phase_source_denials.get(last_phase)
            if denied_source_id is None or len(temporary_source_failures) >= max_parent_turns:
                if denied_source_id is None:
                    values["source_health"] = f"深掘り情報の取得に失敗しました（終了コード {last_rc}）"
                else:
                    # Name the source and the kind. "exit code 2" alone cannot tell a reader
                    # whether one source is missing or the whole lane is broken.
                    kind = phase_source_failure_kinds.get(last_phase, "source_access_denied")
                    values["source_health"] = (
                        f"深掘りsourceの失敗が上限に達しました（最後は {denied_source_id} の {kind}）"
                    )
                return _finish(
                    output, pass_id, values, status="failed", args=args,
                    error=f"parent_failed_rc_{last_rc}",
                )
            try:
                next_cursor = next_required_source_cursor(
                    context, denied_source_id,
                    skipped_source_ids=set(temporary_source_failures),
                )
            except CursorContractError:
                if _restart_cursor_after_pagination_end(
                    coverage_cursor_path, denied_source_id,
                    phase_source_failure_kinds.get(last_phase),
                ):
                    values["source_health"] = (
                        f"{denied_source_id} は最終ページに到達しました。"
                        "次wakeは先頭ページから読み直します"
                    )
                    return _finish(output, pass_id, values, status="ok", args=args)
                values["source_health"] = "一時拒否sourceの後続位置を決められませんでした"
                return _finish(
                    output, pass_id, values, status="failed", args=args,
                    error="temporary_source_successor_unavailable",
                )
            continuing_after_source_failure = True

        coverage_turn = len(phases) - 1
        next_cursor_path = run_dir / f"b2-next-cursor-{coverage_turn}.json"
        if not continuing_after_source_failure:
            try:
                next_cursor = next_search_cursor(
                    last_evidence / "summary.json", context,
                    cursor_path=phase_cursor_paths.get(last_phase),
                )
            except CursorContractError as error:
                if str(error) != "continuation_cursor_unavailable" or not _all_sources_exhausted(last_evidence):
                    values["source_health"] = f"次の探索位置を決められませんでした（{type(error).__name__}）"
                    return _finish(output, pass_id, values, status="failed", args=args, error="b2_continuation_unavailable")
                target_payload = _load(context)
                target = target_payload.get("target_applications") if isinstance(target_payload, dict) else 1
                try:
                    finish(
                        state_path=args.search_objective_state, ledger_path=args.ledger,
                        pass_id=pass_id, target=max(1, int(target)), now=int(time.time()),
                    )
                except (OSError, ValueError) as finish_error:
                    values["source_health"] = f"全探索完了状態を保存できませんでした（{type(finish_error).__name__}）"
                    return _finish(output, pass_id, values, status="failed", args=args, error="b2_objective_finish_failed")
                values["source_health"] = "全source探索完了。次wakeは新着から再開"
                return _finish(output, pass_id, values, status="ok", args=args)
        next_cursor["prior_inspected_request_ids"] = list(dict.fromkeys(
            request_id
            for row in values["report_results"]
            if _valid_b2_request_id(
                request_id := str(row.get("request_id") or "").strip()
            )
        ))
        try:
            _atomic_json(next_cursor_path, next_cursor)
            if not temporary_source_failures:
                checkpoint(
                    state_path=args.search_objective_state, cursor_path=next_cursor_path,
                    pass_id=pass_id, now=int(time.time()),
                )
        except (OSError, ValueError) as error:
            values["source_health"] = f"次の探索位置を保存できませんでした（{type(error).__name__}）"
            return _finish(output, pass_id, values, status="failed", args=args, error="b2_objective_checkpoint_failed")

        must_stop = any(
            values[field] > (refresh_safe_counts or {}).get(field, 0)
            for field in ("actionable", "effect", "readback", "failed", "pending")
        )
        if (must_stop and not continuing_after_source_failure) or (
            len(phases) >= max_parent_turns and not continuing_after_source_failure
        ):
            if temporary_source_failures:
                values["source_health"] = (
                    f"一時拒否source {len(temporary_source_failures)}件を未完のまま保持し、次sourceまで継続"
                )
            elif len(phases) >= max_parent_turns and not must_stop:
                values["source_health"] = (
                    f"新着eligible 0のため既存B2 cursorを{len(phases)} turn確認し、次pageへcheckpoint"
                )
            else:
                values["source_health"] = _wake_sentence(wake["coverage_cursor"])
            return _finish(output, pass_id, values, status="ok", args=args)

        phase_number = len(phases)
        phase = f"coverage-{phase_number}"
        phase_evidence = run_dir / f"coverage-evidence-{phase_number}"
        phase_legacy = run_dir / f"coverage-legacy-b2-{phase_number}.json"
        phase_cursor_paths[phase] = next_cursor_path
        command = _parent_command(
            args, context=context, pass_id=pass_id, evidence_dir=phase_evidence,
            legacy_path=phase_legacy,
            lease_task=f"gig-apply-direct-{pass_id}-coverage-{phase_number}",
            cursor_path=next_cursor_path,
            attempt_budget_path=attempt_budget_path,
        )
        completed = _run_parent(
            command, env, run_dir / f"{phase}.stdout", run_dir / f"{phase}.stderr"
        )
        source_failure = _temporary_source_denial(completed)
        # Bind unconditionally: a later branch reads denied_source_id on every phase, so leaving it
        # assigned only inside the `if` makes an ordinary pass raise UnboundLocalError.
        denied_source_id = source_failure[0] if source_failure is not None else None
        if source_failure is not None:
            failure_kind = source_failure[1]
            phase_source_denials[phase] = denied_source_id
            phase_source_failure_kinds[phase] = failure_kind
            _record_temporary_source_failure(
                run_dir, temporary_source_failures, denied_source_id, phase, failure_kind,
            )
        _atomic_json(run_dir / f"parent.invocation-{phase}.json", {"argv": command})
        parent_rc = completed.returncode
        if parent_rc == 0:
            parent_rc = _validate_parent_result(
                args=args, run_dir=run_dir, phase=phase, evidence_dir=phase_evidence,
                context=context, pass_id=pass_id, cursor_path=next_cursor_path,
                deferred_cursor_path=coverage_cursor_path,
            )
        if parent_rc == 0:
            _harvest_postings(
                args=args, env=env, run_dir=run_dir, phase=phase,
                evidence_dir=phase_evidence,
            )
        phase_values = summarize(
            phase_evidence, parent_rc, require_observations=True,
            intent_root=args.intent_root,
        )
        _publish_fresh_decision_notifications(
            args=args, pass_id=pass_id, evidence_dir=phase_evidence, values=phase_values,
        )
        phases.append((phase, phase_evidence, parent_rc))


if __name__ == "__main__":
    raise SystemExit(main())
