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

Issue #6549 is still open with no maintainer response. After approval, make the CFO report a reserved high-priority borrower without increasing the host-wide cap: cap concurrent revenue-class jobs at 7 (leaving one of the existing 8 finite slots for a borrower) and raise CFO from `support` to `critical_paid`. Verify admission behavior and revenue-loop throughput before release. Do not kill active revenue owners to make room.
