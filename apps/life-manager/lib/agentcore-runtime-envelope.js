"use strict";

const { canonicalJson } = require("./cloud-edition-kernel.js");

const ID = /^[a-z0-9][a-z0-9._:-]{0,199}$/i;
const RELEASE_SHA = /^[a-f0-9]{40}$/;
const EVIDENCE_SHA = /^[a-f0-9]{64}$/;
const REQUEST_FIELDS = Object.freeze([
  "schema_version",
  "tenant_id",
  "job_id",
  "attempt",
  "wake_id",
  "release_sha",
  "input_refs",
]);
const RESULT_FIELDS = Object.freeze([
  "tenant_id",
  "job_id",
  "attempt",
  "release_sha",
  "status",
  "receipt_ref",
  "evidence_sha256",
  "usage",
]);
const USAGE_FIELDS = Object.freeze([
  "provider",
  "resource",
  "quantity",
  "unit",
  "cost_usd_micros",
  "provider_receipt_id",
]);
const STATUSES = new Set([
  "completed",
  "retry",
  "reconcile",
  "not_applicable",
  "policy_denied",
  "blocked",
]);
const INPUT_KINDS = new Set(["state", "credential", "browser-session", "receipt"]);
const MAX_ENVELOPE_BYTES = 16_384;

function plainRecord(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)
      || Object.getPrototypeOf(value) !== Object.prototype) {
    throw new Error(`AgentCore ${label} must be a plain record`);
  }
  return value;
}

function exactFields(value, expected, label) {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((field, index) => field !== wanted[index])) {
    throw new Error(`AgentCore ${label} field set invalid`);
  }
}

function requiredId(value, label) {
  const text = String(value || "");
  if (!ID.test(text)) throw new Error(`AgentCore ${label} invalid`);
  return text;
}

function positiveAttempt(value) {
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new Error("AgentCore attempt invalid");
  }
  return value;
}

function resourceRef(value, expectedTenant, allowedKinds) {
  let parsed;
  try {
    parsed = new URL(String(value || ""));
  } catch {
    throw new Error("AgentCore resource reference invalid");
  }
  const parts = parsed.pathname.split("/").filter(Boolean).map(decodeURIComponent);
  if (
    parsed.protocol !== "lm-resource:"
    || parsed.username || parsed.password || parsed.port || parsed.search || parsed.hash
    || !allowedKinds.has(parsed.hostname)
    || parts.length !== 2
    || parts[0] !== expectedTenant
    || !ID.test(parts[0])
    || !parts[1]
    || parts[1].length > 512
  ) {
    if (parts[0] && parts[0] !== expectedTenant) {
      throw new Error("AgentCore resource reference tenant mismatch");
    }
    throw new Error("AgentCore resource reference invalid");
  }
  return String(value);
}

function bounded(value, label) {
  if (Buffer.byteLength(canonicalJson(value)) > MAX_ENVELOPE_BYTES) {
    throw new Error(`AgentCore ${label} too large`);
  }
}

function frozenClone(value) {
  if (Array.isArray(value)) return Object.freeze(value.map(frozenClone));
  if (value && typeof value === "object") {
    return Object.freeze(Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, frozenClone(item)]),
    ));
  }
  return value;
}

function validateRuntimeRequest(value, options = {}) {
  const request = plainRecord(value, "request");
  exactFields(request, REQUEST_FIELDS, "request");
  if (request.schema_version !== 1) throw new Error("AgentCore request schema invalid");
  const tenantId = requiredId(request.tenant_id, "tenant");
  requiredId(request.job_id, "job");
  positiveAttempt(request.attempt);
  requiredId(request.wake_id, "wake");
  const approvedReleaseSha = String(options.approvedReleaseSha || "");
  if (!RELEASE_SHA.test(request.release_sha)
      || !RELEASE_SHA.test(approvedReleaseSha)
      || request.release_sha !== approvedReleaseSha) {
    throw new Error("AgentCore release SHA is mutable or unapproved");
  }
  if (!Array.isArray(request.input_refs) || request.input_refs.length < 1
      || request.input_refs.length > 64) {
    throw new Error("AgentCore input references invalid");
  }
  for (const ref of request.input_refs) resourceRef(ref, tenantId, INPUT_KINDS);
  bounded(request, "request");
  return frozenClone(request);
}

function validateUsage(value) {
  const usage = plainRecord(value, "usage item");
  exactFields(usage, USAGE_FIELDS, "usage item");
  requiredId(usage.provider, "usage provider");
  requiredId(usage.resource, "usage resource");
  requiredId(usage.unit, "usage unit");
  requiredId(usage.provider_receipt_id, "usage provider receipt");
  if (!Number.isSafeInteger(usage.quantity) || usage.quantity < 0) {
    throw new Error("AgentCore usage quantity invalid");
  }
  if (!Number.isSafeInteger(usage.cost_usd_micros) || usage.cost_usd_micros < 0) {
    throw new Error("AgentCore usage cost invalid");
  }
}

function validateRuntimeResult(value, requestValue) {
  const request = plainRecord(requestValue, "request identity");
  const result = plainRecord(value, "result");
  exactFields(result, RESULT_FIELDS, "result");
  if (
    result.tenant_id !== request.tenant_id
    || result.job_id !== request.job_id
    || result.attempt !== request.attempt
    || result.release_sha !== request.release_sha
  ) {
    throw new Error("AgentCore result execution identity mismatch");
  }
  const tenantId = requiredId(result.tenant_id, "result tenant");
  requiredId(result.job_id, "result job");
  positiveAttempt(result.attempt);
  if (!RELEASE_SHA.test(result.release_sha)) throw new Error("AgentCore result release invalid");
  if (!STATUSES.has(result.status)) throw new Error("AgentCore result status invalid");
  resourceRef(result.receipt_ref, tenantId, new Set(["receipt"]));
  if (!EVIDENCE_SHA.test(String(result.evidence_sha256 || ""))) {
    throw new Error("AgentCore result evidence invalid");
  }
  if (!Array.isArray(result.usage) || result.usage.length > 64) {
    throw new Error("AgentCore result usage invalid");
  }
  for (const item of result.usage) validateUsage(item);
  bounded(result, "result");
  return frozenClone(result);
}

module.exports = {
  MAX_ENVELOPE_BYTES,
  validateRuntimeRequest,
  validateRuntimeResult,
};
