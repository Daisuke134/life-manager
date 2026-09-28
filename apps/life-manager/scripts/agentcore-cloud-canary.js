"use strict";

const TOKYO_REGION = "ap-northeast-1";
const RELEASE_SHA = /^[a-f0-9]{40}$/;
const TOKYO_AGENTCORE_ARN = /^arn:aws[a-zA-Z-]*:bedrock-agentcore:ap-northeast-1:/;

function requiredString(value, field) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${field} is required`);
  }
  return value;
}

function validateCanaryResult(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new Error("canary result must be an object");
  }
  if (input.region !== TOKYO_REGION) {
    throw new Error(`region must be ${TOKYO_REGION}`);
  }
  if (input.effect !== "none") {
    throw new Error("effect must be none");
  }
  if (!RELEASE_SHA.test(String(input.release_sha || ""))) {
    throw new Error("release_sha must be 40 lowercase hexadecimal characters");
  }
  for (const field of [
    "runtime_resource_arn",
    "browser_resource_arn",
    "identity_resource_arn",
  ]) {
    if (!TOKYO_AGENTCORE_ARN.test(String(input[field] || ""))) {
      throw new Error(`${field} must be an AgentCore ARN in ${TOKYO_REGION}`);
    }
  }
  for (const field of [
    "runtime_session_id",
    "browser_session_id",
    "browser_profile_id",
  ]) {
    requiredString(input[field], field);
  }
  if (input.principal_type !== "agent_owned") {
    throw new Error("principal_type must be agent_owned");
  }
  if (input.human_input_count !== 0) {
    throw new Error("human_input_count must be 0");
  }
  const usageReceiptRef = requiredString(input.usage_receipt_ref, "usage_receipt_ref");
  if (!usageReceiptRef.startsWith(`aws-usage://${TOKYO_REGION}/`)) {
    throw new Error(`usage_receipt_ref must identify official AWS usage in ${TOKYO_REGION}`);
  }
  return Object.freeze({ ...input });
}

module.exports = { validateCanaryResult };
