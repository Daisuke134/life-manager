"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { createAgentCoreRuntimeClient } = require("../../lib/agentcore-runtime-client.js");
const { createCloudRuntimeDispatcher } = require("../../lib/cloud-runtime-dispatcher.js");
const {
  createMemoryBrowserSessionLeaseStore,
  createBrowserSessionLeaseCoordinator,
} = require("../../lib/browser-session-lease.js");

const SHA = "a".repeat(40);
const INVOCATION = Object.freeze({
  runtimeArn: "arn:runtime", tenantId: "tenant-a", jobId: "job-a", attempt: 1,
  releaseSha: SHA,
  request: { tenant_id: "tenant-a", job_id: "job-a" },
});

test("pre-effect crash retries; accepted timeout and post-effect disconnect quarantine", async () => {
  for (const [error, disposition] of [
    [Object.assign(new Error("pre-effect provider unavailable"), { name: "ServiceUnavailableException", accepted: false }), "retry"],
    [Object.assign(new Error("AWS timeout after acceptance"), { name: "TimeoutError" }), "reconcile"],
    [Object.assign(new Error("browser disconnected after click"), { accepted: true }), "reconcile"],
  ]) {
    const client = createAgentCoreRuntimeClient({ async invoke() { throw error; } });
    const result = await client.invoke(INVOCATION);
    assert.equal(result.disposition, disposition);
    assert.equal(result.retryable, disposition === "retry");
  }
});

test("Inngest redelivery acquires one lease and invokes one effect only", async () => {
  let leased = false;
  let providerCalls = 0;
  const dispatcher = createCloudRuntimeDispatcher({
    releaseSha: SHA, runtimeArn: "arn:runtime", requestedCostUsdMicros: 1,
    async readTenant() { return { tenant_id: "tenant-a", release_sha: SHA, status: "active", plan_version: "free-v1" }; },
    async recoverExpired() { return { retryable: 0 }; },
    async readJob() {
      return { tenant_id: "tenant-a", job_id: "job-a", status: "queued", attempt: 1, wake_id: "wake-a", input_refs: { task_ref: "lm-resource://state/tenant-a/task-a" } };
    },
    async readBudget() { return { settledCostUsdMicros: 0, reservedCostUsdMicros: 0, activationCreditRemainingUsdMicros: 1_000_000 }; },
    decideAdmission() { return { decision: "allow" }; },
    async acquireLease() { if (leased) return { acquired: false }; leased = true; return { acquired: true }; },
    runtimeClient: { async invoke() { providerCalls += 1; return { disposition: "completed" }; } },
  });
  const [first, redelivery] = await Promise.all([
    dispatcher.dispatch({ tenant_id: "tenant-a", job_id: "job-a" }),
    dispatcher.dispatch({ tenant_id: "tenant-a", job_id: "job-a" }),
  ]);
  assert.deepEqual(new Set([first.disposition, redelivery.disposition]), new Set(["completed", "duplicate"]));
  assert.equal(providerCalls, 1);
});

test("stale browser lease releases the exact provider session once before a new owner", async () => {
  let now = 1_000_000;
  const releases = [];
  const lease = createBrowserSessionLeaseCoordinator(createMemoryBrowserSessionLeaseStore(), {
    now: () => now, ttlMs: 30_000, token: (() => { let n = 0; return () => `00000000-0000-4000-8000-${String(++n).padStart(12, "0")}`; })(),
    async releaseProviderSession(sessionId) { releases.push(sessionId); return true; },
  });
  const first = await lease.acquire({ tenantId: "tenant-a", ownerId: "owner-a" });
  await lease.attach({ ...first, sessionId: "session-a" });
  now += 30_001;
  await lease.acquire({ tenantId: "tenant-a", ownerId: "owner-b" });
  assert.deepEqual(releases, ["session-a"]);
});

test("old release and expired external-effect recovery never invoke the provider", async () => {
  for (const scenario of ["old_release", "external_effect_expired"]) {
    let invokes = 0;
    const dispatcher = createCloudRuntimeDispatcher({
      releaseSha: SHA, runtimeArn: "arn:runtime", requestedCostUsdMicros: 1,
      async readTenant() { return { tenant_id: "tenant-a", release_sha: scenario === "old_release" ? "b".repeat(40) : SHA, status: "active", plan_version: "free-v1" }; },
      async recoverExpired() { return { quarantined: 1 }; },
      async readJob() { return scenario === "external_effect_expired" ? null : { tenant_id: "tenant-a" }; },
      async readBudget() { throw new Error("must not budget"); },
      decideAdmission() { throw new Error("must not admit"); },
      async acquireLease() { throw new Error("must not lease"); },
      runtimeClient: { async invoke() { invokes += 1; } },
    });
    const result = await dispatcher.dispatch({ tenant_id: "tenant-a", job_id: "job-a" });
    assert.equal(result.disposition, scenario === "old_release" ? "release_mismatch" : "not_applicable");
    assert.equal(invokes, 0);
  }
});
