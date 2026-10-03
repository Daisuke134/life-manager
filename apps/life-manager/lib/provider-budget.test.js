"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {
  authorizeProviderOperation, createSupabaseProviderBudgetAuthorizer, defaultProviderCaps, evaluateProviderBudget, summarizeProviderBudget,
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

test("Supabase provider authorizer reads durable daily/monthly usage and fails closed on read errors", async () => {
  const calls = [];
  const authorize = createSupabaseProviderBudgetAuthorizer({
    supaUrl: "https://db.example", supaKey: "service-key", nowMs: Date.parse("2026-10-03T12:00:00Z"),
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, json: async () => [{ tenant_id: "tenant-a", provider: "google_maps", provider_units: 99, estimated_cost_usd: 4.99, unknown_count: 0 }] };
    },
  });
  const denied = await authorize({ tenantId: "tenant-a", provider: "google_maps", operation: "route", providerUnits: 2, estimatedUsd: 0.01 });
  assert.equal(denied.allowed, false);
  assert.equal(denied.reason, "cap_exceeded");
  assert.equal(calls.length, 2);
  assert.match(calls[0].url, /rpc\/lm_provider_budget_summary/);

  const failClosed = createSupabaseProviderBudgetAuthorizer({
    supaUrl: "https://db.example", supaKey: "service-key", fetchImpl: async () => ({ ok: false, status: 503 }),
  });
  const failed = await failClosed({ tenantId: "tenant-a", provider: "google_maps", operation: "route", providerUnits: 1, estimatedUsd: 0.005 });
  assert.equal(failed.allowed, false);
  assert.equal(failed.reason, "budget_read_failed");
  const malformed = createSupabaseProviderBudgetAuthorizer({
    supaUrl: "https://db.example", supaKey: "service-key", nowMs: Date.parse("2026-10-03T12:00:00Z"),
    fetchImpl: async () => ({ ok: true, json: async () => ({}) }),
  });
  const malformedResult = await malformed({ tenantId: "tenant-a", provider: "google_maps", operation: "route", providerUnits: 1, estimatedUsd: 0.005 });
  assert.equal(malformedResult.allowed, false);
  assert.equal(malformedResult.reason, "budget_read_failed");
  const crossTenant = createSupabaseProviderBudgetAuthorizer({
    supaUrl: "https://db.example", supaKey: "service-key", nowMs: Date.parse("2026-10-03T12:00:00Z"),
    fetchImpl: async () => ({ ok: true, json: async () => [{ tenant_id: "other", provider: "google_maps", provider_units: 0, estimated_cost_usd: 0, unknown_count: 0 }] }),
  });
  const crossTenantResult = await crossTenant({ tenantId: "tenant-a", provider: "google_maps", operation: "route", providerUnits: 1, estimatedUsd: 0.005 });
  assert.equal(crossTenantResult.reason, "budget_read_failed");
  const invalidNumeric = createSupabaseProviderBudgetAuthorizer({
    supaUrl: "https://db.example", supaKey: "service-key", nowMs: Date.parse("2026-10-03T12:00:00Z"),
    fetchImpl: async () => ({ ok: true, json: async () => [{ tenant_id: "tenant-a", provider: "google_maps", provider_units: "NaN", estimated_cost_usd: 0, unknown_count: 0 }] }),
  });
  const invalidNumericResult = await invalidNumeric({ tenantId: "tenant-a", provider: "google_maps", operation: "route", providerUnits: 1, estimatedUsd: 0.005 });
  assert.equal(invalidNumericResult.reason, "budget_read_failed");
  const cache = await failClosed({ tenantId: "tenant-a", provider: "google_maps", operation: "route", cacheHit: true, providerUnits: 0, estimatedUsd: 0 });
  assert.equal(cache.allowed, true);
  assert.equal(cache.reason, "cache_hit");

  const dailyAuthorizer = createSupabaseProviderBudgetAuthorizer({
    supaUrl: "https://db.example", supaKey: "service-key", nowMs: Date.parse("2026-10-03T12:00:00Z"),
    fetchImpl: async (_url, options) => {
      const body = JSON.parse(options.body);
      return { ok: true, json: async () => body.p_period_start.endsWith("T00:00:00.000Z")
        && body.p_period_start.slice(8, 10) === "03"
        ? [{ tenant_id: "tenant-a", provider: "google_maps", provider_units: 99, estimated_cost_usd: 0.49, unknown_count: 0 }]
        : [] };
    },
  });
  const dailyDenied = await dailyAuthorizer({ tenantId: "tenant-a", provider: "google_maps", operation: "route", providerUnits: 2, estimatedUsd: 0.01 });
  assert.equal(dailyDenied.allowed, false);
  assert.equal(dailyDenied.reason, "cap_exceeded");
});

test("Supabase provider authorizer uses a valid clock when nowMs is omitted", async () => {
  const authorize = createSupabaseProviderBudgetAuthorizer({
    supaUrl: "https://db.example", supaKey: "service-key",
    fetchImpl: async () => ({ ok: true, json: async () => [] }),
  });
  const result = await authorize({ tenantId: "tenant-a", provider: "google_maps", operation: "route", providerUnits: 1, estimatedUsd: 0.005 });
  assert.equal(result.allowed, true);
});
