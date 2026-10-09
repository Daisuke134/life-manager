"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const { normalizeUsageEvent, recordUsageEvent, runtimeTrace, usageRuntimeEnv } = require("./usage-event.js");

const USAGE_EVENT = { tenantId: "tenant-test", provider: "test", feature: "test", outcome: "success" };

function normalizeMeta(meta) {
  return normalizeUsageEvent({ ...USAGE_EVENT, providerUnits: 1, estimatedCostUsd: 0.005, meta });
}

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
      sku: null,
      operation: "travel_route",
      currency: "USD",
      actual_usd: null,
      billing_status: "estimated",
      pricing_version: "lm-google-maps-estimate-2026-10-08-v1",
      estimate_status: "estimated",
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
  assert.equal(event.meta.actual_usd, 0);
  assert.equal(event.meta.billing_status, "not_applicable");
  assert.equal(event.meta.estimate_status, "not_applicable");
});

test("missing provider quantity and estimate stay unknown, not zero", () => {
  const event = normalizeUsageEvent({
    tenantId: "tenant-1", provider: "gemini", feature: "ask",
    outcome: "failure", failureClass: "usage_unavailable",
    meta: { estimate_status: "unavailable" },
  });

  assert.equal(event.quantity, null);
  assert.equal(event.estUsd, null);
  assert.equal(event.meta.operation, "ask");
  assert.equal(event.meta.sku, null);
  assert.equal(event.meta.actual_usd, null);
  assert.equal(event.meta.billing_status, "unknown");
  assert.equal(event.meta.pricing_version, "lm-gemini-estimate-2026-10-06-v1");
  assert.equal(event.meta.estimate_status, "unavailable");
});

test("an estimate cannot be marked available when its amount is missing", () => {
  const event = normalizeUsageEvent({
    tenantId: "tenant-1", provider: "google_maps", feature: "directions",
    outcome: "failure", estimatedCostUsd: null,
    meta: { estimate_status: "estimated" },
  });

  assert.equal(event.estUsd, null);
  assert.equal(event.meta.estimate_status, "unavailable");
  assert.equal(event.meta.billing_status, "unknown");
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

test("accepts the exact provider metadata enums and scalar types", () => {
  const enums = {
    sku: ["Geocoding", "Directions", "Routes: Compute Routes Pro", "Places - Text Search"],
    pricing_basis: ["list_price_after_free_cap", "list_price_after_free_rpd", "unavailable"],
    route_mode: ["transit", "google"],
    fallback_reason: ["transit_no_route", "transit_provider_4xx", "transit_provider_5xx",
      "transit_network", "transit_timeout", "transit_invalid_response", "non_jp"],
    model: ["gemini-2.5-flash", "gemini-3.7-flash", "gemini-2.5-flash-native-audio-preview-09-2025"],
    estimate_status: ["estimated", "unavailable"],
    estimate_basis: ["audio_duration_proxy"],
  };

  for (const [key, values] of Object.entries(enums)) {
    for (const value of values) assert.equal(normalizeMeta({ [key]: value }).meta[key], value);
    const invalidValues = key === "model" ? ["unsupported", 1, {}, []] : ["unsupported", null, 1, {}, []];
    for (const invalid of invalidValues) {
      assert.throws(() => normalizeMeta({ [key]: invalid }), /metadata/);
    }
  }
  assert.equal(normalizeMeta({ model: null }).meta.model, null);

  for (const key of ["input_tokens", "output_tokens"]) {
    for (const value of [null, 0, 12]) assert.equal(normalizeMeta({ [key]: value }).meta[key], value);
    for (const invalid of [-1, "12", true, NaN, Infinity, {}, []]) {
      assert.throws(() => normalizeMeta({ [key]: invalid }), /metadata/);
    }
  }

  for (const value of [0, 3]) assert.equal(normalizeMeta({ reconnects: value }).meta.reconnects, value);
  for (const invalid of [-1, 1.5, "3", null, {}, []]) {
    assert.throws(() => normalizeMeta({ reconnects: invalid }), /metadata/);
  }
});

test("usage metadata accepts only opaque 64-hex event versions", () => {
  assert.equal(normalizeMeta({ event_version: "b".repeat(64) }).meta.event_version, "b".repeat(64));
  for (const invalid of ["event-id", "b".repeat(63), "b".repeat(65), "B".repeat(64), null, 12]) {
    assert.throws(() => normalizeMeta({ event_version: invalid }), /metadata/);
  }
});

test("rejects unknown and secret-shaped metadata keys and nested values", () => {
  for (const key of ["unknown_field", "customer_email", "api_key", "authorization", "secret_token"]) {
    assert.throws(() => normalizeMeta({ [key]: "synthetic-value" }), /metadata|secret-shaped/);
  }

  const allowedKeys = ["sku", "pricing_basis", "route_mode", "fallback_reason", "model",
    "input_tokens", "output_tokens", "estimate_status", "reconnects", "estimate_basis"];
  for (const key of allowedKeys) {
    for (const nested of [{ nested: "value" }, ["value"]]) {
      assert.throws(() => normalizeMeta({ [key]: nested }), /metadata/);
    }
  }
  assert.throws(() => normalizeMeta({ model: "api_key=synthetic-secret" }), /metadata/);
});

test("rejects metadata keys inherited from the validator object prototype", () => {
  for (const key of ["constructor", "toString", "__proto__"]) {
    assert.throws(() => normalizeMeta({ [key]: "synthetic-value" }));
  }
});

test("recordUsageEvent sends validated provider metadata to the existing cost sink", async () => {
  const metadata = {
    sku: "Routes: Compute Routes Pro",
    pricing_basis: "list_price_after_free_cap",
    route_mode: "transit",
    fallback_reason: "transit_timeout",
    model: "gemini-2.5-flash",
    input_tokens: null,
    output_tokens: 12,
    estimate_status: "unavailable",
    reconnects: 2,
    estimate_basis: "audio_duration_proxy",
  };
  const rows = [];
  const ok = await recordUsageEvent({ ...USAGE_EVENT, providerUnits: 1, meta: metadata }, {
    recordCost: async (row) => { rows.push(row); return true; },
    runtimeEnv: {},
  });

  assert.equal(ok, true);
  assert.equal(rows.length, 1);
  for (const [key, value] of Object.entries(metadata)) assert.equal(rows[0].meta[key], value);
  assert.equal(rows[0].meta.runtime_trace.status, "unlinked");
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

test("recordUsageEvent links unscoped life-call usage to the shared service owner", async () => {
  const envKeys = [
    "RAILWAY_SERVICE_NAME", "RAILWAY_GIT_COMMIT_SHA",
    "LIFE_MANAGER_LOOP_ID", "LIFE_MANAGER_OWNER_ID", "LIFE_MANAGER_RUN_ID",
    "LIFE_MANAGER_OCCURRENCE_ID", "LIFE_MANAGER_RELEASE_SHA",
  ];
  const previous = Object.fromEntries(envKeys.map((key) => [key, process.env[key]]));
  for (const key of envKeys) delete process.env[key];
  process.env.RAILWAY_SERVICE_NAME = "life-call";
  process.env.RAILWAY_GIT_COMMIT_SHA = "f".repeat(40);
  try {
    const rows = [];
    const ok = await recordUsageEvent({
      tenantId: "tenant-1", provider: "google_maps", feature: "ask_resolve_location",
      outcome: "success", providerUnits: 1, providerUnit: "request", estimatedCostUsd: 0.04,
    }, { recordCost: async (row) => { rows.push(row); return true; } });

    assert.equal(ok, true);
    assert.equal(rows.length, 1);
    const trace = rows[0].meta.runtime_trace;
    assert.equal(trace.status, "partial");
    assert.equal(trace.tenant_id, "tenant-1");
    assert.equal(trace.owner_id, "life-call");
    assert.match(trace.run_id, /^run-[0-9a-f-]{36}$/);
    assert.equal(trace.occurrence_id, `life-call:${trace.run_id}`);
    assert.equal(trace.release_sha, "f".repeat(40));
    assert.deepEqual(trace.missing_fields, ["loop_id"]);
    assert.equal(JSON.stringify(rows[0]).includes("RAILWAY_SERVICE_NAME"), false);
  } finally {
    for (const key of envKeys) {
      if (previous[key] === undefined) delete process.env[key];
      else process.env[key] = previous[key];
    }
  }
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

test("provider usage accepts owner-scoped occurrences when loop identity is absent", () => {
  const event = normalizeUsageEvent({
    tenantId: "tenant-1", provider: "google_maps", feature: "travel_route",
    outcome: "success", providerUnits: 1, providerUnit: "request", estimatedCostUsd: 0.005,
  }, {
    LIFE_MANAGER_OWNER_ID: "life-call-travel",
    LIFE_MANAGER_RUN_ID: "route-123",
    LIFE_MANAGER_OCCURRENCE_ID: "life-call-travel:route-123",
    LIFE_MANAGER_RELEASE_SHA: "a".repeat(40),
  });

  assert.deepEqual(event.meta.runtime_trace, {
    schema_version: 1,
    status: "partial",
    tenant_id: "tenant-1",
    owner_id: "life-call-travel",
    run_id: "route-123",
    occurrence_id: "life-call-travel:route-123",
    release_sha: "a".repeat(40),
    missing_fields: ["loop_id"],
  });
});

test("provider usage rejects an occurrence belonging to another owner without loop identity", () => {
  const event = normalizeUsageEvent({
    tenantId: "tenant-1", provider: "google_maps", feature: "travel_route",
    outcome: "success", providerUnits: 1, providerUnit: "request", estimatedCostUsd: 0.005,
  }, {
    LIFE_MANAGER_OWNER_ID: "life-call-travel",
    LIFE_MANAGER_RUN_ID: "route-123",
    LIFE_MANAGER_OCCURRENCE_ID: "foreign-owner:route-123",
    LIFE_MANAGER_RELEASE_SHA: "b".repeat(40),
  });

  assert.deepEqual(event.meta.runtime_trace, {
    schema_version: 1,
    status: "partial",
    tenant_id: "tenant-1",
    owner_id: "life-call-travel",
    run_id: "route-123",
    release_sha: "b".repeat(40),
    missing_fields: ["loop_id", "occurrence_id"],
  });
  assert.equal(JSON.stringify(event.meta.runtime_trace).includes("foreign-owner"), false);
});

test("usage runtime context creates an allowlisted, unique life-call fallback", () => {
  assert.equal(typeof usageRuntimeEnv, "function");
  const source = {
    RAILWAY_SERVICE_NAME: "life-call",
    RAILWAY_GIT_COMMIT_SHA: "f".repeat(40),
    STRIPE_SECRET_KEY: "must-not-enter-runtime-metadata",
    LIFE_MANAGER_PRIVATE_CONTEXT: "must-not-be-copied",
  };
  const first = usageRuntimeEnv(source, { fallbackOwnerId: "life-call-voice" });
  const second = usageRuntimeEnv(source, { fallbackOwnerId: "life-call-voice" });

  assert.equal(first.LIFE_MANAGER_OWNER_ID, "life-call-voice");
  assert.match(first.LIFE_MANAGER_RUN_ID, /^run-[0-9a-f-]{36}$/);
  assert.equal(first.LIFE_MANAGER_OCCURRENCE_ID, `life-call-voice:${first.LIFE_MANAGER_RUN_ID}`);
  assert.equal(first.LIFE_MANAGER_RELEASE_SHA, "f".repeat(40));
  assert.equal(Object.hasOwn(first, "LIFE_MANAGER_LOOP_ID"), false);
  assert.notEqual(first.LIFE_MANAGER_RUN_ID, second.LIFE_MANAGER_RUN_ID);
  assert.deepEqual(Object.keys(first).sort(), [
    "LIFE_MANAGER_OCCURRENCE_ID", "LIFE_MANAGER_OWNER_ID",
    "LIFE_MANAGER_RELEASE_SHA", "LIFE_MANAGER_RUN_ID",
  ]);
  assert.equal(JSON.stringify(first).includes("must-not-enter-runtime-metadata"), false);
  assert.deepEqual(runtimeTrace({ tenantId: "tenant-1" }, first).missing_fields, ["loop_id"]);
});

test("usage runtime context keeps managed partial identity and rejects non-life-call Railway fallback", () => {
  assert.equal(typeof usageRuntimeEnv, "function");
  const partial = usageRuntimeEnv({
    LIFE_MANAGER_OWNER_ID: "managed-owner",
    RAILWAY_SERVICE_NAME: "life-call",
    RAILWAY_GIT_COMMIT_SHA: "a".repeat(40),
  }, { fallbackOwnerId: "life-call-voice" });
  const otherService = usageRuntimeEnv({
    RAILWAY_SERVICE_NAME: "unrelated-service",
    RAILWAY_GIT_COMMIT_SHA: "b".repeat(40),
    STRIPE_SECRET_KEY: "must-not-be-copied",
  }, { fallbackOwnerId: "life-call-voice" });

  assert.deepEqual(partial, { LIFE_MANAGER_OWNER_ID: "managed-owner" });
  assert.deepEqual(otherService, {});
});
