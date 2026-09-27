"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { readCreativeMetrics } = require("../lib/marketing-creative-metrics.js");
const { distributionLedgerPath, recordSlidePackMetrics } = require("./record-slide-pack-metrics.js");

const TENANT = "dais-local";
const PRODUCT = "anicca-ios";
const FORMAT = "larry";
const LOCALE = "ja";
const NOW = "2026-09-28T02:00:00.000Z";

function tempDataDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "record-slide-pack-metrics-"));
}

function distributionRow(overrides = {}) {
  return {
    effect_key: "k",
    job_id: "j",
    receipt: {
      kind: "marketing_native_carousel_distribution",
      status: "published",
      product_id: PRODUCT,
      format_id: FORMAT,
      locale: LOCALE,
      pack_sha256: "a".repeat(64),
      provider_post_id: "post-1",
      ...overrides,
    },
  };
}

test("recordSlidePackMetrics records one row per newly published pack, keyed by pack_sha256", async () => {
  const dataDir = tempDataDir();
  const file = distributionLedgerPath(dataDir, TENANT, PRODUCT);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${JSON.stringify(distributionRow())}\n`);

  const result = await recordSlidePackMetrics({
    dataDir,
    tenantId: TENANT,
    productId: PRODUCT,
    formatId: FORMAT,
    locale: LOCALE,
    fetchAnalytics: async () => ({ views: 100, likes: 10, saves: 5 }),
    now: () => NOW,
  });

  assert.equal(result.recorded.length, 1);
  assert.equal(result.recorded[0].hook_id, "a".repeat(64));
  assert.equal(result.recorded[0].score, 115);

  const stored = readCreativeMetrics(dataDir);
  assert.equal(stored.length, 1);
  assert.equal(stored[0].provider_post_id, "post-1");
});

test("recordSlidePackMetrics is idempotent per provider_post_id", async () => {
  const dataDir = tempDataDir();
  const file = distributionLedgerPath(dataDir, TENANT, PRODUCT);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${JSON.stringify(distributionRow())}\n`);
  let calls = 0;
  const fetchAnalytics = async () => { calls += 1; return { views: 1 }; };

  await recordSlidePackMetrics({ dataDir, tenantId: TENANT, productId: PRODUCT, formatId: FORMAT, locale: LOCALE, fetchAnalytics, now: () => NOW });
  const second = await recordSlidePackMetrics({ dataDir, tenantId: TENANT, productId: PRODUCT, formatId: FORMAT, locale: LOCALE, fetchAnalytics, now: () => NOW });

  assert.equal(calls, 1);
  assert.equal(second.recorded.length, 0);
});

test("recordSlidePackMetrics skips receipts for a different product/format/locale scope", async () => {
  const dataDir = tempDataDir();
  const file = distributionLedgerPath(dataDir, TENANT, PRODUCT);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${JSON.stringify(distributionRow({ locale: "en" }))}\n`);

  const result = await recordSlidePackMetrics({ dataDir, tenantId: TENANT, productId: PRODUCT, formatId: FORMAT, locale: LOCALE, fetchAnalytics: async () => ({ views: 1 }), now: () => NOW });
  assert.equal(result.recorded.length, 0);
});
