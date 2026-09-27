"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  buildMarketingVideoGenerationJob,
  createMarketingVideoGenerationLoopAdapter,
  selectHook,
  verifyMarketingVideoGenerationReceipt,
} = require("./marketing-video-generation-adapter.js");
const { importContentObject } = require("./content-object-store.js");

const HASH_A = "a".repeat(64);
const HASH_B = "b".repeat(64);
const HASH_C = "c".repeat(64);

function job(overrides = {}) {
  return buildMarketingVideoGenerationJob({
    tenantId: "tenant-a",
    productId: "honne-ai",
    formatId: "reelclaw",
    locale: "ja",
    slot: "2026-07-30T12:30:00.000Z",
    packRef: `object://sha256/${HASH_A}`,
    mediaRefs: [
      `object://sha256/${HASH_B}`,
      `object://sha256/${HASH_C}`,
    ],
    ...overrides,
  });
}

test("generic video generation job is deterministic, tenant-bound, and reference-only", () => {
  const value = job();
  const replay = job();

  assert.equal(value.job_id, replay.job_id);
  assert.equal(value.loop_id, "marketing.video.generate");
  assert.equal(value.capability, "marketing.video.generate");
  assert.equal(value.effect_class, "none");
  assert.deepEqual(value.input_refs, {
    product_ref: "product://honne-ai",
    format_ref: "format://reelclaw",
    locale_ref: "locale://ja",
    slot_ref: "schedule-slot://2026-07-30T12:30:00.000Z",
    pack_ref: `object://sha256/${HASH_A}`,
    media_refs: [
      `object://sha256/${HASH_B}`,
      `object://sha256/${HASH_C}`,
    ],
  });
  assert.doesNotMatch(JSON.stringify(value), /\.openclaw|profitable-claude|\/Users\//);
});

test("mobile product packs reject the Life Manager wake/demo format", () => {
  assert.throws(
    () => job({ productId: "anicca-ios", formatId: "anicca-wake" }),
    /cannot use format/i,
  );
});

test("adapter selects the least-recent hook and creates immutable copy plus video lineage", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-video-generation-"));
  const objects = path.join(root, "objects");
  const packPath = path.join(root, "pack.json");
  const firstVideo = path.join(root, "v1.mp4");
  const secondVideo = path.join(root, "v2.mp4");
  const secondVideoRef = `object://sha256/${crypto.createHash("sha256").update("0000ftyp-second-video").digest("hex")}`;
  fs.writeFileSync(packPath, `${JSON.stringify({
    schema_version: 1,
    product_id: "honne-ai",
    format_id: "reelclaw",
    form: "relationship-confession",
    locale: "ja",
    title: "Honne — 言いたいこと、翻訳します",
    hashtags: ["honne", "恋愛"],
    hooks: [
      {
        id: "HJA-001",
        text: "first hook",
        status: "active",
        prior_used_at: "2026-07-28T12:00:00.000Z",
      },
      {
        id: "HJA-002",
        text: "second hook",
        status: "active",
        prior_used_at: null,
        media_ref: secondVideoRef,
      },
      {
        id: "HJA-003",
        text: "killed hook",
        status: "killed",
        prior_used_at: null,
      },
    ],
  })}\n`);
  fs.writeFileSync(firstVideo, Buffer.from("0000ftyp-first-video"));
  fs.writeFileSync(secondVideo, Buffer.from("0000ftyp-second-video"));
  const pack = importContentObject(packPath, { objectDir: objects });
  const media = [firstVideo, secondVideo].map((source) => (
    importContentObject(source, { objectDir: objects })
  ));
  const executionJob = buildMarketingVideoGenerationJob({
    tenantId: "tenant-a",
    productId: "honne-ai",
    formatId: "reelclaw",
    locale: "ja",
    slot: "2026-07-30T12:30:00.000Z",
    packRef: pack.ref,
    mediaRefs: media.map(({ ref }) => ref),
  });
  const historyCalls = [];
  const adapter = createMarketingVideoGenerationLoopAdapter({
    dataDir: root,
    historyProvider: {
      async list(scope) {
        historyCalls.push(scope);
        return [];
      },
    },
    now: () => "2026-07-30T12:30:01.000Z",
  });

  const result = await adapter.execute(executionJob);

  assert.deepEqual(historyCalls, [{
    tenantId: "tenant-a",
    productId: "honne-ai",
    formatId: "reelclaw",
    locale: "ja",
  }]);
  assert.equal(result.receipt.hook_id, "HJA-002");
  assert.equal(result.receipt.product_id, "honne-ai");
  assert.equal(result.receipt.format_id, "reelclaw");
  assert.equal(result.receipt.video_ref, secondVideoRef);
  assert.equal(
    result.receipt.video_sha256,
    result.receipt.video_ref.slice("object://sha256/".length),
  );
  assert.match(result.receipt.copy_ref, /^object:\/\/sha256\/[0-9a-f]{64}$/);
  const copyPath = path.join(
    objects,
    "sha256",
    result.receipt.copy_sha256,
  );
  assert.equal(
    fs.readFileSync(copyPath, "utf8"),
    "second hook\n\n#honne #恋愛\n",
  );
  assert.equal(fs.statSync(copyPath).mode & 0o777, 0o600);
  // The generated copy is plain caption text, so its workspace file is .copy.txt (not .copy.json).
  const workspace = path.join(root, "tenants", "tenant-a", "marketing", "video-generation");
  const workspaceFiles = fs.readdirSync(workspace);
  assert.ok(workspaceFiles.some((name) => name.endsWith(".copy.txt")));
  assert.ok(!workspaceFiles.some((name) => name.endsWith(".copy.json")));
  assert.equal(verifyMarketingVideoGenerationReceipt(result.receipt), true);
});

test("durable generation history overrides imported last-used state", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-video-history-"));
  const objects = path.join(root, "objects");
  const packPath = path.join(root, "pack.json");
  const videoPath = path.join(root, "v1.mp4");
  fs.writeFileSync(packPath, `${JSON.stringify({
    schema_version: 1,
    product_id: "honne-ai",
    format_id: "reelclaw",
    form: "relationship-confession",
    locale: "ja",
    title: "Honne",
    hashtags: ["honne"],
    hooks: [
      { id: "HJA-001", text: "one", status: "active", prior_used_at: null },
      { id: "HJA-002", text: "two", status: "active", prior_used_at: null },
    ],
  })}\n`);
  fs.writeFileSync(videoPath, Buffer.from("0000ftyp-video"));
  const pack = importContentObject(packPath, { objectDir: objects });
  const media = importContentObject(videoPath, { objectDir: objects });
  const adapter = createMarketingVideoGenerationLoopAdapter({
    dataDir: root,
    historyProvider: {
      list: async () => [{
        schema_version: 1,
        kind: "marketing_video_artifact",
        status: "ready",
        product_id: "honne-ai",
        format_id: "reelclaw",
        form: "relationship-confession",
        locale: "ja",
        slot: "2026-07-30T12:30:00.000Z",
        creative_id: "HJA-001-aaaaaaaaaaaa",
        hook_id: "HJA-001",
        hook_sha256: crypto.createHash("sha256").update("one").digest("hex"),
        video_ref: media.ref,
        video_sha256: media.sha256,
        copy_ref: `object://sha256/${"d".repeat(64)}`,
        copy_sha256: "d".repeat(64),
        generated_at: "2026-07-30T12:30:01.000Z",
      }],
    },
    now: () => "2026-07-30T21:30:01.000Z",
  });
  const result = await adapter.execute(buildMarketingVideoGenerationJob({
    tenantId: "tenant-a",
    productId: "honne-ai",
    formatId: "reelclaw",
    locale: "ja",
    slot: "2026-07-30T21:30:00.000Z",
    packRef: pack.ref,
    mediaRefs: [media.ref],
  }));

  assert.equal(result.receipt.hook_id, "HJA-002");
});

test("adapter fails closed on pack identity mismatch, extra fields, or no active hook", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-video-invalid-"));
  const objects = path.join(root, "objects");
  const videoPath = path.join(root, "v1.mp4");
  fs.writeFileSync(videoPath, Buffer.from("0000ftyp-video"));
  const media = importContentObject(videoPath, { objectDir: objects });
  async function executePack(pack) {
    const source = path.join(root, `${crypto.randomUUID()}.json`);
    fs.writeFileSync(source, `${JSON.stringify(pack)}\n`);
    const imported = importContentObject(source, { objectDir: objects });
    const adapter = createMarketingVideoGenerationLoopAdapter({
      dataDir: root,
      historyProvider: { list: async () => [] },
    });
    return adapter.execute(buildMarketingVideoGenerationJob({
      tenantId: "tenant-a",
      productId: "honne-ai",
      formatId: "reelclaw",
      locale: "ja",
      slot: "2026-07-30T12:30:00.000Z",
      packRef: imported.ref,
      mediaRefs: [media.ref],
    }));
  }
  const base = {
    schema_version: 1,
    product_id: "honne-ai",
    format_id: "reelclaw",
    form: "relationship-confession",
    locale: "ja",
    title: "Honne",
    hashtags: [],
    hooks: [
      { id: "HJA-001", text: "one", status: "active", prior_used_at: null },
    ],
  };

  await assert.rejects(
    executePack({ ...base, product_id: "anicca-ios" }),
    /identity/i,
  );
  await assert.rejects(
    executePack({ ...base, secret: "forbidden" }),
    /pack/i,
  );
  await assert.rejects(
    executePack({
      ...base,
      hooks: [{ ...base.hooks[0], status: "killed" }],
    }),
    /active hook/i,
  );
});

test("selectHook is unaffected by metrics when no metrics are supplied (backward compatible)", () => {
  const pack = {
    product_id: "honne-ai",
    format_id: "reelclaw",
    locale: "ja",
    hooks: [
      { id: "HJA-001", text: "one", status: "active", prior_used_at: "2026-07-28T12:00:00.000Z" },
      { id: "HJA-002", text: "two", status: "active", prior_used_at: null },
    ],
  };
  assert.equal(selectHook(pack, []).id, "HJA-002");
  assert.equal(selectHook(pack, [], []).id, "HJA-002");
});

test("selectHook deprioritizes a hook whose recorded metric score is below the median", () => {
  const pack = {
    product_id: "honne-ai",
    format_id: "reelclaw",
    locale: "ja",
    hooks: [
      // HJA-001 is the oldest by prior_used_at, so pure LRU would pick it next.
      { id: "HJA-001", text: "old but underperforms", status: "active", prior_used_at: "2026-07-20T00:00:00.000Z" },
      { id: "HJA-002", text: "newer but performs well", status: "active", prior_used_at: "2026-07-25T00:00:00.000Z" },
    ],
  };
  const metrics = [
    { hook_id: "HJA-001", score: 1 },
    { hook_id: "HJA-002", score: 100 },
  ];
  // Without metrics, LRU alone would pick HJA-001 (oldest).
  assert.equal(selectHook(pack, [], []).id, "HJA-001");
  // With metrics showing HJA-001 underperforms relative to the median, it is deprioritized
  // one tier below every non-deprioritized hook, so HJA-002 is picked instead.
  assert.equal(selectHook(pack, [], metrics).id, "HJA-002");
});

test("selectHook still explores a never-used hook ahead of any scored, already-used hook", () => {
  const pack = {
    product_id: "honne-ai",
    format_id: "reelclaw",
    locale: "ja",
    hooks: [
      { id: "HJA-001", text: "used, top performer", status: "active", prior_used_at: "2026-07-20T00:00:00.000Z" },
      { id: "HJA-002", text: "never used yet", status: "active", prior_used_at: null },
    ],
  };
  const metrics = [{ hook_id: "HJA-001", score: 100 }];
  assert.equal(selectHook(pack, [], metrics).id, "HJA-002");
});

test("selectHook never fully excludes an underperforming hook (only status: killed does that)", () => {
  const pack = {
    product_id: "honne-ai",
    format_id: "reelclaw",
    locale: "ja",
    hooks: [
      { id: "HJA-001", text: "only hook, underperforms", status: "active", prior_used_at: "2026-07-20T00:00:00.000Z" },
    ],
  };
  const metrics = [{ hook_id: "HJA-001", score: 1 }];
  assert.equal(selectHook(pack, [], metrics).id, "HJA-001");
});

test("selectHook rejects invalid metrics rows", () => {
  const pack = {
    product_id: "honne-ai",
    format_id: "reelclaw",
    locale: "ja",
    hooks: [{ id: "HJA-001", text: "one", status: "active", prior_used_at: null }],
  };
  assert.throws(() => selectHook(pack, [], [{ hook_id: "HJA-001", score: -1 }]), /metrics are invalid/);
  assert.throws(() => selectHook(pack, [], [{ hook_id: "HJA-001", score: "high" }]), /metrics are invalid/);
  assert.throws(() => selectHook(pack, [], "not-an-array"), /metrics are invalid/);
});

test("adapter's execute() queries metricsProvider and lets a recorded score change the picked hook", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-video-metrics-"));
  const objects = path.join(root, "objects");
  const packPath = path.join(root, "pack.json");
  const video = path.join(root, "v1.mp4");
  fs.writeFileSync(packPath, `${JSON.stringify({
    schema_version: 1,
    product_id: "honne-ai",
    format_id: "reelclaw",
    form: "relationship-confession",
    locale: "ja",
    title: "Honne",
    hashtags: [],
    hooks: [
      { id: "HJA-001", text: "old but underperforms", status: "active", prior_used_at: "2026-07-20T00:00:00.000Z" },
      { id: "HJA-002", text: "newer but performs well", status: "active", prior_used_at: "2026-07-25T00:00:00.000Z" },
    ],
  })}\n`);
  fs.writeFileSync(video, Buffer.from("0000ftyp-video"));
  const pack = importContentObject(packPath, { objectDir: objects });
  const media = importContentObject(video, { objectDir: objects });
  const metricsCalls = [];
  const adapter = createMarketingVideoGenerationLoopAdapter({
    dataDir: root,
    historyProvider: { list: async () => [] },
    metricsProvider: {
      list: async (scope) => {
        metricsCalls.push(scope);
        return [{ hook_id: "HJA-001", score: 1 }, { hook_id: "HJA-002", score: 100 }];
      },
    },
    now: () => "2026-07-30T12:30:01.000Z",
  });
  const executionJob = buildMarketingVideoGenerationJob({
    tenantId: "tenant-a",
    productId: "honne-ai",
    formatId: "reelclaw",
    locale: "ja",
    slot: "2026-07-30T12:30:00.000Z",
    packRef: pack.ref,
    mediaRefs: [media.ref],
  });

  const result = await adapter.execute(executionJob);

  assert.deepEqual(metricsCalls, [{
    tenantId: "tenant-a",
    productId: "honne-ai",
    formatId: "reelclaw",
    locale: "ja",
  }]);
  assert.equal(result.receipt.hook_id, "HJA-002");
});
