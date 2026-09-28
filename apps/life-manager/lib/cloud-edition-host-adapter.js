"use strict";

const { canonicalJson, executeBusinessTask } = require("./cloud-edition-kernel.js");

const TENANT = /^[a-z0-9][a-z0-9._-]{0,127}$/i;
const HASH = /^[a-f0-9]{64}$/;

function requiredStore(value, name) {
  if (!value || typeof value.read !== "function") {
    throw new Error(`cloud edition ${name} store unavailable`);
  }
  return value;
}

function resourceRef(value, expectedKind, tenantId) {
  let parsed;
  try {
    parsed = new URL(String(value || ""));
  } catch {
    throw new Error("cloud edition resource ref invalid");
  }
  const parts = parsed.pathname.split("/").filter(Boolean).map(decodeURIComponent);
  if (
    parsed.protocol !== "lm-resource:"
    || parsed.hostname !== expectedKind
    || parts.length !== 2
    || !TENANT.test(parts[0])
    || !parts[1]
    || parts[1].length > 256
  ) {
    throw new Error("cloud edition resource ref invalid");
  }
  if (parts[0] !== tenantId) throw new Error("cloud edition tenant scope mismatch");
  return parts[1];
}

function createHostAdapter(mode, options = {}) {
  const tenantId = String(options.tenantId || "");
  if (!TENANT.test(tenantId)) throw new Error("cloud edition tenant invalid");
  if (!HASH.test(String(options.approvedBusinessKernelSha || ""))) {
    throw new Error("cloud edition approved business kernel SHA invalid");
  }
  const stores = {
    credential: requiredStore(options.credentialStore, "credential"),
    "browser-session": requiredStore(options.browserSessionStore, "browser session"),
    state: requiredStore(options.stateStore, "state"),
    receipt: requiredStore(options.receiptStore, "receipt"),
  };
  const read = (kind, ref) => stores[kind].read(tenantId, resourceRef(ref, kind, tenantId));
  const approvedBusinessKernelSha = options.approvedBusinessKernelSha;
  const executeTask = async (task) => {
    if (!task || task.tenant_id !== tenantId) throw new Error("cloud edition tenant scope mismatch");
    const receipt = executeBusinessTask(task, approvedBusinessKernelSha);
    if (typeof stores.receipt.putIfAbsent !== "function" || typeof stores.state.put !== "function") {
      throw new Error("cloud edition durable host store unavailable");
    }
    const persisted = await stores.receipt.putIfAbsent(tenantId, receipt.receipt_id, receipt);
    if (!persisted || typeof persisted.created !== "boolean") {
      throw new Error("cloud edition receipt persistence invalid");
    }
    if (persisted.created) {
      await stores.state.put(tenantId, task.task_id, {
        schema_version: 1,
        task_id: task.task_id,
        status: receipt.status,
        receipt_ref: `lm-resource://receipt/${tenantId}/${encodeURIComponent(receipt.receipt_id)}`,
      });
    }
    const readback = await stores.receipt.read(tenantId, receipt.receipt_id);
    if (!readback || canonicalJson(readback) !== canonicalJson(receipt)) {
      throw new Error("cloud edition official receipt readback mismatch");
    }
    return Object.freeze({
      receipt,
      created: persisted.created,
      replay_zero: persisted.created === false,
      official_readback: Object.freeze({
        verified: true,
        receipt_ref: `lm-resource://receipt/${tenantId}/${encodeURIComponent(receipt.receipt_id)}`,
      }),
    });
  };
  return Object.freeze({
    mode,
    tenantId,
    readCredential: async (ref) => read("credential", ref),
    readBrowserSession: async (ref) => read("browser-session", ref),
    readState: async (ref) => read("state", ref),
    readReceipt: async (ref) => read("receipt", ref),
    executeTask,
  });
}

function createCloudHostAdapter(options) {
  return createHostAdapter("cloud", options);
}

function createLocalHostAdapter(options) {
  return createHostAdapter("local", options);
}

module.exports = { createCloudHostAdapter, createLocalHostAdapter };
