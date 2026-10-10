#!/usr/bin/env node
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { resolveDataRoot } = require("../lib/runtime-paths.js");
const { verifyMarketingNativeCarouselPublicationReceipt } = require("../lib/marketing-native-carousel-publication-adapter.js");
const { persistDailyDigest, sendMetricSnapshot } = require("./instagram-metrics-read.js");
const { collectPostizPhotoWindow, collectTikTokWindow } = require("./tiktok-native-metrics-read.js");
const { persistAniccaDaily, persistAttributionCoverage, persistHonneDaily, persistWeeklyReview, sendSummary } = require("./marketing-product-summary.js");
const { persistAscAcquisition } = require("./marketing-asc-acquisition.js");
const { persistRevenueCatSubscriptions } = require("./marketing-revenuecat-subscriptions.js");

const WINDOWS = Object.freeze({ "2h": 2 * 3600_000, "24h": 24 * 3600_000, "72h": 72 * 3600_000, "7d": 7 * 86400_000 });
const GRACE_MS = 90 * 60_000;
const TARGETS = Object.freeze([
  Object.freeze({ publication_dir: "anicca-ios", product_id: "anicca-ios", locale: "ja", account_id: "@anicca.jp4", native_owner: "anicca.jp4", integration_id: "cmn8x8hdv028uqx0y4gdfse5t", format_id: "reelclaw-card", form: "nudge-card" }),
  Object.freeze({ publication_dir: "anicca-ios", product_id: "anicca-ios", locale: "ja", account_id: "@anicca.jp", native_owner: "anicca.jp", integration_id: "cmp9sdev5012voh0y58qs45xc", format_id: "reelclaw-card", form: "nudge-card" }),
  Object.freeze({ publication_dir: "anicca-ios", product_id: "anicca-ios", locale: "ja", account_id: "@anicca.he", native_owner: "anicca.he", integration_id: "cmq2aoena08bhqp0yx1epjcik", format_id: "reelclaw-card", form: "nudge-card", receipt_job_id: "marketing-video-publication:7732e4c1e7ff88ccad12a0295e6740125f58da2d6e07558e6f9e432bf85349dd" }),
  Object.freeze({ publication_dir: "anicca-ios", product_id: "anicca-ios", locale: "en", account_id: "@anicca_slideshow", native_owner: "anicca_slideshow", integration_id: "cmnenjkff01j1pa0ysufmzhfr", format_id: "slideshow", form: "mental-health-carousel", receipt_job_id: "marketing-native-carousel-publication:0cd8be1c72b8c6fd058741a287995caa20f23363f71ee908d6139127782c788f", postiz_photo_only: true }),
  Object.freeze({ publication_dir: "honne-ai", product_id: "honne-ai", locale: "en", account_id: "@honne_reveal", native_owner: "honne_reveal", integration_id: "cmoig11ew001zlv0yk6vqo1us", format_id: "reelclaw", form: "relationship-confession" }),
  Object.freeze({ publication_dir: "honne-ai", product_id: "honne-ai", locale: "ja", account_id: "@honnevideo", native_owner: "honnevideo", integration_id: "cmnit95mg015rrm0ye5vm8dhl", format_id: "reelclaw", form: "relationship-confession" }),
]);

function discoverTarget(dataDir, target) {
  if (target.postiz_photo_only) {
    const receipts = path.join(dataDir, "marketing/receipts.jsonl");
    if (!fs.existsSync(receipts)) return [];
    const row = fs.readFileSync(receipts, "utf8").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line)).find((candidate) => candidate.job_id === target.receipt_job_id);
    const receipt = row?.receipt; const captionPath = path.join(dataDir, "objects/sha256", String(receipt?.caption_sha256 || ""));
    if (!receipt || receipt.status !== "published" || receipt.provider_reconciled !== true || receipt.platform !== "tiktok" || receipt.account_id !== target.account_id || receipt.integration_ref !== `integration://postiz/tiktok/${target.integration_id}` || receipt.format_id !== target.format_id || receipt.form !== target.form || receipt.locale !== target.locale || receipt.public_url !== null || receipt.provider_state !== "PUBLISHED" || !fs.statSync(captionPath, { throwIfNoEntry: false })?.isFile()) throw new Error(`${target.account_id} Postiz photo receipt invalid`);
    const bytes = fs.readFileSync(captionPath); if (crypto.createHash("sha256").update(bytes).digest("hex") !== receipt.caption_sha256) throw new Error(`${target.account_id} caption object integrity mismatch`);
    return [Object.freeze({ tenant_id: "dais-local", product_id: target.product_id, locale: target.locale, account_id: target.account_id, native_owner: target.native_owner, integration_id: target.integration_id, provider_post_id: receipt.provider_post_id, shortcode: receipt.provider_post_id, video_id: receipt.provider_post_id, public_url: "unavailable", caption: bytes.toString("utf8"), published_at: receipt.published_at, postiz_photo_only: true })];
  }
  const file = path.join(dataDir, "tenants/dais-local/marketing/video-publication", target.publication_dir, "distribution.jsonl");
  let rows = fs.existsSync(file) ? fs.readFileSync(file, "utf8").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line)) : [];
  if (target.receipt_job_id && !rows.some((row) => row.public_url?.includes(target.native_owner))) { const receipts = path.join(dataDir, "marketing/receipts.jsonl"); const matched = fs.existsSync(receipts) ? fs.readFileSync(receipts, "utf8").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line)).find((row) => row.job_id === target.receipt_job_id)?.receipt : null; if (matched) rows = rows.concat({ ...matched, ts: matched.published_at, provider_id: matched.provider_post_id, caption_path: path.join(dataDir, "objects/sha256", matched.caption_sha256) }); }
  const candidates = rows.filter((row) => {
    const match = /^https:\/\/www\.tiktok\.com\/@([^/]+)\/video\/(\d+)\/?$/.exec(String(row.public_url || ""));
    return row.platform === "tiktok" && row.status === "published" && row.provider_reconciled === true && row.format_id === target.format_id && row.form === target.form && row.locale === target.locale && match && `@${match[1]}` === target.account_id;
  });
  const seenUrls = new Set(); const seenProviderIds = new Set();
  return candidates.filter((row) => {
    if (seenUrls.has(row.public_url) || seenProviderIds.has(row.provider_id)) return false;
    seenUrls.add(row.public_url); seenProviderIds.add(row.provider_id); return true;
  }).map((row) => {
    const match = /\/video\/(\d+)/.exec(row.public_url); const captionPath = path.resolve(String(row.caption_path || ""));
    if (row.format_id !== target.format_id || row.form !== target.form || row.locale !== target.locale || !/^c[a-z0-9]+$/.test(String(row.provider_id || "")) || !fs.statSync(captionPath, { throwIfNoEntry: false })?.isFile() || !Number.isFinite(Date.parse(row.ts))) throw new Error(`${target.account_id} verified distribution row invalid`);
    const bytes = fs.readFileSync(captionPath); if (crypto.createHash("sha256").update(bytes).digest("hex") !== row.caption_sha256) throw new Error(`${target.account_id} caption object integrity mismatch`);
    return Object.freeze({ tenant_id: "dais-local", product_id: target.product_id, locale: target.locale, account_id: target.account_id, native_owner: target.native_owner, integration_id: target.integration_id,
      provider_post_id: row.provider_id, shortcode: match[1], video_id: match[1], public_url: row.public_url, caption: bytes.toString("utf8"), published_at: row.ts });
  });
}

function discoverNativeCarouselTargets(dataDir, nowMs = null) {
  const file = path.join(dataDir, "tenants", "dais-local", "marketing", "native-carousel-publication", "anicca-ios", "distribution.jsonl");
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, "utf8").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line))
    .flatMap((row) => {
      const receipt = row && row.receipt;
      if (!receipt || receipt.kind !== "marketing_native_carousel_distribution" || receipt.platform !== "tiktok") return [];
      const publishedMs = Date.parse(String(receipt.published_at || ""));
      const retainedWindowMs = WINDOWS["7d"] + GRACE_MS;
      if (Number.isFinite(nowMs) && Number.isFinite(publishedMs) && nowMs - publishedMs > retainedWindowMs) return [];
      if (!verifyMarketingNativeCarouselPublicationReceipt(receipt)) throw new Error("TikTok native carousel receipt invalid");
      const integration = /^integration:\/\/postiz\/tiktok\/([A-Za-z0-9._:-]+)$/.exec(String(receipt.integration_ref || ""));
      if (!integration) throw new Error("TikTok native carousel integration identity invalid");
      const captionPath = path.join(dataDir, "objects", "sha256", receipt.caption_sha256);
      const captionStat = fs.lstatSync(captionPath, { throwIfNoEntry: false });
      if (!captionStat?.isFile() || (captionStat.mode & 0o077) !== 0) throw new Error("TikTok native carousel caption object invalid");
      const captionBytes = fs.readFileSync(captionPath);
      if (crypto.createHash("sha256").update(captionBytes).digest("hex") !== receipt.caption_sha256) throw new Error("TikTok native carousel caption object integrity mismatch");
      const photoOnly = receipt.public_url == null;
      const direct = /^https:\/\/www\.tiktok\.com\/@([^/]+)\/video\/(\d+)\/?$/.exec(String(receipt.public_url || ""));
      if (!photoOnly && (!direct || `@${direct[1]}` !== receipt.account_id)) throw new Error("TikTok native carousel public URL identity invalid");
      const providerPostId = receipt.provider_post_id;
      return [Object.freeze({
        tenant_id: "dais-local",
        product_id: receipt.product_id,
        locale: receipt.locale,
        account_id: receipt.account_id,
        native_owner: receipt.account_id.replace(/^@/, ""),
        integration_id: integration[1],
        provider_post_id: providerPostId,
        shortcode: photoOnly ? providerPostId : direct[2],
        video_id: photoOnly ? providerPostId : direct[2],
        public_url: photoOnly ? "unavailable" : receipt.public_url,
        caption: captionBytes.toString("utf8"),
        published_at: receipt.published_at,
        ...(photoOnly ? { postiz_photo_only: true } : {}),
      })];
    });
}

function discoverJp4(dataDir) { return discoverTarget(dataDir, TARGETS[0]); }
function discoverTargets(dataDir, nowMs = null) {
  const candidates = TARGETS.flatMap((target) => discoverTarget(dataDir, target))
    .concat(discoverNativeCarouselTargets(dataDir, nowMs));
  const discovered = new Map();
  for (const row of candidates) {
    const key = `${row.integration_id}:${row.provider_post_id}`;
    const existing = discovered.get(key);
    if (!existing) {
      discovered.set(key, row);
      continue;
    }
    for (const field of ["product_id", "locale", "account_id", "native_owner", "public_url", "published_at", "caption"]) {
      if (existing[field] !== row[field]) throw new Error("TikTok metric publication identity conflict");
    }
  }
  return [...discovered.values()];
}

function snapshotFile(dataDir, expected, window) { return path.join(dataDir, "tenants", expected.tenant_id, "marketing", "metrics", expected.native_owner, expected.shortcode, `${window}.combined.json`); }

function delayed(dataDir, expected, window, observedAt) {
  const unavailable = { status: "unavailable", value: null, reason: "source_delayed" };
  const post = Object.fromEntries(["views", "likes", "comments", "shares", "saves", "reach", "watch_time", "completion", "engagement"].map((key) => [key, { ...unavailable }]));
  const snapshot = { schema_version: 1, kind: "tiktok_combined_metric_snapshot", ...expected, window, observed_at: observedAt,
    caption_sha256: crypto.createHash("sha256").update(expected.caption).digest("hex"), sources: { tiktok_native: { status: "unavailable", reason: "source_delayed", identity_verified: true }, postiz_post: { status: "unavailable", reason: "source_delayed" }, postiz_account: { status: "unavailable", reason: "source_delayed" } }, post, account_metrics: { status: "unavailable", reason: "source_delayed" } };
  const file = snapshotFile(dataDir, expected, window); fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  if (fs.existsSync(file)) return { created: false, file, snapshot: JSON.parse(fs.readFileSync(file, "utf8")) };
  const temporary = `${file}.tmp-${process.pid}-${crypto.randomUUID()}`; fs.writeFileSync(temporary, `${JSON.stringify(snapshot, null, 2)}\n`, { mode: 0o600, flag: "wx" }); fs.renameSync(temporary, file); fs.chmodSync(file, 0o600);
  return { created: true, file, snapshot };
}

async function runDue(nowMs = Date.now(), env = process.env, provided = null) {
  const dataDir = resolveDataRoot(env); const results = []; const expecteds = provided || discoverTargets(dataDir, nowMs);
  const reportParts = Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(nowMs)).map(({ type, value }) => [type, value])); const reportDay = `${reportParts.year}-${reportParts.month}-${reportParts.day}`;
  if (Number(reportParts.hour) >= 22 && !provided) { const asc = await persistAscAcquisition(dataDir, reportDay); results.push({ product_id: "mobile-marketing", window: "asc-daily", state: asc.created ? "measured" : "complete", snapshot_ref: asc.snapshot_ref }); const revenuecat = persistRevenueCatSubscriptions(dataDir, reportDay, new Date(nowMs).toISOString()); results.push({ product_id: "mobile-marketing", window: "revenuecat-daily", state: revenuecat.created ? "observed" : "complete", snapshot_ref: revenuecat.snapshot_ref }); const coverage = persistAttributionCoverage(dataDir, reportDay, new Date(nowMs).toISOString()); results.push({ product_id: "mobile-marketing", window: "attribution-daily", state: coverage.created ? "reported" : "complete", telegram: await sendSummary(coverage, env, dataDir), snapshot_ref: coverage.snapshot.snapshot_ref }); const weekly = persistWeeklyReview(dataDir, reportDay, new Date(nowMs).toISOString()); results.push({ product_id: "mobile-marketing", window: "weekly-product", state: weekly.created ? "reported" : "complete", telegram: await sendSummary(weekly, env, dataDir) }); }
  for (const expected of expecteds) {
    for (const [window, delay] of Object.entries(WINDOWS)) {
      const existingFile = snapshotFile(dataDir, expected, window);
      if (fs.existsSync(existingFile)) { const snapshot = JSON.parse(fs.readFileSync(existingFile, "utf8")); results.push({ video_id: expected.video_id, window, state: "complete", telegram: await sendMetricSnapshot({ created: true, file: existingFile, snapshot }, env, dataDir) }); continue; }
      const dueMs = Date.parse(expected.published_at) + delay;
      if (nowMs < dueMs) { results.push({ video_id: expected.video_id, window, state: "pending", due_at: new Date(dueMs).toISOString() }); continue; }
      if (nowMs > dueMs + GRACE_MS) { const snapshot = delayed(dataDir, expected, window, new Date(nowMs).toISOString()); results.push({ video_id: expected.video_id, window, state: "source_delayed", telegram: await sendMetricSnapshot(snapshot, env, dataDir) }); continue; }
      const input = { tenantId: expected.tenant_id, productId: expected.product_id, locale: expected.locale, account: expected.account_id, integrationId: expected.integration_id, providerPostId: expected.provider_post_id, videoId: expected.video_id, publicUrl: expected.public_url, caption: expected.caption, window, publishedAt: expected.published_at };
      // One deleted/unavailable post ("item doesn't exist", live 2026-09-30) used to throw and stop every other
      // account's metrics since 9/27. Record it like the source_delayed branch above and keep going.
      let observation;
      try { observation = await (expected.postiz_photo_only ? collectPostizPhotoWindow : collectTikTokWindow)(input, env, new Date(nowMs).toISOString()); }
      catch (error) { results.push({ video_id: expected.video_id, window, state: "source_unavailable", error: String(error.message || error).slice(0, 200) }); continue; }
      if (observation?.deferred === true) {
        results.push({ video_id: expected.video_id, window, state: "pending", reason: observation.reason || "source_delayed" });
        continue;
      }
      results.push({ video_id: expected.video_id, window, state: "measured", telegram: await sendMetricSnapshot(observation, env, dataDir) });
    }
    const parts = Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(nowMs)).map(({ type, value }) => [type, value])); const reportDay = `${parts.year}-${parts.month}-${parts.day}`;
    if (Number(parts.hour) > 17 || (Number(parts.hour) === 17 && Number(parts.minute) >= 30)) { const digest = persistDailyDigest({ dataDir, reportDay, observedAt: new Date(nowMs).toISOString(), expected }); results.push({ video_id: expected.video_id, window: "daily", state: digest.created ? "reported" : "complete", telegram: await sendMetricSnapshot(digest, env, dataDir) }); }
    else results.push({ video_id: expected.video_id, window: "daily", state: "pending", due_at: `${reportDay}T17:30:00+09:00` });
  }
  if (Number(reportParts.hour) >= 22 && !provided) {
    for (const [productId, persist] of [["honne-ai", persistHonneDaily], ["anicca-ios", persistAniccaDaily]]) { const summary = persist(dataDir, reportDay, new Date(nowMs).toISOString()); results.push({ product_id: productId, window: "daily-product", state: summary.created ? "reported" : "complete", telegram: await sendSummary(summary, env, dataDir) }); }
  }
  return results;
}

if (require.main === module) runDue().then((result) => process.stdout.write(`${JSON.stringify(result)}\n`)).catch((error) => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
module.exports = { GRACE_MS, TARGETS, WINDOWS, delayed, discoverJp4, discoverNativeCarouselTargets, discoverTarget, discoverTargets, runDue, snapshotFile };
