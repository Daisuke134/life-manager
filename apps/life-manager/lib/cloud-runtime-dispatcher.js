"use strict";

const {
  createAgentCoreRuntimeClient,
  runtimeSessionId,
} = require("./agentcore-runtime-client.js");
const { decideAdmission } = require("./cloud-entitlement.js");

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
  for (const name of [
    "readTenant",
    "recoverExpired",
    "readJob",
    "readBudget",
    "decideAdmission",
    "acquireLease",
  ]) {
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
  const refs = Object.entries(job.input_refs)
    .filter(([key]) => key !== "wake_ref")
    .flatMap(([, value]) => (
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
      if (tenant.release_sha !== deps.releaseSha) {
        return Object.freeze({ disposition: "release_mismatch" });
      }
      await deps.recoverExpired(lookup);
      const job = await deps.readJob(lookup);
      if (!job || job.tenant_id !== id.tenantId || job.job_id !== id.jobId
          || !new Set(["queued", "running"]).has(job.status)) {
        return Object.freeze({ disposition: "not_applicable" });
      }
      if (!Number.isSafeInteger(job.attempt) || job.attempt < 1 || !job.wake_id) {
        throw new Error("cloud runtime job attempt identity invalid");
      }
      const budget = await deps.readBudget({ ...lookup, plan_version: tenant.plan_version });
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

function positiveInteger(value, label, fallback) {
  const parsed = value == null ? fallback : Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 1) throw new Error(`${label} invalid`);
  return parsed;
}

function wakeId(inputRefs) {
  const value = inputRefs && inputRefs.wake_ref;
  let parsed;
  try { parsed = new URL(String(value || "")); }
  catch { throw new Error("cloud runtime wake reference invalid"); }
  const parts = parsed.pathname.split("/").filter(Boolean).map(decodeURIComponent);
  if (parsed.protocol !== "lm-resource:" || parsed.hostname !== "state" || parts.length !== 2
      || !parts[1]) {
    throw new Error("cloud runtime wake reference invalid");
  }
  return parts[1];
}

function createProductionCloudRuntimeDispatcher(options = {}) {
  const region = String(options.region || process.env.AWS_REGION || "ap-northeast-1").trim();
  if (region !== "ap-northeast-1") throw new Error("cloud runtime region must be Tokyo");
  const connectionString = String(
    options.connectionString
      || process.env.LM_RUNTIME_DATABASE_URL
      || process.env.LM_FEEDBACK_DATABASE_URL
      || "",
  ).trim();
  if (!connectionString && !options.query) throw new Error("cloud runtime database unavailable");
  const releaseSha = String(options.releaseSha || process.env.LM_AGENTCORE_RELEASE_SHA || "").trim();
  const runtimeArn = String(options.runtimeArn || process.env.LM_AGENTCORE_RUNTIME_ARN || "").trim();
  const leaseOwner = String(options.leaseOwner || process.env.RAILWAY_REPLICA_ID || "inngest-cloud").trim();
  const leaseSeconds = positiveInteger(options.leaseSeconds, "cloud runtime lease", 180);
  const requestedCostUsdMicros = positiveInteger(
    options.requestedCostUsdMicros || process.env.LM_AGENTCORE_REQUEST_COST_USD_MICROS,
    "cloud runtime requested cost",
    20_000,
  );
  let pool;
  const query = options.query || ((sql, params) => {
    if (!pool) {
      const Pool = options.Pool || require("pg").Pool;
      pool = new Pool({ connectionString, max: 8 });
    }
    return pool.query(sql, params);
  });
  const workerId = `${leaseOwner}:${process.pid}`;
  const readTenant = async ({ tenant_id: tenantId }) => {
    const rows = (await query(`
      SELECT tenant_id, region, release_sha, status, plan_version
      FROM public.lm_cloud_tenants
      WHERE tenant_id = $1
      LIMIT 1
    `, [tenantId])).rows;
    if (rows.length === 0) return null;
    if (rows.length !== 1) throw new Error("cloud tenant read returned multiple rows");
    return rows[0];
  };
  const recoverExpired = async ({ tenant_id: tenantId }) => {
    const rows = (await query(
      "SELECT * FROM public.recover_lm_cloud_runtime_leases($1)",
      [tenantId],
    )).rows;
    if (rows.length !== 1) throw new Error("cloud runtime recovery readback invalid");
    return rows[0];
  };
  const readJob = async ({ tenant_id: tenantId, job_id: jobId }) => {
    const rows = (await query(`
      SELECT tenant_id, job_id, status, attempt, input_refs
      FROM public.lm_runtime_jobs
      WHERE tenant_id = $1
        AND job_id = $2
        AND status = 'queued'
        AND available_at <= clock_timestamp()
        AND attempt < max_attempts
      LIMIT 1
    `, [tenantId, jobId])).rows;
    if (rows.length === 0) return null;
    if (rows.length !== 1) throw new Error("cloud job read returned multiple rows");
    const nextAttempt = Number(rows[0].attempt) + 1;
    if (!Number.isSafeInteger(nextAttempt) || nextAttempt < 1) {
      throw new Error("cloud job attempt invalid");
    }
    return {
      ...rows[0],
      attempt: nextAttempt,
      wake_id: wakeId(rows[0].input_refs),
    };
  };
  const readBudget = async ({ tenant_id: tenantId, plan_version: planVersion }) => {
    const rows = (await query(`
      SELECT
        COALESCE(SUM(cost_usd_micros) FILTER (
          WHERE created_at >= date_trunc('month', clock_timestamp())
        ), 0)::text AS settled_monthly,
        COALESCE(SUM(cost_usd_micros), 0)::text AS settled_all_time,
        (SELECT COUNT(*)::text
         FROM public.lm_cloud_runtime_leases
         WHERE tenant_id = $1 AND lease_expires_at > clock_timestamp()) AS active_leases
      FROM public.lm_cloud_usage_ledger
      WHERE tenant_id = $1
    `, [tenantId])).rows;
    if (rows.length !== 1) throw new Error("cloud budget read invalid");
    const monthly = Number(rows[0].settled_monthly);
    const allTime = Number(rows[0].settled_all_time);
    const active = Number(rows[0].active_leases);
    for (const value of [monthly, allTime, active]) {
      if (!Number.isSafeInteger(value) || value < 0) throw new Error("cloud budget value invalid");
    }
    return {
      settledCostUsdMicros: monthly,
      reservedCostUsdMicros: active * requestedCostUsdMicros,
      activationCreditRemainingUsdMicros: planVersion === "free-v1"
        ? Math.max(0, 1_000_000 - allTime)
        : 0,
    };
  };
  const acquireLease = async (input) => {
    const rows = (await query(`
      WITH claimed_job AS (
        UPDATE public.lm_runtime_jobs
        SET status = 'running',
            attempt = attempt + 1,
            lease_owner = $5,
            lease_expires_at = $6::timestamptz,
            updated_at = clock_timestamp()
        WHERE tenant_id = $1
          AND job_id = $2
          AND status = 'queued'
          AND attempt + 1 = $3
          AND NOT EXISTS (
            SELECT 1 FROM public.lm_cloud_runtime_leases
            WHERE tenant_id = $1
          )
        RETURNING tenant_id, job_id, attempt
      )
      INSERT INTO public.lm_cloud_runtime_leases (
        tenant_id, job_id, attempt, runtime_session_id,
        lease_owner, lease_expires_at, generation
      )
      SELECT tenant_id, job_id, attempt, $4, $5, $6::timestamptz, $7
      FROM claimed_job
      RETURNING tenant_id, job_id, attempt, runtime_session_id,
                lease_owner, lease_expires_at, generation
    `, [
      input.tenantId, input.jobId, input.attempt, input.runtimeSessionId,
      input.leaseOwner, input.leaseExpiresAt, input.generation,
    ])).rows;
    if (rows.length > 1) throw new Error("cloud runtime lease claim invalid");
    return { acquired: rows.length === 1, lease: rows[0] || null };
  };
  let awsClient = options.awsClient;
  const awsBoundary = options.awsInvoke || (async (input) => {
    const {
      BedrockAgentCoreClient,
      InvokeAgentRuntimeCommand,
    } = require("@aws-sdk/client-bedrock-agentcore");
    if (!awsClient) awsClient = new BedrockAgentCoreClient({ region });
    try {
      const response = await awsClient.send(new InvokeAgentRuntimeCommand({
        agentRuntimeArn: input.runtimeArn,
        runtimeSessionId: input.runtimeSessionId,
        contentType: "application/json",
        accept: "application/json",
        payload: Buffer.from(JSON.stringify(input.payload)),
      }), { abortSignal: input.signal });
      if (!response.response || typeof response.response.transformToString !== "function") {
        throw Object.assign(new Error("AgentCore response stream unavailable"), { accepted: true });
      }
      const parsed = JSON.parse(await response.response.transformToString());
      return {
        response: parsed,
        provider_request_id: response.$metadata && response.$metadata.requestId,
      };
    } catch (error) {
      if (new Set(["ThrottlingException", "ServiceUnavailableException", "TooManyRequestsException"])
        .has(error && error.name) && error && error.$metadata && error.$metadata.httpStatusCode) {
        error.accepted = false;
      }
      throw error;
    }
  });
  const runtimeClient = createAgentCoreRuntimeClient({
    invoke: awsBoundary,
    timeoutMs: positiveInteger(options.timeoutMs, "cloud runtime timeout", 30_000),
  });
  return createCloudRuntimeDispatcher({
    releaseSha,
    runtimeArn,
    leaseOwner,
    leaseSeconds,
    requestedCostUsdMicros,
    readTenant,
    recoverExpired,
    readJob,
    readBudget,
    decideAdmission,
    acquireLease,
    runtimeClient,
  });
}

module.exports = {
  createCloudRuntimeDispatcher,
  createProductionCloudRuntimeDispatcher,
};
