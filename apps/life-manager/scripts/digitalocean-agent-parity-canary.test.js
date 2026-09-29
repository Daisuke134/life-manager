"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { runCli } = require("./digitalocean-agent-parity-canary.js");

const SHA = "a".repeat(40);
const EXPECTED = { schema_version: "life-manager.cloud-kernel-parity.v1",
  business_kernel_sha: "b".repeat(64), receipt_hash: "c".repeat(64), evidence_hash: "d".repeat(64),
  official_readback: true, replay_zero: true, effect: "none", human_input_count: 0 };

test("CLI refuses non-main release before provider call", async () => {
  let calls = 0;
  await assert.rejects(runCli([
    "--release-sha", SHA, "--output", "/tmp/parity.json", "--spec", "/release/agent.yaml",
    "--secret-path", "/private/key", "--name", "lm-parity",
  ], { localHead: "e".repeat(40), originMain: SHA, client: {}, runFixture: async () => EXPECTED,
    runParity: async () => { calls += 1; } }), /main-derived/i);
  assert.equal(calls, 0);
});

test("CLI computes local expectation and writes exact live parity receipt privately", async (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "lm-do-parity-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const output = path.join(directory, "parity.json");
  const receipt = { status: "verified", release_sha: SHA,
    provider_receipt_id: `digitalocean-agent-parity://sha256/${"f".repeat(64)}`,
    receipt_hash: EXPECTED.receipt_hash, evidence_hash: EXPECTED.evidence_hash,
    replay_zero: true, human_input_count: 0, effect: "none" };
  let received;
  const result = await runCli([
    "--release-sha", SHA, "--output", output, "--spec", "/release/agent.yaml",
    "--secret-path", "/private/key", "--name", "lm-parity",
  ], { localHead: SHA, originMain: SHA, client: {}, runFixture: async () => EXPECTED,
    runParity: async (input) => { received = input; return receipt; } });
  assert.deepEqual(result, receipt);
  assert.deepEqual(received.expected, EXPECTED);
  assert.equal(received.releaseSha, SHA);
  assert.equal(fs.statSync(output).mode & 0o777, 0o600);
  assert.deepEqual(JSON.parse(fs.readFileSync(output, "utf8")), receipt);
});
