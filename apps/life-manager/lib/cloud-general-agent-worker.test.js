"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { createCloudGeneralAgentWorker } = require("./cloud-general-agent-worker.js");

function job(tenantId = "tenant-a", goalId = "financial-continuity") {
  return Object.freeze({
    job_id: `goal:${goalId}:r1`, tenant_id: tenantId,
    loop_id: "life-manager.manager", capability: "general-agent.work",
    effect_class: "none", effect_key: null,
    input_refs: Object.freeze({ goal_ref: `goal-portfolio://${tenantId}/${goalId}?revision=1` }),
    max_attempts: 1, attempt: 1,
  });
}

function result(value = job(), overrides = {}) {
  return {
    operation_id: `broker-${value.tenant_id}-1`, status: "completed",
    tenant_id: value.tenant_id, job_id: value.job_id, attempt: value.attempt,
    capability: value.capability,
    evidence_refs: [`broker://${value.tenant_id}/operation/result`],
    ...overrides,
  };
}

function fixture(overrides = {}) {
  const tenantId = overrides.tenantId || "tenant-a";
  const workerId = overrides.workerId || `worker-${tenantId}`;
  const claimedJob = overrides.job || job(tenantId);
  let available = true;
  const calls = [];
  const admission = overrides.admission || {
    async claim() {
      calls.push(["claim"]);
      if (!available) return null;
      available = false;
      return { job: claimedJob, grant: `grant-${tenantId}` };
    },
  };
  const broker = overrides.broker || {
    async invoke(input) { calls.push(["broker", input]); return result(claimedJob); },
  };
  const completeJob = overrides.completeJob || (async (input) => { calls.push(["complete", input]); return {}; });
  const failJob = overrides.failJob || (async (input) => { calls.push(["fail", input]); return {}; });
  const worker = createCloudGeneralAgentWorker({
    tenantId, workerId, admission, broker, completeJob, failJob,
  });
  return { worker, calls, claimedJob, tenantId, workerId };
}

test("one claimed Goal job crosses surrogate execution and the existing verified receipt contract", async () => {
  const { worker, calls, claimedJob, tenantId, workerId } = fixture();
  assert.deepEqual(await worker.runOnce(), {
    status: "completed", tenant_id: tenantId, job_id: claimedJob.job_id, attempt: 1,
  });
  assert.deepEqual(calls[1], ["broker", {
    grant: `grant-${tenantId}`,
    tenantId,
    jobId: claimedJob.job_id,
    attempt: 1,
    workerId,
    capability: "general-agent.work",
    effectClass: "none",
    credentialRef: "secret://gemini/api-key",
    operation: "gemini.generate-plan",
    inputRefs: claimedJob.input_refs,
  }]);
  assert.equal(calls[2][0], "complete");
  assert.deepEqual(calls[2][1], {
    tenantId,
    jobId: claimedJob.job_id,
    attempt: 1,
    workerId,
    receipt: {
      kind: "general_agent_work",
      status: "completed",
      tenant_id: tenantId,
      job_id: claimedJob.job_id,
      goal_ref: claimedJob.input_refs.goal_ref,
      execution_id: `broker-${tenantId}-1`,
      next_job_refs: [],
    },
  });
  assert.equal(calls.some(([name]) => name === "fail"), false);
});

test("idle and replay claim no second broker operation or completion", async () => {
  const { worker, calls } = fixture();
  await worker.runOnce();
  assert.deepEqual(await worker.runOnce(), {
    status: "idle", tenant_id: "tenant-a", job_id: null, attempt: null,
  });
  assert.equal(calls.filter(([name]) => name === "broker").length, 1);
  assert.equal(calls.filter(([name]) => name === "complete").length, 1);
});

test("broker failure records a bounded non-effectful failure and never completes", async () => {
  const { worker, calls, claimedJob, workerId } = fixture({
    broker: { async invoke() { throw new Error("provider private detail"); } },
  });
  assert.deepEqual(await worker.runOnce(), {
    status: "failed", tenant_id: "tenant-a", job_id: claimedJob.job_id, attempt: 1,
  });
  assert.deepEqual(calls.at(-1), ["fail", {
    tenantId: "tenant-a", jobId: claimedJob.job_id, attempt: 1, workerId,
    errorCode: "CLOUD_CREDENTIAL_BROKER_FAILED", unknownEffect: false,
  }]);
  assert.equal(calls.some(([name]) => name === "complete"), false);
});

test("foreign broker output and completion uncertainty fail closed", async () => {
  const foreign = fixture({
    broker: { async invoke() { return result(job(), { tenant_id: "tenant-b" }); } },
  });
  await assert.rejects(foreign.worker.runOnce(), /cloud general agent worker invalid/iu);
  assert.equal(foreign.calls.some(([name]) => name === "complete"), false);

  const uncertain = fixture({
    completeJob: async () => { throw new Error("completion response lost"); },
  });
  await assert.rejects(uncertain.worker.runOnce(), /completion response lost/iu);
  assert.equal(uncertain.calls.some(([name]) => name === "fail"), false);
});

test("one tenant failure does not prevent an independent sibling worker from completing", async () => {
  const broken = fixture({
    tenantId: "tenant-a",
    broker: { async invoke() { throw new Error("tenant-a unavailable"); } },
  });
  const sibling = fixture({ tenantId: "tenant-b", job: job("tenant-b", "continuity") });
  const [first, second] = await Promise.all([broken.worker.runOnce(), sibling.worker.runOnce()]);
  assert.equal(first.status, "failed");
  assert.equal(second.status, "completed");
  assert.equal(sibling.calls.filter(([name]) => name === "complete").length, 1);
});

test("worker identity and public run arguments are fixed at construction", async () => {
  assert.throws(() => createCloudGeneralAgentWorker({}), /cloud general agent worker invalid/iu);
  const { worker, calls } = fixture();
  await assert.rejects(worker.runOnce({ tenantId: "tenant-b" }), /cloud general agent worker invalid/iu);
  assert.deepEqual(calls, []);
});
