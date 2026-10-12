#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { resolveDataRoot } = require("../lib/runtime-paths.js");
const { discoverExpected: discoverInstagram, snapshotFile: instagramSnapshotFile } = require("./instagram-metrics-due.js");
const { discoverTargets: discoverTikTok, snapshotFile: tiktokSnapshotFile } = require("./tiktok-metrics-due.js");

const WINDOWS = Object.freeze(["24h", "7d"]);
const WINDOW_SET = new Set(WINDOWS);
const POST_METRICS = Object.freeze([
  "views", "reach", "saves", "likes", "comments", "shares", "impressions",
  "watch_time", "average_watch_time", "completion", "engagement",
]);
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

function postMetrics(snapshot, missingReason) {
  return Object.fromEntries(POST_METRICS.map((key) => {
    const metric = snapshot?.post?.[key];
    return [key, metric && typeof metric === "object" && typeof metric.status === "string"
      ? metric
      : { status: "unavailable", value: null, reason: missingReason }];
  }));
}

function joinCreativeMetricRows({ dataDir, productId = "anicca-ios", windows = WINDOWS, nowMs = Date.now() } = {}) {
  if (!dataDir || !IDENTIFIER.test(String(productId)) || !Number.isFinite(nowMs)) {
    throw new Error("creative metrics join input invalid");
  }
  const selectedWindows = [...new Set(windows)];
  if (selectedWindows.length === 0 || selectedWindows.some((window) => !WINDOW_SET.has(window))) {
    throw new Error("creative metrics join window invalid");
  }

  const publications = [
    ...discoverInstagram(dataDir).filter((row) => row.product_id === productId).map((row) => ({ ...row, platform: "instagram" })),
    ...discoverTikTok(dataDir, nowMs).filter((row) => row.product_id === productId).map((row) => ({ ...row, platform: "tiktok" })),
  ];
  const uniquePublications = new Map();
  for (const publication of publications) {
    const providerPostId = String(publication.provider_post_id || "");
    if (!providerPostId) throw new Error("creative metrics publication provider_post_id missing");
    const creativeId = typeof publication.creative_id === "string" && IDENTIFIER.test(publication.creative_id)
      ? publication.creative_id
      : null;
    const normalized = { ...publication, creative_id: creativeId };
    const key = `${publication.platform}:${providerPostId}`;
    const existing = uniquePublications.get(key);
    if (existing && (existing.account_id !== normalized.account_id || existing.locale !== normalized.locale
      || existing.product_id !== normalized.product_id || existing.creative_id !== normalized.creative_id
      || existing.format_id !== normalized.format_id || existing.form !== normalized.form)) {
      throw new Error("creative metrics publication identity conflict");
    }
    uniquePublications.set(key, normalized);
  }

  const rows = [];
  for (const publication of uniquePublications.values()) {
    for (const window of selectedWindows) {
      const file = publication.platform === "instagram"
        ? instagramSnapshotFile(dataDir, window, publication)
        : tiktokSnapshotFile(dataDir, publication, window);
      const snapshot = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : null;
      if (snapshot) {
        const expectedKindPrefix = `${publication.platform}_`;
        if (!String(snapshot.kind || "").startsWith(expectedKindPrefix)
          || !String(snapshot.kind).includes("metric_snapshot")
          || snapshot.product_id !== publication.product_id
          || snapshot.locale !== publication.locale
          || snapshot.account_id !== publication.account_id
          || snapshot.provider_post_id !== publication.provider_post_id
          || snapshot.window !== window
          || (snapshot.creative_id && publication.creative_id && snapshot.creative_id !== publication.creative_id)) {
          throw new Error("creative metric snapshot identity mismatch");
        }
      }
      rows.push({
        creative_id: publication.creative_id,
        format_id: publication.format_id || null,
        form: publication.form || null,
        arm_id: publication.format_id && publication.form ? `${publication.format_id}:${publication.form}` : null,
        attribution_status: publication.creative_id ? "attributed" : "unavailable",
        product_id: publication.product_id,
        platform: publication.platform,
        account_id: publication.account_id,
        locale: publication.locale,
        provider_post_id: publication.provider_post_id,
        public_url: publication.public_url || "unavailable",
        window,
        published_at: publication.published_at,
        observed_at: snapshot?.observed_at || null,
        status: snapshot ? "observed" : "pending",
        ...(!snapshot ? { reason: "snapshot_missing" } : {}),
        metrics: postMetrics(snapshot, snapshot ? "metric_missing" : "snapshot_missing"),
      });
    }
  }
  rows.sort((left, right) => `${left.creative_id || ""}:${left.platform}:${left.locale}:${left.provider_post_id}:${left.window}`
    .localeCompare(`${right.creative_id || ""}:${right.platform}:${right.locale}:${right.provider_post_id}:${right.window}`));
  return {
    schema_version: 1,
    kind: "marketing_creative_metrics_join",
    product_id: productId,
    observed_at: new Date(nowMs).toISOString(),
    windows: selectedWindows,
    rows,
  };
}

function run(argv = process.argv.slice(2), env = process.env) {
  const productId = String(argv[0] || "anicca-ios").trim();
  const windows = String(argv[1] || WINDOWS.join(",")).split(",").map((value) => value.trim()).filter(Boolean);
  return process.stdout.write(`${JSON.stringify(joinCreativeMetricRows({
    dataDir: resolveDataRoot(env),
    productId,
    windows,
  }))}\n`);
}

if (require.main === module) {
  try { run(); }
  catch (error) {
    process.stderr.write(`${String(error.message || error)}\n`);
    process.exitCode = 1;
  }
}

module.exports = { joinCreativeMetricRows, postMetrics, run };
