// _lib/lm-events.js — read a Life Manager user's upcoming Google Calendar events through their
// Composio managed-OAuth connection (the SAME path /lm's calendar-connect.js sets up:
// Composio user_id === the lm_users uid). Mirrors the proven Python reader in
// apps/alarm-backend/scheduler/saas_lateness.py::fetch_composio_events, in JS for the Netlify
// cloud wake scheduler (life-call). No per-user Google API token needed — Composio holds it.
//
// Contract:
//   fetchUpcomingEvents(uid, { nowMs?, horizonH=18, apiKey?, strictCalendarRead?, onCalendarRead? }) -> Promise<Event[]>
//     Event = { summary: string, location: string|null, startMs: number, startIso: string }
//     - timed events only (all-day date-only events are skipped — no leave time to compute)
//     - filtered to [now, now+horizonH], sorted ascending by start
//     - [] by default on: no API key, connection not ACTIVE, Composio error, or no qualifying events
//     - strictCalendarRead=true propagates transport errors; onCalendarRead receives raw item count
//   fetchNextEvent(uid, opts) -> Promise<Event|null>  (the soonest upcoming timed event)
"use strict";

const { getCalendar } = require("./transport/index.js");
const { interpretCalendarEvent } = require("./calendar-interpreter.js");

function isoZ(ms) {
  return new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
}

async function fetchUpcomingEvents(uid, opts = {}) {
  if (!uid) return [];
  const nowMs = opts.nowMs || Date.now();
  const horizonH = opts.horizonH || 18;
  const horizonMs = nowMs + horizonH * 3600 * 1000;
  // 12c: the MENTAL trough trigger needs events that ALREADY ENDED (within TROUGH_AFTER_MS). A
  // timeMin=now window can never return one, which made between_events unreachable in production.
  // lookbackMs (default 0) widens the window backwards for that one caller; every other caller
  // keeps the strict-future contract unchanged.
  const lookbackMs = Number.isFinite(opts.lookbackMs) && opts.lookbackMs > 0 ? opts.lookbackMs : 0;

  // #74: calendar reads go through the transport adapter (composio cloud / gog local). Tests inject
  // their own via opts.calendar; production builds the env-selected one.
  const calendar = opts.calendar || getCalendar({ apiKey: opts.apiKey, gmailAccountId: opts.gmailAccountId });
  const items = await calendar.listEventsRaw(uid, {
    timeMin: isoZ(nowMs - lookbackMs),
    timeMax: isoZ(horizonMs),
    ...(opts.strictCalendarRead === true ? { strict: true } : {}),
  });
  if (typeof opts.onCalendarRead === "function") {
    try { opts.onCalendarRead({ rawItemCount: items.length }); } catch { /* observability must not break calendar reads */ }
  }
  const out = [];
  for (const e of items) {
    const interpreted = interpretCalendarEvent(e);
    if (interpreted.decision === "no_call") continue;
    const raw = (e.start || {}).dateTime; // timed events only; date-only (all-day) skipped
    if (!raw) continue;
    const startMs = Date.parse(raw);
    if (Number.isNaN(startMs)) continue;
    if (startMs > horizonMs) continue;
    if (lookbackMs === 0) {
      if (startMs < nowMs) continue;
    } else {
      // keep an event iff it ends strictly after (nowMs - lookbackMs). Google's own timeMin
      // filter works on end time, so this mirrors the API contract for the widened window. A
      // malformed end.dateTime parses to NaN and falls back to the 1-hour default rather than
      // silently skipping the end-time check.
      const parsedEnd = (e.end || {}).dateTime ? Date.parse((e.end || {}).dateTime) : NaN;
      const endForFilter = Number.isFinite(parsedEnd) ? parsedEnd : startMs + 3600000;
      if (endForFilter <= nowMs - lookbackMs) continue;
    }
    const endRaw = (e.end || {}).dateTime;       // for the leave-time anchor (#69): match a [Travel]
    const endMs = endRaw ? Date.parse(endRaw) : NaN; // block whose endMs === a later event's startMs
    out.push({
      id: e.id || "",
      summary: e.summary || "予定",
      location: e.location || null,
      attendees: Array.isArray(e.attendees) ? e.attendees : [],
      startMs,
      startIso: raw,
      endMs: Number.isNaN(endMs) ? null : endMs,
      endIso: endRaw || null,
      online: interpreted.decision === "online",
    });
  }
  out.sort((a, b) => a.startMs - b.startMs);
  return out;
}

async function fetchNextEvent(uid, opts = {}) {
  const events = await fetchUpcomingEvents(uid, opts);
  return events.length ? events[0] : null;
}

// 11a runtime: care detection needs the user's OWN visit HISTORY. fetchUpcomingEvents is
// future-only by contract (and rightly so — every wake/late consumer depends on it), which is the
// same unreachable-rule disease 12c had: the one thing the care detector needs (past visits) is the
// one thing that fetch can never return. This is a dedicated history read with its own contract
// (mirrors the lookbackMs precedent above rather than stretching the wake reader to ten years):
//   - window = [now - historyMs, now], default ~10 years. Long-period checkups need four real
//     visits before the existing cadence guard may act; a biennial cadence plus the 1.5× overdue
//     threshold needs roughly nine years of evidence at action time.
//   - all-day (date-only) events are KEPT — a barber visit logged all-day is still a visit
//   - no interpretCalendarEvent filter — "no_call" is a call decision, not a history decision
//   - the raw `start` object survives so detectCalendarCare can parse dateTime/date itself
//   - endMs is reported when the source has end.dateTime, and NULL otherwise (all-day rows, or an
//     end the provider could not give). Null means "unknown", never "zero" and never a guess: a
//     consumer that needs a duration owns and documents its own assumption.
//   - STRICT reads: a transport/API failure PROPAGATES (throws) instead of returning []. The wake
//     path's swallow-to-[] is load-bearing there, but here the caller (careUserOnce) persists an
//     append-only once-per-day claim — "the read failed" must never look like "empty calendar",
//     or a single API blip freezes a fabricated empty scan for the whole day.
//   - PROVABLY COMPLETE window: the read follows the transport's page cursor until it is exhausted.
//     The previous shape split the window into ≤3 blind ~183-day chunks and ASSUMED no chunk held
//     more than maxResults events — a guess, not a proof — while throwing Google's nextPageToken
//     away, so a busier calendar would have frozen a silently truncated history into the append-only
//     lm_care_scan_log as if it were the whole truth. Truncation is now impossible to mistake for
//     completeness, in both directions:
//       * cursor exhausted  → the history is complete, by construction
//       * cursor still live at HISTORY_MAX_EVENTS, or a cursor-less transport hands back a FULL page
//         with nothing to follow → THROW. careUserOnce turns that into status:"history_unavailable"
//         (no row, no daily claim, the next 60s tick retries), which is the honest answer: an
//         incomplete history is a failed read wearing a success mask, and detectUnmetCare reads
//         gaps — every event it never saw invents overdue days that did not happen.
const CARE_HISTORY_MS = 3653 * 86400000; // ~10 years, including leap-day headroom
const HISTORY_PAGE_SIZE = 2500;   // Google events.list per-page maximum
const HISTORY_MAX_EVENTS = 10000; // hard cap: four full pages; beyond this, never claim completeness

// One window, walked to exhaustion. Returns raw transport items; every failure mode throws.
async function readHistoryWindow(calendar, uid, timeMin, timeMax) {
  // Transports that cannot page (calendar-gog's `--all-pages` CLI, test fakes) get one shot: a page
  // that comes back FULL is indistinguishable from a truncated one, so it is treated as truncated.
  if (typeof calendar.listEventsPage !== "function") {
    const page = await calendar.listEventsRaw(uid, { timeMin, timeMax, maxResults: HISTORY_PAGE_SIZE, strict: true }) || [];
    if (page.length >= HISTORY_PAGE_SIZE) {
      throw new Error(`calendar history truncated: transport returned a full ${HISTORY_PAGE_SIZE}-event page and exposes no cursor to follow`);
    }
    return page;
  }
  const items = [];
  let pageToken = null;
  for (;;) {
    const page = await calendar.listEventsPage(uid, {
      timeMin, timeMax, maxResults: HISTORY_PAGE_SIZE, pageToken, strict: true,
    }) || {};
    for (const e of page.items || []) items.push(e);
    const next = page.nextPageToken || null;
    if (!next) return items;
    if (items.length >= HISTORY_MAX_EVENTS) {
      throw new Error(`calendar history truncated: more than ${HISTORY_MAX_EVENTS} events in the window and the cursor is still live`);
    }
    if (next === pageToken) throw new Error("calendar history truncated: transport repeated the same page cursor");
    pageToken = next;
  }
}

async function fetchCalendarHistory(uid, opts = {}) {
  if (!uid) return [];
  const nowMs = opts.nowMs || Date.now();
  const historyMs = Number.isFinite(opts.historyMs) && opts.historyMs > 0 ? opts.historyMs : CARE_HISTORY_MS;
  const calendar = opts.calendar || getCalendar({ apiKey: opts.apiKey, gmailAccountId: opts.gmailAccountId });
  const items = await readHistoryWindow(calendar, uid, isoZ(nowMs - historyMs), isoZ(nowMs));
  const seen = new Set();
  const out = [];
  for (const e of items) {
    const id = e && typeof e.id === "string" ? e.id : "";
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const raw = (e.start || {}).dateTime || (e.start || {}).date;
    const startMs = raw ? Date.parse(raw) : NaN;
    if (!Number.isFinite(startMs) || startMs > nowMs) continue; // history holds only real past visits
    // endMs is ADDITIVE (H4: the weekly mirror asks whether a day's events ran into the evening a
    // bedtime answer is about, and a projection with no end forces every consumer to invent one and
    // then reason as if it had been measured). Timed events only: an all-day row has no end instant,
    // and NULL is the honest report of that — a caller that needs a duration must choose and DOCUMENT
    // its own assumption rather than receive a fabricated end wearing the provider's authority. Care
    // callers read id/summary/location/startMs/start and are untouched by an extra key.
    const endRaw = (e.end || {}).dateTime;
    const endParsed = endRaw ? Date.parse(endRaw) : NaN;
    out.push({
      id, summary: e.summary || "", location: e.location || null, startMs,
      endMs: Number.isFinite(endParsed) ? endParsed : null,
      start: e.start,
      attendees: Array.isArray(e.attendees) ? e.attendees : [],
      organizer: e.organizer && typeof e.organizer === "object" ? e.organizer : null,
    });
  }
  out.sort((a, b) => a.startMs - b.startMs);
  return out;
}

module.exports = {
  fetchUpcomingEvents, fetchNextEvent, fetchCalendarHistory,
  CARE_HISTORY_MS, HISTORY_PAGE_SIZE, HISTORY_MAX_EVENTS,
};
