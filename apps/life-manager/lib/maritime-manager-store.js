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
  async function listPending(limit = 20) {
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) invalid();
    const rows = await request(`lm_maritime_manager_enrollments?status=eq.pending&paused_at=is.null&agent_id=is.null&select=${SELECT}&order=created_at.asc,uid.asc&limit=${limit}`);
    if (!Array.isArray(rows) || rows.length > limit || rows.some(row => !row || !UID.test(row.uid)
      || row.status !== 'pending' || row.paused_at !== null || row.agent_id !== null || !SHA.test(row.release_sha))) {
      throw new Error('maritime_manager_store_invalid');
    }
    return rows;
  }
  async function listPaused(limit = 20, afterUid = null) {
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) invalid();
    if (afterUid !== null) identifier(afterUid, UID);
    const rows = await request(`lm_maritime_manager_enrollments?status=eq.paused&paused_at=not.is.null&select=uid,status,paused_at,agent_id,release_sha&order=uid.asc&limit=${limit}`
      + (afterUid === null ? "" : `&uid=gt.${encodeURIComponent(afterUid)}`));
    if (!Array.isArray(rows) || rows.length > limit) throw new Error("maritime_manager_store_invalid");
    let previous = afterUid;
    for (const row of rows) {
      if (!row || !UID.test(row.uid) || row.status !== "paused" || typeof row.paused_at !== "string"
        || !Number.isFinite(Date.parse(row.paused_at)) || !SHA.test(row.release_sha)
        || (row.agent_id !== null && !/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(row.agent_id))
        || (previous !== null && row.uid <= previous)) throw new Error("maritime_manager_store_invalid");
      previous = row.uid;
    }
    return rows;
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
  async function quarantinePendingProvision(uid) {
    identifier(uid, UID);
    const rows = await request(`lm_maritime_manager_enrollments?uid=eq.${encodeURIComponent(uid)}&status=eq.pending&paused_at=is.null&agent_id=is.null`,
      "PATCH", { status: "effect_unknown" });
    if (!Array.isArray(rows) || rows.length > 1 || (rows[0] && (rows[0].uid !== uid
      || rows[0].status !== "effect_unknown" || rows[0].agent_id !== null || rows[0].paused_at !== null))) {
      throw new Error("maritime_manager_store_invalid");
    }
    return rows[0] || null;
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
  function cycleIdentity(input) {
    const uid = identifier(input?.uid, UID);
    const occurrenceId = identifier(input.occurrenceId, /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/);
    const agentId = identifier(input.agentId, /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/);
    const releaseSha = identifier(input.releaseSha, SHA);
    const dateKey = input.dateKey;
    if (typeof dateKey !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(dateKey)
      || !Number.isFinite(Date.parse(dateKey)) || new Date(dateKey).toISOString().slice(0, 10) !== dateKey) invalid();
    return { p_uid: uid, p_occurrence_id: occurrenceId, p_agent_id: agentId,
      p_release_sha: releaseSha, p_date_key: dateKey };
  }
  async function readCycleDispatch(input) {
    return readCycleDispatchIdentity(cycleIdentity(input));
  }
  async function readCycleDispatchIdentity(identity) {
    const rows = await request(`lm_maritime_manager_executions?uid=eq.${encodeURIComponent(identity.p_uid)}`
      + `&occurrence_id=eq.${encodeURIComponent(identity.p_occurrence_id)}`
      + "&select=uid,occurrence_id,agent_id,date_key,release_sha,execution_id&limit=2");
    if (!Array.isArray(rows) || rows.length > 1) throw new Error("maritime_manager_store_invalid");
    const row = rows[0];
    if (row && (row.uid !== identity.p_uid || row.occurrence_id !== identity.p_occurrence_id
      || row.agent_id !== identity.p_agent_id || row.release_sha !== identity.p_release_sha
      || row.date_key !== identity.p_date_key || (row.execution_id !== null
        && (typeof row.execution_id !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(row.execution_id))))) {
      throw new Error("maritime_manager_binding_rejected");
    }
    return row || null;
  }
  async function claimCycleDispatch(input) {
    const identity = cycleIdentity(input);
    const claimed = await request("rpc/claim_lm_maritime_manager_cycle_v1", "POST", identity);
    if (typeof claimed !== "boolean") throw new Error("maritime_manager_store_invalid");
    const row = await readCycleDispatchIdentity(identity);
    if (claimed && !row) throw new Error("maritime_manager_store_invalid");
    return { claimed, row };
  }
  async function bindCycleExecution(input) {
    const identity = cycleIdentity(input);
    const executionId = identifier(input.executionId, /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/);
    const bound = await request("rpc/bind_lm_maritime_manager_execution_v1", "POST", {
      ...identity, p_execution_id: executionId,
    });
    if (bound !== true) throw new Error("maritime_manager_binding_rejected");
    const row = await readCycleDispatchIdentity(identity);
    if (!row || row.execution_id !== executionId) throw new Error("maritime_manager_binding_rejected");
    return row;
  }
  return Object.freeze({ enroll, read, listPending, listPaused, claimProvision, bindAgent, pause, quarantinePendingProvision,
    claimCycleDispatch, readCycleDispatch, bindCycleExecution });
}
module.exports = { createMaritimeManagerStore };
