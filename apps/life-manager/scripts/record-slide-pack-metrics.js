#!/usr/bin/env node
"use strict";

// Records per-pack engagement metrics for a native-carousel (Larry) lane so
// generate-larry-slide-pack.js can bias rotation toward hook/format families
// that scored above median (explore/exploit). Reuses the Postiz-analytics
// fetch + scoring already proven in record-creative-metrics.js (#6047);
// carousel publication receipts don't need that file's generation->publication
// join (a carousel publish job already carries pack_sha256 directly), so this
// reads the carousel's own distribution ledger instead.

const fs = require("node:fs");
const path = require("node:path");
const { resolveDataRoot } = require("../lib/runtime-paths.js");
const { recordCreativeMetric, readCreativeMetrics } = require("../lib/marketing-creative-metrics.js");
const { engagementScore, fetchPostizPostAnalytics } = require("./record-creative-metrics.js");

function distributionLedgerPath(dataDir, tenantId, productId) {
  return path.join(dataDir, "tenants", encodeURIComponent(tenantId), "marketing", "native-carousel-publication", productId, "distribution.jsonl");
}

function readPublishedReceipts(file) {
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, "utf8").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line))
    .filter((row) => row && row.receipt && row.receipt.kind === "marketing_native_carousel_distribution"
      && row.receipt.status === "published" && row.receipt.provider_post_id && row.receipt.pack_sha256);
}

// Idempotent per provider_post_id (skips a post already present in
// readCreativeMetrics(), same guarantee record-creative-metrics.js documents).
async function recordSlidePackMetrics({
  dataDir,
  tenantId,
  productId,
  formatId,
  locale,
  env = process.env,
  fetchAnalytics = fetchPostizPostAnalytics,
  now = () => new Date().toISOString(),
} = {}) {
  const publications = readPublishedReceipts(distributionLedgerPath(dataDir, tenantId, productId))
    .filter((row) => row.receipt.product_id === productId && row.receipt.format_id === formatId && row.receipt.locale === locale);
  const alreadyRecorded = new Set(
    readCreativeMetrics(dataDir)
      .filter((row) => row.tenant_id === tenantId && row.product_id === productId && row.format_id === formatId && row.locale === locale)
      .map((row) => row.provider_post_id),
  );
  const recorded = [];
  for (const { receipt } of publications) {
    if (alreadyRecorded.has(receipt.provider_post_id)) continue;
    const analytics = await fetchAnalytics(receipt.provider_post_id, env);
    const row = recordCreativeMetric(dataDir, {
      tenantId,
      productId,
      formatId,
      locale,
      hookId: receipt.pack_sha256,
      providerPostId: receipt.provider_post_id,
      score: engagementScore(analytics),
      observedAt: now(),
    });
    recorded.push(row);
  }
  return { recorded };
}

if (require.main === module) {
  const env = process.env;
  const dataDir = resolveDataRoot(env);
  const tenantId = String(env.LM_RUNTIME_TENANT_ID || "").trim();
  const [productId, formatId, locale] = process.argv.slice(2);
  if (!tenantId || !productId || !formatId || !locale) {
    process.stderr.write("usage: LM_RUNTIME_TENANT_ID=<tenant> record-slide-pack-metrics.js <productId> <formatId> <locale>\n");
    process.exitCode = 1;
  } else {
    recordSlidePackMetrics({ dataDir, tenantId, productId, formatId, locale })
      .then((result) => process.stdout.write(`${JSON.stringify(result)}\n`))
      .catch((error) => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
  }
}

module.exports = { distributionLedgerPath, readPublishedReceipts, recordSlidePackMetrics };
