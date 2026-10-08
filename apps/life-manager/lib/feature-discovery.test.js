"use strict";

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const {
  DISCOVERY_WEEK_MS,
  lockedDiscoveryGates,
  isDiscoveryDue,
  selectDiscoveryGate,
  discoveryMessage,
  runDiscoveryForUser,
  handleDiscoveryCallback,
} = require("./feature-discovery.js");
const { DISCOVERY_STRINGS } = require("./i18n.js");
const { routeCallbackData } = require("./telegram.js");

const NOW = Date.parse("2026-07-21T00:00:00.000Z");

test("LM-32: location and payout gates distinguish missing, expired, fresh, and registered states", () => {
  assert.deepEqual(lockedDiscoveryGates({ location: null, payoutDestination: null }, NOW), ["location", "payout"]);
  assert.deepEqual(lockedDiscoveryGates({
    location: { latitude: 35, longitude: 139, observed_at: new Date(NOW - 1000).toISOString(), expires_at: new Date(NOW).toISOString() },
    payoutDestination: null,
  }, NOW), ["location", "payout"], "expiry at now is closed");
  assert.deepEqual(lockedDiscoveryGates({
    location: { latitude: 35, longitude: 139, observed_at: new Date(NOW - 1000).toISOString(), expires_at: new Date(NOW + 1).toISOString() },
    payoutDestination: { type: "wallet", address: "0xtest" },
  }, NOW), [], "fresh location and any persisted payout destination are unlocked");
  assert.deepEqual(lockedDiscoveryGates({
    location: { latitude: 35, longitude: 139, observed_at: new Date(NOW - 120_001).toISOString(), expires_at: new Date(NOW + 60_000).toISOString() },
    payoutDestination: null,
  }, NOW), ["location", "payout"], "an unexpired but stale location stays locked");
});

test("LM-32: seven-day throttle includes the exact boundary and rejects future timestamps", () => {
  assert.equal(DISCOVERY_WEEK_MS, 7 * 24 * 60 * 60 * 1000);
  assert.equal(isDiscoveryDue(null, NOW), true);
  assert.equal(isDiscoveryDue(new Date(NOW - DISCOVERY_WEEK_MS).toISOString(), NOW), true);
  assert.equal(isDiscoveryDue(new Date(NOW - DISCOVERY_WEEK_MS + 1).toISOString(), NOW), false);
  assert.equal(isDiscoveryDue(new Date(NOW + 1).toISOString(), NOW), false);
});

test("LM-32: multiple locked gates rotate while unlocked gates are never selected", () => {
  assert.equal(selectDiscoveryGate(["location", "payout"], null), "location");
  assert.equal(selectDiscoveryGate(["location", "payout"], "location"), "payout");
  assert.equal(selectDiscoveryGate(["location", "payout"], "payout"), "location");
  assert.equal(selectDiscoveryGate(["payout"], "location"), "payout");
  assert.equal(selectDiscoveryGate([], "payout"), null);
});

test("LM-32: discovery copy comes verbatim from the i18n table with one gate per message", () => {
  assert.deepEqual(discoveryMessage("location"), {
    text: DISCOVERY_STRINGS.ja.location.text,
    extra: { reply_markup: { inline_keyboard: [[
      { text: DISCOVERY_STRINGS.ja.location.primaryButton, callback_data: "discovery:how:location" },
      { text: DISCOVERY_STRINGS.ja.location.laterButton, callback_data: "discovery:later:location" },
    ]] } },
  });
  assert.deepEqual(discoveryMessage("payout"), {
    text: DISCOVERY_STRINGS.ja.payout.text,
    extra: { reply_markup: { inline_keyboard: [[
      { text: DISCOVERY_STRINGS.ja.payout.primaryButton, callback_data: "discovery:register:payout" },
      { text: DISCOVERY_STRINGS.ja.payout.laterButton, callback_data: "discovery:later:payout" },
    ]] } },
  });
  assert.equal(discoveryMessage("unknown"), null);

  const spec = fs.readFileSync(path.join(__dirname,
    "../../../docs/superpowers/specs/2026-07-19-anicca-one-repo-consolidation-spec.md"), "utf8");
  for (const gate of ["location", "payout"]) {
    const copy = DISCOVERY_STRINGS.ja[gate].text.replace(/\n/g, "\\n");
    assert.ok(spec.includes(`「${copy}」`), `${gate} i18n copy must remain verbatim from spec §9.11`);
  }
});

test("LM-32: user run sends one due locked gate and persists only after Telegram accepts it", async () => {
  const sent = [], saved = [];
  const user = { uid: "u1", telegram_chat_id: "7", last_discovery_at: null, last_discovery_gate: null, payout_destination: null };
  const result = await runDiscoveryForUser(user, NOW, {
    token: "t",
    getLiveLocation: async () => null,
    sendMessage: async (...args) => { sent.push(args); return { ok: true }; },
    saveDiscovery: async (...args) => { saved.push(args); return true; },
  });
  assert.deepEqual(result, { sent: true, gate: "location" });
  assert.equal(sent.length, 1);
  assert.equal(sent[0][1], "7");
  assert.equal(sent[0][2], DISCOVERY_STRINGS.ja.location.text);
  assert.deepEqual(saved, [["u1", NOW, "location"]]);

  const unlocked = await runDiscoveryForUser({ ...user, payout_destination: { type: "wallet" } }, NOW, {
    token: "t",
    getLiveLocation: async () => ({
      latitude: 35, longitude: 139,
      observed_at: new Date(NOW - 1000).toISOString(), expires_at: new Date(NOW + 60_000).toISOString(),
    }),
    sendMessage: async () => { throw new Error("unlocked gates must never send"); },
    saveDiscovery: async () => { throw new Error("unlocked gates must never persist"); },
  });
  assert.deepEqual(unlocked, { sent: false, reason: "all_unlocked" });
});

test("LM-32: failed Telegram send does not burn the weekly throttle", async () => {
  let saves = 0;
  const result = await runDiscoveryForUser({
    uid: "u1", telegram_chat_id: "7", last_discovery_at: null,
    last_discovery_gate: "location", payout_destination: null,
  }, NOW, {
    token: "t",
    getLiveLocation: async () => null,
    sendMessage: async () => ({ ok: false, description: "rejected" }),
    saveDiscovery: async () => { saves++; return true; },
  });
  assert.deepEqual(result, { sent: false, reason: "telegram_failed", gate: "payout" });
  assert.equal(saves, 0);
});

test("LM-32: a user inside the seven-day window performs no gate lookup or send", async () => {
  const result = await runDiscoveryForUser({
    uid: "u1", telegram_chat_id: "7",
    last_discovery_at: new Date(NOW - DISCOVERY_WEEK_MS + 1).toISOString(),
    last_discovery_gate: "location", payout_destination: null,
  }, NOW, {
    getLiveLocation: async () => { throw new Error("throttled users must not query gates"); },
    sendMessage: async () => { throw new Error("throttled users must never send"); },
  });
  assert.deepEqual(result, { sent: false, reason: "throttled" });
});

test("LM-32: discovery callbacks reuse the router; how-to replies and later stays silent", async () => {
  const calls = [];
  const discovery = (data) => handleDiscoveryCallback(data, {
    token: "t", chatId: "7",
    sendMessage: async (...args) => { calls.push(args); return { ok: true }; },
  });
  assert.deepEqual(await routeCallbackData("discovery:how:location", { discovery }), { handled: true, action: "how", gate: "location" });
  assert.equal(calls[0][2], DISCOVERY_STRINGS.ja.locationHowTo);
  assert.deepEqual(await routeCallbackData("discovery:later:location", { discovery }), { handled: true, action: "later", gate: "location" });
  assert.equal(calls.length, 1, "later does not send another message and remains eligible next week");
});

test("LM-32: migration is additive and the E2E hook targets one user", () => {
  const migration = fs.readFileSync(path.join(__dirname, "../migrations/2026-07-21-lm32-feature-discovery.sql"), "utf8");
  assert.match(migration, /ADD COLUMN IF NOT EXISTS last_discovery_at timestamptz/i);
  assert.match(migration, /ADD COLUMN IF NOT EXISTS last_discovery_gate text/i);
  assert.match(migration, /ADD COLUMN IF NOT EXISTS payout_destination jsonb/i);
  const hook = fs.readFileSync(path.join(__dirname, "../scripts/send-feature-discovery.js"), "utf8");
  assert.match(hook, /runDiscoveryForUid/);
  assert.doesNotMatch(hook, /force/i, "the hook must respect unlocked gates and the weekly throttle");
});
