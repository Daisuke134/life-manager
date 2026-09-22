"use strict";

const { isDeepStrictEqual } = require("node:util");

const { enqueueHostedGoal } = require("./hosted-goal-ingress.js");

const PROJECTION_KEYS = Object.freeze([
  "goal_ref", "job_ref", "receipt_ref", "status", "tenant_id",
]);
const NON_EFFECTFUL_CLOUD_HEALTH = Object.freeze({
  async health() {
    return Object.freeze({ ok: true, mode: "cloud", provider: "vault" });
  },
});

function reject(message) {
  throw new Error(message);
}

function requiredDependencies(value) {
  const store = value && value.store;
  if (!value || typeof value.resolveSession !== "function"
    || typeof value.generateGoalPortfolio !== "function"
    || typeof value.enqueueJob !== "function"
    || !store || typeof store.loadContext !== "function"
    || typeof store.putContext !== "function"
    || typeof store.loadTenant !== "function"
    || typeof store.loadGoalPortfolio !== "function"
    || typeof store.saveGoalPortfolio !== "function"
    || typeof store.readProjection !== "function") {
    reject("cloud goal dependencies unavailable");
  }
  return value;
}

function sessionIdentity(value) {
  if (!value || typeof value.uid !== "string" || !value.uid
    || value.uid !== value.uid.trim() || value.uid.length > 200
    || typeof value.chatId !== "string" || !value.chatId
    || value.chatId !== value.chatId.trim() || value.chatId.length > 200) {
    reject("cloud goal session invalid");
  }
  return Object.freeze({ uid: value.uid, chatId: value.chatId });
}

function safeProjection(value, expected) {
  if (!value || typeof value !== "object" || Array.isArray(value)
    || Object.keys(value).length !== PROJECTION_KEYS.length
    || !Object.keys(value).sort().every((key, index) => key === PROJECTION_KEYS[index])
    || value.tenant_id !== expected.tenantId
    || value.job_ref !== expected.jobRef
    || typeof value.goal_ref !== "string" || !value.goal_ref
    || typeof value.status !== "string" || !value.status
    || !(value.receipt_ref === null
      || (typeof value.receipt_ref === "string" && value.receipt_ref))) {
    reject("cloud goal projection scope mismatch");
  }
  return value;
}

async function runCloudGoalSlice(input = {}, injected = {}) {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    reject("cloud goal input invalid");
  }
  if (Object.hasOwn(input, "goal")) {
    reject("caller goal is not accepted; Life Manager owns goal synthesis");
  }
  if (!Number.isFinite(input.nowMs)) reject("cloud goal observation time required");
  try { new Date(input.nowMs).toISOString(); }
  catch { reject("cloud goal observation time required"); }
  if (typeof input.session !== "string" || !input.session) {
    reject("cloud goal session required");
  }

  const deps = requiredDependencies(injected);
  const scope = sessionIdentity(await deps.resolveSession(input.session));
  const existing = await deps.store.loadContext(scope);
  if (!existing && !Object.hasOwn(input, "context")) {
    reject("cloud goal context required");
  }
  if (Object.hasOwn(input, "context")) {
    if (existing && !isDeepStrictEqual(existing, input.context)) {
      reject("cloud goal context drift requires a revision-aware endpoint");
    }
    await deps.store.putContext(scope, input.context);
  }

  const tenantId = scope.uid;
  const hosted = await enqueueHostedGoal({
    scope: Object.freeze({ authenticated: true, tenantId, chatId: scope.chatId }),
    nowMs: input.nowMs,
  }, {
    async loadTenant(requestedTenantId) {
      if (requestedTenantId !== tenantId) reject("cloud goal tenant scope mismatch");
      return deps.store.loadTenant(scope);
    },
    async loadGoalPortfolio(requestedTenantId) {
      if (requestedTenantId !== tenantId) reject("cloud goal portfolio scope mismatch");
      return deps.store.loadGoalPortfolio(tenantId);
    },
    async saveGoalPortfolio(portfolio) {
      if (!portfolio || portfolio.tenant_id !== tenantId) {
        reject("cloud goal portfolio scope mismatch");
      }
      return deps.store.saveGoalPortfolio(portfolio);
    },
    generateGoalPortfolio: deps.generateGoalPortfolio,
    enqueueJob: deps.enqueueJob,
    secretProvider: NON_EFFECTFUL_CLOUD_HEALTH,
  });

  if (!hosted || hosted.tenant_id !== tenantId || typeof hosted.job_id !== "string"
    || typeof hosted.job_ref !== "string" || typeof hosted.created !== "boolean") {
    reject("cloud goal enqueue result invalid");
  }
  const projection = safeProjection(await deps.store.readProjection({
    tenantId,
    jobId: hosted.job_id,
  }), { tenantId, jobRef: hosted.job_ref });

  return Object.freeze({
    created: hosted.created,
    tenant_id: projection.tenant_id,
    goal_ref: projection.goal_ref,
    job_ref: projection.job_ref,
    status: projection.status,
    receipt_ref: projection.receipt_ref,
  });
}

module.exports = { runCloudGoalSlice };
