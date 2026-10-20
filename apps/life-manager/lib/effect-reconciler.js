"use strict";

const RECONCILED_EFFECTS = new Set(["publish", "message", "money"]);
const { MAX_UNKNOWN_RECONCILE_RESULTS } = require("./runtime-job-store.js");

async function reconcileUnknownEffect(job, dependencies = {}) {
  if (!job || job.status !== "reconciling") {
    throw new Error("runtime job is not reconciling");
  }
  if (!RECONCILED_EFFECTS.has(job.effect_class)) {
    throw new Error("runtime effect class cannot be reconciled");
  }
  if (!job.effect_key) throw new Error("runtime effect key missing");
  const { adapter, store } = dependencies;
  if (!adapter || typeof adapter.inspectEffect !== "function") {
    throw new Error("runtime reconciliation adapter invalid");
  }
  if (
    !store
    || typeof store.resolveReconciliation !== "function"
    || typeof store.recordUnknownReconciliation !== "function"
  ) {
    throw new Error("runtime reconciliation store invalid");
  }

  const proof = await adapter.inspectEffect({
    tenantId: job.tenant_id,
    loopId: job.loop_id,
    effectClass: job.effect_class,
    effectKey: job.effect_key,
    jobId: job.job_id,
    attempt: job.attempt,
  });
  if (!proof || !["present", "absent", "unknown", "pending"].includes(proof.state)) {
    throw new Error("runtime adapter proof invalid");
  }
  // An observed running provider execution is known pending, not an unknown effect.
  if (proof.state === "pending") return { status: "reconciling", decision: "pending" };
  if (proof.state === "unknown") {
    // Unknown ages: the store durably counts consecutive unknown results and, at
    // MAX_UNKNOWN_RECONCILE_RESULTS, dead-letters the job for operator review instead
    // of leaving it in an infinite quarantine. Retry is still never permitted here.
    const aged = await store.recordUnknownReconciliation({
      tenantId: job.tenant_id,
      jobId: job.job_id,
      attempt: job.attempt,
      maxUnknownResults: MAX_UNKNOWN_RECONCILE_RESULTS,
    });
    if (aged && aged.status === "dead_letter") {
      return { status: "dead_letter", decision: "unknown_exhausted" };
    }
    return { status: "reconciling", decision: "unknown" };
  }
  if (!proof.receipt || typeof proof.receipt !== "object" || Array.isArray(proof.receipt)) {
    throw new Error("runtime adapter proof receipt invalid");
  }

  return store.resolveReconciliation({
    tenantId: job.tenant_id,
    jobId: job.job_id,
    attempt: job.attempt,
    decision: proof.state,
    receipt: proof.receipt,
  });
}

module.exports = { reconcileUnknownEffect, MAX_UNKNOWN_RECONCILE_RESULTS };
