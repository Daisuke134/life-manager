"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  createCreativeMetricsProvider,
  readCreativeMetrics,
  recordCreativeMetric,
} = require("./marketing-creative-metrics.js");

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "lm-creative-metrics-"));
}

test("recordCreativeMetric appends a validated row and readCreativeMetrics returns it", () => {
  const dataDir = tmpDir();
  const row = recordCreativeMetric(dataDir, {
    tenantId: "tenant-a",
    productId: "honne-ai",
    formatId: "reelclaw",
    locale: "ja",
    hookId: "HJA-001",
    providerPostId: "abc123",
    score: 12.5,
    observedAt: "2026-09-01T00:00:00.000Z",
  });
  assert.equal(row.kind, "marketing_creative_metric");
  const rows = readCreativeMetrics(dataDir);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].hook_id, "HJA-001");
  assert.equal(fs.statSync(path.join(dataDir, "marketing", "creative-metrics.jsonl")).mode & 0o777, 0o600);
});

test("recordCreativeMetric fails closed on invalid input", () => {
  const dataDir = tmpDir();
  assert.throws(() => recordCreativeMetric(dataDir, {
    tenantId: "tenant-a", productId: "honne-ai", formatId: "reelclaw", locale: "ja",
    hookId: "HJA-001", providerPostId: "abc123", score: -1, observedAt: "2026-09-01T00:00:00.000Z",
  }), /score is invalid/);
  assert.throws(() => recordCreativeMetric(dataDir, {
    tenantId: "tenant-a", productId: "honne-ai", formatId: "reelclaw", locale: "ja",
    hookId: "HJA-001", providerPostId: "abc123", score: 1, observedAt: "not-a-date",
  }), /observed_at is invalid/);
});

test("createCreativeMetricsProvider averages scores per hook, scoped to product/format/locale", async () => {
  const dataDir = tmpDir();
  recordCreativeMetric(dataDir, { tenantId: "tenant-a", productId: "honne-ai", formatId: "reelclaw", locale: "ja", hookId: "HJA-001", providerPostId: "p1", score: 10, observedAt: "2026-09-01T00:00:00.000Z" });
  recordCreativeMetric(dataDir, { tenantId: "tenant-a", productId: "honne-ai", formatId: "reelclaw", locale: "ja", hookId: "HJA-001", providerPostId: "p2", score: 20, observedAt: "2026-09-02T00:00:00.000Z" });
  recordCreativeMetric(dataDir, { tenantId: "tenant-a", productId: "honne-ai", formatId: "reelclaw", locale: "ja", hookId: "HJA-002", providerPostId: "p3", score: 1, observedAt: "2026-09-02T00:00:00.000Z" });
  // Different scope must not leak in.
  recordCreativeMetric(dataDir, { tenantId: "tenant-a", productId: "honne-ai", formatId: "reelclaw", locale: "en", hookId: "HJA-001", providerPostId: "p4", score: 999, observedAt: "2026-09-02T00:00:00.000Z" });

  const provider = createCreativeMetricsProvider(dataDir);
  const rows = await provider.list({ tenantId: "tenant-a", productId: "honne-ai", formatId: "reelclaw", locale: "ja" });
  const byHook = Object.fromEntries(rows.map(({ hook_id, score }) => [hook_id, score]));
  assert.equal(byHook["HJA-001"], 15);
  assert.equal(byHook["HJA-002"], 1);
});

test("createCreativeMetricsProvider returns empty list when no ledger exists yet", async () => {
  const dataDir = tmpDir();
  const provider = createCreativeMetricsProvider(dataDir);
  const rows = await provider.list({ tenantId: "tenant-a", productId: "honne-ai", formatId: "reelclaw", locale: "ja" });
  assert.deepEqual(rows, []);
});
