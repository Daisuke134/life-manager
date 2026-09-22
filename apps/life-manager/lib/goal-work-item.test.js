"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { buildGoalWorkItem } = require("./goal-work-item.js");

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

test("one active Life Manager goal becomes one reference-only effect-free WorkItem", () => {
  const workItem = buildGoalWorkItem(goal(), NOW_MS);
  assert.deepEqual(workItem, {
    job_id: "goal:financial-continuity:r1",
    tenant_id: "tenant-a",
    loop_id: "life-manager.manager",
    capability: "general-agent.work",
    effect_class: "none",
    effect_key: null,
    input_refs: {
      goal_ref: "goal-portfolio://tenant-a/financial-continuity?revision=1",
    },
    max_attempts: 1,
  });
  assert.equal(Object.isFrozen(workItem), true);
  assert.doesNotMatch(JSON.stringify(workItem), /financial surplus|settled revenue|life-manager\/J4/u);
});

test("inactive expired or malformed portfolio goals cannot become WorkItems", () => {
  assert.throws(() => buildGoalWorkItem(goal(), undefined), /observation time/i);
  assert.throws(
    () => buildGoalWorkItem(goal({ expires_at: "2026-09-22T11:59:59.000Z" }), NOW_MS),
    /active portfolio goal/i,
  );
  assert.throws(
    () => buildGoalWorkItem(goal({ status: "paused" }), NOW_MS),
    /active portfolio goal/i,
  );
  assert.throws(
    () => buildGoalWorkItem(goal({ origin: "user" }), NOW_MS),
    /goal portfolio invalid/i,
  );
  assert.throws(
    () => buildGoalWorkItem(goal({ cost_budget: { currency: "USD", minor_units: "-1" } }), NOW_MS),
    /goal portfolio invalid/i,
  );
});
