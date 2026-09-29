"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { runtimeSessionId } = require("./agentcore-runtime-client.js");
const {
  createCloudRuntimeDispatcher,
  createProductionCloudRuntimeDispatcher,
} = require("./cloud-runtime-dispatcher.js");

const RELEASE_SHA = "a".repeat(40);
const EVENT = Object.freeze({ tenant_id: "tenant-a", job_id: "job-a" });
const TENANT = Object.freeze({
  tenant_id: "tenant-a",
  region: "ap-northeast-1",
  release_sha: RELEASE_SHA,
  status: "active",
  plan_version: "free-v1",
});
const JOB = Object.freeze({
  tenant_id: "tenant-a",
  job_id: "job-a",
  status: "queued",
  attempt: 1,
  wake_id: "wake-a",
  input_refs: { task_ref: "lm-resource://state/tenant-a/task-a" },
});

function fixture(overrides = {}) {
  const calls = [];
  let invokes = 0;
  const dependencies = {
    releaseSha: RELEASE_SHA,
    runtimeArn: "arn:aws:bedrock-agentcore:ap-northeast-1:000000000000:runtime/life-manager",
    leaseOwner: "dispatcher-a",
    leaseSeconds: 180,
    requestedCostUsdMicros: 20_000,
    async readTenant(input) { calls.push(["tenant", input]); return TENANT; },
    async readJob(input) { calls.push(["job", input]); return JOB; },
    async readBudget(input) {
      calls.push(["budget", input]);
      return {
        settledCostUsdMicros: 10_000,
        reservedCostUsdMicros: 5_000,
        activationCreditRemainingUsdMicros: 1_000_000,
      };
    },
    decideAdmission(input) { calls.push(["admission", input]); return { decision: "allow" }; },
    async acquireLease(input) { calls.push(["lease", input]); return { acquired: true, lease: input }; },
    runtimeClient: {
      async invoke(input) {
        calls.push(["invoke", input]); invokes += 1;
        return { disposition: "completed", result: { status: "completed" } };
      },
    },
    ...overrides,
  };
  return {
    calls,
    dependencies,
    invokes: () => invokes,
    dispatcher: createCloudRuntimeDispatcher(dependencies),
  };
}

test("refetches tenant and job, checks budget and release, atomically leases, then invokes once", async () => {
  const f = fixture();
  const result = await f.dispatcher.dispatch(EVENT);

  assert.equal(result.disposition, "completed");
  assert.deepEqual(f.calls.map(([name]) => name), [
    "tenant", "job", "budget", "admission", "lease", "invoke",
  ]);
  assert.deepEqual(f.calls[0][1], EVENT);
  assert.deepEqual(f.calls[1][1], EVENT);
  assert.equal(f.invokes(), 1);

  const lease = f.calls.find(([name]) => name === "lease")[1];
  const invocation = f.calls.find(([name]) => name === "invoke")[1];
  const stable = runtimeSessionId({
    tenantId: "tenant-a", jobId: "job-a", attempt: 1, releaseSha: RELEASE_SHA,
  });
  assert.equal(lease.runtimeSessionId, stable);
  assert.equal(invocation.runtimeSessionId, stable);
  assert.deepEqual(invocation.request.input_refs, ["lm-resource://state/tenant-a/task-a"]);
});

test("never invokes for stale events, release mismatch, denied budget, or an occupied tenant lease", async () => {
  const scenarios = [
    { readJob: async () => ({ ...JOB, status: "completed" }), expected: "not_applicable" },
    { readTenant: async () => ({ ...TENANT, release_sha: "b".repeat(40) }), expected: "release_mismatch" },
    { decideAdmission: () => ({ decision: "budget_exhausted" }), expected: "budget_exhausted" },
    { acquireLease: async () => ({ acquired: false, lease: null }), expected: "duplicate" },
  ];

  for (const scenario of scenarios) {
    let invoked = 0;
    const f = fixture({
      ...scenario,
      runtimeClient: { async invoke() { invoked += 1; return { disposition: "completed" }; } },
    });
    const result = await f.dispatcher.dispatch(EVENT);
    assert.equal(result.disposition, scenario.expected);
    assert.equal(invoked, 0, scenario.expected);
  }
});

test("rejects events carrying mutable job data instead of tenant/job identifiers only", async () => {
  const f = fixture();
  await assert.rejects(
    f.dispatcher.dispatch({ ...EVENT, attempt: 99, input_refs: { secret_ref: "x" } }),
    /event/i,
  );
  assert.deepEqual(f.calls, []);
  assert.equal(f.invokes(), 0);
});

test("production wiring reads current rows then atomically claims the job and tenant lease before AWS", async () => {
  const calls = [];
  const taskRef = "lm-resource://state/tenant-a/task-a";
  const wakeRef = "lm-resource://state/tenant-a/wake-a";
  const dispatcher = createProductionCloudRuntimeDispatcher({
    releaseSha: RELEASE_SHA,
    runtimeArn: "arn:aws:bedrock-agentcore:ap-northeast-1:000000000000:runtime/life-manager",
    leaseOwner: "dispatcher-production",
    requestedCostUsdMicros: 20_000,
    async query(sql, params) {
      calls.push(["sql", sql, params]);
      if (/FROM public\.lm_cloud_tenants/i.test(sql)) return { rows: [TENANT] };
      if (/FROM public\.lm_runtime_jobs/i.test(sql) && !/WITH claimed_job/i.test(sql)) {
        return { rows: [{
          tenant_id: "tenant-a", job_id: "job-a", status: "queued", attempt: 0,
          input_refs: { wake_ref: wakeRef, task_ref: taskRef },
        }] };
      }
      if (/FROM public\.lm_cloud_usage_ledger/i.test(sql)) {
        return { rows: [{ settled_monthly: "0", settled_all_time: "0", active_leases: "0" }] };
      }
      if (/WITH claimed_job/i.test(sql)) {
        return { rows: [{
          tenant_id: "tenant-a", job_id: "job-a", attempt: 1,
          runtime_session_id: params[3], lease_owner: params[4],
          lease_expires_at: params[5], generation: 1,
        }] };
      }
      throw new Error("unexpected SQL");
    },
    async awsInvoke(command) {
      calls.push(["aws", command]);
      return {
        response: { status: "completed" },
        provider_request_id: "provider-request-a",
      };
    },
  });

  const result = await dispatcher.dispatch(EVENT);

  assert.equal(result.disposition, "completed");
  assert.deepEqual(calls.map(([kind]) => kind), ["sql", "sql", "sql", "sql", "aws"]);
  const claimSql = calls[3][1];
  assert.match(claimSql, /WITH claimed_job AS[\s\S]*UPDATE public\.lm_runtime_jobs/i);
  assert.match(claimSql, /INSERT INTO public\.lm_cloud_runtime_leases/i);
  assert.deepEqual(calls[4][1].payload.input_refs, [taskRef]);
  assert.equal(calls[4][1].payload.wake_id, "wake-a");
});
