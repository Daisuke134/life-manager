"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const { createCloudWorkAuthority } = require("./cloud-work-authority.js");
const { createCloudWorkerAdmission } = require("./cloud-worker-admission.js");

const KEY = Buffer.alloc(32, 23).toString("base64");
const NOW = Date.parse("2026-09-22T12:00:00.000Z");

function claimed(overrides = {}) {
  return {
    job_id: "goal:financial-continuity:r1",
    tenant_id: "tenant-a",
    loop_id: "life-manager.manager",
    capability: "general-agent.work",
    effect_class: "none",
    effect_key: null,
    input_refs: { goal_ref: "goal-portfolio://tenant-a/financial-continuity?revision=1" },
    max_attempts: 1,
    attempt: 1,
    status: "running",
    lease_owner: "cloud-worker-a",
    ...overrides,
  };
}

function fixture(row = claimed()) {
  const calls = [];
  const authority = createCloudWorkAuthority({ signingKey: KEY, now: () => NOW });
  const admission = createCloudWorkerAdmission({
    tenantId: "tenant-a",
    workerId: "cloud-worker-a",
    authority,
    async claimCloudJob(input) { calls.push(input); return row; },
  });
  return { admission, authority, calls };
}

test("claims one fixed-tenant job and returns only the worker projection plus signed grant", async () => {
  const { admission, authority, calls } = fixture();
  const result = await admission.claim();

  assert.deepEqual(calls, [{
    workerId: "cloud-worker-a",
    capabilities: ["general-agent.work"],
    tenantId: "tenant-a",
    leaseSeconds: 180,
  }]);
  assert.deepEqual(result.job, {
    job_id: "goal:financial-continuity:r1",
    tenant_id: "tenant-a",
    loop_id: "life-manager.manager",
    capability: "general-agent.work",
    effect_class: "none",
    effect_key: null,
    input_refs: { goal_ref: "goal-portfolio://tenant-a/financial-continuity?revision=1" },
    max_attempts: 1,
    attempt: 1,
  });
  assert.equal(Object.isFrozen(result), true);
  assert.equal(Object.isFrozen(result.job), true);
  assert.equal(Object.isFrozen(result.job.input_refs), true);
  assert.equal(authority.verify(result.grant, {
    tenantId: "tenant-a", jobId: result.job.job_id, attempt: 1,
    workerId: "cloud-worker-a", capability: "general-agent.work", effectClass: "none",
  }).tenant_id, "tenant-a");
});

test("no work stays a safe no-op and caller cannot override admission policy", async () => {
  const { admission, calls } = fixture(null);
  assert.equal(await admission.claim(), null);
  await assert.rejects(admission.claim({ tenantId: "tenant-b" }), /cloud worker admission invalid/iu);
  assert.equal(calls.length, 1);
});

test("foreign, effectful, over-attempt, or wrong-owner rows fail closed", async () => {
  for (const row of [
    claimed({ tenant_id: "tenant-b" }),
    claimed({ capability: "provider.publish" }),
    claimed({ effect_class: "publish", effect_key: "publish:1" }),
    claimed({ max_attempts: 2 }),
    claimed({ attempt: 2 }),
    claimed({ lease_owner: "cloud-worker-b" }),
    claimed({ input_refs: { goal_ref: "goal-portfolio://tenant-b/other?revision=1" } }),
    claimed({ input_refs: { goal_ref: "goal-portfolio://tenant-a/other?revision=1" } }),
    claimed({ input_refs: { goal_ref: "goal-portfolio://tenant-a/financial-continuity?revision=2" } }),
  ]) {
    await assert.rejects(fixture(row).admission.claim(), /cloud worker admission invalid/iu);
  }
});

test("migration serializes tenant claims and exposes only a service-role non-effectful RPC", () => {
  const sql = fs.readFileSync(path.join(
    __dirname, "../migrations/2026-09-22-lm-cloud-work-admission.sql",
  ), "utf8");
  assert.match(sql, /SECURITY DEFINER/iu);
  assert.match(sql, /pg_advisory_xact_lock\s*\([\s\S]*p_tenant_id/iu);
  assert.match(sql, /p_capabilities\s*<>\s*ARRAY\['general-agent\.work'\]/iu);
  assert.match(sql, /loop_id\s*=\s*'life-manager\.manager'/iu);
  assert.match(sql, /effect_class\s*=\s*'none'/iu);
  assert.match(sql, /max_attempts\s*=\s*1/iu);
  assert.match(sql, /jobs\.input_refs\s*=\s*jsonb_build_object\s*\(\s*'goal_ref'/iu);
  assert.match(sql, /jobs\.input_refs\s*\?\s*'goal_ref'/iu);
  assert.match(sql, /split_part\s*\(\s*jobs\.job_id\s*,\s*':'\s*,\s*2\s*\)/iu);
  assert.match(sql, /status\s*=\s*'running'[\s\S]*lease_expires_at\s*>\s*clock_timestamp/iu);
  assert.match(sql, /LIMIT 1[\s\S]*FOR UPDATE SKIP LOCKED/iu);
  assert.match(sql, /REVOKE ALL ON FUNCTION public\.claim_lm_cloud_runtime_job[\s\S]*FROM PUBLIC/iu);
  assert.match(sql, /GRANT EXECUTE ON FUNCTION public\.claim_lm_cloud_runtime_job[\s\S]*TO service_role/iu);
  assert.doesNotMatch(sql, /GRANT EXECUTE[\s\S]*TO (?:anon|authenticated)/iu);
});
