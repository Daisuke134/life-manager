"use strict";

const { loadCloudExecutionPolicy } = require("./cloud-execution-policy.js");

const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/u;
const TENANT_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/u;

function invalid() {
  throw new Error("cloud worker admission invalid");
}

function workerProjection(row, tenantId, workerId, capability) {
  const refs = row && row.input_refs;
  if (!row || row.tenant_id !== tenantId || row.lease_owner !== workerId
    || row.loop_id !== "life-manager.manager" || row.capability !== capability.capability
    || row.effect_class !== capability.effect_class || row.effect_key !== null
    || row.max_attempts !== capability.max_attempts
    || !Number.isInteger(row.attempt) || row.attempt !== 1 || row.status !== "running"
    || !refs || typeof refs !== "object" || Array.isArray(refs)
    || JSON.stringify(Object.keys(refs)) !== JSON.stringify(["goal_ref"])
    || typeof refs.goal_ref !== "string"
    || !refs.goal_ref.startsWith(`goal-portfolio://${encodeURIComponent(tenantId)}/`)) invalid();
  return Object.freeze({
    job_id: row.job_id,
    tenant_id: row.tenant_id,
    loop_id: row.loop_id,
    capability: row.capability,
    effect_class: row.effect_class,
    effect_key: row.effect_key,
    input_refs: Object.freeze({ goal_ref: refs.goal_ref }),
    max_attempts: row.max_attempts,
    attempt: row.attempt,
  });
}

function createCloudWorkerAdmission(options = {}) {
  const tenantId = String(options.tenantId || "");
  const workerId = String(options.workerId || "");
  const claim = options.claimCloudJob;
  const authority = options.authority;
  const policy = loadCloudExecutionPolicy(options.policyFile);
  const capability = policy.policy.capabilities[0];
  if (!TENANT_ID.test(tenantId) || !SAFE_ID.test(workerId)
    || typeof claim !== "function" || !authority || typeof authority.issue !== "function"
    || authority.policyDigest !== policy.digest) invalid();

  return Object.freeze({
    async claim(...args) {
      if (args.length !== 0) invalid();
      const row = await claim({
        workerId,
        capabilities: [capability.capability],
        tenantId,
        leaseSeconds: policy.policy.claim.lease_seconds,
      });
      if (row == null) return null;
      try {
        const job = workerProjection(row, tenantId, workerId, capability);
        const grant = authority.issue({ job, workerId });
        return Object.freeze({ job, grant });
      } catch {
        return invalid();
      }
    },
  });
}

module.exports = { createCloudWorkerAdmission };
