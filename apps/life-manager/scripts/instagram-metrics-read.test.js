"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { EXPECTED, collectWindow, effectiveSnapshotFile, loadLocalTelegramCredentials, metricPlatform, persistDailyDigest, persistDelayedSnapshot, persistHistoricalCheckpointCorrection, persistSnapshot, postMetrics } = require("./instagram-metrics-read.js");

const html = `<link rel="canonical" href="${EXPECTED.public_url}" /><meta property="og:description" content="0 likes - ${EXPECTED.native_owner}: &quot;強い人の口癖、5つだけ #anicca #セルフケア #習慣 #AI&quot;" />`;
const postRows = [["Views", 32], ["Reach", 31], ["Saves", 0], ["Likes", 0], ["Comments", 0], ["Shares", 0]].map(([label, total]) => ({ label, data: [{ total: String(total) }] }));

test("metric reports select the exact local Life Manager Telegram credential", () => {
  assert.equal(typeof loadLocalTelegramCredentials, "function");
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "lm-local-telegram-"));
  const file = path.join(home, ".local", "share", "anicca", "credentials.json");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify({ credentials: [
    { service: "telegram-life-manager", bot_token: "local-token", chat_id: "local-chat" },
    { service: "telegram-cloud-life-manager", bot_token: "cloud-token", chat_id: "cloud-chat" },
  ] }));
  assert.deepEqual(loadLocalTelegramCredentials({ HOME: home, LM_TELEGRAM_BOT_TOKEN: "cloud-token", LM_TELEGRAM_ALERT_CHAT_ID: "cloud-chat" }), {
    botToken: "local-token",
    chatId: "local-chat",
  });
  fs.rmSync(home, { recursive: true, force: true });
});

test("metric reports fail closed when only the cloud Telegram credential exists", () => {
  assert.equal(typeof loadLocalTelegramCredentials, "function");
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "lm-local-telegram-"));
  const file = path.join(home, ".local", "share", "anicca", "credentials.json");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify({ credentials: [
    { service: "telegram-cloud-life-manager", bot_token: "cloud-token", chat_id: "cloud-chat" },
  ] }));
  assert.throws(() => loadLocalTelegramCredentials({ HOME: home, LM_TELEGRAM_BOT_TOKEN: "cloud-token", LM_TELEGRAM_ALERT_CHAT_ID: "cloud-chat" }), /local_telegram_credential_unavailable/);
  fs.rmSync(home, { recursive: true, force: true });
});

test("missing local Telegram credentials do not persist a snapshot without its notification intent", async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-no-telegram-"));
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-no-credentials-"));
  const originalFetch = global.fetch;
  global.fetch = async () => ({ ok: true, text: async () => html, json: async () => [] });
  try {
    await assert.rejects(
      collectWindow("24h", { HOME: home, LM_DATA_DIR: dataDir, LM_POSTIZ_API_KEY: "postiz-test" }, "2026-10-15T01:00:00.000Z"),
      /local_telegram_credential_unavailable/,
    );
    assert.equal(fs.existsSync(effectiveSnapshotFile(dataDir, "24h")), false);
  } finally {
    global.fetch = originalFetch;
    fs.rmSync(dataDir, { recursive: true, force: true });
    fs.rmSync(home, { recursive: true, force: true });
  }
});

test("current Instagram observation recovers live values without rewriting missed historical checkpoints", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-current-"));
  const historical = persistDelayedSnapshot({ dataDir, window: "7d", observedAt: "2026-10-11T05:13:08.332Z" });
  const priorBytes = fs.readFileSync(historical.file);
  const input = { dataDir, window: "current", observedAt: "2026-10-11T07:53:00.000Z", html, accountRows: [], postRows };
  const current = persistSnapshot(input);
  assert.equal(current.created, true);
  assert.equal(current.snapshot.post.views.value, 32);
  assert.equal(current.snapshot.historical_checkpoint, false);
  assert.match(current.file, /current\/2026-10-11\.combined\.json$/);
  assert.deepEqual(fs.readFileSync(historical.file), priorBytes);
  assert.equal(persistSnapshot({ ...input, observedAt: "2026-10-11T08:00:00.000Z" }).created, false);
  const digest = persistDailyDigest({ dataDir, reportDay: "2026-10-11", observedAt: input.observedAt });
  assert.equal(digest.snapshot.post.views.value, 32);
  assert.equal(digest.snapshot.historical_checkpoint, false);
});

test("missing Instagram metrics are never coerced to zero or used as an engagement numerator", () => {
  const partial = postMetrics([{ label: "Views", data: [{ total: "2229" }] }, { label: "Likes", data: [{ total: null }] }]);
  assert.equal(partial.likes.value, null);
  assert.equal(partial.likes.status, "unavailable");
  assert.equal(partial.engagement.status, "unavailable");
  assert.equal(partial.engagement.reason, "engagement_input_missing");
});

test("a historical measured daily report can receive exactly one current-value correction", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-measured-correction-"));
  persistSnapshot({ dataDir, window: "2h", observedAt: "2026-10-11T07:00:00.000Z", html, accountRows: [], postRows });
  const first = persistDailyDigest({ dataDir, reportDay: "2026-10-11", observedAt: "2026-10-11T08:30:00.000Z" });
  const bytes = fs.readFileSync(first.file);
  const freshRows = postRows.map((row) => row.label === "Views" ? { label: "Views", data: [{ total: "2229" }] } : row);
  persistSnapshot({ dataDir, window: "current", observedAt: "2026-10-11T09:00:00.000Z", html, accountRows: [], postRows: freshRows });
  const correction = persistDailyDigest({ dataDir, reportDay: "2026-10-11", observedAt: "2026-10-11T09:00:00.000Z" });
  assert.equal(correction.created, true);
  assert.match(correction.file, /\.correction\.json$/);
  assert.equal(correction.snapshot.post.views.value, 2229);
  assert.equal(correction.snapshot.source_observed_at, "2026-10-11T09:00:00.000Z");
  assert.deepEqual(fs.readFileSync(first.file), bytes);
  assert.equal(persistDailyDigest({ dataDir, reportDay: "2026-10-11", observedAt: "2026-10-11T10:00:00.000Z" }).created, false);
});

function writeDdvxhMetricFixture(dataDir, metricRows = null) {
  const expected = {
    ...EXPECTED,
    locale: "en",
    account_id: "@anicca.en",
    native_owner: "anicca.en",
    integration_id: "cmn8y95rg02d2qx0y09bbk5pb",
    provider_post_id: "cmui7zo8n0ixho80yybalkhj0",
    shortcode: "DdvxhT1jm8F",
    public_url: "https://www.instagram.com/reel/DdvxhT1jm8F/",
    published_at: "2026-09-26T10:02:41.890420Z",
  };
  const metric = {
    observed_at: "2026-10-03T10:02:54Z", published_at: "2026-09-26T10:01:00.000Z",
    product_id: "anicca-ios", platform: "instagram", integration_id: expected.integration_id,
    postiz_id: expected.provider_post_id, native_post_id: "18112495088019182", native_url: expected.public_url,
    target_age_hours: 168, observed_age_hours: 168.0317, checkpoint_status: "measured", checkpoint_sla_status: "in_window",
    views: 2229, reach: 1610, saves: 3, likes: 1, comments: 0, shares: 0, impressions: null,
    metric_null_reasons: { impressions: "provider_field_missing" },
    raw_evidence_hash: "4adaa1eb4e57c8d3f6d95ef7bcd4bdaa868cd8374b0c97fbeb3f0a86a71779f5",
    snapshot_id: "228aca83e0a54abdac63957c1c349eabc23a6147b9f0e242bea381e165c283d0",
    source: "postiz_instagram_graph_api",
  };
  const identity = {
    observed_at: "2026-10-04T09:44:01Z", publish_date: "2026-09-26T10:01:00.000Z",
    account_id: "instagram.anicca_en", platform: "instagram-standalone", product_id: "anicca-ios",
    integration_id: expected.integration_id, postiz_post_id: expected.provider_post_id,
    native_post_id: "18112495088019182", native_post_url: expected.public_url,
    postiz_state: "PUBLISHED", identity_status: "resolved", resolution_method: "postiz_provider_native_receipt",
  };
  const metricsFile = path.join(dataDir, "marketing-owner-events", "state", "post-metrics.jsonl");
  const identitiesFile = path.join(dataDir, "state", "publication-identity.jsonl");
  fs.mkdirSync(path.dirname(metricsFile), { recursive: true }); fs.mkdirSync(path.dirname(identitiesFile), { recursive: true });
  fs.writeFileSync(metricsFile, `${(metricRows || [metric]).map((row) => JSON.stringify(row)).join("\n")}\n`);
  fs.writeFileSync(identitiesFile, `${JSON.stringify(identity)}\n`);
  const missed = persistDelayedSnapshot({ dataDir, window: "7d", observedAt: "2026-10-11T05:13:08.332Z", expected });
  return { expected, metric, missed, missedBytes: fs.readFileSync(missed.file) };
}

test("a missed 7d snapshot is corrected from one exact measured Postiz checkpoint without rewriting the original", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-7d-ledger-correction-"));
  const { expected, metric, missed, missedBytes } = writeDdvxhMetricFixture(dataDir);
  const historical = persistHistoricalCheckpointCorrection({ dataDir, expected, correctionCreatedAt: "2026-10-14T06:30:00.000Z" });
  assert.equal(historical.created, true, historical.reason);
  const daily = persistDailyDigest({ dataDir, reportDay: "2026-10-14", observedAt: "2026-10-14T06:30:00.000Z", expected });
  const correctionFile = path.join(path.dirname(missed.file), "7d.correction.json");
  assert.equal(fs.existsSync(correctionFile), true);
  const correction = JSON.parse(fs.readFileSync(correctionFile, "utf8"));
  assert.equal(correction.window, "7d");
  assert.equal(correction.observed_at, metric.observed_at);
  assert.equal(correction.correction, true);
  assert.deepEqual([correction.post.views.value, correction.post.reach.value, correction.post.saves.value, correction.post.likes.value], [2229, 1610, 3, 1]);
  assert.equal(correction.post.impressions.status, "unavailable");
  assert.equal(correction.post.impressions.reason, "provider_field_missing");
  assert.equal(correction.post.watch_time.reason, "metric_not_supported");
  assert.equal(correction.post.engagement.percent, 0.18);
  assert.equal(correction.checkpoint_published_at, "2026-09-26T10:01:00.000Z");
  assert.equal(correction.sources.instagram_native.status, "unavailable");
  assert.equal(correction.sources.postiz_post.status, "measured");
  assert.equal(correction.account_metrics.status, "unavailable");
  assert.deepEqual(fs.readFileSync(missed.file), missedBytes);
  assert.equal(daily.snapshot.historical_checkpoint_correction.source_snapshot_id, metric.snapshot_id);
  assert.equal(daily.snapshot.historical_checkpoint_correction.observed_at, metric.observed_at);
});

test("ambiguous normalized rows do not correct a delayed 7d checkpoint", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-7d-ledger-ambiguous-"));
  const first = writeDdvxhMetricFixture(dataDir);
  const duplicate = { ...first.metric, views: 2228 };
  fs.writeFileSync(path.join(dataDir, "marketing-owner-events", "state", "post-metrics.jsonl"), `${JSON.stringify(first.metric)}\n${JSON.stringify(duplicate)}\n`);
  const daily = persistDailyDigest({ dataDir, reportDay: "2026-10-14", observedAt: "2026-10-14T06:30:00.000Z", expected: first.expected });
  assert.equal(fs.existsSync(path.join(path.dirname(first.missed.file), "7d.correction.json")), false);
  assert.deepEqual(fs.readFileSync(first.missed.file), first.missedBytes);
  assert.equal(daily.snapshot.post.views.status, "unavailable");
  assert.equal(daily.snapshot.historical_checkpoint_correction, undefined);
});

test("publication timestamp skew beyond three minutes leaves the delayed checkpoint unavailable", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-7d-ledger-skew-"));
  const { expected, metric, missed, missedBytes } = writeDdvxhMetricFixture(dataDir);
  const outsideWindow = { ...metric, published_at: "2026-09-26T09:59:00.000Z", observed_age_hours: 168.065 };
  fs.writeFileSync(path.join(dataDir, "marketing-owner-events", "state", "post-metrics.jsonl"), `${JSON.stringify(outsideWindow)}\n`);
  const identityFile = path.join(dataDir, "state", "publication-identity.jsonl");
  const identity = JSON.parse(fs.readFileSync(identityFile, "utf8"));
  identity.publish_date = outsideWindow.published_at;
  fs.writeFileSync(identityFile, `${JSON.stringify(identity)}\n`);
  const daily = persistDailyDigest({ dataDir, reportDay: "2026-10-14", observedAt: "2026-10-14T06:30:00.000Z", expected });
  assert.equal(fs.existsSync(path.join(path.dirname(missed.file), "7d.correction.json")), false);
  assert.deepEqual(fs.readFileSync(missed.file), missedBytes);
  assert.equal(daily.snapshot.historical_checkpoint_correction, undefined);
});

test("URL-free Postiz photo snapshots remain TikTok metrics", () => {
  assert.equal(metricPlatform({ kind: "tiktok_postiz_photo_metric_snapshot", public_url: "unavailable" }), "tiktok");
  assert.equal(metricPlatform({ kind: "instagram_combined_metric_snapshot", public_url: "https://www.instagram.com/reel/ABC/" }), "instagram");
});

test("Instagram snapshot binds native content, preserves unavailable, and replays", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-metrics-"));
  const input = { dataDir, window: "24h", observedAt: "2026-08-22T12:00:00.000Z", html, accountRows: [], postRows };
  const first = persistSnapshot(input); const replay = persistSnapshot({ ...input, observedAt: "2026-08-22T13:00:00.000Z" });
  assert.equal(first.created, true); assert.equal(replay.created, false);
  assert.equal(first.snapshot.post.views.value, 32); assert.equal(first.snapshot.post.reach.value, 31);
  assert.equal(first.snapshot.post.watch_time.status, "unavailable"); assert.equal(first.snapshot.sources.postiz_account.status, "unavailable");
  assert.equal(fs.statSync(first.file).mode & 0o777, 0o600);
  assert.throws(() => persistSnapshot({ ...input, dataDir: fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-metrics-")), html: html.replace(EXPECTED.native_owner, "wrong") }), /mismatch/i);
});

test("daily digest preserves a sent unavailable report and writes one measured correction", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-daily-correction-")); const expected = { ...EXPECTED, native_owner: "honnevideo", shortcode: "123", public_url: "https://www.tiktok.com/@honnevideo/video/123", account_id: "@honnevideo", product_id: "honne-ai", locale: "ja" };
  const directory = path.join(dataDir, "tenants", expected.tenant_id, "marketing", "metrics", expected.native_owner, expected.shortcode); fs.mkdirSync(directory, { recursive: true });
  const base = { ...expected, sources: { postiz_post: { status: "unavailable" } }, post: { views: { status: "unavailable" } }, account_metrics: { status: "unavailable" } };
  fs.writeFileSync(path.join(directory, "2h.combined.json"), JSON.stringify({ ...base, window: "2h" })); const first = persistDailyDigest({ dataDir, reportDay: "2026-08-22", observedAt: "2026-08-22T09:00:00.000Z", expected }); assert.equal(first.created, true); assert.equal(first.snapshot.post.views.status, "unavailable");
  fs.writeFileSync(path.join(directory, "24h.combined.json"), JSON.stringify({ ...base, window: "24h", post: { views: { status: "measured", value: 1035 } } })); const correction = persistDailyDigest({ dataDir, reportDay: "2026-08-22", observedAt: "2026-08-22T10:00:00.000Z", expected }); assert.equal(correction.created, true); assert.match(correction.file, /\.correction\.json$/); assert.equal(correction.snapshot.kind, "tiktok_daily_metric_digest_correction"); assert.equal(correction.snapshot.post.views.value, 1035); assert.deepEqual(correction.snapshot.observation_windows.slice(0, 2), [{ window: "2h", status: "unavailable" }, { window: "24h", status: "measured" }]); assert.equal(persistDailyDigest({ dataDir, reportDay: "2026-08-22", observedAt: "2026-08-22T11:00:00.000Z", expected }).created, false);
});
