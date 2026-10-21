"use strict";

const { separateWebUidForSubject } = require("./web-auth.js");
const { sanitizeWebAttribution } = require("./web-attribution.js");
const { normalizeWebFunnelEvent } = require("./web-funnel-events.js");
const { CONSENT_VERSION, normalizeMaritimeSource, createMaritimeDistributionStore } = require("./maritime-distribution.js");
const UID = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const CFO_HASH = /^[a-f0-9]{64}$/;
function timestampIso(value, nullable = false) {
  if (value == null && nullable) return null;
  const date = value instanceof Date ? value : new Date(String(value));
  if (!Number.isFinite(date.getTime())) throw new Error("maritime_manager_persistence_invalid");
  return date.toISOString();
}
function cfoIdentity(value) {
  if (typeof value?.uid !== "string" || !UID.test(value.uid)
    || typeof value.periodKey !== "string" || !value.periodKey.trim()
    || value.periodKey.length > 160 || /[\r\n]/.test(value.periodKey)) {
    throw new Error("maritime_manager_persistence_invalid");
  }
  return { uid: value.uid, periodKey: value.periodKey };
}
function cfoReceiptRow(row, identity) {
  const observedAt = timestampIso(row.observed_at);
  const sentAt = timestampIso(row.sent_at, true);
  if (row.uid !== identity.uid || row.period_key !== identity.periodKey || row.channel !== "email"
    || !CFO_HASH.test(row.recipient_hash || "") || typeof row.message !== "string"
    || !["pending", "sent"].includes(row.status)
    || (row.status === "pending" && (row.provider_message_id !== null || sentAt !== null))
    || (row.status === "sent" && (typeof row.provider_message_id !== "string"
      || !row.provider_message_id || sentAt === null))) {
    throw new Error("maritime_manager_persistence_invalid");
  }
  return { ...row, observed_at: observedAt, sent_at: sentAt };
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

  async function readFirstCompletedWorkAt(uid) {
    if (typeof uid !== "string" || !UID.test(uid)) throw new Error("maritime_manager_identity_mismatch");
    const participantId = distributionStore.participantId(uid);
    if (!/^[a-f0-9]{64}$/.test(participantId || "")) throw new Error("maritime_manager_identity_mismatch");
    const rows = await query(
      `SELECT min(occurred_at) AS first_completed_work_at FROM public.lm_web_funnel_events
       WHERE source_object_id=$1 AND event_name=$2 AND audience_kind=$3`,
      [participantId, "maritime_work_completed", "external"],
    );
    if (rows.length !== 1) throw new Error("maritime_manager_persistence_invalid");
    return timestampIso(rows[0].first_completed_work_at, true);
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

  async function readCfoReceipt(input) {
    const identity = cfoIdentity(input);
    const rows = await query(
      `SELECT uid,period_key,channel,recipient_hash,status,message,observed_at,provider_message_id,sent_at
       FROM public.lm_cfo_result_receipts WHERE uid=$1 AND period_key=$2 LIMIT 2`,
      [identity.uid, identity.periodKey],
    );
    if (rows.length > 1) throw new Error("maritime_manager_persistence_invalid");
    return rows.length ? cfoReceiptRow(rows[0], identity) : null;
  }

  async function claimCfoReceipt(input, payload) {
    const identity = cfoIdentity(input);
    if (payload?.uid !== identity.uid || payload.period_key !== identity.periodKey
      || payload.channel !== "email" || payload.status !== "pending"
      || !CFO_HASH.test(payload.recipient_hash || "") || typeof payload.message !== "string") {
      throw new Error("maritime_manager_persistence_invalid");
    }
    const observedAt = timestampIso(payload.observed_at);
    const rows = await query(
      `INSERT INTO public.lm_cfo_result_receipts
        (uid,period_key,channel,recipient_hash,status,message,observed_at)
       VALUES ($1,$2,'email',$3,'pending',$4,$5::timestamptz)
       ON CONFLICT (uid,period_key) DO NOTHING RETURNING uid`,
      [identity.uid, identity.periodKey, payload.recipient_hash, payload.message, observedAt],
    );
    if (rows.length > 1) throw new Error("maritime_manager_persistence_invalid");
    return rows.length === 1;
  }

  async function markCfoReceipt(input, payload) {
    const identity = cfoIdentity(input);
    if (payload?.status !== "sent" || typeof payload.provider_message_id !== "string"
      || !payload.provider_message_id || payload.provider_message_id.length > 255
      || /[\r\n]/.test(payload.provider_message_id)) {
      throw new Error("maritime_manager_persistence_invalid");
    }
    const sentAt = timestampIso(payload.sent_at);
    const rows = await query(
      `UPDATE public.lm_cfo_result_receipts SET status='sent',provider_message_id=$3,sent_at=$4::timestamptz
       WHERE uid=$1 AND period_key=$2 AND status='pending' RETURNING uid`,
      [identity.uid, identity.periodKey, payload.provider_message_id, sentAt],
    );
    if (rows.length !== 1 || rows[0].uid !== identity.uid) throw new Error("cfo_receipt_claim_lost");
    return true;
  }

  const cfoReceiptIO = Object.freeze({ read: readCfoReceipt, claim: claimCfoReceipt, mark: markCfoReceipt });

  return Object.freeze({ ensureWebUserImpl, storeFirstTouch, readFirstTouch, readFirstCompletedWorkAt,
    participantId: distributionStore.participantId,
    recordManagerEvent: distributionStore.recordManagerEvent,
    recordAnonymousEvent: distributionStore.recordAnonymousEvent,
    getParticipant,
    accept,
    isConsentActive,
    revoke,
    cfoReceiptIO });
}

module.exports = { createMaritimeManagerPersistence };
