"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { existsSync, readFileSync } = require("node:fs");
const { join } = require("node:path");
const { createHmac } = require("node:crypto");
const { chromium } = require("playwright-core");
const {
  normalizeMaritimeSource,
  renderMaritimeLanding,
  parseMaritimeStartPayload,
  createMaritimeDistributionStore,
} = require("./maritime-distribution.js");
const CHROMIUM_PATH = process.env.LM_TEST_CHROMIUM_PATH
  || ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"].find(existsSync);

test("deep-link source is allowlisted and malformed payloads do not become campaign tags", () => {
  assert.equal(normalizeMaritimeSource("community"), "community");
  assert.equal(normalizeMaritimeSource("../../attacker"), "other");
  assert.deepEqual(parseMaritimeStartPayload("/start maritime_community"), { source: "community" });
  assert.deepEqual(parseMaritimeStartPayload("/start maritime_direct"), { source: "direct" });
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
  let failNextMilestoneTransaction = false;
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
      if (failNextMilestoneTransaction) {
        failNextMilestoneTransaction = false;
        return { ok: false, status: 503, json: async () => null };
      }
      const sevenDaysMs = 7 * 24 * 60 * 60 * 1000;
      if (!participant || participant.revoked_at || body.p_milestone !== "successful_use") {
        return { ok: true, status: 200, json: async () => false };
      }
      let eventName;
      let eventAt = Date.parse(body.p_at);
      if (!participant.first_response_at) {
        eventName = "maritime_first_response";
        participant.first_response_at = new Date(eventAt).toISOString();
      } else if (!participant.returned_at) {
        const firstAt = Date.parse(participant.first_response_at);
        eventAt = Math.max(eventAt, firstAt + 1);
        if (eventAt > firstAt + sevenDaysMs) return { ok: true, status: 200, json: async () => false };
        eventName = "maritime_7day_return";
        participant.returned_at = new Date(eventAt).toISOString();
      } else {
        return { ok: true, status: 200, json: async () => false };
      }
      events.push({ eventName, uid: null, sourceObjectId: participantId, occurredAt: new Date(eventAt).toISOString() });
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
  failNextMilestoneTransaction = true;
  assert.equal(await store.recordSuccessfulUse("telegram-987654321"), false);
  assert.equal(participant.first_response_at, null, "a failed RPC transaction must roll back the milestone");
  assert.equal(events.some((event) => event.eventName === "maritime_first_response"), false);
  assert.equal(await store.recordSuccessfulUse("telegram-987654321"), true);
  nowMs += 7 * 24 * 60 * 60 * 1000;
  participant.returned_at = null;
  assert.equal(await store.recordSuccessfulUse("telegram-987654321"), true, "the exact 7-day boundary is included");
  nowMs += 1;
  participant.returned_at = null;
  assert.equal(await store.recordSuccessfulUse("telegram-987654321"), false, "use after 7 days is excluded");
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

test("milestone RPC updates participant and appends its funnel event in one transaction", () => {
  const migration = readFileSync(join(__dirname, "../migrations/2026-10-18-lm-maritime-distribution.sql"), "utf8");
  const routine = migration.match(/CREATE OR REPLACE FUNCTION public\.mark_lm_maritime_pilot_milestone_v1\([\s\S]*?\$function\$([\s\S]*?)\$function\$;/);
  assert.ok(routine, "milestone RPC is defined in the Maritime migration");
  assert.match(routine[1], /UPDATE public\.lm_maritime_pilot_participants[\s\S]*?RETURNING \* INTO v_participant/);
  assert.match(routine[1], /INSERT INTO public\.lm_web_funnel_events/);
  assert.match(routine[1], /format\('maritime:%s:%s', p_participant_id, v_event_name\)/);
  assert.match(routine[1], /p_milestone IS DISTINCT FROM 'successful_use'/);
  assert.match(routine[1], /FROM public\.lm_maritime_pilot_participants[\s\S]*?FOR UPDATE/);
  assert.match(routine[1], /v_participant\.first_response_at IS NULL/);
  assert.match(routine[1], /v_at := GREATEST\(v_at, v_participant\.first_response_at \+ interval '1 microsecond'\)/);
  assert.match(routine[1], /IF v_at > v_participant\.first_response_at \+ interval '7 days' THEN/);
  assert.doesNotMatch(routine[1], /ON CONFLICT DO NOTHING/);
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

test("landing_primary_cta_is_email_and_never_requires_telegram",()=>{
  const html=renderMaritimeLanding({source:"referral",language:"en"});
  assert.match(html,/action="\/auth\/maritime\/email"/);assert.match(html,/type="email"/);
  assert.match(html,/Life Manager Cloud/);assert.match(html,/work, money, everyday tasks, body, and mind/i);
  assert.doesNotMatch(html,/\bpilot\b/i);
  assert.doesNotMatch(html,/<input[^>]+name="(?:goal|budget|telegram)"/);
  assert.doesNotMatch(html,/href="\/maritime\/start/);assert.match(html,/Telegram is optional/);
});
test("active Life Manager Cloud shows a transparent, tenant-owned Capafy connection flow",()=>{
  const html=renderMaritimeLanding({language:"en",user:{email:"person@example.invalid",csrf:"a".repeat(64)},state:"active",capafyStatus:"not_connected"});
  assert.match(html,/Capafy developer account/);assert.match(html,/future product preparation and publication/);
  assert.match(html,/data-action="capafy-connect"/);assert.match(html,/maritime-capafy-autonomy-v1/);
  assert.match(html,/does not publish anything or guarantee sales/i);
  assert.match(html,/\/maritime\/capafy\/connect\/start/);assert.match(html,/\/maritime\/capafy\/connect\/verify/);
  assert.doesNotMatch(html,/\bpilot\b/i);assert.doesNotMatch(html,/CAPAFY_ACCESS_TOKEN|am_sk_/i);
});
test("Capafy email verification step submits in Chromium before the code is available", { skip: !CHROMIUM_PATH && "Chromium executable is not installed" }, async () => {
  const browser = await chromium.launch({ headless: true, executablePath: CHROMIUM_PATH,
    args: ["--no-sandbox", "--disable-dev-shm-usage"] });
  try {
    const page = await browser.newPage();
    await page.setContent(renderMaritimeLanding({ language: "en",
      user: { email: "person@example.invalid", csrf: "a".repeat(64) }, state: "active", capafyStatus: "not_connected" }));
    await page.evaluate(() => {
      window.__capafyRequests = [];
      window.fetch = async (url, options) => {
        window.__capafyRequests.push({ url, body: JSON.parse(options.body) });
        return { ok: true, status: 202, json: async () => ({ status: "check_email", challengeRef: "opaque-challenge" }) };
      };
    });
    await page.locator("#capafy-email").fill("seller@example.com");
    await page.getByRole("button", { name: "Send verification code" }).click();
    await page.waitForFunction(() => window.__capafyRequests.length === 1, undefined, { timeout: 2000 });
    assert.deepEqual(await page.evaluate(() => window.__capafyRequests[0]), {
      url: "/maritime/capafy/connect/start", body: { email: "seller@example.com" },
    });
    assert.equal(await page.locator("#capafy-verification").isVisible(), true);
    assert.equal(await page.locator("#capafy-code").isDisabled(), false);
  } finally {
    await browser.close();
  }
});
test("connected Capafy account is shown without its identifier and can be unlinked",()=>{
 const html=renderMaritimeLanding({language:"en",user:{email:"person@example.invalid",csrf:"a".repeat(64)},state:"active",capafyStatus:"connected"});
 assert.match(html,/Capafy developer account connected/);assert.match(html,/data-action="capafy-disconnect"/);
 assert.match(html,/\/maritime\/capafy\/connect\/disconnect/);assert.doesNotMatch(html,/account:\/\/capafy\/|019d3c7f|am_sk_/i);
});
test("verified_landing_has_csrf_activation_and_escapes_identity",()=>{
  const html=renderMaritimeLanding({source:"x",language:"ja",user:{email:'person<bad>@example.invalid',csrf:"a".repeat(64)},state:null});
  assert.match(html,/data-action="activate"/);assert.match(html,/data-csrf="a{64}"/);
  assert.match(html,/person&lt;bad&gt;@example.invalid/);assert.doesNotMatch(html,/person<bad>/);
  assert.doesNotMatch(html,/action="\/auth\/maritime\/email"/);assert.match(html,/目標・予算の入力は必須ではありません/);
});
test("paused_or_uncertain_landing_does_not_offer_activation",()=>{
  for(const state of ["paused","effect_unknown","provisioning","pending","active"]){
    const html=renderMaritimeLanding({language:"en",user:{email:"person@example.invalid",csrf:"a".repeat(64)},state});
    assert.doesNotMatch(html,/<button[^>]+data-action="activate"/,state);
  }
});

test("landing_inline_script_is_valid_javascript",()=>{
  const {Script}=require("node:vm");
  for(const html of [renderMaritimeLanding({source:"x",language:"ja"}),
    renderMaritimeLanding({language:"en",user:{email:"person@example.invalid",csrf:"a".repeat(64)},state:"active",capafyStatus:"not_connected"}),
    renderMaritimeLanding({language:"en",user:{email:"person@example.invalid",csrf:"a".repeat(64)},state:"active",capafyStatus:"connected"})]){
    const script=html.match(/<script>([\s\S]*?)<\/script>/);assert.ok(script);assert.doesNotThrow(()=>new Script(script[1]));
  }
});


test('email manager has a CSRF-bound stop control and describes retained inflight results',()=>{
 const html=renderMaritimeLanding({language:'ja',user:{email:'person@example.invalid',csrf:'fixture-csrf'},state:'active'});
 assert.match(html,/data-action="stop"/);assert.match(html,/fixture-csrf/);assert.match(html,/maritime\/stop/);
 assert.match(html,/進行中/);assert.match(html,/削除/);
});


test('manager milestones hash participant and occurrence keys and mark founder activity internal',async()=>{
 const uid='lm_11111111-1111-4111-8111-111111111111',events=[];
 const store=createMaritimeDistributionStore({env:{LM_UID_SECRET:'fixture-secret',LM_MARITIME_INTERNAL_UIDS:uid},supaUrl:'https://fixture.invalid',supaKey:'fixture',recordEventImpl:async event=>{events.push(event);return true;}});
 assert.equal(await store.recordManagerEvent('maritime_work_completed',uid,{eventKey:'job:a',source:'instagram',attribution:{utm_source:'instagram',utm_medium:'dm',email:'private@example.invalid',token:'private-token'}}),true);
 await store.recordManagerEvent('maritime_work_completed',uid,{eventKey:'job:a',source:'instagram'});
 await store.recordManagerEvent('maritime_work_completed',uid,{eventKey:'job:b',source:'instagram'});
 assert.equal(events[0].sourceEventId,events[1].sourceEventId);assert.notEqual(events[0].sourceEventId,events[2].sourceEventId);
 assert.equal(events[0].sourceEventId.length<=128,true);assert.equal(events[0].sourceObjectId.length,64);assert.equal(events[0].audienceKind,'internal');
 assert.equal(events[0].uid,null);assert.equal(events[0].attribution.utm_medium,'dm');assert.doesNotMatch(JSON.stringify(events),/private|lm_11111111|job:a/);
 assert.equal(await store.recordManagerEvent('unknown',uid,{source:'instagram'}),false);
});

test('manager email consent event reuses HMAC identity and web attribution',async()=>{
 const uid='lm_11111111-1111-4111-8111-111111111111',events=[];
 const store=createMaritimeDistributionStore({env:{LM_UID_SECRET:'fixture-secret'},recordEventImpl:async event=>{events.push(event);return true;},now:()=>Date.parse('2026-10-21T00:00:00Z')});
 assert.equal(await store.recordConsentEvent(uid,'instagram','web'),true);
 assert.equal(events[0].eventName,'maritime_consent');assert.equal(events[0].uid,null);
 assert.equal(events[0].sourceObjectId,store.participantId(uid));assert.equal(events[0].sourceEventId,`maritime:${store.participantId(uid)}:maritime_consent`);
 assert.deepEqual(events[0].attribution,{utm_source:'maritime-instagram',utm_medium:'web',utm_campaign:'the-first-1000'});
});

test('manager consent revocation event reuses HMAC identity and web attribution',async()=>{
 const uid='lm_11111111-1111-4111-8111-111111111111',events=[];
 const store=createMaritimeDistributionStore({env:{LM_UID_SECRET:'fixture-secret'},recordEventImpl:async event=>{events.push(event);return true;}});
 assert.equal(await store.recordConsentRevokedEvent(uid,'referral','web'),true);
 assert.equal(events[0].eventName,'maritime_consent_revoked');assert.equal(events[0].uid,null);
 assert.equal(events[0].sourceObjectId,store.participantId(uid));
 assert.deepEqual(events[0].attribution,{utm_source:'maritime-referral',utm_medium:'web',utm_campaign:'the-first-1000'});
});
