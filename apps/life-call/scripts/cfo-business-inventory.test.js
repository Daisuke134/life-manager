"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const { sha256Canonical } = require("../lib/cfo-registry.js");
const { main, repoEvidenceExists } = require("./cfo-business-inventory.js");

const NOW = new Date("2026-08-08T00:00:00.000Z");
const UUID = "00000000-0000-4000-8000-000000000001";
const FIXTURE = [
  "PID Status Label",
  "123 0 ai.anicca.writer-report",
  "- 7 ai.anicca.cfo-controller",
  "456 0 ai.anicca.x402-monitor",
  "- 0 com.apple.other",
].join("\n");
const UNMAPPED_FIXTURE = [FIXTURE, "- 0 ai.anicca.franklin3-loop"].join("\n");

function tempStateRoot() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "cfo-business-inventory-"));
}

function run(stateRoot, launchctlText = FIXTURE, uuid = UUID) {
  const output = [];
  const launchctlCalls = [];
  const result = main({
    env: { LIFE_MANAGER_STATE_HOME: stateRoot },
    now: () => new Date(NOW),
    randomUUID: () => uuid,
    launchctlList: (...args) => {
      launchctlCalls.push(args);
      return launchctlText;
    },
    stdout: (line) => output.push(line),
  });
  assert.equal(output.length, 1);
  assert.deepEqual(launchctlCalls, [[]]);
  return { result, summary: JSON.parse(output[0]), output };
}

function receiptDir(stateRoot) {
  return path.join(stateRoot, "cfo", "business-inventory");
}

function onlyReceipt(stateRoot) {
  const names = fs.readdirSync(receiptDir(stateRoot));
  assert.equal(names.length, 1);
  return path.join(receiptDir(stateRoot), names[0]);
}

test("writes one redacted pass receipt from launchctl observations", () => {
  const stateRoot = tempStateRoot();
  try {
    const { result, summary, output } = run(stateRoot);
    assert.equal(result.exitCode, 0);
    assert.deepEqual(Object.keys(summary), [
      "result", "receipt_path", "registry_sha256", "observation_hash",
      "unit_count", "unmapped_count", "ambiguous_count",
    ]);
    assert.equal(summary.result, "pass");
    assert.equal(summary.unit_count, 9);
    assert.equal(summary.unmapped_count, 0);
    assert.equal(summary.ambiguous_count, 0);
    assert.doesNotMatch(output[0], /secret|token|payload|amount|balance|revenue|profit/i);

    const receiptPath = onlyReceipt(stateRoot);
    assert.equal(receiptPath, summary.receipt_path);
    assert.match(receiptPath, /2026-08-08T00-00-00\.000Z--00000000-0000-4000-8000-000000000001\.json$/);
    assert.equal(fs.statSync(path.join(stateRoot, "cfo")).mode & 0o777, 0o700);
    assert.equal(fs.statSync(receiptDir(stateRoot)).mode & 0o777, 0o700);
    assert.equal(fs.statSync(receiptPath).mode & 0o777, 0o600);

    const receipt = JSON.parse(fs.readFileSync(receiptPath, "utf8"));
    assert.equal(receipt.registry_sha256, summary.registry_sha256);
    assert.equal(receipt.observation_hash, summary.observation_hash);
    assert.equal(receipt.observation_hash, sha256Canonical({
      receipt_version: receipt.receipt_version,
      registry_sha256: receipt.registry_sha256,
      financial_units: receipt.financial_units,
      runtime_observations: receipt.runtime_observations,
      source_observations: receipt.source_observations,
      ledger_observations: receipt.ledger_observations,
      unmapped_relevant_labels: receipt.unmapped_relevant_labels,
      ambiguous_labels: receipt.ambiguous_labels,
      result: receipt.result,
    }));
    assert.equal(Object.hasOwn(receipt, "raw_payload"), false);
  } finally {
    fs.rmSync(stateRoot, { recursive: true, force: true });
  }
});

test("writes an immutable failure receipt for unmapped relevant labels", () => {
  const stateRoot = tempStateRoot();
  try {
    const { result, summary } = run(stateRoot, UNMAPPED_FIXTURE, "00000000-0000-4000-8000-000000000002");
    assert.equal(result.exitCode, 1);
    assert.equal(summary.result, "fail");
    assert.equal(summary.unmapped_count, 1);
    assert.equal(summary.ambiguous_count, 0);
    const receiptPath = onlyReceipt(stateRoot);
    const receipt = JSON.parse(fs.readFileSync(receiptPath, "utf8"));
    assert.equal(receipt.result, "fail");
    assert.deepEqual(receipt.unmapped_relevant_labels, ["ai.anicca.franklin3-loop"]);
    assert.equal(fs.statSync(receiptPath).mode & 0o777, 0o600);
  } finally {
    fs.rmSync(stateRoot, { recursive: true, force: true });
  }
});

test("receipt contains exactly one redacted ledger observation per catalogue entry", () => {
  const stateRoot = tempStateRoot();
  try {
    const { result, summary } = run(stateRoot);
    assert.equal(result.exitCode, 0);
    const receipt = JSON.parse(fs.readFileSync(onlyReceipt(stateRoot), "utf8"));
    assert.equal(receipt.ledger_observations.length, 9);
    assert.deepEqual(receipt.ledger_observations.map((item) => item.ledger_source_id), [
      "affiliate_commission_receipts", "capafy_sales_receipts", "gig_payment_receipts",
      "lm_agent_earnings", "payroll_bank_receipts", "proprietary_investing_receipts",
      "revenuecat_subscription_events", "writer_receipts", "x402_settlement_receipts",
    ]);
    assert.ok(receipt.ledger_observations.every((item) => Object.keys(item).every((key) => [
      "ledger_source_id", "availability", "evidence_count",
    ].includes(key))));
    assert.doesNotMatch(JSON.stringify(receipt.ledger_observations), /locator|probe_kind|path|row|amount|currency|buyer|tx|account|balance|payload/i);
    assert.equal(summary.unit_count, 9);
  } finally {
    fs.rmSync(stateRoot, { recursive: true, force: true });
  }
});

test("refuses an existing final path, preserves it, and cleans its unique temporary file", () => {
  const stateRoot = tempStateRoot();
  try {
    fs.mkdirSync(receiptDir(stateRoot), { recursive: true, mode: 0o700 });
    const finalPath = path.join(receiptDir(stateRoot), "2026-08-08T00-00-00.000Z--00000000-0000-4000-8000-000000000001.json");
    const original = Buffer.from("immutable-existing-receipt\n", "utf8");
    fs.writeFileSync(finalPath, original, { mode: 0o600, flag: "wx" });
    const before = fs.readdirSync(receiptDir(stateRoot));

    const { result, summary } = run(stateRoot);
    assert.equal(result.exitCode, 1);
    assert.equal(summary.result, "fail");
    assert.deepEqual(fs.readdirSync(receiptDir(stateRoot)), before);
    assert.deepEqual(fs.readFileSync(finalPath), original);
    assert.equal(fs.statSync(finalPath).mode & 0o777, 0o600);
  } finally {
    fs.rmSync(stateRoot, { recursive: true, force: true });
  }
});

test("executable boundary failure exits nonzero with only a redacted summary", () => {
  const stateRoot = tempStateRoot();
  try {
    const blockedHome = path.join(stateRoot, "blocked-home");
    fs.writeFileSync(blockedHome, "not-a-directory\n", { mode: 0o600, flag: "wx" });
    const bin = path.join(stateRoot, "bin");
    fs.mkdirSync(bin, { mode: 0o700 });
    const launchctl = path.join(bin, "launchctl");
    fs.writeFileSync(launchctl, `#!/bin/sh\nprintf '%s\\n' '${FIXTURE.replace(/'/g, "'\\\"'\\\"'")}'\n`, { mode: 0o700 });
    fs.chmodSync(launchctl, 0o700);
    const child = spawnSync(process.execPath, [path.join(__dirname, "cfo-business-inventory.js")], {
      cwd: path.join(__dirname, ".."),
      env: {
        ...process.env,
        LIFE_MANAGER_STATE_HOME: blockedHome,
        PATH: `${bin}:${process.env.PATH || ""}`,
      },
      encoding: "utf8",
    });
    assert.equal(child.status, 1);
    assert.equal(child.stderr, "");
    const summary = JSON.parse(child.stdout.trim());
    assert.equal(summary.result, "fail");
    assert.equal(summary.receipt_path.startsWith(path.join(blockedHome, "cfo", "business-inventory") + path.sep), true);
    assert.doesNotMatch(child.stdout, /secret|token|payload|amount|balance|revenue|profit/i);
  } finally {
    fs.rmSync(stateRoot, { recursive: true, force: true });
  }
});

test("repo evidence resolution never probes outside REPO_ROOT", () => {
  const calls = [];
  assert.equal(repoEvidenceExists("AGENTS.md", (resolved) => {
    calls.push(resolved);
    return true;
  }), true);
  assert.equal(calls.length, 1);
  assert.equal(repoEvidenceExists("../../etc/passwd", (resolved) => {
    calls.push(resolved);
    return true;
  }), false);
  assert.equal(calls.length, 1);
});

test("package test script includes CFO focused suite in the normal npm test chain", () => {
  const packageJson = JSON.parse(fs.readFileSync(path.join(__dirname, "../package.json"), "utf8"));
  assert.match(packageJson.scripts["test:cfo"], /cfo-registry\.test\.js/);
  assert.match(packageJson.scripts.pretest, /npm run test:cfo/);
});
