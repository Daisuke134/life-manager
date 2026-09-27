"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { JA_LANE } = require("../lib/marketing-native-carousel-publication-adapter.js");
const {
  MIN_DAYS_BETWEEN_REPEAT,
  poolPath,
  readPostedHistory,
  resolveLarryJaSlot,
} = require("./generate-larry-slide-pack.js");

const TENANT = "dais-local";
const NOW = "2026-09-28T01:30:00.000Z";

function tempDataDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "larry-slide-pack-scheduler-"));
}

function writeDistributionLedger(dataDir, rows) {
  const file = path.join(dataDir, "tenants", encodeURIComponent(TENANT), "marketing", "native-carousel-publication", JA_LANE.productId, "distribution.jsonl");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, rows.map((r) => `${JSON.stringify(r)}\n`).join(""));
}

test("resolveLarryJaSlot generates a pool from empty and returns a candidate", { timeout: 60_000 }, () => {
  const dataDir = tempDataDir();
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const { slot, selected } = resolveLarryJaSlot({ env, now: () => NOW, slot: "2026-09-28T01:30:00.000Z" });
  assert.equal(slot, "2026-09-28T01:30:00.000Z");
  assert.match(selected.packRef, /^object:\/\/sha256\/[0-9a-f]{64}$/);
  assert.equal(selected.mediaRefs.length, 6);

  const pool = poolPath(dataDir, TENANT, JA_LANE.productId, JA_LANE.lane);
  assert.ok(fs.existsSync(pool));
});

test("resolveLarryJaSlot does not regenerate once the pool already has enough candidates", { timeout: 60_000 }, () => {
  const dataDir = tempDataDir();
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  resolveLarryJaSlot({ env, now: () => NOW, slot: "2026-09-28T01:30:00.000Z" });
  const pool = poolPath(dataDir, TENANT, JA_LANE.productId, JA_LANE.lane);
  const before = fs.readFileSync(pool, "utf8");
  resolveLarryJaSlot({ env, now: () => NOW, slot: "2026-09-28T07:30:00.000Z" });
  const after = fs.readFileSync(pool, "utf8");
  assert.equal(before, after, "pool should not grow once above MIN_POOL_SIZE");
});

test("resolveLarryJaSlot never repeats a pack posted within MIN_DAYS_BETWEEN_REPEAT and is idempotent per slot", { timeout: 60_000 }, () => {
  const dataDir = tempDataDir();
  const env = { LM_DATA_DIR: dataDir, LM_RUNTIME_TENANT_ID: TENANT };
  const first = resolveLarryJaSlot({ env, now: () => NOW, slot: "2026-09-28T01:30:00.000Z" });
  const firstHash = /object:\/\/sha256\/([0-9a-f]{64})/.exec(first.selected.packRef)[1];

  writeDistributionLedger(dataDir, [
    { effect_key: "k1", job_id: "j1", receipt: { kind: "marketing_native_carousel_distribution", status: "published", pack_sha256: firstHash, published_at: NOW } },
  ]);

  const second = resolveLarryJaSlot({ env, now: () => "2026-09-28T07:30:00.000Z", slot: "2026-09-28T07:30:00.000Z" });
  assert.notEqual(second.selected.packRef, first.selected.packRef);

  // Same slot retried immediately (idempotency-per-slot support): with the
  // pool/history unchanged, resolution is deterministic.
  const retry = resolveLarryJaSlot({ env, now: () => "2026-09-28T07:30:00.000Z", slot: "2026-09-28T07:30:00.000Z" });
  assert.equal(retry.selected.packRef, second.selected.packRef);
});

test("readPostedHistory maps carousel distribution receipts to packRef/postedAt", () => {
  const dataDir = tempDataDir();
  const hash = crypto.createHash("sha256").update("x").digest("hex");
  const file = path.join(dataDir, "ledger.jsonl");
  fs.writeFileSync(file, `${JSON.stringify({ receipt: { kind: "marketing_native_carousel_distribution", status: "published", pack_sha256: hash, published_at: NOW } })}\n`);
  const history = readPostedHistory(file);
  assert.deepEqual(history, [{ packRef: `object://sha256/${hash}`, postedAt: NOW }]);
});

test("MIN_DAYS_BETWEEN_REPEAT is at least a week (per spec: never repeat within N days)", () => {
  assert.ok(MIN_DAYS_BETWEEN_REPEAT >= 7);
});
