"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { importContentObject } = require("../lib/content-object-store.js");
const { PRODUCTS, persistRevenueCatSubscriptions } = require("./marketing-revenuecat-subscriptions.js");
const { PRODUCTS: ASC_PRODUCTS } = require("./marketing-asc-acquisition.js");

function fixture() {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-rc-"));
  const objectDir = path.join(dataDir, "objects");
  const ascDir = path.join(dataDir, "tenants/dais-local/marketing/attribution/asc/2026-08-23");
  fs.mkdirSync(ascDir, { recursive: true });
  const source = path.join(dataDir, "asc-source.json");
  fs.writeFileSync(source, "{}\n");
  const asc = importContentObject(source, { objectDir });
  fs.writeFileSync(path.join(ascDir, "acquisition.json"), JSON.stringify({ snapshot_ref: asc.ref }));
  return { dataDir, objectDir };
}

test("RevenueCat daily coverage follows the six currently published app metrics", () => {
  assert.deepEqual(PRODUCTS, [
    "anicca-ios", "honne-ai", "dhamma-quotes", "sleep-reset", "studio-cherie", "thankful",
  ]);
  assert.deepEqual(PRODUCTS, ASC_PRODUCTS.map(({ product_id }) => product_id));
  const { dataDir } = fixture();
  const result = persistRevenueCatSubscriptions(dataDir, "2026-08-23", "2026-08-23T13:00:00.000Z");
  assert.equal(result.products.length, 6);
  assert.ok(result.products.every((product) => product.source_status === "unavailable"));
});

test("keeps all published products unavailable when no product-owned observation exists", () => {
  const { dataDir } = fixture();
  const result = persistRevenueCatSubscriptions(dataDir, "2026-08-23", "2026-08-23T13:00:00.000Z");
  assert.equal(result.products.length, 6);
  for (const product of result.products) {
    assert.equal(product.source_status, "unavailable");
    for (const metric of Object.values(product.metrics)) assert.deepEqual(metric, { status: "unavailable", value: null, reason: "product_pack_observation_missing" });
  }
});

test("imports isolated measured and unavailable metrics and replays without a second object", () => {
  const { dataDir } = fixture();
  const inbox = path.join(dataDir, "tenants/dais-local/product-packs/metrics/revenuecat");
  fs.mkdirSync(inbox, { recursive: true });
  fs.writeFileSync(path.join(inbox, "anicca-ios.json"), JSON.stringify({
    schema_version: 1, kind: "product_revenuecat_observation", product_id: "anicca-ios",
    observed_at: "2026-08-23T12:55:00.000Z", data_from: "2026-08-22", data_to: "2026-08-22",
    source: "revenuecat_charts_api", source_status: "partial",
    metrics: {
      trial_starts: { status: "measured", value: 1, unit: "count" },
      active_subscriptions: { status: "measured", value: 5, unit: "count" },
      renewals: { status: "unavailable", value: null, reason: "chart_not_exported" },
      cancellations: { status: "measured", value: 0, unit: "count" },
      proceeds_usd: { status: "measured", value: 3.25, unit: "USD", truth: "revenuecat_estimate" }
    }
  }));
  const first = persistRevenueCatSubscriptions(dataDir, "2026-08-23", "2026-08-23T13:00:00.000Z");
  const replay = persistRevenueCatSubscriptions(dataDir, "2026-08-23", "2026-08-23T14:00:00.000Z");
  const anicca = first.products.find((item) => item.product_id === "anicca-ios");
  const honne = first.products.find((item) => item.product_id === "honne-ai");
  assert.equal(anicca.metrics.active_subscriptions.value, 5);
  assert.equal(anicca.metrics.renewals.status, "unavailable");
  assert.equal(honne.source_status, "unavailable");
  assert.equal(replay.created, false);
  assert.equal(replay.snapshot_ref, first.snapshot_ref);
});

test("rejects product identity mismatch and false unavailable zero", () => {
  const { dataDir } = fixture();
  const inbox = path.join(dataDir, "tenants/dais-local/product-packs/metrics/revenuecat");
  fs.mkdirSync(inbox, { recursive: true });
  fs.writeFileSync(path.join(inbox, "anicca-ios.json"), JSON.stringify({
    schema_version: 1, kind: "product_revenuecat_observation", product_id: "honne-ai", observed_at: "2026-08-23T12:55:00.000Z",
    source: "revenuecat_charts_api", source_status: "unavailable",
    metrics: Object.fromEntries(["trial_starts", "active_subscriptions", "renewals", "cancellations", "proceeds_usd"].map((key) => [key, { status: "unavailable", value: 0, reason: "missing" }]))
  }));
  assert.throws(() => persistRevenueCatSubscriptions(dataDir, "2026-08-23"), /product identity mismatch/);
});
