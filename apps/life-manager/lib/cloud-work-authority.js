"use strict";

const crypto = require("node:crypto");

const { loadCloudExecutionPolicy } = require("./cloud-execution-policy.js");

const TOKEN_PREFIX = "lmwg1";
const PAYLOAD_KEYS = [
  "attempt", "capability", "credential_refs", "effect_class", "expires_at", "issued_at",
  "job_id", "policy_digest", "tenant_id", "version", "worker_id",
];
const EXPECTED_KEYS = [
  "attempt", "capability", "effectClass", "jobId", "tenantId", "workerId",
];
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/u;
const TENANT_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/u;

function invalid() {
  throw new Error("cloud work grant invalid");
}

function exactKeys(value, keys) {
  return value && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).length === keys.length
    && Object.keys(value).sort().every((key, index) => key === keys[index]);
}

function authorityKey(value) {
  const source = String(value || process.env.LM_CLOUD_WORK_SIGNING_KEY || "").trim();
  let key;
  if (/^[a-fA-F0-9]{64}$/u.test(source)) key = Buffer.from(source, "hex");
  else {
    try { key = Buffer.from(source, "base64"); }
    catch { key = Buffer.alloc(0); }
  }
  if (key.length !== 32) throw new Error("cloud work authority unavailable");
  return key;
}

function canonicalInstant(value) {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) return null;
  const parsed = new Date(Date.parse(value)).toISOString();
  return parsed === value ? parsed : null;
}

function frozenPayload(value) {
  value.credential_refs = Object.freeze([...value.credential_refs]);
  return Object.freeze(value);
}

function capabilityPolicy(bundle) {
  const entry = bundle.policy.capabilities[0];
  if (!entry || entry.capability !== "general-agent.work" || entry.effect_class !== "none") invalid();
  return entry;
}

function validateJob(job, entry) {
  const refs = job && job.input_refs;
  if (!job || !TENANT_ID.test(String(job.tenant_id || ""))
    || !SAFE_ID.test(String(job.job_id || ""))
    || job.loop_id !== "life-manager.manager"
    || job.capability !== entry.capability
    || job.effect_class !== entry.effect_class || job.effect_key !== null
    || job.max_attempts !== entry.max_attempts
    || !Number.isInteger(job.attempt) || job.attempt < 1 || job.attempt > job.max_attempts
    || !refs || typeof refs !== "object" || Array.isArray(refs)
    || JSON.stringify(Object.keys(refs)) !== JSON.stringify(["goal_ref"])
    || typeof refs.goal_ref !== "string"
    || !refs.goal_ref.startsWith(`goal-portfolio://${encodeURIComponent(job.tenant_id)}/`)) {
    invalid();
  }
  return job;
}

function validateExpected(value) {
  if (!exactKeys(value, EXPECTED_KEYS)
    || !TENANT_ID.test(String(value.tenantId || ""))
    || !SAFE_ID.test(String(value.jobId || ""))
    || !SAFE_ID.test(String(value.workerId || ""))
    || !SAFE_ID.test(String(value.capability || ""))
    || typeof value.effectClass !== "string" || !value.effectClass
    || !Number.isInteger(value.attempt) || value.attempt < 1) invalid();
  return value;
}

function parsePayload(token, key) {
  if (typeof token !== "string") invalid();
  const parts = token.split(".");
  if (parts.length !== 3 || parts[0] !== TOKEN_PREFIX
    || !/^[A-Za-z0-9_-]+$/u.test(parts[1]) || !/^[A-Za-z0-9_-]+$/u.test(parts[2])) invalid();
  const material = `${parts[0]}.${parts[1]}`;
  const expectedSignature = crypto.createHmac("sha256", key).update(material).digest();
  let suppliedSignature;
  try { suppliedSignature = Buffer.from(parts[2], "base64url"); }
  catch { return invalid(); }
  if (suppliedSignature.length !== expectedSignature.length
    || !crypto.timingSafeEqual(suppliedSignature, expectedSignature)) invalid();
  let payload;
  try {
    const decoded = Buffer.from(parts[1], "base64url");
    if (decoded.toString("base64url") !== parts[1]) invalid();
    payload = JSON.parse(decoded.toString("utf8"));
  } catch { return invalid(); }
  return payload;
}

function createCloudWorkAuthority(options = {}) {
  const key = authorityKey(options.signingKey);
  const bundle = loadCloudExecutionPolicy(options.policyFile);
  const entry = capabilityPolicy(bundle);
  const now = typeof options.now === "function" ? options.now : Date.now;

  function observedNow() {
    const value = Number(now());
    if (!Number.isFinite(value)) invalid();
    return value;
  }

  return Object.freeze({
    policyDigest: bundle.digest,

    issue(input = {}) {
      const claimed = validateJob(input.job, entry);
      const workerId = String(input.workerId || "");
      if (!SAFE_ID.test(workerId)) invalid();
      const issuedMs = observedNow();
      const payload = {
        version: 1,
        policy_digest: bundle.digest,
        tenant_id: claimed.tenant_id,
        job_id: claimed.job_id,
        attempt: claimed.attempt,
        worker_id: workerId,
        capability: entry.capability,
        effect_class: entry.effect_class,
        credential_refs: [...entry.credential_refs],
        issued_at: new Date(issuedMs).toISOString(),
        expires_at: new Date(issuedMs + bundle.policy.claim.grant_ttl_seconds * 1000).toISOString(),
      };
      const encoded = Buffer.from(JSON.stringify(payload), "utf8").toString("base64url");
      const material = `${TOKEN_PREFIX}.${encoded}`;
      const signature = crypto.createHmac("sha256", key).update(material).digest("base64url");
      return `${material}.${signature}`;
    },

    verify(token, expectedValue) {
      const expected = validateExpected(expectedValue);
      const payload = parsePayload(token, key);
      const issued = canonicalInstant(payload && payload.issued_at);
      const expires = canonicalInstant(payload && payload.expires_at);
      const current = observedNow();
      if (!exactKeys(payload, PAYLOAD_KEYS)
        || payload.version !== 1 || payload.policy_digest !== bundle.digest
        || payload.tenant_id !== expected.tenantId || payload.job_id !== expected.jobId
        || payload.attempt !== expected.attempt || payload.worker_id !== expected.workerId
        || payload.capability !== expected.capability || payload.effect_class !== expected.effectClass
        || !issued || !expires || Date.parse(expires) - Date.parse(issued)
          !== bundle.policy.claim.grant_ttl_seconds * 1000
        || current < Date.parse(issued) || current > Date.parse(expires)
        || !Array.isArray(payload.credential_refs)
        || payload.credential_refs.length !== entry.credential_refs.length
        || payload.credential_refs.some((ref, index) => ref !== entry.credential_refs[index])) {
        invalid();
      }
      return frozenPayload(payload);
    },
  });
}

module.exports = { createCloudWorkAuthority };
