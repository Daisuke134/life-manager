"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const { buildRuntimeJob } = require("./runtime-job-store.js");
const { assertMarketingProductFormat } = require("./marketing-format-policy.js");

const ADAPTER_ID = "marketing-video-generation";
const LOOP_ID = "marketing.video.generate";
const CAPABILITY = "marketing.video.generate";
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const LOCALE = /^[a-z]{2}(?:-[A-Z]{2})?$/;
const HASH = /^[0-9a-f]{64}$/;
const OBJECT_REF = /^object:\/\/sha256\/([0-9a-f]{64})$/;
const PRODUCT_REF = /^product:\/\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})$/;
const FORMAT_REF = /^format:\/\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})$/;
const LOCALE_REF = /^locale:\/\/([a-z]{2}(?:-[A-Z]{2})?)$/;
const SLOT_REF = /^schedule-slot:\/\/(.+)$/;
const PACK_KEYS = new Set([
  "schema_version",
  "product_id",
  "format_id",
  "form",
  "locale",
  "title",
  "hashtags",
  "hooks",
]);
const HOOK_KEYS = new Set([
  "id",
  "text",
  "status",
  "prior_used_at",
]);
const BOUND_HOOK_KEYS = new Set([...HOOK_KEYS, "media_ref"]);
const RECEIPT_KEYS = new Set([
  "schema_version",
  "kind",
  "status",
  "product_id",
  "format_id",
  "form",
  "locale",
  "slot",
  "creative_id",
  "hook_id",
  "hook_sha256",
  "video_ref",
  "video_sha256",
  "copy_ref",
  "copy_sha256",
  "generated_at",
]);

function identifier(value, label) {
  const text = String(value == null ? "" : value).trim();
  if (!IDENTIFIER.test(text)) throw new Error(`${label} is invalid`);
  return text;
}

function locale(value) {
  const text = String(value || "");
  if (!LOCALE.test(text)) throw new Error("marketing video locale is invalid");
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

function buildMarketingVideoGenerationJob(input = {}) {
  const tenantId = identifier(input.tenantId, "marketing video tenant");
  const productId = identifier(input.productId, "marketing video product");
  const formatId = identifier(input.formatId, "marketing video format");
  assertMarketingProductFormat(productId, formatId);
  const localeId = locale(input.locale);
  const slot = exactInstant(input.slot, "marketing video slot");
  const mediaRefs = Array.isArray(input.mediaRefs)
    ? input.mediaRefs.map((value) => objectRef(value, "marketing video media"))
    : [];
  if (
    mediaRefs.length < 1
    || mediaRefs.length > 20
    || new Set(mediaRefs).size !== mediaRefs.length
  ) {
    throw new Error("marketing video media references are invalid");
  }
  const inputRefs = {
    product_ref: `product://${productId}`,
    format_ref: `format://${formatId}`,
    locale_ref: `locale://${localeId}`,
    slot_ref: `schedule-slot://${slot}`,
    pack_ref: objectRef(input.packRef, "marketing video pack"),
    media_refs: mediaRefs,
  };
  const digest = crypto.createHash("sha256")
    .update(JSON.stringify({ tenant_id: tenantId, input_refs: inputRefs }))
    .digest("hex");
  return buildRuntimeJob({
    jobId: `marketing-video-generation:${digest}`,
    tenantId,
    loopId: LOOP_ID,
    capability: CAPABILITY,
    effectClass: "none",
    effectKey: null,
    inputRefs,
    maxAttempts: 2,
  });
}

function normalizeJob(job) {
  const refs = job && job.input_refs;
  if (
    !refs
    || typeof refs !== "object"
    || Array.isArray(refs)
    || JSON.stringify(Object.keys(refs).sort()) !== JSON.stringify([
      "format_ref",
      "locale_ref",
      "media_refs",
      "pack_ref",
      "product_ref",
      "slot_ref",
    ])
  ) {
    throw new Error("marketing video generation job contract is invalid");
  }
  const product = PRODUCT_REF.exec(String(refs.product_ref || ""));
  const format = FORMAT_REF.exec(String(refs.format_ref || ""));
  const localeMatch = LOCALE_REF.exec(String(refs.locale_ref || ""));
  const slotMatch = SLOT_REF.exec(String(refs.slot_ref || ""));
  if (!product || !format || !localeMatch || !slotMatch) {
    throw new Error("marketing video generation job contract is invalid");
  }
  const input = {
    tenantId: String(job.tenant_id || ""),
    productId: product[1],
    formatId: format[1],
    locale: localeMatch[1],
    slot: slotMatch[1],
    packRef: refs.pack_ref,
    mediaRefs: refs.media_refs,
  };
  const expected = buildMarketingVideoGenerationJob(input);
  if (
    job.loop_id !== LOOP_ID
    || job.capability !== CAPABILITY
    || job.effect_class !== "none"
    || job.effect_key !== null
    || job.job_id !== expected.job_id
  ) {
    throw new Error("marketing video generation job contract is invalid");
  }
  return input;
}

function exactKeys(value, keys) {
  return Boolean(
    value
    && typeof value === "object"
    && !Array.isArray(value)
    && Object.keys(value).length === keys.size
    && Object.keys(value).every((key) => keys.has(key))
  );
}

function boundedText(value, label, max) {
  const text = String(value == null ? "" : value).trim();
  if (!text || text.length > max || /[\u0000-\u0008\u000B\u000C\u000E-\u001F]/.test(text)) {
    throw new Error(`${label} is invalid`);
  }
  return text;
}

function normalizeMarketingVideoPack(value, expected) {
  if (!exactKeys(value, PACK_KEYS) || value.schema_version !== 1) {
    throw new Error("marketing video pack is invalid");
  }
  const productId = identifier(value.product_id, "marketing video pack product");
  const formatId = identifier(value.format_id, "marketing video pack format");
  assertMarketingProductFormat(productId, formatId);
  const localeId = locale(value.locale);
  if (
    productId !== expected.productId
    || formatId !== expected.formatId
    || localeId !== expected.locale
  ) {
    throw new Error("marketing video pack identity mismatch");
  }
  const form = identifier(value.form, "marketing video pack form");
  const title = boundedText(value.title, "marketing video pack title", 160);
  if (
    !Array.isArray(value.hashtags)
    || value.hashtags.length > 20
    || value.hashtags.some((item) => (
      typeof item !== "string"
      || !/^[\p{L}\p{N}_-]{1,60}$/u.test(item)
    ))
  ) {
    throw new Error("marketing video pack hashtags are invalid");
  }
  if (
    !Array.isArray(value.hooks)
    || value.hooks.length < 1
    || value.hooks.length > 500
  ) {
    throw new Error("marketing video pack hooks are invalid");
  }
  const hooks = value.hooks.map((hook) => {
    if (!exactKeys(hook, hook.media_ref === undefined ? HOOK_KEYS : BOUND_HOOK_KEYS)) {
      throw new Error("marketing video pack hook is invalid");
    }
    const prior = hook.prior_used_at == null
      ? null
      : exactInstant(hook.prior_used_at, "marketing video hook prior use");
    if (!["active", "preferred", "killed"].includes(hook.status)) {
      throw new Error("marketing video pack hook status is invalid");
    }
    return {
      id: identifier(hook.id, "marketing video hook id"),
      text: boundedText(hook.text, "marketing video hook text", 500),
      status: hook.status,
      prior_used_at: prior,
      ...(hook.media_ref === undefined ? {} : { media_ref: objectRef(hook.media_ref, "marketing video hook media") }),
    };
  });
  if (new Set(hooks.map(({ id }) => id)).size !== hooks.length) {
    throw new Error("marketing video pack hooks are invalid");
  }
  if (!hooks.some(({ status }) => status !== "killed")) {
    throw new Error("marketing video pack has no active hook");
  }
  return {
    product_id: productId,
    format_id: formatId,
    form,
    locale: localeId,
    title,
    hashtags: [...value.hashtags],
    hooks,
  };
}

function verifyMarketingVideoGenerationReceipt(receipt) {
  if (
    !exactKeys(receipt, RECEIPT_KEYS)
    || receipt.schema_version !== 1
    || receipt.kind !== "marketing_video_artifact"
    || receipt.status !== "ready"
    || !IDENTIFIER.test(String(receipt.product_id || ""))
    || !IDENTIFIER.test(String(receipt.format_id || ""))
    || !IDENTIFIER.test(String(receipt.form || ""))
    || !LOCALE.test(String(receipt.locale || ""))
    || !IDENTIFIER.test(String(receipt.creative_id || ""))
    || !IDENTIFIER.test(String(receipt.hook_id || ""))
    || !HASH.test(String(receipt.hook_sha256 || ""))
  ) {
    return false;
  }
  const video = OBJECT_REF.exec(String(receipt.video_ref || ""));
  const copy = OBJECT_REF.exec(String(receipt.copy_ref || ""));
  if (
    !video
    || !copy
    || video[1] !== receipt.video_sha256
    || copy[1] !== receipt.copy_sha256
  ) {
    return false;
  }
  try {
    exactInstant(receipt.slot, "marketing video receipt slot");
    exactInstant(receipt.generated_at, "marketing video receipt generated_at");
  } catch {
    return false;
  }
  return true;
}

function scoreByHookFromMetrics(metrics) {
  if (!Array.isArray(metrics)) {
    throw new Error("marketing video generation metrics are invalid");
  }
  const scoreByHook = new Map();
  for (const row of metrics) {
    if (
      !row
      || typeof row !== "object"
      || !IDENTIFIER.test(String(row.hook_id || ""))
      || typeof row.score !== "number"
      || !Number.isFinite(row.score)
      || row.score < 0
    ) {
      throw new Error("marketing video generation metrics are invalid");
    }
    scoreByHook.set(row.hook_id, row.score);
  }
  return scoreByHook;
}

// Selects the next hook for this pack: candidates never used (or never scored) are always
// explored first (oldest/never-used wins ties by id, unchanged from the original rotation).
// Among already-used hooks with a recorded metric score, a hook scoring below the median of
// all scored hooks is deprioritized one tier below every non-deprioritized candidate instead
// of being excluded outright — this is the "drop the formats that didn't perform" exploit half
// of the explore/exploit policy, while a single bad sample can never permanently kill a hook
// (only an explicit status: "killed" in the pack does that).
function selectHook(pack, history, metrics = []) {
  if (!Array.isArray(history)) {
    throw new Error("marketing video generation history is invalid");
  }
  const used = new Map();
  for (const receipt of history) {
    if (!verifyMarketingVideoGenerationReceipt(receipt)) {
      throw new Error("marketing video generation history is invalid");
    }
    if (
      receipt.product_id !== pack.product_id
      || receipt.format_id !== pack.format_id
      || receipt.locale !== pack.locale
    ) {
      throw new Error("marketing video generation history scope mismatch");
    }
    const current = used.get(receipt.hook_id);
    if (!current || current < receipt.generated_at) {
      used.set(receipt.hook_id, receipt.generated_at);
    }
  }
  const scoreByHook = scoreByHookFromMetrics(metrics);
  const scores = [...scoreByHook.values()].sort((left, right) => left - right);
  const median = scores.length
    ? (scores.length % 2 === 1
      ? scores[(scores.length - 1) / 2]
      : (scores[scores.length / 2 - 1] + scores[scores.length / 2]) / 2)
    : null;
  const candidates = pack.hooks
    .filter(({ status }) => status !== "killed")
    .map((hook) => {
      const lastUsed = [hook.prior_used_at, used.get(hook.id)]
        .filter(Boolean)
        .sort()
        .at(-1) || null;
      const score = scoreByHook.has(hook.id) ? scoreByHook.get(hook.id) : null;
      const underperforming = median != null && score != null && score < median;
      return { hook, lastUsed, underperforming };
    })
    .sort((left, right) => {
      if (left.underperforming !== right.underperforming) {
        return left.underperforming ? 1 : -1;
      }
      if (left.lastUsed === right.lastUsed) {
        return left.hook.id.localeCompare(right.hook.id);
      }
      if (left.lastUsed == null) return -1;
      if (right.lastUsed == null) return 1;
      return left.lastUsed.localeCompare(right.lastUsed);
    });
  if (!candidates.length) throw new Error("marketing video pack has no active hook");
  return candidates[0].hook;
}

function safeMarketingVideoGenerationSummary(receipt) {
  if (!verifyMarketingVideoGenerationReceipt(receipt)) {
    throw new Error("marketing video generation receipt verification failed");
  }
  return {
    status: receipt.status,
    product_id: receipt.product_id,
    format_id: receipt.format_id,
    locale: receipt.locale,
    slot: receipt.slot,
    creative_id: receipt.creative_id,
    hook_id: receipt.hook_id,
    video_ref: receipt.video_ref,
    copy_ref: receipt.copy_ref,
  };
}

function createMarketingVideoGenerationLoopAdapter(deps = {}) {
  function services() {
    const rawDataDir = String(deps.dataDir || process.env.LM_DATA_DIR || "").trim();
    const dataDir = path.resolve(rawDataDir);
    if (!rawDataDir || dataDir === path.parse(dataDir).root) {
      throw new Error("marketing video generation data directory is invalid");
    }
    const objectStore = deps.objectStore || {
      resolve(ref) {
        const { resolveContentObject } = require("./content-object-store.js");
        return resolveContentObject(ref, { objectDir: path.join(dataDir, "objects") });
      },
      import(source) {
        const { importContentObject } = require("./content-object-store.js");
        return importContentObject(source, { objectDir: path.join(dataDir, "objects") });
      },
    };
    const historyProvider = deps.historyProvider;
    if (!historyProvider || typeof historyProvider.list !== "function") {
      throw new Error("marketing video generation history provider is required");
    }
    const metricsProvider = deps.metricsProvider || { list: async () => [] };
    if (typeof metricsProvider.list !== "function") {
      throw new Error("marketing video generation metrics provider is invalid");
    }
    return { dataDir, objectStore, historyProvider, metricsProvider };
  }
  const now = deps.now || (() => new Date().toISOString());
  return Object.freeze({
    async plan(input) {
      return [buildMarketingVideoGenerationJob(input)];
    },
    async execute(job) {
      const {
        dataDir,
        objectStore,
        historyProvider,
        metricsProvider,
      } = services();
      const contract = normalizeJob(job);
      const pack = normalizeMarketingVideoPack(
        JSON.parse(fs.readFileSync(objectStore.resolve(contract.packRef), "utf8")),
        contract,
      );
      for (const ref of contract.mediaRefs) objectStore.resolve(ref);
      const scope = {
        tenantId: contract.tenantId,
        productId: contract.productId,
        formatId: contract.formatId,
        locale: contract.locale,
      };
      const [history, metrics] = await Promise.all([
        historyProvider.list(scope),
        metricsProvider.list(scope),
      ]);
      const hook = selectHook(pack, history, metrics);
      if (hook.media_ref && !contract.mediaRefs.includes(hook.media_ref)) {
        throw new Error("marketing video hook media is not approved");
      }
      const mediaIndex = Number.parseInt(
        crypto.createHash("sha256")
          .update(`${contract.slot}:${contract.packRef}`)
          .digest("hex")
          .slice(0, 12),
        16,
      ) % contract.mediaRefs.length;
      const videoRef = hook.media_ref || contract.mediaRefs[mediaIndex];
      const videoSha256 = OBJECT_REF.exec(videoRef)[1];
      const workspace = path.join(
        dataDir,
        "tenants",
        encodeURIComponent(contract.tenantId),
        "marketing",
        "video-generation",
      );
      fs.mkdirSync(workspace, { recursive: true, mode: 0o700 });
      const copyPath = path.join(
        workspace,
        `${job.job_id.replace(/[^A-Za-z0-9._-]/g, "_")}.copy.txt`,
      );
      const hashtags = pack.hashtags.map((value) => `#${value}`).join(" ");
      const publishCopy = hashtags
        ? `${hook.text}\n\n${hashtags}\n`
        : `${hook.text}\n`;
      fs.writeFileSync(copyPath, publishCopy, { mode: 0o600 });
      fs.chmodSync(copyPath, 0o600);
      const copy = objectStore.import(copyPath);
      const hookSha256 = crypto.createHash("sha256").update(hook.text).digest("hex");
      const receipt = {
        schema_version: 1,
        kind: "marketing_video_artifact",
        status: "ready",
        product_id: contract.productId,
        format_id: contract.formatId,
        form: pack.form,
        locale: contract.locale,
        slot: contract.slot,
        creative_id: `${hook.id}-${videoSha256.slice(0, 12)}`,
        hook_id: hook.id,
        hook_sha256: hookSha256,
        video_ref: videoRef,
        video_sha256: videoSha256,
        copy_ref: copy.ref,
        copy_sha256: copy.sha256,
        generated_at: exactInstant(now(), "marketing video generation time"),
      };
      if (!verifyMarketingVideoGenerationReceipt(receipt)) {
        throw new Error("marketing video generation receipt verification failed");
      }
      return { receipt };
    },
    async reconcile() {
      return { state: "absent" };
    },
    verify: verifyMarketingVideoGenerationReceipt,
    report: safeMarketingVideoGenerationSummary,
  });
}

module.exports = {
  ADAPTER_ID,
  CAPABILITY,
  LOOP_ID,
  buildMarketingVideoGenerationJob,
  createMarketingVideoGenerationLoopAdapter,
  normalizeMarketingVideoPack,
  safeMarketingVideoGenerationSummary,
  selectHook,
  verifyMarketingVideoGenerationReceipt,
};
