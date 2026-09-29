"use strict";

const { buildGoalWorkItem } = require("./goal-work-item.js");

function dependencies(value) {
  if (
    !value || typeof value.loadTenant !== "function"
    || typeof value.enqueueJob !== "function"
    || !value.secretProvider || typeof value.secretProvider.health !== "function"
  ) throw new Error("hosted goal dependencies unavailable");
  return value;
}

async function enqueueHostedGoal(input = {}, injected = {}) {
  const deps = dependencies(injected);
  const scope = input.scope;
  if (
    !scope || scope.authenticated !== true
    || typeof scope.tenantId !== "string" || !scope.tenantId
    || typeof scope.chatId !== "string" || !scope.chatId
  ) throw new Error("authenticated hosted tenant required");

  const job = buildGoalWorkItem(input.goal, input.nowMs);
  if (job.tenant_id !== scope.tenantId) throw new Error("hosted tenant scope mismatch");
  const tenant = await deps.loadTenant(scope.tenantId);
  if (
    !tenant || tenant.uid !== scope.tenantId
    || String(tenant.telegram_chat_id || "") !== scope.chatId
  ) throw new Error("hosted tenant scope mismatch");
  if (tenant.paid !== true) throw new Error("hosted tenant entitlement required");

  const vault = await deps.secretProvider.health();
  if (!vault || vault.ok !== true || vault.mode !== "cloud"
      || !["vault", "agentcore-identity"].includes(vault.provider)) {
    throw new Error("hosted tenant vault unavailable");
  }
  const queued = await deps.enqueueJob({
    jobId: job.job_id,
    tenantId: job.tenant_id,
    loopId: job.loop_id,
    capability: job.capability,
    effectClass: job.effect_class,
    effectKey: job.effect_key,
    inputRefs: job.input_refs,
    maxAttempts: job.max_attempts,
  });
  if (!queued || typeof queued.created !== "boolean") {
    throw new Error("hosted goal enqueue receipt invalid");
  }
  return Object.freeze({
    created: queued.created,
    tenant_id: job.tenant_id,
    job_id: job.job_id,
    job_ref: `runtime-job://${encodeURIComponent(job.tenant_id)}/${encodeURIComponent(job.job_id)}`,
    vault_provider: vault.provider,
  });
}

module.exports = { enqueueHostedGoal };
