"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  createCloudCostLedger,
  createMemoryCloudCostStore,
} = require("./cloud-cost-ledger.js");

const JAN = Date.parse("2026-01-31T23:59:00Z");
function usage(receipt, cost, overrides = {}) {
  return {
    tenant_id: "tenant-a", job_id: "job-a", provider: "aws",
    resource: "runtime", quantity: 1, unit: "second",
    cost_usd_micros: cost, provider_receipt_id: receipt,
    ...overrides,
  };
}

test("reserve then settle actual releases remainder and provider receipt replay is zero", async () => {
  const store = createMemoryCloudCostStore();
  const ledger = createCloudCostLedger({ store, now: () => JAN });
  const reserved = await ledger.reserve({
    tenantId: "tenant-a", jobId: "job-a", attempt: 1,
    planVersion: "free-v1", tenantStatus: "active", estimatedMaxUsdMicros: 100_000,
  });
  assert.equal(reserved.decision, "allow");
  const first = await ledger.settle({
    tenantId: "tenant-a", jobId: "job-a", attempt: 1,
    reservationRef: reserved.reservation_ref,
    usage: [usage("receipt-1", 40_000)],
  });
  assert.deepEqual(first, {
    status: "settled", actual_cost_usd_micros: 40_000,
    released_usd_micros: 60_000, activation_credit_applied_usd_micros: 40_000,
    replay_zero: false,
  });
  const replay = await ledger.settle({
    tenantId: "tenant-a", jobId: "job-a", attempt: 1,
    reservationRef: reserved.reservation_ref,
    usage: [usage("receipt-1", 40_000)],
  });
  assert.equal(replay.replay_zero, true);
  assert.equal((await store.snapshot("tenant-a", Date.parse("2026-01-15T00:00:00Z"))).usage_count, 1);
});

test("provider receipt collision, foreign tenant, and actual above reservation fail closed", async () => {
  const store = createMemoryCloudCostStore();
  const ledger = createCloudCostLedger({ store, now: () => JAN });
  const reserve = () => ledger.reserve({
    tenantId: "tenant-a", jobId: "job-a", attempt: 1,
    planVersion: "free-v1", tenantStatus: "active", estimatedMaxUsdMicros: 50_000,
  });
  const held = await reserve();
  await assert.rejects(ledger.settle({
    tenantId: "tenant-b", jobId: "job-a", attempt: 1,
    reservationRef: held.reservation_ref, usage: [usage("r", 1, { tenant_id: "tenant-b" })],
  }), /reservation|tenant/i);
  await assert.rejects(ledger.settle({
    tenantId: "tenant-a", jobId: "job-a", attempt: 1,
    reservationRef: held.reservation_ref, usage: [usage("r", 50_001)],
  }), /reservation/i);
});

test("missing provider usage holds the reservation in reconciliation and never assumes zero", async () => {
  const store = createMemoryCloudCostStore();
  const ledger = createCloudCostLedger({ store, now: () => JAN });
  const held = await ledger.reserve({
    tenantId: "tenant-a", jobId: "job-a", attempt: 1,
    planVersion: "free-v1", tenantStatus: "active", estimatedMaxUsdMicros: 50_000,
  });
  const result = await ledger.settle({
    tenantId: "tenant-a", jobId: "job-a", attempt: 1,
    reservationRef: held.reservation_ref, usage: null,
  });
  assert.deepEqual(result, { status: "reconciling", reason: "cost_unknown", held_usd_micros: 50_000 });
  const denied = await ledger.reserve({
    tenantId: "tenant-a", jobId: "job-b", attempt: 1,
    planVersion: "free-v1", tenantStatus: "active", estimatedMaxUsdMicros: 1_450_001,
  });
  assert.equal(denied.decision, "budget_exhausted");
});

test("month boundary resets monthly spend but never restores consumed activation credit", async () => {
  let now = JAN;
  const store = createMemoryCloudCostStore();
  const ledger = createCloudCostLedger({ store, now: () => now });
  const held = await ledger.reserve({
    tenantId: "tenant-a", jobId: "job-a", attempt: 1,
    planVersion: "free-v1", tenantStatus: "active", estimatedMaxUsdMicros: 1_000_000,
  });
  await ledger.settle({
    tenantId: "tenant-a", jobId: "job-a", attempt: 1,
    reservationRef: held.reservation_ref, usage: [usage("jan", 1_000_000)],
  });
  now = Date.parse("2026-02-01T00:01:00Z");
  const feb = await ledger.reserve({
    tenantId: "tenant-a", jobId: "job-b", attempt: 1,
    planVersion: "free-v1", tenantStatus: "active", estimatedMaxUsdMicros: 500_001,
  });
  assert.equal(feb.decision, "budget_exhausted");
});
