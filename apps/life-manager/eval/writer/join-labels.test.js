"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const CLI = path.join(__dirname, "join-labels.js");
const VERSION = "writer-edd-a8-v2";
const DATASET_SHA256 = "7168b3f762f0b72d9dd8259aad09779a305d3a101a3c1bd4f844b9db78cf9e8d";
const REVIEWER_HTML = path.resolve(__dirname, "../../../../docs/evals/writer-edd-a8-label-review.html");

function human(caseId, label, rationale = "") {
  return {
    case_id: caseId,
    dataset_version: VERSION,
    dataset_sha256: DATASET_SHA256,
    human_label: label,
    human_rationale: rationale,
  };
}

function prediction(caseId, verdict) {
  return {
    case_id: caseId,
    dataset_version: VERSION,
    dataset_sha256: DATASET_SHA256,
    judge_verdict: verdict,
  };
}

function runJoin(humans, predictions) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "writer-label-join-"));
  const humanPath = path.join(directory, "human.jsonl");
  const predictionPath = path.join(directory, "predictions.jsonl");
  fs.writeFileSync(humanPath, humans.map((row) => JSON.stringify(row)).join("\n"));
  fs.writeFileSync(predictionPath, predictions.map((row) => JSON.stringify(row)).join("\n"));
  const result = spawnSync(process.execPath, [CLI, "--human-labels", humanPath, "--judge-predictions", predictionPath], {
    encoding: "utf8",
  });
  fs.rmSync(directory, { recursive: true, force: true });
  return result;
}

test("reviewer export uses the canonical dataset version and hash", () => {
  const reviewer = fs.readFileSync(REVIEWER_HTML, "utf8");

  assert.match(reviewer, new RegExp(`const DATASET_SHA256 = "${DATASET_SHA256}";`));
  assert.match(reviewer, /dataset_version: "writer-edd-a8-v2"/u);
});

test("joins by case ID, orders by canonical case order, and leaves a missing verdict UNKNOWN", () => {
  const result = runJoin(
    [human("W-C-002", "FAIL", "Private spec reference"), human("W-C-001", "PASS", "Public CTA")],
    [prediction("W-C-001", "PASS")],
  );

  assert.equal(result.error, undefined, result.error?.message);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stderr, "");
  assert.deepEqual(result.stdout.trim().split("\n").map((line) => JSON.parse(line)), [
    { case_id: "W-C-001", human_label: "PASS", judge_verdict: "PASS" },
    { case_id: "W-C-002", human_label: "FAIL", judge_verdict: "UNKNOWN" },
  ]);
});

test("preserves NEEDS_CONTEXT and does not require a judge verdict for it", () => {
  const result = runJoin([human("W-C-003", "NEEDS_CONTEXT", "Public status unclear")], []);

  assert.equal(result.error, undefined, result.error?.message);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), {
    case_id: "W-C-003",
    human_label: "NEEDS_CONTEXT",
    judge_verdict: "UNKNOWN",
  });
});

test("rejects dataset hash mismatch without echoing input", () => {
  const marker = "PRIVATE-ARTICLE-MARKER";
  const bad = human("W-C-001", "PASS", marker);
  bad.dataset_sha256 = "0".repeat(64);
  const result = runJoin([bad], [prediction("W-C-001", "PASS")]);

  assert.equal(result.status, 2);
  assert.equal(result.stdout, "");
  assert.equal(result.stderr, "Writer label join rejected input\n");
  assert.equal(result.stderr.includes(marker), false);
});

test("rejects dataset version mismatch", () => {
  const bad = human("W-C-001", "PASS");
  bad.dataset_version = "writer-edd-a8-v1";
  const result = runJoin([bad], []);

  assert.equal(result.status, 2);
  assert.equal(result.stdout, "");
  assert.equal(result.stderr, "Writer label join rejected input\n");
});

test("rejects duplicate labels and judge-only cases", () => {
  const duplicate = runJoin(
    [human("W-C-001", "PASS"), human("W-C-001", "FAIL")],
    [prediction("W-C-001", "PASS")],
  );
  assert.equal(duplicate.status, 2);
  assert.equal(duplicate.stderr, "Writer label join rejected input\n");

  const extraPrediction = runJoin(
    [human("W-C-001", "PASS")],
    [prediction("W-C-001", "PASS"), prediction("W-C-002", "FAIL")],
  );
  assert.equal(extraPrediction.status, 2);
  assert.equal(extraPrediction.stderr, "Writer label join rejected input\n");
});

test("rejects a case ID outside the canonical v2 dataset", () => {
  const result = runJoin([human("W-C-999", "PASS")], [prediction("W-C-999", "PASS")]);

  assert.equal(result.status, 2);
  assert.equal(result.stdout, "");
  assert.equal(result.stderr, "Writer label join rejected input\n");
});

test("rejects malformed JSONL without echoing the source text", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "writer-label-join-"));
  const humanPath = path.join(directory, "human.jsonl");
  const predictionPath = path.join(directory, "predictions.jsonl");
  const marker = "PRIVATE-ARTICLE-MARKER";
  fs.writeFileSync(humanPath, `${marker}{not-json`);
  fs.writeFileSync(predictionPath, "");
  const result = spawnSync(process.execPath, [CLI, "--human-labels", humanPath, "--judge-predictions", predictionPath], {
    encoding: "utf8",
  });
  fs.rmSync(directory, { recursive: true, force: true });

  assert.equal(result.status, 2);
  assert.equal(result.stdout, "");
  assert.equal(result.stderr, "Writer label join rejected input\n");
  assert.equal(result.stderr.includes(marker), false);
});
