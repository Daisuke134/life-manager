# Life Manager Provider Cost Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop repeated avoidable provider spend, record truthful provider-complete costs, and enforce the beta daily budget while cached Calendar and route truth remains readable.

**Architecture:** Address normalization and geocoding become persistent shared caches, route selection remains Transit-first and only performs sequential Google fallback after an explicit failure, and every provider operation writes a versioned ledger event. A pure budget policy aggregates current-day measured plus estimated spend and returns `normal`, `warning`, `degraded`, or `stopped`; provider adapters consult it before nonessential work. Unknown billing remains explicit rather than numeric zero.

**Tech Stack:** Node.js CommonJS, `node:test`, Supabase/PostgreSQL, Transit API, Google Maps, Composio, Gemini Live, Telnyx CDR, Resend, Railway usage, owner Telegram reporting.

## Global Constraints

- Focused baseline is 43/43 green for `travel-transit-wire`, `transit`, `route-cache`, `travel-routes`, `ledger`, and `composio-budget` tests.
- Run `npm ci` before the clean full-suite baseline; the planning worktree lacked installed `viem` despite its declared dependency.
- Cache hits required to display existing truth are allowed at every budget state.
- `actual_billed_usd` is nullable; absent provider billing is `actual_status="unknown"`, never `0`.
- Google never runs in parallel with an accepted Transit result.
- This gate does not modify `late-notice.js`, Telegram approval code, or iOS source.

## File Structure

| File | Change |
|---|---|
| `apps/life-manager/lib/geocode-cache.js` | Add normalization and persistent cache adapter |
| `apps/life-manager/lib/geocode-cache.test.js` | Add persistence and tenant-safe cache tests |
| `apps/life-manager/lib/route-cache.js` | Add Supabase store; retain injectable cache interface |
| `apps/life-manager/lib/route-cache.test.js` | Verify persistence, expiry, and provider metadata |
| `apps/life-manager/lib/travel.js` | Write successful geocodes; use durable route cache and sequential fallback |
| `apps/life-manager/lib/transit.js` | Preserve structured provider facts |
| `apps/life-manager/lib/ledger.js` | Replace partial record with complete cost event and owner-visible failure |
| `apps/life-manager/lib/provider-budget.js` | Add thresholds and adapter gate |
| `apps/life-manager/lib/provider-budget.test.js` | Add policy tests |
| `apps/life-manager/lib/transport/calendar-composio.js` | Count real operations and reuse Calendar cache |
| `apps/life-manager/lib/provider-cost-report.js` | Add measured/estimated/fixed/unknown owner report |
| `apps/life-manager/migrations/2026-08-08-lm-provider-cost.sql` | Extend ledger; add persistent geocode cache and budget indexes |
| `apps/life-manager/test/mobile-geocode-cost-guard.test.js` | Spec test row 9 |
| `apps/life-manager/test/mobile-route-provider-budget.test.js` | Spec test row 10 |
| `apps/life-manager/test/provider-cost-contract.test.js` | Spec test row 23 |
| `apps/life-manager/test/provider-budget-gate.test.js` | Spec test row 24 |

### Task 1: Persist Successful Geocodes

**Interface:**

```javascript
function normalizeGeocodeAddress(value)
function createSupabaseGeocodeStore({ supaUrl, supaKey, fetchImpl })
// store.get(normalizedKey) / store.put(normalizedKey, { lat, lng, provider, resolvedAt })
```

- [ ] Write tests proving equivalent whitespace/case forms share one key, a successful first result is persisted, a second process instance performs zero Google calls, and failed/empty responses are not cached as success.
- [ ] Run `node --test lib/geocode-cache.test.js test/mobile-geocode-cost-guard.test.js`; record RED.
- [ ] Add the cache migration and store, then replace `_geoMemo` as the production authority while retaining a small in-process read-through layer.
- [ ] Ensure `travel.js` persists a valid success beyond the process; current `geocodeAddress` already updates `_geoMemo`, but that memo is lost on process restart.
- [ ] Re-run the focused tests and read the staging row back.
- [ ] Commit and push this slice.

### Task 2: Make the Route Cache Durable and Correctly Scoped

- [ ] Add tests for normalized origin/destination, event anchor, timezone, direction, provider, and route mode in the cache key; reject the current shared `_shared` identity.
- [ ] Test TTL expiry, stale metadata, concurrent first writers, and cache availability during budget degradation.
- [ ] Run `node --test lib/route-cache.test.js lib/travel-transit-wire.test.js`; record RED.
- [ ] Wire the existing `lm_route_cache` table through a Supabase store and atomic insert/update path.
- [ ] Keep process Map only as a read-through optimization, never as durable truth.
- [ ] Re-run focused route tests and commit/push.

### Task 3: Preserve Transit Facts and Enforce Sequential Fallback

**Route result shape:**

```javascript
{
  provider, computedAt, timezone, departureAt, arrivalAt, durationSeconds,
  accessWalkSeconds, egressWalkSeconds, transferCount, fare,
  steps: [{ mode, service, headsign, platform, departAt, arriveAt, durationSeconds, geometry }],
  availability: { platform, fare, geometry }
}
```

- [ ] Add tests for event date/timezone and arrive-by outbound/depart-at return queries, preservation of nullable fields, and omission of entrance/exit/best-car/crowding.
- [ ] Add a test where accepted Transit output causes zero Google calls and provider failure causes exactly one budget-authorized Google attempt.
- [ ] Record RED from the current integer-minute projection.
- [ ] Extend `parseTransitPlan`, call `/plan` and guidance with the same anchor, and return the structured result; keep a `.minutes` adapter for unchanged scheduler callers.
- [ ] Re-run route tests and commit/push.

### Task 4: Migrate to a Truthful Cost Event

**Interface:**

```javascript
async function recordProviderCost({
  provider, sku, operation, uid, requestId, quantity, unit,
  pricingVersion, estimatedUsd, actualBilledUsd, actualStatus, metadata
}, deps)
```

- [ ] Write migration/tests requiring all dimensions, `actualStatus` enum validation, nullable actual amount, and owner-visible failed writes.
- [ ] Assert missing actual billing is stored as unknown/null and cannot be coerced to zero.
- [ ] Run `node --test lib/ledger.test.js test/provider-cost-contract.test.js`; record RED.
- [ ] Extend `lm_api_cost`, implement `recordProviderCost`, and retain a narrow compatibility wrapper for old call sites until each adapter migrates.
- [ ] Make failed writes emit a structured owner alert/outbox record while returning failure to the caller.
- [ ] Re-run focused tests, apply staging migration, read rows back, commit, and push.

### Task 5: Instrument Every Provider

- [ ] Add adapter tests for Google Geocoding/Routes, Transit, Composio, Gemini usage/session, Telnyx CDR, Resend sends, Railway allocation, and Supabase allocation.
- [ ] For providers without actual billing, store estimate plus `actual_status=unknown`; for Telnyx CDR store provider actual cost.
- [ ] Replace Composio's unconditional estimated zero with correct operation quantity and explicit billing status.
- [ ] Record Gemini token metadata when supplied; otherwise keep session estimate and unknown actual.
- [ ] Add scheduled import adapters for provider-owned Telnyx/Railway/Supabase measurements without treating a failed import as zero.
- [ ] Run provider contract tests and commit/push in adapter-sized commits.

### Task 6: Enforce the Beta Budget Policy

**Interface:**

```javascript
function evaluateProviderBudget({ measuredUsd, estimatedUsd, thresholds })
// -> { state: "normal"|"warning"|"degraded"|"stopped", totalUsd, reasons }
async function authorizeProviderOperation({ uid, provider, operation, essential, cacheHit }, deps)
```

- [ ] Write tests for warnings at $0.50/day, paid-fallback disablement at $1.00/day, nonessential provider stop at $2.00/day, separate per-user/global voice caps, and unconditional cached reads.
- [ ] Record RED, then implement the pure policy and atomic daily aggregation.
- [ ] Wire Google fallback, nonessential Composio refresh, Gemini optional work, and new calls through the gate. Keep essential cached Calendar/route reads available.
- [ ] Re-run `provider-budget-gate` and call-rate tests; commit/push.

### Task 7: Report, Deploy, and Measure

- [ ] Add an owner report that separately totals measured cost, estimated cost, fixed allocation, and unknown providers.
- [ ] Run the 43-test focused baseline plus all new cost tests, then `npm test` against the clean installed baseline.
- [ ] Deploy the merged gate and verify Railway commit/build identity.
- [ ] Trigger one controlled operation per provider and inspect stored dimensions and failure visibility.
- [ ] Observe seven days of Google Geocoding, Routes, Composio, Transit, Telnyx, Gemini, Resend, Railway, and Supabase usage.
- [ ] Compare to the measured pre-change baseline and publish the daily owner report with remaining unknowns visible.
- [ ] Add the cost completion receipt to the iOS spec, commit, and push.

## Verification Commands

```bash
cd apps/life-manager
node --test lib/travel-transit-wire.test.js lib/transit.test.js lib/route-cache.test.js lib/travel-routes.test.js lib/ledger.test.js lib/composio-budget.test.js
node --test lib/geocode-cache.test.js lib/provider-budget.test.js test/mobile-geocode-cost-guard.test.js test/mobile-route-provider-budget.test.js test/provider-cost-contract.test.js test/provider-budget-gate.test.js
npm test
git diff --check
```

The original focused suite remains at least 43/43 green. Every new focused test passes; the full suite is compared after `npm ci` to the clean-worktree baseline.
