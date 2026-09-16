#!/usr/bin/env python3
"""Canonical, hash-bound input to the browser-isolated application planner.

This module contains only deterministic parsing, identity binding, and durable
serialization. It intentionally has no CDP, WebSocket, or model-provider imports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


VERSION = 1
MAX_BATCH = 40
# One ceiling, read by every check. Raising the application target on 2026-08-06 lifted
# the number in b2_result_gate and application_parent but not the two copies here, and
# the first pass after the raise died on objective_caps_invalid. A cap written in four
# files is four opinions, not a contract.
MAX_APPLICATIONS_CEILING = 20
MAX_SOURCES = 128
_REQUEST_PATHS = (
    re.compile(r"^/requests/([0-9]+)$"),
    re.compile(r"^/job_matching/requests/([0-9]+)$"),
)
_RETAINER_PATH = re.compile(r"^/job_matching/outsources/([0-7][0-9A-HJKMNP-TV-Z]{25})$")
_RETAINER_ULID = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")
_TRACKING_QUERY_KEYS = frozenset({"fbclid", "gclid", "ref"})

_ROOT_FIELDS = frozenset({
    "version", "pass_id", "lease_fence", "observed_at", "objective",
    "search_sources", "request_details", "already_applied_ids", "snapshot_sha256",
})
_LEASE_FIELDS = frozenset({"task", "token", "generation"})
_OBJECTIVE_FIELDS = frozenset({
    "target_applications", "max_applications", "required_search_source_ids",
})
_SOURCE_FIELDS = frozenset({
    "source_id", "url", "page_index", "card_request_ids", "has_next", "exhausted",
    "screenshot_sha256", "dom_sha256",
})
_DETAIL_FIELDS = frozenset({
    "request_id", "canonical_url", "title", "category", "visible_text",
    "accepting_applications", "budget_min_jpy", "budget_max_jpy", "applicants_count",
    "contracted_count", "applicants", "application_questions", "observed_at", "content_sha256",
})
_QUESTION_FIELDS = frozenset({"question", "required", "max_length"})
_APPLICANT_FIELDS = frozenset({
    "user_id", "name", "applied_at", "profile_url", "rating", "sales_count",
    "public_services", "profile_summary",
})
_PROFILE_PATH = re.compile(r"^/users/([0-9]+)$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_HEX_32 = re.compile(r"^[0-9a-f]{32}$")


class SnapshotContractError(ValueError):
    """The collector did not produce an envelope safe to show a planner."""


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def canonical_request_id(value: object) -> str:
    request_id = str(value).strip()
    if not (request_id.isdigit() or _RETAINER_ULID.fullmatch(request_id)):
        raise SnapshotContractError("request_id_must_be_decimal")
    return request_id


def _identity_sort_key(identity: str) -> tuple[int, int | str]:
    """Sort legacy numeric IDs before retainer ULIDs without changing either form."""
    return (0, int(identity)) if identity.isdigit() else (1, identity)


def _is_canonical_identity(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return canonical_request_id(value) == value
    except SnapshotContractError:
        return False


def canonical_request_url(value: object, *, request_id: object | None = None) -> str:
    parsed = urlsplit(str(value).strip())
    if parsed.scheme.lower() != "https" or parsed.hostname is None:
        raise SnapshotContractError("request_url_must_be_https")
    if parsed.hostname.lower().removeprefix("www.") != "coconala.com":
        raise SnapshotContractError("request_url_host_invalid")
    found_id = None
    retainer = False
    for pattern in _REQUEST_PATHS:
        matched = pattern.fullmatch(parsed.path.rstrip("/"))
        if matched:
            found_id = matched.group(1)
            break
    if found_id is None:
        matched = _RETAINER_PATH.fullmatch(parsed.path.rstrip("/"))
        if matched:
            found_id = matched.group(1)
            retainer = True
    if found_id is None:
        raise SnapshotContractError("request_url_path_invalid")
    if request_id is not None and found_id != canonical_request_id(request_id):
        raise SnapshotContractError("request_url_identity_mismatch")
    path = f"/job_matching/outsources/{found_id}" if retainer else f"/requests/{found_id}"
    return f"https://coconala.com{path}"


def canonical_source_url(value: object) -> str:
    parsed = urlsplit(str(value).strip())
    if parsed.scheme.lower() != "https" or parsed.hostname is None:
        raise SnapshotContractError("source_url_must_be_https")
    if parsed.hostname.lower().removeprefix("www.") != "coconala.com":
        raise SnapshotContractError("source_url_host_invalid")
    path = parsed.path.rstrip("/") or "/"
    if path not in {"/requests", "/job_matching/outsources"}:
        raise SnapshotContractError("source_url_path_invalid")
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_QUERY_KEYS and not key.lower().startswith("utm_")
    ]
    return urlunsplit(("https", "coconala.com", path, urlencode(sorted(query)), ""))


def normalize_visible_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    result: list[str] = []
    previous_blank = False
    for line in text.split("\n"):
        line = line.rstrip()
        is_blank = not line.strip()
        if is_blank:
            if previous_blank:
                continue
            result.append("")
        else:
            result.append(line)
        previous_blank = is_blank
    while result and not result[-1]:
        result.pop()
    return "\n".join(result)


def stable_request_text(value: object) -> str:
    """Return the client-authored brief and official Q&A without marketplace chrome."""
    text = normalize_visible_text(value)
    marker = "募集内容\n"
    if marker in text:
        text = text.split(marker, 1)[1]
    question_marker = "\n募集内容についての質問"
    questions = ""
    if question_marker in text:
        question_body = text.split(question_marker, 1)[1]
        for suffix in ("\n応募する", "\n募集者情報", "\nこの募集を通報する", "\nこの募集内容に似ている仕事"):
            if suffix in question_body:
                question_body = question_body.split(suffix, 1)[0]
        questions = question_marker + question_body
    for suffix in ("\n応募者一覧", question_marker):
        if suffix in text:
            text = text.split(suffix, 1)[0]
    return (text.rstrip() + questions).strip()


def detail_content_payload(detail: dict[str, object]) -> dict[str, object]:
    """Single source of truth for the pre-submit stable content fence."""
    return {
        "request_id": detail["request_id"],
        "canonical_url": detail["canonical_url"],
        "title": detail["title"],
        "category": detail["category"],
        "brief": stable_request_text(detail["visible_text"]),
        "accepting_applications": detail["accepting_applications"],
        "budget_min_jpy": detail["budget_min_jpy"],
        "budget_max_jpy": detail["budget_max_jpy"],
        "application_questions": detail["application_questions"],
    }


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json_bytes(payload) + b"\n"
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _nonempty_text(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SnapshotContractError(f"{field}_required")
    return text


def _nonnegative_int_or_none(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SnapshotContractError(f"{field}_must_be_nonnegative_integer_or_null")
    return value


def _normalise_application_questions(value: object) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 20:
        raise SnapshotContractError("application_questions_invalid")
    result: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != _QUESTION_FIELDS:
            raise SnapshotContractError("application_question_fields_invalid")
        question = _nonempty_text(item["question"], "application_question")
        required = item["required"]
        maximum = item["max_length"]
        if len(question) > 1000:
            raise SnapshotContractError("application_question_too_long")
        if not isinstance(required, bool):
            raise SnapshotContractError("application_question_required_invalid")
        if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 5000:
            raise SnapshotContractError("application_question_max_length_invalid")
        result.append({"question": question, "required": required, "max_length": maximum})
    if len({str(item["question"]) for item in result}) != len(result):
        raise SnapshotContractError("application_questions_duplicate")
    return result


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list):
        raise SnapshotContractError(f"{field}_must_be_array")
    return [_nonempty_text(item, field) for item in value]


def _normalise_applicants(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or len(value) > 3:
        raise SnapshotContractError("applicants_must_be_array_max_3")
    result: list[dict[str, object]] = []
    for applicant in value:
        if not isinstance(applicant, dict) or set(applicant) != _APPLICANT_FIELDS:
            raise SnapshotContractError("applicant_fields_invalid")
        name = str(applicant["name"] or "").strip()
        applied_at = str(applicant["applied_at"] or "").strip()
        profile_summary = str(applicant["profile_summary"] or "").strip()
        if not name or not applied_at or not profile_summary:
            continue
        user_id = canonical_request_id(applicant["user_id"])
        parsed = urlsplit(str(applicant["profile_url"]).strip())
        matched = _PROFILE_PATH.fullmatch(parsed.path.rstrip("/"))
        if (
            parsed.scheme.lower() != "https"
            or parsed.hostname is None
            or parsed.hostname.lower().removeprefix("www.") != "coconala.com"
            or matched is None
            or matched.group(1) != user_id
            or parsed.query
            or parsed.fragment
        ):
            raise SnapshotContractError("applicant_profile_url_invalid")
        rating = applicant["rating"]
        if rating is not None and (
            isinstance(rating, bool)
            or not isinstance(rating, (int, float))
            or not 0 <= float(rating) <= 5
        ):
            raise SnapshotContractError("applicant_rating_invalid")
        services = _string_list(applicant["public_services"], "public_services")
        if len(services) > 5:
            raise SnapshotContractError("public_services_max_5")
        result.append({
            "user_id": user_id,
            "name": name,
            "applied_at": applied_at,
            "profile_url": f"https://coconala.com/users/{user_id}",
            "rating": None if rating is None else float(rating),
            "sales_count": _nonnegative_int_or_none(applicant["sales_count"], "sales_count"),
            "public_services": services,
            "profile_summary": profile_summary,
        })
    return result


def _normalise_source(source: object) -> dict[str, object]:
    if not isinstance(source, dict):
        raise SnapshotContractError("search_source_must_be_object")
    try:
        source_id = _nonempty_text(source["source_id"], "source_id")
        page_index = source["page_index"]
        if isinstance(page_index, bool) or not isinstance(page_index, int) or page_index < 1:
            raise SnapshotContractError("source_page_index_invalid")
        card_ids = [canonical_request_id(value) for value in source["card_request_ids"]]
        if len(card_ids) > MAX_BATCH or len(set(card_ids)) != len(card_ids):
            raise SnapshotContractError("source_card_request_ids_invalid")
        has_next = source["has_next"]
        exhausted = source["exhausted"]
        if not isinstance(has_next, bool) or not isinstance(exhausted, bool):
            raise SnapshotContractError("source_pagination_flags_invalid")
        if exhausted == has_next:
            raise SnapshotContractError("source_pagination_contract_invalid")
        screenshot_sha256 = str(source["screenshot_sha256"])
        dom_sha256 = str(source["dom_sha256"])
    except KeyError as error:
        raise SnapshotContractError(f"source_missing:{error.args[0]}") from error
    if not _HEX_64.fullmatch(screenshot_sha256) or not _HEX_64.fullmatch(dom_sha256):
        raise SnapshotContractError("source_artifact_hash_invalid")
    return {
        "source_id": source_id,
        "url": canonical_source_url(source["url"]),
        "page_index": page_index,
        "card_request_ids": card_ids,
        "has_next": has_next,
        "exhausted": exhausted,
        "screenshot_sha256": screenshot_sha256,
        "dom_sha256": dom_sha256,
    }


def _normalise_detail(detail: object) -> dict[str, object]:
    if not isinstance(detail, dict):
        raise SnapshotContractError("request_detail_must_be_object")
    try:
        request_id = canonical_request_id(detail["request_id"])
        visible_text = normalize_visible_text(detail["visible_text"])
        if not visible_text:
            raise SnapshotContractError("visible_text_required")
        accepting = detail["accepting_applications"]
        if not isinstance(accepting, bool):
            raise SnapshotContractError("accepting_applications_must_be_boolean")
        result = {
            "request_id": request_id,
            "canonical_url": canonical_request_url(
                detail["canonical_url"], request_id=request_id
            ),
            "title": _nonempty_text(detail["title"], "title"),
            "category": _nonempty_text(detail["category"], "category"),
            "visible_text": visible_text,
            "accepting_applications": accepting,
            "budget_min_jpy": _nonnegative_int_or_none(
                detail["budget_min_jpy"], "budget_min_jpy"
            ),
            "budget_max_jpy": _nonnegative_int_or_none(
                detail["budget_max_jpy"], "budget_max_jpy"
            ),
            "applicants_count": _nonnegative_int_or_none(
                detail["applicants_count"], "applicants_count"
            ),
            "contracted_count": _nonnegative_int_or_none(
                detail["contracted_count"], "contracted_count"
            ),
            "applicants": _normalise_applicants(detail["applicants"]),
            "application_questions": _normalise_application_questions(
                detail.get("application_questions", [])
            ),
            "observed_at": _nonempty_text(detail["observed_at"], "detail_observed_at"),
        }
    except KeyError as error:
        raise SnapshotContractError(f"detail_missing:{error.args[0]}") from error
    # Observation time proves freshness of the capture, but it is not content.
    # Including it made every parent reread appear stale even when the rendered
    # request was byte-for-byte unchanged.
    # Applicant counts, related-job cards, and relative-time labels can change
    # seconds after collection.  They are observation data, not contract data,
    # and made every pre-submit reread falsely stale.  The freshness fence keeps
    # the stable identity, client-authored brief, budget, and open-state only.
    result["content_sha256"] = sha256_json(detail_content_payload(result))
    return result


def build_envelope(collector: object) -> dict[str, object]:
    """Normalize a parent collector result into the only planner input contract."""
    if not isinstance(collector, dict):
        raise SnapshotContractError("collector_must_be_object")
    try:
        lease = collector["lease_fence"]
        if not isinstance(lease, dict):
            raise SnapshotContractError("lease_fence_must_be_object")
        task = _nonempty_text(lease["task"], "lease_task")
        token = str(lease["token"])
        generation = lease["generation"]
        if not _HEX_32.fullmatch(token):
            raise SnapshotContractError("lease_token_must_be_128_bit_hex")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise SnapshotContractError("lease_generation_invalid")
        objective = collector["objective"]
        if not isinstance(objective, dict):
            raise SnapshotContractError("objective_must_be_object")
        target = objective["target_applications"]
        maximum = objective["max_applications"]
        if (
            isinstance(target, bool) or isinstance(maximum, bool)
            or not isinstance(target, int) or not isinstance(maximum, int)
            or target < 1 or maximum < target or maximum > MAX_APPLICATIONS_CEILING
        ):
            raise SnapshotContractError("objective_caps_invalid")
        required_sources = _string_list(
            objective["required_search_source_ids"], "required_search_source_ids"
        )
        if len(set(required_sources)) != len(required_sources):
            raise SnapshotContractError("required_search_source_ids_duplicate")
        sources = [_normalise_source(item) for item in collector["search_sources"]]
        details = [_normalise_detail(item) for item in collector["request_details"]]
        already_applied = [
            canonical_request_id(value) for value in collector["already_applied_ids"]
        ]
    except KeyError as error:
        raise SnapshotContractError(f"collector_missing:{error.args[0]}") from error
    if not sources or len(sources) > MAX_SOURCES:
        raise SnapshotContractError("search_sources_batch_invalid")
    if len({source["source_id"] for source in sources}) != len(sources):
        raise SnapshotContractError("search_source_ids_duplicate")
    if not set(required_sources).issubset({source["source_id"] for source in sources}):
        raise SnapshotContractError("required_search_source_missing")
    if len(details) > MAX_BATCH or len({detail["request_id"] for detail in details}) != len(details):
        raise SnapshotContractError("request_detail_ids_invalid")
    card_ids = [
        request_id
        for source in sources
        for request_id in source["card_request_ids"]
    ]
    if len(set(card_ids)) != len(card_ids):
        raise SnapshotContractError("card_request_ids_duplicate_across_sources")
    if set(card_ids) != {detail["request_id"] for detail in details}:
        raise SnapshotContractError("card_detail_identity_incomplete")
    if len(set(already_applied)) != len(already_applied):
        raise SnapshotContractError("already_applied_ids_duplicate")
    envelope: dict[str, object] = {
        "version": VERSION,
        "pass_id": _nonempty_text(collector["pass_id"], "pass_id"),
        "lease_fence": {"task": task, "token": token, "generation": generation},
        "observed_at": _nonempty_text(collector["observed_at"], "observed_at"),
        "objective": {
            "target_applications": target,
            "max_applications": maximum,
            "required_search_source_ids": required_sources,
        },
        "search_sources": sources,
        "request_details": details,
        "already_applied_ids": sorted(set(already_applied), key=_identity_sort_key),
    }
    envelope["snapshot_sha256"] = sha256_json(envelope)
    errors = validate_snapshot(envelope)
    if errors:
        raise SnapshotContractError(";".join(errors))
    return envelope


def _keys_equal(value: object, expected: frozenset[str], at: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{at}_must_be_object")
        return False
    actual = set(value)
    missing = sorted(expected - actual)
    additional = sorted(actual - expected)
    if missing:
        errors.append(f"{at}_missing:{','.join(missing)}")
    if additional:
        errors.append(f"{at}_additional:{','.join(additional)}")
    return not missing and not additional


def validate_snapshot(envelope: object) -> list[str]:
    """Return deterministic contract errors; no planner judgment is performed here."""
    errors: list[str] = []
    if not _keys_equal(envelope, _ROOT_FIELDS, "snapshot", errors):
        return errors
    assert isinstance(envelope, dict)
    if envelope.get("version") != VERSION:
        errors.append("snapshot_version_invalid")
    if not isinstance(envelope.get("pass_id"), str) or not envelope["pass_id"]:
        errors.append("snapshot_pass_id_invalid")
    if not _keys_equal(envelope["lease_fence"], _LEASE_FIELDS, "lease_fence", errors):
        return errors
    lease = envelope["lease_fence"]
    assert isinstance(lease, dict)
    if not isinstance(lease["task"], str) or not lease["task"]:
        errors.append("lease_task_invalid")
    if not isinstance(lease["token"], str) or not _HEX_32.fullmatch(lease["token"]):
        errors.append("lease_token_invalid")
    if isinstance(lease["generation"], bool) or not isinstance(lease["generation"], int) or lease["generation"] < 1:
        errors.append("lease_generation_invalid")
    if not isinstance(envelope["observed_at"], str) or not envelope["observed_at"]:
        errors.append("snapshot_observed_at_invalid")
    if not _keys_equal(envelope["objective"], _OBJECTIVE_FIELDS, "objective", errors):
        return errors
    objective = envelope["objective"]
    assert isinstance(objective, dict)
    if (
        isinstance(objective["target_applications"], bool)
        or isinstance(objective["max_applications"], bool)
        or not isinstance(objective["target_applications"], int)
        or not isinstance(objective["max_applications"], int)
        or objective["target_applications"] < 1
        or objective["max_applications"] < objective["target_applications"]
        or objective["max_applications"] > MAX_APPLICATIONS_CEILING
    ):
        errors.append("objective_caps_invalid")
    if not isinstance(objective["required_search_source_ids"], list) or not objective["required_search_source_ids"]:
        errors.append("objective_required_sources_invalid")
    elif not all(isinstance(item, str) and item for item in objective["required_search_source_ids"]):
        errors.append("objective_required_sources_invalid")
    elif len(set(objective["required_search_source_ids"])) != len(objective["required_search_source_ids"]):
        errors.append("objective_required_sources_duplicate")
    sources = envelope["search_sources"]
    details = envelope["request_details"]
    applied = envelope["already_applied_ids"]
    if not isinstance(sources, list) or not sources or len(sources) > MAX_SOURCES:
        errors.append("search_sources_invalid")
    else:
        source_ids: list[str] = []
        card_ids: list[str] = []
        for index, source in enumerate(sources):
            if not _keys_equal(source, _SOURCE_FIELDS, f"search_source[{index}]", errors):
                continue
            assert isinstance(source, dict)
            source_ids.append(str(source["source_id"]))
            if not isinstance(source["source_id"], str) or not source["source_id"]:
                errors.append("source_id_invalid")
            try:
                if source["url"] != canonical_source_url(source["url"]):
                    errors.append("source_url_not_canonical")
            except SnapshotContractError:
                errors.append("source_url_invalid")
            if isinstance(source["page_index"], bool) or not isinstance(source["page_index"], int) or source["page_index"] < 1:
                errors.append("source_page_index_invalid")
            if not isinstance(source["card_request_ids"], list) or len(source["card_request_ids"]) > MAX_BATCH:
                errors.append("source_card_ids_invalid")
            else:
                ids = source["card_request_ids"]
                if not all(
                    _is_canonical_identity(item)
                    for item in ids
                ) or len(set(ids)) != len(ids):
                    errors.append("source_card_ids_invalid")
                card_ids.extend(ids)
            if not isinstance(source["has_next"], bool) or not isinstance(source["exhausted"], bool) or source["has_next"] == source["exhausted"]:
                errors.append("source_pagination_contract_invalid")
            for key in ("screenshot_sha256", "dom_sha256"):
                if not isinstance(source[key], str) or not _HEX_64.fullmatch(source[key]):
                    errors.append(f"source_{key}_invalid")
        if len(set(source_ids)) != len(source_ids):
            errors.append("search_source_ids_duplicate")
        if len(set(card_ids)) != len(card_ids):
            errors.append("card_request_ids_duplicate_across_sources")
        if isinstance(objective["required_search_source_ids"], list) and not set(objective["required_search_source_ids"]).issubset(set(source_ids)):
            errors.append("required_search_source_missing")
    if not isinstance(details, list) or len(details) > MAX_BATCH:
        errors.append("request_details_invalid")
    else:
        detail_ids: list[str] = []
        for index, detail in enumerate(details):
            if not _keys_equal(detail, _DETAIL_FIELDS, f"request_detail[{index}]", errors):
                continue
            assert isinstance(detail, dict)
            request_id = detail["request_id"]
            detail_ids.append(str(request_id))
            if not _is_canonical_identity(request_id):
                errors.append("detail_request_id_invalid")
            try:
                if detail["canonical_url"] != canonical_request_url(detail["canonical_url"], request_id=request_id):
                    errors.append("detail_url_not_canonical")
            except SnapshotContractError:
                errors.append("detail_url_invalid")
            if not isinstance(detail["title"], str) or not detail["title"]:
                errors.append("detail_title_invalid")
            if not isinstance(detail["category"], str) or not detail["category"]:
                errors.append("detail_category_invalid")
            if not isinstance(detail["visible_text"], str) or not detail["visible_text"] or detail["visible_text"] != normalize_visible_text(detail["visible_text"]):
                errors.append("detail_visible_text_invalid")
            if not isinstance(detail["accepting_applications"], bool):
                errors.append("detail_accepting_invalid")
            for key in ("budget_min_jpy", "budget_max_jpy", "applicants_count", "contracted_count"):
                value = detail[key]
                if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                    errors.append(f"detail_{key}_invalid")
            try:
                if detail["applicants"] != _normalise_applicants(detail["applicants"]):
                    errors.append("detail_applicants_not_normalised")
            except SnapshotContractError:
                errors.append("detail_applicants_invalid")
            try:
                if detail["application_questions"] != _normalise_application_questions(
                    detail["application_questions"]
                ):
                    errors.append("detail_application_questions_not_normalised")
            except SnapshotContractError:
                errors.append("detail_application_questions_invalid")
            if not isinstance(detail["observed_at"], str) or not detail["observed_at"]:
                errors.append("detail_observed_at_invalid")
            expected_hash = sha256_json(detail_content_payload(detail))
            if detail["content_sha256"] != expected_hash:
                errors.append("detail_content_sha256_mismatch")
        if len(set(detail_ids)) != len(detail_ids):
            errors.append("request_detail_ids_duplicate")
        if isinstance(sources, list) and sources and not errors:
            all_cards = [identifier for source in sources for identifier in source.get("card_request_ids", [])]
            if set(all_cards) != set(detail_ids):
                errors.append("card_detail_identity_incomplete")
    if (
        not isinstance(applied, list)
        or not all(
            _is_canonical_identity(item)
            for item in applied
        )
        or len(set(applied)) != len(applied)
    ):
        errors.append("already_applied_ids_invalid")
    snapshot_without_hash = {key: value for key, value in envelope.items() if key != "snapshot_sha256"}
    if not isinstance(envelope["snapshot_sha256"], str) or envelope["snapshot_sha256"] != sha256_json(snapshot_without_hash):
        errors.append("snapshot_sha256_mismatch")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--input", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--snapshot", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            envelope = build_envelope(json.loads(args.input.read_text(encoding="utf-8")))
            _atomic_json(args.output, envelope)
            return 0
        envelope = json.loads(args.snapshot.read_text(encoding="utf-8"))
        errors = validate_snapshot(envelope)
        if errors:
            print(json.dumps({"ok": False, "errors": errors}, separators=(",", ":")))
            return 2
        print(json.dumps({"ok": True, "snapshot_sha256": envelope["snapshot_sha256"]}, separators=(",", ":")))
        return 0
    except (OSError, ValueError, SnapshotContractError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, separators=(",", ":")), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
