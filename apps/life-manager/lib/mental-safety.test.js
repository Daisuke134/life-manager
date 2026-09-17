"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { evaluateMentalSafety, SAFETY_VERDICTS } = require("./mental-safety.js");

test("only an explicit trusted imminent-self-harm verdict interrupts routine MENTAL", () => {
  assert.deepEqual(evaluateMentalSafety({ verdict: "none" }), { decision: "continue" });
  assert.deepEqual(evaluateMentalSafety({ verdict: "unknown" }), { decision: "continue" });
  assert.deepEqual(evaluateMentalSafety({ verdict: "imminent_self_harm" }), {
    decision: "safety_route_required", reason: "explicit-imminent-self-harm",
  });
  assert.ok(SAFETY_VERDICTS.includes("imminent_self_harm"));
});

test("ordinary disappointment is never a safety verdict", () => {
  assert.deepEqual(evaluateMentalSafety({ verdict: "job_rejection" }), { decision: "continue" });
  assert.deepEqual(evaluateMentalSafety({ verdict: "calendar_gap" }), { decision: "continue" });
  assert.deepEqual(evaluateMentalSafety({}), { decision: "continue" });
});
