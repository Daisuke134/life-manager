#!/usr/bin/env node
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { createContentObjectStore } = require("../lib/content-object-store.js");
const { createMarketingLocalLedger } = require("../lib/marketing-local-ledger.js");
const { buildMarketingLivenessJob, executeMarketingLivenessJob } = require("../lib/marketing-liveness-adapter.js");
const { resolveDataRoot } = require("../lib/runtime-paths.js");
const { executeCapabilityJob } = require("./runtime-up.js");

const WINDOWS = new Set(["2h", "24h", "72h", "7d"]);
const EXPECTED = Object.freeze({
  tenant_id: "dais-local", product_id: "anicca-ios", locale: "ja",
  account_id: "@anicca.jp1", native_owner: "anicca.ios.jp",
  integration_id: "cmn8ycvtn02djqx0ytuisn9mw", provider_post_id: "cmt2sfjcx02bapj0ymsu4tapf",
  shortcode: "DcTFx_UjSio", public_url: "https://www.instagram.com/reel/DcTFx_UjSio/",
  caption: "強い人の口癖、5つだけ\n\n#anicca #セルフケア #習慣 #AI",
  published_at: "2026-08-21T10:10:15.268Z",
});

function metricPlatform(snapshot) {
  return String(snapshot.kind || "").startsWith("tiktok_")
    || /^https:\/\/www\.tiktok\.com\//.test(String(snapshot.public_url || ""))
    ? "tiktok"
    : "instagram";
}
const POST_LABELS = Object.freeze({ Views: "views", Reach: "reach", Saves: "saves", Likes: "likes", Comments: "comments", Shares: "shares" });

function decodeHtml(value) {
  return String(value).replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n))).replace(/&quot;/g, '"').replace(/&amp;/g, "&");
}

function normalize(value) { return String(value).normalize("NFKC").replace(/\s+/g, " ").trim(); }

function verifyNativeHtml(html, expected = EXPECTED) {
  const description = /<meta property="og:description" content="([^"]*)"/.exec(String(html))?.[1];
  const canonical = /<link rel="canonical" href="([^"]*)"/.exec(String(html))?.[1];
  const decoded = decodeHtml(description || "");
  if (canonical !== expected.public_url || !decoded.includes(expected.native_owner) || !normalize(decoded).includes(normalize(expected.caption))) {
    throw new Error("Instagram native URL, owner, or caption mismatch");
  }
  return { status: "measured", identity_verified: true, native_owner: expected.native_owner };
}

function measured(value, source) {
  const number = Number(value);
  if (!Number.isSafeInteger(number) || number < 0) throw new Error("Instagram metric invalid");
  return { status: "measured", value: number, source };
}

function postMetrics(rows) {
  if (!Array.isArray(rows)) throw new Error("Instagram post analytics invalid");
  const byLabel = new Map(rows.map((row) => [row?.label, row?.data?.[0]?.total]));
  const result = {};
  for (const [label, key] of Object.entries(POST_LABELS)) {
    result[key] = byLabel.has(label) ? measured(byLabel.get(label), "postiz_post_analytics") : { status: "unavailable", value: null, reason: "metric_missing" };
  }
  for (const key of ["impressions", "watch_time", "average_watch_time", "completion"]) result[key] = { status: "unavailable", value: null, reason: "metric_not_supported" };
  const numerator = result.likes.value + result.comments.value + result.shares.value + result.saves.value;
  result.engagement = result.views.value === 0 ? { status: "unavailable", value: null, reason: "zero_view_denominator" }
    : { status: "derived", numerator, denominator: result.views.value, rate: Number((numerator / result.views.value).toFixed(8)), percent: Number((numerator / result.views.value * 100).toFixed(2)), formula: "(likes+comments+shares+saves)/views" };
  return result;
}

function persistSnapshot({ dataDir, window, observedAt, html, accountRows, postRows, expected = EXPECTED }) {
  if (!WINDOWS.has(window) || !Number.isFinite(Date.parse(observedAt))) throw new Error("Instagram metric window invalid");
  const native = verifyNativeHtml(html, expected);
  const snapshot = {
    schema_version: 1, kind: "instagram_combined_metric_snapshot", ...expected,
    window, observed_at: observedAt, caption_sha256: crypto.createHash("sha256").update(expected.caption).digest("hex"),
    sources: { instagram_native: native, postiz_post: { status: "measured" }, postiz_account: Array.isArray(accountRows) && accountRows.length ? { status: "measured" } : { status: "unavailable", reason: "empty_response", response: "empty_array" } },
    post: postMetrics(postRows), account_metrics: Array.isArray(accountRows) && accountRows.length ? accountRows : { status: "unavailable", reason: "empty_response" },
  };
  const directory = path.join(path.resolve(dataDir), "tenants", expected.tenant_id, "marketing", "metrics", expected.native_owner, expected.shortcode);
  const file = path.join(directory, `${window}.combined.json`);
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  if (fs.existsSync(file)) {
    const existing = JSON.parse(fs.readFileSync(file, "utf8"));
    if (existing.public_url !== expected.public_url || existing.provider_post_id !== expected.provider_post_id || existing.caption_sha256 !== snapshot.caption_sha256) throw new Error("Instagram metric replay mismatch");
    return { created: false, file, snapshot: existing };
  }
  const temporary = `${file}.tmp-${process.pid}-${crypto.randomUUID()}`;
  fs.writeFileSync(temporary, `${JSON.stringify(snapshot, null, 2)}\n`, { mode: 0o600, flag: "wx" });
  fs.renameSync(temporary, file); fs.chmodSync(file, 0o600);
  return { created: true, file, snapshot };
}

function persistDelayedSnapshot({ dataDir, window, observedAt, expected = EXPECTED }) {
  if (!WINDOWS.has(window) || !Number.isFinite(Date.parse(observedAt))) throw new Error("Instagram delayed metric window invalid");
  const unavailable = (reason = "source_delayed") => ({ status: "unavailable", value: null, reason });
  const post = Object.fromEntries([...Object.values(POST_LABELS), "impressions", "watch_time", "average_watch_time", "completion", "engagement"].map((key) => [key, unavailable()]));
  const snapshot = { schema_version: 1, kind: "instagram_combined_metric_snapshot", ...expected, window, observed_at: observedAt,
    caption_sha256: crypto.createHash("sha256").update(expected.caption).digest("hex"),
    sources: { instagram_native: { status: "unavailable", reason: "source_delayed", identity_verified: true }, postiz_post: { status: "unavailable", reason: "source_delayed" }, postiz_account: { status: "unavailable", reason: "source_delayed" } },
    post, account_metrics: { status: "unavailable", reason: "source_delayed" } };
  const directory = path.join(path.resolve(dataDir), "tenants", expected.tenant_id, "marketing", "metrics", expected.native_owner, expected.shortcode);
  const file = path.join(directory, `${window}.combined.json`); fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  if (fs.existsSync(file)) return { created: false, file, snapshot: JSON.parse(fs.readFileSync(file, "utf8")) };
  const temporary = `${file}.tmp-${process.pid}-${crypto.randomUUID()}`;
  fs.writeFileSync(temporary, `${JSON.stringify(snapshot, null, 2)}\n`, { mode: 0o600, flag: "wx" }); fs.renameSync(temporary, file); fs.chmodSync(file, 0o600);
  return { created: true, file, snapshot };
}

function persistDailyDigest({ dataDir, reportDay, observedAt, expected = EXPECTED }) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(reportDay) || !Number.isFinite(Date.parse(observedAt))) throw new Error("Instagram daily digest identity invalid");
  const directory = path.join(path.resolve(dataDir), "tenants", expected.tenant_id, "marketing", "metrics", expected.native_owner, expected.shortcode);
  const rows = [...WINDOWS].map((window) => {
    const file = path.join(directory, `${window}.combined.json`);
    if (!fs.existsSync(file)) return { window, status: "pending" };
    const snapshot = JSON.parse(fs.readFileSync(file, "utf8")); const status = Object.values(snapshot.post || {}).some((metric) => metric?.status === "measured" || metric?.status === "derived") ? "measured" : "unavailable";
    return { window, status, file };
  });
  const source = rows.map((row) => row.file && JSON.parse(fs.readFileSync(row.file, "utf8"))).filter(Boolean)
    .find((snapshot) => Object.values(snapshot.post || {}).some((metric) => metric?.status === "measured" || metric?.status === "derived")) || rows.map((row) => row.file && JSON.parse(fs.readFileSync(row.file, "utf8"))).find(Boolean);
  if (!source) throw new Error("Instagram daily digest has no metric snapshot");
  const baseFile = path.join(directory, "daily", `${reportDay}.json`); const correctionFile = path.join(directory, "daily", `${reportDay}.correction.json`);
  if (fs.existsSync(correctionFile)) return { created: false, file: correctionFile, snapshot: JSON.parse(fs.readFileSync(correctionFile, "utf8")) };
  if (fs.existsSync(baseFile)) { const existing = JSON.parse(fs.readFileSync(baseFile, "utf8")); const existingMeasured = Object.values(existing.post || {}).some((metric) => metric?.status === "measured" || metric?.status === "derived"); const sourceMeasured = Object.values(source.post || {}).some((metric) => metric?.status === "measured" || metric?.status === "derived"); if (existingMeasured || !sourceMeasured) return { created: false, file: baseFile, snapshot: existing }; }
  const correction = fs.existsSync(baseFile); const file = correction ? correctionFile : baseFile;
  const snapshot = { ...source, kind: `${/^https:\/\/www\.tiktok\.com\//.test(source.public_url) ? "tiktok" : "instagram"}_daily_metric_digest${correction ? "_correction" : ""}`, window: "daily", observed_at: observedAt, report_day: reportDay,
    observation_windows: rows.map(({ window, status }) => ({ window, status })) };
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const temporary = `${file}.tmp-${process.pid}-${crypto.randomUUID()}`;
  fs.writeFileSync(temporary, `${JSON.stringify(snapshot, null, 2)}\n`, { mode: 0o600, flag: "wx" }); fs.renameSync(temporary, file); fs.chmodSync(file, 0o600);
  return { created: true, file, snapshot };
}

async function sendMetricSnapshot(result, env, dataDir) {
  if (!result.created) return { created: false, reason: "snapshot_replay" };
  const expected = result.snapshot;
  const platform = metricPlatform(expected);
  const lane = platform === "tiktok" ? `tiktok-metrics-${String(expected.account_id).replace(/^@/, "").replace(/[^A-Za-z0-9._-]/g, "-")}` : "anicca-main-ja-instagram";
  const objectStore = createContentObjectStore({ objectDir: path.join(dataDir, "objects") });
  const snapshotRef = objectStore.import(result.file).ref;
  const job = buildMarketingLivenessJob({
    tenantId: expected.tenant_id, telegramTokenRef: "secret://telegram/bot-token", telegramChatRef: "telegram-chat://owner",
    payload: { lane, product: expected.product_id, locale: expected.locale, platform, account: expected.account_id,
      status: "observed", window: result.snapshot.window, observed_at: result.snapshot.observed_at, public_url: expected.public_url, snapshot_ref: snapshotRef,
      ...(result.snapshot.kind === "tiktok_postiz_photo_metric_snapshot" ? { publication_evidence: "postiz_published_exact_assets" } : {}),
      ...(String(result.snapshot.kind || "").endsWith("_correction") ? { correction: true } : {}) },
  });
  const store = createMarketingLocalLedger({ dataDir });
  const queued = await store.enqueueJob({ jobId: job.job_id, tenantId: job.tenant_id, loopId: job.loop_id, capability: job.capability, effectClass: job.effect_class, effectKey: job.effect_key, inputRefs: job.input_refs, maxAttempts: job.max_attempts, availableAt: new Date().toISOString() });
  if (!queued.created) return { created: false, reason: "telegram_replay" };
  const claim = await store.claimJob({ tenantId: job.tenant_id, jobId: job.job_id, capability: job.capability, workerId: "instagram-metrics-read", leaseSeconds: 120 });
  if (!claim) throw new Error("Instagram metric Telegram job is not claimable");
  await executeCapabilityJob(claim, { workerId: "instagram-metrics-read", handlers: { [job.capability]: (claimed) => executeMarketingLivenessJob(claimed, {
    secretProvider: { get: async () => env.LM_TELEGRAM_BOT_TOKEN }, chatProvider: { get: async () => env.LM_TELEGRAM_ALERT_CHAT_ID },
    snapshotProvider: { get: async (_tenantId, ref) => JSON.parse(fs.readFileSync(objectStore.resolve(ref), "utf8")) },
  }) }, heartbeatJob: (input) => store.heartbeatJob(input), completeJob: (input) => store.completeJob(input), failJob: (input) => store.failJob(input), leaseSeconds: 120 });
  const receipt = await store.readReceipt({ tenantId: job.tenant_id, jobId: job.job_id });
  return { created: true, message_id: receipt?.message_id, snapshot_ref: snapshotRef };
}

async function collectWindow(window, env = process.env, observedAt = new Date().toISOString(), expected = EXPECTED) {
  const key = String(env.LM_POSTIZ_API_KEY || "").trim();
  if (!key) throw new Error("LM_POSTIZ_API_KEY is required");
  const get = async (url, headers = {}) => { const response = await fetch(url, { headers }); if (!response.ok) throw new Error(`Instagram metric HTTP ${response.status}`); return response; };
  const days = { "2h": 1, "24h": 1, "72h": 3, "7d": 7 }[window];
  if (!days) throw new Error("Instagram metric window invalid");
  const [page, account, post] = await Promise.all([
    get(expected.public_url).then((response) => response.text()),
    get(`https://api.postiz.com/public/v1/analytics/${expected.integration_id}?date=${days}`, { Authorization: key }).then((response) => response.json()),
    get(`https://api.postiz.com/public/v1/analytics/post/${expected.provider_post_id}?date=${days}`, { Authorization: key }).then((response) => response.json()),
  ]);
  const dataDir = resolveDataRoot(env);
  const result = persistSnapshot({ dataDir, window, observedAt, html: page, accountRows: account, postRows: post, expected });
  const telegram = await sendMetricSnapshot(result, env, dataDir);
  return { created: result.created, file: result.file, post: result.snapshot.post, account: result.snapshot.account_metrics, telegram };
}

if (require.main === module) collectWindow(process.argv[2] || "24h").then((result) => process.stdout.write(`${JSON.stringify(result)}\n`)).catch((error) => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
module.exports = { EXPECTED, collectWindow, metricPlatform, persistDailyDigest, persistDelayedSnapshot, persistSnapshot, postMetrics, sendMetricSnapshot, verifyNativeHtml };
