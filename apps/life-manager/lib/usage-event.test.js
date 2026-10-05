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
      runtime_trace: {
        schema_version: 1,
        status: "unlinked",
        tenant_id: "tenant-1",
        missing_fields: ["loop_id", "owner_id", "run_id", "occurrence_id", "release_sha"],
      },
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
  assert.throws(() => normalizeUsageEvent({
    tenantId: "t", provider: "p", feature: "f", outcome: "success",
    meta: { runtime_trace: { run_id: "forged" } },
  }), /runtime_trace metadata is reserved/);
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

test("provider cost rows retain validated runtime identity for loop-level joins", async () => {
  const rows = [];
  await recordUsageEvent({
    tenantId: "tenant-1", provider: "google_maps", feature: "travel_route",
    outcome: "success", providerUnits: 1, providerUnit: "request", estimatedCostUsd: 0.005,
  }, {
    recordCost: async (row) => { rows.push(row); return true; },
    runtimeEnv: {
      LIFE_MANAGER_LOOP_ID: "life-manager-cfo-hourly",
      LIFE_MANAGER_OWNER_ID: "",
      LIFE_MANAGER_RUN_ID: "run-20261005-1",
      LIFE_MANAGER_OCCURRENCE_ID: "life-manager-cfo-hourly:older-claim",
      LIFE_MANAGER_RELEASE_SHA: "a".repeat(40),
      STRIPE_SECRET_KEY: "must-not-be-recorded",
    },
  });

  assert.deepEqual(rows[0].meta.runtime_trace, {
    schema_version: 1,
    status: "linked",
    tenant_id: "tenant-1",
    loop_id: "life-manager-cfo-hourly",
    owner_id: "life-manager-cfo-hourly",
    run_id: "run-20261005-1",
    occurrence_id: "life-manager-cfo-hourly:older-claim",
    release_sha: "a".repeat(40),
  });
  assert.equal(JSON.stringify(rows[0]).includes("must-not-be-recorded"), false);
});

test("provider usage without runtime identity is explicitly unlinked", () => {
  const event = normalizeUsageEvent({
    tenantId: "tenant-1", provider: "gemini", feature: "ask",
    outcome: "success", providerUnits: 1, providerUnit: "token", estimatedCostUsd: 0.001,
  }, {});

  assert.deepEqual(event.meta.runtime_trace, {
    schema_version: 1,
    status: "unlinked",
    tenant_id: "tenant-1",
    missing_fields: ["loop_id", "owner_id", "run_id", "occurrence_id", "release_sha"],
  });
});

test("provider usage does not link a foreign occurrence or malformed release to the current loop", async () => {
  const rows = [];
  await recordUsageEvent({
    tenantId: "tenant-1", provider: "google_maps", feature: "travel_route",
    outcome: "success", providerUnits: 1, providerUnit: "request", estimatedCostUsd: 0.005,
  }, {
    recordCost: async (row) => { rows.push(row); return true; },
    runtimeEnv: {
      LIFE_MANAGER_LOOP_ID: "life-manager-cfo-hourly",
      LIFE_MANAGER_OWNER_ID: "life-manager-cfo-hourly",
      LIFE_MANAGER_RUN_ID: "run-20261005-2",
      LIFE_MANAGER_OCCURRENCE_ID: "another-loop:old-claim",
      LIFE_MANAGER_RELEASE_SHA: "a".repeat(41),
    },
  });

  assert.deepEqual(rows[0].meta.runtime_trace, {
    schema_version: 1,
    status: "partial",
    tenant_id: "tenant-1",
    loop_id: "life-manager-cfo-hourly",
    owner_id: "life-manager-cfo-hourly",
    run_id: "run-20261005-2",
    missing_fields: ["occurrence_id", "release_sha"],
  });
  assert.equal(JSON.stringify(rows[0].meta.runtime_trace).includes("a".repeat(41)), false);
});

test("provider usage excludes secret-shaped runtime identifiers", () => {
  const event = normalizeUsageEvent({
    tenantId: "tenant-1", provider: "gemini", feature: "ask",
    outcome: "success", providerUnits: 1, providerUnit: "token", estimatedCostUsd: 0.001,
  }, {
    LIFE_MANAGER_LOOP_ID: "life-manager-cfo-hourly",
    LIFE_MANAGER_OWNER_ID: "life-manager-cfo-hourly",
    LIFE_MANAGER_RUN_ID: "sk-abcdefghijklmnop1234",
    LIFE_MANAGER_OCCURRENCE_ID: "life-manager-cfo-hourly:sk-abcdefghijklmnop1234",
    LIFE_MANAGER_RELEASE_SHA: "c".repeat(40),
  });

  assert.deepEqual(event.meta.runtime_trace, {
    schema_version: 1,
    status: "partial",
    tenant_id: "tenant-1",
    loop_id: "life-manager-cfo-hourly",
    owner_id: "life-manager-cfo-hourly",
    release_sha: "c".repeat(40),
    missing_fields: ["run_id", "occurrence_id"],
  });
  assert.equal(JSON.stringify(event).includes("sk-abcdefghijklmnop1234"), false);
});

test("provider usage excludes runtime IDs rejected by the runtime event secret filter", () => {
  const event = normalizeUsageEvent({
    tenantId: "tenant-1", provider: "gemini", feature: "ask",
    outcome: "success", providerUnits: 1, providerUnit: "token", estimatedCostUsd: 0.001,
  }, {
    LIFE_MANAGER_LOOP_ID: "life-manager-cfo-hourly",
    LIFE_MANAGER_RUN_ID: "auth.json",
    LIFE_MANAGER_OCCURRENCE_ID: "life-manager-cfo-hourly:run-20261005-3",
    LIFE_MANAGER_RELEASE_SHA: "d".repeat(40),
  });

  assert.deepEqual(event.meta.runtime_trace, {
    schema_version: 1,
    status: "partial",
    tenant_id: "tenant-1",
    loop_id: "life-manager-cfo-hourly",
    owner_id: "life-manager-cfo-hourly",
    occurrence_id: "life-manager-cfo-hourly:run-20261005-3",
    release_sha: "d".repeat(40),
    missing_fields: ["run_id"],
  });
  assert.equal(JSON.stringify(event).includes("auth.json"), false);
});

test("provider usage rejects runtime IDs matching runtime-event secret assignments", () => {
  for (const secretValue of [
    "token:synthetic-value", "password:synthetic-value",
    "credential:synthetic-value", "api-key:synthetic-value",
  ]) {
    const event = normalizeUsageEvent({
      tenantId: "tenant-1", provider: "gemini", feature: "ask",
      outcome: "success", providerUnits: 1, providerUnit: "token", estimatedCostUsd: 0.001,
    }, {
      LIFE_MANAGER_LOOP_ID: "life-manager-cfo-hourly",
      LIFE_MANAGER_OWNER_ID: "life-manager-cfo-hourly",
      LIFE_MANAGER_RUN_ID: secretValue,
      LIFE_MANAGER_OCCURRENCE_ID: `life-manager-cfo-hourly:${secretValue}`,
      LIFE_MANAGER_RELEASE_SHA: "e".repeat(40),
    });

    assert.equal(event.meta.runtime_trace.status, "partial");
    assert.equal(Object.hasOwn(event.meta.runtime_trace, "run_id"), false);
    assert.equal(Object.hasOwn(event.meta.runtime_trace, "occurrence_id"), false);
    assert.deepEqual(event.meta.runtime_trace.missing_fields, ["run_id", "occurrence_id"]);
    assert.equal(JSON.stringify(event.meta.runtime_trace).includes(secretValue), false);
  }
});

test("provider event identity cannot override the trusted runtime environment", async () => {
  const rows = [];
  await recordUsageEvent({
    tenantId: "tenant-1", provider: "google_maps", feature: "travel_route",
    outcome: "success", providerUnits: 1, providerUnit: "request", estimatedCostUsd: 0.005,
    loopId: "event-loop", ownerId: "event-owner", runId: "event-run",
    occurrenceId: "event-loop:event-run", releaseSha: "f".repeat(40),
  }, {
    recordCost: async (row) => { rows.push(row); return true; },
    runtimeEnv: {
      LIFE_MANAGER_LOOP_ID: "life-manager-cfo-hourly",
      LIFE_MANAGER_RUN_ID: "runtime-run",
      LIFE_MANAGER_OCCURRENCE_ID: "life-manager-cfo-hourly:older-claim",
      LIFE_MANAGER_RELEASE_SHA: "a".repeat(40),
    },
  });

  assert.deepEqual(rows[0].meta.runtime_trace, {
    schema_version: 1,
    status: "linked",
    tenant_id: "tenant-1",
    loop_id: "life-manager-cfo-hourly",
    owner_id: "life-manager-cfo-hourly",
    run_id: "runtime-run",
    occurrence_id: "life-manager-cfo-hourly:older-claim",
    release_sha: "a".repeat(40),
  });
  assert.equal(JSON.stringify(rows[0].meta.runtime_trace).includes("event-loop"), false);
  assert.equal(JSON.stringify(rows[0].meta.runtime_trace).includes("event-run"), false);
});
