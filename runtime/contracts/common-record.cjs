"use strict";

const crypto = require("node:crypto");
const {
  projectFinancialRecord,
  financialRecordId,
} = require("../../apps/life-manager/lib/financial-record-contract.js");
const {
  createCitizenIdentity,
  projectCitizenIdentity,
  citizenIdentityRefs,
  assertCitizenBinding,
  assertCitizenCollection,
  assertSignerAddress,
} = require("./citizen-identity.cjs");

const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const EFFECT_CLASSES = new Set([
  "none", "publish", "message", "money", "application", "trade", "account_mutation",
]);
const RECEIPT_OUTCOMES = new Set(["verified", "failed", "uncertain", "reconciled"]);
const EVIDENCE_REF = /^[a-z][a-z0-9+.-]*:\/\/[A-Za-z0-9._:/-]{1,512}$/;

function invalid(label) {
  throw new Error(`common Job ${label} invalid`);
}

function id(value, label) {
  if (typeof value !== "string" || !ID.test(value)) invalid(label);
  return value;
}

function codePointLength(value) {
  return [...value].length;
}

function maritimeCapafyJobId(phase, tenantId, occurrenceId) {
  const digest = crypto.createHash("sha256")
    .update(`maritime-capafy-${phase}:v1:${tenantId}:${occurrenceId}`)
    .digest("hex");
  return `maritime-capafy-${phase}:${digest}`;
}

// The approved provider jobs carry literal queue identities, rather than URI refs.
// Keep this exception exact and shared by construction and common-record reads.
function validateMaritimeCapafyInputRefs(value) {
  const phase = /^maritime\.manager\.capafy\.(prepare|publish)$/.exec(value.capability || "")?.[1];
  if (!phase) return false;
  const refs = value.input_refs;
  const tenant = value.tenant_id;
  const hasSkillScope = refs?.skill_id !== undefined || refs?.skill_disclosure_sha256 !== undefined;
  const keys = ["source_cycle_job_id", "artifact_ref", "account_ref", "occurrence_id", "release_ref",
    ...(hasSkillScope ? ["skill_id", "skill_disclosure_sha256"] : []),
    ...(phase === "publish" ? ["prepare_job_id", "agent_id", "agent_version_id"] : [])].sort();
  if (!/^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(tenant || "")
    || !refs || typeof refs !== "object" || Array.isArray(refs)
    || JSON.stringify(Object.keys(refs).sort()) !== JSON.stringify(keys)
    || Object.values(refs).some(ref => typeof ref !== "string" || !ref || ref.length > 1000)
    || value.loop_id !== value.capability || value.effect_class !== "publish" || value.max_attempts !== 1
    || value.job_id !== maritimeCapafyJobId(phase, tenant, refs.occurrence_id)
    || !/^maritime-cycle:[0-9a-f]{64}$/.test(refs.source_cycle_job_id)
    || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(refs.occurrence_id)
    || value.effect_key !== `maritime-capafy-${phase}://${tenant}/${encodeURIComponent(refs.occurrence_id)}`
    || !/^release:\/\/git\/[0-9a-f]{40}$/.test(refs.release_ref)
    || !refs.account_ref.startsWith(`account://capafy/${tenant}/`)
    || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(refs.account_ref.slice(`account://capafy/${tenant}/`.length))
    || !refs.artifact_ref.startsWith("artifact://") || refs.artifact_ref.includes("\0")
    || refs.artifact_ref.slice(11).split("/").some(part => !part || part === "." || part === "..")
    || (hasSkillScope && (!ID.test(refs.skill_id || "") || !/^[a-f0-9]{64}$/.test(refs.skill_disclosure_sha256 || "")))
    || (phase === "publish" && (refs.prepare_job_id !== maritimeCapafyJobId("prepare", tenant, refs.occurrence_id)
      || !ID.test(refs.agent_id) || !ID.test(refs.agent_version_id)))) invalid("Maritime Capafy input_refs");
  return true;
}

function projectJob(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid("record");
  const effectClass = value.effect_class;
  if (!EFFECT_CLASSES.has(effectClass)) invalid("effect_class");
  const effectKey = value.effect_key;
  if ((effectClass === "none" && effectKey !== null)
    || (effectClass !== "none" && (typeof effectKey !== "string" || codePointLength(effectKey) < 1 || codePointLength(effectKey) > 500))) {
    invalid("effect_key");
  }
  if (!value.input_refs || typeof value.input_refs !== "object" || Array.isArray(value.input_refs)) {
    invalid("input_refs");
  }
  const providerRefs = validateMaritimeCapafyInputRefs(value);
  const inputRefs = {};
  for (const [key, raw] of Object.entries(value.input_refs)) {
    if (!providerRefs && !/_refs?$/.test(key)) invalid("input_refs");
    const items = Array.isArray(raw) ? raw : [raw];
    if (items.length < 1 || items.some((item) => typeof item !== "string" || codePointLength(item) < 1 || codePointLength(item) > 1000)) {
      invalid("input_refs");
    }
    inputRefs[key] = Array.isArray(raw) ? [...raw] : raw;
  }
  if (!Number.isSafeInteger(value.max_attempts) || value.max_attempts < 1 || value.max_attempts > 20) {
    invalid("max_attempts");
  }
  return {
    schema_version: 1,
    record_type: "job",
    job_id: id(value.job_id, "job_id"),
    tenant_id: id(value.tenant_id, "tenant_id"),
    loop_id: id(value.loop_id, "loop_id"),
    capability: id(value.capability, "capability"),
    effect_class: effectClass,
    effect_key: effectKey,
    input_refs: inputRefs,
    max_attempts: value.max_attempts,
  };
}

function projectReceipt(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid("Receipt record");
  if (!RECEIPT_OUTCOMES.has(value.outcome)) invalid("Receipt outcome");
  if (typeof value.payload_sha256 !== "string" || !/^[a-f0-9]{64}$/.test(value.payload_sha256)) {
    invalid("Receipt payload_sha256");
  }
  if (typeof value.recorded_at !== "string" || !Number.isFinite(Date.parse(value.recorded_at))) {
    invalid("Receipt recorded_at");
  }
  if (value.external_ref !== null && (typeof value.external_ref !== "string" || codePointLength(value.external_ref) > 1024)) {
    invalid("Receipt external_ref");
  }
  if (!Array.isArray(value.evidence_refs) || value.evidence_refs.length > 32
    || value.evidence_refs.some((ref) => typeof ref !== "string" || !EVIDENCE_REF.test(ref))) {
    invalid("Receipt evidence_refs");
  }
  if (value.outcome === "verified" && (!value.external_ref || value.evidence_refs.length < 1)) {
    invalid("Receipt verification evidence");
  }
  return {
    schema_version: 1,
    record_type: "receipt",
    receipt_id: id(value.receipt_id, "Receipt receipt_id"),
    effect_id: id(value.effect_id, "Receipt effect_id"),
    loop_id: id(value.loop_id, "Receipt loop_id"),
    run_id: id(value.run_id, "Receipt run_id"),
    outcome: value.outcome,
    provider: id(value.provider, "Receipt provider"),
    recorded_at: value.recorded_at,
    external_ref: value.external_ref,
    payload_sha256: value.payload_sha256,
    evidence_refs: [...value.evidence_refs],
  };
}

module.exports = {
  validateMaritimeCapafyInputRefs, projectJob, projectReceipt, projectFinancialRecord, financialRecordId,
  createCitizenIdentity, projectCitizenIdentity, citizenIdentityRefs,
  assertCitizenBinding, assertCitizenCollection, assertSignerAddress,
};
