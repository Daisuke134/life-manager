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
const { createMarketingLocalLedger } = require("../lib/marketing-local-ledger.js");
const { COPY_SOURCE_HASH, generateSlidePackCandidates } = require("../lib/marketing-slide-pack-factory.js");
const { selectSlidePack } = require("../lib/marketing-slide-pack-rotation.js");
const { marketingVideoDaySlots, marketingVideoDueSlots } = require("../lib/honne-ja-shadow-schedule.js");
const { JA_LANE } = require("../lib/marketing-native-carousel-publication-adapter.js");
const { JA_LARRY_PRODUCTION_SLOTS } = require("./anicca-larry-ja-canary.js");

const MIN_DAYS_BETWEEN_REPEAT = 7;
const MIN_FAMILY_METRIC_POSTS = 3;
const MAX_PUBLICATION_TIME_SKEW_MS = 180_000;
const MAX_SLOT_LATE_MS = 15 * 60 * 1000;

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

function filterCandidatesForLane(candidates, lane, objectStore) {
  if (lane.platform !== "tiktok") return candidates;
  return candidates.filter((candidate) => {
    if (!candidate?.packRef || !candidate?.captionRef) return false;
    const pack = JSON.parse(fs.readFileSync(objectStore.resolve(candidate.packRef), "utf8"));
    const slideText = (Array.isArray(pack.slides) ? pack.slides : []).map((slide) => String(slide?.text || "")).join("\n");
    const caption = fs.readFileSync(objectStore.resolve(candidate.captionRef), "utf8");
    return !/\bLink in bio\b|プロフィールのリンク/i.test(`${slideText}\n${caption}`);
  });
}

function readCreativeMetricsForFamilies(dataDir, candidates, lane, postedHistory = []) {
  const familyByPackRef = new Map();
  const ambiguousPacks = new Set();
  for (const candidate of candidates) {
    if (!candidate || typeof candidate.packRef !== "string" || typeof candidate.familyId !== "string") continue;
    const existing = familyByPackRef.get(candidate.packRef);
    if (existing && existing !== candidate.familyId) ambiguousPacks.add(candidate.packRef);
    else familyByPackRef.set(candidate.packRef, candidate.familyId);
  }
  for (const packRef of ambiguousPacks) familyByPackRef.delete(packRef);
  if (!lane?.integrationRef || !lane.integrationId || !lane.productId || !lane.locale) return [];

  const publicationsByPostId = new Map();
  const ambiguousPosts = new Set();
  for (const publication of postedHistory) {
    if (publication?.integrationRef !== lane.integrationRef
        || !familyByPackRef.has(publication.packRef)
        || typeof publication.providerPostId !== "string"
        || !Number.isFinite(Date.parse(publication.postedAt || ""))) continue;
    const identity = {
      familyId: familyByPackRef.get(publication.packRef),
      packRef: publication.packRef,
      publishedAt: publication.postedAt,
    };
    const existing = publicationsByPostId.get(publication.providerPostId);
    if (existing && (existing.familyId !== identity.familyId
        || existing.packRef !== identity.packRef
        || existing.publishedAt !== identity.publishedAt)) {
      ambiguousPosts.add(publication.providerPostId);
    } else publicationsByPostId.set(publication.providerPostId, identity);
  }
  for (const postId of ambiguousPosts) publicationsByPostId.delete(postId);
  if (!publicationsByPostId.size) return [];

  const metricFile = path.join(dataDir, "marketing-owner-events", "state", "post-metrics.jsonl");
  let metricLines;
  try { metricLines = fs.readFileSync(metricFile, "utf8").split(/\r?\n/).filter(Boolean); }
  catch (error) { if (error.code === "ENOENT") return []; throw error; }
  const metricsByPostId = new Map();
  const ambiguousMetrics = new Set();
  for (const line of metricLines) {
    let metric;
    try { metric = JSON.parse(line); } catch { continue; }
    const providerPostId = metric?.postiz_id;
    const publication = publicationsByPostId.get(providerPostId);
    // Native collectors omit locale and may not know the product. The exact
    // post/integration receipt supplies that lane identity; reject conflicts.
    if (!publication
        || (metric.product_id != null && metric.product_id !== lane.productId)
        || metric.platform !== lane.platform
        || (metric.locale != null && metric.locale !== lane.locale)
        || metric.integration_id !== lane.integrationId
        || metric.target_age_hours !== 24
        || metric.checkpoint_status !== "measured"
        || metric.checkpoint_sla_status !== "in_window"
        || !Number.isSafeInteger(metric.views) || metric.views < 0
        || !Number.isFinite(Date.parse(metric.observed_at || ""))) continue;
    const metricPublishedAt = Date.parse(metric.published_at || "");
    if (!Number.isFinite(metricPublishedAt)
        || Math.abs(metricPublishedAt - Date.parse(publication.publishedAt)) > MAX_PUBLICATION_TIME_SKEW_MS) continue;
    const existing = metricsByPostId.get(providerPostId);
    if (!existing || Date.parse(existing.observed_at) < Date.parse(metric.observed_at)) {
      metricsByPostId.set(providerPostId, metric);
      ambiguousMetrics.delete(providerPostId);
    } else if (existing.observed_at === metric.observed_at && existing.views !== metric.views) {
      ambiguousMetrics.add(providerPostId);
    }
  }
  for (const postId of ambiguousMetrics) metricsByPostId.delete(postId);

  const viewsByFamily = new Map();
  for (const [providerPostId, metric] of metricsByPostId) {
    const publication = publicationsByPostId.get(providerPostId);
    const samples = viewsByFamily.get(publication.familyId) || new Map();
    samples.set(providerPostId, metric.views);
    viewsByFamily.set(publication.familyId, samples);
  }
  return [...viewsByFamily.entries()]
    .filter(([, samples]) => samples.size >= MIN_FAMILY_METRIC_POSTS)
    .map(([familyId, samples]) => ({
      familyId,
      score: [...samples.values()].reduce((sum, views) => sum + views, 0) / samples.size,
      samples: samples.size,
    }))
    .sort((left, right) => left.familyId.localeCompare(right.familyId));
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
  const distributionLedger = distributionLedgerPath(dataDir, tenantId, lane.productId);
  const initialPostedHistory = readPostedHistory(distributionLedger);
  const nowMs = Date.parse(nowIso);
  const dueSlots = marketingVideoDueSlots(nowMs, "Asia/Tokyo", productionSlots);
  // TikTok uses fixed organic slots: allow launch jitter, but never catch up an expired slot.
  const freshDueSlots = lane.platform === "tiktok"
    ? dueSlots
      .filter((candidateSlot) => nowMs - Date.parse(candidateSlot) <= MAX_SLOT_LATE_MS)
      .sort((left, right) => Date.parse(left) - Date.parse(right))
    : dueSlots;
  const slotHashFor = (candidateSlot) => crypto.createHash("sha256").update(candidateSlot).digest("hex");
  const alreadyPublished = (history, candidateSlot) => history.find(
    (row) => row.integrationRef === lane.integrationRef && row.slotHash === slotHashFor(candidateSlot),
  );
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

  const dueSlot = slot || (lane.platform === "tiktok"
    ? freshDueSlots.at(-1)
    : dueSlots.find((candidateSlot) => !alreadyPublished(initialPostedHistory, candidateSlot))) || null;
  if (!dueSlot) {
    throw Object.assign(new Error(`${lane.name} production has no due slot yet`), { code: "NO_DUE_SLOT" });
  }
  const initialSlotReceipt = alreadyPublished(initialPostedHistory, dueSlot);
  if (initialSlotReceipt) {
    return { slot: dueSlot, selected: null, alreadyPublished: true, providerPostId: initialSlotReceipt.providerPostId };
  }
  if (!freshDueSlots.includes(dueSlot)) {
    throw Object.assign(new Error(`${lane.name} production has no due slot yet`), { code: "NO_DUE_SLOT" });
  }

  const objectStore = createContentObjectStore({ objectDir: path.join(dataDir, "objects") });
  const integrationKey = lane.platform + "_integration_ref";
  const slotProbeId = "slot-probe-" + crypto.createHash("sha256")
    .update([tenantId, lane.integrationRef, dueSlot].join("\n"))
    .digest("hex");
  const priorSlot = await createMarketingLocalLedger({ dataDir, env, now }).readPriorPublicationForSlot({
    tenant_id: tenantId,
    job_id: slotProbeId,
    input_refs: {
      product_ref: "product://" + lane.productId,
      format_ref: "format://" + lane.formatId,
      locale_ref: "locale://" + lane.locale,
      platform_ref: "platform://" + lane.platform,
      slot_ref: "schedule-slot://" + dueSlot,
      [integrationKey]: lane.integrationRef,
    },
  });
  if (priorSlot) {
    if (priorSlot.slot_conflict === true) {
      throw Object.assign(new Error(`${lane.name} slot has conflicting publication jobs`), { code: "SLOT_ALREADY_ATTEMPTED" });
    }
    const priorJob = priorSlot.job;
    const priorReceipt = priorSlot.receipt;
    if (priorReceipt?.status === "published" && priorReceipt.provider_reconciled === true
        && typeof priorReceipt.provider_post_id === "string" && priorReceipt.provider_post_id) {
      return { slot: dueSlot, selected: null, alreadyPublished: true, providerPostId: priorReceipt.provider_post_id };
    }
    if (priorJob.status === "queued" && priorJob.unknown_effect !== true && priorReceipt === null) {
      const refs = priorJob.input_refs || {};
      const selected = {
        packRef: refs.pack_ref,
        mediaRefs: refs.media_refs,
        captionRef: refs.caption_ref,
        approvalRef: refs.approval_ref,
      };
      if (typeof selected.packRef !== "string" || !Array.isArray(selected.mediaRefs)
          || typeof selected.captionRef !== "string" || typeof selected.approvalRef !== "string"
          || filterCandidatesForLane([selected], lane, objectStore).length !== 1) {
        throw Object.assign(new Error(`${lane.name} slot already has a publication attempt`), { code: "SLOT_ALREADY_ATTEMPTED" });
      }
      return { slot: dueSlot, selected, queuedJobReused: true };
    }
    throw Object.assign(new Error(`${lane.name} slot already has a publication attempt`), { code: "SLOT_ALREADY_ATTEMPTED" });
  }

  const workspaceDir = path.join(dataDir, "tenants", encodeURIComponent(tenantId), "marketing", "slide-pack-rotation", lane.productId, ".workspace");
  const imageCacheDir = path.join(dataDir, "tenants", encodeURIComponent(tenantId), "marketing", "slide-pack-rotation", lane.productId, "image-cache");
  const pool = poolPath(dataDir, tenantId, lane.productId, lane.lane);
  let candidates = readPool(pool);
  let selectable = filterCandidatesForLane(candidates, lane, objectStore);

  const selectionOptions = {
    postedHistory: initialPostedHistory,
    integrationRef: lane.integrationRef,
    minDaysBetweenRepeat: MIN_DAYS_BETWEEN_REPEAT,
    now: nowIso,
  };
  const copyHashed = addCandidateCopyHashes(selectable, objectStore);
  const currentAvailable = selectSlidePack({
    ...selectionOptions,
    candidates: copyHashed.filter((candidate) => candidate?.copySourceHash === COPY_SOURCE_HASH),
  });
  const available = currentAvailable || selectSlidePack({ ...selectionOptions, candidates: copyHashed });
  // Legacy stock must not suppress new copy. Refill once only when current
  // copy has no eligible pack; keep old stock as a fallback.
  if (!currentAvailable) {
    const rejected = [];
    let generated;
    try {
      generated = await generateCandidates({
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
    } catch (error) {
      if (!available) throw error;
      process.stderr.write(`${JSON.stringify({ slide_pack_refill_failed: error.message })}\n`);
      generated = [];
    }
    const existingRefs = new Set(candidates.map((c) => c.packRef));
    const fresh = generated.filter((c) => !existingRefs.has(c.packRef));
    appendPool(pool, fresh);
    candidates = candidates.concat(fresh);
    selectable = filterCandidatesForLane(candidates, lane, objectStore);
    if (rejected.length) {
      process.stderr.write(`${JSON.stringify({ slide_pack_gate_rejected: rejected })}\n`);
    }
  }

  const postedHistory = readPostedHistory(distributionLedger);
  const slotReceipt = alreadyPublished(postedHistory, dueSlot);
  if (slotReceipt) {
    return { slot: dueSlot, selected: null, alreadyPublished: true, providerPostId: slotReceipt.providerPostId };
  }
  const metrics = readCreativeMetricsForFamilies(dataDir, selectable, lane, postedHistory);
  const finalCandidates = addCandidateCopyHashes(selectable, objectStore);
  const finalSelectionOptions = { ...selectionOptions, postedHistory, metrics };
  const selected = selectSlidePack({
    ...finalSelectionOptions,
    candidates: finalCandidates.filter((candidate) => candidate?.copySourceHash === COPY_SOURCE_HASH),
  }) || selectSlidePack({ ...finalSelectionOptions, candidates: finalCandidates });
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

module.exports = {
  MIN_DAYS_BETWEEN_REPEAT,
  MIN_FAMILY_METRIC_POSTS,
  poolPath,
  readCreativeMetricsForFamilies,
  readPool,
  readPostedHistory,
  resolveLarryJaSlot,
};
