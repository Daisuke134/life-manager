"use strict";

function baseUrl(url) { return String(url).replace(/\/$/, ""); }
function headers(key, extra = {}) { return { apikey: key, Authorization: `Bearer ${key}`, ...extra }; }

async function readOutcomeSendState(uid, nowMs, supa, fetchImpl = globalThis.fetch, opts = {}) {
  const url = supa && (supa.url || supa.supaUrl);
  const key = supa && (supa.key || supa.supaKey);
  if (!url || !key) return { sentOutcomeIds: [], sentTodayCount: 0, lastSentMs: null };
  const since = new Date(nowMs - 24 * 60 * 60 * 1000).toISOString();
  const query = `uid=eq.${encodeURIComponent(uid)}&sent_at=gte.${encodeURIComponent(since)}`
    + "&select=source_outcome_id,sent_at&order=sent_at.desc";
  const response = await fetchImpl(`${baseUrl(url)}/rest/v1/lm_mental_outcome_send_log?${query}`, {
    headers: headers(key),
  }).catch(() => null);
  if (!response || !response.ok) {
    if (opts.strict) throw new Error(`outcome send state lookup failed (${response ? response.status : "no response"})`);
    return { sentOutcomeIds: [], sentTodayCount: 0, lastSentMs: null };
  }
  const rows = await response.json().catch(() => null);
  if (!Array.isArray(rows)) {
    if (opts.strict) throw new Error("outcome send state lookup returned no rows array");
    return { sentOutcomeIds: [], sentTodayCount: 0, lastSentMs: null };
  }
  const times = rows.map((row) => Date.parse(row.sent_at)).filter(Number.isFinite);
  return {
    sentOutcomeIds: rows.map((row) => String(row.source_outcome_id)),
    sentTodayCount: rows.length,
    lastSentMs: times.length ? Math.max(...times) : null,
  };
}

async function recordOutcomeSend(row, supa, fetchImpl = globalThis.fetch) {
  const url = supa && (supa.url || supa.supaUrl);
  const key = supa && (supa.key || supa.supaKey);
  if (!url || !key || !row || !row.uid || !row.sourceOutcomeId || !row.evidenceRef || !row.quoteId || !row.telegramMessageId) return false;
  const response = await fetchImpl(`${baseUrl(url)}/rest/v1/lm_mental_outcome_send_log`, {
    method: "POST",
    headers: headers(key, { "Content-Type": "application/json", Prefer: "return=minimal" }),
    body: JSON.stringify({
      uid: row.uid,
      source_outcome_id: row.sourceOutcomeId,
      evidence_ref: row.evidenceRef,
      quote_id: row.quoteId,
      telegram_message_id: String(row.telegramMessageId),
    }),
  }).catch(() => null);
  return Boolean(response && response.status === 201);
}

module.exports = { readOutcomeSendState, recordOutcomeSend };
