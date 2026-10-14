"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { EXPECTED, persistDelayedSnapshot, persistSnapshot } = require("./instagram-metrics-read.js");
const { discoverExpected, runDue } = require("./instagram-metrics-due.js");
const { JA_LANE, verifyMarketingNativeCarouselPublicationReceipt } = require("../lib/marketing-native-carousel-publication-adapter.js");

test("missed Instagram checkpoints stay missed while one dated current observation is collected and replayed", async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-current-due-"));
  const nowMs = Date.parse("2026-10-11T07:53:00.000Z");
  const env = { LM_DATA_DIR: dataDir };
  const expected = { ...EXPECTED, published_at: "2026-09-26T10:02:41.890Z" };
  for (const window of ["2h", "24h", "72h", "7d"]) persistDelayedSnapshot({ dataDir, window, observedAt: new Date(nowMs).toISOString(), expected });
  let gets = 0;
  const deps = { collectWindow: async (window, _env, observedAt, target) => {
    gets += 1; assert.equal(window, "current");
    const html = `<link rel="canonical" href="${target.public_url}" /><meta property="og:description" content="${target.native_owner}: ${target.caption.replace(/\n/g, " ")}" />`;
    const result = persistSnapshot({ dataDir, window, observedAt, expected: target, html, accountRows: [], postRows: [{ label: "Views", data: [{ total: "2229" }] }] });
    return { ...result, telegram: { created: false } };
  } };
  const first = await runDue(nowMs, env, [expected], deps);
  assert.equal(first.find((row) => row.window === "7d").state, "checkpoint_missed");
  assert.equal(first.find((row) => row.window === "current").state, "measured");
  const replay = await runDue(nowMs + 60_000, env, [expected], deps);
  assert.equal(replay.find((row) => row.window === "current").state, "complete");
  assert.equal(gets, 1);
});

test("failed current sources cannot permanently starve posts beyond the eight-read budget", async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-current-rotation-"));
  const nowMs = Date.parse("2026-10-11T07:53:00.000Z");
  const targets = Array.from({ length: 9 }, (_, i) => ({ ...EXPECTED, shortcode: `Source${i}`,
    public_url: `https://www.instagram.com/reel/Source${i}/`, published_at: new Date(nowMs - 8 * 86400_000).toISOString() }));
  for (const expected of targets) for (const window of ["2h", "24h", "72h", "7d"]) {
    persistDelayedSnapshot({ dataDir, window, observedAt: new Date(nowMs).toISOString(), expected });
  }
  const initialStart = (Math.floor(nowMs / 1800_000) * 8) % targets.length;
  const healthy = targets[(initialStart + 8) % targets.length];
  let calls = 0;
  const deps = { collectWindow: async (_window, _env, observedAt, expected) => {
    calls += 1;
    if (expected.shortcode !== healthy.shortcode) throw new Error("provider unavailable");
    const html = `<link rel="canonical" href="${expected.public_url}" /><meta property="og:description" content="${expected.native_owner}: ${expected.caption.replace(/\n/g, " ")}" />`;
    return { ...persistSnapshot({ dataDir, window: "current", observedAt, expected, html, accountRows: [], postRows: [{ label: "Views", data: [{ total: "2229" }] }] }), telegram: { created: false } };
  } };
  const first = await runDue(nowMs, { LM_DATA_DIR: dataDir }, targets, deps);
  assert.equal(calls, 8);
  assert.equal(first.find((row) => row.window === "current" && row.shortcode === healthy.shortcode).state, "pending");
  const next = await runDue(nowMs + 1800_000, { LM_DATA_DIR: dataDir }, targets, deps);
  assert.equal(calls, 16);
  assert.equal(next.find((row) => row.window === "current" && row.shortcode === healthy.shortcode).state, "measured");
});

test("due planner persists missed checkpoints and daily metrics without per-post Telegram sends", async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-due-")); let sends = 0;
  const env = { LM_DATA_DIR: dataDir, LM_TELEGRAM_BOT_TOKEN: "fake", LM_TELEGRAM_ALERT_CHAT_ID: "fake" };
  const originalFetch = global.fetch; global.fetch = async () => ({ ok: true, json: async () => ({ ok: true, result: { message_id: ++sends } }) });
  try {
    const result = await runDue(Date.parse(EXPECTED.published_at) + 23 * 3600_000, env, [EXPECTED]);
    assert.equal(result.find((row) => row.window === "2h").state, "checkpoint_missed");
    assert.equal(result.find((row) => row.window === "24h").state, "pending");
    assert.equal(result.find((row) => row.window === "daily").state, "persisted");
    assert.equal(fs.existsSync(path.join(dataDir, "tenants", EXPECTED.tenant_id, "marketing", "metrics", EXPECTED.native_owner, EXPECTED.shortcode, "daily", "2026-08-22.json")), true);
    assert.equal(sends, 0);
    const replay = await runDue(Date.parse(EXPECTED.published_at) + 23 * 3600_000, env, [EXPECTED]);
    assert.equal(replay.find((row) => row.window === "2h").state, "checkpoint_missed");
    assert.equal(replay.find((row) => row.window === "daily").state, "complete"); assert.equal(sends, 0);
  } finally { global.fetch = originalFetch; }
});

test("posts older than the 30-day metric window produce no checkpoint or daily work", async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-metrics-expired-")); let sends = 0;
  const nowMs = Date.parse("2026-10-11T14:00:00.000Z");
  const expected = { ...EXPECTED, shortcode: "ExpiredPost", public_url: "https://www.instagram.com/reel/ExpiredPost/", published_at: "2026-09-10T10:00:00.000Z" };
  const env = { LM_DATA_DIR: dataDir, LM_TELEGRAM_BOT_TOKEN: "fake", LM_TELEGRAM_ALERT_CHAT_ID: "fake" };
  const originalFetch = global.fetch; global.fetch = async () => ({ ok: true, json: async () => ({ ok: true, result: { message_id: ++sends } }) });
  try {
    const result = await runDue(nowMs, env, [expected]);
    assert.deepEqual(result, []);
    assert.equal(sends, 0);
    assert.equal(fs.existsSync(path.join(dataDir, "tenants", expected.tenant_id, "marketing", "metrics", expected.native_owner, expected.shortcode)), false);
  } finally { global.fetch = originalFetch; }
});

test("future verified Instagram rows are discovered from the LM distribution ledger", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-discovery-"));
  const caption = path.join(dataDir, "caption.txt"); fs.writeFileSync(caption, EXPECTED.caption);
  const digest = require("node:crypto").createHash("sha256").update(fs.readFileSync(caption)).digest("hex");
  const directory = path.join(dataDir, "tenants/dais-local/marketing/video-publication/anicca-ios"); fs.mkdirSync(directory, { recursive: true });
  const valid = { ts: EXPECTED.published_at, platform: "instagram", status: "published", provider_reconciled: true, format_id: "reelclaw-card", form: "nudge-card", locale: "ja", provider_id: EXPECTED.provider_post_id, public_url: EXPECTED.public_url, caption_path: caption, caption_sha256: digest };
  const unrelated = [
    { ...valid, locale: "fr", provider_id: "cmtunrelatedencard", public_url: "https://www.instagram.com/reel/EnCard123/" },
    { ...valid, format_id: "reelclaw-widget", form: "widget-demo-reel", provider_id: "cmtunrelatedjawidget", public_url: "https://www.instagram.com/reel/JaWidget123/" },
    { ...valid, format_id: "reelclaw-widget", form: "widget-demo-reel", locale: "en", provider_id: "cmtunrelatedenwidget", public_url: "https://www.instagram.com/reel/EnWidget123/" },
  ];
  fs.writeFileSync(path.join(directory, "distribution.jsonl"), `${unrelated.concat(valid).map(JSON.stringify).join("\n")}\n`);
  assert.deepEqual(discoverExpected(dataDir), [{ ...EXPECTED, format_id: "reelclaw-card", form: "nudge-card" }]);
});

test("malformed JA Card rows remain fail-closed after unrelated rows are filtered", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-malformed-discovery-"));
  const directory = path.join(dataDir, "tenants/dais-local/marketing/video-publication/anicca-ios"); fs.mkdirSync(directory, { recursive: true });
  fs.writeFileSync(path.join(directory, "distribution.jsonl"), `${JSON.stringify({ platform: "instagram", status: "published", provider_reconciled: true, format_id: "reelclaw-card", form: "nudge-card", locale: "ja", provider_id: "bad-provider", public_url: "https://www.instagram.com/reel/not-a-target/" })}\n`);
  assert.throws(() => discoverExpected(dataDir), /Instagram verified distribution row invalid/);
});

test("verified Obou watercolor Reel is discovered as its exact metric effect", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-obou-discovery-"));
  const caption = "相手の感情は相手のもの。";
  const captionPath = path.join(dataDir, "caption.txt"); fs.writeFileSync(captionPath, caption);
  const captionHash = require("node:crypto").createHash("sha256").update(fs.readFileSync(captionPath)).digest("hex");
  const directory = path.join(dataDir, "tenants/dais-local/marketing/video-publication/anicca-ios"); fs.mkdirSync(directory, { recursive: true });
  const row = { ts: "2026-08-26T04:21:05.630917Z", platform: "instagram", status: "published", provider_reconciled: true,
    format_id: "watercolor", form: "buddhist-self-care-reel", locale: "ja", creative_id: "JA-WATERCOLOR-OBOU-b2772de4303a",
    provider_id: "cmt9l523g02mbp20ybq3lefov", public_url: "https://www.instagram.com/reel/DcfVvIkkWyz/",
    caption_path: captionPath, caption_sha256: captionHash, video_sha256: "b2772de4303acc901f42b43a0b3f4af166ae3daeb5ee7fd24e090e5b62f2b0e8" };
  fs.writeFileSync(path.join(directory, "distribution.jsonl"), `${JSON.stringify(row)}\n`);
  assert.deepEqual(discoverExpected(dataDir), [{
    tenant_id: "dais-local", product_id: "anicca-ios", locale: "ja", account_id: "@obou.anicca", native_owner: "obou.anicca",
    format_id: "watercolor", form: "buddhist-self-care-reel",
    creative_id: row.creative_id,
    integration_id: "cmooplxmu04tpmd0y4h3cpk33", provider_post_id: row.provider_id, shortcode: "DcfVvIkkWyz",
    public_url: row.public_url, caption, published_at: row.ts,
  }]);
});

test("verified EN Card Reel is discovered for the exact encards metric lane", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-encards-discovery-"));
  const caption = "You know that feeling when\n\n#affirmations #mentalhealth #selfcare #mindfulness #anicca\n";
  const captionPath = path.join(dataDir, "caption.txt"); fs.writeFileSync(captionPath, caption);
  const captionHash = require("node:crypto").createHash("sha256").update(fs.readFileSync(captionPath)).digest("hex");
  const directory = path.join(dataDir, "tenants/dais-local/marketing/video-publication/anicca-ios"); fs.mkdirSync(directory, { recursive: true });
  const row = { ts: "2026-08-26T07:13:53.435Z", platform: "instagram", status: "published", provider_reconciled: true,
    format_id: "reelclaw-card", form: "nudge-card", locale: "en", creative_id: "EN-CARD-V2-e678c823480f",
    provider_id: "cmt9rbish00qylf0yw6gt9ulr", public_url: "https://www.instagram.com/reel/Dcfph70jorc/",
    caption_path: captionPath, caption_sha256: captionHash, video_sha256: "e678c823480f357c2d87b19dad87b8dc2c0355f50c850c3ba0dc19b3d67a5d88" };
  fs.writeFileSync(path.join(directory, "distribution.jsonl"), `${JSON.stringify(row)}\n`);
  assert.deepEqual(discoverExpected(dataDir), [{
    tenant_id: "dais-local", product_id: "anicca-ios", locale: "en", account_id: "@anicca.encards", native_owner: "anicca.encards",
    format_id: "reelclaw-card", form: "nudge-card",
    creative_id: row.creative_id,
    integration_id: "cmpc3gx4001nklg0y27a8o66q", provider_post_id: row.provider_id, shortcode: "Dcfph70jorc",
    public_url: row.public_url, caption, published_at: row.ts,
  }]);
});

test("verified EN Widget Reel is discovered for the exact anicca.en metric lane", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-en-widget-discovery-"));
  const caption = "Turn screen time into\nself-belief\n\n#affirmations #mentalhealth #selfcare #mindfulness #anicca\n";
  const captionPath = path.join(dataDir, "caption.txt"); fs.writeFileSync(captionPath, caption);
  const captionHash = require("node:crypto").createHash("sha256").update(fs.readFileSync(captionPath)).digest("hex");
  const directory = path.join(dataDir, "tenants/dais-local/marketing/video-publication/anicca-ios"); fs.mkdirSync(directory, { recursive: true });
  const row = { ts: "2026-08-26T08:00:00.000Z", platform: "instagram", status: "published", provider_reconciled: true,
    format_id: "reelclaw-widget", form: "lockscreen-affirmation-widget", locale: "en", creative_id: "EN-WIDGET-BELIEF-c3b80a8f670d",
    provider_id: "cmtwidgetexact123", public_url: "https://www.instagram.com/reel/ExactWidget1/",
    caption_path: captionPath, caption_sha256: captionHash, video_sha256: "c3b80a8f670df10e4eeb9bcdef5037f86ec552b5b7d389001382564f636e95de" };
  fs.writeFileSync(path.join(directory, "distribution.jsonl"), `${JSON.stringify(row)}\n`);
  assert.deepEqual(discoverExpected(dataDir), [{
    tenant_id: "dais-local", product_id: "anicca-ios", locale: "en", account_id: "@anicca.en", native_owner: "anicca.en",
    format_id: "reelclaw-widget", form: "lockscreen-affirmation-widget",
    creative_id: row.creative_id,
    integration_id: "cmn8y95rg02d2qx0y09bbk5pb", provider_post_id: row.provider_id, shortcode: "ExactWidget1",
    public_url: row.public_url, caption, published_at: row.ts,
  }]);
});

test("verified JA Widget Reel is discovered for the exact anicca.jp.videos metric lane", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-ja-widget-discovery-"));
  const caption = "今日の自分を大切にする\n\n#anicca #affirmation";
  const captionPath = path.join(dataDir, "caption.txt"); fs.writeFileSync(captionPath, caption);
  const captionHash = require("node:crypto").createHash("sha256").update(fs.readFileSync(captionPath)).digest("hex");
  const directory = path.join(dataDir, "tenants/dais-local/marketing/video-publication/anicca-ios"); fs.mkdirSync(directory, { recursive: true });
  const row = { ts: "2026-10-12T00:10:00.000Z", platform: "instagram", status: "published", provider_reconciled: true,
    format_id: "reelclaw-widget", form: "lockscreen-affirmation-widget", locale: "ja", creative_id: "JA-WIDGET-TEST-1",
    provider_id: "cmtjajwidget123", public_url: "https://www.instagram.com/reel/JaWidget123/",
    caption_path: captionPath, caption_sha256: captionHash };
  fs.writeFileSync(path.join(directory, "distribution.jsonl"), `${JSON.stringify(row)}\n`);
  assert.deepEqual(discoverExpected(dataDir), [{
    tenant_id: "dais-local", product_id: "anicca-ios", locale: "ja", account_id: "@anicca.jp.videos", native_owner: "anicca.jp.videos",
    format_id: "reelclaw-widget", form: "lockscreen-affirmation-widget",
    creative_id: row.creative_id,
    integration_id: "cmmzzg2es0539p30ycb94ayx0", provider_post_id: row.provider_id, shortcode: "JaWidget123",
    public_url: row.public_url, caption, published_at: row.ts,
  }]);
});

test("verified EN affirmation native-carousel receipt is discovered as an immutable metric effect", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-carousel-discovery-"));
  const caption = "5 affirmations to tell\nyourself every morning... | #anicca #affirmation";
  const captionHash = require("node:crypto").createHash("sha256").update(caption).digest("hex");
  const objectDir = path.join(dataDir, "objects", "sha256"); fs.mkdirSync(objectDir, { recursive: true });
  fs.writeFileSync(path.join(objectDir, captionHash), caption);
  fs.chmodSync(path.join(objectDir, captionHash), 0o600);
  const directory = path.join(dataDir, "tenants/dais-local/marketing/native-carousel-publication/anicca-ios"); fs.mkdirSync(directory, { recursive: true });
  const receipt = {
    schema_version: 1, kind: "marketing_native_carousel_distribution", status: "published",
    product_id: "anicca-ios", format_id: "larry", form: "affirmation-carousel", locale: "en",
    platform: "instagram", account_id: "@anicca.affirmation",
    integration_ref: "integration://postiz/instagram/cmp9pedr700ttqh0yj8o57fog",
    creative_id: "EN-AFFIRMATION-CAROUSEL-da8d8265",
    pack_sha256: "e23cd41257832d2032fd889bd9a16ec95ea8dc213cdd7a2e3f820fbe1578669e",
    media_sha256: ["da8d8265a1344b68a877d776b0cec5b599dc7b3bbd6abc833fcef06e7416df1f", "4fe9ab673f095d39368744974c677cbb5f8305dc2a9dcd1ef1b4b87759d8b42a", "1af8a8c790a733ff1cedca85aaf3de010671a03f54223205da0fd9575a242840", "d097d7b7254ee0a35c95844a89e1f8d1d644775dea134f960ac5e8cb80d230f9", "71ded59ff8a1de5251e607a6ba808945c85537bfca3fbd7f20c65f2912f00e34", "418ad1907d64e4835939bda677709aace44092a936e8a18a7cb8aeeca7652f4f"],
    media_order_sha256: "4daa5db7eb36b424e46057dbf404c390bf1c5c86d44ef99686c48f84429837f9",
    caption_sha256: captionHash, provider_post_id: "cmt9jm8990291p20y0a2l1xmk", provider_reconciled: true,
    public_url: "https://www.instagram.com/p/DcfQ2-hG3KR/", published_at: "2026-08-26T03:37:17.624Z",
  };
  fs.writeFileSync(path.join(directory, "distribution.jsonl"), `${JSON.stringify({ effect_key: "exact", job_id: "job", receipt })}\n`);
  assert.deepEqual(discoverExpected(dataDir), [{
    tenant_id: "dais-local", product_id: "anicca-ios", locale: "en", account_id: "@anicca.affirmation",
    native_owner: "anicca.ios", integration_id: "cmp9pedr700ttqh0yj8o57fog", provider_post_id: "cmt9jm8990291p20y0a2l1xmk",
    format_id: "larry", form: "affirmation-carousel",
    creative_id: receipt.creative_id,
    shortcode: "DcfQ2-hG3KR", public_url: "https://www.instagram.com/p/DcfQ2-hG3KR/", caption,
    published_at: "2026-08-26T03:37:17.624Z",
  }]);
});

test("verified JA Larry native-carousel receipt is discovered for the exact Japanese metric lane", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-ja-carousel-discovery-"));
  const caption = "メンタルが勝手に安定する\n口癖５選\n\n#anicca #affirmation";
  const captionHash = require("node:crypto").createHash("sha256").update(caption).digest("hex");
  const objectDir = path.join(dataDir, "objects", "sha256"); fs.mkdirSync(objectDir, { recursive: true });
  fs.writeFileSync(path.join(objectDir, captionHash), caption); fs.chmodSync(path.join(objectDir, captionHash), 0o600);
  const media = [1, 2, 3, 4, 5, 6].map((position) => String(position).repeat(64));
  const mediaOrderHash = require("node:crypto").createHash("sha256").update(JSON.stringify(media)).digest("hex");
  const receipt = {
    schema_version: 1, kind: "marketing_native_carousel_distribution", status: "published",
    product_id: JA_LANE.productId, format_id: JA_LANE.formatId, form: JA_LANE.form, locale: JA_LANE.locale,
    platform: JA_LANE.platform, account_id: JA_LANE.accountId, integration_ref: JA_LANE.integrationRef,
    creative_id: "LARRY-JA-METRICS-1", pack_sha256: "a".repeat(64), media_sha256: media,
    media_order_sha256: mediaOrderHash, caption_sha256: captionHash, provider_post_id: "cmjalarrymetrics1",
    provider_reconciled: true, public_url: "https://www.instagram.com/p/JaLarryMetrics1/",
    published_at: "2026-10-11T07:30:00.000Z",
  };
  assert.equal(verifyMarketingNativeCarouselPublicationReceipt(receipt), true);
  const directory = path.join(dataDir, "tenants/dais-local/marketing/native-carousel-publication/anicca-ios"); fs.mkdirSync(directory, { recursive: true });
  fs.writeFileSync(path.join(directory, "distribution.jsonl"), `${JSON.stringify({ effect_key: "exact-ja", job_id: "ja-slot", receipt })}\n`);
  assert.deepEqual(discoverExpected(dataDir), [{
    tenant_id: "dais-local", product_id: "anicca-ios", locale: "ja", account_id: "@ani.cca1234", native_owner: "ani.cca1234",
    format_id: "larry", form: "affirmation-carousel",
    creative_id: receipt.creative_id,
    integration_id: "cmq3sq7mc000eqp0y7azfm8yk", provider_post_id: receipt.provider_post_id, shortcode: "JaLarryMetrics1",
    public_url: receipt.public_url, caption, published_at: receipt.published_at,
  }]);
});

test("no metric snapshot leaves the Instagram daily digest pending without failing the run", async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-empty-daily-"));
  const expected = { ...EXPECTED, shortcode: "NoMetricInstagramDue", published_at: "2026-10-12T08:45:00.000Z" };
  const result = await runDue(Date.parse("2026-10-12T09:00:00.000Z"), { LM_DATA_DIR: dataDir }, [expected], {
    collectWindow: async () => { throw new Error("metric source unavailable"); },
  });
  const daily = result.find((row) => row.window === "daily");
  assert.equal(daily.state, "pending");
  assert.equal(daily.reason, "no_metric_snapshot");
});

test("due runner repairs a delayed 7d checkpoint from exact normalized evidence without a new provider read", async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-instagram-due-7d-correction-"));
  const expected = { ...EXPECTED, locale: "en", account_id: "@anicca.en", native_owner: "anicca.en",
    integration_id: "cmn8y95rg02d2qx0y09bbk5pb", provider_post_id: "cmui7zo8n0ixho80yybalkhj0",
    shortcode: "DdvxhT1jm8F", public_url: "https://www.instagram.com/reel/DdvxhT1jm8F/",
    published_at: "2026-09-26T10:01:00.000Z" };
  const nowMs = Date.parse("2026-10-14T06:30:00.000Z"); const env = { LM_DATA_DIR: dataDir };
  persistDelayedSnapshot({ dataDir, window: "7d", observedAt: "2026-10-11T05:13:08.332Z", expected });
  const metric = {
    observed_at: "2026-10-03T10:02:54Z", published_at: expected.published_at,
    product_id: expected.product_id, platform: "instagram", integration_id: expected.integration_id,
    postiz_id: expected.provider_post_id, native_post_id: "18112495088019182", native_url: expected.public_url,
    target_age_hours: 168, observed_age_hours: 168.0317, checkpoint_status: "measured", checkpoint_sla_status: "in_window",
    views: 2229, reach: 1610, saves: 3, likes: 1, comments: 0, shares: 0, impressions: null,
    metric_null_reasons: { impressions: "provider_field_missing" },
    raw_evidence_hash: "4adaa1eb4e57c8d3f6d95ef7bcd4bdaa868cd8374b0c97fbeb3f0a86a71779f5",
    snapshot_id: "228aca83e0a54abdac63957c1c349eabc23a6147b9f0e242bea381e165c283d0",
    source: "postiz_instagram_graph_api",
  };
  const identity = {
    observed_at: "2026-10-04T09:44:01Z", publish_date: expected.published_at,
    account_id: "instagram.anicca_en", platform: "instagram-standalone", product_id: "anicca-ios",
    integration_id: expected.integration_id, postiz_post_id: expected.provider_post_id,
    native_post_id: "18112495088019182", native_post_url: expected.public_url,
    postiz_state: "PUBLISHED", identity_status: "resolved", resolution_method: "postiz_provider_native_receipt",
  };
  const metricsFile = path.join(dataDir, "marketing-owner-events", "state", "post-metrics.jsonl");
  const identitiesFile = path.join(dataDir, "state", "publication-identity.jsonl");
  fs.mkdirSync(path.dirname(metricsFile), { recursive: true }); fs.mkdirSync(path.dirname(identitiesFile), { recursive: true });
  fs.writeFileSync(metricsFile, JSON.stringify(metric) + "\n"); fs.writeFileSync(identitiesFile, JSON.stringify(identity) + "\n");
  const calls = [];
  const result = await runDue(nowMs, env, [expected], { collectWindow: async (window) => { calls.push(window); return { created: false, telegram: { created: false } }; } });
  const correctionFile = path.join(dataDir, "tenants/dais-local/marketing/metrics/anicca.en/DdvxhT1jm8F/7d.correction.json");
  assert.equal(result.find((row) => row.window === "7d").state, "corrected");
  assert.equal(fs.existsSync(correctionFile), true);
  assert.deepEqual(calls, ["current"]);
});
