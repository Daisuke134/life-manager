#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { createContentObjectStore } = require("../lib/content-object-store.js");
const { createMarketingLocalLedger } = require("../lib/marketing-local-ledger.js");
const {
  buildMarketingVideoGenerationJob,
  createMarketingVideoGenerationLoopAdapter,
  verifyMarketingVideoGenerationReceipt,
} = require("../lib/marketing-video-generation-adapter.js");
const {
  buildMarketingVideoPublicationJob,
  createMarketingVideoPublicationLoopAdapter,
  verifyMarketingVideoPublicationReceipt,
} = require("../lib/marketing-video-publication-adapter.js");
const { buildMarketingLivenessJob, executeMarketingLivenessJob } = require("../lib/marketing-liveness-adapter.js");
const { buildMarketingCtaCaptionRef } = require("../lib/marketing-app-store-cta.js");
const { createCreativeMetricsProvider } = require("../lib/marketing-creative-metrics.js");
const { generateVideoHookText } = require("../lib/marketing-slide-pack-text.js");
const { buildCapafyReelCaptionRef, capafyReelTextGenerator } = require("../lib/capafy-reel-content.js");
const { marketingVideoDueSlot } = require("../lib/honne-ja-shadow-schedule.js");
const { executeCapabilityJob } = require("./runtime-up.js");

const TENANT = "dais-local";
const PRODUCTION_SLOTS = Object.freeze(["08:30", "12:30", "21:30"]);
const ANICCA_MAIN_SLOTS = Object.freeze(["08:00", "16:00", "22:37"]);
const ANICCA_MAIN_INSTAGRAM_SLOTS = Object.freeze(["08:10", "13:10", "19:10"]);
const ANICCA_EN_CARD_INSTAGRAM_SLOTS = Object.freeze(["08:45", "12:45", "21:30"]);
const ANICCA_EN_WIDGET_INSTAGRAM_SLOTS = Object.freeze(["07:30", "09:30", "19:00"]);
const ANICCA_AI_YOUTUBE_SLOTS = Object.freeze(["07:45", "13:15", "19:45"]);
const ANICCA_AFFIRMATION_YOUTUBE_SLOTS = Object.freeze(["08:15", "14:15", "20:15"]);
const ANICCA_JA_WIDGET_INSTAGRAM_SLOTS = Object.freeze(["08:05", "13:05", "18:20"]);
const ANICCA_JP4_SLOTS = Object.freeze(["09:15", "15:15", "20:45"]);
const ANICCA_HE_SLOTS = Object.freeze(["07:15", "13:45", "18:15"]);
const CAPAFY_IG_SLOTS = Object.freeze(["09:00", "14:00", "20:00"]);
// freshHookText: every anicca-ios lane cycles a 2-4 hook pack 3x/day, so the same
// caption reposted every ~1.3 days (Postiz public API 2026-09-25..29, e.g. @anicca.he
// "強い人の口癖、5つだけ" 6 times). honne packs hold enough distinct hooks and a
// different product voice, so they keep verbatim pack text.
const LANES = Object.freeze({
  run: { name: "honne JA", product: "honne-ai", format: "reelclaw", locale: "ja", platform: "tiktok", account: "@honnevideo", integrationId: "cmnit95mg015rrm0ye5vm8dhl", slots: PRODUCTION_SLOTS, packKey: "LM_HONNE_JA_PACK_REF", mediaKey: "LM_HONNE_JA_MEDIA_REFS", approvalKey: "LM_HONNE_JA_PUBLICATION_APPROVAL_REF", telegramLane: "honne-ja" },
  "run-anicca-main": { name: "Anicca main", product: "anicca-ios", format: "reelclaw-card", locale: "ja", platform: "tiktok", account: "@anicca.jp", integrationId: "cmp9sdev5012voh0y58qs45xc", slots: ANICCA_MAIN_SLOTS, packKey: "LM_ANICCA_MAIN_PACK_REF", mediaKey: "LM_ANICCA_MAIN_MEDIA_REFS", approvalKey: "LM_ANICCA_MAIN_TIKTOK_APPROVAL_REF", telegramLane: "anicca-main-ja-tiktok", freshHookText: true },
  "run-anicca-main-instagram": { name: "Anicca main Instagram", product: "anicca-ios", format: "reelclaw-card", locale: "ja", platform: "instagram", account: "@anicca.jp1", instagramProfileRef: "profile://instagram/anicca.jp1", integrationId: "cmn8ycvtn02djqx0ytuisn9mw", slots: ANICCA_MAIN_INSTAGRAM_SLOTS, packKey: "LM_ANICCA_MAIN_PACK_REF", mediaKey: "LM_ANICCA_MAIN_MEDIA_REFS", approvalKey: "LM_ANICCA_MAIN_INSTAGRAM_APPROVAL_REF", telegramLane: "anicca-main-ja-instagram", freshHookText: true },
  "run-anicca-en-card-instagram": { name: "Anicca EN Card Instagram", product: "anicca-ios", format: "reelclaw-card", locale: "en", platform: "instagram", account: "@anicca.encards", instagramProfileRef: "profile://instagram/anicca.encards", integrationId: "cmpc3gx4001nklg0y27a8o66q", slots: ANICCA_EN_CARD_INSTAGRAM_SLOTS, packKey: "LM_ANICCA_EN_CARD_PACK_REF", mediaKey: "LM_ANICCA_EN_CARD_MEDIA_REFS", approvalKey: "LM_ANICCA_EN_CARD_INSTAGRAM_APPROVAL_REF", telegramLane: "anicca-en-card-instagram", freshHookText: true },
  "run-anicca-en-widget-instagram": { name: "Anicca EN Widget Instagram", product: "anicca-ios", format: "reelclaw-widget", locale: "en", platform: "instagram", account: "@anicca.en", instagramProfileRef: "profile://instagram/anicca.en", integrationId: "cmn8y95rg02d2qx0y09bbk5pb", slots: ANICCA_EN_WIDGET_INSTAGRAM_SLOTS, packKey: "LM_ANICCA_EN_WIDGET_PRODUCTION_PACK_REF", mediaKey: "LM_ANICCA_EN_WIDGET_PRODUCTION_MEDIA_REFS", approvalKey: "LM_ANICCA_EN_WIDGET_PRODUCTION_APPROVAL_REF", telegramLane: "anicca-en-widget-instagram", freshHookText: true },
  "run-anicca-ai-youtube": { name: "Anicca AI YouTube", product: "anicca-ios", format: "reelclaw-widget", locale: "en", platform: "youtube", account: "@anicca-ai", integrationId: "cmq3u37gi005iqp0y90a2w92n", slots: ANICCA_AI_YOUTUBE_SLOTS, packKey: "LM_ANICCA_AI_YOUTUBE_PACK_REF", mediaKey: "LM_ANICCA_AI_YOUTUBE_MEDIA_REFS", approvalKey: "LM_ANICCA_AI_YOUTUBE_APPROVAL_REF", telegramLane: "anicca-ai-youtube", freshHookText: true },
  "run-anicca-affirmation-youtube": { name: "Anicca Affirmation YouTube", product: "anicca-ios", format: "reelclaw-card", locale: "en", platform: "youtube", account: "@life-manager-m4p", integrationId: "cmn8ymq6c02oio70y5ea1trv8", slots: ANICCA_AFFIRMATION_YOUTUBE_SLOTS, packKey: "LM_ANICCA_AFFIRMATION_YOUTUBE_PACK_REF", mediaKey: "LM_ANICCA_AFFIRMATION_YOUTUBE_MEDIA_REFS", approvalKey: "LM_ANICCA_AFFIRMATION_YOUTUBE_APPROVAL_REF", telegramLane: "anicca-affirmation-youtube", freshHookText: true },
  "run-anicca-ja-widget-instagram": { name: "Anicca JA Widget Instagram", product: "anicca-ios", format: "reelclaw-widget", locale: "ja", platform: "instagram", account: "@anicca.jp.videos", instagramProfileRef: "profile://instagram/anicca.jp.videos", integrationId: "cmmzzg2es0539p30ycb94ayx0", slots: ANICCA_JA_WIDGET_INSTAGRAM_SLOTS, packKey: "LM_ANICCA_JA_WIDGET_PRODUCTION_PACK_REF", mediaKey: "LM_ANICCA_JA_WIDGET_PRODUCTION_MEDIA_REFS", approvalKey: "LM_ANICCA_JA_WIDGET_PRODUCTION_APPROVAL_REF", telegramLane: "anicca-ja-widget-instagram", freshHookText: true },
  "run-anicca-jp4": { name: "Anicca JP4", product: "anicca-ios", format: "reelclaw-card", locale: "ja", platform: "tiktok", account: "@anicca.jp4", integrationId: "cmn8x8hdv028uqx0y4gdfse5t", slots: ANICCA_JP4_SLOTS, packKey: "LM_ANICCA_JP4_PACK_REF", mediaKey: "LM_ANICCA_JP4_MEDIA_REFS", approvalKey: "LM_ANICCA_JP4_TIKTOK_APPROVAL_REF", telegramLane: "anicca-jp4-ja-tiktok", freshHookText: true },
  "run-anicca-he": { name: "Anicca HE", product: "anicca-ios", format: "reelclaw-card", locale: "ja", platform: "tiktok", account: "@anicca.he", integrationId: "cmq2aoena08bhqp0yx1epjcik", slots: ANICCA_HE_SLOTS, packKey: "LM_ANICCA_HE_PACK_REF", mediaKey: "LM_ANICCA_HE_MEDIA_REFS", approvalKey: "LM_ANICCA_HE_TIKTOK_APPROVAL_REF", telegramLane: "anicca-he-ja-tiktok", freshHookText: true },
  // @capafy.hooklab is not connected to Postiz yet (2026-10-05) -- no literal
  // integration id is ever written here; integrationEnvKey is resolved from
  // the environment at run time and the lane fails closed when it is unset
  // (see runHonneJaCycle below), instead of a hardcoded placeholder id.
  "run-capafy-ig": { name: "Capafy IG Reel", product: "capafy-skills", format: "reelclaw-card", locale: "en", platform: "instagram", account: "@capafy.hooklab", instagramProfileRef: "profile://instagram/capafy.hooklab", integrationEnvKey: "CAPAFY_IG_POSTIZ_INTEGRATION_ID", slots: CAPAFY_IG_SLOTS, packKey: "LM_CAPAFY_IG_PACK_REF", mediaKey: "LM_CAPAFY_IG_MEDIA_REFS", approvalKey: "LM_CAPAFY_IG_INSTAGRAM_APPROVAL_REF", telegramLane: "capafy-ig-reel", contentGenerator: "capafy" },
});

function required(value, label) {
  const text = String(value == null ? "" : value).trim();
  if (!text) throw new Error(`${label} is required`);
  return text;
}

function parseArgs(argv) {
  if (!LANES[argv[0]] || ![1, 3].includes(argv.length) || (argv.length === 3 && argv[1] !== "--slot")) {
    throw new Error("usage: honne-ja-cycle.js <run|run-anicca-main|run-anicca-main-instagram|run-anicca-en-card-instagram|run-anicca-en-widget-instagram|run-anicca-ai-youtube|run-anicca-affirmation-youtube|run-anicca-ja-widget-instagram|run-anicca-jp4|run-anicca-he|run-capafy-ig> [--slot <ISO instant>]");
  }
  return { lane: LANES[argv[0]], slot: argv[1] ? String(argv[2]) : null };
}

function runSlot(slot, nowMs, slots = PRODUCTION_SLOTS) {
  const value = slot || marketingVideoDueSlot(nowMs, "Asia/Tokyo", slots);
  if (!value) throw Object.assign(new Error("marketing cycle has no due slot yet"), { code: "NO_DUE_SLOT" });
  const slotMs = Date.parse(String(value));
  if (!Number.isFinite(slotMs) || new Date(slotMs).toISOString() !== value) throw new Error("honne JA cycle run timestamp is invalid");
  return value;
}

function telegramNativeUrlVerified(lane, env, publicUrl) {
  return !lane.verifiedDirectUrlKey
    || String(env[lane.verifiedDirectUrlKey] || "").trim() === publicUrl;
}

function historyProvider(dataDir) {
  const file = path.join(dataDir, "marketing", "receipts.jsonl");
  return { async list(scope) {
    if (!fs.existsSync(file)) return [];
    return fs.readFileSync(file, "utf8").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line).receipt)
      .filter((receipt) => receipt && receipt.kind === "marketing_video_artifact"
        && receipt.product_id === scope.productId && receipt.format_id === scope.formatId
        && receipt.locale === scope.locale && verifyMarketingVideoGenerationReceipt(receipt));
  } };
}

async function executeJob(store, job, workerId, handler) {
  const existing = await store.readReceipt({ tenantId: job.tenant_id, jobId: job.job_id });
  if (existing) return existing;
  const claim = await store.claimJob({ tenantId: job.tenant_id, jobId: job.job_id, capability: job.capability, workerId, leaseSeconds: 300 });
  if (!claim) throw new Error(`honne JA ${job.capability} job is not claimable`);
  await executeCapabilityJob(claim, {
    workerId,
    handlers: { [job.capability]: handler },
    heartbeatJob: (input) => store.heartbeatJob(input),
    completeJob: (input) => store.completeJob(input),
    failJob: (input) => store.failJob(input),
    leaseSeconds: 300,
  });
  const receipt = await store.readReceipt({ tenantId: job.tenant_id, jobId: job.job_id });
  if (!receipt) throw new Error(`honne JA ${job.capability} receipt is unavailable`);
  return receipt;
}

function services(env, dataDir, tenantId, lane) {
  const objectStore = createContentObjectStore({ objectDir: path.join(dataDir, "objects") });
  const scoped = (requestTenantId) => {
    if (requestTenantId !== tenantId) throw new Error("honne JA tenant scope mismatch");
  };
  const secretProvider = { async get(requestTenantId, ref) {
    scoped(requestTenantId);
    if (ref === "secret://postiz/api-key") return required(env.LM_POSTIZ_API_KEY, "LM_POSTIZ_API_KEY");
    if (ref === "secret://telegram/bot-token") return required(env.LM_TELEGRAM_BOT_TOKEN, "LM_TELEGRAM_BOT_TOKEN");
    throw new Error("honne JA secret reference is not allowed");
  } };
  return {
    publication: createMarketingVideoPublicationLoopAdapter({
      objectStore,
      secretProvider,
      integrationProvider: { async get(requestTenantId, ref) {
        scoped(requestTenantId);
        if (ref !== lane.integrationRef) throw new Error(`${lane.name} ${lane.platform} integration scope mismatch`);
        return lane.integrationId;
      } },
      ledgerPath: (requestTenantId, productId) => path.join(dataDir, "tenants", encodeURIComponent(requestTenantId), "marketing", "video-publication", encodeURIComponent(productId), "distribution.jsonl"),
    }),
    liveness: (job) => executeMarketingLivenessJob(job, {
      secretProvider,
      chatProvider: { async get(requestTenantId, ref) {
        scoped(requestTenantId);
        if (ref !== "telegram-chat://owner") throw new Error("honne JA Telegram chat scope mismatch");
        return required(env.LM_TELEGRAM_ALERT_CHAT_ID, "LM_TELEGRAM_ALERT_CHAT_ID");
      } },
    }),
  };
}

async function runHonneJaCycle(argv, deps = {}) {
  const parsed = parseArgs(argv);
  const env = deps.env || process.env;
  // Lanes with a literal integrationId (already Postiz-connected) keep it
  // verbatim; a lane with integrationEnvKey instead (not yet connected, e.g.
  // run-capafy-ig) resolves it from the environment and fails closed with
  // the exact missing key name when unset -- never a placeholder id.
  const integrationId = parsed.lane.integrationEnvKey
    ? required(env[parsed.lane.integrationEnvKey], parsed.lane.integrationEnvKey)
    : parsed.lane.integrationId;
  const lane = { ...parsed.lane, integrationId, integrationRef: `integration://postiz/${parsed.lane.platform}/${integrationId}` };
  const dataDir = path.resolve(required(deps.dataDir || env.LM_DATA_DIR, "LM_DATA_DIR"));
  const tenantId = required(env.LM_RUNTIME_TENANT_ID, "LM_RUNTIME_TENANT_ID");
  if (tenantId !== TENANT) throw new Error("honne JA cycle tenant is invalid");
  const nowMs = deps.nowMs == null ? Date.now() : deps.nowMs;
  const slot = runSlot(parsed.slot, nowMs, lane.slots);
  const packRef = required(env[lane.packKey], lane.packKey);
  const mediaRefs = required(env[lane.mediaKey], lane.mediaKey).split(",").map((value) => value.trim()).filter(Boolean);
  const approvalRef = required(env[lane.approvalKey], lane.approvalKey);
  const objectStore = createContentObjectStore({ objectDir: path.join(dataDir, "objects") });
  const approval = JSON.parse(fs.readFileSync(objectStore.resolve(approvalRef), "utf8"));
  if (approval.scope !== "standing" || approval.product_id !== lane.product || approval.locale !== lane.locale || approval.platform !== lane.platform || (approval.account && approval.account !== lane.account)) {
    throw new Error(`${lane.name} cycle approval scope is invalid`);
  }
  const store = deps.store || createMarketingLocalLedger({ dataDir });
  const generationJob = buildMarketingVideoGenerationJob({ tenantId, productId: lane.product, formatId: lane.format, locale: lane.locale, slot, packRef, mediaRefs });
  const generationQueued = await store.enqueueJob({ jobId: generationJob.job_id, tenantId, loopId: generationJob.loop_id, capability: generationJob.capability, effectClass: generationJob.effect_class, effectKey: generationJob.effect_key, inputRefs: generationJob.input_refs, maxAttempts: generationJob.max_attempts, availableAt: new Date(nowMs).toISOString() });
  // Fresh hook/title/description text is opt-in per lane via lane.freshHookText.
  // Anicca uses the local deterministic copy bank; the Capafy lane keeps its
  // own local skill/listing selector and records that earner's CTA URL.
  let capafyCtaUrl = null;
  const textGenerator = lane.contentGenerator === "capafy"
    ? (deps.textGenerator || (async (args) => {
      const generated = await capafyReelTextGenerator({ ...args, nowMs });
      capafyCtaUrl = generated.ctaUrl;
      return generated;
    }))
    : lane.freshHookText
      ? (deps.textGenerator || ((args) => generateVideoHookText({
        ...args,
        variantSeed: `${lane.name}:${slot}`,
      })))
      : null;
  const generationAdapter = createMarketingVideoGenerationLoopAdapter({ dataDir, historyProvider: historyProvider(dataDir), metricsProvider: deps.metricsProvider || createCreativeMetricsProvider(dataDir), now: () => new Date(nowMs).toISOString(), ...(textGenerator ? { textGenerator } : {}) });
  const artifact = await executeJob(store, generationJob, "honne-ja-cycle", (job) => generationAdapter.execute(job));
  const publicationCreativeId = `${artifact.creative_id}-${slot.replace(/[^A-Za-z0-9]/g, "")}`;
  // Capafy's CTA is a dynamic per-earner capafy.ai link (?ct=capafy-reel-<slug>),
  // not the fixed App Store url buildMarketingCtaCaptionRef looks up per
  // product -- see apps/life-manager/lib/capafy-reel-content.js.
  const captionRef = lane.contentGenerator === "capafy"
    ? buildCapafyReelCaptionRef({
      objectStore,
      workspaceDir: path.join(dataDir, "tenants", encodeURIComponent(tenantId), "marketing", "video-generation"),
      ctaUrl: capafyCtaUrl,
      locale: lane.locale,
    })
    : buildMarketingCtaCaptionRef({
      objectStore,
      workspaceDir: path.join(dataDir, "tenants", encodeURIComponent(tenantId), "marketing", "video-generation"),
      baseCaptionRef: artifact.copy_ref,
      productId: lane.product,
      platform: lane.platform,
      locale: lane.locale,
    });
  const publicationJob = buildMarketingVideoPublicationJob({ tenantId, productId: lane.product, formatId: lane.format, form: artifact.form, locale: lane.locale, slot, creativeId: publicationCreativeId, platform: lane.platform, videoRef: artifact.video_ref, captionRef, approvalRef, instagramProfileRef: lane.platform === "instagram" ? lane.instagramProfileRef : "profile://instagram/unassigned", postizTokenRef: "secret://postiz/api-key", ...(lane.platform === "instagram" ? { instagramIntegrationRef: lane.integrationRef } : lane.platform === "youtube" ? { youtubeIntegrationRef: lane.integrationRef } : { tiktokIntegrationRef: lane.integrationRef }) });
  const publicationQueued = await store.enqueueJob({ jobId: publicationJob.job_id, tenantId, loopId: publicationJob.loop_id, capability: publicationJob.capability, effectClass: publicationJob.effect_class, effectKey: publicationJob.effect_key, inputRefs: publicationJob.input_refs, maxAttempts: publicationJob.max_attempts, availableAt: new Date(nowMs).toISOString() });
  const runtime = services(env, dataDir, tenantId, lane);
  const publication = await executeJob(store, publicationJob, "honne-ja-cycle", (job) => runtime.publication.execute(job));
  const direct = lane.platform === "instagram"
    ? /^https:\/\/www\.instagram\.com\/reel\/[A-Za-z0-9_-]+\/?$/
    : lane.platform === "youtube"
      ? /^https:\/\/www\.youtube\.com\/(?:shorts\/[A-Za-z0-9_-]+|watch\?v=[A-Za-z0-9_-]+(?:&[^#]+)?)\/?$/
      : new RegExp(`^https://www\\.tiktok\\.com/${lane.account}/video/\\d+/?$`);
  if (!verifyMarketingVideoPublicationReceipt(publication) || publication.provider_reconciled !== true || !direct.test(publication.public_url)) {
    throw new Error(`${lane.name} publication receipt is not account-bound and reconciled`);
  }
  const publicationResult = {
    created: publicationQueued.created,
    status: publication.status,
    provider_reconciled: publication.provider_reconciled === true,
    replay_created: !publicationQueued.created,
    public_url: publication.public_url,
    provider_post_id: publication.provider_post_id,
  };
  if (!telegramNativeUrlVerified(lane, env, publication.public_url)) {
    return { slot, generation: { created: generationQueued.created, creative_id: artifact.creative_id }, publication: publicationResult, telegram: { created: false, held: true, message_id: null } };
  }
  const telegramJob = buildMarketingLivenessJob({ tenantId, telegramTokenRef: "secret://telegram/bot-token", telegramChatRef: "telegram-chat://owner", payload: { lane: lane.telegramLane, product: lane.product, locale: lane.locale, platform: lane.platform, account: lane.account, slot, status: "published", public_url: publication.public_url, retry_state: "not_required" } });
  const telegramQueued = await store.enqueueJob({ jobId: telegramJob.job_id, tenantId, loopId: telegramJob.loop_id, capability: telegramJob.capability, effectClass: telegramJob.effect_class, effectKey: telegramJob.effect_key, inputRefs: telegramJob.input_refs, maxAttempts: telegramJob.max_attempts, availableAt: new Date(nowMs).toISOString() });
  const telegram = await executeJob(store, telegramJob, "honne-ja-cycle", runtime.liveness);
  return { slot, generation: { created: generationQueued.created, creative_id: artifact.creative_id }, publication: publicationResult, telegram: { created: telegramQueued.created, held: false, message_id: telegram.message_id } };
}

if (require.main === module) runHonneJaCycle(process.argv.slice(2)).then((result) => process.stdout.write(`${JSON.stringify(result)}\n`)).catch((error) => { if (error && error.code === "NO_DUE_SLOT") { process.stdout.write(`${JSON.stringify({ status: "no_due_slot", reason: error.message })}\n`); return; } process.stderr.write(`${error.message}\n`); process.exitCode = 1; });

module.exports = { ANICCA_AFFIRMATION_YOUTUBE_SLOTS, ANICCA_AI_YOUTUBE_SLOTS, ANICCA_EN_CARD_INSTAGRAM_SLOTS, ANICCA_EN_WIDGET_INSTAGRAM_SLOTS, ANICCA_HE_SLOTS, ANICCA_JA_WIDGET_INSTAGRAM_SLOTS, ANICCA_JP4_SLOTS, ANICCA_MAIN_INSTAGRAM_SLOTS, ANICCA_MAIN_SLOTS, CAPAFY_IG_SLOTS, PRODUCTION_SLOTS, parseArgs, runHonneJaCycle, runSlot, telegramNativeUrlVerified };
