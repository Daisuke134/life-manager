"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { createContentObjectStore } = require("./content-object-store.js");
const { JA_LANE } = require("./marketing-native-carousel-publication-adapter.js");
const { SLIDE_COUNT } = require("./marketing-slide-pack-gate.js");
const { generateSlidePackCandidates, FAMILIES } = require("./marketing-slide-pack-factory.js");

function tempDir(prefix) {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

function candidateCount() {
  return Object.values(FAMILIES).reduce((sum, topics) => sum + topics.length, 0);
}

test("generateSlidePackCandidates produces approved packs matching the adapter's pack/approval contract", { timeout: 60_000 }, () => {
  const objectDir = tempDir("slide-pack-objects-");
  const workspaceDir = tempDir("slide-pack-workspace-");
  const objectStore = createContentObjectStore({ objectDir });
  const now = () => "2026-09-28T09:00:00.000Z";

  const rejected = [];
  const candidates = generateSlidePackCandidates({
    objectStore,
    workspaceDir,
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
  }
});
