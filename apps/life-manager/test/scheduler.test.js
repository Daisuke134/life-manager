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

test("Web travel skips Calendar work unless the persisted account is currently ACTIVE", async () => {
  const { travelUserOnce } = require("../scheduler.js");
  const uid = "lm_11111111-1111-4111-8111-111111111111";
  for (const [accountState, accountId] of [["inactive", "ca-disabled"], ["rebound", "ca-replaced"]]) {
    let guardCalls = 0, calendarReads = 0;
    await travelUserOnce({ uid, telegram_chat_id: null, calendar_connected_account_id: accountId, daily_automation_enabled: true }, {
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
  await travelUserOnce({ uid: "lm_11111111-1111-4111-8111-111111111111", telegram_chat_id: null, daily_automation_enabled: true }, {
    apiKey: "provider-key",
    mapsKey: "maps-key",
    resolveActiveWebCalendarImpl: async () => ({ accountId: "ca-selected" }),
    fillTravel: async (_uid, options) => { calendarExpectedIds.push(options.expectedCalendarAccountId); return { inserted: 0, outboundReports: [] }; },
  });
  assert.deepEqual(calendarExpectedIds, ["ca-selected"]);
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
