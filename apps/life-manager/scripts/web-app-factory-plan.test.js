"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const cli = path.join(__dirname, "web-app-factory-plan.js");
const example = fs.readFileSync(path.join(__dirname, "../examples/web-app-factory/example.json"), "utf8");
function run(input = example, args = ["--now", "2026-10-08T09:00:00Z"], options = {}) {
  return spawnSync(process.execPath, [cli, ...args], { input, encoding: "utf8", timeout: 5000, ...options });
}
test("stdin sample yields a deterministic blocked plan, never deployment or revenue", () => {
  const result = run();
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.equal(report.next_task, "resolve_ownership");
  assert.equal(report.observed_at, "2026-10-08T09:00:00.000Z");
  assert.equal(report.metrics.revenue_minor.value, null);
  assert.equal(report.external_effects, false);
});
test("malformed, excess and unknown fields fail without echoing input", () => {
  for (const input of ["{ secret-password", "x".repeat(1_048_577), example.replace('"schema_version": 1', '"schema_version": 1, "secret": "secret-password"')]) {
    const result = run(input);
    assert.equal(result.status, 1);
    assert.equal(result.stdout, "");
    assert.equal(result.stderr, "web-app-factory: invalid input or arguments\n");
  }
});
test("paid budget and unsupported CLI options cannot enable effects", () => {
  assert.equal(run(example.replace('"additional_spend_minor": 0', '"additional_spend_minor": 1')).status, 1);
  assert.equal(run(example, ["--execute"]).status, 1);
  assert.equal(run(example, ["--now"]).status, 1);
});
test("planning leaves caller files untouched and does not expose environment credentials", () => {
  const cwd = fs.mkdtempSync(path.join(os.tmpdir(), "factory-cli-test-"));
  try {
    fs.writeFileSync(path.join(cwd, "sentinel"), "unchanged");
    const result = run(example, ["--now", "2026-10-08T09:00:00Z"], { cwd, env: { PATH: process.env.PATH, API_KEY: "secret-from-env" } });
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout.includes("secret-from-env"), false);
    assert.deepEqual(fs.readdirSync(cwd), ["sentinel"]);
    assert.equal(fs.readFileSync(path.join(cwd, "sentinel"), "utf8"), "unchanged");
  } finally { fs.rmSync(cwd, { recursive: true }); }
});
