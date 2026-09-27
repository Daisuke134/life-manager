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
const { buildMarketingVideoPublicationJob } = require("../lib/marketing-video-publication-adapter.js");
const { createCreativeMetricsProvider } = require("../lib/marketing-creative-metrics.js");
const { PROMOTION_CONFIRMATION } = require("../lib/marketing-canary.js");
const { HONNE_EN_SLOTS } = require("../lib/honne-en-shadow-runtime.js");
const { marketingVideoDueSlot } = require("../lib/honne-ja-shadow-schedule.js");
const { runHonneEnCanary } = require("./honne-en-canary.js");

const TENANT = "dais-local";
const PRODUCT = "honne-ai";
const FORMAT = "reelclaw";
const LOCALE = "en";
const INTEGRATION_ID = "cmoig11ew001zlv0yk6vqo1us";
const INTEGRATION_REF = `integration://postiz/tiktok/${INTEGRATION_ID}`;

function required(value, label) {
  const text = String(value == null ? "" : value).trim();
  if (!text) throw new Error(`${label} is required`);
  return text;
}

function campaignCaptionRef(objectStore, dataDir, copyRef, campaignUrl) {
  let url; try { url = new URL(required(campaignUrl, "Honne EN campaign URL")); } catch { throw new Error("Honne EN campaign URL is invalid"); }
  if (url.protocol !== "https:" || url.hostname !== "apps.apple.com" || !/\/id6759667221$/.test(url.pathname) || url.searchParams.get("pt") !== "93486075" || url.searchParams.get("ct") !== "honne_en_base_20260823" || url.username || url.password || url.hash) throw new Error("Honne EN campaign URL is invalid");
  const caption = `${fs.readFileSync(objectStore.resolve(copyRef), "utf8").trimEnd()}\n\n${url.href}\n`; const workspace = path.join(dataDir, "tenants/dais-local/marketing/video-generation"); fs.mkdirSync(workspace, { recursive: true, mode: 0o700 }); const candidate = path.join(workspace, `.honne-en-campaign-${process.pid}.txt`); fs.writeFileSync(candidate, caption, { mode: 0o600, flag: "wx" }); try { return objectStore.import(candidate).ref; } finally { fs.unlinkSync(candidate); }
}

function parseArgs(argv) {
  if (argv[0] !== "run" || ![1, 3].includes(argv.length) || (argv.length === 3 && argv[1] !== "--slot")) {
    throw new Error("usage: honne-en-cycle.js run [--slot <ISO instant>]");
  }
  return argv[1] ? String(argv[2]) : null;
}

function runSlot(slot, nowMs) {
  const value = slot || marketingVideoDueSlot(nowMs, "Asia/Tokyo", HONNE_EN_SLOTS);
  if (!value) throw Object.assign(new Error("honne EN cycle has no due slot yet"), { code: "NO_DUE_SLOT" });
  const slotMs = Date.parse(String(value));
  if (!Number.isFinite(slotMs) || new Date(slotMs).toISOString() !== value) throw new Error("honne EN cycle run timestamp is invalid");
  return value;
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

async function generate(store, job, dataDir, nowIso, metricsProvider) {
  const queued = await store.enqueueJob({
    jobId: job.job_id, tenantId: job.tenant_id, loopId: job.loop_id, capability: job.capability,
    effectClass: job.effect_class, effectKey: job.effect_key, inputRefs: job.input_refs,
    maxAttempts: job.max_attempts, availableAt: nowIso,
  });
  const existing = await store.readReceipt({ tenantId: job.tenant_id, jobId: job.job_id });
  if (existing) return { created: queued.created, receipt: existing };
  const claim = await store.claimJob({ tenantId: job.tenant_id, jobId: job.job_id, capability: job.capability, workerId: "honne-en-cycle", leaseSeconds: 180 });
  if (!claim) throw new Error("honne EN generation job is not claimable");
  try {
    const adapter = createMarketingVideoGenerationLoopAdapter({ dataDir, historyProvider: historyProvider(dataDir), metricsProvider: metricsProvider || createCreativeMetricsProvider(dataDir), now: () => nowIso });
    const receipt = (await adapter.execute(claim)).receipt;
    await store.completeJob({ tenantId: claim.tenant_id, jobId: claim.job_id, attempt: claim.attempt, workerId: claim.lease_owner, receipt });
    return { created: queued.created, receipt };
  } catch (error) {
    await store.failJob({ tenantId: claim.tenant_id, jobId: claim.job_id, attempt: claim.attempt, workerId: claim.lease_owner, errorCode: "GENERATION_FAILED", unknownEffect: false });
    throw error;
  }
}

async function enqueuePublication(store, job, availableAt) {
  const existing = await store.readJob({ tenantId: job.tenant_id, jobId: job.job_id });
  if (existing) return { created: false, job: existing };
  return store.enqueueJob({
    jobId: job.job_id, tenantId: job.tenant_id, loopId: job.loop_id, capability: job.capability,
    effectClass: job.effect_class, effectKey: job.effect_key, inputRefs: job.input_refs,
    maxAttempts: job.max_attempts, availableAt,
  });
}

async function runHonneEnCycle(argv, deps = {}) {
  const requestedSlot = parseArgs(argv);
  const env = deps.env || process.env;
  const dataDir = path.resolve(required(deps.dataDir || env.LM_DATA_DIR, "LM_DATA_DIR"));
  const tenantId = required(env.LM_RUNTIME_TENANT_ID, "LM_RUNTIME_TENANT_ID");
  if (tenantId !== TENANT) throw new Error("honne EN cycle tenant is invalid");
  const nowMs = deps.nowMs == null ? Date.now() : deps.nowMs;
  const slot = runSlot(requestedSlot, nowMs);
  const packRef = required(env.LM_HONNE_EN_PACK_REF, "LM_HONNE_EN_PACK_REF");
  const mediaRefs = required(env.LM_HONNE_EN_MEDIA_REFS, "LM_HONNE_EN_MEDIA_REFS").split(",").map((value) => value.trim()).filter(Boolean);
  const approvalRef = required(env.LM_HONNE_EN_PUBLICATION_APPROVAL_REF, "LM_HONNE_EN_PUBLICATION_APPROVAL_REF");
  const objectStore = createContentObjectStore({ objectDir: path.join(dataDir, "objects") });
  const approval = JSON.parse(fs.readFileSync(objectStore.resolve(approvalRef), "utf8"));
  if (approval.scope !== "standing" || approval.product_id !== PRODUCT || approval.locale !== LOCALE || approval.platform !== "tiktok") {
    throw new Error("honne EN cycle approval scope is invalid");
  }
  const store = deps.store || createMarketingLocalLedger({ dataDir });
  const generationJob = buildMarketingVideoGenerationJob({ tenantId, productId: PRODUCT, formatId: FORMAT, locale: LOCALE, slot, packRef, mediaRefs });
  const generation = await generate(store, generationJob, dataDir, new Date(nowMs).toISOString(), deps.metricsProvider);
  const captionRef = campaignCaptionRef(objectStore, dataDir, generation.receipt.copy_ref, env.LM_HONNE_EN_CAMPAIGN_URL);
  const publicationJob = buildMarketingVideoPublicationJob({
    tenantId, productId: PRODUCT, formatId: FORMAT, form: generation.receipt.form, locale: LOCALE, slot,
    creativeId: generation.receipt.creative_id, platform: "tiktok", videoRef: generation.receipt.video_ref,
    captionRef, approvalRef, instagramProfileRef: "profile://instagram/unassigned",
    postizTokenRef: "secret://postiz/api-key", tiktokIntegrationRef: INTEGRATION_REF,
  });
  await enqueuePublication(store, publicationJob, new Date(nowMs).toISOString());
  const result = await runHonneEnCanary(["run", "--tenant", tenantId, "--job-id", publicationJob.job_id], {
    store,
    env: { ...env, LM_DATA_DIR: dataDir, LM_HONNE_EN_CANARY_TRANSPORT: "postiz", LM_HONNE_EN_CANARY_CONFIRM: PROMOTION_CONFIRMATION, LM_HONNE_EN_TIKTOK_INTEGRATION_REF: INTEGRATION_REF, LM_HONNE_EN_TIKTOK_INTEGRATION: INTEGRATION_ID, LM_HONNE_EN_CANARY_WORKER_ID: "honne-en-cycle" },
  });
  return { slot, generation: { job_id: generationJob.job_id, created: generation.created, creative_id: generation.receipt.creative_id }, publication: result.publication, telegram: result.telegram };
}

if (require.main === module) runHonneEnCycle(process.argv.slice(2)).then((result) => process.stdout.write(`${JSON.stringify(result)}\n`)).catch((error) => { if (error && error.code === "NO_DUE_SLOT") { process.stdout.write(`${JSON.stringify({ status: "no_due_slot", reason: error.message })}\n`); return; } process.stderr.write(`${error.message}\n`); process.exitCode = 1; });

module.exports = { campaignCaptionRef, enqueuePublication, parseArgs, runHonneEnCycle, runSlot };
