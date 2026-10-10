"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const DIRECT = /^https:\/\/www\.tiktok\.com\/@([A-Za-z0-9._-]+)\/video\/(\d+)$/;
const POSTIZ_PHOTO_URL = /^https:\/\/www\.tiktok\.com\/@[A-Za-z0-9._-]+\/(?:photo|video)\/\d+\/?$/;
const WINDOWS = new Set(["2h", "24h", "72h", "7d"]);
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const LOCALE = /^[a-z]{2}(?:-[A-Z]{2})?$/;
const ACCOUNT = /^@[A-Za-z0-9._-]{1,127}$/;
const ACCOUNT_LABELS = Object.freeze({
  Followers: "followers",
  Following: "following",
  "Total Likes": "total_likes",
  Videos: "videos",
  Views: "recent_views",
  "Recent Likes": "recent_likes",
  "Recent Comments": "recent_comments",
  "Recent Shares": "recent_shares",
});

function normalized(value) {
  return String(value || "").normalize("NFKC").replace(/\s+/g, " ").trim();
}

function metric(value, label) {
  const number = Number(value);
  if (!Number.isSafeInteger(number) || number < 0) throw new Error(`TikTok ${label} metric invalid`);
  return { status: "measured", value: number, source: "tiktok_native_embedded_json" };
}

function extractTikTokNativeMetrics(scripts, expected) {
  const match = DIRECT.exec(String(expected.publicUrl || ""));
  if (!match || `@${match[1]}` !== expected.account || match[2] !== expected.videoId) {
    throw new Error("TikTok native metric identity invalid");
  }
  let item;
  for (const source of scripts) {
    try {
      const parsed = JSON.parse(source);
      const candidate = parsed?.__DEFAULT_SCOPE__?.["webapp.video-detail"]?.itemInfo?.itemStruct;
      if (String(candidate?.id || "") === expected.videoId) item = candidate;
    } catch {}
  }
  if (
    !item
    || `@${item.author?.uniqueId || ""}` !== expected.account
    || normalized(item.desc) !== normalized(expected.caption)
  ) throw new Error("TikTok native metric content mismatch");
  const stats = item.stats || {};
  const post = {
    views: metric(stats.playCount, "views"),
    likes: metric(stats.diggCount, "likes"),
    comments: metric(stats.commentCount, "comments"),
    shares: metric(stats.shareCount, "shares"),
    saves: metric(stats.collectCount, "saves"),
    reach: { status: "unavailable", value: null, reason: "metric_not_supported" },
    watch_time: { status: "unavailable", value: null, reason: "metric_not_supported" },
    completion: { status: "unavailable", value: null, reason: "metric_not_supported" },
  };
  const numerator = post.likes.value + post.comments.value + post.shares.value + post.saves.value;
  post.engagement = post.views.value === 0
    ? { status: "unavailable", value: null, reason: "zero_view_denominator" }
    : {
        status: "derived",
        numerator,
        denominator: post.views.value,
        rate: Number((numerator / post.views.value).toFixed(8)),
        percent: Number(((numerator / post.views.value) * 100).toFixed(2)),
        formula: "(likes+comments+shares+saves)/views",
      };
  return Object.freeze({ post, caption: item.desc, created_at: new Date(Number(item.createTime) * 1000).toISOString() });
}

function extractPostizAccountMetrics(rows) {
  if (!Array.isArray(rows)) throw new Error("Postiz account analytics invalid");
  const values = {};
  for (const [label, key] of Object.entries(ACCOUNT_LABELS)) {
    const row = rows.find((candidate) => candidate?.label === label);
    const value = Number(row?.data?.[0]?.total);
    if (!Number.isSafeInteger(value) || value < 0) throw new Error(`Postiz ${label} metric invalid`);
    values[key] = {
      status: "measured",
      value,
      source: "postiz_account_analytics",
      ...((key.startsWith("recent_")) ? { scope: "latest_20_videos" } : {}),
    };
  }
  return Object.freeze(values);
}

function postizPostSource(rows) {
  if (!Array.isArray(rows)) throw new Error("Postiz post analytics invalid");
  if (rows.length === 0) {
    return Object.freeze({ status: "unavailable", reason: "empty_response", response: "empty_array" });
  }
  const metrics = {};
  for (const row of rows) {
    const key = String(row?.label || "").trim().toLowerCase();
    const value = Number(row?.data?.[0]?.total);
    if (!/^(views|likes|comments|shares)$/.test(key) || !Number.isSafeInteger(value) || value < 0) {
      throw new Error("Postiz post analytics row invalid");
    }
    metrics[key] = { status: "measured", value, source: "postiz_post_analytics" };
  }
  return Object.freeze({ status: "measured", metrics });
}

function persistTikTokCombinedSnapshot(input) {
  const direct = DIRECT.exec(String(input.publicUrl || ""));
  if (
    !WINDOWS.has(input.window)
    || !IDENTIFIER.test(String(input.tenantId || ""))
    || !IDENTIFIER.test(String(input.productId || ""))
    || !IDENTIFIER.test(String(input.integrationId || ""))
    || !IDENTIFIER.test(String(input.providerPostId || ""))
    || !LOCALE.test(String(input.locale || ""))
    || !direct
    || `@${direct[1]}` !== input.account
    || direct[2] !== input.videoId
    || !Number.isFinite(Date.parse(input.publishedAt))
    || !Number.isFinite(Date.parse(input.observedAt))
  ) throw new Error("TikTok combined metric snapshot identity invalid");
  const directory = path.resolve(input.dataDir, "tenants", input.tenantId, "marketing", "metrics", input.account.slice(1), input.videoId);
  const file = path.join(directory, `${input.window}.combined.json`);
  const captionSha256 = crypto.createHash("sha256").update(Buffer.from(input.caption)).digest("hex");
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  if (fs.existsSync(file)) {
    const existing = JSON.parse(fs.readFileSync(file, "utf8"));
    if (
      existing.public_url !== input.publicUrl || existing.video_id !== input.videoId
      || existing.window !== input.window || existing.tenant_id !== input.tenantId
      || existing.product_id !== input.productId || existing.locale !== input.locale
      || existing.account_id !== input.account || existing.caption_sha256 !== captionSha256
      || existing.integration_id !== input.integrationId || existing.provider_post_id !== input.providerPostId
    ) throw new Error("TikTok combined metric replay mismatch");
    return Object.freeze({ created: false, file, snapshot: existing });
  }
  const snapshot = {
    schema_version: 1,
    kind: "tiktok_combined_metric_snapshot",
    tenant_id: input.tenantId,
    product_id: input.productId,
    locale: input.locale,
    account_id: input.account,
    integration_id: input.integrationId,
    provider_post_id: input.providerPostId,
    video_id: input.videoId,
    public_url: input.publicUrl,
    window: input.window,
    published_at: input.publishedAt,
    observed_at: input.observedAt,
    caption_sha256: captionSha256,
    sources: {
      tiktok_native: { status: "measured", identity_verified: true },
      postiz_post: postizPostSource(input.postizPostAnalytics),
      postiz_account: { status: "measured", scope: "current account plus aggregate of latest 20 videos" },
    },
    post: input.metrics.post,
    account_metrics: extractPostizAccountMetrics(input.postizAccountAnalytics),
  };
  const temporary = `${file}.tmp-${process.pid}-${crypto.randomUUID()}`;
  fs.writeFileSync(temporary, `${JSON.stringify(snapshot, null, 2)}\n`, { mode: 0o600, flag: "wx" });
  fs.renameSync(temporary, file);
  fs.chmodSync(file, 0o600);
  return Object.freeze({ created: true, file, snapshot });
}

function persistPostizPhotoSnapshot(input) {
  if (!WINDOWS.has(input.window) || !IDENTIFIER.test(String(input.tenantId || "")) || !IDENTIFIER.test(String(input.productId || "")) || !IDENTIFIER.test(String(input.integrationId || "")) || !IDENTIFIER.test(String(input.providerPostId || "")) || !LOCALE.test(String(input.locale || "")) || !ACCOUNT.test(String(input.account || "")) || (input.publicUrl !== "unavailable" && !POSTIZ_PHOTO_URL.test(String(input.publicUrl || ""))) || !Number.isFinite(Date.parse(input.publishedAt)) || !Number.isFinite(Date.parse(input.observedAt))) throw new Error("Postiz photo metric snapshot identity invalid");
  const source = postizPostSource(input.postizPostAnalytics);
  const unavailable = { status: "unavailable", value: null, reason: "postiz_post_metric_unavailable" };
  const post = Object.fromEntries(["views", "likes", "comments", "shares"].map((key) => [key, source.status === "measured" && source.metrics[key] ? source.metrics[key] : { ...unavailable }]));
  for (const key of ["saves", "reach", "watch_time", "completion", "engagement"]) post[key] = { status: "unavailable", value: null, reason: "metric_not_supported" };
  const directory = path.resolve(input.dataDir, "tenants", input.tenantId, "marketing", "metrics", input.account.slice(1), input.providerPostId);
  const file = path.join(directory, `${input.window}.combined.json`);
  const captionSha256 = crypto.createHash("sha256").update(Buffer.from(input.caption)).digest("hex");
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  if (fs.existsSync(file)) return Object.freeze({ created: false, file, snapshot: JSON.parse(fs.readFileSync(file, "utf8")) });
  const snapshot = { schema_version: 1, kind: "tiktok_postiz_photo_metric_snapshot", tenant_id: input.tenantId, product_id: input.productId, locale: input.locale, account_id: input.account, integration_id: input.integrationId, provider_post_id: input.providerPostId, video_id: input.providerPostId, public_url: input.publicUrl, window: input.window, published_at: input.publishedAt, observed_at: input.observedAt, caption_sha256: captionSha256, sources: { tiktok_native: { status: "unavailable", reason: "photo_url_not_required" }, postiz_post: source, postiz_account: { status: "measured", scope: "current account plus aggregate of latest 20 videos" } }, post, account_metrics: extractPostizAccountMetrics(input.postizAccountAnalytics) };
  const temporary = `${file}.tmp-${process.pid}-${crypto.randomUUID()}`; fs.writeFileSync(temporary, `${JSON.stringify(snapshot, null, 2)}\n`, { mode: 0o600, flag: "wx" }); fs.renameSync(temporary, file); fs.chmodSync(file, 0o600);
  return Object.freeze({ created: true, file, snapshot });
}

function persistTikTokNativeSnapshot(input) {
  const direct = DIRECT.exec(String(input.publicUrl || ""));
  if (
    !WINDOWS.has(input.window)
    || !IDENTIFIER.test(String(input.tenantId || ""))
    || !IDENTIFIER.test(String(input.productId || ""))
    || !LOCALE.test(String(input.locale || ""))
    || !direct
    || `@${direct[1]}` !== input.account
    || direct[2] !== input.videoId
    || !Number.isFinite(Date.parse(input.publishedAt))
    || !Number.isFinite(Date.parse(input.observedAt))
  ) throw new Error("TikTok native metric snapshot identity invalid");
  const directory = path.resolve(input.dataDir, "tenants", input.tenantId, "marketing", "metrics", input.account.slice(1), input.videoId);
  const file = path.join(directory, `${input.window}.json`);
  const captionSha256 = crypto.createHash("sha256").update(Buffer.from(input.caption)).digest("hex");
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  if (fs.existsSync(file)) {
    const existing = JSON.parse(fs.readFileSync(file, "utf8"));
    if (
      existing.public_url !== input.publicUrl
      || existing.video_id !== input.videoId
      || existing.window !== input.window
      || existing.tenant_id !== input.tenantId
      || existing.product_id !== input.productId
      || existing.locale !== input.locale
      || existing.account_id !== input.account
      || existing.caption_sha256 !== captionSha256
    ) {
      throw new Error("TikTok native metric replay mismatch");
    }
    return Object.freeze({ created: false, file, snapshot: existing });
  }
  const snapshot = {
    schema_version: 1,
    kind: "tiktok_native_metric_snapshot",
    tenant_id: input.tenantId,
    product_id: input.productId,
    locale: input.locale,
    account_id: input.account,
    video_id: input.videoId,
    public_url: input.publicUrl,
    window: input.window,
    published_at: input.publishedAt,
    observed_at: input.observedAt,
    caption_sha256: captionSha256,
    post: input.metrics.post,
  };
  const temporary = `${file}.tmp-${process.pid}-${crypto.randomUUID()}`;
  fs.writeFileSync(temporary, `${JSON.stringify(snapshot, null, 2)}\n`, { mode: 0o600, flag: "wx" });
  fs.renameSync(temporary, file);
  fs.chmodSync(file, 0o600);
  return Object.freeze({ created: true, file, snapshot });
}

module.exports = {
  extractPostizAccountMetrics,
  extractTikTokNativeMetrics,
  persistTikTokCombinedSnapshot,
  persistPostizPhotoSnapshot,
  persistTikTokNativeSnapshot,
  postizPostSource,
};
