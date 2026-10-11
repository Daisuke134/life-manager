"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { EXPECTED, metricPlatform, persistDailyDigest, persistDelayedSnapshot, persistSnapshot, postMetrics } = require("./instagram-metrics-read.js");

const html = `<link rel="canonical" href="${EXPECTED.public_url}" /><meta property="og:description" content="0 likes - ${EXPECTED.native_owner}: &quot;強い人の口癖、5つだけ #anicca #セルフケア #習慣 #AI&quot;" />`;
const postRows = [["Views", 32], ["Reach", 31], ["Saves", 0], ["Likes", 0], ["Comments", 0], ["Shares", 0]].map(([label, total]) => ({ label, data: [{ total: String(total) }] }));

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
