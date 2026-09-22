"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { createCloudCredentialBroker } = require("./cloud-credential-broker.js");
const { createCloudWorkAuthority } = require("./cloud-work-authority.js");

const KEY = Buffer.alloc(32, 29).toString("base64");
const NOW = Date.parse("2026-09-22T12:00:00.000Z");
const RAW_SECRET = "CLOUD_SECRET_MARKER_123";

function job(overrides = {}) {
  return {
    job_id: "goal:financial-continuity:r1", tenant_id: "tenant-a",
    loop_id: "life-manager.manager", capability: "general-agent.work",
    effect_class: "none", effect_key: null,
    input_refs: { goal_ref: "goal-portfolio://tenant-a/financial-continuity?revision=1" },
    max_attempts: 1, attempt: 1, ...overrides,
  };
}

function fixture(overrides = {}) {
  const calls = [];
  const authority = createCloudWorkAuthority({ signingKey: KEY, now: () => NOW });
  const grant = authority.issue({ job: job(), workerId: "cloud-worker-a" });
  const secretProvider = overrides.secretProvider || {
    async health() { calls.push(["health"]); return { ok: true, mode: "cloud", provider: "vault" }; },
    async get(tenantId, ref) { calls.push(["get", tenantId, ref]); return RAW_SECRET; },
  };
  const providerCall = overrides.providerCall || (async (input) => {
    calls.push(["provider", input]);
    assert.equal(input.credentialValue, RAW_SECRET);
    return {
      operation_id: "broker-operation-1",
      status: "completed",
      tenant_id: "tenant-a",
      job_id: "goal:financial-continuity:r1",
      attempt: 1,
      capability: "general-agent.work",
      evidence_refs: ["broker://tenant-a/broker-operation-1/result"],
    };
  });
  const broker = createCloudCredentialBroker({ authority, secretProvider, providerCall });
  return { broker, calls, grant };
}

function invocation(grant, overrides = {}) {
  return {
    grant,
    tenantId: "tenant-a",
    jobId: "goal:financial-continuity:r1",
    attempt: 1,
    workerId: "cloud-worker-a",
    capability: "general-agent.work",
    effectClass: "none",
    credentialRef: "secret://gemini/api-key",
    operation: "gemini.generate-plan",
    inputRefs: { goal_ref: "goal-portfolio://tenant-a/financial-continuity?revision=1" },
    ...overrides,
  };
}

test("valid grant resolves one vault reference internally and returns only a secret-free result", async () => {
  const { broker, calls, grant } = fixture();
  const seenConsole = [];
  const original = { log: console.log, info: console.info, warn: console.warn, error: console.error };
  Object.keys(original).forEach((name) => { console[name] = (...args) => seenConsole.push(args.join(" ")); });
  let result;
  try { result = await broker.invoke(invocation(grant)); }
  finally { Object.assign(console, original); }

  assert.deepEqual(calls.slice(0, 2), [
    ["health"],
    ["get", "tenant-a", "secret://gemini/api-key"],
  ]);
  assert.equal(calls[2][0], "provider");
  assert.deepEqual(result, {
    operation_id: "broker-operation-1",
    status: "completed",
    tenant_id: "tenant-a",
    job_id: "goal:financial-continuity:r1",
    attempt: 1,
    capability: "general-agent.work",
    evidence_refs: ["broker://tenant-a/broker-operation-1/result"],
  });
  assert.equal(Object.isFrozen(result), true);
  assert.equal(Object.isFrozen(result.evidence_refs), true);
  assert.doesNotMatch(JSON.stringify([grant, invocation(grant), result, seenConsole]), new RegExp(RAW_SECRET));
});

test("foreign, tampered, overbroad, and raw-value invocations stop before vault access", async () => {
  const invalid = [
    ["tampered signature", (grant) => {
      const parts = grant.split(".");
      parts[2] = `${parts[2][0] === "A" ? "B" : "A"}${parts[2].slice(1)}`;
      return invocation(parts.join("."));
    }],
    ["foreign tenant", (grant) => invocation(grant, { tenantId: "tenant-b" })],
    ["foreign job", (grant) => invocation(grant, { jobId: "goal:other:r1" })],
    ["foreign attempt", (grant) => invocation(grant, { attempt: 2 })],
    ["foreign worker", (grant) => invocation(grant, { workerId: "cloud-worker-b" })],
    ["foreign capability", (grant) => invocation(grant, { capability: "provider.publish" })],
    ["effectful", (grant) => invocation(grant, { effectClass: "publish" })],
    ["foreign credential", (grant) => invocation(grant, { credentialRef: "secret://other/key" })],
    ["raw credential", (grant) => invocation(grant, { credentialRef: RAW_SECRET })],
    ["foreign operation", (grant) => invocation(grant, { operation: "gemini.raw-secret" })],
    ["foreign goal ref", (grant) => invocation(grant, { inputRefs: { goal_ref: "goal-portfolio://tenant-b/other?revision=1" } })],
    ["same-tenant goal substitution", (grant) => invocation(grant, { inputRefs: { goal_ref: "goal-portfolio://tenant-a/other?revision=1" } })],
    ["same-tenant revision substitution", (grant) => invocation(grant, { inputRefs: { goal_ref: "goal-portfolio://tenant-a/financial-continuity?revision=2" } })],
    ["unknown field", (grant) => ({ ...invocation(grant), extra: true })],
  ];
  for (const [label, make] of invalid) {
    const { broker, calls, grant } = fixture();
    await assert.rejects(broker.invoke(make(grant)), /cloud credential invocation invalid/iu, label);
    assert.deepEqual(calls, []);
  }
});

test("vault and provider failures are generic and never echo secret material", async () => {
  const cases = [
    fixture({ secretProvider: {
      async health() { return { ok: false, mode: "cloud", provider: "vault" }; },
      async get() { throw new Error("must not get"); },
    } }),
    fixture({ secretProvider: {
      async health() { return { ok: true, mode: "cloud", provider: "vault" }; },
      async get() { throw new Error(`vault failed ${RAW_SECRET}`); },
    } }),
    fixture({ providerCall: async () => { throw new Error(`provider failed ${RAW_SECRET}`); } }),
    fixture({ providerCall: async () => ({
      operation_id: RAW_SECRET, status: "completed", tenant_id: "tenant-a",
      job_id: "goal:financial-continuity:r1", attempt: 1,
      capability: "general-agent.work", evidence_refs: ["broker://tenant-a/result"],
    }) }),
  ];
  for (const { broker, grant } of cases) {
    let error;
    try { await broker.invoke(invocation(grant)); } catch (caught) { error = caught; }
    assert.match(error && error.message, /cloud credential broker unavailable/iu);
    assert.doesNotMatch(String(error && error.stack), new RegExp(RAW_SECRET));
  }
});
