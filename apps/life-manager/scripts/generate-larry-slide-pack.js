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
// ponytail: no daemon, no lock file. Reads/writes plain JSON files under
// LM_DATA_DIR; run it right before each slot (cron/launchd), not
// continuously. Two concurrent runs for the same slot could pick the same
// candidate -- harmless, because the publication job's own effect_key dedup
// prevents a double post either way (see marketing-slide-pack-rotation.js).

const fs = require("node:fs");
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
    .map((row) => ({ packRef: `object://sha256/${row.receipt.pack_sha256}`, postedAt: row.receipt.published_at }));
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
async function resolveLarryJaSlot({ env = process.env, now = () => new Date().toISOString(), slot, resolveBackground, generateText, lane = JA_LANE, productionSlots = JA_LARRY_PRODUCTION_SLOTS } = {}) {
  const dataDir = path.resolve(required(env.LM_DATA_DIR, "LM_DATA_DIR"));
  const tenantId = required(env.LM_RUNTIME_TENANT_ID, "LM_RUNTIME_TENANT_ID");
  const nowIso = now();
  const dueSlot = slot || marketingVideoDueSlot(Date.parse(nowIso), "Asia/Tokyo", productionSlots) || nowIso;

  const objectStore = createContentObjectStore({ objectDir: path.join(dataDir, "objects") });
  const workspaceDir = path.join(dataDir, "tenants", encodeURIComponent(tenantId), "marketing", "slide-pack-rotation", lane.productId, ".workspace");
  const imageCacheDir = path.join(dataDir, "tenants", encodeURIComponent(tenantId), "marketing", "slide-pack-rotation", lane.productId, "image-cache");
  const pool = poolPath(dataDir, tenantId, lane.productId, lane.lane);
  let candidates = readPool(pool);

  if (candidates.length < MIN_POOL_SIZE) {
    const rejected = [];
    const generated = await generateSlidePackCandidates({
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
      geminiApiKey: generateText ? env.GEMINI_API_KEY : required(env.GEMINI_API_KEY, "GEMINI_API_KEY"),
      ...(resolveBackground ? { resolveBackground } : {}),
      ...(generateText ? { generateText } : {}),
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

  const postedHistory = readPostedHistory(distributionLedgerPath(dataDir, tenantId, lane.productId));
  const metrics = readCreativeMetricsForFamilies(dataDir, candidates);
  const selected = selectSlidePack({ candidates, postedHistory, metrics, minDaysBetweenRepeat: MIN_DAYS_BETWEEN_REPEAT, now: nowIso });
  if (!selected) {
    throw new Error(`${lane.name} slide pack rotation has no unposted candidate available for this slot`);
  }
  return { slot: dueSlot, selected };
}

if (require.main === module) {
  resolveLarryJaSlot({ slot: process.argv[2] || null }).then(({ slot, selected }) => {
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
