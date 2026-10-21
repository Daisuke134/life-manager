"use strict";

const { separateWebUidForSubject } = require("./web-auth.js");

function createMaritimeManagerPersistence(options = {}) {
  const pgPool = options.pgPool;

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

  return Object.freeze({ ensureWebUserImpl });
}

module.exports = { createMaritimeManagerPersistence };
