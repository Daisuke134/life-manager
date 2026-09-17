"use strict";
// lib/wake-miss.js — spec 2026-08-01-lm-daily-organ-design.md §3 row 1b.
//
// WHY THIS EXISTS (§1.2「計測の穴」): lm_wake_log only ever holds calls we were about to place.
// claimWake inserts moments before the dial, and releaseWake DELETES that claim the instant the dial
// fails so a later tick can retry. The retry is right; the erasure is not. The consequence measured
// on 2026-08-01 is that "the call that should have rung and did not" is invisible — not "failed",
// but absent — which is how three days went by looking healthy.
//
// This ledger is the opposite promise: every wake we owed the user and did not deliver leaves a row
// with a REASON, and /status reads it. §5.4 of the spec states the product rule this serves —
// 沈黙で失敗しない: the user must never be the one who notices.
//
// The table is keyed (uid, event_key) and written with PostgREST merge-duplicates, so a failure that
// repeats across ticks refreshes its reason instead of either duplicating or 409-ing into silence.
// first_seen_at is deliberately absent from every payload: PostgREST updates only the columns it is
// given, so omitting it is what preserves when the breakage started.

const WAKE_MISS_REASONS = {
  // The dial itself failed (Telnyx balance, bad number, transport). releaseWake then wipes the claim.
  DIAL_FAILED: "dial_failed",
  // The provider accepted the reminder and it ended without user response; this is not a dial failure.
  NO_ANSWER: "no_answer",
  // Departure passed LATE_CUTOFF_MIN and no level was ever claimed: nothing rang at all.
  NO_CALL_BEFORE_DEPARTURE: "no_call_before_departure",
  NO_CALL_BEFORE_EVENT: "no_call_before_event",
  MISSED_LEVEL: "missed_level",
};

function supaHeaders(key, prefer) {
  const headers = {
    apikey: key,
    Authorization: `Bearer ${key}`,
    "Content-Type": "application/json",
  };
  if (prefer) headers.Prefer = prefer;
  return headers;
}

// Best-effort by contract: this runs inside the wake loop, and a ledger write must never be the
// reason a later call does not happen. It reports {ok:false} rather than throwing, and never
// pretends a write it could not confirm succeeded.
async function recordWakeMiss(uid, miss = {}, opts = {}) {
  const f = opts.fetchImpl || fetch;
  if (!uid || !miss.eventKey || !miss.reason) return { ok: false, reason: "incomplete" };
  if (!opts.supaUrl || !opts.supaKey) return { ok: false, reason: "no_credentials" };

  const body = {
    uid: String(uid),
    event_key: String(miss.eventKey),
    reason: String(miss.reason),
    occurred_at: new Date(miss.nowMs == null ? Date.now() : miss.nowMs).toISOString(),
  };
  if (miss.eventStartIso) body.event_start = miss.eventStartIso;
  if (miss.dueAtIso) body.due_at = miss.dueAtIso;
  if (miss.levelMin != null) body.level_min = Number(miss.levelMin);
  if (miss.detail) body.detail = String(miss.detail).slice(0, 500);
  if (miss.eventSummary) body.event_summary = String(miss.eventSummary).slice(0, 200);

  let response;
  try {
    response = await f(`${opts.supaUrl}/rest/v1/lm_wake_miss`, {
      method: "POST",
      headers: supaHeaders(opts.supaKey, "return=minimal,resolution=merge-duplicates"),
      body: JSON.stringify(body),
    });
  } catch (e) {
    return { ok: false, reason: "unreachable", error: String((e && e.message) || e) };
  }
  if (!response || !response.ok) {
    return { ok: false, reason: "rejected", status: response ? response.status : null };
  }
  return { ok: true, recorded: body };
}

// The newest miss for ONE user. The uid filter is the tenant boundary; an unfiltered read would put
// another user's schedule into this user's /status.
async function getLastWakeMiss(uid, opts = {}) {
  const f = opts.fetchImpl || fetch;
  if (!uid || !opts.supaUrl || !opts.supaKey) return null;
  const url = `${opts.supaUrl}/rest/v1/lm_wake_miss`
    + `?uid=eq.${encodeURIComponent(uid)}`
    + "&select=uid,event_key,event_start,due_at,level_min,reason,detail,event_summary,occurred_at"
    + "&order=occurred_at.desc&limit=1";
  let response;
  try {
    response = await f(url, { headers: supaHeaders(opts.supaKey) });
  } catch {
    return null;
  }
  if (!response || !response.ok) return null;
  const rows = await response.json().catch(() => null);
  return Array.isArray(rows) && rows[0] ? rows[0] : null;
}

// lib/user-tz.js' rule applies here too: a zone we do not know is NOT evidence the user lives in
// Tokyo. Without a zone the time is still shown — silence would be worse — but it is labelled UTC
// rather than passed off as the user's wall clock.
function clockTime(iso, timeZone) {
  const ms = Date.parse(iso);
  if (!iso || Number.isNaN(ms)) return null;
  if (!timeZone) return `${new Date(ms).toISOString().slice(11, 16)} UTC`;
  try {
    return new Intl.DateTimeFormat("en-GB", {
      hour: "2-digit", minute: "2-digit", hour12: false, timeZone,
    }).format(new Date(ms));
  } catch {
    return `${new Date(ms).toISOString().slice(11, 16)} UTC`;
  }
}

// Pure: the one line /status shows. A reason this module does not know about is printed as itself —
// an unrecognised failure must still be legible, never "undefined".
function wakeMissLine(miss, nowMs, opts = {}) {
  if (!miss) return "🔔 Calls: no missed call recorded";
  const at = clockTime(miss.due_at || miss.occurred_at, opts.timeZone);
  const when = at ? `the ${at} call` : "a call";
  if (miss.reason === WAKE_MISS_REASONS.DIAL_FAILED) {
    return `🔔 Missed: ${when} could not be dialled${miss.detail ? ` (${miss.detail})` : ""}`;
  }
  if (miss.reason === WAKE_MISS_REASONS.NO_ANSWER) {
    return `🔔 Reminder: ${when} rang, but nobody answered`;
  }
  if (miss.reason === WAKE_MISS_REASONS.NO_CALL_BEFORE_DEPARTURE) {
    return `🔔 Missed: ${when} never rang before your departure time`;
  }
  if (miss.reason === WAKE_MISS_REASONS.NO_CALL_BEFORE_EVENT) {
    return `🔔 Missed: ${when} never rang before the event started`;
  }
  if (miss.reason === WAKE_MISS_REASONS.MISSED_LEVEL) {
    return `🔔 Missed: ${when} reminder threshold passed before the scheduler ran`;
  }
  return `🔔 Missed: ${when} did not go out (${miss.reason})`;
}

// §5.4「沈黙で失敗しない」: a row the user has to ask for still makes the user the one who notices.
// This claims the right to TELL them, exactly once. The lock is the write itself — PATCH filtered on
// notified_at IS NULL returns the row only to the caller that flipped it, so the 60s tick can retry a
// failing dial forever without sending a second message. Returns null (stay silent) on any doubt: a
// missed message is a smaller harm than a message loop.
async function claimWakeMissNotice(uid, eventKey, opts = {}) {
  const f = opts.fetchImpl || fetch;
  if (!uid || !eventKey || !opts.supaUrl || !opts.supaKey) return null;
  const url = `${opts.supaUrl}/rest/v1/lm_wake_miss`
    + `?uid=eq.${encodeURIComponent(uid)}`
    + `&event_key=eq.${encodeURIComponent(eventKey)}`
    + "&notified_at=is.null";
  let response;
  try {
    response = await f(url, {
      method: "PATCH",
      headers: supaHeaders(opts.supaKey, "return=representation"),
      body: JSON.stringify({ notified_at: new Date(opts.nowMs == null ? Date.now() : opts.nowMs).toISOString() }),
    });
  } catch {
    return null;
  }
  if (!response || !response.ok) return null;
  const rows = await response.json().catch(() => null);
  return Array.isArray(rows) && rows[0] ? rows[0] : null;
}

// The message the user actually receives. Deliberately NOT the reassurance in §5.4's sketch for the
// departure-passed case: by then the departure is 15+ minutes gone, so "you can still make it" would
// be a fabrication. Each reason says only what is known to be true.
function wakeMissNotice(miss, opts = {}) {
  if (!miss) return null;
  if (miss.reason === WAKE_MISS_REASONS.NO_ANSWER) return null;
  const ja = (opts.lang || "ja") === "ja";
  const at = clockTime(miss.due_at || miss.occurred_at, opts.timeZone);
  const when = at || (ja ? "予定の時刻" : "the scheduled time");
  if (miss.reason === WAKE_MISS_REASONS.NO_CALL_BEFORE_DEPARTURE) {
    return ja
      ? `⚠️ ${when} の呼び出しが鳴りませんでした。出発時刻はすでに過ぎています。`
      : `⚠️ Your ${when} call never rang. Your departure time has already passed.`;
  }
  if (miss.reason === WAKE_MISS_REASONS.NO_CALL_BEFORE_EVENT) {
    return ja
      ? `⚠️ ${when} の呼び出しが鳴りませんでした。予定はすでに始まっています。`
      : `⚠️ Your ${when} call never rang. The event has already started.`;
  }
  if (miss.reason === WAKE_MISS_REASONS.MISSED_LEVEL) {
    return ja
      ? `⚠️ ${when} の呼び出しは時刻を過ぎたため実行できませんでした。`
      : `⚠️ The ${when} call could not run before its reminder time passed.`;
  }
  const why = miss.detail ? (ja ? `（理由: ${miss.detail}）` : ` (${miss.detail})`) : "";
  if (miss.reason === WAKE_MISS_REASONS.DIAL_FAILED) {
    return ja
      ? `⚠️ ${when} の呼び出しに失敗しました${why}。再試行しています。`
      : `⚠️ I could not place your ${when} call${why}. I am retrying.`;
  }
  return ja
    ? `⚠️ ${when} の呼び出しを届けられませんでした（${miss.reason}）。`
    : `⚠️ Your ${when} call did not go out (${miss.reason}).`;
}

module.exports = {
  WAKE_MISS_REASONS, recordWakeMiss, getLastWakeMiss, wakeMissLine,
  claimWakeMissNotice, wakeMissNotice,
};
