"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { importContentObject } = require("../lib/content-object-store.js");
const { PRODUCTS, pending, persistAscAcquisition, rows, summarize } = require("./marketing-asc-acquisition.js");

function addMetricReceipt(dataDir, { productId, appId, accountId, postId, token = null }) {
  const objectDir = path.join(dataDir, "objects");
  const captionFile = path.join(dataDir, `${postId}.caption.txt`);
  const videoFile = path.join(dataDir, `${postId}.video.mp4`);
  const campaignLine = token ? `\nhttps://apps.apple.com/app/id${appId}?ct=${token}&mt=8` : "";
  fs.writeFileSync(captionFile, `Hook for ${accountId}${campaignLine}\n`);
  fs.writeFileSync(videoFile, `video-${postId}`);
  const caption = importContentObject(captionFile, { objectDir });
  const video = importContentObject(videoFile, { objectDir });
  const publicUrl = `https://www.tiktok.com/${accountId}/video/${postId}`;
  const receiptDir = path.join(dataDir, "marketing");
  fs.mkdirSync(receiptDir, { recursive: true });
  fs.appendFileSync(path.join(receiptDir, "receipts.jsonl"), `${JSON.stringify({ receipt: { kind: "marketing_video_distribution", status: "published", product_id: productId, locale: "en", platform: "tiktok", provider_post_id: postId, public_url: publicUrl, creative_id: `${productId}-${postId}`, slot: "2026-08-20T00:00:00.000Z", published_at: "2026-08-20T00:01:00.000Z", video_sha256: video.sha256, caption_sha256: caption.sha256 } })}\n`);
  const metricDir = path.join(dataDir, "tenants", "dais-local", "marketing", "metrics", accountId, postId);
  fs.mkdirSync(metricDir, { recursive: true });
  fs.writeFileSync(path.join(metricDir, "24h.combined.json"), JSON.stringify({ schema_version: 1, kind: "tiktok_combined_metric_snapshot", product_id: productId, locale: "en", account_id: accountId, integration_id: "integration-1", provider_post_id: postId, public_url: publicUrl, window: "24h", observed_at: "2026-08-21T00:01:00.000Z" }));
}

test("ASC acquisition covers six mobile app bindings and keeps pending reports unavailable", () => {
  assert.deepEqual(PRODUCTS.map(({ product_id, app_id, request_id }) => [product_id, app_id, request_id]), [
    ["anicca-ios", "6755129214", "04c74879-547f-4e35-b231-1fafd485801d"],
    ["honne-ai", "6759667221", "c7c05836-181e-49cc-ae71-b57b7a0b466e"],
    ["breath-reset", "6760253231", "9e3cdeeb-1b36-4ad8-b84e-b6a1ab58a443"],
    ["sleep-ritual", "6759916261", "d48b40a7-fd84-4ec7-a448-317c376457e0"],
    ["desk-stretch-timer", "6760048397", "0ffe9de3-7072-4dbc-9d49-afe1a70534b3"],
    ["micro-mood", "6759877003", "4e9b2fc8-6abb-4c6a-b58d-878f7a55e7e7"],
  ]);
  for (const product of PRODUCTS.slice(2)) {
    const value = pending(product);
    assert.equal(value.source_status, "unavailable");
    assert.equal(value.metrics.first_time_downloads.value, null);
    assert.equal(value.metrics.first_time_downloads.reason, "report_pending");
  }
});

test("pending Anicca ASC reports retain configured campaign breakdowns as unavailable", () => {
  const result = pending(PRODUCTS[0]);

  assert.ok(Array.isArray(result.campaign_breakdowns), "pending products must retain configured campaign breakdowns");
  assert.deepEqual(result.campaign_breakdowns.map((row) => [
    row.campaign_id, row.platform, row.account_id, row.locale,
    row.metrics.first_time_downloads.status, row.metrics.first_time_downloads.value,
    row.metrics.impressions.status, row.metrics.impressions.value,
  ]), [
    ["anicca-ios_tt_aniccaaff_en", "tiktok", "@aniccaaffirmation", "en", "unavailable", null, "unavailable", null],
    ["anicca-ios_ig_anicca-en_en", "instagram", "@anicca.en", "en", "unavailable", null, "unavailable", null],
    ["anicca-ios_youtube_en", "youtube", "@anicca-ai", "en", "unavailable", null, "unavailable", null],
  ]);
});

test("ASC product totals remain unattributed and unavailable stays null on replay", async (t) => {
  const parsed = rows("Date\tApp Name\tApp Apple Identifier\tDownload Type\tCounts\n2026-08-20\tDaily Affirmations - Anicca\t6755129214\tFirst-time download\t1\n");
  const anicca = summarize(PRODUCTS[0], parsed, [{ Date: "2026-08-19", "App Name": PRODUCTS[0].app_name, "App Apple Identifier": PRODUCTS[0].app_id, Event: "Impression", "Page Type": "No page", Counts: "9", "Unique Counts": "5" }], []);
  assert.equal(anicca.metrics.first_time_downloads.value, 1);
  assert.equal(anicca.metrics.impressions.value, 9);
  assert.equal(anicca.attribution_status, "unattributed");
  assert.equal(anicca.campaign_id, "anicca-ios_youtube_en");
  assert.equal(anicca.attribution_reason, "campaign_link_configured_no_product_readback");
  assert.equal(anicca.confidence, "official_product_total_campaign_unavailable");
  assert.equal(pending(PRODUCTS[0]).attribution_reason, "campaign_link_configured_no_product_readback");
  assert.equal(summarize(PRODUCTS[0], [], [], []).metrics.first_time_downloads.value, null);
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-asc-join-"));
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  addMetricReceipt(dataDir, { productId: "anicca-ios", appId: "6755129214", accountId: "@anicca-ai", postId: "post-1", token: "anicca-ios_youtube_en" });
  addMetricReceipt(dataDir, { productId: "honne-ai", appId: "6759667221", accountId: "@honne_reveal", postId: "post-2" });
  const collector = (product) => product.product_id === "anicca-ios" ? anicca : pending(product);
  const first = await persistAscAcquisition(dataDir, "2026-08-23", collector);
  const replay = await persistAscAcquisition(dataDir, "2026-08-23", collector);
  assert.equal(first.created, true);
  assert.equal(replay.created, false);
  assert.equal(first.snapshot_ref, replay.snapshot_ref);
  assert.equal(first.products[1].metrics.first_time_downloads.value, null);
  assert.deepEqual(first.rows.map(({ acquisition_status, acquisition_reason }) => [acquisition_status, acquisition_reason]), [
    ["partial", "campaign_link_configured_no_product_readback"],
    ["unattributed", "campaign_not_configured"],
  ]);
});

test("ASC campaign totals are measured only from a matching detailed-report token", () => {
  const honne = PRODUCTS[1]; const downloads = [{ Date: "2026-08-23", "App Apple Identifier": honne.app_id, "Download Type": "First-time download", Counts: "7" }]; const engagement = [{ Date: "2026-08-23", "App Apple Identifier": honne.app_id, Event: "Impression", Counts: "20", "Unique Counts": "12", Campaign: honne.campaign_token }]; const detailed = [{ ...downloads[0], Campaign: honne.campaign_token, Counts: "6" }];
  const measured = summarize(honne, downloads, engagement, [], detailed); assert.equal(measured.metrics.campaign_first_time_downloads.value, 6); assert.equal(measured.metrics.campaign_impressions.value, 20); assert.equal(measured.campaign_status, "measured");
  const withheld = summarize(honne, downloads, engagement.map((row) => ({ ...row, Campaign: "other" })), [], detailed.map((row) => ({ ...row, Campaign: "other" }))); assert.equal(withheld.metrics.campaign_first_time_downloads.value, null); assert.equal(withheld.metrics.campaign_first_time_downloads.status, "unavailable");
});

test("Anicca ASC acquisition uses the exact YouTube campaign token from its active CTA", () => {
  const anicca = PRODUCTS[0];
  const downloads = [{ Date: "2026-10-10", "App Apple Identifier": anicca.app_id, "Download Type": "First-time download", Counts: "1" }];
  const engagement = [
    { Date: "2026-10-10", "App Apple Identifier": anicca.app_id, Event: "Impression", Counts: "12", "Unique Counts": "9", Campaign: "anicca-ios_youtube_en" },
    { Date: "2026-10-10", "App Apple Identifier": anicca.app_id, Event: "Impression", Counts: "40", "Unique Counts": "32", Campaign: "other" },
  ];
  const detailed = [
    { ...downloads[0], Campaign: "anicca-ios_youtube_en", Counts: "1" },
    { ...downloads[0], Campaign: "anicca-ios_youtube_en", "Download Type": "Redownload", Counts: "4" },
    { ...downloads[0], Campaign: "other", Counts: "8" },
  ];
  const result = summarize(anicca, downloads, engagement, [], detailed);
  assert.equal(anicca.campaign_token, "anicca-ios_youtube_en");
  assert.equal(result.campaign_id, "anicca-ios_youtube_en");
  assert.equal(result.metrics.campaign_first_time_downloads.value, 1);
  assert.equal(result.metrics.campaign_impressions.value, 12);
  assert.equal(result.campaign_status, "measured");
  assert.equal(result.attribution_status, "partial");
  assert.equal(result.attribution_reason, "campaign_metrics_observed_for_subset");
  assert.equal(result.confidence, "official_product_total_with_campaign_subset");
});

test("Anicca campaign breakdowns isolate configured CTs by account and preserve missing data as unavailable", () => {
  const anicca = PRODUCTS[0];
  const downloads = [{ Date: "2026-10-10", "App Apple Identifier": anicca.app_id, "Download Type": "First-time download", Counts: "10" }];
  const engagement = [
    { Date: "2026-10-10", "App Apple Identifier": anicca.app_id, Event: "Impression", Counts: "5", "Unique Counts": "4", Campaign: "anicca-ios_ig_anicca-en_en" },
    { Date: "2026-10-10", "App Apple Identifier": anicca.app_id, Event: "Impression", Counts: "9", "Unique Counts": "8", Campaign: "anicca-ios_youtube_en" },
    { Date: "2026-10-10", "App Apple Identifier": anicca.app_id, Event: "Impression", Counts: "99", "Unique Counts": "90", Campaign: "unconfigured" },
  ];
  const detailed = [
    { ...downloads[0], Campaign: "anicca-ios_ig_anicca-en_en", Counts: "2" },
    { ...downloads[0], "Download Type": "Redownload", Campaign: "anicca-ios_ig_anicca-en_en", Counts: "40" },
    { ...downloads[0], Campaign: "anicca-ios_youtube_en", Counts: "1" },
    { ...downloads[0], Campaign: "unconfigured", Counts: "80" },
  ];

  const result = summarize(anicca, downloads, engagement, [], detailed);

  assert.ok(Array.isArray(result.campaign_breakdowns), "configured Anicca campaign breakdowns must be present");
  const byToken = Object.fromEntries(result.campaign_breakdowns.map((row) => [row.campaign_id, {
    platform: row.platform,
    account_id: row.account_id,
    locale: row.locale,
    first_time_downloads: row.metrics.first_time_downloads,
    impressions: row.metrics.impressions,
  }]));
  assert.deepEqual(byToken, {
    "anicca-ios_ig_anicca-en_en": {
      platform: "instagram", account_id: "@anicca.en", locale: "en",
      first_time_downloads: { status: "measured", value: 2, source: "app_store_connect_app_downloads_detailed" },
      impressions: { status: "measured", value: 5, source: "app_store_connect_discovery_engagement_detailed" },
    },
    "anicca-ios_tt_aniccaaff_en": {
      platform: "tiktok", account_id: "@aniccaaffirmation", locale: "en",
      first_time_downloads: { status: "unavailable", value: null, reason: "campaign_not_observed_or_privacy_threshold" },
      impressions: { status: "unavailable", value: null, reason: "campaign_not_observed_or_privacy_threshold" },
    },
    "anicca-ios_youtube_en": {
      platform: "youtube", account_id: "@anicca-ai", locale: "en",
      first_time_downloads: { status: "measured", value: 1, source: "app_store_connect_app_downloads_detailed" },
      impressions: { status: "measured", value: 9, source: "app_store_connect_discovery_engagement_detailed" },
    },
  });
  assert.equal(result.campaign_id, "anicca-ios_youtube_en");
  assert.equal(result.metrics.campaign_first_time_downloads.value, 1);
  assert.equal(result.metrics.campaign_impressions.value, 9);
});

test("ASC campaign breakdowns reject detailed rows for a different App Store app", () => {
  const anicca = PRODUCTS[0];
  const downloads = [{ Date: "2026-10-10", "App Apple Identifier": anicca.app_id, "Download Type": "First-time download", Counts: "10" }];
  const engagement = [{ Date: "2026-10-10", "App Apple Identifier": anicca.app_id, Event: "Impression", Counts: "5", "Unique Counts": "4" }];
  const wrongAppDetailed = [{
    Date: "2026-10-10", "App Apple Identifier": "6759667221", "Download Type": "First-time download",
    Campaign: "anicca-ios_ig_anicca-en_en", Counts: "99",
  }];

  assert.throws(() => summarize(anicca, downloads, engagement, [], wrongAppDetailed), /ASC app identity mismatch/);
});

test("campaign first-time downloads distinguish explicit zero from a redownload-only row", () => {
  const anicca = PRODUCTS[0];
  const downloads = [{ Date: "2026-10-10", "App Apple Identifier": anicca.app_id, "Download Type": "First-time download", Counts: "1" }];
  const engagement = [{ Date: "2026-10-10", "App Apple Identifier": anicca.app_id, Event: "Impression", Counts: "1", "Unique Counts": "1" }];
  const redownloadOnly = [{ Date: "2026-10-10", "App Apple Identifier": anicca.app_id, "Download Type": "Redownload", Campaign: "anicca-ios_tt_aniccaaff_en", Counts: "2" }];
  const tiktokBreakdown = (detailed) => summarize(anicca, downloads, engagement, [], detailed)
    .campaign_breakdowns.find((row) => row.campaign_id === "anicca-ios_tt_aniccaaff_en");

  assert.deepEqual(tiktokBreakdown(redownloadOnly).metrics.first_time_downloads, {
    status: "unavailable", value: null, reason: "campaign_not_observed_or_privacy_threshold",
  });
  assert.deepEqual(tiktokBreakdown([...redownloadOnly, {
    ...redownloadOnly[0], "Download Type": "First-time download", Counts: "0",
  }]).metrics.first_time_downloads, {
    status: "measured", value: 0, source: "app_store_connect_app_downloads_detailed",
  });
});

test("ASC daily metrics keep date-level zeros measured and leave absent report dates missing", () => {
  const anicca = PRODUCTS[0];
  const downloads = [
    { Date: "2026-10-05", "App Apple Identifier": anicca.app_id, "Download Type": "First-time download", Counts: "0" },
    { Date: "2026-10-07", "App Apple Identifier": anicca.app_id, "Download Type": "Redownload", Counts: "2" },
    { Date: "2026-10-08", "App Apple Identifier": anicca.app_id, "Download Type": "First-time download", Counts: "1" },
  ];
  const engagement = [
    { Date: "2026-10-05", "App Apple Identifier": anicca.app_id, Event: "Impression", "Page Type": "No page", Counts: "0", "Unique Counts": "0" },
    { Date: "2026-10-07", "App Apple Identifier": anicca.app_id, Event: "Page View", "Page Type": "Product page", Counts: "3", "Unique Counts": "2" },
  ];
  const result = summarize(anicca, downloads, engagement, []);
  const byDate = Object.fromEntries(result.daily_metrics.map((row) => [row.date, row.metrics]));

  assert.deepEqual(Object.keys(byDate), ["2026-10-05", "2026-10-07", "2026-10-08"]);
  assert.deepEqual([byDate["2026-10-05"].first_time_downloads.status, byDate["2026-10-05"].first_time_downloads.value], ["measured", 0]);
  assert.deepEqual([byDate["2026-10-05"].impressions.status, byDate["2026-10-05"].impressions.value], ["measured", 0]);
  assert.deepEqual([byDate["2026-10-07"].first_time_downloads.status, byDate["2026-10-07"].first_time_downloads.value], ["measured", 0]);
  assert.deepEqual([byDate["2026-10-07"].impressions.status, byDate["2026-10-07"].impressions.value], ["measured", 0]);
  assert.deepEqual([byDate["2026-10-07"].product_page_views.status, byDate["2026-10-07"].product_page_views.value], ["measured", 3]);
  assert.deepEqual([byDate["2026-10-08"].first_time_downloads.status, byDate["2026-10-08"].first_time_downloads.value], ["measured", 1]);
  assert.deepEqual([byDate["2026-10-08"].impressions.status, byDate["2026-10-08"].impressions.value], ["unavailable", null]);
});

test("daily ASC acquisition refreshes a stale lineage pointer from current metrics and receipts", async (t) => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-asc-refresh-"));
  const objectDir = path.join(dataDir, "objects");
  const attributionDir = path.join(dataDir, "tenants/dais-local/marketing/attribution");
  fs.mkdirSync(attributionDir, { recursive: true });
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));

  const staleFile = path.join(dataDir, "stale-lineage.json");
  fs.writeFileSync(staleFile, JSON.stringify({ schema_version: 1, kind: "marketing_attribution_lineage", tenant_id: "dais-local", rows: [{ product_id: "anicca-ios", account_id: "@stale", platform: "tiktok", provider_post_id: "old-post", public_url: "https://www.tiktok.com/@stale/video/old-post", campaign_id: null, attribution_status: "unattributed" }] }));
  const staleObject = importContentObject(staleFile, { objectDir });
  fs.writeFileSync(path.join(attributionDir, "lineage.json"), JSON.stringify({ rows: [{ product_id: "anicca-ios", account_id: "@stale", platform: "tiktok", provider_post_id: "old-post", public_url: "https://www.tiktok.com/@stale/video/old-post", campaign_id: null, attribution_status: "unattributed" }], snapshot_ref: staleObject.ref }));
  addMetricReceipt(dataDir, { productId: "anicca-ios", appId: "6755129214", accountId: "@anicca_new", postId: "123", token: "anicca-ios_youtube_en" });

  const snapshot = await persistAscAcquisition(dataDir, "2026-08-24", async (product) => ({ product_id: product.product_id, source_status: "unavailable" }));
  const currentLineage = JSON.parse(fs.readFileSync(path.join(attributionDir, "lineage.json"), "utf8"));
  assert.notEqual(currentLineage.snapshot_ref, staleObject.ref);
  assert.equal(snapshot.lineage_ref, currentLineage.snapshot_ref);
  assert.equal(snapshot.rows.length, 1);
  assert.equal(snapshot.rows[0].account_id, "@anicca_new");
  assert.equal(snapshot.rows[0].campaign_id, "anicca-ios_youtube_en");
});
