"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const DEFAULT_POLICY = path.resolve(__dirname, "../config/cloud-execution-policy.json");
const ROOT_KEYS = [
  "authority", "capabilities", "claim", "requires_user_authored_goal", "schema_version",
];
const CLAIM_KEYS = ["grant_ttl_seconds", "lease_seconds", "limit"];
const CAPABILITY_KEYS = ["capability", "credential_refs", "effect_class", "max_attempts"];
const SECRET_REF = /^secret:\/\/[a-z0-9][a-z0-9._-]*(?:\/[a-z0-9][a-z0-9._-]*)*$/u;

function invalid() {
  throw new Error("cloud execution policy invalid");
}

function sameKeys(value, expected) {
  return value && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).length === expected.length
    && Object.keys(value).sort().every((key, index) => key === expected[index]);
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => (
      `${JSON.stringify(key)}:${canonicalJson(value[key])}`
    )).join(",")}}`;
  }
  return JSON.stringify(value);
}

function deepFreeze(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  Object.values(value).forEach(deepFreeze);
  return Object.freeze(value);
}

function validate(value) {
  if (!sameKeys(value, ROOT_KEYS)
    || value.schema_version !== "life-manager.cloud-execution-policy.v1"
    || value.authority !== "life_manager"
    || value.requires_user_authored_goal !== false
    || !sameKeys(value.claim, CLAIM_KEYS)
    || value.claim.limit !== 1
    || !Number.isInteger(value.claim.lease_seconds)
    || value.claim.lease_seconds < 30 || value.claim.lease_seconds > 900
    || !Number.isInteger(value.claim.grant_ttl_seconds)
    || value.claim.grant_ttl_seconds < 10
    || value.claim.grant_ttl_seconds > value.claim.lease_seconds
    || !Array.isArray(value.capabilities) || value.capabilities.length !== 1) {
    return invalid();
  }
  const capability = value.capabilities[0];
  if (!sameKeys(capability, CAPABILITY_KEYS)
    || capability.capability !== "general-agent.work"
    || capability.effect_class !== "none"
    || capability.max_attempts !== 1
    || !Array.isArray(capability.credential_refs)
    || capability.credential_refs.length !== 1
    || capability.credential_refs[0] !== "secret://gemini/api-key"
    || !SECRET_REF.test(capability.credential_refs[0])
    || new Set(capability.credential_refs).size !== capability.credential_refs.length) {
    return invalid();
  }
  return value;
}

function loadCloudExecutionPolicy(file = DEFAULT_POLICY) {
  let value;
  try { value = JSON.parse(fs.readFileSync(file, "utf8")); }
  catch { return invalid(); }
  const policy = deepFreeze(validate(value));
  const digest = crypto.createHash("sha256").update(canonicalJson(policy)).digest("hex");
  return deepFreeze({ policy, digest });
}

module.exports = { loadCloudExecutionPolicy };
