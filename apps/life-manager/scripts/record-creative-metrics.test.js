"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { engagementScore, recordCreativeMetrics } = require("./record-creative-metrics.js");
const { readCreativeMetrics } = require("../lib/marketing-creative-metrics.js");

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "lm-record-creative-metrics-"));
}

function writeReceiptLedger(dataDir, rows) {
  const file = path.join(dataDir, "marketing", "receipts.jsonl");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`);
}

function generationRow({ jobId, hookId, creativeId, productId = "honne-ai", formatId = "reelclaw", locale = "ja" }) {
  return {
    schema_version: 1,
    kind: "marketing_video_artifact",
    tenant_id: "dais-local",
    job_id: jobId,
    attempt: 1,
    receipt: {
      product_id: productId,
      format_id: formatId,
      locale,
      hook_id: hookId,
      creative_id: creativeId,
      status: "ready",
    },
  };
}

function publicationRow({ jobId, creativeId, providerPostId, productId = "honne-ai", formatId = "reelclaw", locale = "ja", platform, publicUrl, providerReconciled }) {
  const receipt = {
    product_id: productId,
    format_id: formatId,
    locale,
    status: "published",
    creative_id: creativeId,
    provider_post_id: providerPostId,
  };
  if (platform !== undefined) receipt.platform = platform;
  if (publicUrl !== undefined) receipt.public_url = publicUrl;
  if (providerReconciled !== undefined) receipt.provider_reconciled = providerReconciled;
  return {
    schema_version: 1,
    kind: "marketing_video_distribution",
    tenant_id: "dais-local",
    job_id: jobId,
    attempt: 1,
    receipt,
  };
}

function write24hMetricSnapshot(dataDir, { owner, postId, providerPostId, platform, accountId, publicUrl, post }) {
  const directory = path.join(dataDir, "tenants/dais-local/marketing/metrics", owner, postId);
  fs.mkdirSync(directory, { recursive: true });
  const kind = platform === "tiktok" ? "tiktok_combined_metric_snapshot" : "instagram_combined_metric_snapshot";
  fs.writeFileSync(path.join(directory, "24h.combined.json"), JSON.stringify({
    schema_version: 1, tenant_id: "dais-local", kind, product_id: "anicca-ios", locale: "en", account_id: accountId,
    provider_post_id: providerPostId, public_url: publicUrl, window: "24h",
    observed_at: "2026-10-12T12:00:00.000Z", post,
  }), { mode: 0o600 });
}

test("engagementScore uses Postiz string totals and ignores percentageChange", () => {
  const postizRows = [
    { label: "Views", percentageChange: 250, data: [{ total: "100", date: "2026-10-11" }] },
    { label: "Likes", percentageChange: 900, data: [{ total: "12", date: "2026-10-11" }] },
    { label: "Comments", percentageChange: 25, data: [{ total: "2", date: "2026-10-11" }] },
    { label: "Shares", percentageChange: 0, data: [{ total: "1", date: "2026-10-11" }] },
  ];
  assert.equal(engagementScore(postizRows), 115);
  assert.equal(engagementScore({ views: 100, engagement: { likes: 10, comments: 2 }, tags: ["a"] }), 112);
  assert.equal(engagementScore([{ plays: 5 }, { shares: 3 }]), 8);
  assert.equal(engagementScore(null), null);
  assert.equal(engagementScore([]), null);
});

test("recordCreativeMetrics joins generation -> publication via creative_id prefix and records one row per post", async () => {
  const dataDir = tmpDir();
  writeReceiptLedger(dataDir, [
    generationRow({ jobId: "g1", hookId: "HJA-001", creativeId: "HJA-001-aaaaaaaaaaaa" }),
    publicationRow({ jobId: "p1", creativeId: "HJA-001-aaaaaaaaaaaa-20260927T123000000Z", providerPostId: "post-1" }),
  ]);
  const analyticsCalls = [];
  const result = await recordCreativeMetrics({
    dataDir,
    tenantId: "dais-local",
    productId: "honne-ai",
    formatId: "reelclaw",
    locale: "ja",
    fetchAnalytics: async (providerPostId) => { analyticsCalls.push(providerPostId); return { views: 50, likes: 5 }; },
    now: () => "2026-09-27T00:00:00.000Z",
  });
  assert.deepEqual(analyticsCalls, ["post-1"]);
  assert.equal(result.recorded.length, 1);
  assert.equal(result.recorded[0].hook_id, "HJA-001");
  assert.equal(result.recorded[0].score, 55);
  assert.equal(readCreativeMetrics(dataDir).length, 1);
});

test("creative reporting joins exact native snapshots by provider post and keeps arm metrics separate", async () => {
  const dataDir = tmpDir();
  const base = "AN-EN-001-aaaaaaaaaaaa";
  const tiktokUrl = "https://www.tiktok.com/@aniccaaffirmation/video/1234567890";
  const instagramUrl = "https://www.instagram.com/reel/ABC123/";
  writeReceiptLedger(dataDir, [
    generationRow({ jobId: "g1", hookId: "AN-EN-001", creativeId: base, productId: "anicca-ios", formatId: "larry", locale: "en" }),
    publicationRow({ jobId: "p1", creativeId: `${base}-20261012T091500000Z`, providerPostId: "post-tiktok", productId: "anicca-ios", formatId: "larry", locale: "en", platform: "tiktok", publicUrl: tiktokUrl, providerReconciled: true }),
    publicationRow({ jobId: "p2", creativeId: `${base}-20261012T100000000Z`, providerPostId: "post-instagram", productId: "anicca-ios", formatId: "larry", locale: "en", platform: "instagram", publicUrl: instagramUrl, providerReconciled: true }),
    publicationRow({ jobId: "p3", creativeId: `${base}-20261012T141500000Z`, providerPostId: "post-late", productId: "anicca-ios", formatId: "larry", locale: "en", platform: "tiktok", publicUrl: "https://www.tiktok.com/@aniccaaffirmation/video/1234567891", providerReconciled: true }),
  ]);
  write24hMetricSnapshot(dataDir, { owner: "aniccaaffirmation", postId: "1234567890", providerPostId: "post-tiktok", platform: "tiktok", accountId: "@aniccaaffirmation", publicUrl: tiktokUrl,
    post: { views: { status: "measured", value: 100 }, likes: { status: "measured", value: 5 }, comments: { status: "measured", value: 0 }, shares: { status: "measured", value: 1 }, saves: { status: "unavailable", value: null, reason: "provider_field_missing" } } });
  write24hMetricSnapshot(dataDir, { owner: "anicca.ios", postId: "ABC123", providerPostId: "post-instagram", platform: "instagram", accountId: "@anicca.affirmation", publicUrl: instagramUrl,
    post: { views: { status: "measured", value: 200 }, likes: { status: "measured", value: 10 }, comments: { status: "measured", value: 2 }, shares: { status: "unavailable", value: null, reason: "metric_not_supported" }, saves: { status: "measured", value: 4 } } });

  const result = await recordCreativeMetrics({
    dataDir, tenantId: "dais-local", productId: "anicca-ios", formatId: "larry", locale: "en",
    fetchAnalytics: async () => [{ label: "Views", data: [{ total: "50" }] }, { label: "Likes", data: [{ total: "5" }] }],
    now: () => "2026-10-12T14:30:00.000Z",
  });
  assert.equal(result.recorded.length, 3);
  assert.equal(result.recorded[0].score, 55);
  assert.equal(result.native_metric_joins.length, 3);
  const byPost = Object.fromEntries(result.native_metric_joins.map((row) => [row.provider_post_id, row]));
  assert.equal(byPost["post-tiktok"].creative_id, `${base}-20261012T091500000Z`);
  assert.equal(byPost["post-tiktok"].arm_id, "AN-EN-001");
  assert.equal(byPost["post-tiktok"].account_id, "@aniccaaffirmation");
  assert.equal(byPost["post-tiktok"].metrics.views.value, 100);
  assert.equal(byPost["post-tiktok"].metrics.comments.status, "measured"); assert.equal(byPost["post-tiktok"].metrics.comments.value, 0);
  assert.equal(byPost["post-tiktok"].metrics.saves.status, "unavailable"); assert.equal(byPost["post-tiktok"].metrics.saves.value, null); assert.equal(byPost["post-tiktok"].metrics.saves.reason, "provider_field_missing");
  assert.equal(byPost["post-instagram"].platform, "instagram");
  assert.equal(byPost["post-instagram"].account_id, "@anicca.affirmation");
  assert.equal(byPost["post-instagram"].metrics.views.value, 200);
  assert.equal(byPost["post-late"].status, "pending");
  assert.equal(byPost["post-late"].metrics.views.value, null);
  assert.equal(byPost["post-late"].metrics.views.reason, "native_metric_snapshot_missing");
  assert.equal(result.arm_comparisons.length, 2);
  const tiktokArm = result.arm_comparisons.find((row) => row.platform === "tiktok");
  const instagramArm = result.arm_comparisons.find((row) => row.platform === "instagram");
  assert.equal(tiktokArm.arm_id, "AN-EN-001");
  assert.equal(tiktokArm.locale, "en");
  assert.equal(tiktokArm.metrics.views.mean, 100);
  assert.equal(tiktokArm.metrics.views.pending_posts, 1);
  assert.equal(tiktokArm.metrics.comments.mean, 0);
  assert.equal(tiktokArm.metrics.saves.mean, null);
  assert.equal(instagramArm.metrics.views.mean, 200);
});

test("recordCreativeMetrics is idempotent per provider_post_id on rerun", async () => {
  const dataDir = tmpDir();
  writeReceiptLedger(dataDir, [
    generationRow({ jobId: "g1", hookId: "HJA-001", creativeId: "HJA-001-aaaaaaaaaaaa" }),
    publicationRow({ jobId: "p1", creativeId: "HJA-001-aaaaaaaaaaaa-20260927T123000000Z", providerPostId: "post-1" }),
  ]);
  let calls = 0;
  const fetchAnalytics = async () => { calls += 1; return { views: 50 }; };
  await recordCreativeMetrics({ dataDir, tenantId: "dais-local", productId: "honne-ai", formatId: "reelclaw", locale: "ja", fetchAnalytics, now: () => "2026-09-27T00:00:00.000Z" });
  const second = await recordCreativeMetrics({ dataDir, tenantId: "dais-local", productId: "honne-ai", formatId: "reelclaw", locale: "ja", fetchAnalytics, now: () => "2026-09-28T00:00:00.000Z" });
  assert.equal(calls, 1);
  assert.equal(second.recorded.length, 0);
  assert.equal(readCreativeMetrics(dataDir).length, 1);
});

test("recordCreativeMetrics skips a publication whose generation lineage cannot be found", async () => {
  const dataDir = tmpDir();
  writeReceiptLedger(dataDir, [
    publicationRow({ jobId: "p1", creativeId: "UNKNOWN-000000000000-20260927T123000000Z", providerPostId: "post-1" }),
  ]);
  const result = await recordCreativeMetrics({
    dataDir, tenantId: "dais-local", productId: "honne-ai", formatId: "reelclaw", locale: "ja",
    fetchAnalytics: async () => { throw new Error("must not be called"); },
    now: () => "2026-09-27T00:00:00.000Z",
  });
  assert.deepEqual(result.skipped, ["post-1"]);
  assert.equal(result.recorded.length, 0);
});

test("recordCreativeMetrics does not cross tenant/product/format/locale scope", async () => {
  const dataDir = tmpDir();
  writeReceiptLedger(dataDir, [
    generationRow({ jobId: "g1", hookId: "HJA-001", creativeId: "HJA-001-aaaaaaaaaaaa" }),
    { ...publicationRow({ jobId: "p1", creativeId: "HJA-001-aaaaaaaaaaaa-20260927T123000000Z", providerPostId: "post-1" }), receipt: { ...publicationRow({ jobId: "p1", creativeId: "HJA-001-aaaaaaaaaaaa-20260927T123000000Z", providerPostId: "post-1" }).receipt, locale: "en" } },
  ]);
  const result = await recordCreativeMetrics({
    dataDir, tenantId: "dais-local", productId: "honne-ai", formatId: "reelclaw", locale: "ja",
    fetchAnalytics: async () => { throw new Error("must not be called"); },
    now: () => "2026-09-27T00:00:00.000Z",
  });
  assert.equal(result.recorded.length, 0);
  assert.equal(result.skipped.length, 0);
});

test("recordCreativeMetrics leaves empty Postiz analytics pending instead of recording zero", async () => {
  const dataDir = tmpDir();
  writeReceiptLedger(dataDir, [
    generationRow({ jobId: "g1", hookId: "HJA-001", creativeId: "HJA-001-aaaaaaaaaaaa" }),
    publicationRow({ jobId: "p1", creativeId: "HJA-001-aaaaaaaaaaaa-20260927T123000000Z", providerPostId: "post-1" }),
  ]);
  const result = await recordCreativeMetrics({
    dataDir,
    tenantId: "dais-local",
    productId: "honne-ai",
    formatId: "reelclaw",
    locale: "ja",
    fetchAnalytics: async () => [],
    now: () => "2026-09-27T00:00:00.000Z",
  });
  assert.deepEqual(result.pending, ["post-1"]);
  assert.equal(result.recorded.length, 0);
  assert.equal(readCreativeMetrics(dataDir).length, 0);
});
