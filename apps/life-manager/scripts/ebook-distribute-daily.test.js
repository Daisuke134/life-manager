"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { APPROVED_CLAIMS, JOBS, approvedBaselineScript, run, selectTarget } = require("./ebook-distribute-daily.js");
const { buildMarketingVideoPublicationJob } = require("../lib/marketing-video-publication-adapter.js");

const ROOT = path.resolve(__dirname, "../../..");
const PACK = JSON.parse(fs.readFileSync(
  path.join(ROOT, "skills/earn/marketing-engine/registry/ebook-packs/ebook-ja-watercolor.json"), "utf8",
));
const PACK_EN = JSON.parse(fs.readFileSync(
  path.join(ROOT, "skills/earn/marketing-engine/registry/ebook-packs/ebook-en-anicca-monk.json"), "utf8",
));

test("each Japanese eBook publisher owner resolves one matching account and locale", () => {
  const instagram = selectTarget({
    root: ROOT, pack: PACK, ownerId: "ebook-ja-instagram-daily",
    platform: "instagram", accountId: "instagram.obou_anicca",
  });
  const tiktok = selectTarget({
    root: ROOT, pack: PACK, ownerId: "ebook-ja-tiktok-daily",
    platform: "tiktok", accountId: "tiktok.obou_anicca",
  });

  assert.equal(instagram.account.language, "ja");
  assert.equal(instagram.target.integration_id, instagram.integrationId);
  assert.equal(tiktok.account.language, "ja");
  assert.equal(tiktok.target.integration_id, tiktok.integrationId);
  assert.deepEqual(Object.keys(JOBS).sort(), [
    "ebook-en-tiktok-daily", "ebook-ja-instagram-daily", "ebook-ja-tiktok-daily",
  ]);
  assert.deepEqual(
    Object.entries(JOBS).filter(([owner]) => owner.startsWith("ebook-ja-")).map(([, lane]) => lane.platform).sort(),
    ["instagram", "tiktok"],
  );
});

test("English HeyGen owner is scoped to the existing TikTok account and reports disabled setup", () => {
  const lane = JOBS["ebook-en-tiktok-daily"];
  assert.deepEqual(lane, {
    productId: "ebook-en",
    platform: "tiktok",
    accountId: "tiktok.monk_anicca",
    formatId: "ebook-avatar-iv",
    form: "ebook-reflection-reel",
    locale: "en",
  });

  const selected = selectTarget({
    root: ROOT,
    pack: PACK_EN,
    ownerId: "ebook-en-tiktok-daily",
    platform: lane.platform,
    accountId: lane.accountId,
  });
  assert.equal(selected.account.status, "disabled_verified");
  assert.equal(selected.setup_required, true);
  assert.equal(selected.setup_reason, "provider_disabled");
  assert.equal(selected.target, null);
  assert.equal(selected.integrationId, "cmo5rwq2p00twn10yrsdglng3");
});

test("English baseline policy accepts only the owned HeyGen script and claims", () => {
  const script = {
    product_id: "ebook-en",
    language: "en",
    baseline: true,
    renderer_id: "heygen-avatar-iv",
    cta: "Read The Anicca Reset",
    source_mechanism_ids: ["baseline.owner-authored.ebook-en.1.1"],
  };
  assert.equal(approvedBaselineScript(script, PACK_EN), true);
  assert.equal(approvedBaselineScript({ ...script, language: "ja" }, PACK_EN), false);
  assert.equal(approvedBaselineScript(script, {
    ...PACK_EN, allowed_claims: [...PACK_EN.allowed_claims, "guaranteed results"],
  }), false);
});

test("English owner returns a typed no-effect hold while Postiz keeps its integration disabled", async () => {
  const dataDir = path.join(os.tmpdir(), `ebook-en-disabled-${process.pid}-${Date.now()}`);
  const env = {
    LIFE_MANAGER_LOOP_ID: "ebook-en-tiktok-daily",
    LIFE_MANAGER_OCCURRENCE_ID: "ebook-en-tiktok-daily:run-1",
    LIFE_MANAGER_RELEASE_ROOT: ROOT,
    LIFE_MANAGER_RESULT_HINT_PATH: path.join(dataDir, "entrypoint-result.json"),
    LM_DATA_DIR: dataDir,
    LM_RUNTIME_TENANT_ID: "dais-local",
    LM_EBOOK_PUBLISHING_ENABLED: "true",
  };

  const result = await run(["ebook-en-tiktok-daily"], {
    env,
    nowMs: Date.parse("2026-10-06T08:00:00+09:00"),
  });

  assert.equal(result.state, "setup_required");
  assert.equal(result.reason, "provider_disabled");
  assert.equal(result.effect, 0);
  assert.equal(fs.existsSync(dataDir), false);
});

test("each eBook publication occurrence owns exactly one provider platform effect", () => {
  const slot = "2026-10-06T07:00:00.000Z";
  const jobs = Object.entries(JOBS).filter(([owner]) => owner.startsWith("ebook-ja-")).map(([, lane]) => buildMarketingVideoPublicationJob({
    tenantId: "dais-local",
    productId: "ebook-ja",
    formatId: "ebook-watercolor",
    form: "ebook-reflection-reel",
    locale: "ja",
    slot,
    creativeId: "baseline-ebook-ja-1-1",
    platform: lane.platform,
    videoRef: `object://sha256/${"a".repeat(64)}`,
    captionRef: `object://sha256/${"b".repeat(64)}`,
    approvalRef: `object://sha256/${"c".repeat(64)}`,
    instagramProfileRef: lane.platform === "instagram"
      ? "profile://instagram/obou.anicca" : "profile://instagram/unassigned",
    postizTokenRef: "secret://postiz/api-key",
    ...(lane.platform === "instagram"
      ? { instagramIntegrationRef: "integration://postiz/instagram/cmooplxmu04tpmd0y4h3cpk33" }
      : { tiktokIntegrationRef: "integration://postiz/tiktok/cmo5s4edx00vgn10ygnu34a0n" }),
    slotScopedEffect: true,
  }));

  assert.equal(jobs.length, 2);
  assert.equal(new Set(jobs.map((job) => job.input_refs.platform_ref)).size, 2);
  assert.deepEqual(jobs.map((job) => job.effect_class), ["publish", "publish"]);
  assert.equal(jobs.every((job) => job.loop_id === "marketing.video.publish"), true);
});

test("an unregistered eBook account fails before any render or provider work", async () => {
  const dataDir = path.join(os.tmpdir(), `ebook-closed-${process.pid}-${Date.now()}`);
  const env = {
    LIFE_MANAGER_LOOP_ID: "ebook-ja-instagram-daily",
    LIFE_MANAGER_OCCURRENCE_ID: "ebook-ja-instagram-daily:run-1",
    LIFE_MANAGER_RELEASE_ROOT: ROOT,
    LIFE_MANAGER_RESULT_HINT_PATH: path.join(dataDir, "entrypoint-result.json"),
    LM_DATA_DIR: dataDir,
    LM_RUNTIME_TENANT_ID: "dais-local",
  };
  const pack = { ...PACK, accounts: PACK.accounts.filter((row) => row.account_id !== "instagram.obou_anicca") };
  assert.throws(() => selectTarget({
    root: ROOT, pack, ownerId: "ebook-ja-instagram-daily",
    platform: "instagram", accountId: "instagram.obou_anicca",
  }));
  await assert.rejects(run(["ebook-ja-instagram-daily"], {
    env,
    nowMs: Date.parse("2026-10-06T08:00:00+09:00"),
  }), /readiness gate is closed/);
  assert.equal(fs.existsSync(dataDir), false);
});

test("the standing policy only approves the current Japanese baseline claim set", () => {
  const script = {
    product_id: "ebook-ja",
    language: "ja",
    baseline: true,
    renderer_id: "watercolor-monk",
    cta: "アニッチャ・リセットを読む",
    source_mechanism_ids: ["baseline.owner-authored.ebook-ja.1.1"],
  };
  const pack = {
    product_id: "ebook-ja",
    renderer_id: "watercolor-monk",
    allowed_claims: [...APPROVED_CLAIMS],
  };

  assert.equal(approvedBaselineScript(script, pack), true);
  assert.equal(approvedBaselineScript({ ...script, baseline: false }, pack), false);
  assert.equal(approvedBaselineScript(script, {
    ...pack, allowed_claims: [...APPROVED_CLAIMS, "guaranteed results"],
  }), false);
});
