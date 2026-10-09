#!/usr/bin/env node
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const { createContentObjectStore } = require("../lib/content-object-store.js");
const { createMarketingLocalLedger } = require("../lib/marketing-local-ledger.js");
const { writeMarketingEffectIdentity } = require("../lib/marketing-effect-identity.js");
const {
  findMarketingDestinationTarget,
  loadMarketingDestinationContract,
} = require("../lib/marketing-destination-contract.js");
const {
  buildMarketingVideoPublicationJob,
  createMarketingVideoPublicationLoopAdapter,
  verifyMarketingVideoPublicationReceipt,
} = require("../lib/marketing-video-publication-adapter.js");
const { marketingVideoDueSlot } = require("../lib/honne-ja-shadow-schedule.js");
const { executeCapabilityJob } = require("./runtime-up.js");

const TENANT = "dais-local";
const FORM = "ebook-reflection-reel";
const APPROVED_CLAIMS = Object.freeze([
  "Japanese-language guided reflection ebook",
  "Digital access is sold through the owned checkout page",
]);
const APPROVED_CLAIMS_BY_PRODUCT = Object.freeze({
  "ebook-en": Object.freeze([
    "English-language guided reflection ebook",
    "Digital access is sold through the owned checkout page",
  ]),
  "ebook-ja": APPROVED_CLAIMS,
});
const PACK_FILES = Object.freeze({
  "ebook-en": "ebook-en-anicca-monk.json",
  "ebook-ja": "ebook-ja-watercolor.json",
});
const SCRIPT_POLICY = Object.freeze({
  "ebook-en": {
    language: "en",
    cta: "Read The Anicca Reset",
    sourcePrefix: "baseline.owner-authored.ebook-en.",
    tokenPattern: /^ee_[a-z2-7]{20}$/,
    captionSuffix: "#TheAniccaReset #Reflection",
    approvalId: "ebook-en-system-baseline-v1",
  },
  "ebook-ja": {
    language: "ja",
    cta: "アニッチャ・リセットを読む",
    sourcePrefix: "baseline.owner-authored.ebook-ja.",
    tokenPattern: /^ej_[a-z2-7]{20}$/,
    captionSuffix: "#アニッチャ・リセット #内省",
    approvalId: "ebook-ja-system-baseline-v1",
  },
});
const JOBS = Object.freeze({
  "ebook-en-tiktok-daily": {
    productId: "ebook-en", platform: "tiktok", accountId: "tiktok.monk_anicca",
    formatId: "ebook-avatar-iv", form: FORM, locale: "en",
  },
  "ebook-en-instagram-daily": {
    productId: "ebook-en", platform: "instagram", accountId: "instagram.monk_anicca",
    formatId: "ebook-avatar-iv", form: FORM, locale: "en",
  },
  "ebook-ja-instagram-daily": {
    productId: "ebook-ja", platform: "instagram", accountId: "instagram.obou_anicca",
    formatId: "ebook-watercolor", form: FORM, locale: "ja",
  },
  "ebook-ja-tiktok-daily": {
    productId: "ebook-ja", platform: "tiktok", accountId: "tiktok.obou_anicca",
    formatId: "ebook-watercolor", form: FORM, locale: "ja",
  },
});

function required(value, label) {
  const text = String(value == null ? "" : value).trim();
  if (!text) throw new Error(`${label} is required`);
  return text;
}

function ownerScopedPublicationId(publicationId, ownerId) {
  return `${required(publicationId, "eBook publication ID")}-${required(ownerId, "eBook owner ID")}`;
}

function manualSlotOverride(argv, ownerId, occurrenceId, pack, nowMs) {
  if (argv.length === 0 || (argv.length === 1 && argv[0] === ownerId)) return null;
  if (argv.length !== 3 || argv[0] !== ownerId || argv[1] !== "--slot-at") {
    throw new Error("eBook account owner ID is invalid");
  }
  if (!ownerId.startsWith("ebook-en-") || !occurrenceId.startsWith(`${ownerId}:manual-`)) {
    throw new Error("eBook manual slot override identity is invalid");
  }
  const slotAt = argv[2];
  const instant = Date.parse(slotAt);
  if (!Number.isFinite(instant) || new Date(instant).toISOString() !== slotAt) {
    throw new Error("eBook manual slot override is invalid");
  }
  if (instant > nowMs) throw new Error("eBook manual slot override cannot be in the future");
  if (marketingVideoDueSlot(instant + 1000, "Asia/Tokyo", pack.slots_jst) !== slotAt) {
    throw new Error("eBook manual slot override is not a configured pack slot");
  }
  return slotAt;
}

function requireExistingRenderedReceipt(stateRoot, productId, slotAt) {
  const runKey = sha256(`${productId}|${slotAt}`).slice(0, 24);
  const runId = `ebook-run.${runKey}`;
  const runRoot = path.join(stateRoot, "runs");
  const receiptPath = path.join(runRoot, `${runId}.json`);
  if (!fs.existsSync(receiptPath)) {
    throw new Error("eBook manual slot requires an existing rendered eBook receipt");
  }
  const receipt = readJson(receiptPath, "eBook manual render receipt");
  const render = receipt.render;
  const expectedOutput = path.join(stateRoot, "renders", `${runId}.mp4`);
  if (receipt.run_id !== runId || receipt.product_id !== productId || receipt.slot_at !== slotAt
      || receipt.state !== "rendered" || render?.state !== "rendered"
      || path.resolve(String(render.output || "")) !== path.resolve(expectedOutput)
      || !/^[0-9a-f]{64}$/.test(String(render.sha256 || ""))
      || !fs.existsSync(expectedOutput)
      || !fs.lstatSync(expectedOutput).isFile()
      || sha256(fs.readFileSync(expectedOutput)) !== render.sha256) {
    throw new Error("eBook manual slot receipt is not an exact completed render");
  }
  if (productId === "ebook-en") {
    const sidecarPath = path.join(runRoot, `${runId}.heygen-effect.json`);
    if (!fs.existsSync(sidecarPath)) {
      throw new Error("eBook manual slot has no completed HeyGen receipt");
    }
    const sidecar = readJson(sidecarPath, "eBook manual HeyGen receipt");
    if (sidecar.state !== "completed" || sidecar.provider_status !== "completed"
        || !sidecar.video_id || sidecar.provider_receipt_id !== sidecar.video_id
        || sidecar.video_id !== render.video_id) {
      throw new Error("eBook manual slot has no matching completed HeyGen receipt");
    }
  }
  return receipt;
}

function readJson(file, label) {
  try { return JSON.parse(fs.readFileSync(file, "utf8")); }
  catch { throw new Error(`${label} is unavailable or invalid`); }
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function atomicJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const temporary = `${file}.tmp-${process.pid}-${crypto.randomUUID()}`;
  const descriptor = fs.openSync(temporary, "wx", 0o600);
  try {
    fs.writeFileSync(descriptor, `${JSON.stringify(value)}\n`, "utf8");
    fs.fsyncSync(descriptor);
  } finally {
    fs.closeSync(descriptor);
  }
  fs.renameSync(temporary, file);
  fs.chmodSync(file, 0o600);
}

function writeEffectResult(publication) {
  const file = required(process.env.LIFE_MANAGER_RESULT_HINT_PATH, "Life Manager result hint path");
  const ownerId = required(process.env.LIFE_MANAGER_LOOP_ID, "Life Manager loop ID");
  const occurrenceId = required(process.env.LIFE_MANAGER_OCCURRENCE_ID, "Life Manager occurrence ID");
  const providerReceiptId = required(publication.provider_post_id, "Postiz receipt ID");
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(providerReceiptId)) {
    throw new Error("Postiz receipt ID is invalid");
  }
  atomicJson(file, {
    schema_version: 1,
    kind: "life_manager_effect_result",
    status: "verified_effect",
    effect: 1,
    owner_id: ownerId,
    occurrence_id: occurrenceId,
    provider: "postiz",
    provider_receipt_id: providerReceiptId,
    effect_status: "reconciled",
  });
}

function writeNoEffectResult(env, ownerId, reason) {
  const file = required(env.LIFE_MANAGER_RESULT_HINT_PATH, "Life Manager result hint path");
  const configuredOwner = required(env.LIFE_MANAGER_LOOP_ID, "Life Manager loop ID");
  const occurrenceId = required(env.LIFE_MANAGER_OCCURRENCE_ID, "Life Manager occurrence ID");
  if (configuredOwner !== ownerId || !occurrenceId.startsWith(`${ownerId}:`)
      || !["setup_required", "no_due_slot", "render_not_ready"].includes(reason)) {
    throw new Error("eBook no-effect result identity is invalid");
  }
  atomicJson(file, {
    schema_version: 1,
    kind: "life_manager_no_effect_result",
    status: "verified_no_effect",
    effect: 0,
    owner_id: ownerId,
    occurrence_id: occurrenceId,
    reason,
  });
}

function selectTarget({ root, pack, ownerId, platform, accountId }) {
  const lane = JOBS[ownerId];
  if (!lane || lane.productId !== pack?.product_id || lane.platform !== platform
      || lane.accountId !== accountId) {
    throw new Error("eBook owner does not match its locale pack or account");
  }
  const accountPath = path.join(root, "skills/earn/marketing-engine/registry/accounts", `${accountId}.json`);
  const account = readJson(accountPath, "eBook account registry");
  const entry = readJson(path.join(root, "config/loop-registry.json"), "Life Manager loop registry");
  const destinationContract = loadMarketingDestinationContract(
    path.join(root, "config/marketing-destinations.json"),
  );
  const integrationId = pack.accounts.find((row) => row.account_id === accountId)?.integration_id;
  const target = findMarketingDestinationTarget(destinationContract, {
    jobProductId: lane.productId,
    locale: lane.locale,
    platform,
    integrationId,
    jobFormatId: lane.formatId,
    mediaForm: lane.form,
  });
  if (!target) {
    const hold = destinationContract.holds.find((row) => (
      row.platform === platform
      && row.integration_id === integrationId
      && row.postiz_profile === `@${account.native_handle}`
    ));
    if (hold) {
      if (hold.target_daily_limit !== 0
          || account.schema_version !== "marketing.account.v1"
          || account.product_id !== lane.productId
          || !account.product_ids?.includes(lane.productId)
          || account.platform !== platform
          || account.publisher_integration_id !== integrationId
          || !account.allowed_renderer_ids?.includes(pack.renderer_id)) {
        throw new Error("eBook held account does not match its product and Postiz route");
      }
      return {
        account,
        target: null,
        integrationId,
        setup_required: true,
        setup_reason: hold.reason,
      };
    }
    throw new Error("eBook destination target does not match this account owner");
  }
  if (target.loop_name !== ownerId || target.entrypoint !== "apps/life-manager/scripts/ebook-distribute-daily.sh") {
    throw new Error("eBook destination target does not match this account owner");
  }
  const packPath = path.join(root, "skills/earn/marketing-engine/registry/ebook-packs", target.approved_pack);
  if (target.approved_pack_ref !== `object://sha256/${sha256(fs.readFileSync(packPath))}`) {
    throw new Error("eBook destination does not pin the exact approved pack");
  }
  const loop = entry.loops?.[ownerId];
  if (!loop || loop.label !== target.label || loop.entrypoint !== target.entrypoint
      || JSON.stringify(loop.cadence?.calendar_interval?.map((slot) =>
        `${String(slot.Hour).padStart(2, "0")}:${String(slot.Minute).padStart(2, "0")}`))
        !== JSON.stringify(pack.slots_jst)) {
    throw new Error("eBook destination schedule does not match its owner registry");
  }
  if (account.schema_version !== "marketing.account.v1"
      || account.product_id !== lane.productId || !account.product_ids?.includes(lane.productId)
      || account.platform !== platform || account.publisher_integration_id !== integrationId
      || `@${account.native_handle}` !== target.native_handle
      || target.postiz_profile !== `@${account.native_handle}`
      || !account.allowed_renderer_ids?.includes(pack.renderer_id)) {
    throw new Error("eBook account registry and destination contract differ");
  }
  if (account.status === "disabled_verified") {
    return { account, target, integrationId, setup_required: true, setup_reason: "postiz_channel_disabled" };
  }
  if (account.status !== "approved_active") throw new Error("eBook account is not approved for publishing");
  return { account, target, integrationId, setup_required: false };
}

function approvedBaselineScript(script, pack) {
  const policy = SCRIPT_POLICY[pack?.product_id];
  return Boolean(policy && script && pack
    && script.product_id === pack.product_id
    && script.language === policy.language
    && script.baseline === true
    && script.renderer_id === pack.renderer_id
    && script.cta === policy.cta
    && Array.isArray(script.source_mechanism_ids)
    && script.source_mechanism_ids.length === 1
    && script.source_mechanism_ids[0].startsWith(policy.sourcePrefix)
    && JSON.stringify(pack.allowed_claims) === JSON.stringify(APPROVED_CLAIMS_BY_PRODUCT[pack.product_id]));
}

function renderInput({ python, root, stateRoot, slotAt, product, ownerEnv = process.env }) {
  const renderer = path.join(root, "skills/earn/marketing-engine/ebook_distribute_daily.py");
  const rendererEnv = {
    HOME: ownerEnv.HOME || "",
    PATH: ownerEnv.PATH || "",
    LANG: ownerEnv.LANG || "C.UTF-8",
    LC_ALL: ownerEnv.LC_ALL || "",
    TMPDIR: ownerEnv.TMPDIR || "/tmp",
  };
  if (product === "ebook-en") {
    for (const key of ["LIFE_MANAGER_HEYGEN", "HEYGEN_NO_ANALYTICS"]) {
      const value = ownerEnv[key];
      if (typeof value === "string" && value.trim()) rendererEnv[key] = value;
    }
  }
  const result = spawnSync(python, [renderer, "--product", product, "--slot-at", slotAt,
    "--state-root", stateRoot], {
    cwd: root,
    env: rendererEnv,
    encoding: "utf8",
    timeout: 20 * 60 * 1000,
    maxBuffer: 2 * 1024 * 1024,
  });
  if (result.status !== 0) {
    let errorClass = "unknown";
    const lines = String(result.stdout || "").split(/\r?\n/).filter(Boolean);
    if (lines.length === 1) {
      try {
        const failure = JSON.parse(lines[0]);
        if (failure.schema_version === "marketing.ebook-render-failure.v1"
            && typeof failure.error_class === "string"
            && /^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(failure.error_class)) {
          errorClass = failure.error_class;
        }
      } catch {}
    }
    const exitCode = Number.isInteger(result.status) ? result.status : "unknown";
    throw new Error(`eBook renderer failed: ${errorClass} (exit ${exitCode})`);
  }
  const lines = String(result.stdout || "").split(/\r?\n/).filter(Boolean);
  if (lines.length !== 1) throw new Error("eBook renderer returned invalid JSON");
  let value;
  try { value = JSON.parse(lines[0]); }
  catch { throw new Error("eBook renderer returned invalid JSON"); }
  if (value.schema_version !== "marketing.ebook-owner-input.v1"
      || value.receipt?.state !== "rendered") {
    throw new Error(`eBook render is not ready: ${value.receipt?.state || "unknown"}`);
  }
  return value;
}

async function executeJob(store, job, workerId, handler) {
  const existing = await store.readReceipt({ tenantId: job.tenant_id, jobId: job.job_id });
  if (existing) return existing;
  const queued = await store.enqueueJob({
    jobId: job.job_id,
    tenantId: job.tenant_id,
    loopId: job.loop_id,
    capability: job.capability,
    effectClass: job.effect_class,
    effectKey: job.effect_key,
    inputRefs: job.input_refs,
    maxAttempts: job.max_attempts,
    availableAt: new Date().toISOString(),
  });
  const claim = await store.claimJob({
    tenantId: job.tenant_id,
    jobId: job.job_id,
    capability: job.capability,
    workerId,
    leaseSeconds: 300,
  });
  if (!claim) throw new Error("eBook publication job is not claimable");
  await executeCapabilityJob(claim, {
    workerId,
    handlers: { [job.capability]: handler },
    heartbeatJob: (input) => store.heartbeatJob(input),
    completeJob: (input) => store.completeJob(input),
    failJob: (input) => store.failJob(input),
    leaseSeconds: 300,
  });
  const receipt = await store.readReceipt({ tenantId: job.tenant_id, jobId: job.job_id });
  if (!receipt) throw new Error("eBook publication receipt is unavailable");
  return { ...receipt, created: queued.created };
}

function normalizePostizInstagramReceiptRoute(receipt, context, proof) {
  const identity = proof?.identity;
  const readback = proof?.provider_readback;
  const localContent = readback?.local_content;
  const integrationRef = context?.platform === "instagram" && context.integrationId
    ? `integration://postiz/instagram/${context.integrationId}`
    : "";
  const exactProof = Boolean(
    receipt
    && context?.platform === "instagram"
    && receipt.platform === "instagram"
    && receipt.provider_route === "instagram_file_script"
    && integrationRef
    && proof?.status === "ready"
    && proof.verified === true
    && proof.proof_kind === "postiz_official_readback"
    && proof.owner_id === context.ownerId
    && proof.occurrence_id === context.occurrenceId
    && proof.provider_receipt_id === receipt.provider_post_id
    && identity?.loop_id === context.ownerId
    && identity.occurrence_id === context.occurrenceId
    && identity.job_id === context.jobId
    && identity.effect_key === context.effectKey
    && identity.product_id === receipt.product_id
    && identity.format_id === receipt.format_id
    && identity.form === receipt.form
    && identity.locale === receipt.locale
    && identity.platform === receipt.platform
    && identity.creative_id === receipt.creative_id
    && identity.slot === receipt.slot
    && identity.integration_ref === integrationRef
    && identity.account_id === context.accountId
    && identity.video_sha256 === receipt.video_sha256
    && identity.caption_sha256 === receipt.caption_sha256
    && readback?.provider === "postiz"
    && readback.state === "PUBLISHED"
    && readback.post_id === receipt.provider_post_id
    && readback.public_url === receipt.public_url
    && readback.account_id === context.accountId
    && readback.integration_ref === integrationRef
    && localContent?.video_sha256 === receipt.video_sha256
    && localContent.caption_sha256 === receipt.caption_sha256
  );
  return exactProof
    ? { ...receipt, provider_route: "postiz", provider_reconciled: true }
    : receipt;
}

function verifyLegacyPostizReceipt({
  root,
  python,
  apiKey,
  dataDir,
  tenantId,
  ownerId,
  occurrenceId,
  identityPath,
  ledgerPath,
  env = process.env,
  runner = spawnSync,
}) {
  if (!path.isAbsolute(String(identityPath || ""))) return null;
  const script = path.join(root, "apps/life-manager/scripts/mobile-postiz-provider-reconcile.py");
  const result = runner(python, [
    script,
    "--verify-only",
    "--identity", identityPath,
    "--ledger", ledgerPath,
    "--owner-id", ownerId,
    "--occurrence-id", occurrenceId,
  ], {
    cwd: root,
    env: {
      HOME: env.HOME || "",
      PATH: env.PATH || "",
      LANG: env.LANG || "C.UTF-8",
      LC_ALL: env.LC_ALL || "",
      TMPDIR: env.TMPDIR || "/tmp",
      POSTIZ_API_KEY: apiKey,
      LM_RUNTIME_TENANT_ID: tenantId,
      LM_DATA_DIR: dataDir,
    },
    encoding: "utf8",
    timeout: 240 * 1000,
    maxBuffer: 4 * 1024 * 1024,
  });
  if (result.error || result.status !== 0) return null;
  try {
    return JSON.parse(String(result.stdout || "").trim());
  } catch {
    return null;
  }
}

async function run(argv = process.argv.slice(2), deps = {}) {
  const env = deps.env || process.env;
  const ownerId = required(env.LIFE_MANAGER_LOOP_ID || argv[0], "eBook owner ID");
  const lane = JOBS[ownerId];
  if (!lane || (argv.length && argv[0] !== ownerId)) {
    throw new Error("eBook account owner ID is invalid");
  }
  required(env.LIFE_MANAGER_OCCURRENCE_ID, "Life Manager occurrence ID");
  const occurrenceId = env.LIFE_MANAGER_OCCURRENCE_ID;
  const nowMs = deps.nowMs == null ? Date.now() : deps.nowMs;
  required(env.LIFE_MANAGER_RESULT_HINT_PATH, "Life Manager result hint path");
  const root = path.resolve(required(env.LIFE_MANAGER_RELEASE_ROOT, "Life Manager release root"));
  const dataDir = path.resolve(required(env.LM_DATA_DIR, "LM_DATA_DIR"));
  const tenantId = required(env.LM_RUNTIME_TENANT_ID, "LM_RUNTIME_TENANT_ID");
  if (tenantId !== TENANT) throw new Error("eBook tenant scope is invalid");

  const packFile = PACK_FILES[lane.productId];
  if (!packFile) throw new Error("eBook renderer pack is not registered");
  const pack = readJson(path.join(root, "skills/earn/marketing-engine/registry/ebook-packs", packFile),
    "eBook product pack");
  const manualSlotAt = manualSlotOverride(argv, ownerId, occurrenceId, pack, nowMs);
  const { account, target, integrationId, setup_required, setup_reason } = selectTarget({
    root, pack, ownerId, platform: lane.platform, accountId: lane.accountId,
  });
  if (setup_required) {
    writeNoEffectResult(env, ownerId, "setup_required");
    return { state: "setup_required", reason: setup_reason, owner_id: ownerId, effect: 0 };
  }
  const slotAt = manualSlotAt || marketingVideoDueSlot(nowMs, "Asia/Tokyo", pack.slots_jst);
  if (!slotAt) {
    writeNoEffectResult(env, ownerId, "no_due_slot");
    return { state: "no_due_slot", owner_id: ownerId, effect: 0 };
  }

  if (env.LM_EBOOK_PUBLISHING_ENABLED !== "true") {
    throw new Error("eBook publication readiness gate is closed");
  }
  const apiKey = required(env.LM_POSTIZ_API_KEY, "LM_POSTIZ_API_KEY");
  const stateRoot = path.join(dataDir, "marketing", "ebook");
  if (manualSlotAt) requireExistingRenderedReceipt(stateRoot, lane.productId, slotAt);
  let input;
  try {
    input = renderInput({
      python: required(env.LM_PYTHON, "LM_PYTHON"),
      root,
      stateRoot,
      slotAt,
      product: lane.productId,
      ownerEnv: env,
    });
  } catch (error) {
    // The Postiz publish effect starts only after renderInput returns. HeyGen's
    // separate create/download receipt remains in ebook_runner's sidecar.
    writeNoEffectResult(env, ownerId, "render_not_ready");
    const detail = String(error && error.message ? error.message : "");
    const match = detail.match(/(?:render is not ready|renderer failed): ([A-Za-z][A-Za-z0-9_]*)/);
    return {
      state: "render_not_ready",
      owner_id: ownerId,
      occurrence_id: occurrenceId,
      effect: 0,
      render_error_class: match ? match[1] : "renderer_unavailable",
    };
  }
  const { receipt, script, publication_id: basePublicationId, attribution_token: token } = input;
  const publicationId = ownerScopedPublicationId(basePublicationId, ownerId);
  if (!approvedBaselineScript(script, pack)
      || receipt.product_id !== lane.productId || receipt.slot_at !== slotAt
      || receipt.script_id !== script.script_id
      || !/^[0-9a-f]{64}$/.test(String(receipt.render?.sha256 || ""))) {
    throw new Error("eBook render receipt and baseline script do not match");
  }
  const policy = SCRIPT_POLICY[lane.productId];
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(publicationId)
      || !publicationId.startsWith(`${script.creative_id}-`)
      || !policy.tokenPattern.test(token)) {
    throw new Error("eBook publication identity is invalid");
  }
  const campaignUrl = `https://aniccaai.com/go/${token}`;
  const caption = `${script.body}\n\n${campaignUrl}\n\n${policy.captionSuffix}`;

  const objectStore = createContentObjectStore({ objectDir: path.join(dataDir, "objects") });
  const video = objectStore.import(receipt.render.output);
  if (video.sha256 !== receipt.render.sha256) throw new Error("eBook render hash differs from receipt");
  const captionPath = path.join(stateRoot, "captions", `${publicationId}.txt`);
  fs.mkdirSync(path.dirname(captionPath), { recursive: true, mode: 0o700 });
  if (fs.existsSync(captionPath) && fs.readFileSync(captionPath, "utf8") !== caption) {
    throw new Error("eBook baseline caption conflicts with its creative ID");
  }
  if (!fs.existsSync(captionPath)) {
    try { fs.writeFileSync(captionPath, caption, { mode: 0o600, flag: "wx" }); }
    catch (error) { if (error.code !== "EEXIST") throw error; }
  }
  if (fs.readFileSync(captionPath, "utf8") !== caption) {
    throw new Error("eBook baseline caption conflicts with its creative ID");
  }
  const captionObject = objectStore.import(captionPath);
  const approval = {
    schema_version: "marketing.ebook-standing-approval.v1",
    status: "approved",
    approval_mode: "standing_policy_no_additional_gate",
    policy_id: policy.approvalId,
    product_id: lane.productId,
    account_id: account.account_id,
    integration_id: integrationId,
    platform: lane.platform,
    locale: lane.locale,
    renderer_id: pack.renderer_id,
    source_script_id: script.script_id,
    baseline: true,
    allowed_claims: pack.allowed_claims,
    creative_id: publicationId,
    attribution_token: token,
    video_sha256: video.sha256,
    caption_sha256: captionObject.sha256,
  };
  const approvalPath = path.join(stateRoot, "approvals", `${ownerId}-${publicationId}.json`);
  if (fs.existsSync(approvalPath)
      && JSON.stringify(readJson(approvalPath, "eBook standing approval")) !== JSON.stringify(approval)) {
    throw new Error("eBook standing approval conflicts with its exact inputs");
  }
  if (!fs.existsSync(approvalPath)) atomicJson(approvalPath, approval);
  const approvalObject = objectStore.import(approvalPath);
  const integrationRef = `integration://postiz/${lane.platform}/${integrationId}`;
  const job = buildMarketingVideoPublicationJob({
    tenantId,
    productId: lane.productId,
    formatId: lane.formatId,
    form: lane.form,
    locale: lane.locale,
    slot: slotAt,
    creativeId: publicationId,
    platform: lane.platform,
    videoRef: video.ref,
    captionRef: captionObject.ref,
    approvalRef: approvalObject.ref,
    instagramProfileRef: lane.platform === "instagram"
      ? `profile://instagram/${account.native_handle}`
      : "profile://instagram/unassigned",
    postizTokenRef: "secret://postiz/api-key",
    ...(lane.platform === "instagram"
      ? { instagramIntegrationRef: integrationRef }
      : { tiktokIntegrationRef: integrationRef }),
    slotScopedEffect: true,
  });

  const store = deps.store || createMarketingLocalLedger({ dataDir });
  const ledgerPath = path.join(dataDir, "tenants", encodeURIComponent(tenantId), "marketing",
    "video-publication", encodeURIComponent(lane.productId), "distribution.jsonl");
  const publicationAdapter = createMarketingVideoPublicationLoopAdapter({
    objectStore,
    secretProvider: { async get(requestTenantId, ref) {
      if (requestTenantId !== tenantId || ref !== "secret://postiz/api-key") {
        throw new Error("eBook Postiz secret scope mismatch");
      }
      return apiKey;
    } },
    integrationProvider: { async get(requestTenantId, ref) {
      if (requestTenantId !== tenantId || ref !== integrationRef) {
        throw new Error("eBook Postiz integration scope mismatch");
      }
      return integrationId;
    } },
    accountResolver: () => target.postiz_profile,
    ledgerPath: () => ledgerPath,
  });
  let publication = await store.readReceipt({ tenantId: job.tenant_id, jobId: job.job_id });
  if (!publication) {
    publication = await executeJob(store, job, ownerId,
      (claimed) => publicationAdapter.execute(claimed));
  } else if (lane.platform === "instagram"
      && publication.provider_route === "instagram_file_script") {
    const identityPath = String(env.LIFE_MANAGER_EFFECT_IDENTITY_PATH || "").trim();
    const identityWritten = identityPath && writeMarketingEffectIdentity({
      jobId: job.job_id,
      effectKey: job.effect_key,
      productId: lane.productId,
      formatId: lane.formatId,
      form: lane.form,
      locale: lane.locale,
      platform: lane.platform,
      creativeId: publicationId,
      slot: slotAt,
      integrationRef,
      accountId: target.postiz_profile,
      videoSha256: video.sha256,
      captionSha256: captionObject.sha256,
    });
    const proof = identityWritten ? verifyLegacyPostizReceipt({
      root,
      python: env.LM_PYTHON,
      apiKey,
      dataDir,
      tenantId,
      ownerId,
      occurrenceId: env.LIFE_MANAGER_OCCURRENCE_ID,
      identityPath,
      ledgerPath,
      env,
    }) : null;
    publication = normalizePostizInstagramReceiptRoute(publication, {
      ownerId,
      occurrenceId: env.LIFE_MANAGER_OCCURRENCE_ID,
      jobId: job.job_id,
      effectKey: job.effect_key,
      productId: lane.productId,
      platform: lane.platform,
      integrationId,
      accountId: target.postiz_profile,
    }, proof);
  }
  const publicUrl = String(publication?.public_url || "");
  const tiktokPrefix = `https://www.tiktok.com/@${account.native_handle}/video/`;
  const directAccountUrl = lane.platform === "tiktok"
    ? publicUrl.startsWith(tiktokPrefix) && /^[0-9]+\/?$/.test(publicUrl.slice(tiktokPrefix.length))
    : /^https:\/\/www\.instagram\.com\/(?:reel|p)\/[A-Za-z0-9_-]+\/?$/.test(publicUrl);
  if (!verifyMarketingVideoPublicationReceipt(publication)
      || publication.product_id !== lane.productId || publication.platform !== lane.platform
      || publication.provider_route !== "postiz" || publication.provider_reconciled !== true
      || !publication.provider_post_id || !directAccountUrl) {
    throw new Error("eBook Postiz receipt is not officially reconciled");
  }
  writeEffectResult(publication);
  return {
    state: "published",
    owner_id: ownerId,
    occurrence_id: env.LIFE_MANAGER_OCCURRENCE_ID,
    product_id: lane.productId,
    platform: lane.platform,
    account_id: account.account_id,
    integration_id: integrationId,
    slot_at: slotAt,
    creative_id: publicationId,
    attribution_token: token,
    provider_receipt_id: publication.provider_post_id,
    public_url: publication.public_url,
    provider_reconciled: true,
  };
}

if (require.main === module) {
  run().then((result) => process.stdout.write(`${JSON.stringify(result)}\n`))
    .catch((error) => {
      process.stderr.write(`${error && error.message ? error.message : "eBook publication failed"}\n`);
      process.exitCode = 1;
    });
}

module.exports = {
  APPROVED_CLAIMS,
  JOBS,
  approvedBaselineScript,
  normalizePostizInstagramReceiptRoute,
  ownerScopedPublicationId,
  verifyLegacyPostizReceipt,
  run,
  selectTarget,
};
