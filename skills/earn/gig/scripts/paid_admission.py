#!/usr/bin/env python3
"""Which paid orders may this pass work, and which are skipped over.

★ Priority decides the order things are fetched in. It must not decide whether
anything proceeds. ★

River (riverqueue.com/docs/pro/concurrency-limits, fetched 2026-08-08) states the
rule this module implements, verbatim:

    "any job that _would_ be fetched based on normal prioritization will be
     skipped over if working it would exceed a concurrency limit."

and names the partition this module applies:

    "A common use case is to partition by customer or tenant, allowing each to
     have an independent concurrency limit"

Measured 2026-08-08 05:47 on the live loop, which had neither::

    12 consecutive passes: queue top = 91000001, FIRST_CONTACT redirect -> ask,
                           "no question sent (nothing new to ask)", pass ends
    91000002 (a different paying customer, v5 built and sitting on disk since
             22:07) last selected 22:03 -- eight hours untouched
    STEP B2 skipped (policy B2:unresolved_higher_priority_queue:...:91000001)

One order that could not move stopped a second customer's finished work and all
new-customer intake. This module removes the property that made that fatal: an
order that cannot move is skipped over, and the next one is worked.


What "cannot proceed" means, and why it is read from the ledger
---------------------------------------------------------------

★ It is not re-derived from the pass's control flow. ★ Predicting "this order
will no-op" by re-implementing the dispatch conditions would be a second copy of
a 300-line bash decision tree, wrong the day either copy changes. What is read
instead is the record the loop already writes about itself:
``~/gig/projects/<identity>/events.jsonl``.

``record_queue_selection`` appends ``queue_selected`` every time the pass picks
an order. Anything the pass then achieves appends its own event
(``paid_work_ready_for_browser``, ``FORMAL_DELIVERY_INTENT``,
``paid_answer_browser_sent_reconciled``, ...). So a run of ``queue_selected``
rows with no other event between them is, literally, "we picked this order N
times and nothing happened" -- whatever the cause. The live ledger for 91000001
ends in eight such rows; 91000002's ends in a real event.

★ The unknown-event direction is deliberate. ★ ``INERT_EVENTS`` is a denylist,
not an allowlist: an event this module has never heard of counts as progress and
keeps the order eligible. The two possible mistakes are not symmetric -- skipping
an order that was fine is a paying customer left unserved, while continuing to
work one that is stuck is only today's behaviour, which the rest of the pass
already survives. So the fail-safe direction is "assume it moved".


Starvation in the other direction
---------------------------------

Skipping is cheap, so a permanently-stuck order would otherwise be skipped
forever and quietly abandoned -- the same silence with a different shape. Two
bounds, both counted off the same ledger:

* ``probe_every`` (default 6, i.e. ~6 hourly passes): the order is admitted
  anyway, once. A jam that healed itself out of band is picked up within six
  hours at a cost of one pass; a jam that has not healed writes one more
  ``queue_selected`` and goes back to being skipped.
* ``escalate_at`` (default 12, ~12 hours): an escalation row is written to
  ``~/gig/paid-lane-escalations.jsonl`` and the caller records a typed pass
  failure. Twelve hours is chosen against the clock that actually matters --
  Coconala cancels an unanswered order at 48 hours -- so escalation lands with
  three quarters of the window still open.

Neither bound is a model call and neither needs a new state store.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from delivery_identity import stable_identity  # noqa: E402
import delivery_project  # noqa: E402

try:  # the ledger writer is optional: planning must work without a writable disk
    import project_ledger
except Exception:  # noqa: BLE001 - see record_decisions()
    project_ledger = None  # type: ignore[assignment]

try:  # instrumentation, and instrumentation may never break earning
    import trajectory
except Exception:  # noqa: BLE001 - see record_decisions()
    trajectory = None  # type: ignore[assignment]


ADMIT = "admit"
SKIP = "skip"

REASON_NO_PROGRESS = "no_progress_after_selections"
REASON_CUSTOMER_SLOT = "customer_slot_taken"
REASON_PASS_LIMIT = "pass_order_limit_reached"
REASON_DEADLINE_OVERRIDE = "contact_deadline_override"

EVENT_SKIPPED = "queue_skipped"
EVENT_ESCALATED = "queue_skip_escalated"

# Events that are bookkeeping about the queue, or are written by an out-of-band
# reconciler rather than by working the order. Everything NOT in here counts as
# the order having moved. See the module docstring on why this is a denylist.
INERT_EVENTS = frozenset(
    {
        "project_initialized",
        "queue_selected",
        EVENT_SKIPPED,
        EVENT_ESCALATED,
        # Written by the reply detector / state reconciler off a live DOM read.
        # 91000002 carries nine consecutive rows of it while starved, so treating
        # it as progress would hide exactly the case this module exists for.
        "state_reconciled",
        # A bootstrap of the idempotency digest, not work on the deliverable.
        "feedback_idempotency_bootstrapped",
    }
)

# ★ One order worked per pass. ★ Sequential-within-one-pass, never parallel.
#
# What actually limits it, measured 2026-08-08 rather than assumed:
#   - NOT the browser. launchd runs the whole pass inside
#     run_with_cdp_lock.sh, which exports GIG_CDP_LOCK_HELD=1, so every
#     browser child inside one pass reuses the held lease. The lock forbids
#     parallelism, not a second order.
#   - NOT the wall clock. GIG_PASS_WALL_CLOCK_LIMIT_SECONDS=3480 against
#     measured pass durations of 60-1013s over the last twelve passes.
#   - NOT the model budget. GIG_MODEL_CALL_LIMIT=7; a paid order costs at
#     most two, and the twelve jammed passes spent zero.
#   - ★ The per-pass evidence namespace. ★ Every paid-lane artifact is one
#     fixed path under $EVIDENCE_DIR -- paid-answer.json,
#     paid-queue-expected.json, agent-PAID_QUEUE_DELIVERY/ -- and
#     recover_prior_paid_answer (gig_pass.sh:2406) recovers an unsent answer by
#     globbing those exact fixed paths across passes. Two orders in one pass
#     would either overwrite each other's answer evidence or make the second
#     order's answer unrecoverable, and the failure mode of that is sending one
#     buyer the message composed for another. That is worse than the jam.
#
# The plan below is the mechanism and is exercised at N>1 by its tests; raising
# the shipped default is a separate change that must first make the paid-lane
# evidence namespace per-order. With hourly passes and skipping in place, the
# second order is reached on the next pass rather than the same one -- the jam
# costs one hour, not eight.
DEFAULT_MAX_ORDERS = 1
DEFAULT_STUCK_AFTER = 2
DEFAULT_PROBE_EVERY = 6
DEFAULT_ESCALATE_AT = 12
# ★ A stall counter cannot see the marketplace's own cancellation clock. ★ 91000001
# measured 2026-08-08: twelve barren queue_selected rows and contact_deadline
# 2026-08-09T23:00:00+09:00 -- Coconala auto-cancels the order for seller silence at
# that instant. Waiting is a bet that something changes while we wait; nothing does.
DEFAULT_DEADLINE_WINDOW_HOURS = 24
# ★ The allowance is counted from when the clock started, NOT from total stalledness. ★
#
# The bound must exist: unbounded, this reinstates the incident in the docstring above
# at lines 18-28. delivery_queue promotes an at-risk order to FIRST_CONTACT_PRIORITY=-1,
# so it is decisions[0] and takes the only max_orders=1 slot -- for every pass in the
# window, while a second customer's finished artifact sits untouched, the only alarm
# being the STARVED order escalating twelve hours later.
#
# But the obvious bound is unreachable exactly when it is needed. Counting off
# ``selections_without_progress`` was measured wrong on 91000001 the day it shipped:
# that counter stood at 10 and nothing ever decrements it -- only a real event resets
# it, and the failure mode IS that no real event happens. So the override would have
# been reachable only for an order that became at-risk while stalled 2 or 3, and for
# the deeply-stuck order it exists for it bought zero passes, forever.
#
# ★ The honest boundary is the window itself. ★ The ledger records no risk-onset field
# -- ``record_queue_selection`` (delivery_project.py:56,72) stores neither
# ``contact_deadline`` nor ``first_contact_at_risk`` in the row state, verified on the
# live ledger -- so there is nothing to read that dates the onset directly. What there
# IS: every row carries ``ts`` (project_ledger.py:43), and this module's own definition
# of "at risk enough to override" is "the deadline is inside the window". Those give a
# derived instant that is not a proxy for anything: window entry = deadline - window.
# Selections made after it are the passes the deadline has already bought.
#
# So a deeply-stuck order gets its full allowance the moment its clock enters the
# window, however long it sat stuck beforehand -- 91000001 has 0 selections after its
# 2026-08-08T23:00+09:00 entry -- and an order that has burned the allowance inside the
# window stops holding the slot. With a real bound the window size stops being the
# safety mechanism.
DEADLINE_OVERRIDE_SELECTIONS = 2

DEFAULT_PROJECTS_ROOT = Path("~/gig/projects")
DEFAULT_ESCALATION_LEDGER = Path("~/gig/paid-lane-escalations.jsonl")

_NON_WORD = re.compile(r"\W+")


def customer_key(item: dict[str, Any]) -> str:
    """The partition River calls a tenant: who we would be talking to.

    Buyer name first, because that is the person the "do not send one customer
    two things at once" rule protects. It is free-form marketplace text, so it
    is normalised, and an empty one falls back to the order identity -- which
    partitions that order alone and can never merge two customers by accident.
    """
    buyer = _NON_WORD.sub("", str(item.get("buyer") or "").casefold())
    if buyer:
        return f"buyer:{buyer}"
    try:
        return f"order:{stable_identity(item)}"
    except ValueError:
        return "order:unknown"


def read_events(projects_root: Path, identity: str) -> list[dict[str, Any]]:
    """Every well-formed ledger row for one order, in file order, or []."""
    path = Path(projects_root).expanduser() / identity / "events.jsonl"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


EVENT_ATTEMPT_FAILED = "delivery_attempt_failed"


def _repeated_failures(rows: list[dict[str, Any]]) -> set[int]:
    """Indices of ``delivery_attempt_failed`` rows that repeat the previous reason.

    ★ "Repeated identical failures" is checkable, so it is checked rather than
    assumed. ★ A first failure, or a failure for a new reason, means the loop is
    still doing something different each pass and the order is not stuck. The
    same reason twice means the next attempt will produce the same nothing.

    delivery_attempt.record_failed writes the reason into the merged state as
    ``last_delivery_attempt_reason``. A row without one is treated as its own
    unique reason -- the fail-safe direction, since it keeps the order eligible.
    """
    repeated: set[int] = set()
    previous: str | None = None
    for index, row in enumerate(rows):
        if str(row.get("event") or "") != EVENT_ATTEMPT_FAILED:
            continue
        state = row.get("state")
        reason = str((state or {}).get("last_delivery_attempt_reason") or "") if isinstance(state, dict) else ""
        if reason and reason == previous:
            repeated.add(index)
        previous = reason or None
    return repeated


def selections_without_progress(rows: list[dict[str, Any]]) -> int:
    """How many times running has this order been picked with nothing to show?

    Walks backwards and stops at the first event that is not bookkeeping. A real
    event -- an artifact built, a message reconciled, a delivery attempted for a
    new reason -- resets the count on its own, so the counter needs no reset path
    and cannot be stale.
    """
    repeated = _repeated_failures(rows)
    count = 0
    for index in range(len(rows) - 1, -1, -1):
        event = str(rows[index].get("event") or "")
        if event == "queue_selected":
            count += 1
            continue
        if event in INERT_EVENTS or (event == EVENT_ATTEMPT_FAILED and index in repeated):
            continue
        break
    return count


def consecutive_skips(rows: list[dict[str, Any]]) -> int:
    """How many passes in a row has this order been skipped over?

    Stops at anything that is not a skip and not out-of-band reconciliation, so
    a single admission (probe or otherwise) clears it.
    """
    count = 0
    for row in reversed(rows):
        event = str(row.get("event") or "")
        if event == EVENT_SKIPPED:
            count += 1
            continue
        if event in {"state_reconciled", EVENT_ESCALATED}:
            continue
        break
    return count


def _valid_feedback_hash(value: Any) -> str | None:
    feedback = str(value or "").strip().lower()
    return feedback if re.fullmatch(r"[0-9a-f]{64}", feedback) else None


_MUST_ACTION_PHASES = frozenset({"ACTIONABLE", "WORKING", "VERIFYING", "RESUBMITTING"})


def _must_action(state: Any) -> bool:
    if not isinstance(state, dict):
        return False
    current = _valid_feedback_hash(state.get("buyer_feedback_sha256"))
    handled = _valid_feedback_hash(state.get("handled_buyer_feedback_sha256"))
    if current is not None and handled is not None and current != handled:
        return True
    cycle = state.get("active_feedback_cycle")
    if isinstance(cycle, dict) and cycle.get("phase") in _MUST_ACTION_PHASES:
        return True
    if state.get("next_action") == "WORK_REQUIRED" or state.get("work_state") == "WORK_REQUIRED":
        return True
    return state.get("next_action") == "retry_buyer_visible_delivery"


def _read_bound_state(projects_root: Path, item: dict[str, Any]) -> dict[str, Any] | None:
    try:
        project_root = delivery_project.resolve_project_root(projects_root, item)
    except (OSError, ValueError):
        return None
    return _read_state(project_root)


def _latest_selected_feedback_hash(rows: list[dict[str, Any]]) -> str | None:
    for row in reversed(rows):
        if str(row.get("event") or "") != "queue_selected":
            continue
        state = row.get("state")
        return _valid_feedback_hash(state.get("buyer_feedback_sha256")) if isinstance(state, dict) else None
    return None


def _contact_deadline(item: dict[str, Any]) -> datetime | None:
    """The order's cancellation instant, or None if it cannot be anchored.

    Same parse ``delivery_queue.first_contact_at_risk`` uses to promote priority: ISO
    8601 with a UTC offset. A naive timestamp is rejected, because a deadline that
    cannot be compared is not permission to override anything.
    """
    raw = str(item.get("contact_deadline") or "")
    if not raw:
        return None
    try:
        deadline = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return deadline if deadline.tzinfo is not None else None


def _deadline_within_window(item: dict[str, Any], now: datetime, window_hours: int) -> bool:
    """Is the cancellation clock running and inside ``window_hours``?

    A deadline already in the past is not treated as near -- an order that can never
    progress must not hold a slot once its clock has run out.

    ★ The "is this still at risk" question is not re-answered here. ★ The caller checks
    ``item["first_contact_at_risk"]``, which ``delivery_queue`` (delivery_queue.py:355)
    publishes on every paid item -- computed with the ``seller_message_observed``
    retraction AND against the snapshot clock. Hand-copying that guard into this module
    would be a second copy to keep in sync, and one that can disagree with the promoter
    that put the order at priority -1 in the first place.
    """
    deadline = _contact_deadline(item)
    if deadline is None:
        return False
    return timedelta(0) < deadline - now <= timedelta(hours=window_hours)


def selections_since(rows: list[dict[str, Any]], since: float) -> int:
    """How many times has this order been picked since epoch instant ``since``?

    ★ Undated rows count. ★ Every row this loop writes carries ``ts``
    (project_ledger.py:43), so an undated one is malformed or hand-written. This is the
    override's only bound, and a bound that malformed data can widen is not a bound --
    so the fail-safe direction here is the opposite of ``selections_without_progress``:
    spend the allowance rather than grant an unbounded one.
    """
    count = 0
    for row in rows:
        if str(row.get("event") or "") != "queue_selected":
            continue
        try:
            if float(row["ts"]) >= since:
                count += 1
        except (KeyError, TypeError, ValueError):
            count += 1
    return count


def _last_admitted_ts(rows: list[dict[str, Any]]) -> float:
    """The instant this order last won a pass's slot, or ``0.0`` if it never has.

    Only ``queue_selected`` rows count -- ``record_queue_selection`` (module
    docstring, above) appends one exactly when a pass admits an order to work, never
    when it is skipped. Counting ``queue_skipped`` rows here would invert the round
    robin below: a repeatedly-skipped order would look "recently active" and get
    pushed even further back, which is the opposite of what skip-then-rotate is for.
    A row with no parseable ``ts`` is not counted either way -- it neither proves nor
    disproves a recent win, so it is simply skipped rather than treated as most-recent
    (which would starve every other order behind bad data) or as never (which would
    let bad data hand the same order an unearned turn).
    """
    latest = 0.0
    for row in rows:
        if str(row.get("event") or "") != "queue_selected":
            continue
        try:
            ts = float(row["ts"])
        except (KeyError, TypeError, ValueError):
            continue
        if ts > latest:
            latest = ts
    return latest


def _positive(value: Any, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return number if number > 0 else fallback


def _snapshot_now(item: dict[str, Any]) -> datetime:
    """The honest now: when the banner was read, else the machine clock."""
    raw = str(item.get("snapshot_captured_at") or "")
    if raw:
        try:
            captured = datetime.fromisoformat(raw)
        except ValueError:
            captured = None
        if captured is not None and captured.tzinfo is not None:
            return captured
    return datetime.now(timezone.utc)


def plan(
    items: list[dict[str, Any]],
    *,
    projects_root: Path | str = DEFAULT_PROJECTS_ROOT,
    max_orders: int = DEFAULT_MAX_ORDERS,
    stuck_after: int = DEFAULT_STUCK_AFTER,
    probe_every: int = DEFAULT_PROBE_EVERY,
    escalate_at: int = DEFAULT_ESCALATE_AT,
    deadline_window_hours: int = DEFAULT_DEADLINE_WINDOW_HOURS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Decide, for every queue item in priority order, admit or skip.

    Pure: reads ledgers, writes nothing. ``items`` must already be in the queue's
    own priority order. Priority still decides which item is *looked at* first and,
    among items that are all otherwise eligible, still breaks ties -- but it does not
    decide who wins the shared slot outright. See "round robin" below for why.

    ``now`` is the instant the deadline window is measured against. Unset, it is read
    from the item's ``snapshot_captured_at`` -- ``delivery_queue`` deliberately uses
    the snapshot's capture instant, the honest now, being the moment the banner was
    actually read -- and only then from the machine clock. A machine clock that has
    run past a deadline the snapshot saw as live would otherwise disable the override
    silently and let the order die quietly.

    ★ Round robin: who gets the shared slot(s) when more than one order is eligible. ★
    A genuinely stuck order (rule 1, above) is decided on its own -- it is skipped for
    ``REASON_NO_PROGRESS`` regardless of what else is going on, because it could not
    proceed even with a free slot. Everything else competes for the ``max_orders``
    slots, and that competition is NOT run in priority order: it runs least-recently-
    admitted first. An order that has never won the slot (``last_admitted_ts == 0.0``)
    always outranks one that has, and orders tied on that (typically every order this
    module has never admitted) fall back to priority via the original index.

    This is the reason: with the shipped ``max_orders=1``, pure priority order means
    whichever order sits at the top of the queue wins the slot every single pass for as
    long as it keeps making *some* progress -- it is never "stuck" by rule 1's
    definition, so nothing before this change ever let a second, lower-priority order
    through. That is D1 in 26-gig-loop-asis-tobe-plan.md: "max_orders=1 head-of-line
    blocking means ONE order monopolizes the paid lane while others wait." Least-
    recently-admitted-first turns that into strict alternation: a customer who just won
    the slot yields it to whoever has been waiting longest, and is eligible again next
    time nobody has waited longer.

    River's actual fix (35-gig-no-head-of-line-blocking-design.md rule 2: "1 pass
    processes multiple orders, N slots overall") is not this. Widening ``max_orders``
    needs the paid-lane evidence namespace to be per-order first -- see the comment on
    ``DEFAULT_MAX_ORDERS`` for the concrete failure mode (a second order's answer
    overwriting or becoming unrecoverable, which risks sending one buyer the message
    composed for another). This function does not touch that. Strict rotation with
    ``max_orders`` unchanged already removes the starvation -- "the same order every
    pass, forever" becomes "alternates pass to pass" -- without opening that risk.
    """
    root = Path(projects_root).expanduser()
    max_orders = _positive(max_orders, DEFAULT_MAX_ORDERS)
    stuck_after = _positive(stuck_after, DEFAULT_STUCK_AFTER)
    probe_every = _positive(probe_every, DEFAULT_PROBE_EVERY)
    escalate_at = _positive(escalate_at, DEFAULT_ESCALATE_AT)
    deadline_window_hours = _positive(deadline_window_hours, DEFAULT_DEADLINE_WINDOW_HOURS)

    admitted: list[dict[str, Any]] = []
    taken: set[str] = set()
    finalized: dict[int, dict[str, Any]] = {}  # index -> record, for items decided outright
    candidates: list[dict[str, Any]] = []  # items still competing for a slot

    def _finalize_skip(record: dict[str, Any], skipped: int) -> None:
        # Escalation is about an order nobody is serving, so it is counted
        # only where the skip actually happened -- and on the pass that
        # crosses the boundary, not on every pass after it.
        following = skipped + 1
        record["escalate"] = following > 0 and following % escalate_at == 0
        record["consecutive_skips_after"] = following

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        try:
            identity = delivery_project.resolve_project_root(root, item).name
        except ValueError:
            # No identity means no ledger and no project root; it cannot be
            # worked and it cannot be recorded against. Leave it out entirely
            # rather than let it consume a slot.
            continue
        rows = read_events(root, identity)
        must_action = _must_action(_read_bound_state(root, item))
        stalled = selections_without_progress(rows)
        skipped = consecutive_skips(rows)
        current_feedback = _valid_feedback_hash(item.get("buyer_feedback_sha256"))
        if must_action or (
            current_feedback is not None
            and current_feedback != _latest_selected_feedback_hash(rows)
        ):
            stalled = skipped = 0
        partition = customer_key(item)
        last_admitted_ts = _last_admitted_ts(rows)
        record: dict[str, Any] = {
            "index": index,
            "identity": identity,
            "buyer": item.get("buyer"),
            "talkroom_id": item.get("talkroom_id"),
            "queue_class": item.get("queue_class"),
            "priority": item.get("priority"),
            "customer_key": partition,
            "selections_without_progress": stalled,
            "consecutive_skips": skipped,
            "last_admitted_ts": last_admitted_ts,
            "probe": False,
            "escalate": False,
            "deadline_override": False,
            "must_action": must_action,
        }
        stuck = stalled >= stuck_after
        # A probe is due only after real skips have accumulated. ``skipped == 0``
        # would satisfy ``% probe_every == 0`` and probe on the very first skip,
        # which would make the skip a no-op.
        if stuck and skipped > 0 and skipped % probe_every == 0:
            record["probe"] = True
            stuck = False
        # A live cancellation clock buys DEADLINE_OVERRIDE_SELECTIONS passes counted
        # from window entry -- see that constant for why the boundary is the window and
        # not the stall counter. ★ Deliberately below the two limits it must not
        # outrank: ★ clearing ``stuck`` only removes the backoff, so the slot
        # competition below can still skip this order for pass_order_limit_reached or
        # customer_slot_taken.
        deadline = _contact_deadline(item)
        if (
            stuck
            and item.get("first_contact_at_risk") is True
            and _deadline_within_window(
                item, now or _snapshot_now(item), deadline_window_hours
            )
            and deadline is not None
            and selections_since(
                rows, (deadline - timedelta(hours=deadline_window_hours)).timestamp()
            )
            < DEADLINE_OVERRIDE_SELECTIONS
        ):
            record["deadline_override"] = True
            stuck = False
        if stuck:
            # Decided outright: no free slot would have helped this order, so it is
            # never entered into the round-robin competition below, and its reason is
            # never shadowed by pass_order_limit_reached or customer_slot_taken.
            record.update(decision=SKIP, reason=REASON_NO_PROGRESS)
            _finalize_skip(record, skipped)
            finalized[index] = record
        else:
            candidates.append(record)

    # ★ The competition, in least-recently-admitted-first order. ★ Ties (including the
    # common case of every candidate never having been admitted) fall back to `index`,
    # which is priority order -- so with no contention history this is byte-identical
    # to the old strict-priority loop.
    for record in sorted(
        candidates,
        key=lambda r: (not r["must_action"], r["last_admitted_ts"], r["index"]),
    ):
        partition = record["customer_key"]
        if len(admitted) >= max_orders:
            record.update(decision=SKIP, reason=REASON_PASS_LIMIT)
        elif partition in taken:
            # River's partition-by-tenant: one thing in flight per customer, so
            # a second order from the same buyer waits even when a slot is free.
            record.update(decision=SKIP, reason=REASON_CUSTOMER_SLOT)
        elif record["deadline_override"]:
            record.update(decision=ADMIT, reason=REASON_DEADLINE_OVERRIDE)
        else:
            record.update(decision=ADMIT, reason="")
        if record["decision"] == SKIP:
            _finalize_skip(record, record["consecutive_skips"])
        else:
            taken.add(partition)
            admitted.append(record)
        finalized[record["index"]] = record

    # ★ Output order is always priority order. ★ The competition above reorders who
    # WINS; it never reorders what the caller sees. `test_priority_still_decides_
    # fetch_order_and_never_progress` pins this.
    decisions = [finalized[index] for index in sorted(finalized)]

    return {
        "version": 1,
        "max_orders": max_orders,
        "stuck_after": stuck_after,
        "probe_every": probe_every,
        "escalate_at": escalate_at,
        "deadline_window_hours": deadline_window_hours,
        # The actual safety mechanism, so an operator reading this file can see the
        # bound rather than inferring it from the window (which is not one).
        "deadline_override_selections": DEADLINE_OVERRIDE_SELECTIONS,
        "admitted": [row["identity"] for row in admitted],
        "skipped": [row["identity"] for row in decisions if row["decision"] == SKIP],
        "escalated": [row["identity"] for row in decisions if row.get("escalate")],
        "decisions": decisions,
    }


def record_decisions(
    result: dict[str, Any],
    *,
    projects_root: Path | str = DEFAULT_PROJECTS_ROOT,
    escalation_ledger: Path | str = DEFAULT_ESCALATION_LEDGER,
    pass_id: str = "",
) -> dict[str, Any]:
    """Make every skip durable in the order's own ledger. ★ Never raises. ★

    A skip nobody can see is a customer nobody serves, so it is written where the
    next pass -- and the next reader of this order -- will trip over it. This is
    instrumentation around a paid lane, so a failure to write it may not take the
    pass down: every path returns counts instead of an exception.
    """
    root = Path(projects_root).expanduser()
    ledger_path = Path(escalation_ledger).expanduser()
    written = 0
    escalated = 0
    errors: list[str] = []
    for record in result.get("decisions", []):
        if not isinstance(record, dict) or record.get("decision") != SKIP:
            continue
        identity = str(record.get("identity") or "")
        reason = str(record.get("reason") or "")
        project_root = root / identity
        # ★ The skip is visible in four places, because a skip nobody can see is a
        # customer nobody serves (memory: zero_results_must_record_how_it_looked). ★
        # Here: the order's own ledger and the escalation ledger. The caller adds a
        # log line and keeps the whole plan as pass evidence.
        _record_trajectory(record)
        state = _read_state(project_root)
        if state is None:
            # An order never selected has no project and cannot be stuck; there
            # is nothing to append to and nothing worth creating.
            continue
        # load_top_queue_state runs again after the reply lane recollects the
        # queue, so the same skip is planned twice in one pass. One pass is one
        # skip: the counters this module reads are counts of PASSES, and a
        # double row would make an order look twice as stuck as it is.
        already = str(state.get("last_skip_pass_id") or "")
        if project_ledger is not None and not (pass_id and already == pass_id):
            try:
                project_ledger.append(
                    project_root,
                    {"last_skip_pass_id": pass_id, "last_skip_reason": reason},
                    EVENT_SKIPPED,
                )
                written += 1
            except Exception as error:  # noqa: BLE001 - invariant above
                errors.append(f"{identity}:{type(error).__name__}")
        if not record.get("escalate"):
            continue
        if pass_id and str(state.get("last_skip_escalated_pass_id") or "") == pass_id:
            continue
        row = {
            "ts": round(time.time(), 3),
            "pass_id": pass_id,
            "identity": identity,
            "buyer": record.get("buyer"),
            "talkroom_id": record.get("talkroom_id"),
            "reason": reason,
            "selections_without_progress": record.get("selections_without_progress"),
            "consecutive_skips": record.get("consecutive_skips_after"),
        }
        try:
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with ledger_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            escalated += 1
        except OSError as error:
            errors.append(f"{identity}:{type(error).__name__}")
        if project_ledger is not None:
            try:
                project_ledger.append(
                    project_root,
                    {"last_skip_escalated_pass_id": pass_id},
                    EVENT_ESCALATED,
                )
            except Exception as error:  # noqa: BLE001 - invariant above
                errors.append(f"{identity}:{type(error).__name__}")
    return {"skips_recorded": written, "escalations_recorded": escalated, "errors": errors}


def _read_state(project_root: Path) -> dict[str, Any] | None:
    """The order's materialized state, or None when no project exists yet."""
    try:
        state = json.loads((project_root / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return state if isinstance(state, dict) else None


def _record_trajectory(record: dict[str, Any]) -> None:
    """One EV1 trajectory row per skip. Silent no-op outside a pass."""
    if trajectory is None:
        return
    identity = str(record.get("identity") or "")
    if not identity:
        return
    reason = f"{record.get('reason') or 'skipped'}:{record.get('selections_without_progress')}"
    try:
        trajectory.record(
            stage="PAID_ADMISSION",
            lane="delivery",
            resource_key=f"project:{identity}",
            # The planner only read a ledger; recording it as anything else would
            # claim work that did not happen.
            action="read",
            result="skipped",
            reason=reason,
        )
    except Exception:  # noqa: BLE001 - trajectory.record already swallows; belt and braces
        pass


def _env_int(environ: dict[str, str], name: str, fallback: int) -> int:
    return _positive(environ.get(name), fallback)


def main(argv: list[str] | None = None) -> int:
    import os

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--projects-root", default=str(DEFAULT_PROJECTS_ROOT))
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--escalation-ledger", default=str(DEFAULT_ESCALATION_LEDGER))
    parser.add_argument("--pass-id", default="")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--max-orders", type=int, default=None)
    args = parser.parse_args(argv)

    try:
        queue = json.loads(args.queue.read_text(encoding="utf-8"))
        items = queue.get("items")
        if not isinstance(items, list):
            raise ValueError("queue items is not a list")
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1

    environ = dict(os.environ)
    result = plan(
        items,
        projects_root=args.projects_root,
        max_orders=(
            args.max_orders
            if args.max_orders is not None
            else _env_int(environ, "GIG_PAID_MAX_ORDERS_PER_PASS", DEFAULT_MAX_ORDERS)
        ),
        stuck_after=_env_int(environ, "GIG_PAID_STUCK_AFTER_SELECTIONS", DEFAULT_STUCK_AFTER),
        probe_every=_env_int(environ, "GIG_PAID_SKIP_PROBE_EVERY", DEFAULT_PROBE_EVERY),
        escalate_at=_env_int(environ, "GIG_PAID_SKIP_ESCALATE_AT", DEFAULT_ESCALATE_AT),
        deadline_window_hours=_env_int(
            environ, "GIG_PAID_DEADLINE_WINDOW_HOURS", DEFAULT_DEADLINE_WINDOW_HOURS
        ),
    )
    if args.record:
        result["recorded"] = record_decisions(
            result,
            projects_root=args.projects_root,
            escalation_ledger=args.escalation_ledger,
            pass_id=args.pass_id,
        )
    if args.output is not None:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as error:
            print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
            return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
