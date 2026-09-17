"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");

const {
  EVAL_SCHEMA_VERSION,
  SPLITS,
  CATEGORIES,
  validateCase,
  validateRun,
  validateScore,
  validateGate,
  validateEvalRecord,
} = require("./records.js");

const HASH = "a".repeat(64);
const NOW = "2026-09-15T00:00:00.000Z";

function evaluationCase(overrides = {}) {
  return {
    schema_version: EVAL_SCHEMA_VERSION,
    record_type: "eval_case",
    case_id: "case-1",
    recipe_id: "lancers.application",
    recipe_version: "v1",
    split: "tuning",
    category: "canonical",
    fixture_ref: "fixture://lancers/case-1",
    input_sha256: HASH,
    expected: {
      lifecycle: "completed",
      effect: "verified",
      readback: "present",
      safety: "pass",
    },
    ...overrides,
  };
}

function run(overrides = {}) {
  return {
    schema_version: EVAL_SCHEMA_VERSION,
    record_type: "eval_run",
    run_id: "run-1",
    case_set_sha256: HASH,
    candidate_sha256: HASH,
    baseline_sha256: HASH,
    model: "gpt-6-astra",
    prompt_sha256: HASH,
    tool_fixture_sha256: HASH,
    seed: 7,
    started_at: NOW,
    finished_at: "2026-09-15T00:00:01.000Z",
    status: "completed",
    score_ids: ["score-1"],
    trace_refs: ["trace://run-1"],
    error: null,
    ...overrides,
  };
}

function score(overrides = {}) {
  return {
    schema_version: EVAL_SCHEMA_VERSION,
    record_type: "eval_score",
    score_id: "score-1",
    run_id: "run-1",
    case_id: "case-1",
    outcome: "passed",
    score: 1,
    latency_ms: 120,
    cost_minor: 0,
    safety: "pass",
    evidence_refs: ["evidence://run-1/case-1"],
    error: null,
    ...overrides,
  };
}

function gate(overrides = {}) {
  return {
    schema_version: EVAL_SCHEMA_VERSION,
    record_type: "eval_gate",
    gate_id: "gate-1",
    run_id: "run-1",
    candidate_sha256: HASH,
    baseline_sha256: HASH,
    decision: "block",
    checks: {
      held_out: "block",
      safety: "pass",
      cost: "pass",
      latency: "pass",
      live_evidence: "block",
    },
    reasons: ["held-out cases are not yet evaluated"],
    rollback_ref: null,
    ...overrides,
  };
}

test("EVAL-01 exposes the versioned case/run/score/gate record types", () => {
  assert.equal(EVAL_SCHEMA_VERSION, 1);
  assert.deepEqual(SPLITS, ["tuning", "held_out"]);
  assert.deepEqual(CATEGORIES, ["canonical", "boundary", "adversarial", "regression"]);
  assert.deepEqual(validateCase(evaluationCase()), evaluationCase());
  assert.deepEqual(validateRun(run()), run());
  assert.deepEqual(validateScore(score()), score());
  assert.deepEqual(validateGate(gate()), gate());
});

test("records reject missing hashes, invalid split/category, extra keys, and secret-like refs", () => {
  assert.throws(() => validateCase(evaluationCase({ input_sha256: "short" })), /sha|hash/i);
  assert.throws(() => validateCase(evaluationCase({ split: "live" })), /split/i);
  assert.throws(() => validateCase(evaluationCase({ category: "random" })), /category/i);
  assert.throws(() => validateCase({ ...evaluationCase(), password: "secret" }), /case/i);
  assert.throws(() => validateRun(run({ candidate_sha256: "short" })), /sha|hash/i);
  assert.throws(() => validateRun(run({ trace_refs: ["https://user:pass@example.com"] })), /ref/i);
});

test("run and score records keep timing, cost, safety, and evidence bounded", () => {
  assert.throws(() => validateRun(run({ finished_at: NOW })), /timing|time|finish/i);
  assert.throws(() => validateRun(run({ status: "running", finished_at: run().finished_at })), /running|finish/i);
  assert.throws(() => validateScore(score({ score: 1.1 })), /score/i);
  assert.throws(() => validateScore(score({ latency_ms: -1 })), /latency/i);
  assert.throws(() => validateScore(score({ evidence_refs: [] })), /evidence/i);
  assert.throws(() => validateScore(score({ safety: "unknown" })), /safety/i);
});

test("dispatch validation is strict and returns frozen records", () => {
  for (const record of [evaluationCase(), run(), score(), gate()]) {
    const checked = validateEvalRecord(record);
    assert.equal(Object.isFrozen(checked), true);
    assert.equal(checked.record_type, record.record_type);
  }
  assert.throws(() => validateEvalRecord({ ...gate(), record_type: "unknown" }), /record_type/i);
});
