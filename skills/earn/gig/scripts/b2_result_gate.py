#!/usr/bin/env python3
"""Freeze B2 policy inputs and verify that an apply step actually completed.

The model chooses feasibility and writes proposals.  Code owns the measurable
boundaries: current strategy thresholds, prior application identities, result
cardinality, fresh marketplace evidence, fresh submit proof, and the durable ledger.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit


class ContractError(ValueError):
    """The frozen policy input is absent or malformed."""


_RETAINER_ULID = re.compile(r"[0-7][0-9A-HJKMNP-TV-Z]{25}")


def _valid_request_id(value: Any) -> bool:
    request_id = str(value or "").strip()
    return bool(re.fullmatch(r"\d+", request_id) or _RETAINER_ULID.fullmatch(request_id))


def _request_id_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise ContractError(f"{label}_invalid")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{label}_invalid") from exc
    if number < minimum:
        raise ContractError(f"{label}_invalid")
    return number


def _applied_ids(path: Path) -> list[str]:
    found: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise ContractError("applied_ledger_unreadable") from exc
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or "action" in row:
            continue
        if row.get("recorded_by") in {
            "application_report_proof_recovery",
            "application_report_intent_recovery",
        } and not (
            row.get("submit_verified") is True
            and row.get("applied_page_verified") is True
        ):
            # A file named "*-submitted.png" is not itself proof of submission.
            # Production pass 1785261605 reached only the final modal, saved that
            # filename, and proof recovery otherwise blacklisted the still-open job.
            continue
        request_id = str(row.get("requestId") or row.get("request_id") or "").strip()
        if _valid_request_id(request_id):
            found.add(request_id)
    return sorted(found, key=_request_id_sort_key)


def build_context(prep: dict[str, Any], applied_path: Path) -> dict[str, Any]:
    if not isinstance(prep, dict):
        raise ContractError("prep_invalid")
    thresholds = prep.get("apply_skip_thresholds")
    if not isinstance(thresholds, dict):
        raise ContractError("apply_skip_thresholds_missing")
    categories = [
        str(value).strip()
        for value in (prep.get("category_order") or [])
        if str(value).strip()
    ]
    _integer(prep.get("max_apply_per_pass"), "max_apply_per_pass", minimum=1)
    # One continuous application has its own source, form, and readback.  It is a
    # reserved slot, never an interchangeable twentieth single-offer application.
    target_retainer = 1
    target_single = 19
    return {
        "version": 7,
        # Dais 2026-08-06: quantity IS the strategy. Many posters never pick anyone --
        # measured: 47 of the last ~80 ineligibles were 募集終了/受付停止, jobs that died
        # with no winner -- so hit-rate per application is structurally low and the only
        # lever that compounds is applying to every eligible fresh job, every pass.
        # Tunable through passprep (target_apply_per_pass); the parent contract caps at 20.
        "target_applications": target_single,
        "target_retainer_applications": target_retainer,
        "max_applications": 20,
        "min_budget_jpy": _integer(
            thresholds.get("min_budget_jpy"), "min_budget_jpy", minimum=0
        ),
        "fulfillment_capabilities": {
            "asynchronous_text": True,
            "scheduled_recurring_text": True,
            "durable_follow_up_queue": True,
            "authorized_owner_profile_facts": True,
            "external_account_operations": True,
            "synchronous_voice_video_or_live_presence": False,
            "human_voice_recording": False,
            "physical_presence": False,
        },
        "active_strategy_experiment": (
            prep.get("active_strategy_experiment")
            if isinstance(prep.get("active_strategy_experiment"), dict)
            else None
        ),
        "already_applied_request_ids": _applied_ids(applied_path),
        # A3 (2026-07-30): "retainer:new" is gone from the required program. A pass
        # must be able to close without ever having swept /job_matching/outsources,
        # because sweeping a bucket it can no longer apply into is a page load and a
        # model call spent on an outcome that cannot happen.
        "required_search_source_ids": [
            "single:new",
            *("retainer:new",),
            *(f"single:category:{category}" for category in categories),
            *(("single:keyword",) if categories else ()),
        ],
    }


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"{label}_unreadable") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{label}_invalid")
    return value


def _owned_fresh_file(
    value: Any, root: Path, min_mtime: float
) -> tuple[Path | None, str | None]:
    try:
        path = Path(str(value or "")).resolve()
        path.relative_to(root.resolve())
    except (OSError, ValueError):
        return None, "not_owned"
    try:
        stat = path.stat()
        if not path.is_file() or stat.st_size == 0:
            return None, "missing"
        if stat.st_mtime < min_mtime:
            return None, "stale"
    except OSError:
        return None, "missing"
    return path, None


def _marketplace_url(value: Any) -> bool:
    parsed = urlsplit(str(value or ""))
    return (
        parsed.scheme == "https"
        and parsed.hostname in {"coconala.com", "www.coconala.com"}
        and (
            parsed.path in {
                "/requests",
                "/job_matching/requests",
                "/job_matching/outsources",
            }
            or re.fullmatch(r"/requests/categories/\d+", parsed.path) is not None
        )
        and (
            parsed.path == "/job_matching/outsources"
            or
            not parsed.query
            or parse_qs(parsed.query, keep_blank_values=True).get("sort") == ["new"]
        )
    )


def _request_url(value: Any, request_id: str, bucket: str) -> bool:
    parsed = urlsplit(str(value or ""))
    expected_paths = (
        {
            f"/requests/{request_id}",
            f"/job_matching/requests/{request_id}",
        }
        if bucket == "single"
        else {f"/job_matching/outsources/{request_id}"}
    )
    return (
        parsed.scheme == "https"
        and parsed.hostname in {"coconala.com", "www.coconala.com"}
        and parsed.path in expected_paths
    )


def _search_url(value: Any) -> bool:
    parsed = urlsplit(str(value or ""))
    return (
        parsed.scheme == "https"
        and parsed.hostname in {"coconala.com", "www.coconala.com"}
        and (
            parsed.path in {"/requests", "/job_matching/requests"}
            or parsed.path == "/job_matching/outsources"
            or re.fullmatch(r"/requests/categories/\d+", parsed.path) is not None
        )
    )


def _same_search_url(left: Any, right: Any) -> bool:
    """Compare one official search page without depending on query ordering."""
    if not _search_url(left) or not _search_url(right):
        return False
    left_parsed = urlsplit(str(left))
    right_parsed = urlsplit(str(right))
    return (
        left_parsed.scheme,
        left_parsed.hostname,
        left_parsed.path,
        tuple(sorted(parse_qsl(left_parsed.query, keep_blank_values=True))),
        left_parsed.fragment,
    ) == (
        right_parsed.scheme,
        right_parsed.hostname,
        right_parsed.path,
        tuple(sorted(parse_qsl(right_parsed.query, keep_blank_values=True))),
        right_parsed.fragment,
    )


def _next_page_url(value: Any) -> str:
    url = str(value or "")
    if not _search_url(url):
        raise ContractError("continuation_source_url_invalid")
    parsed = urlsplit(url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    page_index: int | None = None
    current_page = 1
    for index, (key, raw) in enumerate(pairs):
        if key != "page":
            continue
        if page_index is not None or not re.fullmatch(r"\d+", raw) or int(raw) < 1:
            raise ContractError("continuation_page_invalid")
        page_index = index
        current_page = int(raw)
    next_pair = ("page", str(current_page + 1))
    if page_index is None:
        pairs.append(next_pair)
    else:
        pairs[page_index] = next_pair
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(pairs), parsed.fragment)
    )


def _missing_required_source_url(source_id: str) -> str | None:
    """Build a deterministic first page when the model dropped a required source.

    Category ids are marketplace implementation details and are not present in the
    frozen objective. Searching the frozen category label is stable, exact, and keeps
    the parent -- rather than the model -- responsible for the first navigation.
    """
    prefix = "single:category:"
    if source_id.startswith(prefix):
        label = source_id.removeprefix(prefix).strip()
        if label:
            return "https://coconala.com/requests?" + urlencode({
                "keyword": label,
                "recruiting": "true",
            })
    if source_id == "single:keyword":
        return "https://coconala.com/requests?" + urlencode({
            "keyword": "AI",
            "recruiting": "true",
        })
    if source_id == "single:new":
        return "https://coconala.com/requests?sort=new&recruiting=true"
    if source_id == "retainer:new":
        return "https://coconala.com/job_matching/outsources"
    return None


def next_required_source_cursor(
    context_path: Path, failed_source_id: str, *, skipped_source_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Continue after one temporary source failure without marking it exhausted."""
    context = _read_object(context_path, "b2_context")
    required = [
        str(value) for value in context.get("required_search_source_ids", []) if str(value)
    ]
    if failed_source_id not in required:
        raise ContractError("failed_source_not_required")
    skipped = set(skipped_source_ids or set()) | {failed_source_id}
    start = required.index(failed_source_id) + 1
    for source_id in required[start:]:
        if source_id in skipped:
            continue
        source_url = _missing_required_source_url(source_id)
        if source_url is not None:
            return {
                "source_id": source_id,
                "previous_url": "",
                "next_url": source_url,
                "reason": "continue_after_temporary_source_failure",
            }
    raise ContractError("temporary_source_successor_unavailable")


def _search_url_advances(previous: Any, current: Any) -> bool:
    """Return true when one source's current URL is on a later result page."""
    if not _search_url(previous) or not _search_url(current):
        return False

    def position(value: Any) -> tuple[tuple[Any, ...], int] | None:
        parsed = urlsplit(str(value or ""))
        page = 1
        page_seen = False
        stable_pairs: list[tuple[str, str]] = []
        for key, raw in parse_qsl(parsed.query, keep_blank_values=True):
            if key != "page":
                stable_pairs.append((key, raw))
                continue
            if page_seen or not re.fullmatch(r"\d+", raw) or int(raw) < 1:
                return None
            page_seen = True
            page = int(raw)
        return (
            (
                parsed.scheme,
                parsed.hostname,
                parsed.path,
                tuple(sorted(stable_pairs)),
                parsed.fragment,
            ),
            page,
        )

    previous_position = position(previous)
    current_position = position(current)
    return (
        previous_position is not None
        and current_position is not None
        and previous_position[0] == current_position[0]
        and current_position[1] > previous_position[1]
    )


def next_search_cursor(
    summary_path: Path, context_path: Path, *, cursor_path: Path | None = None,
) -> dict[str, Any]:
    summary = _read_object(summary_path, "b2_runner_summary")
    if summary.get("status") != "success" or summary.get("task_label") != "gig-B2":
        raise ContractError("b2_runner_summary_not_success")
    result_path = Path(str(summary.get("result_path") or ""))
    result = _read_object(result_path, "b2_result")
    current = result.get("current_b2")
    if not isinstance(current, dict):
        raise ContractError("current_b2_missing")
    sources = current.get("search_sources")
    if not isinstance(sources, list) or not all(isinstance(row, dict) for row in sources):
        raise ContractError("search_sources_malformed")
    inspected = current.get("inspected_requests")
    if not isinstance(inspected, list) or not all(isinstance(row, dict) for row in inspected):
        raise ContractError("inspected_requests_malformed")
    prior_ids = sorted(
        {
            str(row.get("request_id") or "").strip()
            for row in inspected
            if _valid_request_id(row.get("request_id"))
        },
        key=_request_id_sort_key,
    )

    def cursor(**values: Any) -> dict[str, Any]:
        if prior_ids:
            values["prior_inspected_request_ids"] = prior_ids
        return values
    by_id = {
        str(row.get("source_id") or ""): row
        for row in sources
        if str(row.get("source_id") or "")
    }
    context = _read_object(context_path, "b2_context")
    required = [
        str(value)
        for value in context.get("required_search_source_ids", [])
        if str(value)
    ]
    if cursor_path is not None:
        current_cursor = _read_object(cursor_path, "b2_cursor")
        current_source_id = str(current_cursor.get("source_id") or "")
        if current_source_id not in required:
            raise ContractError("cursor_source_not_required")
        if current_source_id not in by_id:
            raise ContractError("cursor_source_not_observed")
        # A cursor proves that every earlier required source was already traversed.
        # One-source phase summaries intentionally omit those sources, so they must
        # not be reinterpreted as missing and selected again.
        required = required[required.index(current_source_id):]
    raw_applications = result.get("applications")
    applications = raw_applications if isinstance(raw_applications, list) else []
    application_ids = {
        str(row.get("request_id") or "").strip()
        for row in applications
        if isinstance(row, dict)
        and _valid_request_id(row.get("request_id"))
    }
    target = _integer(
        context.get("target_applications"),
        "target_applications",
        minimum=1,
    )
    target_retainer = _integer(
        context.get("target_retainer_applications"),
        "target_retainer_applications",
        minimum=0,
    )
    verified_single_count = sum(1 for request_id in application_ids if request_id.isdigit())
    verified_retainer_count = sum(
        1 for request_id in application_ids if not request_id.isdigit()
    )
    if (
        verified_single_count >= target
        and verified_retainer_count < target_retainer
        and "retainer:new" in required
    ):
        source = by_id.get("retainer:new")
        if source is None:
            return cursor(
                source_id="retainer:new",
                previous_url="",
                next_url="https://coconala.com/job_matching/outsources",
                reason="inspect_missing_source",
            )
        source_url = str(source.get("url") or "")
        if source.get("has_next") is True:
            return cursor(
                source_id="retainer:new",
                previous_url=source_url,
                next_url=_next_page_url(source_url),
                reason="next_page",
            )
        if (
            source.get("exhausted") is False
            and source.get("inspected_count") == 0
            and _search_url(source_url)
        ):
            return cursor(
                source_id="retainer:new",
                previous_url=source_url,
                next_url=source_url,
                reason="inspect_current_page",
            )
    if "single:new" in required and "single:new" not in by_id:
        return cursor(
            source_id="single:new",
            previous_url="",
            next_url="https://coconala.com/requests?sort=new&recruiting=true",
            reason="inspect_missing_source",
        )
    for source_id in required:
        source = by_id.get(source_id)
        if source is None:
            missing_url = _missing_required_source_url(source_id)
            if missing_url is not None:
                return cursor(
                    source_id=source_id,
                    previous_url="",
                    next_url=missing_url,
                    reason="inspect_missing_source_by_keyword",
                )
            continue
        source_url = str(source.get("url") or "")
        if source.get("has_next") is True:
            return cursor(
                source_id=source_id,
                previous_url=source_url,
                next_url=_next_page_url(source_url),
                reason="next_page",
            )
        if (
            source.get("exhausted") is False
            and source.get("inspected_count") == 0
            and _search_url(source_url)
        ):
            return cursor(
                source_id=source_id,
                previous_url=source_url,
                next_url=source_url,
                reason="inspect_current_page",
            )
    raise ContractError("continuation_cursor_unavailable")


def _verified_pass_application_ids(ledger_path: Path, pass_id: str) -> set[str]:
    """Applications this pass submitted AND independently read back as present.

    This is the only count that means money moved: the durable ledger row must
    carry both the submit proof and the canonical applied-page confirmation.
    """
    verified: set[str] = set()
    try:
        ledger_lines = ledger_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return verified
    except OSError as exc:
        raise ContractError("application_ledger_unreadable") from exc
    for raw in ledger_lines:
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        request_id = str(row.get("requestId") or row.get("request_id") or "")
        if (
            str(row.get("pass_id") or "") == pass_id
            and _valid_request_id(request_id)
            and row.get("submit_verified") is True
            and row.get("applied_page_verified") is True
        ):
            verified.add(request_id)
    return verified


def continuation_state(
    gate_result_path: Path,
    ledger_path: Path,
    context_path: Path,
    pass_id: str,
) -> tuple[bool, int, int]:
    try:
        gate_lines = gate_result_path.read_text(encoding="utf-8").splitlines()
        gate = json.loads(gate_lines[-1])
    except (OSError, IndexError, json.JSONDecodeError) as exc:
        raise ContractError("gate_result_unreadable") from exc
    errors = gate.get("errors") if isinstance(gate, dict) else None
    if not isinstance(errors, list) or not all(isinstance(error, str) for error in errors):
        raise ContractError("gate_errors_invalid")
    under_target = "under_target_search_not_exhausted"
    recoverable_volume = under_target in errors and all(
        error == under_target
        or error in {
            "marketplace_url_invalid",
            "marketplace_live_dom_url_mismatch",
        }
        or error.startswith("application_count_mismatch:")
        or error.startswith("application_single_count_mismatch:")
        or error.startswith("application_retainer_count_mismatch:")
        or error.startswith("under_target_inspection_quantity_too_low:")
        or error.startswith("search_source_")
        or error.startswith("search_sources_")
        or error.startswith("continuation_cursor_")
        or error.startswith("eligible_already_applied:")
        or error.startswith("inspected_request_duplicate:")
        for error in errors
    )
    context = _read_object(context_path, "context")
    target = _integer(
        context.get("target_applications"),
        "target_applications",
        minimum=1,
    )
    target_retainer = _integer(
        context.get("target_retainer_applications"),
        "target_retainer_applications",
        minimum=0,
    )
    verified = _verified_pass_application_ids(ledger_path, pass_id)
    verified_singles = {request_id for request_id in verified if request_id.isdigit()}
    verified_retainers = {
        request_id for request_id in verified if not request_id.isdigit()
    }
    retainer_recoverable_errors = {
        "retainer_application_missing",
        "retainer_search_not_exhausted",
    }
    recoverable_retainer = (
        len(verified_singles) >= target
        and len(verified_retainers) < target_retainer
        and any(error in retainer_recoverable_errors for error in errors)
        and all(
            error in retainer_recoverable_errors
            or error.startswith("search_source_")
            or error.startswith("search_sources_")
            or error.startswith("continuation_cursor_")
            for error in errors
        )
    )
    allowed = (
        recoverable_volume and len(verified_singles) < target
    ) or recoverable_retainer
    return allowed, len(verified), target


# E7 (2026-08-07). A terminal B2 gate result carried two unrelated meanings in one
# word. Thirty consecutive passes ended FAILED at B2 while B2 was submitting real
# applications, and a paying customer's undelivered revision hid under the same red
# for hours. These three buckets exist so "red" means one thing again.
#
# SHORTFALL = the lane worked and produced less than the target. That is a
# throughput number and belongs to D1, not to the pass's exit code.
_SHORTFALL_ERROR_PREFIXES = (
    "under_target_search_not_exhausted",
    "under_target_inspection_quantity_too_low:",
    "application_count_mismatch:",
    "application_single_count_mismatch:",
    "application_retainer_count_mismatch:",
)
# EVIDENCE DEFECT = a per-source evidence-binding diagnostic. Measured 2026-08-07:
# all 57-61 of these per pass come from one filename collision, not from a category
# the lane skipped -- application_parent._safe_name strips every non-ASCII character,
# so 47 Japanese-only category labels resolve to the same snapshot filename and
# overwrite each other. The lane DID search them. continuation_state has always
# treated search_source_* as recoverable, so this bucket keeps that verdict; it is
# counted and written out rather than deleted, and it is filed as its own defect.
_EVIDENCE_DEFECT_PREFIXES = ("search_source_not_observed:",)
_COUNT_MISMATCH_RE = re.compile(
    r"^application_count_mismatch:expected=(\d+):actual=(\d+)$"
)


def classify_terminal_outcome(
    *, errors: list[str], verified_count: int, target: int
) -> dict[str, Any]:
    """Split a terminal B2 result into "could not work" vs "did less work".

    Everything not explicitly named a shortfall or an evidence defect blocks, so a
    new error class fails the pass until someone classifies it on purpose. Silence
    must never be the thing that turns a break into a green pass.
    """
    blocking: list[str] = []
    shortfall_errors: list[str] = []
    evidence_defects: list[str] = []
    for error in errors:
        if error.startswith(_EVIDENCE_DEFECT_PREFIXES):
            evidence_defects.append(error)
        elif error.startswith(_SHORTFALL_ERROR_PREFIXES):
            shortfall_errors.append(error)
        else:
            blocking.append(error)

    eligible_available = 0
    applications_reported = 0
    for error in shortfall_errors:
        match = _COUNT_MISMATCH_RE.match(error)
        if match:
            eligible_available = max(eligible_available, int(match.group(1)))
            applications_reported = max(applications_reported, int(match.group(2)))

    if blocking:
        outcome, reason = "broken", "lane_errors"
    elif verified_count == 0 and eligible_available > 0:
        # The one under-target case that IS a malfunction: the marketplace had work
        # this lane judged it could do, and the lane submitted nothing.
        outcome, reason = "broken", "zero_applications_with_work_available"
    elif verified_count < target:
        outcome, reason = "shortfall", "below_target"
    else:
        outcome, reason = "clean", "target_met"

    return {
        "version": 1,
        "outcome": outcome,
        "reason": reason,
        "verified_applications": verified_count,
        "target_applications": target,
        "applications_short_of_target": max(0, target - verified_count),
        "eligible_work_available": eligible_available,
        "applications_reported": applications_reported,
        "blocking_errors": blocking,
        "shortfall_errors": shortfall_errors,
        "evidence_defects": evidence_defects,
        "evidence_defect_count": len(evidence_defects),
    }


def terminal_outcome(
    *,
    gate_result_path: Path,
    ledger_path: Path,
    context_path: Path,
    pass_id: str,
) -> dict[str, Any]:
    try:
        gate_lines = gate_result_path.read_text(encoding="utf-8").splitlines()
        gate = json.loads(gate_lines[-1])
    except (OSError, IndexError, json.JSONDecodeError) as exc:
        raise ContractError("gate_result_unreadable") from exc
    errors = gate.get("errors") if isinstance(gate, dict) else None
    if not isinstance(errors, list) or not all(isinstance(e, str) for e in errors):
        raise ContractError("gate_errors_invalid")
    context = _read_object(context_path, "context")
    target = _integer(
        context.get("target_applications"), "target_applications", minimum=1
    )
    verified = _verified_pass_application_ids(ledger_path, pass_id)
    record = classify_terminal_outcome(
        errors=errors, verified_count=len(verified), target=target
    )
    return {
        "pass_id": str(pass_id),
        **record,
        "verified_request_ids": sorted(verified, key=_request_id_sort_key),
    }


def _ledger_ids(path: Path) -> set[str]:
    return set(_applied_ids(path))


def _ledger_rows(path: Path) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return found
    for raw in lines:
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or "action" in row:
            continue
        request_id = str(row.get("requestId") or row.get("request_id") or "")
        if _valid_request_id(request_id):
            found[request_id] = row
    return found


def _submit_proof_candidates(
    root: Path, pattern: str, evidence_dir: Path | None
) -> list[Path]:
    """Every place a *-submitted.png for THIS pass can legitimately live.

    Measured 2026-08-07: production writes submit proofs to
    <evidence_root>/gig-pass-<id>/agent-B2/, but this lookup globbed
    <evidence_root> non-recursively, so it found none of the 75 real proofs on
    disk and reported application_submit_evidence_missing for every verified
    application. The tests never caught it because their fixtures put the proof
    flat at the root, which is the layout production stopped using.

    Recursion is scoped to this pass's own evidence directory on purpose: an
    unscoped rglob over the root would let a LATER pass's proof satisfy this
    pass's postcondition, which is the class of bug this gate exists to stop.
    The flat root glob stays for the legacy layout still on disk.
    """
    seen: dict[Path, None] = {}
    for base, recursive in ((evidence_dir, True), (root, False)):
        if base is None:
            continue
        try:
            matches = base.rglob(pattern) if recursive else base.glob(pattern)
            for path in matches:
                seen.setdefault(path, None)
        except OSError:
            continue
    return list(seen)


def _has_fresh_submit_proof(
    root: Path,
    request_id: str,
    min_mtime: float,
    *,
    evidence_dir: Path | None = None,
) -> bool:
    for path in _submit_proof_candidates(
        root, f"gig-*-B2-{request_id}-submitted.png", evidence_dir
    ):
        try:
            stat = path.stat()
        except OSError:
            continue
        if path.is_file() and stat.st_size > 0 and stat.st_mtime >= min_mtime:
            return True
    return False


def _fresh_submit_ids(
    root: Path, min_mtime: float, *, evidence_dir: Path | None = None
) -> set[str]:
    found: set[str] = set()
    for path in _submit_proof_candidates(
        root, "gig-*-B2-*-submitted.png", evidence_dir
    ):
        match = re.fullmatch(
            r"gig-.*-B2-([0-9A-Z]+)-submitted\.png",
            path.name,
        )
        if not match:
            continue
        if not _valid_request_id(match.group(1)):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if path.is_file() and stat.st_size > 0 and stat.st_mtime >= min_mtime:
            found.add(match.group(1))
    return found


def _fresh_submit_intent_ids(
    root: Path,
    min_mtime: float,
    states: frozenset[str] = frozenset({"prepared", "confirmed"}),
) -> set[str]:
    found: set[str] = set()
    try:
        for path in root.rglob("gig-*-B2-*-submitted.intent.json"):
            match = re.fullmatch(
                r"gig-.*-B2-([0-9A-Z]+)-submitted\.intent\.json",
                path.name,
            )
            if not match or not _valid_request_id(match.group(1)):
                continue
            try:
                stat = path.stat()
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            request_id = match.group(1)
            if (
                path.is_file()
                and stat.st_size > 0
                and stat.st_mtime >= min_mtime
                and isinstance(payload, dict)
                and str(payload.get("request_id") or "") == request_id
                and payload.get("state") in states
            ):
                found.add(request_id)
    except OSError:
        return found
    return found


def _readback_absent_ids(evidence_dir: Path, min_mtime: float) -> set[str]:
    """Identities this pass's own code-owned readback proved absent.

    cdp_nav_snapshot writes state="prepared" immediately BEFORE the irreversible
    click, so a prepared-only intent means "outcome unknown", never "submitted".
    The readback is the independent authority that resolves it; once it has looked
    at the canonical applied page -- with bounded retries -- and not found the
    identity, treating the pre-click marker as a hidden submission is a RED no
    later pass can ever clear.
    """
    path, error = _owned_fresh_file(
        evidence_dir / "code-applied-readback.json", evidence_dir, min_mtime
    )
    if error or path is None:
        return set()
    try:
        payload = _read_object(path, "applied_page_readback")
    except ContractError:
        return set()
    if payload.get("observed") is not True:
        return set()
    return {
        str(value)
        for value in (payload.get("applied_page_absent_request_ids") or [])
        if _valid_request_id(value)
    }


def _parent_duplicate_fenced_ids(
    summary_path: Path, evidence_dir: Path, min_mtime: float,
) -> set[str]:
    """Read exact IDs the direct parent fenced without producing an application."""
    path, error = _owned_fresh_file(
        summary_path.parent / "parent-commit.json", evidence_dir, min_mtime
    )
    if error or path is None:
        return set()
    try:
        payload = _read_object(path, "parent_commit")
    except ContractError:
        return set()
    rows = payload.get("results")
    if not isinstance(rows, list):
        return set()
    return {
        request_id
        for row in rows
        if isinstance(row, dict)
        and row.get("business_class") == "duplicate_fenced"
        and not isinstance(row.get("application"), dict)
        and _valid_request_id(
            request_id := str(row.get("request_id") or "").strip()
        )
    }


def _deferred_search_source_ids(
    cursor_path: Path | None, required_source_ids: list[str]
) -> set[str]:
    """Sources the durable coverage cursor has not reached yet this wake.

    b2_search_objective.py walks required_search_source_ids with a single moving
    cursor across hourly wakes (next_search_cursor always returns the first
    incomplete source in list order), so everything from the cursor's source_id
    onward is legitimately unswept this wake -- not an evidence defect. A
    missing or unparseable cursor file is not proof of deferral, so it grants
    nothing: fail-closed, same as today's behavior.
    """
    if cursor_path is None:
        return set()
    try:
        cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(cursor, dict):
        return set()
    source_id = str(cursor.get("source_id") or "")
    if not source_id or source_id not in required_source_ids:
        return set()
    return set(required_source_ids[required_source_ids.index(source_id):])


def validate_result(
    *,
    context_path: Path,
    summary_path: Path,
    evidence_dir: Path,
    evidence_root: Path,
    ledger_path: Path,
    min_mtime: float,
    pass_id: str | None = None,
    cursor_contract_path: Path | None = None,
    min_new_inspections: int = 0,
    deferred_coverage_cursor_path: Path | None = None,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    try:
        context = _read_object(context_path, "b2_context")
    except ContractError as exc:
        return False, [str(exc)]
    try:
        summary = _read_object(summary_path, "b2_runner_summary")
    except ContractError as exc:
        return False, [str(exc)]
    if summary.get("status") != "success" or summary.get("task_label") != "gig-B2":
        return False, ["b2_runner_summary_not_success"]
    result_path, result_error = _owned_fresh_file(
        summary.get("result_path"), evidence_dir, min_mtime
    )
    if result_error:
        return False, [f"b2_result_{result_error}"]
    try:
        result = _read_object(result_path, "b2_result")  # type: ignore[arg-type]
    except ContractError as exc:
        return False, [str(exc)]
    if result.get("status") != "ok":
        return False, ["b2_result_invalid"]
    current = result.get("current_b2")
    if not isinstance(current, dict):
        return False, ["current_b2_missing"]

    try:
        bound_context = Path(str(current.get("context_path") or "")).resolve()
        if bound_context != context_path.resolve():
            errors.append("context_path_mismatch")
        if current.get("context_sha256") != sha256_file(context_path):
            errors.append("context_sha256_mismatch")
    except OSError:
        errors.append("context_binding_unreadable")

    marketplace_url = current.get("marketplace_url")
    if not _marketplace_url(marketplace_url):
        errors.append("marketplace_url_invalid")
    _, shot_error = _owned_fresh_file(
        current.get("marketplace_screenshot_path"), evidence_dir, min_mtime
    )
    if shot_error:
        errors.append(f"marketplace_screenshot_{shot_error}")
    dom_path, dom_error = _owned_fresh_file(
        current.get("marketplace_live_dom_path"), evidence_dir, min_mtime
    )
    if dom_error:
        errors.append(f"marketplace_live_dom_{dom_error}")
    if dom_path is not None:
        try:
            dom = _read_object(dom_path, "marketplace_live_dom")
        except ContractError:
            errors.append("marketplace_live_dom_invalid_json")
        else:
            if dom.get("observed") is not True:
                errors.append("marketplace_not_observed")
            if dom.get("not_found") is True:
                errors.append("marketplace_not_found")
            if dom.get("url") != marketplace_url or not _marketplace_url(dom.get("url")):
                errors.append("marketplace_live_dom_url_mismatch")

    inspected = current.get("inspected_requests")
    if not isinstance(inspected, list) or not all(
        isinstance(row, dict) for row in inspected
    ):
        return False, errors + ["inspected_requests_malformed"]

    min_budget = context.get("min_budget_jpy")
    target_applications = context.get("target_applications")
    target_retainer_applications = context.get("target_retainer_applications")
    max_applications = context.get("max_applications")
    if not all(
        isinstance(value, int) and not isinstance(value, bool)
        for value in (
            min_budget,
            target_applications,
            target_retainer_applications,
            max_applications,
        )
    ):
        return False, errors + ["b2_context_thresholds_invalid"]
    already_applied = {
        str(value)
        for value in context.get("already_applied_request_ids", [])
        if str(value)
    }
    ledger_rows = _ledger_rows(ledger_path)
    fresh_submit_intent_ids = _fresh_submit_intent_ids(
        evidence_root,
        min_mtime,
    )
    same_pass_verified_ids = {
        request_id
        for request_id, row in ledger_rows.items()
        if pass_id
        and str(row.get("pass_id") or "") == pass_id
        and row.get("submit_verified") is True
        and row.get("applied_page_verified") is True
    }
    carried_application_ids = same_pass_verified_ids & already_applied
    parent_duplicate_fenced_ids = _parent_duplicate_fenced_ids(
        summary_path, evidence_dir, min_mtime
    )

    seen: dict[str, dict[str, Any]] = {}
    eligible_ids: list[str] = []
    deduped_eligible_ids: list[str] = []
    for row in inspected:
        request_id = str(row.get("request_id") or "").strip()
        if not _valid_request_id(request_id):
            errors.append("request_id_invalid")
            continue
        if request_id in seen:
            errors.append(f"inspected_request_duplicate:{request_id}")
            first = seen[request_id]
            if any(
                first.get(field) != row.get(field)
                for field in ("bucket", "url", "outcome")
            ):
                errors.append(f"inspected_request_conflict:{request_id}")
            continue
        seen[request_id] = row
        bucket = row.get("bucket")
        if bucket not in {"single", "retainer"}:
            errors.append(f"request_bucket_invalid:{request_id}")
            continue
        expected_bucket = "single" if request_id.isdigit() else "retainer"
        if bucket != expected_bucket:
            errors.append(f"request_bucket_identity_mismatch:{request_id}")
        if not _request_url(row.get("url"), request_id, bucket):
            errors.append(f"request_url_invalid:{request_id}")
        outcome = row.get("outcome")
        if outcome not in {"eligible", "ineligible"}:
            errors.append(f"request_outcome_invalid:{request_id}")
            continue
        if outcome != "eligible":
            continue
        if request_id in already_applied and request_id not in carried_application_ids:
            errors.append(f"eligible_already_applied:{request_id}")
            deduped_eligible_ids.append(request_id)
            # The frozen ledger is authoritative.  Preserve the diagnostic but
            # remove this model classification from the new-submit cardinality so
            # a safe dedupe does not demand or trigger a duplicate application.
            continue
        eligible_ids.append(request_id)
        if row.get("accepting_applications") is not True:
            errors.append(f"eligible_marketplace_closed:{request_id}")
        budget_max = row.get("budget_max_jpy")
        if (
            bucket == "single"
            and isinstance(budget_max, (int, float))
            and not isinstance(budget_max, bool)
            and budget_max < min_budget
        ):
            errors.append(f"eligible_budget_below_minimum:{request_id}")

    eligible_count = result.get("eligible_count")
    new_eligible_ids = [
        request_id
        for request_id in eligible_ids
        if request_id not in carried_application_ids
        and request_id not in parent_duplicate_fenced_ids
    ]
    cumulative_observed_eligible_ids = set(eligible_ids) | carried_application_ids
    if eligible_count is None:
        # OpenAI strict output requires this key but permits null.  The count is
        # redundant: inspected_requests is the code-verifiable source of truth.
        # Derive it instead of converting a healthy under-target pagination result
        # into a non-retryable failure (production pass 1785290401).
        eligible_count = len(eligible_ids)
    elif not isinstance(eligible_count, int) or isinstance(eligible_count, bool):
        errors.append("eligible_count_unavailable")
        eligible_count = 0
    elif eligible_count not in {
        len(eligible_ids),
        len(new_eligible_ids),
        len(cumulative_observed_eligible_ids),
        len(eligible_ids) + len(deduped_eligible_ids),
    }:
        errors.append(
            "eligible_count_mismatch:"
            f"reported={eligible_count}:"
            f"observed_cumulative={len(eligible_ids)}:"
            f"observed_new={len(new_eligible_ids)}"
        )

    raw_applications = result.get("applications")
    applications = [] if raw_applications is None else raw_applications
    if not isinstance(applications, list) or not all(
        isinstance(row, dict) for row in applications
    ):
        return False, errors + ["applications_malformed"]

    application_ids: list[str] = []
    application_buckets: dict[str, str] = {}
    for row in applications:
        request_id = str(row.get("request_id") or "").strip()
        application_ids.append(request_id)
        bucket = str(row.get("bucket") or "")
        application_buckets[request_id] = bucket
        if bucket not in {"single", "retainer"}:
            errors.append(f"application_bucket_invalid:{request_id or 'missing'}")
        elif bucket != ("single" if request_id.isdigit() else "retainer"):
            errors.append(
                f"application_bucket_identity_mismatch:{request_id or 'missing'}"
            )
        if (
            request_id not in eligible_ids
            and request_id not in carried_application_ids
        ):
            errors.append(f"application_not_eligible:{request_id or 'missing'}")
        if not _request_url(row.get("url"), request_id, bucket):
            errors.append(f"application_url_invalid:{request_id or 'missing'}")
    if len(application_ids) != len(set(application_ids)):
        errors.append("application_request_duplicate")

    new_application_ids = [
        request_id
        for request_id in application_ids
        if request_id not in carried_application_ids
    ]
    carried_single_ids = {
        request_id for request_id in carried_application_ids if request_id.isdigit()
    }
    carried_retainer_ids = carried_application_ids - carried_single_ids
    new_eligible_single_ids = [
        request_id for request_id in new_eligible_ids if request_id.isdigit()
    ]
    new_eligible_retainer_ids = [
        request_id for request_id in new_eligible_ids if not request_id.isdigit()
    ]
    expected_single_applications = min(
        len(new_eligible_single_ids), max(0, target_applications - len(carried_single_ids))
    )
    expected_retainer_applications = min(
        len(new_eligible_retainer_ids),
        max(0, target_retainer_applications - len(carried_retainer_ids)),
    )
    expected_applications = expected_single_applications + expected_retainer_applications
    recovered_new_application_ids = (
        same_pass_verified_ids
        & set(new_eligible_ids)
        & fresh_submit_intent_ids
    )
    effective_new_application_ids = set(new_application_ids)
    effective_new_application_ids.update(recovered_new_application_ids)
    effective_new_single_ids = {
        request_id for request_id in effective_new_application_ids if request_id.isdigit()
    }
    effective_new_retainer_ids = effective_new_application_ids - effective_new_single_ids
    if len(effective_new_single_ids) != expected_single_applications:
        errors.append(
            "application_single_count_mismatch:"
            f"expected={expected_single_applications}:actual={len(effective_new_single_ids)}"
        )
    if len(effective_new_retainer_ids) != expected_retainer_applications:
        errors.append(
            "application_retainer_count_mismatch:"
            f"expected={expected_retainer_applications}:actual={len(effective_new_retainer_ids)}"
        )
    if len(effective_new_application_ids) != expected_applications:
        errors.append(
            "application_count_mismatch:"
            f"expected={expected_applications}:actual={len(effective_new_application_ids)}"
        )

    cumulative_application_ids = set(application_ids)
    cumulative_application_ids.update(same_pass_verified_ids)
    cumulative_retainer_ids = {
        request_id
        for request_id in cumulative_application_ids
        if not request_id.isdigit()
    }
    cumulative_single_ids = cumulative_application_ids - cumulative_retainer_ids

    required_source_ids_ordered = [
        str(value)
        for value in context.get("required_search_source_ids", [])
        if str(value)
    ]
    deferred_source_ids = _deferred_search_source_ids(
        deferred_coverage_cursor_path, required_source_ids_ordered
    )

    search_sources = current.get("search_sources")
    if not isinstance(search_sources, list) or not all(
        isinstance(row, dict) for row in search_sources
    ):
        search_sources = []
        errors.append("search_sources_malformed")
    source_ids: set[str] = set()
    source_urls: set[str] = set()
    source_rows: dict[str, dict[str, Any]] = {}
    for source in search_sources:
        source_id = str(source.get("source_id") or "")
        prior_source = source_rows.get(source_id)
        if not source_id:
            errors.append(f"search_source_duplicate:{source_id or 'missing'}")
            continue
        if prior_source is not None and not _search_url_advances(
            prior_source.get("url"), source.get("url")
        ):
            errors.append(f"search_source_duplicate:{source_id}")
            continue
        source_ids.add(source_id)
        source_rows[source_id] = source
        source_url = source.get("url")
        if not _search_url(source_url):
            errors.append(f"search_source_url_invalid:{source_id}")
        normalized_source_url = str(source_url or "")
        if normalized_source_url in source_urls:
            if "search_source_url_duplicate" not in errors:
                errors.append("search_source_url_duplicate")
        else:
            source_urls.add(normalized_source_url)
        _, source_shot_error = _owned_fresh_file(
            source.get("screenshot_path"), evidence_dir, min_mtime
        )
        if source_shot_error:
            errors.append(f"search_source_screenshot_{source_shot_error}:{source_id}")
        source_dom, source_dom_error = _owned_fresh_file(
            source.get("live_dom_path"), evidence_dir, min_mtime
        )
        if source_dom_error:
            errors.append(f"search_source_live_dom_{source_dom_error}:{source_id}")
        elif source_dom is not None:
            try:
                source_snapshot = _read_object(source_dom, "search_source_live_dom")
            except ContractError:
                errors.append(f"search_source_live_dom_invalid:{source_id}")
            else:
                if (
                    source_snapshot.get("observed") is not True
                    or source_snapshot.get("not_found") is True
                    or source_snapshot.get("url") != source_url
                ) and source_id not in deferred_source_ids:
                    errors.append(f"search_source_not_observed:{source_id}")
        inspected_count = source.get("inspected_count")
        if (
            not isinstance(inspected_count, int)
            or isinstance(inspected_count, bool)
            or inspected_count < 0
        ):
            errors.append(f"search_source_count_invalid:{source_id}")
    all_sources_exhausted = bool(source_rows) and all(
        source.get("exhausted") is True and source.get("has_next") is False
        for source in source_rows.values()
    )

    prior_inspected_request_ids: set[str] = set()
    if cursor_contract_path is not None:
        try:
            cursor_contract = _read_object(
                cursor_contract_path, "continuation_cursor_contract"
            )
        except ContractError as exc:
            errors.append(str(exc))
        else:
            cursor_source_id = str(cursor_contract.get("source_id") or "")
            cursor_next_url = str(cursor_contract.get("next_url") or "")
            raw_prior_ids = cursor_contract.get("prior_inspected_request_ids") or []
            if not isinstance(raw_prior_ids, list) or not all(
                _valid_request_id(value) for value in raw_prior_ids
            ):
                errors.append("continuation_prior_inspected_ids_invalid")
            else:
                prior_inspected_request_ids = {str(value) for value in raw_prior_ids}
            if not cursor_source_id or not _search_url(cursor_next_url):
                errors.append("continuation_cursor_contract_invalid")
            elif cursor_source_id not in source_rows:
                errors.append(
                    f"continuation_cursor_not_advanced:{cursor_source_id}"
                )
            else:
                observed_source_url = source_rows[cursor_source_id].get("url")
                if not (
                    _same_search_url(observed_source_url, cursor_next_url)
                    or _search_url_advances(cursor_next_url, observed_source_url)
                ):
                    errors.append(
                        f"continuation_cursor_not_advanced:{cursor_source_id}"
                    )

    required_source_ids = {
        str(value)
        for value in context.get("required_search_source_ids", [])
        if str(value)
    }
    retainer_source = source_rows.get("retainer:new")
    eligible_retainer_ids = {
        request_id
        for request_id in eligible_ids
        if not request_id.isdigit()
    }
    if len(cumulative_single_ids) < target_applications:
        if source_ids != required_source_ids or not all_sources_exhausted:
            new_inspected_count = len(set(seen) - prior_inspected_request_ids)
            if (
                min_new_inspections > 0
                and new_inspected_count < min_new_inspections
            ):
                errors.append(
                    "under_target_inspection_quantity_too_low:"
                    f"actual={new_inspected_count}:minimum={min_new_inspections}"
                )
            errors.append("under_target_search_not_exhausted")
    elif "single:new" not in source_ids:
        errors.append("newest_search_evidence_missing")
    # A3 (2026-07-30): the retainer demands are contract-driven, not unconditional.
    # With target_retainer_applications frozen at zero the pass closes on single
    # evidence alone; the block stays so the contract remains the only thing that
    # decides, rather than a deletion someone has to re-derive to reverse.
    if (
        target_retainer_applications > 0
        and len(cumulative_single_ids) >= target_applications
    ):
        if "retainer:new" not in source_ids:
            errors.append("retainer_search_evidence_missing")
        elif len(cumulative_retainer_ids) < target_retainer_applications:
            if eligible_retainer_ids:
                errors.append("retainer_application_missing")
            elif (
                retainer_source is None
                or retainer_source.get("exhausted") is not True
                or retainer_source.get("has_next") is not False
            ):
                errors.append("retainer_search_not_exhausted")

    # A pre-click intent is the ONLY evidence class the readback may retire. A
    # *-submitted.png / .json proof is written after the helper read 応募しました,
    # and a "confirmed" intent says the same; either of those disagreeing with the
    # applied page is a real three-way conflict and stays an error.
    fresh_submit_proof_ids = _fresh_submit_ids(
        evidence_root, min_mtime, evidence_dir=evidence_dir
    )
    retired_prepared_ids = (
        _fresh_submit_intent_ids(
            evidence_root, min_mtime, frozenset({"prepared"})
        )
        - _fresh_submit_intent_ids(
            evidence_root, min_mtime, frozenset({"confirmed"})
        )
        - fresh_submit_proof_ids
    ) & _readback_absent_ids(evidence_dir, min_mtime)
    for request_id in sorted(
        (fresh_submit_proof_ids | fresh_submit_intent_ids)
        - cumulative_application_ids
        - retired_prepared_ids
    ):
        errors.append(f"unreported_submit_evidence:{request_id}")
    readback_path = evidence_dir / "code-applied-readback.json"
    readback_ids: set[str] = set()
    readback_paths: set[str] = set()
    if cumulative_application_ids:
        owned_readback, readback_error = _owned_fresh_file(
            readback_path, evidence_dir, min_mtime
        )
        if readback_error:
            owned_readback = None
        if owned_readback is not None:
            try:
                readback = _read_object(owned_readback, "applied_page_readback")
            except ContractError:
                readback = {}
            if (
                readback.get("source") == "code_owned_cdp_readback"
                and readback.get("observed") is True
                and readback.get("not_found") is False
            ):
                readback_paths = {
                    urlsplit(str(value)).path.rstrip("/")
                    for value in (
                        readback.get("urls")
                        or [readback.get("url")]
                    )
                }
                allowed_readback_paths = {
                    "/mypage/job_matching/applied/offers",
                    "/mypage/job_matching/applied/outsource_applications",
                }
                if not readback_paths or not readback_paths.issubset(
                    allowed_readback_paths
                ):
                    readback_paths = set()
                readback_ids = {
                    str(value)
                    for value in (readback.get("request_ids") or [])
                    if _valid_request_id(value)
                }
    for request_id in sorted(cumulative_application_ids):
        row = ledger_rows.get(request_id)
        canonical_intent_recovery = (
            request_id in fresh_submit_intent_ids
            and row is not None
            and row.get("recorded_by") == "application_report_intent_recovery"
            and row.get("submit_verified") is True
            and row.get("applied_page_verified") is True
        )
        if (
            not _has_fresh_submit_proof(
                evidence_root, request_id, min_mtime, evidence_dir=evidence_dir
            )
            and not canonical_intent_recovery
        ):
            errors.append(f"application_submit_evidence_missing:{request_id}")
        if row is None:
            errors.append(f"application_ledger_missing:{request_id}")
        if request_id not in readback_ids:
            errors.append(f"application_applied_page_readback_missing:{request_id}")
        required_readback_path = (
            "/mypage/job_matching/applied/offers"
            if request_id.isdigit()
            else "/mypage/job_matching/applied/outsource_applications"
        )
        if request_id in readback_ids and required_readback_path not in readback_paths:
            errors.append(
                f"application_applied_page_route_missing:{request_id}"
            )
        if row is not None and (
            row.get("submit_verified") is not True
            or row.get("applied_page_verified") is not True
        ):
            errors.append(f"application_ledger_verification_missing:{request_id}")
    return not errors, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--prep-json", required=True)
    build.add_argument("--applied", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--context", required=True, type=Path)
    validate.add_argument("--runner-summary", required=True, type=Path)
    validate.add_argument("--evidence-dir", required=True, type=Path)
    validate.add_argument("--evidence-root", required=True, type=Path)
    validate.add_argument("--ledger", required=True, type=Path)
    validate.add_argument("--min-mtime", required=True, type=float)
    validate.add_argument("--pass-id")
    validate.add_argument("--cursor-contract", type=Path)
    validate.add_argument("--min-new-inspections", type=int, default=0)
    validate.add_argument("--deferred-coverage-cursor", type=Path)
    continuable = subparsers.add_parser("continuable")
    continuable.add_argument("--gate-result", required=True, type=Path)
    continuable.add_argument("--ledger", required=True, type=Path)
    continuable.add_argument("--context", required=True, type=Path)
    continuable.add_argument("--pass-id", required=True)
    terminal = subparsers.add_parser("terminal-outcome")
    terminal.add_argument("--gate-result", required=True, type=Path)
    terminal.add_argument("--ledger", required=True, type=Path)
    terminal.add_argument("--context", required=True, type=Path)
    terminal.add_argument("--pass-id", required=True)
    terminal.add_argument("--output", type=Path)
    terminal.add_argument("--shortfall-ledger", type=Path)
    next_cursor = subparsers.add_parser("next-cursor")
    next_cursor.add_argument("--runner-summary", required=True, type=Path)
    next_cursor.add_argument("--context", required=True, type=Path)
    next_cursor.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "build":
            prep = json.loads(args.prep_json)
            context = build_context(prep, args.applied)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(context, ensure_ascii=False, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            print(json.dumps({"ok": True, "output": str(args.output)}, separators=(",", ":")))
            return 0
        if args.command == "continuable":
            allowed, verified_count, target = continuation_state(
                gate_result_path=args.gate_result,
                ledger_path=args.ledger,
                context_path=args.context,
                pass_id=args.pass_id,
            )
            print(
                json.dumps(
                    {
                        "continuable": allowed,
                        "verified_count": verified_count,
                        "target": target,
                    },
                    separators=(",", ":"),
                )
            )
            return 0 if allowed else 1
        if args.command == "terminal-outcome":
            record = terminal_outcome(
                gate_result_path=args.gate_result,
                ledger_path=args.ledger,
                context_path=args.context,
                pass_id=args.pass_id,
            )
            payload = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            # Both files are written for every outcome, break included. A record
            # that only keeps the good news is the failure mode E7 exists to end.
            if args.output is not None:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(payload + "\n", encoding="utf-8")
            if args.shortfall_ledger is not None:
                args.shortfall_ledger.parent.mkdir(parents=True, exist_ok=True)
                with args.shortfall_ledger.open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(
                            {
                                "recorded_at": int(time.time()),
                                **{
                                    key: value
                                    for key, value in record.items()
                                    if key != "evidence_defects"
                                },
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        + "\n"
                    )
            print(payload)
            return 0 if record["outcome"] in {"shortfall", "clean"} else 1
        if args.command == "next-cursor":
            cursor = next_search_cursor(args.runner_summary, args.context)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(cursor, ensure_ascii=False, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {"ok": True, "output": str(args.output), **cursor},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            return 0
        ok, errors = validate_result(
            context_path=args.context,
            summary_path=args.runner_summary,
            evidence_dir=args.evidence_dir,
            evidence_root=args.evidence_root,
            ledger_path=args.ledger,
            min_mtime=args.min_mtime,
            pass_id=args.pass_id,
            cursor_contract_path=args.cursor_contract,
            min_new_inspections=max(0, args.min_new_inspections),
            deferred_coverage_cursor_path=args.deferred_coverage_cursor,
        )
        print(json.dumps({"ok": ok, "errors": errors}, ensure_ascii=False, separators=(",", ":")))
        return 0 if ok else 1
    except (ContractError, json.JSONDecodeError) as exc:
        print(
            json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, separators=(",", ":")),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
