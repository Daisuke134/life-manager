"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { importContentObject } = require("../lib/content-object-store.js");
const { PRODUCTS, pending, persistAscAcquisition, rows, summarize } = require("./marketing-asc-acquisition.js");

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

test("ASC product totals remain unattributed and unavailable stays null on replay", async () => {
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
  const objectDir = path.join(dataDir, "objects");
  const attributionDir = path.join(dataDir, "tenants/dais-local/marketing/attribution");
  fs.mkdirSync(attributionDir, { recursive: true });
  const lineageFile = path.join(dataDir, "lineage.json");
  const lineage = { rows: [{ product_id: "anicca-ios", account_id: "@anicca-ai", platform: "youtube", provider_post_id: "post-1", public_url: "https://www.youtube.com/shorts/1", campaign_id: "anicca-ios_youtube_en" }, { product_id: "honne-ai", account_id: "@honne_reveal", platform: "tiktok", provider_post_id: "post-2", public_url: "https://www.tiktok.com/@honne_reveal/video/2", campaign_id: null }] };
  fs.writeFileSync(lineageFile, JSON.stringify(lineage));
  const imported = importContentObject(lineageFile, { objectDir });
  fs.writeFileSync(path.join(attributionDir, "lineage.json"), JSON.stringify({ ...lineage, snapshot_ref: imported.ref }));
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
