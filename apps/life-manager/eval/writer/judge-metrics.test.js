"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const CLI = path.join(__dirname, "judge-metrics.js");
const SOURCE = "synthetic_policy_reference_v1";
const VERSION = "writer-edd-a8-reference-v1";
const SHA = "a".repeat(64);

function row(caseId, referenceLabel, judgeVerdict, overrides = {}) {
  return {
    case_id: caseId,
    reference_label: referenceLabel,
    reference_source: SOURCE,
    reference_set_version: VERSION,
    reference_set_sha256: SHA,
    judge_verdict: judgeVerdict,
    ...overrides,
  };
}

function invoke(rows) {
  return spawnSync(process.execPath, [CLI], {
    input: `${rows.map((item) => JSON.stringify(item)).join("\n")}\n`,
    encoding: "utf8",
  });
}

test("does not emit reference rates until both synthetic classes reach 20", () => {
  const rows = [
    ...Array.from({ length: 19 }, (_, index) => row(`p-${index}`, "PASS", "PASS")),
    ...Array.from({ length: 20 }, (_, index) => row(`f-${index}`, "FAIL", "FAIL")),
  ];
  const result = invoke(rows);

  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), {
    schema_version: 2,
    record_type: "writer_synthetic_reference_metrics",
    scope: "synthetic_reference_agreement",
    reference_source: SOURCE,
    reference_set_version: VERSION,
    reference_set_sha256: SHA,
    human_validation: "not_performed",
    status: "insufficient_reference_cases",
    counts: {
      reference_pass: 19,
      reference_fail: 20,
      reference_unknown: 0,
      judge_unknown: 0,
      correct_pass: 19,
      correct_fail: 20,
      reference_false_pass: 0,
      reference_false_fail: 0,
    },
    rates: {
      reference_tpr: null,
      reference_tnr: null,
      reference_false_pass_rate: null,
      reference_false_fail_rate: null,
    },
  });
});

test("reports distinct fixture false-pass and false-fail rates with provenance", () => {
  const rows = [
    ...Array.from({ length: 19 }, (_, index) => row(`p-${index}`, "PASS", "PASS")),
    row("p-19", "PASS", "FAIL"),
    ...Array.from({ length: 18 }, (_, index) => row(`f-${index}`, "FAIL", "FAIL")),
    row("f-18", "FAIL", "PASS"),
    row("f-19", "FAIL", "PASS"),
  ];
  const result = invoke(rows);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stderr, "");
  assert.deepEqual(JSON.parse(result.stdout), {
    schema_version: 2,
    record_type: "writer_synthetic_reference_metrics",
    scope: "synthetic_reference_agreement",
    reference_source: SOURCE,
    reference_set_version: VERSION,
    reference_set_sha256: SHA,
    human_validation: "not_performed",
    status: "synthetic_reference_metrics_available",
    counts: {
      reference_pass: 20,
      reference_fail: 20,
      reference_unknown: 0,
      judge_unknown: 0,
      correct_pass: 19,
      correct_fail: 18,
      reference_false_pass: 2,
      reference_false_fail: 1,
    },
    rates: {
      reference_tpr: 0.95,
      reference_tnr: 0.9,
      reference_false_pass_rate: 0.1,
      reference_false_fail_rate: 0.05,
    },
  });
});

test("keeps unknown references and judge verdicts out of reference rates", () => {
  const rows = [
    ...Array.from({ length: 20 }, (_, index) => row(`p-${index}`, "PASS", "PASS")),
    ...Array.from({ length: 19 }, (_, index) => row(`f-${index}`, "FAIL", "FAIL")),
    row("f-19", "FAIL", "UNKNOWN"),
    row("context-1", "UNKNOWN", "UNKNOWN"),
  ];
  const result = invoke(rows);
  assert.equal(result.status, 0, result.stderr);
  const summary = JSON.parse(result.stdout);
  assert.equal(summary.status, "incomplete_predictions");
  assert.deepEqual(summary.counts, {
    reference_pass: 20,
    reference_fail: 20,
    reference_unknown: 1,
    judge_unknown: 2,
    correct_pass: 20,
    correct_fail: 19,
    reference_false_pass: 0,
    reference_false_fail: 0,
  });
  assert.deepEqual(summary.rates, {
    reference_tpr: null,
    reference_tnr: null,
    reference_false_pass_rate: null,
    reference_false_fail_rate: null,
  });
});

test("rejects human labels, mixed reference sets, and duplicate IDs without echoing input", () => {
  const marker = "PRIVATE-ARTICLE-MARKER";
  const human = invoke([{
    case_id: marker,
    human_label: "PASS",
    human_rationale: marker,
    judge_verdict: "PASS",
  }]);
  assert.equal(human.status, 2);
  assert.equal(human.stdout, "");
  assert.equal(human.stderr, "Writer metrics rejected input\n");
  assert.equal(human.stderr.includes(marker), false);

  const duplicateRows = [row("x", "PASS", "PASS"), row("x", "FAIL", "FAIL")];
  assert.equal(invoke(duplicateRows).status, 2);

  const mixedRows = [row("x", "PASS", "PASS"), row("y", "FAIL", "FAIL", { reference_set_sha256: "b".repeat(64) })];
  assert.equal(invoke(mixedRows).status, 2);
});
