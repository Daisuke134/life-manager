"use strict";
const assert = require("node:assert/strict"); const fs = require("node:fs"); const os = require("node:os"); const path = require("node:path"); const test = require("node:test"); const { importContentObject } = require("../lib/content-object-store.js"); const { persistAniccaDaily, persistAttributionCoverage, persistHonneDaily, persistWeeklyReview, sendSummary } = require("./marketing-product-summary.js");
const { createMarketingLocalLedger } = require("../lib/marketing-local-ledger.js");
const { buildMarketingLivenessJob } = require("../lib/marketing-liveness-adapter.js");

async function summaryDeliveryFixture(t) {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-summary-delivery-"));
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  const summary = persistAniccaDaily(dataDir, "2026-10-23", "2026-10-23T19:19:22.638Z");
  const summaryRef = importContentObject(summary.file, { objectDir: path.join(dataDir, "objects") }).ref;
  const job = buildMarketingLivenessJob({ tenantId: "dais-local", telegramTokenRef: "secret://telegram/bot-token", telegramChatRef: "telegram-chat://owner", payload: { lane: "marketing-product-summary-anicca", product: "anicca-ios", locale: "ja", platform: "multi", status: "summary", period: "daily", observed_at: summary.snapshot.observed_at, summary_ref: summaryRef } });
  const store = createMarketingLocalLedger({ dataDir });
  await store.enqueueJob({ ...job, available_at: "2026-01-01T00:00:00.000Z" });
  const id = { tenantId: job.tenant_id, jobId: job.job_id };
  const worker = { ...id, capability: job.capability, workerId: "fixture-worker", leaseSeconds: 120 };
  const claim = await store.claimJob(worker);
  const env = { LM_TELEGRAM_BOT_TOKEN: "fixture-token", LM_TELEGRAM_ALERT_CHAT_ID: "fixture-chat" };
  const sent = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "https://api.telegram.org/botfixture-token/sendMessage");
    sent.push(JSON.parse(options.body).text);
    return { json: async () => ({ ok: true, result: { message_id: 708 } }) };
  });
  return { dataDir, summary, store, id, worker, claim, env, sent };
}

test("a retained summary retries the same known no-effect job and never resends its receipt", async (t) => {
  const f = await summaryDeliveryFixture(t);
  await f.store.failJob({ ...f.worker, attempt: f.claim.attempt, errorCode: "CAPABILITY_EXECUTION_FAILED", unknownEffect: false });
  const result = await sendSummary({ ...f.summary, created: false }, f.env, f.dataDir);
  assert.equal(result.message_id, 708);
  assert.equal((await f.store.readJob(f.id)).status, "completed");
  assert.equal((await f.store.readJob(f.id)).attempt, 2);
  assert.equal((await f.store.readReceipt(f.id)).message_id, 708);
  assert.deepEqual(f.sent, [f.summary.snapshot.message]);
  assert.equal((await sendSummary({ ...f.summary, created: false }, f.env, f.dataDir)).created, false);
  assert.equal(f.sent.length, 1);
});

test("retained summary recovery preserves running, unknown and retry-limit fences", async (t) => {
  for (const state of ["running", "unknown", "exhausted"]) await t.test(state, async (t) => {
    const f = await summaryDeliveryFixture(t);
    if (state !== "running") {
      await f.store.failJob({ ...f.worker, attempt: f.claim.attempt, errorCode: "fixture_failure", unknownEffect: state === "unknown" });
      if (state === "exhausted") for (let i = 0; i < 2; i++) {
        await f.store.retryJob(f.id);
        const claim = await f.store.claimJob(f.worker);
        await f.store.failJob({ ...f.worker, attempt: claim.attempt, errorCode: "fixture_failure", unknownEffect: false });
      }
    }
    const before = await f.store.readJob(f.id);
    assert.equal((await sendSummary({ ...f.summary, created: false }, f.env, f.dataDir)).created, false);
    assert.deepEqual(await f.store.readJob(f.id), before);
    assert.deepEqual(f.sent, []);
  });
});

test("summary delivery cannot report success without a durable Telegram receipt", async (t) => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-summary-no-receipt-"));
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  const summary = persistAniccaDaily(dataDir, "2026-10-23", "2026-10-23T19:19:22.638Z");
  summary.snapshot.message = "Invalid sender：送信前に拒否する本文";
  fs.writeFileSync(summary.file, JSON.stringify(summary.snapshot));
  t.mock.method(globalThis, "fetch", async () => { assert.fail("invalid summary must not reach the provider"); });
  await assert.rejects(sendSummary(summary, { LM_TELEGRAM_BOT_TOKEN: "fixture-token", LM_TELEGRAM_ALERT_CHAT_ID: "fixture-chat" }, dataDir), /marketing product summary receipt unavailable/);
  const jobs = fs.readFileSync(path.join(dataDir, "marketing/jobs.jsonl"), "utf8").trim().split("\n").map((line) => JSON.parse(line).job);
  assert.equal(jobs.at(-1).status, "failed");
  assert.equal(jobs.at(-1).unknown_effect, false);
});

test("attribution coverage joins dated downloads while keeping activation and retention unavailable", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-attribution-summary-")); const day = "2026-08-23"; const objectDir = path.join(dataDir, "objects");
  const source = path.join(dataDir, "source.json"); fs.writeFileSync(source, "{}\n"); const ref = importContentObject(source, { objectDir }).ref;
  const ascDir = path.join(dataDir, "tenants/dais-local/marketing/attribution/asc", day); fs.mkdirSync(ascDir, { recursive: true });
  fs.writeFileSync(path.join(ascDir, "acquisition.json"), JSON.stringify({ snapshot_ref: ref, products: [{ product_id: "anicca-ios", source_status: "measured", attribution_status: "partial", attribution_reason: "campaign_metrics_observed_for_subset", campaign_id: "anicca-ios_youtube_en", campaign_status: "measured", campaign_breakdowns: [
    { campaign_id: "anicca-ios_ig_anicca-en_en", platform: "instagram", account_id: "@anicca.en", locale: "en", metrics: { first_time_downloads: { status: "measured", value: 2, source: "app_store_connect_app_downloads_detailed" }, impressions: { status: "measured", value: 5, source: "app_store_connect_discovery_engagement_detailed" } } },
    { campaign_id: "anicca-ios_tt_aniccaaff_en", platform: "tiktok", account_id: "@aniccaaffirmation", locale: "en", metrics: { first_time_downloads: { status: "unavailable", value: null, reason: "campaign_not_observed_or_privacy_threshold" }, impressions: { status: "unavailable", value: null, reason: "campaign_not_observed_or_privacy_threshold" } } },
    { campaign_id: "anicca-ios_youtube_en", platform: "youtube", account_id: "@anicca-ai", locale: "en", metrics: { first_time_downloads: { status: "measured", value: 1, source: "app_store_connect_app_downloads_detailed" }, impressions: { status: "measured", value: 12, source: "app_store_connect_discovery_engagement_detailed" } } },
  ], daily_metrics: [{ date: "2026-08-22", metrics: { first_time_downloads: { status: "measured", value: 1 } } }], metrics: { first_time_downloads: { status: "measured", value: 1 }, campaign_first_time_downloads: { status: "measured", value: 1 }, campaign_impressions: { status: "measured", value: 12 } } }, { product_id: "honne-ai", source_status: "unavailable", attribution_status: "unattributed", attribution_reason: "campaign_link_configured_no_product_readback", campaign_id: "honne_en_base_20260823", campaign_status: "unavailable", metrics: { first_time_downloads: { status: "unavailable", value: null, reason: "report_pending" }, campaign_first_time_downloads: { status: "unavailable", value: null, reason: "report_pending" }, campaign_impressions: { status: "unavailable", value: null, reason: "report_pending" } } }] }));
  const rcDir = path.join(dataDir, "tenants/dais-local/marketing/attribution/revenuecat", day); fs.mkdirSync(rcDir, { recursive: true });
  fs.writeFileSync(path.join(rcDir, "subscriptions.json"), JSON.stringify({ snapshot_ref: ref, products: ["anicca-ios", "honne-ai"].map((product_id) => ({ product_id, source_status: "unavailable", metrics: { trial_starts: { status: "unavailable", value: null, reason: "missing" }, active_subscriptions: { status: "unavailable", value: null, reason: "missing" }, renewals: { status: "unavailable", value: null, reason: "missing" }, cancellations: { status: "unavailable", value: null, reason: "missing" }, proceeds_usd: { status: "unavailable", value: null, reason: "missing" } } })) }));
  const first = persistAttributionCoverage(dataDir, day, "2026-08-23T13:00:00.000Z"); const replay = persistAttributionCoverage(dataDir, day, "2026-08-23T14:00:00.000Z");
  assert.equal(first.created, true); assert.equal(replay.created, false); assert.equal(first.snapshot.source_refs.length, 2);
  assert.match(first.snapshot.message, /Anicca iOS: 初回ダウンロード 1/); assert.match(first.snapshot.message, /有効化 取得不可/); assert.match(first.snapshot.message, /翌日継続率 取得不可/); assert.match(first.snapshot.message, /Honne AI: 初回ダウンロード 取得不可/);
  assert.equal(first.snapshot.products[0].attribution_status, "partial"); assert.equal(first.snapshot.products[0].attribution_reason, "campaign_metrics_observed_for_subset"); assert.equal(first.snapshot.products[0].campaign_id, "anicca-ios_youtube_en"); assert.equal(first.snapshot.products[0].metrics.campaign_first_time_downloads.value, 1); assert.equal(first.snapshot.products[0].metrics.campaign_impressions.value, 12); assert.equal(first.snapshot.products[1].metrics.campaign_first_time_downloads.value, null); assert.equal(first.snapshot.coverage.partial, null); assert.equal(first.snapshot.coverage.reason, "campaign_metrics_observed_for_subset");
  assert.equal(first.snapshot.products[0].campaign_breakdowns.length, 3);
  assert.match(first.snapshot.message, /Instagram @anicca\.en（英語）: 初回ダウンロード 2、表示回数 5/);
  assert.match(first.snapshot.message, /TikTok @aniccaaffirmation（英語）: 初回ダウンロード 取得不可（未観測、またはAppleのプライバシー基準で非表示）/);
  assert.match(first.snapshot.message, /YouTube @anicca-ai（英語）: 初回ダウンロード 1、表示回数 12/);
  assert.match(first.snapshot.message, /アカウント・期間単位の集計/);
  assert.doesNotMatch(first.snapshot.message, /anicca-ios_(?:ig|tt|youtube)|honne_en_base_20260823|campaign_metrics_observed_for_subset|campaign_not_observed_or_privacy_threshold|campaign attribution|Source status|\b(?:measured|unavailable|partial|unattributed)\b/);
  assert.equal(first.snapshot.products[0].metrics.activation.value, null); assert.equal(first.snapshot.products[0].metrics.d7_retention.value, null);
});

test("ASC daily downloads select the preceding date without aggregate fallback", async (t) => {
  const reportDay = "2026-10-23";
  const measured = (value) => ({ status: "measured", value, source: "app_store_connect_app_downloads_standard" });
  for (const [name, dailyMetrics, expected, aggregate = measured(306)] of [
    ["mixed periods without the target date", [
      { date: "2026-01-21", metrics: { first_time_downloads: measured(2) } },
      { date: "2026-10-21", metrics: { impressions: { status: "measured", value: 3 } } },
    ], { status: "unavailable", value: null, reason: "report_pending" }],
    ["exact target date", [
      { date: "2026-10-21", metrics: { first_time_downloads: measured(8) } },
      { date: "2026-10-22", metrics: { first_time_downloads: measured(3) } },
      { date: reportDay, metrics: { first_time_downloads: measured(9) } },
    ], measured(3)],
    ["measured zero", [{ date: "2026-10-22", metrics: { first_time_downloads: measured(0) } }], measured(0)],
    ["missing metric", [{ date: "2026-10-22", metrics: {} }], { status: "unavailable", value: null, reason: "report_pending" }],
    ["explicit privacy suppression", [{ date: "2026-10-22", metrics: { first_time_downloads: { status: "unavailable", value: null, reason: "metric_not_observed_or_privacy_threshold" } } }], { status: "unavailable", value: null, reason: "metric_not_observed_or_privacy_threshold" }],
    ["legacy aggregate-only input", undefined, { status: "unavailable", value: null, reason: "report_pending" }],
    ...["source_timeout", "source_unavailable", "empty_report"].map((reason) => {
      const metric = { status: "unavailable", value: null, reason };
      return [reason, [], metric, metric];
    }),
  ]) {
    await t.test(name, () => {
      const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-asc-daily-period-"));
      t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
      const writeInput = (relative, snapshot) => {
        const file = path.join(dataDir, path.basename(relative)); fs.writeFileSync(file, JSON.stringify(snapshot));
        const ref = importContentObject(file, { objectDir: path.join(dataDir, "objects") }).ref;
        const pointer = path.join(dataDir, "tenants/dais-local/marketing/attribution", relative);
        fs.mkdirSync(path.dirname(pointer), { recursive: true }); fs.writeFileSync(pointer, JSON.stringify({ ...snapshot, snapshot_ref: ref }));
      };
      // Synthetic aggregate deliberately differs from every daily value.
      writeInput(`asc/${reportDay}/acquisition.json`, { schema_version: 1, kind: "marketing_asc_acquisition", report_day: reportDay, products: [
        { product_id: "anicca-ios", source_status: "measured", metrics: { first_time_downloads: aggregate }, daily_metrics: dailyMetrics },
        { product_id: "honne-ai", source_status: "unavailable", metrics: {} },
      ] });
      writeInput(`revenuecat/${reportDay}/subscriptions.json`, { products: ["anicca-ios", "honne-ai"].map((product_id) => ({ product_id, source_status: "unavailable", metrics: {} })) });
      const result = persistAttributionCoverage(dataDir, reportDay, "2026-10-23T13:00:00.000Z");
      const installs = result.snapshot.products.find((product) => product.product_id === "anicca-ios").metrics.installs;
      assert.deepEqual(installs, { ...expected, source_date: "2026-10-22" });
      assert.ok(result.snapshot.message.includes(`Anicca iOS: 初回ダウンロード ${expected.status === "measured" ? expected.value : "取得不可"}（対象日: 2026-10-22）`));
      assert.doesNotMatch(result.snapshot.message, /初回ダウンロード 306/);
    });
  }
});

test("new daily summaries do not present undated legacy coverage as daily downloads", (t) => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-asc-legacy-period-")); const day = "2026-10-23";
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  const file = path.join(dataDir, "tenants/dais-local/marketing/attribution/coverage", day, "summary.json");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const original = JSON.stringify({ products: [{ product_id: "anicca-ios", metrics: { installs: { status: "measured", value: 306 } } }] });
  fs.writeFileSync(file, original);
  const result = persistAniccaDaily(dataDir, day, "2026-10-23T13:00:00.000Z");
  assert.match(result.snapshot.message, /初回ダウンロード 取得不可（対象日不明）/);
  assert.doesNotMatch(result.snapshot.message, /初回ダウンロード 306/);
  assert.equal(fs.readFileSync(file, "utf8"), original);
});

test("Honne daily summary binds EN and JA immutable daily sources and replays", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-honne-summary-")); const day = "2026-08-22";
  for (const target of [{ owner: "honne_reveal", account: "@honne_reveal", locale: "en", video: "1", views: 208 }, { owner: "honnevideo", account: "@honnevideo", locale: "ja", video: "2", views: 1035 }]) { const directory = path.join(dataDir, "tenants/dais-local/marketing/metrics", target.owner, target.video, "daily"); fs.mkdirSync(directory, { recursive: true }); fs.writeFileSync(path.join(directory, `${day}.json`), JSON.stringify({ kind: "tiktok_daily_metric_digest", window: "daily", observed_at: `2026-08-22T${target.locale === "en" ? "10" : "11"}:00:00.000Z`, published_at: "2026-08-21T10:00:00.000Z", account_id: target.account, locale: target.locale, public_url: `https://www.tiktok.com/${target.account}/video/${target.video}`, post: { views: { status: "measured", value: target.views }, likes: { status: "measured", value: 1 }, comments: { status: "measured", value: 0 }, shares: { status: "measured", value: 0 }, saves: { status: "unavailable" }, engagement: { status: "derived", percent: 1 } }, account_metrics: { followers: { status: "measured", value: 5 }, following: { status: "measured", value: 1 }, total_likes: { status: "measured", value: 10 }, videos: { status: "measured", value: 2 } } })); }
  const first = persistHonneDaily(dataDir, day, "2026-08-22T13:00:00.000Z"); const replay = persistHonneDaily(dataDir, day, "2026-08-22T14:00:00.000Z"); assert.equal(first.created, true); assert.equal(replay.created, false); assert.equal(first.snapshot.source_refs.length, 2); assert.match(first.snapshot.message, /@honne_reveal TikTok: 閲覧数 208/); assert.match(first.snapshot.message, /@honnevideo TikTok: 閲覧数 1035/); assert.match(first.snapshot.message, /初回ダウンロード 取得不可、有効化 取得不可/); assert.doesNotMatch(first.snapshot.message, /Views|Reach|Likes|Comments|Shares|Saves|Impressions|Watch time|Average watch time|Completion|Engagement|Account totals|Source status|Source:|Campaign attribution|Life Manager:::|object:\/\/sha256|\b(?:measured|unavailable|partial|unattributed)\b/); assert.equal(fs.statSync(first.file).mode & 0o777, 0o600);
});

test("Anicca daily summary binds main sources and keeps JP4 and HE unavailable", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-anicca-summary-")); const day = "2026-08-22"; const rows = [{ owner: "anicca.jp", account: "@anicca.jp", platform: "tiktok", url: "https://www.tiktok.com/@anicca.jp/video/1" }, { owner: "anicca.ios.jp", account: "@anicca.jp1", platform: "instagram", url: "https://www.instagram.com/reel/ABC123/" }];
  for (const [index, target] of rows.entries()) { const directory = path.join(dataDir, "tenants/dais-local/marketing/metrics", target.owner, String(index + 1), "daily"); fs.mkdirSync(directory, { recursive: true }); fs.writeFileSync(path.join(directory, `${day}.json`), JSON.stringify({ kind: `${target.platform}_daily_metric_digest`, window: "daily", observed_at: `2026-08-22T1${index}:00:00.000Z`, published_at: "2026-08-21T10:00:00.000Z", account_id: target.account, locale: "ja", public_url: target.url, post: { views: { status: "measured", value: 100 + index }, likes: { status: "measured", value: 1 }, comments: { status: "measured", value: 0 }, shares: { status: "measured", value: 0 }, saves: { status: "unavailable" }, engagement: { status: "derived", percent: 1 } }, account_metrics: { status: "unavailable" } })); }
  const coverageDir = path.join(dataDir, "tenants/dais-local/marketing/attribution/coverage", day); fs.mkdirSync(coverageDir, { recursive: true }); fs.writeFileSync(path.join(coverageDir, "summary.json"), JSON.stringify({ products: [{ product_id: "anicca-ios", attribution_status: "partial", attribution_reason: "campaign_metrics_observed_for_subset", campaign_id: "anicca-ios_youtube_en", campaign_status: "measured", campaign_breakdowns: [{ campaign_id: "anicca-ios_ig_anicca-en_en", platform: "instagram", account_id: "@anicca.en", locale: "en", metrics: { first_time_downloads: { status: "measured", value: 2 }, impressions: { status: "measured", value: 5 } } }, { campaign_id: "anicca-ios_tt_aniccaaff_en", platform: "tiktok", account_id: "@aniccaaffirmation", locale: "en", metrics: { first_time_downloads: { status: "unavailable", value: null, reason: "campaign_not_observed_or_privacy_threshold" }, impressions: { status: "unavailable", value: null, reason: "campaign_not_observed_or_privacy_threshold" } } }, { campaign_id: "anicca-ios_youtube_en", platform: "youtube", account_id: "@anicca-ai", locale: "en", metrics: { first_time_downloads: { status: "measured", value: 1 }, impressions: { status: "measured", value: 12 } } }], metrics: { campaign_first_time_downloads: { status: "measured", value: 1 }, campaign_impressions: { status: "measured", value: 12 } } }] }));
  const result = persistAniccaDaily(dataDir, day, "2026-08-22T13:00:00.000Z"); assert.equal(result.created, true); assert.equal(result.snapshot.source_refs.length, 2); assert.match(result.snapshot.message, /@anicca\.jp TikTok: 閲覧数 100/); assert.match(result.snapshot.message, /@anicca\.jp1 Instagram: 閲覧数 101/); assert.match(result.snapshot.message, /@anicca\.jp4 TikTok: 投稿指標・アカウント指標を取得できません/); assert.match(result.snapshot.message, /@anicca\.he TikTok: 投稿指標・アカウント指標を取得できません/); assert.match(result.snapshot.message, /7676500512308481296/); assert.match(result.snapshot.message, /キャンペーン別実績:.*/); assert.match(result.snapshot.message, /初回ダウンロード 1/); assert.match(result.snapshot.message, /表示回数 12/); assert.match(result.snapshot.message, /Instagram @anicca\.en（英語）: 初回ダウンロード 2、表示回数 5/); assert.match(result.snapshot.message, /TikTok @aniccaaffirmation（英語）: 初回ダウンロード 取得不可/); assert.match(result.snapshot.message, /YouTube @anicca-ai（英語）: 初回ダウンロード 1、表示回数 12/); assert.doesNotMatch(result.snapshot.message, /anicca-ios_|campaign_metrics_observed_for_subset|campaign_not_observed_or_privacy_threshold|Views|Reach|Saves|Likes|Comments|Shares|Impressions|Watch time|Average watch time|Completion|Engagement|Account totals|Source status|Source:|object:\/\/sha256|\b(?:measured|unavailable|partial|unattributed)\b/);
});

test("weekly review binds both products without cross-product winner transfer", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-weekly-summary-")); const day = "2026-08-22";
  for (const [product, label] of [["honne-ai", "Honne AI"], ["anicca-ios", "Anicca iOS"]]) { const directory = path.join(dataDir, "tenants/dais-local/marketing/metrics/summaries", product, "daily"); fs.mkdirSync(directory, { recursive: true }); fs.writeFileSync(path.join(directory, `${day}.json`), JSON.stringify({ schema_version: 1, kind: "marketing_product_metric_summary", period: "daily", report_key: day, observed_at: "2026-08-22T13:00:00.000Z", product_id: product, source_refs: [], message: `Life Manager::: ${label} source values` })); }
  const previousCoverageDir = path.join(dataDir, "tenants/dais-local/marketing/attribution/coverage", "2026-08-21"); fs.mkdirSync(previousCoverageDir, { recursive: true });
  fs.writeFileSync(path.join(previousCoverageDir, "summary.json"), JSON.stringify({ products: [{ product_id: "anicca-ios", campaign_breakdowns: [{ campaign_id: "anicca-ios_ig_anicca-en_en", platform: "instagram", account_id: "@anicca.en", locale: "en", metrics: { first_time_downloads: { status: "measured", value: 3 }, impressions: { status: "measured", value: 9 } } }] }] }));
  const coverageDir = path.join(dataDir, "tenants/dais-local/marketing/attribution/coverage", day); fs.mkdirSync(coverageDir, { recursive: true });
  fs.writeFileSync(path.join(coverageDir, "summary.json"), JSON.stringify({ products: [{ product_id: "anicca-ios", attribution_status: "partial", campaign_breakdowns: [
    { campaign_id: "anicca-ios_ig_anicca-en_en", platform: "instagram", account_id: "@anicca.en", locale: "en", metrics: { first_time_downloads: { status: "measured", value: 2 }, impressions: { status: "measured", value: 5 } } },
    { campaign_id: "anicca-ios_tt_aniccaaff_en", platform: "tiktok", account_id: "@aniccaaffirmation", locale: "en", metrics: { first_time_downloads: { status: "unavailable", value: null, reason: "campaign_not_observed_or_privacy_threshold" }, impressions: { status: "unavailable", value: null, reason: "campaign_not_observed_or_privacy_threshold" } } },
  ] }] }));
  const first = persistWeeklyReview(dataDir, day, "2026-08-22T14:00:00.000Z"); const replay = persistWeeklyReview(dataDir, day, "2026-08-22T15:00:00.000Z"); assert.equal(first.created, true); assert.equal(replay.created, false); assert.equal(first.snapshot.period, "weekly"); assert.equal(first.snapshot.report_key, "2026-W34"); assert.match(first.snapshot.message, /Honne AI: データ取得状況 一部取得、記録日数 1\/7日、最新日 2026-08-22/); assert.match(first.snapshot.message, /Anicca iOS: データ取得状況 一部取得、記録日数 1\/7日、最新日 2026-08-22/); assert.match(first.snapshot.message, /最新キャンペーン別実績（レポート日 2026-08-22、7日間合計ではありません）/); assert.match(first.snapshot.message, /Instagram @anicca\.en（英語）: 初回ダウンロード 2、表示回数 5/); assert.match(first.snapshot.message, /TikTok @aniccaaffirmation（英語）: 初回ダウンロード 取得不可（未観測、またはAppleのプライバシー基準で非表示）/); assert.equal(first.snapshot.source_refs.length, 3); assert.match(first.snapshot.message, /アプリ間の勝ちパターン移植は判定しません/); assert.doesNotMatch(first.snapshot.message, /Life Manager:::|source values|source_status|Attribution coverage|Cross-product winner|Keep\/revert|object:\/\/sha256|anicca-ios_|campaign_not_observed_or_privacy_threshold/); assert.equal(fs.statSync(first.file).mode & 0o777, 0o600);
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
  assert.match(summary.snapshot.message, /@anicca\.jp1 Instagram: 現在値.*閲覧数 2229/);
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
  assert.match(result.snapshot.message, /平均アクティブ顧客（直近28日）4\.29/);
  assert.match(result.snapshot.message, /Honne AI: .*新規顧客（直近28日）取得不可/);
});

test("ASC trailing seven-day averages use latest suppressions and keep partial coverage null", (t) => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-asc-seven-day-summary-")); const reportDay = "2026-10-12"; const objectDir = path.join(dataDir, "objects");
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
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
    ["2026-10-11", dailyRow("2026-10-11", 7, 70, 0)],
    // The latest explicit suppression must supersede the old fabricated zero.
    ["2026-10-12", [dailyRow("2026-10-07", 300, 30, 6), dailyRow("2026-10-11", 7, 70, 14, true)]],
  ];
  let currentAscRef;
  for (const [day, daily] of reports) {
    const snapshot = { schema_version: 1, kind: "marketing_asc_acquisition", tenant_id: "dais-local", report_day: day, lineage_ref: "fixture-lineage", products: [acquisitionProduct("anicca-ios", Array.isArray(daily) ? daily : [daily]), acquisitionProduct("honne-ai", [])], rows: [] };
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
  assert.match(result.snapshot.message, /App Store Connectの7日平均/);
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
  writeDaily("anicca.en", "DdvxhT1jm8F", `${day}.historical.correction.json`, {
    observed_at: "2026-10-11T08:18:53.023Z", source_observed_at: "2026-10-11T08:18:53.023Z", published_at: "2026-09-26T10:02:41.890Z",
    historical_checkpoint: false, locale: "en", account_id: "@anicca.en", public_url: "https://www.instagram.com/reel/DdvxhT1jm8F/",
    historical_checkpoint_correction: {
      kind: "instagram_combined_metric_snapshot_correction", window: "7d", observed_at: "2026-10-03T10:02:54Z",
      source_snapshot_id: "228aca83e0a54abdac63957c1c349eabc23a6147b9f0e242bea381e165c283d0",
      post: {
        views: { status: "measured", value: 2229, source_date: "2026-10-03" },
        reach: { status: "measured", value: 1610, source_date: "2026-10-03" },
        saves: { status: "measured", value: 3, source_date: "2026-10-03" },
        likes: { status: "measured", value: 1, source_date: "2026-10-03" },
        comments: { status: "measured", value: 0, source_date: "2026-10-03" },
        shares: { status: "measured", value: 0, source_date: "2026-10-03" },
        impressions: { status: "unavailable", value: null, reason: "provider_field_missing" },
        watch_time: { status: "unavailable", value: null, reason: "metric_not_supported" },
        average_watch_time: { status: "unavailable", value: null, reason: "metric_not_supported" },
        completion: { status: "unavailable", value: null, reason: "metric_not_supported" },
        engagement: { status: "derived", percent: 0.18 },
      },
      account_metrics: { status: "unavailable", reason: "account_metrics_not_in_post_metrics" },
    },
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
  const currentCorrection = JSON.parse(fs.readFileSync(path.join(dataDir, "tenants/dais-local/marketing/metrics/anicca.en/DdvxhT1jm8F/daily", `${day}.historical.correction.json`), "utf8"));
  currentCorrection.observed_at = "2026-10-11T09:18:53.023Z";
  currentCorrection.source_observed_at = currentCorrection.observed_at;
  currentCorrection.post.views.value = 2300;
  writeDaily("anicca.en", "DdvxhT1jm8F", `${day}.current.correction.json`, currentCorrection);

  const summary = persistAniccaDaily(dataDir, day, "2026-10-11T13:00:00.000Z");
  assert.equal(summary.snapshot.source_refs.length, 3);
  assert.match(summary.snapshot.message, /@anicca\.en Instagram: 現在値/);
  assert.match(summary.snapshot.message, /過去のチェックポイント値ではありません/);
  assert.match(summary.snapshot.message, /閲覧数 2300.*リーチ 1610.*保存数 3.*いいね 1.*コメント 0.*シェア 0.*エンゲージメント率 0\.18%/);
  assert.match(summary.snapshot.message, /訂正済み7日checkpoint.*2026-10-03T10:02:54Z/);
  assert.match(summary.snapshot.message, /過去の値.*閲覧数 2229.*2026-10-03.*リーチ 1610.*2026-10-03/);
  assert.match(summary.snapshot.message, /APIでは取得できない項目：表示回数、視聴時間、平均視聴時間、視聴完了率/);
  assert.match(summary.snapshot.message, /アカウント閲覧数 17481.*2026-10-11/);
  assert.match(summary.snapshot.message, /アカウントリーチ 2937.*2026-10-10/);
  assert.match(summary.snapshot.message, /アカウントいいね 31.*アカウントコメント 0.*アカウントシェア 6.*アカウント保存数 25.*アカウント返信数 0/);
  assert.match(summary.snapshot.message, /https:\/\/www\.instagram\.com\/reel\/DdvxhT1jm8F/); assert.doesNotMatch(summary.snapshot.message, /object:\/\/sha256|Views|Reach|Saves|Likes|Comments|Shares|Source status|Source:|Funnel:|Campaign attribution/);
  assert.doesNotMatch(summary.snapshot.message, /999999|888888|777777|Account totals 7/);
});


test("Anicca daily summary persists native TikTok photos without weakening source validation", async (t) => {
  const day = "2026-10-23";
  const photo = {
    kind: "tiktok_daily_metric_digest", window: "daily", observed_at: "2026-10-23T13:00:00.000Z",
    published_at: "2026-10-23T07:00:00.000Z", account_id: "@anicca.jp", locale: "ja",
    public_url: "https://www.tiktok.com/@anicca.jp/photo/7564191602695326977",
    post: { views: { status: "measured", value: 42 } }, account_metrics: { status: "unavailable" },
  };
  for (const [name, changed, accepted] of [
    ["photo permalink", {}, true],
    ["different account", { account_id: "@honnevideo" }, false],
    ["different locale", { locale: "en" }, false],
    ["non-numeric post", { public_url: "https://www.tiktok.com/@anicca.jp/photo/not-a-post" }, false],
    ["foreign host", { public_url: "https://example.com/@anicca.jp/photo/7564191602695326977" }, false],
  ]) {
    await t.test(name, () => {
      const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-anicca-photo-summary-"));
      t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
      const directory = path.join(dataDir, "tenants/dais-local/marketing/metrics/anicca.jp/photo1/daily");
      fs.mkdirSync(directory, { recursive: true });
      fs.writeFileSync(path.join(directory, `${day}.json`), JSON.stringify({ ...photo, ...changed }));
      const persist = () => persistAniccaDaily(dataDir, day, "2026-10-23T14:00:00.000Z");
      if (!accepted) {
        assert.throws(persist, /Anicca iOS @anicca\.jp daily source mismatch/);
        assert.equal(fs.existsSync(path.join(dataDir, "tenants/dais-local/marketing/metrics/summaries/anicca-ios/daily", `${day}.json`)), false);
        return;
      }
      const first = persist();
      assert.equal(first.created, true);
      assert.equal(first.snapshot.source_refs.length, 1);
      assert.match(first.snapshot.message, /@anicca\.jp TikTok: 閲覧数 42/);
      assert.ok(first.snapshot.message.includes(photo.public_url));
      assert.equal(JSON.parse(fs.readFileSync(first.file, "utf8")).source_refs[0], first.snapshot.source_refs[0]);
      assert.equal(persist().created, false);
    });
  }
});
