#!/usr/bin/env node
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { resolveDataRoot } = require("../lib/runtime-paths.js");
const {
  EN_AFFIRMATION_LANE,
  JA_LANE,
  verifyMarketingNativeCarouselPublicationReceipt,
} = require("../lib/marketing-native-carousel-publication-adapter.js");
const { EXPECTED, collectWindow, currentSnapshotFile, effectiveSnapshotFile, persistDailyDigest, persistDelayedSnapshot, persistHistoricalCheckpointCorrection } = require("./instagram-metrics-read.js");

const WINDOWS = Object.freeze({ "2h": 2 * 3600_000, "24h": 24 * 3600_000, "72h": 72 * 3600_000, "7d": 7 * 86400_000 });
const GRACE_MS = 90 * 60_000;
const MAX_POST_AGE_MS = 30 * 86400_000;
const VIDEO_LANES = Object.freeze([
  Object.freeze({ format_id: "reelclaw-card", form: "nudge-card", locale: "ja", account_id: "@anicca.jp1", native_owner: "anicca.ios.jp", integration_id: "cmn8ycvtn02djqx0ytuisn9mw" }),
  Object.freeze({ format_id: "reelclaw-card", form: "nudge-card", locale: "en", account_id: "@anicca.encards", native_owner: "anicca.encards", integration_id: "cmpc3gx4001nklg0y27a8o66q" }),
  Object.freeze({ format_id: "reelclaw-widget", form: "lockscreen-affirmation-widget", locale: "en", account_id: "@anicca.en", native_owner: "anicca.en", integration_id: "cmn8y95rg02d2qx0y09bbk5pb" }),
  Object.freeze({ format_id: "reelclaw-widget", form: "lockscreen-affirmation-widget", locale: "ja", account_id: "@anicca.jp.videos", native_owner: "anicca.jp.videos", integration_id: "cmmzzg2es0539p30ycb94ayx0" }),
  Object.freeze({ format_id: "watercolor", form: "buddhist-self-care-reel", locale: "ja", creative_id: "JA-WATERCOLOR-OBOU-b2772de4303a", video_sha256: "b2772de4303acc901f42b43a0b3f4af166ae3daeb5ee7fd24e090e5b62f2b0e8", account_id: "@obou.anicca", native_owner: "obou.anicca", integration_id: "cmooplxmu04tpmd0y4h3cpk33" }),
]);
const NATIVE_CAROUSEL_LANES = Object.freeze([EN_AFFIRMATION_LANE, JA_LANE]);

function snapshotFile(dataDir, window, expected = EXPECTED) {
  return effectiveSnapshotFile(dataDir, window, expected);
}

function discoverExpected(dataDir) {
  const file = path.join(dataDir, "tenants", "dais-local", "marketing", "video-publication", "anicca-ios", "distribution.jsonl");
  const rows = fs.existsSync(file) ? fs.readFileSync(file, "utf8").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line)) : [];
  const found = [];
  for (const row of rows) {
    if (row.platform !== "instagram" || row.status !== "published" || row.provider_reconciled !== true) continue;
    const lane = VIDEO_LANES.find((candidate) => candidate.format_id === row.format_id && candidate.form === row.form && candidate.locale === row.locale
      && (candidate.creative_id === undefined || candidate.creative_id === row.creative_id)
      && (candidate.video_sha256 === undefined || candidate.video_sha256 === row.video_sha256));
    if (!lane) continue;
    const match = /^https:\/\/www\.instagram\.com\/reel\/([A-Za-z0-9_-]+)\/$/.exec(String(row.public_url || ""));
    const captionPath = path.resolve(String(row.caption_path || ""));
    if (!match || !/^c[a-z0-9]+$/.test(String(row.provider_id || "")) || !fs.statSync(captionPath, { throwIfNoEntry: false })?.isFile() || !Number.isFinite(Date.parse(row.ts))) throw new Error("Instagram verified distribution row invalid");
    const caption = fs.readFileSync(captionPath, "utf8");
    if (crypto.createHash("sha256").update(fs.readFileSync(captionPath)).digest("hex") !== row.caption_sha256) throw new Error("Instagram caption object integrity mismatch");
    found.push(Object.freeze({ tenant_id: "dais-local", product_id: "anicca-ios", locale: lane.locale, account_id: lane.account_id, native_owner: lane.native_owner,
      format_id: lane.format_id, form: lane.form,
      ...(row.creative_id ? { creative_id: row.creative_id } : {}),
      integration_id: lane.integration_id, provider_post_id: row.provider_id, shortcode: match[1], public_url: row.public_url, caption, published_at: row.ts }));
  }
  const carouselFile = path.join(dataDir, "tenants", "dais-local", "marketing", "native-carousel-publication", "anicca-ios", "distribution.jsonl");
  const carouselRows = fs.existsSync(carouselFile) ? fs.readFileSync(carouselFile, "utf8").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line)) : [];
  for (const row of carouselRows) {
    const receipt = row && row.receipt;
    if (!receipt) continue;
    const lane = NATIVE_CAROUSEL_LANES.find((candidate) => candidate.integrationRef === receipt.integration_ref);
    if (!lane) continue;
    if (!verifyMarketingNativeCarouselPublicationReceipt(receipt)) throw new Error("Instagram native carousel receipt invalid");
    const match = /^https:\/\/www\.instagram\.com\/p\/([A-Za-z0-9_-]+)\/$/.exec(String(receipt.public_url || ""));
    const integration = /^integration:\/\/postiz\/instagram\/([A-Za-z0-9._:-]+)$/.exec(String(receipt.integration_ref || ""));
    const captionPath = path.join(dataDir, "objects", "sha256", String(receipt.caption_sha256 || ""));
    const captionStat = fs.statSync(captionPath, { throwIfNoEntry: false });
    if (!match || !integration || !/^c[a-z0-9]+$/.test(String(receipt.provider_post_id || ""))
      || !captionStat?.isFile() || (captionStat.mode & 0o077) !== 0 || !Number.isFinite(Date.parse(receipt.published_at))) {
      throw new Error("Instagram verified native carousel row invalid");
    }
    const captionBytes = fs.readFileSync(captionPath);
    if (crypto.createHash("sha256").update(captionBytes).digest("hex") !== receipt.caption_sha256) throw new Error("Instagram caption object integrity mismatch");
    found.push(Object.freeze({ tenant_id: "dais-local", product_id: receipt.product_id, locale: receipt.locale, account_id: receipt.account_id,
      format_id: receipt.format_id, form: receipt.form,
      creative_id: receipt.creative_id,
      native_owner: lane.nativeOwner.replace(/^@/, ""), integration_id: integration[1], provider_post_id: receipt.provider_post_id,
      shortcode: match[1], public_url: receipt.public_url, caption: captionBytes.toString("utf8"), published_at: receipt.published_at }));
  }
  const identities = new Set(found.map((row) => `${row.shortcode}\n${row.provider_post_id}`));
  if (identities.size !== found.length) throw new Error("Instagram verified distribution rows ambiguous");
  return found.sort((left, right) => left.published_at.localeCompare(right.published_at));
}

async function runDue(nowMs = Date.now(), env = process.env, provided = null, deps = {}) {
  const dataDir = resolveDataRoot(env); const results = [];
  if (!Number.isFinite(nowMs)) throw new Error("Instagram metrics due clock invalid");
  const expecteds = (provided || discoverExpected(dataDir)).filter((expected) => {
    const publishedMs = Date.parse(expected.published_at);
    return Number.isFinite(publishedMs) && nowMs >= publishedMs && nowMs - publishedMs <= MAX_POST_AGE_MS;
  });
  const collect = deps.collectWindow || collectWindow;
  const currentEligible = expecteds.filter((expected) => nowMs >= Date.parse(expected.published_at) && nowMs - Date.parse(expected.published_at) <= MAX_POST_AGE_MS);
  const currentStart = currentEligible.length ? (Math.floor(nowMs / 1800_000) * 8) % currentEligible.length : 0;
  const currentTargets = new Set(Array.from({ length: Math.min(8, currentEligible.length) }, (_, i) => currentEligible[(currentStart + i) % currentEligible.length]));
  let currentReads = 0;
  for (const expected of expecteds) {
    const publishedMs = Date.parse(expected.published_at);
    for (const [window, delay] of Object.entries(WINDOWS)) {
      if (window === "7d") persistHistoricalCheckpointCorrection({ dataDir, expected, correctionCreatedAt: new Date(nowMs).toISOString() });
      const existingSnapshotFile = snapshotFile(dataDir, window, expected);
      if (fs.existsSync(existingSnapshotFile)) {
        const snapshot = JSON.parse(fs.readFileSync(existingSnapshotFile, "utf8"));
        const missed = snapshot.sources?.postiz_post?.reason === "source_delayed";
        results.push({ shortcode: expected.shortcode, window, state: snapshot.correction === true ? "corrected" : missed ? "checkpoint_missed" : "complete" }); continue;
      }
      const dueMs = publishedMs + delay;
      if (nowMs < dueMs) { results.push({ shortcode: expected.shortcode, window, state: "pending", due_at: new Date(dueMs).toISOString() }); continue; }
      if (nowMs > dueMs + GRACE_MS) {
        const snapshot = persistDelayedSnapshot({ dataDir, window, observedAt: new Date(nowMs).toISOString(), expected });
        results.push({ shortcode: expected.shortcode, window, state: "checkpoint_missed", created: snapshot.created }); continue;
      }
      const observation = await collect(window, env, new Date(nowMs).toISOString(), expected);
      results.push({ shortcode: expected.shortcode, window, state: "measured", telegram: observation.telegram });
    }
    const parts = Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(nowMs)).map(({ type, value }) => [type, value]));
    const reportDay = `${parts.year}-${parts.month}-${parts.day}`;
    // Keep missed checkpoints immutable; recover current values separately.
    // Bound each run and stop tracking old posts rather than growing work forever.
    if (nowMs >= publishedMs && nowMs - publishedMs <= 30 * 86400_000) {
      if (fs.existsSync(currentSnapshotFile(dataDir, reportDay, expected))) {
        results.push({ shortcode: expected.shortcode, window: "current", state: "complete" });
      } else if (currentReads < 8 && currentTargets.has(expected)) {
        currentReads += 1;
        try {
          const observation = await collect("current", env, new Date(nowMs).toISOString(), expected);
          results.push({ shortcode: expected.shortcode, window: "current", state: "measured", telegram: observation.telegram });
        } catch (error) {
          results.push({ shortcode: expected.shortcode, window: "current", state: "failed", error_class: error.name,
            reason: String(error.message).slice(0, 160), retryable: true, next_action: "retry_current_observation_next_run" });
        }
      } else results.push({ shortcode: expected.shortcode, window: "current", state: "pending", reason: "current_observation_run_budget" });
    }
    if (Number(parts.hour) > 17 || (Number(parts.hour) === 17 && Number(parts.minute) >= 30)) {
      try {
        const digest = persistDailyDigest({ dataDir, reportDay, observedAt: new Date(nowMs).toISOString(), expected });
        results.push({ shortcode: expected.shortcode, window: "daily", state: digest.created ? "persisted" : "complete" });
      } catch (error) {
        if (error?.message !== "Instagram daily digest has no metric snapshot") throw error;
        results.push({ shortcode: expected.shortcode, window: "daily", state: "pending", reason: "no_metric_snapshot" });
      }
    } else results.push({ shortcode: expected.shortcode, window: "daily", state: "pending", due_at: `${reportDay}T17:30:00+09:00` });
  }
  return results;
}

if (require.main === module) runDue().then((result) => process.stdout.write(`${JSON.stringify(result)}\n`)).catch((error) => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
module.exports = { GRACE_MS, WINDOWS, discoverExpected, runDue, snapshotFile };
