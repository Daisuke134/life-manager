"use strict";

const { createGeneralAgentWorkLoopAdapter } = require("./general-agent-work-adapter.js");
const { validateGoalWorkItem } = require("./goal-work-item.js");

const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/u;
const TENANT_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/u;

function invalid() {
  throw new Error("cloud general agent worker invalid");
}

function projection(status, tenantId, job = null) {
  return Object.freeze({
    status,
    tenant_id: tenantId,
    job_id: job ? job.job_id : null,
    attempt: job ? job.attempt : null,
  });
}

function validateJob(job, tenantId) {
  try { validateGoalWorkItem(job); } catch { return invalid(); }
  if (!job || job.tenant_id !== tenantId || !SAFE_ID.test(String(job.job_id || ""))
    || job.attempt !== 1) invalid();
  return job;
}

function validateBrokerResult(value, job) {
  if (!value || typeof value !== "object" || Array.isArray(value)
    || value.tenant_id !== job.tenant_id || value.job_id !== job.job_id
    || value.attempt !== job.attempt || value.capability !== job.capability
    || !SAFE_ID.test(String(value.operation_id || ""))
    || !new Set(["planned", "completed", "blocked"]).has(value.status)
    || !Array.isArray(value.evidence_refs) || value.evidence_refs.length < 1) invalid();
  return value;
}

function createCloudGeneralAgentWorker(options = {}) {
  const tenantId = String(options.tenantId || "");
  const workerId = String(options.workerId || "");
  const admission = options.admission;
  const broker = options.broker;
  const completeJob = options.completeJob;
  const failJob = options.failJob;
  if (!TENANT_ID.test(tenantId) || !SAFE_ID.test(workerId)
    || !admission || typeof admission.claim !== "function"
    || !broker || typeof broker.invoke !== "function"
    || typeof completeJob !== "function" || typeof failJob !== "function") invalid();

  const adapter = createGeneralAgentWorkLoopAdapter();
  return Object.freeze({
    async runOnce(...args) {
      if (args.length !== 0) invalid();
      const claimed = await admission.claim();
      if (claimed == null) return projection("idle", tenantId);
      if (!claimed || typeof claimed.grant !== "string" || !claimed.grant) invalid();
      const current = validateJob(claimed.job, tenantId);
      let brokerResult;
      try {
        brokerResult = await broker.invoke({
          grant: claimed.grant,
          tenantId,
          jobId: current.job_id,
          attempt: current.attempt,
          workerId,
          capability: current.capability,
          effectClass: current.effect_class,
          credentialRef: "secret://gemini/api-key",
          operation: "gemini.generate-plan",
          inputRefs: current.input_refs,
        });
      } catch {
        await failJob({
          tenantId,
          jobId: current.job_id,
          attempt: current.attempt,
          workerId,
          errorCode: "CLOUD_CREDENTIAL_BROKER_FAILED",
          unknownEffect: false,
        });
        return projection("failed", tenantId, current);
      }
      const safe = validateBrokerResult(brokerResult, current);
      const execution = await adapter.execute(current, {
        async runBoundedSpecialist(expected) {
          if (expected.tenant_id !== tenantId || expected.job_id !== current.job_id
            || expected.goal_ref !== current.input_refs.goal_ref) invalid();
          return {
            kind: "general_agent_work",
            status: safe.status,
            tenant_id: tenantId,
            job_id: current.job_id,
            goal_ref: current.input_refs.goal_ref,
            execution_id: safe.operation_id,
            next_job_refs: [],
          };
        },
      });
      if (!execution || !adapter.verify(execution.receipt, current)) invalid();
      await completeJob({
        tenantId,
        jobId: current.job_id,
        attempt: current.attempt,
        workerId,
        receipt: execution.receipt,
      });
      return projection("completed", tenantId, current);
    },
  });
}

module.exports = { createCloudGeneralAgentWorker };
