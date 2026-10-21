"use strict";

const { separateWebUidForSubject } = require("./web-auth.js");
const { sanitizeWebAttribution } = require("./web-attribution.js");
const { normalizeWebFunnelEvent } = require("./web-funnel-events.js");
const { CONSENT_VERSION, normalizeMaritimeSource, createMaritimeDistributionStore } = require("./maritime-distribution.js");
const UID = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function timestampIso(value, nullable = false) {
  if (value == null && nullable) return null;
  const date = value instanceof Date ? value : new Date(String(value));
  if (!Number.isFinite(date.getTime())) throw new Error("maritime_manager_persistence_invalid");
  return date.toISOString();
}

function createMaritimeManagerPersistence(options = {}) {
  const pgPool = options.pgPool;
  const env = options.env || process.env;
  const now = options.now || (() => new Date().toISOString());
  const nowMs = options.nowMs || (() => Date.now());

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

  async function recordEventImpl(event, eventOptions = {}) {
    let row;
    try { row = normalizeWebFunnelEvent(event, eventOptions.nowMs == null ? Number(nowMs()) : eventOptions.nowMs); }
    catch { return false; }
    try {
      await query(
        `INSERT INTO public.lm_web_funnel_events
          (event_id,event_name,audience_kind,uid,source_object_id,source_event_id,attribution,amount_usd,currency,billing_reason,occurred_at)
         VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9,$10,$11::timestamptz)
         ON CONFLICT DO NOTHING RETURNING event_id`,
        [row.event_id, row.event_name, row.audience_kind || null, row.uid, row.source_object_id, row.source_event_id,
          JSON.stringify(row.attribution), row.amount_usd, row.currency, row.billing_reason, row.occurred_at],
      );
      return true;
    } catch { return false; }
  }

  const distributionStore = createMaritimeDistributionStore({ env, now: nowMs, recordEventImpl });
  async function getParticipant(uid) {
    const id = distributionStore.participantId(uid);
    if (!/^[a-f0-9]{64}$/.test(id || "")) return { ok: false, participant: null };
    try {
      const rows = await query(
        `SELECT participant_id,source,consent_version,consented_at,revoked_at,first_response_at,returned_at
         FROM public.lm_maritime_pilot_participants WHERE participant_id=$1 LIMIT 2`,
        [id],
      );
      if (rows.length > 1) return { ok: false, participant: null };
      if (!rows.length) return { ok: true, participant: null };
      const row = rows[0];
      if (row.participant_id !== id || row.source !== normalizeMaritimeSource(row.source)
        || row.consent_version !== CONSENT_VERSION) return { ok: false, participant: null };
      return { ok: true, participant: {
        ...row,
        consented_at: timestampIso(row.consented_at),
        revoked_at: timestampIso(row.revoked_at, true),
        first_response_at: timestampIso(row.first_response_at, true),
        returned_at: timestampIso(row.returned_at, true),
      } };
    } catch { return { ok: false, participant: null }; }
  }

  async function accept(uid, source) {
    const id = distributionStore.participantId(uid);
    const campaignSource = normalizeMaritimeSource(source);
    const maxUsers = distributionStore.maxUsers;
    if (!/^[a-f0-9]{64}$/.test(id || "") || !Number.isInteger(maxUsers)) return { ok: false, status: "unavailable" };
    const rawNow = nowMs();
    const at = rawNow instanceof Date ? rawNow : new Date(rawNow);
    if (!Number.isFinite(at.getTime())) return { ok: false, status: "unavailable" };
    try {
      const rows = await query(
        "SELECT public.claim_lm_maritime_participant_v1($1,$2,$3,$4,$5::timestamptz) AS status",
        [id, campaignSource, CONSENT_VERSION, maxUsers, at.toISOString()],
      );
      const status = rows.length === 1 ? rows[0].status : null;
      if (!["consented", "already_consented", "capacity_full"].includes(status)) return { ok: false, status: "unavailable" };
      if (status === "capacity_full") return { ok: false, status };
      await distributionStore.recordConsentEvent(uid, campaignSource, "web");
      return { ok: true, status };
    } catch { return { ok: false, status: "unavailable" }; }
  }

  async function isConsentActive(uid) {
    const result = await getParticipant(uid);
    const row = result.participant;
    return result.ok && Boolean(row && row.consent_version === CONSENT_VERSION && row.consented_at && !row.revoked_at);
  }

  async function revoke(uid) {
    const existing = await getParticipant(uid);
    const row = existing.participant;
    if (!existing.ok || !row || row.consent_version !== CONSENT_VERSION || !row.consented_at || row.revoked_at) return false;
    const rawNow = nowMs();
    const at = rawNow instanceof Date ? rawNow : new Date(rawNow);
    if (!Number.isFinite(at.getTime())) return false;
    const id = distributionStore.participantId(uid);
    let rows;
    try {
      rows = await query(
        `UPDATE public.lm_maritime_pilot_participants SET revoked_at=$2::timestamptz,updated_at=$2::timestamptz
         WHERE participant_id=$1 AND consent_version=$3 AND consented_at IS NOT NULL AND revoked_at IS NULL
         RETURNING participant_id`,
        [id, at.toISOString(), CONSENT_VERSION],
      );
    } catch { return false; }
    if (rows.length !== 1 || rows[0].participant_id !== id) return false;
    await distributionStore.recordConsentRevokedEvent(uid, row.source, "web");
    return true;
  }

  return Object.freeze({ ensureWebUserImpl, storeFirstTouch, readFirstTouch,
    participantId: distributionStore.participantId,
    recordManagerEvent: distributionStore.recordManagerEvent,
    recordAnonymousEvent: distributionStore.recordAnonymousEvent,
    getParticipant,
    accept,
    isConsentActive,
    revoke });
}

module.exports = { createMaritimeManagerPersistence };
