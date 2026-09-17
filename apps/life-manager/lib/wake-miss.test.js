"use strict";
// spec 2026-08-01-lm-daily-organ-design.md §1.2「計測の穴」+ §3 row 1b.
//
// A wake call that never rang leaves NO trace today: claimWake happens moments before the dial and
// releaseWake DELETES that claim when the dial fails, so lm_wake_log shows the failure as an event
// that never existed. These tests pin the ledger that makes it exist — and the /status line that
// makes it visible without reading a log.
//
// Run: node --test lib/wake-miss.test.js
const { test } = require("node:test");
const assert = require("node:assert");

const {
  WAKE_MISS_REASONS, recordWakeMiss, getLastWakeMiss, wakeMissLine,
  claimWakeMissNotice, wakeMissNotice,
} = require("./wake-miss.js");

const SUPA = { supaUrl: "https://supa.invalid", supaKey: "service-role-key" };
const NOW = Date.parse("2026-08-05T08:20:00+09:00");

function stubFetch(handler) {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url: String(url), init: init || {} });
    return handler(String(url), init || {});
  };
  return { fetchImpl, calls };
}

const ok = (body) => ({ ok: true, status: 200, json: async () => body });

test("recordWakeMiss writes one row carrying the reason and when the call was due", async () => {
  const { fetchImpl, calls } = stubFetch(() => ({ ok: true, status: 201, json: async () => [] }));
  const result = await recordWakeMiss("lm_user", {
    eventKey: "lm_user|2026-08-05T09:00:00+09:00|5",
    eventStartIso: "2026-08-05T09:00:00+09:00",
    dueAtIso: "2026-08-05T08:15:00+09:00",
    levelMin: 5,
    reason: WAKE_MISS_REASONS.DIAL_FAILED,
    detail: "telnyx balance too low",
    eventSummary: "打ち合わせ",
  }, { ...SUPA, fetchImpl });

  assert.equal(result.ok, true);
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /\/rest\/v1\/lm_wake_miss$/);
  assert.equal(calls[0].init.method, "POST");
  // Upsert, not plain insert: a repeated failure must refresh the reason instead of 409-ing away.
  assert.match(String(calls[0].init.headers.Prefer), /merge-duplicates/);
  const body = JSON.parse(calls[0].init.body);
  assert.equal(body.uid, "lm_user");
  assert.equal(body.reason, "dial_failed");
  assert.equal(body.detail, "telnyx balance too low");
  assert.equal(body.due_at, "2026-08-05T08:15:00+09:00");
  assert.equal(body.level_min, 5);
  // first_seen_at is never in the payload: PostgREST only updates the columns it is given, so
  // omitting it is what preserves "when this first broke" across repeated failures.
  assert.equal("first_seen_at" in body, false);
});

test("recordWakeMiss never throws and reports failure honestly when the store is unreachable", async () => {
  const { fetchImpl } = stubFetch(() => { throw new Error("network down"); });
  const result = await recordWakeMiss("lm_user", {
    eventKey: "k", reason: WAKE_MISS_REASONS.DIAL_FAILED,
  }, { ...SUPA, fetchImpl });
  assert.equal(result.ok, false);
});

test("recordWakeMiss refuses to write without a uid, an event key, or credentials", async () => {
  const { fetchImpl, calls } = stubFetch(() => ({ ok: true, status: 201, json: async () => [] }));
  assert.equal((await recordWakeMiss("", { eventKey: "k", reason: "dial_failed" }, { ...SUPA, fetchImpl })).ok, false);
  assert.equal((await recordWakeMiss("u", { reason: "dial_failed" }, { ...SUPA, fetchImpl })).ok, false);
  assert.equal((await recordWakeMiss("u", { eventKey: "k", reason: "dial_failed" }, { fetchImpl })).ok, false);
  assert.equal(calls.length, 0);
});

test("getLastWakeMiss reads the newest row for that user only", async () => {
  const row = {
    uid: "lm_user", event_key: "k", reason: "dial_failed", detail: "balance",
    due_at: "2026-08-05T08:15:00+09:00", occurred_at: "2026-08-05T08:15:04+09:00",
    event_summary: "打ち合わせ", level_min: 5,
  };
  const { fetchImpl, calls } = stubFetch(() => ok([row]));
  const got = await getLastWakeMiss("lm_user", { ...SUPA, fetchImpl });
  assert.deepEqual(got, row);
  assert.match(calls[0].url, /uid=eq\.lm_user/);
  assert.match(calls[0].url, /order=occurred_at\.desc/);
  assert.match(calls[0].url, /limit=1/);
});

test("getLastWakeMiss returns null rather than inventing a clean bill of health", async () => {
  const unreachable = stubFetch(() => { throw new Error("nope"); });
  assert.equal(await getLastWakeMiss("lm_user", { ...SUPA, fetchImpl: unreachable.fetchImpl }), null);
  const empty = stubFetch(() => ok([]));
  assert.equal(await getLastWakeMiss("lm_user", { ...SUPA, fetchImpl: empty.fetchImpl }), null);
});

test("wakeMissLine says nothing is missing when nothing is missing", () => {
  assert.equal(wakeMissLine(null, NOW), "🔔 Calls: no missed call recorded");
});

test("wakeMissLine names the clock time the call was due and why it did not ring", () => {
  const line = wakeMissLine({
    reason: "dial_failed", detail: "telnyx balance too low",
    due_at: "2026-08-05T08:15:00+09:00", occurred_at: "2026-08-05T08:15:04+09:00",
  }, NOW, { timeZone: "Asia/Tokyo" });
  assert.match(line, /08:15/);
  assert.match(line, /could not be dialled/i);
  assert.match(line, /telnyx balance too low/);
});

test("wakeMissLine distinguishes a departure that passed with no call at all", () => {
  const line = wakeMissLine({
    reason: "no_call_before_departure",
    due_at: "2026-08-05T08:15:00+09:00", occurred_at: "2026-08-05T08:31:00+09:00",
  }, NOW, { timeZone: "Asia/Tokyo" });
  assert.match(line, /08:15/);
  assert.match(line, /never rang/i);
});

test("wakeMissLine labels the clock as UTC when the user's zone is unknown", () => {
  // Same rule as lib/user-tz.js: a zone we do not have is not evidence the user lives in Tokyo.
  const line = wakeMissLine({ reason: "dial_failed", due_at: "2026-08-05T08:15:00+09:00" }, NOW);
  assert.match(line, /23:15 UTC/);
});

test("wakeMissLine keeps an unknown reason readable instead of printing undefined", () => {
  const line = wakeMissLine({ reason: "something_new", due_at: "2026-08-05T08:15:00+09:00" }, NOW,
    { timeZone: "Asia/Tokyo" });
  assert.match(line, /something_new/);
  assert.doesNotMatch(line, /undefined/);
});

// §5.4「沈黙で失敗しない」+ §6: the row alone still makes the user the one who notices. The user must
// be TOLD, exactly once per miss — a 60s tick that keeps retrying a failing dial must not keep
// messaging. The claim is the PATCH itself: only the tick that flips notified_at from NULL sends.
test("claimWakeMissNotice only lets the first caller notify", async () => {
  const winner = stubFetch(() => ok([{ uid: "u", event_key: "k", reason: "dial_failed" }]));
  const won = await claimWakeMissNotice("u", "k", { ...SUPA, fetchImpl: winner.fetchImpl, nowMs: NOW });
  assert.ok(won, "the first tick wins the claim and gets the row to send");
  assert.equal(winner.calls[0].init.method, "PATCH");
  assert.match(winner.calls[0].url, /notified_at=is\.null/, "the NULL filter IS the lock");
  assert.match(winner.calls[0].url, /uid=eq\.u/);
  assert.match(String(winner.calls[0].init.headers.Prefer), /return=representation/);

  const loser = stubFetch(() => ok([]));
  assert.equal(await claimWakeMissNotice("u", "k", { ...SUPA, fetchImpl: loser.fetchImpl, nowMs: NOW }), null,
    "a later tick updates nothing and therefore sends nothing");
});

test("claimWakeMissNotice stays silent rather than double-notifying when the store is unreachable", async () => {
  const { fetchImpl } = stubFetch(() => { throw new Error("down"); });
  assert.equal(await claimWakeMissNotice("u", "k", { ...SUPA, fetchImpl, nowMs: NOW }), null);
});

test("wakeMissNotice tells a dial failure in the user's language with the time and the reason", () => {
  const ja = wakeMissNotice({ reason: "dial_failed", detail: "balance too low", due_at: "2026-08-05T08:05:00+09:00" },
    { lang: "ja", timeZone: "Asia/Tokyo" });
  assert.match(ja, /08:05/);
  assert.match(ja, /呼び出し/);
  const en = wakeMissNotice({ reason: "dial_failed", detail: "balance too low", due_at: "2026-08-05T08:05:00+09:00" },
    { lang: "en", timeZone: "Asia/Tokyo" });
  assert.match(en, /08:05/);
  assert.match(en, /call/i);
});

test("no-answer is a delivered reminder state, not a dial failure notice", () => {
  const miss = { reason: WAKE_MISS_REASONS.NO_ANSWER, due_at: "2026-08-05T08:05:00+09:00" };
  assert.match(wakeMissLine(miss, Date.parse("2026-08-05T08:06:00+09:00"), { timeZone: "Asia/Tokyo" }), /call.*rang|call.*answer/i);
  assert.equal(wakeMissNotice(miss, { lang: "ja", timeZone: "Asia/Tokyo" }), null);
});

test("wakeMissNotice never promises the user can still make it once departure has passed", () => {
  const ja = wakeMissNotice({ reason: "no_call_before_departure", due_at: "2026-08-05T08:05:00+09:00" },
    { lang: "ja", timeZone: "Asia/Tokyo" });
  assert.match(ja, /08:05/);
  assert.doesNotMatch(ja, /間に合/, "the departure is already 15+ min past — that reassurance would be a lie");
  const en = wakeMissNotice({ reason: "no_call_before_departure", due_at: "2026-08-05T08:05:00+09:00" },
    { lang: "en", timeZone: "Asia/Tokyo" });
  assert.doesNotMatch(en, /still make it|on time/i);
});
