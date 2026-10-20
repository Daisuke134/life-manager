"use strict";

const UID = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SUBJECT = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SHA = /^[0-9a-f]{40}$/;
const SELECT = "uid,auth_subject,email,timezone,status,source,consent_version,agent_id,release_sha,paused_at,created_at";
function invalid() { throw new Error("maritime_manager_input_invalid"); }
function identifier(value, pattern) {
  if (typeof value !== "string" || !pattern.test(value)) invalid();
  return value;
}
function bounded(value, max) {
  if (typeof value !== "string" || !value.trim() || value.length > max || /[\r\n]/.test(value)) invalid();
  return value.trim();
}

// Service-owned storage only. Public handlers must derive uid from verified auth.
function createMaritimeManagerStore(options = {}) {
  const env = options.env || process.env;
  const root = String(options.supaUrl || env.SUPABASE_URL || "").replace(/\/$/, "");
  const key = options.supaKey || env.SUPABASE_SERVICE_ROLE_KEY;
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  const now = options.now || (() => new Date().toISOString());
  async function request(path, method = "GET", body, prefer) {
    if (!root || !key) throw new Error("maritime_manager_store_unconfigured");
    let response;
    try {
      response = await fetchImpl(`${root}/rest/v1/${path}`, {
        method, headers: { apikey: key, Authorization: `Bearer ${key}`, "Content-Type": "application/json",
          Prefer: prefer || "return=representation" },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
    } catch { throw new Error("maritime_manager_store_unavailable"); }
    if (!response?.ok) throw new Error("maritime_manager_store_unavailable");
    try { return await response.json(); }
    catch { throw new Error("maritime_manager_store_invalid"); }
  }
  async function read(uid) {
    identifier(uid, UID);
    const rows = await request(`lm_maritime_manager_enrollments?uid=eq.${encodeURIComponent(uid)}&select=${SELECT}&limit=2`);
    if (!Array.isArray(rows) || rows.length > 1 || (rows[0] && rows[0].uid !== uid)) {
      throw new Error("maritime_manager_store_invalid");
    }
    return rows[0] || null;
  }
  async function enroll(input) {
    const uid = identifier(input?.uid, UID);
    const authSubject = identifier(input.authSubject, SUBJECT).toLowerCase();
    const email = bounded(input.email, 320).toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) invalid();
    const timezone = input.timezone || "UTC";
    try { new Intl.DateTimeFormat("en", { timeZone: timezone }); } catch { invalid(); }
    const source = bounded(input.source || "direct", 40);
    if (!/^[a-z0-9_-]+$/.test(source)) invalid();
    const consentVersion = bounded(input.consentVersion, 100);
    const releaseSha = identifier(input.releaseSha, SHA);
    await request("lm_maritime_manager_enrollments?on_conflict=uid", "POST", {
      uid, auth_subject: authSubject, email, timezone, source,
      consent_version: consentVersion, release_sha: releaseSha,
    }, "resolution=ignore-duplicates,return=representation");
    const row = await read(uid);
    if (!row || row.auth_subject !== authSubject || row.email !== email) {
      throw new Error("maritime_manager_identity_mismatch");
    }
    return row;
  }
  async function claimProvision(uid) {
    identifier(uid, UID);
    const result = await request("rpc/claim_lm_maritime_manager_provision_v1", "POST", { p_uid: uid });
    if (typeof result !== "boolean") throw new Error("maritime_manager_store_invalid");
    return result;
  }
  async function bindAgent({ uid, authSubject, agentId, releaseSha }) {
    identifier(uid, UID); authSubject = identifier(authSubject, SUBJECT).toLowerCase(); identifier(releaseSha, SHA);
    identifier(agentId, /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/);
    const bound = await request("rpc/bind_lm_maritime_manager_agent_v1", "POST", {
      p_uid: uid, p_auth_subject: authSubject, p_agent_id: agentId, p_release_sha: releaseSha,
    });
    if (bound !== true) throw new Error("maritime_manager_binding_rejected");
    const row = await read(uid);
    if (!row || row.auth_subject !== authSubject || row.agent_id !== agentId) {
      throw new Error("maritime_manager_binding_rejected");
    }
    return row;
  }
  async function pause(uid) {
    identifier(uid, UID);
    const pausedAt = now();
    if (!Number.isFinite(Date.parse(pausedAt))) invalid();
    const rows = await request(`lm_maritime_manager_enrollments?uid=eq.${encodeURIComponent(uid)}&paused_at=is.null`,
      "PATCH", { status: "paused", paused_at: pausedAt });
    if (!Array.isArray(rows) || rows.length > 1 || (rows[0] && rows[0].uid !== uid)) {
      throw new Error("maritime_manager_store_invalid");
    }
    return read(uid);
  }
  return Object.freeze({ enroll, read, claimProvision, bindAgent, pause });
}
module.exports = { createMaritimeManagerStore };
