"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const {
  buildCloudTenant,
  buildRuntimeLease,
  buildBrowserProfile,
  buildUsageEntry,
  acquireRuntimeLease,
  saveBrowserProfile,
  recordUsage,
} = require("./cloud-runtime-store.js");

const MIGRATION = fs.readFileSync(path.join(
  __dirname,
  "../migrations/20260928_agentcore_cloud_runtime.sql",
), "utf8");
const SHA = "a".repeat(40);

test("cloud records are tenant-bound, Tokyo-only, agent-owned, and use integer money", () => {
  assert.deepEqual(buildCloudTenant({
    tenantId: "tenant-a",
    region: "ap-northeast-1",
    releaseSha: SHA,
    status: "active",
    planVersion: "free-v1",
  }), {
    tenant_id: "tenant-a",
    region: "ap-northeast-1",
    release_sha: SHA,
    status: "active",
    plan_version: "free-v1",
  });

  assert.throws(() => buildCloudTenant({
    tenantId: "tenant-a", region: "us-east-1", releaseSha: SHA,
    status: "active", planVersion: "free-v1",
  }), /Tokyo|ap-northeast-1/i);

  assert.deepEqual(buildBrowserProfile({
    tenantId: "tenant-a",
    provider: "agentcore",
    profileId: "profile-opaque-a",
    principalType: "agent_owned",
  }), {
    tenant_id: "tenant-a",
    provider: "agentcore",
    profile_id: "profile-opaque-a",
    principal_type: "agent_owned",
  });
  assert.throws(() => buildBrowserProfile({
    tenantId: "tenant-a", provider: "agentcore", profileId: "profile-a",
    principalType: "human",
  }), /agent_owned/i);

  assert.equal(buildUsageEntry({
    tenantId: "tenant-a", jobId: "job-a", provider: "aws",
    resource: "agentcore-runtime", quantity: 10, unit: "second",
    costUsdMicros: 6703, providerReceiptId: "cur://aws/receipt-a",
  }).cost_usd_micros, 6703);
  assert.throws(() => buildUsageEntry({
    tenantId: "tenant-a", jobId: "job-a", provider: "aws",
    resource: "agentcore-runtime", quantity: 1, unit: "second",
    costUsdMicros: 1.2, providerReceiptId: "cur://aws/receipt-a",
  }), /integer|micros/i);
});

test("runtime lease creation is tenant/job scoped and cannot be silently rebound", async () => {
  const lease = buildRuntimeLease({
    tenantId: "tenant-a",
    jobId: "job-a",
    attempt: 1,
    runtimeSessionId: "session-a",
    leaseOwner: "dispatcher-a",
    leaseExpiresAt: "2026-09-29T12:05:00.000Z",
    generation: 1,
  });
  const calls = [];
  const result = await acquireRuntimeLease(lease, {
    query: async (sql, params) => {
      calls.push({ sql, params });
      return { rows: [lease] };
    },
  });
  assert.deepEqual(result, lease);
  assert.match(calls[0].sql, /INSERT INTO public\.lm_cloud_runtime_leases/i);
  assert.match(calls[0].sql, /ON CONFLICT \(tenant_id\)/i);
  assert.deepEqual(calls[0].params.slice(0, 2), ["tenant-a", "job-a"]);
});

test("browser profile and usage writes preserve exact tenant ownership and provider idempotency", async () => {
  const profile = buildBrowserProfile({
    tenantId: "tenant-a", provider: "agentcore", profileId: "profile-a",
    principalType: "agent_owned",
  });
  const profileCalls = [];
  await saveBrowserProfile(profile, {
    query: async (sql, params) => {
      profileCalls.push({ sql, params });
      return { rows: [profile] };
    },
  });
  assert.match(profileCalls[0].sql, /ON CONFLICT \(tenant_id, provider\)/i);
  assert.deepEqual(profileCalls[0].params.slice(0, 2), ["tenant-a", "agentcore"]);

  const usage = buildUsageEntry({
    tenantId: "tenant-a", jobId: "job-a", provider: "aws",
    resource: "agentcore-browser", quantity: 10, unit: "second",
    costUsdMicros: 12267, providerReceiptId: "cur://aws/browser-a",
  });
  const usageCalls = [];
  assert.deepEqual(await recordUsage(usage, {
    query: async (sql, params) => {
      usageCalls.push({ sql, params });
      if (/INSERT/i.test(sql)) return { rows: [] };
      return { rows: [usage] };
    },
  }), { created: false, usage });
  assert.match(usageCalls[0].sql, /ON CONFLICT \(provider_receipt_id\) DO NOTHING/i);
  assert.match(usageCalls[1].sql, /tenant_id = \$2/i);

  await assert.rejects(recordUsage(usage, {
    query: async (sql) => ({ rows: /INSERT/i.test(sql) ? [] : [] }),
  }), /collision|tenant/i);
});

test("migration defines one durable cloud contract without a second job queue", () => {
  for (const table of [
    "lm_cloud_tenants",
    "lm_cloud_runtime_leases",
    "lm_cloud_browser_profiles",
    "lm_cloud_usage_ledger",
    "lm_plan_entitlements",
  ]) {
    assert.match(MIGRATION, new RegExp(`CREATE TABLE IF NOT EXISTS public\\.${table}`, "i"));
  }
  assert.doesNotMatch(MIGRATION, /CREATE TABLE[^;]*cloud[^;]*jobs/i);
  assert.match(MIGRATION, /FOREIGN KEY \(job_id, tenant_id\)[\s\S]*lm_runtime_jobs \(job_id, tenant_id\)/i);
  assert.match(MIGRATION, /provider_receipt_id[^;]*UNIQUE|UNIQUE[^;]*provider_receipt_id/i);
  assert.match(MIGRATION, /ENABLE ROW LEVEL SECURITY/i);
  assert.match(MIGRATION, /runtime leases are immutable|reject_lm_cloud_usage_mutation/i);
});
