"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  activePortfolioGoal,
  goalReference,
  synthesizeGoalPortfolio,
  validateGoalPortfolio,
} = require("./goal-portfolio.js");

const GENERATED_AT = "2026-09-22T12:00:00.000Z";
const NOW_MS = Date.parse(GENERATED_AT);
const AUTHORIZED_REFS = [
  "policy://life-manager/J4",
  "fact://tenant-a/income",
  "boundary://tenant-a/no-spend",
];

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

function goal(overrides = {}) {
  return {
    ...candidate(),
    tenant_id: "tenant-a",
    revision: 1,
    origin: "life_manager",
    ...overrides,
  };
}

function portfolio(overrides = {}) {
  return {
    schema_version: "life-manager.goal-portfolio.v1",
    tenant_id: "tenant-a",
    revision: 1,
    generated_at: GENERATED_AT,
    origin: "life_manager",
    goals: [goal()],
    ...overrides,
  };
}

test("missing user-authored goal synthesizes a Life Manager-owned portfolio", async () => {
  const calls = [];
  const generated = await synthesizeGoalPortfolio({
    tenantId: "tenant-a",
    revision: 1,
    generatedAt: GENERATED_AT,
    factRefs: ["fact://tenant-a/income"],
    evidenceRefs: ["policy://life-manager/J4"],
    boundaryRefs: ["boundary://tenant-a/no-spend"],
  }, {
    async generate(input) {
      calls.push(input);
      return { goals: [candidate()] };
    },
  });

  assert.equal(calls.length, 1);
  assert.equal(Object.hasOwn(calls[0], "user_goal"), false);
  assert.equal(calls[0].policy.authority, "life_manager");
  assert.match(calls[0].instruction, /Never ask the person/u);
  assert.equal(calls[0].examples.length, 2);
  assert.deepEqual(calls[0].fact_refs, ["fact://tenant-a/income"]);
  assert.deepEqual(calls[0].evidence_refs, ["policy://life-manager/J4"]);
  assert.deepEqual(calls[0].boundary_refs, ["boundary://tenant-a/no-spend"]);
  assert.deepEqual(generated, portfolio());
  assert.equal(Object.isFrozen(generated), true);
  assert.equal(Object.isFrozen(generated.goals[0]), true);
  assert.equal(goalReference(generated.goals[0]),
    "goal-portfolio://tenant-a/financial-continuity?revision=1");
});

test("portfolio validation rejects identity, schema, provenance, budget, expiry, and size drift", () => {
  const extraGoal = { ...goal(), unexpected: true };
  const duplicate = goal({ statement: "A second statement with the same id" });
  const cases = [
    portfolio({ tenant_id: "tenant-b" }),
    portfolio({ goals: [goal({ tenant_id: "tenant-b" })] }),
    portfolio({ goals: [extraGoal] }),
    portfolio({ goals: [goal(), duplicate] }),
    portfolio({ goals: [goal({ evidence_refs: ["mail://tenant-a/unapproved"] })] }),
    portfolio({ goals: [goal({ cost_budget: { currency: "USD", minor_units: "-1" } })] }),
    portfolio({ goals: [goal({ cost_budget: { currency: "USD", minor_units: "1.5" } })] }),
    portfolio({ goals: [goal({ confidence: 0 })] }),
    portfolio({ goals: [goal({ confidence: 1.1 })] }),
    portfolio({ goals: [goal({ expires_at: "tomorrow" })] }),
    portfolio({ goals: [] }),
    portfolio({ goals: [
      goal({ goal_id: "g1" }), goal({ goal_id: "g2" }),
      goal({ goal_id: "g3" }), goal({ goal_id: "g4" }),
    ] }),
  ];

  cases.forEach((value, index) => {
    assert.throws(() => validateGoalPortfolio(value, {
      tenantId: "tenant-a",
      authorizedRefs: AUTHORIZED_REFS,
    }), /goal portfolio invalid/u, `case ${index}`);
  });
});

test("active goal selection skips expired goals and preserves model priority", () => {
  const value = validateGoalPortfolio(portfolio({ goals: [
    goal({ goal_id: "expired", expires_at: "2026-09-22T11:59:59.000Z" }),
    goal({ goal_id: "first-active", evidence_refs: ["fact://tenant-a/income"] }),
    goal({ goal_id: "second-active", evidence_refs: ["boundary://tenant-a/no-spend"] }),
  ] }), { tenantId: "tenant-a", authorizedRefs: AUTHORIZED_REFS });

  assert.equal(activePortfolioGoal(value, NOW_MS).goal_id, "first-active");
  assert.equal(goalReference(activePortfolioGoal(value, NOW_MS)),
    "goal-portfolio://tenant-a/first-active?revision=1");
});
