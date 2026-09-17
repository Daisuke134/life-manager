#!/usr/bin/env node
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const { buildRuntimeJob } = require("./runtime-job-store.js");
const { createContentObjectStore } = require("./content-object-store.js");
const { resolveRuntimePaths } = require("./runtime-paths.js");
const { assertMarketingProductFormat } = require("./marketing-format-policy.js");
const { writeMarketingEffectIdentity } = require("./marketing-effect-identity.js");
const {
  findMarketingDestinationTarget,
  loadMarketingDestinationContract,
} = require("./marketing-destination-contract.js");

const ADAPTER_ID = "marketing-video-publication";
const LOOP_ID = "marketing.video.publish";
const CAPABILITY = "marketing.video.publish";
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const LOCALE = /^[a-z]{2}(?:-[A-Z]{2})?$/;
const HASH = /^[0-9a-f]{64}$/;
const OBJECT_REF = /^object:\/\/sha256\/([0-9a-f]{64})$/;
const PRODUCT_REF = /^product:\/\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})$/;
const FORMAT_REF = /^format:\/\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})$/;
const FORM_REF = /^form:\/\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})$/;
const LOCALE_REF = /^locale:\/\/([a-z]{2}(?:-[A-Z]{2})?)$/;
const SLOT_REF = /^schedule-slot:\/\/(.+)$/;
const CREATIVE_REF = /^creative:\/\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})$/;
const PLATFORM_REF = /^platform:\/\/(instagram|tiktok|youtube)$/;
const PROFILE_REF = /^profile:\/\/instagram\/[a-z0-9._-]+$/i;
const SECRET_REF = /^secret:\/\/[a-z0-9][a-z0-9._-]*(?:\/[a-z0-9][a-z0-9._-]*)*$/i;
const INSTAGRAM_INTEGRATION_REF = /^integration:\/\/postiz\/instagram\/[a-z0-9._-]+$/i;
const TIKTOK_INTEGRATION_REF = /^integration:\/\/postiz\/tiktok\/[a-z0-9._-]+$/i;
const YOUTUBE_INTEGRATION_REF = /^integration:\/\/postiz\/youtube\/[a-z0-9._-]+$/i;
const EFFECT_KEY = /^marketing:video:([A-Za-z0-9][A-Za-z0-9._-]{0,127}):(instagram|tiktok|youtube):([A-Za-z0-9][A-Za-z0-9._-]{0,127}):([0-9a-f]{64}):([0-9a-f]{64})(?::([0-9a-f]{64}))?$/;
const INSTAGRAM_URL = /^https:\/\/www\.instagram\.com\/(?:reel|p)\/[A-Za-z0-9_-]+\/?$/;
const TIKTOK_URL = /^https:\/\/www\.tiktok\.com\/@[^/]+\/video\/[0-9]+\/?$/;
const YOUTUBE_URL = /^https:\/\/www\.youtube\.com\/(?:shorts\/[A-Za-z0-9_-]+|watch\?v=[A-Za-z0-9_-]+(?:&[^#]+)?)\/?$/;
const PROVIDER_POST_ID = /^[A-Za-z0-9._:-]{1,200}$/;
const PROVIDER_ROUTES = new Set([
  "instagram_file_script",
  "postiz",
  "direct_browser",
]);
const COMMON_REF_KEYS = [
  "approval_ref",
  "caption_ref",
  "creative_ref",
  "form_ref",
  "format_ref",
  "instagram_profile_ref",
  "locale_ref",
  "platform_ref",
  "postiz_token_ref",
  "product_ref",
  "slot_ref",
  "video_ref",
];
const LEGACY_REF_KEYS = [...COMMON_REF_KEYS, "tiktok_integration_ref"].sort();
const INSTAGRAM_REF_KEYS = [...COMMON_REF_KEYS, "instagram_integration_ref"].sort();
const YOUTUBE_REF_KEYS = [...COMMON_REF_KEYS, "youtube_integration_ref"].sort();

function required(value, label) {
  const text = String(value == null ? "" : value).trim();
  if (!text) throw new Error(`${label} is required`);
  return text;
}

function matchRef(value, pattern, label) {
  const text = required(value, label);
  const match = pattern.exec(text);
  if (!match) throw new Error(`${label} reference is invalid`);
  return { text, match };
}

function identifier(value, label) {
  const text = String(value == null ? "" : value).trim();
  if (!IDENTIFIER.test(text)) throw new Error(`${label} is invalid`);
  return text;
}

function locale(value) {
  const text = String(value || "");
  if (!LOCALE.test(text)) throw new Error("marketing video publication locale is invalid");
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

function objectRef(value, label) {
  const text = String(value || "");
  if (!OBJECT_REF.test(text)) throw new Error(`${label} reference is invalid`);
  return text;
}

function effectContract(effectKey) {
  const match = EFFECT_KEY.exec(required(effectKey, "marketing video publication effect key"));
  if (!match) throw new Error("marketing video publication effect key is invalid");
  return {
    productId: match[1],
    platform: match[2],
    creativeId: match[3],
    videoSha256: match[4],
    captionSha256: match[5],
  };
}

function buildMarketingVideoPublicationJob(input = {}) {
  const tenantId = identifier(input.tenantId, "marketing video publication tenant");
  const productId = identifier(input.productId, "marketing video publication product");
  const formatId = identifier(input.formatId, "marketing video publication format");
  assertMarketingProductFormat(productId, formatId);
  const form = identifier(input.form, "marketing video publication form");
  const localeId = locale(input.locale);
  const slot = exactInstant(input.slot, "marketing video publication slot");
  const creativeId = identifier(input.creativeId, "marketing video publication creative");
  const platform = matchRef(
    `platform://${required(input.platform, "marketing video publication platform")}`,
    PLATFORM_REF,
    "marketing video publication platform",
  ).match[1];
  if (platform === "youtube" && !["anicca", "anicca-ios"].includes(productId)) {
    throw new Error("Honne YouTube publication is forbidden");
  }
  const videoRef = objectRef(input.videoRef, "marketing video publication video");
  const captionRef = objectRef(input.captionRef, "marketing video publication caption");
  const approvalRef = objectRef(input.approvalRef, "marketing video publication approval");
  const instagramProfileRef = matchRef(
    platform === "youtube" ? (input.instagramProfileRef || "profile://instagram/unassigned") : input.instagramProfileRef,
    PROFILE_REF,
    "Instagram profile",
  ).text;
  const postizTokenRef = matchRef(input.postizTokenRef, SECRET_REF, "Postiz token").text;
  const modernInstagramIntegration = input.instagramIntegrationRef || input.postizInstagramIntegrationRef;
  const integrationRef = matchRef(
    platform === "youtube"
      ? input.youtubeIntegrationRef || input.postizIntegrationRef || input.tiktokIntegrationRef
      : platform === "instagram"
        ? modernInstagramIntegration || input.postizIntegrationRef || input.tiktokIntegrationRef
        : input.postizIntegrationRef || input.tiktokIntegrationRef,
    platform === "youtube"
      ? YOUTUBE_INTEGRATION_REF
      : platform === "instagram" && modernInstagramIntegration
        ? INSTAGRAM_INTEGRATION_REF
        : TIKTOK_INTEGRATION_REF,
    platform === "youtube"
      ? "YouTube integration"
      : platform === "instagram" && modernInstagramIntegration
        ? "Instagram integration"
        : "TikTok integration",
  ).text;

  const videoHash = OBJECT_REF.exec(videoRef)[1];
  const captionHash = OBJECT_REF.exec(captionRef)[1];

  const inputRefs = {
    product_ref: `product://${productId}`,
    format_ref: `format://${formatId}`,
    form_ref: `form://${form}`,
    locale_ref: `locale://${localeId}`,
    slot_ref: `schedule-slot://${slot}`,
    creative_ref: `creative://${productId}/${creativeId}`,
    platform_ref: `platform://${platform}`,
    video_ref: videoRef,
    caption_ref: captionRef,
    approval_ref: approvalRef,
    instagram_profile_ref: instagramProfileRef,
    postiz_token_ref: postizTokenRef,
    ...(platform === "youtube"
      ? { youtube_integration_ref: integrationRef }
      : platform === "instagram" && modernInstagramIntegration
        ? { instagram_integration_ref: integrationRef }
        : { tiktok_integration_ref: integrationRef }),
  };

  // job_id and effect_key must agree: the database enforces UNIQUE (tenant_id, effect_key)
  // while enqueue only dedupes on job_id, so the same effect identity (same bytes + caption
  // + platform = one effect forever) must always derive the same job_id. Slot is lineage
  // carried in input_refs, never identity.
  const slotScope = input.slotScopedEffect === true ? `:${crypto.createHash("sha256").update(slot).digest("hex")}` : "";
  const effectKey = `marketing:video:${productId}:${platform}:${creativeId}:${videoHash}:${captionHash}${slotScope}`;
  const digest = crypto.createHash("sha256")
    .update(JSON.stringify({ tenant_id: tenantId, effect_key: effectKey }))
    .digest("hex");

  return buildRuntimeJob({
    jobId: `marketing-video-publication:${digest}`,
    tenantId,
    loopId: LOOP_ID,
    capability: CAPABILITY,
    effectClass: "publish",
    effectKey,
    inputRefs,
    maxAttempts: 3,
  });
}

function normalizeJob(job) {
  const refs = job && job.input_refs;
  if (!refs || typeof refs !== "object" || Array.isArray(refs)) {
    throw new Error("marketing video publication job contract is invalid");
  }
  const product = PRODUCT_REF.exec(String(refs.product_ref || ""));
  const format = FORMAT_REF.exec(String(refs.format_ref || ""));
  const form = FORM_REF.exec(String(refs.form_ref || ""));
  const localeMatch = LOCALE_REF.exec(String(refs.locale_ref || ""));
  const slotMatch = SLOT_REF.exec(String(refs.slot_ref || ""));
  const creative = CREATIVE_REF.exec(String(refs.creative_ref || ""));
  const platformMatch = PLATFORM_REF.exec(String(refs.platform_ref || ""));
  if (
    !product
    || !format
    || !form
    || !localeMatch
    || !slotMatch
    || !creative
    || !platformMatch
    || creative[1] !== product[1]
  ) {
    throw new Error("marketing video publication job contract is invalid");
  }
  const platform = platformMatch[1];
  const refKeys = JSON.stringify(Object.keys(refs).sort());
  const expectedRefKeys = platform === "youtube"
    ? [YOUTUBE_REF_KEYS]
    : platform === "instagram"
      ? [INSTAGRAM_REF_KEYS, LEGACY_REF_KEYS]
      : [LEGACY_REF_KEYS];
  if (!expectedRefKeys.some((keys) => refKeys === JSON.stringify(keys))) {
    throw new Error("marketing video publication job contract is invalid");
  }
  const input = {
    tenantId: String(job.tenant_id || ""),
    productId: product[1],
    formatId: format[1],
    form: form[1],
    locale: localeMatch[1],
    slot: slotMatch[1],
    creativeId: creative[2],
    platform: platformMatch[1],
    videoRef: refs.video_ref,
    captionRef: refs.caption_ref,
    approvalRef: refs.approval_ref,
    instagramProfileRef: refs.instagram_profile_ref,
    postizTokenRef: refs.postiz_token_ref,
    postizIntegrationRef: platform === "youtube"
      ? refs.youtube_integration_ref
      : platform === "instagram" && refs.instagram_integration_ref
        ? refs.instagram_integration_ref
        : refs.tiktok_integration_ref,
    ...(platform === "youtube"
      ? { youtubeIntegrationRef: refs.youtube_integration_ref }
      : platform === "instagram" && refs.instagram_integration_ref
        ? { instagramIntegrationRef: refs.instagram_integration_ref }
        : { tiktokIntegrationRef: refs.tiktok_integration_ref }),
    ...(EFFECT_KEY.exec(String(job.effect_key || ""))?.[6] ? { slotScopedEffect: true } : {}),
  };
  let expected;
  try {
    expected = buildMarketingVideoPublicationJob(input);
  } catch {
    throw new Error("marketing video publication job contract is invalid");
  }
  if (
    job.loop_id !== LOOP_ID
    || job.capability !== CAPABILITY
    || job.effect_class !== "publish"
    || job.job_id !== expected.job_id
    || job.effect_key !== expected.effect_key
  ) {
    throw new Error("marketing video publication job contract is invalid");
  }
  return input;
}

function validIso(value) {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

function validPublicUrl(platform, value) {
  const pattern = platform === "instagram"
    ? INSTAGRAM_URL
    : platform === "tiktok"
      ? TIKTOK_URL
      : YOUTUBE_URL;
  return pattern.test(String(value || ""));
}

function verifyMarketingVideoPublicationReceipt(receipt) {
  if (
    !receipt
    || typeof receipt !== "object"
    || Array.isArray(receipt)
    || receipt.schema_version !== 1
    || receipt.kind !== "marketing_video_distribution"
    || receipt.status !== "published"
    || !IDENTIFIER.test(String(receipt.product_id || ""))
    || !IDENTIFIER.test(String(receipt.format_id || ""))
    || !IDENTIFIER.test(String(receipt.form || ""))
    || !LOCALE.test(String(receipt.locale || ""))
    || !IDENTIFIER.test(String(receipt.creative_id || ""))
    || !PLATFORM_REF.test(`platform://${receipt.platform}`)
    || !HASH.test(String(receipt.video_sha256 || ""))
    || !HASH.test(String(receipt.caption_sha256 || ""))
  ) {
    return false;
  }
  try {
    exactInstant(receipt.slot, "marketing video publication receipt slot");
  } catch {
    return false;
  }
  if (!validPublicUrl(receipt.platform, receipt.public_url)) return false;
  if (
    receipt.provider_reconciled !== undefined
    && typeof receipt.provider_reconciled !== "boolean"
  ) {
    return false;
  }
  const hasProviderJoin = receipt.provider_post_id !== undefined
    || receipt.provider_route !== undefined;
  if (hasProviderJoin) {
    if (
      !PROVIDER_POST_ID.test(String(receipt.provider_post_id || ""))
      || !PROVIDER_ROUTES.has(receipt.provider_route)
    ) {
      return false;
    }
  }
  return validIso(receipt.published_at);
}

function safeMarketingVideoPublicationSummary(receipt) {
  if (!verifyMarketingVideoPublicationReceipt(receipt)) {
    throw new Error("marketing video publication receipt verification failed");
  }
  return {
    status: receipt.status,
    product_id: receipt.product_id,
    format_id: receipt.format_id,
    creative_id: receipt.creative_id,
    platform: receipt.platform,
    public_url: receipt.public_url,
    provider_post_id: receipt.provider_post_id || null,
    provider_route: receipt.provider_route || null,
    provider_reconciled: receipt.provider_reconciled === true,
    video_sha256: receipt.video_sha256,
    caption_sha256: receipt.caption_sha256,
  };
}

function tenantSegment(tenantId) {
  return encodeURIComponent(required(tenantId, "marketing video publication tenant"));
}

function defaultLedgerPath(tenantId, productId, paths) {
  return path.join(
    paths.dataDir,
    "tenants",
    tenantSegment(tenantId),
    "marketing",
    "video-publication",
    encodeURIComponent(required(productId, "marketing video publication product")),
    "distribution.jsonl",
  );
}

// Base allowlist for the distribution subprocess plus the exact LM_* variables
// distribute.py reads (LM_DATA_DIR, LM_DISTRIBUTION_LEDGER,
// LM_DISTRIBUTION_APPROVALS, LM_INSTAGRAM_HANDLE, LM_INSTAGRAM_ACCOUNTS,
// LM_INSTAGRAM_POSTER, LM_TIKTOK_INTEGRATION, LM_TIKTOK_DIRECT_MIGRATION,
// LM_POSTIZ_RESOLVE_IP),
// and the non-LM_ variables the real chain reads:
// INSTAGRAPI_PYTHON (instagram_video.sh interpreter override) and CDP_HOST/CDP_PORT
// (skills/earn/marketing-engine/poster.py:44,50,509). Never the full parent environment.
const SUBPROCESS_ENV_KEYS = [
  "PATH",
  "HOME",
  "LANG",
  "LC_ALL",
  "TMPDIR",
  "INSTAGRAPI_PYTHON",
  "CDP_HOST",
  "CDP_PORT",
  "LM_DATA_DIR",
  "LM_TIKTOK_DIRECT_MIGRATION",
  "LM_DISTRIBUTION_LEDGER",
  "LM_DISTRIBUTION_APPROVALS",
  "LM_INSTAGRAM_HANDLE",
  "LM_INSTAGRAM_ACCOUNTS",
  "LM_INSTAGRAM_POSTER",
  "LM_TIKTOK_INTEGRATION",
  "LM_YOUTUBE_INTEGRATION",
  "LM_POSTIZ_RESOLVE_IP",
];

function subprocessEnv(postizToken) {
  const env = {};
  for (const key of SUBPROCESS_ENV_KEYS) {
    if (process.env[key] !== undefined) env[key] = process.env[key];
  }
  env.POSTIZ_API_KEY = postizToken;
  return env;
}

function runDistributionProcess(input) {
  const repoRoot = path.resolve(__dirname, "../../..");
  const script = path.join(repoRoot, "skills/video/lm-distribution/distribute.py");
  const result = spawnSync(input.python || "python3", [
    script,
    "--creative-id", input.creativeId,
    "--platform", input.platform,
    "--format-id", input.formatId,
    "--form", input.form,
    "--locale", input.locale,
    "--slot", input.slot,
    "--video", input.videoPath,
    "--caption-file", input.captionPath,
    "--ledger", input.ledgerPath,
    "--approvals", input.approvalPath,
    "--instagram-handle", input.instagramHandle,
    "--instagram-accounts", input.instagramAccountsPath,
    "--instagram-settings", input.instagramSettingsPath,
    "--instagram-credentials", input.instagramCredentialsPath,
    "--instagram-profile-state", input.instagramProfileStatePath,
    "--instagram-integration", input.instagramIntegration,
    "--tiktok-integration", input.tiktokIntegration,
    "--youtube-integration", input.youtubeIntegration,
  ], {
    cwd: repoRoot,
    env: subprocessEnv(input.postizToken),
    encoding: "utf8",
    timeout: 20 * 60 * 1000,
    maxBuffer: 4 * 1024 * 1024,
  });
  if (result.status !== 0) {
    const lines = String(result.stdout || "").split(/\r?\n/).filter(Boolean);
    let detail = "";
    if (lines.length) {
      try {
        const payload = JSON.parse(lines[lines.length - 1]);
        if (payload && typeof payload.error === "string" && payload.error.trim()) {
          detail = `: ${payload.error.trim()}`;
        }
      } catch {}
    }
    const error = new Error(`marketing video publication distribution failed with exit ${result.status}${detail}`);
    error.unknownEffect = true;
    throw error;
  }
  const lines = String(result.stdout || "").split(/\r?\n/).filter(Boolean);
  if (lines.length !== 1) {
    const error = new Error("marketing video publication distribution returned invalid JSON");
    error.unknownEffect = true;
    throw error;
  }
  try {
    return JSON.parse(lines[0]);
  } catch {
    const error = new Error("marketing video publication distribution returned invalid JSON");
    error.unknownEffect = true;
    throw error;
  }
}

function defaultServices(deps) {
  let paths;
  const runtimePaths = () => {
    if (!paths) paths = resolveRuntimePaths(process.env);
    return paths;
  };
  return {
    objectStore: deps.objectStore || {
      resolve(ref) {
        return createContentObjectStore({
          objectDir: runtimePaths().objectDir,
        }).resolve(ref);
      },
    },
    profileProvider: deps.profileProvider,
    secretProvider: deps.secretProvider,
    integrationProvider: deps.integrationProvider,
    accountResolver: deps.accountResolver || defaultAccountResolver,
    ledgerPath: deps.ledgerPath
      || ((tenantId, productId) => defaultLedgerPath(tenantId, productId, runtimePaths())),
    runDistribution: deps.runDistribution || runDistributionProcess,
    now: deps.now || (() => new Date().toISOString()),
  };
}

function defaultAccountResolver(contract) {
  const match = /^integration:\/\/postiz\/[^/]+\/([A-Za-z0-9._:-]+)$/i.exec(
    String(contract?.postizIntegrationRef || ""),
  );
  if (!match) return null;
  try {
    const target = findMarketingDestinationTarget(loadMarketingDestinationContract(), {
      jobProductId: contract.productId,
      locale: contract.locale,
      platform: contract.platform,
      integrationId: match[1],
      jobFormatId: contract.formatId,
      mediaForm: contract.form,
    });
    return target?.postiz_profile || null;
  } catch {
    return null;
  }
}

async function executeMarketingVideoPublicationJob(job, deps = {}) {
  const contract = normalizeJob(job);
  const services = defaultServices(deps);
  const requiredProviders = [
    ["secret", services.secretProvider],
    ["integration", services.integrationProvider],
  ];
  if (contract.platform === "instagram" && services.profileProvider) {
    requiredProviders.unshift(["profile", services.profileProvider]);
  }
  for (const [name, provider] of requiredProviders) {
    if (!provider || typeof provider.get !== "function") {
      throw new Error(`marketing video publication ${name} provider is required`);
    }
  }
  const videoHash = OBJECT_REF.exec(contract.videoRef)[1];
  const captionHash = OBJECT_REF.exec(contract.captionRef)[1];
  const videoPath = services.objectStore.resolve(contract.videoRef);
  const captionPath = services.objectStore.resolve(contract.captionRef);
  const approvalPath = services.objectStore.resolve(contract.approvalRef);
  const profile = contract.platform === "instagram" && services.profileProvider
    ? await services.profileProvider.get(job.tenant_id, contract.instagramProfileRef)
    : null;
  if (contract.platform === "instagram" && services.profileProvider && (
    !profile
    || !profile.handle
    || !profile.accountsPath
    || !profile.settingsPath
    || !profile.credentialsPath
    || !profile.stateDir
  )) throw new Error("marketing video publication Instagram profile is incomplete");
  const postizToken = await services.secretProvider.get(
    job.tenant_id,
    contract.postizTokenRef,
  );
  const platformIntegration = await services.integrationProvider.get(
    job.tenant_id,
    contract.postizIntegrationRef,
  );
  const accountId = services.accountResolver(contract) || profile?.handle;
  writeMarketingEffectIdentity({
    jobId: job.job_id,
    effectKey: job.effect_key,
    productId: contract.productId,
    formatId: contract.formatId,
    form: contract.form,
    locale: contract.locale,
    platform: contract.platform,
    creativeId: contract.creativeId,
    slot: contract.slot,
    integrationRef: contract.postizIntegrationRef,
    accountId,
    videoSha256: videoHash,
    captionSha256: captionHash,
  });
  const ledgerPath = services.ledgerPath(job.tenant_id, contract.productId);
  fs.mkdirSync(path.dirname(ledgerPath), { recursive: true, mode: 0o700 });
  let result;
  try {
    result = await services.runDistribution({
      productId: contract.productId,
      formatId: contract.formatId,
      form: contract.form,
      locale: contract.locale,
      slot: contract.slot,
      creativeId: contract.creativeId,
      platform: contract.platform,
      videoPath,
      captionPath,
      approvalPath,
      ledgerPath,
      instagramHandle: profile ? profile.handle : "",
      instagramAccountsPath: profile ? profile.accountsPath : "",
      instagramSettingsPath: profile ? profile.settingsPath : "",
      instagramCredentialsPath: profile ? profile.credentialsPath : "",
      instagramProfileStatePath: profile ? profile.stateDir : "",
      postizToken,
      instagramIntegration: platformIntegration,
      tiktokIntegration: platformIntegration,
      youtubeIntegration: platformIntegration,
    });
  } catch (error) {
    // Wrap instead of mutating the foreign error object.
    const message = error && error.message ? error.message : String(error);
    throw Object.assign(new Error(message, { cause: error }), { unknownEffect: true });
  }
  const validResult = Boolean(
    result
    && typeof result === "object"
    && result.creative_id === contract.creativeId
    && result.video_sha256 === videoHash
    && result.caption_sha256 === captionHash
    && result.platform === contract.platform
    && validPublicUrl(contract.platform, result.public_url),
  );
  if (!validResult) {
    const error = new Error("marketing video publication provider result contract mismatch");
    error.unknownEffect = true;
    throw error;
  }
  if (
    !PROVIDER_POST_ID.test(String(result.provider_post_id || ""))
    || !PROVIDER_ROUTES.has(result.provider_route)
  ) {
    const error = new Error("marketing video publication provider metric join keys are missing");
    error.unknownEffect = true;
    throw error;
  }
  const receipt = {
    schema_version: 1,
    kind: "marketing_video_distribution",
    status: "published",
    product_id: contract.productId,
    format_id: contract.formatId,
    form: contract.form,
    locale: contract.locale,
    slot: contract.slot,
    creative_id: contract.creativeId,
    platform: contract.platform,
    video_sha256: videoHash,
    caption_sha256: captionHash,
    public_url: result.public_url,
    provider_post_id: result.provider_post_id,
    provider_route: result.provider_route,
    provider_reconciled: result.provider_reconciled === true,
    published_at: services.now(),
  };
  if (!verifyMarketingVideoPublicationReceipt(receipt)) {
    throw new Error("marketing video publication receipt verification failed");
  }
  return { receipt, result };
}

function readLedgerRows(ledgerPath) {
  try {
    return fs.readFileSync(ledgerPath, "utf8")
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => JSON.parse(line));
  } catch (error) {
    if (error.code === "ENOENT") return [];
    throw new Error("marketing video publication distribution ledger is invalid");
  }
}

function receiptFromRows(rows, contract, now) {
  const matching = rows.filter((row) => (
    row
    && row.status === "published"
    && row.creative_id === contract.creativeId
    && row.video_sha256 === contract.videoSha256
    && row.caption_sha256 === contract.captionSha256
    && row.platform === contract.platform
  ));
  const published = matching.filter((row) => validPublicUrl(contract.platform, row.public_url)).at(-1);
  if (!published) {
    // effect-reconciler.js requires a receipt object for the absent decision.
    return {
      state: "absent",
      receipt: {
        lookup: "ledger_no_published_row",
        platform: contract.platform,
        creative_id: contract.creativeId,
      },
    };
  }
  const publishedAt = validIso(published.ts) ? published.ts : now();
  const provider = (
    PROVIDER_POST_ID.test(String(published.provider_id || ""))
    && PROVIDER_ROUTES.has(published.route)
  ) ? {
      provider_post_id: published.provider_id,
      provider_route: published.route,
    } : {};
  const receipt = {
    schema_version: 1,
    kind: "marketing_video_distribution",
    status: "published",
    product_id: contract.productId,
    format_id: published.format_id,
    form: published.form,
    locale: published.locale,
    slot: published.slot,
    creative_id: contract.creativeId,
    platform: contract.platform,
    video_sha256: contract.videoSha256,
    caption_sha256: contract.captionSha256,
    public_url: published.public_url,
    ...provider,
    provider_reconciled: published.provider_reconciled === true,
    published_at: publishedAt,
  };
  if (!verifyMarketingVideoPublicationReceipt(receipt)) {
    // A published row matched but cannot be reconstructed into a verifiable receipt
    // (legacy shadow rows without lineage): the effect may be real, so neither
    // "present" (would certify an unverifiable receipt) nor "absent" (would
    // authorize retrying an already-performed publish) is honest.
    return { state: "unknown" };
  }
  return { state: "present", receipt };
}

function createMarketingVideoPublicationLoopAdapter(deps = {}) {
  return Object.freeze({
    async plan(context = {}) {
      const platforms = context.platform == null
        ? ["instagram", "tiktok"]
        : [context.platform];
      return platforms.map((platform) => buildMarketingVideoPublicationJob({
        ...context,
        platform,
      }));
    },
    execute(job, services = {}) {
      return executeMarketingVideoPublicationJob(job, { ...deps, ...services });
    },
    async reconcile(effect) {
      const contract = effectContract(effect && effect.effectKey);
      const services = defaultServices(deps);
      return receiptFromRows(
        readLedgerRows(services.ledgerPath(effect.tenantId, contract.productId)),
        contract,
        services.now,
      );
    },
    verify: verifyMarketingVideoPublicationReceipt,
    report: safeMarketingVideoPublicationSummary,
  });
}

module.exports = {
  ADAPTER_ID,
  CAPABILITY,
  LOOP_ID,
  buildMarketingVideoPublicationJob,
  createMarketingVideoPublicationLoopAdapter,
  executeMarketingVideoPublicationJob,
  runDistributionProcess,
  safeMarketingVideoPublicationSummary,
  verifyMarketingVideoPublicationReceipt,
};
