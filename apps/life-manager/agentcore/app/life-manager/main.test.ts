import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

import { executeRuntimeRequest } from "./main.js";

const require = createRequire(import.meta.url);
const {
  createCloudHostAdapter,
  createLocalHostAdapter,
} = require("../../../../lib/cloud-edition-host-adapter.js");
const {
  readBusinessKernelArtifact,
} = require("../../../../lib/cloud-edition-kernel.js");

type Stored = Record<string, unknown>;

function memoryStore(seed: Array<[string, string, Stored]> = []) {
  const rows = new Map(seed.map(([tenant, key, value]) => [
    `${tenant}\u0000${key}`,
    structuredClone(value),
  ]));
  return {
    async read(tenant: string, key: string) {
      return structuredClone(rows.get(`${tenant}\u0000${key}`) || null);
    },
    async put(tenant: string, key: string, value: Stored) {
      rows.set(`${tenant}\u0000${key}`, structuredClone(value));
      return structuredClone(value);
    },
    async putIfAbsent(tenant: string, key: string, value: Stored) {
      const scoped = `${tenant}\u0000${key}`;
      if (rows.has(scoped)) return { created: false, value: structuredClone(rows.get(scoped)) };
      rows.set(scoped, structuredClone(value));
      return { created: true, value: structuredClone(value) };
    },
  };
}

function host(mode: "local" | "cloud", task: Stored) {
  const artifact = readBusinessKernelArtifact();
  const options = {
    tenantId: "tenant-cl01",
    approvedBusinessKernelSha: artifact.sha256,
    credentialStore: memoryStore(),
    browserSessionStore: memoryStore(),
    stateStore: memoryStore([["tenant-cl01", "task-cl01", task]]),
    receiptStore: memoryStore(),
  };
  return mode === "local" ? createLocalHostAdapter(options) : createCloudHostAdapter(options);
}

const TASK = Object.freeze({
  schema_version: 1,
  task_id: "job-cl01",
  tenant_id: "tenant-cl01",
  capability: "foundation.status",
  input: {
    objective: "report the bounded CL01 transport status",
    facts: ["same kernel", "reference only"],
  },
});
const REQUEST = Object.freeze({
  schema_version: 1,
  tenant_id: "tenant-cl01",
  job_id: "job-cl01",
  attempt: 1,
  wake_id: "wake-cl01",
  release_sha: "a".repeat(40),
  input_refs: ["lm-resource://state/tenant-cl01/task-cl01"],
});

test("AgentCore transport returns the same canonical receipt and evidence as the local host", async () => {
  const local = host("local", TASK);
  const cloud = host("cloud", TASK);
  const localResult = await local.executeTask(TASK);

  const envelope = await executeRuntimeRequest(REQUEST, {
    approvedReleaseSha: REQUEST.release_sha,
    host: cloud,
    usage: [],
  });
  const cloudReceipt = await cloud.readReceipt(envelope.receipt_ref);

  assert.deepEqual(cloudReceipt, localResult.receipt);
  assert.deepEqual(envelope, {
    tenant_id: "tenant-cl01",
    job_id: "job-cl01",
    attempt: 1,
    release_sha: "a".repeat(40),
    status: "completed",
    receipt_ref: "lm-resource://receipt/tenant-cl01/business-receipt%3Ajob-cl01",
    evidence_sha256: localResult.receipt.evidence_hash,
    usage: [],
  });
});

test("transport rejects a task reference whose stored job identity differs before execution", async () => {
  const cloud = host("cloud", { ...TASK, task_id: "different-job" });

  await assert.rejects(
    executeRuntimeRequest(REQUEST, {
      approvedReleaseSha: REQUEST.release_sha,
      host: cloud,
      usage: [],
    }),
    /job identity/i,
  );
});
