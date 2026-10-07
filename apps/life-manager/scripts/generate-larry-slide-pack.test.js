"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const { JA_LANE, EN_SLIDESHOW_TIKTOK_LANE } = require("../lib/marketing-native-carousel-publication-adapter.js");
const {
  MIN_DAYS_BETWEEN_REPEAT,
  poolPath,
  readPostedHistory,
  resolveLarryJaSlot,
} = require("./generate-larry-slide-pack.js");

const TENANT = "dais-local";
const NOW = "2026-09-28T01:30:00.000Z";

function tempDataDir(t) {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "larry-slide-pack-scheduler-"));
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  return dataDir;
}

function fakeResolveBackground() {
  return async () => ({ file: path.join(os.tmpdir(), "generate-larry-slide-pack-fixture.png"), costUsd: 0, cached: true });
}

let copyCounter = 0;
function fakeGenerateText() {
  // Realistic-length fake lines (matches real Gemini output length) -- a
  // too-short fake string is an unrepresentative edge case for the render/
  // contrast check, not a real production scenario.
  return async () => {
    copyCounter += 1;
    const n = copyCounter;
    return {
      text: JSON.stringify({
        hook: `テストの見出しです${n}\n二行目もあります`,
        body: [`ひとつめの本文です${n}`, `ふたつめの本文です${n}`, `みっつめの本文です${n}`, `よっつめの本文です${n}`],
      }),
      costUsd: 0.0004,
    };
  };
}

function makeFixtureBackgroundOnce() {
  const file = path.join(os.tmpdir(), "generate-larry-slide-pack-fixture.png");
  if (fs.existsSync(file)) return;
  const { spawnSync } = require("node:child_process");
  // A noisy (non-flat) fixture -- matches marketing-slide-pack-factory.test.js's
  // fixture -- so the renderer's real contrast check reliably passes
  // regardless of the (freshly LLM-generated in production, counter-faked
  // here) text length/content.
  const script = `
from PIL import Image
import random
random.seed(7)
im = Image.new("RGB", (600, 750))
px = im.load()
for y in range(750):
    for x in range(600):
        px[x, y] = ((x * 255) // 600, (y * 255) // 750, random.randint(0, 255))
im.save("${file}")
`;
  const result = spawnSync("python3", ["-c", script], { encoding: "utf8" });
  if (result.status !== 0) throw new Error(`fixture background generation failed: ${result.stderr}`);
}

function writeDistributionLedger(dataDir, rows) {
  const file = path.join(dataDir, "tenants", encodeURIComponent(TENANT), "marketing", "native-carousel-publication", JA_LANE.productId, "distribution.jsonl");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, rows.map((r) => `${JSON.stringify(r)}\n`).join(""));
}

test("resolveLarryJaSlot generates a pool from empty and returns a candidate", { timeout: 60_000 }, async (t) => {
  makeFixtureBackgroundOnce();
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const { slot, selected } = await resolveLarryJaSlot({ env, now: () => NOW, slot: "2026-09-28T01:30:00.000Z", resolveBackground: fakeResolveBackground(), generateText: fakeGenerateText() });
  assert.equal(slot, "2026-09-28T01:30:00.000Z");
  assert.match(selected.packRef, /^object:\/\/sha256\/[0-9a-f]{64}$/);
  assert.equal(selected.mediaRefs.length, 6);

  const pool = poolPath(dataDir, TENANT, JA_LANE.productId, JA_LANE.lane);
  assert.ok(fs.existsSync(pool));
});

test("resolveLarryJaSlot does not regenerate once the pool already has enough candidates", { timeout: 60_000 }, async (t) => {
  makeFixtureBackgroundOnce();
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  await resolveLarryJaSlot({ env, now: () => NOW, slot: "2026-09-28T01:30:00.000Z", resolveBackground: fakeResolveBackground(), generateText: fakeGenerateText() });
  const pool = poolPath(dataDir, TENANT, JA_LANE.productId, JA_LANE.lane);
  const before = fs.readFileSync(pool, "utf8");
  await resolveLarryJaSlot({ env, now: () => NOW, slot: "2026-09-28T07:30:00.000Z", resolveBackground: fakeResolveBackground(), generateText: fakeGenerateText() });
  const after = fs.readFileSync(pool, "utf8");
  assert.equal(before, after, "pool should not grow once above MIN_POOL_SIZE");
});

test("resolveLarryJaSlot never repeats a pack posted within MIN_DAYS_BETWEEN_REPEAT and is idempotent per slot", { timeout: 60_000 }, async (t) => {
  makeFixtureBackgroundOnce();
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const first = await resolveLarryJaSlot({ env, now: () => NOW, slot: "2026-09-28T01:30:00.000Z", resolveBackground: fakeResolveBackground(), generateText: fakeGenerateText() });
  const firstHash = /object:\/\/sha256\/([0-9a-f]{64})/.exec(first.selected.packRef)[1];

  writeDistributionLedger(dataDir, [
    { effect_key: "k1", job_id: "j1", receipt: { kind: "marketing_native_carousel_distribution", status: "published", pack_sha256: firstHash, published_at: NOW } },
  ]);

  const second = await resolveLarryJaSlot({ env, now: () => "2026-09-28T07:30:00.000Z", slot: "2026-09-28T07:30:00.000Z", resolveBackground: fakeResolveBackground(), generateText: fakeGenerateText() });
  assert.notEqual(second.selected.packRef, first.selected.packRef);

  // Same slot retried immediately (idempotency-per-slot support): with the
  // pool/history unchanged, resolution is deterministic.
  const retry = await resolveLarryJaSlot({ env, now: () => "2026-09-28T07:30:00.000Z", slot: "2026-09-28T07:30:00.000Z", resolveBackground: fakeResolveBackground(), generateText: fakeGenerateText() });
  assert.equal(retry.selected.packRef, second.selected.packRef);
});

test("resolveLarryJaSlot skips content rotation when this integration already published the exact due slot", async (t) => {
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT, GEMINI_API_KEY: "fixture" };
  const slot = "2026-09-28T01:30:00.000Z";
  const slotHash = "604a92d13641f0953e91b185a3b3a72c2c8dad510877a892a99b6b09b03d3611";
  writeDistributionLedger(dataDir, [{
    effect_key: `marketing:carousel:anicca-ios:creative:${"a".repeat(64)}:${"b".repeat(64)}:${"c".repeat(64)}:${slotHash}`,
    job_id: "published-slot-job",
    receipt: {
      kind: "marketing_native_carousel_distribution",
      status: "published",
      integration_ref: EN_SLIDESHOW_TIKTOK_LANE.integrationRef,
      pack_sha256: "a".repeat(64),
      published_at: NOW,
      provider_post_id: "postiz-slot-publication-1",
      provider_reconciled: true,
    },
  }]);
  let generations = 0;
  const result = await resolveLarryJaSlot({
    env,
    now: () => NOW,
    slot,
    lane: EN_SLIDESHOW_TIKTOK_LANE,
    productionSlots: ["09:00", "15:00", "21:00"],
    generateCandidates: async () => {
      generations += 1;
      return [{ packRef: `object://sha256/${"d".repeat(64)}`, familyId: "fresh" }];
    },
  });

  assert.deepEqual(result, {
    slot,
    selected: null,
    alreadyPublished: true,
    providerPostId: "postiz-slot-publication-1",
  });
  assert.equal(generations, 0);
});

test("resolveLarryJaSlot rechecks the slot after generation finishes", async (t) => {
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT, GEMINI_API_KEY: "fixture" };
  const slot = "2026-09-28T01:30:00.000Z";
  const slotHash = "604a92d13641f0953e91b185a3b3a72c2c8dad510877a892a99b6b09b03d3611";
  const generated = { packRef: `object://sha256/${"e".repeat(64)}`, familyId: "fresh" };
  const result = await resolveLarryJaSlot({
    env,
    now: () => NOW,
    slot,
    lane: EN_SLIDESHOW_TIKTOK_LANE,
    productionSlots: ["09:00", "15:00", "21:00"],
    generateCandidates: async () => {
      writeDistributionLedger(dataDir, [{
        effect_key: `marketing:carousel:anicca-ios:creative:${"a".repeat(64)}:${"b".repeat(64)}:${"c".repeat(64)}:${slotHash}`,
        job_id: "concurrent-publisher-slot-job",
        receipt: {
          kind: "marketing_native_carousel_distribution",
          status: "published",
          integration_ref: EN_SLIDESHOW_TIKTOK_LANE.integrationRef,
          pack_sha256: "a".repeat(64),
          published_at: NOW,
          provider_post_id: "postiz-concurrent-slot-1",
          provider_reconciled: true,
        },
      }]);
      return [generated];
    },
  });

  assert.deepEqual(result, {
    slot,
    selected: null,
    alreadyPublished: true,
    providerPostId: "postiz-concurrent-slot-1",
  });
});

test("standalone slide-pack CLI exits safely instead of exporting a pack for an already-published slot", (t) => {
  const dataDir = tempDataDir(t);
  const slot = "2026-09-28T01:30:00.000Z";
  const slotHash = "604a92d13641f0953e91b185a3b3a72c2c8dad510877a892a99b6b09b03d3611";
  writeDistributionLedger(dataDir, [{
    effect_key: `marketing:carousel:anicca-ios:creative:${"a".repeat(64)}:${"b".repeat(64)}:${"c".repeat(64)}:${slotHash}`,
    job_id: "published-cli-slot-job",
    receipt: {
      kind: "marketing_native_carousel_distribution",
      status: "published",
      integration_ref: JA_LANE.integrationRef,
      pack_sha256: "a".repeat(64),
      published_at: NOW,
      provider_reconciled: true,
    },
  }]);
  const script = path.join(__dirname, "generate-larry-slide-pack.js");
  const result = spawnSync(process.execPath, [script, slot], {
    cwd: path.resolve(__dirname, "../../.."),
    env: { ...process.env, LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT },
    encoding: "utf8",
  });

  assert.equal(result.status, 75, result.stderr);
  assert.match(result.stderr, /already published/i);
  assert.equal(result.stdout, "");
});

test("readPostedHistory maps carousel distribution receipts to packRef/postedAt", (t) => {
  const dataDir = tempDataDir(t);
  const hash = crypto.createHash("sha256").update("x").digest("hex");
  const file = path.join(dataDir, "ledger.jsonl");
  const slotHash = "604a92d13641f0953e91b185a3b3a72c2c8dad510877a892a99b6b09b03d3611";
  const integrationRef = "integration://postiz/instagram/cmq3sq7mc000eqp0y7azfm8yk";
  fs.writeFileSync(file, `${JSON.stringify({
    effect_key: `marketing:carousel:anicca-ios:creative:${hash}:${"b".repeat(64)}:${"c".repeat(64)}:${slotHash}`,
      receipt: { kind: "marketing_native_carousel_distribution", status: "published", integration_ref: integrationRef, pack_sha256: hash, published_at: NOW, provider_post_id: "postiz-history-1", provider_reconciled: true },
  })}\n`);
  const history = readPostedHistory(file);
  assert.deepEqual(history, [{
    packRef: `object://sha256/${hash}`,
    postedAt: NOW,
    integrationRef,
    slotHash,
    providerPostId: "postiz-history-1",
  }]);
});

test("MIN_DAYS_BETWEEN_REPEAT is at least a week (per spec: never repeat within N days)", () => {
  assert.ok(MIN_DAYS_BETWEEN_REPEAT >= 7);
});

// Root-cause regression coverage: resolveLarryJaSlot must work for any lane,
// not just JA_LANE -- that parameterization (not a second implementation) is
// what lets anicca-larry-ja-rotating.js stop TikTok "Affirmation Girl" /
// "anicca" / "アニッチャ iOS" / "アニッチャ お笑い" / Instagram "anicca" from
// reposting the same fixed pack.
test("resolveLarryJaSlot generates a fresh, English, TikTok-shaped pool for a non-default lane in its own pool file", { timeout: 60_000 }, async (t) => {
  makeFixtureBackgroundOnce();
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const { slot, selected } = await resolveLarryJaSlot({
    env, now: () => NOW, slot: "2026-09-28T09:00:00.000Z",
    lane: EN_SLIDESHOW_TIKTOK_LANE,
    resolveBackground: fakeResolveBackground(),
    generateText: fakeGenerateText(),
  });
  assert.equal(slot, "2026-09-28T09:00:00.000Z");
  assert.match(selected.packRef, /^object:\/\/sha256\/[0-9a-f]{64}$/);

  const jaPool = poolPath(dataDir, TENANT, JA_LANE.productId, JA_LANE.lane);
  const enPool = poolPath(dataDir, TENANT, EN_SLIDESHOW_TIKTOK_LANE.productId, EN_SLIDESHOW_TIKTOK_LANE.lane);
  assert.notEqual(jaPool, enPool);
  assert.ok(fs.existsSync(enPool));
  assert.equal(fs.existsSync(jaPool), false, "must not touch the JA lane's own pool");

  const pack = JSON.parse(fs.readFileSync(
    path.join(dataDir, "objects", "sha256", selected.packRef.slice(-64)),
    "utf8",
  ));
  assert.equal(pack.platform, "tiktok");
  assert.equal(pack.locale, "en");
  // EN_SLIDESHOW_TIKTOK_LANE has no lastSlideRole override, so the factory's
  // own platform-aware default (tiktok -> "cta") must apply -- this is the
  // exact role the adapter's assertPack expects for this lane at publish time.
  assert.equal(pack.slides.at(-1).role, "cta");
});

test("resolveLarryJaSlot renders slides with the managed LIFE_MANAGER_PYTHON, not PATH python3", { timeout: 60_000 }, async (t) => {
  makeFixtureBackgroundOnce();
  const dataDir = tempDataDir(t);
  const calls = path.join(dataDir, "python-calls.txt");
  const shim = path.join(dataDir, "managed-python");
  // Records every argv then defers to the real interpreter so rendering still succeeds.
  fs.writeFileSync(shim, `#!/bin/sh\nprintf '%s\\n' "$*" >> "${calls}"\nexec python3 "$@"\n`, { mode: 0o700 });
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT, LIFE_MANAGER_PYTHON: shim };
  const { selected } = await resolveLarryJaSlot({ env, now: () => NOW, slot: "2026-09-28T01:30:00.000Z", resolveBackground: fakeResolveBackground(), generateText: fakeGenerateText() });
  assert.ok(selected);
  // Slide text carries a newline, so one argv record spans two lines; the shim
  // being the interpreter that rendered is what matters.
  const invoked = fs.readFileSync(calls, "utf8");
  assert.match(invoked, /render-slide-image\.py/);
});

test("an exhausted pool replenishes once and never selects a recently published pack", async (t) => {
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const candidates = Array.from({ length: 5 }, (_, n) => ({
    packRef: `object://sha256/${String(n).repeat(64)}`, familyId: "fixture", createdAt: NOW,
  }));
  const pool = poolPath(dataDir, TENANT, JA_LANE.productId, JA_LANE.lane);
  fs.mkdirSync(path.dirname(pool), { recursive: true });
  fs.writeFileSync(pool, candidates.map(c => JSON.stringify(c)).join("\n") + "\n");
  writeDistributionLedger(dataDir, candidates.map(c => ({ receipt: {
    pack_sha256: c.packRef.split("/").at(-1), published_at: NOW,
  } })));
  let generated = 0;
  const fresh = { ...candidates[0], packRef: `object://sha256/${"f".repeat(64)}` };
  const options = { env, now: () => NOW, generateText: async () => {},
    generateCandidates: async () => { generated += 1; return [candidates[0], fresh]; } };
  const first = await resolveLarryJaSlot(options);
  assert.equal(first.selected.packRef, fresh.packRef);
  assert.equal(generated, 1);
  assert.equal(fs.readFileSync(pool, "utf8").trim().split("\n").length, 6);
  const retry = await resolveLarryJaSlot(options);
  assert.equal(retry.selected.packRef, fresh.packRef);
  assert.equal(generated, 1, "retry with usable inventory must not incur another generation");
});

test("an exhausted pool stays failed when generation yields no fresh approved candidates", async (t) => {
  const dataDir = tempDataDir(t);
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const candidates = Array.from({ length: 4 }, (_, n) => ({
    packRef: `object://sha256/${String(n).repeat(64)}`, familyId: "fixture", createdAt: NOW,
  }));
  const pool = poolPath(dataDir, TENANT, JA_LANE.productId, JA_LANE.lane);
  fs.mkdirSync(path.dirname(pool), { recursive: true });
  fs.writeFileSync(pool, candidates.map(c => JSON.stringify(c)).join("\n") + "\n");
  writeDistributionLedger(dataDir, candidates.map(c => ({ receipt: {
    pack_sha256: c.packRef.split("/").at(-1), published_at: NOW,
  } })));
  const before = fs.readFileSync(pool, "utf8");
  let generated = 0;
  await assert.rejects(resolveLarryJaSlot({ env, now: () => NOW, generateText: async () => {},
    generateCandidates: async () => { generated += 1; return candidates; },
  }), /no unposted candidate/);
  assert.equal(generated, 1, "exhausted inventory must attempt the existing factory once");
  assert.equal(fs.readFileSync(pool, "utf8"), before);
});

test("selection rereads publication history after the factory finishes", async (t) => {
  const dataDir = tempDataDir(t);
  const old = { packRef: `object://sha256/${"a".repeat(64)}`, familyId: "fixture", createdAt: "2026-09-27T00:00:00.000Z" };
  const fresh = { ...old, packRef: `object://sha256/${"f".repeat(64)}`, createdAt: NOW };
  const pool = poolPath(dataDir, TENANT, JA_LANE.productId, JA_LANE.lane);
  fs.mkdirSync(path.dirname(pool), { recursive: true });
  fs.writeFileSync(pool, JSON.stringify(old) + "\n");
  const result = await resolveLarryJaSlot({
    env: { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT }, now: () => NOW,
    generateText: async () => {}, generateCandidates: async () => {
      writeDistributionLedger(dataDir, [{ receipt: { pack_sha256: "a".repeat(64), published_at: NOW } }]);
      return [fresh];
    },
  });
  assert.equal(result.selected.packRef, fresh.packRef);
});
