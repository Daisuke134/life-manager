"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { engagementScore, recordCreativeMetrics } = require("./record-creative-metrics.js");
const { readCreativeMetrics } = require("../lib/marketing-creative-metrics.js");

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "lm-record-creative-metrics-"));
}

function writeReceiptLedger(dataDir, rows) {
  const file = path.join(dataDir, "marketing", "receipts.jsonl");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`);
}

function generationRow({ jobId, hookId, creativeId }) {
  return {
    schema_version: 1,
    kind: "marketing_video_artifact",
    tenant_id: "dais-local",
    job_id: jobId,
    attempt: 1,
    receipt: {
      product_id: "honne-ai",
      format_id: "reelclaw",
      locale: "ja",
      hook_id: hookId,
      creative_id: creativeId,
      status: "ready",
    },
  };
}

function publicationRow({ jobId, creativeId, providerPostId }) {
  return {
    schema_version: 1,
    kind: "marketing_video_distribution",
    tenant_id: "dais-local",
    job_id: jobId,
    attempt: 1,
    receipt: {
      product_id: "honne-ai",
      format_id: "reelclaw",
      locale: "ja",
      status: "published",
      creative_id: creativeId,
      provider_post_id: providerPostId,
    },
  };
}

test("engagementScore uses Postiz string totals and ignores percentageChange", () => {
  const postizRows = [
    { label: "Views", percentageChange: 250, data: [{ total: "100", date: "2026-10-11" }] },
    { label: "Likes", percentageChange: 900, data: [{ total: "12", date: "2026-10-11" }] },
    { label: "Comments", percentageChange: 25, data: [{ total: "2", date: "2026-10-11" }] },
    { label: "Shares", percentageChange: 0, data: [{ total: "1", date: "2026-10-11" }] },
  ];
  assert.equal(engagementScore(postizRows), 115);
  assert.equal(engagementScore({ views: 100, engagement: { likes: 10, comments: 2 }, tags: ["a"] }), 112);
  assert.equal(engagementScore([{ plays: 5 }, { shares: 3 }]), 8);
  assert.equal(engagementScore(null), null);
  assert.equal(engagementScore([]), null);
});

test("recordCreativeMetrics joins generation -> publication via creative_id prefix and records one row per post", async () => {
  const dataDir = tmpDir();
  writeReceiptLedger(dataDir, [
    generationRow({ jobId: "g1", hookId: "HJA-001", creativeId: "HJA-001-aaaaaaaaaaaa" }),
    publicationRow({ jobId: "p1", creativeId: "HJA-001-aaaaaaaaaaaa-20260927T123000000Z", providerPostId: "post-1" }),
  ]);
  const analyticsCalls = [];
  const result = await recordCreativeMetrics({
    dataDir,
    tenantId: "dais-local",
    productId: "honne-ai",
    formatId: "reelclaw",
    locale: "ja",
    fetchAnalytics: async (providerPostId) => { analyticsCalls.push(providerPostId); return { views: 50, likes: 5 }; },
    now: () => "2026-09-27T00:00:00.000Z",
  });
  assert.deepEqual(analyticsCalls, ["post-1"]);
  assert.equal(result.recorded.length, 1);
  assert.equal(result.recorded[0].hook_id, "HJA-001");
  assert.equal(result.recorded[0].score, 55);
  assert.equal(readCreativeMetrics(dataDir).length, 1);
});

test("recordCreativeMetrics is idempotent per provider_post_id on rerun", async () => {
  const dataDir = tmpDir();
  writeReceiptLedger(dataDir, [
    generationRow({ jobId: "g1", hookId: "HJA-001", creativeId: "HJA-001-aaaaaaaaaaaa" }),
    publicationRow({ jobId: "p1", creativeId: "HJA-001-aaaaaaaaaaaa-20260927T123000000Z", providerPostId: "post-1" }),
  ]);
  let calls = 0;
  const fetchAnalytics = async () => { calls += 1; return { views: 50 }; };
  await recordCreativeMetrics({ dataDir, tenantId: "dais-local", productId: "honne-ai", formatId: "reelclaw", locale: "ja", fetchAnalytics, now: () => "2026-09-27T00:00:00.000Z" });
  const second = await recordCreativeMetrics({ dataDir, tenantId: "dais-local", productId: "honne-ai", formatId: "reelclaw", locale: "ja", fetchAnalytics, now: () => "2026-09-28T00:00:00.000Z" });
  assert.equal(calls, 1);
  assert.equal(second.recorded.length, 0);
  assert.equal(readCreativeMetrics(dataDir).length, 1);
});

test("recordCreativeMetrics skips a publication whose generation lineage cannot be found", async () => {
  const dataDir = tmpDir();
  writeReceiptLedger(dataDir, [
    publicationRow({ jobId: "p1", creativeId: "UNKNOWN-000000000000-20260927T123000000Z", providerPostId: "post-1" }),
  ]);
  const result = await recordCreativeMetrics({
    dataDir, tenantId: "dais-local", productId: "honne-ai", formatId: "reelclaw", locale: "ja",
    fetchAnalytics: async () => { throw new Error("must not be called"); },
    now: () => "2026-09-27T00:00:00.000Z",
  });
  assert.deepEqual(result.skipped, ["post-1"]);
  assert.equal(result.recorded.length, 0);
});

test("recordCreativeMetrics does not cross tenant/product/format/locale scope", async () => {
  const dataDir = tmpDir();
  writeReceiptLedger(dataDir, [
    generationRow({ jobId: "g1", hookId: "HJA-001", creativeId: "HJA-001-aaaaaaaaaaaa" }),
    { ...publicationRow({ jobId: "p1", creativeId: "HJA-001-aaaaaaaaaaaa-20260927T123000000Z", providerPostId: "post-1" }), receipt: { ...publicationRow({ jobId: "p1", creativeId: "HJA-001-aaaaaaaaaaaa-20260927T123000000Z", providerPostId: "post-1" }).receipt, locale: "en" } },
  ]);
  const result = await recordCreativeMetrics({
    dataDir, tenantId: "dais-local", productId: "honne-ai", formatId: "reelclaw", locale: "ja",
    fetchAnalytics: async () => { throw new Error("must not be called"); },
    now: () => "2026-09-27T00:00:00.000Z",
  });
  assert.equal(result.recorded.length, 0);
  assert.equal(result.skipped.length, 0);
});

test("recordCreativeMetrics leaves empty Postiz analytics pending instead of recording zero", async () => {
  const dataDir = tmpDir();
  writeReceiptLedger(dataDir, [
    generationRow({ jobId: "g1", hookId: "HJA-001", creativeId: "HJA-001-aaaaaaaaaaaa" }),
    publicationRow({ jobId: "p1", creativeId: "HJA-001-aaaaaaaaaaaa-20260927T123000000Z", providerPostId: "post-1" }),
  ]);
  const result = await recordCreativeMetrics({
    dataDir,
    tenantId: "dais-local",
    productId: "honne-ai",
    formatId: "reelclaw",
    locale: "ja",
    fetchAnalytics: async () => [],
    now: () => "2026-09-27T00:00:00.000Z",
  });
  assert.deepEqual(result.pending, ["post-1"]);
  assert.equal(result.recorded.length, 0);
  assert.equal(readCreativeMetrics(dataDir).length, 0);
});
