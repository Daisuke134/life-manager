"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const GRADER = path.join(__dirname, "receipt-grader.js");
const VALID_FIXTURE = path.join(__dirname, "fixtures", "synthetic-valid-quality-self-heal-v2.json");
const W01_FIXTURE = path.join(__dirname, "fixtures", "w01-empty-input.json");
const W01 = JSON.parse(fs.readFileSync(W01_FIXTURE, "utf8"));

function sha256(bytes) {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

function validInput(overrides = {}) {
  const bytes = fs.readFileSync(VALID_FIXTURE);
  return {
    ...W01,
    case_id: "writer-quality-synthetic-valid-control",
    run_id: "synthetic-writer-run-001",
    artifact_base64: bytes.toString("base64"),
    expected_artifact_sha256: "d43b5f96c1f4d3f1373636c4337db2ec57e6eb5c1fc0941af6e4ae00d21c8bd2",
    prior_receipt_sha256: [],
    publication_status: "draft",
    expected_publication_status: "draft",
    ...overrides,
  };
}

function runGrader(input) {
  const result = spawnSync(process.execPath, [GRADER], {
    input: `${JSON.stringify(input)}\n`,
    encoding: "utf8",
  });
  assert.equal(result.error, undefined, result.error?.message);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stderr, "");
  return JSON.parse(result.stdout);
}

test("W-01 grades the empty receipt without converting unknown quality or net to failure or zero", () => {
  const result = spawnSync(process.execPath, [GRADER], {
    input: `${JSON.stringify(W01)}\n`,
    encoding: "utf8",
  });

  assert.equal(result.error, undefined, result.error?.message);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stderr, "");
  assert.deepEqual(JSON.parse(result.stdout), {
    schema_version: 1,
    record_type: "writer_code_grade",
    case_id: "writer-quality-self-heal-empty-w01",
    run_id: "20261011-210544",
    checks: {
      artifact_hash: "pass",
      receipt_parseability: "fail",
      receipt_schema: "unknown",
      receipt_id: "unknown",
      duplicate_receipt: "unknown",
      publication_status: "pass",
    },
    dimensions: {
      task_completion: "unknown",
      quality: "unknown",
      effect_integrity: "unknown",
      settled_net_minor: null,
    },
    reason_codes: ["quality_self_heal_record_unparseable"],
  });
});

test("a parseable synthetic receipt passes code checks but never asserts article quality or net", () => {
  const result = runGrader(validInput());

  assert.deepEqual(result.checks, {
    artifact_hash: "pass",
    receipt_parseability: "pass",
    receipt_schema: "pass",
    receipt_id: "pass",
    duplicate_receipt: "pass",
    publication_status: "pass",
  });
  assert.deepEqual(result.dimensions, {
    task_completion: "unknown",
    quality: "unknown",
    effect_integrity: "unknown",
    settled_net_minor: null,
  });
});

test("hash tampering and publication mismatch remain separate code-checks", () => {
  const result = runGrader(validInput({
    expected_artifact_sha256: "0".repeat(64),
    publication_status: "published",
    expected_publication_status: "draft",
  }));

  assert.equal(result.checks.artifact_hash, "fail");
  assert.equal(result.checks.receipt_parseability, "pass");
  assert.equal(result.checks.publication_status, "fail");
  assert.ok(result.reason_codes.includes("artifact_sha256_mismatch"));
  assert.ok(result.reason_codes.includes("publication_status_mismatch"));
});

test("duplicate receipt hashes are blocked even when the record and artifact hashes are valid", () => {
  const result = runGrader(validInput({
    prior_receipt_sha256: ["b0d9881778a699cc21ef85e5c42ea9165d317721fab8f62d9c024a241fc2b98b"],
  }));

  assert.equal(result.checks.receipt_id, "pass");
  assert.equal(result.checks.duplicate_receipt, "fail");
  assert.ok(result.reason_codes.includes("duplicate_quality_self_heal_receipt"));
});

test("missing required v2 fields fail schema validation without changing unknown outcomes", () => {
  const record = JSON.parse(fs.readFileSync(VALID_FIXTURE, "utf8"));
  delete record.receipt_snapshots;
  const bytes = Buffer.from(JSON.stringify(record));
  const result = runGrader(validInput({
    artifact_base64: bytes.toString("base64"),
    expected_artifact_sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
  }));

  assert.equal(result.checks.artifact_hash, "pass");
  assert.equal(result.checks.receipt_parseability, "pass");
  assert.equal(result.checks.receipt_schema, "fail");
  assert.equal(result.dimensions.quality, "unknown");
  assert.equal(result.dimensions.settled_net_minor, null);
});

test("a self-hash mismatch fails receipt identity even when artifact integrity matches", () => {
  const record = JSON.parse(fs.readFileSync(VALID_FIXTURE, "utf8"));
  record.receipt_sha256 = "0".repeat(64);
  const bytes = Buffer.from(JSON.stringify(record));
  const result = runGrader(validInput({
    artifact_base64: bytes.toString("base64"),
    expected_artifact_sha256: sha256(bytes),
  }));

  assert.equal(result.checks.artifact_hash, "pass");
  assert.equal(result.checks.receipt_schema, "pass");
  assert.equal(result.checks.receipt_id, "fail");
  assert.ok(result.reason_codes.includes("quality_self_heal_receipt_hash_mismatch"));
});

test("unknown publication state stays unknown rather than becoming a pass or fail", () => {
  const result = runGrader(validInput({
    publication_status: "unknown",
    expected_publication_status: "draft",
  }));

  assert.equal(result.checks.publication_status, "unknown");
});

test("valid JSON that is not a receipt is parseable but fails the receipt schema", () => {
  const bytes = Buffer.from("null");
  const result = runGrader(validInput({
    artifact_base64: bytes.toString("base64"),
    expected_artifact_sha256: sha256(bytes),
  }));

  assert.equal(result.checks.receipt_parseability, "pass");
  assert.equal(result.checks.receipt_schema, "fail");
  assert.equal(result.checks.receipt_id, "fail");
  assert.equal(result.checks.duplicate_receipt, "unknown");
});

test("the stdin grader rejects oversized input without echoing it", () => {
  const privateMarker = "PRIVATE-EVAL-INPUT";
  const result = spawnSync(process.execPath, [GRADER], {
    input: `${privateMarker.repeat(100_000)}\n`,
    encoding: "utf8",
    maxBuffer: 1024 * 1024,
  });

  assert.equal(result.status, 2);
  assert.equal(result.stdout, "");
  assert.equal(result.stderr, "Writer eval rejected input\n");
  assert.equal(result.stderr.includes(privateMarker), false);
});
