"use strict";
// lm_mental_send_log — the MENTAL organ's send budget, shared.
//
// H4 (precepts) rides MENTAL's 3/day cap and 2h spacing rather than opening a second budget: from
// the user's side there is one stream of unsolicited evening messages, and two organs each politely
// keeping to "3 a day" is six a day. So the precepts ask and the weekly mirror READ this table before
// they speak and WRITE to it after they do — the kind rides in `trigger`, and the copy (not the
// table) is what makes a precepts message different from an affirmation.
//
// These two functions used to live inside scheduler.js where only mentalDeps could reach them.
// Nothing about them is scheduler-specific, and a budget that only one caller can see is not a
// budget.
//
// STRICTNESS IS PER-CALLER, ON PURPOSE:
//   * MENTAL (strict: false, the historical behaviour, unchanged) treats an unreadable log as
//     "nothing sent yet". That is wrong-but-shipped, and quietly tightening it here would change the
//     behaviour of a live organ in a branch that is supposed to be adding a different one.
//   * PRECEPTS (strict: true) THROWS instead, and its runtime turns the throw into a silence with a
//     once-per-day log line — the diet organ's `ledger-unreadable` rule. Treating an outage as an
//     empty history is precisely how a 3/day cap becomes unbounded during an incident, and precepts
//     is the organ that would be spending someone else's budget while doing it.

const MENTAL_SEND_WINDOW_MS = 24 * 60 * 60000;
const MENTAL_TEMPLATE_DEDUPE_WINDOW_MS = 14 * 24 * 60 * 60000;

function supaBase(url) {
  return String(url).replace(/\/$/, "");
}

function authHeaders(key, extra) {
  return { apikey: key, Authorization: `Bearer ${key}`, ...extra };
}

// { sentTodayCount, lastSentMs } over the trailing 24 hours — "today" as a rolling window, which is
// what the 3/day cap has always meant here (a calendar-day reset would allow three at 23:50 and
// three more at 00:10).
async function readMentalSendState(uid, nowMs, supa, fetchImpl, opts = {}) {
  const strict = Boolean(opts.strict);
  const url = supa && (supa.url || supa.supaUrl);
  const key = supa && (supa.key || supa.supaKey);
  if (!url || !key) {
    if (strict) throw new Error("mental send log is not configured");
    return { sentTodayCount: 0, lastSentMs: null };
  }
  const f = fetchImpl || globalThis.fetch;
  // The rolling 24-hour window enforces the cap/spacing. Template repetition has a separate
  // fourteen-day horizon, so fetching only the cap window makes yesterday's template eligible
  // again at the exact 24-hour boundary.
  const since = new Date(nowMs - MENTAL_TEMPLATE_DEDUPE_WINDOW_MS).toISOString();
  const query = `uid=eq.${encodeURIComponent(uid)}&sent_at=gte.${encodeURIComponent(since)}`
    + "&select=sent_at,trigger,family,template_id,local_day,window&order=sent_at.desc";
  let response = await f(`${supaBase(url)}/rest/v1/lm_mental_send_log?${query}`, {
    headers: authHeaders(key),
  }).catch(() => null);
  // Deploy order can briefly expose the old schema. Strict V1 callers must stay silent; legacy
  // callers may retain the historical count-only fallback until the additive migration lands.
  if ((!response || !response.ok) && !strict) {
    const legacyQuery = `uid=eq.${encodeURIComponent(uid)}&sent_at=gte.${encodeURIComponent(since)}`
      + "&select=sent_at&order=sent_at.desc";
    response = await f(`${supaBase(url)}/rest/v1/lm_mental_send_log?${legacyQuery}`, {
      headers: authHeaders(key),
    }).catch(() => null);
  }
  if (!response || !response.ok) {
    if (strict) {
      throw new Error(`mental send state lookup failed (${response ? response.status : "no response"})`);
    }
    return { sentTodayCount: 0, lastSentMs: null };
  }
  const rows = await response.json().catch(() => null);
  if (!Array.isArray(rows)) {
    if (strict) throw new Error("mental send state lookup returned no rows array");
    return { sentTodayCount: 0, lastSentMs: null };
  }
  const parsedRows = rows.map((row) => ({ ...row, sentMs: Date.parse(row.sent_at) }))
    .filter((row) => Number.isFinite(row.sentMs) && row.sentMs <= nowMs);
  const capRows = parsedRows.filter((row) => row.sentMs >= nowMs - MENTAL_SEND_WINDOW_MS);
  const recentTemplateRows = parsedRows.filter((row) => row.sentMs >= nowMs - MENTAL_TEMPLATE_DEDUPE_WINDOW_MS);
  return {
    sentTodayCount: capRows.length,
    lastSentMs: capRows.length ? Math.max(...capRows.map((row) => row.sentMs)) : null,
    sentFamilies: [...new Set(capRows.map((row) => row.family).filter(Boolean))],
    recentQuoteIds: recentTemplateRows.map((row) => row.template_id).filter(Boolean),
    sentWindows: capRows.map((row) => row.window).filter(Boolean),
  };
}

// Best-effort by contract: the message has already been delivered by the time this runs, so a failed
// write costs the cap one unit of accuracy and never rolls a sent message back. Returns whether the
// row landed so callers can say so honestly instead of assuming.
async function recordMentalSend(uid, triggerOrMeta, messageId, supa, fetchImpl) {
  const url = supa && (supa.url || supa.supaUrl);
  const key = supa && (supa.key || supa.supaKey);
  if (!url || !key) return false;
  const f = fetchImpl || globalThis.fetch;
  const meta = triggerOrMeta && typeof triggerOrMeta === "object"
    ? triggerOrMeta
    : { trigger: triggerOrMeta, family: "legacy", templateId: String(triggerOrMeta || "legacy"), localDay: null, window: "legacy" };
  const body = {
    uid,
    trigger: String(meta.trigger || meta.window || "legacy"),
    family: String(meta.family || "legacy"),
    template_id: String(meta.templateId || "legacy"),
    window: String(meta.window || "legacy"),
    telegram_message_id: String(messageId),
  };
  if (meta.localDay) body.local_day = String(meta.localDay);
  const response = await f(`${supaBase(url)}/rest/v1/lm_mental_send_log`, {
    method: "POST",
    headers: authHeaders(key, { "Content-Type": "application/json", Prefer: "return=minimal" }),
    body: JSON.stringify(body),
  }).catch(() => null);
  return Boolean(response && response.status === 201);
}

module.exports = { MENTAL_SEND_WINDOW_MS, MENTAL_TEMPLATE_DEDUPE_WINDOW_MS, readMentalSendState, recordMentalSend };
