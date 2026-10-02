"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { createSupabaseGeocodeStore, normalizeGeocodeAddress } = require("./geocode-cache.js");

test("geocode identity normalizes unicode and whitespace", () => {
  assert.equal(normalizeGeocodeAddress("  東京都　渋谷区 1 丁目  "), "東京都 渋谷区 1 丁目");
  assert.equal(normalizeGeocodeAddress(""), "");
});

test("Supabase geocode store persists by hashed address identity across instances", async () => {
  const rows = new Map();
  const calls = [];
  const fetchImpl = async (url, options = {}) => {
    calls.push([String(url), options]);
    if (options.method === "POST") {
      const body = JSON.parse(options.body); rows.set(body.address_key, body);
      return { ok: true, status: 201 };
    }
    const key = decodeURIComponent(new URL(url).searchParams.get("address_key").replace("eq.", ""));
    const row = rows.get(key);
    return { ok: true, status: 200, json: async () => (row ? [row] : []) };
  };
  const first = createSupabaseGeocodeStore({ supaUrl: "https://db.example", supaKey: "service", fetchImpl });
  assert.equal(await first.put("東京都 渋谷区", { lat: 35.6, lon: 139.7, provider: "google", ttlMs: 86_400_000 }), true);
  const second = createSupabaseGeocodeStore({ supaUrl: "https://db.example", supaKey: "service", fetchImpl });
  assert.deepEqual(await second.get("東京都 渋谷区"), { lat: 35.6, lon: 139.7, provider: "google" });
  assert.equal(calls.some(([, options]) => String(options.body || "").includes("東京都")), false);
});

test("expired geocode cache rows are misses", async () => {
  const old = new Date(Date.now() - 90_000).toISOString();
  const fetchImpl = async () => ({ ok: true, status: 200, json: async () => [{
    address_key: "hash", lat: 35.6, lon: 139.7, provider: "openpoi", computed_at: old, ttl_secs: 60,
  }] });
  const store = createSupabaseGeocodeStore({ supaUrl: "https://db.example", supaKey: "service", fetchImpl });
  assert.equal(await store.get("address"), null);
});

test("geocode cache migration stores only hashed identity and bounded status", () => {
  const sql = fs.readFileSync(path.join(__dirname, "../migrations/2026-10-02-lm-geocode-cache.sql"), "utf8");
  assert.match(sql, /CREATE TABLE IF NOT EXISTS public\.lm_geocode_cache/i);
  assert.match(sql, /address_key text PRIMARY KEY/i);
  assert.match(sql, /status IN \('success', 'negative'\)/i);
  assert.doesNotMatch(sql, /address text/i);
});
