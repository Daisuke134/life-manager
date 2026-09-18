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
const { DEFAULTS, readRuntimePreferences } = require("./runtime-preferences.js");

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

test("a pre-quiet-hours schema falls back without disabling the user", async () => {
  const calls = [];
  const result = await readRuntimePreferences("u1", {
    ...SUPA,
    fetchImpl: async (url) => {
      calls.push(url);
      if (calls.length === 1) return { ok: false, status: 400 };
      return { ok: true, status: 200, json: async () => [{ call_enabled: true }] };
    },
  });
  assert.equal(result.call_enabled, true);
  assert.equal(result.mental_quiet_start_minute, null);
  assert.equal(calls.length, 2);
});
