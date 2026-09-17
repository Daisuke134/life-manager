#!/usr/bin/env python3
"""harness_health.py -- Pure: tool-use health aggregation over already-parsed ledger records.

anicca-harness-tooluse-health R8: Python mirror of runtime/loop/harness-health.mjs's R1-R5
(classify_layer, compute_slot_health, compute_brain_transport_health, compute_harness_health,
should_escalate). Identical contract to the JS twin, proven via a SHARED fixture
(runtime/loop/__tests__/fixtures/harness-health-parity.json), not shared code. Reuses
ledger_metrics.load_ledger_rows for jsonl parsing (never a new/duplicated jsonl loader).

INV-NO-JUDGMENT: pure bookkeeping over the already-deterministic `kind` enum index.mjs itself
assigns -- never a new judgment. INV-LOOPDETECT-SEPARATE: `loop_detect` is excluded from
compute_slot_health's subset by a `kind`-membership check, regardless of its own `slot` field.

See the repository design record for the full requirement text.
"""
import os
from datetime import datetime, timezone

# R5's documented default: same `Number(process.env.X) || N` fallback idiom already used by
# catalog-gate.mjs::DEFAULT_BOOTSTRAP_RESERVE_USDC (and its own JS twin, harness-health.mjs).
try:
    DEFAULT_STREAK_THRESHOLD = int(os.environ.get("HARNESS_HEALTH_STREAK_THRESHOLD") or 0) or 5
except (TypeError, ValueError):
    DEFAULT_STREAK_THRESHOLD = 5

CLEAN_KINDS = {"wake", "narrate", "shutdown"}
# R2's slot-health subset: `loop_detect` is deliberately NOT a member even though its records carry
# a `slot` field -- INV-LOOPDETECT-SEPARATE.
SLOT_HEALTH_KINDS = {"wake", "skill_missing", "skill_timeout", "skill_error"}
# R3's brain-transport streak reset set -- narrower than CLEAN_KINDS (shutdown never resets it).
BRAIN_TRANSPORT_RESET_KINDS = {"wake", "narrate"}


def classify_layer(record):
    """R1 -- maps record['kind'] to exactly one health layer. Fail-safe: any unrecognized kind
    (including loop_detect, deliberately out of this mapping per INV-LOOPDETECT-SEPARATE) maps to
    'unknown', never raises."""
    kind = record.get("kind") if isinstance(record, dict) else None
    if kind in CLEAN_KINDS:
        return "clean"
    if kind == "wake_error":
        return "brain_transport"
    if kind == "skill_missing":
        return "tool_missing"
    if kind == "skill_timeout":
        return "tool_timeout"
    if kind == "skill_error":
        return "tool_logic"
    return "unknown"


def compute_slot_health(records, slot):
    """R2 -- per-slot tool-call health over the subset of `records` carrying that exact `slot`
    value AND kind in SLOT_HEALTH_KINDS (loop_detect excluded regardless of its own slot field).
    `records` is assumed chronologically ordered. Returns None if `slot` is absent entirely."""
    arr = records if isinstance(records, list) else []
    subset = [r for r in arr if isinstance(r, dict) and r.get("slot") == slot and r.get("kind") in SLOT_HEALTH_KINDS]
    if not subset:
        return None

    wakes = len(subset)
    failures = 0
    last_failure_layer = None
    last_failure_ts = None
    last_failure_wake_id = None

    for r in subset:
        layer = classify_layer(r)
        if layer != "clean":
            failures += 1
            last_failure_layer = layer
            last_failure_ts = r.get("ts")
            last_failure_wake_id = r.get("wake_id")

    consecutive_failure_streak = 0
    for r in reversed(subset):
        if classify_layer(r) == "clean":
            break
        consecutive_failure_streak += 1

    return {
        "slot": slot,
        "wakes": wakes,
        "failures": failures,
        "failureRate": failures / wakes,
        "consecutiveFailureStreak": consecutive_failure_streak,
        "lastFailureLayer": last_failure_layer,
        "lastFailureTs": last_failure_ts,
        "lastFailureWakeId": last_failure_wake_id,
    }


def compute_brain_transport_health(records):
    """R3 -- loop-level health of ALL wake_error records across the WHOLE ledger, never conflated
    with any single slot's health. Streak scans the WHOLE records list (reset by wake/narrate only);
    any other kind is skipped (neither counts nor resets)."""
    arr = records if isinstance(records, list) else []
    wake_errors = [r for r in arr if isinstance(r, dict) and r.get("kind") == "wake_error"]
    failures = len(wake_errors)

    consecutive_failure_streak = 0
    for r in reversed(arr):
        if not isinstance(r, dict):
            continue
        kind = r.get("kind")
        if kind == "wake_error":
            consecutive_failure_streak += 1
            continue
        if kind in BRAIN_TRANSPORT_RESET_KINDS:
            break
        # any other kind: skip, does not count and does not reset

    last = wake_errors[-1] if wake_errors else None
    return {
        "failures": failures,
        "consecutiveFailureStreak": consecutive_failure_streak,
        "lastFailureTs": last.get("ts") if last else None,
        "lastFailureWakeId": last.get("wake_id") if last else None,
    }


def should_escalate(consecutive_failure_streak, threshold):
    """R5 -- pure boundary predicate, never invokes any repair action itself (R10)."""
    return float(consecutive_failure_streak) >= float(threshold)


def compute_harness_health(records, streak_threshold=None, now=None):
    """R4 -- whole-ledger report shape covering every distinct slot value present in the R2 subset
    (SLOT_HEALTH_KINDS), plus loop-level brain-transport health, each entry annotated with R5's
    `escalate`. Never raises, even for empty/absent `records`.

    `now` is an optional datetime override for generatedAt's wall-clock stamp (test-injection idiom
    mirroring the JS twin's `now` option); defaults to the current UTC instant when omitted."""
    arr = records if isinstance(records, list) else []
    threshold = streak_threshold if streak_threshold is not None else DEFAULT_STREAK_THRESHOLD

    slots = []
    for r in arr:
        if isinstance(r, dict) and r.get("kind") in SLOT_HEALTH_KINDS and r.get("slot") is not None:
            if r["slot"] not in slots:
                slots.append(r["slot"])

    per_slot = {}
    for slot in slots:
        health = compute_slot_health(arr, slot)
        per_slot[slot] = {**health, "escalate": should_escalate(health["consecutiveFailureStreak"], threshold)}

    brain_health = compute_brain_transport_health(arr)
    brain_transport = {**brain_health, "escalate": should_escalate(brain_health["consecutiveFailureStreak"], threshold)}

    generated_at = now if now is not None else datetime.now(timezone.utc)
    return {
        "perSlot": per_slot,
        "brainTransport": brain_transport,
        "generatedAt": generated_at.isoformat().replace("+00:00", "Z"),
    }
