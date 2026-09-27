"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const { createContentObjectStore } = require("./content-object-store.js");
const { JA_LANE } = require("./marketing-native-carousel-publication-adapter.js");
const { SLIDE_COUNT } = require("./marketing-slide-pack-gate.js");
const { generateSlidePackCandidates, FAMILIES, MAX_PACK_COST_USD } = require("./marketing-slide-pack-factory.js");

function tempDir(prefix) {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

function candidateCount() {
  return Object.values(FAMILIES).reduce((sum, topics) => sum + topics.length, 0);
}

// A real (non-flat) photo-like fixture so the renderer's genuine contrast
// check (computed on real pixels, not mocked) has real background variance
// to test against -- only the network-calling Gemini fetch is mocked, never
// the compositor/gate math itself.
function makeFixtureBackground() {
  const file = path.join(os.tmpdir(), `slide-pack-fixture-bg-${process.pid}.png`);
  if (fs.existsSync(file)) return file;
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
  return file;
}

test("generateSlidePackCandidates produces approved packs matching the adapter's pack/approval contract", { timeout: 60_000 }, async () => {
  const objectDir = tempDir("slide-pack-objects-");
  const workspaceDir = tempDir("slide-pack-workspace-");
  const imageCacheDir = tempDir("slide-pack-image-cache-");
  const objectStore = createContentObjectStore({ objectDir });
  const now = () => "2026-09-28T09:00:00.000Z";
  const fixtureBackground = makeFixtureBackground();
  let backgroundCalls = 0;

  const rejected = [];
  const candidates = await generateSlidePackCandidates({
    objectStore,
    workspaceDir,
    imageCacheDir,
    tenantId: "dais-local",
    productId: JA_LANE.productId,
    locale: JA_LANE.locale,
    platform: JA_LANE.platform,
    accountId: JA_LANE.accountId,
    integrationRef: JA_LANE.integrationRef,
    rendererId: JA_LANE.renderer,
    packFormat: JA_LANE.packFormat,
    form: JA_LANE.form,
    now,
    resolveBackground: async () => { backgroundCalls += 1; return { file: fixtureBackground, costUsd: 0.039, cached: false }; },
    onRejected: (info) => rejected.push(info),
  });

  assert.deepEqual(rejected, []);
  assert.equal(candidates.length, candidateCount());

  const familyIds = new Set(candidates.map((c) => c.familyId));
  assert.equal(familyIds.size, Object.keys(FAMILIES).length);

  const seenPackRefs = new Set();
  for (const candidate of candidates) {
    assert.match(candidate.packRef, /^object:\/\/sha256\/[0-9a-f]{64}$/);
    assert.equal(candidate.mediaRefs.length, SLIDE_COUNT);
    assert.equal(seenPackRefs.has(candidate.packRef), false, "packRef must be unique per candidate");
    seenPackRefs.add(candidate.packRef);

    const pack = JSON.parse(fs.readFileSync(objectStore.resolve(candidate.packRef), "utf8"));
    assert.equal(pack.schema_version, 1);
    assert.equal(pack.kind, "marketing_native_carousel_pack");
    assert.equal(pack.product_id, JA_LANE.productId);
    assert.equal(pack.locale, JA_LANE.locale);
    assert.equal(pack.platform, JA_LANE.platform);
    assert.equal(pack.account_id, JA_LANE.accountId);
    assert.equal(pack.renderer_id, JA_LANE.renderer);
    assert.equal(pack.format_id, JA_LANE.packFormat);
    assert.equal(pack.form, JA_LANE.form);
    assert.equal(pack.media_type, "image/jpeg");
    assert.equal(pack.slide_count, SLIDE_COUNT);
    assert.equal(pack.slides.length, SLIDE_COUNT);
    pack.slides.forEach((slide, index) => {
      assert.equal(slide.position, index + 1);
      assert.equal(slide.role, index === 0 ? "hook" : "body");
      assert.ok(slide.text.trim().length > 0);
      assert.equal(slide.media_ref, candidate.mediaRefs[index]);
    });

    const caption = fs.readFileSync(objectStore.resolve(candidate.captionRef), "utf8");
    assert.equal(pack.caption, caption);
    assert.match(caption, /apps\.apple\.com|プロフィールのリンク/);

    for (const mediaRef of candidate.mediaRefs) {
      const file = objectStore.resolve(mediaRef);
      const bytes = fs.readFileSync(file);
      assert.equal(bytes[0], 0xff);
      assert.equal(bytes[1], 0xd8);
    }

    const approval = JSON.parse(fs.readFileSync(objectStore.resolve(candidate.approvalRef), "utf8"));
    assert.equal(approval.schema_version, 1);
    assert.equal(approval.kind, "marketing_native_carousel_publication_approval");
    assert.equal(approval.status, "approved");
    assert.equal(approval.approved_by, "automated-slide-pack-gate");
    assert.ok(approval.gate_score >= 60);
    assert.equal(approval.tenant_id, "dais-local");
    assert.equal(approval.product_id, JA_LANE.productId);
    assert.equal(approval.locale, JA_LANE.locale);
    assert.equal(approval.platform, JA_LANE.platform);
    assert.equal(approval.account_id, JA_LANE.accountId);
    assert.equal(approval.integration_ref, JA_LANE.integrationRef);
    assert.equal(approval.pack_ref, candidate.packRef);
    assert.deepEqual(approval.media_refs, candidate.mediaRefs);
    const crypto = require("node:crypto");
    assert.equal(approval.caption_sha256, crypto.createHash("sha256").update(caption).digest("hex"));
    assert.ok(approval.generation_cost_usd > 0);
    assert.ok(approval.generation_cost_usd <= MAX_PACK_COST_USD);
  }

  assert.equal(backgroundCalls, candidates.length * SLIDE_COUNT);
});

test("generateSlidePackCandidates makes the last slide an app CTA screen with the JA link-in-bio line", { timeout: 60_000 }, async () => {
  const objectDir = tempDir("slide-pack-objects-cta-");
  const workspaceDir = tempDir("slide-pack-workspace-cta-");
  const imageCacheDir = tempDir("slide-pack-image-cache-cta-");
  const objectStore = createContentObjectStore({ objectDir });
  const fixtureBackground = makeFixtureBackground();

  const [candidate] = await generateSlidePackCandidates({
    objectStore,
    workspaceDir,
    imageCacheDir,
    tenantId: "dais-local",
    productId: JA_LANE.productId,
    locale: JA_LANE.locale,
    platform: JA_LANE.platform,
    accountId: JA_LANE.accountId,
    integrationRef: JA_LANE.integrationRef,
    rendererId: JA_LANE.renderer,
    packFormat: JA_LANE.packFormat,
    form: JA_LANE.form,
    now: () => "2026-09-28T09:00:00.000Z",
    resolveBackground: async () => ({ file: fixtureBackground, costUsd: 0.039, cached: false }),
  });

  const pack = JSON.parse(fs.readFileSync(objectStore.resolve(candidate.packRef), "utf8"));
  const lastSlide = pack.slides[SLIDE_COUNT - 1];
  assert.match(lastSlide.text, /Anicca/);
  assert.match(lastSlide.text, /プロフィールのリンクから/);
});

test("generateSlidePackCandidates rejects (not posts) a candidate whose image generation exceeds the cost cap", { timeout: 60_000 }, async () => {
  const objectDir = tempDir("slide-pack-objects-cap-");
  const workspaceDir = tempDir("slide-pack-workspace-cap-");
  const imageCacheDir = tempDir("slide-pack-image-cache-cap-");
  const objectStore = createContentObjectStore({ objectDir });
  const fixtureBackground = makeFixtureBackground();
  const rejected = [];

  const candidates = await generateSlidePackCandidates({
    objectStore,
    workspaceDir,
    imageCacheDir,
    tenantId: "dais-local",
    productId: JA_LANE.productId,
    locale: JA_LANE.locale,
    platform: JA_LANE.platform,
    accountId: JA_LANE.accountId,
    integrationRef: JA_LANE.integrationRef,
    rendererId: JA_LANE.renderer,
    packFormat: JA_LANE.packFormat,
    form: JA_LANE.form,
    now: () => "2026-09-28T09:00:00.000Z",
    resolveBackground: async () => ({ file: fixtureBackground, costUsd: 1, cached: false }),
    onRejected: (info) => rejected.push(info),
  });

  assert.equal(candidates.length, 0);
  assert.equal(rejected.length, candidateCount());
  for (const info of rejected) {
    assert.ok(info.reasons.some((r) => r.includes("cost cap")));
  }
});
