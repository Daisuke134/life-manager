"use strict";

const { isDeepStrictEqual } = require("node:util");

const TOKYO_REGION = "ap-northeast-1";
const RELEASE_SHA = /^[a-f0-9]{40}$/;
const TENANT_STATUSES = new Set(["active", "inactive", "manual_hold"]);
let defaultPool;

function nonEmpty(value, label, max = 500) {
  const text = String(value == null ? "" : value).trim();
  if (!text || text.length > max) throw new Error(`${label} invalid`);
  return text;
}

function positiveInteger(value, label) {
  const parsed = typeof value === "string" && /^\d+$/.test(value) ? Number(value) : value;
  if (!Number.isSafeInteger(parsed) || parsed < 1) throw new Error(`${label} must be a positive integer`);
  return parsed;
}

function nonNegativeInteger(value, label) {
  const parsed = typeof value === "string" && /^\d+$/.test(value) ? Number(value) : value;
  if (!Number.isSafeInteger(parsed) || parsed < 0) throw new Error(`${label} must use non-negative integer micros`);
  return parsed;
}

function instant(value, label) {
  if (value instanceof Date && Number.isFinite(value.getTime())) return value.toISOString();
  const text = nonEmpty(value, label, 100);
  if (!/[zZ]|[+-]\d\d:\d\d$/.test(text) || !Number.isFinite(Date.parse(text))) {
    throw new Error(`${label} invalid`);
  }
  return new Date(text).toISOString();
}

async function saveCloudTenant(input, opts = {}) {
  const tenant = buildCloudTenant(input);
  const { query } = database(opts);
  const rows = (await query(`
    INSERT INTO public.lm_cloud_tenants (
      tenant_id, region, release_sha, status, plan_version
    ) VALUES ($1,$2,$3,$4,$5)
    ON CONFLICT (tenant_id) DO UPDATE
      SET region = EXCLUDED.region,
          release_sha = EXCLUDED.release_sha,
          status = EXCLUDED.status,
          plan_version = EXCLUDED.plan_version,
          updated_at = clock_timestamp()
    RETURNING tenant_id, region, release_sha, status, plan_version
  `, Object.values(tenant))).rows;
  if (rows.length !== 1) throw new Error("cloud tenant write failed");
  return buildCloudTenant(rows[0]);
}

async function createFreeCloudTenant(input = {}, opts = {}) {
  const candidate = buildCloudTenant({
    tenantId: input.tenantId,
    region: TOKYO_REGION,
    releaseSha: input.releaseSha,
    status: "active",
    planVersion: "free-v1",
  });
  const { query } = database(opts);
  const rows = (await query(`
    INSERT INTO public.lm_cloud_tenants (
      tenant_id, region, release_sha, status, plan_version
    ) VALUES ($1,$2,$3,'active','free-v1')
    ON CONFLICT (tenant_id) DO NOTHING
    RETURNING tenant_id, region, release_sha, status, plan_version
  `, [candidate.tenant_id, candidate.region, candidate.release_sha])).rows;
  if (rows.length > 1) throw new Error("cloud Free tenant write failed");
  if (rows.length === 1) return buildCloudTenant(rows[0]);
  const existing = (await query(`
    SELECT tenant_id, region, release_sha, status, plan_version
    FROM public.lm_cloud_tenants WHERE tenant_id = $1 LIMIT 1
  `, [candidate.tenant_id])).rows;
  if (existing.length !== 1) throw new Error("cloud Free tenant readback failed");
  return buildCloudTenant(existing[0]);
}

function database(opts = {}) {
  if (typeof opts.query === "function") return { query: opts.query };
  const connectionString = String(
    opts.connectionString
      || process.env.LM_RUNTIME_DATABASE_URL
      || process.env.LM_FEEDBACK_DATABASE_URL
      || "",
  ).trim();
  if (!connectionString) throw new Error("cloud runtime store unavailable");
  if (!defaultPool) {
    const Pool = opts.Pool || require("pg").Pool;
    defaultPool = new Pool({ connectionString, max: 8 });
  }
  return { query: defaultPool.query.bind(defaultPool) };
}

function buildCloudTenant(input) {
  const source = input && input.tenant_id != null ? {
    tenantId: input.tenant_id,
    region: input.region,
    releaseSha: input.release_sha,
    status: input.status,
    planVersion: input.plan_version,
  } : input;
  const region = nonEmpty(source && source.region, "cloud region", 50);
  if (region !== TOKYO_REGION) throw new Error(`cloud region must be Tokyo (${TOKYO_REGION})`);
  const releaseSha = nonEmpty(source && source.releaseSha, "cloud release SHA", 40);
  if (!RELEASE_SHA.test(releaseSha)) throw new Error("cloud release SHA invalid");
  const status = nonEmpty(source && source.status, "cloud tenant status", 30);
  if (!TENANT_STATUSES.has(status)) throw new Error("cloud tenant status invalid");
  const planVersion = nonEmpty(source && source.planVersion, "cloud plan version", 100);
  if (!/^[a-z0-9][a-z0-9-]*-v\d+$/.test(planVersion)) throw new Error("cloud plan version invalid");
  return Object.freeze({
    tenant_id: nonEmpty(source && source.tenantId, "cloud tenant id", 200),
    region,
    release_sha: releaseSha,
    status,
    plan_version: planVersion,
  });
}

function buildRuntimeLease(input) {
  const source = input && input.tenant_id != null ? {
    tenantId: input.tenant_id,
    jobId: input.job_id,
    attempt: input.attempt,
    runtimeSessionId: input.runtime_session_id,
    leaseOwner: input.lease_owner,
    leaseExpiresAt: input.lease_expires_at,
    generation: input.generation,
  } : input;
  return Object.freeze({
    tenant_id: nonEmpty(source && source.tenantId, "cloud tenant id", 200),
    job_id: nonEmpty(source && source.jobId, "cloud job id", 200),
    attempt: positiveInteger(source && source.attempt, "cloud attempt"),
    runtime_session_id: nonEmpty(source && source.runtimeSessionId, "runtime session id", 500),
    lease_owner: nonEmpty(source && source.leaseOwner, "runtime lease owner", 200),
    lease_expires_at: instant(source && source.leaseExpiresAt, "runtime lease expiry"),
    generation: positiveInteger(source && source.generation, "runtime lease generation"),
  });
}

function buildBrowserProfile(input) {
  const source = input && input.tenant_id != null ? {
    tenantId: input.tenant_id,
    provider: input.provider,
    profileId: input.profile_id,
    principalType: input.principal_type,
  } : input;
  const principalType = nonEmpty(source && source.principalType, "browser principal type", 30);
  if (principalType !== "agent_owned") throw new Error("browser principal type must be agent_owned");
  return Object.freeze({
    tenant_id: nonEmpty(source && source.tenantId, "cloud tenant id", 200),
    provider: nonEmpty(source && source.provider, "browser provider", 100),
    profile_id: nonEmpty(source && source.profileId, "browser profile id", 500),
    principal_type: principalType,
  });
}

function buildUsageEntry(input) {
  const source = input && input.tenant_id != null ? {
    tenantId: input.tenant_id,
    jobId: input.job_id,
    provider: input.provider,
    resource: input.resource,
    quantity: input.quantity,
    unit: input.unit,
    costUsdMicros: input.cost_usd_micros,
    providerReceiptId: input.provider_receipt_id,
  } : input;
  return Object.freeze({
    tenant_id: nonEmpty(source && source.tenantId, "cloud tenant id", 200),
    job_id: nonEmpty(source && source.jobId, "cloud job id", 200),
    provider: nonEmpty(source && source.provider, "usage provider", 100),
    resource: nonEmpty(source && source.resource, "usage resource", 200),
    quantity: positiveInteger(source && source.quantity, "usage quantity"),
    unit: nonEmpty(source && source.unit, "usage unit", 50),
    cost_usd_micros: nonNegativeInteger(source && source.costUsdMicros, "usage cost"),
    provider_receipt_id: nonEmpty(source && source.providerReceiptId, "provider receipt id", 500),
  });
}

function assertExact(existing, expected, label) {
  const projected = Object.fromEntries(Object.keys(expected).map((key) => [key, existing[key]]));
  if (!isDeepStrictEqual(projected, expected)) throw new Error(`${label} collision`);
}

async function acquireRuntimeLease(input, opts = {}) {
  const lease = buildRuntimeLease(input);
  const { query } = database(opts);
  const inserted = (await query(`
    INSERT INTO public.lm_cloud_runtime_leases (
      tenant_id, job_id, attempt, runtime_session_id, lease_owner, lease_expires_at, generation
    ) VALUES ($1,$2,$3,$4,$5,$6::timestamptz,$7)
    ON CONFLICT (tenant_id) DO NOTHING
    RETURNING tenant_id, job_id, attempt, runtime_session_id, lease_owner, lease_expires_at, generation
  `, Object.values(lease))).rows;
  if (inserted.length === 1) return buildRuntimeLease(inserted[0]);
  if (inserted.length > 1) throw new Error("runtime lease returned multiple rows");
  const existing = (await query(`
    SELECT tenant_id, job_id, attempt, runtime_session_id, lease_owner, lease_expires_at, generation
    FROM public.lm_cloud_runtime_leases WHERE tenant_id = $1 LIMIT 1
  `, [lease.tenant_id])).rows;
  if (existing.length !== 1) throw new Error("runtime lease collision");
  const canonical = buildRuntimeLease(existing[0]);
  assertExact(canonical, lease, "runtime lease");
  return canonical;
}

async function saveBrowserProfile(input, opts = {}) {
  const profile = buildBrowserProfile(input);
  const { query } = database(opts);
  const rows = (await query(`
    INSERT INTO public.lm_cloud_browser_profiles (
      tenant_id, provider, profile_id, principal_type
    ) VALUES ($1,$2,$3,$4)
    ON CONFLICT (tenant_id, provider) DO UPDATE
      SET profile_id = EXCLUDED.profile_id,
          principal_type = EXCLUDED.principal_type,
          updated_at = clock_timestamp()
    RETURNING tenant_id, provider, profile_id, principal_type
  `, Object.values(profile))).rows;
  if (rows.length !== 1) throw new Error("browser profile write failed");
  return buildBrowserProfile(rows[0]);
}

async function recordUsage(input, opts = {}) {
  const usage = buildUsageEntry(input);
  const { query } = database(opts);
  const inserted = (await query(`
    INSERT INTO public.lm_cloud_usage_ledger (
      tenant_id, job_id, provider, resource, quantity, unit,
      cost_usd_micros, provider_receipt_id
    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
    ON CONFLICT (provider_receipt_id) DO NOTHING
    RETURNING tenant_id, job_id, provider, resource, quantity, unit,
              cost_usd_micros, provider_receipt_id
  `, Object.values(usage))).rows;
  if (inserted.length === 1) return { created: true, usage: buildUsageEntry(inserted[0]) };
  if (inserted.length > 1) throw new Error("usage insert returned multiple rows");
  const existing = (await query(`
    SELECT tenant_id, job_id, provider, resource, quantity, unit,
           cost_usd_micros, provider_receipt_id
    FROM public.lm_cloud_usage_ledger
    WHERE provider_receipt_id = $1 AND tenant_id = $2
    LIMIT 1
  `, [usage.provider_receipt_id, usage.tenant_id])).rows;
  if (existing.length !== 1) throw new Error("provider receipt tenant collision");
  const canonical = buildUsageEntry(existing[0]);
  assertExact(canonical, usage, "provider receipt");
  return { created: false, usage: canonical };
}

module.exports = {
  TOKYO_REGION,
  buildCloudTenant,
  buildRuntimeLease,
  buildBrowserProfile,
  buildUsageEntry,
  saveCloudTenant,
  createFreeCloudTenant,
  acquireRuntimeLease,
  saveBrowserProfile,
  recordUsage,
};
