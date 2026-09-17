"use strict";

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const {
  NO_DESTINATION_MESSAGE,
  evaluateLateArrival,
  formatLateSuccessMessage,
  upsertLiveLocation,
  getLiveLocation,
  deleteLiveLocation,
  claimLateEvent,
  processLocationLateNotice,
  enqueueLateApprovalCard,
  markAnswered,
  recordAmdResult,
  applyAmdDetection,
} = require("./late-notice.js");
const { createLateDraft, createInMemoryLateApprovalStore } = require("./late-approval.js");
const { sendLateNotice } = require("./notify.js");

const NOW = Date.parse("2026-07-21T09:45:00+09:00");
const EVENT = {
  id: "event-1", summary: "プロダクト定例", location: "渋谷ヒカリエ",
  startMs: Date.parse("2026-07-21T10:15:00+09:00"), startIso: "2026-07-21T10:15:00+09:00",
  attendees: [{ email: "guest@example.com" }],
};
const LIVE = {
  latitude: 35.681236, longitude: 139.767125,
  observed_at: "2026-07-21T00:44:00.000Z", expires_at: "2026-07-21T01:00:00.000Z",
};

test("location gate distinguishes missing, expired, on-time, and late", () => {
  assert.deepEqual(evaluateLateArrival({ nowMs: NOW, event: EVENT, travelMinutes: 35, location: null }), {
    decision: "location_missing",
  });
  assert.deepEqual(evaluateLateArrival({ nowMs: NOW, event: EVENT, travelMinutes: 35, location: { ...LIVE, expires_at: "2026-07-21T00:45:00.000Z" } }), {
    decision: "location_expired",
  });
  assert.deepEqual(evaluateLateArrival({ nowMs: NOW, event: EVENT, travelMinutes: 30, location: LIVE }), {
    decision: "on_time", arrivalMs: EVENT.startMs, lateMinutes: 0,
  });
  assert.deepEqual(evaluateLateArrival({ nowMs: NOW, event: EVENT, travelMinutes: 43, location: LIVE }), {
    decision: "late", arrivalMs: Date.parse("2026-07-21T10:28:00+09:00"), lateMinutes: 13,
  });
});

test("success copy follows spec table and rounds the notice ETA up to five minutes", () => {
  assert.equal(formatLateSuccessMessage(EVENT, Date.parse("2026-07-21T10:28:00+09:00"), 13),
    "📨 現在地から見て10:15に間に合わないため、先方に「15分ほど遅れます」とメールを送っておきました。次の電車なら10:28着です。");
});

test("location helpers upsert the latest live fix, enforce expiry, and atomically claim an event", async () => {
  const calls = [];
  const replies = [
    { ok: true, status: 201, json: async () => [] },
    { ok: true, status: 200, json: async () => [{ uid: "u1", ...LIVE }] },
    { ok: true, status: 201, json: async () => [] },
  ];
  const fetchImpl = async (url, init = {}) => { calls.push({ url, init }); return replies.shift(); };
  const opts = { supaUrl: "https://db.test", supaKey: "k", fetchImpl };
  assert.equal(await upsertLiveLocation("u1", {
    latitude: LIVE.latitude, longitude: LIVE.longitude,
    observedAtMs: Date.parse(LIVE.observed_at), expiresAtMs: Date.parse(LIVE.expires_at), messageId: "41",
  }, opts), true);
  assert.match(calls[0].url, /lm_user_locations\?on_conflict=uid/);
  assert.match(calls[0].init.headers.Prefer, /resolution=merge-duplicates/);
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    uid: "u1", latitude: LIVE.latitude, longitude: LIVE.longitude,
    telegram_message_id: "41", source: "telegram_live_location",
    observed_at: LIVE.observed_at, expires_at: LIVE.expires_at,
  });
  assert.deepEqual(await getLiveLocation("u1", NOW, opts), { uid: "u1", ...LIVE });
  assert.equal(await claimLateEvent("u1", "event-1", opts), true);
  assert.match(calls[2].url, /lm_late_notice_log/);
  assert.deepEqual(JSON.parse(calls[2].init.body), { uid: "u1", event_key: "event-1" });
});

test("deleteLiveLocation removes exactly the named tenant's row and reports the honest count", async () => {
  // A fake store that honours the PostgREST uid filter: deleting u1 must leave u2's fix untouched.
  const store = new Map([
    ["u1", { uid: "u1", ...LIVE }],
    ["u2", { uid: "u2", latitude: 1.5, longitude: 2.5, observed_at: LIVE.observed_at, expires_at: LIVE.expires_at }],
  ]);
  const fetchImpl = async (url, init = {}) => {
    const parsed = new URL(url);
    assert.equal(parsed.pathname, "/rest/v1/lm_user_locations");
    assert.equal(String(init.method || "GET").toUpperCase(), "DELETE");
    assert.match(init.headers.Prefer, /return=representation/, "the delete must read back what it removed");
    const uid = String(parsed.searchParams.get("uid") || "").replace(/^eq\./, "");
    assert.ok(uid, "an unfiltered DELETE would wipe every tenant — the uid filter is mandatory");
    const removed = store.has(uid) ? [store.get(uid)] : [];
    store.delete(uid);
    return { ok: true, status: 200, json: async () => removed };
  };
  const opts = { supaUrl: "https://db.test", supaKey: "k", fetchImpl };
  assert.deepEqual(await deleteLiveLocation("u1", opts), { deleted: 1 });
  assert.equal(store.has("u1"), false, "u1's row is gone");
  assert.deepEqual(store.get("u2"), { uid: "u2", latitude: 1.5, longitude: 2.5, observed_at: LIVE.observed_at, expires_at: LIVE.expires_at },
    "the other tenant's location is untouched");
  assert.deepEqual(await deleteLiveLocation("u1", opts), { deleted: 0 }, "a second delete honestly reports zero rows");
});

test("deleteLiveLocation refuses to guess: missing config or a failed request returns null, never a count", async () => {
  assert.equal(await deleteLiveLocation("u1", { supaKey: "k", fetchImpl: async () => { throw new Error("unreachable"); } }), null);
  assert.equal(await deleteLiveLocation("", { supaUrl: "https://db.test", supaKey: "k", fetchImpl: async () => { throw new Error("unreachable"); } }), null);
  assert.equal(await deleteLiveLocation("u1", {
    supaUrl: "https://db.test", supaKey: "k",
    fetchImpl: async () => ({ ok: false, status: 500, json: async () => [] }),
  }), null);
  assert.equal(await deleteLiveLocation("u1", {
    supaUrl: "https://db.test", supaKey: "k",
    fetchImpl: async () => { throw new Error("network down"); },
  }), null);
});

test("gate-closed and on-time decisions perform no claim, email, or Telegram I/O", async () => {
  let sideEffects = 0;
  const deps = {
    routeMinutes: async () => 30,
    claimEvent: async () => { sideEffects++; return true; },
    sendLateNotice: async () => { sideEffects++; return { sent: true }; },
    sendMessage: async () => { sideEffects++; },
  };
  assert.deepEqual(await processLocationLateNotice({ user: { uid: "u1" }, location: null, events: [EVENT], nowMs: NOW }, deps),
    { decision: "location_missing" });
  assert.deepEqual(await processLocationLateNotice({ user: { uid: "u1" }, location: LIVE, events: [EVENT], nowMs: NOW }, deps),
    { decision: "on_time", arrivalMs: EVENT.startMs, lateMinutes: 0 });
  assert.equal(sideEffects, 0);
});

function resolvedRecipient() {
  return {
    display_name: "Meeting partner",
    email: "guest@example.com",
    source: "calendar",
    evidence_refs: ["calendar:event:event-1:attendee:0"],
    confidence: 1,
    event_role: "attendee",
  };
}

function lateApprovalDeps({ store, resolution = { status: "resolved", candidates: [resolvedRecipient()], evidenceRefs: ["calendar:event:event-1:attendee:0"] }, cards, sendLateNotice = async () => { throw new Error("tick must never send mail"); }, sendMessage = async () => ({ ok: true }) } = {}) {
  return {
    routeMinutes: async () => 43,
    claimEvent: async () => true,
    sendLateNotice,
    resolveLateRecipients: async () => resolution,
    lateApprovalStore: store,
    enqueueLateApprovalCard: async (request) => { cards.push(request); return { queued: true }; },
    sendMessage,
  };
}

test("late tick never invokes the injectable mail sender", async () => {
  const store = createInMemoryLateApprovalStore({ nowMs: NOW });
  const cards = [];
  const result = await processLocationLateNotice({
    user: { uid: "u1", name: "Dais", email: "me@example.com", telegram_chat_id: "7" },
    location: LIVE, events: [EVENT], nowMs: NOW, telegramToken: "tg",
  }, lateApprovalDeps({ store, cards, sendLateNotice: async () => {
    throw new Error("sendLateNotice must not run from a late tick");
  } }));

  assert.equal(result.decision, "late");
  assert.equal(result.sent, false);
  assert.equal(result.draft.status, "awaiting_decision");
  assert.equal(cards.length, 1);
});

test("late ticks create one immutable draft/card request and reuse the stored row", async () => {
  const store = createInMemoryLateApprovalStore({ nowMs: NOW });
  const cards = [];
  const input = {
    user: { uid: "u1", name: "Dais", email: "me@example.com", telegram_chat_id: "7" },
    location: LIVE, events: [EVENT], nowMs: NOW, telegramToken: "tg",
  };
  const first = await processLocationLateNotice(input, lateApprovalDeps({ store, cards }));
  const second = await processLocationLateNotice(input, lateApprovalDeps({ store, cards }));

  assert.equal(first.draft.draftId, second.draft.draftId);
  assert.equal(second.draft.duplicate, true);
  assert.equal(store.size(), 1);
  assert.equal(cards.length, 1, "a retry must not enqueue a second Telegram card");
  assert.match(first.draft.bodySnapshot, /about 15 minutes late/);
  assert.equal(first.draft.etaEvidence.routeMinutes, 43);
  assert.equal(first.draft.etaEvidence.eventStartMs, EVENT.startMs);
  assert.deepEqual(cards[0].extra.reply_markup.inline_keyboard[0].map((button) => button.text), ["送る", "送らない"]);
  assert.match(cards[0].text, /about 15 minutes late/);
});

test("Telegram approval card escapes calendar-controlled HTML before sending", async () => {
  const draft = await createLateDraft({
    uid: "u1",
    eventKey: "event-html-card",
    recipientStatus: "resolved",
    recipients: [{
      display_name: "A & B",
      email: "guest@example.com",
      source: "calendar<&",
      evidence_refs: ["calendar:event:<1>"],
    }],
    evidenceSnapshot: { status: "resolved" },
    bodySnapshot: "Hi — A & B is running late to <meeting>.",
    etaEvidence: { basis: "route_eta_from_live_location", routeMinutes: 43, etaMinutes: 15 },
    nowMs: NOW,
  }, createInMemoryLateApprovalStore({ nowMs: NOW }));
  const sent = [];
  const result = await enqueueLateApprovalCard({
    telegramToken: "telegram-token",
    user: { uid: "u1", telegram_chat_id: "100" },
    nowMs: NOW,
    callbackSecret: "fixture-secret",
  }, { id: draft.eventKey, summary: "meeting" }, draft, {
    sendMessage: async (...args) => {
      sent.push(args);
      return { ok: true, result: { message_id: 7 } };
    },
  });
  assert.equal(result.queued, true);
  assert.match(result.request.text, /A & B <guest@example\.com>/);
  assert.match(sent[0][2], /A &amp; B/);
  assert.match(sent[0][2], /&lt;guest@example\.com&gt;/);
  assert.match(sent[0][2], /calendar&lt;&amp;/);
  assert.match(sent[0][2], /calendar:event:&lt;1&gt;/);
});

test("a real 60-second retry returns the first immutable draft without collision or a second card", async () => {
  const store = createInMemoryLateApprovalStore({ nowMs: NOW });
  const cards = [];
  let existingDraft = null;
  let routeCalls = 0;
  let resolverCalls = 0;
  const input = {
    user: { uid: "u1", name: "Dais", email: "me@example.com", telegram_chat_id: "7" },
    location: LIVE, events: [EVENT], telegramToken: "tg",
  };
  const deps = {
    ...lateApprovalDeps({ store, cards }),
    routeMinutes: async () => { routeCalls++; return 43; },
    resolveLateRecipients: async () => {
      resolverCalls++;
      return { status: "resolved", candidates: [resolvedRecipient()], evidenceRefs: ["calendar:event:event-1:attendee:0"] };
    },
    getLateDraft: async ({ uid, eventKey }) => existingDraft && existingDraft.uid === uid && existingDraft.eventKey === eventKey
      ? existingDraft
      : null,
    createLateDraft: async (draftInput, draftStore) => {
      existingDraft = await createLateDraft(draftInput, draftStore);
      return existingDraft;
    },
  };
  const first = await processLocationLateNotice({ ...input, nowMs: NOW }, deps);
  const second = await processLocationLateNotice({ ...input, nowMs: NOW + 60_000 }, deps);

  assert.equal(first.draft.status, "awaiting_decision");
  assert.equal(second.draft.draftId, first.draft.draftId);
  assert.equal(second.draft.duplicate, true);
  assert.notEqual(second.reason, "draft_failed");
  assert.equal(cards.length, 1, "a real retry must not enqueue a second Telegram card");
  assert.equal(second.draft.bodySnapshot, first.draft.bodySnapshot);
  assert.deepEqual(second.draft.etaEvidence, first.draft.etaEvidence);
  assert.equal(routeCalls, 1, "a retry returns the stored row before routing again");
  assert.equal(resolverCalls, 1, "a retry returns the stored row before resolving again");
});

for (const status of ["missing", "ambiguous"]) {
  test(`${status} recipient resolution stores no-send state without a button or external operation`, async () => {
    const store = createInMemoryLateApprovalStore({ nowMs: NOW });
    const cards = [];
    let telegramCalls = 0;
    const result = await processLocationLateNotice({
      user: { uid: "u1", name: "Dais", email: "me@example.com", telegram_chat_id: "7" },
      location: LIVE, events: [EVENT], nowMs: NOW, telegramToken: "tg",
    }, lateApprovalDeps({
      store,
      cards,
      resolution: { status, candidates: status === "ambiguous" ? [resolvedRecipient(), { ...resolvedRecipient(), email: "other@example.com" }] : [], evidenceRefs: [] },
      sendLateNotice: async () => { throw new Error("mail must not run"); },
      sendMessage: async () => { telegramCalls++; throw new Error("Telegram must not run"); },
    }));

    assert.equal(result.decision, "late");
    assert.equal(result.draft.status, `recipient_${status}`);
    assert.equal(cards.length, 0);
    assert.equal(telegramCalls, 0);
    assert.equal(store.size(), 1);
  });
}

test("missing Calendar recipients become a terminal draft without the old failure message", async () => {
  const store = createInMemoryLateApprovalStore({ nowMs: NOW });
  const cards = [];
  const result = await processLocationLateNotice({
    user: { uid: "u1", telegram_chat_id: "7" }, location: LIVE,
    events: [{ ...EVENT, attendees: [] }], nowMs: NOW, telegramToken: "tg",
  }, lateApprovalDeps({
    store,
    cards,
    resolution: { status: "missing", candidates: [], evidenceRefs: [] },
  }));
  assert.equal(result.draft.status, "recipient_missing");
  assert.equal(result.approvalRequired, false);
  assert.deepEqual(cards, []);
  assert.equal(NO_DESTINATION_MESSAGE, "⚠️ 先方の連絡先が見つからず、遅刻連絡は送れていません");
});

test("late tick renders the complete approval card but never sends the Resend notice", async () => {
  const store = createInMemoryLateApprovalStore({ nowMs: NOW });
  const cards = [];
  const mail = [];
  const result = await processLocationLateNotice({
    user: { uid: "u1", name: "Dais", email: "dais@example.com", telegram_chat_id: "7" },
    location: LIVE, events: [EVENT], nowMs: NOW, telegramToken: "tg", noticeOpts: { resendKey: "r" },
  }, lateApprovalDeps({
    store,
    cards,
    sendLateNotice: async (...args) => { mail.push(args); return { sent: true }; },
  }));
  assert.equal(result.sent, false);
  assert.equal(result.draft.status, "awaiting_decision");
  assert.deepEqual(mail, []);
  assert.equal(cards.length, 1);
  assert.match(cards[0].text, /guest@example\.com/);
  assert.match(cards[0].text, /calendar/);
  assert.match(cards[0].text, /calendar:event:event-1:attendee:0/);
  assert.match(cards[0].text, /Sent automatically by Life Manager/);
});

test("structured notice reuses the Resend mail path and excludes self/organizer attendees", async () => {
  const calls = [];
  const result = await sendLateNotice("u1", {
    ...EVENT,
    attendees: [
      { email: "self@example.com", self: true },
      { email: "organizer@example.com", organizer: true },
      { email: "guest@example.com" },
    ],
  }, {
    userName: "Dais", userEmail: "dais@example.com", etaMinutes: 15, resendKey: "r",
    fetchImpl: async (url, init) => {
      calls.push({ url, body: JSON.parse(init.body) });
      return { ok: true, status: 200, json: async () => ({ id: "mail-1" }) };
    },
  });
  assert.equal(result.sent, true);
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].body.to, ["guest@example.com"]);
  assert.match(calls[0].body.text, /Sent automatically by Life Manager on Dais's behalf/);
});

test("migration creates additive location and event-dedup tables", () => {
  const sql = fs.readFileSync(path.join(__dirname, "../migrations/2026-07-21-lm30-location-gate.sql"), "utf8");
  assert.match(sql, /CREATE TABLE IF NOT EXISTS lm_user_locations/);
  assert.match(sql, /expires_at timestamptz NOT NULL/);
  assert.match(sql, /CREATE TABLE IF NOT EXISTS lm_late_notice_log/);
  assert.match(sql, /PRIMARY KEY \(uid, event_key\)/);
});

// The Telegram leg remains auditable, but the message is now the approval card, not a delivery receipt.
test("the approval-card Telegram message id is carried on the result", async () => {
  const store = createInMemoryLateApprovalStore({ nowMs: NOW });
  const result = await processLocationLateNotice({
    user: { uid: "u1", telegram_chat_id: "7" }, location: LIVE,
    events: [EVENT], nowMs: NOW, telegramToken: "tg",
  }, {
    ...lateApprovalDeps({ store, cards: [] }),
    enqueueLateApprovalCard: undefined,
    sendMessage: async () => ({ ok: true, result: { message_id: 4242 } }),
  });
  assert.equal(result.sent, false);
  assert.equal(result.telegramMessageId, 4242);
  assert.equal((await store.getDraft(result.draft.draftId)).telegramApprovalMessageId, "4242");
});

test("an approval-card Telegram send that returns no id leaves the field absent", async () => {
  const store = createInMemoryLateApprovalStore({ nowMs: NOW });
  const result = await processLocationLateNotice({
    user: { uid: "u1", telegram_chat_id: "7" }, location: LIVE,
    events: [EVENT], nowMs: NOW, telegramToken: "tg",
  }, {
    ...lateApprovalDeps({ store, cards: [] }),
    enqueueLateApprovalCard: undefined,
    sendMessage: async () => ({ ok: false }),
  });
  assert.equal(result.sent, false);
  assert.equal("telegramMessageId" in result, false);
});

// ---------------------------------------------------------------------------
// spec 2026-08-01-lm-daily-organ-design.md §1.3 + §3 row 2 — AMD detection telemetry.
//
// Measured over every Telnyx call event correlated to lm_wake_log: human → answered_at set, 10/10;
// machine/not_sure → null, 33/33. The recording path is healthy; the TABLE is the defect. Four
// different realities ("a person answered", "rang unanswered", "voicemail", "the webhook never
// arrived") collapse into one reading, so a rotated Telnyx signing key would make every call fail
// silently forever with nothing anywhere recording it. These tests pin the column that separates
// them, and pin that a PATCH matching zero rows is not the same value as a PATCH that never landed.
// ---------------------------------------------------------------------------

const SUPA = { supaUrl: "https://supa.invalid", supaKey: "service-role-key" };

function stubFetch(handler) {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url: String(url), init: init || {}, body: JSON.parse((init || {}).body || "null") });
    return handler(String(url), init || {});
  };
  return { fetchImpl, calls };
}

const patchedRows = (rows) => async () => ({ ok: true, status: 200, json: async () => rows });

test("AMD human writes both the raw result and answered_at", async () => {
  const { fetchImpl, calls } = stubFetch(patchedRows([{ event_key: "k" }]));
  const out = await applyAmdDetection("lm_u", "k", {
    result: "human", nowMs: Date.parse("2026-08-01T00:10:00Z"), ...SUPA, fetchImpl,
  });

  assert.equal(out.result, "human");
  assert.equal(out.amd.ok, true);
  assert.equal(out.amd.matched, 1);
  assert.equal(out.answered.ok, true);
  assert.equal(out.answered.matched, 1);

  const amdWrite = calls.find((c) => c.body && "amd_result" in c.body);
  const answeredWrite = calls.find((c) => c.body && "answered_at" in c.body);
  assert.ok(amdWrite, "the raw AMD result must be persisted");
  assert.ok(answeredWrite, "a human detection must still set answered_at");
  assert.equal(amdWrite.body.amd_result, "human");
  assert.equal(answeredWrite.body.answered_at, "2026-08-01T00:10:00.000Z");
  // The amd_result write must NOT inherit the answered_at=is.null latch: a detection arriving after
  // a row is already answered would otherwise be dropped, i.e. unrecorded again.
  assert.doesNotMatch(amdWrite.url, /answered_at=is\.null/);
  assert.match(answeredWrite.url, /answered_at=is\.null/);
});

test("AMD machine records the voicemail as itself and never sets answered_at", async () => {
  const { fetchImpl, calls } = stubFetch(patchedRows([{ event_key: "k" }]));
  const out = await applyAmdDetection("lm_u", "k", { result: "machine", ...SUPA, fetchImpl });

  assert.equal(out.amd.ok, true);
  assert.equal(out.amd.matched, 1);
  assert.equal(out.answered, null, "no answered_at write may be attempted for a machine");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].body.amd_result, "machine");
  assert.equal("answered_at" in calls[0].body, false);
  assert.equal(calls.some((c) => /answered_at=is\.null/.test(c.url)), false);
});

test("AMD not_sure is recorded as itself, not folded into machine or dropped", async () => {
  const { fetchImpl, calls } = stubFetch(patchedRows([{ event_key: "k" }]));
  const out = await applyAmdDetection("lm_u", "k", { result: "not_sure", ...SUPA, fetchImpl });

  assert.equal(out.amd.matched, 1);
  assert.equal(out.answered.matched, 1);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].body.amd_result, "not_sure");
  assert.equal("answered_at" in calls[1].body, true);
});

// The defect §1.3 names outright: markAnswered returned false for "matched zero rows" AND for "the
// request never landed", so a rotated signing key looked exactly like a user who did not pick up.
test("a PATCH matching zero rows is distinguishable from a PATCH whose request failed", async () => {
  const zeroRows = await markAnswered("lm_u", "k", {
    ...SUPA, fetchImpl: async () => ({ ok: true, status: 200, json: async () => [] }),
  });
  assert.deepEqual(
    { ok: zeroRows.ok, matched: zeroRows.matched },
    { ok: true, matched: 0 },
    "the write reached Supabase and correctly matched nothing",
  );

  const httpFail = await markAnswered("lm_u", "k", {
    ...SUPA, fetchImpl: async () => ({ ok: false, status: 503, json: async () => ({}) }),
  });
  assert.equal(httpFail.ok, false, "a 5xx is a failure to record, not a zero match");
  assert.equal(httpFail.matched, 0);
  assert.ok(httpFail.error, "the failure must name itself");

  const thrown = await markAnswered("lm_u", "k", {
    ...SUPA, fetchImpl: async () => { throw new Error("ECONNRESET"); },
  });
  assert.equal(thrown.ok, false);
  assert.ok(thrown.error);

  // Same contract on the amd_result write, or the new column inherits the old blindness.
  const amdZero = await recordAmdResult("lm_u", "k", {
    result: "machine", ...SUPA, fetchImpl: async () => ({ ok: true, status: 200, json: async () => [] }),
  });
  assert.deepEqual({ ok: amdZero.ok, matched: amdZero.matched }, { ok: true, matched: 0 });
  const amdFail = await recordAmdResult("lm_u", "k", {
    result: "machine", ...SUPA, fetchImpl: async () => ({ ok: false, status: 403, json: async () => ({}) }),
  });
  assert.equal(amdFail.ok, false);
  assert.equal(amdFail.matched, 0);
});

// server.js:816 (the media bridge, LM_AMD=off fallback) calls markAnswered with no new options.
// It must keep issuing exactly the one latched answered_at PATCH it always did.
test("the media bridge caller still issues one latched answered_at PATCH and nothing else", async () => {
  const { fetchImpl, calls } = stubFetch(patchedRows([{ event_key: "k" }]));
  const out = await markAnswered("lm_u", "k", { ...SUPA, nowMs: Date.parse("2026-08-01T00:10:00Z"), fetchImpl });

  assert.equal(out.matched, 1);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].init.method, "PATCH");
  assert.match(calls[0].url, /\/rest\/v1\/lm_wake_log\?/);
  assert.match(calls[0].url, /answered_at=is\.null/);
  assert.deepEqual(calls[0].body, { answered_at: "2026-08-01T00:10:00.000Z" });
});

// `answered: null` is reserved for "not a human, so not attempted". A human we could not correlate
// must report a FAILED write, not the same null — otherwise an undecodable client_state reads as a
// deliberate skip, which is exactly the ambiguity this change exists to remove.
test("a detection with no wake identifiers writes nothing and says so", async () => {
  const explode = async () => { throw new Error("must not be called"); };
  const out = await applyAmdDetection("", "", { result: "human", ...SUPA, fetchImpl: explode });
  assert.equal(out.amd.ok, false);
  assert.equal(out.amd.error, "missing_args");
  assert.equal(out.answered.ok, false);
  assert.equal(out.answered.error, "missing_args");
});

// ---------------------------------------------------------------------------
// spec §3 row 2b / §5.2.1 — hanging up on a voicemail.
//
// Measured: `hangup_source` was `callee` on all 43 correlated events, i.e. NOTHING in this codebase
// ever ended a wake call. The carrier's 120-second recording limit did. So AMD said `machine`, and
// the bridge then spoke two minutes of Gemini Live (~$0.05) into a recording nobody plays back —
// 17 machines against 3 humans, and the last four days of wake calls were 100% voicemail.
//
// These tests pin the two halves of the fix that can regress independently: the hangup must happen,
// and it must never cost us the amd_result row (spec row 2), which is the only thing that lets a
// voicemail be told apart from a webhook that never arrived.
// ---------------------------------------------------------------------------

// A probabilistic machine result is evidence, not permission to cut off a paying human.
function amdFetch() {
  return stubFetch(async () => ({ ok: true, status: 200, json: async () => [{ event_key: "k" }] }));
}

for (const result of ["machine", "not_sure", "human"]) {
  test(`AMD ${result} records its result without hanging up the caller`, async () => {
    const { fetchImpl, calls } = amdFetch();
    const out = await applyAmdDetection("lm_u", "k", { result, ...SUPA, fetchImpl });
    assert.equal(out.amd.matched, 1);
    assert.equal(out.hangup, null);
    assert.equal(calls.some((call) => /api\.telnyx\.com/.test(call.url)), false);
    assert.equal(calls.find((call) => call.body && "amd_result" in call.body).body.amd_result, result);
    if (result === "machine") assert.equal(out.answered, null);
    else assert.equal(out.answered.matched, 1);
  });
}

test("an unreadable detection records no verdict and never hangs up", async () => {
  const { fetchImpl } = amdFetch();
  const out = await applyAmdDetection("lm_u", "k", { result: "", ...SUPA, fetchImpl });
  assert.equal(out.amd.error, "missing_result");
  assert.equal(out.hangup, null);
});
