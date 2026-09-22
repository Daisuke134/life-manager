"use strict";

const { buildGoalWorkItem } = require("./goal-work-item.js");
const {
  activePortfolioGoal,
  synthesizeGoalPortfolio,
  validateGoalPortfolio,
} = require("./goal-portfolio.js");

function dependencies(value) {
  if (
    !value || typeof value.loadTenant !== "function"
    || typeof value.enqueueJob !== "function"
    || typeof value.loadGoalPortfolio !== "function"
    || typeof value.saveGoalPortfolio !== "function"
    || typeof value.generateGoalPortfolio !== "function"
    || !value.secretProvider || typeof value.secretProvider.health !== "function"
  ) throw new Error("hosted goal dependencies unavailable");
  return value;
}

async function enqueueHostedGoal(input = {}, injected = {}) {
  if (Object.hasOwn(input, "goal")) {
    throw new Error("caller goal is not accepted; Life Manager owns goal synthesis");
  }
  const deps = dependencies(injected);
  const scope = input.scope;
  if (
    !scope || scope.authenticated !== true
    || typeof scope.tenantId !== "string" || !scope.tenantId
    || typeof scope.chatId !== "string" || !scope.chatId
  ) throw new Error("authenticated hosted tenant required");
  if (!Number.isFinite(input.nowMs)) throw new Error("hosted goal observation time required");

  const tenant = await deps.loadTenant(scope.tenantId);
  if (
    !tenant || tenant.uid !== scope.tenantId
    || String(tenant.telegram_chat_id || "") !== scope.chatId
  ) throw new Error("hosted tenant scope mismatch");
  if (tenant.paid !== true) throw new Error("hosted tenant entitlement required");

  const vault = await deps.secretProvider.health();
  if (!vault || vault.ok !== true || vault.mode !== "cloud" || vault.provider !== "vault") {
    throw new Error("hosted tenant vault unavailable");
  }

  const factRefs = Array.isArray(tenant.fact_refs) ? tenant.fact_refs : [];
  const evidenceRefs = Array.isArray(tenant.evidence_refs) && tenant.evidence_refs.length > 0
    ? tenant.evidence_refs
    : ["policy://life-manager/J4"];
  const boundaryRefs = Array.isArray(tenant.boundary_refs) ? tenant.boundary_refs : [];
  const authorizedRefs = [...factRefs, ...evidenceRefs, ...boundaryRefs];
  let portfolio = await deps.loadGoalPortfolio(scope.tenantId);
  if (!portfolio) {
    portfolio = await synthesizeGoalPortfolio({
      tenantId: scope.tenantId,
      revision: 1,
      generatedAt: new Date(input.nowMs).toISOString(),
      factRefs,
      evidenceRefs,
      boundaryRefs,
    }, { generate: deps.generateGoalPortfolio });
    await deps.saveGoalPortfolio(portfolio);
  } else {
    portfolio = validateGoalPortfolio(portfolio, {
      tenantId: scope.tenantId,
      authorizedRefs,
    });
  }
  const goal = activePortfolioGoal(portfolio, input.nowMs);
  const job = buildGoalWorkItem(goal, input.nowMs);
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
    vault_provider: "vault",
  });
}

module.exports = { enqueueHostedGoal };
