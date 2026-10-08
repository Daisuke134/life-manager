#!/usr/bin/env node
"use strict";

// Runs ahead of each JA Larry posting slot: tops up a pool of automated-gate
// -approved, unposted slide packs and resolves which one this slot should
// post. Prints the four object refs the canary already requires
// (LM_ANICCA_LARRY_JA_{PACK,MEDIA,CAPTION,APPROVAL}_REF) as shell `export`
// lines so a wrapper can `eval` them before invoking
// anicca-larry-ja-canary.js -- the canary itself is untouched, so its
// existing (heavily tested) validation still runs unchanged at publish time.
//
// ponytail: no daemon. Reads/writes plain JSON files under LM_DATA_DIR. The
// managed owner serializes runs; this resolver checks the durable distribution
// ledger before and after generation so an already-published slot cannot rotate
// to another pack. The content-scoped effect_key only deduplicates identical
// packs; it is not the slot fence.

const fs = require("node:fs");
const crypto = require("node:crypto");
const path = require("node:path");

const { createContentObjectStore } = require("../lib/content-object-store.js");
const { readCreativeMetrics } = require("../lib/marketing-creative-metrics.js");
const { generateSlidePackCandidates } = require("../lib/marketing-slide-pack-factory.js");
const { selectSlidePack } = require("../lib/marketing-slide-pack-rotation.js");
const { marketingVideoDueSlot } = require("../lib/honne-ja-shadow-schedule.js");
const { JA_LANE } = require("../lib/marketing-native-carousel-publication-adapter.js");
const { JA_LARRY_PRODUCTION_SLOTS } = require("./anicca-larry-ja-canary.js");

const MIN_POOL_SIZE = 4;
const MIN_DAYS_BETWEEN_REPEAT = 7;

function required(value, label) {
  const text = String(value == null ? "" : value).trim();
  if (!text) throw new Error(`${label} is required`);
  return text;
}

function poolPath(dataDir, tenantId, productId, lane) {
  return path.join(dataDir, "tenants", encodeURIComponent(tenantId), "marketing", "slide-pack-rotation", productId, `${lane}-pool.jsonl`);
}

function readPool(file) {
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, "utf8").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
}

function appendPool(file, candidates) {
  if (!candidates.length) return;
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const lines = candidates.map((candidate) => `${JSON.stringify(candidate)}\n`).join("");
  fs.appendFileSync(file, lines, { mode: 0o600 });
  fs.chmodSync(file, 0o600);
}

function distributionLedgerPath(dataDir, tenantId, productId) {
  return path.join(dataDir, "tenants", encodeURIComponent(tenantId), "marketing", "native-carousel-publication", productId, "distribution.jsonl");
}

function readPostedHistory(file) {
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, "utf8").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line))
    .filter((row) => row && row.receipt && row.receipt.pack_sha256 && row.receipt.published_at)
    .map((row) => {
      const effectParts = String(row.effect_key || "").split(":");
      const slotHash = effectParts.length === 8
        && effectParts[0] === "marketing"
        && effectParts[1] === "carousel"
        && /^[0-9a-f]{64}$/.test(effectParts[7])
        ? effectParts[7]
        : null;
      return {
        packRef: `object://sha256/${row.receipt.pack_sha256}`,
        ...(row.receipt.caption_sha256 ? { captionHash: row.receipt.caption_sha256 } : {}),
        ...(row.receipt.text_sha256 ? { textHash: row.receipt.text_sha256 } : {}),
        postedAt: row.receipt.published_at,
        integrationRef: row.receipt.integration_ref || null,
        slotHash,
        providerPostId: row.receipt.provider_post_id || null,
      };
    });
}

function addCandidateCopyHashes(candidates, objectStore) {
  return candidates.map((candidate) => {
    if (!candidate || typeof candidate.captionRef !== "string") return candidate;
    const caption = fs.readFileSync(objectStore.resolve(candidate.captionRef));
    const pack = JSON.parse(fs.readFileSync(objectStore.resolve(candidate.packRef), "utf8"));
    if (!Array.isArray(pack.slides)) throw new Error("slide pack rotation candidate is invalid");
    return {
      ...candidate,
      captionHash: crypto.createHash("sha256").update(caption).digest("hex"),
      textHash: crypto.createHash("sha256")
        .update(JSON.stringify(pack.slides.map((slide) => slide.text)))
        .digest("hex"),
    };
  });
}

function readCreativeMetricsForFamilies(dataDir, candidates) {
  const familyByPackRef = new Map(candidates.map((c) => [c.packRef, c.familyId]));
  return readCreativeMetrics(dataDir)
    .filter((row) => familyByPackRef.has(`object://sha256/${row.hook_id}`))
    .map((row) => ({ familyId: familyByPackRef.get(`object://sha256/${row.hook_id}`), score: row.score }));
}

// `lane` is any of the lane objects exported by
// marketing-native-carousel-publication-adapter.js (JA_LANE by default, for
// backward compatibility). This function is intentionally lane-agnostic --
// every field it reads (productId/locale/platform/accountId/integrationRef/
// renderer/packFormat/form/lastSlideRole/name/lane) already exists on every
// lane object, so the same rotation pipeline that stopped the JA Larry
// Instagram lane from reposting also fixes any other lane wired to it,
// without a second implementation.
async function resolveLarryJaSlot({ env = process.env, now = () => new Date().toISOString(), slot, resolveBackground, generateCandidates = generateSlidePackCandidates, lane = JA_LANE, productionSlots = JA_LARRY_PRODUCTION_SLOTS } = {}) {
  const dataDir = path.resolve(required(env.LM_DATA_DIR, "LM_DATA_DIR"));
  const tenantId = required(env.LM_RUNTIME_TENANT_ID, "LM_RUNTIME_TENANT_ID");
  const nowIso = now();
  const dueSlot = slot || marketingVideoDueSlot(Date.parse(nowIso), "Asia/Tokyo", productionSlots);
  if (!dueSlot) {
    throw Object.assign(new Error(`${lane.name} production has no due slot yet`), { code: "NO_DUE_SLOT" });
  }
  const distributionLedger = distributionLedgerPath(dataDir, tenantId, lane.productId);
  const initialPostedHistory = readPostedHistory(distributionLedger);
  const slotHash = crypto.createHash("sha256").update(dueSlot).digest("hex");
  const alreadyPublished = (history) => history.find(
    (row) => row.integrationRef === lane.integrationRef && row.slotHash === slotHash,
  );
  const initialSlotReceipt = alreadyPublished(initialPostedHistory);
  if (initialSlotReceipt) {
    return { slot: dueSlot, selected: null, alreadyPublished: true, providerPostId: initialSlotReceipt.providerPostId };
  }
  const dayFormatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  const localDay = dayFormatter.format(new Date(nowIso));
  const publishedToday = initialPostedHistory.filter((row) => {
    if (row.integrationRef !== lane.integrationRef) return false;
    const publishedAt = new Date(row.postedAt);
    return Number.isFinite(publishedAt.getTime()) && dayFormatter.format(publishedAt) === localDay;
  }).length;
  if (publishedToday >= productionSlots.length) {
    throw Object.assign(new Error(`${lane.name} daily publication limit reached`), { code: "DAILY_LIMIT_REACHED" });
  }

  const objectStore = createContentObjectStore({ objectDir: path.join(dataDir, "objects") });
  const workspaceDir = path.join(dataDir, "tenants", encodeURIComponent(tenantId), "marketing", "slide-pack-rotation", lane.productId, ".workspace");
  const imageCacheDir = path.join(dataDir, "tenants", encodeURIComponent(tenantId), "marketing", "slide-pack-rotation", lane.productId, "image-cache");
  const pool = poolPath(dataDir, tenantId, lane.productId, lane.lane);
  let candidates = readPool(pool);

  const available = selectSlidePack({
    candidates: addCandidateCopyHashes(candidates, objectStore),
    postedHistory: initialPostedHistory,
    integrationRef: lane.integrationRef,
    minDaysBetweenRepeat: MIN_DAYS_BETWEEN_REPEAT,
    now: nowIso,
  });
  // Total inventory can exceed the warm-up floor while every pack is still
  // inside the no-repeat window. Refill once through the same gated factory.
  if (candidates.length < MIN_POOL_SIZE || !available) {
    const rejected = [];
    const generated = await generateCandidates({
      objectStore,
      workspaceDir,
      imageCacheDir,
      tenantId,
      productId: lane.productId,
      locale: lane.locale,
      platform: lane.platform,
      accountId: lane.accountId,
      integrationRef: lane.integrationRef,
      rendererId: lane.renderer,
      packFormat: lane.packFormat,
      form: lane.form,
      lastSlideRole: lane.lastSlideRole,
      variantSeed: dueSlot,
      ...(resolveBackground ? { resolveBackground } : {}),
      // launchd hands Mobile jobs the managed venv python (Pillow lives there, not in the release python).
      ...(env.LIFE_MANAGER_PYTHON ? { python: env.LIFE_MANAGER_PYTHON } : {}),
      now,
      onRejected: (info) => rejected.push(info),
    });
    const existingRefs = new Set(candidates.map((c) => c.packRef));
    const fresh = generated.filter((c) => !existingRefs.has(c.packRef));
    appendPool(pool, fresh);
    candidates = candidates.concat(fresh);
    if (rejected.length) {
      process.stderr.write(`${JSON.stringify({ slide_pack_gate_rejected: rejected })}\n`);
    }
  }

  const postedHistory = readPostedHistory(distributionLedger);
  const slotReceipt = alreadyPublished(postedHistory);
  if (slotReceipt) {
    return { slot: dueSlot, selected: null, alreadyPublished: true, providerPostId: slotReceipt.providerPostId };
  }
  const metrics = readCreativeMetricsForFamilies(dataDir, candidates);
  const selected = selectSlidePack({
    candidates: addCandidateCopyHashes(candidates, objectStore),
    postedHistory,
    integrationRef: lane.integrationRef,
    metrics,
    minDaysBetweenRepeat: MIN_DAYS_BETWEEN_REPEAT,
    now: nowIso,
  });
  if (!selected) {
    throw new Error(`${lane.name} slide pack rotation has no unposted candidate available for this slot`);
  }
  return { slot: dueSlot, selected };
}

if (require.main === module) {
  resolveLarryJaSlot({ slot: process.argv[2] || null }).then(({ slot, selected, alreadyPublished }) => {
    if (alreadyPublished) {
      process.stderr.write(`slot already published: ${slot}\n`);
      process.exitCode = 75;
      return;
    }
    process.stdout.write([
      `export LM_ANICCA_LARRY_JA_PACK_REF='${selected.packRef}'`,
      `export LM_ANICCA_LARRY_JA_MEDIA_REFS='${JSON.stringify(selected.mediaRefs)}'`,
      `export LM_ANICCA_LARRY_JA_CAPTION_REF='${selected.captionRef}'`,
      `export LM_ANICCA_LARRY_JA_APPROVAL_REF='${selected.approvalRef}'`,
      `export LM_ANICCA_LARRY_JA_SLOT='${slot}'`,
      "",
    ].join("\n"));
  }).catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}

module.exports = { MIN_DAYS_BETWEEN_REPEAT, MIN_POOL_SIZE, poolPath, readPool, readPostedHistory, resolveLarryJaSlot };
