"use strict";

const { runtimeSessionId } = require("./agentcore-runtime-client.js");

const EVENT_FIELDS = Object.freeze(["tenant_id", "job_id"]);
const RELEASE_SHA = /^[a-f0-9]{40}$/;

function exactEvent(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("cloud runtime event invalid");
  }
  const actual = Object.keys(value).sort();
  if (actual.length !== EVENT_FIELDS.length
      || actual.some((field, index) => field !== [...EVENT_FIELDS].sort()[index])) {
    throw new Error("cloud runtime event must contain tenant/job identifiers only");
  }
  const tenantId = String(value.tenant_id || "").trim();
  const jobId = String(value.job_id || "").trim();
  if (!tenantId || !jobId || tenantId.length > 200 || jobId.length > 200) {
    throw new Error("cloud runtime event identity invalid");
  }
  return { tenantId, jobId };
}

function dependencies(options) {
  for (const name of ["readTenant", "readJob", "readBudget", "decideAdmission", "acquireLease"]) {
    if (typeof options[name] !== "function") throw new Error(`cloud runtime ${name} unavailable`);
  }
  if (!options.runtimeClient || typeof options.runtimeClient.invoke !== "function") {
    throw new Error("cloud runtime client unavailable");
  }
  if (!RELEASE_SHA.test(String(options.releaseSha || ""))) {
    throw new Error("cloud runtime release invalid");
  }
  return options;
}

function inputReferences(job) {
  if (!job.input_refs || typeof job.input_refs !== "object" || Array.isArray(job.input_refs)) {
    throw new Error("cloud runtime job input references invalid");
  }
  const refs = Object.values(job.input_refs).flatMap((value) => (
    Array.isArray(value) ? value : [value]
  ));
  if (refs.length < 1 || refs.some((value) => typeof value !== "string" || !value.trim())) {
    throw new Error("cloud runtime job input references invalid");
  }
  return refs;
}

function createCloudRuntimeDispatcher(options = {}) {
  const deps = dependencies(options);
  const now = typeof deps.now === "function" ? deps.now : () => new Date();
  return Object.freeze({
    async dispatch(event) {
      const id = exactEvent(event);
      const lookup = { tenant_id: id.tenantId, job_id: id.jobId };
      const tenant = await deps.readTenant(lookup);
      if (!tenant || tenant.tenant_id !== id.tenantId) {
        return Object.freeze({ disposition: "not_applicable" });
      }
      const job = await deps.readJob(lookup);
      if (!job || job.tenant_id !== id.tenantId || job.job_id !== id.jobId
          || job.status !== "queued") {
        return Object.freeze({ disposition: "not_applicable" });
      }
      if (tenant.release_sha !== deps.releaseSha) {
        return Object.freeze({ disposition: "release_mismatch" });
      }
      if (!Number.isSafeInteger(job.attempt) || job.attempt < 1 || !job.wake_id) {
        throw new Error("cloud runtime job attempt identity invalid");
      }
      const budget = await deps.readBudget(lookup);
      const admission = deps.decideAdmission({
        planVersion: tenant.plan_version,
        tenantStatus: tenant.status,
        manualHold: tenant.status === "manual_hold",
        settledCostUsdMicros: budget.settledCostUsdMicros,
        reservedCostUsdMicros: budget.reservedCostUsdMicros,
        requestedCostUsdMicros: deps.requestedCostUsdMicros,
        activationCreditRemainingUsdMicros: budget.activationCreditRemainingUsdMicros,
      });
      if (!admission || admission.decision !== "allow") {
        return Object.freeze({ disposition: admission && admission.decision || "policy_denied" });
      }
      const sessionId = runtimeSessionId({
        tenantId: id.tenantId,
        jobId: id.jobId,
        attempt: job.attempt,
        releaseSha: deps.releaseSha,
      });
      const observed = now();
      const observedMs = observed instanceof Date ? observed.getTime() : Date.parse(observed);
      if (!Number.isFinite(observedMs)) throw new Error("cloud runtime clock invalid");
      const leaseSeconds = Number(deps.leaseSeconds || 180);
      const claim = await deps.acquireLease({
        tenantId: id.tenantId,
        jobId: id.jobId,
        attempt: job.attempt,
        runtimeSessionId: sessionId,
        leaseOwner: String(deps.leaseOwner || "cloud-dispatcher"),
        leaseExpiresAt: new Date(observedMs + leaseSeconds * 1_000).toISOString(),
        generation: job.attempt,
      });
      if (!claim || claim.acquired !== true) {
        return Object.freeze({ disposition: "duplicate" });
      }
      return deps.runtimeClient.invoke({
        runtimeArn: deps.runtimeArn,
        runtimeSessionId: sessionId,
        tenantId: id.tenantId,
        jobId: id.jobId,
        attempt: job.attempt,
        releaseSha: deps.releaseSha,
        request: {
          schema_version: 1,
          tenant_id: id.tenantId,
          job_id: id.jobId,
          attempt: job.attempt,
          wake_id: job.wake_id,
          release_sha: deps.releaseSha,
          input_refs: inputReferences(job),
        },
      });
    },
  });
}

module.exports = { createCloudRuntimeDispatcher };
