"use strict";

const fs = require("node:fs");

const MIN_PER_CLASS = 20;
const MAX_INPUT_BYTES = 1_000_000;
const CASE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/u;
const HUMAN_LABELS = new Set(["PASS", "FAIL", "NEEDS_CONTEXT"]);
const JUDGE_VERDICTS = new Set(["PASS", "FAIL", "UNKNOWN"]);

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

function validateRows(rows) {
  if (!Array.isArray(rows)) rejectInput();
  const seen = new Set();
  for (const row of rows) {
    if (!row || typeof row !== "object" || Array.isArray(row)) rejectInput();
    const keys = Object.keys(row).sort();
    if (keys.length !== 3
      || keys[0] !== "case_id"
      || keys[1] !== "human_label"
      || keys[2] !== "judge_verdict") rejectInput();
    if (typeof row.case_id !== "string" || !CASE_ID.test(row.case_id) || seen.has(row.case_id)) {
      rejectInput();
    }
    if (!HUMAN_LABELS.has(row.human_label) || !JUDGE_VERDICTS.has(row.judge_verdict)) rejectInput();
    seen.add(row.case_id);
  }
}

function roundedRate(numerator, denominator) {
  return Number((numerator / denominator).toFixed(6));
}

function summarize(rows) {
  validateRows(rows);
  const counts = {
    human_pass: 0,
    human_fail: 0,
    human_needs_context: 0,
    judge_unknown: 0,
    correct_pass: 0,
    correct_fail: 0,
    false_pass: 0,
    false_fail: 0,
  };

  for (const row of rows) {
    if (row.human_label === "NEEDS_CONTEXT") {
      counts.human_needs_context += 1;
      continue;
    }
    counts[`human_${row.human_label.toLowerCase()}`] += 1;
    if (row.judge_verdict === "UNKNOWN") {
      counts.judge_unknown += 1;
      continue;
    }
    if (row.human_label === "PASS") {
      if (row.judge_verdict === "PASS") counts.correct_pass += 1;
      else counts.false_fail += 1;
    } else if (row.judge_verdict === "FAIL") {
      counts.correct_fail += 1;
    } else {
      counts.false_pass += 1;
    }
  }

  const enoughLabels = counts.human_pass >= MIN_PER_CLASS && counts.human_fail >= MIN_PER_CLASS;
  const completePredictions = counts.judge_unknown === 0;
  const status = !enoughLabels
    ? "insufficient_labels"
    : completePredictions ? "metrics_available" : "incomplete_predictions";
  const rates = status !== "metrics_available"
    ? { tpr: null, tnr: null, false_pass_rate: null, false_fail_rate: null }
    : {
      tpr: roundedRate(counts.correct_pass, counts.human_pass),
      tnr: roundedRate(counts.correct_fail, counts.human_fail),
      false_pass_rate: roundedRate(counts.false_pass, counts.human_fail),
      false_fail_rate: roundedRate(counts.false_fail, counts.human_pass),
    };

  return {
    schema_version: 1,
    record_type: "writer_binary_judge_metrics",
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
