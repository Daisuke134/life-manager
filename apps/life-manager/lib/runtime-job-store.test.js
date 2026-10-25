"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {
  buildRuntimeJob,
  enqueueJob,
  enqueueJobAt,
  readCommonJob,
  readCommonReceipt,
  claimJobs,
  claimReconcilingJobs,
  withRuntimeTenantControlLock,
  heartbeatJob,
  completeJob,
  completeJobAndEnqueue,
  failJob,
  resolveReconciliation,
  resolveReconciliationAndEnqueue,
  recordUnknownReconciliation,
  MAX_UNKNOWN_RECONCILE_RESULTS,
} = require("./runtime-job-store.js");

test("Railway app-root startup does not eagerly require repo-root contracts", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-railway-root-"));
  const lib = path.join(root, "lib");
  fs.mkdirSync(lib);
  fs.copyFileSync(path.join(__dirname, "runtime-job-store.js"), path.join(lib, "runtime-job-store.js"));
  assert.doesNotThrow(() => require(path.join(lib, "runtime-job-store.js")));
  fs.rmSync(root, { recursive: true, force: true });
});

const MIGRATION = fs.readFileSync(path.join(
  __dirname,
  "../migrations/20260729_runtime_jobs.sql",
), "utf8");
const AGING_MIGRATION = fs.readFileSync(path.join(
  __dirname,
  "../migrations/20260730_runtime_reconcile_unknown_aging.sql",
), "utf8");

function sampleJob(overrides = {}) {
  return {
    jobId: "job-001",
    tenantId: "tenant-a",
    loopId: "marketing.an icca.slideshow",
    capability: "content.publish",
    effectClass: "publish",
    effectKey: "tiktok:anicca:asset-001",
    inputRefs: {
      product_ref: "product:anicca",
      asset_ref: "object:sha256:abc",
    },
    maxAttempts: 3,
    ...overrides,
  };
}

test("runtime job is tenant-bound, reference-only, bounded, and immutable", () => {
  const job = buildRuntimeJob(sampleJob());
  assert.equal(job.job_id, "job-001");
  assert.equal(job.tenant_id, "tenant-a");
  assert.equal(job.effect_class, "publish");
  assert.equal(job.max_attempts, 3);
  assert.deepEqual(job.input_refs, {
    product_ref: "product:anicca",
    asset_ref: "object:sha256:abc",
  });
  assert.equal(Object.isFrozen(job), true);

  assert.throws(() => buildRuntimeJob(sampleJob({
    inputRefs: { password: "do-not-store-secrets" },
  })), /reference-only/i);
  assert.throws(() => buildRuntimeJob(sampleJob({
    effectClass: "money",
    effectKey: "",
  })), /effect key/i);
  assert.throws(() => buildRuntimeJob(sampleJob({ maxAttempts: 0 })), /max attempts/i);
});

test("enqueue is idempotent by job id and rejects a cross-tenant collision", async () => {
  const calls = [];
  const existing = {
    job_id: "job-001",
    tenant_id: "tenant-a",
    loop_id: "marketing.anicca.slideshow",
    capability: "content.publish",
    effect_class: "publish",
    effect_key: "tiktok:anicca:asset-001",
    input_refs: sampleJob().inputRefs,
    max_attempts: 3,
    status: "queued",
  };
  const query = async (sql, params) => {
    calls.push({ sql, params });
    if (/INSERT INTO public\.lm_runtime_jobs/i.test(sql)) return { rows: [] };
    return { rows: [existing] };
  };

  const result = await enqueueJob(sampleJob({
    loopId: "marketing.anicca.slideshow",
  }), { query });
  assert.deepEqual(result, { created: false, job: existing });
  assert.match(calls[0].sql, /ON CONFLICT \(job_id\) DO NOTHING/i);
  assert.match(calls[1].sql, /WHERE job_id = \$1 AND tenant_id = \$2/i);
  assert.equal(calls[1].params[1], "tenant-a");

  await assert.rejects(
    enqueueJob(sampleJob(), {
      query: async (sql) => (/INSERT/i.test(sql) ? { rows: [] } : { rows: [] }),
    }),
    /collision/i,
  );
});

test("enqueue accepts the canonical job returned by buildRuntimeJob", async () => {
  const canonical = buildRuntimeJob(sampleJob({
    loopId: "marketing.anicca.slideshow",
  }));
  const result = await enqueueJob(canonical, {
    query: async (sql) => ({
      rows: /INSERT INTO public\.lm_runtime_jobs/i.test(sql)
        ? [{ ...canonical, status: "queued" }]
        : [],
    }),
  });

  assert.equal(result.created, true);
  assert.equal(result.job.job_id, canonical.job_id);
  assert.equal(result.job.effect_class, "publish");
});

test("scheduled enqueue writes available_at atomically and keeps idempotency exact", async () => {
  const calls = [];
  const canonical = buildRuntimeJob(sampleJob({ loopId: "connector.events" }));
  const availableAt = "2026-08-02T01:05:00.000Z";
  const query = async (sql, params) => {
    calls.push({ sql, params });
    return { rows: [{ ...canonical, available_at: availableAt, status: "queued" }] };
  };
  const created = await enqueueJobAt(canonical, availableAt, { query });
  assert.equal(created.created, true);
  assert.match(calls[0].sql, /available_at/i);
  assert.equal(calls[0].params.at(-1), availableAt);

  const existingQuery = async (sql) => ({
    rows: /INSERT INTO public\.lm_runtime_jobs/i.test(sql)
      ? []
      : [{ ...canonical, available_at: availableAt, status: "queued" }],
  });
  assert.equal((await enqueueJobAt(canonical, availableAt, { query: existingQuery })).created, false);
  await assert.rejects(enqueueJobAt(canonical, "not-a-time", { query }), /available time invalid/i);
  await assert.rejects(enqueueJobAt(canonical, "2026-08-02T01:06:00.000Z", {
    query: async (sql) => ({ rows: /INSERT/i.test(sql) ? [] : [{ ...canonical, available_at: availableAt }] }),
  }), /available time collision/i);
});

test("Postgres rows project through the common Job contract at a tenant-scoped read boundary", async () => {
  const row = {
    job_id: "job-001", tenant_id: "tenant-a", loop_id: "marketing.anicca.slideshow",
    capability: "content.publish", effect_class: "publish",
    effect_key: "tiktok:anicca:asset-001", input_refs: sampleJob().inputRefs,
    max_attempts: 3,
  };
  const calls = [];
  const projected = await readCommonJob({ tenantId: "tenant-a", jobId: "job-001" }, {
    query: async (sql, params) => { calls.push({ sql, params }); return { rows: [row] }; },
  });
  assert.deepEqual(projected, { schema_version: 1, record_type: "job", ...row });
  assert.match(calls[0].sql, /WHERE job_id = \$1 AND tenant_id = \$2/i);
  assert.deepEqual(calls[0].params, ["job-001", "tenant-a"]);

  assert.equal(await readCommonJob({ tenantId: "tenant-a", jobId: "missing" }, {
    query: async () => ({ rows: [] }),
  }), null);
  await assert.rejects(readCommonJob({ tenantId: "tenant-a", jobId: "legacy" }, {
    query: async () => ({ rows: [{ ...row, loop_id: "legacy loop" }] }),
  }), /common Job loop_id invalid/);
});

test("immutable Postgres receipts project only with provider verification evidence", async () => {
  const row = {
    job_id: "job-001", tenant_id: "tenant-a", attempt: 1, outcome: "completed",
    effect_key: "tiktok:anicca:asset-001", loop_id: "marketing.anicca.slideshow",
    effect_class: "publish", created_at: "2026-09-07T00:00:00Z",
    receipt: {
      provider: "postiz", provider_post_id: "post-1", run_id: "run-1",
      evidence_refs: ["postiz://post/post-1"], status: "published",
    },
  };
  const calls = [];
  const projected = await readCommonReceipt({ tenantId: "tenant-a", jobId: "job-001", attempt: 1 }, {
    query: async (sql, params) => { calls.push({ sql, params }); return { rows: [row] }; },
  });
  assert.equal(projected.record_type, "receipt");
  assert.equal(projected.outcome, "verified");
  assert.equal(projected.provider, "postiz");
  assert.equal(projected.external_ref, "post-1");
  assert.deepEqual(projected.evidence_refs, ["postiz://post/post-1"]);
  assert.match(projected.payload_sha256, /^[a-f0-9]{64}$/);
  assert.match(calls[0].sql, /JOIN public\.lm_runtime_jobs/i);
  assert.deepEqual(calls[0].params, ["job-001", "tenant-a", 1]);

  await assert.rejects(readCommonReceipt({ tenantId: "tenant-a", jobId: "job-001", attempt: 1 }, {
    query: async () => ({ rows: [{ ...row, receipt: { status: "published" } }] }),
  }), /lacks provider verification evidence/);
  await assert.rejects(readCommonReceipt({ tenantId: "tenant-a", jobId: "job-001", attempt: 1 }, {
    query: async () => ({ rows: [{ ...row, receipt: { ...row.receipt, provider_post_id: {} } }] }),
  }), /external reference is invalid/);
  await assert.rejects(readCommonReceipt({ tenantId: "tenant-a", jobId: "job-001", attempt: 1 }, {
    query: async () => ({ rows: [{ ...row, effect_class: "none", effect_key: null }] }),
  }), /requires an external effect/);
  await assert.rejects(readCommonReceipt({ tenantId: "tenant-a", jobId: "job-001", attempt: 1 }, {
    query: async () => ({ rows: [{ ...row, outcome: "reconciled_absent" }] }),
  }), /not representable/);
});

test("claim filters capabilities, has a bounded lease, and uses one narrow atomic RPC", async () => {
  const calls = [];
  const rows = [{ job_id: "job-001", tenant_id: "tenant-a", attempt: 1 }];
  const query = async (sql, params) => {
    calls.push({ sql, params });
    return { rows };
  };
  const claimed = await claimJobs({
    workerId: "worker-publish-1",
    capabilities: ["content.publish", "content.render"],
    tenantId: "tenant-a",
    limit: 2,
    leaseSeconds: 180,
  }, { query });

  assert.deepEqual(claimed, rows);
  assert.match(calls[0].sql, /claim_lm_runtime_jobs\(\$1, \$2::text\[\], \$3, \$4, \$5\)/i);
  assert.deepEqual(calls[0].params, [
    "worker-publish-1",
    ["content.publish", "content.render"],
    "tenant-a",
    2,
    180,
  ]);
});

test("heartbeat, completion, failure, and reconciliation are tenant and attempt scoped", async () => {
  const calls = [];
  const query = async (sql, params) => {
    calls.push({ sql, params });
    return { rows: [{ job_id: "job-001", tenant_id: "tenant-a", attempt: 1 }] };
  };
  const identity = {
    tenantId: "tenant-a",
    jobId: "job-001",
    attempt: 1,
    workerId: "worker-publish-1",
  };

  await heartbeatJob({ ...identity, leaseSeconds: 180 }, { query });
  await completeJob({
    ...identity,
    receipt: { provider_id: "post-123", url: "https://example.com/post/123" },
  }, { query });
  await failJob({ ...identity, errorCode: "TIMEOUT", unknownEffect: true }, { query });
  await resolveReconciliation({
    tenantId: "tenant-a",
    jobId: "job-001",
    attempt: 1,
    decision: "absent",
    receipt: { lookup: "not_found" },
  }, { query });

  for (const call of calls) {
    assert.equal(call.params[0], "tenant-a");
    assert.equal(call.params[1], "job-001");
    assert.equal(call.params[2], 1);
  }
  assert.match(calls[0].sql, /heartbeat_lm_runtime_job/i);
  assert.match(calls[1].sql, /complete_lm_runtime_job/i);
  assert.match(calls[2].sql, /fail_lm_runtime_job/i);
  assert.equal(calls[2].params[5], true);
  assert.match(calls[3].sql, /resolve_lm_runtime_effect/i);
  assert.equal(calls[3].params[3], "absent");
});

test("collision error names the mismatched fields so operators can diagnose slot-lineage drift", async () => {
  // S-1: the existing publish effect was enqueued with different lineage (for example the
  // same creative re-planned at a new slot). The error must say WHAT differs.
  const existing = {
    job_id: "job-001",
    tenant_id: "tenant-a",
    loop_id: "marketing.anicca.slideshow",
    capability: "content.publish",
    effect_class: "publish",
    effect_key: "tiktok:anicca:asset-001",
    input_refs: {
      product_ref: "product:anicca",
      asset_ref: "object:sha256:abc",
      slot_ref: "slot:2026-07-30T12:30:00.000Z",
    },
    max_attempts: 3,
    status: "queued",
  };
  const query = async (sql) => (
    /INSERT INTO public\.lm_runtime_jobs/i.test(sql) ? { rows: [] } : { rows: [existing] }
  );

  await assert.rejects(
    enqueueJob(sampleJob({ loopId: "marketing.anicca.slideshow" }), { query }),
    (error) => {
      assert.match(error.message, /runtime job id collision/);
      assert.match(error.message, /input_refs/);
      assert.match(error.message, /lineage|slot/i);
      return true;
    },
  );
});

test("unknown reconcile aging uses one narrow RPC with the bounded constant", async () => {
  assert.equal(MAX_UNKNOWN_RECONCILE_RESULTS, 5);
  const calls = [];
  const query = async (sql, params) => {
    calls.push({ sql, params });
    return {
      rows: [{
        job_id: "job-001", tenant_id: "tenant-a", attempt: 1,
        status: "reconciling", reconcile_attempts: 1,
      }],
    };
  };

  const row = await recordUnknownReconciliation({
    tenantId: "tenant-a",
    jobId: "job-001",
    attempt: 1,
    maxUnknownResults: MAX_UNKNOWN_RECONCILE_RESULTS,
  }, { query });

  assert.equal(row.status, "reconciling");
  assert.match(calls[0].sql, /age_lm_runtime_reconciliation\(\$1, \$2, \$3, \$4\)/i);
  assert.deepEqual(calls[0].params, ["tenant-a", "job-001", 1, 5]);

  await assert.rejects(recordUnknownReconciliation({
    tenantId: "tenant-a",
    jobId: "job-001",
    attempt: 1,
    maxUnknownResults: 0,
  }, { query }), /unknown limit/i);
  await assert.rejects(recordUnknownReconciliation({
    tenantId: "tenant-a",
    jobId: "job-001",
    attempt: 1,
  }, { query: async () => ({ rows: [] }) }), /lost job/i);
});

test("money completion and its continuation use one atomic RPC", async () => {
  const calls = [];
  const row = await completeJobAndEnqueue({ tenantId: "tenant-a", jobId: "job-001", attempt: 1,
    workerId: "worker-a", receipt: { kind: "agent_economy_wake" },
    nextJob: sampleJob({ jobId: "job-002", tenantId: "tenant-a", loopId: "agent-economy",
      capability: "agent-economy.start", effectClass: "money", effectKey: "wake:2", maxAttempts: 1 }),
    availableAt: "2026-09-11T00:05:00.000Z" }, { query: async (sql, params) => {
    calls.push({ sql, params });
    return { rows: [{ job_id: "job-001", tenant_id: "tenant-a", attempt: 1 }] };
  } });
  assert.equal(row.job_id, "job-001");
  assert.equal(calls.length, 1);
  assert.match(calls[0].sql, /complete_lm_runtime_job_and_enqueue/);
  assert.equal(calls[0].params[10], "tenant-a");
});

test("aging migration adds a durable unknown counter that dead-letters exhausted reconciliation", () => {
  assert.match(AGING_MIGRATION, /ADD COLUMN IF NOT EXISTS reconcile_attempts/i);
  assert.match(AGING_MIGRATION, /age_lm_runtime_reconciliation/i);
  assert.match(AGING_MIGRATION, /RECONCILE_UNKNOWN_EXHAUSTED/);
  assert.match(AGING_MIGRATION, /dead_letter/);
  // Resolution (present or absent) resets the counter so a later reconciliation
  // lifecycle starts its own aging window.
  assert.match(AGING_MIGRATION, /reconcile_attempts = 0/);
  assert.match(AGING_MIGRATION, /status = 'reconciling'/);
});

test("migration enforces atomic claim, bounded retry, unique effects, and immutable receipts", () => {
  assert.match(MIGRATION, /CREATE TABLE IF NOT EXISTS public\.lm_runtime_jobs/i);
  assert.match(MIGRATION, /CREATE TABLE IF NOT EXISTS public\.lm_runtime_job_receipts/i);
  assert.match(MIGRATION, /PRIMARY KEY \(job_id, attempt\)/i);
  assert.match(MIGRATION, /UNIQUE \(tenant_id, effect_key\)/i);
  assert.match(MIGRATION, /FOR UPDATE SKIP LOCKED/i);
  assert.match(MIGRATION, /UPDATE public\.lm_runtime_jobs[\s\S]*RETURNING/i);
  assert.match(MIGRATION, /attempt < max_attempts/i);
  assert.match(MIGRATION, /dead_letter/i);
  assert.match(MIGRATION, /status = 'reconciling'/i);
  assert.match(MIGRATION, /OLD TABLE|immutable/i);
  assert.doesNotMatch(MIGRATION, /advisory_(?:lock|xact_lock)/i);
});


test("reconciliation readback seats are bounded and preserve original job due time", async () => {
  const row = { ...buildRuntimeJob(sampleJob()), status: "reconciling", attempt: 1,
    available_at: "2026-10-20T00:00:00.000Z" };
  const calls = [];
  const opts = { query: async (sql, params) => { calls.push({ sql, params }); return { rows: [row] }; } };
  assert.deepEqual(await claimReconcilingJobs({ capabilities: ["maritime.manager.cycle"], tenantId: "tenant-a", limit: 2 }, opts), [row]);
  assert.deepEqual(calls[0].params, [["maritime.manager.cycle"], "tenant-a", 2]);
  assert.match(calls[0].sql, /FOR UPDATE SKIP LOCKED/i);
  assert.match(calls[0].sql, /updated_at[^]*interval '30 seconds'/i);
  assert.match(calls[0].sql, /SET updated_at = clock_timestamp\(\)/i);
  assert.doesNotMatch(calls[0].sql, /SET available_at/i);
  for (const invalid of [0, 51, -1]) {
    await assert.rejects(() => claimReconcilingJobs({ capabilities: ["x"], limit: invalid }, opts), /limit/);
  }
  await assert.rejects(() => claimReconcilingJobs({ capabilities: [] }, opts), /capabilities/);
  assert.equal(calls.length, 1);
});


test("reconciled completion and successor share one transaction with rollback and tenant fence", async () => {
  const calls = [];
  let failInsert = false;
  const nextJob = sampleJob({ jobId: "job-next", effectKey: "effect-next" });
  const scheduled = { ...buildRuntimeJob(nextJob), available_at: "2026-10-21T00:00:00.000Z" };
  const client = {
    query: async (sql, params) => {
      calls.push(sql.trim());
      if (/resolve_lm_runtime_effect/.test(sql)) return { rows: [{ status: "completed" }] };
      if (/INSERT INTO/.test(sql)) { if (failInsert) throw new Error("enqueue failed"); return { rows: [scheduled] }; }
      return { rows: [] };
    },
    release: () => calls.push("RELEASE"),
  };
  const input = { tenantId: "tenant-a", jobId: "job-001", attempt: 1, decision: "present", receipt: { ok: true }, nextJob, availableAt: scheduled.available_at };
  const opts = { connect: async () => client };
  assert.equal((await resolveReconciliationAndEnqueue(input, opts)).status, "completed");
  assert.equal(calls[0], "BEGIN");
  assert.match(calls[1], /resolve_lm_runtime_effect/);
  assert.match(calls[2], /INSERT INTO/);
  assert.deepEqual(calls.slice(-2), ["COMMIT", "RELEASE"]);
  calls.length = 0; failInsert = true;
  await assert.rejects(() => resolveReconciliationAndEnqueue(input, opts), /enqueue failed/);
  assert.deepEqual(calls.slice(-2), ["ROLLBACK", "RELEASE"]);
  calls.length = 0;
  await assert.rejects(() => resolveReconciliationAndEnqueue({ ...input, nextJob: { ...nextJob, tenantId: "foreign" } }, opts), /tenant mismatch/);
  await assert.rejects(() => resolveReconciliationAndEnqueue({ ...input, decision: "absent" }, opts), /decision/);
  assert.deepEqual(calls, []);
});


test("tenant control lock uses a dedicated bounded transaction and releases on error",async()=>{
 const calls=[];const client={query:async(sql,params)=>{calls.push([sql,params]);return {rows:[]};},release:()=>calls.push(['RELEASE'])};
 const opts={connect:async()=>client};
 assert.equal(await withRuntimeTenantControlLock({tenantId:'tenant-a'},async()=>{calls.push(['OP']);return 'ok';},opts),'ok');
 assert.equal(calls[0][0],'BEGIN');assert.match(calls[1][0],/lock_timeout/);assert.match(calls[2][0],/pg_advisory_xact_lock/);
 assert.deepEqual(calls[2][1],['maritime-control:tenant-a']);assert.deepEqual(calls.slice(-2),[['COMMIT',undefined],['RELEASE']]);
 calls.length=0;await assert.rejects(()=>withRuntimeTenantControlLock({tenantId:'tenant-a'},async()=>{throw new Error('fixture failure');},opts),/fixture failure/);
 assert.deepEqual(calls.slice(-2),[['ROLLBACK',undefined],['RELEASE']]);
});

test("only the two Maritime Capafy capabilities accept their exact tenant-bound identity refs", async () => {
  const tenant = "lm_11111111-1111-4111-8111-111111111111";
  const providerRuntime = require("./maritime-manager-provider-runtime.js");
  const shared = {tenantId:tenant,releaseSha:"b".repeat(40),occurrenceId:"slot:1",
    cycleJobId:"maritime-cycle:"+"a".repeat(64),artifactRef:"artifact://original/listing.md",
    accountRef:`account://capafy/${tenant}/seller-1`};
  const canonicalPrepare = providerRuntime.buildMaritimeCapafyPrepareJob(shared);
  for (const phase of ["prepare", "publish"]) {
    const canonical = phase === "prepare" ? canonicalPrepare : providerRuntime.buildMaritimeCapafyPublishJob({
      ...shared,sourceCycleJobId:shared.cycleJobId,prepareJobId:canonicalPrepare.job_id,agentId:"123",agentVersionId:"456"});
    const job=buildRuntimeJob(canonical);
    const refs=canonical.input_refs;
    assert.deepEqual(job.input_refs,refs);
    const hydrated=await readCommonJob({tenantId:tenant,jobId:job.job_id},{query:async()=>({rows:[job]})});
    assert.deepEqual(hydrated.input_refs,refs);
    const invalids=[
      {...canonical,capability:"other.publish"}, {...canonical,input_refs:{...refs,api_key:"secret"}},
      {...canonical,input_refs:{...refs,occurrence_id:"secret://token/value"}},
      {...canonical,input_refs:{...refs,account_ref:"account://capafy/lm_22222222-2222-4222-8222-222222222222/seller-1"}},
      {...canonical,input_refs:{...refs,source_cycle_job_id:"arbitrary"}}, {...canonical,max_attempts:2},
      {...canonical,input_refs:{...refs,agent_id:"secret://token/value"}},
      {...canonical,job_id:`maritime-capafy-${phase}:`+"d".repeat(64)},
      ...(phase==="publish"?[{...canonical,input_refs:{...refs,prepare_job_id:"maritime-capafy-prepare:"+"c".repeat(64)}}]:[]),
    ];
    for(const bad of invalids) assert.throws(()=>buildRuntimeJob(bad),/invalid|reference-only/);
    await assert.rejects(readCommonJob({tenantId:tenant,jobId:job.job_id},
      {query:async()=>({rows:[{...job,input_refs:{...refs,api_key:"secret"}}]})}),/invalid/);
  }
});
