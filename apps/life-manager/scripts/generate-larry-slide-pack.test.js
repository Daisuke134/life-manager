"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const { importContentObject } = require("../lib/content-object-store.js");
const { createMarketingLocalLedger } = require("../lib/marketing-local-ledger.js");
const { JA_LANE, JA_MAIN_TIKTOK_LANE, EN_AFFIRMATION_LANE, EN_AFFIRMATION_TIKTOK_LANE, EN_SLIDESHOW_TIKTOK_LANE, JA_BUDDHA_TIKTOK_LANE } = require("../lib/marketing-native-carousel-publication-adapter.js");
const { EN_AFFIRMATION_TIKTOK_PRODUCTION_SLOTS, EN_SLIDESHOW_PRODUCTION_SLOTS } = require("./anicca-larry-ja-canary.js");
const {
  MIN_DAYS_BETWEEN_REPEAT,
  MIN_POOL_SIZE,
  poolPath,
  readPostedHistory,
  resolveLarryJaSlot,
} = require("./generate-larry-slide-pack.js");

const TENANT = "dais-local";
const NOW = "2026-09-28T01:30:00.000Z";

function tempDataDir(t) {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "larry-slide-pack-scheduler-"));
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  return dataDir;
}

function fakeResolveBackground() {
  return async () => ({ file: path.join(os.tmpdir(), "generate-larry-slide-pack-fixture.png"), costUsd: 0, cached: true });
}

function makeFixtureBackgroundOnce() {
  const file = path.join(os.tmpdir(), "generate-larry-slide-pack-fixture.png");
  if (fs.existsSync(file)) return;
  const { spawnSync } = require("node:child_process");
  // A noisy (non-flat) fixture -- matches marketing-slide-pack-factory.test.js's
  // fixture -- so the renderer's real contrast check reliably passes
  // regardless of the (freshly LLM-generated in production, counter-faked
  // here) text length/content.
  const script = `
from PIL import Image
import random
random.seed(7)
im = Image.new("RGB", (600, 750))
px = im.load()
for y in range(750):
    for x in range(600):
        px[x, y] = ((x * 255) // 600, (y * 255) // 750, random.randint(0, 255))
im.save("${file}")
`;
  const result = spawnSync("python3", ["-c", script], { encoding: "utf8" });
  if (result.status !== 0) throw new Error(`fixture background generation failed: ${result.stderr}`);
}

function writeDistributionLedger(dataDir, rows) {
  const file = path.join(dataDir, "tenants", encodeURIComponent(TENANT), "marketing", "native-carousel-publication", JA_LANE.productId, "distribution.jsonl");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, rows.map((r) => `${JSON.stringify(r)}\n`).join(""));
}

function seedPersistedSlidePool(dataDir, lane) {
  const objectDir = path.join(dataDir, "objects");
  const importText = (name, value) => {
    const source = path.join(dataDir, name);
    fs.writeFileSync(source, value);
    return importContentObject(source, { objectDir }).ref;
  };
  const mediaRefs = Array.from({ length: 6 }, (_, index) => importText(
    `catchup-media-${index}.jpg`, Buffer.from([0xff, 0xd8, 0xff, index + 1, 0xff, 0xd9]),
  ));
  const candidates = Array.from({ length: MIN_POOL_SIZE }, (_, index) => {
    const slides = mediaRefs.map((media_ref, position) => ({
      position: position + 1,
      role: position === 0 ? "hook" : (position === 5 ? "cta" : "body"),
      text: `stored catch-up text ${index}-${position}`,
      media_ref,
    }));
    return {
      packRef: importText(`catchup-pack-${index}.json`, JSON.stringify({ slides })),
      mediaRefs,
      captionRef: importText(`catchup-caption-${index}.txt`, `stored caption ${index}`),
      approvalRef: importText(`catchup-approval-${index}.json`, JSON.stringify({ status: "approved" })),
      familyId: `stored-family-${index}`,
      createdAt: "2026-10-01T00:00:00.000Z",
    };
  });
  const pool = poolPath(dataDir, TENANT, lane.productId, lane.lane);
  fs.mkdirSync(path.dirname(pool), { recursive: true });
  fs.writeFileSync(pool, candidates.map((row) => `${JSON.stringify(row)}\n`).join(""));
  return candidates;
}

async function seedPublicationJob(dataDir, lane, slot, options = {}) {
  const now = options.now || slot;
  const ledger = createMarketingLocalLedger({ dataDir, now: () => now });
  const jobId = "slot-job-" + String(lane.lane || lane.accountId).replace(/[^A-Za-z0-9_-]/g, "-")
    + "-" + slot.replace(/[^0-9]/g, "");
  const candidate = options.candidate;
  const input = {
    job_id: jobId,
    tenant_id: TENANT,
    loop_id: "marketing.video.publish",
    capability: "marketing.video.publish",
    effect_class: "publish",
    effect_key: "marketing:carousel:test:" + slot,
    input_refs: {
      product_ref: "product://" + lane.productId,
      format_ref: "format://" + lane.formatId,
      form_ref: "form://" + lane.form,
      locale_ref: "locale://" + lane.locale,
      slot_ref: "schedule-slot://" + slot,
      platform_ref: "platform://" + lane.platform,
      account_ref: lane.accountRef,
      tiktok_integration_ref: lane.integrationRef,
      ...(candidate ? {
        pack_ref: candidate.packRef,
        media_refs: candidate.mediaRefs,
        caption_ref: candidate.captionRef,
        approval_ref: candidate.approvalRef,
      } : {}),
    },
    max_attempts: 3,
    available_at: now,
  };
  await ledger.enqueueJob(input);
  if (options.unknownEffect === true) {
    const claim = await ledger.claimJob({
      tenantId: TENANT,
      jobId,
      capability: "marketing.video.publish",
      workerId: "slot-fixture-worker",
      leaseSeconds: 30,
    });
    await ledger.failJob({
      tenantId: TENANT,
      jobId,
      attempt: claim.attempt,
      workerId: "slot-fixture-worker",
      errorCode: "provider_unknown",
      unknownEffect: true,
    });
  }
  return { ledger, input, jobId };
}

test("resolveLarryJaSlot generates a pool from empty and returns a candidate", { timeout: 60_000 }, async (t) => {
  makeFixtureBackgroundOnce();
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const { slot, selected } = await resolveLarryJaSlot({ env, now: () => NOW, slot: "2026-09-28T01:30:00.000Z", resolveBackground: fakeResolveBackground() });
  assert.equal(slot, "2026-09-28T01:30:00.000Z");
  assert.match(selected.packRef, /^object:\/\/sha256\/[0-9a-f]{64}$/);
  assert.equal(selected.mediaRefs.length, 6);

  const pool = poolPath(dataDir, TENANT, JA_LANE.productId, JA_LANE.lane);
  assert.ok(fs.existsSync(pool));
});

test("resolveLarryJaSlot returns a typed no-due result before the first slot without generating a pack", async (t) => {
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  let generateCalls = 0;
  await assert.rejects(resolveLarryJaSlot({
    env,
    now: () => "2026-10-09T00:05:00.000+09:00",
    lane: EN_AFFIRMATION_LANE,
    productionSlots: ["10:00", "15:00", "20:00"],
    generateCandidates: async () => {
      generateCalls += 1;
      throw new Error("must not generate before the first due slot");
    },
  }), (error) => error && error.code === "NO_DUE_SLOT");
  assert.equal(generateCalls, 0);
  assert.equal(fs.existsSync(poolPath(dataDir, TENANT, EN_AFFIRMATION_LANE.productId, EN_AFFIRMATION_LANE.lane)), false);
});

test("resolveLarryJaSlot preserves the oldest-slot catch-up behavior for Instagram", { timeout: 60_000 }, async (t) => {
  makeFixtureBackgroundOnce();
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const result = await resolveLarryJaSlot({
    env,
    now: () => "2026-09-28T09:00:00.000Z", // 18:00 JST; 10:30 and 16:30 have both passed.
    resolveBackground: fakeResolveBackground(),
  });

  assert.equal(result.slot, "2026-09-28T01:30:00.000Z"); // first unposted Instagram slot, 10:30 JST.
  assert.ok(result.selected);
});

test("resolveLarryJaSlot selects the latest fresh TikTok slot instead of catching up an older slot", async (t) => {
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const lane = EN_AFFIRMATION_TIKTOK_LANE;
  seedPersistedSlidePool(dataDir, lane);
  const result = await resolveLarryJaSlot({
    env,
    now: () => "2026-10-13T05:16:00.000Z", // 14:16 JST; 14:15 is current, 09:15 is stale.
    lane,
    productionSlots: EN_AFFIRMATION_TIKTOK_PRODUCTION_SLOTS,
    generateCandidates: async () => { throw new Error("the persisted pack pool should be reused"); },
  });

  assert.equal(result.slot, "2026-10-13T05:15:00.000Z");
  assert.ok(result.selected);
});

test("resolveLarryJaSlot does not catch up a missed TikTok slot after its freshness window", async (t) => {
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  let generateCalls = 0;
  await assert.rejects(resolveLarryJaSlot({
    env,
    now: () => "2026-10-13T07:10:00.000Z", // 16:10 JST; 14:15 is over 15 minutes late.
    lane: EN_AFFIRMATION_TIKTOK_LANE,
    productionSlots: EN_AFFIRMATION_TIKTOK_PRODUCTION_SLOTS,
    generateCandidates: async () => {
      generateCalls += 1;
      throw new Error("must not generate for a missed slot");
    },
  }), (error) => error && error.code === "NO_DUE_SLOT");
  assert.equal(generateCalls, 0);
});

test("resolveLarryJaSlot advances to the current slot without replaying an older unknown job", { timeout: 60_000 }, async (t) => {
  makeFixtureBackgroundOnce();
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const oldSlot = "2026-10-13T00:15:00.000Z";
  const currentSlot = "2026-10-13T05:15:00.000Z";
  await seedPublicationJob(dataDir, EN_AFFIRMATION_TIKTOK_LANE, oldSlot, {
    now: "2026-10-13T05:15:22.000Z",
    unknownEffect: true,
  });
  seedPersistedSlidePool(dataDir, EN_AFFIRMATION_TIKTOK_LANE);

  const result = await resolveLarryJaSlot({
    env,
    now: () => "2026-10-13T05:16:00.000Z", // 14:16 JST; 14:15 is current, 09:15 is stale.
    lane: EN_AFFIRMATION_TIKTOK_LANE,
    productionSlots: EN_AFFIRMATION_TIKTOK_PRODUCTION_SLOTS,
    generateCandidates: async () => { throw new Error("the persisted pack pool should be reused"); },
  });

  assert.equal(result.slot, currentSlot);
  assert.ok(result.selected);
});

test("resolveLarryJaSlot holds an already-attempted current slot without generating or re-enqueueing", async (t) => {
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const currentSlot = "2026-10-13T05:15:00.000Z";
  await seedPublicationJob(dataDir, EN_AFFIRMATION_TIKTOK_LANE, currentSlot, {
    now: "2026-10-13T05:15:22.000Z",
    unknownEffect: true,
  });
  let generateCalls = 0;

  await assert.rejects(resolveLarryJaSlot({
    env,
    now: () => "2026-10-13T05:16:00.000Z",
    lane: EN_AFFIRMATION_TIKTOK_LANE,
    productionSlots: EN_AFFIRMATION_TIKTOK_PRODUCTION_SLOTS,
    generateCandidates: async () => { generateCalls += 1; throw new Error("must not regenerate an attempted slot"); },
  }), (error) => error && error.code === "SLOT_ALREADY_ATTEMPTED");

  assert.equal(generateCalls, 0);
});

test("resolveLarryJaSlot refuses a safe queued job when a second historical same-slot job exists", async (t) => {
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const lane = EN_AFFIRMATION_TIKTOK_LANE;
  const currentSlot = "2026-10-13T05:15:00.000Z";
  const now = "2026-10-13T05:16:00.000Z";
  const candidate = seedPersistedSlidePool(dataDir, lane)[0];
  const { ledger, jobId } = await seedPublicationJob(dataDir, lane, currentSlot, { now, candidate });
  const queued = await ledger.readJob({ tenantId: TENANT, jobId });
  const unresolved = {
    ...queued,
    job_id: "historical-unknown-same-slot-job",
    effect_key: "historical-unknown-same-slot-effect",
    status: "failed",
    attempt: 1,
    unknown_effect: true,
    error_code: "provider_unknown",
    lease_owner: null,
    lease_expires_at: null,
  };
  fs.appendFileSync(path.join(dataDir, "marketing", "jobs.jsonl"), `${JSON.stringify({
    schema_version: 1,
    kind: "job",
    event: "fail",
    job: unresolved,
  })}\n`);
  let generateCalls = 0;

  await assert.rejects(resolveLarryJaSlot({
    env,
    now: () => now,
    lane,
    productionSlots: EN_AFFIRMATION_TIKTOK_PRODUCTION_SLOTS,
    generateCandidates: async () => { generateCalls += 1; throw new Error("must not regenerate a conflicted slot"); },
  }), (error) => error && error.code === "SLOT_ALREADY_ATTEMPTED");

  assert.equal(generateCalls, 0);
});

test("resolveLarryJaSlot reuses a safe queued job for its current slot", async (t) => {
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const lane = EN_AFFIRMATION_TIKTOK_LANE;
  const currentSlot = "2026-10-13T05:15:00.000Z";
  const now = "2026-10-13T05:16:00.000Z";
  const candidate = seedPersistedSlidePool(dataDir, lane)[0];
  await seedPublicationJob(dataDir, lane, currentSlot, { now, candidate });
  let generateCalls = 0;

  const result = await resolveLarryJaSlot({
    env,
    now: () => now,
    lane,
    productionSlots: EN_AFFIRMATION_TIKTOK_PRODUCTION_SLOTS,
    generateCandidates: async () => { generateCalls += 1; throw new Error("queued job must keep its original pack"); },
  });

  assert.equal(result.slot, currentSlot);
  assert.deepEqual(result.selected, {
    packRef: candidate.packRef,
    mediaRefs: candidate.mediaRefs,
    captionRef: candidate.captionRef,
    approvalRef: candidate.approvalRef,
  });
  assert.equal(result.queuedJobReused, true);
  assert.equal(generateCalls, 0);
});

test("resolveLarryJaSlot does not consume future daily slots before their configured times", async (t) => {
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const lane = JA_MAIN_TIKTOK_LANE;
  const slots = ["08:00", "16:00", "22:37"];
  const slot08 = "2026-10-09T23:00:00.000Z";
  const slot16 = "2026-10-10T07:00:00.000Z";
  const slot22 = "2026-10-10T13:37:00.000Z";
  const slotReceipt = (slot, suffix, postedAt) => ({
    effect_key: `marketing:carousel:${lane.productId}:creative:${"a".repeat(64)}:${"b".repeat(64)}:${"c".repeat(64)}:${crypto.createHash("sha256").update(slot).digest("hex")}`,
    job_id: `published-${suffix}`,
    receipt: {
      kind: "marketing_native_carousel_distribution",
      status: "published",
      integration_ref: lane.integrationRef,
      pack_sha256: suffix.repeat(64),
      published_at: postedAt,
      provider_post_id: `postiz-${suffix}`,
      provider_reconciled: true,
    },
  });
  writeDistributionLedger(dataDir, [
    slotReceipt(slot08, "d", "2026-10-10T00:06:09.055Z"),
    slotReceipt(slot16, "e", "2026-10-10T08:50:15.021Z"),
  ]);
  const stored = seedPersistedSlidePool(dataDir, lane);
  let generateCalls = 0;
  await assert.rejects(resolveLarryJaSlot({
    env,
    now: () => "2026-10-10T08:55:00.000Z", // 17:55 JST: third configured slot is still ahead.
    lane,
    productionSlots: slots,
    generateCandidates: async () => {
      generateCalls += 1;
      throw new Error("future slot must not be published early");
    },
  }), (error) => error && error.code === "NO_DUE_SLOT");
  assert.equal(generateCalls, 0);
  const result = await resolveLarryJaSlot({
    env,
    now: () => "2026-10-10T13:37:00.000Z", // 22:37 JST: the last configured slot is now due.
    lane,
    productionSlots: slots,
    generateCandidates: async () => {
      generateCalls += 1;
      throw new Error("due slot should reuse the durable pack pool");
    },
  });
  assert.equal(result.slot, slot22);
  assert.equal(result.catchUp, undefined);
  assert.ok(stored.some((candidate) => candidate.packRef === result.selected.packRef));
  assert.equal(generateCalls, 0);
});

test("resolveLarryJaSlot stops after the lane's verified daily receipt limit", async (t) => {
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  writeDistributionLedger(dataDir, [
    "2026-10-09T00:05:00.000+09:00",
    "2026-10-09T00:13:00.000+09:00",
    "2026-10-09T00:17:00.000+09:00",
  ].map((publishedAt, index) => ({
    effect_key: `marketing:carousel:anicca-ios:creative:${"a".repeat(64)}:${"b".repeat(64)}:${"c".repeat(64)}:${crypto.createHash("sha256").update(`slot-${index}`).digest("hex")}`,
    job_id: `published-off-slot-${index}`,
    receipt: {
      kind: "marketing_native_carousel_distribution",
      status: "published",
      integration_ref: EN_AFFIRMATION_LANE.integrationRef,
      pack_sha256: "a".repeat(64),
      published_at: publishedAt,
      provider_post_id: `postiz-off-slot-${index}`,
      provider_reconciled: true,
    },
  })));
  let generateCalls = 0;
  await assert.rejects(resolveLarryJaSlot({
    env,
    now: () => "2026-10-09T01:05:00.000Z",
    lane: EN_AFFIRMATION_LANE,
    productionSlots: ["10:00", "15:00", "20:00"],
    generateCandidates: async () => {
      generateCalls += 1;
      throw new Error("must not generate after the lane daily limit");
    },
  }), (error) => error && error.code === "DAILY_LIMIT_REACHED");
  assert.equal(generateCalls, 0);
});

test("resolveLarryJaSlot does not regenerate once the pool already has enough candidates", { timeout: 60_000 }, async (t) => {
  makeFixtureBackgroundOnce();
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  await resolveLarryJaSlot({ env, now: () => NOW, slot: "2026-09-28T01:30:00.000Z", resolveBackground: fakeResolveBackground() });
  const pool = poolPath(dataDir, TENANT, JA_LANE.productId, JA_LANE.lane);
  const before = fs.readFileSync(pool, "utf8");
  await resolveLarryJaSlot({ env, now: () => "2026-09-28T07:30:00.000Z", slot: "2026-09-28T07:30:00.000Z", resolveBackground: fakeResolveBackground() });
  const after = fs.readFileSync(pool, "utf8");
  assert.equal(before, after, "pool should not grow once above MIN_POOL_SIZE");
});

test("TikTok rotation preserves but never selects approved packs with an unavailable link-in-bio CTA", async (t) => {
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const lane = EN_AFFIRMATION_TIKTOK_LANE;
  const objectDir = path.join(dataDir, "objects");
  const importText = (name, value) => {
    const source = path.join(dataDir, name);
    fs.writeFileSync(source, value);
    return importContentObject(source, { objectDir }).ref;
  };
  const slides = (last) => Array.from({ length: 6 }, (_, index) => ({
    position: index + 1,
    role: index === 0 ? "hook" : (index === 5 ? "cta" : "body"),
    text: index === 5 ? last : `body ${index + 1}`,
  }));
  const oldPackRef = importText("old-link-in-bio-pack.json", JSON.stringify({ slides: slides("Anicca\nLink in bio") }));
  const oldCaptionRef = importText("old-link-in-bio-caption.txt", "What would make this morning gentler?\n\nLink in bio for the app\n");
  const oldCandidate = { packRef: oldPackRef, captionRef: oldCaptionRef, familyId: "question-hook", createdAt: "2026-10-11T00:00:00.000Z" };
  const hiddenCtaSlides = slides("Anicca\nSearch Anicca on the App Store");
  hiddenCtaSlides[2].text = "A gentle reminder: Link in bio";
  const hiddenCtaPackRef = importText("hidden-link-in-bio-pack.json", JSON.stringify({ slides: hiddenCtaSlides }));
  const searchableCaptionRef = importText("search-cta-caption.txt", "What would make this morning gentler?\n\nSearch Anicca on the App Store\n");
  const hiddenCtaCandidate = { packRef: hiddenCtaPackRef, captionRef: searchableCaptionRef, familyId: "listicle", createdAt: "2026-10-11T00:01:00.000Z" };
  const pool = poolPath(dataDir, TENANT, lane.productId, lane.lane);
  fs.mkdirSync(path.dirname(pool), { recursive: true });
  fs.writeFileSync(pool, `${JSON.stringify(oldCandidate)}\n${JSON.stringify(hiddenCtaCandidate)}\n`);

  const freshPackRef = importText("search-cta-pack.json", JSON.stringify({ slides: slides("Anicca\nSearch Anicca on the App Store") }));
  const freshCaptionRef = importText("search-cta-caption.txt", "What would make this morning gentler?");
  const freshCandidate = { packRef: freshPackRef, captionRef: freshCaptionRef, familyId: "question-hook", createdAt: "2026-10-12T11:15:00.000Z" };
  let generateCalls = 0;
  const slot = "2026-10-12T11:15:00.000Z";
  const result = await resolveLarryJaSlot({
    env,
    now: () => slot,
    slot,
    lane,
    productionSlots: ["09:15", "14:15", "20:15"],
    generateCandidates: async () => { generateCalls += 1; return [freshCandidate]; },
  });

  assert.equal(generateCalls, 1);
  assert.equal(result.selected.packRef, freshPackRef);
  const persisted = fs.readFileSync(pool, "utf8").split(/\r?\n/).filter(Boolean).map(JSON.parse);
  assert.ok(persisted.some((candidate) => candidate.packRef === oldPackRef), "old immutable candidate remains in the pool history");
  assert.ok(persisted.some((candidate) => candidate.packRef === hiddenCtaPackRef), "invalid old candidate remains in the pool history");
  assert.ok(persisted.some((candidate) => candidate.packRef === freshPackRef));
});

test("resolveLarryJaSlot never repeats a pack posted within MIN_DAYS_BETWEEN_REPEAT and is idempotent per slot", { timeout: 60_000 }, async (t) => {
  makeFixtureBackgroundOnce();
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const first = await resolveLarryJaSlot({ env, now: () => NOW, slot: "2026-09-28T01:30:00.000Z", resolveBackground: fakeResolveBackground() });
  const firstHash = /object:\/\/sha256\/([0-9a-f]{64})/.exec(first.selected.packRef)[1];

  writeDistributionLedger(dataDir, [
    { effect_key: "k1", job_id: "j1", receipt: { kind: "marketing_native_carousel_distribution", status: "published", pack_sha256: firstHash, published_at: NOW } },
  ]);

  const second = await resolveLarryJaSlot({ env, now: () => "2026-09-28T07:30:00.000Z", slot: "2026-09-28T07:30:00.000Z", resolveBackground: fakeResolveBackground() });
  assert.notEqual(second.selected.packRef, first.selected.packRef);

  // Same slot retried immediately (idempotency-per-slot support): with the
  // pool/history unchanged, resolution is deterministic.
  const retry = await resolveLarryJaSlot({ env, now: () => "2026-09-28T07:30:00.000Z", slot: "2026-09-28T07:30:00.000Z", resolveBackground: fakeResolveBackground() });
  assert.equal(retry.selected.packRef, second.selected.packRef);
});

test("resolveLarryJaSlot skips content rotation when this integration already published the exact due slot", async (t) => {
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const slot = "2026-09-28T01:00:00.000Z";
  const slotHash = crypto.createHash("sha256").update(slot).digest("hex");
  writeDistributionLedger(dataDir, [{
    effect_key: `marketing:carousel:anicca-ios:creative:${"a".repeat(64)}:${"b".repeat(64)}:${"c".repeat(64)}:${slotHash}`,
    job_id: "published-slot-job",
    receipt: {
      kind: "marketing_native_carousel_distribution",
      status: "published",
      integration_ref: EN_AFFIRMATION_LANE.integrationRef,
      pack_sha256: "a".repeat(64),
      published_at: NOW,
      provider_post_id: "postiz-slot-publication-1",
      provider_reconciled: true,
    },
  }]);
  let generations = 0;
  const result = await resolveLarryJaSlot({
    env,
    now: () => "2026-09-28T01:05:00.000Z",
    slot,
    lane: EN_AFFIRMATION_LANE,
    productionSlots: ["10:00", "15:00", "20:00"],
    generateCandidates: async () => {
      generations += 1;
      return [{ packRef: `object://sha256/${"d".repeat(64)}`, familyId: "fresh" }];
    },
  });

  assert.deepEqual(result, {
    slot,
    selected: null,
    alreadyPublished: true,
    providerPostId: "postiz-slot-publication-1",
  });
  assert.equal(generations, 0);
});

test("resolveLarryJaSlot rechecks the slot after generation finishes", async (t) => {
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const slot = "2026-09-28T00:00:00.000Z";
  const slotHash = crypto.createHash("sha256").update(slot).digest("hex");
  const generated = { packRef: `object://sha256/${"e".repeat(64)}`, familyId: "fresh" };
  const result = await resolveLarryJaSlot({
    env,
    now: () => "2026-09-28T00:05:00.000Z", // 09:05 JST, inside the 09:00 slot window.
    slot,
    lane: EN_SLIDESHOW_TIKTOK_LANE,
    productionSlots: ["09:00", "15:00", "21:00"],
    generateCandidates: async () => {
      writeDistributionLedger(dataDir, [{
        effect_key: `marketing:carousel:anicca-ios:creative:${"a".repeat(64)}:${"b".repeat(64)}:${"c".repeat(64)}:${slotHash}`,
        job_id: "concurrent-publisher-slot-job",
        receipt: {
          kind: "marketing_native_carousel_distribution",
          status: "published",
          integration_ref: EN_SLIDESHOW_TIKTOK_LANE.integrationRef,
          pack_sha256: "a".repeat(64),
          published_at: NOW,
          provider_post_id: "postiz-concurrent-slot-1",
          provider_reconciled: true,
        },
      }]);
      return [generated];
    },
  });

  assert.deepEqual(result, {
    slot,
    selected: null,
    alreadyPublished: true,
    providerPostId: "postiz-concurrent-slot-1",
  });
});

test("standalone slide-pack CLI exits safely instead of exporting a pack for an already-published slot", (t) => {
  const dataDir = tempDataDir(t);
  const slot = "2026-09-28T01:30:00.000Z";
  const slotHash = "604a92d13641f0953e91b185a3b3a72c2c8dad510877a892a99b6b09b03d3611";
  writeDistributionLedger(dataDir, [{
    effect_key: `marketing:carousel:anicca-ios:creative:${"a".repeat(64)}:${"b".repeat(64)}:${"c".repeat(64)}:${slotHash}`,
    job_id: "published-cli-slot-job",
    receipt: {
      kind: "marketing_native_carousel_distribution",
      status: "published",
      integration_ref: JA_LANE.integrationRef,
      pack_sha256: "a".repeat(64),
      published_at: NOW,
      provider_reconciled: true,
    },
  }]);
  const script = path.join(__dirname, "generate-larry-slide-pack.js");
  const result = spawnSync(process.execPath, [script, slot], {
    cwd: path.resolve(__dirname, "../../.."),
    env: { ...process.env, LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT },
    encoding: "utf8",
  });

  assert.equal(result.status, 75, result.stderr);
  assert.match(result.stderr, /already published/i);
  assert.equal(result.stdout, "");
});

test("readPostedHistory maps carousel distribution receipts to packRef/postedAt", (t) => {
  const dataDir = tempDataDir(t);
  const hash = crypto.createHash("sha256").update("x").digest("hex");
  const file = path.join(dataDir, "ledger.jsonl");
  const slotHash = "604a92d13641f0953e91b185a3b3a72c2c8dad510877a892a99b6b09b03d3611";
  const integrationRef = "integration://postiz/instagram/cmq3sq7mc000eqp0y7azfm8yk";
  fs.writeFileSync(file, `${JSON.stringify({
    effect_key: `marketing:carousel:anicca-ios:creative:${hash}:${"b".repeat(64)}:${"c".repeat(64)}:${slotHash}`,
      receipt: { kind: "marketing_native_carousel_distribution", status: "published", integration_ref: integrationRef, pack_sha256: hash, published_at: NOW, provider_post_id: "postiz-history-1", provider_reconciled: true },
  })}\n`);
  const history = readPostedHistory(file);
  assert.deepEqual(history, [{
    packRef: `object://sha256/${hash}`,
    postedAt: NOW,
    integrationRef,
    slotHash,
    providerPostId: "postiz-history-1",
  }]);
});

test("MIN_DAYS_BETWEEN_REPEAT is at least a week (per spec: never repeat within N days)", () => {
  assert.ok(MIN_DAYS_BETWEEN_REPEAT >= 7);
});

// Root-cause regression coverage: resolveLarryJaSlot must work for any lane,
// not just JA_LANE -- that parameterization (not a second implementation) is
// what lets anicca-larry-ja-rotating.js stop TikTok "Affirmation Girl" /
// "anicca" / "アニッチャ iOS" / "アニッチャ お笑い" / Instagram "anicca" from
// reposting the same fixed pack.
test("resolveLarryJaSlot generates a fresh, English, TikTok-shaped pool for a non-default lane in its own pool file", { timeout: 60_000 }, async (t) => {
  makeFixtureBackgroundOnce();
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const { slot, selected } = await resolveLarryJaSlot({
    env, now: () => "2026-09-28T00:05:00.000Z", slot: "2026-09-28T00:00:00.000Z",
    lane: EN_SLIDESHOW_TIKTOK_LANE,
    productionSlots: EN_SLIDESHOW_PRODUCTION_SLOTS,
    resolveBackground: fakeResolveBackground(),
  });
  assert.equal(slot, "2026-09-28T00:00:00.000Z");
  assert.match(selected.packRef, /^object:\/\/sha256\/[0-9a-f]{64}$/);

  const jaPool = poolPath(dataDir, TENANT, JA_LANE.productId, JA_LANE.lane);
  const enPool = poolPath(dataDir, TENANT, EN_SLIDESHOW_TIKTOK_LANE.productId, EN_SLIDESHOW_TIKTOK_LANE.lane);
  assert.notEqual(jaPool, enPool);
  assert.ok(fs.existsSync(enPool));
  assert.equal(fs.existsSync(jaPool), false, "must not touch the JA lane's own pool");

  const pack = JSON.parse(fs.readFileSync(
    path.join(dataDir, "objects", "sha256", selected.packRef.slice(-64)),
    "utf8",
  ));
  assert.equal(pack.platform, "tiktok");
  assert.equal(pack.locale, "en");
  // EN_SLIDESHOW_TIKTOK_LANE has no lastSlideRole override, so the factory's
  // own platform-aware default (tiktok -> "cta") must apply -- this is the
  // exact role the adapter's assertPack expects for this lane at publish time.
  assert.equal(pack.slides.at(-1).role, "cta");
});

test("resolveLarryJaSlot renders slides with the managed LIFE_MANAGER_PYTHON, not PATH python3", { timeout: 60_000 }, async (t) => {
  makeFixtureBackgroundOnce();
  const dataDir = tempDataDir(t);
  const calls = path.join(dataDir, "python-calls.txt");
  const shim = path.join(dataDir, "managed-python");
  // Records every argv then defers to the real interpreter so rendering still succeeds.
  fs.writeFileSync(shim, `#!/bin/sh\nprintf '%s\\n' "$*" >> "${calls}"\nexec python3 "$@"\n`, { mode: 0o700 });
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT, LIFE_MANAGER_PYTHON: shim };
  const { selected } = await resolveLarryJaSlot({ env, now: () => NOW, slot: "2026-09-28T01:30:00.000Z", resolveBackground: fakeResolveBackground() });
  assert.ok(selected);
  // Slide text carries a newline, so one argv record spans two lines; the shim
  // being the interpreter that rendered is what matters.
  const invoked = fs.readFileSync(calls, "utf8");
  assert.match(invoked, /render-slide-image\.py/);
});

test("an exhausted pool replenishes once and never selects a recently published pack", async (t) => {
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const candidates = Array.from({ length: 5 }, (_, n) => ({
    packRef: `object://sha256/${String(n).repeat(64)}`, familyId: "fixture", createdAt: NOW,
  }));
  const pool = poolPath(dataDir, TENANT, JA_LANE.productId, JA_LANE.lane);
  fs.mkdirSync(path.dirname(pool), { recursive: true });
  fs.writeFileSync(pool, candidates.map(c => JSON.stringify(c)).join("\n") + "\n");
  writeDistributionLedger(dataDir, candidates.map(c => ({ receipt: {
    pack_sha256: c.packRef.split("/").at(-1), published_at: NOW,
  } })));
  let generated = 0;
  const fresh = { ...candidates[0], packRef: `object://sha256/${"f".repeat(64)}` };
  const options = { env, now: () => NOW,
    generateCandidates: async () => { generated += 1; return [candidates[0], fresh]; } };
  const first = await resolveLarryJaSlot(options);
  assert.equal(first.selected.packRef, fresh.packRef);
  assert.equal(generated, 1);
  assert.equal(fs.readFileSync(pool, "utf8").trim().split("\n").length, 6);
  const retry = await resolveLarryJaSlot(options);
  assert.equal(retry.selected.packRef, fresh.packRef);
  assert.equal(generated, 1, "retry with usable inventory must not incur another generation");
});

test("an exhausted pool stays failed when generation yields no fresh approved candidates", async (t) => {
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const candidates = Array.from({ length: 4 }, (_, n) => ({
    packRef: `object://sha256/${String(n).repeat(64)}`, familyId: "fixture", createdAt: NOW,
  }));
  const pool = poolPath(dataDir, TENANT, JA_LANE.productId, JA_LANE.lane);
  fs.mkdirSync(path.dirname(pool), { recursive: true });
  fs.writeFileSync(pool, candidates.map(c => JSON.stringify(c)).join("\n") + "\n");
  writeDistributionLedger(dataDir, candidates.map(c => ({ receipt: {
    pack_sha256: c.packRef.split("/").at(-1), published_at: NOW,
  } })));
  const before = fs.readFileSync(pool, "utf8");
  let generated = 0;
  await assert.rejects(resolveLarryJaSlot({ env, now: () => NOW,
    generateCandidates: async () => { generated += 1; return candidates; },
  }), /no unposted candidate/);
  assert.equal(generated, 1, "exhausted inventory must attempt the existing factory once");
  assert.equal(fs.readFileSync(pool, "utf8"), before);
});

test("selection rereads publication history after the factory finishes", async (t) => {
  const dataDir = tempDataDir(t);
  const old = { packRef: `object://sha256/${"a".repeat(64)}`, familyId: "fixture", createdAt: "2026-09-27T00:00:00.000Z" };
  const fresh = { ...old, packRef: `object://sha256/${"f".repeat(64)}`, createdAt: NOW };
  const pool = poolPath(dataDir, TENANT, JA_LANE.productId, JA_LANE.lane);
  fs.mkdirSync(path.dirname(pool), { recursive: true });
  fs.writeFileSync(pool, JSON.stringify(old) + "\n");
  const result = await resolveLarryJaSlot({
    env: { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT }, now: () => NOW,
    generateCandidates: async () => {
      writeDistributionLedger(dataDir, [{ receipt: { pack_sha256: "a".repeat(64), published_at: NOW } }]);
      return [fresh];
    },
  });
  assert.equal(result.selected.packRef, fresh.packRef);
});

test("resolveLarryJaSlot skips existing packs whose caption or slide text repeats on the same account", async (t) => {
  const dataDir = tempDataDir(t);
  const objectDir = path.join(dataDir, "objects");
  function importObject(name, content) {
    const source = path.join(dataDir, name);
    fs.writeFileSync(source, content);
    return importContentObject(source, { objectDir }).ref;
  }
  function slides(prefix) {
    return Array.from({ length: 6 }, (_, index) => `${prefix}-${index + 1}`);
  }
  const repeatedCaption = "same caption copy";
  const repeatedText = slides("same slide copy");
  const uniqueTexts = slides("unique approved text");
  const repeatedCaptionRef = importObject("recent-caption.txt", repeatedCaption);
  const repeatedTextPackRef = importObject("recent-text-pack.json", JSON.stringify({
    slides: repeatedText.map((text) => ({ text })),
  }));
  const candidates = [
    {
      packRef: importObject("duplicate-caption-pack.json", JSON.stringify({ slides: slides("caption-duplicate").map((text) => ({ text })) })),
      captionRef: repeatedCaptionRef,
      familyId: "caption-duplicate",
      createdAt: "2026-09-01T00:00:00.000Z",
    },
    {
      packRef: repeatedTextPackRef,
      captionRef: importObject("text-duplicate-caption.txt", "different caption copy"),
      familyId: "text-duplicate",
      createdAt: "2026-09-02T00:00:00.000Z",
    },
    {
      packRef: importObject("double-duplicate-pack.json", JSON.stringify({
        slides: repeatedText.map((text) => ({ text })),
      })),
      captionRef: repeatedCaptionRef,
      familyId: "double-duplicate",
      createdAt: "2026-09-03T00:00:00.000Z",
    },
    {
      packRef: importObject("unique-pack.json", JSON.stringify({ slides: uniqueTexts.map((text) => ({ text })) })),
      captionRef: importObject("unique-caption.txt", "unique caption copy"),
      familyId: "unique",
      createdAt: "2026-09-04T00:00:00.000Z",
    },
  ];
  const pool = poolPath(dataDir, TENANT, JA_BUDDHA_TIKTOK_LANE.productId, JA_BUDDHA_TIKTOK_LANE.lane);
  fs.mkdirSync(path.dirname(pool), { recursive: true });
  fs.writeFileSync(pool, candidates.map((candidate) => JSON.stringify(candidate)).join("\n") + "\n");
  const repeatedTextHash = crypto.createHash("sha256").update(JSON.stringify(repeatedText)).digest("hex");
  const uniqueTextHash = crypto.createHash("sha256").update(JSON.stringify(uniqueTexts)).digest("hex");
  writeDistributionLedger(dataDir, [
    { receipt: {
      integration_ref: JA_BUDDHA_TIKTOK_LANE.integrationRef,
      pack_sha256: "a".repeat(64),
      caption_sha256: repeatedCaptionRef.slice(-64),
      text_sha256: "b".repeat(64),
      published_at: "2026-10-07T07:00:00.000Z",
    } },
    { receipt: {
      integration_ref: JA_BUDDHA_TIKTOK_LANE.integrationRef,
      pack_sha256: "c".repeat(64),
      caption_sha256: "d".repeat(64),
      text_sha256: repeatedTextHash,
      published_at: "2026-10-07T08:00:00.000Z",
    } },
    { receipt: {
      integration_ref: "integration://postiz/tiktok/other-account",
      pack_sha256: "e".repeat(64),
      caption_sha256: candidates[3].captionRef.slice(-64),
      text_sha256: uniqueTextHash,
      published_at: "2026-10-07T09:00:00.000Z",
    } },
  ]);
  let generationCalls = 0;
  const result = await resolveLarryJaSlot({
    env: { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT },
    now: () => "2026-10-08T04:05:00.000Z", // 13:05 JST, inside the 13:00 slot window.
    slot: "2026-10-08T04:00:00.000Z",
    lane: JA_BUDDHA_TIKTOK_LANE,
    productionSlots: ["07:00", "13:00", "20:00"],
    generateCandidates: async () => { generationCalls += 1; return []; },
  });

  assert.equal(result.selected.packRef, candidates[3].packRef);
  assert.equal(generationCalls, 0, "an existing approved unique text variant should avoid new material generation");
});
