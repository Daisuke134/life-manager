# CFO host-admission readback — 2026-10-04

Status: `capacity_busy` reproduced in the latest CFO occurrence; current host occupancy explains the repeated blocker. Read-only diagnosis only.

## Occurrence evidence

- Latest `life-manager-cfo-hourly` natural occurrence: `18db2a5616cdbc40-72786`, 2026-10-04 08:57 JST, release `b7fb1dfa5a2ca1c8fb561a69536b7ad9061edbfc`.
- Terminal state: `blocked`, exit 75, `host_admission_deferred:resource_capacity_busy`; no provider receipt or official readback. The previous durable CFO report remains from 07:10 JST.
- The loop registry maps CFO to `resource_class=deterministic`, `admission_class=borrow`, `priority=support`.

## Current host snapshot — 09:38 JST

- The resource-admission implementation defaults to `LIFE_MANAGER_HOST_MAX_FINITE_RUNS=8`. CFO's LaunchAgent sets `LIFE_MANAGER_HOST_MIN_REVENUE_RUNS=3` but no total/revenue max override; the environment file also has no capacity-max override.
- All 8 owner records in the live `owners` directory passed the implementation's PID/start-time identity check: 7 `agent` and 1 `deterministic`; all 8 have `admission_class=revenue` and phase `running`.
- Live owner IDs: `hf-gig-paid-direct`, `life-manager-anicca-ja-widget-instagram`, `life-manager-honne-ja`, `life-manager-anicca-en-card-instagram`, `life-manager-anicca-jp4`, `marketing-owner-events`, `life-manager-anicca-en-affirmation-tiktok`, `crowdworks-revenue-application`.
- The latest local `memory.json` snapshot is stale (mtime 2026-09-13), so current memory headroom is not established. The 08:57 occurrence's typed blocker is specifically `resource_capacity_busy`, and the later 09:38 owner snapshot shows 8/8 live slots.
- This 09:38 snapshot is not a persisted snapshot of the 08:57 occurrence's exact holders; it proves current 8/8 occupancy and is consistent with the repeated `capacity_busy` event, but does not claim the same eight processes caused that earlier occurrence.
- A read-only SQLite schema/query attempt returned `database is locked` while multiple host processes held the admission DB. No DB recovery, owner stop/kill, scheduler wake, or capacity change was attempted.

## Candidate repair after repository approval

The original repair proposal below is superseded by the current-session queue analysis. Its `critical_paid`-as-borrower setting is invalid under `_normalize_priority`, and a revenue cap alone does not make the CFO waiter outrank aged support borrowers. See the corrected design below.

## Corrected current-session readback and design — 2026-10-04 22:08 JST

- Issue #6549 remains OPEN with zero comments; the authoritative GitHub reactions endpoint shows one `+1` by `Daisuke134` at 20:09 JST, satisfying its source-change gate.
- New natural `lm-loop status` readbacks show `life-manager-cfo-hourly` at 21:57 JST (`18db54e679b119c8-16831`) and `life-manager-financial-report` at 21:55 JST (`18db54c907217910-9553`) both deferred before entrypoint with `resource_capacity_busy`, exit 75, `effect=not_applicable`, and no provider receipt.
- A fresh PID/start-time check found 8/8 live slots (agent 5, browser 1, deterministic 2). Read-only SQLite shows the current CFO occurrence remains `queued`, `borrow/support`, `effect_unknown=0`; the deterministic eligible queue contains 29 `borrow/support` waiters and 2 `revenue` waiters.
- The earlier proposed `critical_paid` borrower is rejected by `_normalize_priority` (`critical_paid requires revenue admission`). A revenue cap alone also does not prioritize CFO ahead of aged support borrowers. That recommendation is superseded.
- Corrected source-only proposal: reuse `priority=revenue` for the existing `borrow` CFO owner; no new enum or schema change. Queue rank is based first on the existing effective priority for actual revenue admission, then a fixed borrow/revenue report band, then a fixed borrow/support band with age only breaking ties inside that band. This avoids promoting a 30-minute-old borrowed CFO to critical-paid ahead of fresh real revenue and keeps aged support from jumping above higher classes.
- Preserve total cap 8, current owners, queue identity/sequence, and effect fences. Do not preempt/kill loops, raise capacity, or clear the queue. Implementation/test and independent review are still pending; this proposal is not production behavior.
- No code/config/production mutation was made during this diagnosis. Source tests and independent review remain required before any promotion.
