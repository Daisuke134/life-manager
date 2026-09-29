"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { runDigitalOceanCompatibilityCanary } = require("./digitalocean-compatibility-canary.js");

function fixture(overrides = {}) {
  const calls = [];
  const client = {
    async balance() { calls.push("balance"); return calls.length === 1 ? { balance: "10.00" } : { balance: "9.99" }; },
    async createCanary() { calls.push("create"); return { session_id: "sess_canary1" }; },
    async show(id) { calls.push(`show:${id}`); return { id, status: "ready" }; },
    async logs(id) { calls.push(`logs:${id}`); return [{ type: "run.completed" }]; },
    async remove(id) { calls.push(`remove:${id}`); return { removed: true, session_id: id }; },
    ...overrides.client,
  };
  return {
    calls,
    deps: {
      client,
      async verifyReadOnlyOutcome() {
        calls.push("verify");
        return {
          tenant_isolated: true, effect: "none", human_input_count: 0, no_ask: true,
          browser_continuity: true, official_readback: true, replay_zero: true,
        };
      },
      async recordCleanup(value) { calls.push(`cleanup:${value.sessionId}`); },
      async recordCleanupFailure() { calls.push("cleanup-failure"); },
      ...overrides.deps,
    },
  };
}

test("bounded canary proves every cutover invariant then tears down and reads cost again", async () => {
  const f = fixture();
  const result = await runDigitalOceanCompatibilityCanary({ name: "lm-canary" }, f.deps);
  assert.equal(result.provider, "digitalocean-managed-agents");
  assert.deepEqual(result.before_balance, { balance: "10.00" });
  assert.deepEqual(result.after_balance, { balance: "9.99" });
  assert.deepEqual(result.teardown, { removed: true, session_id: "sess_canary1" });
  assert.deepEqual(f.calls, ["balance", "create", "show:sess_canary1", "logs:sess_canary1", "verify",
    "remove:sess_canary1", "balance", "cleanup:sess_canary1"]);
});

test("successful proof is not returned when exact teardown fails", async () => {
  const f = fixture({
    client: { async remove() { f.calls.push("remove:sess_canary1"); throw new Error("remove failed"); } },
  });
  await assert.rejects(runDigitalOceanCompatibilityCanary({ name: "lm-canary" }, f.deps), /remove failed/);
  assert.equal(f.calls.at(-1), "remove:sess_canary1");
});

test("failed proof still removes the exact session and records bounded cost", async () => {
  const f = fixture({ deps: { async verifyReadOnlyOutcome() { f.calls.push("verify"); return { tenant_isolated: false }; } } });
  await assert.rejects(runDigitalOceanCompatibilityCanary({ name: "lm-canary" }, f.deps), /proof incomplete/i);
  assert.deepEqual(f.calls.slice(-3), ["remove:sess_canary1", "balance", "cleanup:sess_canary1"]);
});

test("cleanup failure never replaces the primary proof failure", async () => {
  const original = new Error("provider proof failed");
  const f = fixture({
    client: { async logs() { f.calls.push("logs:sess_canary1"); throw original; }, async remove() { f.calls.push("remove:sess_canary1"); throw new Error("remove failed"); } },
  });
  await assert.rejects(runDigitalOceanCompatibilityCanary({ name: "lm-canary" }, f.deps), (error) => error === original);
  assert.equal(f.calls.at(-1), "cleanup-failure");
});
