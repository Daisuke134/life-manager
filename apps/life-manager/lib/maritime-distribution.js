"use strict";

const { createHmac } = require("node:crypto");
const { recordWebFunnelEvent } = require("./web-funnel-events.js");

const DEFAULT_PUBLIC_MAX_USERS = 25;
const MAX_PUBLIC_USERS = 1000;
const CONSENT_VERSION = "maritime-retention-v1";
const PARTICIPANT_ID_RE = /^[a-f0-9]{64}$/;
const SOURCES = new Set([
  "landing", "aniccaai", "x", "reddit", "discord", "telegram", "community", "referral", "hackathon", "direct", "other",
]);
const ANONYMOUS_EVENTS = new Set(["maritime_landing_view", "maritime_cta_click"]);
const USER_EVENTS = new Set([
  "maritime_start", "maritime_consent", "maritime_consent_revoked",
  "maritime_first_response", "maritime_7day_return",
]);
const MILESTONES = Object.freeze({
  first_response: "maritime_first_response",
  return_7d: "maritime_7day_return",
});

function parseMaritimeMaxUsers(value) {
  if (value == null || String(value).trim() === "") return DEFAULT_PUBLIC_MAX_USERS;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 1 && parsed <= MAX_PUBLIC_USERS ? parsed : null;
}

function normalizeMaritimeSource(value) {
  const source = String(value || "").trim().toLowerCase();
  return SOURCES.has(source) ? source : "other";
}

function parseMaritimeStartPayload(value) {
  const text = String(value || "").trim();
  const match = /^\/start(?:@[A-Za-z0-9_]+)?\s+maritime_([a-z0-9_-]{1,40})$/i.exec(text);
  return match ? { source: normalizeMaritimeSource(match[1]) } : null;
}

function sourceAttribution(source, medium = "telegram") {
  return {
    utm_source: `maritime-${normalizeMaritimeSource(source)}`,
    utm_medium: medium,
    utm_campaign: "the-first-1000",
  };
}

function createMaritimeDistributionStore({
  env = process.env,
  supaUrl,
  supaKey,
  fetchImpl = globalThis.fetch,
  recordEventImpl = recordWebFunnelEvent,
  now = () => Date.now(),
} = {}) {
  const base = String(supaUrl || env.SUPABASE_URL || "").replace(/\/$/, "");
  const key = String(supaKey || env.SUPABASE_SERVICE_ROLE_KEY || "").trim();
  const uidSecret = String(env.LM_UID_SECRET || "");
  const maxUsers = parseMaritimeMaxUsers(env.MARITIME_PILOT_MAX_USERS);
  const headers = {
    apikey: key,
    Authorization: `Bearer ${key}`,
    "Content-Type": "application/json",
  };

  function ready() {
    return Boolean(base && key && uidSecret && typeof fetchImpl === "function");
  }

  function participantId(uid) {
    const value = String(uid || "");
    if (!value || value.length > 128 || !uidSecret) return null;
    return createHmac("sha256", uidSecret).update(`maritime:participant:${value}`).digest("hex");
  }

  async function writeEvent(eventName, { uid, source = "other", medium = "telegram" } = {}) {
    if (!ANONYMOUS_EVENTS.has(eventName) && !USER_EVENTS.has(eventName)) return false;
    if (typeof recordEventImpl !== "function") return false;
    const id = uid == null ? null : participantId(uid);
    if (uid != null && !id) return false;
    const event = {
      eventName,
      uid: null,
      sourceObjectId: id,
      ...(id ? { sourceEventId: `maritime:${id}:${eventName}` } : {}),
      attribution: sourceAttribution(source, medium),
      occurredAt: new Date(Number(now())).toISOString(),
    };
    try {
      return (await recordEventImpl(event, {
        supaUrl: base,
        supaKey: key,
        fetchImpl,
        nowMs: Number(now()),
      })) !== false;
    } catch { return false; }
  }

  async function recordAnonymousEvent(eventName, source) {
    if (!ANONYMOUS_EVENTS.has(eventName)) return false;
    return writeEvent(eventName, { source, medium: "web" });
  }

  async function recordStart(uid, source) {
    return writeEvent("maritime_start", { uid, source });
  }

  async function getParticipant(uid) {
    const id = participantId(uid);
    if (!ready() || !id || !PARTICIPANT_ID_RE.test(id)) return { ok: false, participant: null };
    const url = new URL(`${base}/rest/v1/lm_maritime_pilot_participants`);
    url.searchParams.set("participant_id", `eq.${id}`);
    url.searchParams.set("select", "participant_id,source,consent_version,consented_at,revoked_at,first_response_at,returned_at");
    url.searchParams.set("limit", "2");
    let response;
    try { response = await fetchImpl(url.toString(), { headers }); }
    catch { return { ok: false, participant: null }; }
    if (!response || !response.ok) return { ok: false, participant: null };
    const rows = await response.json().catch(() => null);
    if (!Array.isArray(rows) || rows.length > 1) return { ok: false, participant: null };
    return { ok: true, participant: rows[0] || null };
  }

  async function callRpc(name, body) {
    if (!ready()) return { ok: false, result: null };
    let response;
    try {
      response = await fetchImpl(`${base}/rest/v1/rpc/${name}`, {
        method: "POST", headers, body: JSON.stringify(body),
      });
    } catch { return { ok: false, result: null }; }
    if (!response || !response.ok) return { ok: false, result: null };
    return { ok: true, result: await response.json().catch(() => null) };
  }

  async function accept(uid, source) {
    const id = participantId(uid);
    const campaignSource = normalizeMaritimeSource(source);
    if (!ready() || !id || maxUsers == null) return { ok: false, status: "unavailable" };
    const result = await callRpc("claim_lm_maritime_participant_v1", {
      p_participant_id: id,
      p_source: campaignSource,
      p_consent_version: CONSENT_VERSION,
      p_max_users: maxUsers,
      p_now: new Date(Number(now())).toISOString(),
    });
    if (!result.ok || !["consented", "already_consented", "capacity_full"].includes(result.result)) {
      return { ok: false, status: "unavailable" };
    }
    if (result.result === "capacity_full") return { ok: false, status: "capacity_full" };
    await writeEvent("maritime_consent", { uid, source: campaignSource });
    return { ok: true, status: result.result };
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
    const id = participantId(uid);
    const revokedAt = new Date(Number(now())).toISOString();
    const url = new URL(`${base}/rest/v1/lm_maritime_pilot_participants`);
    url.searchParams.set("participant_id", `eq.${id}`);
    url.searchParams.set("revoked_at", "is.null");
    let response;
    try {
      response = await fetchImpl(url.toString(), {
        method: "PATCH",
        headers: { ...headers, Prefer: "return=representation" },
        body: JSON.stringify({ revoked_at: revokedAt, updated_at: revokedAt }),
      });
    } catch { return false; }
    if (!response || !response.ok) return false;
    const rows = await response.json().catch(() => null);
    if (!Array.isArray(rows) || rows.length !== 1) return false;
    await writeEvent("maritime_consent_revoked", { uid, source: row.source });
    return true;
  }

  async function markMilestone(uid, milestone) {
    const eventName = MILESTONES[milestone];
    const id = participantId(uid);
    if (!eventName || !id || !(await isConsentActive(uid))) return false;
    const result = await callRpc("mark_lm_maritime_pilot_milestone_v1", {
      p_participant_id: id,
      p_milestone: milestone,
      p_at: new Date(Number(now())).toISOString(),
    });
    if (!result.ok || result.result !== true) return false;
    const participant = await getParticipant(uid);
    await writeEvent(eventName, { uid, source: participant.participant?.source || "other" });
    return true;
  }

  return Object.freeze({
    maxUsers,
    participantId,
    getParticipant,
    recordAnonymousEvent,
    recordStart,
    accept,
    isConsentActive,
    revoke,
    markMilestone,
  });
}

module.exports = {
  CONSENT_VERSION,
  DEFAULT_PUBLIC_MAX_USERS,
  MAX_PUBLIC_USERS,
  parseMaritimeMaxUsers,
  normalizeMaritimeSource,
  parseMaritimeStartPayload,
  createMaritimeDistributionStore,
};
