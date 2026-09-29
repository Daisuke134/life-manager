"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { runCli } = require("./digitalocean-infrastructure-canary.js");

const SHA = "a".repeat(40);

test("CLI writes one private release-bound verified provider receipt", async (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "lm-do-canary-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const output = path.join(directory, "receipt.json");
  const result = {
    provider: "digitalocean-managed-agents",
    before_balance: { balance: "10" }, after_balance: { balance: "9.99" },
    teardown: [{ removed: true, session_id: "sess_b" }, { removed: true, session_id: "sess_a" }],
    proof: { tenant_isolated: true, browser_continuity: true, official_readback: true,
      replay_zero: true, no_ask: true, human_input_count: 0, effect: "none" },
  };
  const receipt = await runCli([
    "--release-sha", SHA, "--output", output, "--spec", "/release/bare.yaml",
    "--name-prefix", "lm-live",
  ], { client: {}, runCanary: async () => result, now: () => "2026-09-29T00:00:00.000Z" });
  assert.equal(receipt.status, "verified");
  assert.equal(receipt.release_sha, SHA);
  assert.match(receipt.provider_receipt_id, /^digitalocean-infrastructure:\/\/sha256\/[a-f0-9]{64}$/);
  assert.deepEqual(receipt.readback, result);
  assert.equal(fs.statSync(output).mode & 0o777, 0o600);
  assert.deepEqual(JSON.parse(fs.readFileSync(output, "utf8")), receipt);
});

test("CLI rejects non-release identity and relative evidence path before provider calls", async () => {
  let calls = 0;
  for (const args of [
    ["--release-sha", "bad", "--output", "/tmp/x", "--spec", "/release/bare.yaml", "--name-prefix", "lm-live"],
    ["--release-sha", SHA, "--output", "relative.json", "--spec", "/release/bare.yaml", "--name-prefix", "lm-live"],
  ]) {
    await assert.rejects(runCli(args, { client: {}, runCanary: async () => { calls += 1; } }), /usage|absolute/i);
  }
  assert.equal(calls, 0);
});
