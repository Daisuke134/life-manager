"use strict";

const {
  validateCase,
  validateRun,
  validateScore,
  validateGate,
} = require("./records.js");

const MAX_COST_MULTIPLIER = 1.2;
const MAX_LATENCY_MULTIPLIER = 1.2;
const CANDIDATE_BOUNDARY_SCHEMA_VERSION = 1;
const CANDIDATE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/u;
const CANDIDATE_HASH = /^[a-f0-9]{64}$/u;
const CANDIDATE_PATH = /^[A-Za-z0-9._/-]{1,512}$/u;
const CANDIDATE_REF = /^[a-z][a-z0-9+.-]*:\/\/\S{1,1024}$/iu;
const CANDIDATE_CAPABILITIES = Object.freeze([
  "identity", "permissions", "credentials", "evidence_rules", "evaluator",
  "provider_effect", "scheduler",
]);
const PROTECTED_CANDIDATE_PATHS = Object.freeze([
  /^AGENTS\.md$/u,
  /^CLAUDE\.md$/u,
  /^\.github\//u,
  /^config\//u,
  /^runtime\//u,
  /^apps\/life-manager\/eval\/agent-contract\//u,
  /^apps\/life-manager\/lib\/(?:product-onboarding|notification-policy)\.js$/u,
  /^skills\/(?:context|eval|goal|graph|harness|loop|observability)-engineering\//u,
  /^skills\/loop-development\//u,
  /(^|\/)(?:credentials?|secrets?|state|\.env)(?:\/|$)/iu,
]);

function invalid(label) {
  throw new Error(`EvalGate ${label} invalid`);
}

function exactKeys(value, expected, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid(label);
  const actual = Object.keys(value).sort();
  const keys = [...expected].sort();
  if (actual.length !== keys.length || actual.some((key, index) => key !== keys[index])) invalid(label);
}

function finiteRatio(value, label) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) invalid(label);
  return value;
}

function nonNegativeInteger(value, label) {
  if (!Number.isSafeInteger(value) || value < 0) invalid(label);
  return value;
}

function validateCandidateBoundary(value) {
  exactKeys(value, [
    "schema_version", "candidate_id", "base_release_sha256", "candidate_sha256",
    "changed_paths", "capabilities", "rollback_ref",
  ], "candidate boundary");
  if (value.schema_version !== CANDIDATE_BOUNDARY_SCHEMA_VERSION) invalid("candidate boundary version");
  if (typeof value.candidate_id !== "string" || !CANDIDATE_ID.test(value.candidate_id)) {
    invalid("candidate boundary candidate_id");
  }
  if (typeof value.base_release_sha256 !== "string" || !CANDIDATE_HASH.test(value.base_release_sha256)) {
    invalid("candidate boundary base hash");
  }
  if (typeof value.candidate_sha256 !== "string" || !CANDIDATE_HASH.test(value.candidate_sha256)) {
    invalid("candidate boundary candidate hash");
  }
  if (!Array.isArray(value.changed_paths) || value.changed_paths.length < 1 || value.changed_paths.length > 1024) {
    invalid("candidate boundary changed paths");
  }
  const changedPaths = value.changed_paths.map((changedPath) => {
    if (typeof changedPath !== "string" || !CANDIDATE_PATH.test(changedPath)
      || changedPath.startsWith("/") || changedPath.includes("..") || changedPath.includes("\\")) {
      invalid("candidate boundary path");
    }
    return changedPath;
  });
  if (new Set(changedPaths).size !== changedPaths.length) invalid("candidate boundary duplicate path");
  exactKeys(value.capabilities, CANDIDATE_CAPABILITIES, "candidate boundary capabilities");
  const reasons = [];
  for (const capability of CANDIDATE_CAPABILITIES) {
    if (value.capabilities[capability] !== false) reasons.push("mutation_capability_forbidden");
  }
  for (const changedPath of changedPaths) {
    if (PROTECTED_CANDIDATE_PATHS.some((pattern) => pattern.test(changedPath))) {
      reasons.push("protected_path_changed");
    } else if (!(
      changedPath.startsWith("prompts/")
      || changedPath.startsWith("docs/agent-engineering/")
      || /^skills\/[^/]+\/SKILL\.md$/u.test(changedPath)
      || /^skills\/[^/]+\/prompts\//u.test(changedPath)
    )) {
      reasons.push("candidate_path_not_allowed");
    }
  }
  if (typeof value.rollback_ref !== "string" || !CANDIDATE_REF.test(value.rollback_ref)) {
    invalid("candidate boundary rollback_ref");
  }
  return Object.freeze({
    schema_version: CANDIDATE_BOUNDARY_SCHEMA_VERSION,
    candidate_id: value.candidate_id,
    base_release_sha256: value.base_release_sha256,
    candidate_sha256: value.candidate_sha256,
    changed_paths: Object.freeze(changedPaths),
    capabilities: Object.freeze({ ...value.capabilities }),
    rollback_ref: value.rollback_ref,
    promotable: reasons.length === 0,
    reasons: Object.freeze([...new Set(reasons)]),
  });
}

function validateBaseline(value) {
  exactKeys(value, ["held_out_score", "cost_minor", "latency_ms", "safety"], "baseline");
  const heldOutScore = finiteRatio(value.held_out_score, "baseline held_out_score");
  const costMinor = nonNegativeInteger(value.cost_minor, "baseline cost_minor");
  const latencyMs = nonNegativeInteger(value.latency_ms, "baseline latency_ms");
  if (value.safety !== "pass") invalid("baseline safety");
  return Object.freeze({ held_out_score: heldOutScore, cost_minor: costMinor, latency_ms: latencyMs, safety: "pass" });
}

function validateLiveEvidence(value) {
  exactKeys(value, ["official_readback", "replay_zero"], "live evidence");
  if (!["verified", "unknown", "absent"].includes(value.official_readback)) invalid("official_readback");
  if (typeof value.replay_zero !== "boolean") invalid("replay_zero");
  return Object.freeze({ ...value });
}

function average(rows, field) {
  return rows.reduce((total, row) => total + row[field], 0) / rows.length;
}

function sameIds(left, right) {
  const a = [...left].sort();
  const b = [...right].sort();
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

function decidePromotionGate(input) {
  exactKeys(input, ["run", "cases", "scores", "baseline", "liveEvidence", "rollback_ref"], "input");
  const run = validateRun(input.run);
  const cases = input.cases.map(validateCase);
  const scores = input.scores.map(validateScore);
  if (cases.length > 10_000 || scores.length > 10_000) invalid("bounds");
  const baseline = validateBaseline(input.baseline);
  const liveEvidence = validateLiveEvidence(input.liveEvidence);

  const reasons = [];
  let structurePass = true;
  const caseById = new Map();
  for (const item of cases) {
    if (caseById.has(item.case_id)) {
      structurePass = false;
      reasons.push(`duplicate case ${item.case_id}`);
    }
    caseById.set(item.case_id, item);
  }
  const scoreById = new Map();
  for (const item of scores) {
    if (scoreById.has(item.score_id)) {
      structurePass = false;
      reasons.push(`duplicate score ${item.score_id}`);
    }
    scoreById.set(item.score_id, item);
    if (item.run_id !== run.run_id) {
      structurePass = false;
      reasons.push(`score ${item.score_id} belongs to another run`);
    }
    if (!caseById.has(item.case_id)) {
      structurePass = false;
      reasons.push(`score ${item.score_id} references an unknown case`);
    }
  }
  if (!sameIds(run.score_ids, scores.map((item) => item.score_id))) {
    structurePass = false;
    reasons.push("run score IDs do not match score records");
  }
  const scoresByCase = new Map();
  for (const item of scores) scoresByCase.set(item.case_id, (scoresByCase.get(item.case_id) || []).concat(item));
  for (const item of cases) {
    if ((scoresByCase.get(item.case_id) || []).length !== 1) {
      structurePass = false;
      reasons.push(`case ${item.case_id} is not scored exactly once`);
    }
  }

  const heldOutCases = cases.filter((item) => item.split === "held_out");
  const heldOutScores = heldOutCases.flatMap((item) => scoresByCase.get(item.case_id) || []);
  const heldOutAverage = heldOutScores.length ? average(heldOutScores, "score") : null;
  const heldOutPass = structurePass && heldOutScores.length > 0
    && heldOutScores.every((item) => item.outcome === "passed")
    && heldOutAverage >= baseline.held_out_score;
  if (!heldOutPass) reasons.push("held-out behavior is missing, failed, or below baseline");

  const safetyPass = run.status === "completed" && baseline.safety === "pass"
    && scores.length > 0 && scores.every((item) => item.safety === "pass");
  if (!safetyPass) reasons.push("safety or run completion check failed");

  const costAverage = scores.length ? average(scores, "cost_minor") : null;
  const costPass = costAverage !== null && costAverage <= baseline.cost_minor * MAX_COST_MULTIPLIER;
  if (!costPass) reasons.push("cost regressed beyond the allowed margin");

  const latencyAverage = scores.length ? average(scores, "latency_ms") : null;
  const latencyPass = latencyAverage !== null && latencyAverage <= baseline.latency_ms * MAX_LATENCY_MULTIPLIER;
  if (!latencyPass) reasons.push("latency regressed beyond the allowed margin");

  const livePass = liveEvidence.official_readback === "verified" && liveEvidence.replay_zero === true;
  if (!livePass) reasons.push("official live readback or replay-zero proof is missing");

  if (input.rollback_ref === null) reasons.push("rollback pointer is missing");
  const checks = {
    held_out: heldOutPass && !reasons.some((reason) => reason.startsWith("case ") || reason.startsWith("score ") || reason.startsWith("duplicate ")) ? "pass" : "block",
    safety: safetyPass ? "pass" : "block",
    cost: costPass ? "pass" : "block",
    latency: latencyPass ? "pass" : "block",
    live_evidence: livePass ? "pass" : "block",
  };
  const promote = Object.values(checks).every((value) => value === "pass") && input.rollback_ref !== null && reasons.length === 0;
  const gate = validateGate({
    schema_version: 1,
    record_type: "eval_gate",
    gate_id: `gate-${run.run_id}`,
    run_id: run.run_id,
    candidate_sha256: run.candidate_sha256,
    baseline_sha256: run.baseline_sha256,
    decision: promote ? "pass" : "block",
    checks,
    reasons: promote ? [] : [...new Set(reasons)].slice(0, 16),
    rollback_ref: input.rollback_ref,
  });
  return Object.freeze({
    promote,
    gate,
    metrics: Object.freeze({
      held_out_score: heldOutAverage,
      held_out_count: heldOutScores.length,
      cost_minor: costAverage,
      latency_ms: latencyAverage,
    }),
  });
}

function decideCandidatePromotion(input) {
  exactKeys(input, ["eval", "candidateBoundary"], "candidate promotion input");
  if (!input.candidateBoundary || typeof input.candidateBoundary !== "object"
    || Array.isArray(input.candidateBoundary)) {
    throw new Error("EvalGate candidate boundary required");
  }
  const boundary = validateCandidateBoundary(input.candidateBoundary);
  const evaluation = decidePromotionGate(input.eval);
  const reasons = [...new Set([
    ...evaluation.gate.reasons,
    ...boundary.reasons,
  ])].slice(0, 16);
  const promote = evaluation.promote && boundary.promotable;
  const gate = validateGate({
    ...evaluation.gate,
    decision: promote ? "pass" : "block",
    reasons: promote ? [] : reasons.length ? reasons : ["candidate_boundary_blocked"],
  });
  return Object.freeze({
    promote,
    boundary,
    gate,
    metrics: evaluation.metrics,
  });
}

module.exports = {
  CANDIDATE_BOUNDARY_SCHEMA_VERSION,
  CANDIDATE_CAPABILITIES,
  MAX_COST_MULTIPLIER,
  MAX_LATENCY_MULTIPLIER,
  decideCandidatePromotion,
  decidePromotionGate,
  validateCandidateBoundary,
};
