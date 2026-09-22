"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const { createCloudGoalStore } = require("./cloud-goal-store.js");

const SCOPE_A = Object.freeze({ uid: "tenant-a", chatId: "101" });
const SCOPE_B = Object.freeze({ uid: "tenant-b", chatId: "202" });

function context(tenantId = "tenant-a", revision = 1, overrides = {}) {
  return {
    schema_version: "life-manager.goal-context.v1",
    tenant_id: tenantId,
    revision,
    fact_refs: [`fact://${tenantId}/income`],
    account_refs: [`account://${tenantId}/calendar`],
    consent_refs: [`consent://${tenantId}/calendar-read`],
    boundary_refs: [`boundary://${tenantId}/no-owner-spend`],
    ...overrides,
  };
}

function goal(tenantId = "tenant-a", revision = 1, overrides = {}) {
  return {
    goal_id: "financial-continuity",
    tenant_id: tenantId,
    revision,
    origin: "life_manager",
    statement: "Increase verified financial surplus within delegated boundaries",
    expected_outcome: "One attributable settled revenue receipt",
    confidence: 0.8,
    evidence_refs: ["policy://life-manager/J4"],
    cost_budget: { currency: "USD", minor_units: "0" },
    risk_budget: "low",
    dependencies: [],
    expires_at: null,
    success_receipt: null,
    status: "active",
    ...overrides,
  };
}

function portfolio(tenantId = "tenant-a", revision = 1, overrides = {}) {
  return {
    schema_version: "life-manager.goal-portfolio.v1",
    tenant_id: tenantId,
    revision,
    generated_at: "2026-09-22T12:00:00.000Z",
    origin: "life_manager",
    goals: [goal(tenantId, revision)],
    ...overrides,
  };
}

function memoryDatabase() {
  const users = new Map([
    ["tenant-a", { uid: "tenant-a", telegram_chat_id: "101", paid: true }],
    ["tenant-b", { uid: "tenant-b", telegram_chat_id: "202", paid: true }],
  ]);
  const contexts = new Map();
  const portfolios = new Map();
  const jobs = new Map();
  const receipts = new Map();
  const key = (tenantId, revision) => `${tenantId}:${revision}`;
  return {
    users, contexts, portfolios, jobs, receipts,
    async query(sql, params = []) {
      if (/put_lm_goal_context/i.test(sql)) {
        const [tenantId, chatId, revision, raw, digest] = params;
        const user = users.get(tenantId);
        if (!user || user.telegram_chat_id !== chatId) return { rows: [] };
        const id = key(tenantId, revision);
        const existing = contexts.get(id);
        if (existing && existing.context_sha256 !== digest) throw new Error("goal context collision");
        if (existing) return { rows: [{ ...existing, created: false }] };
        const row = {
          tenant_id: tenantId, revision, context: JSON.parse(raw),
          context_sha256: digest, created: true,
        };
        contexts.set(id, row);
        return { rows: [{ ...row }] };
      }
      if (/put_lm_goal_portfolio/i.test(sql)) {
        const [tenantId, revision, raw, digest] = params;
        if (!contexts.has(key(tenantId, revision))) return { rows: [] };
        const id = key(tenantId, revision);
        const existing = portfolios.get(id);
        if (existing && existing.portfolio_sha256 !== digest) throw new Error("goal portfolio collision");
        if (existing) return { rows: [{ ...existing, created: false }] };
        const row = {
          tenant_id: tenantId, revision, portfolio: JSON.parse(raw),
          portfolio_sha256: digest, created: true,
        };
        portfolios.set(id, row);
        return { rows: [{ ...row }] };
      }
      if (/SELECT user_row\.uid/i.test(sql)) {
        const [tenantId, chatId] = params;
        const user = users.get(tenantId);
        return { rows: user && user.telegram_chat_id === chatId ? [{ ...user }] : [] };
      }
      if (/FROM public\.lm_goal_contexts AS context_row/i.test(sql)) {
        const [tenantId, chatId, revision] = params;
        const user = users.get(tenantId);
        if (!user || (chatId != null && user.telegram_chat_id !== chatId)) return { rows: [] };
        const row = [...contexts.values()]
          .filter((value) => value.tenant_id === tenantId
            && (revision == null || value.revision === revision))
          .sort((left, right) => right.revision - left.revision)[0];
        return { rows: row ? [{ ...row }] : [] };
      }
      if (/FROM public\.lm_goal_portfolios AS portfolio_row/i.test(sql)) {
        const [tenantId] = params;
        const row = [...portfolios.values()]
          .filter((value) => value.tenant_id === tenantId)
          .sort((left, right) => right.revision - left.revision)[0];
        if (!row) return { rows: [] };
        const savedContext = contexts.get(key(tenantId, row.revision));
        return { rows: [{
          ...row,
          context: savedContext && savedContext.context,
          context_sha256: savedContext && savedContext.context_sha256,
        }] };
      }
      if (/FROM public\.lm_runtime_jobs AS jobs/i.test(sql)) {
        const [tenantId, jobId] = params;
        const row = jobs.get(`${tenantId}:${jobId}`);
        if (!row) return { rows: [] };
        const receipt = receipts.get(`${tenantId}:${jobId}`) || null;
        return { rows: [{ ...row, receipt: receipt && receipt.receipt, receipt_attempt: receipt && receipt.attempt }] };
      }
      throw new Error(`unexpected query: ${String(sql).slice(0, 80)}`);
    },
  };
}

test("context revisions persist once and exact replay survives a fresh store", async () => {
  const db = memoryDatabase();
  const store = createCloudGoalStore({ query: db.query });
  const first = await store.putContext(SCOPE_A, context());
  const replay = await store.putContext(SCOPE_A, context());
  assert.equal(first.created, true);
  assert.equal(replay.created, false);
  assert.deepEqual(first.context, context());

  await assert.rejects(
    store.putContext(SCOPE_A, context("tenant-a", 1, {
      fact_refs: ["fact://tenant-a/changed"],
    })),
    /context collision/i,
  );
  const second = await store.putContext(SCOPE_A, context("tenant-a", 2));
  assert.equal(second.created, true);
  assert.equal((await createCloudGoalStore({ query: db.query }).loadContext(SCOPE_A)).revision, 2);
  assert.equal(db.contexts.size, 2);
});

test("context and tenant reads require the exact existing Panel scope", async () => {
  const db = memoryDatabase();
  const store = createCloudGoalStore({ query: db.query });
  await store.putContext(SCOPE_A, context());
  assert.equal(await store.loadContext({ uid: "tenant-a", chatId: "202" }), null);
  assert.equal(await store.loadTenant({ uid: "tenant-a", chatId: "202" }), null);
  await assert.rejects(
    store.putContext({ uid: "tenant-a", chatId: "202" }, context()),
    /scope mismatch/i,
  );
  assert.deepEqual(await store.loadTenant(SCOPE_A), {
    uid: "tenant-a",
    telegram_chat_id: "101",
    paid: true,
    fact_refs: ["fact://tenant-a/income"],
    evidence_refs: [
      "policy://life-manager/J4",
      "account://tenant-a/calendar",
      "consent://tenant-a/calendar-read",
    ],
    boundary_refs: ["boundary://tenant-a/no-owner-spend"],
  });
  assert.equal(JSON.stringify(await store.loadTenant(SCOPE_A)).includes("no-owner-spend"), true);
});

test("validated portfolios are immutable by tenant revision and reload with context authority", async () => {
  const db = memoryDatabase();
  const store = createCloudGoalStore({ query: db.query });
  await store.putContext(SCOPE_A, context());
  const first = await store.saveGoalPortfolio(portfolio());
  const replay = await store.saveGoalPortfolio(portfolio());
  assert.equal(first.created, true);
  assert.equal(replay.created, false);
  assert.deepEqual(await createCloudGoalStore({ query: db.query }).loadGoalPortfolio("tenant-a"), portfolio());
  await assert.rejects(
    store.saveGoalPortfolio(portfolio("tenant-a", 1, {
      goals: [goal("tenant-a", 1, { statement: "Drifted statement" })],
    })),
    /portfolio collision/i,
  );
  await assert.rejects(store.saveGoalPortfolio(portfolio("tenant-b")), /context unavailable/i);
});

test("queued and completed jobs project only opaque tenant-scoped state", async () => {
  const db = memoryDatabase();
  const store = createCloudGoalStore({ query: db.query });
  const jobId = "goal:financial-continuity:r1";
  const goalRef = "goal-portfolio://tenant-a/financial-continuity?revision=1";
  db.jobs.set(`tenant-a:${jobId}`, {
    job_id: jobId,
    tenant_id: "tenant-a",
    loop_id: "life-manager.manager",
    capability: "general-agent.work",
    effect_class: "none",
    effect_key: null,
    input_refs: { goal_ref: goalRef },
    max_attempts: 1,
    status: "queued",
  });

  assert.deepEqual(await store.readProjection({ tenantId: "tenant-a", jobId }), {
    tenant_id: "tenant-a",
    goal_ref: goalRef,
    job_ref: "runtime-job://tenant-a/goal%3Afinancial-continuity%3Ar1",
    status: "queued",
    receipt_ref: null,
  });
  assert.equal(await store.readProjection({ tenantId: "tenant-b", jobId }), null);

  db.jobs.get(`tenant-a:${jobId}`).status = "completed";
  db.receipts.set(`tenant-a:${jobId}`, {
    attempt: 1,
    receipt: {
      kind: "general_agent_work",
      status: "planned",
      tenant_id: "tenant-a",
      job_id: jobId,
      goal_ref: goalRef,
      execution_id: "bounded-execution-1",
      next_job_refs: [],
    },
  });
  const completed = await store.readProjection({ tenantId: "tenant-a", jobId });
  assert.deepEqual(completed, {
    tenant_id: "tenant-a",
    goal_ref: goalRef,
    job_ref: "runtime-job://tenant-a/goal%3Afinancial-continuity%3Ar1",
    status: "planned",
    receipt_ref: "runtime-receipt://tenant-a/goal%3Afinancial-continuity%3Ar1/1",
  });
  assert.doesNotMatch(
    JSON.stringify(completed),
    /financial surplus|income|calendar-read|no-owner-spend|101|provider/i,
  );
});

test("migration keeps goal state immutable tenant-bound and service-role-only", () => {
  const sql = fs.readFileSync(path.join(
    __dirname,
    "../migrations/2026-09-22-lm-goal-context-portfolios.sql",
  ), "utf8");
  assert.match(sql, /CREATE TABLE IF NOT EXISTS public\.lm_goal_contexts/i);
  assert.match(sql, /CREATE TABLE IF NOT EXISTS public\.lm_goal_portfolios/i);
  assert.match(sql, /PRIMARY KEY \(tenant_id, revision\)/i);
  assert.match(sql, /REFERENCES public\.lm_users\(uid\)/i);
  assert.match(sql, /ENABLE ROW LEVEL SECURITY/gi);
  assert.match(sql, /users\.telegram_chat_id::text = p_chat_id/i);
  assert.match(sql, /pg_advisory_xact_lock/i);
  assert.match(sql, /goal context collision/i);
  assert.match(sql, /goal portfolio collision/i);
  assert.match(sql, /GRANT SELECT ON TABLE public\.lm_goal_contexts TO service_role/i);
  assert.match(sql, /GRANT SELECT ON TABLE public\.lm_goal_portfolios TO service_role/i);
  assert.doesNotMatch(sql, /GRANT [^;]*INSERT[^;]* TO service_role/i);
  assert.match(
    sql,
    /users\.telegram_chat_id::text = p_chat_id[\s\S]{0,120}FOR KEY SHARE/i,
  );
  const tenantLocks = sql.match(
    /hashtextextended\('lm_goal_state:' \|\| p_tenant_id, 0\)/g,
  ) || [];
  assert.equal(tenantLocks.length, 2);
  assert.match(sql, /GRANT EXECUTE ON FUNCTION public\.put_lm_goal_context[\s\S]+TO service_role/i);
  assert.match(sql, /GRANT EXECUTE ON FUNCTION public\.put_lm_goal_portfolio[\s\S]+TO service_role/i);
  assert.doesNotMatch(sql, /GRANT (?:SELECT|INSERT|UPDATE|DELETE|ALL|EXECUTE)[\s\S]{0,180} TO (?:anon|authenticated)/i);
  assert.match(sql, /lm_runtime_jobs_goal_ref_idx[\s\S]+input_refs->>'goal_ref'/i);
});
