"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const { normalizeUsageEvent, recordUsageEvent } = require("./usage-event.js");

test("normalizes a tenant/provider/feature usage event without customer billing", () => {
  assert.deepEqual(normalizeUsageEvent({
    tenantId: "tenant-1",
    provider: "google_maps",
    feature: "travel_route",
    outcome: "failure",
    failureClass: "provider_4xx",
    cacheHit: false,
    providerUnits: 1,
    providerUnit: "request",
    estimatedCostUsd: 0.005,
  }), {
    uid: "tenant-1",
    kind: "provider_usage",
    quantity: 1,
    unit: "request",
    estUsd: 0.005,
    meta: {
      provider: "google_maps",
      feature: "travel_route",
      outcome: "failure",
      failure_class: "provider_4xx",
      cache_hit: false,
      customer_usage: false,
    },
  });
});

test("cache hits carry zero provider units and zero estimated cost", () => {
  const event = normalizeUsageEvent({
    tenantId: "tenant-1", provider: "google_maps", feature: "travel_route",
    outcome: "cache_hit", cacheHit: true, providerUnits: 99, estimatedCostUsd: 12,
  });
  assert.equal(event.quantity, 0);
  assert.equal(event.estUsd, 0);
  assert.equal(event.meta.cache_hit, true);
});

test("rejects missing dimensions, invalid outcomes, and secret-shaped metadata", () => {
  assert.throws(() => normalizeUsageEvent({ tenantId: "t", provider: "p" }), /feature/);
  assert.throws(() => normalizeUsageEvent({
    tenantId: "t", provider: "p", feature: "f", outcome: "maybe",
  }), /outcome/);
  assert.throws(() => normalizeUsageEvent({
    tenantId: "t", provider: "p", feature: "f", outcome: "success",
    meta: { api_key: "do-not-store" },
  }), /secret-shaped/);
});

test("recordUsageEvent delegates the normalized row to the existing cost ledger", async () => {
  const rows = [];
  const ok = await recordUsageEvent({
    tenantId: "tenant-1", provider: "gemini", feature: "ask",
    outcome: "success", providerUnits: 42, providerUnit: "tokens",
    estimatedCostUsd: 0.001,
  }, { recordCost: async (row) => { rows.push(row); return true; } });
  assert.equal(ok, true);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].kind, "provider_usage");
  assert.equal(rows[0].meta.customer_usage, false);
});

test("usage event can carry an actual settlement without converting missing actual to zero", () => {
  const event = normalizeUsageEvent({
    tenantId: "tenant-1", provider: "google_cloud", feature: "maps",
    outcome: "success", providerUnits: 2, estimatedCostUsd: 0.01,
    billingStatus: "settled", actualCostUsd: 0.02, sourceReceiptRef: "google-billing://receipt",
  });
  assert.equal(event.billingStatus, "settled");
  assert.equal(event.actualUsd, 0.02);
  assert.equal(event.sourceReceiptRef, "google-billing://receipt");
});
