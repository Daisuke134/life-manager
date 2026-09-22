"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  goalContextReference,
  goalSynthesisRefs,
  validateGoalContext,
} = require("./goal-context.js");

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

test("goal context is exact tenant-bound reference-only and produces synthesis refs", () => {
  const value = validateGoalContext(context(), "tenant-a");
  assert.deepEqual(value, context());
  assert.equal(Object.isFrozen(value), true);
  for (const refs of [value.fact_refs, value.account_refs, value.consent_refs, value.boundary_refs]) {
    assert.equal(Object.isFrozen(refs), true);
  }
  assert.equal(goalContextReference(value), "goal-context://tenant-a?revision=1");
  const synthesis = goalSynthesisRefs(value);
  assert.deepEqual(synthesis, {
    factRefs: ["fact://tenant-a/income"],
    evidenceRefs: [
      "policy://life-manager/J4",
      "account://tenant-a/calendar",
      "consent://tenant-a/calendar-read",
    ],
    boundaryRefs: ["boundary://tenant-a/no-owner-spend"],
  });
  assert.equal(Object.isFrozen(synthesis), true);
  assert.equal(Object.isFrozen(synthesis.evidenceRefs), true);
});

test("empty one-time inputs still retain the standing Life Manager policy", () => {
  const value = validateGoalContext(context({
    fact_refs: [], account_refs: [], consent_refs: [], boundary_refs: [],
  }), "tenant-a");
  assert.deepEqual(goalSynthesisRefs(value), {
    factRefs: [], evidenceRefs: ["policy://life-manager/J4"], boundaryRefs: [],
  });
});

test("goal context rejects shape identity reference and size drift", () => {
  const extra = { ...context(), raw_goal: "Make money" };
  const tooMany = Array.from({ length: 101 }, (_, index) => `fact://tenant-a/f-${index}`);
  const cases = [
    [context({ schema_version: "other" }), "tenant-a"],
    [context({ tenant_id: "tenant-b" }), "tenant-a"],
    [context({ revision: 0 }), "tenant-a"],
    [context({ revision: 101 }), "tenant-a"],
    [extra, "tenant-a"],
    [context({ fact_refs: ["annual salary 100"] }), "tenant-a"],
    [context({ fact_refs: ["fact://tenant-a/income secret"] }), "tenant-a"],
    [context({ fact_refs: ["credential://tenant-a/password"] }), "tenant-a"],
    [context({ fact_refs: ["fact://tenant-b/income"] }), "tenant-a"],
    [context({ account_refs: ["fact://tenant-a/calendar"] }), "tenant-a"],
    [context({ consent_refs: ["consent://tenant-a/calendar-read#token"] }), "tenant-a"],
    [context({ boundary_refs: ["boundary://tenant-a"] }), "tenant-a"],
    [context({ fact_refs: tooMany }), "tenant-a"],
    [context({ fact_refs: ["fact://tenant-a/income", "fact://tenant-a/income"] }), "tenant-a"],
    [context({ account_refs: ["account://tenant-a/shared"], consent_refs: ["account://tenant-a/shared"] }), "tenant-a"],
  ];
  cases.forEach(([value, tenantId], index) => {
    assert.throws(() => validateGoalContext(value, tenantId), /goal context invalid/i, `case ${index}`);
  });
});
