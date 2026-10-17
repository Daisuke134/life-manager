# Anicca Creative Feedback Implementation Plan

> **For agentic workers:** implement the tasks below in order. Each code change begins with a failing test.

**Goal:** Make Anicca's existing English carousel rotation use exact, measured 24-hour post views so later slots can favor creative families that reach more people.

**Architecture:** Keep the existing deterministic candidate generator and selector. Join the native-carousel publication receipt to the local per-post metrics ledger by provider post ID and exact lane identity; accept a publication-time difference up to 180 seconds. Pass only qualified family scores to the selector. This adds no provider request, scheduler, publication slot, or paid service.

**Tech Stack:** Node.js, existing JSONL receipts, `node:test`.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` — “Anicca creative feedback source gap”.

## Files

- `apps/life-manager/scripts/generate-larry-slide-pack.js`: derive family scores from existing in-window post metrics when the rotation runs.
- `apps/life-manager/scripts/generate-larry-slide-pack.test.js`: prove exact publication-to-metric joins and fail-closed sample handling.

## Tasks

### 1. RED: add the measured-view family-score regression

- Seed the native-carousel distribution ledger with published packs from two families on one English lane.
- Seed `marketing-owner-events/state/post-metrics.jsonl` with three distinct 24-hour in-window samples for each family and decoys for another integration, a missed checkpoint, a 72-hour row, and publication-time skew at 9 seconds and 181 seconds.
- Assert the selector receives only the two family scores, calculated from 24-hour views, and that under-sampled families have no score.
- Run `node --test apps/life-manager/scripts/generate-larry-slide-pack.test.js`; confirm failure because the current selector returns no scores from the empty creative-metrics ledger.

### 2. GREEN: use local snapshots in the existing selector

- Join receipts and metric rows using provider post ID, product, locale, integration ID, exact `pack_sha256`, and publication time within 180 seconds. The 9-second skew is accepted; the 181-second skew is excluded.
- Accept only numeric `views` from `target_age_hours=24`, `checkpoint_status=measured`, and `checkpoint_sla_status=in_window` rows.
- Require three distinct posts per family before returning a mean score; leave missing or late rows out rather than converting them to zero.
- Use the existing rotation selector unchanged so its no-repeat and slot idempotency rules remain intact.

### 3. Verify and promote

- Run the focused generator and rotation tests plus `git diff --check`.
- Confirm the diff makes no provider request and changes no publishing cadence or effect fence.
- Commit and push on this branch; pass exact-head checks, merge, then let the registered release/owner path load the merged release.
- Confirm a natural English slot uses an accepted candidate and that its official publication receipt can join to a later 24-hour metric row.

## Review Focus

- Wrong account or integration cannot influence an English lane.
- Publication timestamp skew over 180 seconds cannot influence a lane; an observed 9-second provider delay remains joinable through exact post ID and integration identity.
- Stale, missed, unavailable, duplicate, and ambiguous snapshots do not count toward the three-post minimum.
- Zero views remain a measured zero only when the provider explicitly measured them; missing views remain unscored.
- Existing `effect_unknown` fences, slot dedupe, no-catch-up, and no-repeat-within-seven-days behavior remain unchanged.
