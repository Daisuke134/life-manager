"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { loadCloudExecutionPolicy } = require("./cloud-execution-policy.js");

function canonicalPolicy() {
  return {
    schema_version: "life-manager.cloud-execution-policy.v1",
    authority: "life_manager",
    requires_user_authored_goal: false,
    claim: { limit: 1, lease_seconds: 180, grant_ttl_seconds: 60 },
    capabilities: [{
      capability: "general-agent.work",
      effect_class: "none",
      max_attempts: 1,
      credential_refs: ["secret://gemini/api-key"],
    }],
  };
}

function writePolicy(t, value) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cloud-policy-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const file = path.join(root, "policy.json");
  fs.writeFileSync(file, JSON.stringify(value));
  return file;
}

test("loads one frozen Life Manager-owned non-effectful Cloud policy with a stable digest", () => {
  const first = loadCloudExecutionPolicy();
  const second = loadCloudExecutionPolicy();

  assert.deepEqual(first.policy, canonicalPolicy());
  assert.match(first.digest, /^[a-f0-9]{64}$/u);
  assert.equal(first.digest, second.digest);
  assert.equal(Object.isFrozen(first), true);
  assert.equal(Object.isFrozen(first.policy), true);
  assert.equal(Object.isFrozen(first.policy.claim), true);
  assert.equal(Object.isFrozen(first.policy.capabilities[0]), true);
  assert.equal(Object.isFrozen(first.policy.capabilities[0].credential_refs), true);
  assert.doesNotMatch(JSON.stringify(first), /AIza|sk-|api.?key[=:]/iu);
});

test("canonical digest does not depend on JSON object key order", (t) => {
  const canonical = canonicalPolicy();
  const reordered = {
    capabilities: canonical.capabilities,
    claim: canonical.claim,
    requires_user_authored_goal: false,
    authority: "life_manager",
    schema_version: canonical.schema_version,
  };
  assert.equal(
    loadCloudExecutionPolicy(writePolicy(t, reordered)).digest,
    loadCloudExecutionPolicy(writePolicy(t, canonical)).digest,
  );
});

test("rejects authority, goal ownership, capability, effect, credential, and bound drift", (t) => {
  const base = canonicalPolicy();
  const invalid = [
    { ...base, extra: true },
    { ...base, authority: "user" },
    { ...base, requires_user_authored_goal: true },
    { ...base, claim: { ...base.claim, limit: 2 } },
    { ...base, claim: { ...base.claim, lease_seconds: 29 } },
    { ...base, claim: { ...base.claim, lease_seconds: 901 } },
    { ...base, claim: { ...base.claim, grant_ttl_seconds: 181 } },
    { ...base, claim: { ...base.claim, extra: true } },
    { ...base, capabilities: [] },
    { ...base, capabilities: [...base.capabilities, base.capabilities[0]] },
    { ...base, capabilities: [{ ...base.capabilities[0], capability: "provider.publish" }] },
    { ...base, capabilities: [{ ...base.capabilities[0], effect_class: "publish" }] },
    { ...base, capabilities: [{ ...base.capabilities[0], max_attempts: 2 }] },
    { ...base, capabilities: [{ ...base.capabilities[0], credential_refs: [] }] },
    { ...base, capabilities: [{ ...base.capabilities[0], credential_refs: ["sk-raw-secret"] }] },
    { ...base, capabilities: [{ ...base.capabilities[0], credential_refs: ["secret://other/key"] }] },
    { ...base, capabilities: [{ ...base.capabilities[0], credential_refs: [
      "secret://gemini/api-key", "secret://gemini/api-key",
    ] }] },
    { ...base, capabilities: [{ ...base.capabilities[0], raw_secret: "forbidden" }] },
  ];

  invalid.forEach((value, index) => {
    assert.throws(
      () => loadCloudExecutionPolicy(writePolicy(t, value)),
      /cloud execution policy invalid/iu,
      `invalid policy ${index}`,
    );
  });
});

test("missing and malformed policy files fail closed", (t) => {
  assert.throws(
    () => loadCloudExecutionPolicy("/definitely/missing/cloud-policy.json"),
    /cloud execution policy invalid/iu,
  );
  const file = writePolicy(t, canonicalPolicy());
  fs.writeFileSync(file, "not-json");
  assert.throws(() => loadCloudExecutionPolicy(file), /cloud execution policy invalid/iu);
});
