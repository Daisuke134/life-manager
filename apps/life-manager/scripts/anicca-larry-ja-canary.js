#!/usr/bin/env node
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const { createContentObjectStore } = require("../lib/content-object-store.js");
const { createMarketingLocalLedger } = require("../lib/marketing-local-ledger.js");
const { isMarketingLaneManifest } = require("../lib/marketing-lane-manifest.js");
const {
  ACCOUNT_ID,
  EN_AFFIRMATION_LANE,
  EN_AFFIRMATION_TIKTOK_LANE,
  EN_SLIDESHOW_TIKTOK_LANE,
  JA_BUDDHA_TIKTOK_LANE,
  JA_JP1_TIKTOK_LANE,
  JA_MAIN_TIKTOK_LANE,
  INTEGRATION_REF,
  JA_LANE,
  buildMarketingNativeCarouselPublicationJob,
  createMarketingNativeCarouselPublicationLoopAdapter,
  verifyMarketingNativeCarouselPublicationReceipt,
} = require("../lib/marketing-native-carousel-publication-adapter.js");
const {
  buildMarketingLivenessJob,
  executeMarketingLivenessJob,
} = require("../lib/marketing-liveness-adapter.js");
const { executeCapabilityJob } = require("./runtime-up.js");
const { armControls, restoreControls } = require("./anicca-en-widget-canary.js");
const { marketingVideoDueSlot } = require("../lib/honne-ja-shadow-schedule.js");

const TENANT = "dais-local";
const PRODUCT = "anicca-ios";
const LOCALE = "ja";
const FORMAT = "larry";
const FORM = "affirmation-carousel";
const LANE = "anicca-larry-ja-instagram";
const TOKEN_REF = "secret://postiz/api-key";
const TELEGRAM_TOKEN_REF = "secret://telegram/bot-token";
const CHAT_REF = "telegram-chat://owner";
const OBJECT_REF = /^object:\/\/sha256\/[0-9a-f]{64}$/;
const ACCOUNT_REF = "account://instagram/@ani.cca1234";
const JA_LARRY_PRODUCTION_SLOTS = Object.freeze(["10:30", "16:30", "22:30"]);
const EN_AFFIRMATION_PRODUCTION_SLOTS = Object.freeze(["10:00", "15:00", "20:00"]);
const EN_AFFIRMATION_TIKTOK_PRODUCTION_SLOTS = Object.freeze(["09:15", "14:15", "20:15"]);
const EN_SLIDESHOW_PRODUCTION_SLOTS = Object.freeze(["09:00", "15:00", "21:00"]);
const JA_MAIN_TIKTOK_PRODUCTION_SLOTS = Object.freeze(["08:00", "16:00", "22:37"]);
const JA_JP1_TIKTOK_PRODUCTION_SLOTS = Object.freeze(["06:30", "12:00", "18:00"]);
const JA_BUDDHA_TIKTOK_PRODUCTION_SLOTS = Object.freeze(["07:00", "13:00", "20:00"]);

const JA_RUNNER_LANE = JA_LANE;
const EN_RUNNER_LANE = EN_AFFIRMATION_LANE;
const EN_TIKTOK_RUNNER_LANE = EN_AFFIRMATION_TIKTOK_LANE;
const TIKTOK_SLIDESHOW_RUNNER_LANE = EN_SLIDESHOW_TIKTOK_LANE;
const JA_MAIN_TIKTOK_RUNNER_LANE = JA_MAIN_TIKTOK_LANE;
const JA_JP1_TIKTOK_RUNNER_LANE = JA_JP1_TIKTOK_LANE;
const COMMAND_LANES = Object.freeze({ run: JA_RUNNER_LANE, "run-ja-larry-production": JA_RUNNER_LANE, "run-en-affirmation": EN_RUNNER_LANE, "run-en-affirmation-production": EN_RUNNER_LANE, "run-en-affirmation-tiktok-production": EN_TIKTOK_RUNNER_LANE, "run-en-slideshow-tiktok": TIKTOK_SLIDESHOW_RUNNER_LANE, "run-en-slideshow-tiktok-production": TIKTOK_SLIDESHOW_RUNNER_LANE, "run-ja-main-tiktok": JA_MAIN_TIKTOK_RUNNER_LANE, "run-ja-main-tiktok-production": JA_MAIN_TIKTOK_RUNNER_LANE, "run-ja-jp1-tiktok-production": JA_JP1_TIKTOK_RUNNER_LANE, "run-ja-buddha-tiktok-production": JA_BUDDHA_TIKTOK_LANE });
const PRODUCTION_SLOTS = Object.freeze({ "run-ja-larry-production": JA_LARRY_PRODUCTION_SLOTS, "run-en-affirmation-production": EN_AFFIRMATION_PRODUCTION_SLOTS, "run-en-affirmation-tiktok-production": EN_AFFIRMATION_TIKTOK_PRODUCTION_SLOTS, "run-en-slideshow-tiktok-production": EN_SLIDESHOW_PRODUCTION_SLOTS, "run-ja-main-tiktok-production": JA_MAIN_TIKTOK_PRODUCTION_SLOTS, "run-ja-jp1-tiktok-production": JA_JP1_TIKTOK_PRODUCTION_SLOTS, "run-ja-buddha-tiktok-production": JA_BUDDHA_TIKTOK_PRODUCTION_SLOTS });

function required(value, label) {
  const text = String(value == null ? "" : value).trim();
  if (!text) throw new Error(`${label} is required`);
  return text;
}

function exactInstant(value, label) {
  const text = String(value || "");
  const date = new Date(text);
  if (!Number.isFinite(date.getTime()) || date.toISOString() !== text) {
    throw new Error(`${label} is invalid`);
  }
  return text;
}

function parseArgs(argv = []) {
  if (argv.length === 1 && PRODUCTION_SLOTS[argv[0]]) return { command: argv[0], slot: null };
  const lane = argv.length === 3 && argv[1] === "--slot" ? COMMAND_LANES[argv[0]] : null;
  if (lane) {
    return { command: argv[0], slot: exactInstant(argv[2], `${lane.name || "Larry"} canary slot`) };
  }
  throw new Error("usage: anicca-larry-ja-canary.js <production command> [--slot <exact ISO instant>]");
}

function parseMediaRefs(value, lane = JA_RUNNER_LANE) {
  const raw = String(value || "").trim();
  let values;
  if (raw.startsWith("[")) {
    try { values = JSON.parse(raw); } catch { throw new Error(`${lane.name} media refs are invalid`); }
  } else values = raw.split(",").map((item) => item.trim()).filter(Boolean);
  if (!Array.isArray(values) || values.length !== 6 || values.some((item) => !OBJECT_REF.test(String(item)))) {
    throw new Error(`${lane.name} media refs are invalid`);
  }
  return values.map(String);
}

function dataDirFrom(env) {
  const raw = required(env.LM_DATA_DIR, "LM_DATA_DIR");
  const dataDir = path.resolve(raw);
  if (!path.isAbsolute(raw) || dataDir === path.parse(dataDir).root) throw new Error("LM_DATA_DIR is invalid");
  return dataDir;
}

function laneConfig(env, parsed, now, lane = JA_RUNNER_LANE) {
  const dataDir = dataDirFrom(env);
  const tenantId = required(env.LM_RUNTIME_TENANT_ID, "LM_RUNTIME_TENANT_ID");
  if (tenantId !== TENANT) throw new Error("Larry JA canary tenant is invalid");
  const packRef = required(env[lane.packEnv], lane.packEnv);
  const mediaRefs = parseMediaRefs(env[lane.mediaEnv], lane);
  const captionRef = required(env[lane.captionEnv], lane.captionEnv);
  const approvalRef = required(env[lane.approvalEnv], lane.approvalEnv);
  for (const [ref, label] of [[packRef, "pack"], [captionRef, "caption"], [approvalRef, "approval"]]) {
    if (!OBJECT_REF.test(ref)) throw new Error(`${lane.name} ${label} ref is invalid`);
  }
  if (lane.packRef && (packRef !== lane.packRef || JSON.stringify(mediaRefs) !== JSON.stringify(lane.mediaRefs)
    || captionRef !== lane.captionRef || approvalRef !== lane.approvalRef)) {
    throw new Error(`${lane.name} dedicated object references are not the approved lane`);
  }
  required(env.LM_POSTIZ_API_KEY, "LM_POSTIZ_API_KEY");
  required(env.LM_TELEGRAM_BOT_TOKEN, "LM_TELEGRAM_BOT_TOKEN");
  required(env.LM_TELEGRAM_ALERT_CHAT_ID, "LM_TELEGRAM_ALERT_CHAT_ID");
  const verificationRef = String(env[lane.verificationEnv] || "").trim() || null;
  if (verificationRef && !OBJECT_REF.test(verificationRef)) throw new Error(`${lane.name} native verification ref is invalid`);
  return {
    dataDir,
    tenantId,
    slot: parsed.slot || exactInstant(now(), "Larry JA canary clock"),
    packRef,
    mediaRefs,
    captionRef,
    approvalRef,
    verificationRef,
    lane,
  };
}

function sha256Json(value) {
  return crypto.createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

function scopedSecretProvider(env, tenantId, lane = JA_RUNNER_LANE) {
  return { async get(requestTenantId, ref) {
    if (requestTenantId !== tenantId) throw new Error(`${lane.name} secret tenant scope mismatch`);
    if (ref === lane.tokenRef) return required(env.LM_POSTIZ_API_KEY, "LM_POSTIZ_API_KEY");
    if (ref === lane.telegramTokenRef) return required(env.LM_TELEGRAM_BOT_TOKEN, "LM_TELEGRAM_BOT_TOKEN");
    throw new Error(`${lane.name} secret reference is not allowed`);
  } };
}

async function executeJob(store, job, workerId, handler, execute = executeCapabilityJob) {
  const existing = await store.readReceipt({ tenantId: job.tenant_id, jobId: job.job_id });
  if (existing) return { created: false, receipt: existing };
  const claim = await store.claimJob({ tenantId: job.tenant_id, jobId: job.job_id, capability: job.capability, workerId, leaseSeconds: 300 });
  if (!claim) {
    const retained = await store.readReceipt({ tenantId: job.tenant_id, jobId: job.job_id });
    if (retained) return { created: false, receipt: retained };
    throw new Error(`Larry JA ${job.capability} job is not claimable`);
  }
  await execute(claim, {
    workerId,
    handlers: { [job.capability]: handler },
    heartbeatJob: (input) => store.heartbeatJob(input),
    completeJob: (input) => store.completeJob(input),
    failJob: (input) => store.failJob(input),
    leaseSeconds: 300,
  });
  const receipt = await store.readReceipt({ tenantId: job.tenant_id, jobId: job.job_id });
  if (!receipt) {
    const state = await store.readJob({ tenantId: job.tenant_id, jobId: job.job_id });
    const error = new Error(`Larry JA ${job.capability} receipt is unavailable`);
    if (state && state.unknown_effect === true) error.unknownEffect = true;
    throw error;
  }
  return { created: true, receipt };
}

function verifyNativeObject(ref, objectStore, receipt, trustedNow, lane = JA_RUNNER_LANE) {
  if (!ref) return false;
  let value;
  try {
    const file = objectStore.resolve(ref);
    value = JSON.parse(fs.readFileSync(file, "utf8"));
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    const evidence = String(value.evidence_ref || "");
    if (!OBJECT_REF.test(evidence)) return false;
    objectStore.resolve(evidence);
    const verifiedAt = exactInstant(value.verified_at, `${lane.name} native verification verified_at`);
    const publishedMs = Date.parse(exactInstant(receipt.published_at, `${lane.name} publication published_at`));
    const verifiedMs = Date.parse(verifiedAt);
    const trustedMs = Date.parse(exactInstant(trustedNow, `${lane.name} trusted verification clock`));
    return value.schema_version === 1
      && value.kind === "marketing_native_carousel_native_verification"
      && value.status === "verified"
      && value.product_id === lane.productId
      && value.account_id === lane.accountId
      && (value.native_owner === undefined || value.native_owner === lane.nativeOwner)
      && value.integration_ref === lane.integrationRef
      && value.public_url === receipt.public_url
      && value.pack_sha256 === receipt.pack_sha256
      && JSON.stringify(value.media_sha256) === JSON.stringify(receipt.media_sha256)
      && value.media_order_sha256 === sha256Json(receipt.media_sha256)
      && value.caption_sha256 === receipt.caption_sha256
      && publishedMs < verifiedMs
      && verifiedMs <= trustedMs;
  } catch {
    return false;
  }
}

function publicationLedgerPath(dataDir, tenantId, lane = JA_RUNNER_LANE) {
  return path.join(dataDir, "tenants", encodeURIComponent(tenantId), "marketing", "native-carousel-publication", lane.productId, "distribution.jsonl");
}

function enAffirmationProductionSlot(nowMs) {
  return marketingVideoDueSlot(nowMs, "Asia/Tokyo", EN_AFFIRMATION_PRODUCTION_SLOTS);
}

function jaLarryProductionSlot(nowMs) {
  return marketingVideoDueSlot(nowMs, "Asia/Tokyo", JA_LARRY_PRODUCTION_SLOTS);
}

function enSlideshowProductionSlot(nowMs) {
  return marketingVideoDueSlot(nowMs, "Asia/Tokyo", EN_SLIDESHOW_PRODUCTION_SLOTS);
}

function assertProductionControls(config, lane) {
  const manifest = JSON.parse(fs.readFileSync(path.join(config.dataDir, "marketing", "lane-manifest.json"), "utf8"));
  const fence = JSON.parse(fs.readFileSync(path.join(config.dataDir, "marketing", "publication-effect-fence.json"), "utf8"));
  const targets = manifest.lanes.filter((row) => row.integration_id === lane.integrationId && row.profile === (lane.manifestProfile || lane.accountId));
  if (!isMarketingLaneManifest(manifest) || fence.state !== "closed" || targets.length !== 1
    || targets[0].lane_state !== "production-armed" || targets[0].production_armed !== true || targets[0].target_daily_limit !== 3) {
    throw new Error(`${lane.name} production controls are invalid`);
  }
}

async function runAniccaCarouselCanary(argv = [], deps = {}) {
  let parsed = parseArgs(argv);
  const lane = COMMAND_LANES[parsed.command];
  const production = Boolean(PRODUCTION_SLOTS[parsed.command]);
  const env = deps.env || process.env;
  const now = deps.now || (() => new Date().toISOString());
  const trustedNow = exactInstant(now(), `${lane.name} canary clock`);
  if (production && !parsed.slot) {
    const slot = marketingVideoDueSlot(Date.parse(trustedNow), "Asia/Tokyo", PRODUCTION_SLOTS[parsed.command]);
    if (!slot) throw Object.assign(new Error(`${lane.name} production has no due slot yet`), { code: "NO_DUE_SLOT" });
    parsed = { ...parsed, slot };
  }
  const clock = () => trustedNow;
  const config = laneConfig(env, parsed, clock, lane);
  const objectStore = deps.objectStore || createContentObjectStore({ objectDir: path.join(config.dataDir, "objects") });
  const secretProvider = deps.secretProvider || scopedSecretProvider(env, config.tenantId, lane);
  const store = deps.store || createMarketingLocalLedger({ dataDir: config.dataDir, env, now: clock });
  const publicationJob = buildMarketingNativeCarouselPublicationJob({
    tenantId: config.tenantId,
    productId: lane.productId,
    formatId: lane.formatId,
    form: lane.form,
    locale: lane.locale,
    slot: config.slot,
    creativeId: lane.creativeId || "LARRY-JA-CANARY",
    accountId: lane.accountId,
    integrationRef: lane.integrationRef,
    packRef: config.packRef,
    mediaRefs: config.mediaRefs,
    captionRef: config.captionRef,
    approvalRef: config.approvalRef,
    postizTokenRef: lane.tokenRef,
    slotScopedEffect: production,
  });
  const publicationAdapter = createMarketingNativeCarouselPublicationLoopAdapter({
    objectStore,
    secretProvider,
    ledgerPath: () => publicationLedgerPath(config.dataDir, config.tenantId, lane),
    ...(deps.runDistribution ? { runDistribution: deps.runDistribution } : {}),
    now: clock,
  });
  const existingPublication = await store.readReceipt({ tenantId: publicationJob.tenant_id, jobId: publicationJob.job_id });
  const controlLane = {
    ...lane,
    tenant: TENANT,
    product: lane.productId,
    account: lane.accountId,
    format: lane.formatId,
    enforceApprovedPack: true,
  };
  if (production) assertProductionControls(config, lane);
  const controls = !production && lane.manifestAccount && !existingPublication
    ? armControls(config, publicationJob, controlLane)
    : null;
  let queued;
  let publicationRun;
  let publicationError;
  let restoreError;
  try {
    queued = await store.enqueueJob({ ...publicationJob, availableAt: trustedNow });
    publicationRun = await executeJob(store, publicationJob, lane.workerLabel, (job) => publicationAdapter.execute(job), deps.executeCapabilityJob || executeCapabilityJob);
  } catch (error) {
    publicationError = error;
  } finally {
    if (controls) {
      try { restoreControls(controls.paths, controls); } catch (error) { restoreError = error; }
    }
  }
  if (restoreError) {
    const error = new Error(`${lane.name} publication controls could not be restored`);
    error.unknownEffect = true;
    if (publicationError) error.cause = publicationError;
    throw error;
  }
  if (publicationError) throw publicationError;
  const publication = publicationRun.receipt;
  if (!verifyMarketingNativeCarouselPublicationReceipt(publication) || publication.provider_reconciled !== true) {
    const error = new Error("Larry JA publication receipt is not reconciled");
    error.unknownEffect = true;
    throw error;
  }
  const publicationResult = { created: queued.created && publicationRun.created, public_url: publication.public_url, provider_post_id: publication.provider_post_id };
  const postizPhotoVerified = lane.platform === "tiktok"
    && publication.public_url == null
    && publication.provider_state === "PUBLISHED"
    && publication.provider_posting_method === "DIRECT_POST"
    && publication.provider_content_sha256 === publication.caption_sha256;
  const postizProductionVerified = production && publication.status === "published" && publication.provider_reconciled === true;
  if (!postizPhotoVerified && !postizProductionVerified && !verifyNativeObject(config.verificationRef, objectStore, publication, trustedNow, lane)) {
    return { slot: config.slot, publication: publicationResult, telegram: { created: false, held: true, message_id: null } };
  }
  const telegramJob = buildMarketingLivenessJob({
    tenantId: config.tenantId,
    telegramTokenRef: lane.telegramTokenRef,
    telegramChatRef: lane.chatRef,
    payload: { lane: lane.lane, product: lane.productId, locale: lane.locale, platform: lane.platform, account: lane.nativeOwner, slot: config.slot, status: "published", public_url: postizPhotoVerified ? "unavailable" : publication.public_url, retry_state: "not_required", ...(postizPhotoVerified ? { publication_evidence: "postiz_published_exact_assets" } : {}) },
  });
  const telegramQueued = await store.enqueueJob({ ...telegramJob, availableAt: trustedNow });
  const telegramRun = await executeJob(store, telegramJob, lane.workerLabel, (job) => executeMarketingLivenessJob(job, { secretProvider, chatProvider: { get: async (tenantId, ref) => { if (tenantId !== config.tenantId || ref !== lane.chatRef) throw new Error(`${lane.name} Telegram chat scope mismatch`); return required(env.LM_TELEGRAM_ALERT_CHAT_ID, "LM_TELEGRAM_ALERT_CHAT_ID"); } }, sendTelegram: deps.sendTelegram, now: clock }), deps.executeCapabilityJob || executeCapabilityJob);
  return { slot: config.slot, publication: publicationResult, telegram: { created: telegramQueued.created && telegramRun.created, held: false, message_id: telegramRun.receipt.message_id } };
}

function runAniccaLarryJaCanary(argv = [], deps = {}) {
  if (parseArgs(argv).command !== "run") throw new Error("Larry JA canary accepts only the run command");
  return runAniccaCarouselCanary(argv, deps);
}

function runAniccaEnAffirmationInstagramCanary(argv = [], deps = {}) {
  if (parseArgs(argv).command !== "run-en-affirmation") throw new Error("EN affirmation canary accepts only the run-en-affirmation command");
  return runAniccaCarouselCanary(argv, deps);
}

function runAniccaEnSlideshowTikTokCanary(argv = [], deps = {}) {
  if (parseArgs(argv).command !== "run-en-slideshow-tiktok") throw new Error("EN slideshow TikTok canary accepts only the run-en-slideshow-tiktok command");
  return runAniccaCarouselCanary(argv, deps);
}

function runAniccaJp1TikTokCanary(argv = [], deps = {}) {
  if (parseArgs(argv).command !== "run-ja-jp1-tiktok-production") throw new Error("JA jp1 TikTok canary accepts only the run-ja-jp1-tiktok-production command");
  return runAniccaCarouselCanary(argv, deps);
}

if (require.main === module) {
  runAniccaCarouselCanary(process.argv.slice(2)).then((result) => process.stdout.write(`${JSON.stringify(result)}\n`)).catch((error) => { if (error && error.code === "NO_DUE_SLOT") { process.stdout.write(`${JSON.stringify({ status: "no_due_slot", reason: error.message })}\n`); return; } process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
}

module.exports = { ACCOUNT_ID, EN_AFFIRMATION_LANE, EN_AFFIRMATION_PRODUCTION_SLOTS, EN_AFFIRMATION_TIKTOK_LANE, EN_AFFIRMATION_TIKTOK_PRODUCTION_SLOTS, EN_SLIDESHOW_PRODUCTION_SLOTS, EN_SLIDESHOW_TIKTOK_LANE, INTEGRATION_REF, JA_JP1_TIKTOK_LANE, JA_JP1_TIKTOK_PRODUCTION_SLOTS, JA_LARRY_PRODUCTION_SLOTS, JA_MAIN_TIKTOK_LANE, JA_MAIN_TIKTOK_PRODUCTION_SLOTS, LANE, assertProductionControls, enAffirmationProductionSlot, enSlideshowProductionSlot, jaLarryProductionSlot, parseArgs, runAniccaCarouselCanary, runAniccaEnAffirmationInstagramCanary, runAniccaEnSlideshowTikTokCanary, runAniccaJp1TikTokCanary, runAniccaLarryJaCanary, verifyNativeObject };
