"use strict";
const assert = require("node:assert/strict"); const fs = require("node:fs"); const os = require("node:os"); const path = require("node:path"); const test = require("node:test"); const { importContentObject } = require("../lib/content-object-store.js"); const { persistAniccaDaily, persistAttributionCoverage, persistHonneDaily, persistWeeklyReview } = require("./marketing-product-summary.js");

test("attribution coverage joins product totals while keeping activation and retention unavailable", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-attribution-summary-")); const day = "2026-08-23"; const objectDir = path.join(dataDir, "objects");
  const source = path.join(dataDir, "source.json"); fs.writeFileSync(source, "{}\n"); const ref = importContentObject(source, { objectDir }).ref;
  const ascDir = path.join(dataDir, "tenants/dais-local/marketing/attribution/asc", day); fs.mkdirSync(ascDir, { recursive: true });
  fs.writeFileSync(path.join(ascDir, "acquisition.json"), JSON.stringify({ snapshot_ref: ref, products: [{ product_id: "anicca-ios", source_status: "measured", attribution_status: "partial", attribution_reason: "campaign_metrics_observed_for_subset", campaign_id: "anicca-ios_youtube_en", campaign_status: "measured", metrics: { first_time_downloads: { status: "measured", value: 1 }, campaign_first_time_downloads: { status: "measured", value: 1 }, campaign_impressions: { status: "measured", value: 12 } } }, { product_id: "honne-ai", source_status: "unavailable", attribution_status: "unattributed", attribution_reason: "campaign_link_configured_no_product_readback", campaign_id: "honne_en_base_20260823", campaign_status: "unavailable", metrics: { first_time_downloads: { status: "unavailable", value: null, reason: "report_pending" }, campaign_first_time_downloads: { status: "unavailable", value: null, reason: "report_pending" }, campaign_impressions: { status: "unavailable", value: null, reason: "report_pending" } } }] }));
  const rcDir = path.join(dataDir, "tenants/dais-local/marketing/attribution/revenuecat", day); fs.mkdirSync(rcDir, { recursive: true });
  fs.writeFileSync(path.join(rcDir, "subscriptions.json"), JSON.stringify({ snapshot_ref: ref, products: ["anicca-ios", "honne-ai"].map((product_id) => ({ product_id, source_status: "unavailable", metrics: { trial_starts: { status: "unavailable", value: null, reason: "missing" }, active_subscriptions: { status: "unavailable", value: null, reason: "missing" }, renewals: { status: "unavailable", value: null, reason: "missing" }, cancellations: { status: "unavailable", value: null, reason: "missing" }, proceeds_usd: { status: "unavailable", value: null, reason: "missing" } } })) }));
  const first = persistAttributionCoverage(dataDir, day, "2026-08-23T13:00:00.000Z"); const replay = persistAttributionCoverage(dataDir, day, "2026-08-23T14:00:00.000Z");
  assert.equal(first.created, true); assert.equal(replay.created, false); assert.equal(first.snapshot.source_refs.length, 2);
  assert.match(first.snapshot.message, /Anicca iOS: Install 1/); assert.match(first.snapshot.message, /Activation 取得不可/); assert.match(first.snapshot.message, /D1 retention 取得不可/); assert.match(first.snapshot.message, /Honne AI: Install 取得不可/); assert.match(first.snapshot.message, /Honne AI: .*campaign attribution: unattributed \(campaign_link_configured_no_product_readback\)/);
  assert.equal(first.snapshot.products[0].attribution_status, "partial"); assert.equal(first.snapshot.products[0].attribution_reason, "campaign_metrics_observed_for_subset"); assert.equal(first.snapshot.products[0].campaign_id, "anicca-ios_youtube_en"); assert.equal(first.snapshot.products[0].metrics.campaign_first_time_downloads.value, 1); assert.equal(first.snapshot.products[0].metrics.campaign_impressions.value, 12); assert.equal(first.snapshot.products[1].metrics.campaign_first_time_downloads.value, null); assert.equal(first.snapshot.coverage.partial, null); assert.equal(first.snapshot.coverage.reason, "campaign_metrics_observed_for_subset");
  assert.match(first.snapshot.message, /campaign attribution: partial.*campaign_metrics_observed_for_subset/); assert.match(first.snapshot.message, /ASC初回DL 1/); assert.match(first.snapshot.message, /ASC impressions 12/);
  assert.equal(first.snapshot.products[0].metrics.activation.value, null); assert.equal(first.snapshot.products[0].metrics.d7_retention.value, null);
});

test("Honne daily summary binds EN and JA immutable daily sources and replays", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-honne-summary-")); const day = "2026-08-22";
  for (const target of [{ owner: "honne_reveal", account: "@honne_reveal", locale: "en", video: "1", views: 208 }, { owner: "honnevideo", account: "@honnevideo", locale: "ja", video: "2", views: 1035 }]) { const directory = path.join(dataDir, "tenants/dais-local/marketing/metrics", target.owner, target.video, "daily"); fs.mkdirSync(directory, { recursive: true }); fs.writeFileSync(path.join(directory, `${day}.json`), JSON.stringify({ kind: "tiktok_daily_metric_digest", window: "daily", observed_at: `2026-08-22T${target.locale === "en" ? "10" : "11"}:00:00.000Z`, published_at: "2026-08-21T10:00:00.000Z", account_id: target.account, locale: target.locale, public_url: `https://www.tiktok.com/${target.account}/video/${target.video}`, post: { views: { status: "measured", value: target.views }, likes: { status: "measured", value: 1 }, comments: { status: "measured", value: 0 }, shares: { status: "measured", value: 0 }, saves: { status: "unavailable" }, engagement: { status: "derived", percent: 1 } }, account_metrics: { followers: { status: "measured", value: 5 }, following: { status: "measured", value: 1 }, total_likes: { status: "measured", value: 10 }, videos: { status: "measured", value: 2 } } })); }
  const first = persistHonneDaily(dataDir, day, "2026-08-22T13:00:00.000Z"); const replay = persistHonneDaily(dataDir, day, "2026-08-22T14:00:00.000Z"); assert.equal(first.created, true); assert.equal(replay.created, false); assert.equal(first.snapshot.source_refs.length, 2); assert.match(first.snapshot.message, /@honne_reveal TikTok: Views 208/); assert.match(first.snapshot.message, /@honnevideo TikTok: Views 1035/); assert.match(first.snapshot.message, /Funnel: Install 取得不可、Activation 取得不可/); assert.equal(fs.statSync(first.file).mode & 0o777, 0o600);
});

test("Anicca daily summary binds main sources and keeps JP4 and HE unavailable", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-anicca-summary-")); const day = "2026-08-22"; const rows = [{ owner: "anicca.jp", account: "@anicca.jp", platform: "tiktok", url: "https://www.tiktok.com/@anicca.jp/video/1" }, { owner: "anicca.ios.jp", account: "@anicca.jp1", platform: "instagram", url: "https://www.instagram.com/reel/ABC123/" }];
  for (const [index, target] of rows.entries()) { const directory = path.join(dataDir, "tenants/dais-local/marketing/metrics", target.owner, String(index + 1), "daily"); fs.mkdirSync(directory, { recursive: true }); fs.writeFileSync(path.join(directory, `${day}.json`), JSON.stringify({ kind: `${target.platform}_daily_metric_digest`, window: "daily", observed_at: `2026-08-22T1${index}:00:00.000Z`, published_at: "2026-08-21T10:00:00.000Z", account_id: target.account, locale: "ja", public_url: target.url, post: { views: { status: "measured", value: 100 + index }, likes: { status: "measured", value: 1 }, comments: { status: "measured", value: 0 }, shares: { status: "measured", value: 0 }, saves: { status: "unavailable" }, engagement: { status: "derived", percent: 1 } }, account_metrics: { status: "unavailable" } })); }
  const coverageDir = path.join(dataDir, "tenants/dais-local/marketing/attribution/coverage", day); fs.mkdirSync(coverageDir, { recursive: true }); fs.writeFileSync(path.join(coverageDir, "summary.json"), JSON.stringify({ products: [{ product_id: "anicca-ios", attribution_status: "partial", attribution_reason: "campaign_metrics_observed_for_subset", campaign_id: "anicca-ios_youtube_en", campaign_status: "measured", metrics: { campaign_first_time_downloads: { status: "measured", value: 1 }, campaign_impressions: { status: "measured", value: 12 } } }] }));
  const result = persistAniccaDaily(dataDir, day, "2026-08-22T13:00:00.000Z"); assert.equal(result.created, true); assert.equal(result.snapshot.source_refs.length, 2); assert.match(result.snapshot.message, /@anicca\.jp TikTok: Views 100/); assert.match(result.snapshot.message, /@anicca\.jp1 Instagram: Views 101/); assert.match(result.snapshot.message, /@anicca\.jp4 TikTok: 全social\/account metrics取得不可/); assert.match(result.snapshot.message, /@anicca\.he TikTok: 全social\/account metrics取得不可/); assert.match(result.snapshot.message, /7676500512308481296/); assert.match(result.snapshot.message, /Campaign attribution: partial.*campaign_metrics_observed_for_subset/); assert.match(result.snapshot.message, /ASC初回DL 1/); assert.match(result.snapshot.message, /ASC impressions 12/);
});

test("weekly review binds both products without cross-product winner transfer", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-weekly-summary-")); const day = "2026-08-22";
  for (const [product, label] of [["honne-ai", "Honne AI"], ["anicca-ios", "Anicca iOS"]]) { const directory = path.join(dataDir, "tenants/dais-local/marketing/metrics/summaries", product, "daily"); fs.mkdirSync(directory, { recursive: true }); fs.writeFileSync(path.join(directory, `${day}.json`), JSON.stringify({ schema_version: 1, kind: "marketing_product_metric_summary", period: "daily", report_key: day, observed_at: "2026-08-22T13:00:00.000Z", product_id: product, source_refs: [], message: `Life Manager::: ${label} source values` })); }
  const first = persistWeeklyReview(dataDir, day, "2026-08-22T14:00:00.000Z"); const replay = persistWeeklyReview(dataDir, day, "2026-08-22T15:00:00.000Z"); assert.equal(first.created, true); assert.equal(replay.created, false); assert.equal(first.snapshot.period, "weekly"); assert.equal(first.snapshot.report_key, "2026-W34"); assert.equal(first.snapshot.source_refs.length, 2); assert.match(first.snapshot.message, /Honne AI source values/); assert.match(first.snapshot.message, /Anicca iOS source values/); assert.match(first.snapshot.message, /Cross-product winner: 判定しない/); assert.match(first.snapshot.message, /Attribution coverage: 取得不可/); assert.equal(fs.statSync(first.file).mode & 0o777, 0o600);
});

test("Anicca summary consumes current corrections ahead of retained historical reports", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-summary-current-correction-"));
  const day = "2026-10-11";
  for (const owner of ["anicca.jp", "anicca.ios.jp"]) {
    const directory = path.join(dataDir, "tenants/dais-local/marketing/metrics", owner, "post1", "daily");
    fs.mkdirSync(directory, { recursive: true });
    const snapshot = { observed_at: `${day}T08:30:00.000Z`, published_at: `${day}T07:00:00.000Z`, locale: "ja", account_id: owner === "anicca.jp" ? "@anicca.jp" : "@anicca.jp1",
      public_url: owner === "anicca.jp" ? "https://www.tiktok.com/@anicca.jp/video/1" : "https://www.instagram.com/reel/DdvxhT1jm8F/",
      post: { views: { status: "measured", value: 32 } }, account_metrics: { status: "unavailable" } };
    fs.writeFileSync(path.join(directory, `${day}.json`), JSON.stringify(snapshot));
    fs.writeFileSync(path.join(directory, `${day}.correction.json`), JSON.stringify({ ...snapshot, post: { views: { status: "measured", value: 64 } } }));
    fs.writeFileSync(path.join(directory, `${day}.current.correction.json`), JSON.stringify({ ...snapshot, observed_at: `${day}T09:00:00.000Z`, historical_checkpoint: false,
      post: { views: { status: "measured", value: 2229 } } }));
  }
  const summary = persistAniccaDaily(dataDir, day, `${day}T09:30:00.000Z`);
  assert.match(summary.snapshot.message, /@anicca\.jp1 Instagram: 現在値.*Views 2229/);
});

test("attribution funnel reports app-scoped RevenueCat customer activity and keeps unavailable charts null", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-rc-activity-summary-")); const day = "2026-10-12"; const objectDir = path.join(dataDir, "objects");
  const source = path.join(dataDir, "source.json"); fs.writeFileSync(source, "{}\n"); const ref = importContentObject(source, { objectDir }).ref;
  const metrics = { first_time_downloads: { status: "unavailable", value: null, reason: "report_pending" }, campaign_first_time_downloads: { status: "unavailable", value: null, reason: "campaign_not_observed" }, campaign_impressions: { status: "unavailable", value: null, reason: "campaign_not_observed" } };
  const ascDir = path.join(dataDir, "tenants/dais-local/marketing/attribution/asc", day); fs.mkdirSync(ascDir, { recursive: true });
  fs.writeFileSync(path.join(ascDir, "acquisition.json"), JSON.stringify({ snapshot_ref: ref, products: ["anicca-ios", "honne-ai"].map((product_id) => ({ product_id, source_status: "unavailable", attribution_status: "unattributed", attribution_reason: "campaign_not_configured", campaign_status: "unavailable", metrics })) }));
  const rcDir = path.join(dataDir, "tenants/dais-local/marketing/attribution/revenuecat", day); fs.mkdirSync(rcDir, { recursive: true });
  fs.writeFileSync(path.join(rcDir, "subscriptions.json"), JSON.stringify({ snapshot_ref: ref, products: [
    { product_id: "anicca-ios", source_status: "unavailable", customer_activity_status: "measured", metrics: { customers_new: { status: "measured", value: 19 }, customers_active: { status: "measured", value: 4.29 } } },
    { product_id: "honne-ai", source_status: "unavailable", customer_activity_status: "unavailable", metrics: { customers_new: { status: "unavailable", value: null, reason: "chart_not_enabled" }, customers_active: { status: "unavailable", value: null, reason: "chart_not_enabled" } } },
  ] }));

  const result = persistAttributionCoverage(dataDir, day, "2026-10-12T13:00:00.000Z");
  const anicca = result.snapshot.products.find((product) => product.product_id === "anicca-ios");
  const honne = result.snapshot.products.find((product) => product.product_id === "honne-ai");
  assert.equal(anicca.source_status.revenuecat_customer_activity, "measured");
  assert.equal(anicca.metrics.customers_new_28d.value, 19);
  assert.equal(anicca.metrics.customers_active_daily_average_28d.value, 4.29);
  assert.equal(honne.source_status.revenuecat_customer_activity, "unavailable");
  assert.deepEqual([honne.metrics.customers_new_28d.status, honne.metrics.customers_new_28d.value], ["unavailable", null]);
  assert.match(result.snapshot.message, /新規顧客（直近28日）19/);
  assert.match(result.snapshot.message, /平均DAU（直近28日）4\.29/);
  assert.match(result.snapshot.message, /Honne AI: .*新規顧客（直近28日）取得不可/);
});

test("ASC trailing seven-day averages use distinct source dates and keep partial coverage null", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-asc-seven-day-summary-")); const reportDay = "2026-10-12"; const objectDir = path.join(dataDir, "objects");
  const writeSnapshot = (snapshot) => {
    const source = path.join(dataDir, `asc-${snapshot.report_day}.json`); fs.writeFileSync(source, `${JSON.stringify(snapshot)}\n`);
    const ref = importContentObject(source, { objectDir }).ref; const directory = path.join(dataDir, "tenants/dais-local/marketing/attribution/asc", snapshot.report_day); fs.mkdirSync(directory, { recursive: true });
    fs.writeFileSync(path.join(directory, "acquisition.json"), JSON.stringify({ ...snapshot, snapshot_ref: ref })); return ref;
  };
  const dailyRow = (date, download, impressions, views, viewsUnavailable = false) => ({ date, metrics: {
    first_time_downloads: { status: "measured", value: download },
    impressions: { status: "measured", value: impressions },
    product_page_views: viewsUnavailable ? { status: "unavailable", value: null, reason: "report_pending" } : { status: "measured", value: views },
  } });
  const acquisitionProduct = (product_id, daily_metrics) => ({ product_id, source_status: "measured", attribution_status: "unattributed", attribution_reason: "campaign_not_configured", campaign_status: "unavailable",
    metrics: { first_time_downloads: { status: "measured", value: 0 }, campaign_first_time_downloads: { status: "unavailable", value: null, reason: "campaign_not_configured" }, campaign_impressions: { status: "unavailable", value: null, reason: "campaign_not_configured" } }, daily_metrics });
  const reports = [
    ["2026-10-05", dailyRow("2026-10-05", 1, 10, 2)], ["2026-10-06", dailyRow("2026-10-06", 2, 20, 4)],
    ["2026-10-07", dailyRow("2026-10-07", 3, 30, 6)], ["2026-10-08", dailyRow("2026-10-08", 4, 40, 8)],
    ["2026-10-09", dailyRow("2026-10-09", 5, 50, 10)], ["2026-10-10", dailyRow("2026-10-10", 6, 60, 12)],
    ["2026-10-11", dailyRow("2026-10-11", 7, 70, 14, true)],
    ["2026-10-12", dailyRow("2026-10-07", 300, 30, 6)],
  ];
  let currentAscRef;
  for (const [day, daily] of reports) {
    const snapshot = { schema_version: 1, kind: "marketing_asc_acquisition", tenant_id: "dais-local", report_day: day, lineage_ref: "fixture-lineage", products: [acquisitionProduct("anicca-ios", [daily]), acquisitionProduct("honne-ai", [])], rows: [] };
    const ref = writeSnapshot(snapshot); if (day === reportDay) currentAscRef = ref;
  }
  const rcSource = path.join(dataDir, "rc-source.json"); fs.writeFileSync(rcSource, "{}\n"); const rcRef = importContentObject(rcSource, { objectDir }).ref;
  const rcDirectory = path.join(dataDir, "tenants/dais-local/marketing/attribution/revenuecat", reportDay); fs.mkdirSync(rcDirectory, { recursive: true });
  fs.writeFileSync(path.join(rcDirectory, "subscriptions.json"), JSON.stringify({ snapshot_ref: rcRef, products: ["anicca-ios", "honne-ai"].map((product_id) => ({ product_id, source_status: "unavailable", metrics: {} })) }));

  const result = persistAttributionCoverage(dataDir, reportDay, "2026-10-12T13:00:00.000Z");
  const anicca = result.snapshot.products.find((product) => product.product_id === "anicca-ios");
  const honne = result.snapshot.products.find((product) => product.product_id === "honne-ai");
  assert.deepEqual([anicca.asc_7d.window_start, anicca.asc_7d.window_end], ["2026-10-05", "2026-10-11"]);
  assert.deepEqual([anicca.metrics.asc_7d_first_time_downloads.status, anicca.metrics.asc_7d_first_time_downloads.value, anicca.metrics.asc_7d_first_time_downloads.observed_days], ["measured", 46.42857142857143, 7]);
  assert.deepEqual([anicca.metrics.asc_7d_impressions.status, anicca.metrics.asc_7d_impressions.value], ["measured", 40]);
  assert.deepEqual([anicca.metrics.asc_7d_product_page_views.status, anicca.metrics.asc_7d_product_page_views.value, anicca.metrics.asc_7d_product_page_views.observed_days], ["partial", null, 6]);
  assert.deepEqual(anicca.metrics.asc_7d_product_page_views.missing_dates, ["2026-10-11"]);
  assert.equal(anicca.source_status.asc_7d, "partial");
  assert.equal(honne.source_status.asc_7d, "unavailable");
  assert.equal(result.snapshot.source_refs.includes(currentAscRef), true);
  assert.match(result.snapshot.message, /ASC 7日/);
  assert.match(result.snapshot.message, /商品ページ閲覧 取得不可（6\/7日）/);
});

test("Anicca daily summary includes @anicca.en current metrics and ignores stale posts", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-anicca-en-summary-")); const day = "2026-10-11";
  const writeDaily = (owner, shortcode, filename, snapshot) => {
    const directory = path.join(dataDir, "tenants/dais-local/marketing/metrics", owner, shortcode, "daily");
    fs.mkdirSync(directory, { recursive: true }); fs.writeFileSync(path.join(directory, filename), JSON.stringify(snapshot));
  };
  writeDaily("anicca.jp", "TikTok1", `${day}.json`, { observed_at: `${day}T08:00:00.000Z`, published_at: `${day}T07:00:00.000Z`,
    locale: "ja", account_id: "@anicca.jp", public_url: "https://www.tiktok.com/@anicca.jp/video/1",
    post: { views: { status: "measured", value: 100 } }, account_metrics: { status: "unavailable", reason: "source_delayed" } });
  writeDaily("anicca.ios.jp", "Instagram1", `${day}.json`, { observed_at: `${day}T08:01:00.000Z`, published_at: `${day}T07:00:00.000Z`,
    locale: "ja", account_id: "@anicca.jp1", public_url: "https://www.instagram.com/reel/ABC123/",
    post: { views: { status: "measured", value: 101 } }, account_metrics: { status: "unavailable", reason: "source_delayed" } });
  writeDaily("anicca.en", "OldReel", `${day}.json`, { observed_at: `${day}T10:00:00.000Z`, published_at: "2026-09-01T10:00:00.000Z",
    locale: "en", account_id: "@anicca.en", public_url: "https://www.instagram.com/reel/OldReel/",
    post: { views: { status: "measured", value: 999999 } }, account_metrics: { status: "unavailable", reason: "source_delayed" } });
  writeDaily("anicca.en", "DdvxhT1jm8F", `${day}.current.correction.json`, {
    observed_at: "2026-10-11T08:18:53.023Z", source_observed_at: "2026-10-11T08:18:53.023Z", published_at: "2026-09-26T10:02:41.890Z",
    historical_checkpoint: false, locale: "en", account_id: "@anicca.en", public_url: "https://www.instagram.com/reel/DdvxhT1jm8F/",
    post: {
      views: { status: "measured", value: 2229 }, reach: { status: "measured", value: 1610 }, saves: { status: "measured", value: 3 },
      likes: { status: "measured", value: 1 }, comments: { status: "measured", value: 0 }, shares: { status: "measured", value: 0 },
      impressions: { status: "unavailable", value: null, reason: "metric_not_supported" },
      watch_time: { status: "unavailable", value: null, reason: "metric_not_supported" },
      average_watch_time: { status: "unavailable", value: null, reason: "metric_not_supported" },
      completion: { status: "unavailable", value: null, reason: "metric_not_supported" },
      engagement: { status: "derived", percent: 0.18 },
    },
    account_metrics: [
      { label: "Views", data: [{ total: 17481, date: "2026-10-11" }] },
      { label: "Reach", data: [{ total: 1703, date: "2026-10-05" }, { total: 2937, date: "2026-10-10" }] },
      { label: "Likes", data: [{ total: 31, date: "2026-10-11" }] },
      { label: "Comments", data: [{ total: 0, date: "2026-10-11" }] },
      { label: "Shares", data: [{ total: 6, date: "2026-10-11" }] },
      { label: "Saves", data: [{ total: 25, date: "2026-10-11" }] },
      { label: "Replies", data: [{ total: 0, date: "2026-10-11" }] },
    ],
  });
  writeDaily("anicca.en", "MissingDate", `${day}.json`, { observed_at: `${day}T10:30:00.000Z`, locale: "en", account_id: "@anicca.en",
    public_url: "https://www.instagram.com/reel/MissingDate/", post: { views: { status: "measured", value: 888888 } } });
  writeDaily("anicca.en", "InvalidDate", `${day}.json`, { observed_at: `${day}T10:40:00.000Z`, published_at: "not-a-date", locale: "en", account_id: "@anicca.en",
    public_url: "https://www.instagram.com/reel/InvalidDate/", post: { views: { status: "measured", value: 777777 } } });

  const summary = persistAniccaDaily(dataDir, day, "2026-10-11T13:00:00.000Z");
  assert.equal(summary.snapshot.source_refs.length, 3);
  assert.match(summary.snapshot.message, /@anicca\.en Instagram: 現在値/);
  assert.match(summary.snapshot.message, /過去のチェックポイント値ではありません/);
  assert.match(summary.snapshot.message, /Views 2229.*Reach 1610.*Saves 3.*Likes 1.*Comments 0.*Shares 0.*Engagement 0\.18%/);
  assert.match(summary.snapshot.message, /API未提供: Impressions、Watch time、Average watch time、Completion/);
  assert.match(summary.snapshot.message, /Account Views 17481.*2026-10-11/);
  assert.match(summary.snapshot.message, /Account Reach 2937.*2026-10-10/);
  assert.match(summary.snapshot.message, /Account Likes 31.*Account Comments 0.*Account Shares 6.*Account Saves 25.*Account Replies 0/);
  assert.match(summary.snapshot.message, /https:\/\/www\.instagram\.com\/reel\/DdvxhT1jm8F/);
  assert.doesNotMatch(summary.snapshot.message, /999999|888888|777777|Account totals 7/);
});
