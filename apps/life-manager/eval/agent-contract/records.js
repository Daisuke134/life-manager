"use strict";

// Versioned, append-only evaluation records.  These records describe evidence
// and decisions; they never carry credentials, provider sessions, or authority
// to change production.

const EVAL_SCHEMA_VERSION = 1;
const SPLITS = Object.freeze(["tuning", "held_out"]);
const CATEGORIES = Object.freeze(["canonical", "boundary", "adversarial", "regression"]);
const LIFECYCLES = Object.freeze([
  "queued", "running", "retry_scheduled", "deferred", "human_wait",
  "completed", "failed", "blocked",
]);
const EFFECTS = Object.freeze(["not_applicable", "planned", "started", "verified", "failed", "unknown"]);
const READBACKS = Object.freeze(["not_applicable", "absent", "present", "unknown"]);
const RECORD_TYPES = Object.freeze(["eval_case", "eval_run", "eval_score", "eval_gate"]);
const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const HASH = /^[a-f0-9]{64}$/;
const REF = /^[a-z][a-z0-9+.-]*:\/\/[A-Za-z0-9._:/?#-]{1,512}$/i;
const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$/;

function invalid(label) {
  throw new Error(`EvalRecord ${label} invalid`);
}

function exactKeys(value, expected, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid(label);
  const actual = Object.keys(value).sort();
  const keys = [...expected].sort();
  if (actual.length !== keys.length || actual.some((key, index) => key !== keys[index])) invalid(label);
}

function id(value, label) {
  if (typeof value !== "string" || !ID.test(value)) invalid(label);
  return value;
}

function hash(value, label) {
  if (typeof value !== "string" || !HASH.test(value)) invalid(label);
  return value;
}

function ref(value, label) {
  if (typeof value !== "string" || !REF.test(value) || value.includes("@")) invalid(label);
  return value;
}

function token(value, label) {
  if (typeof value !== "string" || !TOKEN.test(value)) invalid(label);
  return value;
}

function instant(value, label) {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))
    || !/[zZ]|[+-]\d\d:\d\d$/.test(value)) invalid(label);
  return new Date(value).toISOString();
}

function boundedText(value, label, max, allowEmpty = false) {
  if (typeof value !== "string" || value.length > max || (!allowEmpty && value.trim() === "")
    || /\b(?:password|cookie|api[_ -]?key|access[_ -]?token)\b/i.test(value)) invalid(label);
  return value;
}

function boundedRefs(value, label, { min = 0, max = 64 } = {}) {
  if (!Array.isArray(value) || value.length < min || value.length > max) invalid(label);
  const refs = value.map((item) => ref(item, label));
  if (new Set(refs).size !== refs.length) invalid(label);
  return Object.freeze(refs);
}

function validateExpected(value) {
  exactKeys(value, ["lifecycle", "effect", "readback", "safety"], "expected");
  if (!LIFECYCLES.includes(value.lifecycle)) invalid("expected lifecycle");
  if (!EFFECTS.includes(value.effect)) invalid("expected effect");
  if (!READBACKS.includes(value.readback)) invalid("expected readback");
  if (!["pass", "block"].includes(value.safety)) invalid("expected safety");
  return Object.freeze({ ...value });
}

function validateCase(value) {
  exactKeys(value, [
    "schema_version", "record_type", "case_id", "recipe_id", "recipe_version",
    "split", "category", "fixture_ref", "input_sha256", "expected",
  ], "case");
  if (value.schema_version !== EVAL_SCHEMA_VERSION || value.record_type !== "eval_case") invalid("case version");
  id(value.case_id, "case_id");
  token(value.recipe_id, "recipe_id");
  token(value.recipe_version, "recipe_version");
  if (!SPLITS.includes(value.split)) invalid("split");
  if (!CATEGORIES.includes(value.category)) invalid("category");
  ref(value.fixture_ref, "fixture_ref");
  hash(value.input_sha256, "input_sha256");
  const expected = validateExpected(value.expected);
  return Object.freeze({ ...value, expected });
}

function validateRun(value) {
  exactKeys(value, [
    "schema_version", "record_type", "run_id", "case_set_sha256", "candidate_sha256",
    "baseline_sha256", "model", "prompt_sha256", "tool_fixture_sha256", "seed",
    "started_at", "finished_at", "status", "score_ids", "trace_refs", "error",
  ], "run");
  if (value.schema_version !== EVAL_SCHEMA_VERSION || value.record_type !== "eval_run") invalid("run version");
  id(value.run_id, "run_id");
  hash(value.case_set_sha256, "case_set_sha256");
  hash(value.candidate_sha256, "candidate_sha256");
  hash(value.baseline_sha256, "baseline_sha256");
  token(value.model, "model");
  hash(value.prompt_sha256, "prompt_sha256");
  hash(value.tool_fixture_sha256, "tool_fixture_sha256");
  if (!Number.isSafeInteger(value.seed) || value.seed < 0 || value.seed > 0xffffffff) invalid("seed");
  const startedAt = instant(value.started_at, "started_at");
  const finishedAt = value.finished_at === null ? null : instant(value.finished_at, "finished_at");
  if (!["running", "completed", "failed", "blocked"].includes(value.status)) invalid("status");
  if (value.status === "running" ? finishedAt !== null : finishedAt === null) invalid("run finish");
  if (finishedAt !== null && Date.parse(finishedAt) <= Date.parse(startedAt)) invalid("run timing");
  if (!Array.isArray(value.score_ids) || value.score_ids.length > 10_000) invalid("score_ids");
  const scoreIds = value.score_ids.map((item) => id(item, "score_id"));
  if (new Set(scoreIds).size !== scoreIds.length) invalid("score_ids");
  const traceRefs = boundedRefs(value.trace_refs, "trace_refs", { min: 1, max: 64 });
  const error = value.error === null ? null : boundedText(value.error, "error", 2048);
  return Object.freeze({
    ...value,
    started_at: startedAt,
    finished_at: finishedAt,
    score_ids: Object.freeze(scoreIds),
    trace_refs: traceRefs,
    error,
  });
}

function validateScore(value) {
  exactKeys(value, [
    "schema_version", "record_type", "score_id", "run_id", "case_id", "outcome",
    "score", "latency_ms", "cost_minor", "safety", "evidence_refs", "error",
  ], "score");
  if (value.schema_version !== EVAL_SCHEMA_VERSION || value.record_type !== "eval_score") invalid("score version");
  id(value.score_id, "score_id");
  id(value.run_id, "run_id");
  id(value.case_id, "case_id");
  if (!["passed", "failed", "blocked", "error"].includes(value.outcome)) invalid("outcome");
  if (typeof value.score !== "number" || !Number.isFinite(value.score) || value.score < 0 || value.score > 1) invalid("score");
  if (!Number.isSafeInteger(value.latency_ms) || value.latency_ms < 0) invalid("latency_ms");
  if (!Number.isSafeInteger(value.cost_minor) || value.cost_minor < 0) invalid("cost_minor");
  if (!["pass", "block"].includes(value.safety)) invalid("safety");
  const evidenceRefs = boundedRefs(value.evidence_refs, "evidence_refs", { min: 1, max: 32 });
  const error = value.error === null ? null : boundedText(value.error, "error", 2048);
  return Object.freeze({ ...value, evidence_refs: evidenceRefs, error });
}

function validateGate(value) {
  exactKeys(value, [
    "schema_version", "record_type", "gate_id", "run_id", "candidate_sha256",
    "baseline_sha256", "decision", "checks", "reasons", "rollback_ref",
  ], "gate");
  if (value.schema_version !== EVAL_SCHEMA_VERSION || value.record_type !== "eval_gate") invalid("gate version");
  id(value.gate_id, "gate_id");
  id(value.run_id, "run_id");
  hash(value.candidate_sha256, "candidate_sha256");
  hash(value.baseline_sha256, "baseline_sha256");
  if (!["pass", "block"].includes(value.decision)) invalid("decision");
  exactKeys(value.checks, ["held_out", "safety", "cost", "latency", "live_evidence"], "checks");
  for (const check of Object.values(value.checks)) {
    if (!["pass", "block"].includes(check)) invalid("check");
  }
  if (!Array.isArray(value.reasons) || value.reasons.length > 16) invalid("reasons");
  const reasons = value.reasons.map((reason) => boundedText(reason, "reason", 512));
  const rollbackRef = value.rollback_ref === null ? null : ref(value.rollback_ref, "rollback_ref");
  return Object.freeze({ ...value, checks: Object.freeze({ ...value.checks }), reasons: Object.freeze(reasons), rollback_ref: rollbackRef });
}

function validateEvalRecord(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid("record");
  switch (value.record_type) {
    case "eval_case": return validateCase(value);
    case "eval_run": return validateRun(value);
    case "eval_score": return validateScore(value);
    case "eval_gate": return validateGate(value);
    default: invalid("record_type");
  }
}

module.exports = {
  EVAL_SCHEMA_VERSION,
  SPLITS,
  CATEGORIES,
  LIFECYCLES,
  EFFECTS,
  READBACKS,
  RECORD_TYPES,
  validateCase,
  validateRun,
  validateScore,
  validateGate,
  validateEvalRecord,
};
