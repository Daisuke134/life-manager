"use strict";

const { validateEvidenceRefs } = require("../../lib/evidence-ref.js");

const SCHEMA_VERSION = 1;
const TRACKS = Object.freeze(["agent_native", "one_shot_onboarding", "simulation"]);
const SPLITS = Object.freeze(["tuning", "held_out"]);
const CATEGORIES = Object.freeze(["canonical", "boundary", "adversarial", "regression"]);
const REVENUE_CLASSES = Object.freeze([
  "subscription", "retainer", "recurring_usage", "one_time",
  "realized_investment", "fundraising", "internal_transfer", "unknown",
]);
const COST_CATEGORIES = Object.freeze([
  "model", "browser", "cloud", "tool", "platform_fee", "payment_fee",
  "advertising", "refund", "delivery", "operating",
  "realized_investment_loss", "due_liability", "tax",
]);
const COUNTERPARTY_CLASSES = Object.freeze(["external_customer", "self", "related", "unknown"]);
const ACTOR_CLASSES = Object.freeze(["life_manager", "human", "external_ai", "provider"]);
const CREDENTIAL_CLASSES = Object.freeze(["none", "agent_owned", "one_shot_user", "recurring_user"]);
const EVENT_KINDS = Object.freeze([
  "bootstrap", "human_intervention", "credential_use",
  "external_ai_intervention", "external_effect", "policy_violation",
]);
const EFFECTS = Object.freeze(["not_applicable", "planned", "started", "verified", "failed", "unknown"]);
const READBACKS = Object.freeze(["not_applicable", "absent", "present", "unknown"]);

const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/u;
const HASH = /^[a-f0-9]{64}$/u;
const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$/u;
const CURRENCY = /^[A-Z][A-Z0-9]{2,9}$/u;

function invalid(label) {
  throw new Error(`EconomicAutonomyRecord ${label} invalid`);
}

function exactKeys(value, expected, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid(label);
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length
    || actual.some((key, index) => key !== wanted[index])) invalid(label);
}

function identifier(value, label) {
  if (typeof value !== "string" || !ID.test(value)) invalid(label);
  return value;
}

function token(value, label) {
  if (typeof value !== "string" || !TOKEN.test(value)) invalid(label);
  return value;
}

function hash(value, label) {
  if (typeof value !== "string" || !HASH.test(value)) invalid(label);
  return value;
}

function instant(value, label) {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))
    || !/[zZ]|[+-]\d\d:\d\d$/u.test(value)) invalid(label);
  return new Date(value).toISOString();
}

function nonNegativeInteger(value, label) {
  if (!Number.isSafeInteger(value) || value < 0) invalid(label);
  return value;
}

function signedInteger(value, label) {
  if (!Number.isSafeInteger(value)) invalid(label);
  return value;
}

function boolean(value, label) {
  if (typeof value !== "boolean") invalid(label);
  return value;
}

function boundedText(value, label, max = 2048) {
  if (typeof value !== "string" || value.trim() === "" || value.length > max
    || /\b(?:password|cookie|api[_ -]?key|access[_ -]?token)\b/iu.test(value)) invalid(label);
  return value;
}

function refs(value, label, { min = 0, max = 64 } = {}) {
  try {
    return validateEvidenceRefs(value, label, { min, max });
  } catch {
    invalid(label);
  }
}

function sortedTokens(value, label, { allowEmpty = true } = {}) {
  if (!Array.isArray(value) || (!allowEmpty && value.length === 0) || value.length > 64) invalid(label);
  const checked = value.map((item) => token(item, label));
  if (new Set(checked).size !== checked.length
    || checked.some((item, index) => index > 0 && checked[index - 1].localeCompare(item) >= 0)) {
    invalid(`${label} order`);
  }
  return Object.freeze(checked);
}

function validateEpisode(value) {
  exactKeys(value, [
    "schema_version", "record_type", "episode_id", "subject_id", "track", "currency",
    "period_start", "period_end", "starting_capital_minor", "spend_cap_minor",
    "release_sha256", "model", "toolchain_sha256", "policy_sha256",
  ], "episode");
  if (value.schema_version !== SCHEMA_VERSION || value.record_type !== "economic_autonomy_episode") {
    invalid("episode version");
  }
  identifier(value.episode_id, "episode_id");
  identifier(value.subject_id, "subject_id");
  if (!TRACKS.includes(value.track)) invalid("track");
  if (typeof value.currency !== "string" || !CURRENCY.test(value.currency)) invalid("currency");
  const periodStart = instant(value.period_start, "period_start");
  const periodEnd = instant(value.period_end, "period_end");
  if (Date.parse(periodEnd) <= Date.parse(periodStart)) invalid("period");
  nonNegativeInteger(value.starting_capital_minor, "starting_capital_minor");
  nonNegativeInteger(value.spend_cap_minor, "spend_cap_minor");
  hash(value.release_sha256, "release_sha256");
  token(value.model, "model");
  hash(value.toolchain_sha256, "toolchain_sha256");
  hash(value.policy_sha256, "policy_sha256");
  return Object.freeze({ ...value, period_start: periodStart, period_end: periodEnd });
}

function validateAttribution(value) {
  exactKeys(value, [
    "schema_version", "record_type", "record_id", "loop_id", "counterparty_class",
    "counterparty_sha256", "revenue_class", "cost_category", "evidence_refs",
  ], "attribution");
  if (value.schema_version !== SCHEMA_VERSION || value.record_type !== "economic_attribution") {
    invalid("attribution version");
  }
  identifier(value.record_id, "record_id");
  identifier(value.loop_id, "loop_id");
  const isRevenue = value.revenue_class !== null;
  const isCost = value.cost_category !== null;
  if (isRevenue === isCost) invalid("classification");
  if (isRevenue) {
    if (!REVENUE_CLASSES.includes(value.revenue_class)) invalid("revenue_class");
    if (!COUNTERPARTY_CLASSES.includes(value.counterparty_class)) invalid("counterparty_class");
    hash(value.counterparty_sha256, "counterparty_sha256");
  } else {
    if (!COST_CATEGORIES.includes(value.cost_category)) invalid("cost_category");
    if (value.revenue_class !== null || value.counterparty_class !== null
      || value.counterparty_sha256 !== null) invalid("classification counterparty");
  }
  return Object.freeze({ ...value, evidence_refs: refs(value.evidence_refs, "evidence_refs", { min: 1, max: 32 }) });
}

function validateAutonomyEvent(value) {
  exactKeys(value, [
    "schema_version", "record_type", "event_id", "episode_id", "event_kind", "actor_class",
    "credential_class", "occurred_at", "duration_seconds", "effect", "readback",
    "duplicate", "evidence_refs",
  ], "autonomy event");
  if (value.schema_version !== SCHEMA_VERSION || value.record_type !== "economic_autonomy_event") {
    invalid("autonomy event version");
  }
  identifier(value.event_id, "event_id");
  identifier(value.episode_id, "episode_id");
  if (!EVENT_KINDS.includes(value.event_kind)) invalid("event_kind");
  if (!ACTOR_CLASSES.includes(value.actor_class)) invalid("actor_class");
  if (!CREDENTIAL_CLASSES.includes(value.credential_class)) invalid("credential_class");
  const occurredAt = instant(value.occurred_at, "occurred_at");
  nonNegativeInteger(value.duration_seconds, "duration_seconds");
  if (!EFFECTS.includes(value.effect)) invalid("effect");
  if (!READBACKS.includes(value.readback)) invalid("readback");
  boolean(value.duplicate, "duplicate");
  return Object.freeze({
    ...value,
    occurred_at: occurredAt,
    evidence_refs: refs(value.evidence_refs, "evidence_refs", { min: 1, max: 32 }),
  });
}

function validateCostCoverage(value) {
  exactKeys(value, ["schema_version", "record_type", "episode_id", "categories"], "cost coverage");
  if (value.schema_version !== SCHEMA_VERSION || value.record_type !== "economic_cost_coverage") {
    invalid("cost coverage version");
  }
  identifier(value.episode_id, "episode_id");
  exactKeys(value.categories, COST_CATEGORIES, "cost coverage categories");
  const seenRecordIds = new Set();
  const categories = {};
  for (const category of COST_CATEGORIES) {
    const entry = value.categories[category];
    exactKeys(entry, ["status", "record_ids", "evidence_refs"], `cost coverage ${category}`);
    if (!Array.isArray(entry.record_ids) || entry.record_ids.length > 10_000) {
      invalid(`cost coverage ${category} record_ids`);
    }
    const recordIds = entry.record_ids.map((recordId) => identifier(recordId, "cost record_id"));
    for (const recordId of recordIds) {
      if (seenRecordIds.has(recordId)) invalid("cost coverage duplicate record_id");
      seenRecordIds.add(recordId);
    }
    let evidenceRefs;
    if (entry.status === "records") {
      if (recordIds.length === 0) invalid(`cost coverage ${category} records`);
      evidenceRefs = refs(entry.evidence_refs, `cost coverage ${category} evidence`, { max: 32 });
    } else if (["zero_cost", "not_applicable"].includes(entry.status)) {
      if (recordIds.length !== 0) invalid(`cost coverage ${category} record_ids`);
      evidenceRefs = refs(entry.evidence_refs, `cost coverage ${category} evidence`, { min: 1, max: 32 });
    } else {
      invalid(`cost coverage ${category} status`);
    }
    categories[category] = Object.freeze({
      status: entry.status,
      record_ids: Object.freeze(recordIds),
      evidence_refs: evidenceRefs,
    });
  }
  return Object.freeze({ ...value, categories: Object.freeze(categories) });
}

function validateExpected(value) {
  exactKeys(value, [
    "eligible", "settled_net_profit_minor", "recurring_revenue_minor", "reason_codes",
  ], "case expected");
  boolean(value.eligible, "expected eligible");
  signedInteger(value.settled_net_profit_minor, "expected settled_net_profit_minor");
  nonNegativeInteger(value.recurring_revenue_minor, "expected recurring_revenue_minor");
  const reasonCodes = sortedTokens(value.reason_codes, "expected reason_codes");
  if (value.eligible !== (reasonCodes.length === 0)) invalid("expected eligibility reasons");
  return Object.freeze({ ...value, reason_codes: reasonCodes });
}

function validateCase(value) {
  exactKeys(value, [
    "schema_version", "record_type", "case_id", "split", "category",
    "fixture_ref", "input_sha256", "expected",
  ], "case");
  if (value.schema_version !== SCHEMA_VERSION || value.record_type !== "economic_autonomy_case") {
    invalid("case version");
  }
  identifier(value.case_id, "case_id");
  if (!SPLITS.includes(value.split)) invalid("split");
  if (!CATEGORIES.includes(value.category)) invalid("category");
  const fixtureRef = refs([value.fixture_ref], "fixture_ref", { min: 1, max: 1 })[0];
  hash(value.input_sha256, "input_sha256");
  return Object.freeze({ ...value, fixture_ref: fixtureRef, expected: validateExpected(value.expected) });
}

function validateRun(value) {
  exactKeys(value, [
    "schema_version", "record_type", "run_id", "case_set_sha256", "release_sha256",
    "model", "toolchain_sha256", "started_at", "finished_at", "status",
    "score_ids", "trace_refs", "error",
  ], "run");
  if (value.schema_version !== SCHEMA_VERSION || value.record_type !== "economic_autonomy_run") {
    invalid("run version");
  }
  identifier(value.run_id, "run_id");
  hash(value.case_set_sha256, "case_set_sha256");
  hash(value.release_sha256, "release_sha256");
  token(value.model, "model");
  hash(value.toolchain_sha256, "toolchain_sha256");
  const startedAt = instant(value.started_at, "started_at");
  const finishedAt = instant(value.finished_at, "finished_at");
  if (Date.parse(finishedAt) <= Date.parse(startedAt)) invalid("run timing");
  if (!["completed", "failed", "blocked"].includes(value.status)) invalid("run status");
  if (!Array.isArray(value.score_ids) || value.score_ids.length > 10_000) invalid("score_ids");
  const scoreIds = value.score_ids.map((scoreId) => identifier(scoreId, "score_id"));
  if (new Set(scoreIds).size !== scoreIds.length) invalid("duplicate score_id");
  const traceRefs = refs(value.trace_refs, "trace_refs", { min: 1, max: 64 });
  const error = value.error === null ? null : boundedText(value.error, "run error");
  if ((value.status === "completed") !== (error === null)) invalid("run error");
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
    "schema_version", "record_type", "score_id", "run_id", "case_id", "episode_id",
    "eligible", "reason_codes", "currency", "settled_customer_revenue_minor",
    "recurring_revenue_minor", "total_cost_minor", "settled_net_profit_minor",
    "contribution_margin_bps", "self_funded", "human_intervention_count",
    "human_intervention_seconds", "external_ai_intervention_count", "credential_classes",
    "effect_unknown_count", "duplicate_effect_count", "evidence_refs",
  ], "score");
  if (value.schema_version !== SCHEMA_VERSION || value.record_type !== "economic_autonomy_score") {
    invalid("score version");
  }
  for (const [field, fieldValue] of [
    ["score_id", value.score_id], ["run_id", value.run_id], ["case_id", value.case_id],
    ["episode_id", value.episode_id],
  ]) identifier(fieldValue, field);
  boolean(value.eligible, "eligible");
  const reasonCodes = sortedTokens(value.reason_codes, "reason_codes");
  if (value.eligible !== (reasonCodes.length === 0)) invalid("eligibility reasons");
  if (typeof value.currency !== "string" || !CURRENCY.test(value.currency)) invalid("currency");
  nonNegativeInteger(value.settled_customer_revenue_minor, "settled_customer_revenue_minor");
  nonNegativeInteger(value.recurring_revenue_minor, "recurring_revenue_minor");
  nonNegativeInteger(value.total_cost_minor, "total_cost_minor");
  signedInteger(value.settled_net_profit_minor, "settled_net_profit_minor");
  if (value.contribution_margin_bps !== null) {
    signedInteger(value.contribution_margin_bps, "contribution_margin_bps");
  }
  boolean(value.self_funded, "self_funded");
  if (value.self_funded && !value.eligible) invalid("self_funded eligibility");
  nonNegativeInteger(value.human_intervention_count, "human_intervention_count");
  nonNegativeInteger(value.human_intervention_seconds, "human_intervention_seconds");
  nonNegativeInteger(value.external_ai_intervention_count, "external_ai_intervention_count");
  const credentialClasses = sortedTokens(value.credential_classes, "credential_classes");
  if (credentialClasses.some((credentialClass) => !CREDENTIAL_CLASSES.includes(credentialClass))) {
    invalid("credential_classes");
  }
  nonNegativeInteger(value.effect_unknown_count, "effect_unknown_count");
  nonNegativeInteger(value.duplicate_effect_count, "duplicate_effect_count");
  return Object.freeze({
    ...value,
    reason_codes: reasonCodes,
    credential_classes: credentialClasses,
    evidence_refs: refs(value.evidence_refs, "evidence_refs", { min: 1, max: 128 }),
  });
}

module.exports = {
  SCHEMA_VERSION,
  TRACKS,
  SPLITS,
  CATEGORIES,
  REVENUE_CLASSES,
  COST_CATEGORIES,
  COUNTERPARTY_CLASSES,
  ACTOR_CLASSES,
  CREDENTIAL_CLASSES,
  EVENT_KINDS,
  EFFECTS,
  READBACKS,
  validateCase,
  validateEpisode,
  validateAttribution,
  validateAutonomyEvent,
  validateCostCoverage,
  validateRun,
  validateScore,
};
