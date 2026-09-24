"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  ACTOR_CLASSES,
  COST_CATEGORIES,
  COUNTERPARTY_CLASSES,
  CREDENTIAL_CLASSES,
  EVENT_KINDS,
  REVENUE_CLASSES,
  TRACKS,
  validateAttribution,
  validateAutonomyEvent,
  validateCase,
  validateCostCoverage,
  validateEpisode,
  validateRun,
  validateScore,
} = require("./records.js");

const HASH_A = "a".repeat(64);
const HASH_B = "b".repeat(64);
const HASH_C = "c".repeat(64);
const HASH_D = "d".repeat(64);
const RECORD_ID = `financial:${"1".repeat(64)}`;

function episode(overrides = {}) {
  return {
    schema_version: 1,
    record_type: "economic_autonomy_episode",
    episode_id: "episode-agent-native-1",
    subject_id: "tenant-a",
    track: "agent_native",
    currency: "USDC",
    period_start: "2026-09-01T00:00:00.000Z",
    period_end: "2026-10-01T00:00:00.000Z",
    starting_capital_minor: 500000000,
    spend_cap_minor: 100000000,
    release_sha256: HASH_A,
    model: "gpt-6-astra",
    toolchain_sha256: HASH_B,
    policy_sha256: HASH_C,
    ...overrides,
  };
}

function revenueAttribution(overrides = {}) {
  return {
    schema_version: 1,
    record_type: "economic_attribution",
    record_id: RECORD_ID,
    loop_id: "agent-economy-x402-sell",
    counterparty_class: "external_customer",
    counterparty_sha256: HASH_D,
    revenue_class: "recurring_usage",
    cost_category: null,
    evidence_refs: ["x402://receipt/abc"],
    ...overrides,
  };
}

function costAttribution(overrides = {}) {
  return revenueAttribution({
    counterparty_class: null,
    counterparty_sha256: null,
    revenue_class: null,
    cost_category: "model",
    ...overrides,
  });
}

function autonomyEvent(overrides = {}) {
  return {
    schema_version: 1,
    record_type: "economic_autonomy_event",
    event_id: "event-1",
    episode_id: "episode-agent-native-1",
    event_kind: "external_effect",
    actor_class: "life_manager",
    credential_class: "agent_owned",
    occurred_at: "2026-09-02T00:00:00.000Z",
    duration_seconds: 0,
    effect: "verified",
    readback: "present",
    duplicate: false,
    evidence_refs: ["x402://receipt/abc"],
    ...overrides,
  };
}

function coverage(overrides = {}) {
  const categories = Object.fromEntries(COST_CATEGORIES.map((category) => [category, {
    status: "not_applicable",
    record_ids: [],
    evidence_refs: [`policy://episode/${category}`],
  }]));
  categories.model = {
    status: "records",
    record_ids: [RECORD_ID],
    evidence_refs: [],
  };
  return {
    schema_version: 1,
    record_type: "economic_cost_coverage",
    episode_id: "episode-agent-native-1",
    categories,
    ...overrides,
  };
}

function caseRecord(overrides = {}) {
  return {
    schema_version: 1,
    record_type: "economic_autonomy_case",
    case_id: "case-agent-native-1",
    split: "held_out",
    category: "regression",
    fixture_ref: "fixture://economic-autonomy/agent-native-1",
    input_sha256: HASH_A,
    expected: {
      eligible: true,
      settled_net_profit_minor: 9685000,
      recurring_revenue_minor: 10000000,
      reason_codes: [],
    },
    ...overrides,
  };
}

function runRecord(overrides = {}) {
  return {
    schema_version: 1,
    record_type: "economic_autonomy_run",
    run_id: "run-1",
    case_set_sha256: HASH_A,
    release_sha256: HASH_B,
    model: "gpt-6-astra",
    toolchain_sha256: HASH_C,
    started_at: "2026-09-24T00:00:00.000Z",
    finished_at: "2026-09-24T00:00:01.000Z",
    status: "completed",
    score_ids: ["score-1"],
    trace_refs: ["trace://economic-autonomy/run-1"],
    error: null,
    ...overrides,
  };
}

function scoreRecord(overrides = {}) {
  return {
    schema_version: 1,
    record_type: "economic_autonomy_score",
    score_id: "score-1",
    run_id: "run-1",
    case_id: "case-agent-native-1",
    episode_id: "episode-agent-native-1",
    eligible: true,
    reason_codes: [],
    currency: "USDC",
    settled_customer_revenue_minor: 10000000,
    recurring_revenue_minor: 10000000,
    total_cost_minor: 315000,
    settled_net_profit_minor: 9685000,
    contribution_margin_bps: 9685,
    self_funded: true,
    human_intervention_count: 0,
    human_intervention_seconds: 0,
    external_ai_intervention_count: 0,
    credential_classes: ["agent_owned"],
    effect_unknown_count: 0,
    duplicate_effect_count: 0,
    evidence_refs: ["x402://receipt/abc"],
    ...overrides,
  };
}

test("LM-EAB exports the closed v1 vocabularies and freezes valid records", () => {
  assert.deepEqual(TRACKS, ["agent_native", "one_shot_onboarding", "simulation"]);
  assert.equal(REVENUE_CLASSES.includes("fundraising"), true);
  assert.equal(COST_CATEGORIES.length, 13);
  assert.deepEqual(COUNTERPARTY_CLASSES, ["external_customer", "self", "related", "unknown"]);
  assert.equal(ACTOR_CLASSES.includes("external_ai"), true);
  assert.equal(CREDENTIAL_CLASSES.includes("recurring_user"), true);
  assert.equal(EVENT_KINDS.includes("policy_violation"), true);

  for (const value of [
    validateEpisode(episode()),
    validateAttribution(revenueAttribution()),
    validateAttribution(costAttribution()),
    validateAutonomyEvent(autonomyEvent()),
    validateCostCoverage(coverage()),
    validateCase(caseRecord()),
    validateRun(runRecord()),
    validateScore(scoreRecord()),
  ]) assert.equal(Object.isFrozen(value), true);
});

test("episode rejects extra keys, invalid tracks, unsafe amounts, and non-positive periods", () => {
  assert.throws(() => validateEpisode({ ...episode(), extra: true }), /episode/i);
  assert.throws(() => validateEpisode(episode({ track: "human_operated" })), /track/i);
  assert.throws(() => validateEpisode(episode({ spend_cap_minor: Number.MAX_SAFE_INTEGER + 1 })), /spend/i);
  assert.throws(() => validateEpisode(episode({ period_end: episode().period_start })), /period/i);
});

test("attribution requires exactly one revenue or cost classification", () => {
  assert.throws(() => validateAttribution(revenueAttribution({ cost_category: "model" })), /classification/i);
  assert.throws(() => validateAttribution(revenueAttribution({ counterparty_sha256: null })), /counterparty/i);
  assert.throws(() => validateAttribution(costAttribution({ counterparty_class: "external_customer" })), /classification|counterparty/i);
  assert.throws(() => validateAttribution(costAttribution({ evidence_refs: ["https://user:pass@example.com"] })), /evidence|ref/i);
});

test("autonomy events enforce closed actor, credential, effect, and readback vocabularies", () => {
  assert.throws(() => validateAutonomyEvent(autonomyEvent({ actor_class: "codex" })), /actor/i);
  assert.throws(() => validateAutonomyEvent(autonomyEvent({ credential_class: "borrowed" })), /credential/i);
  assert.throws(() => validateAutonomyEvent(autonomyEvent({ effect: "assumed" })), /effect/i);
  assert.throws(() => validateAutonomyEvent(autonomyEvent({ readback: "maybe" })), /readback/i);
  assert.throws(() => validateAutonomyEvent(autonomyEvent({ duration_seconds: -1 })), /duration/i);
});

test("cost coverage requires every category exactly once and evidence for zero or not-applicable claims", () => {
  const missing = coverage();
  delete missing.categories.browser;
  assert.throws(() => validateCostCoverage(missing), /categor/i);

  const noEvidence = coverage();
  noEvidence.categories.browser = { status: "zero_cost", record_ids: [], evidence_refs: [] };
  assert.throws(() => validateCostCoverage(noEvidence), /evidence|coverage/i);

  const duplicate = coverage();
  duplicate.categories.model.record_ids = [RECORD_ID, RECORD_ID];
  assert.throws(() => validateCostCoverage(duplicate), /duplicate/i);
});

test("case and run records preserve held-out identity and terminal timing", () => {
  assert.throws(() => validateCase(caseRecord({ split: "live" })), /split/i);
  assert.throws(() => validateCase(caseRecord({ input_sha256: "short" })), /hash|sha/i);
  assert.throws(() => validateRun(runRecord({ finished_at: runRecord().started_at })), /timing|finish/i);
  assert.throws(() => validateRun(runRecord({ status: "failed", error: null })), /error/i);
  assert.throws(() => validateRun(runRecord({ status: "completed", error: "unexpected" })), /error/i);
});

test("score accepts signed economic outcomes but rejects unsorted or duplicate reason codes", () => {
  const loss = validateScore(scoreRecord({
    eligible: false,
    reason_codes: ["policy_violation"],
    settled_net_profit_minor: -500,
    contribution_margin_bps: -100,
    self_funded: false,
  }));
  assert.equal(loss.settled_net_profit_minor, -500);
  assert.equal(validateScore(scoreRecord({ contribution_margin_bps: null })).contribution_margin_bps, null);
  assert.throws(() => validateScore(scoreRecord({ reason_codes: ["z_reason", "a_reason"] })), /reason/i);
  assert.throws(() => validateScore(scoreRecord({ reason_codes: ["same", "same"] })), /reason/i);
  assert.throws(() => validateScore(scoreRecord({ credential_classes: ["unknown"] })), /credential/i);
});
