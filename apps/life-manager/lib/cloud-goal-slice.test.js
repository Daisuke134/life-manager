"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { createCloudGoalStore } = require("./cloud-goal-store.js");
const { runCloudGoalSlice } = require("./cloud-goal-slice.js");
const { buildRuntimeJob } = require("./runtime-job-store.js");

const NOW_MS = Date.parse("2026-09-22T12:00:00.000Z");
const SESSION_A = "panel-session-a";

function context(overrides = {}) {
  return {
    schema_version: "life-manager.goal-context.v1",
    tenant_id: "tenant-a",
    revision: 1,
    fact_refs: ["fact://tenant-a/income"],
    account_refs: ["account://tenant-a/calendar"],
    consent_refs: ["consent://tenant-a/calendar-read"],
    boundary_refs: ["boundary://tenant-a/no-owner-spend"],
    ...overrides,
  };
}

function candidate(overrides = {}) {
  return {
    goal_id: "financial-continuity",
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

function memoryDatabase(overrides = {}) {
  const users = new Map([
    ["tenant-a", {
      uid: "tenant-a",
      telegram_chat_id: "101",
      paid: overrides.paid !== false,
    }],
    ["tenant-b", { uid: "tenant-b", telegram_chat_id: "202", paid: true }],
  ]);
  const sessions = new Map([
    [SESSION_A, { uid: "tenant-a", chatId: "101" }],
    ["mismatched-session", { uid: "tenant-a", chatId: "999" }],
  ]);
  const contexts = new Map();
  const portfolios = new Map();
  const jobs = new Map();
  const receipts = new Map();
  const calls = { resolve: 0, generate: 0, savePortfolio: 0, enqueue: 0 };
  const versionKey = (tenantId, revision) => `${tenantId}:${revision}`;
  return {
    users, sessions, contexts, portfolios, jobs, receipts, calls,
    async query(sql, params = []) {
      if (/put_lm_goal_context/i.test(sql)) {
        const [tenantId, chatId, revision, raw, sha256] = params;
        const user = users.get(tenantId);
        if (!user || user.telegram_chat_id !== chatId) return { rows: [] };
        const key = versionKey(tenantId, revision);
        const existing = contexts.get(key);
        if (existing && (existing.context_sha256 !== sha256
          || JSON.stringify(existing.context) !== JSON.stringify(JSON.parse(raw)))) {
          throw new Error("goal context collision");
        }
        if (existing) return { rows: [{ ...existing, created: false }] };
        const row = {
          tenant_id: tenantId,
          revision,
          context: JSON.parse(raw),
          context_sha256: sha256,
          created: true,
        };
        contexts.set(key, row);
        return { rows: [{ ...row }] };
      }
      if (/put_lm_goal_portfolio/i.test(sql)) {
        calls.savePortfolio += 1;
        const [tenantId, revision, raw, sha256] = params;
        const contextRow = contexts.get(versionKey(tenantId, revision));
        if (!contextRow) return { rows: [] };
        const key = versionKey(tenantId, revision);
        const existing = portfolios.get(key);
        if (existing && (existing.portfolio_sha256 !== sha256
          || JSON.stringify(existing.portfolio) !== JSON.stringify(JSON.parse(raw)))) {
          throw new Error("goal portfolio collision");
        }
        if (existing) return { rows: [{ ...existing, created: false }] };
        const row = {
          tenant_id: tenantId,
          revision,
          portfolio: JSON.parse(raw),
          portfolio_sha256: sha256,
          created: true,
        };
        portfolios.set(key, row);
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
        const contextRow = contexts.get(versionKey(tenantId, row.revision));
        return { rows: [{
          ...row,
          context: contextRow && contextRow.context,
          context_sha256: contextRow && contextRow.context_sha256,
        }] };
      }
      if (/FROM public\.lm_runtime_jobs AS jobs/i.test(sql)) {
        const [tenantId, jobId] = params;
        const row = jobs.get(`${tenantId}:${jobId}`);
        if (!row) return { rows: [] };
        const receipt = receipts.get(`${tenantId}:${jobId}`) || null;
        return { rows: [{
          ...row,
          receipt: receipt && receipt.receipt,
          receipt_attempt: receipt && receipt.attempt,
        }] };
      }
      throw new Error(`unexpected query: ${String(sql).slice(0, 80)}`);
    },
  };
}

function dependencies(db, overrides = {}) {
  const store = overrides.store || createCloudGoalStore({ query: db.query.bind(db) });
  return {
    resolveSession: async (session) => {
      db.calls.resolve += 1;
      return db.sessions.get(session) || null;
    },
    store,
    generateGoalPortfolio: async () => {
      db.calls.generate += 1;
      return { goals: [candidate()] };
    },
    enqueueJob: async (input) => {
      db.calls.enqueue += 1;
      const job = buildRuntimeJob(input);
      const key = `${job.tenant_id}:${job.job_id}`;
      const existing = db.jobs.get(key);
      if (existing) {
        assert.deepEqual(buildRuntimeJob(existing), job);
        return { created: false, job: existing };
      }
      const row = { ...job, status: "queued" };
      db.jobs.set(key, row);
      return { created: true, job: row };
    },
  };
}

function input(overrides = {}) {
  return { session: SESSION_A, nowMs: NOW_MS, context: context(), ...overrides };
}

test("authenticated first use persists once and fresh instances replay the same opaque job", async () => {
  const db = memoryDatabase();
  const firstDeps = dependencies(db);
  assert.deepEqual(Object.keys(firstDeps).sort(), [
    "enqueueJob", "generateGoalPortfolio", "resolveSession", "store",
  ]);
  const first = await runCloudGoalSlice(input(), firstDeps);
  const replay = await runCloudGoalSlice(
    { session: SESSION_A, nowMs: NOW_MS },
    firstDeps,
  );
  const fresh = await runCloudGoalSlice(
    { session: SESSION_A, nowMs: NOW_MS },
    dependencies(db),
  );

  const expected = {
    created: true,
    tenant_id: "tenant-a",
    goal_ref: "goal-portfolio://tenant-a/financial-continuity?revision=1",
    job_ref: "runtime-job://tenant-a/goal%3Afinancial-continuity%3Ar1",
    status: "queued",
    receipt_ref: null,
  };
  assert.deepEqual(first, expected);
  assert.deepEqual(replay, { ...expected, created: false });
  assert.deepEqual(fresh, { ...expected, created: false });
  assert.equal(db.calls.generate, 1);
  assert.equal(db.calls.savePortfolio, 1);
  assert.equal(db.contexts.size, 1);
  assert.equal(db.portfolios.size, 1);
  assert.equal(db.jobs.size, 1);
  assert.equal(db.jobs.values().next().value.effect_class, "none");

  await assert.rejects(
    runCloudGoalSlice(input({ context: context({ revision: 2 }) }), firstDeps),
    /context drift|revision-aware/i,
  );
  assert.equal(db.contexts.size, 1);
  assert.equal(db.calls.generate, 1);
  assert.equal(db.calls.savePortfolio, 1);
  assert.equal(db.jobs.size, 1);
});

test("safe projection exposes an opaque runtime receipt and no private source values", async () => {
  const db = memoryDatabase();
  const deps = dependencies(db);
  const first = await runCloudGoalSlice(input(), deps);
  const jobId = "goal:financial-continuity:r1";
  const key = `tenant-a:${jobId}`;
  db.jobs.get(key).status = "completed";
  db.jobs.get(key).provider_payload = "must-not-project";
  db.receipts.set(key, {
    attempt: 1,
    receipt: {
      kind: "general_agent_work",
      status: "planned",
      tenant_id: "tenant-a",
      job_id: jobId,
      goal_ref: first.goal_ref,
      execution_id: "bounded-execution-1",
      next_job_refs: [],
    },
  });

  const completed = await runCloudGoalSlice({ session: SESSION_A, nowMs: NOW_MS }, deps);
  assert.deepEqual(completed, {
    ...first,
    created: false,
    status: "planned",
    receipt_ref: "runtime-receipt://tenant-a/goal%3Afinancial-continuity%3Ar1/1",
  });
  assert.doesNotMatch(
    JSON.stringify(completed),
    /financial surplus|settled revenue|income|calendar|no-owner-spend|101|credential|provider/i,
  );
});

test("invalid caller session scope entitlement context and goal stop before goal work", async () => {
  const cases = [
    { request: input({ session: "" }), error: /session/i },
    { request: input({ session: "unknown" }), error: /session/i },
    { request: input({ session: "mismatched-session" }), error: /scope/i },
    { request: input({ context: { ...context(), fact_refs: ["raw-secret"] } }), error: /context/i },
    { request: input({ goal: candidate() }), error: /goal/i },
    { request: input({ nowMs: Number.NaN }), error: /time/i },
  ];

  for (const item of cases) {
    const db = memoryDatabase();
    await assert.rejects(runCloudGoalSlice(item.request, dependencies(db)), item.error);
    assert.equal(db.calls.generate, 0);
    assert.equal(db.calls.savePortfolio, 0);
    assert.equal(db.calls.enqueue, 0);
    assert.equal(db.portfolios.size, 0);
    assert.equal(db.jobs.size, 0);
  }

  const unpaid = memoryDatabase({ paid: false });
  await assert.rejects(runCloudGoalSlice(input(), dependencies(unpaid)), /entitlement/i);
  assert.equal(unpaid.calls.generate, 0);
  assert.equal(unpaid.calls.savePortfolio, 0);
  assert.equal(unpaid.calls.enqueue, 0);
  assert.equal(unpaid.portfolios.size, 0);
  assert.equal(unpaid.jobs.size, 0);
});

test("a foreign projection fails closed without another model save or job mutation", async () => {
  const db = memoryDatabase();
  await runCloudGoalSlice(input(), dependencies(db));
  const baseline = {
    generate: db.calls.generate,
    savePortfolio: db.calls.savePortfolio,
    portfolios: db.portfolios.size,
    jobs: db.jobs.size,
  };
  const realStore = createCloudGoalStore({ query: db.query.bind(db) });
  const foreignStore = {
    ...realStore,
    async readProjection() {
      return {
        tenant_id: "tenant-b",
        goal_ref: "goal-portfolio://tenant-b/foreign?revision=1",
        job_ref: "runtime-job://tenant-b/goal%3Aforeign%3Ar1",
        status: "queued",
        receipt_ref: null,
      };
    },
  };
  await assert.rejects(
    runCloudGoalSlice(
      { session: SESSION_A, nowMs: NOW_MS },
      dependencies(db, { store: foreignStore }),
    ),
    /projection|scope/i,
  );
  assert.equal(db.calls.generate, baseline.generate);
  assert.equal(db.calls.savePortfolio, baseline.savePortfolio);
  assert.equal(db.portfolios.size, baseline.portfolios);
  assert.equal(db.jobs.size, baseline.jobs);
});
