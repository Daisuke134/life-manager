"""D014: bounded, aggregate-metadata-only composition check across 3–8 releases.

The check can identify *possible* arithmetic reconstruction of suppressed
categories from repeated purportedly comparable tables. Equality of declared
cohort metadata is not evidence of equality of underlying people or source
authenticity. All results remain inert: no ingestion, release, field action,
consent or welfare impact is authorized or certified by this function.
"""
from __future__ import annotations

from itertools import combinations

from .public_aggregate_cross_release import preflight_cross_release
from .public_aggregate_preflight import MIN_CELL, preflight_public_aggregate


SCHEMA = "manager.public-aggregate-release-family.v1"
MIN_RELEASES = 3
MAX_RELEASES = 8



def _comparable_subfamily_arithmetic(releases: tuple) -> set[str]:
    """Flag arithmetic risk within a declared comparable subset of 3+ tables.

    Used when an otherwise unrelated release makes the *whole* batch
    incomparable. This is a conservative metadata-only screen, not proof
    that the real cohorts coincide or a disclosure risk has materialized.
    Never return reconstructed counts.
    """
    reference = releases[0]
    if any(
        release["population"] != reference["population"]
        or release["outcome"] != reference["outcome"]
        or release["route"] != reference["route"]
        for release in releases[1:]
    ):
        return set()

    partitions = [release["partition"] for release in releases]
    first_total = partitions[0]["total"]
    cell_maps = [
        {cell["category"]: cell for cell in partition["cells"]}
        for partition in partitions
    ]
    categories = set(cell_maps[0])
    if (
        any(partition["total"] != first_total for partition in partitions[1:])
        or any(set(mapped) != categories for mapped in cell_maps[1:])
        or any(
            len({mapped[name]["sensitive"] for mapped in cell_maps}) != 1
            for name in categories
        )
    ):
        return set()

    visible = {}
    suppression_exposed = False
    for name in categories:
        entries = [mapped[name]["count"] for mapped in cell_maps]
        observed = {count for count in entries if count is not None}
        if len(observed) > 1:
            # Contradictory counts cannot be subtracted as the same population.
            return set()
        if observed and None in entries:
            suppression_exposed = True
        visible[name] = next(iter(observed)) if observed else None

    findings = set()
    if suppression_exposed:
        findings.add("FAMILY_SUPPRESSION_UNDONE")
    hidden = sum(value is None for value in visible.values())
    remainder = first_total - sum(
        value for value in visible.values() if value is not None
    )
    if remainder < 0 or (hidden == 0 and remainder != 0):
        findings.add("FAMILY_INCONSISTENT_TOTAL")
    elif hidden == 1:
        findings.add("FAMILY_SINGLE_HIDDEN_CELL")
    elif hidden >= 2 and remainder < MIN_CELL:
        findings.add("FAMILY_SMALL_COMPLEMENT")
    return findings

def preflight_release_family(releases: list | tuple) -> dict:
    """Screen a small *declared* family of published, same-partition aggregates.

    Returns fixed diagnostic codes only, never counts, category names, URLs,
    source identifiers, inferred values or original input packets. Pairwise
    checks are retained, but a third release may resolve a cell that remains
    hidden after every individual pair. Different partitions are not assumed
    comparable and are referred for independent statistical review.
    """
    if type(releases) not in (list, tuple) or not MIN_RELEASES <= len(releases) <= MAX_RELEASES:
        raise ValueError("a bounded family of 3 to 8 aggregate releases is required")

    # Validate every member with the existing exact-schema/source gate first.
    members = [preflight_public_aggregate(packet) for packet in releases]
    reasons = set()
    if any(member["status"] == "REJECT" for member in members):
        reasons.add("FAMILY_MEMBER_REJECTED")

    for first, second in combinations(releases, 2):
        pair = preflight_cross_release(first, second)
        if pair["status"] == "REJECT":
            reasons.add("FAMILY_PAIR_REJECTED")
        if "RELEASE_SOURCE_OVERLAP" in pair["reason_codes"]:
            reasons.add("FAMILY_SOURCE_OVERLAP")

    reference = releases[0]
    same_scope = all(
        packet["population"] == reference["population"]
        and packet["outcome"] == reference["outcome"]
        and packet["route"] == reference["route"]
        for packet in releases[1:]
    )
    if not same_scope:
        reasons.add("FAMILY_SCOPE_NOT_COMPARABLE")
    else:
        partitions = [packet["partition"] for packet in releases]
        cells = [
            {cell["category"]: cell for cell in partition["cells"]}
            for partition in partitions
        ]
        categories = set(cells[0])
        if any(set(partition_cells) != categories for partition_cells in cells[1:]):
            reasons.add("FAMILY_CATEGORIES_NOT_COMPARABLE")
        elif any(partition["total"] != partitions[0]["total"] for partition in partitions[1:]):
            reasons.add("FAMILY_TOTALS_NOT_COMPARABLE")
        elif any(
            len({partition_cells[name]["sensitive"] for partition_cells in cells}) != 1
            for name in categories
        ):
            # Different sensitivity declarations may denote different source
            # semantics; never infer private residuals across such metadata.
            reasons.add("FAMILY_SENSITIVITY_NOT_COMPARABLE")
        else:
            merged = {}
            conflicted = False
            for name in categories:
                entries = [partition_cells[name]["count"] for partition_cells in cells]
                released = {value for value in entries if value is not None}
                if len(released) > 1:
                    conflicted = True
                    continue
                if None in entries and released:
                    reasons.add("FAMILY_SUPPRESSION_UNDONE")
                merged[name] = next(iter(released)) if released else None

            if conflicted:
                # A changed value could be real change, revision or mistake.
                # Do not add numbers or derive a residual under that ambiguity.
                reasons.add("FAMILY_COUNTS_NOT_COMPARABLE")
            else:
                known = sum(count for count in merged.values() if count is not None)
                hidden = sum(count is None for count in merged.values())
                residual = partitions[0]["total"] - known
                if residual < 0 or (hidden == 0 and residual != 0):
                    reasons.add("FAMILY_INCONSISTENT_TOTAL")
                elif hidden == 1:
                    # The remaining withheld value is exactly reconstructable,
                    # regardless of the arbitrary minimum-cell heuristic.
                    reasons.add("FAMILY_SINGLE_HIDDEN_CELL")
                elif hidden >= 2 and residual < MIN_CELL:
                    reasons.add("FAMILY_SMALL_COMPLEMENT")

    # A fourth unrelated table must not mask reconstruction within A, B, C.
    # Examine every proper 3+ subfamily (at most 8 releases, bounded);
    # incompatible cohorts/totals/categories/sensitivity/counts are never
    # pooled. Pairwise checks above are retained for the whole batch.
    if len(releases) > MIN_RELEASES:
        for size in range(MIN_RELEASES, len(releases)):
            for subset in combinations(releases, size):
                reasons.update(_comparable_subfamily_arithmetic(subset))

    reject_reasons = {
        "FAMILY_MEMBER_REJECTED",
        "FAMILY_PAIR_REJECTED",
        "FAMILY_SUPPRESSION_UNDONE",
        "FAMILY_INCONSISTENT_TOTAL",
        "FAMILY_SINGLE_HIDDEN_CELL",
        "FAMILY_SMALL_COMPLEMENT",
    }
    return {
        "schema": SCHEMA,
        "status": "REJECT" if reasons & reject_reasons else "REVIEW_REQUIRED",
        "reason_codes": sorted(reasons),
        "can_ingest": False,
        "can_publish": False,
        "can_execute": False,
        "can_contact_participants": False,
        "source_bytes_verified": False,
        "publisher_identity_verified": False,
        "rights_verified_independently": False,
        "cohort_identity_verified": False,
        "cross_release_independence_verified": False,
        "disclosure_certified": False,
        "consent_or_ethics_approved": False,
        "causal_effect_verified": False,
        "beneficiary_effect": "NOT_MEASURED",
        "next_action": "NO_ACTION",
    }
