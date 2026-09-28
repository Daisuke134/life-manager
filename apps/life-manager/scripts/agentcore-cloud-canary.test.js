"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const { validateCanaryResult } = require("./agentcore-cloud-canary");

const TOKYO_REGION = "ap-northeast-1";
const RELEASE_SHA = "a".repeat(40);

function validResult(overrides = {}) {
  return {
    region: TOKYO_REGION,
    effect: "none",
    release_sha: RELEASE_SHA,
    runtime_resource_arn: "arn:aws:bedrock-agentcore:ap-northeast-1:123456789012:runtime/lm-cl00",
    runtime_session_id: "runtime-session-cl00",
    browser_resource_arn: "arn:aws:bedrock-agentcore:ap-northeast-1:123456789012:browser/lm-cl00",
    browser_session_id: "browser-session-cl00",
    browser_profile_id: "browser-profile-cl00",
    identity_resource_arn: "arn:aws:bedrock-agentcore:ap-northeast-1:123456789012:identity/lm-cl00",
    principal_type: "agent_owned",
    human_input_count: 0,
    usage_receipt_ref: "aws-usage://ap-northeast-1/lm-cl00/receipt-1",
    ...overrides,
  };
}

test("accepts complete Tokyo read-only canary evidence", () => {
  const result = validateCanaryResult(validResult());

  assert.equal(result.region, TOKYO_REGION);
  assert.equal(result.effect, "none");
  assert.match(result.release_sha, /^[a-f0-9]{40}$/);
  assert.ok(result.runtime_session_id);
  assert.ok(result.browser_session_id);
  assert.ok(result.browser_profile_id);
  assert.equal(result.principal_type, "agent_owned");
  assert.equal(result.human_input_count, 0);
  assert.ok(result.usage_receipt_ref);
});

test("rejects a missing Tokyo region", () => {
  assert.throws(
    () => validateCanaryResult(validResult({ region: "" })),
    /region.*ap-northeast-1/i,
  );
});

test("rejects every AgentCore resource ARN outside Tokyo", () => {
  for (const field of [
    "runtime_resource_arn",
    "browser_resource_arn",
    "identity_resource_arn",
  ]) {
    const foreignArn = validResult()[field].replace(TOKYO_REGION, "us-east-1");
    assert.throws(
      () => validateCanaryResult(validResult({ [field]: foreignArn })),
      new RegExp(`${field}.*${TOKYO_REGION}`, "i"),
    );
  }
});

test("rejects a mutable or unpinned release SHA", () => {
  for (const release_sha of ["main", "latest", "a".repeat(39), "A".repeat(40)]) {
    assert.throws(
      () => validateCanaryResult(validResult({ release_sha })),
      /release_sha.*40/i,
    );
  }
});

test("rejects a missing runtime session ID", () => {
  assert.throws(
    () => validateCanaryResult(validResult({ runtime_session_id: "" })),
    /runtime_session_id/i,
  );
});

test("rejects a missing browser session or profile ID", () => {
  for (const field of ["browser_session_id", "browser_profile_id"]) {
    assert.throws(
      () => validateCanaryResult(validResult({ [field]: "" })),
      new RegExp(field, "i"),
    );
  }
});

test("rejects a missing official AWS usage receipt reference", () => {
  assert.throws(
    () => validateCanaryResult(validResult({ usage_receipt_ref: "" })),
    /usage_receipt_ref/i,
  );
});

test("rejects any canary provider effect", () => {
  assert.throws(
    () => validateCanaryResult(validResult({ effect: "browser_write" })),
    /effect.*none/i,
  );
});

test("rejects a human principal or any human input", () => {
  assert.throws(
    () => validateCanaryResult(validResult({ principal_type: "human" })),
    /principal_type.*agent_owned/i,
  );
  assert.throws(
    () => validateCanaryResult(validResult({ human_input_count: 1 })),
    /human_input_count.*0/i,
  );
});
