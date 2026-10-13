"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { importContentObject } = require("../lib/content-object-store.js");
const { persistAscAcquisition } = require("./marketing-asc-acquisition.js");
const { buildLineage, persistLineage } = require("./marketing-attribution-lineage.js");

function fixtureDataDir() {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-attribution-fixture-"));
  fs.mkdirSync(path.join(dataDir, "marketing"), { recursive: true });
  fs.writeFileSync(path.join(dataDir, "marketing", "receipts.jsonl"), "");
  return dataDir;
}

function addMetricFixture(dataDir, { productId, appId, accountId, postId, token = null, receiptCopies = 1 }) {
  const captionFile = path.join(dataDir, `${postId}.caption.txt`);
  const videoFile = path.join(dataDir, `${postId}.video.mp4`);
  const campaignLine = token ? `\nhttps://apps.apple.com/app/id${appId}?ct=${token}&mt=8` : "";
  fs.writeFileSync(captionFile, `Hook for ${accountId}${campaignLine}\n`);
  fs.writeFileSync(videoFile, `video-${postId}`);
  const caption = importContentObject(captionFile, { objectDir: path.join(dataDir, "objects") });
  const video = importContentObject(videoFile, { objectDir: path.join(dataDir, "objects") });
  const publicUrl = `https://www.tiktok.com/${accountId}/video/${postId}`;
  const receipt = { kind: "marketing_video_distribution", status: "published", product_id: productId, locale: "en", platform: "tiktok", provider_post_id: postId, public_url: publicUrl, creative_id: `${productId}-${postId}`, slot: "2026-08-20T00:00:00.000Z", published_at: "2026-08-20T00:01:00.000Z", video_sha256: video.sha256, caption_sha256: caption.sha256 };
  for (let index = 0; index < receiptCopies; index += 1) fs.appendFileSync(path.join(dataDir, "marketing", "receipts.jsonl"), `${JSON.stringify({ receipt })}\n`);
  const metricDir = path.join(dataDir, "tenants", "dais-local", "marketing", "metrics", accountId, postId);
  fs.mkdirSync(metricDir, { recursive: true });
  fs.writeFileSync(path.join(metricDir, "24h.combined.json"), JSON.stringify({ schema_version: 1, kind: "tiktok_combined_metric_snapshot", product_id: productId, locale: "en", account_id: accountId, integration_id: "integration-1", provider_post_id: postId, public_url: publicUrl, window: "24h", observed_at: "2026-08-21T00:01:00.000Z" }));
  return accountId;
}

test("exact publication lineage stays unattributed when campaign is unavailable and replays", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-attribution-"));
  const objectDir = path.join(dataDir, "objects");
  const captionFile = path.join(dataDir, "caption.txt");
  const videoFile = path.join(dataDir, "video.mp4");
  fs.writeFileSync(captionFile, "Exact hook\nBody\n");
  fs.writeFileSync(videoFile, "video");
  const caption = importContentObject(captionFile, { objectDir });
  const video = importContentObject(videoFile, { objectDir });
  const url = "https://www.tiktok.com/@account/video/123";
  const receiptDir = path.join(dataDir, "marketing");
  fs.mkdirSync(receiptDir, { recursive: true });
  fs.writeFileSync(path.join(receiptDir, "receipts.jsonl"), `${JSON.stringify({
    job_id: `marketing-video-publication:${"a".repeat(64)}`,
    receipt: { kind: "marketing_video_distribution", status: "published", product_id: "honne-ai", locale: "en", platform: "tiktok", provider_post_id: "post-1", public_url: url, creative_id: "HEN-1", slot: "2026-08-20T00:00:00.000Z", published_at: "2026-08-20T00:01:00.000Z", video_sha256: video.sha256, caption_sha256: caption.sha256 },
  })}\n`);
  const metricDir = path.join(dataDir, "tenants", "dais-local", "marketing", "metrics", "account", "123");
  fs.mkdirSync(metricDir, { recursive: true });
  fs.writeFileSync(path.join(metricDir, "24h.combined.json"), JSON.stringify({ schema_version: 1, kind: "tiktok_combined_metric_snapshot", product_id: "honne-ai", locale: "en", account_id: "@account", integration_id: "integration-1", provider_post_id: "post-1", public_url: url, window: "24h", observed_at: "2026-08-21T00:01:00.000Z" }));

  const first = persistLineage({ dataDir });
  const second = persistLineage({ dataDir });
  assert.equal(first.created, true);
  assert.equal(second.created, false);
  assert.equal(first.snapshot_ref, second.snapshot_ref);
  assert.deepEqual(first.coverage, { included: 1, exact_publication_lineage: 1, campaign_attributed: 0, unattributed: 1, unprovable: 0, attribution_rate: null, attribution_rate_status: "unavailable", attribution_rate_reason: "campaign_not_configured" });
  assert.equal(first.rows[0].hook_text, "Exact hook");
  assert.equal(first.rows[0].hook_sha256, crypto.createHash("sha256").update("Exact hook").digest("hex"));
  assert.equal(first.rows[0].campaign_id, null);
  assert.equal(first.rows[0].attribution_status, "unattributed");
});

test("lineage reads an Apple campaign token from the exact caption object", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-attribution-campaign-")); const objectDir = path.join(dataDir, "objects"); const captionFile = path.join(dataDir, "caption.txt"); const videoFile = path.join(dataDir, "video.mp4"); fs.writeFileSync(captionFile, "Exact hook\n\nhttps://apps.apple.com/app/id6759667221?pt=93486075&ct=honne_en_base_20260823&mt=8\n"); fs.writeFileSync(videoFile, "video"); const caption = importContentObject(captionFile, { objectDir }); const video = importContentObject(videoFile, { objectDir }); const url = "https://www.tiktok.com/@honne_reveal/video/123";
  const receiptDir = path.join(dataDir, "marketing"); fs.mkdirSync(receiptDir, { recursive: true }); fs.writeFileSync(path.join(receiptDir, "receipts.jsonl"), `${JSON.stringify({ receipt: { kind: "marketing_video_distribution", status: "published", product_id: "honne-ai", locale: "en", platform: "tiktok", provider_post_id: "post-1", public_url: url, creative_id: "HEN-1", slot: "2026-08-20T00:00:00.000Z", published_at: "2026-08-20T00:01:00.000Z", video_sha256: video.sha256, caption_sha256: caption.sha256 } })}\n`); const metricDir = path.join(dataDir, "tenants/dais-local/marketing/metrics/honne_reveal/123"); fs.mkdirSync(metricDir, { recursive: true }); fs.writeFileSync(path.join(metricDir, "24h.combined.json"), JSON.stringify({ kind: "tiktok_combined_metric_snapshot", product_id: "honne-ai", locale: "en", account_id: "@honne_reveal", integration_id: "integration-1", provider_post_id: "post-1", public_url: url, window: "24h", observed_at: "2026-08-21T00:01:00.000Z" }));
  const result = persistLineage({ dataDir }); assert.equal(result.rows[0].campaign_id, "honne_en_base_20260823"); assert.equal(result.rows[0].campaign_status, "configured"); assert.equal(result.rows[0].attribution_status, "partial");
});

test("campaign CT is accepted only for its matching mobile product", (t) => {
  const dataDir = fixtureDataDir();
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  addMetricFixture(dataDir, { productId: "anicca-ios", appId: "6755129214", accountId: "@anicca_good", postId: "anicca-good", token: "anicca-ios_youtube_en" });
  addMetricFixture(dataDir, { productId: "anicca-ios", appId: "6755129214", accountId: "@anicca_wrong", postId: "anicca-wrong", token: "honne_en_base_20260823" });
  addMetricFixture(dataDir, { productId: "honne-ai", appId: "6759667221", accountId: "@honne_wrong", postId: "honne-wrong", token: "anicca-ios_youtube_en" });
  addMetricFixture(dataDir, { productId: "anicca-ios", appId: "6759667221", accountId: "@anicca_wrong_app", postId: "anicca-wrong-app", token: "anicca-ios_youtube_en" });

  const rows = buildLineage({ dataDir }).rows;
  const byAccount = Object.fromEntries(rows.map((row) => [row.account_id, row]));
  assert.equal(byAccount["@anicca_good"].campaign_id, "anicca-ios_youtube_en");
  assert.equal(byAccount["@anicca_wrong"].campaign_id, null);
  assert.equal(byAccount["@honne_wrong"].campaign_id, null);
  assert.equal(byAccount["@anicca_wrong_app"].campaign_id, null);
  assert.equal(byAccount["@anicca_wrong"].attribution_reason, "campaign_token_product_mismatch");
  assert.equal(byAccount["@anicca_wrong_app"].attribution_reason, "campaign_app_id_mismatch");
});

test("missing or ambiguous publication receipts stay unprovable without dropping exact rows", (t) => {
  const dataDir = fixtureDataDir();
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  addMetricFixture(dataDir, { productId: "anicca-ios", appId: "6755129214", accountId: "@exact", postId: "exact-row" });
  addMetricFixture(dataDir, { productId: "anicca-ios", appId: "6755129214", accountId: "@missing", postId: "missing-row", receiptCopies: 0 });
  addMetricFixture(dataDir, { productId: "honne-ai", appId: "6759667221", accountId: "@ambiguous", postId: "ambiguous-row", receiptCopies: 2 });

  const result = buildLineage({ dataDir });
  const byAccount = Object.fromEntries(result.rows.map((row) => [row.account_id, row]));
  assert.equal(result.rows.length, 3);
  assert.equal(byAccount["@exact"].publication_match_status, "exact");
  assert.equal(byAccount["@missing"].attribution_status, "unprovable");
  assert.equal(byAccount["@missing"].attribution_reason, "publication_receipt_missing");
  assert.equal(byAccount["@ambiguous"].attribution_status, "unprovable");
  assert.equal(byAccount["@ambiguous"].attribution_reason, "publication_receipt_ambiguous");
  assert.equal(result.coverage.exact_publication_lineage, 1);
  assert.equal(result.coverage.unprovable, 2);
  assert.equal(result.coverage.unattributed, 1);
});

test("ASC acquisition preserves unprovable publication lineage", async (t) => {
  const dataDir = fixtureDataDir();
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  addMetricFixture(dataDir, { productId: "anicca-ios", appId: "6755129214", accountId: "@exact", postId: "exact-row" });
  addMetricFixture(dataDir, { productId: "anicca-ios", appId: "6755129214", accountId: "@missing", postId: "missing-row", receiptCopies: 0 });
  persistLineage({ dataDir });

  const snapshot = await persistAscAcquisition(dataDir, "2026-08-21", async (product) => ({ product_id: product.product_id, source_status: "unavailable" }));
  const row = snapshot.rows.find((candidate) => candidate.account_id === "@missing");
  assert.equal(row.acquisition_status, "unprovable");
  assert.equal(row.acquisition_reason, "publication_receipt_missing");
});
