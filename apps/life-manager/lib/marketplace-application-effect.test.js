"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  buildMarketplaceApplicationJob,
  marketplaceApplicationContract,
} = require("./marketplace-application-job.js");
const {
  runMarketplaceApplicationEffect,
} = require("./marketplace-application-effect.js");

function goalWorkItem() {
  return {
    job_id: "goal:goal-1",
    tenant_id: "tenant-1",
    loop_id: "life-manager.manager",
    capability: "general-agent.work",
    effect_class: "none",
    effect_key: null,
    input_refs: { goal_ref: "intent-entry://tenant-1/goal-1" },
    max_attempts: 1,
  };
}

function input(overrides = {}) {
  return {
    goalWorkItem: goalWorkItem(),
    capabilityRef: "provider-capability://lancers/marketplace.application",
    opportunityRef: "marketplace-opportunity://lancers/job-123",
    intentRef: `application-intent://sha256/${"a".repeat(64)}`,
    authorizationRef: `authorization-receipt://sha256/${"b".repeat(64)}`,
    ...overrides,
  };
}

test("application identity is deterministic, reference-only, and authorization-bound", () => {
  const first = buildMarketplaceApplicationJob(input());
  const replay = buildMarketplaceApplicationJob(input());
  const changedAuthorization = buildMarketplaceApplicationJob(input({
    authorizationRef: `authorization-receipt://sha256/${"c".repeat(64)}`,
  }));
  assert.deepEqual(replay, first);
  assert.equal(first.effect_class, "publish");
  assert.equal(first.max_attempts, 1);
  assert.notEqual(changedAuthorization.effect_key, first.effect_key);
  assert.doesNotMatch(JSON.stringify(first), /proposal|account|credential|private/i);
  assert.deepEqual(marketplaceApplicationContract(first).input_refs, first.input_refs);
});

test("noncanonical parent or unbound references are rejected", () => {
  assert.throws(
    () => buildMarketplaceApplicationJob(input({
      goalWorkItem: { ...goalWorkItem(), effect_class: "publish" },
    })),
    /Goal WorkItem/i,
  );
  assert.throws(
    () => buildMarketplaceApplicationJob(input({ authorizationRef: "authorization-receipt://raw" })),
    /authorization reference/i,
  );
  assert.throws(
    () => buildMarketplaceApplicationJob(input({
      capabilityRef: "provider-capability://fiverr/marketplace.application",
    })),
    /provider mismatch/i,
  );
  const valid = buildMarketplaceApplicationJob(input());
  assert.throws(
    () => marketplaceApplicationContract({
      ...valid,
      input_refs: { ...valid.input_refs, extra_ref: "object://unexpected" },
    }),
    /job invalid/i,
  );
});

test("absent effect executes once, completes from post-readback, and replays zero", async () => {
  const job = buildMarketplaceApplicationJob(input());
  let submitted = false;
  let executions = 0;
  const deps = {
    inspectApplication: async () => submitted
      ? { state: "present", receipt: { record_type: "application_receipt" } }
      : { state: "absent" },
    executeOnce: async () => { executions += 1; submitted = true; },
    verifyReceipt: (receipt) => Object.freeze({ ...receipt, verified: true }),
  };
  const first = await runMarketplaceApplicationEffect(job, deps);
  const replay = await runMarketplaceApplicationEffect(job, deps);
  assert.equal(first.effect_started, true);
  assert.equal(first.receipt.verified, true);
  assert.equal(replay.replayed, true);
  assert.equal(executions, 1);
});

test("unknown pre-readback never executes and remains an unknown effect", async () => {
  const job = buildMarketplaceApplicationJob(input());
  let executions = 0;
  await assert.rejects(
    runMarketplaceApplicationEffect(job, {
      inspectApplication: async () => ({ state: "unknown" }),
      executeOnce: async () => { executions += 1; },
      verifyReceipt: (receipt) => receipt,
    }),
    (error) => error.code === "APPLICATION_EFFECT_UNKNOWN" && error.unknownEffect === true,
  );
  assert.equal(executions, 0);
});

test("typed human-required proof skips before execution without human delegation", async () => {
  const job = buildMarketplaceApplicationJob(input());
  let executions = 0;
  await assert.rejects(
    runMarketplaceApplicationEffect(job, {
      inspectApplication: async () => ({
        state: "human_required",
        requirements: ["interview", "free_form_response"],
        evidence_ref: "provider-readback://lancers/job-123/requirements",
      }),
      executeOnce: async () => { executions += 1; },
      verifyReceipt: (receipt) => receipt,
    }),
    (error) => error.code === "APPLICATION_HUMAN_REQUIRED"
      && error.unknownEffect === false
      && error.disposition === "skip"
      && error.delegateToHuman === false
      && error.bypassAllowed === false,
  );
  assert.equal(executions, 0);
});

test("post-readback failure is unknown after exactly one execution", async () => {
  const job = buildMarketplaceApplicationJob(input());
  let inspections = 0;
  let executions = 0;
  await assert.rejects(
    runMarketplaceApplicationEffect(job, {
      inspectApplication: async () => {
        inspections += 1;
        if (inspections === 1) return { state: "absent" };
        throw new Error("provider unavailable");
      },
      executeOnce: async () => { executions += 1; },
      verifyReceipt: (receipt) => receipt,
    }),
    (error) => error.code === "APPLICATION_EFFECT_UNKNOWN" && error.unknownEffect === true,
  );
  assert.equal(executions, 1);
});
