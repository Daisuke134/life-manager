"use strict";

const { createHash } = require("node:crypto");
const { isDeepStrictEqual } = require("node:util");

const { buildRuntimeJob } = require("./runtime-job-store.js");
const { verifyMarketingVideoPublicationReceipt } = require("./marketing-video-publication-adapter.js");
const { zonedSlotInstant } = require("./honne-ja-shadow-schedule.js");
const { hashChatId, sendMessage } = require("./telegram.js");

const ADAPTER_ID = "marketing-liveness-telegram";
const CAPABILITY = "marketing.liveness.telegram";
const LOOP_ID = "marketing.liveness";
const ARMED = "production-armed";
const LANE_STATES = new Set([ARMED, "disabled", "default-off", "shadow"]);
const SLOT = /^([01]\d|2[0-3]):([0-5]\d)$/;
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const LOCALE = /^[a-z]{2}(?:-[A-Z]{2})?$/;
const ACCOUNT = /^@?[A-Za-z0-9._-]{1,127}$/;
const SECRET_REF = /^secret:\/\/[a-z0-9][a-z0-9._-]*(?:\/[a-z0-9][a-z0-9._-]*)*$/i;
const CHAT_REF = /^telegram-chat:\/\/[a-z0-9][a-z0-9._-]*$/i;
const LIVENESS_REF = /^marketing-liveness:\/\/(.+)$/;
const SNAPSHOT_REF = /^object:\/\/sha256\/[0-9a-f]{64}$/;
const METRIC_WINDOWS = new Set(["2h", "24h", "72h", "7d", "daily"]);
const POSTIZ_TIKTOK_POST_URL = /^https:\/\/www\.tiktok\.com\/@[A-Za-z0-9._-]+\/(?:photo|video)\/\d+\/?$/;

function required(value, label) {
  const text = String(value == null ? "" : value).trim();
  if (!text) throw new Error(`${label} is required`);
  return text;
}

function exactInstant(value, label) {
  const text = String(value || "");
  const date = new Date(text);
  if (!Number.isFinite(date.getTime()) || date.toISOString() !== text) {
    throw new Error(`${label} is invalid`);
  }
  return text;
}

function normalizeLane(input = {}) {
  const lane = {
    lane_id: required(input.lane_id, "marketing liveness lane"),
    state: required(input.state, "marketing liveness lane state"),
    product: required(input.product, "marketing liveness product"),
    locale: required(input.locale, "marketing liveness locale"),
    platform: required(input.platform, "marketing liveness platform"),
    ...(input.account ? { account: String(input.account).trim() } : {}),
    time_zone: required(input.time_zone, "marketing liveness time zone"),
    slots: Array.isArray(input.slots) ? [...new Set(input.slots.map(String))].sort() : [],
    after: exactInstant(input.after, "marketing liveness start"),
    grace_minutes: Number(input.grace_minutes),
  };
  if (
    !IDENTIFIER.test(lane.lane_id)
    || !IDENTIFIER.test(lane.product)
    || !LOCALE.test(lane.locale)
    || !LANE_STATES.has(lane.state)
    || !["instagram", "tiktok", "youtube"].includes(lane.platform)
    || (lane.account !== undefined && !ACCOUNT.test(lane.account))
    || lane.slots.length < 1
    || lane.slots.some((slot) => !SLOT.test(slot))
    || !Number.isInteger(lane.grace_minutes)
    || lane.grace_minutes < 0
    || lane.grace_minutes > 1440
  ) {
    throw new Error("marketing liveness lane is invalid");
  }
  return lane;
}

function calendarDay(ms, timeZone) {
  let parts;
  try {
    parts = new Intl.DateTimeFormat("en-CA", {
      timeZone, year: "numeric", month: "2-digit", day: "2-digit",
    }).formatToParts(new Date(ms));
  } catch {
    throw new Error("marketing liveness time zone is invalid");
  }
  const map = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return { year: Number(map.year), month: Number(map.month), day: Number(map.day) };
}

function previousDay(day) {
  const date = new Date(Date.UTC(day.year, day.month - 1, day.day) - 86400000);
  return { year: date.getUTCFullYear(), month: date.getUTCMonth() + 1, day: date.getUTCDate() };
}

function expectedSlots(laneInput, nowMs) {
  const lane = normalizeLane(laneInput);
  if (lane.state !== ARMED) return [];
  const cutoff = Number(nowMs) - lane.grace_minutes * 60000;
  if (!Number.isFinite(cutoff)) throw new Error("marketing liveness clock is invalid");
  const afterMs = Date.parse(lane.after);
  const result = [];
  let day = calendarDay(cutoff, lane.time_zone);
  const firstDay = calendarDay(afterMs, lane.time_zone);
  while (
    result.length < 100
    && Date.UTC(day.year, day.month - 1, day.day) >= Date.UTC(firstDay.year, firstDay.month - 1, firstDay.day)
  ) {
    for (let index = lane.slots.length - 1; index >= 0 && result.length < 100; index -= 1) {
      let instant;
      try { instant = zonedSlotInstant(day, lane.slots[index], lane.time_zone); } catch { continue; }
      const slotMs = Date.parse(instant);
      if (slotMs >= afterMs && slotMs <= cutoff) result.push(instant);
    }
    day = previousDay(day);
  }
  return result.reverse();
}

function publicationFor(receipts, lane, slot) {
  return receipts.find((receipt) => (
    verifyMarketingVideoPublicationReceipt(receipt)
    && receipt.provider_reconciled === true
    && receipt.product_id === lane.product
    && receipt.locale === lane.locale
    && receipt.platform === lane.platform
    && receipt.slot === slot
  )) || null;
}

function livenessPayload(lane, slot, receipt) {
  return {
    lane: lane.lane_id,
    product: lane.product,
    locale: lane.locale,
    platform: lane.platform,
    slot,
    status: receipt ? "published" : "missed",
    public_url: receipt ? receipt.public_url : "unavailable",
    retry_state: receipt ? "not_required" : "unavailable",
    ...(lane.account ? { account: lane.account } : {}),
  };
}

function payloadRef(payload) {
  return `marketing-liveness://${encodeURIComponent(JSON.stringify(payload))}`;
}

function parsePayloadRef(ref) {
  const match = LIVENESS_REF.exec(required(ref, "marketing liveness ref"));
  if (!match) throw new Error("marketing liveness ref is invalid");
  let payload;
  try { payload = JSON.parse(decodeURIComponent(match[1])); } catch { throw new Error("marketing liveness ref is invalid"); }
  for (const key of ["lane", "product", "locale", "platform", "status"]) {
    if (!Object.hasOwn(payload, key)) throw new Error("marketing liveness ref is invalid");
  }
  if (payload.status === "summary") {
    if (!IDENTIFIER.test(payload.lane) || !IDENTIFIER.test(payload.product) || !LOCALE.test(payload.locale) || payload.platform !== "multi" || !["daily", "weekly"].includes(payload.period) || !SNAPSHOT_REF.test(String(payload.summary_ref || "")) || !Number.isFinite(Date.parse(payload.observed_at))) throw new Error("marketing summary ref is invalid");
    return payload;
  }
  if (!Object.hasOwn(payload, "public_url")) throw new Error("marketing liveness ref is invalid");
  if (payload.status === "observed") {
    const postizPhotoMetric = payload.platform === "tiktok"
      && payload.publication_evidence === "postiz_published_exact_assets"
      && (payload.public_url === "unavailable" || POSTIZ_TIKTOK_POST_URL.test(String(payload.public_url || "")));
    if (
      !IDENTIFIER.test(payload.lane) || !IDENTIFIER.test(payload.product) || !LOCALE.test(payload.locale)
      || !["instagram", "tiktok"].includes(payload.platform) || !ACCOUNT.test(String(payload.account || ""))
      || (payload.correction !== undefined && payload.correction !== true)
      || !METRIC_WINDOWS.has(payload.window) || !SNAPSHOT_REF.test(String(payload.snapshot_ref || ""))
      || !Number.isFinite(Date.parse(payload.observed_at))
      || (!postizPhotoMetric && !(payload.platform === "instagram" ? /^https:\/\/www\.instagram\.com\/(?:reel|p)\/[A-Za-z0-9_-]+\/?$/.test(payload.public_url) : /^https:\/\/www\.tiktok\.com\/@[^/]+\/video\/[0-9]+\/?$/.test(payload.public_url)))
      || (payload.metrics !== undefined && (!payload.metrics || typeof payload.metrics !== "object" || Array.isArray(payload.metrics)
        || Object.values(payload.metrics).some((metric) => !metric || !["measured", "derived", "unavailable"].includes(metric.status))))
    ) throw new Error("marketing metric ref is invalid");
    return payload;
  }
  for (const key of ["slot", "retry_state"]) if (!Object.hasOwn(payload, key)) throw new Error("marketing liveness ref is invalid");
  exactInstant(payload.slot, "marketing liveness slot");
  const postizPhotoProof = payload.platform === "tiktok"
    && payload.status === "published"
    && (payload.public_url === "unavailable" || POSTIZ_TIKTOK_POST_URL.test(String(payload.public_url || "")))
    && payload.publication_evidence === "postiz_published_exact_assets";
  if (
    !IDENTIFIER.test(payload.lane)
    || !IDENTIFIER.test(payload.product)
    || !LOCALE.test(payload.locale)
    || !["instagram", "tiktok", "youtube"].includes(payload.platform)
    || (payload.account !== undefined && !ACCOUNT.test(String(payload.account)))
    || !["published", "missed"].includes(payload.status)
    || (payload.status === "published" && !postizPhotoProof && !(
      payload.platform === "tiktok"
        ? /^https:\/\/www\.tiktok\.com\/@[^/]+\/video\/[0-9]+\/?$/.test(payload.public_url)
        : payload.platform === "instagram"
          ? /^https:\/\/www\.instagram\.com\/(?:reel|p)\/[A-Za-z0-9_-]+\/?$/.test(payload.public_url)
          : /^https:\/\/www\.youtube\.com\/(?:shorts\/[A-Za-z0-9_-]+|watch\?v=[A-Za-z0-9_-]+(?:&[^#]+)?)\/?$/.test(payload.public_url)
    ))
    || (payload.status === "missed" && payload.public_url !== "unavailable")
    || (payload.status === "published" && payload.retry_state !== "not_required")
    || (payload.status === "missed" && payload.retry_state !== "unavailable")
  ) throw new Error("marketing liveness ref is invalid");
  return payload;
}

function buildMarketingLivenessJob(input = {}) {
  const tenantId = required(input.tenantId, "marketing liveness tenant");
  const telegramTokenRef = required(input.telegramTokenRef, "Telegram token ref");
  const telegramChatRef = required(input.telegramChatRef, "Telegram chat ref");
  if (!SECRET_REF.test(telegramTokenRef) || !CHAT_REF.test(telegramChatRef)) {
    throw new Error("marketing liveness Telegram reference is invalid");
  }
  const payload = input.payload;
  const ref = payloadRef(payload);
  parsePayloadRef(ref);
  const digest = createHash("sha256").update(`${tenantId}\n${ref}`).digest("hex");
  return buildRuntimeJob({
    jobId: `marketing-liveness:${digest}`,
    tenantId,
    loopId: LOOP_ID,
    capability: CAPABILITY,
    effectClass: "message",
    effectKey: `telegram:marketing-liveness:${digest}`,
    inputRefs: {
      marketing_liveness_ref: ref,
      telegram_token_ref: telegramTokenRef,
      telegram_chat_ref: telegramChatRef,
    },
    maxAttempts: 3,
  });
}

function planMarketingLivenessJobs(input = {}) {
  const receipts = Array.isArray(input.receipts) ? input.receipts : [];
  const jobs = [];
  for (const laneInput of Array.isArray(input.lanes) ? input.lanes : []) {
    const lane = normalizeLane(laneInput);
    for (const slot of expectedSlots(lane, input.nowMs)) {
      jobs.push(buildMarketingLivenessJob({
        tenantId: input.tenantId,
        telegramTokenRef: input.telegramTokenRef,
        telegramChatRef: input.telegramChatRef,
        payload: livenessPayload(lane, slot, publicationFor(receipts, lane, slot)),
      }));
    }
  }
  return jobs;
}

function renderMessage(payload) {
  if (payload.status === "summary") return payload.message;
  if (payload.status === "observed") {
    const labels = {
      views: "閲覧数", reach: "リーチ", impressions: "表示回数", likes: "いいね数",
      comments: "コメント数", shares: "シェア数", saves: "保存数", watch_time: "視聴時間",
      average_watch_time: "平均視聴時間", completion: "完視聴率", engagement: "エンゲージメント率",
      account_totals: "アカウント全体の指標", account_views: "アカウント閲覧数",
      account_reach: "アカウントリーチ", account_followers: "フォロワー数",
      account_following: "フォロー中", account_total_likes: "総いいね数", account_videos: "投稿数",
      account_recent_views: "直近20投稿の閲覧数", account_recent_likes: "直近20投稿のいいね数",
      account_recent_comments: "直近20投稿のコメント数", account_recent_shares: "直近20投稿のシェア数",
    };
    const product = { "honne-ai": "Honne", "anicca-ios": "Anicca iOS", anicca: "Anicca" }[payload.product] || "アプリ";
    const platform = { tiktok: "TikTok", instagram: "Instagram", youtube: "YouTube", multi: "複数SNS" }[payload.platform] || "SNS";
    const window = { "2h": "2時間", "24h": "24時間", "72h": "72時間", "7d": "7日間", daily: "日次", current: "現在" }[payload.window] || "指定期間";
    const account = payload.account ? "（" + payload.account + "）" : "（登録済みアカウント）";
    const measured = [];
    const unavailable = [];
    const unsupported = [];
    for (const [key, metric] of Object.entries(payload.metrics || {})) {
      const label = labels[key] || "その他の指標";
      if (metric.status === "unavailable") {
        (metric.reason === "metric_not_supported" ? unsupported : unavailable).push(label);
      } else {
        const value = metric.percent != null ? String(metric.percent) + "%" : String(metric.value);
        const sourceDate = metric.source_date ? "（" + metric.source_date + "時点）" : "";
        measured.push(label + " " + value + sourceDate);
      }
    }
    const observedTime = Date.parse(String(payload.metric_observed_at || ""));
    const observedText = Number.isFinite(observedTime)
      ? new Intl.DateTimeFormat("ja-JP", { timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(observedTime)
      : "";
    const current = payload.current_observation
      ? "今回取得した現在値です" + (observedText ? "（取得時刻 " + observedText + "）" : "") + "。過去のチェックポイント値ではありません。"
      : "";
    const identity = payload.publication_evidence === "postiz_published_exact_assets"
      ? "Postizの公開記録と承認済み素材の一致を確認しました。"
      : "";
    const url = typeof payload.public_url === "string" && payload.public_url.startsWith("https://")
      ? "投稿リンク: " + payload.public_url + "。"
      : "投稿リンクは取得できませんでした。";
    const header = "📊 " + product + "の" + platform + account + "、" + window
      + (payload.correction ? "の訂正メトリクスです。" : "のメトリクスです。");
    const parts = [header];
    if (current) parts.push(current);
    if (measured.length) parts.push(measured.join("、") + "。");
    if (unavailable.length) parts.push("取得できなかった指標: " + unavailable.join("、") + "。");
    if (unsupported.length) parts.push("APIでは提供されていない指標: " + unsupported.join("、") + "。");
    if (identity) parts.push(identity);
    parts.push(url);
    return parts.join(" ");
  }
  const accountPattern = payload.platform === "tiktok"
    ? /^https:\/\/www\.tiktok\.com\/@([^/]+)\/video\//
    : payload.platform === "instagram"
      ? /^https:\/\/www\.instagram\.com\/(?:reel|p)\/([^/]+)/
      : null;
  const accountHandle = accountPattern
    ? String(payload.public_url || "").match(accountPattern)?.[1]
    : null;
  const account = payload.account || (accountHandle ? `@${accountHandle}` : `the configured ${payload.lane} account`);
  const product = { "honne-ai": "Honne AI", "anicca-ios": "Anicca iOS", anicca: "Anicca" }[payload.product]
    || payload.product;
  const locale = { en: "English", ja: "Japanese" }[payload.locale] || payload.locale;
  const platform = { tiktok: "TikTok", instagram: "Instagram", youtube: "YouTube" }[payload.platform]
    || payload.platform;
  if (payload.status === "published") {
    if (payload.publication_evidence === "postiz_published_exact_assets") {
      const postLink = payload.public_url === "unavailable" ? "投稿リンク未取得。" : `投稿リンク: ${payload.public_url}。`;
      return `Life Manager::: ${product}'s ${locale} photo carousel was published on ${platform} for ${account} in the ${payload.slot} slot. Postiz API status: PUBLISHED. The exact locally stored approved assets and caption matched. ${postLink}Retry: ${payload.retry_state}.`;
    }
    return `Life Manager::: ${product}'s ${locale} post was published on ${platform} for ${account} in the ${payload.slot} slot. Status: published. Public URL: ${payload.public_url}. Retry: ${payload.retry_state}.`;
  }
  return `Life Manager::: ${product}'s ${locale} post was not published on ${platform} for ${account} in the ${payload.slot} slot. Status: missed. Public URL: unavailable. Retry: unavailable.`;
}

async function executeMarketingLivenessJob(job, deps = {}) {
  if (!job || job.capability !== CAPABILITY || job.effect_class !== "message") {
    throw new Error("marketing liveness job contract mismatch");
  }
  const payload = parsePayloadRef(job.input_refs && job.input_refs.marketing_liveness_ref);
  const expected = buildMarketingLivenessJob({
    tenantId: job.tenant_id,
    telegramTokenRef: job.input_refs.telegram_token_ref,
    telegramChatRef: job.input_refs.telegram_chat_ref,
    payload,
  });
  if (
    job.job_id !== expected.job_id
    || job.loop_id !== expected.loop_id
    || job.effect_key !== expected.effect_key
    || !isDeepStrictEqual(job.input_refs, expected.input_refs)
  ) throw new Error("marketing liveness job contract mismatch");
  if (!deps.secretProvider || !deps.chatProvider) throw new Error("marketing liveness provider is required");
  const token = await deps.secretProvider.get(job.tenant_id, job.input_refs.telegram_token_ref);
  const chatId = await deps.chatProvider.get(job.tenant_id, job.input_refs.telegram_chat_ref);
  let renderedPayload = payload;
  if (payload.status === "summary") {
    if (!deps.snapshotProvider) throw new Error("marketing summary snapshot provider is required");
    const snapshot = await deps.snapshotProvider.get(job.tenant_id, payload.summary_ref);
    if (!snapshot || snapshot.kind !== "marketing_product_metric_summary" || snapshot.period !== payload.period || typeof snapshot.message !== "string" || !(snapshot.message.startsWith("Life Manager:::") || snapshot.message.startsWith("Life Manager：")) || Buffer.byteLength(snapshot.message) > 4096 || !Array.isArray(snapshot.source_refs) || snapshot.source_refs.some((ref) => !SNAPSHOT_REF.test(ref))) throw new Error("marketing summary snapshot mismatch");
    renderedPayload = { ...payload, report_key: snapshot.report_key, source_refs: snapshot.source_refs, message: snapshot.message };
  }
  if (payload.status === "observed" && payload.metrics === undefined) {
    if (!deps.snapshotProvider) throw new Error("marketing metric snapshot provider is required");
    const snapshot = await deps.snapshotProvider.get(job.tenant_id, payload.snapshot_ref);
    if (!snapshot || snapshot.public_url !== payload.public_url || snapshot.window !== payload.window || !snapshot.post) throw new Error("marketing metric snapshot mismatch");
    const compact = Object.fromEntries(Object.entries(snapshot.post).map(([key, metric]) => [key,
      metric.status === "unavailable" ? { status: "unavailable", reason: metric.reason }
        : metric.status === "derived" ? { status: "derived", percent: metric.percent }
          : { status: "measured", value: metric.value }]));
    if (snapshot.sources?.postiz_account?.status === "unavailable") compact.account_totals = { status: "unavailable" };
    else if (snapshot.account_metrics && typeof snapshot.account_metrics === "object" && !Array.isArray(snapshot.account_metrics)) {
      for (const [key, metric] of Object.entries(snapshot.account_metrics)) {
        if (!metric || !["measured", "derived", "unavailable"].includes(metric.status)) throw new Error("marketing account metric snapshot invalid");
        compact[`account_${key}`] = metric.status === "unavailable" ? { status: "unavailable" }
          : metric.status === "derived" ? { status: "derived", percent: metric.percent }
            : { status: "measured", value: metric.value };
      }
    } else if (Array.isArray(snapshot.account_metrics)) {
      for (const row of snapshot.account_metrics) {
        const key = String(row.label || "").toLowerCase().replace(/[^a-z0-9]+/g, "_");
        const point = row.data?.at(-1);
        const value = point?.total == null || String(point.total).trim() === "" ? NaN : Number(point.total);
        if (!key || !Number.isFinite(value) || value < 0) continue;
        compact[`account_${key}`] = { status: "measured", value, source_date: point.date };
      }
    } else compact.account_totals = { status: "unavailable" };
    renderedPayload = { ...payload, metrics: compact,
      ...(snapshot.historical_checkpoint === false ? { current_observation: true, metric_observed_at: snapshot.source_observed_at || snapshot.observed_at } : {}),
      ...(Array.isArray(snapshot.observation_windows) ? { window_summary: snapshot.observation_windows.map((row) => `${row.window} ${row.status}`) } : {}) };
  }
  let providerResult;
  try {
    providerResult = await (deps.sendTelegram || sendMessage)(token, chatId, renderMessage(renderedPayload));
  } catch (error) {
    throw Object.assign(new Error("marketing liveness Telegram send failed", { cause: error }), { unknownEffect: true });
  }
  const messageId = Number(providerResult && providerResult.result && providerResult.result.message_id);
  if (!providerResult || providerResult.ok !== true || !Number.isSafeInteger(messageId) || messageId < 1) {
    const error = new Error("marketing liveness Telegram receipt is invalid");
    error.unknownEffect = true;
    throw error;
  }
  return { receipt: {
    schema_version: 1,
    kind: "telegram_marketing_liveness",
    ...renderedPayload,
    message_id: messageId,
    chat_id_hash: hashChatId(chatId),
    sent_at: (deps.now || (() => new Date().toISOString()))(),
  } };
}

function verifyMarketingLivenessReceipt(receipt) {
  if (!receipt || receipt.schema_version !== 1 || receipt.kind !== "telegram_marketing_liveness") return false;
  try { parsePayloadRef(payloadRef(receipt)); } catch { return false; }
  return Number.isSafeInteger(receipt.message_id) && receipt.message_id > 0
    && /^[0-9a-f]{64}$/.test(String(receipt.chat_id_hash || ""))
    && Number.isFinite(Date.parse(receipt.sent_at));
}

function createMarketingLivenessLoopAdapter(deps = {}) {
  return Object.freeze({
    plan: async (context = {}) => planMarketingLivenessJobs(context),
    execute: (job, services = {}) => executeMarketingLivenessJob(job, { ...deps, ...services }),
    reconcile: async () => ({ state: "unknown" }),
    verify: verifyMarketingLivenessReceipt,
    report(receipt) {
      if (!verifyMarketingLivenessReceipt(receipt)) throw new Error("marketing liveness receipt verification failed");
      return { product: receipt.product, locale: receipt.locale, platform: receipt.platform, slot: receipt.slot, status: receipt.status, public_url: receipt.public_url, retry_state: receipt.retry_state };
    },
  });
}

module.exports = {
  ADAPTER_ID, CAPABILITY, LOOP_ID, ARMED,
  buildMarketingLivenessJob, createMarketingLivenessLoopAdapter,
  executeMarketingLivenessJob, expectedSlots, planMarketingLivenessJobs,
  renderMessage, verifyMarketingLivenessReceipt,
};
