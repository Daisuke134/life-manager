"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");

const { decidePromotionGate } = require("./gate.js");
const { EVAL_SCHEMA_VERSION } = require("./records.js");

const HASH = "a".repeat(64);
const NOW = "2026-09-15T00:00:00.000Z";

function evaluationCase(caseId, split) {
  return {
    schema_version: EVAL_SCHEMA_VERSION,
    record_type: "eval_case",
    case_id: caseId,
    recipe_id: "recipe.example",
    recipe_version: "v1",
    split,
    category: "regression",
    fixture_ref: `fixture://eval/${caseId}`,
    input_sha256: HASH,
    expected: { lifecycle: "completed", effect: "verified", readback: "present", safety: "pass" },
  };
}

function run(overrides = {}) {
  return {
    schema_version: EVAL_SCHEMA_VERSION,
    record_type: "eval_run",
    run_id: "run-1",
    case_set_sha256: HASH,
    candidate_sha256: "b".repeat(64),
    baseline_sha256: "c".repeat(64),
    model: "gpt-6-astra",
    prompt_sha256: HASH,
    tool_fixture_sha256: HASH,
    seed: 1,
    started_at: NOW,
    finished_at: "2026-09-15T00:00:01.000Z",
    status: "completed",
    score_ids: ["score-tuning", "score-heldout"],
    trace_refs: ["trace://run-1"],
    error: null,
    ...overrides,
  };
}

function score(scoreId, caseId, overrides = {}) {
  return {
    schema_version: EVAL_SCHEMA_VERSION,
    record_type: "eval_score",
    score_id: scoreId,
    run_id: "run-1",
    case_id: caseId,
    outcome: "passed",
    score: 1,
    latency_ms: 80,
    cost_minor: 5,
    safety: "pass",
    evidence_refs: [`evidence://run-1/${caseId}`],
    error: null,
    ...overrides,
  };
}

function input(overrides = {}) {
  return {
    run: run(),
    cases: [evaluationCase("case-tuning", "tuning"), evaluationCase("case-heldout", "held_out")],
    scores: [score("score-tuning", "case-tuning"), score("score-heldout", "case-heldout")],
    baseline: { held_out_score: 0.8, cost_minor: 10, latency_ms: 100, safety: "pass" },
    liveEvidence: { official_readback: "verified", replay_zero: true },
    rollback_ref: "rollback://run-1",
    ...overrides,
  };
}

test("EVAL-03 passes only when held-out, safety, cost, latency, live evidence, and rollback clear", () => {
  const result = decidePromotionGate(input());
  assert.equal(result.promote, true);
  assert.equal(result.gate.decision, "pass");
  assert.deepEqual(result.gate.checks, {
    held_out: "pass", safety: "pass", cost: "pass", latency: "pass", live_evidence: "pass",
  });
});

test("held-out regression, safety failure, cost/latency regression, or missing live proof blocks", () => {
  const scenarios = [
    { scores: [score("score-tuning", "case-tuning"), score("score-heldout", "case-heldout", { outcome: "failed", score: 0 })] },
    { scores: [score("score-tuning", "case-tuning", { safety: "block" }), score("score-heldout", "case-heldout")] },
    { scores: [score("score-tuning", "case-tuning", { cost_minor: 13 }), score("score-heldout", "case-heldout", { cost_minor: 13 })] },
    { scores: [score("score-tuning", "case-tuning", { latency_ms: 130 }), score("score-heldout", "case-heldout", { latency_ms: 130 })] },
    { liveEvidence: { official_readback: "unknown", replay_zero: false } },
  ];
  for (const scenario of scenarios) {
    const result = decidePromotionGate(input(scenario));
    assert.equal(result.promote, false);
    assert.equal(result.gate.decision, "block");
  }
});

test("missing held-out coverage, score identity mismatch, and absent rollback fail closed", () => {
  assert.equal(decidePromotionGate(input({ cases: [evaluationCase("case-tuning", "tuning")] })).promote, false);
  assert.equal(decidePromotionGate(input({ scores: [score("score-tuning", "case-tuning"), score("score-other", "case-other")] })).promote, false);
  assert.equal(decidePromotionGate(input({ rollback_ref: null })).promote, false);
  assert.throws(() => decidePromotionGate(input({ baseline: { held_out_score: 2, cost_minor: 10, latency_ms: 100, safety: "pass" } })), /baseline/i);
});
