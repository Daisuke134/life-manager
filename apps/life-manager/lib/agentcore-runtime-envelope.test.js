"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  validateRuntimeRequest,
  validateRuntimeResult,
} = require("./agentcore-runtime-envelope.js");

const RELEASE_SHA = "a".repeat(40);
const REQUEST = Object.freeze({
  schema_version: 1,
  tenant_id: "tenant-a",
  job_id: "job-a",
  attempt: 1,
  wake_id: "wake-a",
  release_sha: RELEASE_SHA,
  input_refs: ["lm-resource://state/tenant-a/business-task-a"],
});

const RESULT = Object.freeze({
  tenant_id: "tenant-a",
  job_id: "job-a",
  attempt: 1,
  release_sha: RELEASE_SHA,
  status: "completed",
  receipt_ref: "lm-resource://receipt/tenant-a/business-receipt%3Ajob-a",
  evidence_sha256: "b".repeat(64),
  usage: [{
    provider: "aws",
    resource: "agentcore-runtime",
    quantity: 125,
    unit: "milliseconds",
    cost_usd_micros: 7,
    provider_receipt_id: "usage-a",
  }],
});

test("accepts a bounded reference-only request for the approved immutable release", () => {
  assert.deepEqual(
    validateRuntimeRequest(REQUEST, { approvedReleaseSha: RELEASE_SHA }),
    REQUEST,
  );
});

test("rejects every missing execution identity and a mutable or unapproved release", () => {
  for (const field of ["tenant_id", "job_id", "attempt", "wake_id", "release_sha"]) {
    const invalid = { ...REQUEST };
    delete invalid[field];
    assert.throws(
      () => validateRuntimeRequest(invalid, { approvedReleaseSha: RELEASE_SHA }),
      undefined,
      field,
    );
  }

  for (const releaseSha of ["main", "b".repeat(40)]) {
    assert.throws(
      () => validateRuntimeRequest(
        { ...REQUEST, release_sha: releaseSha },
        { approvedReleaseSha: RELEASE_SHA },
      ),
      /release/i,
    );
  }
});

test("rejects inline credentials, foreign-tenant references, and oversized capsules", () => {
  for (const inline of [
    { password: "human-secret" },
    { api_key: "provider-secret" },
    { cookies: [{ name: "session", value: "secret" }] },
    { payload: { objective: "raw task data" } },
  ]) {
    assert.throws(
      () => validateRuntimeRequest(
        { ...REQUEST, ...inline },
        { approvedReleaseSha: RELEASE_SHA },
      ),
      /field|reference|credential|payload/i,
    );
  }

  assert.throws(
    () => validateRuntimeRequest(
      { ...REQUEST, input_refs: ["lm-resource://state/tenant-b/business-task-a"] },
      { approvedReleaseSha: RELEASE_SHA },
    ),
    /tenant/i,
  );

  assert.throws(
    () => validateRuntimeRequest(
      {
        ...REQUEST,
        input_refs: Array.from(
          { length: 64 },
          (_, index) => `lm-resource://state/tenant-a/${String(index).padStart(3, "0")}-${"x".repeat(300)}`,
        ),
      },
      { approvedReleaseSha: RELEASE_SHA },
    ),
    /large/i,
  );
});

test("accepts only a bounded result tied to the exact request identity", () => {
  assert.deepEqual(validateRuntimeResult(RESULT, REQUEST), RESULT);

  for (const field of ["receipt_ref", "evidence_sha256", "usage"]) {
    const invalid = { ...RESULT };
    delete invalid[field];
    assert.throws(() => validateRuntimeResult(invalid, REQUEST), undefined, field);
  }

  for (const invalid of [
    { ...RESULT, tenant_id: "tenant-b" },
    { ...RESULT, attempt: 2 },
    { ...RESULT, release_sha: "c".repeat(40) },
    { ...RESULT, status: "success" },
    { ...RESULT, receipt_ref: "lm-resource://receipt/tenant-b/foreign" },
    { ...RESULT, evidence_sha256: "not-a-hash" },
    { ...RESULT, usage: [{ ...RESULT.usage[0], cost_usd_micros: 0.5 }] },
    { ...RESULT, usage: [{ ...RESULT.usage[0], provider_receipt_id: "" }] },
    { ...RESULT, raw_output: "unbounded" },
  ]) {
    assert.throws(() => validateRuntimeResult(invalid, REQUEST));
  }
});
