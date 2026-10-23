"""D014: fail-closed public-aggregate metadata preflight, without ingesting rows.

This is NOT disclosure clearance, identity verification, consent, research
approval, a welfare effect, or authorization to fetch/publish/act. The publisher
and an independent reviewer must assess linkage and overlapping releases.
"""
from __future__ import annotations

from datetime import datetime
import re
from typing import Mapping

from manager_core.models.source import Source


SCHEMA = "manager.public-aggregate-preflight.v1"
MIN_CELL = 10  # Internal screening heuristic; NOT a statutory anonymity threshold.


def _exact(value, fields, what):
    if not isinstance(value, Mapping) or set(value) != set(fields):
        raise ValueError(f"invalid {what} fields")
    return value


def _identifier(value):
    if type(value) is not str or re.fullmatch(r"[a-z][a-z0-9_]{0,39}", value) is None:
        raise ValueError("invalid aggregate category ID")
    return value


def _nonempty(value):
    if type(value) is not str or not (1 <= len(value.strip()) <= 180):
        raise ValueError("nonempty bounded aggregate metadata required")
    # No URLs, raw narratives, unbounded text, identifiers or person profiles.
    if any(ord(c) < 32 for c in value):
        raise ValueError("invalid aggregate metadata control characters")
    return value


def _count(value):
    if type(value) is not int or value < 0 or value > 10**9:
        raise ValueError("nonnegative bounded aggregate count required")
    return value


def _choice(value, values):
    if type(value) is not str or value not in values:
        raise ValueError("unsupported aggregate metadata value")
    return value


def preflight_public_aggregate(packet: Mapping) -> dict:
    """Check a declared *public aggregate release* without retrieving its data.

    Returns only fixed diagnostic codes; never includes arbitrary packet text,
    counts or category names. A positive screening outcome is not a permission
    or evidence of an independent statistical-disclosure review.
    """
    p = _exact(packet, ("schema", "route", "release_state", "granularity",
                        "source", "population", "outcome", "partition",
                        "cross_release_review"), "packet")
    if p["schema"] != SCHEMA:
        raise ValueError("unsupported public aggregate schema")
    route = _choice(p["route"], {"existing_public", "partner_public"})
    release_state = _choice(p["release_state"], {"published", "not_published", "unknown"})
    granularity = _choice(p["granularity"], {"public_aggregate", "individual", "unknown"})
    overlap_review = _choice(p["cross_release_review"],
                             {"not_assessed", "externally_documented"})

    s = _exact(p["source"], ("source_id", "url", "license_id", "rights",
                              "content_sha256", "retrieved_at", "privacy_class"), "source")
    try:
        retrieved_at = datetime.fromisoformat(s["retrieved_at"])
    except (TypeError, ValueError):
        raise ValueError("invalid source timestamp") from None
    Source(source_id=s["source_id"], url=s["url"], license_id=s["license_id"],
           rights=s["rights"], content_sha256=s["content_sha256"],
           retrieved_at=retrieved_at, privacy_class=s["privacy_class"])

    pop = _exact(p["population"], ("description", "window", "unit", "geography"),
                 "population")
    for field in ("description", "window", "unit"):
        _nonempty(pop[field])
    _choice(pop["geography"], {"national", "regional", "non_geographic"})

    outcome = _exact(p["outcome"], ("construct", "unit", "relation"), "outcome")
    _nonempty(outcome["construct"])
    _nonempty(outcome["unit"])
    relation = _choice(outcome["relation"], {"context_only", "proposed_study_outcome"})

    tab = _exact(p["partition"], ("total", "cells"), "partition")
    total = _count(tab["total"])
    cells = tab["cells"]
    if not isinstance(cells, list) or not 1 <= len(cells) <= 32:
        raise ValueError("a bounded aggregate partition is required")
    seen = set()
    known_sum = 0
    suppressed = 0
    reasons = set()
    if total < MIN_CELL:
        reasons.add("SMALL_TOTAL")
    for cell in cells:
        c = _exact(cell, ("category", "count", "sensitive"), "partition cell")
        label = _identifier(c["category"])
        if label in seen:
            raise ValueError("duplicate aggregate category")
        seen.add(label)
        if type(c["sensitive"]) is not bool:
            raise ValueError("explicit sensitivity flag required")
        if c["count"] is None:
            suppressed += 1
            continue
        count = _count(c["count"])
        known_sum += count
        if 0 < count < MIN_CELL:
            reasons.add("SMALL_RELEASED_CELL")
        if count == 0 and c["sensitive"]:
            reasons.add("SENSITIVE_ZERO_CELL_REVIEW")
    if known_sum > total:
        reasons.add("INCONSISTENT_PARTITION")
    if suppressed == 0 and known_sum != total:
        reasons.add("INCONSISTENT_PARTITION")
    if suppressed == 1 and total >= known_sum:
        # A released exact total reveals the only hidden count by subtraction,
        # even when the hidden count would exceed the basic size threshold.
        reasons.add("SINGLE_SUPPRESSED_CELL_RECONSTRUCTABLE")
    if suppressed >= 2:
        if total >= known_sum and total - known_sum < MIN_CELL:
            reasons.add("SUPPRESSED_COMPLEMENT_BELOW_MINIMUM")
        else:
            reasons.add("SUPPRESSED_GROUP_REQUIRES_REVIEW")
    if release_state != "published":
        reasons.add("NOT_PUBLICLY_RELEASED")
    if granularity != "public_aggregate":
        reasons.add("NOT_AGGREGATE_ONLY")
    if overlap_review != "externally_documented":
        reasons.add("CROSS_RELEASE_LINKAGE_NOT_REVIEWED")
    if route == "partner_public":
        reasons.add("PARTNER_ETHICS_CONSENT_NOT_AUTHENTICATED")
    if relation != "context_only":
        reasons.add("STUDY_OUTCOME_NOT_AUTHENTICATED")

    hard_reasons = {"SMALL_TOTAL", "SMALL_RELEASED_CELL", "INCONSISTENT_PARTITION",
                    "SINGLE_SUPPRESSED_CELL_RECONSTRUCTABLE",
                    "SUPPRESSED_COMPLEMENT_BELOW_MINIMUM", "NOT_PUBLICLY_RELEASED",
                    "NOT_AGGREGATE_ONLY"}
    status = ("REJECT" if reasons & hard_reasons else
              "REVIEW_REQUIRED" if reasons else "PRELIMINARY_METADATA_ONLY")
    return {
        "schema": SCHEMA,
        "status": status,
        "reason_codes": sorted(reasons),
        "can_ingest": False,
        "can_publish": False,
        "can_execute": False,
        "can_contact_participants": False,
        "source_bytes_verified": False,
        "publisher_identity_verified": False,
        "rights_verified_independently": False,
        "disclosure_certified": False,
        "consent_or_ethics_approved": False,
        "causal_effect_verified": False,
        "beneficiary_effect": "NOT_MEASURED",
        "next_action": ("NO_ACTION" if status != "PRELIMINARY_METADATA_ONLY"
                        else "INDEPENDENT_SOURCE_AND_DISCLOSURE_REVIEW"),
    }
