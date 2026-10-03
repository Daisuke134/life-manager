"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {
  authorizeProviderOperation, defaultProviderCaps, evaluateProviderBudget, summarizeProviderBudget,
} = require("./provider-budget.js");

test("provider budget states are deterministic and unknown cost is never normal", () => {
  const thresholds = { warningUsd: 8, degradedUsd: 10, stoppedUsd: 12 };
  assert.equal(evaluateProviderBudget({ measuredUsd: 1, estimatedUsd: 1, unknownCount: 0, thresholds }).state, "normal");
  assert.equal(evaluateProviderBudget({ measuredUsd: 7, estimatedUsd: 2, unknownCount: 0, thresholds }).state, "warning");
  assert.equal(evaluateProviderBudget({ measuredUsd: 10, estimatedUsd: 0, unknownCount: 0, thresholds }).state, "degraded");
  assert.equal(evaluateProviderBudget({ measuredUsd: 13, estimatedUsd: 0, unknownCount: 0, thresholds }).state, "stopped");
  const unknown = evaluateProviderBudget({ measuredUsd: 0, estimatedUsd: 0, unknownCount: 1, thresholds });
  assert.equal(unknown.state, "degraded");
  assert.match(unknown.reasons.join(","), /unknown_cost/);
});

test("budget authorization isolates tenants and preserves cache reads", () => {
  const states = new Map([["tenant-a:google_maps", "stopped"], ["tenant-b:google_maps", "normal"]]);
  const deps = { getState: (tenantId, provider) => states.get(`${tenantId}:${provider}`) || "normal" };
  assert.deepEqual(authorizeProviderOperation({ tenantId: "tenant-a", provider: "google_maps", operation: "route", essential: false, cacheHit: false }, deps), {
    allowed: false, state: "stopped", reason: "budget_stopped",
  });
  assert.deepEqual(authorizeProviderOperation({ tenantId: "tenant-a", provider: "google_maps", operation: "route", essential: true, cacheHit: true }, deps), {
    allowed: true, state: "stopped", reason: "cache_hit",
  });
  assert.deepEqual(authorizeProviderOperation({ tenantId: "tenant-b", provider: "google_maps", operation: "route", essential: false, cacheHit: false }, deps), {
    allowed: true, state: "normal", reason: "allowed",
  });
});

test("provider budget summary exposes units, cache hits, estimates, settled, unknown, and observation", () => {
  const summary = summarizeProviderBudget([
    { ts: "2026-10-02T00:00:00Z", tenantId: "a", provider: "google_maps", units: 2, cacheHit: false, estimatedUsd: 0.01, actualUsd: null },
    { ts: "2026-10-02T01:00:00Z", tenantId: "a", provider: "google_maps", units: 0, cacheHit: true, estimatedUsd: 0, actualUsd: null },
    { ts: "2026-10-02T02:00:00Z", tenantId: "a", provider: "google_maps", units: 1, cacheHit: false, estimatedUsd: null, actualUsd: 0.02 },
    { ts: "2026-10-02T02:30:00Z", tenantId: "a", provider: "google_maps", units: 0, cacheHit: false, estimatedUsd: null, actualUsd: null },
  ], { now: "2026-10-02T03:00:00Z" });
  assert.deepEqual(summary, {
    eventCount: 4, providerUnits: 3, cacheHits: 1, estimatedUsd: 0.01,
    settledUsd: 0.02, unknownCount: 1, lastObservedAt: "2026-10-02T02:30:00.000Z",
  });
});

test("default provider caps are explicit and evaluate both currency and units", () => {
  const caps = defaultProviderCaps();
  assert.deepEqual(caps["google_maps:route"], { dailyUsd: 0.5, monthlyUsd: 5, monthlyUnits: 100 });
  assert.equal(evaluateProviderBudget({
    estimatedUsd: 5.01, units: 1, caps: caps["google_maps:route"], period: "monthly",
  }).state, "stopped");
  const byUnits = evaluateProviderBudget({
    estimatedUsd: 0, units: 101, caps: caps["google_maps:route"], period: "monthly",
  });
  assert.equal(byUnits.state, "stopped");
  assert.match(byUnits.reasons.join(","), /cap_exceeded/);
});

test("authorization denies a projected cap breach but keeps essential cache reads", () => {
  const caps = defaultProviderCaps();
  const deps = {
    state: "normal", caps,
    getUsage: () => ({ estimatedUsd: 4.99, units: 99 }),
  };
  const denied = authorizeProviderOperation({
    tenantId: "tenant-a", provider: "google_maps", operation: "route",
    estimatedUsd: 0.01, providerUnits: 2, period: "monthly",
  }, deps);
  assert.equal(denied.allowed, false);
  assert.equal(denied.reason, "cap_exceeded");
  assert.equal(denied.nextAction, "use_cache_or_stop");
  const cache = authorizeProviderOperation({
    tenantId: "tenant-a", provider: "google_maps", operation: "route",
    estimatedUsd: 99, providerUnits: 99, essential: true, cacheHit: true, period: "monthly",
  }, deps);
  assert.deepEqual(cache, {
    allowed: true, state: "normal", reason: "cache_hit",
    capKey: "google_maps:route", capState: "stopped", nextAction: "read_cache",
  });
});
