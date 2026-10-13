"use strict";

const fs = require("node:fs");

const MIN_PER_CLASS = 20;
const MAX_INPUT_BYTES = 1_000_000;
const CASE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/u;
const REFERENCE_SOURCE = "synthetic_policy_reference_v1";
const REFERENCE_LABELS = new Set(["PASS", "FAIL", "UNKNOWN"]);
const JUDGE_VERDICTS = new Set(["PASS", "FAIL", "UNKNOWN"]);
const SHA256 = /^[a-f0-9]{64}$/u;

function rejectInput() {
  throw new Error("Writer metrics input invalid");
}

function parseJsonl(input) {
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

function exactKeys(value, expected) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function validateRows(rows) {
  if (!Array.isArray(rows)) rejectInput();
  const seen = new Set();
  let referenceSetVersion = null;
  let referenceSetSha256 = null;
  for (const row of rows) {
    if (!exactKeys(row, [
      "case_id",
      "judge_verdict",
      "reference_label",
      "reference_set_sha256",
      "reference_set_version",
      "reference_source",
    ])) rejectInput();
    if (typeof row.case_id !== "string" || !CASE_ID.test(row.case_id) || seen.has(row.case_id)) rejectInput();
    if (!REFERENCE_LABELS.has(row.reference_label) || !JUDGE_VERDICTS.has(row.judge_verdict)) rejectInput();
    if (row.reference_source !== REFERENCE_SOURCE
      || typeof row.reference_set_version !== "string"
      || !row.reference_set_version
      || typeof row.reference_set_sha256 !== "string"
      || !SHA256.test(row.reference_set_sha256)) rejectInput();
    if ((referenceSetVersion && referenceSetVersion !== row.reference_set_version)
      || (referenceSetSha256 && referenceSetSha256 !== row.reference_set_sha256)) rejectInput();
    referenceSetVersion = row.reference_set_version;
    referenceSetSha256 = row.reference_set_sha256;
    seen.add(row.case_id);
  }
  return { referenceSetVersion, referenceSetSha256 };
}

function roundedRate(numerator, denominator) {
  return Number((numerator / denominator).toFixed(6));
}

function summarize(rows) {
  const referenceSet = validateRows(rows);
  const counts = {
    reference_pass: 0,
    reference_fail: 0,
    reference_unknown: 0,
    judge_unknown: 0,
    correct_pass: 0,
    correct_fail: 0,
    reference_false_pass: 0,
    reference_false_fail: 0,
  };

  for (const row of rows) {
    if (row.judge_verdict === "UNKNOWN") counts.judge_unknown += 1;
    if (row.reference_label === "UNKNOWN") {
      counts.reference_unknown += 1;
      continue;
    }
    counts[`reference_${row.reference_label.toLowerCase()}`] += 1;
    if (row.judge_verdict === "UNKNOWN") {
      continue;
    }
    if (row.reference_label === "PASS") {
      if (row.judge_verdict === "PASS") counts.correct_pass += 1;
      else counts.reference_false_fail += 1;
    } else if (row.judge_verdict === "FAIL") {
      counts.correct_fail += 1;
    } else {
      counts.reference_false_pass += 1;
    }
  }

  const enoughReferenceCases = counts.reference_pass >= MIN_PER_CLASS && counts.reference_fail >= MIN_PER_CLASS;
  const status = !enoughReferenceCases
    ? "insufficient_reference_cases"
    : counts.judge_unknown > 0
      ? "incomplete_predictions"
      : counts.reference_unknown > 0
        ? "incomplete_reference_cases"
        : "synthetic_reference_metrics_available";
  const rates = status !== "synthetic_reference_metrics_available"
    ? {
      reference_tpr: null,
      reference_tnr: null,
      reference_false_pass_rate: null,
      reference_false_fail_rate: null,
    }
    : {
      reference_tpr: roundedRate(counts.correct_pass, counts.reference_pass),
      reference_tnr: roundedRate(counts.correct_fail, counts.reference_fail),
      reference_false_pass_rate: roundedRate(counts.reference_false_pass, counts.reference_fail),
      reference_false_fail_rate: roundedRate(counts.reference_false_fail, counts.reference_pass),
    };

  return {
    schema_version: 2,
    record_type: "writer_synthetic_reference_metrics",
    scope: "synthetic_reference_agreement",
    reference_source: REFERENCE_SOURCE,
    reference_set_version: referenceSet.referenceSetVersion,
    reference_set_sha256: referenceSet.referenceSetSha256,
    human_validation: "not_performed",
    status,
    counts,
    rates,
  };
}

function main() {
  try {
    if (process.argv.length !== 2) rejectInput();
    const input = fs.readFileSync(0, "utf8");
    process.stdout.write(`${JSON.stringify(summarize(parseJsonl(input)))}\n`);
  } catch {
    process.stderr.write("Writer metrics rejected input\n");
    process.exitCode = 2;
  }
}

if (require.main === module) main();

module.exports = { summarize };
