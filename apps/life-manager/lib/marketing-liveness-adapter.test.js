"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  buildMarketingLivenessJob,
  executeMarketingLivenessJob,
  planMarketingLivenessJobs,
  verifyMarketingLivenessReceipt,
} = require("./marketing-liveness-adapter.js");

const HASH = "a".repeat(64);
const BASE = {
  tenantId: "tenant-a",
  nowMs: Date.parse("2026-08-20T02:30:00.000Z"),
  telegramTokenRef: "secret://telegram/bot-token",
  telegramChatRef: "telegram-chat://owner",
};
const LANE = {
  lane_id: "honne-en-tiktok",
  state: "production-armed",
  product: "honne-ai",
  locale: "en",
  platform: "tiktok",
  time_zone: "Asia/Tokyo",
  slots: ["07:00", "11:00", "20:30"],
  after: "2026-08-20T00:00:00.000Z",
  grace_minutes: 15,
};

function publication(slot = "2026-08-20T02:00:00.000Z") {
  return {
    schema_version: 1, kind: "marketing_video_distribution", status: "published",
    product_id: "honne-ai", format_id: "reelclaw", form: "video", locale: "en",
    slot, creative_id: "hen-001", platform: "tiktok", video_sha256: HASH,
    caption_sha256: HASH, public_url: "https://www.tiktok.com/@honne_reveal/video/7668814897594779655",
    provider_post_id: "7668814897594779655", provider_route: "postiz",
    provider_reconciled: true, published_at: "2026-08-20T02:05:00.000Z",
  };
}

test("production-armed slot emits a fake-transport receipt with the verified direct public URL", async () => {
  const jobs = planMarketingLivenessJobs({ ...BASE, lanes: [LANE], receipts: [publication()] });
  assert.equal(jobs.length, 1);
  const sent = [];
  const result = await executeMarketingLivenessJob(jobs[0], {
    secretProvider: { get: async () => "fake-token" },
    chatProvider: { get: async () => "fake-chat" },
    sendTelegram: async (token, chatId, text) => {
      sent.push({ token, chatId, text });
      return { ok: true, result: { message_id: 701 } };
    },
    now: () => "2026-08-20T02:30:00.000Z",
  });
  assert.equal(sent.length, 1);
  assert.match(sent[0].text, /^Life Manager:::/);
  assert.match(sent[0].text, /Honne AI's English post was published on TikTok/);
  assert.match(sent[0].text, /2026-08-20T02:00:00.000Z slot/);
  assert.match(sent[0].text, /Status: published/);
  assert.match(sent[0].text, /Public URL: https:\/\/www\.tiktok\.com\/@honne_reveal\/video\/7668814897594779655/);
  assert.match(sent[0].text, /Retry: not_required/);
  assert.doesNotMatch(sent[0].text, /📤 user6721125412040|https:\/\/www\.tiktok\.com\/@honne_reveal$/);
  assert.doesNotMatch(sent[0].text, /product:|locale:|platform:/);
  assert.equal(verifyMarketingLivenessReceipt(result.receipt), true);
});

test("miss alert identity is stable so rerun enqueues and sends only once", async () => {
  const planned = planMarketingLivenessJobs({ ...BASE, lanes: [LANE], receipts: [] });
  const replay = planMarketingLivenessJobs({ ...BASE, lanes: [LANE], receipts: [] });
  assert.equal(planned.length, 1);
  assert.equal(replay[0].job_id, planned[0].job_id);
  assert.equal(replay[0].effect_key, planned[0].effect_key);
  const stored = new Set();
  let sends = 0;
  for (const job of [planned[0], replay[0]]) {
    if (stored.has(job.job_id)) continue;
    stored.add(job.job_id);
    await executeMarketingLivenessJob(job, {
      secretProvider: { get: async () => "fake-token" },
      chatProvider: { get: async () => "fake-chat" },
      sendTelegram: async (_token, _chat, text) => {
        sends += 1;
        assert.match(text, /^Life Manager:::/);
        assert.match(text, /Honne AI's English post was not published on TikTok/);
        assert.match(text, /Status: missed\. Public URL: unavailable\. Retry: unavailable/);
        return { ok: true, result: { message_id: 702 } };
      },
    });
  }
  assert.equal(sends, 1);
});

test("published TikTok photo carousel reports exact Postiz and local-asset proof without a URL", async () => {
  const payload = { lane: "anicca-en-slideshow-tiktok", product: "anicca-ios", locale: "en", platform: "tiktok", account: "@anicca_slideshow", slot: "2026-08-26T04:54:59.000Z", status: "published", public_url: "unavailable", retry_state: "not_required", publication_evidence: "postiz_published_exact_assets" };
  const job = buildMarketingLivenessJob({ tenantId: "dais-local", telegramTokenRef: "secret://telegram/bot-token", telegramChatRef: "telegram-chat://owner", payload });
  const sent = [];
  const result = await executeMarketingLivenessJob(job, { secretProvider: { get: async () => "token" }, chatProvider: { get: async () => "123" }, sendTelegram: async (_token, _chat, text) => { sent.push(text); return { ok: true, result: { message_id: 77 } }; }, now: () => "2026-08-26T05:35:00.000Z" });
  assert.equal(result.receipt.message_id, 77);
  assert.match(sent[0], /photo carousel was published/);
  assert.match(sent[0], /Postiz API status: PUBLISHED/);
  assert.match(sent[0], /投稿リンク未取得/);
  assert.doesNotMatch(sent[0], /Public URL/);
  assert.throws(() => buildMarketingLivenessJob({ tenantId: "dais-local", telegramTokenRef: "secret://telegram/bot-token", telegramChatRef: "telegram-chat://owner", payload: { ...payload, publication_evidence: "wrong" } }), /invalid/i);
});

test("disabled, default-off, and shadow lanes never produce miss alerts", () => {
  const lanes = ["disabled", "default-off", "shadow"].map((state, index) => ({
    ...LANE, lane_id: `honne-${index}`, state,
  }));
  assert.deepEqual(planMarketingLivenessJobs({ ...BASE, lanes, receipts: [] }), []);
});

test("unreconciled publication is unavailable, unknown lane states fail, and old lanes still inspect recent slots", () => {
  const unreconciled = { ...publication(), provider_reconciled: false };
  const [job] = planMarketingLivenessJobs({ ...BASE, lanes: [LANE], receipts: [unreconciled] });
  assert.match(decodeURIComponent(job.input_refs.marketing_liveness_ref), /"status":"missed"/);
  assert.throws(() => planMarketingLivenessJobs({
    ...BASE, lanes: [{ ...LANE, state: "prodution-armed" }], receipts: [],
  }), /lane is invalid/);
  const recentJobs = planMarketingLivenessJobs({
    ...BASE,
    lanes: [{ ...LANE, after: "2024-01-01T00:00:00.000Z", slots: ["11:00"] }],
    receipts: [publication()],
  });
  const recent = recentJobs.find((candidate) => (
    decodeURIComponent(candidate.input_refs.marketing_liveness_ref).includes("2026-08-20T02:00:00.000Z")
  ));
  assert.ok(recent);
  assert.match(decodeURIComponent(recent.input_refs.marketing_liveness_ref), /"status":"published"/);
});

test("jsonb input-ref key order does not invalidate the same bound job", async () => {
  const [job] = planMarketingLivenessJobs({ ...BASE, lanes: [LANE], receipts: [publication()] });
  const reordered = { ...job, input_refs: Object.fromEntries(Object.entries(job.input_refs).reverse()) };
  await assert.doesNotReject(() => executeMarketingLivenessJob(reordered, {
    secretProvider: { get: async () => "fake-token" },
    chatProvider: { get: async () => "fake-chat" },
    sendTelegram: async () => ({ ok: true, result: { message_id: 703 } }),
  }));
});

test("metric snapshot renders every measured and unavailable field with stable dedupe identity", async () => {
  const payload = {
    lane: "anicca-main-ja-instagram", product: "anicca-ios", locale: "ja", platform: "instagram", account: "@anicca.jp1",
    status: "observed", window: "24h", observed_at: "2026-08-22T12:00:00.000Z",
    public_url: "https://www.instagram.com/reel/DcTFx_UjSio/", snapshot_ref: `object://sha256/${HASH}`,
  };
  const input = { tenantId: "dais-local", telegramTokenRef: "secret://telegram/bot-token", telegramChatRef: "telegram-chat://owner", payload };
  const job = buildMarketingLivenessJob(input); const replay = buildMarketingLivenessJob(input); const sent = [];
  assert.equal(replay.job_id, job.job_id);
  const result = await executeMarketingLivenessJob(job, {
    secretProvider: { get: async () => "fake-token" }, chatProvider: { get: async () => "fake-chat" },
    snapshotProvider: { get: async () => ({ public_url: payload.public_url, window: "24h", post: { views: { status: "measured", value: 32 }, reach: { status: "measured", value: 31 }, engagement: { status: "derived", percent: 0 }, watch_time: { status: "unavailable" } }, sources: { postiz_account: { status: "unavailable" } } }) },
    sendTelegram: async (_token, _chat, text) => { sent.push(text); return { ok: true, result: { message_id: 704 } }; },
  });
  assert.match(sent[0], /Anicca iOSのInstagram（@anicca.jp1）、24時間のメトリクスです/);
  assert.match(sent[0], /閲覧数 32、リーチ 31、エンゲージメント率 0%/);
  assert.match(sent[0], /取得できなかった指標: 視聴時間、アカウント全体の指標/);
  assert.match(sent[0], /投稿リンク: https:\/\/www\.instagram\.com\/reel\/DcTFx_UjSio\//);
  assert.doesNotMatch(sent[0], /Snapshot:|object:\/\/sha256|anicca-ios|Views|Reach|Account totals/);
  assert.equal(verifyMarketingLivenessReceipt(result.receipt), true);
});

test("Instagram current recovery reports real account values, source time, and unsupported fields separately", async () => {
  const payload = { lane: "anicca-en-widget-instagram", product: "anicca-ios", locale: "en", platform: "instagram", account: "@anicca.en",
    status: "observed", window: "daily", observed_at: "2026-10-11T08:30:00.000Z",
    public_url: "https://www.instagram.com/reel/DdvxhT1jm8F/", snapshot_ref: `object://sha256/${HASH}` };
  const job = buildMarketingLivenessJob({ tenantId: "dais-local", telegramTokenRef: "secret://telegram/bot-token", telegramChatRef: "telegram-chat://owner", payload });
  let text;
  await executeMarketingLivenessJob(job, {
    secretProvider: { get: async () => "fake-token" }, chatProvider: { get: async () => "fake-chat" },
    snapshotProvider: { get: async () => ({ public_url: payload.public_url, window: "daily", historical_checkpoint: false,
      source_observed_at: "2026-10-11T07:53:00.000Z", post: { views: { status: "measured", value: 2229 }, watch_time: { status: "unavailable", reason: "metric_not_supported" } },
      sources: { postiz_account: { status: "measured" } }, account_metrics: [
        { label: "Views", data: [{ total: 17481, date: "2026-10-11" }] },
        { label: "Reach", data: [{ total: 1703, date: "2026-10-05" }, { total: 2937, date: "2026-10-10" }] },
      ] }) },
    sendTelegram: async (_token, _chat, body) => { text = body; return { ok: true, result: { message_id: 705 } }; },
  });
  assert.match(text, /現在値.*2026\/10\/11 16:53/);
  assert.match(text, /過去のチェックポイント値ではありません/);
  assert.match(text, /アカウント閲覧数 17481（2026-10-11時点）/);
  assert.match(text, /アカウントリーチ 2937（2026-10-10時点）/);
  assert.match(text, /APIでは提供されていない指標: 視聴時間/);
  assert.doesNotMatch(text, /Snapshot:|object:\/\/sha256|anicca-ios|Account views|Account totals/);
});

test("TikTok metric snapshot renders every account value instead of an aggregate count", async () => {
  const payload = {
    lane: "anicca-jp4-ja-tiktok", product: "anicca-ios", locale: "ja", platform: "tiktok", account: "@anicca.jp4",
    status: "observed", window: "24h", correction: true, observed_at: "2026-08-22T14:46:13.240Z",
    public_url: "https://www.tiktok.com/@anicca.jp4/video/7676495865816632583", snapshot_ref: `object://sha256/${HASH}`,
  };
  const job = buildMarketingLivenessJob({ tenantId: "dais-local", telegramTokenRef: "secret://telegram/bot-token", telegramChatRef: "telegram-chat://owner", payload }); const sent = [];
  await executeMarketingLivenessJob(job, {
    secretProvider: { get: async () => "fake-token" }, chatProvider: { get: async () => "fake-chat" },
    snapshotProvider: { get: async () => ({ public_url: payload.public_url, window: "24h", post: { views: { status: "measured", value: 141 } }, sources: { postiz_account: { status: "measured" } }, account_metrics: { followers: { status: "measured", value: 122 }, following: { status: "measured", value: 0 }, total_likes: { status: "measured", value: 6839 }, videos: { status: "measured", value: 304 }, recent_views: { status: "measured", value: 11873 }, recent_likes: { status: "measured", value: 110 }, recent_comments: { status: "measured", value: 1 }, recent_shares: { status: "measured", value: 2 } } }) },
    sendTelegram: async (_token, _chat, text) => { sent.push(text); return { ok: true, result: { message_id: 705 } }; },
  });
  assert.match(sent[0], /フォロワー数 122、フォロー中 0、総いいね数 6839、投稿数 304/);
  assert.match(sent[0], /24時間の訂正メトリクスです/);
  assert.match(sent[0], /直近20投稿の閲覧数 11873、直近20投稿のいいね数 110、直近20投稿のコメント数 1、直近20投稿のシェア数 2/);
  assert.doesNotMatch(sent[0], /Snapshot:|object:\/\/sha256|anicca-ios|Followers|Account totals/);
});

test("immutable product summary renders through the durable Telegram adapter", async () => {
  const payload = { lane: "marketing-product-summary-honne", product: "honne-ai", locale: "en", platform: "multi", status: "summary", period: "daily", observed_at: "2026-08-22T13:00:00.000Z", summary_ref: `object://sha256/${HASH}` }; const job = buildMarketingLivenessJob({ tenantId: "dais-local", telegramTokenRef: "secret://telegram/bot-token", telegramChatRef: "telegram-chat://owner", payload }); const sent = [];
  const result = await executeMarketingLivenessJob(job, { secretProvider: { get: async () => "fake-token" }, chatProvider: { get: async () => "fake-chat" }, snapshotProvider: { get: async () => ({ kind: "marketing_product_metric_summary", period: "daily", report_key: "2026-08-22", source_refs: [`object://sha256/${HASH}`], message: "Life Manager::: Honne AIの日次プロダクトメトリクスです。" }) }, sendTelegram: async (_token, _chat, message) => { sent.push(message); return { ok: true, result: { message_id: 706 } }; } });
  assert.equal(sent[0], "Life Manager::: Honne AIの日次プロダクトメトリクスです。"); assert.equal(result.receipt.report_key, "2026-08-22"); assert.equal(verifyMarketingLivenessReceipt(result.receipt), true);
});


test("generated Japanese product summaries pass the real adapter and invalid headings never send", async (t) => {
  const fs = require("node:fs"); const os = require("node:os"); const path = require("node:path");
  const { persistHonneDaily } = require("../scripts/marketing-product-summary.js");
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-summary-heading-"));
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  const snapshot = persistHonneDaily(dataDir, "2026-10-23", "2026-10-23T13:00:00.000Z").snapshot;
  assert.ok(snapshot.message.startsWith("Life Manager："));
  const payload = { lane: "marketing-product-summary-honne", product: "honne-ai", locale: "en", platform: "multi", status: "summary", period: "daily", observed_at: "2026-10-23T13:00:00.000Z", summary_ref: `object://sha256/${HASH}` };
  const job = buildMarketingLivenessJob({ tenantId: "dais-local", telegramTokenRef: "secret://telegram/bot-token", telegramChatRef: "telegram-chat://owner", payload });
  const sent = [];
  const deps = {
    secretProvider: { get: async () => "fake-token" }, chatProvider: { get: async () => "fake-chat" },
    snapshotProvider: { get: async () => snapshot },
    sendTelegram: async (_token, _chat, message) => { sent.push(message); return { ok: true, result: { message_id: 707 } }; },
  };
  const result = await executeMarketingLivenessJob(job, deps);
  assert.deepEqual(sent, [snapshot.message]);
  assert.equal(result.receipt.report_key, "2026-10-23");
  assert.equal(verifyMarketingLivenessReceipt(result.receipt), true);
  sent.length = 0;
  await assert.rejects(executeMarketingLivenessJob(job, {
    ...deps, snapshotProvider: { get: async () => ({ ...snapshot, message: "Other sender：" + snapshot.message.slice("Life Manager：".length) }) },
  }), /marketing summary snapshot mismatch/);
  assert.deepEqual(sent, []);
});
