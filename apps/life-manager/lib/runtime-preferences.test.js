"use strict";
// spec 2026-08-01-lm-daily-organ-design.md §5.2.1 — the phone is opt-IN.
//
// DEFAULTS is what a user gets when they have said nothing. It is merged into every user the
// scheduler loads (scheduler.js supaUsers) and every user re-read by uid (getUserByUid), so this one
// frozen object decides whether silence means "phone me" or "leave me alone". §5.2.1 settles it:
// measured, the phone reached a human 3 times against 17 voicemails, and Telegram is the channel that
// actually pushes someone out the door. So silence means no call.
//
// Run: node --test lib/runtime-preferences.test.js
const test = require("node:test");
const assert = require("node:assert");
const { DEFAULTS, readRuntimePreferences, readWebTravelControlState } = require("./runtime-preferences.js");

const SUPA = { supaUrl: "https://supa.invalid", supaKey: "service-role-key" };
const rows = (value) => async () => ({ ok: true, status: 200, json: async () => value });

test("silence is not consent to be phoned", () => {
  assert.equal(DEFAULTS.call_enabled, false,
    "a user who expressed no preference must not be called (spec §5.2.1)");
});

test("the channels that are not a phone call stay on by default", () => {
  // Flipping the phone must not quietly mute the product. Telegram IS the product now (§5.3), so
  // notifications and the daily automation keep their opt-OUT semantics; only the phone changed.
  assert.equal(DEFAULTS.notifications_enabled, true);
  assert.equal(DEFAULTS.daily_automation_enabled, true);
});

test("an explicit opt-in is honoured, and an absent row falls back to no call", async () => {
  const optedIn = await readRuntimePreferences("u1", { ...SUPA, fetchImpl: rows([{ call_enabled: true }]) });
  assert.equal(optedIn.call_enabled, true, "someone who switched calls on is still called");

  const noRow = await readRuntimePreferences("u1", { ...SUPA, fetchImpl: rows([]) });
  assert.equal(noRow.call_enabled, false, "no preference row means no phone call");

  const optedOut = await readRuntimePreferences("u1", { ...SUPA, fetchImpl: rows([{ call_enabled: false }]) });
  assert.equal(optedOut.call_enabled, false);
});

test("a row whose call_enabled is SQL NULL is 'said nothing', not 'said yes'", async () => {
  // A row can exist because the user toggled some OTHER setting. PostgREST returns the untouched
  // column as null, which spreads OVER the default — so the default alone cannot save us here and
  // every consumer must test for `=== true` rather than `!== false`.
  const nulled = await readRuntimePreferences("u1", { ...SUPA, fetchImpl: rows([{ call_enabled: null }]) });
  assert.notEqual(nulled.call_enabled, true, "a NULL column must never read as an opt-in");
});

test("an unreadable preference store yields no preferences at all, not a permissive guess", async () => {
  assert.equal(await readRuntimePreferences("u1", { ...SUPA, fetchImpl: async () => { throw new Error("offline"); } }), null);
  assert.equal(await readRuntimePreferences("u1", { ...SUPA, fetchImpl: async () => ({ ok: false, status: 503 }) }), null);
  assert.equal(await readRuntimePreferences("", { ...SUPA, fetchImpl: rows([]) }), null);
});

test("Web control state returns the exact Calendar enable claim and database timestamp", async () => {
  const uid = "lm_11111111-1111-4111-8111-111111111111";
  const claimId = "2e59df08-f437-44fd-bbe9-5d835ba467f0";
  const claimedAt = "2026-10-06T03:00:00+00:00";
  const queries = [];
  const result = await readWebTravelControlState(uid, {
    ...SUPA,
    fetchImpl: async (url) => {
      const parsed = new URL(String(url));
      queries.push(parsed);
      if (parsed.pathname.endsWith("/lm_users")) {
        return rows([{
          uid,
          telegram_chat_id: null,
          calendar_enable_pending: true,
          calendar_enable_claim_id: claimId,
          calendar_enable_claimed_at: claimedAt,
        }])();
      }
      return rows([{ daily_automation_enabled: false, calendar_disconnect_pending: false }])();
    },
  });

  assert.deepEqual(result, {
    dailyAutomationEnabled: false,
    disconnectPending: false,
    enablePending: true,
    initialScanAllowed: false,
    billingEntitled: false,
    enableClaimId: claimId,
    enableClaimedAt: claimedAt,
  });
  assert.match(queries[0].searchParams.get("select"), /calendar_enable_claim_id/);
  assert.match(queries[0].searchParams.get("select"), /calendar_enable_claimed_at/);
  assert.match(queries[0].searchParams.get("select"), /web_trial_payment_method_present/);
});

test("Web control state fails closed when a pending Calendar claim has no valid owner metadata", async () => {
  const uid = "lm_11111111-1111-4111-8111-111111111111";
  const result = await readWebTravelControlState(uid, {
    ...SUPA,
    fetchImpl: async (url) => {
      const parsed = new URL(String(url));
      if (parsed.pathname.endsWith("/lm_users")) {
        return rows([{
          uid,
          telegram_chat_id: null,
          calendar_enable_pending: true,
          calendar_enable_claim_id: null,
          calendar_enable_claimed_at: null,
        }])();
      }
      return rows([{ daily_automation_enabled: false, calendar_disconnect_pending: false }])();
    },
  });

  assert.equal(result, null);
});

test("Web control state permits an explicit rescan only while no first Travel value or subscription exists", async () => {
  const uid = "lm_11111111-1111-4111-8111-111111111111";
  const accountId = "ca-selected-123";
  const result = await readWebTravelControlState(uid, {
    ...SUPA,
    expectedCalendarAccountId: accountId,
    fetchImpl: async (url) => {
      const parsed = new URL(String(url));
      if (parsed.pathname.endsWith("/lm_users")) return rows([{
        uid,
        telegram_chat_id: null,
        calendar_provider: "composio_gcal",
        calendar_connected_account_id: accountId,
        calendar_enable_pending: false,
        calendar_enable_claim_id: null,
        calendar_enable_claimed_at: null,
        web_initial_scan_completed_at: "2030-01-01T08:00:00.000Z",
        web_first_travel_at: null,
        stripe_subscription_id: null,
        trial_expires_at: null,
        plan_status: null,
        paid: false,
      }])();
      return rows([{ daily_automation_enabled: false, calendar_disconnect_pending: false }])();
    },
  });

  assert.equal(result.initialScanAllowed, true);
  assert.equal(result.billingEntitled, false);
});

test("Web control state returns current paid entitlement for pre-Calendar and write gates", async () => {
  const uid = "lm_11111111-1111-4111-8111-111111111111";
  const user = {
    uid, telegram_chat_id: null, calendar_enable_pending: false,
    calendar_provider: "composio_gcal", calendar_connected_account_id: "ca-selected-123",
    web_first_travel_at: "2030-01-01T00:00:00.000Z", stripe_subscription_id: "sub_web",
    paid: true, plan_status: "active", trial_expires_at: null, web_trial_payment_method_present: false,
    web_billing_cancel_at_period_end: false,
  };
  const preference = { daily_automation_enabled: true, calendar_disconnect_pending: false };
  const result = await readWebTravelControlState(uid, {
    ...SUPA,
    expectedCalendarAccountId: "ca-selected-123",
    nowMs: Date.parse("2030-01-01T00:00:00.000Z"),
    fetchImpl: async (url) => new URL(String(url)).pathname.endsWith("/lm_users")
      ? rows([user])() : rows([preference])(),
  });
  assert.equal(result.billingEntitled, true);

  Object.assign(user, { paid: false, plan_status: "trialing",
    trial_expires_at: "2030-01-02T00:00:00.000Z", web_trial_payment_method_present: true });
  const trial = await readWebTravelControlState(uid, {
    ...SUPA,
    expectedCalendarAccountId: "ca-selected-123",
    nowMs: Date.parse("2030-01-01T00:00:00.000Z"),
    fetchImpl: async (url) => new URL(String(url)).pathname.endsWith("/lm_users")
      ? rows([user])() : rows([preference])(),
  });
  assert.equal(trial.billingEntitled, true);

  user.web_trial_payment_method_present = false;
  const trialWithoutCard = await readWebTravelControlState(uid, {
    ...SUPA,
    expectedCalendarAccountId: "ca-selected-123",
    nowMs: Date.parse("2030-01-01T00:00:00.000Z"),
    fetchImpl: async (url) => new URL(String(url)).pathname.endsWith("/lm_users")
      ? rows([user])() : rows([preference])(),
  });
  assert.equal(trialWithoutCard.billingEntitled, false);

  user.paid = false;
  user.plan_status = "past_due";
  const pastDue = await readWebTravelControlState(uid, {
    ...SUPA,
    expectedCalendarAccountId: "ca-selected-123",
    fetchImpl: async (url) => new URL(String(url)).pathname.endsWith("/lm_users")
      ? rows([user])() : rows([preference])(),
  });
  assert.equal(pastDue.billingEntitled, false);
});
