"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const { test } = require("node:test");
process.env.LM_CALL_SECRET = "unit_secret";

test("scheduler helper-skip and signed streamUrl contract", () => {
  const { isHelperBlock, buildStreamUrl } = require("../scheduler.js");
  assert.strictEqual(isHelperBlock("[Travel] [APPLIED] x"), true);
  assert.strictEqual(isHelperBlock("🎤 [PENDING] y"), true);
  assert.strictEqual(isHelperBlock("Dentist"), false);
  process.env.PUBLIC_WSS = "wss://life-call.up.railway.app";
  const u = buildStreamUrl({ summary: "Dentist & Co", startIso: "2026-06-18T20:40:00+09:00", location: "Tokyo" }, "firm");
  const p = new URL(u);
  assert.strictEqual(p.pathname, "/ws");
  assert.ok(p.searchParams.get("sig"), "must carry an HMAC sig");
  assert.strictEqual(p.searchParams.get("urgency"), "firm");
});

test("voice allowance context is signed and tampering is rejected by the bridge", () => {
  const { buildStreamUrl } = require("../scheduler.js");
  const { ctxFromReq } = require("../server.js");
  process.env.PUBLIC_WSS = "wss://life-call.up.railway.app";
  const url = new URL(buildStreamUrl({ summary: "Dentist", startIso: "2026-06-18T20:40:00+09:00",
    location: "Tokyo", wakeUid: "tenant-a", wakeEventKey: "call-a", voicePeriodStart: "2026-09-01",
    voiceReservationToken: "11111111-1111-4111-8111-111111111111", voiceAllowedSeconds: 37 }, "firm"));
  assert.deepEqual(ctxFromReq({ url: `${url.pathname}${url.search}` }).voiceReservation, {
    periodStart: "2026-09-01", reservationToken: "11111111-1111-4111-8111-111111111111", allowedSeconds: 37,
  });
  url.searchParams.set("voiceAllowedSeconds", "38");
  assert.equal(ctxFromReq({ url: `${url.pathname}${url.search}` }), null);
});

test("late tick scheduler surface has no mail sender dependency", () => {
  const source = fs.readFileSync(path.join(__dirname, "../scheduler.js"), "utf8");
  assert.doesNotMatch(source, /require\(["']\.\/lib\/notify\.js["']\)/);
  const start = source.indexOf("async function lateNoticeUserOnce");
  const end = source.indexOf("\n// ── Per-user single-invocation functions", start);
  assert.ok(start >= 0 && end > start, "lateNoticeUserOnce source boundary must remain discoverable");
  const lateTickSource = source.slice(start, end);
  assert.doesNotMatch(lateTickSource, /sendLateNotice|noticeOpts|RESEND_API_KEY/);
});

test("Web-only location questions have no email fallback", () => {
  const { questionChannelForUser } = require("../scheduler.js");
  assert.equal(typeof questionChannelForUser, "function");
  assert.equal(questionChannelForUser({
    uid: "lm_11111111-1111-4111-8111-111111111111",
    telegram_chat_id: null,
    email: "calendar-owner@example.test",
  }), null);
  assert.equal(questionChannelForUser({ uid: "legacy-user", telegram_chat_id: "123", email: "user@example.test" }), "telegram");
  assert.equal(questionChannelForUser({ uid: "legacy-user", telegram_chat_id: null, email: "user@example.test" }), "email");
});

test("a Web-only tenant with an explicitly linked Telegram sender uses Telegram instead of email", () => {
  const { questionChannelForUser } = require("../scheduler.js");
  assert.equal(questionChannelForUser({
    uid: "lm_11111111-1111-4111-8111-111111111111",
    telegram_chat_id: null,
    web_message_telegram_chat_id: "123456789",
    email: "calendar-owner@example.test",
  }), "telegram");
});

test("Web linked Telegram ask uses the bound chat and never substitutes Google email for Gmail access", async () => {
  const { askUserOnce } = require("../scheduler.js");
  const calls = [];
  await askUserOnce({
    uid: "lm_11111111-1111-4111-8111-111111111111",
    telegram_chat_id: null,
    web_message_telegram_chat_id: "123456789",
    email: "calendar-owner@example.test",
    gmail_account_id: null,
  }, {
    askTickImpl: async (uid, options) => { calls.push({ uid, options }); return { asked: 1 }; },
    composioKey: "fixture-composio",
    resendKey: "fixture-resend",
    mapsKey: "fixture-maps",
    geminiKey: "fixture-gemini",
    supaUrl: "https://fixture.supabase.co",
    supaKey: "fixture-service-role",
    telegramToken: "fixture-telegram-token",
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].uid, "lm_11111111-1111-4111-8111-111111111111");
  assert.equal(calls[0].options.telegramChatId, "123456789");
  assert.equal(calls[0].options.userEmail, null);
  assert.equal(calls[0].options.gmailAccountId, null);
});

test("scheduler projects the Web Telegram sender from the separate identity registry", async () => {
  const { supaUsers } = require("../scheduler.js");
  assert.equal(typeof supaUsers, "function", "the scheduler user projection must be testable");
  const before = { url: process.env.SUPABASE_URL, key: process.env.SUPABASE_SERVICE_ROLE_KEY };
  const originalFetch = global.fetch;
  const uid = "lm_11111111-1111-4111-8111-111111111111";
  const calls = [];
  process.env.SUPABASE_URL = "https://fixture.supabase.co";
  process.env.SUPABASE_SERVICE_ROLE_KEY = "fixture-service-role";
  global.fetch = async (input) => {
    const url = new URL(String(input));
    calls.push(url);
    if (url.pathname === "/rest/v1/lm_users") {
      return { ok: true, async json() { return [{ uid, telegram_chat_id: null, email: "calendar-owner@example.test", gmail_account_id: null }]; } };
    }
    if (url.pathname === "/rest/v1/lm_panel_preferences") {
      return { ok: true, async json() { return [{ uid, notifications_enabled: true, daily_automation_enabled: true }]; } };
    }
    if (url.pathname === "/rest/v1/lm_message_channels") {
      return { ok: true, async json() { return [
        { uid, sender_id: "123456789", owner_kind: "web_link" },
        { uid: "legacy-user", sender_id: "987654321", owner_kind: "legacy" },
      ]; } };
    }
    throw new Error(`unexpected scheduler query ${url.pathname}`);
  };
  try {
    const users = await supaUsers();
    assert.equal(users.length, 1);
    assert.equal(users[0].uid, uid);
    assert.equal(users[0].telegram_chat_id, null);
    assert.equal(users[0].web_message_telegram_chat_id, "123456789");
    assert.equal(users[0].gmail_account_id, null);
    assert.equal(calls.length, 3);
  } finally {
    global.fetch = originalFetch;
    if (before.url === undefined) delete process.env.SUPABASE_URL; else process.env.SUPABASE_URL = before.url;
    if (before.key === undefined) delete process.env.SUPABASE_SERVICE_ROLE_KEY; else process.env.SUPABASE_SERVICE_ROLE_KEY = before.key;
  }
});

test("Inngest user reload includes the linked Web Telegram route", async () => {
  const { getUserByUid } = require("../scheduler.js");
  const before = { url: process.env.SUPABASE_URL, key: process.env.SUPABASE_SERVICE_ROLE_KEY };
  const originalFetch = global.fetch;
  const uid = "lm_22222222-2222-4222-8222-222222222222";
  process.env.SUPABASE_URL = "https://fixture.supabase.co";
  process.env.SUPABASE_SERVICE_ROLE_KEY = "fixture-service-role";
  global.fetch = async (input) => {
    const url = new URL(String(input));
    if (url.pathname === "/rest/v1/lm_users") {
      if (url.searchParams.get("select")?.includes("calendar_enable_pending")) {
        return { ok: true, async json() { return [{
          uid, telegram_chat_id: null, calendar_provider: "composio_gcal",
          calendar_connected_account_id: "cal_abc123", calendar_enable_pending: false,
          calendar_enable_claim_id: null, calendar_enable_claimed_at: null,
          web_initial_scan_completed_at: "2030-01-01T00:00:00Z", web_first_travel_at: "2030-01-01T00:00:00Z",
          stripe_subscription_id: "sub_test", trial_expires_at: "2030-01-08T00:00:00Z",
          plan_status: "trialing", paid: false, web_trial_payment_method_present: true,
          web_billing_cancel_at_period_end: false,
        }]; } };
      }
      return { ok: true, async json() { return [{
        uid, name: "Web user", phone: null, paid: false, plan_status: "trialing",
        trial_expires_at: "2030-01-08T00:00:00Z", web_trial_payment_method_present: true,
        web_first_travel_at: "2030-01-01T00:00:00Z", calendar_provider: "composio_gcal",
        home_address: null, gmail_account_id: null, email: "calendar-owner@example.test",
        telegram_chat_id: null, call_language: "ja", wake_policy: null,
      }]; } };
    }
    if (url.pathname === "/rest/v1/lm_panel_preferences") {
      return { ok: true, async json() { return [{ daily_automation_enabled: true, calendar_disconnect_pending: false }]; } };
    }
    if (url.pathname === "/rest/v1/lm_message_channels") {
      return { ok: true, async json() { return [{ uid, sender_id: "123456789", owner_kind: "web_link" }]; } };
    }
    throw new Error(`unexpected Inngest user reload ${url.pathname}`);
  };
  try {
    const user = await getUserByUid(uid);
    assert.equal(user.uid, uid);
    assert.equal(user.telegram_chat_id, null);
    assert.equal(user.web_message_telegram_chat_id, "123456789");
    assert.equal(user.gmail_account_id, null);
    assert.equal(user.email, "calendar-owner@example.test");
  } finally {
    global.fetch = originalFetch;
    if (before.url === undefined) delete process.env.SUPABASE_URL; else process.env.SUPABASE_URL = before.url;
    if (before.key === undefined) delete process.env.SUPABASE_SERVICE_ROLE_KEY; else process.env.SUPABASE_SERVICE_ROLE_KEY = before.key;
  }
});

test("Web-only ask loop performs no Calendar or email request without a linked message channel", async () => {
  const { askUserOnce } = require("../scheduler.js");
  const before = Object.fromEntries([
    "COMPOSIO_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "GEMINI_API_KEY", "LIFE_MAPS_KEY", "RESEND_API_KEY",
  ].map((key) => [key, process.env[key]]));
  const originalFetch = global.fetch;
  const calls = [];
  Object.assign(process.env, {
    COMPOSIO_API_KEY: "fixture-composio",
    SUPABASE_URL: "https://supabase.example",
    SUPABASE_SERVICE_ROLE_KEY: "fixture-service-role",
    GEMINI_API_KEY: "fixture-gemini",
    LIFE_MAPS_KEY: "fixture-maps",
    RESEND_API_KEY: "fixture-resend",
  });
  global.fetch = async (url) => {
    calls.push(String(url));
    return { ok: true, status: 200, json: async () => [] };
  };
  try {
    await askUserOnce({
      uid: "lm_11111111-1111-4111-8111-111111111111",
      telegram_chat_id: null,
      email: "calendar-owner@example.test",
      daily_automation_enabled: true,
      notifications_enabled: true,
    });
    assert.deepEqual(calls, []);
  } finally {
    global.fetch = originalFetch;
    for (const [key, value] of Object.entries(before)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
});

test("Web travel skips Calendar work unless the persisted account is currently ACTIVE", async () => {
  const { travelUserOnce } = require("../scheduler.js");
  const uid = "lm_11111111-1111-4111-8111-111111111111";
  for (const [accountState, accountId] of [["inactive", "ca-disabled"], ["rebound", "ca-replaced"]]) {
    let guardCalls = 0, calendarReads = 0;
    await travelUserOnce({ uid, telegram_chat_id: null, calendar_connected_account_id: accountId, daily_automation_enabled: true,
      web_first_travel_at: "2030-01-01T00:00:00.000Z", paid: true, plan_status: "active" }, {
      apiKey: "provider-key",
      mapsKey: "maps-key",
      resolveActiveWebCalendarImpl: async (verifiedUid) => {
        guardCalls++;
        assert.equal(verifiedUid, uid);
        return null;
      },
      fillTravel: async () => { calendarReads++; return { inserted: 0, outboundReports: [] }; },
    });
    assert.equal(guardCalls, 1, `${accountState} account must be checked`);
    assert.equal(calendarReads, 0, `${accountState} account must not read Calendar`);
  }
});

test("Web travel proceeds after the persisted exact account passes the ACTIVE gate", async () => {
  const { travelUserOnce } = require("../scheduler.js");
  const calendarExpectedIds = [];
  await travelUserOnce({ uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null, daily_automation_enabled: true,
    web_first_travel_at: "2030-01-01T00:00:00.000Z", paid: true, plan_status: "active" }, {
    apiKey: "provider-key",
    mapsKey: "maps-key",
    resolveActiveWebCalendarImpl: async () => ({ accountId: "ca-selected" }),
    readWebTravelControlStateImpl: async () => ({ dailyAutomationEnabled: true, billingEntitled: true, disconnectPending: false, enablePending: false }),
    fillTravel: async (_uid, options) => { calendarExpectedIds.push(options.expectedCalendarAccountId); return { inserted: 0, outboundReports: [] }; },
  });
  assert.deepEqual(calendarExpectedIds, ["ca-selected"]);
});

test("one-shot Web scan passes its narrow Calendar write allowance through travel", async () => {
  const { travelUserOnce } = require("../scheduler.js");
  let calendarOptions;
  await travelUserOnce({ uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null,
    daily_automation_enabled: false, web_initial_scan_completed_at: null,
    stripe_subscription_id: null, paid: false }, {
    initialScan: true,
    apiKey: "provider-key",
    mapsKey: "maps-key",
    resolveActiveWebCalendarImpl: async () => ({ accountId: "ca-selected" }),
    readWebTravelControlStateImpl: async () => ({ dailyAutomationEnabled: false,
      disconnectPending: false, enablePending: false, initialScanAllowed: true }),
    fillTravel: async (_uid, options) => {
      calendarOptions = options;
      return { inserted: 0, outboundReports: [] };
    },
  });

  assert.equal(calendarOptions.expectedCalendarAccountId, "ca-selected");
  assert.equal(calendarOptions.allowWebInitialScan, true);
});

test("Web scheduler rechecks billing after ACTIVE lookup before Calendar reads", async () => {
  const { travelUserOnce } = require("../scheduler.js");
  let calendarCalls = 0;
  await travelUserOnce({ uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null,
    daily_automation_enabled: true, web_first_travel_at: "2030-01-01T00:00:00.000Z",
    paid: true, plan_status: "active" }, {
    apiKey: "provider-key", mapsKey: "maps-key",
    resolveActiveWebCalendarImpl: async () => ({ accountId: "ca-selected" }),
    readWebTravelControlStateImpl: async () => ({ dailyAutomationEnabled: true, billingEntitled: false,
      disconnectPending: false, enablePending: false }),
    fillTravel: async () => { calendarCalls++; return { inserted: 0, outboundReports: [] }; },
  });
  assert.equal(calendarCalls, 0);
});

test("Web unpaid, past-due, and expired-trial tenants stop before Calendar reads", async () => {
  const { travelUserOnce } = require("../scheduler.js");
  const uid = "lm_11111111-1111-4111-8111-111111111111";
  const nowMs = Date.parse("2030-01-01T00:00:00.000Z");
  for (const state of [
    { paid: false, plan_status: "canceled", trial_expires_at: null },
    { paid: false, plan_status: "past_due", trial_expires_at: null },
    { paid: false, plan_status: "trialing", trial_expires_at: "2029-12-31T23:59:59.000Z",
      web_trial_payment_method_present: true },
  ]) {
    let calendarReads = 0;
    await travelUserOnce({ uid, telegram_chat_id: null, daily_automation_enabled: true,
      web_first_travel_at: "2029-12-01T00:00:00.000Z", ...state }, {
      apiKey: "provider-key", mapsKey: "maps-key", nowMs,
      resolveActiveWebCalendarImpl: async () => { calendarReads++; return { accountId: "ca-selected" }; },
      readWebTravelControlStateImpl: async () => ({ dailyAutomationEnabled: true, billingEntitled: true, disconnectPending: false, enablePending: false }),
      fillTravel: async () => { calendarReads++; return { inserted: 0, outboundReports: [] }; },
    });
    assert.equal(calendarReads, 0, `${state.plan_status} must be gated before provider reads`);
  }
});

test("current card-backed Web trial remains eligible until trial_expires_at", async () => {
  const { travelUserOnce } = require("../scheduler.js");
  const calendarExpectedIds = [];
  await travelUserOnce({
    uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null,
    daily_automation_enabled: true, paid: false, plan_status: "trialing", web_trial_payment_method_present: true,
    trial_expires_at: "2030-01-02T00:00:00.000Z",
  }, {
    apiKey: "provider-key", mapsKey: "maps-key", nowMs: Date.parse("2030-01-01T00:00:00.000Z"),
    resolveActiveWebCalendarImpl: async () => ({ accountId: "ca-selected" }),
    readWebTravelControlStateImpl: async () => ({ dailyAutomationEnabled: true, billingEntitled: true, disconnectPending: false, enablePending: false }),
    fillTravel: async (_uid, options) => { calendarExpectedIds.push(options.expectedCalendarAccountId); return { inserted: 0, outboundReports: [] }; },
  });
  assert.deepEqual(calendarExpectedIds, ["ca-selected"]);
});

test("Inngest user reload includes the Web billing expiry fields used by travel entitlement", async () => {
  const scheduler = require("../scheduler.js");
  const names = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"];
  const before = Object.fromEntries(names.map((name) => [name, process.env[name]]));
  const originalFetch = global.fetch;
  const urls = [];
  process.env.SUPABASE_URL = "https://supabase.example";
  process.env.SUPABASE_SERVICE_ROLE_KEY = "service-role-fixture";
  global.fetch = async (input) => {
    const url = new URL(String(input));
    urls.push(url);
    if (url.pathname.endsWith("/lm_users")) return { ok: true, json: async () => [{
      uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null,
      web_first_travel_at: "2030-01-01T00:00:00.000Z", paid: false, plan_status: "trialing",
      web_trial_payment_method_present: true,
      trial_expires_at: "2030-01-08T00:00:00.000Z", calendar_provider: "composio_gcal",
    }] };
    if (url.pathname.endsWith("/lm_panel_preferences")) return { ok: true, json: async () => [{
      uid: "lm_11111111-1111-4111-8111-111111111111", daily_automation_enabled: true,
      call_enabled: false, notifications_enabled: false, call_time_zone: "Asia/Tokyo",
    }] };
    return { ok: false, json: async () => [] };
  };
  try {
    const row = await scheduler.getUserByUid("lm_11111111-1111-4111-8111-111111111111");
    const userSelect = urls.find((url) => url.pathname.endsWith("/lm_users")).searchParams.get("select");
    for (const field of ["web_first_travel_at", "plan_status", "trial_expires_at", "web_trial_payment_method_present"]) {
      assert.ok(userSelect.split(",").includes(field), `${field} must reach the per-user travel gate`);
      assert.equal(row[field] != null, true);
    }
  } finally {
    global.fetch = originalFetch;
    for (const [name, value] of Object.entries(before)) {
      if (value === undefined) delete process.env[name]; else process.env[name] = value;
    }
  }
});

test("Web initial scan bypasses daily automation only for the exact active account", async () => {
  const { travelUserOnce } = require("../scheduler.js");
  const uid = "lm_11111111-1111-4111-8111-111111111111";
  const calendarExpectedIds = [];
  await travelUserOnce({
    uid,
    telegram_chat_id: null,
    daily_automation_enabled: false,
    home_address: null,
    expectedCalendarAccountId: "ca-selected",
  }, {
    initialScan: true,
    apiKey: "provider-key",
    mapsKey: "maps-key",
    resolveActiveWebCalendarImpl: async () => ({ accountId: "ca-selected" }),
    readWebTravelControlStateImpl: async () => ({
      dailyAutomationEnabled: false,
      disconnectPending: false,
      enablePending: false,
      initialScanAllowed: true,
    }),
    fillTravel: async (_uid, options) => {
      calendarExpectedIds.push(options.expectedCalendarAccountId);
      assert.equal(options.allowWebInitialScan, true);
      assert.equal(options.home, null);
      return { inserted: 1, outboundReports: [] };
    },
  });

  assert.deepEqual(calendarExpectedIds, ["ca-selected"]);
});

test("Web travel rereads persisted controls after ACTIVE await before entering fillTravel", async () => {
  const { travelUserOnce } = require("../scheduler.js");
  const order = [];
  let fillCalls = 0;
  const preference = { dailyAutomationEnabled: true, billingEntitled: true,
    disconnectPending: false, enablePending: false };
  await travelUserOnce({ uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null, daily_automation_enabled: true,
    web_first_travel_at: "2030-01-01T00:00:00.000Z", paid: true, plan_status: "active" }, {
    apiKey: "provider-key",
    mapsKey: "maps-key",
    resolveActiveWebCalendarImpl: async () => {
      order.push("active");
      preference.billingEntitled = false;
      return { accountId: "ca-selected" };
    },
    readWebTravelControlStateImpl: async (uid) => {
      order.push("controls");
      assert.equal(uid, "lm_11111111-1111-4111-8111-111111111111");
      return { ...preference };
    },
    fillTravel: async () => { fillCalls++; return { inserted: 0, outboundReports: [] }; },
  });

  assert.deepEqual(order, ["active", "controls"]);
  assert.equal(fillCalls, 0);
});

test("Web control-state reader does not default a missing preference row to enabled", async () => {
  const { readWebTravelControlState } = require("../lib/runtime-preferences.js");
  const result = await readWebTravelControlState("lm_11111111-1111-4111-8111-111111111111", {
    supaUrl: "https://supabase.example",
    supaKey: "service-role-key",
    fetchImpl: async (url) => {
      const parsed = new URL(String(url));
      if (parsed.pathname.endsWith("/lm_users")) {
        return { ok: true, json: async () => [{
          uid: "lm_11111111-1111-4111-8111-111111111111",
          telegram_chat_id: null,
          calendar_enable_pending: false,
        }] };
      }
      return { ok: true, json: async () => [] };
    },
  });

  assert.deepEqual(result, { dailyAutomationEnabled: null, disconnectPending: false, enablePending: false,
    initialScanAllowed: false, billingEntitled: false });
});

test("Web travel refuses to switch account after the caller's ACTIVE check", async () => {
  const { travelUserOnce } = require("../scheduler.js");
  let calendarReads = 0;
  await travelUserOnce({ uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null,
    expectedCalendarAccountId: "ca-checked-before", daily_automation_enabled: true }, {
    apiKey: "provider-key",
    mapsKey: "maps-key",
    resolveActiveWebCalendarImpl: async () => ({ accountId: "ca-rebound-after" }),
    fillTravel: async () => { calendarReads++; return { inserted: 0, outboundReports: [] }; },
  });
  assert.equal(calendarReads, 0);
});

test("Web travel skips when the Telegram binding field is unavailable", async () => {
  const { travelUserOnce } = require("../scheduler.js");
  let guardCalls = 0, calendarReads = 0;
  await travelUserOnce({ uid: "lm_11111111-1111-4111-8111-111111111111", daily_automation_enabled: true }, {
    apiKey: "provider-key",
    mapsKey: "maps-key",
    resolveActiveWebCalendarImpl: async () => { guardCalls++; return { accountId: "ca-selected" }; },
    fillTravel: async () => { calendarReads++; return { inserted: 0, outboundReports: [] }; },
  });
  assert.equal(guardCalls, 0);
  assert.equal(calendarReads, 0);
});

test("Telegram travel keeps the existing Calendar path without the Web gate", async () => {
  const { travelUserOnce } = require("../scheduler.js");
  let guardCalls = 0, calendarReads = 0;
  await travelUserOnce({ uid: "telegram-user", telegram_chat_id: "101", daily_automation_enabled: true }, {
    apiKey: "provider-key",
    mapsKey: "maps-key",
    resolveActiveWebCalendarImpl: async () => { guardCalls++; return null; },
    fillTravel: async () => { calendarReads++; return { inserted: 0, outboundReports: [] }; },
  });
  assert.equal(guardCalls, 0);
  assert.equal(calendarReads, 1);
});

async function observeOrganCalendarAndCare(uid, telegramChatId) {
  const { organsUserOnce } = require("../scheduler.js");
  let calendarReads = 0, careRuns = 0;
  await organsUserOnce({
    uid,
    telegram_chat_id: telegramChatId,
    daily_automation_enabled: true,
    notifications_enabled: false,
  }, Date.UTC(2026, 9, 6), {
    getEvents: () => null,
    fetchUpcomingEvents: async () => { calendarReads++; return []; },
    putEvents: () => {},
    fetchVerifiedOutcomes: async () => [],
    mental: async () => null,
    care: async () => { careRuns++; return null; },
    log: () => {},
  });
  return { calendarReads, careRuns };
}

test("legacy organ scheduler does not read Calendar or run care for a Web-only tenant", async () => {
  const result = await observeOrganCalendarAndCare("lm_11111111-1111-4111-8111-111111111111", null);
  assert.deepEqual(result, { calendarReads: 0, careRuns: 0 });
});

test("legacy organ scheduler keeps Calendar reads and care for a Telegram tenant", async () => {
  const result = await observeOrganCalendarAndCare("telegram-user", "101");
  assert.deepEqual(result, { calendarReads: 1, careRuns: 1 });
});
