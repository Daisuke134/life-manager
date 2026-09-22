"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const test = require("node:test");

const { createCloudWorkAuthority } = require("./cloud-work-authority.js");

const KEY = Buffer.alloc(32, 17).toString("base64");
const NOW = Date.parse("2026-09-22T12:00:00.000Z");

function job(overrides = {}) {
  return {
    job_id: "goal:financial-continuity:r1",
    tenant_id: "tenant-a",
    loop_id: "life-manager.manager",
    capability: "general-agent.work",
    effect_class: "none",
    effect_key: null,
    input_refs: { goal_ref: "goal-portfolio://tenant-a/financial-continuity?revision=1" },
    max_attempts: 1,
    attempt: 1,
    ...overrides,
  };
}

function expected(overrides = {}) {
  return {
    tenantId: "tenant-a",
    jobId: "goal:financial-continuity:r1",
    attempt: 1,
    workerId: "cloud-worker-a",
    capability: "general-agent.work",
    effectClass: "none",
    ...overrides,
  };
}

function authority(now = NOW, key = KEY) {
  return createCloudWorkAuthority({ signingKey: key, now: () => now });
}

function resign(token, change, key = KEY) {
  const [prefix, encoded] = token.split(".");
  const payload = JSON.parse(Buffer.from(encoded, "base64url").toString("utf8"));
  const changed = { ...payload, ...change };
  const nextEncoded = Buffer.from(JSON.stringify(changed)).toString("base64url");
  const material = `${prefix}.${nextEncoded}`;
  const signature = crypto.createHmac("sha256", Buffer.from(key, "base64"))
    .update(material).digest("base64url");
  return `${material}.${signature}`;
}

test("issues a deterministic short-lived policy-bound grant and verifies its exact identity", () => {
  const service = authority();
  const token = service.issue({ job: job(), workerId: "cloud-worker-a" });
  const replay = service.issue({ job: job(), workerId: "cloud-worker-a" });
  const verified = service.verify(token, expected());

  assert.equal(token, replay);
  assert.match(token, /^lmwg1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/u);
  assert.deepEqual(verified, {
    version: 1,
    policy_digest: service.policyDigest,
    tenant_id: "tenant-a",
    job_id: "goal:financial-continuity:r1",
    attempt: 1,
    worker_id: "cloud-worker-a",
    capability: "general-agent.work",
    effect_class: "none",
    credential_refs: ["secret://gemini/api-key"],
    issued_at: "2026-09-22T12:00:00.000Z",
    expires_at: "2026-09-22T12:01:00.000Z",
  });
  assert.equal(Object.isFrozen(verified), true);
  assert.equal(Object.isFrozen(verified.credential_refs), true);
  assert.doesNotMatch(JSON.stringify([token, verified]), /AIza|sk-|raw-secret/iu);
});

test("rejects tamper, current-policy drift, expiry, future issue time, and malformed tokens", () => {
  const service = authority();
  const token = service.issue({ job: job(), workerId: "cloud-worker-a" });
  const parts = token.split(".");
  const invalid = [
    `${parts[0]}.${parts[1]}.${parts[2].slice(0, -1)}A`,
    resign(token, { policy_digest: "c".repeat(64) }),
    resign(token, { expires_at: "2026-09-22T12:05:00.000Z" }),
    resign(token, { credential_refs: ["secret://other/key"] }),
    resign(token, { extra: true }),
    "not-a-grant",
    "lmwg2.e30.invalid",
  ];
  for (const value of invalid) {
    assert.throws(() => service.verify(value, expected()), /cloud work grant invalid/iu);
  }
  assert.throws(
    () => authority(NOW + 60_001).verify(token, expected()),
    /cloud work grant invalid/iu,
  );
  const future = authority(NOW + 1_000).issue({ job: job(), workerId: "cloud-worker-a" });
  assert.throws(() => service.verify(future, expected()), /cloud work grant invalid/iu);
});

test("validly signed grants still reject every foreign execution identity", () => {
  const service = authority();
  const token = service.issue({ job: job(), workerId: "cloud-worker-a" });
  const foreign = [
    expected({ tenantId: "tenant-b" }),
    expected({ jobId: "goal:other:r1" }),
    expected({ attempt: 2 }),
    expected({ workerId: "cloud-worker-b" }),
    expected({ capability: "provider.publish" }),
    expected({ effectClass: "publish" }),
    { ...expected(), extra: true },
  ];
  for (const identity of foreign) {
    assert.throws(() => service.verify(token, identity), /cloud work grant invalid/iu);
  }
});

test("issuance rejects foreign jobs, unsupported work, malformed identity, and weak keys", () => {
  const service = authority();
  const invalidJobs = [
    job({ tenant_id: "../tenant-b" }),
    job({ job_id: "job with spaces" }),
    job({ attempt: 0 }),
    job({ attempt: 2 }),
    job({ capability: "provider.publish" }),
    job({ effect_class: "publish", effect_key: "publish:1" }),
    job({ max_attempts: 2 }),
  ];
  for (const value of invalidJobs) {
    assert.throws(
      () => service.issue({ job: value, workerId: "cloud-worker-a" }),
      /cloud work grant invalid/iu,
    );
  }
  for (const workerId of ["", "../worker", "worker with spaces"]) {
    assert.throws(() => service.issue({ job: job(), workerId }), /cloud work grant invalid/iu);
  }
  for (const signingKey of ["", "short", Buffer.alloc(31).toString("base64")]) {
    assert.throws(() => authority(NOW, signingKey), /cloud work authority unavailable/iu);
  }
});
