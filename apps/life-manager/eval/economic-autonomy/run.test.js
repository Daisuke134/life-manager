"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const {
  FIXTURES_DIR,
  evaluateCase,
  parseCasesText,
  runCorpus,
} = require("./run.js");

const CASES_PATH = path.join(__dirname, "cases.jsonl");

function sha256(bytes) {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

test("case corpus has verified fixtures and balanced tuning and held-out splits", () => {
  const cases = parseCasesText(fs.readFileSync(CASES_PATH, "utf8"));
  assert.equal(cases.length, 4);
  for (const item of cases) {
    const filename = new URL(item.fixture_ref).pathname.slice(1);
    const bytes = fs.readFileSync(path.join(FIXTURES_DIR, filename));
    assert.equal(sha256(bytes), item.input_sha256);
  }
  for (const split of ["tuning", "held_out"]) {
    const splitCases = cases.filter((item) => item.split === split);
    assert.equal(splitCases.length, 2);
    assert.deepEqual(new Set(splitCases.map((item) => item.expected.eligible)), new Set([true, false]));
  }
});

test("runner scores every case exactly once and matches all expected fields", () => {
  const result = runCorpus(CASES_PATH);
  const cases = parseCasesText(fs.readFileSync(CASES_PATH, "utf8"));
  assert.equal(result.run.status, "completed");
  assert.equal(result.scores.length, cases.length);
  assert.equal(new Set(result.scores.map((score) => score.case_id)).size, cases.length);
  assert.deepEqual(
    result.scores.map((score) => score.case_id),
    cases.map((item) => item.case_id),
  );
  assert.deepEqual(
    new Set(result.scores.filter((score) => score.case_id.includes("fundraising")
      || score.case_id.includes("duplicate")).map((score) => score.case_id)),
    new Set(["fundraising-not-mrr", "duplicate-receipt-block"]),
  );
  for (const [index, score] of result.scores.entries()) {
    const expected = cases[index].expected;
    assert.equal(score.eligible, expected.eligible);
    assert.equal(score.settled_net_profit_minor, expected.settled_net_profit_minor);
    assert.equal(score.recurring_revenue_minor, expected.recurring_revenue_minor);
    assert.deepEqual(score.reason_codes, expected.reason_codes);
  }
});

test("CLI emits only validated run and score records without fixture or private data", () => {
  const result = spawnSync(process.execPath, [path.join(__dirname, "run.js"), "--cases", CASES_PATH], {
    cwd: path.dirname(__dirname),
    encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stderr, "");
  const rows = result.stdout.trim().split("\n").map((line) => JSON.parse(line));
  assert.equal(rows[0].record_type, "economic_autonomy_run");
  assert.equal(rows.filter((row) => row.record_type === "economic_autonomy_score").length, 4);
  for (const forbidden of [
    "financialRecords", "attributions", "autonomyEvents", "tenant-a",
    "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    FIXTURES_DIR, os.homedir(),
  ]) assert.equal(result.stdout.includes(forbidden), false, forbidden);
});

test("runner is deterministic, read-only, and has no network surface", () => {
  const source = fs.readFileSync(path.join(__dirname, "run.js"), "utf8");
  for (const forbidden of [
    "node:http", "node:https", "node:net", "node:dns", "fetch(",
    "writeFile", "appendFile", "createWriteStream",
  ]) assert.equal(source.includes(forbidden), false, forbidden);
  const before = fs.readdirSync(FIXTURES_DIR).sort();
  const first = JSON.stringify(runCorpus(CASES_PATH));
  const second = JSON.stringify(runCorpus(CASES_PATH));
  assert.equal(first, second);
  assert.deepEqual(fs.readdirSync(FIXTURES_DIR).sort(), before);
});

test("fixture-byte tampering fails before scoring", () => {
  const item = parseCasesText(fs.readFileSync(CASES_PATH, "utf8"))[0];
  assert.throws(() => evaluateCase(item, {
    readFixture() { return Buffer.from("tampered\n", "utf8"); },
    runId: "run-tampered",
  }), /fixture hash mismatch/u);
});

test("an extra case key fails the exact record contract", () => {
  const first = JSON.parse(fs.readFileSync(CASES_PATH, "utf8").split("\n")[0]);
  first.unexpected = true;
  assert.throws(() => parseCasesText(`${JSON.stringify(first)}\n`), /case invalid/u);
});

test("an expected-result mismatch fails the run", () => {
  const item = JSON.parse(JSON.stringify(
    parseCasesText(fs.readFileSync(CASES_PATH, "utf8"))[0],
  ));
  item.expected.settled_net_profit_minor += 1;
  assert.throws(() => evaluateCase(item, { runId: "run-mismatch" }), /expected mismatch/u);
});
