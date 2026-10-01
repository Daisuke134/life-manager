"use strict";

const { createHash } = require("node:crypto");

const SKIP = new Set([
  "interview",
  "assessment",
  "recording",
  "camera",
  "screen_share",
  "free_form_response",
  "ongoing_approval",
]);
const HOLD = new Set([
  "captcha",
  "kyc",
  "identity_verification",
  "legal_bootstrap_authorization",
  "provider_bootstrap_authorization",
]);
const BOOTSTRAP = new Set([
  "legal_bootstrap_authorization",
  "provider_bootstrap_authorization",
]);
const EVIDENCE_REF = /^[a-z][a-z0-9+.-]{1,31}:\/\/[A-Za-z0-9][A-Za-z0-9._~:/?#@!$&'()*+,;=%-]{0,999}$/;

function qualifyHumanRequirement(input = {}) {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new Error("human requirement invalid");
  }
  const requirements = input.requirements;
  if (!Array.isArray(requirements) || requirements.length === 0) {
    throw new Error("human requirement invalid");
  }
  const reasonCodes = [...new Set(requirements)].sort();
  if (reasonCodes.length !== requirements.length
      || reasonCodes.some((value) => typeof value !== "string" || (!SKIP.has(value) && !HOLD.has(value)))) {
    throw new Error("human requirement invalid");
  }
  const evidenceRef = input.evidence_ref;
  if (typeof evidenceRef !== "string" || !EVIDENCE_REF.test(evidenceRef)) {
    throw new Error("human requirement evidence invalid");
  }
  const canonical = JSON.stringify([reasonCodes, evidenceRef]);
  return Object.freeze({
    state: "human_required",
    disposition: reasonCodes.some((value) => HOLD.has(value)) ? "hold" : "skip",
    reason_codes: Object.freeze(reasonCodes),
    evidence_ref: evidenceRef,
    qualification_id: createHash("sha256").update(canonical, "utf8").digest("hex"),
    delegate_to_human: false,
    bypass_allowed: false,
    bootstrap_boundary: reasonCodes.some((value) => BOOTSTRAP.has(value))
      ? "one_time_bootstrap_authorization" : null,
  });
}

module.exports = { qualifyHumanRequirement };
