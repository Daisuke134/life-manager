"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { importContentObject } = require("../lib/content-object-store.js");
const { PRODUCTS, derivedFunnelRates, pending, persistAscAcquisition, rows, summarize } = require("./marketing-asc-acquisition.js");

test("ASC funnel rates are measured with explicit numerators and denominators", () => {
  const rates = derivedFunnelRates({
    first_time_downloads: { status: "measured", value: 2 },
    unique_impressions: { status: "measured", value: 10 },
    unique_product_page_views: { status: "measured", value: 4 },
  });
  assert.deepEqual(rates.impression_to_page_view, {
    status: "measured", value: 0.4, numerator: 4, denominator: 10,
  });
  assert.deepEqual(rates.page_view_to_install, {
    status: "measured", value: 0.5, numerator: 2, denominator: 4,
  });
  assert.deepEqual(rates.impression_to_install, {
    status: "measured", value: 0.2, numerator: 2, denominator: 10,
  });
});

test("ASC funnel rates fail closed on unavailable metrics and zero denominators", () => {
  const rates = derivedFunnelRates({
    first_time_downloads: { status: "measured", value: 2 },
    unique_impressions: { status: "measured", value: 0 },
    unique_product_page_views: { status: "unavailable", value: null, reason: "provider_403" },
  });
  assert.equal(rates.impression_to_install.status, "unavailable");
  assert.equal(rates.impression_to_install.reason, "denominator_zero");
  assert.equal(rates.page_view_to_install.reason, "source_metric_unavailable:unique_product_page_views");
});

test("ASC product totals remain unattributed and unavailable stays null on replay", async () => {
  const parsed = rows("Date\tApp Name\tApp Apple Identifier\tDownload Type\tCounts\n2026-08-20\tDaily Affirmations - Anicca\t6755129214\tFirst-time download\t1\n");
  const anicca = summarize(PRODUCTS[0], parsed, [{ Date: "2026-08-19", "App Name": PRODUCTS[0].app_name, "App Apple Identifier": PRODUCTS[0].app_id, Event: "Impression", "Page Type": "No page", Counts: "9", "Unique Counts": "5" }], []);
  assert.equal(anicca.metrics.first_time_downloads.value, 1);
  assert.equal(anicca.metrics.impressions.value, 9);
  assert.equal(anicca.attribution_status, "unattributed");
  assert.equal(summarize(PRODUCTS[0], [], [], []).metrics.first_time_downloads.value, null);
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-asc-join-"));
  const objectDir = path.join(dataDir, "objects");
  const attributionDir = path.join(dataDir, "tenants/dais-local/marketing/attribution");
  fs.mkdirSync(attributionDir, { recursive: true });
  const lineageFile = path.join(dataDir, "lineage.json");
  const lineage = { rows: [{ product_id: "anicca-ios", account_id: "@anicca.jp", platform: "tiktok", provider_post_id: "post-1", public_url: "https://www.tiktok.com/@anicca.jp/video/1", campaign_id: null }, { product_id: "honne-ai", account_id: "@honne_reveal", platform: "tiktok", provider_post_id: "post-2", public_url: "https://www.tiktok.com/@honne_reveal/video/2", campaign_id: null }] };
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
  assert.ok(first.rows.every((row) => row.acquisition_status === "unattributed"));
});

test("ASC campaign totals are measured only from a matching detailed-report token", () => {
  const honne = PRODUCTS[1]; const downloads = [{ Date: "2026-08-23", "App Apple Identifier": honne.app_id, "Download Type": "First-time download", Counts: "7" }]; const engagement = [{ Date: "2026-08-23", "App Apple Identifier": honne.app_id, Event: "Impression", Counts: "20", "Unique Counts": "12", Campaign: honne.campaign_token }]; const detailed = [{ ...downloads[0], Campaign: honne.campaign_token, Counts: "6" }];
  const measured = summarize(honne, downloads, engagement, [], detailed); assert.equal(measured.metrics.campaign_first_time_downloads.value, 6); assert.equal(measured.metrics.campaign_impressions.value, 20); assert.equal(measured.campaign_status, "measured");
  const withheld = summarize(honne, downloads, engagement.map((row) => ({ ...row, Campaign: "other" })), [], detailed.map((row) => ({ ...row, Campaign: "other" }))); assert.equal(withheld.metrics.campaign_first_time_downloads.value, null); assert.equal(withheld.metrics.campaign_first_time_downloads.status, "unavailable");
});
