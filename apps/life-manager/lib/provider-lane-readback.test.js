"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  normalizeProviderLanes,
  readProviderLanes,
  reportingPeriodBounds,
} = require("./provider-lane-readback.js");

const ROWS = [
  {
    tenant_id: "tenant-a",
    usage_day: "2026-10-03T00:00:00Z", provider: "openpoi", feature: "places_search",
    outcome: "success", event_count: 2, provider_units: 2, estimated_cost_usd: 0, unknown_count: 0,
  },
  {
    tenant_id: "tenant-a",
    usage_day: "2026-10-03T00:00:00Z", provider: "google_maps", feature: "places_search",
    outcome: "failure", event_count: 1, provider_units: 1, estimated_cost_usd: 0.005, unknown_count: 0,
  },
  {
    tenant_id: "tenant-a",
    usage_day: "2026-10-03T00:00:00Z", provider: "transit_api", feature: "travel_route",
    outcome: "success", event_count: 1, provider_units: 1, estimated_cost_usd: 0, unknown_count: 0,
  },
  {
    tenant_id: "tenant-a",
    usage_day: "2026-10-03T00:00:00Z", provider: "google_maps", feature: "geocoding",
    outcome: "success", event_count: 3, provider_units: 3, estimated_cost_usd: 0.015, unknown_count: 0,
  },
  {
    tenant_id: "tenant-a",
    usage_day: "2026-10-03T00:00:00Z", provider: "geocoder_cache", feature: "geocoding",
    outcome: "cache_hit", event_count: 1, provider_units: 0, estimated_cost_usd: 0, unknown_count: 0,
  },
];

test("normalizes provider usage rows into fresh lanes and bounded fallback counts", () => {
  const result = normalizeProviderLanes(ROWS, {
    reportingDate: "2026-10-03",
    nowMs: Date.parse("2026-10-03T12:00:00Z"),
  });
  assert.equal(result.status, "fresh");
  assert.deepEqual(result.lanes.poi, {
    status: "fresh", primary: "openpoi", fallbackCalls: 1, fallbackCap: 100,
    eventCount: 3, providerUnits: 3, estimatedUsd: 0.005, unknownCount: 0,
  });
  assert.equal(result.lanes.transit.primary, "transit_api");
  assert.equal(result.lanes.transit.fallbackCalls, 0);
  assert.equal(result.lanes.geocoder.primary, "geocoder_cache");
  assert.equal(result.lanes.geocoder.fallbackCalls, 3);
});

test("missing or failed lane readback stays partial instead of becoming zero", () => {
  const result = normalizeProviderLanes([
    { usage_day: "2026-10-03T00:00:00Z", provider: "transit_api", feature: "travel_route", outcome: "failure", event_count: 1, provider_units: 0, estimated_cost_usd: 0 },
  ], { reportingDate: "2026-10-03", nowMs: Date.parse("2026-10-03T12:00:00Z") });
  assert.equal(result.status, "partial");
  assert.equal(result.lanes.poi.status, "partial");
  assert.equal(result.lanes.poi.fallbackCalls, 0);
  assert.equal(result.lanes.transit.status, "partial");
  assert.ok(result.failures.includes("provider_lane_readback_missing:poi"));
  assert.ok(result.failures.includes("provider_lane_no_success:transit"));
});

test("Google-only success is not a fresh free-primary lane", () => {
  const result = normalizeProviderLanes([
    { usage_day: "2026-10-03T00:00:00Z", provider: "google_maps", feature: "places_search", outcome: "success", event_count: 1, provider_units: 1, estimated_cost_usd: 0.005, unknown_count: 0 },
    { usage_day: "2026-10-03T00:00:00Z", provider: "google_maps", feature: "travel_route", outcome: "success", event_count: 1, provider_units: 1, estimated_cost_usd: 0.005, unknown_count: 0 },
    { usage_day: "2026-10-03T00:00:00Z", provider: "google_maps", feature: "geocoding", outcome: "success", event_count: 1, provider_units: 1, estimated_cost_usd: 0.005, unknown_count: 0 },
  ], { reportingDate: "2026-10-03", nowMs: Date.parse("2026-10-03T12:00:00Z") });
  assert.equal(result.status, "partial");
  assert.equal(result.lanes.poi.status, "partial");
  assert.ok(result.failures.includes("provider_lane_primary_missing:poi"));
});

test("provider lane numeric and unknown-cost fields fail closed, and zero units are not fallback calls", () => {
  const result = normalizeProviderLanes([
    { usage_day: "2026-10-03T00:00:00Z", provider: "openpoi", feature: "places_search", outcome: "success", event_count: 1, provider_units: 1, estimated_cost_usd: 0 },
    { usage_day: "2026-10-03T00:00:00Z", provider: "google_maps", feature: "places_search", outcome: "failure", event_count: 1, provider_units: 0, estimated_cost_usd: 0, unknown_count: 0 },
    { usage_day: "2026-10-03T00:00:00Z", provider: "transit_api", feature: "travel_route", outcome: "success", event_count: 1, provider_units: "bad", estimated_cost_usd: 0, unknown_count: 0 },
  ], { reportingDate: "2026-10-03", nowMs: Date.parse("2026-10-03T12:00:00Z") });
  assert.equal(result.lanes.poi.fallbackCalls, 0);
  assert.equal(result.lanes.transit.status, "partial");
  assert.ok(result.failures.includes("provider_lane_numeric_invalid:transit"));
  assert.ok(result.failures.includes("provider_lane_unknown_cost:poi"));
});

test("accepts a UTC day bucket that overlaps the reporting day in JST", () => {
  const result = normalizeProviderLanes([
    { usage_day: "2026-10-02T00:00:00Z", provider: "openpoi", feature: "places_search", outcome: "success", event_count: 1, provider_units: 1, estimated_cost_usd: 0, unknown_count: 0 },
    { usage_day: "2026-10-02T00:00:00Z", provider: "transit_api", feature: "travel_route", outcome: "success", event_count: 1, provider_units: 1, estimated_cost_usd: 0, unknown_count: 0 },
    { usage_day: "2026-10-02T00:00:00Z", provider: "google_maps", feature: "geocoding", outcome: "success", event_count: 1, provider_units: 1, estimated_cost_usd: 0.005, unknown_count: 0 },
    { usage_day: "2026-10-02T00:00:00Z", provider: "geocoder_cache", feature: "geocoding", outcome: "cache_hit", event_count: 1, provider_units: 0, estimated_cost_usd: 0, unknown_count: 0 },
  ], { reportingDate: "2026-10-03", nowMs: Date.parse("2026-10-03T02:00:00Z") });
  assert.equal(result.status, "fresh");
});

test("Supabase readback uses the bounded RPC and returns normalized lane evidence", async () => {
  const calls = [];
  const result = await readProviderLanes({
    supaUrl: "https://db.example",
    supaKey: "service-key",
    tenantId: "tenant-a",
    reportingDate: "2026-10-03",
    nowMs: Date.parse("2026-10-03T12:00:00Z"),
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return { ok: true, async json() { return ROWS; } };
    },
  });
  assert.equal(result.status, "fresh");
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /\/rest\/v1\/rpc\/lm_provider_lane_summary$/);
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    p_period_start: reportingPeriodBounds("2026-10-03").start,
    p_period_end: reportingPeriodBounds("2026-10-03").end,
    p_tenant_id: "tenant-a",
  });
});

test("Supabase readback fails closed on an unusable response", async () => {
  await assert.rejects(() => readProviderLanes({
    supaUrl: "https://db.example", supaKey: "service-key", tenantId: "tenant-a",
    reportingDate: "2026-10-03", fetchImpl: async () => ({ ok: false, status: 503 }),
  }), /provider lane readback failed/);
});

test("Supabase readback rejects an invalid tenant identity", async () => {
  await assert.rejects(() => readProviderLanes({
    supaUrl: "https://db.example", supaKey: "service-key", tenantId: "tenant-a,tenant-b",
    reportingDate: "2026-10-03", fetchImpl: async () => ({ ok: true, json: async () => ROWS }),
  }), /tenant invalid/);
});
