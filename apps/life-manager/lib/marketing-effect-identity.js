"use strict";

const fs = require("node:fs");
const path = require("node:path");

const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/;
const OCCURRENCE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const HASH = /^[0-9a-f]{64}$/;
const EFFECT_KEY = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,511}$/;
const INTEGRATION_REF = /^integration:\/\/postiz\/[a-z]+\/[A-Za-z0-9._:-]{1,200}$/i;
const ACCOUNT = /^@[A-Za-z0-9._-]{1,127}$/;

function required(value, label, pattern = ID) {
  const text = String(value == null ? "" : value).trim();
  if (!pattern.test(text)) throw new Error(`marketing effect identity ${label} is invalid`);
  return text;
}

function writeMarketingEffectIdentity(input = {}) {
  const target = String(process.env.LIFE_MANAGER_EFFECT_IDENTITY_PATH || "").trim();
  if (!target) return false;
  if (!path.isAbsolute(target)) throw new Error("marketing effect identity path must be absolute");

  const occurrenceId = required(
    process.env.LIFE_MANAGER_OCCURRENCE_ID, "occurrence_id", OCCURRENCE,
  );
  const runtimeRunId = required(process.env.LIFE_MANAGER_RUN_ID, "runtime_run_id");
  const loopId = required(process.env.LIFE_MANAGER_LOOP_ID, "loop_id");
  const row = {
    schema_version: 1,
    kind: "life_manager_effect_identity",
    runtime_run_id: runtimeRunId,
    occurrence_id: occurrenceId,
    loop_id: loopId,
    job_id: required(input.jobId, "job_id"),
    effect_key: required(input.effectKey, "effect_key", EFFECT_KEY),
    product_id: required(input.productId, "product_id"),
    format_id: required(input.formatId, "format_id"),
    form: required(input.form, "form"),
    locale: required(input.locale, "locale"),
    platform: required(input.platform, "platform"),
    creative_id: required(input.creativeId, "creative_id"),
    slot: required(input.slot, "slot"),
    integration_ref: required(input.integrationRef, "integration_ref", INTEGRATION_REF),
    account_id: required(input.accountId, "account_id", ACCOUNT),
    video_sha256: input.videoSha256 == null ? null : required(input.videoSha256, "video_sha256", HASH),
    caption_sha256: required(input.captionSha256, "caption_sha256", HASH),
    ...(Array.isArray(input.mediaSha256) ? {
      media_sha256: input.mediaSha256.map((value) => required(value, "media_sha256", HASH)),
    } : {}),
    ...(input.packSha256 == null ? {} : { pack_sha256: required(input.packSha256, "pack_sha256", HASH) }),
    ...(input.mediaOrderSha256 == null ? {} : {
      media_order_sha256: required(input.mediaOrderSha256, "media_order_sha256", HASH),
    }),
  };

  fs.mkdirSync(path.dirname(target), { recursive: true, mode: 0o700 });
  const flags = fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_APPEND
    | (fs.constants.O_NOFOLLOW || 0);
  const fd = fs.openSync(target, flags, 0o600);
  try {
    fs.fchmodSync(fd, 0o600);
    fs.writeSync(fd, `${JSON.stringify(row)}\n`, null, "utf8");
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
  return true;
}

module.exports = { writeMarketingEffectIdentity };
