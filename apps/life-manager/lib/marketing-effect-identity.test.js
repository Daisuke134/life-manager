"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { writeMarketingEffectIdentity } = require("./marketing-effect-identity.js");

test("writes an exact runtime occurrence-to-publication identity sidecar", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-effect-identity-"));
  const sidecar = path.join(root, "effect-identities", "run-1.jsonl");
  const previous = {
    LIFE_MANAGER_EFFECT_IDENTITY_PATH: process.env.LIFE_MANAGER_EFFECT_IDENTITY_PATH,
    LIFE_MANAGER_OCCURRENCE_ID: process.env.LIFE_MANAGER_OCCURRENCE_ID,
    LIFE_MANAGER_RUN_ID: process.env.LIFE_MANAGER_RUN_ID,
    LIFE_MANAGER_LOOP_ID: process.env.LIFE_MANAGER_LOOP_ID,
  };
  Object.assign(process.env, {
    LIFE_MANAGER_EFFECT_IDENTITY_PATH: sidecar,
    LIFE_MANAGER_OCCURRENCE_ID: "life-manager-honne-ja:run-1",
    LIFE_MANAGER_RUN_ID: "run-1",
    LIFE_MANAGER_LOOP_ID: "life-manager-honne-ja",
  });
  try {
    assert.equal(writeMarketingEffectIdentity({
      jobId: "marketing-video-publication:job-1",
      effectKey: "marketing:video:honne-ai:tiktok:HJA-007-aaaaaaaaaaaa:" + "a".repeat(64) + ":" + "b".repeat(64),
      productId: "honne-ai",
      formatId: "reelclaw",
      form: "relationship-confession",
      locale: "ja",
      platform: "tiktok",
      creativeId: "HJA-007-aaaaaaaaaaaa",
      slot: "2026-07-30T12:30:00.000Z",
      integrationRef: "integration://postiz/tiktok/honne-ai-ja",
      accountId: "@honnevideo",
      videoSha256: "a".repeat(64),
      captionSha256: "b".repeat(64),
    }), true);
    assert.deepEqual(JSON.parse(fs.readFileSync(sidecar, "utf8")), {
      schema_version: 1,
      kind: "life_manager_effect_identity",
      runtime_run_id: "run-1",
      occurrence_id: "life-manager-honne-ja:run-1",
      loop_id: "life-manager-honne-ja",
      job_id: "marketing-video-publication:job-1",
      effect_key: "marketing:video:honne-ai:tiktok:HJA-007-aaaaaaaaaaaa:" + "a".repeat(64) + ":" + "b".repeat(64),
      product_id: "honne-ai",
      format_id: "reelclaw",
      form: "relationship-confession",
      locale: "ja",
      platform: "tiktok",
      creative_id: "HJA-007-aaaaaaaaaaaa",
      slot: "2026-07-30T12:30:00.000Z",
      integration_ref: "integration://postiz/tiktok/honne-ai-ja",
      account_id: "@honnevideo",
      video_sha256: "a".repeat(64),
      caption_sha256: "b".repeat(64),
    });
    assert.equal(fs.statSync(sidecar).mode & 0o777, 0o600);
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
});

test("does not create a sidecar when the runtime did not provide an identity path", () => {
  const previous = process.env.LIFE_MANAGER_EFFECT_IDENTITY_PATH;
  delete process.env.LIFE_MANAGER_EFFECT_IDENTITY_PATH;
  try {
    assert.equal(writeMarketingEffectIdentity({ jobId: "job-1" }), false);
  } finally {
    if (previous === undefined) delete process.env.LIFE_MANAGER_EFFECT_IDENTITY_PATH;
    else process.env.LIFE_MANAGER_EFFECT_IDENTITY_PATH = previous;
  }
});
