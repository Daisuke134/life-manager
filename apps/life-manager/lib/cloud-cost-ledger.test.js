"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {
  createCloudCostLedger,
  createMemoryCloudCostStore,
  createPostgresCloudCostStore,
  buildCloudUnitEconomicsReport,
  allocateSharedCost,
} = require("./cloud-cost-ledger.js");
const MIGRATION = fs.readFileSync(path.join(__dirname, "../migrations/2026-09-29-lm-cloud-cost-reservations.sql"), "utf8");

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

test("concurrent redelivery cannot share or release the first reservation", async () => {
  const store = createMemoryCloudCostStore();
  const ledger = createCloudCostLedger({ store, now: () => JAN });
  const input = {
    tenantId: "tenant-a", jobId: "job-a", attempt: 1,
    planVersion: "free-v1", tenantStatus: "active", estimatedMaxUsdMicros: 50_000,
  };
  const first = await ledger.reserve(input);
  const second = await ledger.reserve(input);
  assert.equal(first.decision, "allow");
  assert.deepEqual(second, { decision: "duplicate" });
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

test("Postgres adapter uses narrow atomic reservation, settlement, reconciliation, and release RPCs", async () => {
  const calls = [];
  const store = createPostgresCloudCostStore({ query: async (sql, params) => {
    calls.push({ sql, params });
    if (/reserve_lm_cloud_cost/i.test(sql)) return { rows: [{ decision: "allow", reservation_ref: "lm-cost:postgres_ref", reserved_usd_micros: "50000", replay_zero: false }] };
    if (/reconcile_lm_cloud_cost/i.test(sql)) return { rows: [{ status: "reconciling", held_usd_micros: "50000" }] };
    if (/settle_lm_cloud_cost/i.test(sql)) return { rows: [{ status: "settled", actual_cost_usd_micros: "30000", released_usd_micros: "20000", activation_credit_applied_usd_micros: "30000", replay_zero: false }] };
    if (/release_lm_cloud_cost/i.test(sql)) return { rows: [{ released: true }] };
    throw new Error("unexpected SQL");
  } });
  assert.equal((await store.reserveAtomic({ tenant_id: "tenant-a", job_id: "job-a", attempt: 1, plan_version: "free-v1", estimated_max_usd_micros: 50000, reservation_ref: "lm-cost:postgres_ref", now_ms: JAN })).decision, "allow");
  assert.equal((await store.reconcile({ tenant_id: "tenant-a", job_id: "job-a", attempt: 1, reservation_ref: "lm-cost:postgres_ref" })).reserved_usd_micros, 50000);
  assert.equal((await store.settle({ tenant_id: "tenant-a", job_id: "job-a", attempt: 1, reservation_ref: "lm-cost:postgres_ref" }, [usage("r", 30000)], JAN)).row.actual_cost_usd_micros, 30000);
  assert.equal(await store.release("tenant-a", "lm-cost:postgres_ref"), true);
  assert.deepEqual(calls.map(({ sql }) => sql.match(/(reserve|reconcile|settle|release)_lm_cloud_cost/i)[1]), ["reserve", "reconcile", "settle", "release"]);
});

test("cost migration is private, tenant/job scoped, TTL-owned, and receipt-deduplicated", () => {
  assert.match(MIGRATION, /UNIQUE \(tenant_id, job_id, attempt\)/i);
  assert.match(MIGRATION, /expires_at.*interval '5 minutes'/is);
  assert.match(MIGRATION, /FOR UPDATE/i);
  assert.match(MIGRATION, /ON CONFLICT \(provider_receipt_id\) DO NOTHING/i);
  assert.match(MIGRATION, /status='reconciling',expires_at=NULL/i);
  assert.match(MIGRATION, /ENABLE ROW LEVEL SECURITY/i);
  assert.match(MIGRATION, /REVOKE ALL ON TABLE public\.lm_cloud_cost_reservations FROM PUBLIC/i);
});

test("unit economics separates company revenue, every cost, contribution, and user income", () => {
  const records = [
    { scope: "business", kind: "business_revenue", direction: "credit", amount_minor: 4900, currency: "USD", source: { provider: "stripe", external_ref: "sub-1" }, verification: { status: "verified" } },
    { scope: "business", kind: "business_revenue", direction: "credit", amount_minor: 1000, currency: "USD", source: { provider: "market", external_ref: "sale-1" }, verification: { status: "verified" } },
    { scope: "business", kind: "business_cost", direction: "debit", amount_minor: 500, currency: "USD", source: { provider: "stripe", external_ref: "refund-1" }, verification: { status: "verified" } },
    { scope: "business", kind: "fee", direction: "debit", amount_minor: 171, currency: "USD", source: { provider: "stripe", external_ref: "fee-1" }, verification: { status: "verified" } },
    { scope: "personal", kind: "personal_income", direction: "credit", amount_minor: 2000, currency: "USD", source: { provider: "market", external_ref: "income-1" }, verification: { status: "verified" } },
  ];
  const report = buildCloudUnitEconomicsReport({
    tenantId: "tenant-a", monthStart: "2026-01-01", records,
    usage: [
      { provider: "aws", resource: "runtime", cost_usd_micros: 120_000 },
      { provider: "openai", resource: "model", cost_usd_micros: 80_000 },
      { provider: "anicca-shared", resource: "railway", cost_usd_micros: 50_000 },
    ],
    unsettledReservations: 0,
  });
  assert.equal(report.subscription_collected_usd_micros, 49_000_000);
  assert.equal(report.internal_company_revenue_usd_micros, 10_000_000);
  assert.equal(report.refunds_usd_micros, 5_000_000);
  assert.equal(report.stripe_fees_usd_micros, 1_710_000);
  assert.equal(report.variable_cost_usd_micros, 200_000);
  assert.equal(report.allocated_shared_cost_usd_micros, 50_000);
  assert.equal(report.user_income_usd_micros, 20_000_000);
  assert.equal(report.contribution_usd_micros, 52_040_000);
  assert.deepEqual(report.variable_costs, [
    { provider: "aws", resource: "runtime", cost_usd_micros: 120_000 },
    { provider: "openai", resource: "model", cost_usd_micros: 80_000 },
  ]);
});

test("unknown cost makes contribution unknown, and shared allocation preserves every micro", () => {
  const report = buildCloudUnitEconomicsReport({
    tenantId: "tenant-a", monthStart: "2026-01-01", records: [], usage: [], unsettledReservations: 1,
  });
  assert.equal(report.cost_state, "unknown");
  assert.equal(report.contribution_usd_micros, null);
  const allocated = allocateSharedCost(10, ["tenant-c", "tenant-a", "tenant-b"]);
  assert.deepEqual(allocated, [
    { tenant_id: "tenant-a", cost_usd_micros: 4 },
    { tenant_id: "tenant-b", cost_usd_micros: 3 },
    { tenant_id: "tenant-c", cost_usd_micros: 3 },
  ]);
  assert.equal(allocated.reduce((sum, row) => sum + row.cost_usd_micros, 0), 10);
});
