"use strict";

const WRITER_TOKEN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function parseWriterStartPayload(text) {
  const value = String(text || "").trim();
  const match = value.match(/^\/start(?:@[A-Za-z0-9_]+)?\s+wr_([^\s]+)$/i);
  if (!match || !WRITER_TOKEN.test(match[1])) return null;
  return match[1].toLowerCase();
}

async function bindWriterAttribution(uid, token, supaUrl, supaKey, fetchImpl = fetch) {
  if (!uid || !WRITER_TOKEN.test(String(token || "")) || !supaUrl || !supaKey) return false;
  const url = `${String(supaUrl).replace(/\/$/, "")}/rest/v1/lm_users?uid=eq.${encodeURIComponent(uid)}&writer_attribution_ref=is.null`;
  const response = await fetchImpl(url, {
    method: "PATCH",
    headers: {
      apikey: supaKey,
      Authorization: `Bearer ${supaKey}`,
      "Content-Type": "application/json",
      Prefer: "return=minimal",
    },
    body: JSON.stringify({ writer_attribution_ref: String(token).toLowerCase() }),
  }).catch(() => null);
  return Boolean(response && (response.status === 200 || response.status === 204));
}

module.exports = { parseWriterStartPayload, bindWriterAttribution };
