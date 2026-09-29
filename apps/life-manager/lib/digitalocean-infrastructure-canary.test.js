"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { runDigitalOceanInfrastructureCanary } = require("./digitalocean-infrastructure-canary.js");

function fixture(overrides = {}) {
  const calls = [];
  let createIndex = 0;
  const client = {
    async balance() { calls.push("balance"); return calls.filter((x) => x === "balance").length === 1 ? { balance: "10" } : { balance: "9.99" }; },
    async createBareCanary({ name }) { createIndex += 1; calls.push(`create:${name}`); return { session_id: `sess_bare${createIndex}` }; },
    async show(id) { calls.push(`show:${id}`); return { id, status: "ready" }; },
    async exec(id) {
      calls.push(`exec:${id}`);
      if (id === "sess_bare2") return { exit_code: 0, stdout: "LM_TENANT_ISOLATED\n", stderr: "" };
      const count = calls.filter((x) => x === `exec:${id}`).length;
      return { exit_code: 0, stdout: count === 1 ? "LM_BROWSER_WRITE_OK\n" : "LM_BROWSER_CONTINUITY_OK\n", stderr: "" };
    },
    async remove(id) { calls.push(`remove:${id}`); return { removed: true, session_id: id }; },
    ...overrides.client,
  };
  return { calls, client };
}

test("model-free canary proves separate workspaces and Chromium profile continuity then removes both sessions", async () => {
  const f = fixture();
  const result = await runDigitalOceanInfrastructureCanary({
    namePrefix: "lm-infra", specPath: "/release/bare.yaml",
  }, { client: f.client });
  assert.equal(result.proof.tenant_isolated, true);
  assert.equal(result.proof.browser_continuity, true);
  assert.equal(result.proof.human_input_count, 0);
  assert.equal(result.proof.effect, "none");
  assert.deepEqual(result.after_balance, { balance: "9.99" });
  assert.deepEqual(result.teardown.map((row) => row.session_id), ["sess_bare2", "sess_bare1"]);
  assert.deepEqual(f.calls, ["balance", "create:lm-infra-a", "show:sess_bare1", "exec:sess_bare1",
    "create:lm-infra-b", "show:sess_bare2", "exec:sess_bare2", "exec:sess_bare1",
    "remove:sess_bare2", "remove:sess_bare1", "balance"]);
});

test("failed isolation still removes every created session and preserves the primary error", async () => {
  const original = new Error("isolation receipt invalid");
  const f = fixture({ client: { async exec(id) {
    f.calls.push(`exec:${id}`);
    if (id === "sess_bare2") throw original;
    return { exit_code: 0, stdout: "LM_BROWSER_WRITE_OK\n", stderr: "" };
  } } });
  await assert.rejects(runDigitalOceanInfrastructureCanary({
    namePrefix: "lm-infra", specPath: "/release/bare.yaml",
  }, { client: f.client }), (error) => error === original);
  assert.deepEqual(f.calls.slice(-3), ["remove:sess_bare2", "remove:sess_bare1", "balance"]);
});

test("missing exact browser marker fails closed", async () => {
  const f = fixture({ client: { async exec(id) {
    f.calls.push(`exec:${id}`);
    if (id === "sess_bare2") return { exit_code: 0, stdout: "LM_TENANT_ISOLATED\n", stderr: "" };
    return { exit_code: 0, stdout: "almost", stderr: "" };
  } } });
  await assert.rejects(runDigitalOceanInfrastructureCanary({
    namePrefix: "lm-infra", specPath: "/release/bare.yaml",
  }, { client: f.client }), /browser write receipt invalid/i);
});
