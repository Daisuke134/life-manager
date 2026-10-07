"use strict";

const { randomUUID } = require("node:crypto");
const { recordCost } = require("./ledger.js");

const OUTCOMES = new Set(["success", "failure", "cache_hit"]);
const SECRET_KEY = /(api[_-]?key|authorization|credential|password|secret|token)/i;
const META_ENUMS = {
  sku: ["Geocoding", "Directions", "Routes: Compute Routes Pro", "Places - Text Search"],
  pricing_basis: ["list_price_after_free_cap", "list_price_after_free_rpd", "unavailable"],
  route_mode: ["transit", "google"],
  fallback_reason: ["transit_no_route", "transit_provider_4xx", "transit_provider_5xx",
    "transit_network", "transit_timeout", "transit_invalid_response", "non_jp"],
  model: ["gemini-2.5-flash", "gemini-3.7-flash", "gemini-2.5-flash-native-audio-preview-09-2025"],
  estimate_status: ["estimated", "unavailable", "not_applicable"],
  estimate_basis: ["audio_duration_proxy"],
};
const OPAQUE_EVENT_VERSION = /^[a-f0-9]{64}$/;
const SAFE_RUNTIME_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const SAFE_RELEASE_SHA = /^(?:[a-f0-9]{40}|[a-f0-9]{64})$/;
const SECRET_RUNTIME_VALUE = /(?:(?:token|secret|password|credential|api.?key)\s*[=:]|auth\.json|sk-[A-Za-z0-9_-]{16,})/i;
const RUNTIME_TRACE_FIELDS = ["tenant_id", "loop_id", "owner_id", "run_id", "occurrence_id", "release_sha"];
const MANAGED_RUNTIME_FIELDS = [
  "LIFE_MANAGER_LOOP_ID", "LIFE_MANAGER_OWNER_ID", "LIFE_MANAGER_RUN_ID",
  "LIFE_MANAGER_OCCURRENCE_ID", "LIFE_MANAGER_RELEASE_SHA",
];

function usageRuntimeEnv(source = process.env, options = {}) {
  const env = source && typeof source === "object" && !Array.isArray(source) ? source : {};
  const config = options && typeof options === "object" && !Array.isArray(options) ? options : {};
  const runtimeEnv = Object.fromEntries(MANAGED_RUNTIME_FIELDS
    .filter((key) => env[key] != null)
    .map((key) => [key, env[key]]));
  const managedContextPresent = MANAGED_RUNTIME_FIELDS.some((key) => env[key] != null
    && String(env[key]).trim() !== "");
  const ownerId = typeof config.fallbackOwnerId === "string" ? config.fallbackOwnerId.trim() : "";
  if (!managedContextPresent && env.RAILWAY_SERVICE_NAME === "life-call" && ownerId) {
    const runId = typeof config.fallbackRunId === "string" && config.fallbackRunId.trim()
      ? config.fallbackRunId.trim() : `run-${randomUUID()}`;
    runtimeEnv.LIFE_MANAGER_OWNER_ID = ownerId;
    runtimeEnv.LIFE_MANAGER_RUN_ID = runId;
    runtimeEnv.LIFE_MANAGER_OCCURRENCE_ID = `${ownerId}:${runId}`;
    if (env.RAILWAY_GIT_COMMIT_SHA != null) {
      runtimeEnv.LIFE_MANAGER_RELEASE_SHA = env.RAILWAY_GIT_COMMIT_SHA;
    }
  }
  return runtimeEnv;
}

function requiredText(value, name) {
  const text = value == null ? "" : String(value).trim();
  if (!text) throw new Error(`${name} is required`);
  return text;
}

function enumValue(key, value) {
  return typeof value === "string" && META_ENUMS[key].includes(value);
}

const META_VALIDATORS = {
  sku: (value) => enumValue("sku", value),
  pricing_basis: (value) => enumValue("pricing_basis", value),
  route_mode: (value) => enumValue("route_mode", value),
  fallback_reason: (value) => enumValue("fallback_reason", value),
  model: (value) => value === null || enumValue("model", value),
  input_tokens: (value) => value === null || (typeof value === "number" && Number.isFinite(value) && value >= 0),
  output_tokens: (value) => value === null || (typeof value === "number" && Number.isFinite(value) && value >= 0),
  estimate_status: (value) => enumValue("estimate_status", value),
  pricing_version: (value) => value === null || (typeof value === "string"
    && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/.test(value)),
  reconnects: (value) => Number.isInteger(value) && value >= 0,
  estimate_basis: (value) => enumValue("estimate_basis", value),
  event_version: (value) => typeof value === "string" && OPAQUE_EVENT_VERSION.test(value),
};

function safeMeta(meta) {
  const source = meta == null ? {} : meta;
  if (!source || typeof source !== "object" || Array.isArray(source)) {
    throw new Error("meta must be an object");
  }
  for (const key of Object.keys(source)) {
    if (key === "runtime_trace") throw new Error("runtime_trace metadata is reserved");
    const validate = Object.hasOwn(META_VALIDATORS, key) ? META_VALIDATORS[key] : null;
    if (!validate) {
      if (SECRET_KEY.test(key)) throw new Error(`secret-shaped metadata key: ${key}`);
      throw new Error(`unknown metadata key: ${key}`);
    }
    if (!validate(source[key])) throw new Error(`invalid metadata value: ${key}`);
  }
  return { ...source };
}

function finiteNonNegativeOrNull(value) {
  if (value == null || (typeof value === "string" && value.trim() === "")) return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function safeRuntimeId(value) {
  return typeof value === "string" && value !== "unknown"
    && SAFE_RUNTIME_ID.test(value) && !SECRET_RUNTIME_VALUE.test(value)
    ? value : null;
}

function runtimeTrace(event, runtimeEnv = {}) {
  const env = runtimeEnv && typeof runtimeEnv === "object" && !Array.isArray(runtimeEnv)
    ? runtimeEnv : {};
  const tenantId = safeRuntimeId(event.tenantId);
  const loopId = safeRuntimeId(env.LIFE_MANAGER_LOOP_ID);
  const ownerSource = env.LIFE_MANAGER_OWNER_ID || loopId;
  const ownerId = safeRuntimeId(ownerSource);
  const runId = safeRuntimeId(env.LIFE_MANAGER_RUN_ID);
  const occurrenceCandidate = safeRuntimeId(env.LIFE_MANAGER_OCCURRENCE_ID);
  const occurrencePrefix = loopId || ownerId;
  const occurrenceId = occurrencePrefix && occurrenceCandidate
    && occurrenceCandidate.startsWith(`${occurrencePrefix}:`) ? occurrenceCandidate : null;
  const releaseCandidate = env.LIFE_MANAGER_RELEASE_SHA;
  const releaseSha = typeof releaseCandidate === "string" && SAFE_RELEASE_SHA.test(releaseCandidate)
    ? releaseCandidate : null;
  const identity = {
    tenant_id: tenantId,
    loop_id: loopId,
    owner_id: ownerId,
    run_id: runId,
    occurrence_id: occurrenceId,
    release_sha: releaseSha,
  };
  const missing = RUNTIME_TRACE_FIELDS.filter((field) => identity[field] == null);
  const runtimeIdentityPresent = [loopId, ownerId, runId, occurrenceId, releaseSha].some(Boolean);
  return {
    schema_version: 1,
    status: missing.length === 0 ? "linked" : (runtimeIdentityPresent ? "partial" : "unlinked"),
    ...Object.fromEntries(Object.entries(identity).filter(([, value]) => value != null)),
    ...(missing.length ? { missing_fields: missing } : {}),
  };
}

function normalizeUsageEvent(event = {}, runtimeEnv = {}) {
  const tenantId = requiredText(event.tenantId, "tenantId");
  const provider = requiredText(event.provider, "provider");
  const feature = requiredText(event.feature, "feature");
  const outcome = requiredText(event.outcome, "outcome");
  if (!OUTCOMES.has(outcome)) throw new Error(`invalid outcome: ${outcome}`);

  const cacheHit = outcome === "cache_hit" || event.cacheHit === true;
  const meta = safeMeta(event.meta);
  const quantity = cacheHit ? 0 : finiteNonNegativeOrNull(event.providerUnits);
  const estimateUnavailable = meta.estimate_status === "unavailable";
  const estUsd = cacheHit ? 0 : (estimateUnavailable ? null
    : finiteNonNegativeOrNull(event.estimatedCostUsd));
  const operation = requiredText(event.operation || feature, "operation");
  const billingStatus = cacheHit ? "not_applicable"
    : (estUsd == null || estUsd === 0 ? "unknown" : "estimated");
  const estimateStatus = cacheHit ? "not_applicable"
    : (estUsd == null ? "unavailable" : (meta.estimate_status || "estimated"));
  const pricingVersion = Object.hasOwn(meta, "pricing_version") ? meta.pricing_version : ({
    google_maps: "lm-google-maps-estimate-2026-10-08-v1",
    gemini: "lm-gemini-estimate-2026-10-06-v1",
    google_search_grounding: "lm-gemini-estimate-2026-10-06-v1",
  })[provider] || null;

  return {
    uid: tenantId,
    kind: "provider_usage",
    quantity,
    unit: event.providerUnit == null ? "request" : String(event.providerUnit),
    estUsd,
    meta: {
      ...meta,
      provider,
      sku: meta.sku || meta.model || null,
      operation,
      currency: "USD",
      actual_usd: cacheHit ? 0 : null,
      billing_status: billingStatus,
      pricing_version: pricingVersion,
      estimate_status: estimateStatus,
      feature,
      outcome,
      failure_class: event.failureClass == null ? null : String(event.failureClass),
      cache_hit: cacheHit,
      // Stripe/customer allowance is a later, separate acceptance boundary (COST-06).
      customer_usage: false,
      runtime_trace: runtimeTrace(event, runtimeEnv),
    },
  };
}

async function recordUsageEvent(event, opts = {}) {
  const { runtimeEnv = process.env, ...writeOptions } = opts;
  const write = opts.recordCost || recordCost;
  return write(normalizeUsageEvent(event, runtimeEnv), writeOptions);
}

module.exports = { normalizeUsageEvent, recordUsageEvent, runtimeTrace, usageRuntimeEnv, OUTCOMES };
