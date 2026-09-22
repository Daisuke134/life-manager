"use strict";

const {
  GOAL_SYNTHESIS_EXAMPLES,
  GOAL_SYNTHESIS_INSTRUCTION,
  readGoalPolicy,
} = require("./goal-policy.js");

const PORTFOLIO_KEYS = Object.freeze([
  "generated_at", "goals", "origin", "revision", "schema_version", "tenant_id",
]);
const GOAL_KEYS = Object.freeze([
  "confidence", "cost_budget", "dependencies", "evidence_refs", "expected_outcome",
  "expires_at", "goal_id", "origin", "revision", "risk_budget", "statement", "status",
  "success_receipt", "tenant_id",
]);
const CANDIDATE_KEYS = Object.freeze(GOAL_KEYS.filter((key) => (
  !["origin", "revision", "tenant_id"].includes(key)
)));
const COST_KEYS = Object.freeze(["currency", "minor_units"]);
const GOAL_STATUSES = new Set(["active", "paused", "retired"]);
const IDENTIFIER = /^[a-z0-9][a-z0-9._-]{0,199}$/u;
const CURRENCY = /^[A-Z]{3}$/u;
const MINOR_UNITS = /^(0|[1-9][0-9]*)$/u;

function invalid() {
  throw new Error("goal portfolio invalid");
}

function deepFreeze(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  for (const child of Object.values(value)) deepFreeze(child);
  return Object.freeze(value);
}

function exactKeys(value, expected) {
  return value && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).length === expected.length
    && Object.keys(value).sort().every((key, index) => key === expected[index]);
}

function strictIso(value) {
  if (typeof value !== "string") return false;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) && new Date(timestamp).toISOString() === value;
}

function reference(value) {
  if (typeof value !== "string" || !value || value.length > 1024 || /\s/u.test(value)) return false;
  try {
    const parsed = new URL(value);
    return Boolean(parsed.protocol && (parsed.hostname || parsed.pathname));
  } catch {
    return false;
  }
}

function referenceList(value, { allowEmpty = true } = {}) {
  return Array.isArray(value)
    && (allowEmpty || value.length > 0)
    && value.every(reference)
    && new Set(value).size === value.length;
}

function nonEmptyString(value, maxLength) {
  return typeof value === "string" && value === value.trim()
    && value.length > 0 && value.length <= maxLength;
}

function validateGoal(goal, portfolio, authorizedRefs, goalIds) {
  if (!exactKeys(goal, GOAL_KEYS)
    || !IDENTIFIER.test(goal.goal_id)
    || goal.tenant_id !== portfolio.tenant_id
    || goal.revision !== portfolio.revision
    || goal.origin !== "life_manager"
    || !nonEmptyString(goal.statement, 2000)
    || !nonEmptyString(goal.expected_outcome, 2000)
    || typeof goal.confidence !== "number" || goal.confidence <= 0 || goal.confidence > 1
    || !referenceList(goal.evidence_refs, { allowEmpty: false })
    || goal.evidence_refs.some((ref) => !authorizedRefs.has(ref))
    || !exactKeys(goal.cost_budget, COST_KEYS)
    || !CURRENCY.test(goal.cost_budget.currency)
    || !MINOR_UNITS.test(goal.cost_budget.minor_units)
    || !nonEmptyString(goal.risk_budget, 100)
    || !Array.isArray(goal.dependencies)
    || goal.dependencies.some((dependency) => (
      !IDENTIFIER.test(dependency) || dependency === goal.goal_id || !goalIds.has(dependency)
    ))
    || new Set(goal.dependencies).size !== goal.dependencies.length
    || !(goal.expires_at === null || strictIso(goal.expires_at))
    || !(goal.success_receipt === null || reference(goal.success_receipt))
    || !GOAL_STATUSES.has(goal.status)) {
    return invalid();
  }
  return goal;
}

function validateGoalPortfolio(value, context = {}) {
  if (!exactKeys(value, PORTFOLIO_KEYS)
    || value.schema_version !== "life-manager.goal-portfolio.v1"
    || !IDENTIFIER.test(value.tenant_id)
    || value.tenant_id !== context.tenantId
    || !Number.isInteger(value.revision) || value.revision < 1
    || !strictIso(value.generated_at)
    || value.origin !== "life_manager"
    || !Array.isArray(value.goals) || value.goals.length < 1 || value.goals.length > 3
    || !referenceList(context.authorizedRefs, { allowEmpty: false })) {
    return invalid();
  }
  const goalIds = new Set(value.goals.map((goal) => goal && goal.goal_id));
  if (goalIds.size !== value.goals.length) return invalid();
  const authorizedRefs = new Set(context.authorizedRefs);
  value.goals.forEach((goal) => validateGoal(goal, value, authorizedRefs, goalIds));
  return deepFreeze(value);
}

function synthesisInput(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)
    || !IDENTIFIER.test(input.tenantId)
    || !Number.isInteger(input.revision) || input.revision < 1
    || !strictIso(input.generatedAt)
    || !referenceList(input.factRefs)
    || !referenceList(input.evidenceRefs)
    || !referenceList(input.boundaryRefs)) {
    return invalid();
  }
  const authorizedRefs = [...input.factRefs, ...input.evidenceRefs, ...input.boundaryRefs];
  if (new Set(authorizedRefs).size !== authorizedRefs.length || authorizedRefs.length === 0) {
    return invalid();
  }
  return { ...input, authorizedRefs };
}

async function synthesizeGoalPortfolio(input = {}, dependencies = {}) {
  const normalized = synthesisInput(input);
  if (typeof dependencies.generate !== "function") return invalid();
  const policy = readGoalPolicy(dependencies.policyFile);
  const modelInput = deepFreeze({
    instruction: GOAL_SYNTHESIS_INSTRUCTION,
    examples: GOAL_SYNTHESIS_EXAMPLES,
    policy,
    tenant_id: normalized.tenantId,
    fact_refs: [...normalized.factRefs],
    evidence_refs: [...normalized.evidenceRefs],
    boundary_refs: [...normalized.boundaryRefs],
  });
  const generated = await dependencies.generate(modelInput);
  if (!exactKeys(generated, ["goals"])
    || !Array.isArray(generated.goals) || generated.goals.length < 1 || generated.goals.length > 3
    || generated.goals.some((goal) => !exactKeys(goal, CANDIDATE_KEYS)
      || goal.success_receipt !== null || goal.status !== "active")) {
    return invalid();
  }
  const portfolio = {
    schema_version: "life-manager.goal-portfolio.v1",
    tenant_id: normalized.tenantId,
    revision: normalized.revision,
    generated_at: normalized.generatedAt,
    origin: "life_manager",
    goals: generated.goals.map((goal) => ({
      ...goal,
      tenant_id: normalized.tenantId,
      revision: normalized.revision,
      origin: "life_manager",
    })),
  };
  return validateGoalPortfolio(portfolio, {
    tenantId: normalized.tenantId,
    authorizedRefs: normalized.authorizedRefs,
  });
}

function activePortfolioGoal(portfolio, nowMs) {
  if (!portfolio || !Array.isArray(portfolio.goals) || !Number.isFinite(nowMs)) return invalid();
  const goal = portfolio.goals.find((item) => item.status === "active"
    && (item.expires_at === null || Date.parse(item.expires_at) > nowMs));
  if (!goal) return invalid();
  return goal;
}

function goalReference(goal) {
  if (!goal || !IDENTIFIER.test(goal.tenant_id) || !IDENTIFIER.test(goal.goal_id)
    || !Number.isInteger(goal.revision) || goal.revision < 1 || goal.origin !== "life_manager") {
    return invalid();
  }
  return `goal-portfolio://${encodeURIComponent(goal.tenant_id)}/${encodeURIComponent(goal.goal_id)}?revision=${goal.revision}`;
}

module.exports = {
  activePortfolioGoal,
  goalReference,
  synthesizeGoalPortfolio,
  validateGoalPortfolio,
};
