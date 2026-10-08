// lib/feature-discovery.js — LM-32 weekly discovery for still-locked context gates.
"use strict";
const { readRuntimePreferences } = require("./runtime-preferences.js");

async function settle(promise, fallback) { try { return await promise; } catch { return fallback; } }

const { DISCOVERY_STRINGS } = require("./i18n.js");
const { sendMessage } = require("./telegram.js");
const { getLiveLocation } = require("./late-notice.js");
const { askPayoutQuestion } = require("./payout-question.js");
const { inspectTelegramLiveLocation } = require("./live-location.js");

const DISCOVERY_WEEK_MS = 7 * 24 * 60 * 60 * 1000;
const GATE_ORDER = Object.freeze(["location", "payout"]);

function hasPayoutDestination(destination) {
  if (!destination) return false;
  if (typeof destination !== "object") return String(destination).trim().length > 0;
  return Object.keys(destination).length > 0;
}

function lockedDiscoveryGates(context = {}, nowMs = Date.now()) {
  const freshLocation = inspectTelegramLiveLocation(context.location, nowMs).fresh;
  return GATE_ORDER.filter((gate) => gate === "location"
    ? !freshLocation
    : !hasPayoutDestination(context.payoutDestination));
}

function isDiscoveryDue(lastDiscoveryAt, nowMs = Date.now()) {
  if (!lastDiscoveryAt) return true;
  const lastMs = Date.parse(lastDiscoveryAt);
  return Number.isFinite(lastMs) && lastMs <= nowMs - DISCOVERY_WEEK_MS;
}

function selectDiscoveryGate(lockedGates, lastGate) {
  const locked = new Set((lockedGates || []).filter((gate) => GATE_ORDER.includes(gate)));
  if (!locked.size) return null;
  const start = GATE_ORDER.includes(lastGate) ? GATE_ORDER.indexOf(lastGate) + 1 : 0;
  for (let offset = 0; offset < GATE_ORDER.length; offset++) {
    const gate = GATE_ORDER[(start + offset) % GATE_ORDER.length];
    if (locked.has(gate)) return gate;
  }
  return null;
}

function discoveryMessage(gate) {
  const strings = DISCOVERY_STRINGS.ja;
  if (gate === "location") return {
    text: strings.location.text,
    extra: { reply_markup: { inline_keyboard: [[
      { text: strings.location.primaryButton, callback_data: "discovery:how:location" },
      { text: strings.location.laterButton, callback_data: "discovery:later:location" },
    ]] } },
  };
  if (gate === "payout") return {
    text: strings.payout.text,
    extra: { reply_markup: { inline_keyboard: [[
      { text: strings.payout.primaryButton, callback_data: "discovery:register:payout" },
      { text: strings.payout.laterButton, callback_data: "discovery:later:payout" },
    ]] } },
  };
  return null;
}

function supaHeaders(key, prefer) {
  return {
    apikey: key,
    Authorization: `Bearer ${key}`,
    "Content-Type": "application/json",
    ...(prefer ? { Prefer: prefer } : {}),
  };
}

async function listDiscoveryUsers(opts = {}) {
  const f = opts.fetchImpl || fetch;
  if (!opts.supaUrl || !opts.supaKey) return [];
  const select = "uid,telegram_chat_id,last_discovery_at,last_discovery_gate,payout_destination";
  const url = `${opts.supaUrl}/rest/v1/lm_users?telegram_chat_id=not.is.null&select=${select}`;
  const response = await settle(f(url, { headers: supaHeaders(opts.supaKey) }), null);
  if (!response || !response.ok) return [];
  const rows = await settle(response.json(), []);
  if (!Array.isArray(rows)) return [];
  return Promise.all(rows.map(async (user) => {
    const prefs = await readRuntimePreferences(user.uid, opts);
    return prefs ? { ...user, ...prefs } : { ...user, notifications_enabled: false, runtime_preferences_failed: true };
  }));
}

async function getDiscoveryUser(uid, opts = {}) {
  const f = opts.fetchImpl || fetch;
  if (!opts.supaUrl || !opts.supaKey || !uid) return null;
  const select = "uid,telegram_chat_id,last_discovery_at,last_discovery_gate,payout_destination";
  const url = `${opts.supaUrl}/rest/v1/lm_users?uid=eq.${encodeURIComponent(uid)}&telegram_chat_id=not.is.null&select=${select}&limit=1`;
  const response = await settle(f(url, { headers: supaHeaders(opts.supaKey) }), null);
  if (!response || !response.ok) return null;
  const rows = await settle(response.json(), []);
  const user = Array.isArray(rows) && rows[0] ? rows[0] : null;
  if (!user) return null;
  const prefs = await readRuntimePreferences(uid, opts);
  return prefs ? { ...user, ...prefs } : { ...user, notifications_enabled: false, runtime_preferences_failed: true };
}

async function saveDiscovery(uid, nowMs, gate, opts = {}) {
  const f = opts.fetchImpl || fetch;
  if (!opts.supaUrl || !opts.supaKey || !uid || !GATE_ORDER.includes(gate)) return false;
  const url = `${opts.supaUrl}/rest/v1/lm_users?uid=eq.${encodeURIComponent(uid)}`;
  const response = await settle(f(url, {
    method: "PATCH",
    headers: supaHeaders(opts.supaKey, "return=minimal"),
    body: JSON.stringify({
      last_discovery_at: new Date(nowMs).toISOString(),
      last_discovery_gate: gate,
    }),
  }), null);
  return Boolean(response && response.ok);
}

async function runDiscoveryForUser(user, nowMs = Date.now(), deps = {}) {
  if (!user || !user.uid || !user.telegram_chat_id) return { sent: false, reason: "unreachable" };
  if (user.notifications_enabled === false) return { sent: false, reason: user.runtime_preferences_failed ? "preferences_unavailable" : "notifications_disabled" };
  if (!isDiscoveryDue(user.last_discovery_at, nowMs)) return { sent: false, reason: "throttled" };

  const dbOpts = {
    supaUrl: deps.supaUrl,
    supaKey: deps.supaKey,
    fetchImpl: deps.fetchImpl,
  };
  const location = await (deps.getLiveLocation || getLiveLocation)(user.uid, nowMs, dbOpts);
  const locked = lockedDiscoveryGates({
    location,
    payoutDestination: user.payout_destination,
  }, nowMs);
  const gate = selectDiscoveryGate(locked, user.last_discovery_gate);
  if (!gate) return { sent: false, reason: "all_unlocked" };

  const message = discoveryMessage(gate);
  const result = await (deps.sendMessage || sendMessage)(
    deps.token,
    user.telegram_chat_id,
    message.text,
    message.extra,
  );
  if (!result || !result.ok) return { sent: false, reason: "telegram_failed", gate };

  const persisted = await (deps.saveDiscovery || ((uid, at, sentGate) =>
    saveDiscovery(uid, at, sentGate, dbOpts)))(user.uid, nowMs, gate);
  if (!persisted) throw new Error(`discovery state save failed uid=${String(user.uid).slice(0, 12)}`);
  return { sent: true, gate };
}

async function runDiscoveryForUid(uid, nowMs = Date.now(), deps = {}) {
  const user = await (deps.getDiscoveryUser || getDiscoveryUser)(uid, deps);
  if (!user) return { sent: false, reason: "user_not_found" };
  return runDiscoveryForUser(user, nowMs, deps);
}

async function handleDiscoveryCallback(data, deps = {}) {
  const match = /^discovery:(how|later|register):(location|payout)$/.exec(String(data || ""));
  if (!match) return { ignored: true };
  const [, action, gate] = match;
  if (action === "how" && gate === "location") {
    await (deps.sendMessage || sendMessage)(
      deps.token,
      deps.chatId,
      DISCOVERY_STRINGS.ja.locationHowTo,
    );
  }
  // FIN-b: "register" used to fall through to a bare acknowledgement, which is why the payout gate
  // could never be unlocked from Telegram. It now opens the §9.11 closed question — asked once ever,
  // because askPayoutQuestion reads lm_users.payout_destination before it sends anything.
  if (action === "register" && gate === "payout") {
    const ask = deps.askPayoutQuestion || askPayoutQuestion;
    const outcome = await ask(deps);
    return { handled: true, action, gate, asked: Boolean(outcome && outcome.asked), ...(outcome && outcome.reason ? { reason: outcome.reason } : {}) };
  }
  // "later" deliberately does not mutate last_discovery_at: the original discovery send already
  // set the seven-day throttle.
  return { handled: true, action, gate };
}

module.exports = {
  DISCOVERY_WEEK_MS,
  GATE_ORDER,
  lockedDiscoveryGates,
  isDiscoveryDue,
  selectDiscoveryGate,
  discoveryMessage,
  listDiscoveryUsers,
  getDiscoveryUser,
  saveDiscovery,
  runDiscoveryForUser,
  runDiscoveryForUid,
  handleDiscoveryCallback,
};
