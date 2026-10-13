"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");
const { joinLabels, loadDataset, loadReferenceSet } = require("./join-labels.js");

const CLI = path.join(__dirname, "join-labels.js");
const VERSION = "writer-edd-a8-v3";
const DATASET_SHA256 = "355729f17728c1ef8638cde71f8deca44a37619854f1be6995efdd11df3c1f39";
const REFERENCE_VERSION = "writer-edd-a8-reference-v1";
const REFERENCE_SOURCE = "synthetic_policy_reference_v1";
const CASES = new Set([
  1, 4, 5, 8, 10, 12, 13, 16, 18, 19,
  21, 23, 25, 28, 29, 32, 33, 35, 38, 39,
]);

function reference(caseId, label, rationale = "synthetic case reference") {
  return {
    case_id: caseId,
    dataset_version: VERSION,
    dataset_sha256: DATASET_SHA256,
    reference_set_version: REFERENCE_VERSION,
    reference_label: label,
    reference_rationale: rationale,
    reference_source: REFERENCE_SOURCE,
  };
}

function referenceSet() {
  const rows = Array.from({ length: 40 }, (_, index) => {
    const caseId = `W-C-${String(index + 1).padStart(3, "0")}`;
    return reference(caseId, CASES.has(index + 1) ? "PASS" : "FAIL");
  });
  const bytes = `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`;
  return {
    rows,
    version: REFERENCE_VERSION,
    sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
    source: REFERENCE_SOURCE,
  };
}

function prediction(caseId, verdict, referenceSha256) {
  return {
    case_id: caseId,
    dataset_version: VERSION,
    dataset_sha256: DATASET_SHA256,
    reference_set_version: REFERENCE_VERSION,
    reference_set_sha256: referenceSha256,
    judge_verdict: verdict,
  };
}

function runJoin(references, predictions) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "writer-reference-join-"));
  const referencePath = path.join(directory, "reference.jsonl");
  const predictionPath = path.join(directory, "predictions.jsonl");
  const referenceBytes = `${references.map((row) => JSON.stringify(row)).join("\n")}\n`;
  const referenceSha = crypto.createHash("sha256").update(referenceBytes).digest("hex");
  fs.writeFileSync(referencePath, referenceBytes);
  fs.writeFileSync(predictionPath, `${predictions.map((row) => JSON.stringify({
    ...row,
    reference_set_sha256: referenceSha,
  })).join("\n")}\n`);
  const result = spawnSync(process.execPath, [CLI, "--reference-labels", referencePath, "--judge-predictions", predictionPath], {
    encoding: "utf8",
  });
  fs.rmSync(directory, { recursive: true, force: true });
  return result;
}

test("loads the canonical case version and reviewer snapshot", () => {
  const dataset = loadDataset();
  const reviewer = fs.readFileSync(path.resolve(__dirname, "../../../../docs/evals/writer-edd-a8-label-review.html"), "utf8");

  assert.equal(dataset.version, VERSION);
  assert.equal(dataset.sha256, DATASET_SHA256);
  assert.match(reviewer, new RegExp(`const DATASET_SHA256 = "${DATASET_SHA256}";`));
  assert.match(reviewer, /dataset_version: "writer-edd-a8-v3"/u);
  const casesMatch = reviewer.match(/^const CASES = (.+);$/mu);
  assert.ok(casesMatch, "optional audit page has a case list");
  assert.deepEqual(JSON.parse(casesMatch[1]), dataset.cases);
});

test("loads a complete synthetic reference set without human labels", () => {
  const dataset = loadDataset();
  const references = loadReferenceSet();
  const counts = { PASS: 0, FAIL: 0, UNKNOWN: 0 };

  for (const row of references.rows) counts[row.reference_label] += 1;
  assert.equal(references.rows.length, 40);
  assert.equal(references.source, REFERENCE_SOURCE);
  assert.equal(references.sha256.length, 64);
  assert.equal(new Set(references.rows.map((row) => row.case_id)).size, dataset.cases.length);
  assert.deepEqual(counts, { PASS: 20, FAIL: 20, UNKNOWN: 0 });
  assert.ok(references.rows.every((row) => !Object.hasOwn(row, "human_label")
    && !Object.hasOwn(row, "human_rationale")));
});

test("joins fixture references by case ID and keeps missing predictions UNKNOWN", () => {
  const references = referenceSet();
  const result = joinLabels(references, [prediction("W-C-001", "PASS", references.sha256)]);

  assert.deepEqual(result.slice(0, 2), [
    {
      case_id: "W-C-001",
      reference_label: "PASS",
      reference_source: REFERENCE_SOURCE,
      reference_set_version: REFERENCE_VERSION,
      reference_set_sha256: references.sha256,
      judge_verdict: "PASS",
    },
    {
      case_id: "W-C-002",
      reference_label: "FAIL",
      reference_source: REFERENCE_SOURCE,
      reference_set_version: REFERENCE_VERSION,
      reference_set_sha256: references.sha256,
      judge_verdict: "UNKNOWN",
    },
  ]);
  assert.doesNotMatch(JSON.stringify(result), /reference_rationale/u);
});

test("requires exactly 20 PASS and 20 FAIL reference cases", () => {
  const refs = referenceSet();
  refs.rows[0].reference_label = "FAIL";

  assert.throws(() => joinLabels(refs, []), /Writer reference join rejected input/u);
});

test("rejects a reference digest that does not match its contents", () => {
  const references = referenceSet();
  references.sha256 = "0".repeat(64);

  assert.throws(() => joinLabels(references, []), /Writer reference join rejected input/u);
});

test("rejects human-export rows in the standard synthetic-reference path", () => {
  const humanExport = [{
    case_id: "W-C-001",
    dataset_version: VERSION,
    dataset_sha256: DATASET_SHA256,
    human_label: "PASS",
    human_rationale: "PRIVATE_RATIONALE_MARKER",
  }];
  const result = runJoin(humanExport, [prediction("W-C-001", "PASS")]);

  assert.equal(result.status, 2);
  assert.equal(result.stdout, "");
  assert.equal(result.stderr, "Writer reference join rejected input\n");
  assert.equal(result.stderr.includes("PRIVATE_RATIONALE_MARKER"), false);
});

test("rejects mismatched dataset metadata and malformed reference JSONL without echoing it", () => {
  const mismatched = referenceSet().rows;
  mismatched[0] = { ...mismatched[0], dataset_version: "writer-edd-a8-v2" };
  const mismatchResult = runJoin(mismatched, []);
  assert.equal(mismatchResult.status, 2);
  assert.equal(mismatchResult.stderr, "Writer reference join rejected input\n");

  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "writer-reference-join-"));
  const referencePath = path.join(directory, "reference.jsonl");
  const predictionPath = path.join(directory, "predictions.jsonl");
  const marker = "PRIVATE_REFERENCE_MARKER";
  fs.writeFileSync(referencePath, `${marker}{not-json`);
  fs.writeFileSync(predictionPath, "");
  const malformed = spawnSync(process.execPath, [
    CLI,
    "--reference-labels", referencePath,
    "--judge-predictions", predictionPath,
  ], { encoding: "utf8" });
  fs.rmSync(directory, { recursive: true, force: true });

  assert.equal(malformed.status, 2);
  assert.equal(malformed.stdout, "");
  assert.equal(malformed.stderr, "Writer reference join rejected input\n");
  assert.equal(malformed.stderr.includes(marker), false);
});

test("rejects duplicate reference IDs, judge-only cases, and dataset hash mismatch", () => {
  const refs = referenceSet().rows;
  const duplicate = runJoin([refs[0], refs[0], ...refs.slice(2)], [prediction("W-C-001", "PASS")]);
  assert.equal(duplicate.status, 2);
  assert.equal(duplicate.stderr, "Writer reference join rejected input\n");

  const judgeOnly = runJoin(refs, [prediction("W-C-999", "FAIL")]);
  assert.equal(judgeOnly.status, 2);

  const mismatch = [...refs];
  mismatch[0] = { ...mismatch[0], dataset_sha256: "0".repeat(64) };
  const hashMismatch = runJoin(mismatch, []);
  assert.equal(hashMismatch.status, 2);
  assert.equal(hashMismatch.stderr, "Writer reference join rejected input\n");
});
