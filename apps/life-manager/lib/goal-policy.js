"use strict";

const fs = require("node:fs");
const path = require("node:path");

const DEFAULT_POLICY = path.resolve(__dirname, "../config/goal-policy.json");
const POLICY_KEYS = Object.freeze([
  "authority",
  "human_gates",
  "human_inputs",
  "objective_order",
  "requires_user_authored_goal",
  "schema_version",
]);
const HUMAN_INPUTS = Object.freeze(["facts", "accounts", "credentials", "consent", "boundaries"]);
const OBJECTIVE_ORDER = Object.freeze(["safety", "continuity", "financial_surplus", "marginal_outcome"]);

const GOAL_SYNTHESIS_INSTRUCTION = [
  "Create and prioritize a small Goal Portfolio from the authorized facts, evidence, consent, and boundaries supplied by Life Manager.",
  "Never ask the person to invent, choose, or restate a goal.",
  "Preserve safety, legality, identity, and declared boundaries; then continuity, verified financial surplus, and the highest evidence-backed marginal outcome.",
  "Return goals grounded only in the supplied evidence references. Mark an exact typed human gate only when autonomous continuation is impossible.",
].join(" ");

function deepFreeze(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  for (const child of Object.values(value)) deepFreeze(child);
  return Object.freeze(value);
}

const GOAL_SYNTHESIS_EXAMPLES = deepFreeze([
  {
    input: {
      fact_refs: [],
      evidence_refs: ["policy://life-manager/J4"],
      boundary_refs: [],
    },
    output: {
      goals: [{
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
      }],
    },
  },
  {
    input: {
      fact_refs: ["fact://tenant-a/income-shortfall"],
      evidence_refs: ["ledger://tenant-a/financial-snapshot"],
      boundary_refs: ["boundary://tenant-a/no-owner-spend"],
    },
    output: {
      goals: [{
        goal_id: "close-income-gap",
        statement: "Find the highest-value lawful income action that needs no owner spending",
        expected_outcome: "Verified attributable income without owner-funded spend",
        confidence: 0.9,
        evidence_refs: ["ledger://tenant-a/financial-snapshot", "boundary://tenant-a/no-owner-spend"],
        cost_budget: { currency: "USD", minor_units: "0" },
        risk_budget: "low",
        dependencies: [],
        expires_at: null,
        success_receipt: null,
        status: "active",
      }],
    },
  },
]);

function sameArray(actual, expected) {
  return Array.isArray(actual)
    && actual.length === expected.length
    && actual.every((value, index) => value === expected[index]);
}

function invalid() {
  throw new Error("goal policy invalid");
}

function readGoalPolicy(file = DEFAULT_POLICY) {
  let value;
  try {
    value = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return invalid();
  }
  if (!value || typeof value !== "object" || Array.isArray(value)
    || !sameArray(Object.keys(value).sort(), POLICY_KEYS)
    || value.schema_version !== "life-manager.goal-policy.v1"
    || value.authority !== "life_manager"
    || value.requires_user_authored_goal !== false
    || !sameArray(value.human_inputs, HUMAN_INPUTS)
    || !sameArray(value.objective_order, OBJECTIVE_ORDER)
    || !Array.isArray(value.human_gates) || value.human_gates.length === 0
    || value.human_gates.some((gate) => typeof gate !== "string" || !gate.trim() || gate !== gate.trim())
    || new Set(value.human_gates).size !== value.human_gates.length) {
    return invalid();
  }
  return deepFreeze(value);
}

module.exports = {
  GOAL_SYNTHESIS_EXAMPLES,
  GOAL_SYNTHESIS_INSTRUCTION,
  readGoalPolicy,
};
