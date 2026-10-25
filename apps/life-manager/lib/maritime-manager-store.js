"use strict";

const UID = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SUBJECT = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SHA = /^[0-9a-f]{40}$/;
const SELECT = "uid,auth_subject,email,timezone,status,source,consent_version,consent_v2_at,agent_id,release_sha,paused_at,created_at";
const { MANAGER_CONSENT_VERSION } = require("./maritime-distribution.js");
function invalid() { throw new Error("maritime_manager_input_invalid"); }
function identifier(value, pattern) {
  if (typeof value !== "string" || !pattern.test(value)) invalid();
  return value;
}
function bounded(value, max) {
  if (typeof value !== "string" || !value.trim() || value.length > max || /[\r\n]/.test(value)) invalid();
  return value.trim();
}
function timestampIso(value, nullable = false) {
  if (value == null && nullable) return null;
  const date = value instanceof Date ? value : new Date(String(value));
  if (!Number.isFinite(date.getTime())) throw new Error("maritime_manager_store_invalid");
  return date.toISOString();
}
function dateKeyString(value) {
  if (value instanceof Date) {
    if (!Number.isFinite(value.getTime())) throw new Error("maritime_manager_store_invalid");
    return value.toISOString().slice(0, 10);
  }
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value) return value;
  throw new Error("maritime_manager_store_invalid");
}

// Service-owned storage only. Public handlers must derive uid from verified auth.
function createMaritimeManagerStore(options = {}) {
  const env = options.env || process.env;
  const root = String(options.supaUrl || env.SUPABASE_URL || "").replace(/\/$/, "");
  const key = options.supaKey || env.SUPABASE_SERVICE_ROLE_KEY;
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  const pgPool = options.pgPool;
  const now = options.now || (() => new Date().toISOString());
  async function queryPg(statement, values) {
    if (!pgPool || typeof pgPool.query !== "function") throw new Error("maritime_manager_store_unconfigured");
    let result;
    try { result = await pgPool.query(statement, values); }
    catch { throw new Error("maritime_manager_store_unavailable"); }
    if (!result || !Array.isArray(result.rows)) throw new Error("maritime_manager_store_invalid");
    return result.rows;
  }
  async function request(path, method = "GET", body, prefer, signal) {
    if (!root || !key) throw new Error("maritime_manager_store_unconfigured");
    let response;
    try {
      response = await fetchImpl(`${root}/rest/v1/${path}`, {
        method, ...(signal ? { signal } : {}), headers: { apikey: key, Authorization: `Bearer ${key}`, "Content-Type": "application/json",
          Prefer: prefer || "return=representation" },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
    } catch { throw new Error("maritime_manager_store_unavailable"); }
    if (!response?.ok) throw new Error("maritime_manager_store_unavailable");
    try { return await response.json(); }
    catch { throw new Error("maritime_manager_store_invalid"); }
  }
  async function read(uid, { signal } = {}) {
    identifier(uid, UID);
    const rows = await queryPg(
      `SELECT ${SELECT} FROM public.lm_maritime_manager_enrollments WHERE uid = $1 LIMIT 2`, [uid],
    );
    if (rows.length > 1 || (rows[0] && rows[0].uid !== uid)) {
      throw new Error("maritime_manager_store_invalid");
    }
    if (!rows[0]) return null;
    return { ...rows[0], consent_v2_at: timestampIso(rows[0].consent_v2_at, true),
      paused_at: timestampIso(rows[0].paused_at, true), created_at: timestampIso(rows[0].created_at) };
  }
  async function listPending(limit = 20) {
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) invalid();
    const rows = await queryPg(
      `SELECT ${SELECT} FROM public.lm_maritime_manager_enrollments WHERE status IN ('pending', 'provisioning') AND paused_at IS NULL AND agent_id IS NULL ORDER BY created_at ASC, uid ASC LIMIT $1`,
      [limit],
    );
    if (rows.length > limit || rows.some(row => !row || !UID.test(row.uid)
      || !['pending', 'provisioning'].includes(row.status) || row.paused_at !== null || row.agent_id !== null || !SHA.test(row.release_sha))) {
      throw new Error('maritime_manager_store_invalid');
    }
    return rows.map(row => ({ ...row, created_at: timestampIso(row.created_at) }));
  }
  async function listReconsentedActive(limit = 20, afterUid = null) {
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) invalid();
    if (afterUid !== null) identifier(afterUid, UID);
    const rows = await queryPg(
      `SELECT ${SELECT} FROM public.lm_maritime_manager_enrollments
       WHERE status = 'active' AND consent_version = $1 AND consent_v2_at IS NOT NULL
         AND paused_at IS NULL AND agent_id IS NOT NULL AND ($2::text IS NULL OR uid > $2)
       ORDER BY uid ASC LIMIT $3`,
      [MANAGER_CONSENT_VERSION, afterUid, limit],
    );
    if (rows.length > limit) throw new Error('maritime_manager_store_invalid');
    let previous = afterUid;
    for (const row of rows) {
      if (!row || !UID.test(row.uid) || row.status !== 'active' || row.consent_version !== MANAGER_CONSENT_VERSION
        || !Number.isFinite(Date.parse(timestampIso(row.consent_v2_at))) || row.paused_at !== null
        || typeof row.agent_id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(row.agent_id)
        || !SHA.test(row.release_sha) || (previous !== null && row.uid <= previous)) {
        throw new Error('maritime_manager_store_invalid');
      }
      previous = row.uid;
    }
    return rows.map(row => ({ ...row, consent_v2_at: timestampIso(row.consent_v2_at),
      paused_at: timestampIso(row.paused_at, true), created_at: timestampIso(row.created_at) }));
  }
  async function listPaused(limit = 20, afterUid = null) {
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) invalid();
    if (afterUid !== null) identifier(afterUid, UID);
    const rows = await queryPg(
      `SELECT uid,status,paused_at,agent_id,release_sha FROM public.lm_maritime_manager_enrollments WHERE status = $1 AND paused_at IS NOT NULL AND ($2::text IS NULL OR uid > $2) ORDER BY uid ASC LIMIT $3`,
      ["paused", afterUid, limit],
    );
    if (rows.length > limit) throw new Error("maritime_manager_store_invalid");
    let previous = afterUid;
    for (const row of rows) {
      if (!row || !UID.test(row.uid) || row.status !== "paused" || row.paused_at == null || !SHA.test(row.release_sha)
        || (row.agent_id !== null && !/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(row.agent_id))
        || (previous !== null && row.uid <= previous)) throw new Error("maritime_manager_store_invalid");
      timestampIso(row.paused_at);
      previous = row.uid;
    }
    return rows.map(row => ({ ...row, paused_at: timestampIso(row.paused_at) }));
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
    const inserted = await queryPg(
      `INSERT INTO public.lm_maritime_manager_enrollments
        (uid,auth_subject,email,timezone,status,source,consent_version,release_sha)
       SELECT i.uid,i.auth_subject,$3,$4,'pending',$5,$6,$7
       FROM public.lm_maritime_manager_identities AS i
       WHERE i.uid=$1 AND i.auth_subject=$2
       ON CONFLICT (uid) DO NOTHING RETURNING uid`,
      [uid, authSubject, email, timezone, source, consentVersion, releaseSha],
    );
    if (inserted.length > 1) throw new Error("maritime_manager_store_invalid");
    const row = await read(uid);
    if (!row || row.auth_subject !== authSubject || row.email !== email) {
      throw new Error("maritime_manager_identity_mismatch");
    }
    return row;
  }
  async function reconsent(input) {
    const uid = identifier(input?.uid, UID);
    const authSubject = identifier(input?.authSubject, SUBJECT).toLowerCase();
    if (input?.consentVersion !== MANAGER_CONSENT_VERSION) invalid();
    const rows = await queryPg(
      `UPDATE public.lm_maritime_manager_enrollments
       SET consent_version = $3, consent_v2_at = COALESCE(consent_v2_at, clock_timestamp())
       WHERE uid = $1 AND auth_subject = $2 AND consent_version = 'maritime-manager-v1'
         AND status IN ('pending', 'provisioning', 'active') AND paused_at IS NULL
         AND ((status = 'active' AND agent_id IS NOT NULL)
           OR (status IN ('pending', 'provisioning') AND agent_id IS NULL))
       RETURNING ${SELECT}`,
      [uid, authSubject, MANAGER_CONSENT_VERSION],
    );
    if (rows.length > 1 || (rows[0] && (rows[0].uid !== uid || rows[0].auth_subject !== authSubject
      || rows[0].consent_version !== MANAGER_CONSENT_VERSION || rows[0].paused_at != null
      || !Number.isFinite(Date.parse(timestampIso(rows[0].consent_v2_at)))
      || (rows[0].status === "active" ? !rows[0].agent_id
        : (!["pending", "provisioning"].includes(rows[0].status) || rows[0].agent_id != null))))) {
      throw new Error("maritime_manager_store_invalid");
    }
    return rows[0] ? { ...rows[0], consent_v2_at: timestampIso(rows[0].consent_v2_at),
      paused_at: timestampIso(rows[0].paused_at, true), created_at: timestampIso(rows[0].created_at) } : null;
  }
  async function claimProvision(uid) {
    identifier(uid, UID);
    const rows = await queryPg("SELECT public.claim_lm_maritime_manager_provision_v1($1) AS claimed", [uid]);
    if (rows.length !== 1 || typeof rows[0].claimed !== "boolean") throw new Error("maritime_manager_store_invalid");
    return rows[0].claimed;
  }
  async function bindAgent({ uid, authSubject, agentId, releaseSha }) {
    identifier(uid, UID); authSubject = identifier(authSubject, SUBJECT).toLowerCase(); identifier(releaseSha, SHA);
    identifier(agentId, /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/);
    const rows = await queryPg(
      "SELECT public.bind_lm_maritime_manager_agent_v1($1,$2,$3,$4) AS bound",
      [uid, authSubject, agentId, releaseSha],
    );
    if (rows.length !== 1 || typeof rows[0].bound !== "boolean") throw new Error("maritime_manager_store_invalid");
    if (rows[0].bound !== true) throw new Error("maritime_manager_binding_rejected");
    const row = await read(uid);
    if (!row || row.auth_subject !== authSubject || row.agent_id !== agentId || row.release_sha !== releaseSha
      || (row.paused_at !== null ? row.status !== "paused" : row.status !== "active")) {
      throw new Error("maritime_manager_binding_rejected");
    }
    return row;
  }
  async function quarantinePendingProvision(uid) {
    identifier(uid, UID);
    const rows = await queryPg(
      `UPDATE public.lm_maritime_manager_enrollments SET status = $2
       WHERE uid = $1 AND status IN ('pending', 'provisioning') AND paused_at IS NULL AND agent_id IS NULL RETURNING ${SELECT}`,
      [uid, "effect_unknown"],
    );
    if (rows.length > 1 || (rows[0] && (rows[0].uid !== uid
      || rows[0].status !== "effect_unknown" || rows[0].agent_id !== null || rows[0].paused_at !== null))) {
      throw new Error("maritime_manager_store_invalid");
    }
    return rows[0] ? { ...rows[0], paused_at: timestampIso(rows[0].paused_at, true), created_at: timestampIso(rows[0].created_at) } : null;
  }
  async function pause(uid) {
    identifier(uid, UID);
    const pausedAt = now();
    if (!Number.isFinite(Date.parse(pausedAt))) invalid();
    const rows = await queryPg(
      "UPDATE public.lm_maritime_manager_enrollments SET status = 'paused', paused_at = $2 WHERE uid = $1 AND paused_at IS NULL RETURNING uid",
      [uid, pausedAt],
    );
    if (rows.length > 1 || (rows[0] && rows[0].uid !== uid)) {
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
    const rows = await queryPg(
      "SELECT uid,occurrence_id,agent_id,date_key::text AS date_key,release_sha,execution_id FROM public.lm_maritime_manager_executions WHERE uid=$1 AND occurrence_id=$2 LIMIT 2",
      [identity.p_uid, identity.p_occurrence_id],
    );
    if (rows.length > 1) throw new Error("maritime_manager_store_invalid");
    const raw = rows[0];
    const row = raw ? { ...raw, date_key: dateKeyString(raw.date_key) } : null;
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
    const rows = await queryPg(
      "SELECT public.claim_lm_maritime_manager_cycle_v1($1,$2,$3,$4,$5::date) AS claimed",
      [identity.p_uid, identity.p_occurrence_id, identity.p_agent_id, identity.p_release_sha, identity.p_date_key],
    );
    if (rows.length !== 1 || typeof rows[0].claimed !== "boolean") throw new Error("maritime_manager_store_invalid");
    const claimed = rows[0].claimed;
    const row = await readCycleDispatchIdentity(identity);
    if (claimed && !row) throw new Error("maritime_manager_store_invalid");
    return { claimed, row };
  }
  async function bindCycleExecution(input) {
    const identity = cycleIdentity(input);
    const executionId = identifier(input.executionId, /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/);
    const rows = await queryPg(
      "SELECT public.bind_lm_maritime_manager_execution_v1($1,$2,$3,$4,$5::date,$6) AS bound",
      [identity.p_uid, identity.p_occurrence_id, identity.p_agent_id, identity.p_release_sha, identity.p_date_key, executionId],
    );
    if (rows.length !== 1 || typeof rows[0].bound !== "boolean") throw new Error("maritime_manager_store_invalid");
    if (rows[0].bound !== true) throw new Error("maritime_manager_binding_rejected");
    const row = await readCycleDispatchIdentity(identity);
    if (!row || row.execution_id !== executionId) throw new Error("maritime_manager_binding_rejected");
    return row;
  }
  return Object.freeze({ enroll, reconsent, read, listPending, listReconsentedActive, listPaused, claimProvision, bindAgent, pause, quarantinePendingProvision,
    claimCycleDispatch, readCycleDispatch, bindCycleExecution });
}
module.exports = { createMaritimeManagerStore };
