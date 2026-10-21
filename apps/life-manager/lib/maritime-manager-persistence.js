"use strict";

const { separateWebUidForSubject } = require("./web-auth.js");
const { sanitizeWebAttribution } = require("./web-attribution.js");
const UID = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function createMaritimeManagerPersistence(options = {}) {
  const pgPool = options.pgPool;
  const now = options.now || (() => new Date().toISOString());

  async function query(statement, values) {
    if (!pgPool || typeof pgPool.query !== "function") {
      throw new Error("maritime_manager_persistence_unconfigured");
    }
    let result;
    try { result = await pgPool.query(statement, values); }
    catch { throw new Error("maritime_manager_persistence_unavailable"); }
    if (!result || !Array.isArray(result.rows)) throw new Error("maritime_manager_persistence_invalid");
    return result.rows;
  }

  async function ensureWebUserImpl(subject) {
    const uid = separateWebUidForSubject(subject);
    const authSubject = String(subject).toLowerCase();
    await query(
      "INSERT INTO public.lm_maritime_manager_identities(uid,auth_subject) VALUES ($1,$2) ON CONFLICT DO NOTHING",
      [uid, authSubject],
    );
    const rows = await query(
      "SELECT uid,auth_subject FROM public.lm_maritime_manager_identities WHERE auth_subject=$1 LIMIT 2",
      [authSubject],
    );
    if (rows.length !== 1 || rows[0].uid !== uid || String(rows[0].auth_subject).toLowerCase() !== authSubject) {
      throw new Error("maritime_manager_identity_mismatch");
    }
    return uid;
  }

  async function readFirstTouch(uid) {
    if (typeof uid !== "string" || !UID.test(uid)) throw new Error("maritime_manager_identity_mismatch");
    const rows = await query(
      "SELECT first_touch,first_touch_at FROM public.lm_maritime_manager_identities WHERE uid=$1 LIMIT 2",
      [uid],
    );
    if (rows.length > 1) throw new Error("maritime_manager_persistence_invalid");
    if (!rows.length) return {};
    const row = rows[0];
    if ((row.first_touch == null) !== (row.first_touch_at == null)) {
      throw new Error("maritime_manager_persistence_invalid");
    }
    return sanitizeWebAttribution(row.first_touch);
  }

  async function storeFirstTouch(uid, attribution) {
    if (typeof uid !== "string" || !UID.test(uid)) throw new Error("maritime_manager_identity_mismatch");
    const clean = sanitizeWebAttribution(attribution);
    if (!Object.keys(clean).length) return false;
    const rawNow = now();
    const timestamp = rawNow instanceof Date ? rawNow : new Date(rawNow);
    if (!Number.isFinite(timestamp.getTime())) throw new Error("maritime_manager_persistence_invalid");
    const rows = await query(
      `UPDATE public.lm_maritime_manager_identities SET first_touch=$2::jsonb,first_touch_at=$3::timestamptz
       WHERE uid=$1 AND first_touch IS NULL AND first_touch_at IS NULL RETURNING uid`,
      [uid, JSON.stringify(clean), timestamp.toISOString()],
    );
    if (rows.length > 1) throw new Error("maritime_manager_persistence_invalid");
    if (rows.length === 1) return true;
    return Object.keys(await readFirstTouch(uid)).length > 0;
  }

  return Object.freeze({ ensureWebUserImpl, storeFirstTouch, readFirstTouch });
}

module.exports = { createMaritimeManagerPersistence };
