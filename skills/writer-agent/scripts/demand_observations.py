#!/usr/bin/env python3
"""Read existing publisher and funnel receipts into demand-card observations.

The adapters are intentionally read-only. They never instantiate a writer-owned
store in write mode, append a ledger row, or turn an absent measurement into 0.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import quote, urlsplit


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from claim_store import canonicalize_url  # noqa: E402


class DemandObservationError(ValueError):
    """A durable receipt cannot be converted to a trustworthy observation."""


FULL_BODY_MIN_CHARS = 256
FULL_BODY_MAX_BYTES = 2 * 1024 * 1024
FULL_BODY_CAPTURE_METHOD = "http_full_body"
PUBLISHER_SOURCE_FAMILY = "publisher_opportunity"
CIVO_SOURCE_ID = "civo"
CIVO_OFFICIAL_URL = "https://www.civo.com/write-for-us"
CIVO_EVIDENCE_PROFILE = "civo-write-for-us-v1"
TECHI_SOURCE_ID = "techi-author"
TECHI_OFFICIAL_URL = "https://www.techi.com/authors/apply"
TECHI_EVIDENCE_PROFILE = "techi-author-v1"
CACHED_PUBLISHER_MAX_AGE_SECONDS = 7 * 24 * 60 * 60

_CIVO_TITLE_UNIT = "civo write for us"
_CIVO_SUBMIT_ACTION_UNIT = "submit your idea"
_CIVO_START_WRITING_UNIT = "start writing"
_CIVO_ACCEPTANCE_SENTENCE_UNIT = (
    "once your idea is accepted by our content team, start writing and submit a first draft"
)
_CIVO_PAYMENT_HEADING_UNIT = "get paid"
_CIVO_PAYMENT_SENTENCE_UNIT = (
    "when your tutorial or guide is approved, edited, and published, "
    "you will be paid via paypal or civo credits"
)
_CIVO_LABEL_UNITS = frozenset(
    {
        _CIVO_TITLE_UNIT,
        _CIVO_SUBMIT_ACTION_UNIT,
        _CIVO_START_WRITING_UNIT,
        _CIVO_PAYMENT_HEADING_UNIT,
    }
)
_CIVO_SENTENCE_SPLIT_RE = re.compile(r"(?:\r?\n+|(?<=[.!?])\s+)")
_CIVO_MAX_MARKDOWN_UNITS = 4096

_RECIPIENT = r"(?:you(?:['’]ll)?|(?:the\s+)?(?:writer|author|contributor)s?)"
_RECIPIENT_CORE = r"(?:you|(?:the\s+)?(?:writer|author|contributor)s?)"
_PAYER = (
    r"(?:we|our\s+(?:team|editor(?:ial)?(?:\s+team)?|company)|"
    r"(?:the\s+)?(?:publisher|editor(?:ial)?(?:\s+team)?|company))"
)
_PAYMENT_NEGATION_RE = re.compile(
    r"\b(?:no|not(?!\s+only\b)|never|without|uncompensated|unpaid|"
    r"unrewarded|cannot|can't|can’t|won't|won’t|doesn't|doesn’t|don't|"
    r"don’t|isn't|isn’t|aren't|aren’t|neither|nor)\b"
)
_AUTHOR_ATTRIBUTION_RE = re.compile(
    r"\b(?:author|authors|writer|writers|contributor|contributors)\s+credits?\b"
)
_RECIPIENT_COMPENSATION_RE = re.compile(
    rf"\b{_RECIPIENT}\s+"
    r"(?:(?:will|may|can|should|must)\s+)?"
    r"(?:get\s+(?:paid|payment|compensation|(?:[a-z][\w-]*\s+)?credits?|"
    r"(?:[a-z][\w-]*\s+)?paypal)|"
    r"be\s+(?:paid|compensated|rewarded)|"
    r"(?:receive|receives|received|earn|earns|earned)\s+"
    r"(?:payment|compensation|pay|(?:[a-z][\w-]*\s+)?credits?|"
    r"(?:[a-z][\w-]*\s+)?paypal)|"
    r"(?:are|is)\s+(?:paid|compensated|rewarded))\b"
)
_PAYER_COMPENSATION_RE = re.compile(
    rf"\b{_PAYER}\s+"
    r"(?:(?:will|may|can|usually|typically)\s+)?"
    r"(?:pay|pays|compensate|compensates|compensated|reward|rewards)\s+"
    rf"(?:the\s+)?{_RECIPIENT_CORE}\b"
)
_PAYER_RAIL_TO_RECIPIENT_RE = re.compile(
    rf"\b{_PAYER}\s+"
    r"(?:(?:will|may|can|usually|typically)\s+)?"
    r"(?:offer|offers|provide|provides|give|gives|send|sends|pay|pays|"
    r"award|awards|grant|grants)\s+"
    r"(?:the\s+)?(?:payment|compensation|(?:[a-z][\w-]*\s+)?paypal|"
    r"(?:[a-z][\w-]*\s+)?credits?)\b"
    rf".{{0,64}}\bto\s+{_RECIPIENT_CORE}\b"
)
_PASSIVE_PAYMENT_TO_RECIPIENT_RE = re.compile(
    r"\b(?:payment|compensation|pay|paid)\b"
    rf".{{0,64}}\b(?:to|for)\s+{_RECIPIENT_CORE}\b"
)
_PAYMENT_CLAUSE_SPLIT_RE = re.compile(
    r"(?:\n+|;\s*|(?<=[.!?])\s+|,\s*(?=(?:and|but|however|yet|while)\b)|"
    r"\s+(?:and|but|however|yet|while)\s+(?=(?:we|our|you|"
    r"(?:the\s+)?(?:writer|author|contributor)s?|"
    r"(?:the\s+)?(?:publisher|editor(?:ial)?(?:\s+team)?|company))\b))"
)


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    """Persist a receipt without exposing a partially written body."""

    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise DemandObservationError(f"receipt is not a regular file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(dict(value), handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _relative_config_path(value: Any, field: str, default: str) -> Path:
    selected = default if value in (None, "") else value
    if not isinstance(selected, str) or not selected.strip():
        raise DemandObservationError(f"{field} must be a relative path")
    path = Path(selected)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise DemandObservationError(f"{field} must be a relative path")
    return path


def _state_path(
    skill_dir: Path, state_dir: Path | str | None, value: str | Path
) -> Path:
    """Resolve mutable receipts outside an immutable release when configured."""

    if state_dir is None:
        return skill_dir / value
    relative = Path(value)
    if relative.parts and relative.parts[0] == "state":
        relative = Path(*relative.parts[1:])
    return Path(state_dir) / relative


def _configured_publisher_source(
    skill_dir: Path, config: Mapping[str, Any]
) -> tuple[str, dict[str, Any], Path]:
    source_id = config.get("demand_source_id")
    if not isinstance(source_id, str) or not source_id.strip():
        raise DemandObservationError("demand_source_id must be a non-empty string")
    source_id = source_id.strip()
    source_config = skill_dir / _relative_config_path(
        config.get("demand_source_config"),
        "demand_source_config",
        "config/opportunity-watch.json",
    )
    if source_config.is_symlink() or not source_config.is_file():
        raise DemandObservationError("demand source config is not a regular file")
    try:
        payload = json.loads(source_config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DemandObservationError("demand source config is invalid") from error
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise DemandObservationError("demand source config version must be 1")
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise DemandObservationError("demand source config sources must be a list")
    matches = [
        row for row in sources
        if isinstance(row, dict) and row.get("id") == source_id
    ]
    if len(matches) != 1:
        raise DemandObservationError(
            f"demand source id must resolve exactly once: {source_id}"
        )
    source = dict(matches[0])
    source_url = _source_url(source.get("official_program_url"))
    if source_url is None:
        raise DemandObservationError("configured publisher source URL is invalid")
    # The source registry stores display URLs, while the opportunity store uses
    # canonical URLs without a trailing slash.  Normalize only at this boundary
    # so policy checks cannot miss a matching opportunity row.
    source_url = canonicalize_url(source_url, "rss")
    profile = source.get("evidence_profile")
    if source_id == CIVO_SOURCE_ID:
        if source_url != CIVO_OFFICIAL_URL:
            raise DemandObservationError(
                "Civo official source URL must be exactly https://www.civo.com/write-for-us"
            )
        if profile != CIVO_EVIDENCE_PROFILE:
            raise DemandObservationError(
                "Civo source requires evidence_profile=civo-write-for-us-v1"
            )
    elif source_id == TECHI_SOURCE_ID:
        if source_url != TECHI_OFFICIAL_URL:
            raise DemandObservationError(
                "TECHi official source URL must be exactly https://www.techi.com/authors/apply"
            )
        if profile != TECHI_EVIDENCE_PROFILE:
            raise DemandObservationError(
                "TECHi source requires evidence_profile=techi-author-v1"
            )
    else:
        raise DemandObservationError(
            "demand source id must have a fixed publisher evidence profile"
        )
    if "required_evidence" in source:
        raise DemandObservationError(
            "required_evidence is unsupported; use the fixed publisher evidence_profile"
        )
    return source_id, source, source_config


def _normalize_civo_unit(value: str, *, heading: bool = False) -> str:
    text = value.strip()
    if heading:
        text = text.lstrip("#").strip()
    text = " ".join(text.casefold().split())
    while text.endswith((".", "!", "?")):
        text = text[:-1].rstrip()
    return text


def _civo_markdown_units(body: str) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(body.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("!["):
            continue
        heading_candidate = line.lstrip("#")
        if line != heading_candidate and heading_candidate.startswith(" "):
            text = _normalize_civo_unit(line, heading=True)
            if text:
                units.append({"kind": "heading", "text": text, "line": line_number})
            continue
        for fragment in _CIVO_SENTENCE_SPLIT_RE.split(line):
            text = _normalize_civo_unit(fragment)
            if not text:
                continue
            is_label = (
                fragment.strip() == line
                and not line.endswith((".", "!", "?"))
                and text in _CIVO_LABEL_UNITS
            )
            units.append(
                {
                    "kind": "heading" if is_label else "sentence",
                    "text": text,
                    "line": line_number,
                }
            )
            if len(units) > _CIVO_MAX_MARKDOWN_UNITS:
                raise DemandObservationError(
                    "full official Civo demand source has too many markdown units"
                )
    return units


def _civo_unit_record(unit_id: str, unit: Mapping[str, Any]) -> dict[str, str]:
    text = str(unit["text"])
    return {
        "id": unit_id,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def _civo_window_record(
    window_id: str,
    units: list[dict[str, Any]],
    start: int,
    expected: tuple[tuple[str, str, str], ...],
) -> dict[str, Any]:
    actual = units[start : start + len(expected)]
    if len(actual) != len(expected) or any(
        unit["kind"] != kind or unit["text"] != text
        for unit, (_unit_id, kind, text) in zip(actual, expected)
    ):
        raise DemandObservationError(
            f"full official Civo demand source missing evidence window: {window_id}"
        )
    unit_ids = [unit_id for unit_id, _kind, _text in expected]
    hash_input = "\n".join(
        f"{unit_id}={unit['text']}" for unit_id, unit in zip(unit_ids, actual)
    )
    return {
        "id": window_id,
        "unit_ids": unit_ids,
        "sha256": hashlib.sha256(hash_input.encode("utf-8")).hexdigest(),
    }


def _civo_evidence_artifacts(
    body: str,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    units = _civo_markdown_units(body)

    title = next(
        (
            unit
            for unit in units
            if unit["kind"] == "heading" and unit["text"] == _CIVO_TITLE_UNIT
        ),
        None,
    )
    if title is None:
        raise DemandObservationError(
            "full official Civo demand source missing evidence unit: civo.title"
        )

    submit = next(
        (
            unit
            for unit in units
            if unit["kind"] == "heading" and unit["text"] == _CIVO_SUBMIT_ACTION_UNIT
        ),
        None,
    )
    if submit is None:
        raise DemandObservationError(
            "full official Civo demand source missing evidence unit: civo.submit_action"
        )

    acceptance_index = next(
        (
            index
            for index, unit in enumerate(units)
            if unit["kind"] == "sentence"
            and unit["text"] == _CIVO_ACCEPTANCE_SENTENCE_UNIT
        ),
        None,
    )
    if acceptance_index is None:
        raise DemandObservationError(
            "full official Civo demand source missing evidence unit: civo.acceptance_sentence"
        )

    acceptance_window = _civo_window_record(
        "civo.acceptance_window",
        units,
        acceptance_index - 1,
        (
            ("civo.start_writing_heading", "heading", _CIVO_START_WRITING_UNIT),
            ("civo.acceptance_sentence", "sentence", _CIVO_ACCEPTANCE_SENTENCE_UNIT),
            ("civo.get_paid_heading", "heading", _CIVO_PAYMENT_HEADING_UNIT),
            ("civo.payment_sentence", "sentence", _CIVO_PAYMENT_SENTENCE_UNIT),
        ),
    )

    paid_index = next(
        (
            index
            for index, unit in enumerate(units[:-1])
            if unit["kind"] == "heading"
            and unit["text"] == _CIVO_PAYMENT_HEADING_UNIT
            and units[index + 1]["kind"] == "sentence"
            and units[index + 1]["text"] == _CIVO_PAYMENT_SENTENCE_UNIT
        ),
        None,
    )
    if paid_index is None:
        raise DemandObservationError(
            "full official Civo demand source missing evidence unit adjacency: "
            "civo.get_paid_heading->civo.payment_sentence"
        )

    payment_window = _civo_window_record(
        "civo.payment_window",
        units,
        paid_index,
        (
            ("civo.get_paid_heading", "heading", _CIVO_PAYMENT_HEADING_UNIT),
            ("civo.payment_sentence", "sentence", _CIVO_PAYMENT_SENTENCE_UNIT),
            ("civo.post_payment_submit_action", "heading", _CIVO_SUBMIT_ACTION_UNIT),
            ("civo.post_payment_start_writing", "heading", _CIVO_START_WRITING_UNIT),
            ("civo.post_payment_get_paid", "heading", _CIVO_PAYMENT_HEADING_UNIT),
        ),
    )

    evidence_units = [
        _civo_unit_record("civo.title", title),
        _civo_unit_record("civo.submit_action", submit),
        _civo_unit_record("civo.acceptance_sentence", units[acceptance_index]),
        _civo_unit_record("civo.get_paid_heading", units[paid_index]),
        _civo_unit_record("civo.payment_sentence", units[paid_index + 1]),
    ]
    return evidence_units, [acceptance_window, payment_window]


def _civo_evidence_units(body: str) -> list[dict[str, str]]:
    evidence_units, _evidence_windows = _civo_evidence_artifacts(body)
    return evidence_units


def _techi_visible_text(value: str) -> str:
    """Reduce a raw official HTML response to stable visible text.

    The normal watcher prefers a text rendering service, but a direct HTTPS
    fallback can return HTML.  Hashing the normalized visible text keeps the
    receipt deterministic across those two transports and prevents scripts or
    navigation chrome from becoming demand evidence.
    """

    without_non_content = re.sub(
        r"(?is)<(?:script|style|noscript|svg|template)\b.*?</(?:script|style|noscript|svg|template)>",
        " ",
        value,
    )
    without_tags = re.sub(r"(?s)<[^>]+>", "\n", without_non_content)
    unescaped = html.unescape(without_tags)
    lines = [" ".join(line.split()) for line in unescaped.splitlines()]
    return "\n".join(line for line in lines if line)


def _techi_evidence_artifacts(
    body: str,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Bind the decisive TECHi application and payment statements."""

    normalized = _techi_visible_text(body)
    lowered = normalized.casefold()
    # TECHi changed the visible application heading from "Apply to write for
    # TECHi" to "Apply as Author" without changing the program or payment
    # terms.  Keep the evidence unit stable while accepting either observed
    # heading, and hash the exact phrase captured in the current receipt.
    required = {
        "techi.title": ("apply to write for techi", "apply as author"),
        "techi.accepted_work": ("accepted work",),
        "techi.pay_per_publish": ("pay per publish",),
        "techi.paid_monthly": ("paid monthly via stripe",),
    }
    matched = {
        unit_id: next((phrase for phrase in phrases if phrase in lowered), None)
        for unit_id, phrases in required.items()
    }
    missing = [unit_id for unit_id, phrase in matched.items() if phrase is None]
    if missing:
        raise DemandObservationError(
            "full official TECHi demand source missing evidence units: "
            + ",".join(missing)
        )
    evidence_units = [
        {
            "id": unit_id,
            "sha256": hashlib.sha256(str(matched[unit_id]).encode("utf-8")).hexdigest(),
        }
        for unit_id, phrase in required.items()
    ]
    payment_ids = ["techi.accepted_work", "techi.pay_per_publish", "techi.paid_monthly"]
    payment_hash = hashlib.sha256("\n".join(payment_ids).encode("utf-8")).hexdigest()
    return evidence_units, [
        {"id": "techi.payment_window", "unit_ids": payment_ids, "sha256": payment_hash}
    ]


def _publisher_evidence_artifacts(
    body: str, evidence_profile: str
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    if evidence_profile == CIVO_EVIDENCE_PROFILE:
        return _civo_evidence_artifacts(body)
    if evidence_profile == TECHI_EVIDENCE_PROFILE:
        return _techi_evidence_artifacts(body)
    raise DemandObservationError(
        f"unsupported publisher evidence_profile: {evidence_profile}"
    )


def _has_affirmative_payment_clause(value: str) -> bool:
    """Require publisher-to-writer compensation in one bounded clause."""

    clauses = _PAYMENT_CLAUSE_SPLIT_RE.split(value)
    for clause in clauses:
        clause = clause.strip()
        if not clause or _PAYMENT_NEGATION_RE.search(clause):
            continue
        if _AUTHOR_ATTRIBUTION_RE.search(clause):
            continue
        if (
            _RECIPIENT_COMPENSATION_RE.search(clause)
            or _PAYER_COMPENSATION_RE.search(clause)
            or _PAYER_RAIL_TO_RECIPIENT_RE.search(clause)
            or _PASSIVE_PAYMENT_TO_RECIPIENT_RE.search(clause)
        ):
            return True
    return False


def _validate_publisher_body(
    body: bytes, *, evidence_profile: str | None = None
) -> str:
    if not isinstance(body, bytes) or not body:
        raise DemandObservationError("full official demand source returned no bytes")
    if len(body) > FULL_BODY_MAX_BYTES:
        raise DemandObservationError("full official demand source body exceeds 2 MiB")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DemandObservationError("full official demand source is not UTF-8") from error
    normalized = text.strip()
    if evidence_profile == TECHI_EVIDENCE_PROFILE:
        normalized = _techi_visible_text(normalized)
    if len(normalized) < FULL_BODY_MIN_CHARS:
        raise DemandObservationError(
            "full official demand source body is shorter than the minimum length"
        )
    lowered = normalized.casefold()
    if evidence_profile is not None:
        _publisher_evidence_artifacts(normalized, evidence_profile)
        return normalized
    submission_terms = ("submit", "submission", "contribute")
    if not any(term in lowered for term in submission_terms):
        raise DemandObservationError(
            "full official demand source body lacks publisher submission terms"
        )
    if not _has_affirmative_payment_clause(lowered):
        raise DemandObservationError(
            "full official demand source body lacks affirmative publisher payment terms"
        )
    # Demand-card normalization hashes the trimmed full body. Keep the durable
    # receipt canonical at this boundary so the captured bytes and hash agree.
    return normalized


def configured_full_body_observations(
    skill_dir: Path | str,
    config: Mapping[str, Any],
    *,
    observed_at: str,
    state_dir: Path | str | None = None,
    fetcher: Any = None,
) -> list[dict[str, Any]]:
    """Capture one configured publisher page as a durable demand observation.

    The URL comes from the existing opportunity-watch source registry, while the
    bytes are fetched through its approved full-page adapter. No ledger row or
    model excerpt can satisfy this boundary.
    """

    skill_dir = Path(skill_dir)
    source_id, source, _source_config = _configured_publisher_source(skill_dir, config)
    source_url = canonicalize_url(
        _source_url(source.get("official_program_url")) or "",
        "rss",
    )
    opportunity_database = _state_path(skill_dir, state_dir, "state/opportunities.sqlite3")
    if opportunity_database.exists():
        policy_rows = _read_only_rows(
            opportunity_database,
            "SELECT state,ai_policy FROM opportunities "
            "WHERE official_program_url=? ORDER BY updated_at DESC LIMIT 1",
            (source_url,),
        )
        if policy_rows:
            state = str(policy_rows[0]["state"] or "").upper()
            ai_policy = str(policy_rows[0]["ai_policy"] or "").upper()
            if state in {"CLOSED", "REJECTED_POLICY", "EXPIRED"} or ai_policy == "PROHIBITED":
                # The official page may still be readable, but its current policy
                # is not an eligible paid-writing demand source.  Keep the page out
                # of the card rather than letting a stale body override the store.
                return []
    if fetcher is None:
        # Keep the dependency lazy: tests and read-only adapters can load this
        # module without importing the model-backed opportunity watcher.
        from opportunity_watch import fetch_official

        fetcher = fetch_official
    try:
        raw_body = fetcher(source)
    except Exception as error:
        try:
            cached = cached_full_body_observations(
                skill_dir,
                config,
                observed_at=observed_at,
                state_dir=state_dir,
            )
        except DemandObservationError as cached_error:
            raise DemandObservationError(
                f"official demand source unavailable: {source_id}; "
                f"cached receipt unavailable: {cached_error}"
            ) from error
        return cached
    try:
        body = _validate_publisher_body(
            raw_body,
            evidence_profile=str(source["evidence_profile"]),
        )
        evidence_units, evidence_windows = _publisher_evidence_artifacts(
            body, str(source["evidence_profile"])
        )
    except DemandObservationError as error:
        # The approved fetcher can return a transport-success page that is only
        # a bot/interstitial shell.  Coconala's loop treats that as an unusable
        # source capture and reuses a recent, independently hash-verified
        # receipt; do the same here instead of converting one bad page into a
        # whole-loop DEMAND_CARD_INVALID terminal.
        try:
            cached = cached_full_body_observations(
                skill_dir,
                config,
                observed_at=observed_at,
                state_dir=state_dir,
            )
        except DemandObservationError as cached_error:
            raise DemandObservationError(
                f"official demand source invalid: {source_id}; {error}; "
                f"cached receipt unavailable: {cached_error}"
            ) from error
        return cached
    source_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
    observation = {
        "observation_id": f"demand-source:{source_id}:program",
        "source_family": PUBLISHER_SOURCE_FAMILY,
        "source_url": source_url,
        "source_sha256": source_sha256,
        "full_body": body,
        "capture_method": FULL_BODY_CAPTURE_METHOD,
        "observed_at": str(observed_at),
        "captured_at": str(observed_at),
        "metrics": {"publisher": source.get("publisher"), "source_id": source_id},
        "evidence_units": evidence_units,
        "evidence_windows": evidence_windows,
    }
    receipt_path = _state_path(skill_dir, state_dir, _relative_config_path(
        config.get("demand_source_receipt"),
        "demand_source_receipt",
        "state/demand-source-bodies.json",
    ))
    _atomic_json(
        receipt_path,
        {
            "version": 1,
            "observed_at": str(observed_at),
            "source_id": source_id,
            "source_family": PUBLISHER_SOURCE_FAMILY,
            "source_url": source_url,
            "source_sha256": source_sha256,
            "capture_method": FULL_BODY_CAPTURE_METHOD,
            "evidence_units": evidence_units,
            "evidence_windows": evidence_windows,
            "observations": [observation],
        },
    )
    return [observation]


def cached_full_body_observations(
    skill_dir: Path | str,
    config: Mapping[str, Any],
    *,
    observed_at: str,
    state_dir: Path | str | None = None,
    max_age_seconds: int = CACHED_PUBLISHER_MAX_AGE_SECONDS,
) -> list[dict[str, Any]]:
    """Reuse a recently verified publisher body during a bounded source outage.

    The cached bytes remain hash-bound to the original capture timestamp.  The
    returned row is explicitly marked as reused, so a stale body can never be
    mistaken for a fresh fetch.  Once the bounded age expires, fail closed.
    """

    skill_dir = Path(skill_dir)
    source_id, source, _source_config = _configured_publisher_source(skill_dir, config)
    receipt_path = _state_path(skill_dir, state_dir, _relative_config_path(
        config.get("demand_source_receipt"),
        "demand_source_receipt",
        "state/demand-source-bodies.json",
    ))
    if not receipt_path.exists() or receipt_path.is_symlink() or not receipt_path.is_file():
        raise DemandObservationError("demand source receipt is missing or not a regular file")
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DemandObservationError("demand source receipt is invalid") from error
    if not isinstance(payload, dict):
        raise DemandObservationError("demand source receipt is not an object")
    if payload.get("source_id") != source_id:
        raise DemandObservationError("demand source receipt identity differs")
    source_url = canonicalize_url(
        _source_url(source.get("official_program_url")) or "",
        "rss",
    )
    if payload.get("source_url") != source_url:
        raise DemandObservationError("demand source receipt URL differs")
    captured_at = payload.get("observed_at")
    if not isinstance(captured_at, str) or not captured_at.strip():
        raise DemandObservationError("demand source receipt timestamp is missing")
    try:
        captured_dt = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        observed_dt = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
    except ValueError as error:
        raise DemandObservationError("demand source receipt timestamp is invalid") from error
    if captured_dt.tzinfo is None or observed_dt.tzinfo is None:
        raise DemandObservationError("demand source receipt timestamp must include a timezone")
    age_seconds = (observed_dt - captured_dt).total_seconds()
    if age_seconds < 0:
        raise DemandObservationError("demand source receipt timestamp is in the future")
    if age_seconds > max_age_seconds:
        raise DemandObservationError(
            f"demand source receipt is older than {max_age_seconds // 86400} days"
        )
    rows = payload.get("observations")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise DemandObservationError("demand source receipt observations are invalid")
    row = dict(rows[0])
    body = row.get("full_body")
    declared_hash = row.get("source_sha256")
    if not isinstance(body, str) or not body.strip():
        raise DemandObservationError("demand source receipt body is missing")
    if not isinstance(declared_hash, str):
        raise DemandObservationError("demand source receipt body hash is missing")
    normalized = _validate_publisher_body(
        body.encode("utf-8"),
        evidence_profile=str(source["evidence_profile"]),
    )
    actual_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    if declared_hash.lower() != actual_hash or payload.get("source_sha256") != actual_hash:
        raise DemandObservationError("demand source receipt body hash does not match")
    evidence_units, evidence_windows = _publisher_evidence_artifacts(
        normalized, str(source["evidence_profile"])
    )
    if row.get("source_url") != source_url:
        raise DemandObservationError("demand source observation URL differs")
    row.update(
        {
            "source_sha256": actual_hash,
            "full_body": normalized,
            "capture_method": FULL_BODY_CAPTURE_METHOD,
            "observed_at": captured_at,
            "captured_at": row.get("captured_at") or captured_at,
            "reused_at": str(observed_at),
            "reuse_reason": "official-source-unavailable",
            "evidence_units": evidence_units,
            "evidence_windows": evidence_windows,
            "metrics": {
                **(row.get("metrics") if isinstance(row.get("metrics"), Mapping) else {}),
                "publisher": source.get("publisher"),
                "source_id": source_id,
                "receipt_age_seconds": int(age_seconds),
            },
        }
    )
    return [row]


def _source_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    url = value.strip()
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    return url


def _receipt_body(row: Mapping[str, Any]) -> tuple[str, str]:
    body = json.dumps(
        dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return body, hashlib.sha256(body.encode("utf-8")).hexdigest()


def _observation(
    *,
    observation_id: str,
    source_family: str,
    source_url: str,
    row: Mapping[str, Any],
    metrics: Mapping[str, Any],
    capture_method: str,
) -> dict[str, Any]:
    body, digest = _receipt_body(row)
    return {
        "observation_id": observation_id,
        "source_family": source_family,
        "source_url": source_url,
        "source_sha256": digest,
        "full_body": body,
        "capture_method": capture_method,
        "metrics": dict(metrics),
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.is_symlink() or not path.is_file():
        raise DemandObservationError(f"receipt is not a regular file: {path}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise DemandObservationError(f"invalid JSONL receipt: {path}:{line_number}") from error
        if not isinstance(value, dict):
            raise DemandObservationError(f"receipt row must be an object: {path}:{line_number}")
        rows.append(value)
    return rows


def funnel_observations(state_dir: Path | str) -> list[dict[str, Any]]:
    """Read funnel/own-metrics/product-funnel rows without changing their values."""

    state_dir = Path(state_dir)
    sources = (
        ("funnel.jsonl", "owned_funnel", "measured", "live_url"),
        ("own-metrics.jsonl", "reader_demand", "metric", "url"),
        ("product-funnel.jsonl", "owned_funnel", "event", "source_url"),
    )
    observations: list[dict[str, Any]] = []
    for filename, family, metric_field, url_field in sources:
        path = state_dir / filename
        for index, row in enumerate(_read_jsonl(path), 1):
            source_url = _source_url(row.get(url_field))
            if source_url is None:
                # A metric without a public source URL cannot be cited as demand.
                # Keep it out rather than inventing a URL or moving it to another row.
                continue
            metrics = row.get(metric_field)
            if not isinstance(metrics, Mapping):
                metrics = {}
            observations.append(
                _observation(
                    observation_id=f"{filename}:{index}",
                    source_family=family,
                    source_url=source_url,
                    row=row,
                    metrics=metrics,
                    capture_method="ledger_jsonl",
                )
            )
    return observations


def _read_only_rows(database: Path | str, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    path = Path(database)
    if not path.exists() or path.is_symlink() or not path.is_file():
        raise DemandObservationError(f"opportunity store is not a regular file: {path}")
    uri = f"file:{quote(str(path.resolve()))}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            return connection.execute(query, params).fetchall()
        finally:
            connection.close()
    except sqlite3.Error as error:
        raise DemandObservationError("opportunity store read failed") from error


def opportunity_observations(database: Path | str) -> list[dict[str, Any]]:
    """Adapt existing OpportunityStore rows; this function is strictly read-only."""

    opportunities = _read_only_rows(
        database,
        "SELECT opportunity_id,publisher,official_program_url,application_url,state,"
        "intake_state,fee_min,fee_max,currency,fee_basis,received_amount,"
        "received_currency,ai_policy,next_action,first_observed_at,last_verified_at FROM opportunities "
        "WHERE UPPER(COALESCE(state,'')) NOT IN ('CLOSED','REJECTED_POLICY','EXPIRED') "
        "AND UPPER(COALESCE(ai_policy,'')) <> 'PROHIBITED' "
        "ORDER BY first_observed_at,opportunity_id",
    )
    observations: list[dict[str, Any]] = []
    for row in opportunities:
        opportunity_id = str(row["opportunity_id"])
        official_url = _source_url(row["official_program_url"])
        if official_url is None:
            continue
        evidence = _read_only_rows(
            database,
            "SELECT retrieved_sha256,payload_json FROM opportunity_evidence "
            "WHERE opportunity_id=? ORDER BY observed_at,evidence_id LIMIT 1",
            (opportunity_id,),
        )
        evidence_hash = str(evidence[0]["retrieved_sha256"]) if evidence else None
        full_body = None
        body_hash = None
        capture_method = "opportunity_store_evidence"
        if evidence:
            try:
                payload = json.loads(str(evidence[0]["payload_json"]))
            except json.JSONDecodeError:
                payload = {}
            candidate_body = payload.get("full_body") if isinstance(payload, dict) else None
            if isinstance(candidate_body, str) and candidate_body.strip():
                candidate_body = candidate_body.strip()
                candidate_hash = hashlib.sha256(candidate_body.encode("utf-8")).hexdigest()
                declared_hash = payload.get("source_sha256")
                if declared_hash in (None, candidate_hash):
                    full_body = candidate_body
                    body_hash = candidate_hash
                    capture_method = str(payload.get("capture_method") or "http_full_body")
        base = {
            "source_url": official_url,
            "source_sha256": body_hash or evidence_hash,
            "full_body": full_body,
            "capture_method": capture_method,
        }
        observations.append(
            {
                "observation_id": f"opportunity:{opportunity_id}:program",
                "source_family": "publisher_opportunity",
                **base,
                "metrics": {
                    "publisher": row["publisher"],
                    "state": row["state"],
                    "intake_state": row["intake_state"],
                    "ai_policy": row["ai_policy"],
                    "next_action": row["next_action"],
                    "fee_basis": row["fee_basis"],
                },
            }
        )
        if row["fee_min"] is not None or row["fee_max"] is not None or row["received_amount"] is not None:
            observations.append(
                {
                    "observation_id": f"opportunity:{opportunity_id}:price",
                    "source_family": "paid_market",
                    **base,
                    "metrics": {
                        "fee_min": row["fee_min"],
                        "fee_max": row["fee_max"],
                        "currency": row["currency"],
                        "fee_basis": row["fee_basis"],
                        "received_amount": row["received_amount"],
                        "received_currency": row["received_currency"],
                        "ai_policy": row["ai_policy"],
                        "next_action": row["next_action"],
                    },
                }
            )
    return observations


def claim_observations(database: Path | str) -> list[dict[str, Any]]:
    """Read claim receipts with a source family, without opening the claim DB writable."""

    rows = _read_only_rows(
        database,
        "SELECT claim_id,source_family,canonical_url,full_body,source_sha256,"
        "capture_method,first_retrieved_sha256 FROM claims "
        "WHERE source_family IS NOT NULL ORDER BY first_observed_at,claim_id",
    )
    observations: list[dict[str, Any]] = []
    for row in rows:
        source_url = _source_url(row["canonical_url"])
        if source_url is None:
            continue
        observation: dict[str, Any] = {
            "observation_id": f"claim:{row['claim_id']}",
            "source_family": row["source_family"],
            "source_url": source_url,
            "source_sha256": row["source_sha256"] or row["first_retrieved_sha256"],
            "capture_method": row["capture_method"] or "claim_store_receipt",
        }
        if isinstance(row["full_body"], str) and row["full_body"].strip():
            observation["full_body"] = row["full_body"]
        observations.append(observation)
    return observations


def mix_observations(
    *,
    opportunity_database: Path | str | None = None,
    state_dir: Path | str | None = None,
    extra: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Read all configured receipts and concatenate them without deduping truth."""

    observations: list[dict[str, Any]] = []
    if opportunity_database is not None:
        observations.extend(opportunity_observations(opportunity_database))
    if state_dir is not None:
        observations.extend(funnel_observations(state_dir))
    observations.extend(dict(item) for item in extra)
    return observations
