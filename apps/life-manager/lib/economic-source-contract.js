"use strict";

const { validateEvidenceRefs } = require("./evidence-ref.js");

const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/u;
const ADAPTER = /^[a-z][a-z0-9-]{0,127}$/u;
const HASH = /^[a-f0-9]{64}$/u;
const SOURCE_KINDS = new Set(["funnel", "financial", "cost"]);
const IMPLEMENTATIONS = new Set(["implemented", "partial", "missing", "not_applicable"]);
const STATES = new Set([
  "not_configured", "unavailable", "empty", "observed_unverified",
  "observed_verified", "not_applicable",
]);
const FUNNEL_STAGES = new Set([
  "discovered", "published", "impression", "click", "lead", "application", "reply",
  "contract", "delivery", "order", "trial", "subscription", "renewal", "payment",
  "refund", "payout", "retention",
]);

function invalid(label) {
  throw new Error(`EconomicSource ${label} invalid`);
}

function exactKeys(value, expected, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid(label);
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length
    || actual.some((key, index) => key !== wanted[index])) invalid(label);
}

function id(value, label) {
  if (typeof value !== "string" || !ID.test(value)) invalid(label);
  return value;
}

function instant(value, label) {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))
    || !/[zZ]|[+-]\d\d:\d\d$/u.test(value)) invalid(label);
  return new Date(value).toISOString();
}

function receiptIds(value, { min = 0 } = {}) {
  if (!Array.isArray(value) || value.length < min || value.length > 10_000) {
    invalid("provider receipt ids");
  }
  const checked = value.map((item) => id(item, "provider receipt id"));
  if (new Set(checked).size !== checked.length) invalid("provider receipt ids duplicate");
  return Object.freeze(checked);
}

function validateEconomicSourceObservation(value) {
  exactKeys(value, [
    "schema_version", "record_type", "observation_id", "product_loop_id", "subject_id",
    "source_kind", "adapter", "implementation", "state", "observed_at",
    "provider_receipt_ids", "evidence_refs",
  ], "source observation");
  if (value.schema_version !== 1 || value.record_type !== "economic_source_observation") {
    invalid("source observation version");
  }
  id(value.observation_id, "observation_id");
  id(value.product_loop_id, "product_loop_id");
  id(value.subject_id, "subject_id");
  if (!SOURCE_KINDS.has(value.source_kind) || !IMPLEMENTATIONS.has(value.implementation)
    || !STATES.has(value.state)) invalid("source classification");
  const notApplicable = value.implementation === "not_applicable";
  if (notApplicable !== (value.adapter === null) || notApplicable !== (value.state === "not_applicable")) {
    invalid("source applicability");
  }
  if (value.adapter !== null && (typeof value.adapter !== "string" || !ADAPTER.test(value.adapter))) {
    invalid("source adapter");
  }
  const providerReceiptIds = receiptIds(value.provider_receipt_ids, {
    min: ["empty", "observed_verified"].includes(value.state) ? 1 : 0,
  });
  if (value.state === "not_applicable" && providerReceiptIds.length !== 0) {
    invalid("source provider receipts");
  }
  return Object.freeze({
    ...value,
    observed_at: instant(value.observed_at, "source observed_at"),
    provider_receipt_ids: providerReceiptIds,
    evidence_refs: validateEvidenceRefs(value.evidence_refs, "source evidence refs", { min: 1, max: 64 }),
  });
}

function validateEconomicFunnelObservation(value) {
  exactKeys(value, [
    "schema_version", "record_type", "funnel_observation_id", "source_observation_id",
    "product_loop_id", "subject_id", "stage", "cohort_sha256", "state", "count",
    "observed_at", "provider_receipt_ids", "evidence_refs",
  ], "funnel observation");
  if (value.schema_version !== 1 || value.record_type !== "economic_funnel_observation") {
    invalid("funnel observation version");
  }
  id(value.funnel_observation_id, "funnel_observation_id");
  id(value.source_observation_id, "source_observation_id");
  id(value.product_loop_id, "product_loop_id");
  id(value.subject_id, "subject_id");
  if (!FUNNEL_STAGES.has(value.stage) || !STATES.has(value.state)
    || typeof value.cohort_sha256 !== "string" || !HASH.test(value.cohort_sha256)) {
    invalid("funnel classification");
  }
  if (["observed_verified", "observed_unverified"].includes(value.state)) {
    if (!Number.isSafeInteger(value.count) || value.count < 0) invalid("funnel count");
  } else if (value.state === "empty") {
    if (value.count !== 0) invalid("funnel count");
  } else if (value.count !== null) {
    invalid("funnel count");
  }
  const providerReceiptIds = receiptIds(value.provider_receipt_ids, {
    min: ["empty", "observed_verified"].includes(value.state) ? 1 : 0,
  });
  return Object.freeze({
    ...value,
    observed_at: instant(value.observed_at, "funnel observed_at"),
    provider_receipt_ids: providerReceiptIds,
    evidence_refs: validateEvidenceRefs(value.evidence_refs, "funnel evidence refs", { min: 1, max: 64 }),
  });
}

function joinEconomicFunnelObservation(rawSource, rawFunnel) {
  const source = validateEconomicSourceObservation(rawSource);
  const funnel = validateEconomicFunnelObservation(rawFunnel);
  const identityMatches = source.source_kind === "funnel"
    && source.observation_id === funnel.source_observation_id
    && source.product_loop_id === funnel.product_loop_id
    && source.subject_id === funnel.subject_id;
  const stateMatches = source.state === funnel.state
    || (source.state === "observed_verified" && funnel.state === "empty");
  const receiptsMatch = funnel.provider_receipt_ids.every(
    (receiptId) => source.provider_receipt_ids.includes(receiptId),
  );
  const evidenceMatches = funnel.evidence_refs.some((ref) => source.evidence_refs.includes(ref));
  if (!identityMatches || !stateMatches || !receiptsMatch || !evidenceMatches) {
    throw new Error("EconomicSource funnel join invalid");
  }
  return Object.freeze({ source, funnel });
}

module.exports = {
  FUNNEL_STAGES: Object.freeze([...FUNNEL_STAGES]),
  IMPLEMENTATIONS: Object.freeze([...IMPLEMENTATIONS]),
  SOURCE_KINDS: Object.freeze([...SOURCE_KINDS]),
  STATES: Object.freeze([...STATES]),
  joinEconomicFunnelObservation,
  validateEconomicFunnelObservation,
  validateEconomicSourceObservation,
};
