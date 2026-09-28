"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  createCloudHostAdapter,
  createLocalHostAdapter,
} = require("./cloud-edition-host-adapter.js");
const { readBusinessKernelArtifact } = require("./cloud-edition-kernel.js");

function recordingStore(kind, calls) {
  return {
    async read(tenantId, key) {
      calls.push([kind, "read", tenantId, key]);
      return { tenant_id: tenantId, key };
    },
    async put(tenantId, key, value) {
      calls.push([kind, "put", tenantId, key, value]);
      return value;
    },
    async putIfAbsent(tenantId, key, value) {
      calls.push([kind, "putIfAbsent", tenantId, key, value]);
      return { created: true, value };
    },
  };
}

function memoryStore(kind, calls = []) {
  const rows = new Map();
  return {
    rows,
    async read(tenantId, key) {
      calls.push([kind, "read", tenantId, key]);
      return rows.get(`${tenantId}\u0000${key}`) || null;
    },
    async put(tenantId, key, value) {
      calls.push([kind, "put", tenantId, key]);
      rows.set(`${tenantId}\u0000${key}`, structuredClone(value));
      return structuredClone(value);
    },
    async putIfAbsent(tenantId, key, value) {
      calls.push([kind, "putIfAbsent", tenantId, key]);
      const scoped = `${tenantId}\u0000${key}`;
      if (rows.has(scoped)) return { created: false, value: structuredClone(rows.get(scoped)) };
      rows.set(scoped, structuredClone(value));
      return { created: true, value: structuredClone(value) };
    },
  };
}

function hostOptions(mode, approvedBusinessKernelSha, calls = []) {
  return {
    tenantId: "tenant-a",
    approvedBusinessKernelSha,
    credentialStore: memoryStore(`${mode}:credential`, calls),
    browserSessionStore: memoryStore(`${mode}:browser-session`, calls),
    stateStore: memoryStore(`${mode}:state`, calls),
    receiptStore: memoryStore(`${mode}:receipt`, calls),
  };
}

test("tenant A cannot read tenant B credential, browser session, state, or receipt", async () => {
  const calls = [];
  const host = createCloudHostAdapter({
    tenantId: "tenant-a",
    approvedBusinessKernelSha: "a".repeat(64),
    credentialStore: recordingStore("credential", calls),
    browserSessionStore: recordingStore("browser-session", calls),
    stateStore: recordingStore("state", calls),
    receiptStore: recordingStore("receipt", calls),
  });
  const attempts = [
    ["readCredential", "credential"],
    ["readBrowserSession", "browser-session"],
    ["readState", "state"],
    ["readReceipt", "receipt"],
  ];

  for (const [method, kind] of attempts) {
    await assert.rejects(
      host[method](`lm-resource://${kind}/tenant-b/private-record`),
      /tenant scope mismatch/i,
    );
  }

  assert.deepEqual(calls, []);
});

test("local and Cloud run the same approved business kernel task with the same receipt and evidence hash", async () => {
  const artifact = readBusinessKernelArtifact();
  const task = {
    schema_version: 1,
    task_id: "foundation-parity-1",
    tenant_id: "tenant-a",
    capability: "foundation.status",
    input: {
      objective: "report the bounded Cloud foundation status",
      facts: ["tenant isolated", "effect free"],
    },
  };
  const local = createLocalHostAdapter(hostOptions("local", artifact.sha256));
  const cloud = createCloudHostAdapter(hostOptions("cloud", artifact.sha256));

  const localResult = await local.executeTask(task);
  const cloudResult = await cloud.executeTask(task);

  assert.deepEqual(cloudResult.receipt, localResult.receipt);
  assert.equal(localResult.receipt.business_kernel_sha, artifact.sha256);
  assert.match(localResult.receipt.capsule_hash, /^[a-f0-9]{64}$/);
  assert.match(localResult.receipt.evidence_hash, /^[a-f0-9]{64}$/);
  assert.match(localResult.receipt.receipt_hash, /^[a-f0-9]{64}$/);
  assert.equal(localResult.official_readback.verified, true);
  assert.equal(cloudResult.official_readback.verified, true);
  assert.equal(localResult.created, true);
  assert.equal(cloudResult.created, true);

  const replay = await cloud.executeTask(task);
  assert.equal(replay.created, false);
  assert.equal(replay.replay_zero, true);
  assert.deepEqual(replay.receipt, cloudResult.receipt);
});

test("an unapproved business kernel SHA fails before state or receipt persistence", async () => {
  const calls = [];
  const host = createCloudHostAdapter(hostOptions("cloud", "b".repeat(64), calls));
  const task = {
    schema_version: 1,
    task_id: "foundation-unapproved-1",
    tenant_id: "tenant-a",
    capability: "foundation.status",
    input: { objective: "must not run", facts: [] },
  };

  await assert.rejects(host.executeTask(task), /approved business kernel SHA mismatch/i);
  assert.deepEqual(calls, []);
});
