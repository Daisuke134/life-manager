"use strict";

const INPUT_KEYS = [
  "attempt", "capability", "credentialRef", "effectClass", "grant", "inputRefs",
  "jobId", "operation", "tenantId", "workerId",
];
const RESULT_KEYS = [
  "attempt", "capability", "evidence_refs", "job_id", "operation_id", "status", "tenant_id",
];
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/u;
const TENANT_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/u;
const SAFE_REF = /^[a-z][a-z0-9+.-]*:\/\/[A-Za-z0-9._:/-]{1,512}$/u;
const SECRET_REF = /^secret:\/\/[a-z0-9][a-z0-9._-]*(?:\/[a-z0-9][a-z0-9._-]*)*$/u;
const STATUSES = new Set(["planned", "completed", "blocked"]);

function invocationInvalid() {
  throw new Error("cloud credential invocation invalid");
}

function unavailable() {
  throw new Error("cloud credential broker unavailable");
}

function exactKeys(value, keys) {
  return value && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).length === keys.length
    && Object.keys(value).sort().every((key, index) => key === keys[index]);
}

function validateInvocation(value) {
  const refs = value && value.inputRefs;
  if (!exactKeys(value, INPUT_KEYS)
    || typeof value.grant !== "string" || !value.grant
    || !TENANT_ID.test(String(value.tenantId || ""))
    || !SAFE_ID.test(String(value.jobId || ""))
    || !SAFE_ID.test(String(value.workerId || ""))
    || value.capability !== "general-agent.work" || value.effectClass !== "none"
    || !Number.isInteger(value.attempt) || value.attempt !== 1
    || !SECRET_REF.test(String(value.credentialRef || ""))
    || value.operation !== "gemini.generate-plan"
    || !refs || typeof refs !== "object" || Array.isArray(refs)
    || JSON.stringify(Object.keys(refs)) !== JSON.stringify(["goal_ref"])
    || typeof refs.goal_ref !== "string"
    || !refs.goal_ref.startsWith(`goal-portfolio://${encodeURIComponent(value.tenantId)}/`)) {
    invocationInvalid();
  }
  return value;
}

function validateResult(value, expected, secret) {
  if (!exactKeys(value, RESULT_KEYS)
    || !SAFE_ID.test(String(value.operation_id || ""))
    || !STATUSES.has(value.status)
    || value.tenant_id !== expected.tenantId || value.job_id !== expected.jobId
    || value.attempt !== expected.attempt || value.capability !== expected.capability
    || !Array.isArray(value.evidence_refs) || value.evidence_refs.length < 1
    || value.evidence_refs.length > 16
    || new Set(value.evidence_refs).size !== value.evidence_refs.length
    || value.evidence_refs.some((ref) => typeof ref !== "string" || !SAFE_REF.test(ref))
    || JSON.stringify(value).includes(secret)) unavailable();
  return Object.freeze({
    operation_id: value.operation_id,
    status: value.status,
    tenant_id: value.tenant_id,
    job_id: value.job_id,
    attempt: value.attempt,
    capability: value.capability,
    evidence_refs: Object.freeze([...value.evidence_refs]),
  });
}

function createCloudCredentialBroker(options = {}) {
  const authority = options.authority;
  const secretProvider = options.secretProvider;
  const providerCall = options.providerCall;
  if (!authority || typeof authority.verify !== "function"
    || !secretProvider || typeof secretProvider.health !== "function"
    || typeof secretProvider.get !== "function" || typeof providerCall !== "function") unavailable();

  return Object.freeze({
    async invoke(input) {
      let value;
      let grant;
      try {
        value = validateInvocation(input);
        grant = authority.verify(value.grant, {
          tenantId: value.tenantId,
          jobId: value.jobId,
          attempt: value.attempt,
          workerId: value.workerId,
          capability: value.capability,
          effectClass: value.effectClass,
        });
        if (grant.credential_refs.length !== 1
          || grant.credential_refs[0] !== value.credentialRef
          || value.credentialRef !== "secret://gemini/api-key") invocationInvalid();
      } catch {
        return invocationInvalid();
      }

      try {
        const health = await secretProvider.health();
        if (!health || health.ok !== true || health.mode !== "cloud" || health.provider !== "vault") {
          return unavailable();
        }
        const secret = await secretProvider.get(value.tenantId, value.credentialRef);
        if (typeof secret !== "string" || !secret || secret.length > 8192) return unavailable();
        const result = await providerCall(Object.freeze({
          operation: value.operation,
          credentialValue: secret,
          tenantId: value.tenantId,
          jobId: value.jobId,
          attempt: value.attempt,
          workerId: value.workerId,
          capability: value.capability,
          inputRefs: Object.freeze({ goal_ref: value.inputRefs.goal_ref }),
        }));
        return validateResult(result, value, secret);
      } catch {
        return unavailable();
      }
    },
  });
}

module.exports = { createCloudCredentialBroker };
