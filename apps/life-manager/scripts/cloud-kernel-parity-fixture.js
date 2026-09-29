#!/usr/bin/env node

"use strict";

const { createCloudHostAdapter } = require("../lib/cloud-edition-host-adapter.js");
const { readBusinessKernelArtifact } = require("../lib/cloud-edition-kernel.js");

function memoryStore() {
  const rows = new Map();
  return {
    async read(tenantId, key) { return rows.get(`${tenantId}\0${key}`) || null; },
    async put(tenantId, key, value) {
      rows.set(`${tenantId}\0${key}`, structuredClone(value));
      return structuredClone(value);
    },
    async putIfAbsent(tenantId, key, value) {
      const scoped = `${tenantId}\0${key}`;
      if (rows.has(scoped)) return { created: false, value: structuredClone(rows.get(scoped)) };
      rows.set(scoped, structuredClone(value));
      return { created: true, value: structuredClone(value) };
    },
  };
}

async function runFixture() {
  const artifact = readBusinessKernelArtifact();
  const receiptStore = memoryStore();
  const host = createCloudHostAdapter({
    tenantId: "provider-canary",
    approvedBusinessKernelSha: artifact.sha256,
    credentialStore: memoryStore(),
    browserSessionStore: memoryStore(),
    stateStore: memoryStore(),
    receiptStore,
  });
  const task = {
    schema_version: 1,
    task_id: "provider-parity-v1",
    tenant_id: "provider-canary",
    capability: "foundation.status",
    input: {
      objective: "report the bounded cloud provider parity status",
      facts: ["tenant isolated", "effect free", "no human input"],
    },
  };
  const first = await host.executeTask(task);
  const replay = await host.executeTask(task);
  if (first.created !== true || first.official_readback.verified !== true
      || replay.created !== false || replay.replay_zero !== true
      || replay.receipt.receipt_hash !== first.receipt.receipt_hash) {
    throw new Error("cloud kernel parity fixture verification failed");
  }
  return Object.freeze({
    schema_version: "life-manager.cloud-kernel-parity.v1",
    business_kernel_sha: first.receipt.business_kernel_sha,
    receipt_hash: first.receipt.receipt_hash,
    evidence_hash: first.receipt.evidence_hash,
    official_readback: true,
    replay_zero: true,
    effect: "none",
    human_input_count: 0,
  });
}

if (require.main === module) {
  runFixture().then((result) => process.stdout.write(`${JSON.stringify(result)}\n`)).catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}

module.exports = { runFixture };
