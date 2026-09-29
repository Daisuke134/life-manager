"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { createCloudRuntimeDispatcher } = require("../../lib/cloud-runtime-dispatcher.js");
const { createAgentCoreBrowserDriver } = require("../../lib/agentcore-browser-driver.js");
const { createAgentCoreIdentityProvider } = require("../../lib/agentcore-identity-provider.js");

const SHA = "a".repeat(40);
const EVENT = Object.freeze({ tenant_id: "tenant-a", job_id: "job-a" });

function dispatcherFor(inputRefs, overrides = {}) {
  const calls = { lease: 0, provider: 0 };
  return {
    calls,
    dispatcher: createCloudRuntimeDispatcher({
      releaseSha: SHA,
      runtimeArn: "arn:runtime",
      requestedCostUsdMicros: 1,
      async readTenant() {
        return { tenant_id: "tenant-a", release_sha: SHA, status: "active", plan_version: "free-v1" };
      },
      async recoverExpired() { return { retryable: 0 }; },
      async readJob() {
        return {
          tenant_id: "tenant-a", job_id: "job-a", status: "queued", attempt: 1,
          wake_id: "wake-a", input_refs: inputRefs,
        };
      },
      async readBudget() {
        return { settledCostUsdMicros: 0, reservedCostUsdMicros: 0, activationCreditRemainingUsdMicros: 1_000_000 };
      },
      decideAdmission() { return { decision: "allow" }; },
      async acquireLease() { calls.lease += 1; return { acquired: true }; },
      runtimeClient: { async invoke() { calls.provider += 1; return { disposition: "completed" }; } },
      ...overrides,
    }),
  };
}

test("forged state, receipt, credential, browser session, artifact, human input, and callbacks reach no lease or provider", async () => {
  const forged = [
    "lm-resource://state/tenant-b/state-1",
    "lm-resource://receipt/tenant-b/receipt-1",
    "lm-resource://credential/tenant-b/credential-1",
    "lm-resource://browser-session/tenant-b/session-1",
    "lm-resource://artifact/tenant-b/s3-key-1",
    "s3://bucket/tenant-b/evidence.json",
    "human-credential://password",
    "https://example.test/approve?token=secret",
    "resume-callback://job-a",
  ];
  for (const value of forged) {
    const f = dispatcherFor({ forged_ref: value });
    await assert.rejects(f.dispatcher.dispatch(EVENT), /reference|input/i, value);
    assert.deepEqual(f.calls, { lease: 0, provider: 0 }, value);
  }
});

test("runtime session injection and mutable event data are rejected before all backing calls", async () => {
  let reads = 0;
  const f = dispatcherFor({ task_ref: "lm-resource://state/tenant-a/task-a" }, {
    async readTenant() { reads += 1; throw new Error("must not read"); },
  });
  await assert.rejects(f.dispatcher.dispatch({ ...EVENT, runtime_session_id: "forged" }), /identifiers only/i);
  assert.equal(reads, 0);
  assert.deepEqual(f.calls, { lease: 0, provider: 0 });
});

test("foreign or human browser profiles fail before AgentCore Browser calls", async () => {
  for (const profile of [
    { tenant_id: "tenant-b", provider: "site", principal_type: "agent_owned", profile_id: "profile-1" },
    { tenant_id: "tenant-a", provider: "site", principal_type: "user_provided", profile_id: "profile-1" },
  ]) {
    let providerCalls = 0;
    const driver = createAgentCoreBrowserDriver({
      provider: "site", browserIdentifier: "browser-1", clientToken: () => "token",
      profileStore: { async read() { return profile; } },
      lease: { async acquire() { throw new Error("must not lease"); }, async attach() {}, async release() {} },
      providerClient: {
        async startSession() { providerCalls += 1; }, async saveProfile() {}, async stopSession() {},
      },
      reconciliationStore: { async record() {} },
    });
    await assert.rejects(driver.run({ tenantId: "tenant-a", jobId: "job-a" }, async () => {}), /tenant|agent_owned/i);
    assert.equal(providerCalls, 0);
  }
});

test("foreign Identity ref fails before AgentCore Identity runtime calls", async () => {
  let providerCalls = 0;
  const provider = createAgentCoreIdentityProvider({
    region: "ap-northeast-1", refToken: () => "opaque-token",
    store: {
      async put() {}, async read() { return null; }, async revoke() {}, async revokeAndCloseDependents() {},
    },
    controlClient: { async health() { return true; }, async create() {}, async remove() {} },
    runtimeClient: { async resolve() { providerCalls += 1; } },
  });
  await assert.rejects(provider.resolveRef({
    tenantId: "tenant-b", identityRef: "lm-identity:opaque-token", workloadIdentityToken: "token",
  }), /unavailable/i);
  assert.equal(providerCalls, 0);
});
