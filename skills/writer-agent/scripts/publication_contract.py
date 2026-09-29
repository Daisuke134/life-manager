"""Single-source destination contract for writer publication dispatch."""

from __future__ import annotations


# These three destinations are the current publication obligation.  The order
# is also the stable order used by plans and receipts.
ACTIVE_PAIRS = (
    "note/ja",
    "substack/ja",
    "substack/en",
)

# These configured destinations are dormant until a separately approved
# dispatch contract enables them.  They receive durable skip receipts rather
# than publication intents or failed/pending work.
#
# x-article/ja moved here 2026-09-29 (Dais): the X Articles editor is
# permanently unreachable for our account (x-editor-unreachable, staged
# 2026-09-28) and X distribution now goes through normal link posts via
# Postiz instead. See NEWLY_DORMANT_PAIRS below for the one-time transition
# handling this requires for already-persisted "active-four" runs.
DORMANT_PAIRS = (
    "zenn-article/ja",
    "devto/en",
    "x-article/en",
    "x-post/ja",
    "x-article/ja",
)

# Destinations that were required under a still-persisted "active-four"
# contract label but became dormant in this contract revision. An
# already-created run may be missing the key entirely (never staged before
# the destination went dormant) or may carry a terminal non-skip status (e.g.
# "unavailable" with a permanent-unavailable skip receipt) recorded before
# the transition. Both shapes must still resume/terminate honestly.
NEWLY_DORMANT_PAIRS = ("x-article/ja",)

SUPPORTED_PAIRS = ACTIVE_PAIRS + DORMANT_PAIRS

# Persisted pre-active-four runs can still be resumed honestly.  This is a
# migration contract, not the current publication obligation.
LEGACY_EXACT8_PAIRS = (
    "note/ja",
    "zenn-article/ja",
    "devto/en",
    "substack/ja",
    "substack/en",
    "x-article/ja",
    "x-article/en",
    "x-post/ja",
)

# The active four split into revenue destinations and one non-blocking
# distribution surface. Only the revenue set can hold the daily shipment open.
REVENUE_PAIRS = (
    "note/ja",
    "substack/ja",
    "substack/en",
)

NON_BLOCKING_PAIRS = tuple(
    pair for pair in ACTIVE_PAIRS if pair not in REVENUE_PAIRS
)

REVENUE_SET = "revenue-set"
NON_BLOCKING_DISTRIBUTION = "non-blocking-distribution"
DORMANT = "dormant"
UNKNOWN_ROLE = "unknown"


def revenue_role(pair: str) -> str:
    """Classify one destination pair by its §2.5 revenue role."""
    if pair in REVENUE_PAIRS:
        return REVENUE_SET
    if pair in NON_BLOCKING_PAIRS:
        return NON_BLOCKING_DISTRIBUTION
    if pair in DORMANT_PAIRS:
        return DORMANT
    return UNKNOWN_ROLE


def blocks_revenue_shipment(pair: str) -> bool:
    """True only when a failure of this pair can hold the paid shipment open."""
    return revenue_role(pair) == REVENUE_SET
