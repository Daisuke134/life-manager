"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const MAX_INPUT_BYTES = 1_000_000;
const REFERENCE_LABELS = new Set(["PASS", "FAIL", "UNKNOWN"]);
const JUDGE_VERDICTS = new Set(["PASS", "FAIL", "UNKNOWN"]);
const REFERENCE_SOURCE = "synthetic_policy_reference_v1";
const DATASET_PATH = path.resolve(__dirname, "../../../../docs/evals/writer-edd-a8-label-set.md");
const REFERENCE_PATH = path.resolve(__dirname, "fixtures/a8-category-c-reference-v1.jsonl");

function rejectInput(errorClass = "invalid_reference_labels") {
  const error = new Error("Writer reference join rejected input");
  error.code = errorClass;
  throw error;
}

function exactKeys(value, expected) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function loadDataset() {
  const bytes = fs.readFileSync(DATASET_PATH);
  const source = bytes.toString("utf8");
  const versionMatch = source.match(/^\*\*Status:\*\* synthetic case set v(\d+)\b/mu);
  if (!versionMatch) rejectInput();

  const cases = [];
  const seen = new Set();
  for (const line of source.split(/\r?\n/u)) {
    if (!/^\|\s*W-C-\d{3}\s*\|/u.test(line)) continue;
    const match = line.match(/^\|\s*(W-C-\d{3})\s*\|\s*(.*?)\s*\|\s*\|\s*\|$/u);
    if (!match || seen.has(match[1])) rejectInput();
    seen.add(match[1]);
    cases.push({ case_id: match[1], excerpt: match[2] });
  }
  if (cases.length === 0) rejectInput();

  return {
    cases,
    caseIds: cases.map((item) => item.case_id),
    caseIdSet: seen,
    version: `writer-edd-a8-v${versionMatch[1]}`,
    sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
  };
}

function readJsonl(filePath) {
  let input;
  try {
    input = fs.readFileSync(filePath, "utf8");
  } catch {
    rejectInput();
  }
  if (Buffer.byteLength(input, "utf8") > MAX_INPUT_BYTES) rejectInput();

  return input.split(/\r?\n/u)
    .filter((line) => line.trim() !== "")
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        rejectInput();
      }
    });
}

function loadReferenceSet(filePath = REFERENCE_PATH, dataset = loadDataset()) {
  let bytes;
  try {
    bytes = fs.readFileSync(filePath);
  } catch {
    rejectInput();
  }
  if (bytes.length > MAX_INPUT_BYTES) rejectInput();
  const rows = readJsonl(filePath);
  const canonicalBytes = Buffer.from(`${rows.map((row) => JSON.stringify(row)).join("\n")}\n`);
  if (!bytes.equals(canonicalBytes)) rejectInput();
  const byCaseId = validateReferenceRows(rows, dataset);
  const first = rows[0];
  return {
    rows,
    version: first.reference_set_version,
    sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
    source: first.reference_source,
  };
}

function validateReferenceRows(rows, dataset) {
  if (!Array.isArray(rows) || rows.length !== dataset.cases.length || rows.length === 0) rejectInput();
  const byCaseId = new Map();
  let source;
  let version;
  const counts = { PASS: 0, FAIL: 0, UNKNOWN: 0 };
  for (const row of rows) {
    if (!exactKeys(row, [
      "case_id",
      "dataset_sha256",
      "dataset_version",
      "reference_label",
      "reference_rationale",
      "reference_set_version",
      "reference_source",
    ])) rejectInput();
    if (row.dataset_version !== dataset.version || row.dataset_sha256 !== dataset.sha256) rejectInput();
    if (typeof row.case_id !== "string" || !dataset.caseIdSet.has(row.case_id) || byCaseId.has(row.case_id)) rejectInput();
    if (!REFERENCE_LABELS.has(row.reference_label) || typeof row.reference_rationale !== "string") rejectInput();
    if (row.reference_source !== REFERENCE_SOURCE
      || typeof row.reference_set_version !== "string"
      || !/^writer-edd-a8-reference-v\d+$/u.test(row.reference_set_version)) rejectInput();
    if ((source && source !== row.reference_source) || (version && version !== row.reference_set_version)) rejectInput();
    source = row.reference_source;
    version = row.reference_set_version;
    counts[row.reference_label] += 1;
    byCaseId.set(row.case_id, row.reference_label);
  }

  if (dataset.caseIds.some((caseId) => !byCaseId.has(caseId))) rejectInput();
  if (counts.PASS < 20 || counts.FAIL < 20) rejectInput("insufficient_reference_labels");
  return byCaseId;
}

function parseArgs(args) {
  if (args.length !== 4 || args[0] !== "--reference-labels" || !args[1]
    || args[2] !== "--judge-predictions" || !args[3]) rejectInput();
  return { referencePath: args[1], predictionPath: args[3] };
}

function validatePredictions(rows, dataset, referenceSet) {
  const byCaseId = new Map();
  for (const row of rows) {
    if (!exactKeys(row, [
      "case_id",
      "dataset_sha256",
      "dataset_version",
      "judge_verdict",
      "reference_set_sha256",
      "reference_set_version",
    ])) rejectInput();
    if (row.dataset_version !== dataset.version || row.dataset_sha256 !== dataset.sha256
      || row.reference_set_version !== referenceSet.version || row.reference_set_sha256 !== referenceSet.sha256) rejectInput();
    if (typeof row.case_id !== "string" || !referenceSet.byCaseId.has(row.case_id) || byCaseId.has(row.case_id)) rejectInput();
    if (!JUDGE_VERDICTS.has(row.judge_verdict)) rejectInput();
    byCaseId.set(row.case_id, row.judge_verdict);
  }
  return byCaseId;
}

function joinLabels(referenceSet, predictionRows, dataset = loadDataset()) {
  if (!referenceSet || !Array.isArray(referenceSet.rows)) rejectInput();
  const byCaseId = validateReferenceRows(referenceSet.rows, dataset);
  const canonicalBytes = Buffer.from(`${referenceSet.rows.map((row) => JSON.stringify(row)).join("\n")}\n`);
  const canonicalSha256 = crypto.createHash("sha256").update(canonicalBytes).digest("hex");
  if (!/^[a-f0-9]{64}$/u.test(referenceSet.sha256)
    || referenceSet.sha256 !== canonicalSha256
    || typeof referenceSet.version !== "string"
    || referenceSet.source !== REFERENCE_SOURCE) rejectInput();
  const predictionByCaseId = validatePredictions(predictionRows, dataset, {
    ...referenceSet,
    byCaseId,
  });

  for (const caseId of predictionByCaseId.keys()) {
    if (!byCaseId.has(caseId)) rejectInput();
  }

  return dataset.caseIds.map((caseId) => {
    return {
      case_id: caseId,
      reference_label: byCaseId.get(caseId),
      reference_source: referenceSet.source,
      reference_set_version: referenceSet.version,
      reference_set_sha256: referenceSet.sha256,
      judge_verdict: predictionByCaseId.get(caseId) || "UNKNOWN",
    };
  });
}

function main() {
  try {
    const { referencePath, predictionPath } = parseArgs(process.argv.slice(2));
    const dataset = loadDataset();
    const referenceSet = loadReferenceSet(referencePath, dataset);
    const joined = joinLabels(referenceSet, readJsonl(predictionPath), dataset);
    if (joined.length > 0) {
      process.stdout.write(`${joined.map((row) => JSON.stringify(row)).join("\n")}\n`);
    }
  } catch {
    process.stderr.write("Writer reference join rejected input\n");
    process.exitCode = 2;
  }
}

if (require.main === module) main();

module.exports = { joinLabels, loadDataset, loadReferenceSet, readJsonl };
