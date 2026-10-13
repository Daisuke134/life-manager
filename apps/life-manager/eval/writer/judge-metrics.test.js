"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const CLI = path.join(__dirname, "judge-metrics.js");

function row(caseId, humanLabel, judgeVerdict) {
  return { case_id: caseId, human_label: humanLabel, judge_verdict: judgeVerdict };
}

function invoke(rows) {
  return spawnSync(process.execPath, [CLI], {
    input: `${rows.map((item) => JSON.stringify(item)).join("\n")}\n`,
    encoding: "utf8",
  });
}

test("does not emit rates until both human classes reach 20", () => {
  const rows = [
    ...Array.from({ length: 19 }, (_, index) => row(`p-${index}`, "PASS", "PASS")),
    ...Array.from({ length: 20 }, (_, index) => row(`f-${index}`, "FAIL", "FAIL")),
  ];
  const result = invoke(rows);

  assert.equal(result.error, undefined, result.error?.message);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stderr, "");
  assert.deepEqual(JSON.parse(result.stdout), {
    schema_version: 1,
    record_type: "writer_binary_judge_metrics",
    status: "insufficient_labels",
    counts: {
      human_pass: 19,
      human_fail: 20,
      human_needs_context: 0,
      judge_unknown: 0,
      correct_pass: 19,
      correct_fail: 20,
      false_pass: 0,
      false_fail: 0,
    },
    rates: {
      tpr: null,
      tnr: null,
      false_pass_rate: null,
      false_fail_rate: null,
    },
  });
});

test("separates false-pass and false-fail and uses human PASS as positive", () => {
  const rows = [
    ...Array.from({ length: 19 }, (_, index) => row(`p-${index}`, "PASS", "PASS")),
    row("p-19", "PASS", "FAIL"),
    ...Array.from({ length: 18 }, (_, index) => row(`f-${index}`, "FAIL", "FAIL")),
    row("f-18", "FAIL", "PASS"),
    row("f-19", "FAIL", "PASS"),
  ];
  const result = invoke(rows);

  assert.equal(result.error, undefined, result.error?.message);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stderr, "");
  assert.deepEqual(JSON.parse(result.stdout), {
    schema_version: 1,
    record_type: "writer_binary_judge_metrics",
    status: "metrics_available",
    counts: {
      human_pass: 20,
      human_fail: 20,
      human_needs_context: 0,
      judge_unknown: 0,
      correct_pass: 19,
      correct_fail: 18,
      false_pass: 2,
      false_fail: 1,
    },
    rates: {
      tpr: 0.95,
      tnr: 0.9,
      false_pass_rate: 0.1,
      false_fail_rate: 0.05,
    },
  });
});

test("keeps NEEDS_CONTEXT and UNKNOWN out of rates", () => {
  const rows = [
    ...Array.from({ length: 20 }, (_, index) => row(`p-${index}`, "PASS", "PASS")),
    ...Array.from({ length: 19 }, (_, index) => row(`f-${index}`, "FAIL", "FAIL")),
    row("f-19", "FAIL", "UNKNOWN"),
    row("context-1", "NEEDS_CONTEXT", "UNKNOWN"),
  ];
  const result = invoke(rows);

  assert.equal(result.error, undefined, result.error?.message);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stderr, "");
  assert.deepEqual(JSON.parse(result.stdout), {
    schema_version: 1,
    record_type: "writer_binary_judge_metrics",
    status: "incomplete_predictions",
    counts: {
      human_pass: 20,
      human_fail: 20,
      human_needs_context: 1,
      judge_unknown: 1,
      correct_pass: 20,
      correct_fail: 19,
      false_pass: 0,
      false_fail: 0,
    },
    rates: {
      tpr: null,
      tnr: null,
      false_pass_rate: null,
      false_fail_rate: null,
    },
  });
});

test("rejects duplicate case IDs without echoing input", () => {
  const marker = "PRIVATE-ARTICLE-MARKER";
  const rows = [
    row(marker, "PASS", "PASS"),
    row(marker, "FAIL", "FAIL"),
  ];
  const result = invoke(rows);

  assert.equal(result.status, 2);
  assert.equal(result.stdout, "");
  assert.equal(result.stderr, "Writer metrics rejected input\n");
  assert.equal(result.stderr.includes(marker), false);
});

test("rejects invalid labels without echoing the submitted content", () => {
  const marker = "PRIVATE-ARTICLE-MARKER";
  const result = invoke([
    row("case-1", marker, "PASS"),
  ]);

  assert.equal(result.status, 2);
  assert.equal(result.stdout, "");
  assert.equal(result.stderr, "Writer metrics rejected input\n");
  assert.equal(result.stderr.includes(marker), false);
});
