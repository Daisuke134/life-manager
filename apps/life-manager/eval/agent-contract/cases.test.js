"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { validateCase } = require("./records.js");

const CASES_PATH = path.join(__dirname, "cases.jsonl");

function readCases() {
  return fs.readFileSync(CASES_PATH, "utf8")
    .split("\n")
    .filter((line) => line.trim())
    .map((line, index) => {
      try { return JSON.parse(line); } catch (error) { throw new Error(`case line ${index + 1}: ${error.message}`); }
    });
}

test("EVAL-02 contains five representative failure classes with valid contracts", () => {
  const cases = readCases().map(validateCase);
  assert.equal(cases.length, 5);
  assert.deepEqual(new Set(cases.map((item) => item.case_id)), new Set([
    "coconala-source-outage",
    "lancers-login-unavailable",
    "mercor-auth-save-failure",
    "connector-registration-failure",
    "fundraiser-deadline-failure",
  ]));
  assert.equal(new Set(cases.map((item) => item.split)).size, 2);
  for (const item of cases) {
    assert.equal(item.expected.safety, "pass");
    assert.equal(item.expected.readback, "unknown");
    assert.doesNotMatch(JSON.stringify(item), /password|cookie|token|https?:\/\//i);
  }
});

test("EVAL-02 fixtures reject duplicate case identity and malformed JSONL", () => {
  const cases = readCases();
  assert.throws(() => {
    const duplicate = [...cases, cases[0]];
    const ids = duplicate.map((item) => validateCase(item).case_id);
    if (new Set(ids).size !== ids.length) throw new Error("duplicate case_id");
  }, /duplicate/i);
  assert.throws(() => validateCase({ ...cases[0], case_id: "not valid" }), /case_id/i);
});
