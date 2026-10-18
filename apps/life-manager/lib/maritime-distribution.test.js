"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { createHmac } = require("node:crypto");
const {
  normalizeMaritimeSource,
  parseMaritimeStartPayload,
  createMaritimeDistributionStore,
} = require("./maritime-distribution.js");

test("deep-link source is allowlisted and malformed payloads do not become campaign tags", () => {
  assert.equal(normalizeMaritimeSource("community"), "community");
  assert.equal(normalizeMaritimeSource("../../attacker"), "other");
  assert.deepEqual(parseMaritimeStartPayload("/start maritime_community"), { source: "community" });
  assert.deepEqual(parseMaritimeStartPayload("/start@LifeManagerBot maritime_referral"), { source: "referral" });
  assert.equal(parseMaritimeStartPayload("/startmaritime_community"), null);
  assert.equal(parseMaritimeStartPayload("/start maritime_community?redirect=https://evil.example"), null);
});

test("landing and Telegram starts retain only an allowlisted campaign source", async () => {
  const events = [];
  const store = createMaritimeDistributionStore({
    env: { LM_UID_SECRET: "fixture-secret" },
    supaUrl: "https://fixture.supabase.co",
    supaKey: "fixture-service-role",
    fetchImpl: async () => { throw new Error("anonymous funnel events must use the event writer"); },
    recordEventImpl: async (event) => { events.push(event); return true; },
  });

  assert.equal(await store.recordAnonymousEvent("maritime_landing_view", "discord"), true);
  assert.equal(await store.recordAnonymousEvent("landing_view", "discord"), false);
  assert.equal(await store.recordStart("telegram-987654321", "discord"), true);
  assert.deepEqual(events.map((event) => event.eventName), ["maritime_landing_view", "maritime_start"]);
  assert.deepEqual(events[0].attribution, {
    utm_source: "maritime-discord", utm_medium: "web", utm_campaign: "the-first-1000",
  });
  assert.equal(events[1].sourceObjectId.length, 64);
  assert.doesNotMatch(JSON.stringify(events), /telegram-987654321/);
});

test("consent recovers the first Telegram source from the HMAC-keyed start event", async () => {
  const requested = [];
  const uid = "telegram-987654321";
  const participantId = createHmac("sha256", "fixture-secret")
    .update(`maritime:participant:${uid}`)
    .digest("hex");
  let sourceEventPresent = true;
  const store = createMaritimeDistributionStore({
    env: { LM_UID_SECRET: "fixture-secret" },
    supaUrl: "https://fixture.supabase.co",
    supaKey: "fixture-service-role",
    fetchImpl: async (input) => {
      const url = new URL(String(input));
      requested.push(url);
      if (url.pathname === "/rest/v1/lm_web_funnel_events") {
        return {
          ok: true,
          status: 200,
          json: async () => sourceEventPresent ? [{ attribution: { utm_source: "maritime-discord" } }] : [],
        };
      }
      throw new Error(`unexpected request ${url.pathname}`);
    },
  });

  assert.equal(typeof store.startSource, "function");
  assert.equal(await store.startSource(uid), "discord");
  assert.equal(requested[0].searchParams.get("source_object_id"), `eq.${participantId}`);
  assert.equal(requested[0].searchParams.get("event_name"), "eq.maritime_start");
  assert.doesNotMatch(requested[0].toString(), /telegram-987654321/);
  sourceEventPresent = false;
  assert.equal(await store.startSource(uid), null, "no recorded notice must not be treated as a consented source");
});

test("consent and milestones use HMAC participant ids and persist no Telegram identity or message text", async () => {
  const calls = [];
  const events = [];
  const participantId = createHmac("sha256", "fixture-secret")
    .update("maritime:participant:telegram-987654321")
    .digest("hex");
  let participant = null;
  let nowMs = Date.parse("2026-10-18T00:00:00.000Z");
  const fetchImpl = async (input, init = {}) => {
    const url = new URL(String(input));
    const method = String(init.method || "GET").toUpperCase();
    const body = init.body ? JSON.parse(init.body) : null;
    calls.push({ path: url.pathname, method, body, search: url.search });
    if (url.pathname === "/rest/v1/rpc/claim_lm_maritime_participant_v1" && method === "POST") {
      participant = {
        participant_id: body.p_participant_id,
        source: body.p_source,
        consent_version: body.p_consent_version,
        consented_at: "2026-10-18T00:00:00.000Z",
        revoked_at: null,
        first_response_at: null,
        returned_at: null,
      };
      return { ok: true, status: 200, json: async () => "consented" };
    }
    if (url.pathname === "/rest/v1/lm_maritime_pilot_participants" && method === "GET") {
      return { ok: true, status: 200, json: async () => participant ? [{ ...participant }] : [] };
    }
    if (url.pathname === "/rest/v1/rpc/mark_lm_maritime_pilot_milestone_v1" && method === "POST") {
      const key = body.p_milestone === "first_response" ? "first_response_at" : "returned_at";
      const sevenDaysMs = 7 * 24 * 60 * 60 * 1000;
      const tooSoon = body.p_milestone === "return_7d"
        && (!participant?.first_response_at || Date.parse(body.p_at) - Date.parse(participant.first_response_at) < sevenDaysMs);
      if (!participant || participant.revoked_at || participant[key] || tooSoon) {
        return { ok: true, status: 200, json: async () => false };
      }
      participant[key] = body.p_at;
      return { ok: true, status: 200, json: async () => true };
    }
    if (url.pathname === "/rest/v1/lm_maritime_pilot_participants" && method === "PATCH") {
      if (participant && !participant.revoked_at) {
        Object.assign(participant, body);
        return { ok: true, status: 200, json: async () => [{ ...participant }] };
      }
      return { ok: true, status: 200, json: async () => [] };
    }
    throw new Error(`unexpected request ${method} ${url.pathname}`);
  };
  const store = createMaritimeDistributionStore({
    env: { LM_UID_SECRET: "fixture-secret", MARITIME_PILOT_MAX_USERS: "25" },
    supaUrl: "https://fixture.supabase.co",
    supaKey: "fixture-service-role",
    fetchImpl,
    recordEventImpl: async (event) => { events.push(event); return true; },
    now: () => nowMs,
  });

  assert.deepEqual(await store.accept("telegram-987654321", "community"), { ok: true, status: "consented" });
  assert.equal(await store.isConsentActive("telegram-987654321"), true);
  assert.equal(await store.markMilestone("telegram-987654321", "first_response"), true);
  assert.equal(await store.markMilestone("telegram-987654321", "first_response"), false);
  assert.equal(await store.markMilestone("telegram-987654321", "return_7d"), false);
  nowMs += 7 * 24 * 60 * 60 * 1000;
  assert.equal(await store.markMilestone("telegram-987654321", "return_7d"), true);
  assert.equal(await store.revoke("telegram-987654321"), true);
  assert.equal(await store.isConsentActive("telegram-987654321"), false);

  const claim = calls.find((call) => call.path.endsWith("claim_lm_maritime_participant_v1"));
  assert.equal(claim.body.p_participant_id, participantId);
  assert.equal(claim.body.p_source, "community");
  assert.equal(claim.body.p_max_users, 25);
  assert.equal(Object.hasOwn(claim.body, "telegram_id"), false);
  assert.deepEqual(events.map((event) => event.eventName), [
    "maritime_consent", "maritime_first_response", "maritime_7day_return", "maritime_consent_revoked",
  ]);
  assert.ok(events.every((event) => event.uid == null && event.sourceObjectId === participantId));
  assert.doesNotMatch(JSON.stringify(events), /telegram-987654321|private prompt|private response/);
});

test("full cohort cap does not create a consent record or a provider milestone", async () => {
  const events = [];
  const store = createMaritimeDistributionStore({
    env: { LM_UID_SECRET: "fixture-secret", MARITIME_PILOT_MAX_USERS: "25" },
    supaUrl: "https://fixture.supabase.co",
    supaKey: "fixture-service-role",
    fetchImpl: async (input, init = {}) => {
      const url = new URL(String(input));
      if (url.pathname.endsWith("claim_lm_maritime_participant_v1") && init.method === "POST") {
        return { ok: true, status: 200, json: async () => "capacity_full" };
      }
      throw new Error(`unexpected request ${url.pathname}`);
    },
    recordEventImpl: async (event) => { events.push(event); return true; },
  });

  assert.deepEqual(await store.accept("new-participant", "referral"), { ok: false, status: "capacity_full" });
  assert.deepEqual(events, []);
});
