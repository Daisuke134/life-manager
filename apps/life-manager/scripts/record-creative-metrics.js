#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { resolveDataRoot } = require("../lib/runtime-paths.js");
const { recordCreativeMetric, readCreativeMetrics } = require("../lib/marketing-creative-metrics.js");

const NATIVE_METRIC_FIELDS = Object.freeze(["views", "reach", "impressions", "likes", "comments", "shares", "saves"]);

function readWrappedReceipts(dataDir, kind) {
  const file = path.join(dataDir, "marketing", "receipts.jsonl");
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, "utf8")
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line))
    .filter((row) => row && row.kind === "receipt" && row.receipt
      && typeof row.receipt === "object" && row.receipt.kind === kind);
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

function read24hSnapshots(dataDir, tenantId, providerPostIds) {
  const snapshots = new Map([...providerPostIds].map((providerPostId) => [providerPostId, []]));
  const root = path.join(dataDir, "tenants", encodeURIComponent(tenantId), "marketing", "metrics");
  let accounts;
  try { accounts = fs.readdirSync(root, { withFileTypes: true }); }
  catch (error) { if (error.code === "ENOENT") return snapshots; throw error; }
  for (const account of accounts) {
    if (!account.isDirectory()) continue;
    const accountDir = path.join(root, account.name);
    for (const post of fs.readdirSync(accountDir, { withFileTypes: true })) {
      if (!post.isDirectory()) continue;
      const file = path.join(accountDir, post.name, "24h.combined.json");
      const info = fs.lstatSync(file, { throwIfNoEntry: false });
      if (!info?.isFile() || (info.mode & 0o077) !== 0) continue;
      let snapshot;
      try { snapshot = JSON.parse(fs.readFileSync(file, "utf8")); }
      catch { continue; }
      if (snapshots.has(snapshot.provider_post_id)) snapshots.get(snapshot.provider_post_id).push(snapshot);
    }
  }
  return snapshots;
}

function nativeMetricValue(metric) {
  if (metric?.status === "measured" && typeof metric.value === "number" && Number.isFinite(metric.value) && metric.value >= 0) {
    return { status: "measured", value: metric.value };
  }
  if (metric?.status === "unavailable" && metric.value === null && metric.reason) {
    return { status: "unavailable", value: null, reason: metric.reason };
  }
  return { status: "unavailable", value: null, reason: metric?.reason || "native_metric_field_unavailable" };
}

function buildNativeMetricJoins(dataDir, publications, generations, expected) {
  const scoped = publications.map((publication) => {
    const receipt = publication.receipt;
    const generation = generations.find((row) => (
      receipt.creative_id.startsWith(`${row.receipt.creative_id}-`)
    ));
    return { publication, receipt, generation };
  });
  const snapshots = read24hSnapshots(dataDir, expected.tenantId, scoped.map(({ receipt }) => receipt.provider_post_id));
  const joins = scoped.map(({ receipt, generation }) => {
    const base = {
      product_id: expected.productId,
      format_id: expected.formatId,
      locale: expected.locale,
      platform: receipt.platform || "unavailable",
      account_id: receipt.account_id || null,
      arm_id: generation?.receipt.hook_id || null,
      creative_id: receipt.creative_id,
      provider_post_id: receipt.provider_post_id,
      window: "24h",
    };
    const unavailableMetrics = (reason) => Object.fromEntries(NATIVE_METRIC_FIELDS.map((field) => [field, { status: "unavailable", value: null, reason }]));
    if (!generation) return { ...base, status: "unavailable", reason: "creative_generation_missing", metrics: unavailableMetrics("creative_generation_missing") };
    if (receipt.provider_reconciled !== true) return { ...base, status: "unavailable", reason: "publication_not_reconciled", metrics: unavailableMetrics("publication_not_reconciled") };
    const candidates = (snapshots.get(receipt.provider_post_id) || []).filter((snapshot) => (
      snapshot.tenant_id === expected.tenantId
      && typeof snapshot.account_id === "string"
      && snapshot.product_id === expected.productId
      && snapshot.locale === expected.locale
      && (!receipt.account_id || snapshot.account_id === receipt.account_id)
      && snapshot.public_url === receipt.public_url
      && snapshot.window === "24h"
      && snapshot.kind === `${receipt.platform}_combined_metric_snapshot`
    ));
    if (!candidates.length) return { ...base, status: "pending", reason: "native_metric_snapshot_missing", metrics: unavailableMetrics("native_metric_snapshot_missing") };
    if (candidates.length !== 1) return { ...base, status: "unavailable", reason: "native_metric_snapshot_ambiguous", metrics: unavailableMetrics("native_metric_snapshot_ambiguous") };
    const snapshot = candidates[0];
    const metrics = Object.fromEntries(NATIVE_METRIC_FIELDS.map((field) => [field, nativeMetricValue(snapshot.post?.[field])]));
    const status = Object.values(metrics).some((metric) => metric.status === "measured") ? "measured" : "unavailable";
    return { ...base, account_id: snapshot.account_id, status, reason: status === "measured" ? null : "supported_native_metrics_unavailable", observed_at: snapshot.observed_at, published_at: snapshot.published_at, metrics };
  });
  return joins;
}

function compareNativeMetricArms(joins) {
  const groups = new Map();
  for (const row of joins) {
    if (!row.arm_id) continue;
    const key = `${row.arm_id}\n${row.platform}\n${row.locale}`;
    const group = groups.get(key) || { arm_id: row.arm_id, platform: row.platform, locale: row.locale, rows: [] };
    group.rows.push(row);
    groups.set(key, group);
  }
  return [...groups.values()].map(({ arm_id, platform, locale, rows }) => ({
    arm_id,
    platform,
    locale,
    posts: rows.length,
    metrics: Object.fromEntries(NATIVE_METRIC_FIELDS.map((field) => {
      const measured = rows.map((row) => row.metrics[field]).filter((metric) => metric.status === "measured").map((metric) => metric.value);
      const pending = rows.filter((row) => row.metrics[field].reason === "native_metric_snapshot_missing").length;
      const unavailable = rows.length - measured.length - pending;
      return [field, {
        status: measured.length ? "measured" : pending === rows.length ? "pending" : "unavailable",
        measured_posts: measured.length,
        pending_posts: pending,
        unavailable_posts: unavailable,
        mean: measured.length ? Math.round(measured.reduce((sum, value) => sum + value, 0) / measured.length * 100) / 100 : null,
      }];
    })),
  }));
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
    nativeAccount = null,
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
        && (!nativeAccount || (row.account_id === nativeAccount.accountId && row.platform === nativeAccount.platform
          && row.window === "24h" && row.metric === "views"))
      ))
      .map((row) => row.provider_post_id),
  );
  const recorded = [];
  const skipped = [];
  const pending = [];
  const nativeMetricJoins = buildNativeMetricJoins(dataDir, publications, generations, { tenantId, productId, formatId, locale });
  if (nativeAccount) {
    for (const row of nativeMetricJoins) {
      const age = Date.parse(row.observed_at) - Date.parse(row.published_at);
      if (row.account_id !== nativeAccount.accountId || row.platform !== nativeAccount.platform
        || row.status !== "measured" || row.metrics.views.status !== "measured"
        || !(age >= 86400000 && age <= 93600000) || alreadyRecorded.has(row.provider_post_id)) continue;
      recorded.push(recordCreativeMetric(dataDir, {
        tenantId, productId, formatId, locale, nativeAccount,
        hookId: row.arm_id, providerPostId: row.provider_post_id,
        score: row.metrics.views.value, observedAt: new Date(row.observed_at).toISOString(),
      }));
      alreadyRecorded.add(row.provider_post_id);
    }
    return { recorded, skipped, pending, native_metric_joins: nativeMetricJoins, arm_comparisons: compareNativeMetricArms(nativeMetricJoins) };
  }
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
  return { recorded, skipped, pending, native_metric_joins: nativeMetricJoins, arm_comparisons: compareNativeMetricArms(nativeMetricJoins) };
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
