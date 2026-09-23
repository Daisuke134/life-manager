#!/usr/bin/env node
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const SAFE_OWNER = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const SAFE_RECEIPT = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const MAX_RESULT_BYTES = 1024 * 1024;

function required(value, label) {
  const text = String(value == null ? "" : value).trim();
  if (!text) throw new Error(`${label} is required`);
  return text;
}

function readResult(file) {
  const info = fs.lstatSync(file);
  if (!info.isFile() || info.isSymbolicLink() || info.nlink !== 1 || info.size > MAX_RESULT_BYTES) {
    throw new Error("mobile result capture is invalid");
  }
  const lines = fs.readFileSync(file, "utf8").split(/\r?\n/).filter((line) => line.trim());
  if (lines.length !== 1) throw new Error("mobile result must contain one JSON line");
  const value = JSON.parse(lines[0]);
  if (!value || typeof value !== "object" || Array.isArray(value)
      || !value.publication || typeof value.publication !== "object"
      || Array.isArray(value.publication)) {
    throw new Error("mobile publication result is invalid");
  }
  return value.publication;
}

function effectStatus(publication) {
  if (typeof publication.created === "boolean") {
    return publication.created ? "verified" : "reconciled";
  }
  if (publication.status === "published" && publication.provider_reconciled === true
      && publication.replay_created === false) {
    return "reconciled";
  }
  throw new Error("mobile publication result lacks exact effect proof");
}

function writePrivateJson(target, value) {
  const parent = path.dirname(target);
  const parentInfo = fs.lstatSync(parent);
  if (!parentInfo.isDirectory() || parentInfo.isSymbolicLink()) {
    throw new Error("mobile result hint parent is invalid");
  }
  try {
    fs.lstatSync(target);
    throw new Error("mobile result hint already exists");
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  const temporary = path.join(
    parent,
    `.${path.basename(target)}.${process.pid}.${crypto.randomBytes(6).toString("hex")}`,
  );
  let descriptor;
  try {
    descriptor = fs.openSync(temporary, "wx", 0o600);
    fs.writeFileSync(descriptor, `${JSON.stringify(value)}\n`, "utf8");
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = undefined;
    fs.chmodSync(temporary, 0o600);
    fs.renameSync(temporary, target);
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
    try { fs.unlinkSync(temporary); } catch (error) { if (error.code !== "ENOENT") throw error; }
  }
}

function main(argv = process.argv.slice(2), env = process.env) {
  if (argv.length !== 1) throw new Error("usage: mobile-effect-result.js <runner-stdout>");
  const ownerId = required(env.LIFE_MANAGER_LOOP_ID, "LIFE_MANAGER_LOOP_ID");
  const occurrenceId = required(env.LIFE_MANAGER_OCCURRENCE_ID, "LIFE_MANAGER_OCCURRENCE_ID");
  const output = required(env.LIFE_MANAGER_RESULT_HINT_PATH, "LIFE_MANAGER_RESULT_HINT_PATH");
  if (!SAFE_OWNER.test(ownerId) || !occurrenceId.startsWith(`${ownerId}:`)
      || occurrenceId.length > 256) {
    throw new Error("mobile effect identity is invalid");
  }
  const publication = readResult(argv[0]);
  const providerReceiptId = required(publication.provider_post_id, "provider_post_id");
  if (!SAFE_RECEIPT.test(providerReceiptId)) throw new Error("provider_post_id is invalid");
  writePrivateJson(output, {
    schema_version: 1,
    kind: "life_manager_effect_result",
    status: "verified_effect",
    effect: 1,
    owner_id: ownerId,
    occurrence_id: occurrenceId,
    provider: "postiz",
    provider_receipt_id: providerReceiptId,
    effect_status: effectStatus(publication),
  });
}

if (require.main === module) {
  try { main(); } catch (error) { process.stderr.write(`${error.message}\n`); process.exitCode = 1; }
}

module.exports = { effectStatus, main, readResult, writePrivateJson };
