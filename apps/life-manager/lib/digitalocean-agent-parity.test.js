"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { runDigitalOceanAgentParity } = require("./digitalocean-agent-parity.js");

const RELEASE = "a".repeat(40);
const EXPECTED = Object.freeze({
  schema_version: "life-manager.cloud-kernel-parity.v1",
  business_kernel_sha: "b".repeat(64), receipt_hash: "c".repeat(64), evidence_hash: "d".repeat(64),
  official_readback: true, replay_zero: true, effect: "none", human_input_count: 0,
});

function fixture(overrides = {}) {
  const calls = [];
  const client = {
    async balance() { calls.push("balance"); return calls.filter((x) => x === "balance").length === 1 ? { balance: "9.99" } : { balance: "9.98" }; },
    async createAgentCanary() { calls.push("create"); return { session_id: "sess_agent1" }; },
    async show(id) { calls.push(`show:${id}`); return { id, status: "ready" }; },
    async prompt(id, text) { calls.push(`prompt:${id}`); assert.match(text, new RegExp(RELEASE)); return { session_id: id, run_id: "run_1", status: "completed", text: JSON.stringify(EXPECTED) }; },
    async remove(id) { calls.push(`remove:${id}`); return { removed: true, session_id: id }; },
    ...overrides.client,
  };
  return { calls, client };
}

function input() {
  return { releaseSha: RELEASE, expected: EXPECTED, name: "lm-parity", specPath: "/release/agent.yaml",
    secretPath: "/private/openai.key", repo: "Daisuke134/life-manager" };
}

test("agent parity binds exact release and local hashes then tears down before returning receipt", async () => {
  const f = fixture();
  const result = await runDigitalOceanAgentParity(input(), { client: f.client });
  assert.equal(result.status, "verified");
  assert.equal(result.release_sha, RELEASE);
  assert.match(result.provider_receipt_id, /^digitalocean-agent-parity:\/\/sha256\/[a-f0-9]{64}$/);
  assert.equal(result.receipt_hash, EXPECTED.receipt_hash);
  assert.equal(result.evidence_hash, EXPECTED.evidence_hash);
  assert.equal(result.replay_zero, true);
  assert.equal(result.human_input_count, 0);
  assert.deepEqual(result.after_balance, { balance: "9.98" });
  assert.deepEqual(f.calls, ["balance", "create", "show:sess_agent1", "prompt:sess_agent1",
    "remove:sess_agent1", "balance"]);
});

test("agent self-report mismatch fails closed and still removes the session", async () => {
  const f = fixture({ client: { async prompt(id) { f.calls.push(`prompt:${id}`); return {
    session_id: id, run_id: "run_1", status: "completed", text: JSON.stringify({ ...EXPECTED, receipt_hash: "e".repeat(64) }),
  }; } } });
  await assert.rejects(runDigitalOceanAgentParity(input(), { client: f.client }), /parity mismatch/i);
  assert.deepEqual(f.calls.slice(-2), ["remove:sess_agent1", "balance"]);
});

test("non-JSON agent prose is never accepted as parity evidence", async () => {
  const f = fixture({ client: { async prompt(id) { f.calls.push(`prompt:${id}`); return {
    session_id: id, run_id: "run_1", status: "completed", text: `passed\n${JSON.stringify(EXPECTED)}`,
  }; } } });
  await assert.rejects(runDigitalOceanAgentParity(input(), { client: f.client }), /JSON invalid/i);
});
