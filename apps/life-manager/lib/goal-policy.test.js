"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  GOAL_SYNTHESIS_EXAMPLES,
  GOAL_SYNTHESIS_INSTRUCTION,
  readGoalPolicy,
} = require("./goal-policy.js");

test("Life Manager is the only goal authority and user-authored goals are optional", () => {
  const policy = readGoalPolicy();

  assert.equal(policy.schema_version, "life-manager.goal-policy.v1");
  assert.equal(policy.authority, "life_manager");
  assert.equal(policy.requires_user_authored_goal, false);
  assert.deepEqual(policy.human_inputs, ["facts", "accounts", "credentials", "consent", "boundaries"]);
  assert.deepEqual(policy.objective_order, ["safety", "continuity", "financial_surplus", "marginal_outcome"]);
  assert.match(GOAL_SYNTHESIS_INSTRUCTION, /Never ask the person to invent, choose, or restate a goal/u);
  assert.equal(GOAL_SYNTHESIS_EXAMPLES.length, 2);
  assert.equal(Object.isFrozen(GOAL_SYNTHESIS_EXAMPLES), true);
});

test("unknown policy fields and another authority fail closed", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-goal-policy-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const file = path.join(root, "policy.json");
  fs.writeFileSync(file, JSON.stringify({ ...readGoalPolicy(), authority: "user", extra: true }));

  assert.throws(() => readGoalPolicy(file), /goal policy invalid/u);
});

test("required goals, reordered objectives, and malformed human gates fail closed", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-goal-policy-invalid-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const canonical = readGoalPolicy();
  const invalidPolicies = [
    { ...canonical, schema_version: "life-manager.goal-policy.v2" },
    { ...canonical, requires_user_authored_goal: true },
    { ...canonical, human_inputs: ["accounts", "facts", "credentials", "consent", "boundaries"] },
    { ...canonical, objective_order: ["continuity", "safety", "financial_surplus", "marginal_outcome"] },
    { ...canonical, human_gates: [] },
    { ...canonical, human_gates: ["kyc", "kyc"] },
    { ...canonical, human_gates: [" kyc"] },
  ];

  invalidPolicies.forEach((policy, index) => {
    const file = path.join(root, `policy-${index}.json`);
    fs.writeFileSync(file, JSON.stringify(policy));
    assert.throws(() => readGoalPolicy(file), /goal policy invalid/u, `case ${index}`);
  });
});
