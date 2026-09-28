"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");

const ID = /^[a-z0-9][a-z0-9._:-]{0,199}$/i;
const HASH = /^[a-f0-9]{64}$/;

function canonicalJson(value) {
  if (value === null || typeof value === "boolean" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "number" && Number.isFinite(value)) return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object" && Object.getPrototypeOf(value) === Object.prototype) {
    return `{${Object.keys(value).sort().map((key) =>
      `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  throw new Error("cloud edition canonical value invalid");
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function readBusinessKernelArtifact() {
  const digest = sha256(fs.readFileSync(__filename));
  return Object.freeze({
    schema_version: 1,
    sha256: digest,
    ref: `business-kernel://sha256/${digest}`,
  });
}

function executeBusinessTask(task, approvedSha) {
  const artifact = readBusinessKernelArtifact();
  if (!HASH.test(String(approvedSha || "")) || approvedSha !== artifact.sha256) {
    throw new Error("approved business kernel SHA mismatch");
  }
  if (
    !task || task.schema_version !== 1
    || !ID.test(String(task.task_id || ""))
    || !ID.test(String(task.tenant_id || ""))
    || !ID.test(String(task.capability || ""))
    || !task.input || typeof task.input !== "object" || Array.isArray(task.input)
  ) {
    throw new Error("cloud edition business task invalid");
  }
  const capsule = canonicalJson({
    schema_version: 1,
    task_id: task.task_id,
    tenant_id: task.tenant_id,
    capability: task.capability,
    input: task.input,
  });
  if (Buffer.byteLength(capsule) > 16_384) throw new Error("cloud edition task capsule too large");
  const capsuleHash = sha256(capsule);
  const evidenceHash = sha256(canonicalJson({
    schema_version: 1,
    task_id: task.task_id,
    tenant_id: task.tenant_id,
    capability: task.capability,
    status: "completed",
    capsule_hash: capsuleHash,
  }));
  const receipt = {
    schema_version: 1,
    record_type: "business_receipt",
    receipt_id: `business-receipt:${task.task_id}`,
    task_id: task.task_id,
    tenant_id: task.tenant_id,
    capability: task.capability,
    status: "completed",
    effect_class: "none",
    business_kernel_sha: artifact.sha256,
    capsule_hash: capsuleHash,
    evidence_hash: evidenceHash,
  };
  return Object.freeze({
    ...receipt,
    receipt_hash: sha256(canonicalJson(receipt)),
  });
}

module.exports = { canonicalJson, executeBusinessTask, readBusinessKernelArtifact };
