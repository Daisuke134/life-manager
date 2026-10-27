"""D014: conservative cross-release disclosure checks on *metadata only*.

These checks detect simple arithmetic reconstruction across two purportedly
comparable public tables. They cannot authenticate source contents, cohort
identity, permission, anonymity, consent, or effect. They never fetch data,
handle participant rows, publish, or authorize an intervention.

Grounded in ONS guidance on secondary suppression, linked releases and
differencing. Other disclosure mechanisms remain outside this narrow screen.
"""
from __future__ import annotations

from typing import Mapping
from urllib.parse import urlsplit

from .public_aggregate_preflight import MIN_CELL, preflight_public_aggregate


SCHEMA = "manager.public-aggregate-cross-release.v1"


def _source_origin_key(url: str) -> tuple:
    """Conservative HTTPS source alias key, NOT independently verified provenance.

    RFC 3986 §6.2.2.1 makes URI host case-insensitive. For HTTPS, an explicit
    default port 443 denotes the same endpoint as an omitted port. Keep path,
    query and non-default ports distinct; discard fragment identifiers. This
    cannot establish whether bytes or publisher identity are actually equal.
    Called only after the existing Source schema/HTTPS metadata validation.
    """
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("invalid public aggregate source port") from None
    if port is not None and not (1 <= port <= 65535):
        raise ValueError("invalid public aggregate source port")
    return (
        parsed.scheme.lower(),
        parsed.hostname.lower(),
        None if port in (None, 443) else port,
        parsed.path,
        parsed.query,
    )


def preflight_cross_release(first: Mapping, second: Mapping) -> dict:
    """Check two declared public partitions; return reason codes, not their data.

    Cohort equality is *only* checked as a metadata claim. Exact equality of
    these strings does not prove underlying records or time windows coincide.
    An operator must independently check this before using the arithmetic.
    """
    first_gate = preflight_public_aggregate(first)
    second_gate = preflight_public_aggregate(second)
    reasons = set()
    hard = {
        "MEMBER_RELEASE_REJECTED",
        "CROSS_RELEASE_INCONSISTENT_TOTAL",
        "CROSS_RELEASE_SUPPRESSION_UNDONE",
        "CROSS_RELEASE_SINGLE_HIDDEN_CELL",
        "CROSS_RELEASE_SMALL_COMPLEMENT",
    }

    if first_gate["status"] == "REJECT" or second_gate["status"] == "REJECT":
        reasons.add("MEMBER_RELEASE_REJECTED")

    # The input source metadata is validated by the existing Source contract,
    # but identities, hashes and provenance are NOT independently verified.
    a_source, b_source = first["source"], second["source"]
    # URI host names are case-insensitive, and HTTPS :443 is its default
    # port. Preserve case-sensitive paths, query strings and other ports.
    # Parse both sources eagerly so malformed ports fail closed even if an
    # ID/digest match would otherwise short-circuit the comparison.
    # A matching URL key or digest is still ONLY a possible source alias.
    a_url_key = _source_origin_key(a_source["url"])
    b_url_key = _source_origin_key(b_source["url"])
    if (
        a_source["source_id"] == b_source["source_id"]
        or a_url_key == b_url_key
        or a_source["content_sha256"].lower() == b_source["content_sha256"].lower()
    ):
        reasons.add("RELEASE_SOURCE_OVERLAP")

    if (
        first["population"] != second["population"]
        or first["outcome"] != second["outcome"]
        or first["route"] != second["route"]
    ):
        reasons.add("COHORT_OR_CONSTRUCT_NOT_COMPARABLE")
        a_pop, b_pop = first["population"], second["population"]
        if (
            first["route"] == second["route"]
            and first["outcome"] == second["outcome"]
            and a_pop["window"] == b_pop["window"]
            and a_pop["unit"] == b_pop["unit"]
            and (
                a_pop["geography"] != b_pop["geography"]
                or a_pop["description"] != b_pop["description"]
            )
        ):
            # Two same-period tables with different geographic or population
            # scope MAY be linkable by differencing (ONS R5). We cannot
            # establish nesting from metadata, so never subtract their cells.
            reasons.add("CROSS_RELEASE_POSSIBLE_SCOPE_DIFFERENCING")
    else:
        a_partition, b_partition = first["partition"], second["partition"]
        a_cells = {cell["category"]: cell for cell in a_partition["cells"]}
        b_cells = {cell["category"]: cell for cell in b_partition["cells"]}
        a = {name: cell["count"] for name, cell in a_cells.items()}
        b = {name: cell["count"] for name, cell in b_cells.items()}
        if set(a) != set(b):
            reasons.add("CROSS_RELEASE_CATEGORIES_DIFFER")
        elif any(
            a_cells[name]["sensitive"] != b_cells[name]["sensitive"]
            for name in a
        ):
            # Sensitivity describes a category, not whether this edition
            # suppressed its count. A conflicting declaration means the
            # partition semantics cannot be safely aligned for subtraction.
            reasons.add("CROSS_RELEASE_SENSITIVITY_NOT_COMPARABLE")
        elif a_partition["total"] != b_partition["total"]:
            # A rolling window or genuinely changing population might differ;
            # do not infer a residual from two inconsistent denominators.
            reasons.add("CROSS_RELEASE_TOTALS_DIFFER")
        elif any(
            a[name] is not None and b[name] is not None and a[name] != b[name]
            for name in a
        ):
            reasons.add("CROSS_RELEASE_COUNTS_CONFLICT")
        else:
            # Only under the unverified SAME population and SAME partition
            # assumption can disclosed cells be unioned arithmetically.
            if any(
                (a[name] is None and b[name] is not None)
                or (b[name] is None and a[name] is not None)
                for name in a
            ):
                # A suppression in one release was undone by the other.
                reasons.add("CROSS_RELEASE_SUPPRESSION_UNDONE")
            merged = {
                name: a[name] if a[name] is not None else b[name]
                for name in a
            }
            known_sum = sum(value for value in merged.values() if value is not None)
            hidden_count = sum(value is None for value in merged.values())
            residual = a_partition["total"] - known_sum
            if residual < 0:
                reasons.add("CROSS_RELEASE_INCONSISTENT_TOTAL")
            elif hidden_count == 1:
                # A single hidden count is computable from the published total,
                # even if its inferred value is above our heuristic threshold.
                reasons.add("CROSS_RELEASE_SINGLE_HIDDEN_CELL")
            elif hidden_count >= 2 and residual < MIN_CELL:
                reasons.add("CROSS_RELEASE_SMALL_COMPLEMENT")

    # Even an arithmetically unremarkable pair needs an independent
    # multi-publication disclosure/rights review. Never self-certify.
    status = "REJECT" if reasons.intersection(hard) else "REVIEW_REQUIRED"
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
        "cohort_identity_verified": False,
        "cross_release_independence_verified": False,
        "disclosure_certified": False,
        "consent_or_ethics_approved": False,
        "causal_effect_verified": False,
        "beneficiary_effect": "NOT_MEASURED",
        "next_action": "NO_ACTION",
    }
