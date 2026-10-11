#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { resolveDataRoot } = require("../lib/runtime-paths.js");
const { recordCreativeMetric, readCreativeMetrics } = require("../lib/marketing-creative-metrics.js");

function readWrappedReceipts(dataDir, kind) {
  const file = path.join(dataDir, "marketing", "receipts.jsonl");
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, "utf8")
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line))
    .filter((row) => row && row.kind === kind && row.receipt && typeof row.receipt === "object");
}

// Postiz returns metric rows with string totals and numeric percentage changes. Sum only the
// totals for that shape; keep the legacy numeric-object form for existing callers.
function engagementScore(analytics) {
  if (Array.isArray(analytics) && analytics.length === 0) return null;

  const postizRows = Array.isArray(analytics)
    ? analytics.filter((row) => row && typeof row === "object"
      && ("label" in row || "percentageChange" in row || Array.isArray(row.data)))
    : [];
  if (postizRows.length) {
    let total = 0;
    let found = false;
    for (const row of postizRows) {
      for (const metric of Array.isArray(row.data) ? row.data : []) {
        const value = metric?.total;
        const numeric = typeof value === "number" ? value
          : typeof value === "string" && value.trim() ? Number(value)
            : Number.NaN;
        if (!Number.isFinite(numeric)) continue;
        total += numeric;
        found = true;
      }
    }
    return found ? total : null;
  }

  let total = 0;
  let found = false;
  const walk = (value) => {
    if (typeof value === "number" && Number.isFinite(value)) { total += value; found = true; return; }
    if (Array.isArray(value)) { value.forEach(walk); return; }
    if (value && typeof value === "object") {
      for (const [key, nested] of Object.entries(value)) {
        if (key !== "percentageChange") walk(nested);
      }
    }
  };
  walk(analytics);
  return found ? total : null;
}

async function fetchPostizPostAnalytics(providerPostId, env = process.env) {
  const key = String(env.LM_POSTIZ_API_KEY || "").trim();
  if (!key) throw new Error("LM_POSTIZ_API_KEY is required");
  const response = await fetch(
    `https://api.postiz.com/public/v1/analytics/post/${encodeURIComponent(providerPostId)}?date=7`,
    { headers: { Authorization: key } },
  );
  if (!response.ok) throw new Error(`Postiz analytics HTTP ${response.status}`);
  return response.json();
}

// Joins each published generation receipt (marketing_video_artifact, carries hook_id) to its
// publication receipt (marketing_video_distribution, carries provider_post_id) via the
// creative_id prefix relationship established in honne-ja-cycle.js/honne-en-cycle.js
// (`${generation.creative_id}-${slotDigits}` === publication.creative_id), fetches that
// post's Postiz analytics, and appends one creative-metrics row per provider_post_id.
// Idempotent: a provider_post_id already recorded is skipped on rerun.
async function recordCreativeMetrics(options = {}) {
  const {
    dataDir,
    tenantId,
    productId,
    formatId,
    locale,
    env = process.env,
    fetchAnalytics = fetchPostizPostAnalytics,
    now = () => new Date().toISOString(),
  } = options;
  const generations = readWrappedReceipts(dataDir, "marketing_video_artifact").filter((row) => (
    row.tenant_id === tenantId
    && row.receipt.product_id === productId
    && row.receipt.format_id === formatId
    && row.receipt.locale === locale
  ));
  const publications = readWrappedReceipts(dataDir, "marketing_video_distribution").filter((row) => (
    row.tenant_id === tenantId
    && row.receipt.product_id === productId
    && row.receipt.format_id === formatId
    && row.receipt.locale === locale
    && row.receipt.status === "published"
    && row.receipt.provider_post_id
  ));
  const alreadyRecorded = new Set(
    readCreativeMetrics(dataDir)
      .filter((row) => (
        row.tenant_id === tenantId
        && row.product_id === productId
        && row.format_id === formatId
        && row.locale === locale
      ))
      .map((row) => row.provider_post_id),
  );
  const recorded = [];
  const skipped = [];
  const pending = [];
  for (const publication of publications) {
    const providerPostId = publication.receipt.provider_post_id;
    if (alreadyRecorded.has(providerPostId)) continue;
    const generation = generations.find((row) => (
      publication.receipt.creative_id.startsWith(`${row.receipt.creative_id}-`)
    ));
    if (!generation) { skipped.push(providerPostId); continue; }
    const analytics = await fetchAnalytics(providerPostId, env);
    const score = engagementScore(analytics);
    if (score === null) { pending.push(providerPostId); continue; }
    const row = recordCreativeMetric(dataDir, {
      tenantId,
      productId,
      formatId,
      locale,
      hookId: generation.receipt.hook_id,
      providerPostId,
      score,
      observedAt: now(),
    });
    recorded.push(row);
  }
  return { recorded, skipped, pending };
}

if (require.main === module) {
  const env = process.env;
  const dataDir = resolveDataRoot(env);
  const tenantId = String(env.LM_RUNTIME_TENANT_ID || "").trim();
  const [productId, formatId, locale] = process.argv.slice(2);
  if (!tenantId || !productId || !formatId || !locale) {
    process.stderr.write("usage: LM_RUNTIME_TENANT_ID=<tenant> record-creative-metrics.js <productId> <formatId> <locale>\n");
    process.exitCode = 1;
  } else {
    recordCreativeMetrics({ dataDir, tenantId, productId, formatId, locale })
      .then((result) => process.stdout.write(`${JSON.stringify(result)}\n`))
      .catch((error) => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
  }
}

module.exports = { engagementScore, fetchPostizPostAnalytics, recordCreativeMetrics };
