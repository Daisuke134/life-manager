"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const { TARGETS } = require("./tiktok-metrics-due.js");
const SCRIPT = path.join(__dirname, "marketing-creative-metrics-join.js");

function writeJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
}

function createFixture() {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-creative-metrics-join-"));
  const caption = "A fixture caption with a verified hash.";
  const captionSha = crypto.createHash("sha256").update(caption).digest("hex");
  const captionPath = path.join(dataDir, "caption.txt");
  fs.writeFileSync(captionPath, caption);
  const objectPath = path.join(dataDir, "objects", "sha256", captionSha);
  fs.mkdirSync(path.dirname(objectPath), { recursive: true });
  fs.writeFileSync(objectPath, caption, { mode: 0o600 });

  const instagramRow = {
    ts: "2026-10-11T23:45:00.000Z",
    platform: "instagram",
    status: "published",
    provider_reconciled: true,
    format_id: "reelclaw-widget",
    form: "lockscreen-affirmation-widget",
    locale: "en",
    creative_id: "ANI-EN-IG-CAROUSEL-V1",
    provider_id: "cmtigcreative1",
    public_url: "https://www.instagram.com/reel/IgCreative1/",
    caption_path: captionPath,
    caption_sha256: captionSha,
    video_sha256: "a".repeat(64),
  };
  const instagramUnattributedRow = {
    ...instagramRow,
    creative_id: undefined,
    provider_id: "cmtiglegacy1",
    public_url: "https://www.instagram.com/reel/IgLegacy1/",
  };
  const videoLedger = path.join(dataDir, "tenants/dais-local/marketing/video-publication/anicca-ios/distribution.jsonl");
  fs.mkdirSync(path.dirname(videoLedger), { recursive: true });
  fs.writeFileSync(videoLedger, `${[instagramRow, instagramUnattributedRow].map((row) => JSON.stringify(row)).join("\n")}\n`);

  const target = TARGETS.find((row) => row.account_id === "@anicca_slideshow");
  assert.ok(target, "Anicca English TikTok slideshow lane must remain in metrics discovery");
  const tiktokReceipt = {
    status: "published",
    provider_reconciled: true,
    platform: "tiktok",
    product_id: target.product_id,
    locale: target.locale,
    account_id: target.account_id,
    integration_ref: `integration://postiz/tiktok/${target.integration_id}`,
    format_id: target.format_id,
    form: target.form,
    creative_id: "ANI-EN-TT-CAROUSEL-V1",
    public_url: null,
    provider_state: "PUBLISHED",
    provider_post_id: "postiz-ani-carousel-v1",
    caption_sha256: captionSha,
    published_at: "2026-10-11T23:50:00.000Z",
  };
  const receiptFile = path.join(dataDir, "marketing/receipts.jsonl");
  fs.mkdirSync(path.dirname(receiptFile), { recursive: true });
  fs.writeFileSync(receiptFile, `${JSON.stringify({ job_id: target.receipt_job_id, receipt: tiktokReceipt })}\n`);

  writeJson(path.join(dataDir, "tenants/dais-local/marketing/metrics/anicca.en/IgCreative1/24h.combined.json"), {
    schema_version: 1,
    kind: "instagram_combined_metric_snapshot",
    product_id: "anicca-ios",
    locale: "en",
    account_id: "@anicca.en",
    provider_post_id: "cmtigcreative1",
    shortcode: "IgCreative1",
    public_url: instagramRow.public_url,
    window: "24h",
    observed_at: "2026-10-12T00:00:00.000Z",
    post: {
      views: { status: "measured", value: 0 },
      saves: { status: "unavailable", value: null, reason: "metric_not_supported" },
    },
  });
  writeJson(path.join(dataDir, "tenants/dais-local/marketing/metrics/anicca_slideshow/postiz-ani-carousel-v1/24h.combined.json"), {
    schema_version: 1,
    kind: "tiktok_postiz_photo_metric_snapshot",
    product_id: "anicca-ios",
    locale: "en",
    account_id: "@anicca_slideshow",
    provider_post_id: "postiz-ani-carousel-v1",
    video_id: "postiz-ani-carousel-v1",
    public_url: "unavailable",
    window: "24h",
    observed_at: "2026-10-12T00:05:00.000Z",
    post: {
      views: { status: "measured", value: 31 },
      shares: { status: "unavailable", value: null, reason: "metric_not_supported" },
    },
  });
  return { dataDir, captionSha };
}

function runJoin(dataDir) {
  return spawnSync(process.execPath, [SCRIPT, "anicca-ios"], {
    encoding: "utf8",
    env: { ...process.env, LM_DATA_DIR: dataDir, LM_MODE: "local" },
  });
}

test("creative metrics CLI joins verified receipts to 24h/7d snapshots without coercing unavailable to zero", (t) => {
  const { dataDir } = createFixture();
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));

  const result = runJoin(dataDir);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.equal(report.kind, "marketing_creative_metrics_join");
  assert.equal(report.product_id, "anicca-ios");
  assert.equal(report.rows.length, 6);

  const ig24 = report.rows.find((row) => row.account_id === "@anicca.en" && row.window === "24h" && row.creative_id);
  assert.equal(ig24.creative_id, "ANI-EN-IG-CAROUSEL-V1");
  assert.equal(ig24.arm_id, "reelclaw-widget:lockscreen-affirmation-widget");
  assert.equal(ig24.provider_post_id, "cmtigcreative1");
  assert.equal(ig24.public_url, "https://www.instagram.com/reel/IgCreative1/");
  assert.equal(ig24.platform, "instagram");
  assert.equal(ig24.metrics.views.status, "measured");
  assert.equal(ig24.metrics.views.value, 0);
  assert.equal(ig24.metrics.saves.status, "unavailable");
  assert.equal(ig24.metrics.saves.value, null);

  const tt24 = report.rows.find((row) => row.account_id === "@anicca_slideshow" && row.window === "24h");
  assert.equal(tt24.creative_id, "ANI-EN-TT-CAROUSEL-V1");
  assert.equal(tt24.arm_id, "slideshow:mental-health-carousel");
  assert.equal(tt24.provider_post_id, "postiz-ani-carousel-v1");
  assert.equal(tt24.public_url, "unavailable");
  assert.equal(tt24.platform, "tiktok");
  assert.equal(tt24.metrics.views.value, 31);

  const legacy = report.rows.find((row) => row.provider_post_id === "cmtiglegacy1" && row.window === "24h");
  assert.equal(legacy.creative_id, null);
  assert.equal(legacy.attribution_status, "unavailable");
  assert.equal(legacy.status, "pending");

  const missingSevenDay = report.rows.find((row) => row.provider_post_id === "cmtigcreative1" && row.window === "7d");
  assert.equal(missingSevenDay.status, "pending");
  assert.equal(missingSevenDay.metrics.views.value, null);
});

test("creative metrics CLI fails closed on a snapshot from another account", (t) => {
  const { dataDir } = createFixture();
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  const snapshotPath = path.join(dataDir, "tenants/dais-local/marketing/metrics/anicca.en/IgCreative1/24h.combined.json");
  const snapshot = JSON.parse(fs.readFileSync(snapshotPath, "utf8"));
  snapshot.account_id = "@other-account";
  writeJson(snapshotPath, snapshot);

  const result = runJoin(dataDir);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /metric snapshot identity mismatch/i);
});

test("creative metrics join prefers an exact 7d correction over its source-delayed snapshot", (t) => {
  const { dataDir, captionSha } = createFixture();
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  const directory = path.join(dataDir, "tenants/dais-local/marketing/metrics/anicca.en/IgCreative1");
  const base = {
    schema_version: 1, kind: "instagram_combined_metric_snapshot", product_id: "anicca-ios", locale: "en",
    account_id: "@anicca.en", integration_id: "cmn8y95rg02d2qx0y09bbk5pb", provider_post_id: "cmtigcreative1", shortcode: "IgCreative1",
    caption_sha256: captionSha,
    public_url: "https://www.instagram.com/reel/IgCreative1/", published_at: "2026-10-11T23:45:00.000Z", window: "7d",
    sources: { postiz_post: { status: "unavailable", reason: "source_delayed" } },
    post: { views: { status: "unavailable", value: null, reason: "source_delayed" } },
  };
  writeJson(path.join(directory, "7d.combined.json"), base);
  writeJson(path.join(directory, "7d.correction.json"), {
    ...base, kind: "instagram_combined_metric_snapshot_correction", correction: true,
    observed_at: "2026-10-13T23:45:00.000Z", source_snapshot_id: "a".repeat(64),
    post: { views: { status: "measured", value: 2229, source_date: "2026-10-13" } },
  });

  const result = runJoin(dataDir);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(result.stdout);
  const ig7 = report.rows.find((row) => row.account_id === "@anicca.en" && row.provider_post_id === "cmtigcreative1" && row.window === "7d");
  assert.equal(ig7.status, "observed");
  assert.equal(ig7.metrics.views.status, "measured");
  assert.equal(ig7.metrics.views.value, 2229);
});
