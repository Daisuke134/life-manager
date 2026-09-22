"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { buildGoalWorkItem } = require("./goal-work-item.js");
const { createGeneralAgentWorkLoopAdapter } = require("./general-agent-work-adapter.js");

const NOW_MS = Date.parse("2026-09-22T12:00:00.000Z");

function goal(overrides = {}) {
  return {
    goal_id: "financial-continuity",
    tenant_id: "tenant-a",
    revision: 1,
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

function job() {
  return buildGoalWorkItem(goal(), NOW_MS);
}

function receipt(overrides = {}) {
  return {
    kind: "general_agent_work",
    status: "planned",
    tenant_id: "tenant-a",
    job_id: "goal:financial-continuity:r1",
    goal_ref: "goal-portfolio://tenant-a/financial-continuity?revision=1",
    execution_id: "bounded-execution-1",
    next_job_refs: ["runtime-job://tenant-a/next-job-1"],
    ...overrides,
  };
}

test("adapter plans from a portfolio goal and runs one bounded reference-only specialist", async () => {
  const calls = [];
  const adapter = createGeneralAgentWorkLoopAdapter({
    async runBoundedSpecialist(input) {
      calls.push(input);
      return receipt();
    },
  });

  assert.deepEqual(await adapter.plan({ portfolioGoal: goal(), nowMs: NOW_MS }), [job()]);
  const result = await adapter.execute(job());
  assert.deepEqual(calls, [{
    tenant_id: "tenant-a",
    job_id: "goal:financial-continuity:r1",
    goal_ref: "goal-portfolio://tenant-a/financial-continuity?revision=1",
  }]);
  assert.deepEqual(result, { receipt: receipt() });
  assert.equal(adapter.verify(result.receipt, job()), true);
  assert.deepEqual(adapter.report(result.receipt), {
    status: "planned",
    execution_id: "bounded-execution-1",
    next_job_count: 1,
  });
  assert.deepEqual(await adapter.reconcile({}), { state: "unknown" });
  assert.doesNotMatch(JSON.stringify([calls, result]), /financial surplus|settled revenue|life-manager\/J4|secret|chat/i);
});

test("adapter rejects mismatched goal references and overbroad receipts", async () => {
  await assert.rejects(createGeneralAgentWorkLoopAdapter().execute(job()), /specialist/i);
  for (const malformed of [
    receipt({ tenant_id: "tenant-b" }),
    receipt({ job_id: "goal:other:r1" }),
    receipt({ goal_ref: "goal-portfolio://tenant-a/other?revision=1" }),
    receipt({ goal_ref: "goal-portfolio://tenant-a/financial-continuity?revision=2" }),
    receipt({ next_job_refs: ["https://private.example/job"] }),
    receipt({ goal_statement: "raw goal must not escape" }),
  ]) {
    const adapter = createGeneralAgentWorkLoopAdapter({
      async runBoundedSpecialist() { return malformed; },
    });
    await assert.rejects(adapter.execute(job()), /receipt/i);
    assert.equal(adapter.verify(malformed, job()), false);
  }
});
