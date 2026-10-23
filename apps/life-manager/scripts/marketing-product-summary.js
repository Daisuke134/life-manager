#!/usr/bin/env node
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { createContentObjectStore } = require("../lib/content-object-store.js");
const { createMarketingLocalLedger } = require("../lib/marketing-local-ledger.js");
const { buildMarketingLivenessJob, executeMarketingLivenessJob } = require("../lib/marketing-liveness-adapter.js");
const { executeCapabilityJob } = require("./runtime-up.js");

const HONNE = Object.freeze({ product_id: "honne-ai", label: "Honne AI", targets: [{ owner: "honne_reveal", account: "@honne_reveal", locale: "en", platform: "TikTok", required: true }, { owner: "honnevideo", account: "@honnevideo", locale: "ja", platform: "TikTok", required: true }] });
const ANICCA = Object.freeze({ product_id: "anicca-ios", label: "Anicca iOS", targets: [{ owner: "anicca.jp", account: "@anicca.jp", locale: "ja", platform: "TikTok", required: true }, { owner: "anicca.ios.jp", account: "@anicca.jp1", locale: "ja", platform: "Instagram", required: true }, { owner: "anicca.en", account: "@anicca.en", locale: "en", platform: "Instagram", required: false }, { owner: "anicca.jp4", account: "@anicca.jp4", locale: "ja", platform: "TikTok", required: false }, { owner: "anicca.he", account: "@anicca.he", locale: "ja", platform: "TikTok", required: false, public_url: "https://www.tiktok.com/@anicca.he/video/7676500512308481296" }] });
const SUMMARY_ROUTES = Object.freeze({ "honne-ai": Object.freeze({ lane: "marketing-product-summary-honne", locale: "en" }), "anicca-ios": Object.freeze({ lane: "marketing-product-summary-anicca", locale: "ja" }), "mobile-marketing": Object.freeze({ lane: "marketing-product-summary-weekly", locale: "ja" }) });

function latestDaily(dataDir, owner, reportDay) {
  const root = path.join(dataDir, "tenants/dais-local/marketing/metrics", owner); if (!fs.existsSync(root)) return null;
  const reportEnd = Date.parse(`${reportDay}T23:59:59.999+09:00`); const cutoff = reportEnd - 30 * 86400_000; const candidates = [];
  for (const id of fs.readdirSync(root)) {
    const daily = path.join(root, id, "daily"); if (!fs.existsSync(daily)) continue;
    const rows = [`${reportDay}.current.correction.json`, `${reportDay}.historical.correction.json`, `${reportDay}.correction.json`, `${reportDay}.json`]
      .map((name) => path.join(daily, name)).filter((candidate) => fs.existsSync(candidate))
      .map((file) => ({ file, snapshot: JSON.parse(fs.readFileSync(file, "utf8")) }))
      .filter(({ snapshot }) => Number.isFinite(Date.parse(snapshot.observed_at || "")))
      .sort((a, b) => Date.parse(b.snapshot.observed_at) - Date.parse(a.snapshot.observed_at));
    const { file, snapshot } = rows[0] || {}; if (!snapshot) continue;
    const publishedAt = Date.parse(snapshot.published_at || "");
    if (!Number.isFinite(publishedAt) || publishedAt > reportEnd || publishedAt < cutoff) continue;
    candidates.push({ file, snapshot });
  }
  return candidates.sort((a, b) => Date.parse(b.snapshot.observed_at) - Date.parse(a.snapshot.observed_at))[0] || null;
}

function metricText(snapshot) {
  if (!snapshot) return "投稿指標・アカウント指標を取得できません（当日データなし）";
  const labels = { views: "閲覧数", reach: "リーチ", saves: "保存数", likes: "いいね", comments: "コメント", shares: "シェア", impressions: "表示回数", watch_time: "視聴時間", average_watch_time: "平均視聴時間", completion: "視聴完了率", engagement: "エンゲージメント率", followers: "フォロワー数", following: "フォロー数", total_likes: "累計いいね数", videos: "投稿数", replies: "返信数", recent_views: "直近20投稿の閲覧数", recent_likes: "直近20投稿のいいね", recent_comments: "直近20投稿のコメント", recent_shares: "直近20投稿のシェア" };
  const measured = []; const unavailable = []; const unsupported = [];
  const addMetric = (label, metric) => {
    if (!metric || metric.status === "unavailable") { (metric?.reason === "metric_not_supported" ? unsupported : unavailable).push(label); return; }
    measured.push(`${label} ${metric.percent != null ? `${metric.percent}%` : metric.value}${metric.source_date ? `（${metric.source_date}）` : ""}`);
  };
  for (const [key, label] of Object.entries(labels)) addMetric(label, snapshot.post?.[key]);
  const accountMetrics = snapshot.account_metrics;
  if (Array.isArray(accountMetrics)) {
    if (!accountMetrics.length) unavailable.push("アカウント合計");
    for (const row of accountMetrics) {
      const key = String(row?.label || "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
      const point = Array.isArray(row?.data) ? row.data.at(-1) : null; const value = point?.total == null || String(point.total).trim() === "" ? NaN : Number(point.total);
      addMetric(`アカウント${labels[key] || "指標"}`, Number.isFinite(value) && value >= 0 ? { status: "measured", value, source_date: point.date } : { status: "unavailable", reason: "metric_missing" });
    }
  } else if (!accountMetrics || accountMetrics.status === "unavailable") unavailable.push("アカウント合計");
  else {
    for (const [key, metric] of Object.entries(accountMetrics)) {
      if (key === "status" || key === "reason" || key === "value") continue;
      addMetric(labels[key] ? `アカウント${labels[key]}` : "その他のアカウント指標", metric);
    }
  }
  const current = snapshot.historical_checkpoint === false ? `現在値（取得時刻: ${snapshot.source_observed_at || snapshot.observed_at}。過去のチェックポイント値ではありません）。` : "";
  const historicalLabel = snapshot.correction === true && snapshot.source_window === "7d"
    ? `過去の値・訂正済み7日checkpoint（実測日時: ${snapshot.source_observed_at || snapshot.observed_at}）。`
    : "";
  const historicalCorrection = snapshot.historical_checkpoint_correction && snapshot.source_window !== "7d"
    ? `過去の値・訂正済み7日checkpoint（実測日時: ${snapshot.historical_checkpoint_correction.observed_at}）。${metricText(snapshot.historical_checkpoint_correction)}`
    : "";
  const measuredText = measured.length ? `${measured.join("、")}。` : "";
  const unavailableText = `取得できない項目：${unavailable.length ? unavailable.join("、") : "なし"}`;
  const unsupportedText = unsupported.length ? `。APIでは取得できない項目：${unsupported.join("、")}` : "";
  return `${current}${historicalLabel}${measuredText}${unavailableText}${unsupportedText}${historicalCorrection}`;
}

const FUNNEL_PRODUCTS = Object.freeze([["anicca-ios", "Anicca iOS"], ["honne-ai", "Honne AI"]]);
const PRODUCT_METRICS = Object.freeze(["activation", "retained_users", "d1_retention", "d7_retention"]);
function unavailable(reason) { return { status: "unavailable", value: null, reason }; }
function validateObservationMetric(productId, name, metric) {
  if (!metric || !["measured", "unavailable"].includes(metric.status)) throw new Error(`${productId} ${name} status is invalid`);
  if (metric.status === "unavailable") { if (metric.value !== null || !metric.reason) throw new Error(`${productId} ${name} unavailable metric is invalid`); }
  else if (typeof metric.value !== "number" || !Number.isFinite(metric.value)) throw new Error(`${productId} ${name} measured value is invalid`);
  return metric;
}
function productAnalytics(dataDir, productId, objectStore) {
  const file = path.join(dataDir, "tenants/dais-local/product-packs/metrics/product-analytics", `${productId}.json`);
  if (!fs.existsSync(file)) return { source_ref: null, product_id: productId, source_status: "unavailable", metrics: Object.fromEntries(PRODUCT_METRICS.map((name) => [name, unavailable("product_pack_observation_missing")])) };
  const input = JSON.parse(fs.readFileSync(file, "utf8")); if (input.schema_version !== 1 || input.kind !== "product_activation_retention_observation") throw new Error(`${productId} product analytics contract mismatch`); if (input.product_id !== productId) throw new Error(`${productId} product analytics identity mismatch`); if (!Number.isFinite(Date.parse(input.observed_at)) || !["measured", "partial", "unavailable"].includes(input.source_status)) throw new Error(`${productId} product analytics source metadata is invalid`);
  const metrics = Object.fromEntries(PRODUCT_METRICS.map((name) => [name, validateObservationMetric(productId, name, input.metrics?.[name])])); const statuses = new Set(Object.values(metrics).map(({ status }) => status)); if (input.source_status === "measured" && statuses.has("unavailable")) throw new Error(`${productId} measured product source contains unavailable metric`); if (input.source_status === "unavailable" && statuses.has("measured")) throw new Error(`${productId} unavailable product source contains measured metric`);
  return { source_ref: objectStore.import(file).ref, product_id: productId, source_status: input.source_status, observed_at: input.observed_at, data_from: input.data_from || null, data_to: input.data_to || null, cohort_definition: input.cohort_definition || null, metrics };
}
function metricValue(metric) { return metric?.status === "measured" ? String(metric.value) : "取得不可"; }
function coverageMetricValue(metric) { return metric?.status === "measured" ? String(metric.value) : `取得不可（${metric?.observed_days || 0}/${metric?.expected_days || 7}日）`; }
function sourceStatusText(status) { return status === "measured" || status === "complete" ? "取得済み" : status === "partial" ? "一部取得" : status === "unavailable" ? "取得不可" : "未確認"; }
function campaignMetricText(metric) {
  if (metric?.status === "measured") return String(metric.value);
  if (metric?.reason === "report_pending") return "取得不可（App Store Connectのレポート待ち）";
  if (metric?.reason === "campaign_not_observed_or_privacy_threshold") return "取得不可（未観測、またはAppleのプライバシー基準で非表示）";
  return "取得不可";
}
const CAMPAIGN_PLATFORMS = Object.freeze({ instagram: "Instagram", tiktok: "TikTok", youtube: "YouTube" });
const CAMPAIGN_LOCALES = Object.freeze({ en: "英語", ja: "日本語", es: "スペイン語" });
function coverageFile(dataDir, reportDay) { return path.join(dataDir, "tenants/dais-local/marketing/attribution/coverage", reportDay, "summary.json"); }
function coverageFor(dataDir, reportDay, productId) { const file = coverageFile(dataDir, reportDay); if (!fs.existsSync(file)) return null; return JSON.parse(fs.readFileSync(file, "utf8")).products?.find((product) => product.product_id === productId) || null; }
function utcDayOffset(day, offset) { const epoch = Date.parse(`${day}T00:00:00.000Z`); if (!Number.isFinite(epoch)) throw new Error("report day is invalid"); return new Date(epoch + offset * 86400000).toISOString().slice(0, 10); }
function ascDailyDownloads(acquisition, reportDay) {
  const sourceDate = utcDayOffset(reportDay, -1);
  const daily = (Array.isArray(acquisition.daily_metrics) ? acquisition.daily_metrics : []).find((row) => row.date === sourceDate);
  return { ...(daily?.metrics?.first_time_downloads || unavailable("report_pending")), source_date: sourceDate };
}
const ASC_SEVEN_DAY_METRICS = Object.freeze(["first_time_downloads", "impressions", "product_page_views"]);
function ascSevenDayMetrics(dataDir, reportDay, productId, objectStore) {
  const windowEnd = utcDayOffset(reportDay, -1); const windowStart = utcDayOffset(windowEnd, -6);
  const days = Array.from({ length: 7 }, (_, index) => utcDayOffset(windowStart, index)); const daySet = new Set(days);
  const observations = Object.fromEntries(ASC_SEVEN_DAY_METRICS.map((name) => [name, new Map()])); const sourceRefs = new Set();
  for (let offset = 0; offset <= 7; offset += 1) {
    const sourceDay = utcDayOffset(reportDay, -offset); const file = path.join(dataDir, "tenants/dais-local/marketing/attribution/asc", sourceDay, "acquisition.json");
    if (!fs.existsSync(file)) continue;
    let snapshot;
    try { snapshot = JSON.parse(fs.readFileSync(file, "utf8")); if (snapshot.kind !== "marketing_asc_acquisition" || snapshot.report_day !== sourceDay || !snapshot.snapshot_ref) continue; objectStore.resolve(snapshot.snapshot_ref); }
    catch { continue; }
    const product = snapshot.products?.find((row) => row.product_id === productId); let used = false;
    for (const daily of Array.isArray(product?.daily_metrics) ? product.daily_metrics : []) {
      if (!daySet.has(daily.date)) continue;
      for (const name of ASC_SEVEN_DAY_METRICS) {
        if (observations[name].has(daily.date)) continue;
        const metric = daily.metrics?.[name];
        if (metric?.status === "unavailable" && metric.value === null) {
          observations[name].set(daily.date, null); used = true; continue;
        }
        if (metric?.status !== "measured" || typeof metric.value !== "number" || !Number.isFinite(metric.value) || metric.value < 0) continue;
        observations[name].set(daily.date, metric.value); used = true;
      }
    }
    if (used) sourceRefs.add(snapshot.snapshot_ref);
  }
  const metrics = Object.fromEntries(ASC_SEVEN_DAY_METRICS.map((name) => {
    const values = new Map([...observations[name]].filter(([, value]) => value !== null)); const missingDates = days.filter((day) => !values.has(day)); const observedDays = values.size;
    const status = observedDays === 7 ? "measured" : observedDays ? "partial" : "unavailable";
    const average = status === "measured" ? [...values.values()].reduce((total, value) => total + value, 0) / 7 : null;
    return [name, { status, value: average, aggregation: "mean_daily", unit: "count", data_from: windowStart, data_to: windowEnd,
      observed_days: observedDays, expected_days: 7, missing_dates: missingDates, ...(status === "measured" ? {} : { reason: observedDays ? "asc_7d_coverage_incomplete" : "report_pending" }) }];
  }));
  const statuses = Object.values(metrics).map((metric) => metric.status);
  return { status: statuses.every((status) => status === "measured") ? "measured" : statuses.some((status) => status !== "unavailable") ? "partial" : "unavailable",
    window_start: windowStart, window_end: windowEnd, metrics, source_refs: [...sourceRefs] };
}
function funnelText(product) {
  if (!product) return "初回ダウンロード 取得不可、有効化 取得不可、無料体験開始 取得不可、有料契約中 取得不可、継続利用者 取得不可、翌日継続率 取得不可、7日後継続率 取得不可、RevenueCat収益推定 取得不可、新規顧客（直近28日）取得不可、平均アクティブ顧客（直近28日）取得不可、App Store Connectの7日平均は取得不可";
  const metric = product.metrics;
  const installs = metric.installs?.source_date ? `${metricValue(metric.installs)}（対象日: ${metric.installs.source_date}）` : "取得不可（対象日不明）";
  return `初回ダウンロード ${installs}、有効化 ${metricValue(metric.activation)}、無料体験開始 ${metricValue(metric.trials)}、有料契約中 ${metricValue(metric.paid_active)}、継続利用者 ${metricValue(metric.retained_users)}、翌日継続率 ${metricValue(metric.d1_retention)}、7日後継続率 ${metricValue(metric.d7_retention)}、RevenueCat収益推定 ${metricValue(metric.proceeds_usd)}、新規顧客（直近28日）${metricValue(metric.customers_new_28d)}、平均アクティブ顧客（直近28日）${metricValue(metric.customers_active_daily_average_28d)}、App Store Connectの7日平均 初回ダウンロード ${coverageMetricValue(metric.asc_7d_first_time_downloads)} / 表示回数 ${coverageMetricValue(metric.asc_7d_impressions)} / 商品ページ閲覧 ${coverageMetricValue(metric.asc_7d_product_page_views)}`;
}
function campaignText(product) {
  if (!product) return "キャンペーン別実績は取得不可（計測データ未接続）";
  const breakdowns = Array.isArray(product.campaign_breakdowns) ? product.campaign_breakdowns : [];
  if (breakdowns.length) {
    const channels = breakdowns.map((row) => `${CAMPAIGN_PLATFORMS[row.platform] || "SNS"} ${row.account_id}（${CAMPAIGN_LOCALES[row.locale] || "その他"}）: 初回ダウンロード ${campaignMetricText(row.metrics?.first_time_downloads)}、表示回数 ${campaignMetricText(row.metrics?.impressions)}`);
    return `キャンペーン別実績: ${channels.join("。" )}。${product.attribution_status === "partial" ? "一部チャネルのみ計測しています。" : ""}個別投稿ではなく、アカウント・期間単位の集計です。`;
  }
  return product.campaign_id
    ? "キャンペーンリンクは設定済みですが、チャネル別のApp Store Connect実績はまだ取得できていません。"
    : "キャンペーンリンク未設定のため、チャネル別のApp Store Connect実績は取得できません。";
}

function persistAttributionCoverage(dataDir, reportDay, observedAt) {
  const file = coverageFile(dataDir, reportDay); if (fs.existsSync(file)) return { created: false, file, snapshot: JSON.parse(fs.readFileSync(file, "utf8")) };
  const objectStore = createContentObjectStore({ objectDir: path.join(dataDir, "objects") }); const root = path.join(dataDir, "tenants/dais-local/marketing/attribution"); const ascFile = path.join(root, "asc", reportDay, "acquisition.json"); const rcFile = path.join(root, "revenuecat", reportDay, "subscriptions.json"); if (!fs.existsSync(ascFile) || !fs.existsSync(rcFile)) throw new Error("attribution product inputs are missing"); const asc = JSON.parse(fs.readFileSync(ascFile, "utf8")); const rc = JSON.parse(fs.readFileSync(rcFile, "utf8")); objectStore.resolve(asc.snapshot_ref); objectStore.resolve(rc.snapshot_ref);
  const products = FUNNEL_PRODUCTS.map(([productId, label]) => { const acquisition = asc.products.find((row) => row.product_id === productId); const subscription = rc.products.find((row) => row.product_id === productId); if (!acquisition || !subscription) throw new Error(`${productId} attribution product identity is missing`); const analytics = productAnalytics(dataDir, productId, objectStore); const campaignReason = acquisition.attribution_reason || "campaign_not_configured"; return { product_id: productId, label, source_status: { asc: acquisition.source_status, revenuecat: subscription.source_status, product_analytics: analytics.source_status }, source_refs: analytics.source_ref ? [analytics.source_ref] : [], attribution_status: acquisition.attribution_status || "unattributed", attribution_reason: campaignReason, campaign_id: acquisition.campaign_id || null, campaign_status: acquisition.campaign_status || "unavailable", campaign_breakdowns: acquisition.campaign_breakdowns || [], metrics: { installs: ascDailyDownloads(acquisition, reportDay), campaign_first_time_downloads: acquisition.metrics.campaign_first_time_downloads || unavailable(campaignReason), campaign_impressions: acquisition.metrics.campaign_impressions || unavailable(campaignReason), activation: analytics.metrics.activation, trials: subscription.metrics.trial_starts, paid_active: subscription.metrics.active_subscriptions, retained_users: analytics.metrics.retained_users, d1_retention: analytics.metrics.d1_retention, d7_retention: analytics.metrics.d7_retention, proceeds_usd: subscription.metrics.proceeds_usd } }; });
  const ascSevenDayRefs = [];
  for (const product of products) {
    const sevenDay = ascSevenDayMetrics(dataDir, reportDay, product.product_id, objectStore);
    product.asc_7d = { window_start: sevenDay.window_start, window_end: sevenDay.window_end, metrics: sevenDay.metrics };
    product.source_status.asc_7d = sevenDay.status;
    product.metrics.asc_7d_first_time_downloads = sevenDay.metrics.first_time_downloads;
    product.metrics.asc_7d_impressions = sevenDay.metrics.impressions;
    product.metrics.asc_7d_product_page_views = sevenDay.metrics.product_page_views;
    ascSevenDayRefs.push(...sevenDay.source_refs);
  }
  for (const product of products) {
    const subscription = rc.products.find((row) => row.product_id === product.product_id);
    product.source_status.revenuecat_customer_activity = subscription.customer_activity_status || "unavailable";
    product.metrics.customers_new_28d = subscription.metrics.customers_new || unavailable("revenuecat_customer_activity_unavailable");
    product.metrics.customers_active_daily_average_28d = subscription.metrics.customers_active || unavailable("revenuecat_customer_activity_unavailable");
  }
  const reason = products.find((product) => product.attribution_status === "partial")?.attribution_reason || products.find((product) => product.attribution_reason === "campaign_link_configured_no_product_readback")?.attribution_reason || "campaign_not_configured";
  const message = `Life Manager：${reportDay}のモバイルアプリ計測レポートです。\n${products.map((product) => `${product.label}: ${funnelText(product)}。データ取得状況: App Store Connect ${sourceStatusText(product.source_status.asc)}、7日指標 ${sourceStatusText(product.source_status.asc_7d)}、RevenueCat ${sourceStatusText(product.source_status.revenuecat)}、RevenueCat顧客指標 ${sourceStatusText(product.source_status.revenuecat_customer_activity)}、アプリ内分析 ${sourceStatusText(product.source_status.product_analytics)}。${campaignText(product)}`).join("\n")}\n投稿ごとのダウンロードと購入者の対応は未確認です。取得不可は0として扱わず、HonneとAniccaの数値は別々に集計します。`;
  const historicalAscRefs = ascSevenDayRefs.filter((ref) => ref !== asc.snapshot_ref);
  const sourceRefs = [asc.snapshot_ref, rc.snapshot_ref, ...historicalAscRefs, ...products.flatMap((product) => product.source_refs)];
  const snapshot = { schema_version: 1, kind: "marketing_product_metric_summary", period: "daily", report_key: `attribution-${reportDay}`, observed_at: observedAt, product_id: "mobile-marketing", source_refs: sourceRefs, products, coverage: { verified: null, partial: null, unattributed: null, rate_status: "unavailable", reason }, message }; fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 }); const temporary = `${file}.tmp-${process.pid}-${crypto.randomUUID()}`; fs.writeFileSync(temporary, `${JSON.stringify(snapshot, null, 2)}\n`, { mode: 0o600, flag: "wx" }); fs.renameSync(temporary, file); fs.chmodSync(file, 0o600); return { created: true, file, snapshot };
}

function persistProductDaily(dataDir, reportDay, observedAt, product) {
  const objectStore = createContentObjectStore({ objectDir: path.join(dataDir, "objects") }); const rows = product.targets.map((target) => { const row = latestDaily(dataDir, target.owner, reportDay); if (!row) return { ...target, snapshot: null, ref: null }; const direct = target.platform === "Instagram" ? /^https:\/\/www\.instagram\.com\/(?:reel|p)\/[A-Za-z0-9_-]+\/?$/ : /^https:\/\/www\.tiktok\.com\/@[^/]+\/(?:photo|video)\/\d+\/?$/; if (row.snapshot.account_id !== target.account || row.snapshot.locale !== target.locale || !direct.test(row.snapshot.public_url)) throw new Error(`${product.label} ${target.account} daily source mismatch`); return { ...target, ...row, ref: objectStore.import(row.file).ref }; });
  const missingAccounts = rows.filter((row) => !row.snapshot).map((row) => row.account); const missingRequiredAccounts = rows.filter((row) => row.required && !row.snapshot).map((row) => row.account); const availableCount = rows.length - missingAccounts.length; const sourceStatus = availableCount === 0 ? "unavailable" : missingAccounts.length ? "partial" : "complete";
  const coverage = coverageFor(dataDir, reportDay, product.product_id); const sourceRefs = rows.map((row) => row.ref).filter(Boolean); const message = `Life Manager：${product.label}の${reportDay}日次レポートです。\n${rows.map((row) => `${row.account} ${row.platform}: ${metricText(row.snapshot)}。公開URL: ${row.snapshot?.public_url || row.public_url || "取得不可"}`).join("\n")}\nデータ取得状況: ${sourceStatusText(sourceStatus)}。必須アカウントの取得不可: ${missingRequiredAccounts.length ? missingRequiredAccounts.join("、") : "なし"}。\n${funnelText(coverage)}。${campaignText(coverage)}`;
  const snapshot = { schema_version: 1, kind: "marketing_product_metric_summary", period: "daily", report_key: reportDay, observed_at: observedAt, product_id: product.product_id, source_status: sourceStatus, missing_accounts: missingAccounts, missing_required_accounts: missingRequiredAccounts, source_refs: sourceRefs, message }; const file = path.join(dataDir, "tenants/dais-local/marketing/metrics/summaries", product.product_id, "daily", `${reportDay}.json`); fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  if (fs.existsSync(file)) return { created: false, file, snapshot: JSON.parse(fs.readFileSync(file, "utf8")) }; const temporary = `${file}.tmp-${process.pid}-${crypto.randomUUID()}`; fs.writeFileSync(temporary, `${JSON.stringify(snapshot, null, 2)}\n`, { mode: 0o600, flag: "wx" }); fs.renameSync(temporary, file); fs.chmodSync(file, 0o600); return { created: true, file, snapshot };
}

function persistHonneDaily(dataDir, reportDay, observedAt) { return persistProductDaily(dataDir, reportDay, observedAt, HONNE); }
function persistAniccaDaily(dataDir, reportDay, observedAt) { return persistProductDaily(dataDir, reportDay, observedAt, ANICCA); }

function isoWeek(reportDay) {
  const date = new Date(`${reportDay}T00:00:00.000Z`); if (!Number.isFinite(date.getTime())) throw new Error("weekly report day is invalid"); date.setUTCDate(date.getUTCDate() + 4 - (date.getUTCDay() || 7)); const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1)); return `${date.getUTCFullYear()}-W${String(Math.ceil((((date - yearStart) / 86400000) + 1) / 7)).padStart(2, "0")}`;
}

function productDailySources(dataDir, productId, reportDay) {
  const root = path.join(dataDir, "tenants/dais-local/marketing/metrics/summaries", productId, "daily"); if (!fs.existsSync(root)) return [];
  const end = Date.parse(`${reportDay}T00:00:00.000Z`); const start = end - 6 * 86400_000;
  return fs.readdirSync(root).filter((name) => /^\d{4}-\d{2}-\d{2}\.json$/.test(name)).map((name) => ({ file: path.join(root, name), day: name.slice(0, 10) })).filter(({ day }) => { const time = Date.parse(`${day}T00:00:00.000Z`); return time >= start && time <= end; }).map((row) => ({ ...row, snapshot: JSON.parse(fs.readFileSync(row.file, "utf8")) })).sort((a, b) => a.day.localeCompare(b.day));
}

function latestWeeklyCampaign(dataDir, productId, reportDay, objectStore) {
  for (let offset = 0; offset < 7; offset += 1) {
    const day = utcDayOffset(reportDay, -offset); const file = coverageFile(dataDir, day);
    if (!fs.existsSync(file)) continue;
    const product = JSON.parse(fs.readFileSync(file, "utf8")).products?.find((row) => row.product_id === productId);
    if (product) return { day, product, source_ref: objectStore.import(file).ref };
  }
  return null;
}

function persistWeeklyReview(dataDir, reportDay, observedAt) {
  const objectStore = createContentObjectStore({ objectDir: path.join(dataDir, "objects") }); const week = isoWeek(reportDay); const products = [["honne-ai", "Honne AI"], ["anicca-ios", "Anicca iOS"]].map(([productId, label]) => { const rows = productDailySources(dataDir, productId, reportDay); const latest = rows.at(-1) || null; const sourceStatus = !rows.length ? "unavailable" : rows.length < 7 || rows.some((row) => row.snapshot.source_status !== "complete") ? "partial" : "complete"; return { productId, label, rows, latest, refs: rows.map((row) => objectStore.import(row.file).ref), campaign: latestWeeklyCampaign(dataDir, productId, reportDay, objectStore), source_status: sourceStatus, coverage_days: rows.length, missing_days: Math.max(0, 7 - rows.length) }; });
  const sourceRefs = [...new Set([...products.flatMap((product) => product.refs), ...products.map((product) => product.campaign?.source_ref).filter(Boolean)])]; const sourceStatus = products.every((product) => product.source_status === "complete") ? "complete" : products.some((product) => product.source_status !== "unavailable") ? "partial" : "unavailable"; const unavailableProducts = products.filter((product) => product.source_status === "unavailable").map((product) => product.productId); const partialProducts = products.filter((product) => product.source_status === "partial").map((product) => product.productId); const campaignLines = products.map((product) => product.campaign
    ? `${product.label}: 最新キャンペーン別実績（レポート日 ${product.campaign.day}、7日間合計ではありません）。${campaignText(product.campaign.product)}`
    : `${product.label}: キャンペーン別実績は取得不可（週次期間内にApp Store Connectのキャンペーンデータなし）。`); const message = `Life Manager：${week}のモバイル配信週次レポートです。\n${products.map((product) => `${product.label}: データ取得状況 ${sourceStatusText(product.source_status)}、記録日数 ${product.coverage_days}/7日、最新日 ${product.latest?.day || "取得不可"}。`).join("\n")}\n週内の最新キャンペーン別実績（7日間合計ではありません）：\n${campaignLines.join("\n")}\nアプリ間の勝ちパターン移植は判定しません。HonneとAniccaを分けて学習します。\n次の変更判断は購入者データが揃うまで保留します。`;
  const snapshot = { schema_version: 1, kind: "marketing_product_metric_summary", period: "weekly", report_key: week, observed_at: observedAt, product_id: "mobile-marketing", source_status: sourceStatus, missing_products: products.filter((product) => product.source_status !== "complete").map((product) => product.productId), unavailable_products: unavailableProducts, partial_products: partialProducts, products: products.map(({ productId, label, source_status, coverage_days, missing_days }) => ({ product_id: productId, label, source_status, coverage_days, missing_days })), source_refs: sourceRefs, message }; const file = path.join(dataDir, "tenants/dais-local/marketing/metrics/summaries/mobile-marketing/weekly", `${week}.json`); fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  if (fs.existsSync(file)) return { created: false, file, snapshot: JSON.parse(fs.readFileSync(file, "utf8")) }; const temporary = `${file}.tmp-${process.pid}-${crypto.randomUUID()}`; fs.writeFileSync(temporary, `${JSON.stringify(snapshot, null, 2)}\n`, { mode: 0o600, flag: "wx" }); fs.renameSync(temporary, file); fs.chmodSync(file, 0o600); return { created: true, file, snapshot };
}

async function sendSummary(result, env, dataDir) {
  if (!result.created) return { created: false, reason: "summary_replay" }; const objectStore = createContentObjectStore({ objectDir: path.join(dataDir, "objects") }); const summaryRef = objectStore.import(result.file).ref;
  const route = SUMMARY_ROUTES[result.snapshot.product_id]; if (!route) throw new Error("marketing product summary route is unavailable");
  const job = buildMarketingLivenessJob({ tenantId: "dais-local", telegramTokenRef: "secret://telegram/bot-token", telegramChatRef: "telegram-chat://owner", payload: { lane: route.lane, product: result.snapshot.product_id, locale: route.locale, platform: "multi", status: "summary", period: result.snapshot.period, observed_at: result.snapshot.observed_at, summary_ref: summaryRef } }); const store = createMarketingLocalLedger({ dataDir }); const queued = await store.enqueueJob({ jobId: job.job_id, tenantId: job.tenant_id, loopId: job.loop_id, capability: job.capability, effectClass: job.effect_class, effectKey: job.effect_key, inputRefs: job.input_refs, maxAttempts: job.max_attempts, availableAt: new Date().toISOString() }); if (!queued.created) return { created: false, reason: "telegram_replay" };
  const claim = await store.claimJob({ tenantId: job.tenant_id, jobId: job.job_id, capability: job.capability, workerId: "marketing-product-summary", leaseSeconds: 120 }); if (!claim) throw new Error("marketing product summary job is not claimable"); await executeCapabilityJob(claim, { workerId: "marketing-product-summary", handlers: { [job.capability]: (candidate) => executeMarketingLivenessJob(candidate, { secretProvider: { get: async () => env.LM_TELEGRAM_BOT_TOKEN }, chatProvider: { get: async () => env.LM_TELEGRAM_ALERT_CHAT_ID }, snapshotProvider: { get: async (_tenantId, ref) => JSON.parse(fs.readFileSync(objectStore.resolve(ref), "utf8")) } }) }, heartbeatJob: (input) => store.heartbeatJob(input), completeJob: (input) => store.completeJob(input), failJob: (input) => store.failJob(input), leaseSeconds: 120 }); const receipt = await store.readReceipt({ tenantId: job.tenant_id, jobId: job.job_id }); return { created: true, message_id: receipt?.message_id, summary_ref: summaryRef };
}

module.exports = { latestDaily, persistAniccaDaily, persistAttributionCoverage, persistHonneDaily, persistProductDaily, persistWeeklyReview, sendSummary };
