"use strict";

const { completeVoiceAllowance } = require("./managed-allowance.js");

const STALE_MS = 3 * 60 * 1000;

async function reconcileStaleVoiceAllowances({ supaUrl, supaKey, telnyxKey,
  fetchImpl = global.fetch, nowMs = Date.now(), offset = 0, pageSize = 20, timeoutMs = 10000 } = {}) {
  if (!supaUrl || !supaKey || !telnyxKey) throw new Error("voice reconciliation config missing");
  if (!Number.isInteger(offset) || offset < 0 || !Number.isInteger(pageSize) || pageSize < 1 || pageSize > 20
    || !Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 10000) {
    throw new Error("invalid voice reconciliation page");
  }
  const base = String(supaUrl).replace(/\/$/, "");
  const dbHeaders = { apikey: supaKey, Authorization: `Bearer ${supaKey}` };
  const timedFetch = (url, options = {}) => fetchImpl(url, { ...options, signal: AbortSignal.timeout(timeoutMs) });
  const read = async (url, headers = dbHeaders) => {
    const response = await timedFetch(url, { headers });
    if (!response.ok) {
      const error = new Error(`voice reconciliation read HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return response.json();
  };
  const query = (table, params) => {
    const url = new URL(`${base}/rest/v1/${table}`);
    for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
    return url;
  };
  const rows = await read(query("lm_voice_allowance_ledger", {
    select: "uid,call_key,period_start,reservation_token,reserved_seconds",
    status: "eq.accepted", created_at: `lt.${new Date(nowMs - STALE_MS).toISOString()}`,
    order: "created_at.asc,call_key.asc", limit: String(pageSize), offset: String(offset),
  }));
  if (!Array.isArray(rows)) throw new Error("voice reconciliation ledger response invalid");
  let settled = 0, errors = 0, rateLimited = false;
  for (const row of rows) {
    if (rateLimited) break;
    if (!row.uid || !row.call_key || !row.period_start || !row.reservation_token
      || !Number.isInteger(row.reserved_seconds) || row.reserved_seconds < 1) continue;
    try {
      const wakes = await read(query("lm_wake_log", {
        select: "telnyx_call_control_id,telnyx_call_session_id",
        uid: `eq.${row.uid}`, event_key: `eq.${row.call_key}`, limit: "2",
      }));
      if (wakes.length !== 1 || !wakes[0].telnyx_call_control_id || !wakes[0].telnyx_call_session_id) continue;
      const session = wakes[0].telnyx_call_session_id;
      const cdrUrl = new URL("https://api.telnyx.com/v2/detail_records");
      cdrUrl.searchParams.set("filter[record_type]", "call-control");
      cdrUrl.searchParams.set("filter[telnyx_session_id]", session);
      cdrUrl.searchParams.set("page[size]", "2");
      const result = await read(cdrUrl, { Authorization: `Bearer ${telnyxKey}` });
      if (!Array.isArray(result.data) || result.data.length !== 1 || result.meta?.total_results !== 1) continue;
      const cdr = result.data[0];
      const seconds = cdr.call_sec;
      const unanswered = cdr.connected === 0 && cdr.completed === 0
        && seconds === 0 && cdr.billed_sec === 0;
      const answered = cdr.connected === 1 && cdr.completed === 1
        && Number.isInteger(seconds) && seconds >= 0;
      if (cdr.telnyx_session_id !== session || cdr.record_type !== "call-control"
        || cdr.direction !== "outbound" || !cdr.finished_at
        || seconds > row.reserved_seconds || (!unanswered && !answered)) continue;
      const receipt = await completeVoiceAllowance(row.uid, row.call_key, base, supaKey, {
        fetchImpl: timedFetch,
        reservation: { periodStart: row.period_start, reservationToken: row.reservation_token },
        connectedSeconds: seconds,
      });
      if (receipt && receipt.allowed === true) settled += 1;
      else errors += 1;
    } catch (error) {
      errors += 1;
      if (error.status === 429) rateLimited = true;
    }
  }
  return { checked: rows.length, settled, errors,
    nextOffset: rateLimited ? offset : rows.length === pageSize
      ? (settled > 0 ? offset : offset + pageSize) : 0 };
}

module.exports = { reconcileStaleVoiceAllowances };
