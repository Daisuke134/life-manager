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
const JSONL_CACHE = new Map();
const HISTORICAL_PUBLISH_TIMESTAMP_SKEW_MS = 3 * 60_000;

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
  const byLabel = new Map(rows.map((row) => [row?.label, row?.data?.at(-1)?.total]));
  const result = {};
  for (const [label, key] of Object.entries(POST_LABELS)) {
    const value = byLabel.get(label);
    result[key] = value != null && String(value).trim() !== "" ? measured(value, "postiz_post_analytics") : { status: "unavailable", value: null, reason: "metric_missing" };
  }
  for (const key of ["impressions", "watch_time", "average_watch_time", "completion"]) result[key] = { status: "unavailable", value: null, reason: "metric_not_supported" };
  const complete = ["views", "likes", "comments", "shares", "saves"].every((key) => result[key].status === "measured");
  const numerator = result.likes.value + result.comments.value + result.shares.value + result.saves.value;
  result.engagement = !complete ? { status: "unavailable", value: null, reason: "engagement_input_missing" }
    : result.views.value === 0 ? { status: "unavailable", value: null, reason: "zero_view_denominator" }
    : { status: "derived", numerator, denominator: result.views.value, rate: Number((numerator / result.views.value).toFixed(8)), percent: Number((numerator / result.views.value * 100).toFixed(2)), formula: "(likes+comments+shares+saves)/views" };
  return result;
}

function currentSnapshotFile(dataDir, reportDay, expected = EXPECTED) {
  return path.join(path.resolve(dataDir), "tenants", expected.tenant_id, "marketing", "metrics", expected.native_owner, expected.shortcode, "current", `${reportDay}.combined.json`);
}

function metricSnapshotFile(dataDir, window, expected = EXPECTED) {
  return path.join(path.resolve(dataDir), "tenants", expected.tenant_id, "marketing", "metrics", expected.native_owner, expected.shortcode, `${window}.combined.json`);
}

function historicalCorrectionFile(dataDir, window, expected = EXPECTED) {
  return path.join(path.resolve(dataDir), "tenants", expected.tenant_id, "marketing", "metrics", expected.native_owner, expected.shortcode, `${window}.correction.json`);
}

function effectiveSnapshotFile(dataDir, window, expected = EXPECTED) {
  const original = metricSnapshotFile(dataDir, window, expected);
  if (window !== "7d") return original;
  const correctionFile = historicalCorrectionFile(dataDir, window, expected);
  if (!fs.existsSync(correctionFile)) return original;
  try {
    const correction = JSON.parse(fs.readFileSync(correctionFile, "utf8"));
    if (correction.correction === true && correction.window === window && correction.product_id === expected.product_id
      && correction.integration_id === expected.integration_id && correction.provider_post_id === expected.provider_post_id
      && correction.public_url === expected.public_url && correction.published_at === expected.published_at
      && correction.caption_sha256 === crypto.createHash("sha256").update(expected.caption).digest("hex")) return correctionFile;
  } catch {}
  return original;
}

function jsonlRows(dataDir, relativePath) {
  const file = path.join(path.resolve(dataDir), relativePath);
  let stat;
  try { stat = fs.statSync(file); } catch { return []; }
  if (!stat.isFile()) return [];
  const cached = JSONL_CACHE.get(file);
  if (cached?.size === stat.size && cached.mtimeMs === stat.mtimeMs) return cached.rows;
  let rows = [];
  try {
    for (const line of fs.readFileSync(file, "utf8").split(/\r?\n/).filter(Boolean)) {
      const row = JSON.parse(line);
      if (!row || typeof row !== "object" || Array.isArray(row)) { rows = null; break; }
      rows.push(row);
    }
  } catch { rows = null; }
  JSONL_CACHE.set(file, { size: stat.size, mtimeMs: stat.mtimeMs, rows });
  return rows;
}

function postMetricsFromLedgerRow(row) {
  const keys = Object.values(POST_LABELS);
  if (keys.some((key) => row[key] != null && (!Number.isSafeInteger(row[key]) || row[key] < 0))) return null;
  if (row.impressions != null && (!Number.isSafeInteger(row.impressions) || row.impressions < 0)) return null;
  const sourceDate = row.observed_at.slice(0, 10);
  const postRows = Object.entries(POST_LABELS).map(([label, key]) => ({ label, data: [{ total: row[key] == null ? null : String(row[key]) }] }));
  const post = postMetrics(postRows);
  for (const key of keys) {
    if (post[key].status === "measured") post[key] = { ...post[key], source: row.source, source_date: sourceDate };
    else if (row.metric_null_reasons?.[key]) post[key].reason = row.metric_null_reasons[key];
  }
  post.impressions = row.impressions == null
    ? { status: "unavailable", value: null, reason: row.metric_null_reasons?.impressions || "metric_missing" }
    : { status: "measured", value: row.impressions, source: row.source, source_date: sourceDate };
  if (post.engagement.status === "derived") post.engagement.source_date = sourceDate;
  return post;
}

function persistHistoricalCheckpointCorrection({ dataDir, expected = EXPECTED, correctionCreatedAt = new Date().toISOString() }) {
  const originalFile = metricSnapshotFile(dataDir, "7d", expected);
  if (!fs.existsSync(originalFile)) return { created: false, reason: "historical_snapshot_missing" };
  let original;
  let originalBytes;
  try { originalBytes = fs.readFileSync(originalFile); original = JSON.parse(originalBytes.toString("utf8")); } catch { return { created: false, reason: "historical_snapshot_invalid" }; }
  if (original.window !== "7d" || original.sources?.postiz_post?.reason !== "source_delayed"
    || original.product_id !== expected.product_id || original.integration_id !== expected.integration_id
    || original.provider_post_id !== expected.provider_post_id || original.public_url !== expected.public_url
    || original.published_at !== expected.published_at
    || original.caption_sha256 !== crypto.createHash("sha256").update(expected.caption).digest("hex")) return { created: false, reason: "historical_snapshot_not_correctable" };

  const metricsRows = jsonlRows(dataDir, "marketing-owner-events/state/post-metrics.jsonl");
  const identityRows = jsonlRows(dataDir, "state/publication-identity.jsonl");
  if (!Array.isArray(metricsRows) || !Array.isArray(identityRows)) return { created: false, reason: "normalized_metrics_ledger_invalid" };
  const metricCandidates = metricsRows.filter((row) => row.product_id === expected.product_id && row.platform === "instagram"
    && row.postiz_id === expected.provider_post_id && row.target_age_hours === 168);
  const identityCandidates = identityRows.filter((row) => row.product_id === expected.product_id && row.postiz_post_id === expected.provider_post_id);
  if (metricCandidates.length !== 1 || identityCandidates.length !== 1) return { created: false, reason: "historical_metrics_identity_ambiguous" };
  const metric = metricCandidates[0]; const identity = identityCandidates[0];
  const metricPublishedAt = Date.parse(metric.published_at || "");
  const expectedPublishedAt = Date.parse(expected.published_at || "");
  const metricObservedAt = Date.parse(metric.observed_at || "");
  const measuredAgeHours = (metricObservedAt - metricPublishedAt) / 3600_000;
  if (!Number.isFinite(metricPublishedAt) || !Number.isFinite(expectedPublishedAt) || !Number.isFinite(metricObservedAt)
    || metric.published_at !== identity.publish_date
    || Math.abs(metricPublishedAt - expectedPublishedAt) > HISTORICAL_PUBLISH_TIMESTAMP_SKEW_MS
    || Math.abs(measuredAgeHours - metric.observed_age_hours) > 0.0001
    || metric.native_url !== expected.public_url || metric.integration_id !== expected.integration_id
    || metric.source !== "postiz_instagram_graph_api" || metric.checkpoint_status !== "measured"
    || metric.checkpoint_sla_status !== "in_window" || !Number.isFinite(metric.observed_age_hours)
    || metric.observed_age_hours < 168 || metric.observed_age_hours > 169.5
    || typeof metric.observed_at !== "string" || !Number.isFinite(Date.parse(metric.observed_at))
    || typeof metric.native_post_id !== "string" || !metric.native_post_id
    || !/^[a-f0-9]{64}$/.test(String(metric.snapshot_id || ""))
    || !/^[a-f0-9]{64}$/.test(String(metric.raw_evidence_hash || ""))) return { created: false, reason: "historical_metrics_row_invalid" };
  if (identity.platform !== "instagram-standalone" || identity.native_post_url !== expected.public_url
    || identity.publish_date !== metric.published_at || identity.integration_id !== expected.integration_id
    || identity.native_post_id !== metric.native_post_id
    || identity.postiz_state !== "PUBLISHED" || identity.identity_status !== "resolved"
    || identity.resolution_method !== "postiz_provider_native_receipt") return { created: false, reason: "historical_publication_identity_invalid" };

  const correctionFile = historicalCorrectionFile(dataDir, "7d", expected);
  if (fs.existsSync(correctionFile)) {
    try {
      const existing = JSON.parse(fs.readFileSync(correctionFile, "utf8"));
      if (existing.correction === true && existing.public_url === expected.public_url && existing.provider_post_id === expected.provider_post_id
        && existing.source_snapshot_id === metric.snapshot_id && existing.source_raw_evidence_hash === metric.raw_evidence_hash) {
        return { created: false, file: correctionFile, snapshot: existing };
      }
    } catch {}
    return { created: false, reason: "historical_correction_conflict" };
  }

  const snapshot = {
    schema_version: 1, kind: "instagram_combined_metric_snapshot_correction", ...expected,
    window: "7d", observed_at: metric.observed_at, correction_created_at: correctionCreatedAt,
    correction: true, historical_checkpoint: true,
    checkpoint_published_at: metric.published_at,
    caption_sha256: crypto.createHash("sha256").update(expected.caption).digest("hex"),
    corrects_source_snapshot_sha256: crypto.createHash("sha256").update(originalBytes).digest("hex"),
    source_snapshot_id: metric.snapshot_id, source_raw_evidence_hash: metric.raw_evidence_hash,
    sources: {
      instagram_native: { status: "unavailable", reason: original.sources?.instagram_native?.reason || "historical_native_metrics_not_recovered", identity_verified: true },
      postiz_post: { status: "measured", source: metric.source, publication_identity: identity.resolution_method },
      postiz_account: { status: "unavailable", reason: "account_metrics_not_in_post_metrics" },
    },
    post: postMetricsFromLedgerRow(metric),
    account_metrics: { status: "unavailable", reason: "account_metrics_not_in_post_metrics" },
  };
  if (!snapshot.post) return { created: false, reason: "historical_metrics_values_invalid" };
  fs.mkdirSync(path.dirname(correctionFile), { recursive: true, mode: 0o700 });
  const temporary = `${correctionFile}.tmp-${process.pid}-${crypto.randomUUID()}`;
  fs.writeFileSync(temporary, `${JSON.stringify(snapshot, null, 2)}\n`, { mode: 0o600, flag: "wx" });
  fs.renameSync(temporary, correctionFile); fs.chmodSync(correctionFile, 0o600);
  return { created: true, file: correctionFile, snapshot };
}

function persistSnapshot({ dataDir, window, observedAt, html, accountRows, postRows, expected = EXPECTED }) {
  if ((!WINDOWS.has(window) && window !== "current") || !Number.isFinite(Date.parse(observedAt))) throw new Error("Instagram metric window invalid");
  const native = verifyNativeHtml(html, expected);
  const metrics = postMetrics(postRows);
  if (window === "current" && !Object.values(metrics).some((metric) => metric.status === "measured")) {
    throw new Error("Instagram current observation has no post metrics");
  }
  const snapshot = {
    schema_version: 1, kind: "instagram_combined_metric_snapshot", ...expected,
    window, observed_at: observedAt, caption_sha256: crypto.createHash("sha256").update(expected.caption).digest("hex"),
    ...(window === "current" ? { historical_checkpoint: false, requested_lookback_days: 7, metric_scope: "provider_current_observation" } : {}),
    sources: { instagram_native: native, postiz_post: { status: "measured" }, postiz_account: Array.isArray(accountRows) && accountRows.length ? { status: "measured" } : { status: "unavailable", reason: "empty_response", response: "empty_array" } },
    post: metrics, account_metrics: Array.isArray(accountRows) && accountRows.length ? accountRows : { status: "unavailable", reason: "empty_response" },
  };
  const reportDay = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(observedAt));
  const file = window === "current" ? currentSnapshotFile(dataDir, reportDay, expected) : metricSnapshotFile(dataDir, window, expected);
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
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
  const file = metricSnapshotFile(dataDir, window, expected); fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  if (fs.existsSync(file)) return { created: false, file, snapshot: JSON.parse(fs.readFileSync(file, "utf8")) };
  const temporary = `${file}.tmp-${process.pid}-${crypto.randomUUID()}`;
  fs.writeFileSync(temporary, `${JSON.stringify(snapshot, null, 2)}\n`, { mode: 0o600, flag: "wx" }); fs.renameSync(temporary, file); fs.chmodSync(file, 0o600);
  return { created: true, file, snapshot };
}

function persistDailyDigest({ dataDir, reportDay, observedAt, expected = EXPECTED }) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(reportDay) || !Number.isFinite(Date.parse(observedAt))) throw new Error("Instagram daily digest identity invalid");
  const directory = path.join(path.resolve(dataDir), "tenants", expected.tenant_id, "marketing", "metrics", expected.native_owner, expected.shortcode);
  const historicalResult = persistHistoricalCheckpointCorrection({ dataDir, expected, correctionCreatedAt: observedAt });
  const historicalCorrection = historicalResult.snapshot || null;
  const rows = [...WINDOWS].map((window) => {
    const file = effectiveSnapshotFile(dataDir, window, expected);
    if (!fs.existsSync(file)) return { window, status: "pending" };
    const snapshot = JSON.parse(fs.readFileSync(file, "utf8"));
    const measuredValue = Object.values(snapshot.post || {}).some((metric) => metric?.status === "measured" || metric?.status === "derived");
    const status = snapshot.correction === true ? "corrected" : measuredValue ? "measured" : "unavailable";
    return { window, status, file };
  });
  const currentFile = currentSnapshotFile(dataDir, reportDay, expected);
  const source = (fs.existsSync(currentFile) ? JSON.parse(fs.readFileSync(currentFile, "utf8")) : null) || rows.map((row) => row.file && JSON.parse(fs.readFileSync(row.file, "utf8"))).filter(Boolean)
    .find((snapshot) => Object.values(snapshot.post || {}).some((metric) => metric?.status === "measured" || metric?.status === "derived")) || rows.map((row) => row.file && JSON.parse(fs.readFileSync(row.file, "utf8"))).find(Boolean);
  if (!source) throw new Error("Instagram daily digest has no metric snapshot");
  const baseFile = path.join(directory, "daily", `${reportDay}.json`);
  const correctionFile = path.join(directory, "daily", `${reportDay}.correction.json`);
  const currentCorrectionFile = path.join(directory, "daily", `${reportDay}.current.correction.json`);
  const historicalDailyCorrectionFile = path.join(directory, "daily", `${reportDay}.historical.correction.json`);
  const retainedFile = [historicalDailyCorrectionFile, currentCorrectionFile, correctionFile, baseFile].find((file) => fs.existsSync(file));
  let addHistoricalCorrection = false;
  if (retainedFile) {
    const existing = JSON.parse(fs.readFileSync(retainedFile, "utf8"));
    const existingMeasured = Object.values(existing.post || {}).some((metric) => metric?.status === "measured" || metric?.status === "derived");
    const sourceMeasured = Object.values(source.post || {}).some((metric) => metric?.status === "measured" || metric?.status === "derived");
    const promoteCurrent = source.historical_checkpoint === false && existing.historical_checkpoint !== false;
    const existingCorrectionId = existing.historical_checkpoint_correction?.source_snapshot_id
      || (existing.source_window === "7d" && existing.correction === true ? existing.source_snapshot_id : null);
    addHistoricalCorrection = Boolean(historicalCorrection && existingCorrectionId !== historicalCorrection.source_snapshot_id);
    if ((existingMeasured && !promoteCurrent && !addHistoricalCorrection) || !sourceMeasured || (retainedFile !== baseFile && !promoteCurrent && !addHistoricalCorrection)) return { created: false, file: retainedFile, snapshot: existing };
  }
  const dailyCorrection = fs.existsSync(baseFile);
  const sourceWindow = source.window || null;
  const hasHistoricalCorrection = Boolean(historicalCorrection);
  const file = addHistoricalCorrection ? historicalDailyCorrectionFile
    : dailyCorrection ? (source.historical_checkpoint === false ? currentCorrectionFile : correctionFile) : baseFile;
  const snapshot = { ...source, kind: `${/^https:\/\/www\.tiktok\.com\//.test(source.public_url) ? "tiktok" : "instagram"}_daily_metric_digest${dailyCorrection || source.correction === true || hasHistoricalCorrection ? "_correction" : ""}`, window: "daily", observed_at: observedAt, report_day: reportDay,
    source_window: sourceWindow,
    source_observed_at: source.observed_at,
    ...(hasHistoricalCorrection ? { historical_checkpoint_correction: historicalCorrection } : {}),
    ...(dailyCorrection || source.correction === true || hasHistoricalCorrection ? { correction: true } : {}),
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
  const days = { "2h": 1, "24h": 1, "72h": 3, "7d": 7, current: 7 }[window];
  if (!days) throw new Error("Instagram metric window invalid");
  const [page, account, post] = await Promise.all([
    get(expected.public_url).then((response) => response.text()),
    get(`https://api.postiz.com/public/v1/analytics/${expected.integration_id}?date=${days}`, { Authorization: key }).then((response) => response.json()),
    get(`https://api.postiz.com/public/v1/analytics/post/${expected.provider_post_id}?date=${days}`, { Authorization: key }).then((response) => response.json()),
  ]);
  const dataDir = resolveDataRoot(env);
  const result = persistSnapshot({ dataDir, window, observedAt, html: page, accountRows: account, postRows: post, expected });
  const telegram = window === "current" ? { created: false, reason: "current_observation_for_daily_report" } : await sendMetricSnapshot(result, env, dataDir);
  return { created: result.created, file: result.file, post: result.snapshot.post, account: result.snapshot.account_metrics, telegram };
}

if (require.main === module) collectWindow(process.argv[2] || "24h").then((result) => process.stdout.write(`${JSON.stringify(result)}\n`)).catch((error) => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
module.exports = { EXPECTED, collectWindow, currentSnapshotFile, effectiveSnapshotFile, historicalCorrectionFile, metricPlatform, persistDailyDigest, persistDelayedSnapshot, persistHistoricalCheckpointCorrection, persistSnapshot, postMetrics, sendMetricSnapshot, verifyNativeHtml };
