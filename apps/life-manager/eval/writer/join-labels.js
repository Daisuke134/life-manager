"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const MAX_INPUT_BYTES = 1_000_000;
const HUMAN_LABELS = new Set(["PASS", "FAIL", "NEEDS_CONTEXT"]);
const JUDGE_VERDICTS = new Set(["PASS", "FAIL", "UNKNOWN"]);
const DATASET_PATH = path.resolve(__dirname, "../../../../docs/evals/writer-edd-a8-label-set.md");

function rejectInput() {
  throw new Error("Writer label join rejected input");
}

function exactKeys(row, expected) {
  if (!row || typeof row !== "object" || Array.isArray(row)) return false;
  const actual = Object.keys(row).sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function loadDataset() {
  const bytes = fs.readFileSync(DATASET_PATH);
  const source = bytes.toString("utf8");
  const versionMatch = source.match(/^\*\*Status:\*\*[^\n]*\bv(\d+)\b/mu);
  if (!versionMatch) rejectInput();

  const caseIds = [];
  const seen = new Set();
  for (const match of source.matchAll(/^\|\s*(W-C-\d{3})\s*\|/gmu)) {
    if (seen.has(match[1])) rejectInput();
    seen.add(match[1]);
    caseIds.push(match[1]);
  }
  if (caseIds.length === 0) rejectInput();

  return {
    caseIds,
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

function parseArgs(args) {
  if (args.length !== 4 || args[0] !== "--human-labels" || args[2] !== "--judge-predictions") {
    rejectInput();
  }
  return { humanPath: args[1], predictionPath: args[3] };
}

function validateMetadata(row, dataset) {
  if (row.dataset_version !== dataset.version || row.dataset_sha256 !== dataset.sha256) rejectInput();
  if (typeof row.case_id !== "string" || !dataset.caseIdSet.has(row.case_id)) rejectInput();
}

function validateHumanRows(rows, dataset) {
  const byCaseId = new Map();
  for (const row of rows) {
    if (!exactKeys(row, ["case_id", "dataset_sha256", "dataset_version", "human_label", "human_rationale"])) {
      rejectInput();
    }
    validateMetadata(row, dataset);
    if (byCaseId.has(row.case_id) || !HUMAN_LABELS.has(row.human_label) || typeof row.human_rationale !== "string") {
      rejectInput();
    }
    byCaseId.set(row.case_id, row.human_label);
  }
  return byCaseId;
}

function validatePredictions(rows, dataset) {
  const byCaseId = new Map();
  for (const row of rows) {
    if (!exactKeys(row, ["case_id", "dataset_sha256", "dataset_version", "judge_verdict"])) rejectInput();
    validateMetadata(row, dataset);
    if (byCaseId.has(row.case_id) || !JUDGE_VERDICTS.has(row.judge_verdict)) rejectInput();
    byCaseId.set(row.case_id, row.judge_verdict);
  }
  return byCaseId;
}

function joinLabels(humanRows, predictionRows, dataset = loadDataset()) {
  const humanByCaseId = validateHumanRows(humanRows, dataset);
  const predictionByCaseId = validatePredictions(predictionRows, dataset);

  for (const caseId of predictionByCaseId.keys()) {
    if (!humanByCaseId.has(caseId)) rejectInput();
  }

  return dataset.caseIds
    .filter((caseId) => humanByCaseId.has(caseId))
    .map((caseId) => ({
      case_id: caseId,
      human_label: humanByCaseId.get(caseId),
      judge_verdict: predictionByCaseId.get(caseId) || "UNKNOWN",
    }));
}

function main() {
  try {
    const { humanPath, predictionPath } = parseArgs(process.argv.slice(2));
    const dataset = loadDataset();
    const joined = joinLabels(readJsonl(humanPath), readJsonl(predictionPath), dataset);
    if (joined.length > 0) {
      process.stdout.write(`${joined.map((row) => JSON.stringify(row)).join("\n")}\n`);
    }
  } catch {
    process.stderr.write("Writer label join rejected input\n");
    process.exitCode = 2;
  }
}

if (require.main === module) main();

module.exports = { joinLabels };
