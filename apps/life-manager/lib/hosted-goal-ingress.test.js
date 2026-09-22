"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { createSecretProvider } = require("./secret-provider.js");
const { enqueueHostedGoal } = require("./hosted-goal-ingress.js");
const { createGeneralAgentWorkLoopAdapter } = require("./general-agent-work-adapter.js");
const { executeCapabilityJob } = require("../scripts/runtime-up.js");

const NOW_MS = Date.parse("2026-09-22T12:00:00.000Z");

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

function fixture(overrides = {}) {
  const jobs = new Map();
  const calls = [];
  let savedPortfolio = overrides.savedPortfolio || null;
  const vault = {
    async get() { throw new Error("ingress must not read secret values"); },
    async health() { return overrides.vaultHealth || { ok: true }; },
  };
  return {
    calls,
    jobs,
    get savedPortfolio() { return savedPortfolio; },
    deps: {
      async loadTenant(tenantId) {
        calls.push(["tenant", tenantId]);
        return overrides.tenant || {
          uid: "tenant-a",
          telegram_chat_id: "chat-a",
          phone: "phone-redacted",
          paid: true,
          fact_refs: ["fact://tenant-a/income"],
          evidence_refs: ["policy://life-manager/J4"],
          boundary_refs: ["boundary://tenant-a/no-spend"],
        };
      },
      secretProvider: createSecretProvider({ mode: "cloud", vault }),
      async loadGoalPortfolio(tenantId) {
        calls.push(["load-portfolio", tenantId]);
        return savedPortfolio;
      },
      async generateGoalPortfolio(input) {
        calls.push(["generate", input]);
        return { goals: [candidate()] };
      },
      async saveGoalPortfolio(portfolio) {
        calls.push(["save", portfolio]);
        savedPortfolio = portfolio;
      },
      async enqueueJob(input) {
        calls.push(["enqueue", input]);
        const key = `${input.tenantId}:${input.jobId}`;
        const created = !jobs.has(key);
        jobs.set(key, input);
        return { created };
      },
    },
  };
}

function hostedInput(overrides = {}) {
  return {
    scope: { authenticated: true, tenantId: "tenant-a", chatId: "chat-a" },
    nowMs: NOW_MS,
    ...overrides,
  };
}

test("hosted ingress creates and persists its own goal once then replay is zero", async () => {
  const f = fixture();
  const first = await enqueueHostedGoal(hostedInput(), f.deps);
  const replay = await enqueueHostedGoal(hostedInput(), f.deps);

  assert.deepEqual(first, {
    created: true,
    tenant_id: "tenant-a",
    job_id: "goal:financial-continuity:r1",
    job_ref: "runtime-job://tenant-a/goal%3Afinancial-continuity%3Ar1",
    vault_provider: "vault",
  });
  assert.deepEqual(replay, { ...first, created: false });
  assert.equal(f.calls.filter(([kind]) => kind === "generate").length, 1);
  assert.equal(f.calls.filter(([kind]) => kind === "save").length, 1);
  assert.equal(f.savedPortfolio.origin, "life_manager");
  assert.equal(f.jobs.size, 1);
  assert.deepEqual([...f.jobs.values()][0], {
    jobId: "goal:financial-continuity:r1",
    tenantId: "tenant-a",
    loopId: "life-manager.manager",
    capability: "general-agent.work",
    effectClass: "none",
    effectKey: null,
    inputRefs: {
      goal_ref: "goal-portfolio://tenant-a/financial-continuity?revision=1",
    },
    maxAttempts: 1,
  });
  assert.doesNotMatch(JSON.stringify([first, replay, [...f.jobs.values()]]), /financial surplus|settled revenue|chat-a|phone-redacted|secret/i);
});

test("caller-authored goals are rejected before model save or enqueue", async () => {
  const f = fixture();
  await assert.rejects(enqueueHostedGoal(hostedInput({ goal: candidate() }), f.deps), /user goal|caller goal/i);
  assert.equal(f.calls.filter(([kind]) => ["generate", "save", "enqueue"].includes(kind)).length, 0);
  assert.equal(f.jobs.size, 0);
});

test("unauthenticated unpaid cross-tenant and unhealthy-vault requests have zero effect", async () => {
  const cases = [
    { input: hostedInput({ scope: { authenticated: false, tenantId: "tenant-a", chatId: "chat-a" } }) },
    { input: hostedInput(), tenant: { uid: "tenant-a", telegram_chat_id: "chat-a", paid: false } },
    { input: hostedInput({ scope: { authenticated: true, tenantId: "tenant-a", chatId: "chat-b" } }) },
    { input: hostedInput(), tenant: { uid: "tenant-b", telegram_chat_id: "chat-a", paid: true } },
    { input: hostedInput(), vaultHealth: { ok: false } },
  ];

  for (const item of cases) {
    const f = fixture(item);
    await assert.rejects(enqueueHostedGoal(item.input, f.deps), /authenticated|scope|entitlement|vault/i);
    assert.equal(f.calls.filter(([kind]) => ["generate", "save", "enqueue"].includes(kind)).length, 0);
    assert.equal(f.jobs.size, 0);
  }
});

test("one hosted tenant crosses vault queue worker receipt and replay-zero", async () => {
  const f = fixture();
  const first = await enqueueHostedGoal(hostedInput(), f.deps);
  const queued = [...f.jobs.values()][0];
  const claimed = {
    job_id: queued.jobId,
    tenant_id: queued.tenantId,
    loop_id: queued.loopId,
    capability: queued.capability,
    effect_class: queued.effectClass,
    effect_key: queued.effectKey,
    input_refs: queued.inputRefs,
    max_attempts: queued.maxAttempts,
    attempt: 1,
  };
  const workerCalls = [];
  const receipts = [];
  let scheduledHeartbeat;
  let specialistRuns = 0;
  const adapter = createGeneralAgentWorkLoopAdapter({
    async runBoundedSpecialist(work) {
      specialistRuns += 1;
      await scheduledHeartbeat();
      return {
        kind: "general_agent_work",
        status: "planned",
        tenant_id: work.tenant_id,
        job_id: work.job_id,
        goal_ref: work.goal_ref,
        execution_id: "bounded-execution-1",
        next_job_refs: ["runtime-job://tenant-a/next-job-1"],
      };
    },
  });

  await executeCapabilityJob(claimed, {
    workerId: "hosted-worker-a",
    handlers: { "general-agent.work": (work) => adapter.execute(work) },
    heartbeatJob: async (value) => workerCalls.push(["heartbeat", value]),
    completeJob: async (value) => { workerCalls.push(["complete", value]); receipts.push(value.receipt); },
    failJob: async (value) => workerCalls.push(["fail", value]),
    leaseSeconds: 90,
    setIntervalFn(callback) { scheduledHeartbeat = callback; return "heartbeat-timer"; },
    clearIntervalFn(timer) { workerCalls.push(["clear", timer]); },
  });

  const replay = await enqueueHostedGoal(hostedInput(), f.deps);
  assert.equal(first.created, true);
  assert.equal(replay.created, false);
  assert.equal(specialistRuns, 1);
  assert.equal(f.jobs.size, 1);
  assert.equal(receipts.length, 1);
  assert.deepEqual(workerCalls.map(([kind]) => kind), ["heartbeat", "clear", "complete"]);
  assert.deepEqual(receipts[0], {
    kind: "general_agent_work",
    status: "planned",
    tenant_id: "tenant-a",
    job_id: "goal:financial-continuity:r1",
    goal_ref: "goal-portfolio://tenant-a/financial-continuity?revision=1",
    execution_id: "bounded-execution-1",
    next_job_refs: ["runtime-job://tenant-a/next-job-1"],
  });
  assert.doesNotMatch(JSON.stringify(receipts), /financial surplus|settled revenue|chat-a|phone-redacted|secret/i);
});
